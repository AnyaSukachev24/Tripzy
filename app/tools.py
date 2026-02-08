from typing import List, Dict, Any, Optional
import json
import os
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from dotenv import load_dotenv

load_dotenv()

# --- 1. WEB SEARCH (The Researcher's Eyes) ---
@tool
def web_search_tool(query: str) -> str:
    """
    Performs a web search using DuckDuckGo.
    Optimized for Wikivoyage if 'destination' is mentioned.
    """
    print(f"  [Tool] Searching Web: {query}")
    
    # Research Insight: Prefer Wikivoyage for travel data
    if "wikivoyage" not in query.lower() and "site:" not in query.lower():
        # Auto-append if generic travel query
        # But for now, let's trust the refined prompt.
        pass

    try:
        search = DuckDuckGoSearchRun()
        return search.invoke(query)
    except Exception as e:
        return f"Search failed: {str(e)}"

# --- 2. FLIGHT SEARCH (Amadeus Test - Placeholder) ---
@tool
def search_flights_tool(origin: str, destination: str, date: str) -> str:
    """
    Searches for flights using Amadeus Test API.
    """
    print(f"  [Tool] Searching Flights: {origin} -> {destination} on {date}")
    # TODO: Implement Amadeus API call here
    return json.dumps([
        {"airline": "MockAir", "price": 450, "currency": "USD", "departure": "10:00 AM"},
        {"airline": "TestJet", "price": 420, "currency": "USD", "departure": "02:00 PM"},
    ])

# --- 3. PROFILE RAG (Pinecone - Placeholder) ---
@tool
def search_user_profile_tool(query: str) -> str:
    """
    Searches the user's profile in Pinecone for preferences.
    """
    print(f"  [Tool] RAG Search: {query}")
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        return "User likes: Budget travel, Museums, Vegan food. (Mock Profile - No API Key)"
        
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=api_key)
        index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "tripzy-users"))
        
        # Create embedding for query (Using Gemini or fake)
        # For simplicity in MVP without embedding cost, we might skip vector search 
        # and just return metadata if we can, or assume retrieval.
        # But real usage requires embeddings.
        # We'll return a placeholder string if we can't embed.
        return "User prefers: Window seats, 4-star hotels, Italian food. (Real Pinecone fetch requires embeddings)"
    except Exception as e:
        return f"Profile fetch error: {str(e)}"
