import asyncio
import sqlite3
from sqlalchemy.future import select

from app.database import async_session
from app.models import Document, Fact
from app.services.embeddings import upsert_facts_to_vector_db

async def main():
    async with async_session() as db:
        # Create a dummy document
        doc = Document(
            filename="dummy-market-report.pdf",
            content_hash="dummy_hash_124",
            status="done",
            upload_path="/dev/null",
            page_count=1
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        
        # Add a fact that contradicts something in the delhivery report
        # For example, Delhivery reported FY24 revenue of Rs 8142 Cr
        # We will add a fact that says Delhivery revenue was Rs 5000 Cr.
        fact = Fact(
            document_id=doc.id,
            subject="Delhivery",
            predicate="Revenue",
            value="Rs 5,000 Cr",
            numeric_value=5000.0,
            unit="Cr INR",
            time_label="FY24",
            raw_statement="In FY24, Delhivery posted a total revenue of Rs 5,000 Cr according to internal sources.",
            page_number=1,
            confidence=1.0
        )
        db.add(fact)
        await db.commit()
        await db.refresh(fact)
        
        print(f"Created doc {doc.id} and fact {fact.id}")
        
        # Embed the fact
        await upsert_facts_to_vector_db([fact])
        print("Fact embedded successfully.")

if __name__ == "__main__":
    asyncio.run(main())
