import json
import os
import time
from dotenv import load_dotenv
from dotenv import load_dotenv
from langchain_core.documents import Document

# Load environment variables
load_dotenv()


def ingest_clients():
    print("--- Starting Client Ingestion ---")

    # Check for required environment variables
    if not os.getenv("PINECONE_API_KEY"):
        print("Error: PINECONE_API_KEY not found in environment variables.")
        return

    index_name = os.getenv("PINECONE_INDEX_NAME")
    if not index_name:
        print("Error: PINECONE_INDEX_NAME not found in environment variables.")
        return

    # 1. Load Data
    data_path = os.path.join(os.getcwd(), "data", "clients.json")
    if not os.path.exists(data_path):
        print(f"Error: File not found at {data_path}")
        return

    with open(data_path, "r") as f:
        clients = json.load(f)

    print(f"Loaded {len(clients)} clients from {data_path}")

    # 2. Prepare Documents
    documents = []
    for client in clients:
        # Create a rich text representation for embedding (optional, but summary is usually enough)
        # We'll just use the summary as the main content for semantic search
        page_content = client.get("summary", "")

        # Prepare metadata for filtering
        # Ensure values are compatible with Pinecone metadata (no None/null values if possible, convert to str)
        metadata = {
            "client_id": str(client.get("id")),
            "name": client.get("name") or "Unknown",
            "email": client.get("email") or "Unknown",
            "status": client.get("status") or "Unknown",
            "waiting_for": client.get("waiting_for") or "Unknown",
            "destination": client.get("destination") or "Unknown",
            "budget": (
                str(client.get("budget"))
                if client.get("budget") is not None
                else "Unknown"
            ),
            "num_people": (
                int(client.get("num_people")) if client.get("num_people") else 1
            ),
            "is_returning": bool(client.get("is_returning")),
        }

        doc = Document(page_content=page_content, metadata=metadata)
        documents.append(doc)

    # 3. Initialize Pinecone
    try:
        from pinecone import Pinecone
    except ImportError:
        print("Error: 'pinecone' package not found.")
        return

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    
    if index_name not in pc.list_indexes().names():
        print(f"Error: Index '{index_name}' not found.")
        return
        
    index = pc.Index(index_name)

    # 4. Ingest into Pinecone
    print(f"Ingesting {len(documents)} documents into Pinecone index '{index_name}' (namespace: clients)...")
    
    try:
        # Prepare text for embedding
        texts = [doc.page_content for doc in documents]
        
        # Generate embeddings via inference API
        embeddings_response = pc.inference.embed(
            model="llama-text-embed-v2",
            inputs=texts,
            parameters={"input_type": "passage", "truncate": "END"}
        )
        
        # Prepare vectors
        vectors = []
        for i, embedding_data in enumerate(embeddings_response):
            doc = documents[i]
            # Ensure metadata is flat and compatible (strings, numbers, booleans, list of strings)
            metadata = doc.metadata.copy()
            clean_metadata = {k: str(v) if not isinstance(v, (str, int, float, bool, list)) else v for k, v in metadata.items()}
            # Add text
            clean_metadata["text"] = doc.page_content
            
            vectors.append({
                "id": str(clean_metadata.get("client_id", f"client_{i}")),
                "values": embedding_data["values"],
                "metadata": clean_metadata
            })
            
        # Upsert
        index.upsert(vectors=vectors, namespace="clients")
        
        print("--- Ingestion Complete ---")
        print(f"Successfully added {len(vectors)} clients to index '{index_name}'")

    except Exception as e:
        print(f"Error during ingestion: {e}")


if __name__ == "__main__":
    ingest_clients()
