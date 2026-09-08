"""API router for fetching and searching extracted facts."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Fact

router = APIRouter(prefix="/api/facts", tags=["facts"])


@router.get("/", response_model=List[dict])
async def list_facts(
    document_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List extracted facts, optionally filtered by document_id."""
    query = select(Fact)
    if document_id:
        query = query.where(Fact.document_id == document_id)
        
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    facts = result.scalars().all()
    
    return [
        {
            "id": f.id,
            "document_id": f.document_id,
            "subject": f.subject,
            "predicate": f.predicate,
            "value": f.value,
            "numeric_value": f.numeric_value,
            "unit": f.unit,
            "time_label": f.time_label,
            "scope": f.scope,
            "raw_statement": f.raw_statement,
            "page_number": f.page_number,
            "confidence": f.confidence
        }
        for f in facts
    ]
