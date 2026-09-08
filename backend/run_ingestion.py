import asyncio
import os
from sqlalchemy.future import select

from app.database import async_session
from app.models import Document
from app.services.ingestion import process_document_task

async def main():
    async with async_session() as db:
        stmt = select(Document).where(Document.status.in_(["processing", "failed"]))
        result = await db.execute(stmt)
        docs = result.scalars().all()
        
        for doc in docs:
            print(f"Re-processing doc {doc.id}")
            filepath = doc.upload_path
            if os.path.exists(filepath):
                await process_document_task(doc.id, filepath, db)
            else:
                print(f"File {filepath} not found!")

if __name__ == "__main__":
    asyncio.run(main())
