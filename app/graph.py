import sys

# Force UTF-8 output encoding globally so that print() never crashes with
# Unicode characters (arrows, emoji, etc.) regardless of OS locale.
# - On Mac/Linux: stdout is already UTF-8 → this is a safe no-op.
# - On Windows (CP1252/CP1255 terminals): fixes the charmap UnicodeEncodeError.
# - When running under uvicorn/gunicorn: already UTF-8, no effect.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from typing import Any, Dict, Literal, List
from datetime import datetime
from langgraph.checkpoint.memory import MemorySaver
from app.state import AgentState, Amenity, TripPlan, UserProfile
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
import os
import json
import logging
import re
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    retry_if_exception_type,
    before_sleep_log,
    retry_if_exception,
)
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prompts
from app.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT
from app.prompts.planner_prompt import get_planner_prompt
from app.prompts.critique_prompt import get_critique_prompt
from app.prompts.attractions_prompt import ATTRACTIONS_SYSTEM_PROMPT

# Tools
from app.tools import (
    web_search_tool,
    search_flights_tool,
    search_hotels_tool,
    suggest_destination_tool,
    suggest_attractions_tool,
    create_plan_tool,
    search_activities_tool,
    flight_price_analysis_tool,
    flight_status_tool,
    airport_search_tool,
    airline_lookup_tool,
    travel_recommendations_tool,
    cheapest_flights_tool,
    hotel_ratings_tool,
    search_flights_with_kiwi_tool,
    # New Amadeus tools (Phase 26)
    resolve_airport_code_tool,
    get_airline_info_tool,
    search_tours_activities_tool,
    search_tours_activities_tool,
    search_points_of_interest_tool,
)


# --- Retry Configuration ---
def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception is a rate-limit / quota error."""
    msg = str(exc).lower()
    return (
        "429" in msg
        or "rate limit" in msg
        or "resource_exhausted" in msg
        or "too many requests" in msg
        or "quota" in msg
        or "throttl" in msg
    )


def _is_retriable_error(exc: Exception) -> bool:
    """Return True for errors worth retrying (rate limits + transient server errors)."""
    if _is_rate_limit_error(exc):
        return True
    msg = str(exc).lower()
    return (
        "500" in msg
        or "502" in msg
        or "503" in msg
        or "timeout" in msg
        or "connection" in msg
    )


def _classify_error(exc: Exception, service_name: str = "") -> dict:
    """
    Classify an exception into a user-friendly category.

    Returns a dict with:
      - ``code``     – machine-readable error code for the JSON response
      - ``user_msg`` – friendly Markdown message to show the user
    """
    msg = str(exc).lower()

    if _is_rate_limit_error(exc):
        return {
            "code": "rate_limit",
            "user_msg": (
                "⏳ Our AI assistant is a bit busy right now due to high demand. "
                "Please wait a moment and try again."
            ),
        }

    if (
        "401" in msg
        or "403" in msg
        or "unauthorized" in msg
        or "invalid api key" in msg
        or "authentication" in msg
        or "access denied" in msg
    ):
        return {
            "code": "auth_error",
            "user_msg": (
                "🔒 There's a configuration issue on our end and we couldn't "
                "authenticate with one of our services. Our team has been notified."
            ),
        }

    if (
        "timeout" in msg
        or "timed out" in msg
        or "connection" in msg
        or "refused" in msg
        or "unreachable" in msg
        or "socket" in msg
        or "errno" in msg
        or "network" in msg
    ):
        return {
            "code": "network_error",
            "user_msg": (
                "🌐 We had trouble connecting to one of our services. "
                "Please check your connection and try again in a moment."
            ),
        }

    if (
        "500" in msg
        or "502" in msg
        or "503" in msg
        or "bad gateway" in msg
        or "service unavailable" in msg
        or "server error" in msg
        or "internal server" in msg
    ):
        return {
            "code": "api_error",
            "user_msg": (
                "⚠️ One of our services returned an unexpected error. "
                "Please try again in a moment."
            ),
        }

    if service_name:
        # Make the service name human-readable: "search_flights_tool" → "flight search"
        label = (
            service_name
            .replace("search_", "")
            .replace("_tool", "")
            .replace("_", " ")
            .strip()
        )
        return {
            "code": "tool_error",
            "user_msg": (
                f"🔍 The {label} service ran into an issue and couldn't complete "
                "the search. You may want to try different dates or parameters."
            ),
        }

    return {
        "code": "unknown",
        "user_msg": "😕 Something unexpected happened on our end. Please try again.",
    }


def _wait_for_rate_limit(retry_state) -> float:
    """
    Custom wait strategy:
    - If the exception carries a Retry-After header, honour it (+ 2 s buffer).
    - Otherwise, use exponential backoff capped at 60 s.
    """
    exc = retry_state.outcome.exception()
    if exc:
        # Try to read Retry-After from the response headers (Azure / OpenAI pattern)
        try:
            response = getattr(exc, "response", None)
            if response is not None:
                retry_after = response.headers.get("Retry-After", None)
                if retry_after:
                    wait = float(retry_after) + 2  # small buffer
                    logger.warning(
                        f"[Rate Limit] Retry-After header says {retry_after}s — waiting {wait}s"
                    )
                    return wait
        except Exception:
            pass
        if _is_rate_limit_error(exc):
            # Aggressive backoff for rate-limit errors: 20s → 40s → 60s
            attempt = retry_state.attempt_number
            wait = min(20 * attempt, 60)
            logger.warning(
                f"[Rate Limit] Attempt {attempt} — waiting {wait}s before retry"
            )
            return wait
    # Fallback: standard exponential backoff for other transient errors
    attempt = retry_state.attempt_number
    return min(2**attempt, 15)


def retry_decorator(func):
    """
    Decorator for retrying LLM calls with smart backoff.

    Retry strategy:
    - Max 4 attempts
    - Rate-limit errors (429): wait 20s/40s/60s (or Retry-After header)
    - Other transient errors: exponential backoff up to 15s
    - Non-retriable errors (auth, bad request): fail immediately
    """
    return retry(
        stop=stop_after_attempt(4),
        wait=_wait_for_rate_limit,
        retry=retry_if_exception(_is_retriable_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )(func)


# --- Safe LLM Invoke Helper ---
@retry_decorator
def safe_llm_invoke(chain, input_data: Dict[str, Any]):
    """
    Safely invoke an LLM chain with automatic retry on failures.

    Args:
        chain: The LangChain chain to invoke
        input_data: Input dictionary for the chain

    Returns:
        The chain's output

    Raises:
        Exception: After 4 failed attempts
    """
    logger.info(f"Invoking LLM with input keys: {list(input_data.keys())}")
    try:
        result = chain.invoke(input_data)
        logger.info("LLM invocation successful")
        return result
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        raise


# LLM Selection: LLMOD only
api_key = os.getenv("LLMOD_API_KEY")

if not api_key:
    raise RuntimeError("LLMOD_API_KEY is not set. Cannot initialize LLM.")

logger.info(
    "[LLM] Using LLMOD model: %s",
    os.environ.get("LLM_MODEL", "RPRTHPB-gpt-5-mini"),
)

llm = ChatOpenAI(
    model=os.environ.get("LLM_MODEL", "RPRTHPB-gpt-5-mini"),
    api_key=api_key,
    base_url=os.environ.get("LLMOD_BASE_URL", "https://api.llmod.ai/v1"),
)

# --- Output Models ---
class SupervisorOutput(BaseModel):
    next_step: Literal["Trip_Planner", "Attractions", "End"] = Field(
        description="Next worker to call."
    )
    reasoning: str = Field(description="Reason for selecting this node.")
    instruction: str = Field(description="Specific instructions for the next worker.")
    duration_days: int = Field(
        description="Trip duration in days. If not mentioned in User Input, USE VALUE FROM CURRENT STATE. Set to 0 only if unknown.",
        default=0,
    )
    destination: str = Field(
        description="Destination (e.g., 'Bali'). If not mentioned in User Input, USE VALUE FROM CURRENT STATE. Empty if unknown.",
        default="",
    )
    budget_limit: float = Field(
        description="Budget limit. If not mentioned in User Input, USE VALUE FROM CURRENT STATE. 0 if unknown.",
        default=0.0,
    )
    budget_currency: str = Field(
        description="Currency code. If not mentioned, USE VALUE FROM CURRENT STATE. Default USD.",
        default="USD",
    )
    trip_type: str = Field(
        description="Type of trip. If not mentioned, USE VALUE FROM CURRENT STATE. Empty if unknown.",
        default="",
    )
    origin_city: str = Field(
        description="User's starting location/city (e.g., 'London', 'NYC'). Empty if not specified.",
        default="",
    )
    preferences: list[str] = Field(
        description="List of extracted preferences/keywords (e.g., 'beach', 'history', 'warm').",
        default=[],
    )
    traveling_personas_number: int = Field(
        description="Number of people traveling. Default 1.",
        default=1,
    )
    amenities: List[Amenity] = Field(
        description="List of amenities extracted from the user request.",
        default=[],
    )
    request_type: Literal[
        "AttractionsOnly",
        "FlightOnly",
        "HotelOnly",
        "GeneralQuestion",
    ] = Field(
        description="Intent: 'AttractionsOnly' for sights/activities/restaurants, 'FlightOnly'/'HotelOnly' for transport/accommodation searches, 'GeneralQuestion' for travel facts.",
        default="GeneralQuestion",
    )
    pending_stages: List[str] = Field(
        description="For combined requests: list of remaining request types to execute after the current stage (e.g. ['HotelOnly', 'AttractionsOnly']). Empty list by default.",
        default=[],
    )


class AttractionsOutput(BaseModel):
    response: str = Field(description="The formatted response with numbered list of attractions/restaurants to show the user.")


class PlannerOutput(BaseModel):
    thought: str = Field(description="Internal reasoning.")
    call_researcher: str = Field(
        description="Query for researcher if needed.", default=""
    )
    call_flights: Dict[str, str] = Field(
        description="Flight search params: {origin, dest, date}.", default={}
    )
    call_hotels: Dict[str, str] = Field(
        description="Hotel search params: {city, in, out, budget}.", default={}
    )
    final_response: str = Field(
        description="Response to user if plan is ready.", default=""
    )
    update_plan: Dict[str, Any] = Field(
        description="Updates to the trip plan state.", default={}
    )


class CritiqueOutput(BaseModel):
    decision: Literal["APPROVE", "REJECT"] = Field(description="Decision on the plan.")
    feedback: str = Field(description="Feedback if rejected.", default="")
    score: int = Field(description="Quality score 1-10.")


# --- NODES ---


# 1. SUPERVISOR NODE
def supervisor_node(state: AgentState) -> Dict[str, Any]:
    print(f"--- NODE: SUPERVISOR --- State keys: {list(state.keys())}")
    user_query = state.get("user_query", "")
    print(f"  User Query in Supervisor: {user_query}")
    import sys

    sys.stdout.flush()

    # --- Build conversation history for multi-turn context ---
    from langchain_core.messages import HumanMessage, AIMessage
    messages = state.get("messages", [])
    
    messages_to_add = []
    is_new_turn = False
    
    if not messages or not (isinstance(messages[-1], HumanMessage) and messages[-1].content == user_query):
        messages_to_add.append(HumanMessage(content=user_query))
        is_new_turn = True

    all_context_messages = messages + messages_to_add
    conversation_history = ""
    if all_context_messages:
        history_lines = []
        for msg in all_context_messages[-8:]:
            role = "User" if isinstance(msg, HumanMessage) else "Agent"
            history_lines.append(f"{role}: {msg.content[:200]}")
        conversation_history = "\nCONVERSATION HISTORY:\n" + "\n".join(history_lines)

    # Start every new conversation fresh. Do not auto-load any external profile.
    # The session profile is built incrementally from this conversation only.
    current_profile = state.get("user_profile")

    # Prepare Profile String for Context
    profile_context = "Unknown"
    if current_profile:
        profile_context = (
            f"Style: {current_profile.travel_style or 'Any'}, "
            f"Diet: {', '.join(current_profile.dietary_needs)}, "
            f"Interests: {', '.join(current_profile.interests)}, "
            f"Accessibility: {', '.join(current_profile.accessibility_needs)}"
        )

    # Helper function to persist state updates on ALL return paths
    def _apply_updates(
        updates: dict, extracted_prefs: list = None, extracted_trip_type: str = None, is_terminal: bool = False
    ) -> dict:
        """Helper to merge profile updates and message/turn logic before returning state."""
        # 1. Build/update a session-local profile from conversation signals only.
        profile = current_profile
        if profile is None and (extracted_prefs or extracted_trip_type):
            profile = UserProfile(user_id="session-local")

        if profile is not None:
            lower_interests = {i.lower() for i in (profile.interests or [])}
            merged_interests = list(profile.interests or [])
            for pref in (extracted_prefs or []):
                if pref and pref.lower() not in lower_interests:
                    merged_interests.append(pref)
                    lower_interests.add(pref.lower())

            dietary_keywords = {
                "vegan": "vegan",
                "vegetarian": "vegetarian",
                "gluten-free": "gluten-free",
                "gluten free": "gluten-free",
                "kosher": "kosher",
            }
            lower_diet = {d.lower() for d in (profile.dietary_needs or [])}
            merged_diet = list(profile.dietary_needs or [])
            for pref in (extracted_prefs or []):
                normalized = dietary_keywords.get((pref or "").strip().lower())
                if normalized and normalized.lower() not in lower_diet:
                    merged_diet.append(normalized)
                    lower_diet.add(normalized.lower())

            if extracted_trip_type and not profile.travel_style:
                profile.travel_style = extracted_trip_type

            profile.interests = merged_interests
            profile.dietary_needs = merged_diet
            updates["user_profile"] = profile
                    
        # 2. Context-switch: if destination changed, wipe stale trip_plan and duration
        new_dest = updates.get("destination")
        old_dest = state.get("destination")
        if new_dest and old_dest and new_dest.lower() != old_dest.lower():
            updates.setdefault("trip_plan", None)
            # Don't carry over duration from old destination — it belongs to old context
            if "duration_days" not in updates:
                updates["duration_days"] = 0

        # 3. Deduplicate preferences (operator.add accumulates duplicates over turns)
        if "preferences" in updates:
            seen = set()
            deduped = []
            for p in (updates["preferences"] or []):
                pl = p.lower()
                if pl not in seen:
                    seen.add(pl)
                    deduped.append(p)
            updates["preferences"] = deduped

        # 4. Multi-turn memory appending logic
        msgs = list(messages_to_add)
        if is_terminal and updates.get("supervisor_instruction"):
            msgs.append(AIMessage(content=updates["supervisor_instruction"]))
        
        if msgs:
            updates["messages"] = msgs
            
        if is_new_turn:
            updates["researcher_calls"] = 0
            
        return updates

    # Simple Router Logic (Optimization: Don't call LLM for simple greetings)
    # Strip punctuation/whitespace and check case-insensitively
    import re

    cleaned_query = re.sub(r"[^\w\s]", "", user_query.strip()).lower().strip()
    _GREETING_EXACT = {"hi", "hello", "hey", "test", "yo", "sup", "hi there", "hello there",
                       "hey there", "good morning", "good afternoon", "good evening",
                       "greetings", "howdy", "what's up", "whats up"}
    _is_greeting = (cleaned_query in _GREETING_EXACT or
                    (len(cleaned_query.split()) <= 3 and
                     any(cleaned_query.startswith(g) for g in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"])))
    if _is_greeting:
        return _apply_updates(
            {
                "next_step": "End",
                "supervisor_instruction": "Hi! I'm Tripzy, your AI travel assistant. I can help you discover destinations, search for flights, find hotels, and suggest things to do. What are you looking for?",
                "steps": [
                    {
                        "module": "Supervisor",
                        "prompt": user_query,
                        "response": "Greeted user.",
                    }
                ],
            },
            is_terminal=True
        )

    # ── ATTRACTIONS QUERY CAPTURE ─────────────────────────────────────────────
    # If we just asked "what kind of attractions?" and this is the user's reply,
    # store it as attractions_query and route to Attractions.
    _prior_request_type = state.get("request_type") or ""
    _prior_attractions_q = (state.get("attractions_query") or "").strip()
    _prior_instruction = (state.get("supervisor_instruction") or "").lower()
    if (
        _prior_request_type == "AttractionsOnly"
        and not _prior_attractions_q
        and "what kind of attractions" in _prior_instruction
        and user_query.strip()
    ):
        _dest = state.get("destination", "")
        print(f"  [ATTRACTIONS QUERY CAPTURE] Storing attractions_query: {user_query!r}")
        return _apply_updates(
            {
                "next_step": "Attractions",
                "request_type": "AttractionsOnly",
                "attractions_query": user_query.strip(),
                "destination": _dest,
                "pending_stages": state.get("pending_stages") or [],
                "steps": [{"module": "Supervisor", "prompt": user_query,
                            "response": f"Stored attractions_query, routing to Attractions."}],
            }
        )
    # ─────────────────────────────────────────────────────────────────────────

    # ── PENDING STAGES CHECK (combined request chaining) ──────────────────────
    # If there are pending stages from a previous combined request stage and
    # the previous stage produced a result, auto-route to Trip_Planner for the
    # next stage without calling the LLM.
    pending_stages_from_state = list(state.get("pending_stages") or [])
    if pending_stages_from_state and state.get("trip_plan"):
        next_stage = pending_stages_from_state.pop(0)
        _dest = state.get("destination", "")

        if next_stage == "AttractionsOnly":
            # For attractions we need a free-text query — ask if not yet captured.
            _attr_q = (state.get("attractions_query") or "").strip()
            if not _attr_q:
                print(f"  [PENDING STAGES] AttractionsOnly next — asking for attractions_query.")
                return _apply_updates(
                    {
                        "next_step": "End",
                        "request_type": "AttractionsOnly",
                        "pending_stages": [next_stage] + pending_stages_from_state,  # put it back
                        "supervisor_instruction": "What kind of attractions are you looking for? (e.g. beaches, temples, restaurants, nightlife, museums)",
                        "destination": _dest,
                        "steps": [{"module": "Supervisor", "prompt": user_query,
                                    "response": "Asked user for attractions type before continuing pipeline."}],
                    },
                    is_terminal=True,
                )
            print(f"  [PENDING STAGES] Auto-routing to Attractions for AttractionsOnly (remaining: {pending_stages_from_state})")
            return _apply_updates(
                {
                    "next_step": "Attractions",
                    "request_type": "AttractionsOnly",
                    "pending_stages": pending_stages_from_state,
                    "supervisor_instruction": f"Find attractions in {_dest} matching: {_attr_q}",
                    "destination": _dest,
                    "attractions_query": _attr_q,
                    "steps": [{"module": "Supervisor", "prompt": user_query,
                                "response": f"Auto-continuing to AttractionsOnly."}],
                }
            )

        _stage_instructions = {
            "HotelOnly": f"Find the best hotel options in {_dest}. Use check-in/check-out dates from state.",
        }
        _stage_instruction = _stage_instructions.get(next_stage, f"Continue with {next_stage} for {_dest}.")
        print(f"  [PENDING STAGES] Auto-routing to Trip_Planner for {next_stage} (remaining: {pending_stages_from_state})")
        return _apply_updates(
            {
                "next_step": "Trip_Planner",
                "request_type": next_stage,
                "pending_stages": pending_stages_from_state,
                "supervisor_instruction": _stage_instruction,
                "destination": _dest,
                "origin_city": state.get("origin_city", ""),
                "budget_limit": state.get("budget_limit") or 0,
                "budget_currency": state.get("budget_currency") or "USD",
                "trip_type": state.get("trip_type") or "",
                "duration_days": state.get("duration_days") or 0,
                "traveling_personas_number": state.get("traveling_personas_number") or 1,
                "amenities": list(state.get("amenities") or []),
                "preferences": [],
                "steps": [{"module": "Supervisor", "prompt": user_query,
                            "response": f"Auto-continuing combined request: {next_stage}."}],
            }
        )
    # ─────────────────────────────────────────────────────────────────────────

    # Format context for the LLM clearly, including RAG results
    steps = state.get("steps", [])
    research_steps = [s for s in steps if s.get("module") == "Researcher"]

    # Format RAG results as clean text (not raw JSON) so the LLM can reason over them
    research_history = ""
    if research_steps:
        history_lines = []
        for s in research_steps[-3:]:
            resp = s.get("response", "")
            try:
                parsed = json.loads(resp)
                if isinstance(parsed, list):
                    dest_texts = []
                    for d in parsed[:5]:
                        name = d.get("destination", d.get("name", "Unknown"))
                        summary = d.get("summary", "")[:200]
                        score = d.get("score", "")
                        dest_texts.append(f"  • {name} (relevance={score}): {summary}")
                    history_lines.append(
                        "PREVIOUS DESTINATION SUGGESTIONS:\n" + "\n".join(dest_texts)
                    )
                else:
                    history_lines.append(f"RESEARCH RESULT: {resp[:500]}")
            except (json.JSONDecodeError, TypeError):
                history_lines.append(f"RESEARCH RESULT: {resp[:500]}")
        research_history = "\n".join(history_lines)

    current_context = (
        f"CURRENT STATE:\n"
        f"- Today's Date: {datetime.today().strftime('%Y-%m-%d')} (use this to resolve relative dates like 'next week', 'next month', 'this weekend', 'in 2 weeks')\n"
        f"- User Profile: {profile_context}\n"
        f"- Destination: {state.get('destination') or 'Not Set'}\n"
        f"- Duration: {state.get('duration_days') or 0} days\n"
        f"- Budget: {state.get('budget_limit') or 0} {state.get('budget_currency') or 'USD'}\n"
        f"- Trip Type: {state.get('trip_type') or 'Not Set'}\n"
        f"- Origin: {state.get('origin_city') or 'Not Set'}\n"
        f"- Travelers: {state.get('traveling_personas_number') or 1}\n"
        f"- Amenities: {state.get('amenities') or []}\n"
        f"- Request Type: {state.get('request_type') or 'Not Set'}\n"
        f"- Preferences so far: {', '.join(state.get('preferences') or []) or 'None'}\n"
        f"{research_history}\n"
        f"{conversation_history}"
    )

    # Construct Messages for ChatPromptTemplate
    llm_messages = [
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        ("human", "Context:\n{context}\n\nUser Input: {query}"),
    ]

    # DYNAMIC INJECTION: Add loop-prevention instruction into the messages list
    # (Previously this was built but never added — now it IS added)
    asks_for_new_region = False  # hoisted so Preference Refinement Guard can access it
    if research_steps:
        user_query_lower = user_query.lower()
        asks_for_new_region = any(
            kw in user_query_lower
            for kw in [
                # Region / change keywords
                "south america",
                "north america",
                "europe",
                "asia",
                "africa",
                "southeast asia",
                "caribbean",
                "middle east",
                "mediterranean",
                "something else",
                "other options",
                "different",
                "instead",
                "other countries",
                "another",
                "more options",
                "other region",
                "elsewhere",
                "different place",
                # Climate / environment preferences
                "beach", "beachy", "warm", "tropical", "hot", "sunny",
                "island", "snorkel", "diving", "swim", "ocean", "sea",
                "cold", "snow", "ski", "mountains", "hiking", "adventure",
                "desert", "safari", "nature", "outdoors",
                # Budget / style preferences
                "budget", "cheap", "affordable", "backpack", "luxury",
                "boutique", "all-inclusive",
                # Travel persona
                "family", "kids", "children", "solo", "couple",
                "romantic", "honeymoon", "friends",
                # Activity preferences
                "culture", "history", "museum", "food", "nightlife",
                "relax", "spa", "wellness", "shopping",
            ]
        )
        if asks_for_new_region:
            loop_prevention_msg = (
                "SYSTEM: The user is adding NEW preferences or refining their request "
                "(e.g. climate, activities, budget, travel style). "
                "You MUST route to 'Researcher' to run a fresh suggest_destination_tool search "
                "with ALL merged preferences (old + new). Do NOT route to End without searching first."
            )
        else:
            loop_prevention_msg = (
                "SYSTEM: Destination suggestions have already been retrieved (see PREVIOUS DESTINATION SUGGESTIONS above). "
                "If the user has added NEW preferences (climate, activities, budget, style) "
                "not reflected in those suggestions → route to Researcher with all merged preferences. "
                "If the user is picking from the existing options or asking a general question → "
                "route to End with a warm, natural response."
            )
        llm_messages.append(("system", loop_prevention_msg))

    prompt = ChatPromptTemplate.from_messages(llm_messages)
    chain = prompt | llm.with_structured_output(SupervisorOutput)

    try:
        result = safe_llm_invoke(
            chain, {"query": user_query, "context": current_context}
        )

        print(f"SUPERVISOR RESULT: {result}")
        print(
            f"  [Supervisor] next_step={result.next_step}, request_type={result.request_type}, prefs={result.preferences}"
        )

        # ── COMBINED REQUEST DETECTION (Python-level, takes priority over LLM) ──
        # Detect when user asks for multiple service types in one message.
        _uq = user_query.lower()
        _flight_kws = ["flight", "fly ", "flying ", "flights", "airline", "fly to"]
        _hotel_kws  = ["hotel", " stay", "accommodation", "hostel", "lodging"]
        _attr_kws   = ["things to do", "attractions", "activities", "what to do",
                       "restaurants", "sights", "tours", "explore"]
        _py_wants_flight = any(k in _uq for k in _flight_kws)
        _py_wants_hotel  = any(k in _uq for k in _hotel_kws)
        _py_wants_attr   = any(k in _uq for k in _attr_kws)
        _combined = [t for t, w in [("FlightOnly", _py_wants_flight),
                                     ("HotelOnly",  _py_wants_hotel),
                                     ("AttractionsOnly", _py_wants_attr)] if w]
        if len(_combined) > 1:
            result.request_type = _combined[0]
            result.pending_stages = _combined[1:]
            print(f"  [COMBINED REQUEST GUARD] Detected {_combined}: first={_combined[0]}, pending={result.pending_stages}")
        # ─────────────────────────────────────────────────────────────────────

        # ── ASK FOR REQUEST TYPE GUARD ────────────────────────────────────────
        # Destination known but no service type specified → ask what they want.
        _known_dest = result.destination or state.get("destination", "")
        _no_concrete_service = not (_py_wants_flight or _py_wants_hotel or _py_wants_attr)
        _prior_request_type = state.get("request_type") or ""
        if (
            _known_dest
            and _no_concrete_service
            and result.next_step == "End"
            and not _prior_request_type  # not mid-conversation
        ):
            print(f"  [ASK REQUEST TYPE GUARD] Destination known ({_known_dest}) but service unclear → asking.")
            return _apply_updates(
                {
                    "next_step": "End",
                    "supervisor_instruction": "What would you like help with: flights, hotels, or attractions?",
                    "destination": _known_dest,
                    "duration_days": result.duration_days or state.get("duration_days") or 0,
                    "budget_limit": result.budget_limit or state.get("budget_limit") or 0,
                    "budget_currency": result.budget_currency or state.get("budget_currency", "USD"),
                    "trip_type": result.trip_type or state.get("trip_type") or "",
                    "preferences": result.preferences or [],
                    "request_type": "GeneralQuestion",
                    "pending_stages": [],
                    "steps": [{"module": "Supervisor", "prompt": user_query,
                                "response": "Asked user for request type (flights/hotels/attractions)."}],
                },
                extracted_prefs=result.preferences,
                is_terminal=True,
            )
        # ─────────────────────────────────────────────────────────────────────

        step_log = {
            "module": "Supervisor",
            "prompt": user_query,
            "response": f"Routing to {result.next_step}: {result.reasoning}",
        }

        # ── DESTINATION SWITCH GUARD (code-level override) ───────────────────
        # If prior request was FlightOnly/HotelOnly and the supervisor mistakenly
        # routes to End with a different destination, correct it to Trip_Planner.
        prior_request_type = state.get("request_type", "")
        prior_destination = (state.get("destination") or "").strip().lower()
        new_destination = (result.destination or "").strip().lower()
        if (
            prior_request_type in ("FlightOnly", "HotelOnly")
            and new_destination
            and prior_destination
            and new_destination != prior_destination
            and result.next_step == "End"
            and result.request_type in ("HotelOnly", "FlightOnly")
        ):
            print(
                f"  [DEST SWITCH GUARD] Overriding End/{result.request_type} "
                f"→ Trip_Planner/{prior_request_type} (dest: {prior_destination} → {new_destination})"
            )
            result.next_step = "Trip_Planner"
            result.request_type = prior_request_type
        # ─────────────────────────────────────────────────────────────────────

        # HANDLE GENERAL QUESTIONS (Facts, Geography)
        if result.request_type == "GeneralQuestion":
            print(f"  [GENERAL QUESTION] Routing to Researcher for answering question.")

            # If we haven't done research yet, route to researcher for web search
            if not research_steps:
                return _apply_updates(
                    {
                        "next_step": "Researcher",
                    # Instead of TOOL_CALLS, we just pass the text instruction so researcher does a web search
                    "supervisor_instruction": result.instruction or user_query,
                    "destination": result.destination or state.get("destination"),
                    "duration_days": result.duration_days or state.get("duration_days"),
                    "budget_limit": result.budget_limit or state.get("budget_limit"),
                    "budget_currency": result.budget_currency
                    or state.get("budget_currency", "USD"),
                    "trip_type": result.trip_type or state.get("trip_type"),
                    "origin_city": result.origin_city or state.get("origin_city"),
                    "traveling_personas_number": result.traveling_personas_number
                    or state.get("traveling_personas_number", 1),
                    "amenities": result.amenities,
                    "preferences": result.preferences,
                    "request_type": result.request_type,
                    "steps": [
                        {
                            "module": "Supervisor",
                            "prompt": user_query,
                            "response": "Routing to Researcher to answer general question.",
                        }
                    ],
                })
            else:
                # We already did research, summarize back to the user
                last_research_response = research_steps[-1].get("response", "")
                return _apply_updates(
                    {
                        "next_step": "End",
                        # Format a nice output based on the research finding
                        "supervisor_instruction": result.instruction,
                        "destination": result.destination or state.get("destination"),
                        "duration_days": result.duration_days
                        or state.get("duration_days"),
                        "budget_limit": result.budget_limit
                        or state.get("budget_limit"),
                        "budget_currency": result.budget_currency
                        or state.get("budget_currency", "USD"),
                        "trip_type": result.trip_type or state.get("trip_type"),
                        "origin_city": result.origin_city or state.get("origin_city"),
                        "traveling_personas_number": result.traveling_personas_number
                        or state.get("traveling_personas_number", 1),
                        "amenities": result.amenities,
                        "preferences": result.preferences,
                        "request_type": result.request_type,
                        "steps": [
                            {
                                "module": "Supervisor",
                                "prompt": user_query,
                                "response": result.instruction,
                            }
                        ],
                    },
                    extracted_prefs=result.preferences,
                    extracted_trip_type=result.trip_type,
                    is_terminal=True
                )

        # EDGE CASE VALIDATION - Check for impossible/problematic requests
        from app.edge_case_validator import process_edge_cases

        # Only enforce strict planning constraints (duration + budget required) for full Planning requests.
        # FlightOnly, HotelOnly, AttractionsOnly, Discovery don't need duration.
        PARTIAL_REQUEST_TYPES = {
            "FlightOnly",
            "HotelOnly",
            "AttractionsOnly",
            "Discovery",
            "Greeting",
        }
        request_type_for_validation = result.request_type or ""
        # Full planning is disabled — always treat as partial
        is_planning = False

        edge_case_result = process_edge_cases(
            user_query=user_query,
            duration_days=result.duration_days,
            budget_limit=result.budget_limit,
            budget_currency=result.budget_currency,
            trip_type=result.trip_type,
            destination=result.destination,
            is_planning=is_planning,
        )

        if edge_case_result["has_edge_case"] and edge_case_result["should_block"]:
            # Don't proceed to planning, inform user of the issue
            print(
                f"  [EDGE CASE DETECTED] {edge_case_result['error_message'][:100]}..."
            )
            return _apply_updates(
                {
                    "next_step": "End",
                    "supervisor_instruction": edge_case_result["error_message"],
                    "destination": result.destination or state.get("destination"),
                    "duration_days": result.duration_days or state.get("duration_days"),
                    "budget_limit": result.budget_limit or state.get("budget_limit"),
                    "budget_currency": result.budget_currency
                    or state.get("budget_currency", "USD"),
                    "trip_type": result.trip_type or state.get("trip_type"),
                    "origin_city": result.origin_city or state.get("origin_city"),
                    "traveling_personas_number": result.traveling_personas_number
                    or state.get("traveling_personas_number", 1),
                    "amenities": result.amenities,
                    "preferences": result.preferences,
                    "steps": [
                        {
                            "module": "Supervisor",
                            "prompt": user_query,
                            "response": f"Edge Case Detected: {edge_case_result['error_message']}",
                        }
                    ],
                },
                extracted_prefs=result.preferences,
                extracted_trip_type=result.trip_type,
                is_terminal=True
            )

        # ────────────────────────────────────────────────────────────────────────
        # VAGUE DESTINATION GUARD
        # If the user says "Europe", "Caribbean", etc. — not a real destination.
        # Ask them to pick a specific city, with tailored examples per region.
        # ────────────────────────────────────────────────────────────────────────
        VAGUE_DESTINATIONS = {
            "europe", "european", "south america", "north america", "latin america",
            "central america", "asia", "southeast asia", "east asia", "south asia",
            "middle east", "africa", "sub-saharan africa", "north africa", "oceania",
            "pacific", "caribbean", "caribbeans", "scandinavia", "nordic",
            "mediterranean", "balkans", "eastern europe", "western europe",
            "central asia", "the world", "somewhere", "anywhere", "abroad",
            "overseas", "international", "a nice place", "a good place",
            "somewhere nice", "somewhere warm", "somewhere cold", "somewhere sunny",
            "somewhere exotic",
        }

        _REGION_EXAMPLES = {
            "caribbean":      "Aruba, Bahamas (Nassau), Barbados, Curaçao, or Cancún",
            "caribbeans":     "Aruba, Bahamas (Nassau), Barbados, Curaçao, or Cancún",
            "europe":         "Paris, Rome, Barcelona, Amsterdam, or Prague",
            "european":       "Paris, Rome, Barcelona, Amsterdam, or Prague",
            "mediterranean":  "Barcelona, Nice, Santorini, Dubrovnik, or Malta",
            "scandinavia":    "Stockholm, Copenhagen, Oslo, Helsinki, or Reykjavik",
            "nordic":         "Stockholm, Copenhagen, Oslo, Helsinki, or Reykjavik",
            "southeast asia": "Bangkok, Bali, Singapore, Ho Chi Minh City, or Kuala Lumpur",
            "east asia":      "Tokyo, Seoul, Hong Kong, Taipei, or Shanghai",
            "south asia":     "Mumbai, Delhi, Colombo, Kathmandu, or Dhaka",
            "middle east":    "Dubai, Tel Aviv, Amman, Doha, or Muscat",
            "africa":         "Cape Town, Marrakech, Nairobi, Cairo, or Lagos",
            "north africa":   "Marrakech, Cairo, Tunis, Casablanca, or Alexandria",
            "south america":  "Buenos Aires, Rio de Janeiro, Lima, Medellín, or Cartagena",
            "latin america":  "Mexico City, Bogotá, Buenos Aires, Lima, or San José",
            "central america":"San José, Panama City, Guatemala City, or Antigua",
            "oceania":        "Sydney, Auckland, Melbourne, Fiji, or Bora Bora",
            "pacific":        "Sydney, Auckland, Honolulu, Fiji, or Bora Bora",
        }

        def _is_vague_destination(dest: str) -> bool:
            if not dest:
                return False
            return dest.strip().lower() in VAGUE_DESTINATIONS

        def _vague_dest_message(dest: str, request_type: str) -> str:
            key = dest.strip().lower()
            examples = _REGION_EXAMPLES.get(key)
            region_name = dest.strip().title()
            if examples:
                return (
                    f"**{region_name}** is a broad region — flights and hotels need a specific "
                    f"city or island. Which one did you have in mind? For example: {examples}."
                )
            service = {"FlightOnly": "flights", "HotelOnly": "hotels"}.get(request_type, "this search")
            return (
                f"**{region_name}** is a broad region and {service} require a specific city or "
                "destination. Could you tell me which city or place you'd like to visit?"
            )

        raw_destination = result.destination or state.get("destination") or ""
        # Fallback: LLM sometimes clears destination when it recognises a vague region.
        # Scan the raw user query for any known vague keyword so the guard still fires.
        if not raw_destination:
            _uq_lower = user_query.lower()
            for _vd in sorted(VAGUE_DESTINATIONS, key=len, reverse=True):  # longest match first
                if _vd in _uq_lower:
                    raw_destination = _vd
                    print(f"  [VAGUE DEST FALLBACK] Extracted '{_vd}' from user query (LLM cleared destination)")
                    break
        if result.request_type in ("FlightOnly", "HotelOnly") and _is_vague_destination(raw_destination):
            print(f"  [VAGUE DEST GUARD] '{raw_destination}' is a region → asking for specific city.")
            _vague_msg = _vague_dest_message(raw_destination, result.request_type)
            return _apply_updates(
                {
                    "next_step": "End",
                    "supervisor_instruction": _vague_msg,
                    "destination": "",
                    "request_type": result.request_type,
                    "pending_stages": result.pending_stages or [],
                    "steps": [{"module": "Supervisor", "prompt": user_query,
                                "response": f"Vague destination '{raw_destination}' → asked for specific city."}],
                },
                extracted_prefs=result.preferences,
                extracted_trip_type=result.trip_type,
                is_terminal=True,
            )

        # MULTI-TURN: Check if we have minimum required information
        # If supervisor wants to route to Trip_Planner, validate we have destination + duration
        if result.next_step == "Trip_Planner":
            missing_required = []

            # Check what we already have in state (from previous turns)
            print(
                f"state dest: {state.get('destination')}, and res dest: {result.destination}"
            )
            current_destination = state.get("destination") or result.destination
            current_duration = state.get("duration_days") or result.duration_days

            # DIFFERENT REQUREMENTS BASED ON REQUEST TYPE
            req_type = result.request_type or "Discovery"

            # --- MANUAL OVERRIDE FOR ATTRACTIONS ONLY ---
            # LLMs struggle to differentiate "Planning with known destination" vs "AttractionsOnly".
            # If user explicitly says they have booked/flights/hotel, force AttractionsOnly.
            user_query_lower = state.get("user_query", "").lower()
            if (
                "already booked" in user_query_lower
                or "have flights" in user_query_lower
                or "have hotel" in user_query_lower
            ):
                print(
                    "  [OVERRIDE] Detected 'already booked' intent -> Forcing AttractionsOnly"
                )
                req_type = "AttractionsOnly"
                # Also update the result object so it propagates correctly
                result.request_type = "AttractionsOnly"

            # Destination is always required
            if not current_destination:
                missing_required.append("destination")

            # Duration: Not required since full planning is disabled. Optional for all types.

            # Origin: Required for FlightOnly.
            # For Planning, it's good but maybe optional? Let's keep it optional for Planning to be safe,
            # but strict for FlightOnly where moving people is the whole point.
            current_origin = state.get("origin_city") or result.origin_city
            if req_type == "FlightOnly":
                if not current_origin:
                    missing_required.append("origin")

            # For HotelOnly, we might want check-in/out dates, usually implied by "duration" or specific dates.
            # If duration is 0, we might ask "for how many nights?"
            if req_type == "HotelOnly":
                if not current_duration or current_duration == 0:
                    # Optional: enforce duration for hotels too?
                    # valid: "Hotel in Paris" -> 1 night default? Or ask?
                    # Let's ask to be helpful.
                    missing_required.append("duration")

            # If missing required info, ask for the FIRST missing piece
            if missing_required:
                # Helper to make questions contextual
                topic = f"{result.trip_type} trip" if result.trip_type else "trip"

                if "destination" in missing_required:
                    clarifying_question = f"That sounds great! 🌍 But could you tell me where you'd like to go for your {topic}? (e.g., Paris, Bali, Tokyo)"
                elif "duration" in missing_required:
                    if req_type == "HotelOnly":
                        clarifying_question = f"I'd love to find you a hotel! 🏨 How many nights do you need to stay?"
                    else:
                        clarifying_question = f"I'd love to plan this {topic} for you! 🗓️ How many days or weeks are you thinking of traveling?"
                elif "origin" in missing_required:
                    clarifying_question = f"To find the best flights ✈️, could you tell me which city you'll be flying from?"
                else:
                    clarifying_question = result.instruction

                print(
                    f"  [MULTI-TURN] Missing required info: {missing_required}. Asking for clarification."
                )
                return _apply_updates(
                    {
                        "next_step": "End",
                        "supervisor_instruction": clarifying_question,
                        "destination": result.destination or current_destination,
                        "duration_days": result.duration_days or current_duration,
                        "origin_city": result.origin_city or current_origin,
                        # Persist other fields too so they aren't lost if extracted in this turn
                        "budget_limit": result.budget_limit
                        or state.get("budget_limit"),
                        "budget_currency": result.budget_currency
                        or state.get("budget_currency", "USD"),
                        "trip_type": result.trip_type or state.get("trip_type"),
                        "preferences": result.preferences,
                        "traveling_personas_number": result.traveling_personas_number
                        or state.get("traveling_personas_number", 1),
                        "amenities": result.amenities,
                        "request_type": req_type,  # Ensure this is persisted!
                        # Preserve pending_stages so combined requests survive mid-flow clarifications
                        "pending_stages": result.pending_stages if result.pending_stages else (state.get("pending_stages") or []),
                        "steps": [
                            {
                                "module": "Supervisor",
                                "prompt": user_query,
                                "response": f"Need more information: {clarifying_question}",
                            }
                        ],
                    },
                    extracted_prefs=result.preferences,
                    extracted_trip_type=result.trip_type,
                    is_terminal=True
                )
        else:
            print(
                f"  [MULTI-TURN] All required info present. Routing to {result.next_step}."
            )

        # GENERAL KNOWLEDGE GUARD: If supervisor routes to End but request_type
        # is HotelOnly/FlightOnly with all required fields present, it answered
        # from general knowledge instead of searching. Override to Trip_Planner.
        if result.next_step == "End" and result.request_type in ("HotelOnly", "FlightOnly"):
            current_dest = result.destination or state.get("destination")
            current_duration = result.duration_days or state.get("duration_days")
            current_origin = result.origin_city or state.get("origin_city")
            # Check if all fields are actually present
            hotel_ready = (
                result.request_type == "HotelOnly"
                and current_dest
                and current_duration and current_duration > 0
            )
            flight_ready = (
                result.request_type == "FlightOnly"
                and current_dest
                and current_origin
                # date is in instruction or user message
                and any(
                    c.isdigit() for c in (result.instruction or user_query)
                )
            )
            # For HotelOnly: if all fields present, any "question" is LLM fabricating hotel options
            # from general knowledge ("Here are 3 hotels... Which to search?") — always override.
            # For FlightOnly: only override if not a genuine clarifying question.
            instruction_is_question = result.instruction.strip().endswith("?") if result.instruction else False
            if hotel_ready or (flight_ready and not instruction_is_question):
                print(
                    f"  [GK GUARD] Supervisor answered from general knowledge for {result.request_type}. "
                    f"Overriding End → Trip_Planner."
                )
                result.next_step = "Trip_Planner"

        # ── ATTRACTIONS QUERY GUARD ───────────────────────────────────────────
        # AttractionsOnly needs a free-text description of what the user wants.
        # Fall back (in order) to: explicit attractions_query state → raw user
        # query → Supervisor-generated instruction. Only prompt the user again
        # when all three sources are empty.
        if result.request_type == "AttractionsOnly" and result.next_step == "Attractions":
            _attractions_q = (
                state.get("attractions_query")
                or state.get("user_query")
                or result.instruction
                or ""
            ).strip()
            if not _attractions_q:
                print("  [ATTRACTIONS GUARD] No attractions_query in state — asking user.")
                return _apply_updates(
                    {
                        "next_step": "End",
                        "supervisor_instruction": "What kind of attractions are you looking for? (e.g. beaches, temples, restaurants, nightlife, museums)",
                        "destination": result.destination or state.get("destination"),
                        "request_type": "AttractionsOnly",
                        "pending_stages": result.pending_stages or state.get("pending_stages") or [],
                        "steps": [{"module": "Supervisor", "prompt": user_query,
                                    "response": "Asked user for attractions type."}],
                    },
                    extracted_prefs=result.preferences,
                    is_terminal=True,
                )
            elif not state.get("attractions_query"):
                # Backfill so the Attractions node and downstream state always
                # have an explicit attractions_query set.
                print(f"  [ATTRACTIONS GUARD] Backfilling attractions_query: {_attractions_q!r}")
                result.__dict__["_backfill_attractions_q"] = _attractions_q
        # ─────────────────────────────────────────────────────────────────────

        updates = {
            "next_step": result.next_step,
            "supervisor_instruction": result.instruction,
            "duration_days": result.duration_days or state.get("duration_days"),
            "destination": result.destination or state.get("destination"),
            "budget_limit": result.budget_limit or state.get("budget_limit"),
            "budget_currency": result.budget_currency
            or state.get("budget_currency", "USD"),
            "trip_type": result.trip_type or state.get("trip_type"),
            "origin_city": result.origin_city or state.get("origin_city"),
            "traveling_personas_number": result.traveling_personas_number
            or state.get("traveling_personas_number", 1),
            "amenities": result.amenities,
            "preferences": result.preferences,
            "request_type": result.request_type,
            "pending_stages": result.pending_stages if result.pending_stages else (state.get("pending_stages") or []),
            "steps": [step_log],
        }

        # ── ATTRACTIONS_QUERY PERSISTENCE ────────────────────────────────────
        # a) Follow-up: user already had an attractions result and is now asking
        #    for something different (e.g. "and museums? maybe local history").
        #    → OVERWRITE attractions_query with the fresh user message so the
        #      Attractions node searches only the new intent.
        # b) First-time / backfill: no prior attractions_query in state yet.
        #    → Fill from the fallback chain: existing value → backfill tag →
        #      current user_query.
        if result.request_type == "AttractionsOnly":
            _prior_attr_q = (state.get("attractions_query") or "").strip()
            if _prior_attr_q and user_query.strip():
                print(
                    f"  [ATTRACTIONS FOLLOW-UP] Replacing stale query "
                    f"{_prior_attr_q!r} with new intent {user_query.strip()!r}"
                )
                updates["attractions_query"] = user_query.strip()
            else:
                updates["attractions_query"] = (
                    _prior_attr_q
                    or getattr(result, "_backfill_attractions_q", None)
                    or user_query.strip()
                    or ""
                )
        else:
            updates["attractions_query"] = state.get("attractions_query", "")
        # ─────────────────────────────────────────────────────────────────────

        return _apply_updates(
            updates,
            extracted_prefs=result.preferences,
            extracted_trip_type=result.trip_type,
            is_terminal=(updates.get("next_step") == "End")
        )
    except Exception as e:
        print(f"  Supervisor Error: {str(e)}")
        classified = _classify_error(e)
        error_msg = classified["user_msg"]
        return _apply_updates(
            {
                "next_step": "End",
                "supervisor_instruction": error_msg,
                "steps": [{"module": "Supervisor", "error": str(e), "response": error_msg}],
            },
            is_terminal=True
        )


# ... (Previous code remains the same up to Planner Node)


def _validate_plan_output(request_type: str, trip_plan_data: dict) -> tuple:
    """
    Validates that the plan actually contains the expected data for the request type.
    Returns (is_valid: bool, sorry_message: str | None).
    """
    if request_type == "FlightOnly":
        outbound = trip_plan_data.get("outbound_flight") or {}
        if not outbound:
            flights = trip_plan_data.get("flights") or []
            outbound = flights[0] if flights else {}
        if not outbound:
            return False, (
                "Sorry, we couldn't find any available flights for your route. "
                "This may be due to limited availability or a temporary issue with the "
                "flight search. Please try different dates or a different route."
            )
    elif request_type == "HotelOnly":
        hotels = trip_plan_data.get("hotels") or []
        if not hotels:
            return False, (
                "Sorry, we couldn't find any available hotels for your destination. "
                "This may be due to limited availability or a temporary issue with the "
                "hotel search. Please try adjusting your dates or preferences."
            )
    return True, None


def _build_staged_approval_msg(
    request_type: str,
    trip_plan: dict,
    destination: str,
    origin_city: str,
    duration_days: int,
    budget_limit: float,
    budget_currency: str,
    fallback_response: str = "",
) -> str:
    """
    Builds a human-readable, single-option approval question for a given stage.
    Returns a Markdown string with the best option and a yes/no question.
    """
    if request_type == "FlightOnly":
        outbound = trip_plan.get("outbound_flight") or {}
        return_fl = trip_plan.get("return_flight") or {}
        # Also try legacy flights list
        if not outbound:
            flights = trip_plan.get("flights") or []
            outbound = flights[0] if flights else {}
            return_fl = flights[1] if len(flights) > 1 else {}

        if not outbound:
            return fallback_response or "I found a flight option. Would you like to proceed? (yes/no)"

        airline = (outbound.get("source") or outbound.get("airline") or
                   outbound.get("carrierCode") or "Unknown Airline")
        orig = outbound.get("origin") or origin_city or "?"
        dest = outbound.get("destination") or destination or "?"
        price_raw = outbound.get("price", 0)
        try:
            price_val = float(str(price_raw).split()[0].replace(",", ""))
        except (ValueError, TypeError):
            price_val = None
        depart_date = outbound.get("date") or outbound.get("departure") or ""
        return_date = (return_fl.get("date") or return_fl.get("departure") or "") if return_fl else ""
        flight_dur = outbound.get("duration") or ""
        is_direct = outbound.get("is_direct")
        direct_label = ""
        if is_direct is not None:
            direct_label = "Direct" if is_direct else "1+ Stops"

        msg = "✈️ **I found this flight option:**\n\n"
        msg += f"**Route:** {orig} → {dest}\n"
        if depart_date:
            msg += f"**Depart:** {depart_date}\n"
        if return_date:
            msg += f"**Return:** {return_date}\n"
        msg += f"**Airline:** {airline}\n"
        if flight_dur:
            msg += f"**Flight time:** {flight_dur}\n"
        if direct_label:
            msg += f"**Type:** {direct_label}\n"
        if price_val is not None:
            msg += f"**Price:** ${price_val:.0f} {budget_currency}\n"
        elif price_raw:
            msg += f"**Price:** {price_raw}\n"

        return msg

    elif request_type == "HotelOnly":
        hotels = trip_plan.get("hotels") or []
        if not hotels:
            return fallback_response or "I found a hotel option. Would you like to proceed? (yes/no)"

        hotel = hotels[0]
        name = hotel.get("name") or "Hotel"
        rating = hotel.get("rating") or hotel.get("rate") or ""
        price_night = hotel.get("price_per_night") or hotel.get("price") or ""
        total = hotel.get("total_price") or hotel.get("totalPrice") or ""
        location = hotel.get("location") or destination or ""
        if isinstance(location, dict):
            location = location.get("address") or destination
        amenities = hotel.get("amenities") or []

        msg = f"🏨 **I found this hotel in {destination}:**\n\n"
        msg += f"**Hotel:** {name}\n"
        if rating:
            msg += f"**Rating:** {rating} ⭐\n"
        if price_night:
            msg += f"**Price:** {price_night} per night\n"
        if total and duration_days:
            msg += f"**Total:** {total} for {duration_days} nights\n"
        if location and str(location).lower() != destination.lower():
            msg += f"**Location:** {location}\n"
        if amenities:
            amenity_strs = [str(a) for a in amenities[:5]]
            msg += f"**Amenities:** {', '.join(amenity_strs)}\n"

        return msg

    else:
        # AttractionsOnly or other: no approval gate, just return plan text
        return fallback_response or f"Here are the top attractions in {destination}!"


# 2. PLANNER NODE
def planner_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: TRIP_PLANNER ---")
    instruction = state.get("supervisor_instruction", "")

    # Get context data
    duration_days = state.get("duration_days", 7)
    destination = state.get("destination", "")
    budget_limit = state.get("budget_limit", 0.0)
    budget_currency = state.get("budget_currency", "USD")
    trip_type = state.get("trip_type", "")
    origin_city = state.get("origin_city", "")
    traveling_personas_number = state.get("traveling_personas_number", 1)
    amenities = state.get("amenities", [])

    # Build conversation history
    from langchain_core.messages import HumanMessage
    messages = state.get("messages", [])
    conversation_history = "None"
    if messages:
        history_lines = []
        for msg in messages[-4:]:
            role = "User" if isinstance(msg, HumanMessage) else "Agent"
            content = msg.content if msg.content else str(msg)
            history_lines.append(f"{role}: {str(content)[:150]}")
        conversation_history = "\n".join(history_lines)

    # Extract Research Info
    steps = state.get("steps", [])
    research_steps = [s for s in steps if s.get("module") == "Researcher"]
    research_info = "\n".join([f"- {s.get('response')}" for s in research_steps[-3:]])

    # DEFINE TOOLS FOR PLANNER
    # We bind the search tools directly to the LLM
    tools = [
        search_flights_tool,
        search_hotels_tool,
        suggest_destination_tool,
        suggest_attractions_tool,
        search_activities_tool,
        cheapest_flights_tool,
        hotel_ratings_tool,
        resolve_airport_code_tool,
        get_airline_info_tool,
        search_tours_activities_tool,
    ]

    # We also need a structured way to return the FINAL plan.
    # We can use a "SubmitPlan" tool or just rely on the final_response text if we want to keep it simple,
    # BUT the existing architecture expects a JSON `trip_plan` object.
    # Let's bind a "SubmitPlan" tool to handle the final output structured data.

    # Dynamic Prompt based on Request Type
    request_type = state.get("request_type", "FlightOnly")

    from pydantic import create_model
    from typing import Optional

    class Flight(BaseModel):
        source: str = Field(
            ..., description="The airline or source providing the flight"
        )
        origin: str = Field(..., description="The origin airport or city")
        destination: str = Field(..., description="The destination airport or city")
        price: float = Field(..., description="The price of the flight")
        duration: str = Field(..., description="The duration of the flight")
        date: str = Field(..., description="The date of the flight")
        is_direct: bool = Field(
            ..., description="True if the flight is direct, False otherwise"
        )

    class Hotel(BaseModel):
        name: str = Field(..., description="The name of the hotel")
        price_per_night: float = Field(
            ..., description="The price per night of the hotel"
        )
        total_price: float = Field(..., description="The total price of the hotel")
        rating: float = Field(..., description="The rating of the hotel")
        location: str = Field(..., description="The location of the hotel")
        amenities: List[str] = Field(..., description="The amenities of the hotel")
        check_in_date: str = Field(..., description="The check-in date of the hotel")
        check_out_date: str = Field(..., description="The check-out date of the hotel")

    base_fields = {
        "destination": (str, Field(default="", description="Destination city")),
        "origin_city": (str, Field(default="unknown", description="Origin city")),
        "dates": (str, Field(default="", description="Date range")),
        "duration_days": (int, Field(default=0, description="Duration in days")),
        "budget_estimate": (
            float,
            Field(default=0.0, description="Estimated total budget"),
        ),
        "budget_currency": (str, Field(default="USD", description="Currency")),
        "trip_type": (str, Field(default=request_type, description="Trip type")),
        "travelers": (int, Field(default=1, description="Number of travelers")),
    }

    if request_type in ["FlightOnly"]:
        base_fields["outbound_flight"] = (
            Flight,
            Field(
                ...,
                description="The outbound flight from origin to destination. REQUIRED.",
            ),
        )
        if duration_days is not None:
            base_fields["return_flight"] = (
                Flight,
                Field(
                    ...,
                    description="The return flight from destination back to origin. REQUIRED.",
                ),
            )
    if request_type in ["HotelOnly"]:
        base_fields["hotels"] = (
            List[Hotel],
            Field(
                ...,
                description="Selected hotels as a list of Hotel objects. REQUIRED.",
            ),
        )

    if request_type in ["AttractionsOnly"]:
        base_fields["itinerary"] = (
            List[Dict[str, Any]],
            Field(..., description="Daily itinerary of activities. REQUIRED."),
        )

    TripPlanData = create_model("TripPlanData", **base_fields)

    class SubmitPlan(BaseModel):
        """Submit the finalized trip plan. ALWAYS call this when the plan is ready."""

        final_response: str = Field(
            description="Friendly, rich Markdown response to show the user."
        )
        trip_plan: TripPlanData = Field(
            ...,
            description="The complete trip plan data. REQUIRED - always include this.",
        )

    # Bind tools + SubmitPlan
    # processing_tools = tools + [SubmitPlan] # LangChain can bind Pydantic models as tools

    system_prompt = get_planner_prompt(request_type)

    # Construct prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            (
                "human",
                "Current Check: Duration={duration_days}, Dest={destination}, Origin City={origin_city}, Budget={budget_limit}, Number of travelers={traveling_personas_number} Amenities={amenities}. Instruction: {instruction}\n\nCONVERSATION HISTORY:\n{conversation_history}",
            ),
        ]
    )

    # Bind tools to LLM
    # We use bind_tools to let the LLM choose between searching or submitting
    llm_with_tools = llm.bind_tools(tools + [SubmitPlan])
    chain = prompt | llm_with_tools

    print(f"  [DEBUG] CALLING PLANNER with specific details...")

    # Phase 29: Format User Profile for Planner
    user_profile = state.get("user_profile")
    user_profile_str = "None"
    if user_profile:
        user_profile_str = (
            f"Style: {user_profile.travel_style or 'Any'}, "
            f"Diet: {', '.join(user_profile.dietary_needs)}, "
            f"Interests: {', '.join(user_profile.interests)}, "
            f"Accessibility: {', '.join(user_profile.accessibility_needs)}"
        )

    try:
        # Invoke LLM
        result = safe_llm_invoke(
            chain,
            {
                "instruction": instruction,
                "user_profile": user_profile_str,
                "feedback": state.get("critique_feedback", "None"),
                "research_info": research_info if research_info else "None",
                "conversation_history": conversation_history,
                "trip_plan": str(state.get("trip_plan", "None")),
                "budget": str(state.get("budget", "None")),
                "duration_days": duration_days,
                "destination": destination,
                "budget_limit": budget_limit,
                "budget_currency": state.get("budget_currency", "USD"),
                "trip_type": trip_type,
                "origin_city": origin_city,
                "traveling_personas_number": traveling_personas_number,
                "amenities": amenities,
                "current_date": datetime.today().strftime("%Y-%m-%d"),
            },
        )

        # Helper to parse tool calls
        tool_calls = (
            result.tool_calls
            if hasattr(result, "tool_calls") and result.tool_calls
            else []
        )

        # Ensure create_plan_tool has attractions_data in AttractionsOnly flows.
        if request_type == "AttractionsOnly" and tool_calls:
            cached_attractions = state.get("last_attraction_results") or []
            for tc in tool_calls:
                if not isinstance(tc, dict) or tc.get("name") != "create_plan_tool":
                    continue
                args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                if not args.get("attractions_data") and cached_attractions:
                    args["attractions_data"] = json.dumps(cached_attractions, default=str)
                    tc["args"] = args

        content = result.content if hasattr(result, "content") else ""
        content_str = content if content else ""

        _safe = lambda s: str(s).encode("ascii", "replace").decode("ascii")
        print(f"  Planner Content: {_safe(content_str)}")
        print(f"  Tool Calls: {len(tool_calls)}")
        print(f"  Tool Calls: {_safe(tool_calls)}")

        step_log = {
            "module": "Trip_Planner",
            "prompt": instruction,
            "response": content_str if content_str else "Executing Tools...",
        }

        # Handle SubmitPlan Call Before Routing
        submit_plan_call = next(
            (
                tc
                for tc in tool_calls
                if isinstance(tc, dict) and tc.get("name") == "SubmitPlan"
            ),
            None,
        )

        if submit_plan_call:
            submission = submit_plan_call["args"]
            print(f"  [DEBUG] SubmitPlan Args: {list(submission.keys())}")
            final_res = submission.get("final_response", "")
            if final_res:
                step_log["response"] = final_res

        updates = {"steps": [step_log]}
        # Analyze Tool Calls
        if submit_plan_call:
            print(f"  [DEBUG] SubmitPlan Args: {str(submit_plan_call).encode('ascii', 'replace').decode('ascii')}")
            submission = submit_plan_call.get("args", {})
            trip_plan_data = submission.get("trip_plan", {})
            final_response_from_llm = submission.get("final_response", "")
            updates["trip_plan"] = trip_plan_data

            # ── OUTPUT VALIDATION: abort early if no usable results were found ──
            is_valid, sorry_msg = _validate_plan_output(request_type, trip_plan_data)
            if not is_valid:
                print(f"  [VALIDATION] No results for {request_type}: {sorry_msg}")
                step_log["response"] = sorry_msg
                updates["trip_plan"] = None  # clear so /api/execute shows instruction, not empty plan
                updates["steps"] = [step_log]
                updates["supervisor_instruction"] = sorry_msg
                updates["next_step"] = "End"
                return updates

            # Build a staged, single-option approval message instead of passing
            # the raw LLM response. AttractionsOnly gets the LLM text (no gate needed).
            approval_msg = _build_staged_approval_msg(
                request_type=request_type,
                trip_plan=trip_plan_data,
                destination=destination,
                origin_city=origin_city,
                duration_days=duration_days or 0,
                budget_limit=budget_limit or 0.0,
                budget_currency=budget_currency or "USD",
                fallback_response=final_response_from_llm,
            )
            # No approval gate for flights or hotels — present result immediately.
            # If more stages are pending (e.g. hotel after flight, attractions after hotel),
            # continue to Supervisor to handle the next stage.
            pending_stages = state.get("pending_stages") or []
            # Append closing message only on the very last stage
            final_msg = approval_msg
            if request_type in ("FlightOnly", "HotelOnly") and not pending_stages:
                final_msg = approval_msg + "\n\n---\n✈️ Enjoy your trip! Safe travels from the Tripzy team. 🌍"
            step_log["response"] = final_msg
            updates["steps"] = [step_log]
            updates["supervisor_instruction"] = final_msg
            if request_type in ("FlightOnly", "HotelOnly"):
                if pending_stages:
                    updates["next_step"] = "Supervisor"
                else:
                    updates["next_step"] = "End"
            else:
                updates["next_step"] = "Human_Approval"
            return updates

        if not tool_calls:
            # No tools called? The LLM gave a text response (rare with bind_tools)
            # Use content as supervisor instruction and route back to Supervisor
            updates["supervisor_instruction"] = (
                content_str or "Planner needs more information."
            )
            updates["next_step"] = "Supervisor"
            return updates

        # Analyze Tool Calls

        # If Search Tools are called, route to Researcher (updated to handle tool calls)
        # LOOP GUARD: Hard-cap on researcher_calls even in the normal (no-exception) path
        researcher_calls = state.get("researcher_calls", 0)
        MAX_RESEARCHER_CALLS = 4  # 2 for tool calls + 1 retry + 1 buffer
        if researcher_calls >= MAX_RESEARCHER_CALLS:
            print(
                f"  [GUARD] Max researcher calls reached ({researcher_calls}). Forcing plan submission."
            )
            # Build a minimal plan from what we know and submit it
            fallback_plan = {
                "destination": destination,
                "origin_city": origin_city,
                "dates": "To be confirmed",
                "duration_days": duration_days,
                "budget_estimate": budget_limit or 0,
                "budget_currency": state.get("budget_currency", "USD"),
                "trip_type": trip_type,
                "travelers": traveling_personas_number,
                "flights": [],
                "hotels": [],
                "itinerary": [
                    {"day": i + 1, "activity": f"Day {i+1} in {destination}", "cost": 0}
                    for i in range(duration_days or 1)
                ],
                "special_notes": "Plan generated with limited research data. Some details may be incomplete.",
            }
            updates["trip_plan"] = fallback_plan
            updates["supervisor_instruction"] = (
                "Plan Drafted (fallback - max research iterations reached)"
            )
            updates["next_step"] = "Human_Approval"
            return updates

        # DEDUP CHECK: stop if the exact same tool call (name + args) has been run >= 2 times
        import json

        last_steps = state.get("steps", [])
        # Only check steps from the CURRENT planning session (after the last Supervisor step)
        last_supervisor_idx = max(
            (i for i, s in enumerate(last_steps) if s.get("module") == "Supervisor"),
            default=-1,
        )
        current_session_steps = last_steps[last_supervisor_idx + 1:] if last_supervisor_idx >= 0 else last_steps
        researcher_steps = [s for s in current_session_steps if s.get("module") == "Researcher"]
        if researcher_steps and len(tool_calls) == 1:
            new_tool_name = tool_calls[0].get("name", "")
            new_tool_args = tool_calls[0].get("args", {})
            # Normalize args to a canonical string for exact-match comparison
            try:
                new_call_sig = json.dumps({new_tool_name: new_tool_args}, sort_keys=True)
            except Exception:
                new_call_sig = str(new_tool_name) + str(new_tool_args)
            # Count how many researcher steps already ran this exact tool+args combo
            exact_run_count = 0
            for s in researcher_steps:
                prior_prompt = s.get("prompt", "")
                # The researcher logs the call as "TOOL_CALLS: [...]" in the prompt
                if new_tool_name and new_tool_name in prior_prompt:
                    try:
                        prior_json_str = prior_prompt.replace("TOOL_CALLS:", "").strip()
                        prior_calls = json.loads(prior_json_str)
                        for pc in prior_calls:
                            try:
                                prior_sig = json.dumps({pc["name"]: pc.get("args", {})}, sort_keys=True)
                            except Exception:
                                prior_sig = str(pc.get("name")) + str(pc.get("args"))
                            if prior_sig == new_call_sig:
                                exact_run_count += 1
                    except Exception:
                        pass  # skip unparseable steps — don't count as duplicate
            if exact_run_count >= 2:
                print(
                    f"  [DEDUP GUARD] Planner repeating identical tool call '{new_tool_name}' with same args (already ran {exact_run_count}x). Forcing submit."
                )
                fallback_plan = {
                    "destination": destination,
                    "origin_city": origin_city,
                    "dates": "To be confirmed",
                    "duration_days": duration_days,
                    "budget_estimate": budget_limit or 0,
                    "budget_currency": state.get("budget_currency", "USD"),
                    "trip_type": trip_type,
                    "travelers": traveling_personas_number,
                    "flights": [],
                    "hotels": [],
                    "itinerary": [
                        {
                            "day": i + 1,
                            "activity": f"Day {i+1} in {destination}",
                            "cost": 0,
                        }
                        for i in range(duration_days or 1)
                    ],
                    "special_notes": "Plan generated with limited research data.",
                }
                updates["trip_plan"] = fallback_plan
                # Check if the last researcher step returned 0 results
                last_researcher = researcher_steps[-1] if researcher_steps else {}
                last_response = last_researcher.get("response", "")
                no_results = (
                    "0 valid" in last_response
                    or "no hotels" in last_response.lower()
                    or "no flights" in last_response.lower()
                    or last_response.strip() == ""
                )
                if no_results:
                    if "hotel" in new_tool_name:
                        user_msg = (
                            f"I couldn't find available hotels in {destination} for those dates. "
                            "This can happen due to high demand or limited inventory. "
                            "Would you like me to try different dates, a nearby city, or adjust the budget?"
                        )
                    elif "flight" in new_tool_name:
                        user_msg = (
                            f"I couldn't find available flights to {destination} for that date. "
                            "Would you like me to try flexible dates or nearby airports?"
                        )
                    else:
                        user_msg = (
                            f"I searched for results in {destination} but nothing matched. "
                            "Would you like to try different criteria?"
                        )
                else:
                    user_msg = (
                        f"I've completed the search for {destination}. "
                        "Would you like to refine the search or try different options?"
                    )
                updates["supervisor_instruction"] = user_msg
                _pending = state.get("pending_stages") or []
                updates["next_step"] = "Supervisor" if _pending else "End"
                return updates

        # Serialize tool calls for Researcher
        updates["supervisor_instruction"] = (
            f"TOOL_CALLS: {json.dumps(tool_calls, default=str)}"
        )
        updates["next_step"] = "Researcher"

        return updates

    except Exception as e:
        err_str = str(e).encode("ascii", "replace").decode("ascii")
        print(f"Planner Error: {err_str}")
        # Guard: if researcher called too many times, go to End instead of looping
        researcher_calls = state.get("researcher_calls", 0)
        # Also end immediately on encoding errors — retrying Researcher won't fix them
        is_encoding_error = isinstance(e, (UnicodeEncodeError, UnicodeDecodeError))
        if researcher_calls >= 4 or is_encoding_error:
            print(
                f"  [GUARD] Ending planner (calls={researcher_calls}, encoding_err={is_encoding_error})."
            )
            # Build a minimal plan from what we have so the user gets SOMETHING
            emergency_plan = {
                "destination": destination,
                "origin_city": origin_city,
                "dates": "To be confirmed",
                "duration_days": duration_days,
                "budget_estimate": budget_limit or 0,
                "budget_currency": state.get("budget_currency", "USD"),
                "trip_type": trip_type,
                "travelers": traveling_personas_number,
                "flights": [],
                "hotels": state.get("last_hotel_results", []),
                "itinerary": [
                    {"day": i + 1, "activity": f"Day {i+1} in {destination}", "cost": 0}
                    for i in range(duration_days or 1)
                ],
                "special_notes": "Hotels were found successfully. Full plan generation encountered a formatting issue.",
            }
            return {
                "next_step": "End",
                "trip_plan": emergency_plan,
                "supervisor_instruction": "Plan Drafted",
                "steps": [{"module": "Trip_Planner", "prompt": instruction, "response": f"Emergency plan generated after error: {err_str}"}],
            }
        return {"next_step": "Researcher", "supervisor_instruction": _classify_error(e)["user_msg"]}


# 3. CRITIQUE NODE
def critique_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: CRITIQUE ---")
    instruction = state.get("supervisor_instruction", "")
    trip_plan = state.get("trip_plan")
    duration_days = state.get("duration_days", 7)
    budget_limit = state.get("budget_limit", 0.0)
    current_revisions = state.get("revision_count", 0)

    # HARD VALIDATION 1: Check duration before calling LLM
    # Only for full "Planning" requests. Partial plans don't need strict itinerary days.
    request_type = state.get("request_type", "FlightOnly")
    # Duration and budget validations skipped - full planning is disabled
    # Only partial request types (FlightOnly, HotelOnly, AttractionsOnly) reach critique now

    # TOKEN OPTIMIZATION: Skip LLM critique for partial requests (FlightOnly, HotelOnly, AttractionsOnly)
    # Only do Python-based hard validations (budget check above already ran)
    # For these request types, auto-approve to save ~800-1200 tokens per request
    if request_type in ("FlightOnly", "HotelOnly", "AttractionsOnly"):
        print(f"  [CRITIQUE] Auto-approving {request_type} (no LLM critique needed)")
        # Don't overwrite supervisor_instruction — the planner's final_response is already set
        return {
            "next_step": "Human_Approval",
            "steps": [
                {
                    "module": "Critique",
                    "prompt": "Auto-validation",
                    "response": f"APPROVE: {request_type} auto-approved",
                }
            ],
        }

    # For any remaining request types, do a simple auto-approve
    print(f"  [CRITIQUE] Auto-approving fallback for request_type={request_type}")
    return {
        "next_step": "Human_Approval",
        "steps": [
            {
                "module": "Critique",
                "prompt": "Auto-validation",
                "response": "APPROVE: Auto-approved",
            }
        ],
    }


# 4. HUMAN APPROVAL NODE
def human_approval_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: HUMAN APPROVAL ---")
    request_type = state.get("request_type", "")
    pending_stages = state.get("pending_stages") or []
    user_query = (state.get("user_query") or "").strip().lower()

    # AttractionsOnly needs no confirmation — just present the results.
    # Legacy "approve_trip_plan" signal also auto-approves.
    if request_type == "AttractionsOnly" or user_query == "approve_trip_plan":
        if pending_stages:
            print(f"  [HUMAN APPROVAL] Auto-approve AttractionsOnly. Next stage: {pending_stages[0]}")
            return {"next_step": "Supervisor"}
        return {"next_step": "End"}

    # ---------- YES / NO / UNCLEAR detection ----------
    _YES = {
        "yes", "ok", "sure", "approved", "approve", "book", "great", "perfect",
        "go ahead", "proceed", "confirm", "confirmed", "let's do it", "looks good",
        "fine", "yep", "yeah", "yup", "absolutely", "sounds good", "do it",
        "book it", "that works", "love it", "awesome", "deal",
    }
    _NO = {
        "no", "nope", "cancel", "different", "change", "cheaper", "reject",
        "not interested", "try again", "dont", "other", "another",
        "not that", "not sure", "not what", "too expensive", "skip",
    }

    query_words = set(user_query.replace("'", "").split())
    _YES_PHRASES = ("yes", "ok", "sure", "book it", "go ahead", "looks good", "perfect",
                    "great", "sounds good", "yep", "yeah", "proceed", "let's do it")
    _NO_PHRASES  = ("no ", " no", "nope", "cancel", "different option", "cheaper",
                    "not that", "try again", "something else", "other option")

    is_yes = bool(query_words & _YES) or any(p in user_query for p in _YES_PHRASES)
    is_no  = bool(query_words & _NO)  or any(p in user_query for p in _NO_PHRASES)

    # Edge: if both match (e.g. "no thanks, looks good") prefer YES so the user isn't
    # bounced unexpectedly — but only when is_yes has a strong positive signal.
    if is_yes and is_no:
        is_no = False  # lean toward YES to avoid false rejection

    if is_yes:
        print(f"  [HUMAN APPROVAL] User accepted. pending_stages={pending_stages}")
        if request_type == "FlightOnly":
            confirm_msg = "✅ Flight confirmed! Your booking details have been saved."
        elif request_type == "HotelOnly":
            confirm_msg = "✅ Hotel confirmed! Your stay is all set."
        else:
            confirm_msg = "✅ Confirmed! Your choice has been saved."
        if pending_stages:
            return {
                "next_step": "Supervisor",
                "supervisor_instruction": confirm_msg,
                "steps": [{"module": "Human_Approval", "prompt": user_query, "response": confirm_msg}],
            }
        return {
            "next_step": "End",
            "supervisor_instruction": confirm_msg,
            "steps": [{"module": "Human_Approval", "prompt": user_query, "response": confirm_msg}],
        }

    if is_no:
        rejection_msg = (
            "No problem! What would you like to change — "
            "the price range, travel dates, airline preference, or something else?"
        )
        print("  [HUMAN APPROVAL] User rejected.")
        return {
            "next_step": "End",
            "supervisor_instruction": rejection_msg,
            "steps": [{"module": "Human_Approval", "prompt": user_query, "response": rejection_msg}],
        }

    # Unclear / no keywords matched
    clarify_msg = (
        "I didn't quite catch that — would you like to go ahead with this option? "
        "Please reply **yes** to confirm or **no** to see alternatives."
    )
    print("  [HUMAN APPROVAL] Unclear response — asking to clarify.")
    return {
        "next_step": "End",
        "supervisor_instruction": clarify_msg,
        "steps": [{"module": "Human_Approval", "prompt": user_query, "response": clarify_msg}],
    }


# 4. RESEARCHER NODE (Enhanced for Tools)
def researcher_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: RESEARCHER ---")
    # Increment researcher_calls counter (loop guard)
    researcher_calls = (state.get("researcher_calls") or 0) + 1
    print(f"  [RESEARCHER] Call #{researcher_calls}")
    instruction = state.get("supervisor_instruction", "")

    results = ""
    tool_used = "Web Search"
    step_logs = []

    # Check for NATIVE TOOL CALLS passed from Planner
    if instruction.startswith("TOOL_CALLS:"):
        import json

        _current_tool = ""  # tracks the tool being executed for error reporting
        try:
            json_str = instruction.replace("TOOL_CALLS:", "").strip()
            tool_calls = json.loads(json_str)

            tool_map = {
                "search_flights_tool": search_flights_tool,
                "search_hotels_tool": search_hotels_tool,
                "suggest_destination_tool": suggest_destination_tool,
                "suggest_attractions_tool": suggest_attractions_tool,
                "create_plan_tool": create_plan_tool,
                "search_activities_tool": search_activities_tool,
                "flight_price_analysis_tool": flight_price_analysis_tool,
                "flight_status_tool": flight_status_tool,
                "airport_search_tool": airport_search_tool,
                "airline_lookup_tool": airline_lookup_tool,
                "travel_recommendations_tool": travel_recommendations_tool,
                # New Amadeus tools (Phase 26) - previously missing from Researcher
                "resolve_airport_code_tool": resolve_airport_code_tool,
                "get_airline_info_tool": get_airline_info_tool,
                "search_tours_activities_tool": search_tours_activities_tool,
                "search_points_of_interest_tool": search_points_of_interest_tool,
                "cheapest_flights_tool": cheapest_flights_tool,
                "hotel_ratings_tool": hotel_ratings_tool,
                "search_flights_with_kiwi_tool": search_flights_with_kiwi_tool,
            }

            for tc in tool_calls:
                t_name = tc["name"]
                _current_tool = t_name
                t_args = tc["args"]

                if t_name == "create_plan_tool" and isinstance(t_args, dict):
                    # Auto-fill plan inputs from cached state so planner can compose without re-calling tools.
                    if not t_args.get("flights_data") and state.get("last_flight_results"):
                        t_args["flights_data"] = json.dumps(state.get("last_flight_results", []), default=str)
                    if not t_args.get("hotels_data") and state.get("last_hotel_results"):
                        t_args["hotels_data"] = json.dumps(state.get("last_hotel_results", []), default=str)
                    if not t_args.get("attractions_data") and state.get("last_attraction_results"):
                        t_args["attractions_data"] = json.dumps(state.get("last_attraction_results", []), default=str)

                if t_name in tool_map:
                    print(f"  [Executing Tool] {t_name} with {t_args}")
                    tool_res = tool_map[t_name].invoke(t_args)
                    # Create individual log for this tool
                    step_log = {
                        "module": "Researcher",
                        "prompt": f"Executing {t_name}: {t_args}",
                        "response": str(tool_res)[:1000],
                    }
                    step_logs.append(step_log)  # Append to list

                    results += f"Tool Result ({t_name}):\n{tool_res}\n"
                    tool_used = t_name  # Keep track of last used

                    # Cache hotel/flight results so the emergency planner path can use them
                    try:
                        parsed_res = json.loads(tool_res) if isinstance(tool_res, str) else tool_res
                        if t_name == "search_hotels_tool" and isinstance(parsed_res, list) and parsed_res:
                            # Normalize to the HotelInfo-compatible format expected by main.py
                            cached_hotels = []
                            for h in parsed_res[:5]:
                                cached_hotels.append({
                                    "name": h.get("name", ""),
                                    "rating": str(h.get("rating", "")),
                                    "price": h.get("price_per_night", ""),
                                    "location": h.get("location", {}).get("address", "") if isinstance(h.get("location"), dict) else str(h.get("location", "")),
                                    "amenities": h.get("amenities", []),
                                    "booking_link": h.get("booking_link", "#"),
                                    "check_in": h.get("check_in", ""),
                                    "check_out": h.get("check_out", ""),
                                    "total_price": h.get("total_price", ""),
                                    "price_per_night": h.get("price_per_night", ""),
                                })
                            step_logs.append({"_cache_hotels": cached_hotels})  # Marker
                            print(f"  [Researcher] Cached {len(cached_hotels)} hotels to state")
                        elif t_name in ("search_flights_tool", "search_flights_with_kiwi_tool", "cheapest_flights_tool"):
                            if isinstance(parsed_res, list) and parsed_res:
                                step_logs.append({"_cache_flights": parsed_res[:5]})
                        elif t_name == "suggest_attractions_tool":
                            cached_attractions = []
                            if isinstance(parsed_res, list) and parsed_res:
                                cached_attractions = parsed_res[:10]
                            elif isinstance(parsed_res, dict) and isinstance(parsed_res.get("attractions"), list):
                                cached_attractions = parsed_res.get("attractions", [])[:10]
                            if cached_attractions:
                                step_logs.append({"_cache_attractions": cached_attractions})
                                print(f"  [Researcher] Cached {len(cached_attractions)} attractions to state")
                    except Exception as cache_err:
                        print(f"  [Researcher] Cache warning: {cache_err}")
                else:
                    results += f"Error: Unknown tool {t_name}\n"

        except Exception as e:
            _err = _classify_error(e, service_name=_current_tool)
            error_log = {
                "module": "Researcher",
                "prompt": "Tool Execution",
                "response": _err["user_msg"],
                "error_code": _err["code"],
            }
            print(f"  [Error] Tool Execution Failed ({_err['code']}): {e}")
            step_logs.append(error_log)
            results += f"Tool Error: {_err['user_msg']}\n"

    # Check for Legacy Structured calls (Backwards compatibility if needed, or if Supervisor uses it)
    elif "FLIGHTS:" in instruction or "HOTELS:" in instruction:
        # ... (Previous legacy logic can remain or be removed. Keeping for safety for now)
        if "FLIGHTS:" in instruction:
            import json

            try:
                # Extract JSON part
                start = instruction.find("FLIGHTS:") + len("FLIGHTS:")
                end = (
                    instruction.find("HOTELS:")
                    if "HOTELS:" in instruction
                    else len(instruction)
                )
                flight_params_str = instruction[start:end].strip()
                flight_params = json.loads(flight_params_str)
                tool_used = "Flight Search (Legacy)"
                flight_res = search_flights_tool.invoke(
                    {
                        "origin": flight_params.get("origin", ""),
                        "destination": flight_params.get("dest", ""),
                        "departure_date": flight_params.get("date", ""),
                    }
                )
                results += f"Flight Options:\n{flight_res}\n"

                step_logs.append(
                    {
                        "module": "Researcher",
                        "prompt": f"Legacy Flight Search: {flight_params}",
                        "response": str(flight_res)[:1000],
                    }
                )

            except Exception as e:
                results += f"Flight search error: {str(e)}\n"

        if "HOTELS:" in instruction:
            import json

            try:
                start = instruction.find("HOTELS:") + len("HOTELS:")
                hotel_params_str = instruction[start:].strip()
                hotel_params = json.loads(hotel_params_str)
                tool_used = "Hotel Search (Legacy)"
                hotel_res = search_hotels_tool.invoke(
                    {
                        "city": hotel_params.get("city", ""),
                        "check_in": hotel_params.get("in", ""),
                        "check_out": hotel_params.get("out", ""),
                        "budget": hotel_params.get("budget", "medium"),
                        "adults": hotel_params.get("adults", 1),  # Fix: was missing
                        "sort_by": hotel_params.get("sort_by", "price"),
                    }
                )
                results += f"Hotel Options:\n{hotel_res}\n"

                step_logs.append(
                    {
                        "module": "Researcher",
                        "prompt": f"Legacy Hotel Search: {hotel_params}",
                        "response": str(hotel_res)[:1000],
                    }
                )

            except Exception as e:
                results += f"Hotel search error: {str(e)}\n"

    else:
        # Default Web Search
        # Execute Tools
        # For simple text searches
        if (
            instruction and "Suggestion" not in instruction
        ):  # Don't search for "Plan Drafted"
            results = web_search_tool.invoke(instruction)
            step_logs.append(
                {
                    "module": "Researcher",
                    "prompt": f"Web Search: {instruction}",
                    "response": str(results)[:1000],
                }
            )

    # If steps were not added (fallback), add a generic one
    if not step_logs:
        step_logs.append(
            {
                "module": "Researcher",
                "prompt": f"Executing {tool_used}: {instruction[:50]}...",
                "response": results[:1000],
            }
        )

    # Extract cached hotel/flight data from step_logs markers
    cached_hotels = None
    cached_flights = None
    cached_attractions = None
    clean_step_logs = []
    for sl in step_logs:
        if "_cache_hotels" in sl:
            cached_hotels = sl["_cache_hotels"]
        elif "_cache_flights" in sl:
            cached_flights = sl["_cache_flights"]
        elif "_cache_attractions" in sl:
            cached_attractions = sl["_cache_attractions"]
        else:
            clean_step_logs.append(sl)
    step_logs = clean_step_logs

    # Decide where to route after research:
    # Dynamically route back to whoever called us (Supervisor or Trip_Planner)
    steps = state.get("steps", [])
    last_caller = "Supervisor"
    if steps:
        # Find the most recent step that was either Planner or Supervisor
        for s in reversed(steps):
            if s.get("module") in ["Supervisor", "Trip_Planner"]:
                last_caller = s["module"]
                break

    # Ensure standard names
    next_node = (
        "Trip_Planner" if last_caller == "Trip_Planner" else "Supervisor"
    )

    # Quick fix: if we somehow got here with 0 duration and no destination,
    # and we are returning to Supervisor, let it process the results naturally.
    print(f"  [RESEARCHER] Routing back to: {next_node}")

    result_payload = {
        "steps": step_logs,
        "supervisor_instruction": results,  # Return results for Planner/Supervisor to see
        "next_step": next_node,
        "researcher_calls": researcher_calls,
    }
    if cached_hotels is not None:
        result_payload["last_hotel_results"] = cached_hotels
    if cached_flights is not None:
        result_payload["last_flight_results"] = cached_flights
    if cached_attractions is not None:
        result_payload["last_attraction_results"] = cached_attractions
    return result_payload


# 5. ATTRACTIONS STUB NODE
def attractions_node(state: AgentState) -> Dict[str, Any]:
    """
    RAG-first attractions node.
    1. Build query from attractions_query + destination.
    2. Call suggest_attractions_tool → top 3 results.
    3. Call LLMOD to rewrite as 3 friendly recommendations.
    4. Return formatted text → End.
    """
    print("--- NODE: ATTRACTIONS ---")
    destination = (state.get("destination") or "").strip() or "your destination"
    attractions_query = (state.get("attractions_query") or state.get("user_query") or "").strip()
    user_query = state.get("user_query", "")

    # ── Step 1: RAG retrieval ──────────────────────────────────────────────────
    interests = [attractions_query] if attractions_query else None
    raw_rag = ""
    try:
        raw_rag = suggest_attractions_tool.invoke({
            "destination": destination,
            "interests": interests,
            "trip_type": state.get("trip_type") or "",
        })
        print(f"  [Attractions] RAG returned {len(raw_rag)} chars")
    except Exception as e:
        print(f"  [Attractions] RAG failed: {e}")

    # ── Step 2: Parse top 3 results ────────────────────────────────────────────
    top_items: list = []
    try:
        payload = json.loads(raw_rag)
        rows = payload if isinstance(payload, list) else payload.get("results", [])
        for item in rows:
            if isinstance(item, dict):
                top_items.append(item)
            if len(top_items) >= 3:
                break
    except Exception:
        pass

    raw_text = raw_rag or "No results found."
    if top_items:
        lines = []
        for i, item in enumerate(top_items, 1):
            name = item.get("name", f"Option {i}")
            desc = (item.get("description") or item.get("category") or "")[:120]
            lines.append(f"{i}. {name} — {desc}")
        raw_text = "\n".join(lines)

    # ── Step 3: LLMOD formatting pass ─────────────────────────────────────────
    format_prompt = (
        f"The user is looking for: '{attractions_query}' in {destination}.\n"
        f"Here are up to 3 results from our database:\n{raw_text}\n\n"
        "Rewrite these as 3 clear, friendly recommendations. "
        "For each: write the name in bold, then a single sentence describing why it matches the request. "
        "Do not add extra headings or preamble."
    )
    formatted_response = ""
    try:
        from langchain_core.messages import HumanMessage as HMsg
        llm_resp = llm.invoke([HMsg(content=format_prompt)])
        formatted_response = llm_resp.content if hasattr(llm_resp, "content") else str(llm_resp)
        print(f"  [Attractions] LLMOD formatted {len(formatted_response)} chars")
    except Exception as e:
        print(f"  [Attractions] LLMOD formatting failed: {e}")
        formatted_response = f"Here are some recommendations in {destination}:\n{raw_text}"

    if not formatted_response.strip():
        formatted_response = (
            f"I found some options for '{attractions_query}' in {destination}:\n{raw_text}"
        )

    # ── Step 4: Return ─────────────────────────────────────────────────────────
    from langchain_core.messages import AIMessage
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=formatted_response))

    closing = "\n\n---\n✈️ Enjoy your trip! Safe travels from the Tripzy team. 🌍"
    final_attractions_response = formatted_response + closing

    step_log = {
        "module": "Attractions",
        "prompt": user_query,
        "response": final_attractions_response,
    }

    return {
        "messages": messages,
        "supervisor_instruction": final_attractions_response,
        "next_step": "End",
        "steps": [step_log],
    }


# --- GRAPH ---
workflow = StateGraph(AgentState)

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Trip_Planner", planner_node)
workflow.add_node("Researcher", researcher_node)
workflow.add_node("Attractions", attractions_node)
workflow.add_node("Critique", critique_node)
workflow.add_node("Human_Approval", human_approval_node)

workflow.add_edge(START, "Supervisor")


# Supervisor Routing
def route_supervisor(state: AgentState):
    return state.get("next_step", "End")


workflow.add_conditional_edges(
    "Supervisor",
    route_supervisor,
    {"Trip_Planner": "Trip_Planner", "Researcher": "Researcher", "Attractions": "Attractions", "End": END},
)

# Attractions returns to user
workflow.add_edge("Attractions", END)


# Planner Conditional Edge
def route_planner(state: AgentState):
    return state.get("next_step", "Supervisor")


workflow.add_conditional_edges(
    "Trip_Planner",
    route_planner,
    {
        "Researcher": "Researcher",
        "Critique": "Critique",
        "Human_Approval": "Human_Approval",
        "Supervisor": "Supervisor",
        "End": END,
    },
)


# Critique Logic
def route_critique(state: AgentState):
    return state.get("next_step", "Supervisor")


workflow.add_conditional_edges(
    "Critique",
    route_critique,
    {
        "Trip_Planner": "Trip_Planner",
        "Human_Approval": "Human_Approval",
        "Supervisor": "Supervisor",
    },
)


# Human Approval Logic
def route_human_approval(state: AgentState):
    # Use next_step set by human_approval_node (partial plans → End, full plans → Supervisor)
    return state.get("next_step", "Supervisor")


workflow.add_conditional_edges(
    "Human_Approval",
    route_human_approval,
    {"End": END, "Supervisor": "Supervisor"},
)


# Researcher routes dynamically (to Trip_Planner or Supervisor depending on caller)
def route_researcher(state: AgentState):
    return state.get("next_step", "Supervisor")


workflow.add_conditional_edges(
    "Researcher",
    route_researcher,
    {"Trip_Planner": "Trip_Planner", "Supervisor": "Supervisor"},
)

memory = MemorySaver()

graph = workflow.compile(checkpointer=memory, interrupt_before=["Human_Approval"])
