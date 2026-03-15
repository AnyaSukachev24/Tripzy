import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.graph import graph

def test_plan_trip():
    print("--- TESTING PLANNER NODE ---")
    
    input_payload = {"user_query": "Plan a 3-day trip to Paris with a budget of $1000."}
    config = {"configurable": {"thread_id": "test_thread_1"}}
    
    try:
        # Run graph
        final_state = graph.invoke(input_payload, config=config)
        
        # Check Plan
        plan = final_state.get("trip_plan")
        if plan:
            print("\n✅ SUCCESS: Trip Plan Generated!")
            print(json.dumps(plan, indent=2))
        else:
            print("\n❌ FAILURE: No trip plan found in state.")
            print("Final State Keys:", final_state.keys())
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    test_plan_trip()
