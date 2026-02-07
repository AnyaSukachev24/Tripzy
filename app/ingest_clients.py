import json
import os
import time
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_pinecone import PineconeVectorStore
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

    # 3. Initialize Embeddings
    # specific model can be "models/embedding-001" or "models/text-embedding-004" depending on availability
    # We will use "models/text-embedding-004" as it is generally better for retrieval tasks with Gemini
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

    # 4. Ingest into Pinecone
    print(f"Ingesting {len(documents)} documents into Pinecone index '{index_name}'...")

    try:
        # Using from_documents automatically uses the environment variables for API key if set (PINECONE_API_KEY)
        vector_store = PineconeVectorStore.from_documents(
            documents=documents, embedding=embeddings, index_name=index_name
        )
        print("--- Ingestion Complete ---")
        print(f"Successfully added {len(documents)} clients to index '{index_name}'")

    except Exception as e:
        print(f"Error during ingestion: {e}")


if __name__ == "__main__":
    ingest_clients()
