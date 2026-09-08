"""SQLAlchemy ORM models for documents, facts, evidence, and relationships."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ── Helpers ────────────────────────────────────────────────────────────
def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Document ───────────────────────────────────────────────────────────
class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=_uuid)
    filename = Column(String, nullable=False)
    content_hash = Column(String, nullable=False, unique=True, index=True)
    status = Column(
        SAEnum("queued", "processing", "done", "failed", name="doc_status"),
        default="queued",
        nullable=False,
    )
    error_message = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    upload_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    facts = relationship("Fact", back_populates="document", cascade="all, delete-orphan")


# ── Fact ───────────────────────────────────────────────────────────────
class Fact(Base):
    __tablename__ = "facts"

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    subject = Column(String, nullable=False)
    predicate = Column(String, nullable=False)
    value = Column(String, nullable=False)            # original textual value
    numeric_value = Column(Float, nullable=True)       # parsed number for comparison
    unit = Column(String, nullable=True)
    time_start = Column(String, nullable=True)
    time_end = Column(String, nullable=True)
    time_label = Column(String, nullable=True)
    scope = Column(String, nullable=True)

    raw_statement = Column(Text, nullable=False)       # exact source sentence
    note = Column(Text, nullable=True)                 # extraction notes / caveats
    is_partial = Column(Boolean, default=False, nullable=False)
    page_number = Column(Integer, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)  # extraction confidence

    created_at = Column(DateTime, default=_now, nullable=False)

    document = relationship("Document", back_populates="facts")
    # Relationships where this fact is on either side
    relationships_as_a = relationship(
        "FactRelationship",
        foreign_keys="FactRelationship.fact_a_id",
        back_populates="fact_a",
        cascade="all, delete-orphan",
    )
    relationships_as_b = relationship(
        "FactRelationship",
        foreign_keys="FactRelationship.fact_b_id",
        back_populates="fact_b",
        cascade="all, delete-orphan",
    )


# ── Fact Relationship ──────────────────────────────────────────────────
class FactRelationship(Base):
    __tablename__ = "fact_relationships"

    id = Column(String, primary_key=True, default=_uuid)
    fact_a_id = Column(String, ForeignKey("facts.id"), nullable=False, index=True)
    fact_b_id = Column(String, ForeignKey("facts.id"), nullable=False, index=True)

    relationship_type = Column(
        SAEnum(
            "CORROBORATES",
            "CONTRADICTS",
            "CONTEXTUALLY_DIFFERS",
            "SAME_FACT",
            "UNRELATED",
            "UNCERTAIN",
            name="rel_type",
        ),
        nullable=False,
    )
    reason = Column(Text, nullable=False)              # LLM or rule explanation
    match_confidence = Column(Float, default=1.0, nullable=False)
    determined_by = Column(String, nullable=False)     # "rule" or "llm_judge"

    created_at = Column(DateTime, default=_now, nullable=False)

    fact_a = relationship("Fact", foreign_keys=[fact_a_id], back_populates="relationships_as_a")
    fact_b = relationship("Fact", foreign_keys=[fact_b_id], back_populates="relationships_as_b")
