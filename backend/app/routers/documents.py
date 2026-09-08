"""API router for document ingestion and retrieval."""

import os
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db, async_session
from app.models import Document
from app.config import UPLOAD_DIR
from app.services.ingestion import compute_file_hash, process_document_task

# In-memory progress tracker: {doc_id: {"done": int, "total": int, "stage": str}}
_progress: dict = {}
_analyzing_docs: set = set()

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Upload a PDF document, store it, and queue for processing."""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    file_bytes = await file.read()
    content_hash = compute_file_hash(file_bytes)
    
    # Check if duplicate
    stmt = select(Document).where(Document.content_hash == content_hash)
    result = await db.execute(stmt)
    existing_doc = result.scalar_one_or_none()
    
    if existing_doc:
        if existing_doc.status == "failed":
            # If it failed previously, delete it and allow re-upload
            await db.delete(existing_doc)
            await db.commit()
        else:
            return {
                "message": "Document already exists",
                "document_id": existing_doc.id,
                "status": existing_doc.status
            }
        
    # Save file to disk
    filepath = UPLOAD_DIR / f"{content_hash}.pdf"
    with open(filepath, "wb") as f:
        f.write(file_bytes)
        
    # Create DB record
    new_doc = Document(
        filename=file.filename,
        content_hash=content_hash,
        upload_path=str(filepath)
    )
    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)
    
    # Queue background processing
    # We create a separate session for the background task since the request session will close
    async def _run_task():
        async with async_session() as task_db:
            await process_document_task(new_doc.id, str(filepath), task_db, _progress)
            
    background_tasks.add_task(_run_task)
    
    return {
        "message": "Upload successful, processing started",
        "document_id": new_doc.id,
        "status": new_doc.status
    }


@router.get("")
async def list_documents(db: AsyncSession = Depends(get_db)) -> Any:
    """List all ingested documents and clean up failed ones."""
    from sqlalchemy import delete
    # Automatically delete failed documents on fetch so they disappear from UI
    await db.execute(delete(Document).where(Document.status == "failed"))
    await db.commit()

    stmt = select(Document).order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    docs = result.scalars().all()
    from datetime import timezone
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
            "page_count": doc.page_count,
            "error_message": doc.error_message,
            "created_at": doc.created_at.replace(tzinfo=timezone.utc) if doc.created_at else None
        }
        for doc in docs
    ]


@router.get("/{document_id}")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)) -> Any:
    """Get status and metadata for a single document."""
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    from datetime import timezone
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "page_count": doc.page_count,
        "error_message": doc.error_message,
        "created_at": doc.created_at.replace(tzinfo=timezone.utc) if doc.created_at else None
    }

@router.get("/{document_id}/progress")
async def get_progress(document_id: str):
    """Return live chunk-processing progress for a document being ingested."""
    info = _progress.get(document_id)
    if not info:
        return {"stage": "unknown", "done": 0, "total": 0}
    return info


@router.post("/{document_id}/analyze")
async def trigger_analysis(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # Verify document exists
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalars().first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if doc.status != "done":
        raise HTTPException(
            status_code=400, 
            detail="Document must finish ingestion before it can be analyzed."
        )

    _analyzing_docs.add(document_id)

    # We create a separate session for the background task
    async def _run_analysis():
        try:
            from app.services.cross_check import analyze_document_facts
            async with async_session() as task_db:
                await analyze_document_facts(document_id, task_db)
        finally:
            _analyzing_docs.discard(document_id)
            
    background_tasks.add_task(_run_analysis)
    
    return {"message": "Cross-check analysis started in the background."}

@router.get("/{document_id}/analysis_status")
async def get_analysis_status(document_id: str):
    """Return whether background cross-check analysis is currently active."""
    return {"is_analyzing": document_id in _analyzing_docs}

@router.get("/{document_id}/relationships")
async def get_relationships(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    from app.models import Fact, FactRelationship
    # Get all facts for this document
    stmt = select(Fact).where(Fact.document_id == document_id)
    res = await db.execute(stmt)
    facts = res.scalars().all()
    
    if not facts:
        return []
        
    fact_ids = [f.id for f in facts]
    
    # Get all relationships where fact_a or fact_b is in this document's facts
    stmt_rels = select(FactRelationship).where(
        (FactRelationship.fact_a_id.in_(fact_ids)) | 
        (FactRelationship.fact_b_id.in_(fact_ids))
    )
    res_rels = await db.execute(stmt_rels)
    relationships = res_rels.scalars().all()
    
    # Map facts for quick lookup
    fact_map = {}
    
    # We need to fetch ALL facts that are part of these relationships (including from other docs)
    all_related_fact_ids = set()
    for r in relationships:
        all_related_fact_ids.add(r.fact_a_id)
        all_related_fact_ids.add(r.fact_b_id)
        
    if all_related_fact_ids:
        stmt_all_facts = select(Fact).where(Fact.id.in_(list(all_related_fact_ids)))
        res_all_facts = await db.execute(stmt_all_facts)
        for f in res_all_facts.scalars().all():
            fact_map[f.id] = f
    
    # Convert to dict for serialization
    return [
        {
            "id": r.id,
            "fact_a": {k: v for k, v in fact_map[r.fact_a_id].__dict__.items() if not k.startswith("_")} if r.fact_a_id in fact_map else {"id": r.fact_a_id},
            "fact_b": {k: v for k, v in fact_map[r.fact_b_id].__dict__.items() if not k.startswith("_")} if r.fact_b_id in fact_map else {"id": r.fact_b_id},
            "relationship_type": r.relationship_type,
            "reason": r.reason,
            "match_confidence": r.match_confidence
        }
        for r in relationships
    ]


@router.delete("/{document_id}")
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)) -> Any:
    """Delete a document, its facts, relationships, and vector embeddings."""
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    filename = doc.filename
    upload_path = doc.upload_path

    # 1. Delete vectors from ChromaDB
    try:
        from app.services.embeddings import facts_collection
        facts_collection.delete(where={"document_id": document_id})
    except Exception as e:
        print(f"Error removing Chroma embeddings for {document_id}: {e}")

    # 2. Delete relationships involving facts of this document
    from sqlalchemy import delete
    from app.models import FactRelationship, Fact
    
    fact_ids_stmt = select(Fact.id).where(Fact.document_id == document_id)
    fact_ids = (await db.execute(fact_ids_stmt)).scalars().all()
    
    if fact_ids:
        await db.execute(
            delete(FactRelationship).where(
                (FactRelationship.fact_a_id.in_(fact_ids)) | 
                (FactRelationship.fact_b_id.in_(fact_ids))
            )
        )
        await db.execute(delete(Fact).where(Fact.document_id == document_id))

    # 3. Delete Document record
    await db.delete(doc)
    await db.commit()

    # 4. Remove file from uploads if present
    if upload_path and os.path.exists(upload_path):
        try:
            os.remove(upload_path)
        except Exception as e:
            print(f"Error removing file {upload_path}: {e}")

    # 5. Clean in-memory tracking
    _progress.pop(document_id, None)
    _analyzing_docs.discard(document_id)

    return {"status": "success", "message": f"Document '{filename}' deleted successfully."}

