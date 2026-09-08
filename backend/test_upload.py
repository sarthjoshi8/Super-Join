import requests
import time

BASE_URL = "http://127.0.0.1:8000/api"
filepath = "/Users/harsh/Downloads/starter-datasets/delhivery/01-delhivery-prospectus-2022-excerpt.pdf"

print(f"Uploading {filepath}...")
with open(filepath, "rb") as f:
    files = {"file": f}
    resp = requests.post(f"{BASE_URL}/documents/upload", files=files)
    
print("Response:", resp.status_code, resp.text)
data = resp.json()
doc_id = data["document_id"]

# Poll status
while True:
    res = requests.get(f"{BASE_URL}/documents/{doc_id}")
    doc = res.json()
    print(f"Status: {doc['status']}")
    if doc['status'] in ["done", "failed"]:
        break
    time.sleep(2)
