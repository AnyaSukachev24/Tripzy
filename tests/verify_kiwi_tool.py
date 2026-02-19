
import sys
import os
import json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.tools import search_flights_with_kiwi_tool

def test_kiwi_tool():
    print("Testing search_flights_with_kiwi_tool...")
    
    # Test case: London to Paris next week (approx)
    # Note: Using fixed date might be problematic for future runs, 
    # but let's pick a date reasonably far in future or dynamically.
    from datetime import datetime, timedelta
    future_date = (datetime.now() + timedelta(days=14)).strftime("%d/%m/%Y")
    
    print(f"Searching for flights LHR -> CDG on {future_date}")
    
    try:
        result = search_flights_with_kiwi_tool.invoke({
            "origin": "LHR",
            "destination": "CDG",
            "departure_date": future_date,
            "passengers": 1
        })
        
        print("\nTool Result:")
        print(result[:500] + "...") # Print first 500 chars
        
        if "Kiwi search failed" in result:
             print("FAILED: Tool returned error.")
        else:
             print("SUCCESS: Tool executed successfully.")
             
    except Exception as e:
        print(f"FAILED: Exception during tool execution: {e}")

if __name__ == "__main__":
    test_kiwi_tool()
