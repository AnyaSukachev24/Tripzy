"""
Verify Partial Plan Support: FlightOnly, HotelOnly, AttractionsOnly.
Runs 3 test cases through the live graph and checks:
1. Correct request_type detection (via Supervisor)
2. Correct tools called (e.g. only flights for FlightOnly)
3. Successful completion (SubmitPlan called) without Critique blocking.
"""
import sys
import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.graph import graph
from langchain_core.messages import ToolMessage, AIMessage

TEST_CASES = [
    {
        "id": "flight_only_london_nyc",
        "description": "Flight Only: London to NYC",
        "user_query": "Find me flights from London to NYC for next week. Just flights.",
        "expect_type": "FlightOnly",
        "expect_tools": ["search_flights_tool", "resolve_airport_code_tool"],
        "expect_no_tools": ["search_hotels_tool", "search_tours_activities_tool"],
    },
    {
        "id": "hotel_only_paris",
        "description": "Hotel Only: 4-star in Paris",
        "user_query": "I need a 4-star hotel in Paris for 3 nights starting tomorrow. No flights needed.",
        "expect_type": "HotelOnly",
        "expect_tools": ["search_hotels_tool"],
        "expect_no_tools": ["search_flights_tool"],
    },
    {
        "id": "attractions_only_tokyo",
        "description": "Attractions Only: Things to do in Tokyo",
        "user_query": "I'm going to Tokyo. I have flights and hotel. What should I do?",
        "expect_type": "AttractionsOnly",  # or Discovery
        "expect_tools": ["suggest_attractions_tool", "search_travel_knowledge"],
        "expect_no_tools": ["search_flights_tool", "search_hotels_tool"],
    },
]

def run_case(case: dict) -> dict:
    tid = case["id"]
    config = {"configurable": {"thread_id": f"verify_partial_{tid}_{int(time.time())}"}}
    print(f"\n{'='*60}")
    print(f"[{tid}] {case['description']}")
    print(f"  Query: {case['user_query']}")

    t0 = time.time()
    try:
        result = graph.invoke({"user_query": case["user_query"]}, config=config)
    except Exception as e:
        return {"id": tid, "passed": False, "error": str(e), "elapsed": time.time() - t0}

    elapsed = time.time() - t0
    
    # State inspection
    request_type = result.get("request_type")
    print(f"  Final State request_type: {request_type}")

    # Tool inspection
    messages = result.get("messages", [])
    tools_called = set()
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                tools_called.add(tc["name"])
    
    print(f"  Tools called: {sorted(list(tools_called))}")

    # Checks
    checks = {}
    
    # 1. Request Type
    # Note: AttractionsOnly might sometimes be "Discovery", which is acceptable
    if case["expect_type"] == "AttractionsOnly" and request_type in ["AttractionsOnly", "Discovery"]:
        checks["request_type"] = True
    else:
        checks[f"request_type_is_{case['expect_type']}"] = (request_type == case["expect_type"])

    # 2. Expected Tools (at least one of them should be called if list provided)
    if case["expect_tools"]:
        found_any = any(t in tools_called for t in case["expect_tools"])
        checks["expected_tool_called"] = found_any
        if not found_any:
            print(f"    [FAIL] Expected one of {case['expect_tools']}, got {tools_called}")

    # 3. Unexpected Tools (none should be called)
    for t in case["expect_no_tools"]:
        checks[f"no_{t}"] = t not in tools_called
        if t in tools_called:
             print(f"    [FAIL] Unexpected tool {t} was called!")

    # 4. Success (SubmitPlan called at end, or just finished)
    # For partial plans, we expect SubmitPlan to be called eventually
    checks["submit_plan_called"] = "SubmitPlan" in tools_called

    all_passed = all(checks.values())
    return {
        "id": tid,
        "passed": all_passed,
        "checks": checks,
        "elapsed": elapsed,
        "request_type": request_type
    }

def main():
    print("VERIFYING PARTIAL PLANS")
    results = []
    for case in TEST_CASES:
        r = run_case(case)
        results.append(r)
    
    print(f"\n{'='*60}")
    passed_count = sum(1 for r in results if r["passed"])
    print(f"SUMMARY: {passed_count}/{len(results)} PASSED")
    
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['id']} (Type: {r.get('request_type')})")
        if not r["passed"]:
            print(f"    Checks: {r['checks']}")

    if passed_count != len(results):
        sys.exit(1)

if __name__ == "__main__":
    main()
