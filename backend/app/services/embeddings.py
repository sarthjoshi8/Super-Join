"""Vector embeddings and ChromaDB management using Gemini embeddings."""

import asyncio
from typing import List

import chromadb
from google import genai

from app.config import (
    CHROMA_PERSIST_DIR,
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
)
from app.models import Fact


# Initialize ChromaDB persistent client.
chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)


# Get or create the facts collection.
# We provide embeddings ourselves, so Chroma does not download
# the local all-MiniLM-L6-v2 model.
facts_collection = chroma_client.get_or_create_collection(
    name="facts",
    metadata={"hnsw:space": "cosine"},
)


# Initialize Gemini client.
genai_client = genai.Client(api_key=GEMINI_API_KEY)


def build_fact_embedding_string(fact: Fact) -> str:
    """Build the text representation used for semantic embeddings."""
    parts = [
        f"Subject: {fact.subject}",
        f"Predicate: {fact.predicate}",
        f"Value: {fact.value}",
    ]

    if fact.unit:
        parts.append(f"Unit: {fact.unit}")

    if fact.time_label:
        parts.append(f"Time: {fact.time_label}")

    if fact.scope:
        parts.append(f"Scope: {fact.scope}")

    return " | ".join(parts)


async def _embed_batch(batch: List[str]) -> List[List[float]]:
    """Generate embeddings using Gemini's embedding API."""
    if not batch:
        return []

    try:
        response = await asyncio.to_thread(
            genai_client.models.embed_content,
            model=GEMINI_EMBEDDING_MODEL,
            contents=batch,
        )

        embeddings = []

        for item in response.embeddings:
            embeddings.append(
                [float(value) for value in item.values]
            )

        return embeddings

    except Exception as exc:
        print(f"[Embeddings] Gemini embedding error: {exc}")
        return []


async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate Gemini embeddings for a list of texts."""
    if not texts:
        return []

    return await _embed_batch(texts)


async def upsert_facts_to_vector_db(facts: List[Fact]) -> None:
    """
    Generate embeddings for facts and store them in ChromaDB.

    Gemini is used for embeddings instead of Chroma's local
    all-MiniLM-L6-v2 model, significantly reducing memory usage
    on low-memory hosting environments such as Render Free.
    """
    if not facts:
        return

    # Check which facts are already indexed.
    existing = set()

    try:
        document_id = facts[0].document_id

        result = facts_collection.get(
            where={"document_id": document_id}
        )

        existing = set(result.get("ids", []))

    except Exception as exc:
        print(
            f"[Embeddings] Existing check note: {exc}"
        )

    facts_to_embed = [
        fact
        for fact in facts
        if fact.id not in existing
    ]

    if not facts_to_embed:
        print(
            f"[Embeddings] All {len(facts)} facts already indexed!"
        )
        return

    print(
        f"[Embeddings] Indexing "
        f"{len(facts_to_embed)} new facts "
        f"({len(existing)} already indexed)...",
        flush=True,
    )

    # Small batches keep memory usage low.
    batch_size = 20

    for i in range(
        0,
        len(facts_to_embed),
        batch_size,
    ):
        batch = facts_to_embed[
            i : i + batch_size
        ]

        batch_ids = [
            fact.id
            for fact in batch
        ]

        batch_texts = [
            build_fact_embedding_string(fact)
            for fact in batch
        ]

        batch_metadatas = [
            {
                "document_id": fact.document_id
            }
            for fact in batch
        ]

        embeddings = await _embed_batch(
            batch_texts
        )

        if len(embeddings) != len(batch):
            print(
                "[Embeddings] Embedding count mismatch. "
                f"Expected {len(batch)}, "
                f"received {len(embeddings)}."
            )
            continue

        facts_collection.upsert(
            ids=batch_ids,
            embeddings=embeddings,
            metadatas=batch_metadatas,
            documents=batch_texts,
        )

        processed = min(
            i + batch_size,
            len(facts_to_embed),
        )

        print(
            f"    [Embeddings] Upserted "
            f"{processed}/{len(facts_to_embed)} facts",
            flush=True,
        )

        await asyncio.sleep(0.1)