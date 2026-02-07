from typing import List, Dict, Any, Optional
import os
import json
from langchain_core.tools import tool
from langchain_pinecone import PineconeVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv

load_dotenv()


# --- 1. SEARCH CUSTOMERS (RAG) ---
@tool
def search_customers_tool(query: str) -> str:
    """
    Searches the client database (Pinecone) for the most relevant customer profile.
    Returns the customer's full profile as a JSON string.
    """
    print(f"  [Tool] Searching customers for: {query}")

    # 1. Initialize Vector Store
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    index_name = os.getenv("PINECONE_INDEX_NAME")

    try:
        vector_store = PineconeVectorStore(index_name=index_name, embedding=embeddings)

        # 2. Retrieval
        # We retrieve 1 best match because we want "THE" customer
        docs = vector_store.similarity_search(query, k=1)

        if not docs:
            return "No matching customer found."

        # 3. Format Output
        # Reconstruct the customer dict from metadata + page_content
        best_doc = docs[0]
        customer_data = best_doc.metadata
        customer_data["summary"] = best_doc.page_content

        # Ensure ID is an int/str as needed
        return json.dumps(customer_data, indent=2)

    except Exception as e:
        return f"Error connecting to DB: {str(e)}"


# --- 2. SEARCH DESTINATIONS (Wikivoyage Mock) ---
@tool
def search_destinations_tool(tags: List[str]) -> str:
    """
    Searches for destinations matching the given tags (e.g., "beaches", "history", "wine").
    Returns a list of top matching destinations.
    """
    print(f"  [Tool] Searching destinations for tags: {tags}")

    # MOCK DB for now (Phase 2.2 was skipped/mocked)
    mock_destinations = [
        {
            "name": "Tuscany, Italy",
            "tags": ["wine", "history", "art", "nature"],
            "description": "Famous for its landscapes, history, artistic legacy, and its influence on high culture.",
        },
        {
            "name": "Kyoto, Japan",
            "tags": ["history", "culture", "nature", "temples"],
            "description": "Famous for its classical Buddhist temples, gardens, imperial palaces, Shinto shrines and traditional wooden houses.",
        },
        {
            "name": "Bora Bora, French Polynesia",
            "tags": ["beaches", "luxury", "romance", "nature"],
            "description": "A major international tourist destination, famous for its aqua-centric luxury resorts.",
        },
        {
            "name": "Paris, France",
            "tags": ["history", "art", "romance", "city"],
            "description": "The global center for art, fashion, gastronomy and culture.",
        },
        {
            "name": "New York City, USA",
            "tags": ["city", "business", "nightlife", "shopping"],
            "description": "The most populous city in the United States, known for its skyline, culture, and energy.",
        },
    ]

    # Simple keyword matching
    matches = []
    for dest in mock_destinations:
        if any(tag.lower() in [t.lower() for t in dest["tags"]] for tag in tags):
            matches.append(dest)

    if not matches:
        return "No specific destinations found for these tags. Suggest popular ones."

    return json.dumps(matches[:3], indent=2)


# --- 3. ACTION TOOLS (Executors) ---


@tool
def book_service_tool(service_type: str, details: str) -> str:
    """
    Books a service (flight, hotel, car).
    Args:
        service_type: "flight", "hotel", or "car"
        details: description of what to book
    Returns: Confirmation ID
    """
    print(f"  [Tool] Booking {service_type}: {details}")
    import uuid

    confirmation_id = str(uuid.uuid4())[:8].upper()
    return f"Booking confirmed. ID: #{confirmation_id}"


@tool
def send_email_tool(recipient: str, subject: str, body: str) -> str:
    """
    Sends an email to the customer.
    """
    print(f"  [Tool] Sending Email to {recipient}")
    return f"Email sent successfully to {recipient}."


@tool
def generate_itinerary_file_tool(plan_summary: str) -> str:
    """
    Generates a PDF/Text file for the itinerary.
    """
    print(f"  [Tool] Generating File")
    return "Itinerary_Final.pdf generated."
