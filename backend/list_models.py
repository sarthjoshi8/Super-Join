from google import genai
import os
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
for m in client.models.list():
    if "embed" in m.name.lower() or "embed" in m.supported_actions:
        print(m.name, m.supported_actions)
