"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import documents, facts

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    await init_db()
    yield


app = FastAPI(
    title="Fact Knowledge Layer",
    description="Extract, ground, and cross-reference facts from PDF documents.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(documents.router)
app.include_router(facts.router)


# CORS — allow the Vite dev server during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "https://sarthjoshi8-super-join.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Document, Fact
from app.services.embeddings import facts_collection

# ── Health & Status ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "fact-knowledge-layer"}

@app.get("/api/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    # Get total documents
    doc_count = await db.scalar(select(func.count(Document.id)))
    # Get total facts
    fact_count = await db.scalar(select(func.count(Fact.id)))
    # Get chroma embeddings count
    try:
        chroma_count = facts_collection.count()
    except Exception:
        chroma_count = 0
        
    return {
        "status": "ok",
        "documents": doc_count,
        "facts": fact_count,
        "chroma_embeddings": chroma_count
    }
