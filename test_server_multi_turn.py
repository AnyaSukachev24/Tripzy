# -*- coding: utf-8 -*-
"""
Comprehensive multi-turn server integration tests for Tripzy.
Covers 3 core features + 8 edge case scenarios.

Features tested:
  1. Continuous conversation (multi-turn memory via thread_id)
  2. User profile (loading + continuous updates)
  3. Destination suggestions (Discovery flow)

Edge cases:
  4. Greeting / small talk (should NOT route to Planner)
  5. Flight-only request
  6. Hotel-only request
  7. Budget exceeded + renegotiation
  8. Incomplete info → clarification loop
  9. Mid-conversation destination change
 10. Attractions-only request
 11. Conversation context switch (new topic in same session)

Usage:
    # No server needed (direct graph):
    python test_server_multi_turn.py --offline --delay 4

    # Against running FastAPI server:
    python test_server_multi_turn.py --url http://localhost:8000

    # Run only a specific feature group:
    python test_server_multi_turn.py --offline --only feature1
    # Groups: feature1, feature2, feature3, edge
"""
import sys
import os
import uuid
import time
import json
import argparse

sys.stdout.reconfigure(encoding='utf-8')
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# ── Result tracking ────────────────────────────────────────────────────────────
_all_results = []

def _record(label: str, status: str, elapsed: float, error: str = "", modules=None, response: str = ""):
    _all_results.append({
        "label": label, "status": status, "elapsed": elapsed,
        "error": error, "modules": modules or [], "response": response
    })

# ── Offline helpers ─────────────────────────────────────────────────────────────

def _invoke_graph(graph, query: str, thread_id: str, label: str, delay_sec: int):
    """Run one turn in offline mode."""
    from dotenv import load_dotenv
    config = {"configurable": {"thread_id": thread_id}}
    print(f"\n>>> [{label}]  thread={thread_id[:8]}…")
    print(f"    Query : {query}")

    # Log to session-specific conversation file
    if hasattr(sys.modules[__name__], '_current_run_dir'):
        conv_file = os.path.join(sys.modules[__name__]._current_run_dir, "conversation.md")
        with open(conv_file, "a", encoding="utf-8") as f:
            f.write(f"### Test Scenario: {label}\n")
            f.write(f"**User**: {query}\n\n")

    t0 = time.time()
    try:
        state = graph.invoke({"user_query": query}, config=config)
        elapsed = round(time.time() - t0, 2)
        
        # Log full trace to a dedicated file for each scenario
        if hasattr(sys.modules[__name__], '_current_run_dir'):
            trace_file = os.path.join(sys.modules[__name__]._current_run_dir, f"trace_{label.replace(':', '').replace(' ', '_').lower()}.json")
            # We filter out non-serializable parts if any, or just dump the state dict
            # Standard json dump of LangChain messages might need a helper, but for now we'll do our best
            try:
                # Convert messages to dicts for serialization
                serializable_state = state.copy()
                if "messages" in serializable_state:
                    serializable_state["messages"] = [
                        {"role": m.type, "content": m.content} for m in serializable_state["messages"]
                    ]
                with open(trace_file, "w", encoding="utf-8") as f:
                    json.dump(serializable_state, f, indent=2, ensure_ascii=False)
            except:
                pass

        modules = [s.get("module") for s in state.get("steps", [])]
        instruction = state.get("supervisor_instruction", "")
        dest = state.get("destination")
        days = state.get("duration_days")
        request_type = state.get("request_type")

        print(f"    ✓ ({elapsed}s) type={request_type}, dest={dest}, days={days}")
        print(f"    Modules : {' → '.join(modules) or 'none'}")
        print(f"    Response: {str(instruction)[:250]}")
        _record(label, "ok", elapsed, modules=modules, response=str(instruction))
        
        if hasattr(sys.modules[__name__], '_current_run_dir'):
            conv_file = os.path.join(sys.modules[__name__]._current_run_dir, "conversation.md")
            with open(conv_file, "a", encoding="utf-8") as f:
                f.write(f"**Tripzy**: {instruction}\n\n---\n\n")
            
        return state
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"    ✗ ERROR ({elapsed}s): {e}")
        _record(label, "error", elapsed, error=str(e)[:120])
        return {}
    finally:
        if delay_sec > 0:
            print(f"    [pause {delay_sec}s…]")
            time.sleep(delay_sec)


def run_offline_tests(delay_sec: int = 4, only: str = "all"):
    from dotenv import load_dotenv
    load_dotenv()
    from app.graph import graph

    def invoke(query, label, thread=None):
        t = thread or str(uuid.uuid4())
        return _invoke_graph(graph, query, t, label, delay_sec), t

    print("\n" + "=" * 72)
    print("  TRIPZY MULTI-TURN TESTS  (OFFLINE / DIRECT GRAPH)")
    print("=" * 72)

    # Initialize timestamped run directory
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = os.path.join(project_root, "runs", timestamp)
    os.makedirs(run_dir, exist_ok=True)
    sys.modules[__name__]._current_run_dir = run_dir

    with open(os.path.join(run_dir, "conversation.md"), "w", encoding="utf-8") as f:
        f.write(f"# Tripzy Run: {timestamp}\n\n")
        f.write("This file contains the examples of message exchanges between the User and Tripzy.\n\n")

    # ── FEATURE 1: Restaurant Search ───────────────────────────────────────────
    if only in ("all", "feature1"):
        print("\n\n── FEATURE 1: Restaurants ─────────────────────────────────────────────")
        T1 = str(uuid.uuid4())

        s1, _ = invoke("Find me a top-rated vegan restaurant in Tokyo.", "F1-T1: Tokyo Vegan", thread=T1)
        if s1:
            steps = s1.get("steps", [])
            attr_ran = any(s.get("module") == "Attractions" for s in steps)
            print(f"  {'✅' if attr_ran else '❌'} Attractions node triggered")

    # ── FEATURE 2: Attractions & Follow-up ──────────────────────────────────────
    if only in ("all", "feature2"):
        print("\n\n── FEATURE 2: Cultural Exploration ───────────────────────────────────")
        T2 = str(uuid.uuid4())

        s2, _ = invoke("What are the best museums in Paris?", "F2-T1: Paris Museums", thread=T2)
        s3, _ = invoke("Which of those are good for kids?", "F2-T2: Kids friendly", thread=T2)

        if s3:
            steps = s3.get("steps", [])
            attr_ran = any(s.get("module") == "Attractions" for s in steps)
            print(f"  {'✅' if attr_ran else '❌'} Attractions node triggered for follow-up")

    # ── FEATURE 3: Tours & Activities ──────────────────────────────────────────
    if only in ("all", "feature3"):
        print("\n\n── FEATURE 3: Tours & Activities ─────────────────────────────────────")
        T3 = str(uuid.uuid4())

        s4, _ = invoke(
            "I want to go on a street food tour in Bangkok.",
            "F3-T1: Bangkok Food Tour",
            thread=T3
        )

        if s4:
            steps = s4.get("steps", [])
            attr_ran = any(s.get("module") == "Attractions" for s in steps)
            print(f"  {'✅' if attr_ran else '❌'} Attractions node triggered for tour")

    # ── EDGE 4: Greeting / Small Talk ──────────────────────────────────────────
    if only in ("all", "edge"):
        print("\n\n── EDGE 4: Greeting / Small Talk ───────────────────────────────────────")

        s8, _ = invoke("Hi there! How are you?", "E4: Greeting")
        if s8:
            steps = s8.get("steps", [])
            planner_ran = any(s.get("module") in ("Trip_Planner", "Planner") for s in steps)
            resp = s8.get("supervisor_instruction", "")
            greeting_resp = any(kw in resp.lower() for kw in ["hello", "hi", "help", "assist", "travel", "plan"])
            print(f"  {'✅' if not planner_ran else '❌'} Planner NOT triggered for greeting")
            print(f"  {'✅' if greeting_resp else '⚠'} Friendly response given")

        # ── EDGE 5: Flight Only ─────────────────────────────────────────────────
        print("\n\n── EDGE 5: Flight-Only Request ─────────────────────────────────────────")

        s9, _ = invoke(
            "Just find me flights from Tel Aviv to London on 2026-06-15.",
            "E5: Flight-only"
        )
        if s9:
            rtype = s9.get("request_type", "")
            steps = s9.get("steps", [])
            researcher_ran = any(s.get("module") == "Researcher" for s in steps)
            print(f"  {'✅' if 'flight' in rtype.lower() else '⚠'} Request type: {rtype} (expected FlightOnly)")
            print(f"  {'✅' if researcher_ran else '⚠'} Researcher fetched flights: {researcher_ran}")

        # ── EDGE 6: Hotel Only ──────────────────────────────────────────────────
        print("\n\n── EDGE 6: Hotel-Only Request ──────────────────────────────────────────")

        s10, _ = invoke(
            "Find me a hotel in Barcelona for July 5-10, max $150/night.",
            "E6: Hotel-only"
        )
        if s10:
            rtype = s10.get("request_type", "")
            steps = s10.get("steps", [])
            researcher_ran = any(s.get("module") == "Researcher" for s in steps)
            print(f"  {'✅' if 'hotel' in rtype.lower() else '⚠'} Request type: {rtype} (expected HotelOnly)")
            print(f"  {'✅' if researcher_ran else '⚠'} Researcher fetched hotels: {researcher_ran}")

        # ── EDGE 7: Budget Exceeded + Renegotiation ─────────────────────────────
        print("\n\n── EDGE 7: Budget Exceeded + Renegotiation ─────────────────────────────")
        T7 = str(uuid.uuid4())

        s11, _ = invoke(
            "Plan 7 days in Maldives with budget $100.",
            "E7-T1: Unrealistic budget",
            thread=T7
        )
        if s11:
            warning = s11.get("budget_warning", "")
            resp = s11.get("supervisor_instruction", "")
            budget_mentioned = warning or any(kw in resp.lower() for kw in ["budget", "cost", "expensive", "afford", "$100"])
            print(f"  {'✅' if budget_mentioned else '⚠'} Budget issue mentioned in response")

        s12, _ = invoke(
            "Ok let's increase budget to $3000.",
            "E7-T2: Increase budget",
            thread=T7
        )
        if s12:
            budget = s12.get("budget_limit", 0)
            print(f"  {'✅' if budget >= 2000 else '⚠'} Budget updated to: {budget} (expected ~3000)")

        # ── EDGE 8: Incomplete Info → Clarification ─────────────────────────────
        print("\n\n── EDGE 8: Incomplete Info → Clarification ─────────────────────────────")
        T8 = str(uuid.uuid4())

        s13, _ = invoke(
            "Plan a trip for me.",
            "E8-T1: Too vague — no destination/budget/duration",
            thread=T8
        )
        if s13:
            resp = s13.get("supervisor_instruction", "")
            planner_ran = any(s.get("module") in ("Trip_Planner", "Planner") for s in s13.get("steps", []))
            asks_for_more = any(kw in resp.lower() for kw in
                                ["where", "destination", "budget", "how long", "duration", "?", "tell me"])
            print(f"  {'✅' if not planner_ran else '⚠'} Planner not triggered for vague request: {not planner_ran}")
            print(f"  {'✅' if asks_for_more else '⚠'} Agent asks clarifying question")

        # ── EDGE 9: Mid-conversation Destination Change ──────────────────────────
        print("\n\n── EDGE 9: Mid-Conversation Destination Change ─────────────────────────")
        T9 = str(uuid.uuid4())

        s14, _ = invoke(
            "Plan 5 days in Rome with $2000 budget.",
            "E9-T1: Start with Rome",
            thread=T9
        )
        s15, _ = invoke(
            "Actually, let's change to Paris instead.",
            "E9-T2: Switch to Paris",
            thread=T9
        )
        if s15:
            dest = s15.get("destination", "")
            paris_ok = "paris" in str(dest).lower()
            print(f"  {'✅' if paris_ok else '❌'} Destination switched to: {dest} (expected Paris)")

        # ── EDGE 10: Attractions Only ────────────────────────────────────────────
        print("\n\n── EDGE 10: Attractions-Only Request ───────────────────────────────────")

        s16, _ = invoke(
            "What are the best things to do in Tokyo for a family?",
            "E10: Attractions-only"
        )
        if s16:
            rtype = s16.get("request_type", "")
            steps = s16.get("steps", [])
            attractions_ran = any(s.get("module") == "Attractions" for s in steps)
            resp = s16.get("supervisor_instruction", "")
            has_attractions = any(kw in resp.lower() for kw in
                                   ["museum", "park", "temple", "coming soon", "attraction", "visit", "kids", "family"])
            print(f"  Request type: {rtype}")
            print(f"  {'✅' if attractions_ran else '⚠'} Attractions node ran")
            print(f"  {'✅' if has_attractions else '⚠'} Attraction content in response")

        # ── EDGE 11: Context Switch ──────────────────────────────────────────────
        print("\n\n── EDGE 11: Context Switch (Different Topic Same Session) ──────────────")
        T11 = str(uuid.uuid4())

        s17, _ = invoke(
            "Plan 4 days in Dubai with $3000 budget.",
            "E11-T1: Dubai planning",
            thread=T11
        )
        s18, _ = invoke(
            "Actually forget Dubai. What are some romantic destinations in Europe under $2500?",
            "E11-T2: Context switch to Discovery",
            thread=T11
        )
        if s18:
            steps = s18.get("steps", [])
            researcher_ran = any(s.get("module") == "Researcher" for s in steps)
            resp = s18.get("supervisor_instruction", "")
            europe_mentioned = any(c in resp for c in
                                   ["Paris", "Rome", "Prague", "Venice", "Santorini", "Barcelona",
                                    "Amsterdam", "Lisbon", "suggest", "romantic"])
            print(f"  {'✅' if researcher_ran else '⚠'} Researcher ran for Discovery")
            print(f"  {'✅' if europe_mentioned else '⚠'} European destinations suggested")

    # ── Summary ─────────────────────────────────────────────────────────────────
    _print_summary()


def _print_summary():
    print("\n\n" + "=" * 72)
    print("  FINAL SUMMARY")
    print("=" * 72)
    passed = sum(1 for r in _all_results if r["status"] == "ok")
    failed = [r for r in _all_results if r["status"] != "ok"]
    for r in _all_results:
        icon = "✅" if r["status"] == "ok" else "❌"
        mods = " → ".join(r.get("modules", [])) or "n/a"
        print(f"  {icon} [{r['label']}] ({r.get('elapsed', '?')}s)")
        if r.get("error"):
            print(f"       Error: {r['error']}")
    print(f"\n  Passed: {passed}/{len(_all_results)}")
    if failed:
        print(f"  Failed: {len(failed)}")


# ── Online server mode ─────────────────────────────────────────────────────────

def run_server_tests(base_url: str, delay_sec: int, only: str):
    try:
        import httpx
    except ImportError:
        print("httpx not installed. Run: pip install httpx")
        return

    print(f"\n{'='*72}")
    print(f"  TRIPZY MULTI-TURN SERVER TESTS  ({base_url})")
    print(f"{'='*72}")

    def chat(thread_id: str, query: str, label: str):
        print(f"\n>>> [{label}]  thread={thread_id[:8]}…")
        print(f"    Query : {query}")
        t0 = time.time()
        try:
            resp = httpx.post(
                f"{base_url}/api/execute",
                json={"prompt": query, "thread_id": thread_id},
                timeout=120.0,
            )
            elapsed = round(time.time() - t0, 2)
            data = resp.json()
            status = data.get("status", "unknown")
            response_text = data.get("response", "")
            steps = data.get("steps", [])
            modules = [s.get("module") for s in steps]
            print(f"    Status  : {status} ({elapsed}s)")
            print(f"    Modules : {' → '.join(modules) or 'none'}")
            print(f"    Response: {response_text[:200]}")
            _record(label, status, elapsed, modules=modules, response=response_text)
            return data
        except httpx.ConnectError:
            elapsed = round(time.time() - t0, 2)
            print(f"    ✗ CONNECTION ERROR — is server running at {base_url}?")
            _record(label, "connection_error", elapsed)
            return {}
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"    ✗ ERROR: {e}")
            _record(label, "error", elapsed, error=str(e)[:120])
            return {}
        finally:
            if delay_sec > 0:
                time.sleep(delay_sec)

    if only in ("all", "feature1"):
        print("\n\n── FEATURE 1: Continuous Conversation ─────────────────────────────────")
        T1 = str(uuid.uuid4())
        chat(T1, "I want to plan a trip.", "F1-T1: Vague")
        chat(T1, "I'm thinking Rome.", "F1-T2: Destination")
        d3 = chat(T1, "For 4 days.", "F1-T3: Duration")
        if d3:
            resp = d3.get("response", "")
            ctx_ok = "rome" in resp.lower() or "4 day" in resp.lower()
            print(f"  {'✅' if ctx_ok else '⚠'} Context continuity check")

    if only in ("all", "feature2"):
        print("\n\n── FEATURE 2: User Profile ─────────────────────────────────────────────")
        T2 = str(uuid.uuid4())
        d4 = chat(T2, "I'm vegan and love adventure. Plan 5 days in Costa Rica.", "F2-T1: Profile")
        if d4:
            resp = d4.get("response", "")
            print(f"  {'✅' if d4.get('status') == 'ok' else '❌'} Profile request processed")
            diet_ok = any(kw in resp.lower() for kw in ["vegan", "diet", "food", "vegetarian", "adventure", "outdoor"])
            print(f"  {'✅' if diet_ok else '⚠'} Profile reflected in response")

    if only in ("all", "feature3"):
        print("\n\n── FEATURE 3: Destination Suggestions ─────────────────────────────────")
        T3 = str(uuid.uuid4())
        d5 = chat(T3, "Where should I go in Europe for a romantic trip? Budget $2000.", "F3-T1: Discovery")
        if d5:
            modules = d5.get("modules", [])
            resp = d5.get("response", "")
            print(f"  {'✅' if 'Researcher' in modules else '⚠'} Researcher ran")
            cities = ["Paris", "Rome", "Prague", "Santorini", "destination", "suggest"]
            print(f"  {'✅' if any(c in resp for c in cities) else '⚠'} City suggestions in response")
        d6 = chat(T3, "Let's go to Paris! 5 days.", "F3-T2: Follow-up Paris")
        if d6:
            resp = d6.get("response", "")
            print(f"  {'✅' if 'paris' in resp.lower() else '⚠'} Paris picked up")

    if only in ("all", "edge"):
        print("\n\n── EDGE: Greeting ──────────────────────────────────────────────────────")
        d7 = chat(str(uuid.uuid4()), "Hi! How are you?", "E4: Greeting")
        if d7:
            modules = d7.get("modules", [])
            print(f"  {'✅' if 'Planner' not in modules else '❌'} Planner not triggered for greeting")

        print("\n\n── EDGE: Flight Only ───────────────────────────────────────────────────")
        d8 = chat(str(uuid.uuid4()), "Find flights from Tel Aviv to Paris on 2026-07-10.", "E5: Flight-only")
        if d8:
            modules = d8.get("modules", [])
            print(f"  {'✅' if 'Researcher' in modules else '⚠'} Researcher fetched flights")

    _print_summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tripzy multi-turn feature tests")
    parser.add_argument("--offline", action="store_true",
                        help="Run directly against graph (no HTTP server needed)")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--delay", type=int, default=5,
                        help="Seconds between API calls (default: 5)")
    parser.add_argument("--only", default="all",
                        choices=["all", "feature1", "feature2", "feature3", "edge"],
                        help="Run only a specific test group")
    args = parser.parse_args()

    if args.offline:
        run_offline_tests(delay_sec=args.delay, only=args.only)
    else:
        run_server_tests(base_url=args.url, delay_sec=args.delay, only=args.only)
