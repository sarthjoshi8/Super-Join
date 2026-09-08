"""Automatic ingestion of built-in PDF datasets."""

import os
from pathlib import Path

from sqlalchemy.future import select

from app.config import DATA_DIR, UPLOAD_DIR
from app.database import async_session
from app.models import Document
from app.services.ingestion import compute_file_hash, process_document_task


# Built-in PDFs are stored in the repository-level data directory.
BUILTIN_DATASET_DIR = DATA_DIR / "built-in-dataset"


async def ingest_builtin_dataset() -> None:
    """
    Automatically add and process built-in PDFs.

    This function is idempotent:
    - PDFs already present in the database are skipped.
    - New PDFs are added as Document records.
    - New PDFs are processed through the existing ingestion pipeline.
    """

    if not BUILTIN_DATASET_DIR.exists():
        print(f"[Built-in Dataset] Directory not found: {BUILTIN_DATASET_DIR}")
        return

    pdf_files = sorted(BUILTIN_DATASET_DIR.glob("*.pdf"))

    if not pdf_files:
        print("[Built-in Dataset] No PDF files found.")
        return

    print(
        f"[Built-in Dataset] Found {len(pdf_files)} PDF(s) "
        f"in {BUILTIN_DATASET_DIR}"
    )

    async with async_session() as db:
        for pdf_path in pdf_files:
            try:
                # Read PDF bytes and calculate the same hash used by uploads.
                file_bytes = await _read_file(pdf_path)
                content_hash = compute_file_hash(file_bytes)

                # Check whether this exact PDF is already indexed.
                stmt = select(Document).where(
                    Document.content_hash == content_hash
                )
                result = await db.execute(stmt)
                existing_doc = result.scalar_one_or_none()

                if existing_doc:
                    print(
                        f"[Built-in Dataset] Already exists: "
                        f"{existing_doc.filename} "
                        f"(status={existing_doc.status})"
                    )
                    continue

                # Store a copy in the normal upload directory.
                upload_path = UPLOAD_DIR / f"{content_hash}.pdf"

                if not upload_path.exists():
                    with open(upload_path, "wb") as f:
                        f.write(file_bytes)

                # Create the same Document record used by normal uploads.
                document = Document(
                    filename=pdf_path.name,
                    content_hash=content_hash,
                    upload_path=str(upload_path),
                    status="queued",
                )

                db.add(document)
                await db.commit()
                await db.refresh(document)

                print(
                    f"[Built-in Dataset] Added: "
                    f"{document.filename} ({document.id})"
                )

                # Use the existing ingestion pipeline.
                await process_document_task(
                    document.id,
                    str(upload_path),
                    db,
                )

                print(
                    f"[Built-in Dataset] Finished: "
                    f"{document.filename}"
                )

            except Exception as e:
                print(
                    f"[Built-in Dataset] Failed to process "
                    f"{pdf_path.name}: {e}"
                )

                # Keep processing the remaining PDFs.
                await db.rollback()


async def _read_file(path: Path) -> bytes:
    """Read a file without blocking the async event loop."""
    def _read() -> bytes:
        with open(path, "rb") as f:
            return f.read()

    import asyncio

    return await asyncio.to_thread(_read)