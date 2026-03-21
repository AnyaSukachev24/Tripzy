"""
tests/runner.py — Phased test runner with early-stop for Tripzy.

Phases (cheapest → most expensive):
  Phase 1: routing_tests.yaml       — ~8 LLM calls, STOP on any failure
  Phase 2: feature_*.yaml           — ~26 LLM calls, skip failing group
  Phase 3: edge_cases.yaml          — ~16 LLM calls, run if Phase 2 >= 80%
  Phase 4: conversations.yaml       — ~12 LLM calls, run if Phase 3 >= 80%

Usage:
  python tests/runner.py                    # Run all phases
  python tests/runner.py --fast             # Phase 1 only (routing smoke test)
  python tests/runner.py --phase 2          # Run phases 1 and 2
  python tests/runner.py --feature flights  # Run only flights feature group
  python tests/runner.py --delay 2          # Seconds to sleep between turns
  python tests/runner.py --report           # Also save markdown report
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

# Ensure project root is on the path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tests.evaluator import evaluate_turn, extract_response

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CASES_DIR = Path(__file__).parent / "cases"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

PHASE_FILES = {
    1: ["routing_tests.yaml"],
    2: [
        "feature_discovery.yaml",
        "feature_attractions.yaml",
        "feature_flights.yaml",
        "feature_hotels.yaml",
        "feature_general_questions.yaml",
    ],
    3: ["edge_cases.yaml"],
    4: ["conversations.yaml"],
}

FEATURE_MAP = {
    "routing": "routing_tests.yaml",
    "discovery": "feature_discovery.yaml",
    "attractions": "feature_attractions.yaml",
    "flights": "feature_flights.yaml",
    "hotels": "feature_hotels.yaml",
    "general": "feature_general_questions.yaml",
    "edge": "edge_cases.yaml",
    "conversations": "conversations.yaml",
    "e2e": "e2e_full_flow.yaml",
}

PHASE_LABELS = {1: "Routing", 2: "Features", 3: "Edge Cases", 4: "Conversations"}


# ---------------------------------------------------------------------------
# Graph invocation
# ---------------------------------------------------------------------------


def invoke_turn(graph, query: str, thread_id: str, delay_sec: float = 0) -> dict[str, Any]:
    """Invoke one turn of the graph and return the full state dict."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = graph.invoke({"user_query": query}, config=config)
    except Exception as e:
        print(f"  [ERROR] Graph invocation failed: {e}")
        return {}
    finally:
        if delay_sec > 0:
            time.sleep(delay_sec)
    return state or {}


# ---------------------------------------------------------------------------
# Single test case runner
# ---------------------------------------------------------------------------


def run_test(graph, test: dict, delay_sec: float = 0) -> dict:
    """Run a single test case (potentially multi-turn). Returns a result dict."""
    test_id = test.get("id", "?")
    name = test.get("name", "unnamed")
    tags = test.get("tags", [])
    turns = test.get("turns", [])

    thread_id = str(uuid.uuid4())
    turn_results = []
    overall_passed = True
    error_msg = ""
    t0 = time.time()

    try:
        for i, turn in enumerate(turns):
            user_msg = turn.get("user", "")
            expected = turn.get("expected", {})

            state = invoke_turn(graph, user_msg, thread_id, delay_sec)
            response = extract_response(state)

            result = evaluate_turn(
                state_after=state,
                response_text=response,
                expected=expected,
                test_id=f"{test_id}[turn{i+1}]",
            )
            turn_results.append(result)

            if not result.passed:
                overall_passed = False

    except Exception as e:
        overall_passed = False
        error_msg = str(e)

    elapsed = round(time.time() - t0, 2)
    return {
        "test_id": test_id,
        "name": name,
        "tags": tags,
        "passed": overall_passed,
        "elapsed": elapsed,
        "turn_results": turn_results,
        "error": error_msg,
    }


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------


def _print_test_result(r: dict):
    status = "PASS" if r["passed"] else "FAIL"
    print(f"  [{status}] {r['test_id']}: {r['name']} ({r['elapsed']}s)")
    if r.get("error"):
        print(f"    [ERROR] {r['error']}")
    if not r["passed"]:
        for i, tr in enumerate(r["turn_results"]):
            if not tr.passed:
                print(f"    Turn {i+1} failures:")
                for c in tr.failed_checks:
                    print(f"      {c}")


def _print_phase_summary(label: str, results: list[dict]):
    total = len(results)
    if total == 0:
        print(f"  {label}: 0/0 (no tests)")
        return
    passed = sum(1 for r in results if r["passed"])
    if passed == total:
        emoji = "✅"
    elif passed / total >= 0.8:
        emoji = "⚠️"
    else:
        emoji = "❌"
    print(f"\n  {label}: {passed}/{total} {emoji}")


def pass_rate(results: list[dict]) -> float:
    if not results:
        return 1.0
    return sum(1 for r in results if r["passed"]) / len(results)


# ---------------------------------------------------------------------------
# File runner
# ---------------------------------------------------------------------------


def run_file(graph, yaml_path: Path, delay_sec: float = 0) -> list[dict]:
    """Load a YAML file and run all tests in it. Returns results list."""
    if not yaml_path.exists():
        print(f"  [SKIP] Not found: {yaml_path.name}")
        return []

    with open(yaml_path, encoding="utf-8") as f:
        tests = yaml.safe_load(f) or []

    results = []
    for test in tests:
        r = run_test(graph, test, delay_sec)
        _print_test_result(r)
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run(
    max_phase: int = 4,
    feature: str | None = None,
    delay_sec: float = 0,
) -> dict[str, list[dict]]:
    """
    Run the evaluation suite.

    Returns:
        Dict mapping phase/feature keys → list of test result dicts.
    """
    from dotenv import load_dotenv
    load_dotenv()
    from app.graph import graph

    all_results: dict[str, list[dict]] = {}
    run_start = time.time()

    # --- Feature-specific run (bypasses phases) ---
    if feature:
        fname = FEATURE_MAP.get(feature.lower())
        if not fname:
            print(f"Unknown feature: {feature!r}. Options: {list(FEATURE_MAP)}")
            return {}
        print(f"\n{'='*60}")
        print(f"  TRIPZY EVAL — feature: {feature}")
        print(f"{'='*60}")
        results = run_file(graph, CASES_DIR / fname, delay_sec)
        all_results[feature] = results
        _print_phase_summary(f"Feature: {feature}", results)
        _print_total(run_start)
        return all_results

    # --- Phased run ---
    for phase_num in range(1, max_phase + 1):
        files = PHASE_FILES.get(phase_num, [])
        label = PHASE_LABELS[phase_num]

        print(f"\n{'='*60}")
        print(f"  PHASE {phase_num}: {label}")
        print(f"{'='*60}")

        phase_results: list[dict] = []

        for fname in files:
            group = fname.replace(".yaml", "").replace("feature_", "")
            print(f"\n  [{group}]")
            file_results = run_file(graph, CASES_DIR / fname, delay_sec)
            phase_results.extend(file_results)

            # Phase 2: on group failure, print warning and continue next group
            if phase_num == 2:
                fr = pass_rate(file_results)
                if fr < 1.0:
                    failed = [r["test_id"] for r in file_results if not r["passed"]]
                    print(f"    ⚠️  Group {group}: {fr:.0%} pass rate. Failures: {failed}")

        all_results[f"phase{phase_num}"] = phase_results
        rate = pass_rate(phase_results)
        _print_phase_summary(f"Phase {phase_num} ({label})", phase_results)

        # Early-stop rules
        if phase_num == 1 and rate < 1.0:
            print(
                f"\n[STOP] Phase 1 routing failures! "
                f"Fix routing before running feature tests."
            )
            break

        if phase_num >= 2 and phase_num < max_phase and rate < 0.80:
            next_label = PHASE_LABELS.get(phase_num + 1, "")
            print(
                f"\n[SKIP] Phase {phase_num + 1} ({next_label}) skipped "
                f"— Phase {phase_num} pass rate {rate:.0%} < 80%"
            )
            break

    _print_total(run_start)
    return all_results


def _print_total(run_start: float):
    total = round(time.time() - run_start, 1)
    print(f"\n  Total run time: {total}s")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Tripzy evaluation runner")
    parser.add_argument(
        "--fast", action="store_true",
        help="Phase 1 only — routing smoke test (~8 LLM calls)"
    )
    parser.add_argument(
        "--phase", type=int, default=4, choices=[1, 2, 3, 4],
        help="Run up to this phase number (default: 4)"
    )
    parser.add_argument(
        "--feature", type=str, default=None,
        metavar="NAME",
        help=f"Run a single feature group: {list(FEATURE_MAP.keys())}"
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Seconds to sleep between LLM turns (rate-limit guard)"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Save a markdown report to tests/results/"
    )
    args = parser.parse_args()

    max_phase = 1 if args.fast else args.phase

    results = run(
        max_phase=max_phase,
        feature=args.feature,
        delay_sec=args.delay,
    )

    if args.report and results:
        from tests.report import save_report
        path = save_report(results)
        print(f"\n  Report saved: {path}")


if __name__ == "__main__":
    main()
