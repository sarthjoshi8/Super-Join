import asyncio
import json
from app.services.ingestion import extract_facts_from_chunk_with_gemini, extract_pdf_chunks
from pydantic import BaseModel

async def main():
    print("Extracting first page of Delhivery Prospectus...")
    chunks = await extract_pdf_chunks("../data/delhivery/01-delhivery-prospectus-2022-excerpt.pdf")
    first_chunk = chunks[0]["text"]
    
    print(f"Text length: {len(first_chunk)}")
    print("Sending to Gemini...")
    facts = await extract_facts_from_chunk_with_gemini(first_chunk)
    
    print(f"Extracted {len(facts)} facts.")
    for f in facts:
        print(f.model_dump_json(indent=2))

if __name__ == "__main__":
    asyncio.run(main())
