import asyncio
import time
from app.database import async_session
from app.models import Document, Fact
from app.services.embeddings import upsert_facts_to_vector_db, GEMINI_EMBEDDING_MODEL
from sqlalchemy import select

async def main():
    print(f"Using embedding model: {GEMINI_EMBEDDING_MODEL}", flush=True)
    async with async_session() as session:
        for doc_id in ['7ccd594e-9490-41b1-9e6e-72f8f3d537fc', 'd3f7f587-cfdf-445b-8f5c-1b53e606ee7e']:
            doc = await session.get(Document, doc_id)
            if not doc:
                print(f"Document {doc_id} not found", flush=True)
                continue
            facts = (await session.execute(select(Fact).where(Fact.document_id == doc_id))).scalars().all()
            print(f"\n=======================================================", flush=True)
            print(f"Embedding '{doc.filename}' ({len(facts)} facts)...", flush=True)
            print(f"=======================================================", flush=True)
            t0 = time.time()
            await upsert_facts_to_vector_db(facts)
            t1 = time.time()
            print(f"--> Successfully embedded and indexed {len(facts)} facts in {t1 - t0:.2f}s!", flush=True)
            doc.status = "done"
            await session.commit()
            print(f"--> Document '{doc.filename}' status updated to 'done'!", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
