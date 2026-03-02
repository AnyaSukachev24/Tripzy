from typing import Any, Dict, Literal, List
from langgraph.checkpoint.memory import MemorySaver
from app.state import AgentState, Amenity, TripPlan, UserProfile
from langgraph.graph import StateGraph, START, END


# ... imports ...


from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
import os
import json
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prompts
from app.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT
from app.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT, get_planner_prompt
from app.prompts.critique_prompt import CRITIQUE_SYSTEM_PROMPT

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
    get_user_profile,
)


# --- Retry Configuration ---
def retry_decorator(func):
    """
    Decorator for retrying LLM calls with exponential backoff.

    Retry strategy:
    - Max 3 attempts
    - Exponential backoff: 2^x * 1 second (1s, 2s, 4s)
    - Only retry on specific exceptions (API errors, timeouts)
    """
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),  # Retry on any exception
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
        Exception: After 3 failed attempts
    """
    logger.info(f"Invoking LLM with input keys: {list(input_data.keys())}")
    try:
        result = chain.invoke(input_data)
        logger.info("LLM invocation successful")
        return result
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        raise


# LLM Selection: Azure OpenAI primary, Gemini fallback
import os
if os.getenv("AZURE_OPENAI_API_KEY"):
    logger.info("[LLM] Using Azure OpenAI: %s", os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"))
    llm = AzureChatOpenAI(
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
        temperature=0,
    )
else:
    logger.info("[LLM] Falling back to Google Gemini")
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)


# --- Output Models ---
class SupervisorOutput(BaseModel):
    next_step: Literal["Trip_Planner", "Researcher", "End"] = Field(
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
    request_type: Literal["Planning", "Discovery", "FlightOnly", "HotelOnly", "AttractionsOnly"] = Field(
        description="Intent: 'Planning' for full trips, 'Discovery' for vague/suggestion requests, 'FlightOnly'/'HotelOnly'/'AttractionsOnly' for partial plans.",
        default="Planning",
    )


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
    conversation_history = ""
    prior_steps = state.get("steps", [])
    # Extract up to last 6 meaningful exchange steps for the LLM context
    relevant_steps = [s for s in prior_steps if s.get("module") in ["Supervisor", "Planner", "Researcher"] and s.get("response")]
    if relevant_steps:
        history_lines = []
        for s in relevant_steps[-6:]:
            mod = s.get("module", "")
            prompt = s.get("prompt", "")[:200]
            resp = s.get("response", "")[:300]
            history_lines.append(f"[{mod}] User: {prompt} → Response: {resp}")
        conversation_history = "\nCONVERSATION HISTORY (Recent Turns):\n" + "\n".join(history_lines)

    # --- Phase 29: User Profile Retrieval ---
    user_profile_update = {}
    current_profile = state.get("user_profile")
    
    if not current_profile:
        try:
            # TODO: In production, get user_id from context/session
            # For now, we use the test profile we inspected earlier
            test_user_id = "test@example.com" 
            # Note: The tool handles ID sanitization/lookup
            profile_dict = get_user_profile.invoke({"user_id": test_user_id})
            if profile_dict:
                current_profile = UserProfile(**profile_dict)
                user_profile_update = {"user_profile": current_profile}
                print(f"  [Supervisor] Loaded User Profile: {current_profile.travel_style}, {current_profile.dietary_needs}")
        except Exception as e:
            print(f"  [Supervisor] Failed to load user profile: {e}")

    # Prepare Profile String for Context
    profile_context = "Unknown"
    if current_profile:
        profile_context = (
            f"Style: {current_profile.travel_style or 'Any'}, "
            f"Diet: {', '.join(current_profile.dietary_needs)}, "
            f"Interests: {', '.join(current_profile.interests)}, "
            f"Accessibility: {', '.join(current_profile.accessibility_needs)}"
        )

    # Helper function to persist user profile on ALL return paths
    def _apply_profile_updates(updates: dict, extracted_prefs: list = None, extracted_trip_type: str = None) -> dict:
        """Helper to merge profile updates before returning state."""
        if user_profile_update:
            updates.update(user_profile_update)
            
        if current_profile:
            new_prefs_added = False
            merged_prefs = set(current_profile.interests or [])
            if extracted_prefs:
                for p in extracted_prefs:
                    if p.lower() not in [ext.lower() for ext in merged_prefs]:
                        merged_prefs.add(p)
                        new_prefs_added = True
            
            merged_diet = set(current_profile.dietary_needs or [])
            new_style = current_profile.travel_style
            if extracted_trip_type and not current_profile.travel_style:
                new_style = extracted_trip_type
                new_prefs_added = True
                
            if new_prefs_added:
                try:
                    from app.tools import create_user_profile_tool
                    user_email = getattr(current_profile, 'email', None) or current_profile.user_id
                    user_name = getattr(current_profile, 'name', None) or current_profile.user_id
                    create_user_profile_tool.invoke({
                        "name": user_name,
                        "email": user_email,
                        "preferences": list(merged_prefs),
                        "dietary_needs": list(merged_diet),
                        "accessibility_needs": list(current_profile.accessibility_needs or []),
                        "travel_style": new_style or ""
                    })
                    print(f"  [Supervisor] Background profile update triggered. New prefs: {list(merged_prefs - set(current_profile.interests or []))}")

                    current_profile.interests = list(merged_prefs)
                    current_profile.travel_style = new_style
                    updates["user_profile"] = current_profile
                except Exception as e:
                    print(f"  [Supervisor] Failed to update profile in background: {e}")
        return updates

    # Simple Router Logic (Optimization: Don't call LLM for simple greetings)
    # Strip punctuation/whitespace and check case-insensitively
    import re
    cleaned_query = re.sub(r'[^\w\s]', '', user_query.strip()).lower().strip()
    if cleaned_query in ["hi", "hello", "hey", "test", "yo", "sup"]:
        return _apply_profile_updates({
            "next_step": "End",
            "supervisor_instruction": "Hello! I'm your AI Travel Agent. Where would you like to go today? I can suggest destinations, plan full trips, search for flights and hotels!",
            "steps": [
                {
                    "module": "Supervisor",
                    "prompt": user_query,
                    "response": "Greeted user and asked for travel intent.",
                }
            ],
        })

    # Format context for the LLM so it knows what has already been provided
    # INJECT RESEARCH HISTORY: Get recent steps from Researcher to prevent loops
    steps = state.get("steps", [])
    research_steps = [s for s in steps if s.get("module") == "Researcher"]
    research_history = ""
    if research_steps:
        research_history = "\nRECENT RESEARCH RESULTS:\n" + "\n".join(
            [f"- {s.get('response')[:500]}..." for s in research_steps[-3:]]
        )

    current_context = (
        f"CURRENT STATE:\n"
        f"- User Profile: {profile_context}\n"
        f"- Destination: {state.get('destination') or 'Not Set'}\n"
        f"- Duration: {state.get('duration_days') or 0} days\n"
        f"- Budget: {state.get('budget_limit') or 0} {state.get('budget_currency') or 'USD'}\n"
        f"- Trip Type: {state.get('trip_type') or 'Not Set'}\n"
        f"- Origin: {state.get('origin_city') or 'Not Set'}\n"
        f"- Travelers: {state.get('traveling_personas_number') or 1}\n"
        f"- Amenities: {state.get('amenities') or []}\n"
        f"- Request Type: {state.get('request_type') or 'Not Set'}\n"
        f"{research_history}"
        f"{conversation_history}"
    )

    # Construct Messages for ChatPromptTemplate
    messages = [
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        ("human", "Context:\n{context}\n\nUser Input: {query}"),
    ]

    # DYNAMIC SYSTEM MESSAGE: Prevent loops if research exists
    if research_steps:
        loop_prevention_msg = (
            "CRITICAL SYSTEM INSTRUCTION:\n"
            "You have access to RECENT RESEARCH RESULTS in the context above.\n"
            "Do NOT route to 'Researcher' again for the same query.\n"
            "If the research results are sufficient to answer the user, route to 'End' and summarize the findings in the 'instruction' field."
        )
    prompt = ChatPromptTemplate.from_messages(messages)

    chain = prompt | llm.with_structured_output(SupervisorOutput)

    try:  # Pass the formatted context to the prompt
        # We use the original user_query, not a modified one
        result = safe_llm_invoke(
            chain, {"query": user_query, "context": current_context}
        )
        
        print(f"SUPERVISOR RESULT: {result}")

        # HARD OVERRIDE: Prevent infinite loops if Researcher just suggested destinations
        if research_steps:
            last_research = research_steps[-1].get("prompt", "")
            last_research_response = research_steps[-1].get("response", "")
            
            if "suggest_destination_tool" in last_research and result.next_step in ("Researcher", "End"):
                print("  [GUARD OVERRIDE] Researcher just suggested destinations. Formatting response for user.")
                
                # Build a beautiful formatted response from the raw JSON
                def _format_destination_suggestions(raw_json_str: str, trip_type: str = "", preferences: list = None) -> str:
                    """Format raw destination JSON into beautiful markdown."""
                    preferences = preferences or []
                    try:
                        raw = json.loads(raw_json_str)
                    except Exception:
                        return raw_json_str

                    # Trip type emoji mapping
                    EMOJI_MAP = {
                        "honeymoon": "💑", "romantic": "💑",
                        "beach": "🏖️", "tropical": "🏖️",
                        "adventure": "🧗", "hiking": "🏔️", "mountains": "🏔️",
                        "cultural": "🏛️", "history": "🏛️", "temples": "🏯",
                        "family": "👨‍👩‍👧‍👦", "kids": "👨‍👩‍👧‍👦",
                        "luxury": "✨", "premium": "✨",
                        "budget": "💰", "backpacker": "🎒",
                        "business": "💼",
                        "food": "🍜", "gastronomy": "🍽️",
                        "nature": "🌿", "wildlife": "🦁",
                        "ski": "⛷️", "snow": "❄️",
                    }
                    
                    icon = "✈️"
                    pref_lower = (trip_type + " " + " ".join(preferences)).lower()
                    for kw, em in EMOJI_MAP.items():
                        if kw in pref_lower:
                            icon = em
                            break

                    lines = [f"## {icon} Here are some destination suggestions for you:\n"]
                    
                    shown = []
                    if isinstance(raw, list):
                        items = raw
                    elif isinstance(raw, dict):
                        items = raw.get("suggestions", [raw])
                    else:
                        items = []

                    for item in items[:5]:
                        name = item.get("destination", item.get("title", "Unknown"))
                        # Deduplicate
                        if name in shown:
                            continue
                        shown.append(name)
                        
                        # Clean up summary
                        summary = item.get("summary", item.get("description", ""))
                        # Strip wikivoyage section headers
                        summary = summary.replace("==", "").replace("===", "")
                        # Take first 2 sentences
                        sentences = [s.strip() for s in summary.split(".") if len(s.strip()) > 20]
                        blurb = ". ".join(sentences[:2]).strip()
                        if blurb and not blurb.endswith("."):
                            blurb += "."
                        
                        score = item.get("score", 0)
                        source = item.get("source", "")
                        
                        lines.append(f"### 📍 {name}")
                        if blurb:
                            lines.append(f"{blurb}")
                        if source:
                            lines.append(f"*Source: {source}*")
                        lines.append("")

                    if not shown:
                        return "I couldn't find specific destinations matching your criteria. Could you tell me more about what you're looking for?"
                    
                    # Contextual closing question
                    if "honeymoon" in pref_lower or "romantic" in pref_lower:
                        q = "Which of these romantic destinations appeals to you most? Or would you like me to suggest something different? 💕"
                    elif "adventure" in pref_lower or "hiking" in pref_lower:
                        q = "Which of these adventure destinations sounds exciting? I can also suggest more specific activities! 🏔️"
                    elif "beach" in pref_lower or "tropical" in pref_lower:
                        q = "Which beach destination catches your eye? I can also adjust based on your travel dates! 🌊"
                    elif "cultural" in pref_lower or "history" in pref_lower:
                        q = "Which of these cultural destinations interests you? I can also recommend specific museums and historical sites! 🏛️"
                    else:
                        q = "Which of these destinations interests you? Or would you like suggestions with different criteria?"
                    
                    lines.append(f"---\n{q}")
                    return "\n".join(lines)

                friendly_output = _format_destination_suggestions(
                    last_research_response,
                    trip_type=result.trip_type or state.get("trip_type", ""),
                    preferences=result.preferences or state.get("preferences", [])
                )

                
                return {
                    "next_step": "End",
                    "supervisor_instruction": friendly_output,
                    "destination": result.destination or state.get("destination"),
                    "duration_days": result.duration_days or state.get("duration_days"),
                    "budget_limit": result.budget_limit or state.get("budget_limit"),
                    "budget_currency": result.budget_currency or state.get("budget_currency", "USD"),
                    "trip_type": result.trip_type or state.get("trip_type"),
                    "origin_city": result.origin_city or state.get("origin_city"),
                    "traveling_personas_number": result.traveling_personas_number or state.get("traveling_personas_number", 1),
                    "amenities": result.amenities,
                    "preferences": result.preferences,
                    "request_type": result.request_type,
                    "steps": [
                        {
                            "module": "Supervisor",
                            "prompt": user_query,
                            "response": friendly_output,  # Store the formatted output here so main.py finds it
                        }

                    ],
                }

        step_log = {
            "module": "Supervisor",
            "prompt": user_query,
            "response": f"Routing to {result.next_step}: {result.reasoning}",
        }

        # HANDLE DISCOVERY (Vague Requests)
        if result.request_type == "Discovery":
            print(f"  [DISCOVERY MODE] Preferences: {result.preferences}")

            # If we have a Discovery request (even with empty preferences) and no destination, route to Researcher for suggestions
            # ONLY if we haven't already done research (to avoid loops)
            if not result.destination and not research_steps:
                import json
                
                
                # Budget tier selection - priority order:
                # 1. Explicit trip_type from the user ("budget trip" -> budget)
                # 2. Budget limit amount from the query
                # 3. User profile travel style
                if result.trip_type and result.trip_type.lower() in ["budget", "backpacker", "cheap"]:
                    budget_tier = "budget"
                elif result.trip_type and result.trip_type.lower() in ["luxury", "premium", "high-end"]:
                    budget_tier = "luxury"
                elif result.budget_limit > 0:
                    if result.budget_limit < 800:
                        budget_tier = "budget"
                    elif result.budget_limit > 3000:
                        budget_tier = "luxury"
                    else:
                        budget_tier = "medium"
                elif current_profile and current_profile.travel_style:
                    style = current_profile.travel_style.lower()
                    if "budget" in style or "cheap" in style or "backpacker" in style:
                        budget_tier = "budget"
                    elif "luxury" in style or "premium" in style:
                        budget_tier = "luxury"
                    else:
                        budget_tier = "medium"
                else:
                    budget_tier = "medium"
                
                tool_args = {
                    "preferences": ", ".join(result.preferences) if result.preferences else "travel options",
                    "budget_tier": budget_tier,
                    "trip_type": result.trip_type or "",
                    "duration_days": result.duration_days or 0,
                    "user_profile": profile_context if current_profile else None
                }
                
                tool_calls = [{"name": "suggest_destination_tool", "args": tool_args}]
                search_query = f"TOOL_CALLS: {json.dumps(tool_calls)}"

                print(f"  [DISCOVERY] Routing to Researcher: {search_query}")
                return {
                    "messages": messages,
                    "next_step": "Researcher",
                    "supervisor_instruction": search_query,
                    "destination": result.destination or state.get("destination"),
                    "duration_days": result.duration_days or state.get("duration_days"),
                    "budget_limit": result.budget_limit or state.get("budget_limit"),
                    "budget_currency": result.budget_currency
                    or state.get("budget_currency", "USD"),
                    "trip_type": result.trip_type or state.get("trip_type"),
                    "origin_city": result.origin_city or state.get("origin_city"),
                    "traveling_personas_number": result.traveling_personas_number
                    or state.get("traveling_personas_number", 1),
                    "amenities": result.amenities,  # additive
                    "preferences": result.preferences,  # additive
                    "request_type": result.request_type,
                    "steps": [
                        {
                            "module": "Supervisor",
                            "prompt": user_query,
                            "response": "Routing to Researcher for destination suggestions.",
                        }
                    ],
                }

        # EDGE CASE VALIDATION - Check for impossible/problematic requests
        from app.edge_case_validator import process_edge_cases

        # Only enforce strict planning constraints (duration + budget required) for full Planning requests.
        # FlightOnly, HotelOnly, AttractionsOnly, Discovery don't need duration.
        PARTIAL_REQUEST_TYPES = {"FlightOnly", "HotelOnly", "AttractionsOnly", "Discovery", "Greeting"}
        request_type_for_validation = result.request_type or ""
        is_planning = (result.next_step == "Trip_Planner" and
                       request_type_for_validation not in PARTIAL_REQUEST_TYPES)

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
            return _apply_profile_updates({
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
            }, extracted_prefs=result.preferences, extracted_trip_type=result.trip_type)

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
            req_type = result.request_type or "Planning"
            
            # --- MANUAL OVERRIDE FOR ATTRACTIONS ONLY ---
            # LLMs struggle to differentiate "Planning with known destination" vs "AttractionsOnly".
            # If user explicitly says they have booked/flights/hotel, force AttractionsOnly.
            user_query_lower = state.get("user_query", "").lower()
            if "already booked" in user_query_lower or "have flights" in user_query_lower or "have hotel" in user_query_lower:
                print("  [OVERRIDE] Detected 'already booked' intent -> Forcing AttractionsOnly")
                req_type = "AttractionsOnly"
                # Also update the result object so it propagates correctly
                result.request_type = "AttractionsOnly"

            # Destination is always required
            if not current_destination:
                missing_required.append("destination")

            # Duration: Required for Planning. Optional for others.
            if req_type == "Planning":
                if not current_duration or current_duration == 0:
                    missing_required.append("duration")
            
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
                return _apply_profile_updates({
                    "messages": messages,
                    "next_step": "End",
                    "supervisor_instruction": clarifying_question,
                    "destination": result.destination or current_destination,
                    "duration_days": result.duration_days or current_duration,
                    "origin_city": result.origin_city or current_origin,
                    # Persist other fields too so they aren't lost if extracted in this turn
                    "budget_limit": result.budget_limit or state.get("budget_limit"),
                    "budget_currency": result.budget_currency
                    or state.get("budget_currency", "USD"),
                    "trip_type": result.trip_type or state.get("trip_type"),
                    "preferences": result.preferences,
                    "traveling_personas_number": result.traveling_personas_number
                    or state.get("traveling_personas_number", 1),
                    "amenities": result.amenities,
                    "request_type": req_type, # Ensure this is persisted!
                    "steps": [
                        {
                            "module": "Supervisor",
                            "prompt": user_query,
                            "response": f"Need more information: {clarifying_question}",
                        }
                    ],
                }, extracted_prefs=result.preferences, extracted_trip_type=result.trip_type)
        else:
            print(
                f"  [MULTI-TURN] All required info present. Routing to {result.next_step}."
            )
        updates = {
            "messages": messages,
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
            "steps": [step_log],
        }
        return _apply_profile_updates(updates, extracted_prefs=result.preferences, extracted_trip_type=result.trip_type)
    except Exception as e:
        print(f"  Supervisor Error: {str(e)}")
        error_msg = f"System Error: {str(e)}"
        return {
            "next_step": "End",
            "supervisor_instruction": error_msg,
            "steps": [{"module": "Supervisor", "error": str(e), "response": error_msg}],
        }


# ... (Previous code remains the same up to Planner Node)


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

    # Extract Research Info
    steps = state.get("steps", [])
    research_steps = [s for s in steps if s.get("module") == "Researcher"]
    research_info = "\n".join([f"- {s.get('response')}" for s in research_steps[-3:]])

    # DEFINE TOOLS FOR PLANNER
    # We bind the search tools directly to the LLM
    tools = [
        # Core tools
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
        # New Amadeus enrichment tools (Phase 26)
        resolve_airport_code_tool,
        get_airline_info_tool,
        search_tours_activities_tool,
        search_points_of_interest_tool,
    ]

    # We also need a structured way to return the FINAL plan.
    # We can use a "SubmitPlan" tool or just rely on the final_response text if we want to keep it simple,
    # BUT the existing architecture expects a JSON `trip_plan` object.
    # Let's bind a "SubmitPlan" tool to handle the final output structured data.

    class SubmitPlan(BaseModel):
        """Submit the finalized trip plan. ALWAYS call this when the plan is ready."""

        final_response: str = Field(description="Friendly, rich Markdown response to show the user.")
        trip_plan: Dict[str, Any] = Field(
            default={},
            description="The complete trip plan JSON with keys: destination, origin_city, dates, duration_days, budget_estimate, budget_currency, trip_type, travelers, flights, hotels, itinerary. REQUIRED - always include this."
        )

    # Bind tools + SubmitPlan
    # processing_tools = tools + [SubmitPlan] # LangChain can bind Pydantic models as tools

    # Dynamic Prompt based on Request Type
    request_type = state.get("request_type", "Planning")
    system_prompt = get_planner_prompt(request_type)

    # Construct prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            (
                "human",
                "Current Check: Duration={duration_days}, Dest={destination}, Budget={budget_limit}, Number of travelers={traveling_personas_number} Amenities={amenities}. Instruction: {instruction}",
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
            },
        )

        # Helper to parse tool calls
        tool_calls = result.tool_calls if hasattr(result, 'tool_calls') and result.tool_calls else []
        content = result.content if hasattr(result, 'content') else ""
        content_str = content if content else ""

        print(f"  Planner Content: {content_str[:100]}...")
        print(f"  Tool Calls: {len(tool_calls)}")
        print(f"  Tool Calls: {tool_calls}")

        step_log = {
            "module": "Planner",
            "prompt": instruction,
            "response": content_str if content_str else "Executing Tools...",
        }

        updates = {"steps": [step_log]}

        if not tool_calls:
            # No tools called? The LLM gave a text response (rare with bind_tools)
            # Use content as supervisor instruction and route back to Supervisor
            updates["supervisor_instruction"] = content_str or "Planner needs more information."
            updates["next_step"] = "Supervisor"
            return updates

        # Analyze Tool Calls
        # If "SubmitPlan" is called, we are done with planning
        submit_plan_call = next(
            (tc for tc in tool_calls if tc["name"] == "SubmitPlan"), None
        )

        if submit_plan_call:
            submission = submit_plan_call["args"]
            print(f"  [DEBUG] SubmitPlan Args: {list(submission.keys())}")
            updates["trip_plan"] = submission.get("trip_plan", {})
            updates["supervisor_instruction"] = "Plan Drafted"
            updates["next_step"] = "Critique"
            return updates

        # If Search Tools are called, route to Researcher (updated to handle tool calls)
        # LOOP GUARD: Hard-cap on researcher_calls even in the normal (no-exception) path
        researcher_calls = state.get("researcher_calls", 0)
        MAX_RESEARCHER_CALLS = 8
        if researcher_calls >= MAX_RESEARCHER_CALLS:
            print(f"  [GUARD] Max researcher calls reached ({researcher_calls}). Forcing plan submission.")
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
                "itinerary": [{"day": i + 1, "activity": f"Day {i+1} in {destination}", "cost": 0}
                              for i in range(duration_days or 1)],
                "special_notes": "Plan generated with limited research data. Some details may be incomplete."
            }
            updates["trip_plan"] = fallback_plan
            updates["supervisor_instruction"] = "Plan Drafted (fallback - max research iterations reached)"
            updates["next_step"] = "Human_Approval"
            return updates

        # DEDUP CHECK: avoid re-routing to Researcher with the exact same single tool already run
        import json
        last_steps = state.get("steps", [])
        researcher_steps = [s for s in last_steps if s.get("module") == "Researcher"]
        if researcher_steps and len(tool_calls) == 1:
            last_researcher_prompt = researcher_steps[-1].get("prompt", "")
            new_tool_name = tool_calls[0].get("name", "")
            if new_tool_name and new_tool_name in last_researcher_prompt:
                print(f"  [DEDUP GUARD] Planner is repeating tool '{new_tool_name}' already run. Forcing submit.")
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
                    "itinerary": [{"day": i + 1, "activity": f"Day {i+1} in {destination}", "cost": 0}
                                  for i in range(duration_days or 1)],
                    "special_notes": "Plan generated with limited research data."
                }
                updates["trip_plan"] = fallback_plan
                updates["supervisor_instruction"] = "Plan Drafted (dedup guard - repeated tool call)"
                updates["next_step"] = "Human_Approval"
                return updates

        # Serialize tool calls for Researcher
        updates["supervisor_instruction"] = (
            f"TOOL_CALLS: {json.dumps(tool_calls, default=str)}"
        )
        updates["next_step"] = "Researcher"

        return updates

    except Exception as e:
        print(f"Planner Error: {e}")
        # Guard: if researcher called too many times, go to End instead of looping
        researcher_calls = state.get("researcher_calls", 0)
        if researcher_calls >= 4:
            print(f"  [GUARD] Max researcher calls reached ({researcher_calls}). Ending.")
            return {"next_step": "End", "supervisor_instruction": f"I encountered an issue planning your trip: {e}. Please try again with more specific details."}
        return {"next_step": "Researcher", "supervisor_instruction": f"Error: {e}"}


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
    request_type = state.get("request_type", "Planning")
    if request_type == "Planning" and trip_plan and "itinerary" in trip_plan:
        actual_days = len(trip_plan.get("itinerary", []))
        print(f"  [VALIDATION] Expected {duration_days} days, got {actual_days} days")

        if actual_days != duration_days and actual_days > 0 and current_revisions < 3:
            print(f"  [VALIDATION FAILED] Duration mismatch! Sending back to Planner.")
            feedback = f"DURATION ERROR: The plan has {actual_days} days but the user requested {duration_days} days. Please regenerate the itinerary with EXACTLY {duration_days} days."
            return {
                "critique_feedback": feedback,
                "revision_count": current_revisions + 1,
                "next_step": "Trip_Planner",
                "steps": [{"module": "Critique", "prompt": "Duration Validation", "response": feedback}],
            }

    # HARD VALIDATION 2: Budget check
    # Skip for FlightOnly/HotelOnly as total cost might be just one component
    if request_type == "Planning" and trip_plan and budget_limit and budget_limit > 0:
        plan_cost = trip_plan.get("budget_estimate", 0)
        if plan_cost > 0 and plan_cost > budget_limit * 1.15:  # 15% overage tolerance
            print(f"  [BUDGET EXCEEDED] Plan=${plan_cost:.0f}, Limit=${budget_limit:.0f}")
            if current_revisions < 3:
                budget_feedback = (
                    f"BUDGET EXCEEDED: The plan costs ${plan_cost:.0f} but the user's budget is ${budget_limit:.0f}. "
                    f"Please find cheaper flights, select more affordable hotels, or reduce activity costs to stay within budget."
                )
                return {
                    "critique_feedback": budget_feedback,
                    "revision_count": current_revisions + 1,
                    "next_step": "Trip_Planner",
                    "budget_warning": budget_feedback,
                    "steps": [{"module": "Critique", "prompt": "Budget Validation", "response": budget_feedback}],
                }

    # Proceed with LLM-based critique
    # Build user_profile string for the prompt template variable
    user_profile = state.get("user_profile")
    user_profile_str = "None"
    if user_profile:
        user_profile_str = (
            f"Style: {user_profile.travel_style or 'Any'}, "
            f"Diet: {', '.join(user_profile.dietary_needs or [])}, "
            f"Interests: {', '.join(user_profile.interests or [])}"
        )

    prompt = ChatPromptTemplate.from_messages(
        [("system", CRITIQUE_SYSTEM_PROMPT), ("human", "Plan to Review: {trip_plan}")]
    )

    chain = prompt | llm.with_structured_output(CritiqueOutput)

    result = safe_llm_invoke(
        chain,
        {
            "instruction": instruction,
            "trip_plan": str(trip_plan),
            "budget": str(state.get("budget", "None")),
            "duration_days": duration_days,
            "user_profile": user_profile_str,
        },
    )

    step_log = {
        "module": "Critique",
        "prompt": "Reviewing Plan...",
        "response": f"{result.decision}: {result.feedback}",
    }

    updates = {"steps": [step_log]}

    if result.decision == "REJECT" and current_revisions < 3:
        updates["critique_feedback"] = result.feedback
        updates["revision_count"] = current_revisions + 1
        updates["next_step"] = "Trip_Planner"
    else:
        # Approved OR Max Revisions Reached
        approval_msg = "The plan has been APPROVED by the critic. Please confirm if you want to generate the final response."
        if current_revisions >= 3:
            approval_msg = "Maximum revisions reached. Finalize the plan with the current best effort."

        updates["supervisor_instruction"] = approval_msg
        updates["next_step"] = "Human_Approval"

    return updates


# 4. HUMAN APPROVAL NODE
def human_approval_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: HUMAN APPROVAL (PAUSED) ---")
    return {"next_step": "End" if state.get("user_query") == "approve_trip_plan" else "Supervisor"}


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
                t_args = tc["args"]

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
                else:
                    results += f"Error: Unknown tool {t_name}\n"

        except Exception as e:
            error_log = {
                "module": "Researcher",
                "prompt": "Tool Execution",
                "response": f"Error: {str(e)}",
            }
            print(f"  [Error] Tool Execution Failed: {e}")
            step_logs.append(error_log)
            results += f"Tool Execution Error: {str(e)}\n"

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

    # Decide where to route after research:
    # Dynamically route back to whoever called us (Supervisor or Trip_Planner)
    steps = state.get("steps", [])
    last_caller = "Supervisor"
    if steps:
        # Find the most recent step that was either Planner or Supervisor
        for s in reversed(steps):
            if s.get("module") in ["Supervisor", "Planner", "Trip_Planner"]:
                last_caller = s["module"]
                break
    
    # Ensure standard names
    next_node = "Trip_Planner" if last_caller in ["Planner", "Trip_Planner"] else "Supervisor"
    
    # Quick fix: if we somehow got here with 0 duration and no destination, 
    # and we are returning to Supervisor, let it process the results naturally.
    print(f"  [RESEARCHER] Routing back to: {next_node}")

    return {
        "steps": step_logs,
        "supervisor_instruction": results,  # Return results for Planner/Supervisor to see
        "next_step": next_node,
        "researcher_calls": researcher_calls,
    }


# --- GRAPH ---
workflow = StateGraph(AgentState)

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Trip_Planner", planner_node)
workflow.add_node("Researcher", researcher_node)
workflow.add_node("Critique", critique_node)
workflow.add_node("Human_Approval", human_approval_node)

workflow.add_edge(START, "Supervisor")


# Supervisor Routing
def route_supervisor(state: AgentState):
    return state.get("next_step", "End")


workflow.add_conditional_edges(
    "Supervisor",
    route_supervisor,
    {"Trip_Planner": "Trip_Planner", "Researcher": "Researcher", "End": END},
)


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
    if state.get("user_query") == "approve_trip_plan":
        return "End"
    return "Supervisor"

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
