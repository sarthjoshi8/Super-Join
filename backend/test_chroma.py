from app.services.embeddings import facts_collection
print(facts_collection.count())
# print a sample of the first few items
res = facts_collection.get(limit=5)
print(res["ids"])
print([m["document_id"] for m in res["metadatas"]])
