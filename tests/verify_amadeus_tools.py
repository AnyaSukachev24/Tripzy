
import os
import sys
import json
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from app.amadeus_rate_limiter import get_amadeus_client
from app.tools import (
    resolve_airport_code_tool,
    get_airline_info_tool,
    search_tours_activities_tool,
    search_points_of_interest_tool,
    search_cheapest_dates_tool,
)

def run_verification():
    print("=== Verifying Amadeus Tools & Rate Limiter ===")
    
    # Check credentials
    api_key = os.getenv("AMADEUS_API_KEY")
    api_secret = os.getenv("AMADEUS_API_SECRET")
    if not api_key or not api_secret:
        print("[FAIL] AMADEUS_API_KEY or AMADEUS_API_SECRET not found in environment.")
        print("Skipping real API tests.")
        return

    client = get_amadeus_client()
    if not client:
        print("❌ Failed to initialize Amadeus client.")
        return
    print("[PASS] Amadeus client initialized (Rate Limiter Active)")

    # 1. Resolve Airport Code
    print("\n--- Test 1: Resolve Airport Code (Paris) ---")
    try:
        res = resolve_airport_code_tool.invoke("Paris")
        print(f"Result: {res[:200]}...")
        data = json.loads(res)
        if isinstance(data, list) and len(data) > 0 and "iataCode" in data[0]:
            print("[PASS] Resolve Airport Code: PASSED")
        else:
            print("[FAIL] Resolve Airport Code: FAILED (Invalid format)")
    except Exception as e:
        print(f"[FAIL] Resolve Airport Code: FAILED ({e})")

    # 2. Airline Info
    print("\n--- Test 2: Airline Info (BA - British Airways) ---")
    try:
        res = get_airline_info_tool.invoke("BA")
        print(f"Result: {res[:200]}...")
        data = json.loads(res)
        if isinstance(data, list) and len(data) > 0 and "businessName" in data[0]:
            print("[PASS] Airline Info: PASSED")
        else:
            print("[FAIL] Airline Info: FAILED (Invalid format)")
    except Exception as e:
        print(f"[FAIL] Airline Info: FAILED ({e})")

    # 3. Tours & Activities
    print("\n--- Test 3: Tours & Activities (Paris Lat/Lng) ---")
    try:
        # Paris: 48.8566, 2.3522
        res = search_tours_activities_tool.invoke({"latitude": 48.8566, "longitude": 2.3522})
        print(f"Result: {res[:200]}...")
        data = json.loads(res)
        if isinstance(data, list):
             # It might be empty if API has no content for test env or location, but list is good
            print(f"[PASS] Tours & Activities: PASSED (Found {len(data)} items)")
        elif isinstance(data, dict) and "error" in data:
             print(f"[WARN] Tours & Activities: API Error ({data['error']})")
        else:
            print("[FAIL] Tours & Activities: FAILED (Invalid format)")
    except Exception as e:
        print(f"[FAIL] Tours & Activities: FAILED ({e})")

    # 4. Points of Interest
    print("\n--- Test 4: Points of Interest (Paris Lat/Lng) ---")
    try:
        res = search_points_of_interest_tool.invoke({"latitude": 48.8566, "longitude": 2.3522, "categories": ["SIGHTS"]})
        print(f"Result: {res[:200]}...")
        data = json.loads(res)
        if isinstance(data, list):
            print(f"[PASS] Points of Interest: PASSED (Found {len(data)} items)")
        elif isinstance(data, dict) and "results" in data:
             print(f"[WARN] Points of Interest: API Warning ({data.get('warning', 'Unknown')}) - Found {len(data['results'])} mock items")
        elif isinstance(data, dict) and "error" in data:
             print(f"[WARN] Points of Interest: API Error ({data['error']})")
        else:
            print("[FAIL] Points of Interest: FAILED (Invalid format)")
    except Exception as e:
        print(f"[FAIL] Points of Interest: FAILED ({e})")

    # 5. Cheapest Dates
    print("\n--- Test 5: Cheapest Dates (LHR -> JFK) ---")
    try:
        res = search_cheapest_dates_tool.invoke({"origin": "LHR", "destination": "JFK"})
        print(f"Result: {res[:200]}...")
        data = json.loads(res)
        if isinstance(data, list):
            print(f"[PASS] Cheapest Dates: PASSED (Found {len(data)} items)")
        elif isinstance(data, dict) and "results" in data:
             print(f"[WARN] Cheapest Dates: API Warning ({data.get('warning', 'Unknown')}) - Found {len(data['results'])} mock items")
        elif isinstance(data, dict) and "error" in data:
             print(f"[WARN] Cheapest Dates: API Error ({data['error']})")
        else:
            print("[FAIL] Cheapest Dates: FAILED (Invalid format)")
    except Exception as e:
        print(f"[FAIL] Cheapest Dates: FAILED ({e})")

if __name__ == "__main__":
    run_verification()
