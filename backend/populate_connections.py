import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from sqlalchemy.future import select
from app.database import async_session
from app.models import Fact, Document, FactRelationship
from app.services.embeddings import upsert_facts_to_vector_db, facts_collection
from app.services.cross_check import analyze_document_facts

async def run_population():
    print("==================================================")
    print("STEP 1: Checking Existing Facts & Documents")
    print("==================================================")
    
    async with async_session() as db:
        # 1. Fetch all facts
        stmt_facts = select(Fact)
        res_facts = await db.execute(stmt_facts)
        facts = res_facts.scalars().all()
        print(f"Total facts in SQLite: {len(facts)}")
        
        # 2. Fetch completed documents
        stmt_docs = select(Document).where(Document.status == "done")
        res_docs = await db.execute(stmt_docs)
        docs = res_docs.scalars().all()
        print(f"Total completed documents: {len(docs)}")

    print("\n==================================================")
    print("STEP 2: Indexing Facts into Vector DB (Local MiniLM)")
    print("==================================================")
    
    # We embed grouped by document
    docs_map = {}
    for f in facts:
        docs_map.setdefault(f.document_id, []).append(f)
        
    for doc_id, doc_facts in docs_map.items():
        print(f"Embedding doc {doc_id} ({len(doc_facts)} facts)...")
        await upsert_facts_to_vector_db(doc_facts)

    print(f"\nVector DB collection count: {facts_collection.count()}")

    print("\n==================================================")
    print("STEP 3: Cross-Checking Documents & Mapping Connections")
    print("==================================================")

    for doc in docs:
        print(f"\nAnalyzing connections for document: {doc.filename} ({doc.id})")
        async with async_session() as db:
            await analyze_document_facts(doc.id, db)

    print("\n==================================================")
    print("STEP 4: Verifying Relationship Counts")
    print("==================================================")
    
    async with async_session() as db:
        stmt_rels = select(FactRelationship)
        res_rels = await db.execute(stmt_rels)
        all_rels = res_rels.scalars().all()
        
        corroborates = sum(1 for r in all_rels if r.relationship_type == "CORROBORATES")
        contradicts = sum(1 for r in all_rels if r.relationship_type == "CONTRADICTS")
        context_diff = sum(1 for r in all_rels if r.relationship_type == "CONTEXTUALLY_DIFFERS")
        
        print(f"TOTAL RELATIONSHIPS CREATED: {len(all_rels)}")
        print(f" - CORROBORATES: {corroborates}")
        print(f" - CONTRADICTS: {contradicts}")
        print(f" - CONTEXTUALLY_DIFFERS: {context_diff}")

if __name__ == "__main__":
    asyncio.run(run_population())
