import asyncio
from app.database import async_session
from app.services.cross_check import analyze_document_facts

async def main():
    async with async_session() as db:
        await analyze_document_facts("e0e27e69-ba73-417d-8f61-1fa784133ca6", db)

if __name__ == "__main__":
    asyncio.run(main())
