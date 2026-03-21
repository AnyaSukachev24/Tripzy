"""
tests/report.py — Markdown report generator for Tripzy evaluation runs.

Saves: tests/results/run_<timestamp>.md
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

PHASE_LABELS = {
    "phase1": "Phase 1 — Routing",
    "phase2": "Phase 2 — Features",
    "phase3": "Phase 3 — Edge Cases",
    "phase4": "Phase 4 — Conversations",
}


def _pass_rate(results: list[dict]) -> float:
    if not results:
        return 1.0
    return sum(1 for r in results if r["passed"]) / len(results)


def _status_emoji(rate: float, total: int) -> str:
    if total == 0:
        return "—"
    if rate == 1.0:
        return "✅"
    if rate >= 0.8:
        return "⚠️"
    return "❌"


def save_report(all_results: dict[str, list[dict]], path: Path | None = None) -> Path:
    """
    Generate and save a markdown report.

    Args:
        all_results: Dict from runner.run() — keys are phase names or feature names.
        path: Optional output path. Defaults to tests/results/run_<timestamp>.md

    Returns:
        Path to saved report.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if path is None:
        path = RESULTS_DIR / f"run_{timestamp}.md"

    lines: list[str] = []
    lines.append(f"# Tripzy Eval Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # --- Summary table ---
    lines.append("## Summary\n")
    total_tests = 0
    total_passed = 0
    all_phases_known = all(k in PHASE_LABELS for k in all_results)

    for key, results in all_results.items():
        label = PHASE_LABELS.get(key, f"Feature: {key}")
        n = len(results)
        p = sum(1 for r in results if r["passed"])
        rate = _pass_rate(results)
        emoji = _status_emoji(rate, n)
        lines.append(f"- **{label}**: {p}/{n} {emoji}")
        total_tests += n
        total_passed += p

    # Skipped phases
    if all_phases_known:
        for phase_key, phase_label in PHASE_LABELS.items():
            if phase_key not in all_results:
                lines.append(f"- **{phase_label}**: skipped")

    lines.append("")
    lines.append(f"**Total: {total_passed}/{total_tests} tests passed**\n")

    # --- Failures ---
    all_failures = []
    for key, results in all_results.items():
        for r in results:
            if not r["passed"]:
                all_failures.append((key, r))

    if all_failures:
        lines.append("## Failures\n")
        for key, r in all_failures:
            label = PHASE_LABELS.get(key, key)
            lines.append(f"### [{label}] {r['test_id']}: {r['name']}")
            if r.get("error"):
                lines.append(f"  - **Error**: `{r['error']}`")
            for i, tr in enumerate(r.get("turn_results", [])):
                if not tr.passed:
                    lines.append(f"  - Turn {i+1} failed checks:")
                    for c in tr.failed_checks:
                        exp = repr(c.expected) if c.expected is not None else ""
                        act = repr(c.actual) if c.actual is not None else ""
                        lines.append(f"    - `{c.name}`: expected {exp}, got {act}")
                        if c.detail:
                            lines.append(f"      > {c.detail}")
            lines.append("")
    else:
        lines.append("## Failures\n\n_None — all tests passed!_\n")

    # --- Full results table ---
    lines.append("## All Results\n")
    lines.append("| ID | Name | Status | Time |")
    lines.append("|-----|------|--------|------|")
    for key, results in all_results.items():
        for r in results:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            lines.append(f"| {r['test_id']} | {r['name']} | {status} | {r['elapsed']}s |")
    lines.append("")

    # --- Token usage estimate ---
    lines.append("## Token Usage Estimate\n")
    total_turns = sum(
        sum(len(r.get("turn_results", [])) or 1 for r in results)
        for results in all_results.values()
    )
    lines.append(f"- Total graph invocations (LLMOD calls): ~{total_turns}")
    lines.append(f"- Estimated tokens: ~{total_turns * 700:,} (rough average 700 tokens/turn)")
    lines.append(f"- Groq eval calls: used for `groq_check: true` tests only (free, not LLMOD)\n")

    report_text = "\n".join(lines)
    path.write_text(report_text, encoding="utf-8")
    return path
