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
def search_flights_tool(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = None,
    adults: int = 1,
) -> str:
    """
    Searches for flights using Amadeus API.
    Returns a list of flight options with airline, price, duration, and booking info.
    Inputs:
    - origin: IATA code or city name (e.g., "LON", "London")
    - destination: IATA code or city name (e.g., "PAR", "Paris")
    - departure_date: YYYY-MM-DD
    - return_date: YYYY-MM-DD (optional)
    """
    print(
        f"  [Tool] Searching Flights: {origin} -> {destination} on {departure_date} (Adults: {adults})"
    )

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
            "id": str(i + 1),
            "itineraries": [
                {
                    "duration": f"PT{duration}H30M",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": origin.upper(),
                                "at": f"{departure_date}T{departure_hour:02d}:00:00",
                            },
                            "arrival": {
                                "iataCode": destination.upper(),
                                "at": f"{departure_date}T{departure_hour+duration:02d}:30:00",
                            },
                            "carrierCode": airline[:2].upper(),
                            "number": str(random.randint(100, 999)),
                        }
                    ],
                }
            ],
            "price": {"currency": "USD", "total": str(price)},
            "validatingAirlineCodes": [airline[:2].upper()],
            "airline_name": airline,  # Enriched for easier reading
        }
        mock_results.append(flight)

    return json.dumps(mock_results)


# --- 3. HOTEL SEARCH (SerpApi/Amadeus Integration) ---
@tool
def search_hotels_tool(
    city: str,
    check_in: str,
    check_out: str,
    budget: str = "medium",
    adults: int = 1,
    amenities: Optional[List[str]] = None,
) -> str:
    """
    Searches for hotels in a city.
    Returns list of hotels with rating, price, and location.
    """
    print(
        f"  [Tool] Searching Hotels: {city} ({check_in} to {check_out}) (Adults: {adults}, Amenities: {amenities})"
    )

    amadeus_api_key = os.getenv("AMADEUS_API_KEY")
    amadeus_api_secret = os.getenv("AMADEUS_API_SECRET")

    # Real API Implementation (Commented out until keys are verified)
    if amadeus_api_key and amadeus_api_secret:
        # Map "budget" string to Amadeus priceRange format (Price per night)
        budget_map = {"budget": "0-150", "medium": "150-400", "luxury": "400-2000"}
        price_range = budget_map.get(budget.lower(), "0-1000")

        try:
            amadeus = Client(
                client_id=amadeus_api_key, client_secret=amadeus_api_secret
            )

            # STEP 1: Find Hotel IDs with specific amenities (Phase 24 filtering)
            # Amadeus expects amenities as a comma-separated string of ENUMS
            list_params = {"cityCode": city.upper()}
            if amenities:
                list_params["amenities"] = ",".join(amenities).upper()

            hotel_list = amadeus.reference_data.locations.hotels.by_city.get(
                **list_params
            )

            if not hotel_list.data:
                return f"No hotels found in {city} matching amenities: {amenities}"

            # Get top 10 IDs to check for availability
            hotel_ids = [h["hotelId"] for h in hotel_list.data[:10]]

            # STEP 2: Get specific offers/prices for those IDs
            offers_response = amadeus.shopping.hotel_offers_search.get(
                hotelIds=",".join(hotel_ids),
                adults=adults,
                checkInDate=check_in,
                checkOutDate=check_out,
                priceRange=price_range,
                currency="USD",
            )

            # STEP 3: Clean data for the AI Agent
            results = []
            for offer in offers_response.data[:3]:
                results.append(
                    {
                        "name": offer["hotel"]["name"],
                        "hotelId": offer["hotel"]["hotelId"],
                        "total_price": f"{offer['offers'][0]['price']['total']} {offer['offers'][0]['price']['currency']}",
                        "description": offer["offers"][0]["room"]
                        .get("description", {})
                        .get("text", "No description"),
                        "amenities": offer["hotel"].get("amenities", []),
                    }
                )

            return json.dumps(results, indent=2)

        except ResponseError as error:
            return f"Amadeus API error: {error}"
        except Exception as e:
            return f"Unexpected error: {e}"
    else:
        # Fallback to Realistic Mock Data
        # Realistic Mock Data (Fallback)
        import random

        hotel_types = {
            "budget": ["Hostel", "Inn", "Motel"],
            "medium": ["Hotel", "Suites", "Resort"],
            "luxury": ["Grand Hotel", "Palace", "Spa Resort"],
        }

        budget_key = "medium"
        if "cheap" in budget.lower() or "low" in budget.lower():
            budget_key = "budget"
        if "luxury" in budget.lower() or "high" in budget.lower():
            budget_key = "luxury"

        base_price = {"budget": 50, "medium": 150, "luxury": 400}

        mock_hotels = []
        for i in range(3):
            name = f"{city} {random.choice(hotel_types[budget_key])} {i+1}"
            price = base_price[budget_key] + random.randint(-20, 50)
            rating = round(random.uniform(3.5, 5.0), 1)

            mock_hotels.append(
                {
                    "name": name,
                    "rating": rating,
                    "price_per_night": price,
                    "currency": "USD",
                    "amenities": (
                        ["Wifi", "Breakfast"] if random.random() > 0.5 else ["Wifi"]
                    ),
                    "booking_link": f"https://example.com/book/{name.replace(' ', '-').lower()}",
                }
            )

        return json.dumps(mock_hotels)
