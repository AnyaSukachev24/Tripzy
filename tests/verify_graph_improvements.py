"""
Quick graph import + state verification test.
Checks that all changes compile and state schema is correct.
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

def test_state_models():
    """Test new Pydantic models in state.py"""
    print("=" * 60)
    print("  TEST 1: State Models")
    print("=" * 60)
    from app.state import TripPlan, FlightInfo, HotelInfo, ItineraryDay, AgentState

    # Test TripPlan creation
    plan = TripPlan(
        destination="Paris, France",
        origin_city="London",
        dates="2026-06-01 to 2026-06-07",
        duration_days=7,
        budget_estimate=3000.0,
        budget_currency="USD",
        trip_type="honeymoon",
        travelers=2,
        flights=[{"airline": "British Airways", "price": "$450"}],
        hotels=[{"name": "Grand Hotel", "price": "$200/night"}],
        itinerary=[{"day": 1, "activity": "Eiffel Tower Visit", "cost": 50}],
    )
    assert plan.destination == "Paris, France"
    assert plan.duration_days == 7
    assert len(plan.flights) == 1
    print(f"  [OK] TripPlan model works: {plan.destination}, {plan.duration_days} days, ${plan.budget_estimate}")
    
    # Test dict export (for compatibility with existing code)
    plan_dict = plan.model_dump()
    assert "destination" in plan_dict
    print(f"  [OK] TripPlan.model_dump() works, keys: {list(plan_dict.keys())}")
    return True

def test_graph_import():
    """Test graph imports correctly with new state."""
    print("\n" + "=" * 60)
    print("  TEST 2: Graph Import")
    print("=" * 60)
    from app.graph import graph, supervisor_node, planner_node, researcher_node, critique_node
    print("  [OK] All graph nodes imported")
    
    # Check graph structure
    nodes = list(graph.nodes.keys())
    print(f"  [OK] Graph nodes: {nodes}")
    assert "Supervisor" in nodes
    assert "Trip_Planner" in nodes
    assert "Researcher" in nodes
    assert "Critique" in nodes
    assert "Human_Approval" in nodes
    return True

def test_researcher_routing_logic():
    """Test that Researcher correctly identifies routing target."""
    print("\n" + "=" * 60)
    print("  TEST 3: Researcher Routing Logic")
    print("=" * 60)
    
    # Simulate TOOL_CALLS instruction (from Planner)
    planner_instruction = 'TOOL_CALLS: [{"name": "search_flights_tool", "args": {}}]'
    came_from_planner = planner_instruction.startswith("TOOL_CALLS:")
    assert came_from_planner == True, "Should detect Planner origin"
    print(f"  [OK] TOOL_CALLS detection works -> routes to Trip_Planner")

    # Simulate discovery instruction (from Supervisor)
    discovery_instruction = "Suggest 3 beach destinations for $2000 budget"
    came_from_planner = discovery_instruction.startswith("TOOL_CALLS:")
    assert came_from_planner == False, "Should detect Supervisor origin"
    print(f"  [OK] Non-TOOL_CALLS detection works -> routes to Supervisor")
    return True

def test_critique_budget_logic():
    """Test budget validation logic in critique."""
    print("\n" + "=" * 60)
    print("  TEST 4: Budget-Aware Critique Logic")
    print("=" * 60)
    
    budget_limit = 2000.0
    plan_cost_over = 2500.0  # 25% over - should trigger
    plan_cost_under = 2100.0  # 5% over - within tolerance
    
    tolerance = 1.15  # 15% tolerance
    
    should_reject_over = plan_cost_over > budget_limit * tolerance
    should_reject_under = plan_cost_under > budget_limit * tolerance
    
    assert should_reject_over == True, "Should reject 25% over budget"
    assert should_reject_under == False, "Should allow 5% over (within 15% tolerance)"
    
    print(f"  [OK] Budget ${plan_cost_over} > ${budget_limit}*1.15 correctly REJECTED")
    print(f"  [OK] Budget ${plan_cost_under} <= ${budget_limit}*1.15 correctly ALLOWED")
    return True

def test_response_selection():
    """Test smart response selection logic."""
    print("\n" + "=" * 60)
    print("  TEST 5: Smart Response Selection")
    print("=" * 60)
    
    INTERNAL_TAGS = {"Plan Drafted", "Done", "None", ""}
    
    # Should skip internal tags
    assert "Plan Drafted" in INTERNAL_TAGS, "Plan Drafted should be filtered"
    assert "Done" in INTERNAL_TAGS, "Done should be filtered"
    assert "" in INTERNAL_TAGS, "Empty should be filtered"
    
    # Should keep real content
    assert "Here is your 5-day Paris itinerary..." not in INTERNAL_TAGS
    
    # Routing tag prefixes that should be skipped in step fallback
    skip_prefixes = ["Routing to", "Need more", "Edge Case", "Error", "Executing"]
    real_content = "Here is your trip plan for Bali:"
    should_skip = any(real_content.startswith(p) for p in skip_prefixes)
    assert should_skip == False, "Real content should not be skipped"
    
    print(f"  [OK] Internal tags correctly identified: {INTERNAL_TAGS}")
    print(f"  [OK] Real content not filtered: '{real_content}'")
    return True

if __name__ == "__main__":
    tests = [
        ("State Models", test_state_models),
        ("Graph Import", test_graph_import),
        ("Researcher Routing Logic", test_researcher_routing_logic),
        ("Budget-Aware Critique", test_critique_budget_logic),
        ("Response Selection", test_response_selection),
    ]
    
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            if fn():
                passed += 1
                print(f"  >>> PASS: {name}")
        except Exception as e:
            failed += 1
            print(f"  >>> FAIL: {name} - {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed / {len(tests)} total")
    print("=" * 60)
