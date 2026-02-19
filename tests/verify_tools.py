"""
Quick verification script for all 7 Tripzy tools.
Tests imports, mock fallbacks, and live Amadeus API.
"""
import json
import sys
import os

# Ensure we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def test_imports():
    """Test all 7 tools import correctly."""
    print("=" * 60)
    print("  TEST 1: Import All Tools")
    print("=" * 60)
    from app.tools import (
        web_search_tool,
        search_flights_tool,
        search_hotels_tool,
        suggest_destination_tool,
        suggest_attractions_tool,
        create_user_profile_tool,
        create_plan_tool,
    )
    tools = [
        web_search_tool,
        search_flights_tool,
        search_hotels_tool,
        suggest_destination_tool,
        suggest_attractions_tool,
        create_user_profile_tool,
        create_plan_tool,
    ]
    print(f"  [OK] All {len(tools)} tools imported: {[t.name for t in tools]}")
    return True


def test_flight_search():
    """Test flight search tool (should use Amadeus if keys available, else mock)."""
    print("\n" + "=" * 60)
    print("  TEST 2: Flight Search")
    print("=" * 60)
    from app.tools import search_flights_tool

    has_keys = bool(os.getenv("AMADEUS_API_KEY") and os.getenv("AMADEUS_API_SECRET"))
    print(f"  Amadeus keys present: {has_keys}")

    result = search_flights_tool.invoke({
        "origin": "LON",
        "destination": "PAR",
        "departure_date": "2026-06-01",
        "return_date": "2026-06-07",
        "adults": 1,
    })

    data = json.loads(result)
    print(f"  [OK] Returned {len(data)} flight offers")
    if data:
        first = data[0]
        print(f"     Price: {first.get('price', {}).get('total', 'N/A')} {first.get('price', {}).get('currency', '')}")
        if first.get("validatingAirlineCodes"):
            print(f"     Airline: {first['validatingAirlineCodes']}")
    return True


def test_hotel_search():
    """Test hotel search tool."""
    print("\n" + "=" * 60)
    print("  TEST 3: Hotel Search")
    print("=" * 60)
    from app.tools import search_hotels_tool

    result = search_hotels_tool.invoke({
        "city": "PAR",
        "check_in": "2026-06-01",
        "check_out": "2026-06-07",
        "budget": "medium",
        "adults": 1,
    })

    data = json.loads(result)
    print(f"  [OK] Returned {len(data)} hotel offers")
    if data:
        first = data[0]
        print(f"     Hotel: {first.get('name', 'N/A')}")
        price_key = 'total_price' if 'total_price' in first else 'price_per_night'
        print(f"     Price: {first.get(price_key, 'N/A')}")
    return True


def test_suggest_destination():
    """Test destination suggestion tool."""
    print("\n" + "=" * 60)
    print("  TEST 4: Suggest Destination")
    print("=" * 60)
    from app.tools import suggest_destination_tool

    result = suggest_destination_tool.invoke({
        "preferences": "beach relaxation warm weather",
        "budget_tier": "medium",
        "trip_type": "honeymoon",
        "climate": "tropical",
    })

    data = json.loads(result)
    print(f"  [OK] Got destination suggestions")
    if isinstance(data, dict) and "suggestions" in data:
        print(f"     Source: {data.get('source', 'unknown')}")
        print(f"     Result preview: {str(data.get('suggestions', ''))[:150]}...")
    elif isinstance(data, list):
        print(f"     Found {len(data)} destinations")
    return True


def test_suggest_attractions():
    """Test attraction suggestion tool."""
    print("\n" + "=" * 60)
    print("  TEST 5: Suggest Attractions")
    print("=" * 60)
    from app.tools import suggest_attractions_tool

    result = suggest_attractions_tool.invoke({
        "destination": "Paris",
        "interests": ["history", "food", "art"],
        "trip_type": "romantic",
    })

    data = json.loads(result)
    print(f"  [OK] Got attraction suggestions")
    if isinstance(data, dict):
        print(f"     Source: {data.get('source', 'unknown')}")
    elif isinstance(data, list):
        print(f"     Found {len(data)} attractions")
    return True


def test_create_user_profile():
    """Test user profile creation tool."""
    print("\n" + "=" * 60)
    print("  TEST 6: Create User Profile")
    print("=" * 60)
    from app.tools import create_user_profile_tool

    result = create_user_profile_tool.invoke({
        "name": "Test User",
        "email": "test@example.com",
        "preferences": ["beach", "history", "food"],
        "dietary_needs": ["vegan"],
        "travel_style": "medium",
    })

    data = json.loads(result)
    print(f"  [OK] Profile created: {data.get('status', 'unknown')}")
    print(f"     Name: {data.get('profile', {}).get('name', 'N/A')}")
    return True


def test_create_plan():
    """Test plan creation tool."""
    print("\n" + "=" * 60)
    print("  TEST 7: Create Plan")
    print("=" * 60)
    from app.tools import create_plan_tool

    result = create_plan_tool.invoke({
        "destination": "Paris, France",
        "origin": "London",
        "duration_days": 5,
        "budget": 3000.0,
        "currency": "USD",
        "trip_type": "honeymoon",
        "travelers": 2,
    })

    data = json.loads(result)
    print(f"  [OK] Plan created!")
    print(f"     Destination: {data.get('destination')}")
    print(f"     Duration: {data.get('duration_days')} days")
    print(f"     Budget: ${data.get('budget', {}).get('total', 'N/A')}")
    print(f"     Itinerary days: {len(data.get('itinerary', []))}")
    return True


def test_search_activities():
    """Test tours and activities search."""
    print("\n" + "=" * 60)
    print("  TEST 8: Search Activities")
    print("=" * 60)
    from app.tools import search_activities_tool
    
    # Paris coordinates
    result = search_activities_tool.invoke({
        "latitude": 48.8566,
        "longitude": 2.3522,
        "radius": 5
    })
    
    data = json.loads(result)
    print(f"  [OK] Returned {len(data)} activities")
    if data and isinstance(data, list):
        print(f"     Example: {data[0].get('name', 'N/A')} - {data[0].get('price', {}).get('amount', 'N/A')}")
    return True


def test_flight_price_analysis():
    """Test flight price analysis."""
    print("\n" + "=" * 60)
    print("  TEST 9: Flight Price Analysis")
    print("=" * 60)
    from app.tools import flight_price_analysis_tool
    
    result = flight_price_analysis_tool.invoke({
        "origin": "MAD",
        "destination": "NYC",
        "departure_date": "2026-06-01"
    })
    
    data = json.loads(result)
    print(f"  [OK] Analysis Result: {data.get('summary', 'No summary')}")
    return True


def test_flight_status():
    """Test flight status."""
    print("\n" + "=" * 60)
    print("  TEST 10: Flight Status")
    print("=" * 60)
    from app.tools import flight_status_tool
    
    result = flight_status_tool.invoke({
        "carrier_code": "BA",
        "flight_number": "117",
        "date": "2026-06-01"
    })
    
    data = json.loads(result)
    print(f"  [OK] Status: {data.get('status', 'Unknown')}")
    return True


def test_airport_search():
    """Test airport/city search."""
    print("\n" + "=" * 60)
    print("  TEST 11: Airport Search")
    print("=" * 60)
    from app.tools import airport_search_tool
    
    result = airport_search_tool.invoke({"keyword": "London"})
    
    data = json.loads(result)
    print(f"  [OK] Found {len(data)} locations")
    if data:
        print(f"     First match: {data[0].get('name')} ({data[0].get('iataCode')})")
    return True


def test_airline_lookup():
    """Test airline lookup."""
    print("\n" + "=" * 60)
    print("  TEST 12: Airline Lookup")
    print("=" * 60)
    from app.tools import airline_lookup_tool
    
    result = airline_lookup_tool.invoke({"airline_code": "LH"})
    
    data = json.loads(result)
    print(f"  [OK] Airline Info: {data[0].get('businessName') if isinstance(data, list) and data else 'N/A'}")
    return True


def test_travel_recommendations():
    """Test travel recommendations."""
    print("\n" + "=" * 60)
    print("  TEST 13: Travel Recommendations")
    print("=" * 60)
    from app.tools import travel_recommendations_tool
    
    result = travel_recommendations_tool.invoke({"city_code": "PAR"})
    
    data = json.loads(result)
    print(f"  [OK] Recommended {len(data)} destinations")
    if data:
        print(f"     Top pick: {data[0].get('name')} ({data[0].get('iataCode')})")
    return True


def test_cheapest_flights():
    """Test cheapest flight dates."""
    print("\n" + "=" * 60)
    print("  TEST 14: Cheapest Flight Dates")
    print("=" * 60)
    from app.tools import cheapest_flights_tool
    
    result = cheapest_flights_tool.invoke({
        "origin": "LHR",
        "destination": "JFK"
    })
    
    data = json.loads(result)
    print(f"  [OK] Found {len(data)} cheapest date options")
    if data:
        print(f"     Best Price: {data[0].get('price', 'N/A')}")
    return True


def test_hotel_ratings():
    """Test hotel ratings."""
    print("\n" + "=" * 60)
    print("  TEST 15: Hotel Ratings")
    print("=" * 60)
    from app.tools import hotel_ratings_tool
    
    result = hotel_ratings_tool.invoke({"hotel_ids": ["ADPAR001"]})
    
    data = json.loads(result)
    print(f"  [OK] Ratings found: {len(data) > 0}")
    if data:
        print(f"     Sentiment: {data[0].get('overallRating', 'N/A')}/100")
    return True


if __name__ == "__main__":
    print("\nTRIPZY TOOLS VERIFICATION\n")

    tests = [
        ("Imports", test_imports),
        ("Flight Search", test_flight_search),
        ("Hotel Search", test_hotel_search),
        ("Destination Suggestion", test_suggest_destination),
        ("Attraction Suggestion", test_suggest_attractions),
        ("User Profile", test_create_user_profile),
        ("Create Plan", test_create_plan),
        ("Search Activities", test_search_activities),
        ("Flight Price Analysis", test_flight_price_analysis),
        ("Flight Status", test_flight_status),
        ("Airport Search", test_airport_search),
        ("Airline Lookup", test_airline_lookup),
        ("Travel Recommendations", test_travel_recommendations),
        ("Cheapest Flights", test_cheapest_flights),
        ("Hotel Ratings", test_hotel_ratings),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {name} FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 60)
