"""
Re-embed all facts that exist in SQLite but are missing from ChromaDB.
Run once to fix sync issues: python3 re_embed_all.py
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.database import async_session
from app.models import Fact
from app.services.embeddings import facts_collection, upsert_facts_to_vector_db
from sqlalchemy.future import select


async def main():
    async with async_session() as db:
        all_facts = (await db.execute(select(Fact))).scalars().all()
        print(f"Total facts in SQLite: {len(all_facts)}")

        # Find which ones are missing from Chroma
        all_ids = [f.id for f in all_facts]
        chroma_data = facts_collection.get(ids=all_ids, include=[])
        chroma_ids = set(chroma_data["ids"])
        missing = [f for f in all_facts if f.id not in chroma_ids]

        print(f"Already in Chroma : {len(chroma_ids)}")
        print(f"Missing from Chroma: {len(missing)}")

        if not missing:
            print("Nothing to do — Chroma is already in sync.")
            return

        batch_size = 30
        for i in range(0, len(missing), batch_size):
            batch = missing[i : i + batch_size]
            await upsert_facts_to_vector_db(batch)
            done = min(i + batch_size, len(missing))
            print(f"  Embedded {done}/{len(missing)} facts", flush=True)

        final_count = facts_collection.count()
        print(f"\nChroma now has {final_count} facts — all done!")


if __name__ == "__main__":
    asyncio.run(main())
