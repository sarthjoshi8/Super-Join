"""Fast PDF processing, chunking, and Gemini fact extraction service."""

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


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

# Number of Gemini requests allowed at the same time.
# 3 is a good balance for Render Free + Gemini API.
GEMINI_CONCURRENCY = 3

# Maximum time allowed for one Gemini request.
GEMINI_TIMEOUT = 90

# Number of retries for temporary failures.
MAX_RETRIES = 3


# -------------------------------------------------------------------
# Pydantic schemas
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# File hash
# -------------------------------------------------------------------

def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(file_bytes).hexdigest()


# -------------------------------------------------------------------
# PDF extraction
# -------------------------------------------------------------------

async def extract_pdf_chunks(
    filepath: str,
) -> List[Dict[str, Any]]:
    """
    Extract PDF text into bounded-size chunks.

    PyMuPDF runs in a worker thread so FastAPI remains responsive.
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


# -------------------------------------------------------------------
# Gemini fact extraction
# -------------------------------------------------------------------

def build_fact_prompt(chunk_text: str) -> str:
    """Build the Gemini extraction prompt."""

    return f"""
Extract all verifiable facts from the following document text.

Facts may include:
- Skills, technologies and tools
- Roles, job titles, companies and institutions
- Dates, durations and time periods
- Metrics, numbers and quantities
- Degrees, certifications and achievements
- Locations
- Stated attributes about people, companies or products
- Financial, operational, business, economic, or statistical facts

Rules:
- Follow the exact JSON schema provided.
- Do not infer information that is not clearly stated.
- If a value is implied but not explicit, set is_partial=true.
- For non-numeric facts use numeric_value=null.
- Extract ONLY facts.
- Keep raw_statement short and directly supported by the text.
- Avoid duplicate facts.
- Return an empty facts list if no verifiable facts are present.

TEXT:
{chunk_text}
"""


async def extract_facts_from_chunk_with_gemini(
    chunk_text: str,
    chunk_number: Optional[int] = None,
) -> List[ExtractedFact]:
    """
    Extract facts from one chunk using Gemini.

    A timeout prevents one request from blocking the entire
    document indefinitely.
    """

    prompt = build_fact_prompt(chunk_text)

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    genai_client.models.generate_content,
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=FactExtractionResponse,
                        temperature=0.1,
                    ),
                ),
                timeout=GEMINI_TIMEOUT,
            )

            data = json.loads(response.text)

            validated = FactExtractionResponse.model_validate(
                data
            )

            print(
                f"[Gemini] Chunk "
                f"{chunk_number if chunk_number is not None else '?'} "
                f"extracted {len(validated.facts)} facts",
                flush=True,
            )

            return validated.facts

        except asyncio.TimeoutError:

            print(
                f"[Gemini] Chunk "
                f"{chunk_number if chunk_number is not None else '?'} "
                f"timed out on attempt {attempt}/{MAX_RETRIES}",
                flush=True,
            )

        except Exception as exc:

            error_text = str(exc)

            print(
                f"[Gemini] Chunk "
                f"{chunk_number if chunk_number is not None else '?'} "
                f"failed on attempt {attempt}/{MAX_RETRIES}: "
                f"{error_text}",
                flush=True,
            )

            # Gemini rate limit.
            if (
                "RESOURCE_EXHAUSTED" in error_text
                or "429" in error_text
            ):

                # Short exponential backoff.
                # We intentionally don't sleep 65 seconds here.
                wait_time = min(
                    5 * attempt,
                    15,
                )

                print(
                    f"[Gemini] Rate limit detected. "
                    f"Waiting {wait_time}s...",
                    flush=True,
                )

                await asyncio.sleep(wait_time)

            elif "schema" in error_text.lower():

                prompt = (
                    "Return ONLY valid JSON matching the exact "
                    "FactExtractionResponse schema.\n\n"
                    + prompt
                )

                await asyncio.sleep(1)

            else:

                await asyncio.sleep(2)

    print(
        f"[Gemini] Chunk "
        f"{chunk_number if chunk_number is not None else '?'} "
        f"failed after {MAX_RETRIES} attempts. Continuing.",
        flush=True,
    )

    return []


# -------------------------------------------------------------------
# Concurrent Gemini processing
# -------------------------------------------------------------------

async def process_chunk_with_limit(
    semaphore: asyncio.Semaphore,
    chunk: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    """
    Process one chunk while respecting the global Gemini
    concurrency limit.
    """

    async with semaphore:

        print(
            f"[Ingestion] Gemini processing "
            f"chunk {index}",
            flush=True,
        )

        facts = await extract_facts_from_chunk_with_gemini(
            chunk["text"],
            chunk_number=index,
        )

        return {
            "index": index,
            "page_number": chunk["page_number"],
            "facts": facts,
        }


# -------------------------------------------------------------------
# Main processing pipeline
# -------------------------------------------------------------------

async def process_document_task(
    doc_id: str,
    filepath: str,
    session: AsyncSession,
    progress_store: Optional[dict] = None,
) -> None:
    """
    Process a PDF using controlled parallel Gemini extraction.

    Pipeline:

        PDF
          ↓
        PyMuPDF
          ↓
        3 Gemini requests at once
          ↓
        Database
          ↓
        Lightweight local embeddings
          ↓
        ChromaDB

    Only a small number of Gemini requests run simultaneously
    to keep Render memory and API rate usage under control.
    """

    try:

        # ------------------------------------------------------------
        # Mark document as processing
        # ------------------------------------------------------------

        await session.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(
                status="processing",
                error_message=None,
            )
        )

        await session.commit()

        # ------------------------------------------------------------
        # Extract PDF chunks
        # ------------------------------------------------------------

        chunks = await extract_pdf_chunks(filepath)

        total_chunks = len(chunks)

        print(
            f"[Ingestion] Document {doc_id}: "
            f"{total_chunks} chunk(s)",
            flush=True,
        )

        if total_chunks == 0:

            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    status="failed",
                    error_message="No readable text found in PDF.",
                )
            )

            await session.commit()

            return

        if progress_store is not None:

            progress_store[doc_id] = {
                "stage": "extracting",
                "done": 0,
                "total": total_chunks,
            }

        # ------------------------------------------------------------
        # Controlled concurrent Gemini processing
        # ------------------------------------------------------------

        semaphore = asyncio.Semaphore(
            GEMINI_CONCURRENCY
        )

        tasks = [
            process_chunk_with_limit(
                semaphore,
                chunk,
                index,
            )
            for index, chunk in enumerate(
                chunks,
                start=1,
            )
        ]

        print(
            f"[Ingestion] Starting "
            f"{GEMINI_CONCURRENCY} concurrent Gemini workers",
            flush=True,
        )

        results = []

        # Process chunks in small concurrent groups.
        #
        # We do not launch all chunks at once. This keeps memory
        # predictable on Render Free.
        for group_start in range(
            0,
            len(tasks),
            GEMINI_CONCURRENCY,
        ):

            group = tasks[
                group_start:
                group_start + GEMINI_CONCURRENCY
            ]

            group_results = await asyncio.gather(
                *group,
                return_exceptions=True,
            )

            for result in group_results:

                if isinstance(
                    result,
                    Exception,
                ):

                    print(
                        f"[Ingestion] Chunk worker failed: "
                        f"{result}",
                        flush=True,
                    )

                    continue

                results.append(result)

            completed = min(
                group_start + GEMINI_CONCURRENCY,
                total_chunks,
            )

            if progress_store is not None:

                progress_store[doc_id]["stage"] = (
                    "extracting"
                )

                progress_store[doc_id]["done"] = (
                    completed
                )

            print(
                f"[Ingestion] Gemini progress: "
                f"{completed}/{total_chunks} chunks",
                flush=True,
            )

        # ------------------------------------------------------------
        # Store results in original chunk order
        # ------------------------------------------------------------

        results.sort(
            key=lambda item: item["index"]
        )

        total_facts = 0

        for result in results:

            facts = result["facts"]

            if not facts:
                continue

            page_number = result[
                "page_number"
            ]

            chunk_db_facts = []

            for extracted_fact in facts:

                db_fact = Fact(
                    document_id=doc_id,
                    subject=extracted_fact.subject,
                    predicate=extracted_fact.predicate,
                    value=extracted_fact.value,
                    numeric_value=(
                        extracted_fact.numeric_value
                    ),
                    unit=extracted_fact.unit,
                    time_start=(
                        extracted_fact.time_start
                    ),
                    time_end=(
                        extracted_fact.time_end
                    ),
                    time_label=(
                        extracted_fact.time_label
                    ),
                    scope=extracted_fact.scope,
                    raw_statement=(
                        extracted_fact.raw_statement
                    ),
                    is_partial=(
                        extracted_fact.is_partial
                    ),
                    note=extracted_fact.note,
                    page_number=page_number,
                    confidence=(
                        extracted_fact.confidence
                    ),
                )

                session.add(db_fact)
                chunk_db_facts.append(db_fact)

            # --------------------------------------------------------
            # Commit facts
            # --------------------------------------------------------

            await session.commit()

            # Refresh IDs generated by SQLAlchemy.
            for db_fact in chunk_db_facts:
                await session.refresh(db_fact)

            # --------------------------------------------------------
            # Local embeddings
            # --------------------------------------------------------

            if progress_store is not None:

                progress_store[doc_id]["stage"] = (
                    "embedding"
                )

            await upsert_facts_to_vector_db(
                chunk_db_facts
            )

            total_facts += len(
                chunk_db_facts
            )

            print(
                f"[Ingestion] Stored "
                f"{len(chunk_db_facts)} facts "
                f"from chunk {result['index']}",
                flush=True,
            )

            # Release references.
            del chunk_db_facts
            del facts

        # ------------------------------------------------------------
        # Final document status
        # ------------------------------------------------------------

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
                f"[Ingestion] Document {doc_id} "
                f"completed with "
                f"{total_facts} fact(s).",
                flush=True,
            )

        else:

            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    status="failed",
                    page_count=total_chunks,
                    error_message=(
                        "No facts could be extracted "
                        "from the document."
                    ),
                )
            )

            print(
                f"[Ingestion] Document {doc_id} "
                f"produced no facts.",
                flush=True,
            )

        await session.commit()

        if progress_store is not None:
            progress_store.pop(
                doc_id,
                None,
            )

    except Exception as exc:

        print(
            f"[Ingestion] Document {doc_id} failed: "
            f"{exc}",
            flush=True,
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
                f"[Ingestion] Could not update failed "
                f"status: {status_exc}",
                flush=True,
            )

