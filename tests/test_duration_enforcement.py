"""
Test to verify that duration enforcement is working correctly.
Tests the fix implemented in critique_node and planner_prompt.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graph import graph
from langchain_core.messages import HumanMessage

def test_duration_enforcement(duration_days, destination, budget):
    """Test that the agent creates exactly the requested number of days"""
    print("=" * 80)
    print(f"TEST: {duration_days}-day trip to {destination} with ${budget} budget")
    print("=" * 80)
    
    initial_state = {
        "messages": [HumanMessage(content=f"Plan a {duration_days} day trip to {destination} with a budget of ${budget}")],
        "user_query": f"Plan a {duration_days} day trip to {destination} with a budget of ${budget}",
        "trip_plan": None,
        "budget": None,
        "next_step": "ProfileLoader",
        "critique_feedback": None,
        "revision_count": 0,
        "steps": []
    }
    
    config = {"configurable": {"thread_id": f"test-duration-{duration_days}"}}
    
    try:
        print(f"\n[TEST] Starting graph execution...")
        
        # Run until complete or human approval
        for i, state in enumerate(graph.stream(initial_state, config)):
            if "__end__" in state:
                final_state = state["__end__"]
                trip_plan = final_state.get("trip_plan")
                
                if trip_plan and "itinerary" in trip_plan:
                    actual_days = len(trip_plan["itinerary"])
                    print(f"\n[RESULT] Expected: {duration_days} days")
                    print(f"[RESULT] Got: {actual_days} days")
                    
                    if actual_days == duration_days:
                        print(f"✅ PASS: Duration matches ({actual_days}/{duration_days})")
                        return True
                    else:
                        print(f"❌ FAIL: Duration mismatch ({actual_days}/{duration_days})")
                        print(f"\n[DEBUG] Revision count: {final_state.get('revision_count', 0)}")
                        print(f"[DEBUG] Last feedback: {final_state.get('critique_feedback', 'None')}")
                        return False
                else:
                    print("⚠️ WARNING: No trip plan generated")
                    return False
                break
                    
    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_all_tests():
    """Run comprehensive duration tests"""
    print("\n" + "="*80)
    print("RUNNING DURATION ENFORCEMENT TESTS")
    print("="*80 + "\n")
    
    test_cases = [
        (7, "Paris", 3000),
        (14, "Bali", 5000),
        (3, "Tokyo", 2000),
    ]
    
    results = []
    
    for duration, destination, budget in test_cases:
        result = test_duration_enforcement(duration, destination, budget)
        results.append((duration, destination, result))
        print("\n" + "-"*80 + "\n")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, _, result in results if result)
    total = len(results)
    
    for duration, destination, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {duration}-day trip to {destination}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({(passed/total*100):.0f}%)")
    
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
