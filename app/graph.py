from typing import Any, Dict, Literal
from langgraph.checkpoint.memory import MemorySaver
from app.state import AgentState
from langgraph.graph import StateGraph, START, END
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
    before_sleep_log
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prompts
from app.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT
from app.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT
from app.prompts.critique_prompt import CRITIQUE_SYSTEM_PROMPT

# Tools
from app.tools import web_search_tool, search_flights_tool, search_user_profile_tool

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
        reraise=True
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
        temperature=0
    )
else:
    # Fallback to Ollama (Local)
    llm = ChatOllama(model="llama3", temperature=0)

# --- Output Models ---
class SupervisorOutput(BaseModel):
    next_step: Literal["Trip_Planner", "Researcher", "End"] = Field(description="Next worker to call.")
    reasoning: str = Field(description="Reason for selecting this node.")
    instruction: str = Field(description="Specific instructions for the next worker.")
    duration_days: int = Field(description="Trip duration in days extracted from user query.", default=0)
    destination: str = Field(description="Destination extracted from user query (e.g., 'Bali', 'Paris'). Empty if not specified.", default="")
    budget_limit: float = Field(description="Budget limit extracted from user query (e.g., '$5000' → 5000.0). 0 if not specified.", default=0.0)
    budget_currency: str = Field(description="Currency code (USD, EUR, etc.). Default USD.", default="USD")
    trip_type: str = Field(description="Type of trip: honeymoon, family, business, solo, adventure, cultural. Empty if unclear.", default="")

class PlannerOutput(BaseModel):
    thought: str = Field(description="Internal reasoning.")
    call_researcher: str = Field(description="Query for researcher if needed.", default="")
    final_response: str = Field(description="Response to user if plan is ready.", default="")
    update_plan: Dict[str, Any] = Field(description="Updates to the trip plan state.", default={})

class CritiqueOutput(BaseModel):
    decision: Literal["APPROVE", "REJECT"] = Field(description="Decision on the plan.")
    feedback: str = Field(description="Feedback if rejected.", default="")
    score: int = Field(description="Quality score 1-10.")

# --- NODES ---

# 0. PROFILE LOADER NODE
def profile_loader_node(state: AgentState) -> Dict[str, Any]:
    import sys
    print(f"--- NODE: PROFILE LOADER --- State keys: {list(state.keys())}")
    user_query = state.get("user_query")
    print(f"  User Query in Loader: {user_query}")
    sys.stdout.flush()
    user_id = "default_user" # In prod, get from request
    
    # Fetch Profile
    # In a real app, this might call a DB or the tool directly
    profile_text = search_user_profile_tool.invoke(user_id)
    
    step_log = {
        "module": "ProfileLoader",
        "prompt": "Loading Profile...",
        "response": profile_text
    }
    
    return {
        "user_profile": {"summary": profile_text},
        "steps": [step_log],
        "user_query": user_query
    }

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
            "steps": [{"module": "Supervisor", "prompt": user_query, "response": "Hello! I am Tripzy."}]
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        ("human", "User Input: {query}")
    ])
    
    chain = prompt | llm.with_structured_output(SupervisorOutput)
    
    print(f"  Supervisor Query: {user_query}")
    try:
        result = safe_llm_invoke(chain, {"query": user_query})
        print(f"  Supervisor Result: {result}")
        print(f"  [DEBUG] DURATION EXTRACTED: {result.duration_days} days")
        print(f"  [DEBUG] DESTINATION EXTRACTED: '{result.destination}'")
        print(f"  [DEBUG] BUDGET EXTRACTED: ${result.budget_limit} {result.budget_currency}")
        print(f"  [DEBUG] TRIP TYPE DETECTED: '{result.trip_type}'")
        print(f"  [DEBUG] INSTRUCTION: {result.instruction}")
        
        step_log = {
            "module": "Supervisor",
            "prompt": user_query,
            "response": f"Routing to {result.next_step}: {result.reasoning}"
        }
        
        updates = {
            "next_step": result.next_step,
            "supervisor_instruction": result.instruction,
            "steps": [step_log]
        }
        
        # Extract duration if provided
        if result.duration_days and result.duration_days > 0:
            updates["duration_days"] = result.duration_days
            
        # Extract destination if provided  
        if result.destination:
            updates["destination"] = result.destination
            
        # Extract budget if provided
        if result.budget_limit and result.budget_limit > 0:
            updates["budget_limit"] = result.budget_limit
            updates["budget_currency"] = result.budget_currency or "USD"
            
        # Extract trip type if detected
        if result.trip_type:
            updates["trip_type"] = result.trip_type
        
        # EDGE CASE VALIDATION - Check for impossible/problematic requests
        from app.edge_case_validator import process_edge_cases
        
        # Only enforce strict planning constraints (like non-zero duration) if we are actually planning
        is_planning = (result.next_step == "Trip_Planner")
        
        edge_case_result = process_edge_cases(
            user_query=user_query,
            duration_days=result.duration_days,
            budget_limit=result.budget_limit,
            budget_currency=result.budget_currency,
            trip_type=result.trip_type,
            destination=result.destination,
            is_planning=is_planning
        )
        
        if edge_case_result["has_edge_case"] and edge_case_result["should_block"]:
            # Don't proceed to planning, inform user of the issue
            print(f"  [EDGE CASE DETECTED] {edge_case_result['error_message'][:100]}...")
            return {
                "next_step": "End",
                "supervisor_instruction": edge_case_result["error_message"],
                "steps": [{
                    "module": "Supervisor",
                    "prompt": user_query,
                    "response": f"Edge Case Detected: {edge_case_result['error_message']}"
                }]
            }
        
        # MULTI-TURN: Check if we have minimum required information  
        # If supervisor wants to route to Trip_Planner, validate we have destination + duration
        if result.next_step == "Trip_Planner":
            missing_required = []
            
            # Check what we already have in state (from previous turns)
            current_destination = state.get("destination") or result.destination
            current_duration = state.get("duration_days") or result.duration_days
            
            if not current_destination:
                missing_required.append("destination")
            if not current_duration or current_duration == 0:
                missing_required.append("duration")
            
            # If missing required info, ask for the FIRST missing piece
            if missing_required:
                # Helper to make questions contextual
                topic = f"{result.trip_type} trip" if result.trip_type else "trip"
                
                if "destination" in missing_required:
                    clarifying_question = f"That sounds great! 🌍 But could you tell me where you'd like to go for your {topic}? (e.g., Paris, Bali, Tokyo)"
                elif "duration" in missing_required:
                    clarifying_question = f"I'd love to plan this {topic} for you! 🗓️ How many days or weeks are you thinking of traveling?"
                else:
                    clarifying_question = result.instruction
                
                print(f"  [MULTI-TURN] Missing required info: {missing_required}. Asking for clarification.")
                return {
                    "next_step": "End",
                    "supervisor_instruction": clarifying_question,
                    "steps": [{
                        "module": "Supervisor",
                        "prompt": user_query,
                        "response": f"Need more information: {clarifying_question}"
                    }]
                }
            
        return updates
    except Exception as e:
        print(f"  Supervisor Error: {str(e)}")
        error_msg = f"System Error: {str(e)}"
        return {
            "next_step": "End", 
            "supervisor_instruction": error_msg,
            "steps": [{"module": "Supervisor", "error": str(e), "response": error_msg}]
        }

# 2. PLANNER NODE
def planner_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: PLANNER ---")
    instruction = state.get("supervisor_instruction", "")
    
    # Note: PLANNER_SYSTEM_PROMPT already has placeholders for:
    # {instruction}, {user_profile}, {research_info}, {feedback}, {duration_days}, {destination}
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_SYSTEM_PROMPT)
    ])
    
    # Get duration from state (default to 7 if not specified)
    duration_days = state.get("duration_days", 7)
    print(f"  [DEBUG] PLANNER RECEIVED duration_days: {duration_days}")
    print(f"  [DEBUG] PLANNER RECEIVED instruction: {instruction}")
    
    # Get destination from state
    destination = state.get("destination", "")
    print(f"  [DEBUG] PLANNER RECEIVED destination: '{destination}'")
    
    # Get budget from state
    budget_limit = state.get("budget_limit", 0.0)
    budget_currency = state.get("budget_currency", "USD")
    print(f"  [DEBUG] PLANNER RECEIVED budget: ${budget_limit} {budget_currency}")
    
    # Get trip type from state
    trip_type = state.get("trip_type", "")
    print(f"  [DEBUG] PLANNER RECEIVED trip_type: '{trip_type}'")
    
    # Extract Research Info
    steps = state.get("steps", [])
    research_steps = [s for s in steps if s.get("module") == "Researcher"]
    research_info = "\n".join([f"- {s.get('response')}" for s in research_steps[-3:]]) # Top 3 recent
    
    chain = prompt | llm.with_structured_output(PlannerOutput, method="json_mode")
    
    print(f"  [DEBUG] CALLING PLANNER with duration_days={duration_days}, destination='{destination}', budget=${budget_limit}, trip_type='{trip_type}'")
    result = safe_llm_invoke(chain, {
        "instruction": instruction,
        "feedback": state.get("critique_feedback", "None"),
        "research_info": research_info if research_info else "None",
        "user_profile": str(state.get("user_profile", "None")),
        "trip_plan": str(state.get("trip_plan", "None")),
        "budget": str(state.get("budget", "None")),
        "duration_days": duration_days,
        "destination": destination,
        "budget_limit": budget_limit,
        "budget_currency": budget_currency,
        "trip_type": trip_type
    })
    
    
    # Robustness: If instruction is to finalize, ensure we have a final response
    if ("APPROVED" in instruction or "Finalize" in instruction) and not result.final_response:
        result.final_response = result.thought
    print(f"  Planner thought: {result.thought}")
    print(f"  Planner wants researcher? {result.call_researcher}")
    print(f"  [DEBUG] PLANNER RESPONSE - update_plan: {result.update_plan}")
    if result.update_plan:
        print(f"  [DEBUG] DESTINATION: {result.update_plan.get('destination')}")
        print(f"  [DEBUG] ITINERARY DAYS: {len(result.update_plan.get('itinerary', []))}")
    response_text = result.final_response if result.final_response else result.thought
    
    step_log = {
        "module": "Planner",
        "prompt": instruction,
        "response": response_text
    }
    
    # Update State
    updates = {"steps": [step_log]}
    
    # Check if research is needed
    if result.call_researcher:
        updates["supervisor_instruction"] = result.call_researcher
        updates["next_step"] = "Researcher"
    elif result.update_plan:
        updates["trip_plan"] = result.update_plan
        # Go to Critique instead of Supervisor
        updates["next_step"] = "Critique" 
    elif result.final_response:
        updates["supervisor_instruction"] = "Done"
        # If finished, go directly to End. 
        # The main loop will see the last step has the response.
        updates["next_step"] = "End"
    else:
        # Default fallback
        updates["next_step"] = "Supervisor"
        
    return updates

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
            print(f"  [VALIDATION FAILED] Duration mismatch!")
            step_log = {
                "module": "Critique",
                "prompt": "Validating duration...",
                "response": f"REJECT: Plan has {actual_days} days but {duration_days} required"
            }
            
            current_revisions = state.get("revision_count", 0)
            
            if current_revisions < 3:
                return {
                    "steps": [step_log],
                    "critique_feedback": f"CRITICAL: You created {actual_days} days but the user requested EXACTLY {duration_days} days. Count your itinerary items before responding. You must have {duration_days} items in the itinerary array.",
                    "revision_count": current_revisions + 1,
                    "next_step": "Trip_Planner"
                }
            else:
                # Max revisions reached, force approval with warning
                return {
                    "steps": [step_log],
                    "supervisor_instruction": "Maximum revisions reached. Proceeding with current plan despite duration mismatch.",
                    "next_step": "Human_Approval"
                }
    
    # Proceed with LLM-based critique
    prompt = ChatPromptTemplate.from_messages([
        ("system", CRITIQUE_SYSTEM_PROMPT),
        ("human", "Plan to Review: {trip_plan}")
    ])
    
    chain = prompt | llm.with_structured_output(CritiqueOutput)
    
    result = safe_llm_invoke(chain, {
        "instruction": instruction,
        "user_profile": str(state.get("user_profile", "None")),
        "trip_plan": str(trip_plan),
        "budget": str(state.get("budget", "None")),
        "duration_days": duration_days
    })
    
    step_log = {
        "module": "Critique",
        "prompt": "Reviewing Plan...",
        "response": f"{result.decision}: {result.feedback}"
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
    # This node is a placeholder for the interrupt
    return {"next_step": "Trip_Planner"}

# 3. RESEARCHER NODE
def researcher_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: RESEARCHER ---")
    query = state.get("supervisor_instruction", "")
    
    # Execute Tools
    # For MVP, we just use DuckDuckGo
    results = web_search_tool.invoke(query)
    
    step_log = {
        "module": "Researcher",
        "prompt": query,
        "response": results[:500] # Truncate for log
    }
    
    return {
        "steps": [step_log],
        # Feed result back to Planner effectively? 
        # Actually, in this simple graph, we might want to loop back to Supervisor
        # who then passes info to Planner.
    }

# --- GRAPH ---
workflow = StateGraph(AgentState)

workflow.add_node("ProfileLoader", profile_loader_node)
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Trip_Planner", planner_node)
workflow.add_node("Researcher", researcher_node)
workflow.add_node("Critique", critique_node)
workflow.add_node("Human_Approval", human_approval_node)

workflow.add_edge(START, "ProfileLoader")
workflow.add_edge("ProfileLoader", "Supervisor")

# Supervisor Routing
def route_supervisor(state: AgentState):
    return state.get("next_step", "End")

workflow.add_conditional_edges(
    "Supervisor",
    route_supervisor,
    {
        "Trip_Planner": "Trip_Planner",
        "Researcher": "Researcher",
        "End": END
    }
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
        "End": END
    }
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
        "Supervisor": "Supervisor"
    }
)

# Human Approval Logic
workflow.add_edge("Human_Approval", "Trip_Planner")

# Researcher -> Planner (Direct Loop for efficiency)
# Or Supervisor? Let's go Supervisor to be safe and update context.
# Actually, if Researcher just ran, Planner needs to see resume.
# Let's go Researcher -> Planner?
# But Planner needs "instruction". Instruction is currently "Research X".
# We need to reset instruction to "Plan a trip"?
# Supervisor is safer for now.
workflow.add_edge("Researcher", "Supervisor")

memory = MemorySaver()

graph = workflow.compile(checkpointer=memory, interrupt_before=["Human_Approval"])
