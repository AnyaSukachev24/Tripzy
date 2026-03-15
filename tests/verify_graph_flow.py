"""
Real graph flow verification test.
Tests the full pipeline with a real user query.
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import uuid

# Override stdout for Windows encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def test_graph_discovery_flow():
    """Test: Discovery flow (where should I go?) - should NOT loop"""
    print("=" * 60)
    print("  FLOW TEST 1: Discovery - 'Where should I go?'")
    print("=" * 60)
    from app.graph import graph
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    result = graph.invoke(
        {"user_query": "I have $2000 and 7 days. I like beaches. Where should I go?"},
        config=config
    )
    
    steps = result.get("steps", [])
    modules = [s.get("module") for s in steps]
    instruction = result.get("supervisor_instruction", "")
    
    print(f"  Steps taken: {modules}")
    print(f"  Final instruction (first 200 chars): {instruction[:200]}")
    print(f"  researcher_calls: {result.get('researcher_calls', 0)}")
    print(f"  request_type: {result.get('request_type', 'N/A')}")
    
    # Assertions
    assert len(steps) > 0, "Must have at least one step"
    # Should not loop excessively (researcher_calls bounded)
    researcher_calls = result.get("researcher_calls", 0) or 0
    assert researcher_calls <= 4, f"Too many researcher calls: {researcher_calls}"
    
    print("  [OK] Discovery flow completed without looping")
    return True


def test_graph_clarification_flow():
    """Test: Incomplete query - should ask for clarification"""
    print("\n" + "=" * 60)
    print("  FLOW TEST 2: Incomplete - 'Plan a trip' (no destination)")
    print("=" * 60)
    from app.graph import graph
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    result = graph.invoke(
        {"user_query": "I want to go on a trip"},
        config=config
    )
    
    steps = result.get("steps", [])
    instruction = result.get("supervisor_instruction", "")
    next_step = result.get("next_step", "")
    
    print(f"  Steps: {[s.get('module') for s in steps]}")
    print(f"  Instruction: {instruction[:200]}")
    print(f"  next_step: {next_step}")
    
    # Should ask for clarification (destination or duration missing)
    assert next_step == "End", f"Expected End for incomplete query, got: {next_step}"
    assert any(keyword in instruction.lower() for keyword in ["where", "destination", "go", "beach", "exciting"]), \
        f"Expected clarification question, got: {instruction}"
    
    print("  [OK] Correctly asked for clarification")
    return True


def test_graph_edge_case_past_date():
    """Test: Past date should be blocked at Supervisor"""
    print("\n" + "=" * 60)
    print("  FLOW TEST 3: Past date rejection")
    print("=" * 60)
    from app.graph import graph
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    result = graph.invoke(
        {"user_query": "Plan a 5-day trip to Paris from London starting January 2020 with $3000 budget"},
        config=config
    )
    
    steps = result.get("steps", [])
    instruction = result.get("supervisor_instruction", "")
    next_step = result.get("next_step", "")
    
    print(f"  Steps: {[s.get('module') for s in steps]}")
    print(f"  Instruction: {instruction[:200]}")
    
    # Should detect past date and block
    assert next_step == "End", f"Expected End for past date, got: {next_step}"
    assert any(keyword in instruction.lower() for keyword in ["past", "2020", "date", "future", "historical"]), \
        f"Expected past date error, got: {instruction}"
    
    print("  [OK] Past date correctly blocked")
    return True


if __name__ == "__main__":
    tests = [
        ("Discovery Flow", test_graph_discovery_flow),
        ("Clarification Flow", test_graph_clarification_flow),
        ("Past Date Edge Case", test_graph_edge_case_past_date),
    ]
    
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            if fn():
                passed += 1
                print(f"  >>> PASS: {name}\n")
        except Exception as e:
            failed += 1
            print(f"  >>> FAIL: {name} - {e}\n")
            import traceback
            traceback.print_exc()
    
    print("=" * 60)
    print(f"  GRAPH FLOW RESULTS: {passed} passed, {failed} failed / {len(tests)} total")
    print("=" * 60)
