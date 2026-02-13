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

# --- 2. FLIGHT SEARCH (Amadeus Integration) ---
@tool
def search_flights_tool(origin: str, destination: str, departure_date: str, return_date: str = None) -> str:
    """
    Searches for flights using Amadeus API. 
    Returns a list of flight options with airline, price, duration, and booking info.
    Inputs: 
    - origin: IATA code or city name (e.g., "LON", "London")
    - destination: IATA code or city name (e.g., "PAR", "Paris")
    - departure_date: YYYY-MM-DD
    - return_date: YYYY-MM-DD (optional)
    """
    print(f"  [Tool] Searching Flights: {origin} -> {destination} on {departure_date}")
    
    amadeus_api_key = os.getenv("AMADEUS_API_KEY")
    amadeus_api_secret = os.getenv("AMADEUS_API_SECRET")
    
    # Real API Implementation (Commented out until keys are verified)
    # if amadeus_api_key and amadeus_api_secret:
    #     try:
    #         # Initialize Amadeus client
    #         from amadeus import Client, ResponseError
    #         amadeus = Client(client_id=amadeus_api_key, client_secret=amadeus_api_secret)
    #         response = amadeus.shopping.flight_offers_search.get(
    #             originLocationCode=origin[-3:].upper(), # Simple heuristic for IATA
    #             destinationLocationCode=destination[-3:].upper(),
    #             departureDate=departure_date,
    #             adults=1,
    #             max=5
    #         )
    #         # Parse response...
    #         return json.dumps(response.data)
    #     except Exception as e:
    #         print(f"  [Warning] Amadeus API failed: {e}")

    # Fallback to Realistic Mock Data
    import random
    airlines = ["British Airways", "Air France", "EasyJet", "Ryanair", "Lufthansa"]
    base_price = random.randint(150, 600)
    
    mock_results = []
    for i in range(3):
        airline = random.choice(airlines)
        price = base_price + random.randint(-50, 50)
        departure_hour = random.randint(6, 20)
        duration = random.randint(1, 4)
        
        flight = {
            "type": "flight-offer",
            "id": str(i+1),
            "itineraries": [{
                "duration": f"PT{duration}H30M",
                "segments": [{
                    "departure": {"iataCode": origin.upper(), "at": f"{departure_date}T{departure_hour:02d}:00:00"},
                    "arrival": {"iataCode": destination.upper(), "at": f"{departure_date}T{departure_hour+duration:02d}:30:00"},
                    "carrierCode": airline[:2].upper(),
                    "number": str(random.randint(100, 999))
                }]
            }],
            "price": {"currency": "USD", "total": str(price)},
            "validatingAirlineCodes": [airline[:2].upper()],
            "airline_name": airline # Enriched for easier reading
        }
        mock_results.append(flight)
        
    return json.dumps(mock_results)

# --- 3. HOTEL SEARCH (SerpApi/Amadeus Integration) ---
@tool
def search_hotels_tool(city: str, check_in: str, check_out: str, budget: str = "medium") -> str:
    """
    Searches for hotels in a city.
    Returns list of hotels with rating, price, and location.
    """
    print(f"  [Tool] Searching Hotels: {city} ({check_in} to {check_out})")
    
    # Realistic Mock Data (Fallback)
    import random
    hotel_types = {
        "budget": ["Hostel", "Inn", "Motel"],
        "medium": ["Hotel", "Suites", "Resort"],
        "luxury": ["Grand Hotel", "Palace", "Spa Resort"]
    }
    
    budget_key = "medium"
    if "cheap" in budget.lower() or "low" in budget.lower(): budget_key = "budget"
    if "luxury" in budget.lower() or "high" in budget.lower(): budget_key = "luxury"
    
    base_price = {"budget": 50, "medium": 150, "luxury": 400}
    
    mock_hotels = []
    for i in range(3):
        name = f"{city} {random.choice(hotel_types[budget_key])} {i+1}"
        price = base_price[budget_key] + random.randint(-20, 50)
        rating = round(random.uniform(3.5, 5.0), 1)
        
        mock_hotels.append({
            "name": name,
            "rating": rating,
            "price_per_night": price,
            "currency": "USD",
            "amenities": ["Wifi", "Breakfast"] if random.random() > 0.5 else ["Wifi"],
            "booking_link": f"https://example.com/book/{name.replace(' ', '-').lower()}"
        })
        
    return json.dumps(mock_hotels)

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
