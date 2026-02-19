import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")
if not api_key:
    print("Error: PINECONE_API_KEY not found in .env")
    exit(1)

pc = Pinecone(api_key=api_key)

print(f"{'Index Name':<20} | {'Dimension':<10} | {'Metric':<10} | {'Status':<10} | {'Host'}")
print("-" * 100)

for index_model in pc.list_indexes():
    name = index_model.name
    try:
        details = pc.describe_index(name)
        dim = details.dimension
        metric = details.metric
        status = details.status['state']
        host = details.host
        print(f"{name:<20} | {dim:<10} | {metric:<10} | {status:<10} | {host}")
    except Exception as e:
        print(f"{name:<20} | Error: {e}")
