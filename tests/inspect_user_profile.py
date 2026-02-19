
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

from pinecone import Pinecone

def inspect_profile():
    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME")
    
    if not api_key or not index_name:
        print("Error: Missing Pinecone env vars.")
        return

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)
    
    # Query for any vector in user_profiles namespace
    # We use a dummy vector of 0s. Dimension is 1024.
    dummy_vec = [0.0] * 1024
    
    try:
        results = index.query(
            vector=dummy_vec,
            top_k=5,
            namespace="user_profiles",
            include_metadata=True
        )
        
        print(f"Found {len(results.matches)} profiles.")
        for match in results.matches:
            print("-" * 40)
            print(f"ID: {match.id}")
            print(f"Score: {match.score}")
            print("Metadata:")
            for k, v in match.metadata.items():
                print(f"  {k}: {v}")
                
    except Exception as e:
        print(f"Error querying Pinecone: {e}")

if __name__ == "__main__":
    inspect_profile()
