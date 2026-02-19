"""
Full-flow validation: 5 real use cases from the golden dataset run through the live graph.
Tests: routing, tool dispatch, RAG, hotel/flight results, edge case detection.
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

# ---------------------------------------------------------------------------
# Real use cases (subsets from golden_dataset.json + extra spot-checks)
# ---------------------------------------------------------------------------
TEST_CASES = [
    {
        "id": "family_paris_7d",
        "description": "7-day family trip to Paris — full plan: flights + hotels + activities",
        "user_query": "Plan a 7 day family trip to Paris from London for 2 adults and 2 kids, budget $3000",
        "expect_tools": ["search_flights_tool", "search_hotels_tool"],
        "expect_plan_keys": ["flights", "hotels"],
    },
    {
        "id": "flights_only_request",
        "description": "Flights-only — London to Dubai for 5 days in March",
        "user_query": "Find me the best flights from London to Dubai for 5 days in March, budget $800 for flights only",
        "expect_tools": ["search_flights_tool"],
        "expect_plan_keys": ["flights"],
    },
    {
        "id": "solo_tokyo_rag",
        "description": "5-day solo Tokyo — should call suggest_attractions_tool (RAG)",
        "user_query": "Plan a 5 day solo cultural trip to Tokyo from LA, budget $1800",
        "expect_tools": ["suggest_attractions_tool", "search_hotels_tool"],
        "expect_plan_keys": [],
    },
    {
        "id": "extreme_budget_impossible",
        "description": "Edge case: $20 budget — should be blocked by edge case validator",
        "user_query": "I want to travel for a week with only $20",
        "expect_tools": [],           # No tools — blocked before planning
        "expect_edge_block": True,    # Graph should return at Supervisor with error message
    },
    {
        "id": "vague_romantic_beaches",
        "description": "Vague request — should route to Researcher/Discovery mode",
        "user_query": "I want to go on a romantic honeymoon with beaches",
        "expect_tools": [],
        "expect_clarifying_q": True,  # Supervisor should ask for missing info
    },
]


def run_case(case: dict) -> dict:
    """Run one test case through the graph and return a result summary."""
    tid = case["id"]
    config = {"configurable": {"thread_id": f"validate_{tid}_{int(time.time())}"}}
    print(f"\n{'='*60}")
    print(f"[{tid}] {case['description']}")
    print(f"  Query: {case['user_query']}")

    t0 = time.time()
    try:
        result = graph.invoke({"user_query": case["user_query"]}, config=config)
    except Exception as e:
        return {"id": tid, "passed": False, "error": str(e), "elapsed": time.time() - t0}

    elapsed = time.time() - t0

    # --- Analyse messages for tool calls ---
    messages = result.get("messages", [])
    tool_calls_made = set()
    tool_results_ok = {}

    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                tool_calls_made.add(name)
        if isinstance(msg, ToolMessage):
            try:
                parsed = json.loads(msg.content)
                if isinstance(parsed, list) and parsed:
                    tool_results_ok[getattr(msg, "name", "unknown")] = True
                elif isinstance(parsed, dict) and "warning" not in parsed:
                    tool_results_ok[getattr(msg, "name", "unknown")] = True
            except Exception:
                pass

    # --- Checks ---
    checks = {}

    # 1. Expected tools called
    expected_tools = case.get("expect_tools", [])
    for t in expected_tools:
        checks[f"tool_called:{t}"] = t in tool_calls_made

    # 2. Edge-case block
    if case.get("expect_edge_block"):
        supervisor_msg = result.get("supervisor_instruction", "")
        checks["edge_case_blocked"] = any(
            kw in str(supervisor_msg).lower()
            for kw in ["insufficient", "impossible", "cannot", "$20", "budget"]
        )

    # 3. Clarifying question for vague requests
    if case.get("expect_clarifying_q"):
        supervisor_msg = result.get("supervisor_instruction", "")
        checks["clarifying_question_asked"] = any(
            kw in str(supervisor_msg).lower()
            for kw in ["where", "destination", "budget", "how many", "duration", "days", "city"]
        )

    # 4. Trip plan has expected keys
    plan = result.get("trip_plan") or {}
    for key in case.get("expect_plan_keys", []):
        checks[f"plan_has:{key}"] = key in plan

    all_passed = all(checks.values())

    # Print summary
    for check_name, ok in checks.items():
        print(f"    {'[PASS]' if ok else '[FAIL]'} {check_name}")
    print(f"  Tools called: {sorted(tool_calls_made)}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Overall: {'PASSED' if all_passed else 'FAILED'}")

    return {
        "id": tid,
        "passed": all_passed,
        "checks": checks,
        "tools_called": sorted(tool_calls_made),
        "elapsed": round(elapsed, 1),
        "error": None,
    }


def main():
    print("TRIPZY FULL-FLOW VALIDATION")
    print(f"Running {len(TEST_CASES)} real use cases\n")

    results = []
    for case in TEST_CASES:
        r = run_case(case)
        results.append(r)
        time.sleep(1)   # brief pause between runs

    # Summary
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed}/{len(results)} PASSED")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        err = f" | ERROR: {r['error']}" if r.get("error") else ""
        print(f"  [{status}] {r['id']} ({r.get('elapsed', '?')}s){err}")

    # Save JSON report
    out_dir = Path(__file__).parent.parent / "evaluation-results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"full_flow_validation_{int(time.time())}.json"
    with open(out_file, "w") as f:
        json.dump({"passed": passed, "total": len(results), "results": results}, f, indent=2)
    print(f"\nReport saved: {out_file}")

    return passed == len(results)


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
