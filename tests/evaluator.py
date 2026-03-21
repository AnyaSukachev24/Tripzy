"""
tests/evaluator.py — Two-tier rule-based evaluator for Tripzy.

Tier 1: Pure rule-based checks (routing, state, keywords, format). Zero LLM tokens.
Tier 2: Optional Groq quality checks (free API, NOT Tripzy's LLMOD budget).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Groq client — lazy init, only used when test YAML has groq_check: true
# ---------------------------------------------------------------------------
_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set in .env — required for groq_check tests"
            )
        from openai import OpenAI

        _groq_client = OpenAI(api_key=api_key, base_url=base_url)
    return _groq_client


GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    expected: Any = None
    actual: Any = None
    detail: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        msg = f"  [{status}] {self.name}"
        if not self.passed:
            msg += f"\n         expected: {self.expected!r}"
            msg += f"\n         actual:   {self.actual!r}"
            if self.detail:
                msg += f"\n         hint:     {self.detail}"
        return msg


@dataclass
class EvalResult:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        lines = []
        for c in self.checks:
            lines.append(str(c))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------


def evaluate_turn(
    state_after: dict[str, Any],
    response_text: str,
    expected: dict[str, Any],
    test_id: str = "",
) -> EvalResult:
    """
    Evaluate a single turn against its expected spec.

    Args:
        state_after:   The AgentState dict returned after the graph invocation.
        response_text: The final response text shown to the user.
        expected:      The `expected` block from the YAML test case.
        test_id:       Test identifier for error messages.

    Returns:
        EvalResult with all individual check results.
    """
    checks: list[CheckResult] = []
    rt = response_text or ""

    # 1. Routing check
    # "End" → check final state next_step is "End"
    # Anything else → check whether that node was visited in state["steps"]
    # (module names: Trip_Planner→"Planner", Researcher→"Researcher", Attractions→"Attractions")
    if "next_step" in expected:
        exp = expected["next_step"]
        _NODE_TO_MODULE = {
            "Trip_Planner": "Planner",
            "Researcher": "Researcher",
            "Attractions": "Attractions",
            "Supervisor": "Supervisor",
        }
        if exp == "End":
            act = state_after.get("next_step", "")
            passed = act == "End"
            detail = "Graph did not terminate at End"
        else:
            module = _NODE_TO_MODULE.get(exp, exp)
            visited = [s.get("module", "") for s in state_after.get("steps", [])]
            passed = module in visited
            act = visited
            detail = f"Node '{module}' not found in visited steps: {visited}"
        checks.append(
            CheckResult(
                name="next_step",
                passed=passed,
                expected=exp,
                actual=act,
                detail=detail,
            )
        )

    # 2. Request type check
    if "request_type" in expected:
        exp = expected["request_type"]
        act = state_after.get("request_type", "")
        checks.append(
            CheckResult(
                name="request_type",
                passed=(act == exp),
                expected=exp,
                actual=act,
            )
        )

    # 3. State variable checks
    for key, exp_val in expected.get("state_after", {}).items():
        act_val = state_after.get(key)
        if exp_val is None:
            passed = act_val is None or act_val == "" or act_val == 0
        else:
            passed = exp_val.lower() in str(act_val or "").lower()
        checks.append(
            CheckResult(
                name=f"state.{key}",
                passed=passed,
                expected=exp_val,
                actual=act_val,
            )
        )

    # 4. Response must contain keywords
    for kw in expected.get("response_contains", []):
        passed = kw.lower() in rt.lower()
        checks.append(
            CheckResult(
                name=f"contains:{kw!r}",
                passed=passed,
                expected=f"response contains {kw!r}",
                actual=rt[:120] + "..." if len(rt) > 120 else rt,
            )
        )

    # 5. Response must NOT contain forbidden strings
    for kw in expected.get("response_excludes", []):
        passed = kw.lower() not in rt.lower()
        checks.append(
            CheckResult(
                name=f"excludes:{kw!r}",
                passed=passed,
                expected=f"response does NOT contain {kw!r}",
                actual=(rt[:120] + "...") if not passed and len(rt) > 120 else rt[:120],
                detail="Possible raw JSON leak or forbidden pattern",
            )
        )

    # 6. Response length guard
    if "max_response_chars" in expected:
        limit = expected["max_response_chars"]
        checks.append(
            CheckResult(
                name=f"max_response_chars<={limit}",
                passed=len(rt) <= limit,
                expected=f"<= {limit} chars",
                actual=f"{len(rt)} chars",
                detail="Response is too verbose",
            )
        )

    # 7. Always-on JSON leak check
    json_leaked = '{"' in rt or "```json" in rt
    checks.append(
        CheckResult(
            name="no_json_leak",
            passed=not json_leaked,
            expected="no raw JSON in response",
            actual="JSON found" if json_leaked else "clean",
            detail='Response contains raw JSON ({"  or ```json)',
        )
    )

    # 8. Question count guard
    if "question_count_max" in expected:
        limit = expected["question_count_max"]
        q_count = rt.count("?")
        checks.append(
            CheckResult(
                name=f"question_count<={limit}",
                passed=q_count <= limit,
                expected=f"<= {limit} questions",
                actual=f"{q_count} questions",
                detail="Too many clarifying questions",
            )
        )

    # 9. Optional Groq quality check (free, not LLMOD)
    if expected.get("groq_check") and expected.get("groq_prompt"):
        groq_passed = _run_groq_check(rt, expected["groq_prompt"])
        checks.append(
            CheckResult(
                name="groq_quality",
                passed=groq_passed,
                expected="YES from Groq quality check",
                actual="YES" if groq_passed else "NO",
                detail=expected["groq_prompt"][:100],
            )
        )

    passed = all(c.passed for c in checks)
    return EvalResult(passed=passed, checks=checks)


# ---------------------------------------------------------------------------
# Groq quality check helper
# ---------------------------------------------------------------------------


def _run_groq_check(response_text: str, prompt: str) -> bool:
    """Call free Groq model for a YES/NO quality check. Returns True = pass."""
    try:
        client = _get_groq_client()
        full_prompt = (
            f"{prompt}\n\n"
            f"Response to evaluate:\n{response_text}\n\n"
            "Answer only YES or NO."
        )
        result = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": full_prompt}],
            max_tokens=10,
            temperature=0,
        )
        content = result.choices[0].message.content or ""
        # Strip <think>...</think> blocks from qwen3 models
        import re as _re
        content = _re.sub(r"<think>.*?</think>", "", content, flags=_re.DOTALL).strip().upper()
        return "YES" in content or content.startswith("Y")
    except Exception as e:
        print(f"  [WARN] Groq check failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Utility: extract response text from graph state
# ---------------------------------------------------------------------------


def extract_response(state: dict[str, Any]) -> str:
    """
    Extract the final user-facing response text from a graph state.
    Tripzy stores the response in `supervisor_instruction` (set by supervisor/planner).
    Falls back to last message content.
    """
    # Primary: supervisor_instruction is what's shown to the user
    instruction = state.get("supervisor_instruction")
    if instruction:
        return str(instruction)

    # Fallback: last AI/assistant message
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "content") and hasattr(msg, "type"):
            if msg.type in ("ai", "assistant"):
                return str(msg.content)
        if isinstance(msg, dict):
            if msg.get("role") in ("ai", "assistant"):
                return str(msg.get("content", ""))

    # Last resort: any last message
    if messages:
        last = messages[-1]
        if hasattr(last, "content"):
            return str(last.content)
        if isinstance(last, dict):
            return str(last.get("content", ""))

    return ""
