"""PDF processing, chunking, and fact extraction service."""

import asyncio
import hashlib
import json
from typing import List, Dict, Any, Optional

import fitz  # PyMuPDF
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    MAX_CHUNK_CHARS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)
from app.models import Document, Fact
from app.services.embeddings import upsert_facts_to_vector_db


genai_client = genai.Client(api_key=GEMINI_API_KEY)


# ── Pydantic Schema for Gemini Structured Output ───────────────────────


class ExtractedFact(BaseModel):
    subject: str = Field(
        description="The main entity the fact is about."
    )

    predicate: str = Field(
        description="What is being stated about the subject."
    )

    value: str = Field(
        description="The stated value, kept as a string."
    )

    numeric_value: Optional[float] = Field(
        description="Parsed numeric value if applicable.",
        default=None,
    )

    unit: Optional[str] = Field(
        description="Unit of measurement.",
        default=None,
    )

    time_start: Optional[str] = Field(
        description="Structured start date if parseable.",
        default=None,
    )

    time_end: Optional[str] = Field(
        description="Structured end date if parseable.",
        default=None,
    )

    time_label: Optional[str] = Field(
        description="Original free-text period label.",
        default=None,
    )

    scope: Optional[str] = Field(
        description="Scope of the metric.",
        default=None,
    )

    raw_statement: str = Field(
        description="Exact sentence or phrase proving the fact."
    )

    is_partial: bool = Field(
        description="True when the fact is incomplete or ambiguous.",
        default=False,
    )

    note: Optional[str] = Field(
        description="Notes about ambiguity or assumptions.",
        default=None,
    )

    confidence: float = Field(
        description="Confidence score from 0.0 to 1.0.",
        default=1.0,
    )


class FactExtractionResponse(BaseModel):
    facts: List[ExtractedFact]


# ── File Hash ───────────────────────────────────────────────────────────


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(file_bytes).hexdigest()


# ── PDF Extraction ──────────────────────────────────────────────────────


async def extract_pdf_chunks(filepath: str) -> List[Dict[str, Any]]:
    """
    Extract PDF text into bounded-size chunks.

    PDF work happens in a worker thread so it does not block FastAPI.
    """

    def _extract():
        chunks = []

        with fitz.open(filepath) as doc:
            current_chunk_text = ""
            current_start_page = 1

            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()

                if not text:
                    continue

                if (
                    current_chunk_text
                    and len(current_chunk_text) + len(text)
                    > MAX_CHUNK_CHARS
                ):
                    chunks.append(
                        {
                            "text": current_chunk_text,
                            "page_number": current_start_page,
                        }
                    )

                    current_chunk_text = text + "\n"
                    current_start_page = page_num

                else:
                    current_chunk_text += text + "\n"

            if current_chunk_text:
                chunks.append(
                    {
                        "text": current_chunk_text,
                        "page_number": current_start_page,
                    }
                )

        return chunks

    return await asyncio.to_thread(_extract)


# ── Gemini Fact Extraction ──────────────────────────────────────────────


async def extract_facts_from_chunk_with_gemini(
    chunk_text: str,
) -> List[ExtractedFact]:
    """Extract structured facts from one chunk using Gemini."""

    prompt = f"""
Extract all verifiable facts from the following document text.

Facts may include:
- Skills, technologies and tools
- Roles, job titles, companies and institutions
- Dates, durations and time periods
- Metrics, numbers and quantities
- Degrees, certifications and achievements
- Locations
- Stated attributes about people, companies or products

Rules:
- Follow the exact JSON schema provided.
- Do not infer information that is not clearly stated.
- If a value is implied but not explicit, set is_partial=true.
- For non-numeric facts use numeric_value=null.
- Extract ONLY facts.

TEXT:
{chunk_text}
"""

    for attempt in range(1, 6):
        try:
            response = await asyncio.to_thread(
                genai_client.models.generate_content,
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FactExtractionResponse,
                    temperature=0.1,
                ),
            )

            data = json.loads(response.text)

            validated = FactExtractionResponse.model_validate(data)

            return validated.facts

        except Exception as exc:
            if attempt == 5:
                print(
                    f"[Ingestion] Gemini extraction failed "
                    f"after {attempt} attempts: {exc}"
                )
                return []

            print(
                f"[Ingestion] Gemini extraction attempt "
                f"{attempt} failed: {exc}"
            )

            error_text = str(exc)

            if (
                "RESOURCE_EXHAUSTED" in error_text
                or "429" in error_text
            ):
                await asyncio.sleep(65)

            else:
                await asyncio.sleep(5)

            if attempt == 1 and "schema" in error_text.lower():
                prompt = (
                    "Previous attempt failed due to JSON schema "
                    "validation. Ensure strict schema compliance.\n"
                    + prompt
                )

    return []


# ── Main Processing Pipeline ────────────────────────────────────────────


async def process_document_task(
    doc_id: str,
    filepath: str,
    session: AsyncSession,
    progress_store: Optional[dict] = None,
) -> None:
    """
    Process one PDF using a memory-efficient sequential pipeline.

    Important for low-memory hosting such as Render Free:
    - PDF chunks are processed one at a time.
    - Gemini calls are sequential.
    - Facts are committed per chunk.
    - Embeddings are created per chunk.
    - We do not keep every document fact in RAM.
    """

    try:
        # ── Mark document as processing ────────────────────────────────

        await session.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(
                status="processing",
                error_message=None,
            )
        )

        await session.commit()

        # ── Extract PDF chunks ─────────────────────────────────────────

        chunks = await extract_pdf_chunks(filepath)

        total_chunks = len(chunks)

        print(
            f"[Ingestion] Document {doc_id}: "
            f"{total_chunks} chunk(s)"
        )

        if progress_store is not None:
            progress_store[doc_id] = {
                "stage": "extracting",
                "done": 0,
                "total": total_chunks,
            }

        total_facts = 0

        # ── Process ONE chunk at a time ────────────────────────────────

        for index, chunk in enumerate(chunks, start=1):

            print(
                f"[Ingestion] Document {doc_id}: "
                f"processing chunk {index}/{total_chunks}"
            )

            facts = await extract_facts_from_chunk_with_gemini(
                chunk["text"]
            )

            chunk_db_facts = []

            # ── Store facts from this chunk ────────────────────────────

            for extracted_fact in facts:
                db_fact = Fact(
                    document_id=doc_id,
                    subject=extracted_fact.subject,
                    predicate=extracted_fact.predicate,
                    value=extracted_fact.value,
                    numeric_value=extracted_fact.numeric_value,
                    unit=extracted_fact.unit,
                    time_start=extracted_fact.time_start,
                    time_end=extracted_fact.time_end,
                    time_label=extracted_fact.time_label,
                    scope=extracted_fact.scope,
                    raw_statement=extracted_fact.raw_statement,
                    is_partial=extracted_fact.is_partial,
                    note=extracted_fact.note,
                    page_number=chunk["page_number"],
                    confidence=extracted_fact.confidence,
                )

                session.add(db_fact)
                chunk_db_facts.append(db_fact)

            if chunk_db_facts:
                await session.commit()

                # Refresh only this chunk's facts.
                for db_fact in chunk_db_facts:
                    await session.refresh(db_fact)

                # ── Embed only this chunk ──────────────────────────────

                if progress_store is not None:
                    progress_store[doc_id]["stage"] = "embedding"

                await upsert_facts_to_vector_db(chunk_db_facts)

                total_facts += len(chunk_db_facts)

            if progress_store is not None:
                progress_store[doc_id]["stage"] = "extracting"
                progress_store[doc_id]["done"] = index

            # Release chunk-level references before continuing.
            del facts
            del chunk_db_facts

            # Give the event loop a chance to release resources.
            await asyncio.sleep(0.1)

        # ── Final document status ──────────────────────────────────────

        if total_facts > 0:

            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    status="done",
                    page_count=total_chunks,
                    error_message=None,
                )
            )

            print(
                f"[Ingestion] Document {doc_id} completed "
                f"with {total_facts} fact(s)."
            )

        else:

            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    status="failed",
                    error_message=(
                        "Rate limits exhausted or no facts "
                        "could be extracted."
                    ),
                )
            )

            print(
                f"[Ingestion] Document {doc_id} produced no facts."
            )

        await session.commit()

        if progress_store is not None:
            progress_store.pop(doc_id, None)

    except Exception as exc:

        print(
            f"[Ingestion] Document {doc_id} failed: {exc}"
        )

        await session.rollback()

        try:
            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    status="failed",
                    error_message=str(exc),
                )
            )

            await session.commit()

        except Exception as status_exc:
            print(
                f"[Ingestion] Could not update failed status: "
                f"{status_exc}"
            )