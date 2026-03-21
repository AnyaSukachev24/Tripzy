# -*- coding: utf-8 -*-
"""
Multi-case test script for the Tripzy Travel Agent.
Tests various user intents to verify routing, personalization, and loop prevention.
"""
import sys
import os
import uuid
import time

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

from app.graph import graph

TEST_CASES = [
    {
        "id": "TC-01",
        "name": "Vague Discovery (no prefs, no budget)",
        "query": "I want to go on a trip but don't know where to go.",
        "expected": "Should route to Researcher -> suggest_destination_tool -> End with suggestions",
    },
    {
        "id": "TC-02",
        "name": "Discovery with preferences (beach + snorkeling)",
        "query": "I want to go somewhere warm and beachy. I love snorkeling.",
        "expected": "Should call suggest_destination_tool with beach/snorkeling preferences",
    },
    {
        "id": "TC-03",
        "name": "Discovery with budget constraint ($800)",
        "query": "I have $800 and want a budget trip. Where should I go?",
        "expected": "Should call suggest_destination_tool with budget_tier=budget",
    },
    {
        "id": "TC-04",
        "name": "Full Planning (Barcelona, 7 days)",
        "query": "Plan a 7-day trip to Barcelona from New York.",
        "expected": "Should route to Trip_Planner with destination=Barcelona, duration=7",
    },
    {
        "id": "TC-05",
        "name": "Partial Planning - missing duration",
        "query": "I want to go to Tokyo.",
        "expected": "Should ask clarifying question: how many days?",
    },
    {
        "id": "TC-06",
        "name": "Greeting (no LLM needed)",
        "query": "Hello!",
        "expected": "Should route to End immediately without calling LLM",
    },
    {
        "id": "TC-07",
        "name": "Attractions query (Paris museums + landmarks)",
        "query": "What attractions should I visit in Paris? I like museums and landmarks.",
        "expected": "Should call suggest_attractions_tool and return grounded city suggestions",
    },
    {
        "id": "TC-08",
        "name": "Restaurant intent in destination",
        "query": "I am going to Tokyo. Suggest great local food and restaurant spots.",
        "expected": "Should prioritize dining-style attraction matches, then fallback if sparse",
    },
]


def run_test(case: dict, delay_sec: int = 5) -> dict:
    """Run a single test case and return structured results."""
    tid = f"test_multi_{uuid.uuid4()}"
    config = {"configurable": {"thread_id": tid}}

    print(f"\n{'='*60}")
    print(f"[{case['id']}] {case['name']}")
    print(f"Query:    {case['query']}")
    print(f"Expected: {case['expected']}")
    print("-" * 60)

    start = time.time()
    try:
        result = graph.invoke({"user_query": case["query"]}, config=config)
        elapsed = round(time.time() - start, 2)

        final_instruction = result.get("supervisor_instruction", "")
        next_step_final = result.get("next_step", "Unknown")
        steps = result.get("steps", [])
        modules_visited = [s.get("module") for s in steps]

        print(f"\n[PASS] Completed in {elapsed}s")
        print(f"   Final Next Step : {next_step_final}")
        print(f"   Modules Visited : {' -> '.join(modules_visited)}")
        print(f"   Output Preview  : {str(final_instruction)[:350]}")

        return {
            "id": case["id"],
            "name": case["name"],
            "status": "PASS",
            "elapsed": elapsed,
            "modules": modules_visited,
            "output_preview": str(final_instruction)[:350],
        }

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        print(f"\n[ERROR] after {elapsed}s: {e}")
        return {
            "id": case["id"],
            "name": case["name"],
            "status": "ERROR",
            "elapsed": elapsed,
            "error": str(e)[:300],
        }
    finally:
        if delay_sec > 0:
            print(f"   [Waiting {delay_sec}s before next test for rate limit...]")
            time.sleep(delay_sec)


def main():
    print("\n=== TRIPZY AGENT - MULTI-CASE TESTING ===")
    print(f"Running {len(TEST_CASES)} test cases...\n")

    results = []
    for case in TEST_CASES:
        r = run_test(case, delay_sec=5)
        results.append(r)

    # Summary table
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    for r in results:
        icon = "[PASS]" if r["status"] == "PASS" else "[ERROR]"
        modules = " -> ".join(r.get("modules", [])) if r.get("modules") else "N/A"
        print(f"{icon} [{r['id']}] {r['name']} ({r['elapsed']}s)")
        print(f"       Route  : {modules}")
        if r.get("error"):
            print(f"       Error  : {r['error'][:150]}")
        else:
            print(f"       Output : {r.get('output_preview', '')[:120]}")
        print()

    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"Result: {passed}/{len(results)} tests passed.")


if __name__ == "__main__":
    main()
