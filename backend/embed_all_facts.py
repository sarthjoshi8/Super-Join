import asyncio
from sqlalchemy.future import select

from app.database import async_session
from app.models import Fact
from app.services.embeddings import upsert_facts_to_vector_db

async def main():
    async with async_session() as db:
        stmt = select(Fact)
        res = await db.execute(stmt)
        facts = res.scalars().all()
        print(f"Found {len(facts)} facts to embed.")
        
        # Embed in batches to avoid rate limit or payload size issues
        batch_size = 50
        for i in range(0, len(facts), batch_size):
            batch = facts[i:i+batch_size]
            await upsert_facts_to_vector_db(batch)
            print(f"Embedded batch {i//batch_size + 1}")

if __name__ == "__main__":
    asyncio.run(main())
