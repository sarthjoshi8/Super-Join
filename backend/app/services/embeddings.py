"""Vector embeddings and ChromaDB management."""

import os
import re
import json
import asyncio
import hashlib
import chromadb
from google import genai
from google.genai import types
from typing import List, Optional

from app.config import CHROMA_PERSIST_DIR, GEMINI_API_KEY, GEMINI_EMBEDDING_MODEL
from app.models import Fact

import chromadb.utils.embedding_functions as ef

# Initialize ChromaDB persistent client
chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

# Initialize high-performance local embedding function (runs offline, 0 quota limits)
local_ef = ef.DefaultEmbeddingFunction()

# Get or create collection for facts
facts_collection = chroma_client.get_or_create_collection(
    name="facts",
    metadata={"hnsw:space": "cosine"},
    embedding_function=local_ef
)

# Initialize Gemini Client
genai_client = genai.Client(api_key=GEMINI_API_KEY)


def build_fact_embedding_string(fact: Fact) -> str:
    """Build the string to be embedded from structured fact properties."""
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
    """Embed a batch of texts using the local embedding function without API quota constraints."""
    if not batch:
        return []
    try:
        embeddings = await asyncio.to_thread(local_ef, batch)
        return [[float(x) for x in emb] for emb in embeddings]
    except Exception as e:
        print(f"[Embeddings] Local embedding error: {e}")
        return []


async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for all texts using the local embedding model."""
    if not texts:
        return []
    return await _embed_batch(texts)


async def upsert_facts_to_vector_db(facts: List[Fact]) -> None:
    """Embed and upsert a list of Fact ORM objects into ChromaDB incrementally.
    Skips facts that are already indexed in ChromaDB.
    """
    if not facts:
        return

    # Check which facts already exist in ChromaDB to avoid redundant embedding
    existing = set()
    try:
        doc_id = facts[0].document_id
        res = facts_collection.get(where={"document_id": doc_id})
        existing = set(res.get("ids", []))
    except Exception as e:
        print(f"[Embeddings] Existing check note: {e}")

    facts_to_embed = [f for f in facts if f.id not in existing]
    if not facts_to_embed:
        print(f"[Embeddings] All {len(facts)} facts already indexed in vector DB!")
        return

    print(f"[Embeddings] Indexing {len(facts_to_embed)} new facts ({len(existing)} already indexed)...")
    batch_size = 100
    for i in range(0, len(facts_to_embed), batch_size):
        chunk = facts_to_embed[i : i + batch_size]
        chunk_ids = [f.id for f in chunk]
        chunk_texts = [build_fact_embedding_string(f) for f in chunk]
        chunk_metadatas = [{"document_id": f.document_id} for f in chunk]

        chunk_embeddings = await _embed_batch(chunk_texts)
        if chunk_embeddings:
            facts_collection.upsert(
                ids=chunk_ids,
                embeddings=chunk_embeddings,
                metadatas=chunk_metadatas,
                documents=chunk_texts
            )
            print(f"    [Embeddings] Upserted {min(i + batch_size, len(facts_to_embed))}/{len(facts_to_embed)} facts to vector DB", flush=True)

        if i + batch_size < len(facts_to_embed):
            await asyncio.sleep(0.05)
