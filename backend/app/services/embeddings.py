"""Lightweight local embeddings and ChromaDB management.

This implementation intentionally does NOT use Gemini embeddings or
download a local ML model. It creates deterministic feature-hashing
vectors using only Python's standard library, which keeps memory usage
very low on Render Free.
"""

import asyncio
import hashlib
import math
import re
from typing import List

import chromadb

from app.config import CHROMA_PERSIST_DIR
from app.models import Fact


# -------------------------------------------------------------------
# ChromaDB
# -------------------------------------------------------------------

chroma_client = chromadb.PersistentClient(
    path=CHROMA_PERSIST_DIR
)

facts_collection = chroma_client.get_or_create_collection(
    name="facts",
    metadata={"hnsw:space": "cosine"},
)


# -------------------------------------------------------------------
# Lightweight embedding configuration
# -------------------------------------------------------------------

# Fixed vector size.
# Larger = slightly better representation but more storage.
EMBEDDING_DIMENSION = 256


# -------------------------------------------------------------------
# Text helpers
# -------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Convert text into simple normalized tokens."""
    text = text.lower()

    tokens = re.findall(
        r"[a-z0-9]+",
        text,
    )

    return tokens


def _hash_token(token: str) -> int:
    """Return a deterministic integer hash for a token."""
    digest = hashlib.sha256(
        token.encode("utf-8")
    ).digest()

    return int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    )


def _token_weight(token: str) -> float:
    """Give longer/more specific tokens slightly more weight."""
    length = len(token)

    if length >= 10:
        return 1.5

    if length >= 6:
        return 1.25

    return 1.0


# -------------------------------------------------------------------
# Embedding generation
# -------------------------------------------------------------------

def _create_embedding(text: str) -> List[float]:
    """
    Create a deterministic lightweight vector.

    This is feature hashing rather than an ML embedding model.
    It requires no external model, no API call, and almost no RAM.
    """

    vector = [0.0] * EMBEDDING_DIMENSION

    tokens = _tokenize(text)

    if not tokens:
        return vector

    for token in tokens:
        token_hash = _hash_token(token)

        index = token_hash % EMBEDDING_DIMENSION

        # Use another hash bit to determine the sign.
        sign = 1.0 if (token_hash >> 8) % 2 == 0 else -1.0

        weight = _token_weight(token)

        vector[index] += sign * weight

    # Add lightweight bigram features.
    for first, second in zip(tokens, tokens[1:]):
        bigram = f"{first}_{second}"

        bigram_hash = _hash_token(bigram)

        index = bigram_hash % EMBEDDING_DIMENSION

        sign = (
            1.0
            if (bigram_hash >> 8) % 2 == 0
            else -1.0
        )

        vector[index] += sign * 0.5

    # L2 normalize for cosine similarity.
    magnitude = math.sqrt(
        sum(value * value for value in vector)
    )

    if magnitude > 0:
        vector = [
            value / magnitude
            for value in vector
        ]

    return vector


async def _embed_batch(
    batch: List[str],
) -> List[List[float]]:
    """Generate lightweight local embeddings."""

    if not batch:
        return []

    try:
        return await asyncio.to_thread(
            lambda: [
                _create_embedding(text)
                for text in batch
            ]
        )

    except Exception as exc:
        print(
            f"[Embeddings] Local embedding error: {exc}",
            flush=True,
        )
        return []


async def generate_embeddings(
    texts: List[str],
) -> List[List[float]]:
    """
    Generate embeddings for arbitrary text.

    Kept as a public function so other parts of the application
    can use the same embedding implementation if needed.
    """

    if not texts:
        return []

    return await _embed_batch(texts)


# -------------------------------------------------------------------
# ChromaDB indexing
# -------------------------------------------------------------------

async def upsert_facts_to_vector_db(
    facts: List[Fact],
) -> None:
    """
    Generate lightweight local embeddings and store facts in ChromaDB.

    No Gemini embedding API is used here.
    """

    if not facts:
        return

    # Check which facts are already indexed.
    existing = set()

    try:
        document_id = facts[0].document_id

        result = facts_collection.get(
            where={
                "document_id": document_id
            }
        )

        existing = set(
            result.get("ids", [])
        )

    except Exception as exc:
        print(
            f"[Embeddings] Existing check note: {exc}",
            flush=True,
        )

    facts_to_embed = [
        fact
        for fact in facts
        if fact.id not in existing
    ]

    if not facts_to_embed:
        print(
            f"[Embeddings] All "
            f"{len(facts)} facts already indexed!",
            flush=True,
        )
        return

    print(
        f"[Embeddings] Indexing "
        f"{len(facts_to_embed)} new facts "
        f"({len(existing)} already indexed)...",
        flush=True,
    )

    # Keep batches small for Render Free.
    batch_size = 50

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
                f"received {len(embeddings)}.",
                flush=True,
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

        await asyncio.sleep(0.05)


def build_fact_embedding_string(
    fact: Fact,
) -> str:
    """Build the text representation used for embeddings."""

    parts = [
        f"Subject: {fact.subject}",
        f"Predicate: {fact.predicate}",
        f"Value: {fact.value}",
    ]

    if fact.unit:
        parts.append(
            f"Unit: {fact.unit}"
        )

    if fact.time_label:
        parts.append(
            f"Time: {fact.time_label}"
        )

    if fact.scope:
        parts.append(
            f"Scope: {fact.scope}"
        )

    return " | ".join(parts)
