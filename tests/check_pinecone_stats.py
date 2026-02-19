
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.tools import _get_pinecone_client_and_index

def check_pinecone_stats():
    print("Checking Pinecone Index Stats...")
    pc, index = _get_pinecone_client_and_index()
    
    if not pc or not index:
        print("❌ Pinecone client or index not available.")
        return

    try:
        stats = index.describe_index_stats()
        print("\n--- PINECONE INDEX STATS ---")
        print(f"Total Vector Count: {stats.total_vector_count}")
        print(f"Namespaces: {stats.namespaces}")
        print(f"Dimension: {stats.dimension}")
        print("----------------------------\n")
        
        if stats.total_vector_count == 0:
            print("⚠️ Index is empty! RAG tools will fallback to web search.")
        else:
            print("✅ Index populated.")
            
    except Exception as e:
        print(f"❌ Error getting stats: {e}")

if __name__ == "__main__":
    check_pinecone_stats()
