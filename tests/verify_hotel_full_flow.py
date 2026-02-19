
import sys
import os
import json
from dotenv import load_dotenv

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

from app.graph import graph

def run_test():
    print("--- Hotel Search Full Flow Verification ---")
    # Query designed to trigger hotel search with specific dates and sorting request
    user_query = "Find me a hotel in Paris for Jun 1-5 2026. I want the best rated one. Please sort by rating."
    print(f"User Query: {user_query}")
    
    config = {"configurable": {"thread_id": "verify_hotel_flow"}}
    
    try:
        # Invoke the graph (Planner -> Researcher/Tools -> Planner -> Response)
        result = graph.invoke({"user_query": user_query}, config=config)
        plan = result.get("trip_plan", {})
        
        print("\n--- Result Plan ---")
        print(json.dumps(plan, indent=2))
        
        # Validation Logic
        passed = True
        
        # Check Hotel Section
        hotels = plan.get("accommodation", [])
        if not hotels:
            print("[WARN] No accommodation found in structured 'trip_plan'. Checking raw messages...")
            # If planner returns text instead of structure, we might need to check result['messages']
            # But graph usually returns structured plan.
            passed = False
        else:
            print(f"Found {len(hotels)} hotels.")
            first = hotels[0]
            print(f"Top Hotel: {first.get('name')} | Rating: {first.get('rating')}")
            
            # 1. Check Rating Presence
            if "rating" in first or "sentiment" in str(first):
                 print("[PASS] Rating info present.")
            else:
                 print("[FAIL] Rating info missing.")
                 passed = False

            # 2. Check Location Info
            if "location" in first:
                 loc = first["location"]
                 if isinstance(loc, dict) and "address" in loc:
                     print(f"[PASS] Location info present: {loc['address']}")
                 else:
                     print("[WARN] Location present but missing address field.")
            else:
                 print("[FAIL] Location info missing.")
                 passed = False
        
        if passed:
            print("\n✅ Verification PASSED: Tool output contains enhanced fields (rating/location).")
        else:
            print("\n❌ Verification FAILED: Missing required enhanced fields.")
            
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
