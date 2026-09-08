import asyncio
import os
import shutil
from pathlib import Path
from sqlalchemy.future import select
from sqlalchemy import delete

from app.database import async_session, init_db
from app.models import Document, Fact, FactRelationship
from app.config import UPLOAD_DIR
from app.services.ingestion import compute_file_hash, process_document_task
from app.services.cross_check import analyze_document_facts

DATASET_DIR = Path("/Users/harsh/Downloads/starter-datasets/india-macroeconomy")

FILES = [
    "01-india-economic-survey-2024-25-excerpt.pdf",
    "02-rbi-annual-report-2024-25-excerpt.pdf",
    "03-imf-india-2025-article-iv-excerpt.pdf",
]

async def main():
    await init_db()
    print("=== Starting Direct Ingestion of India Macroeconomy Dataset ===")
    
    doc_ids = []
    
    for filename in FILES:
        filepath = DATASET_DIR / filename
        if not filepath.exists():
            print(f"File not found: {filepath}")
            continue
            
        print(f"\nProcessing file: {filename}")
        with open(filepath, "rb") as f:
            file_bytes = f.read()
            
        content_hash = compute_file_hash(file_bytes)
        target_path = UPLOAD_DIR / f"{content_hash}.pdf"
        with open(target_path, "wb") as f:
            f.write(file_bytes)
            
        async with async_session() as session:
            # Delete old records for this file/hash if any exist
            stmt = select(Document).where(
                (Document.filename == filename) | (Document.content_hash == content_hash)
            )
            res = await session.execute(stmt)
            existing_docs = res.scalars().all()
            for doc in existing_docs:
                print(f"Cleaning up old record: {doc.id} ({doc.filename})")
                # Delete relationships
                facts_stmt = select(Fact.id).where(Fact.document_id == doc.id)
                facts_res = await session.execute(facts_stmt)
                f_ids = facts_res.scalars().all()
                if f_ids:
                    await session.execute(
                        delete(FactRelationship).where(
                            (FactRelationship.fact_a_id.in_(f_ids)) | (FactRelationship.fact_b_id.in_(f_ids))
                        )
                    )
                    await session.execute(delete(Fact).where(Fact.document_id == doc.id))
                await session.delete(doc)
            await session.commit()
            
            # Create fresh document
            new_doc = Document(
                filename=filename,
                content_hash=content_hash,
                upload_path=str(target_path)
            )
            session.add(new_doc)
            await session.commit()
            await session.refresh(new_doc)
            doc_id = new_doc.id
            doc_ids.append(doc_id)
            print(f"Created Document record: {doc_id}")
            
        # Process document
        print(f"Extracting facts with Gemini and embedding...")
        async with async_session() as session:
            await process_document_task(doc_id, str(target_path), session)
            
        # Verify facts count
        async with async_session() as session:
            f_res = await session.execute(select(Fact).where(Fact.document_id == doc_id))
            facts = f_res.scalars().all()
            d_res = await session.execute(select(Document).where(Document.id == doc_id))
            d = d_res.scalar_one()
            print(f"Finished {filename}: Status={d.status}, Facts Extracted={len(facts)}")
            
    print("\n=== Ingestion Complete! Running Cross-Document Analysis ===")
    for doc_id in doc_ids:
        async with async_session() as session:
            print(f"Analyzing connections for doc {doc_id}...")
            await analyze_document_facts(doc_id, session)
            
    async with async_session() as session:
        rel_res = await session.execute(select(FactRelationship))
        rels = rel_res.scalars().all()
        print(f"\nTotal Cross-Document Relationships Found: {len(rels)}")
        for r in rels[:10]:
            print(f" - [{r.relationship_type.upper()}] ({r.match_confidence:.2f}): {r.reason}")
            
    print("\n=== Dataset is now permanently stored in the Database! ===")

if __name__ == "__main__":
    asyncio.run(main())
