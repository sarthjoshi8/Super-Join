"""PDF processing, chunking, and fact extraction service."""

import hashlib
import os
import asyncio
import json
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from google import genai
from google.genai import types

from app.models import Document, Fact
from app.config import MAX_CHUNK_CHARS, GEMINI_API_KEY, GEMINI_MODEL, MAX_CONCURRENT_GEMINI
from app.services.embeddings import upsert_facts_to_vector_db

genai_client = genai.Client(api_key=GEMINI_API_KEY)

# ── Pydantic Schema for Gemini Structured Output ───────────────────────

class ExtractedFact(BaseModel):
    subject: str = Field(description="The main entity the fact is about (e.g. 'Delhivery', 'India').")
    predicate: str = Field(description="What is being stated about the subject (e.g. 'revenue', 'GDP growth').")
    value: str = Field(description="The stated value, kept as a string to preserve formatting (e.g. '₹8,142 Cr', '~7.2%').")
    numeric_value: Optional[float] = Field(description="The parsed numeric float value if applicable, for comparison.", default=None)
    unit: Optional[str] = Field(description="The unit of measurement (e.g. 'Cr INR', '%', 'million').", default=None)
    time_start: Optional[str] = Field(description="Structured start date if parseable (e.g. '2023-04-01').", default=None)
    time_end: Optional[str] = Field(description="Structured end date if parseable.", default=None)
    time_label: Optional[str] = Field(description="The original free-text period label (e.g. 'FY24', 'Q4 FY24').", default=None)
    scope: Optional[str] = Field(description="The scope of the metric (e.g. 'consolidated', 'standalone', 'express parcel').", default=None)
    raw_statement: str = Field(description="The exact literal sentence or phrase from the text that proves this fact.")
    is_partial: bool = Field(description="Set to true if the value is missing, ambiguous, or inferred with low confidence.", default=False)
    note: Optional[str] = Field(description="Explain why a fact is partial, or note any ambiguities/assumptions.", default=None)
    confidence: float = Field(description="Confidence score (0.0 to 1.0) that this fact is objectively verifiable and correctly extracted.", default=1.0)


class FactExtractionResponse(BaseModel):
    facts: List[ExtractedFact]


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of a file's bytes."""
    return hashlib.sha256(file_bytes).hexdigest()


async def extract_pdf_chunks(filepath: str) -> List[Dict[str, Any]]:
    """
    Extract text from a PDF, chunked roughly by page.
    Returns a list of chunks with metadata (e.g., page number).
    """
    def _extract():
        chunks = []
        doc = fitz.open(filepath)
        
        current_chunk_text = ""
        current_start_page = 1
        
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if not text:
                continue
                
            # If adding this page exceeds max chunk chars and we already have some text,
            # push the current chunk and start a new one
            if current_chunk_text and (len(current_chunk_text) + len(text) > MAX_CHUNK_CHARS):
                chunks.append({
                    "text": current_chunk_text,
                    "page_number": current_start_page  # representing the start page of this chunk
                })
                current_chunk_text = text + "\n"
                current_start_page = page_num
            else:
                current_chunk_text += text + "\n"
                
        # Append the final chunk if there's leftover text
        if current_chunk_text:
            chunks.append({
                "text": current_chunk_text,
                "page_number": current_start_page
            })
            
        return chunks
        
    return await asyncio.to_thread(_extract)

async def extract_facts_from_chunk_with_gemini(chunk_text: str) -> List[ExtractedFact]:
    """Call Gemini to extract structured facts from a text chunk."""
    prompt = f"""
Extract all verifiable facts from the following document text. Facts may include:
- Skills, technologies, tools mentioned (e.g. "Python", "React", "AWS")
- Roles, job titles, companies, institutions
- Dates, durations, time periods (e.g. "3 years experience", "2022-2024")
- Metrics, numbers, quantities (e.g. "managed a team of 10", "GPA 3.8", "revenue ₹100Cr")
- Degrees, certifications, achievements
- Locations (cities, countries)
- Any stated claim or attribute about a person, company, or product

Rules:
- Follow the exact JSON schema provided.
- Do not infer information not clearly stated.
- If a value is implied but not explicit, set is_partial=true and explain in note.
- For non-numeric facts use numeric_value=null.
- Extract ONLY facts, nothing else.

TEXT:
{chunk_text}
"""

    # Try calling Gemini. If it fails, retry up to 5 times.
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
        except Exception as e:
            if attempt == 5:
                print(f"Failed to extract facts after {attempt} retries: {e}")
                return []
            print(f"Fact extraction failed on attempt {attempt}, retrying: {e}")
            # If rate limit, sleep longer to clear the 15/min quota window
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                await asyncio.sleep(65)
            else:
                await asyncio.sleep(5)
            # Only append schema warning after first failure if we think it's a validation error
            if attempt == 1 and "schema" in str(e).lower():
                prompt = "Previous attempt failed due to JSON schema validation. Ensure strict compliance to the schema.\n" + prompt

    return []


async def process_document_task(
    doc_id: str,
    filepath: str,
    session: AsyncSession,
    progress_store: Optional[dict] = None,
) -> None:
    """
    Background task to process a document:
    1. Chunk text via PyMuPDF.
    2. Extract facts via Gemini JSON output.
    3. Persist facts to SQLite.
    4. Embed facts and upsert to ChromaDB.
    """
    try:
        # Mark as processing
        await session.execute(
            update(Document).where(Document.id == doc_id).values(status="processing")
        )
        await session.commit()
        
        # 1. Extract chunks
        chunks = await extract_pdf_chunks(filepath)
        total = len(chunks)
        if progress_store is not None:
            progress_store[doc_id] = {"stage": "extracting", "done": 0, "total": total}
        
        all_db_facts = []
        done_count = 0
        
        # 2. Extract facts from each chunk (concurrently with a limit)
        from app.config import MAX_CONCURRENT_GEMINI
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_GEMINI)  # configurable concurrency
        
        async def process_chunk(chunk):
            nonlocal done_count
            async with semaphore:
                facts = await extract_facts_from_chunk_with_gemini(chunk["text"])
                done_count += 1
                if progress_store is not None:
                    progress_store[doc_id]["done"] = done_count
                return [
                    Fact(
                        document_id=doc_id,
                        subject=ef.subject,
                        predicate=ef.predicate,
                        value=ef.value,
                        numeric_value=ef.numeric_value,
                        unit=ef.unit,
                        time_start=ef.time_start,
                        time_end=ef.time_end,
                        time_label=ef.time_label,
                        scope=ef.scope,
                        raw_statement=ef.raw_statement,
                        is_partial=ef.is_partial,
                        note=ef.note,
                        page_number=chunk["page_number"],
                        confidence=ef.confidence
                    )
                    for ef in facts
                ]
                
        # Run all chunk extractions concurrently
        results = await asyncio.gather(*(process_chunk(chunk) for chunk in chunks), return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Error processing chunk: {result}")
            else:
                for db_fact in result:
                    session.add(db_fact)
                    all_db_facts.append(db_fact)
                
        await session.commit()
        
        # We need to refresh the db_facts to get their generated IDs before embedding
        for f in all_db_facts:
            await session.refresh(f)
            
        # 4. Embed and upsert to ChromaDB
        if all_db_facts:
            if progress_store is not None:
                progress_store[doc_id]["stage"] = "embedding"
            await upsert_facts_to_vector_db(all_db_facts)
        
        # Mark as done if we got facts, else failed
        if all_db_facts:
            await session.execute(
                update(Document).where(Document.id == doc_id).values(
                    status="done",
                    page_count=len(chunks)
                )
            )
        else:
            await session.execute(
                update(Document).where(Document.id == doc_id).values(
                    status="failed",
                    error_message="Rate limits exhausted or no facts could be extracted."
                )
            )
        await session.commit()
        
    except Exception as e:
        # Mark as failed
        await session.execute(
            update(Document).where(Document.id == doc_id).values(
                status="failed",
                error_message=str(e)
            )
        )
        await session.commit()
