"""
Test script to debug Tripzy agent flow
Tests: Plan a 14 day honeymoon trip to Bali for 2 people with a budget of $5000
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graph import graph
from langchain_core.messages import HumanMessage

def test_bali_prompt():
    print("="*80)
    print("TESTING: Plan a 14 day honeymoon trip to Bali for 2 people with a budget of $5000")
    print("="*80)
    
    initial_state = {
        "messages": [HumanMessage(content="Plan a 14 day honeymoon trip to Bali for 2 people with a budget of $5000")],
        "user_query": "Plan a 14 day honeymoon trip to Bali for 2 people with a budget of $5000",
        "trip_plan": None,
        "budget": None,
        "next_step": "ProfileLoader",
        "critique_feedback": None,
        "revision_count": 0,
        "steps": []
    }
    
    print("\n[TEST] Starting graph execution...")
    
    config = {"configurable": {"thread_id": "test-bali-1"}}
    
    try:
        # Run until human approval needed
        for i, state in enumerate(graph.stream(initial_state, config)):
            print(f"\n[TEST] Step {i+1}: {list(state.keys())}")
            
            # Check if we have trip plan
            if "__end__" in state:
                final_state = state["__end__"]
                print("\n" + "="*80)
                print("FINAL STATE REACHED")
                print("="*80)
                
                trip_plan = final_state.get("trip_plan")
                duration_days = final_state.get("duration_days")
                
                print(f"\n[RESULT] Duration Days in State: {duration_days}")
                
                if trip_plan:
                    print(f"\n[RESULT] Destination: {trip_plan.get('destination')}")
                    itinerary = trip_plan.get('itinerary', [])
                    print(f"[RESULT] Itinerary Length: {len(itinerary)} days")
                    print(f"[RESULT] Budget Estimate: ${trip_plan.get('budget_estimate')}")
                    
                    print("\n[ANALYSIS]")
                    print(f"  Expected: 14 days to Bali")
                    print(f"  Got: {len(itinerary)} days to {trip_plan.get('destination')}")
                    
                    if "Bali" not in trip_plan.get('destination', ''):
                        print("  ❌ FAIL: Wrong destination!")
                    else:
                        print("  ✅ PASS: Correct destination!")
                        
                    if len(itinerary) != 14:
                        print(f"  ❌ FAIL: Wrong duration! ({len(itinerary)} != 14)")
                    else:
                        print("  ✅ PASS: Correct duration!")
                
                break
                
            # Check for interrupt
            if "Trip_Planner" in state:
                planner_state = state["Trip_Planner"]
                if planner_state.get("next_step") == "Human_Approval":
                    print("\n[TEST] Reached human approval point")
                    print(f"[TEST] Trip Plan: {planner_state.get('trip_plan')}")
                    break
                    
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_bali_prompt()
