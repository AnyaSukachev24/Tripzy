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
    Performs a web search using DuckDuckGo (Free).
    Useful for finding local events, weather, or general travel advice.
    """
    print(f"  [Tool] Searching Web: {query}")
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
    Searches user history in Pinecone.
    """
    print(f"  [Tool] RAG Search: {query}")
    # TODO: Implement Pinecone lookup
    return "User loves hiking and vegan food. Budget conscious."
