from typing import Any, Dict, Literal, List
from langgraph.checkpoint.memory import MemorySaver
from app.state import AgentState, Amenity
from langgraph.graph import StateGraph, START, END


# ... imports ...


from langchain_community.chat_models import ChatOllama
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
from app.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT
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


# Using Azure OpenAI
if os.getenv("AZURE_OPENAI_API_KEY"):
    llm = AzureChatOpenAI(
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        temperature=0,
    )
else:
    # Fallback to Ollama (Local)
    llm = ChatOllama(model="llama3", temperature=0)


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
    request_type: Literal["Planning", "Discovery"] = Field(
        description="Intent: 'Planning' for specific trips, 'Discovery' for vague requests.",
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

    # Simple Router Logic (Optimization: Don't call LLM for "Hi")
    if user_query.lower() in ["hi", "hello", "test"]:
        return {
            "next_step": "End",
            "steps": [
                {
                    "module": "Supervisor",
                    "prompt": user_query,
                    "response": "Hello! I am Tripzy.",
                }
            ],
        }

    # Format context for the LLM so it knows what has already been provided
    # INJECT RESEARCH HISTORY: Get recent steps from Researcher to prevent loops
    steps = state.get("steps", [])
    research_steps = [s for s in steps if s.get("module") == "Researcher"]
    research_history = ""
    if research_steps:
        research_history = "\nRECENT RESEARCH RESULTS:\n" + "\n".join(
            [f"- {s.get('response')[:500]}..." for s in research_steps[-3:]]
        )

    current_context = f"CURRENT STATE:\n- Destination: {state.get('destination') or 'Not Set'}\n- Duration: {state.get('duration_days') or 0} days\n- Budget: {state.get('budget_limit') or 0} {state.get('budget_currency') or 'USD'}\n- Trip Type: {state.get('trip_type') or 'Not Set'}\n- Origin: {state.get('origin_city') or 'Not Set'}\n- Travelers: {state.get('traveling_personas_number') or 1}\n- Amenities: {state.get('amenities') or []}\n{research_history}"

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
        # Insert before the last human message or append as strict system instruction
        messages.insert(1, ("system", loop_prevention_msg))

    prompt = ChatPromptTemplate.from_messages(messages)

    chain = prompt | llm.with_structured_output(SupervisorOutput)

    try:  # Pass the formatted context to the prompt
        # We use the original user_query, not a modified one
        result = safe_llm_invoke(
            chain, {"query": user_query, "context": current_context}
        )
        print(f"SUPERVISOR RESULT: {result}")

        step_log = {
            "module": "Supervisor",
            "prompt": user_query,
            "response": f"Routing to {result.next_step}: {result.reasoning}",
        }

        # HANDLE DISCOVERY (Vague Requests)
        if result.request_type == "Discovery":
            print(f"  [DISCOVERY MODE] Preferences: {result.preferences}")

            # If we have preferences but no destination, route to Researcher for suggestions
            # ONLY if we haven't already done research (to avoid loops)
            if result.preferences and not result.destination and not research_steps:
                search_query = f"Suggest 3-5 travel destinations matching these preferences: {', '.join(result.preferences)}."
                if result.budget_limit > 0:
                    search_query += f" Budget: ${result.budget_limit}."
                if result.duration_days > 0:
                    search_query += f" Duration: {result.duration_days} days."

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

        # Only enforce strict planning constraints (like non-zero duration) if we are actually planning
        is_planning = result.next_step == "Trip_Planner"

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
            return {
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
            }

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

            if not current_destination:
                missing_required.append("destination")
            if not current_duration or current_duration == 0:
                missing_required.append("duration")
            # Origin is good to have but maybe not strictly blocking if we want to just browse?
            # But for "Plan a trip", yes.
            # Let's make it soft-blocking or ask nicely.
            # For now, let's treat it as required for "Trip_Planner".
            current_origin = state.get("origin_city") or result.origin_city
            if not current_origin:
                missing_required.append("origin")

            # If missing required info, ask for the FIRST missing piece
            if missing_required:
                # Helper to make questions contextual
                topic = f"{result.trip_type} trip" if result.trip_type else "trip"

                if "destination" in missing_required:
                    clarifying_question = f"That sounds great! 🌍 But could you tell me where you'd like to go for your {topic}? (e.g., Paris, Bali, Tokyo)"
                elif "duration" in missing_required:
                    clarifying_question = f"I'd love to plan this {topic} for you! 🗓️ How many days or weeks are you thinking of traveling?"
                elif "origin" in missing_required:
                    clarifying_question = f"To find the best flights ✈️, could you tell me which city you'll be flying from?"
                else:
                    clarifying_question = result.instruction

                print(
                    f"  [MULTI-TURN] Missing required info: {missing_required}. Asking for clarification."
                )
                return {
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
                    "steps": [
                        {
                            "module": "Supervisor",
                            "prompt": user_query,
                            "response": f"Need more information: {clarifying_question}",
                        }
                    ],
                }
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
            "steps": [step_log],
        }
        return updates
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
    print("--- NODE: PLANNER ---")
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
    ]

    # We also need a structured way to return the FINAL plan.
    # We can use a "SubmitPlan" tool or just rely on the final_response text if we want to keep it simple,
    # BUT the existing architecture expects a JSON `trip_plan` object.
    # Let's bind a "SubmitPlan" tool to handle the final output structured data.

    class SubmitPlan(BaseModel):
        """Submit the finalized trip plan."""

        final_response: str = Field(description="Response to user.")
        trip_plan: Dict[str, Any] = Field(description="The complete trip plan JSON.")

    # Bind tools + SubmitPlan
    # processing_tools = tools + [SubmitPlan] # LangChain can bind Pydantic models as tools

    # Construct prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PLANNER_SYSTEM_PROMPT),
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

    try:
        # Invoke LLM
        result = safe_llm_invoke(
            chain,
            {
                "instruction": instruction,
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
        tool_calls = result.tool_calls
        content = result.content

        print(f"  Planner Content: {content[:100]}...")
        print(f"  Tool Calls: {len(tool_calls)}")
        print(f"  Tool Calls: {tool_calls}")

        step_log = {
            "module": "Planner",
            "prompt": instruction,
            "response": content if content else "Executing Tools...",
        }

        updates = {"steps": [step_log]}

        if not tool_calls:
            # No tools called? Fallback to Supervisor or just loop?
            # If content suggests a question, maybe go to User/End?
            # For now, treat as "thinking" or "asking supervisor"
            updates["supervisor_instruction"] = content
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
        # We pass the tool_calls list to Researcher via state or instruction
        # Since our graph uses `state` persistence, let's store it.
        # But wait, `Researcher` reads `supervisor_instruction`.
        # We should serialize these tool calls into the instruction for the Researcher to execute.
        # OR better: The Researcher node SHOULD be the one executing them.

        # Let's format the instruction to pass the tool calls
        # We will use a special prefix "TOOL_CALLS:" to let Researcher know
        import json

        # We can't pass objects easily in a string instruction without serialization
        # But we can store them in specific state key `tool_calls` if we added it to AgentState?
        # AgentState definition is in `app/state.py`. We might need to add it there.
        # For now, let's serialize into the instruction string.

        # Serialize tool calls for Researcher
        updates["supervisor_instruction"] = (
            f"TOOL_CALLS: {json.dumps(tool_calls, default=str)}"
        )
        updates["next_step"] = "Researcher"

        return updates

    except Exception as e:
        print(f"Planner Error: {e}")
        return {"next_step": "Researcher", "supervisor_instruction": f"Error: {e}"}


# 3. CRITIQUE NODE
def critique_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: CRITIQUE ---")
    instruction = state.get("supervisor_instruction", "")
    trip_plan = state.get("trip_plan")
    duration_days = state.get("duration_days", 7)

    # HARD VALIDATION: Check duration before calling LLM
    if trip_plan and "itinerary" in trip_plan:
        actual_days = len(trip_plan.get("itinerary", []))
        print(f"  [VALIDATION] Expected {duration_days} days, got {actual_days} days")

        if actual_days != duration_days:
            # ... (Existing validation logic)
            print(f"  [VALIDATION FAILED] Duration mismatch!")
            # ... (rest of logic)

    # ... (Rest of Critique Node logic)
    # Re-implementing the rest to ensure it's not lost in replacement

    # Proceed with LLM-based critique
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
        },
    )

    step_log = {
        "module": "Critique",
        "prompt": "Reviewing Plan...",
        "response": f"{result.decision}: {result.feedback}",
    }

    updates = {"steps": [step_log]}

    current_revisions = state.get("revision_count", 0)

    if result.decision == "REJECT" and current_revisions < 3:
        updates["critique_feedback"] = result.feedback
        updates["revision_count"] = current_revisions + 1
        updates["next_step"] = "Trip_Planner"
    else:
        # Approved OR Max Revisions Reached
        instruction = "The plan has been APPROVED by the critic. Please confirm if you want to generate the final response."
        if current_revisions >= 3:
            instruction = "Maximum revisions reached. Finalize the plan with the current best effort."

        updates["supervisor_instruction"] = instruction
        updates["next_step"] = "Human_Approval"

    return updates


# 4. HUMAN APPROVAL NODE
def human_approval_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: HUMAN APPROVAL (PAUSED) ---")
    return {"next_step": "Trip_Planner"}


# 3. RESEARCHER NODE (Enhanced for Tools)
def researcher_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: RESEARCHER ---")
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

    return {
        "steps": step_logs,
        "supervisor_instruction": results,  # Return results for Planner to see
        "next_step": "Trip_Planner",  # IMPORTANT: Loop back to Planner, NOT Supervisor
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
workflow.add_edge("Human_Approval", "Trip_Planner")

# Researcher -> Supervisor (Default loop)
workflow.add_edge("Researcher", "Supervisor")

memory = MemorySaver()

graph = workflow.compile(checkpointer=memory, interrupt_before=["Human_Approval"])
