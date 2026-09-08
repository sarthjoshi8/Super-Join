import asyncio
import json
import uuid
from typing import List
from google import genai
from google.genai import types
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
import traceback

from app.models import Fact, FactRelationship
from app.services.embeddings import facts_collection, genai_client
from app.config import GEMINI_MODEL

class RelationshipAdjudication(BaseModel):
    pair_id: str
    relationship: str
    reason: str

class BatchAdjudicationResult(BaseModel):
    results: list[RelationshipAdjudication]

async def analyze_document_facts(document_id: str, db: Session):
    """
    Find relationships between facts in this document and facts in other documents.
    """
    stmt = select(Fact).where(Fact.document_id == document_id)
    result = await db.execute(stmt)
    document_facts = result.scalars().all()
    
    print(f"Found {len(document_facts)} facts for document {document_id}")
    if not document_facts:
        return

    # 1. Collect all potential pairs to adjudicate
    pairs_to_adjudicate = []
    
    for fact in document_facts:
        try:
            chroma_result = facts_collection.get(ids=[fact.id], include=["embeddings"])
            embeddings = chroma_result.get("embeddings")
            if embeddings is None or len(embeddings) == 0:
                continue
            embedding_vector = embeddings[0]
            if embedding_vector is None or len(embedding_vector) == 0:
                continue
                
            # Query top 5 similar facts from OTHER documents
            search_result = facts_collection.query(
                query_embeddings=[list(embedding_vector)],
                n_results=5,
                where={"document_id": {"$ne": document_id}},
                include=["distances"]
            )
            
            ids_list = search_result.get("ids") if search_result else None
            dists_list = search_result.get("distances") if search_result else None
            if not ids_list or len(ids_list) == 0 or len(ids_list[0]) == 0:
                continue

            # Filter candidate facts by semantic vector distance (<= 0.38 for local MiniLM embeddings)
            raw_ids = search_result["ids"][0]
            raw_dists = search_result["distances"][0] if dists_list and len(dists_list[0]) > 0 else []
            
            similar_ids = [
                fid for fid, dist in zip(raw_ids, raw_dists)
                if dist <= 0.38
            ] if raw_dists else raw_ids
            
            if not similar_ids:
                continue
            
            stmt_similar = select(Fact).where(Fact.id.in_(similar_ids))
            sim_res = await db.execute(stmt_similar)
            similar_facts = sim_res.scalars().all()
            
            for sim_fact in similar_facts:
                # Skip if a relationship already exists
                stmt_existing = select(FactRelationship).where(
                    ((FactRelationship.fact_a_id == fact.id) & (FactRelationship.fact_b_id == sim_fact.id)) |
                    ((FactRelationship.fact_a_id == sim_fact.id) & (FactRelationship.fact_b_id == fact.id))
                )
                existing = (await db.execute(stmt_existing)).scalars().first()
                
                if not existing:
                    pairs_to_adjudicate.append((fact, sim_fact))
                    
        except Exception as e:
            print(f"Error querying pairs for fact {fact.id}: {e}")

    print(f"Total relevant pairs to adjudicate: {len(pairs_to_adjudicate)}")
    
    # 2. Batch process pairs (1 batch at a time to prevent rate limits)
    batch_size = 20
    batches = [
        pairs_to_adjudicate[i:i + batch_size]
        for i in range(0, len(pairs_to_adjudicate), batch_size)
    ]
    semaphore = asyncio.Semaphore(1)

    async def _run_batch(batch):
        async with semaphore:
            await process_batch(batch, db)
            await db.commit()
            await asyncio.sleep(1.0)  # Gentle pacing between batches

    for b in batches:
        await _run_batch(b)

def heuristic_adjudicate(fact_a: Fact, fact_b: Fact) -> tuple[str, str]:
    """Fallback adjudication when LLM is unavailable or rate-limited."""
    sub_a = (fact_a.subject or "").lower().strip()
    sub_b = (fact_b.subject or "").lower().strip()
    val_a = (fact_a.value or "").lower().strip()
    val_b = (fact_b.value or "").lower().strip()
    time_a = (fact_a.time_label or "").lower().strip()
    time_b = (fact_b.time_label or "").lower().strip()
    scope_a = (fact_a.scope or "").lower().strip()
    scope_b = (fact_b.scope or "").lower().strip()
    
    words_a = set(sub_a.split())
    words_b = set(sub_b.split())
    overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
    
    if overlap < 0.25 and sub_a not in sub_b and sub_b not in sub_a:
        return "UNRELATED", "Different subjects"
        
    same_time = (time_a == time_b) or not time_a or not time_b
    same_scope = (scope_a == scope_b) or not scope_a or not scope_b
    
    if val_a == val_b:
        if same_time and same_scope:
            return "CORROBORATES", f"Both sources report consistent value ({fact_a.value}) for {fact_a.subject}."
        else:
            return "CONTEXTUALLY_DIFFERS", f"Same metric ({fact_a.value}) but spans different periods or scopes ({time_a or 'general'} vs {time_b or 'general'})."
    else:
        if same_time and same_scope:
            return "CONTRADICTS", f"Discrepancy in reported values: '{fact_a.value}' vs '{fact_b.value}' for {fact_a.subject}."
        else:
            return "CONTEXTUALLY_DIFFERS", f"Values differ ('{fact_a.value}' vs '{fact_b.value}') due to different periods or scopes ({time_a or 'general'} vs {time_b or 'general'})."

async def process_batch(batch: List[tuple[Fact, Fact]], db: Session):
    """Process a batch of fact pairs with Gemini, falling back to heuristic logic if rate-limited."""
    if not batch:
        return
        
    pair_map = {}
    prompt_lines = [
        "You are a financial and semantic fact-checking assistant. Given pairs of statements extracted from different documents, determine their logical relationship.",
        "Relationship must be exactly one of: 'CORROBORATES', 'CONTRADICTS', 'CONTEXTUALLY_DIFFERS', 'UNRELATED'.",
        "Return a JSON list of results. Each result must contain the pair_id, relationship, and reason.",
        ""
    ]
    
    for fact_a, fact_b in batch:
        pid = str(uuid.uuid4())
        pair_map[pid] = (fact_a, fact_b)
        
        prompt_lines.append(f"--- PAIR {pid} ---")
        prompt_lines.append(f"Fact A: Subject: {fact_a.subject} | Predicate: {fact_a.predicate} | Value: {fact_a.value} | Context: {fact_a.raw_statement}")
        prompt_lines.append(f"Fact B: Subject: {fact_b.subject} | Predicate: {fact_b.predicate} | Value: {fact_b.value} | Context: {fact_b.raw_statement}")
        prompt_lines.append("")

    prompt = "\n".join(prompt_lines)
    
    llm_succeeded = False
    for attempt in range(1, 3):
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BatchAdjudicationResult,
                temperature=0.1
            )
            response = await asyncio.to_thread(
                lambda: genai_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
            )
            
            result_data = json.loads(response.text)
            results = result_data.get("results", [])
            
            for res in results:
                pid = res.get("pair_id")
                rel_type = res.get("relationship", "UNRELATED")
                reason = res.get("reason", "No reason provided")
                
                if pid in pair_map:
                    fa, fb = pair_map[pid]
                    if rel_type != "UNRELATED":
                        rel = FactRelationship(
                            fact_a_id=fa.id,
                            fact_b_id=fb.id,
                            relationship_type=rel_type,
                            reason=reason,
                            determined_by="llm_judge",
                            match_confidence=1.0
                        )
                        db.add(rel)
            llm_succeeded = True
            break
            
        except Exception as e:
            err_str = str(e)
            print(f"[CrossCheck] Gemini adjudication attempt {attempt} issue: {err_str[:120]}")
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or attempt == 2:
                print("[CrossCheck] Applying fallback heuristic adjudication for batch...")
                break
            await asyncio.sleep(2)

    if not llm_succeeded:
        # Fallback to heuristic adjudication
        for fa, fb in batch:
            rel_type, reason = heuristic_adjudicate(fa, fb)
            if rel_type != "UNRELATED":
                rel = FactRelationship(
                    fact_a_id=fa.id,
                    fact_b_id=fb.id,
                    relationship_type=rel_type,
                    reason=reason,
                    determined_by="heuristic_matcher",
                    match_confidence=0.85
                )
                db.add(rel)
