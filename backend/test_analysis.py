import requests
import time
import json

BASE_URL = "http://127.0.0.1:8000/api"

def main():
    # 1. Get documents
    resp = requests.get(f"{BASE_URL}/documents")
    docs = resp.json()
    done_docs = [d for d in docs if d["status"] == "done"]
    
    if not done_docs:
        print("No processed documents available.")
        return
        
    doc = done_docs[0]
    print(f"Selected document: {doc['id']} ({doc['filename']})")
    
    # 2. Trigger analysis
    resp = requests.post(f"{BASE_URL}/documents/{doc['id']}/analyze")
    print(f"Trigger analysis response: {resp.status_code} - {resp.text}")
    
    # 3. Wait a bit for background task to complete some facts
    print("Waiting 15 seconds for analysis to process...")
    time.sleep(15)
    
    # 4. Get relationships
    resp = requests.get(f"{BASE_URL}/documents/{doc['id']}/relationships")
    relationships = resp.json()
    
    print(f"Found {len(relationships)} relationships:")
    print(json.dumps(relationships, indent=2))

if __name__ == "__main__":
    main()
