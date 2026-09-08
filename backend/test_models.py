import asyncio
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

async def test_model(model_name):
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    try:
        response = client.models.generate_content(
            model=model_name,
            contents="Say 'hello world'",
        )
        print(f"{model_name}: Success! -> {response.text}")
    except Exception as e:
        print(f"{model_name}: Failed -> {e}")

async def main():
    models = ["gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-flash-latest"]
    for m in models:
        await test_model(m)

if __name__ == "__main__":
    asyncio.run(main())
