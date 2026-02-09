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

# Prompts
from app.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT
from app.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT
from app.prompts.critique_prompt import CRITIQUE_SYSTEM_PROMPT

# Tools
from app.tools import web_search_tool, search_flights_tool, search_user_profile_tool

# --- LLM Setup ---
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
    next_step: Literal["Trip_Planner", "Researcher", "End"] = Field(description="The next node to execute.")
    reasoning: str = Field(description="Reason for selecting this node.")
    instruction: str = Field(description="Specific instructions for the next worker.")

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
        result = chain.invoke({"query": user_query})
        print(f"  Supervisor Result: {result}")
        
        step_log = {
            "module": "Supervisor",
            "prompt": user_query,
            "response": f"Routing to {result.next_step}: {result.reasoning}"
        }
        
        return {
            "next_step": result.next_step,
            "supervisor_instruction": result.instruction,
            "steps": [step_log]
        }
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
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_SYSTEM_PROMPT),
        ("human", "Instruction: {instruction}\nCritique Feedback: {feedback}")
    ])
    
    # Extract Research Info
    steps = state.get("steps", [])
    research_steps = [s for s in steps if s.get("module") == "Researcher"]
    research_info = "\n".join([f"- {s.get('response')}" for s in research_steps[-3:]]) # Top 3 recent
    
    chain = prompt | llm.with_structured_output(PlannerOutput, method="json_mode")
    
    result = chain.invoke({
        "instruction": instruction,
        "feedback": state.get("critique_feedback", "None"),
        "research_info": research_info if research_info else "None",
        "user_profile": str(state.get("user_profile", "None")),
        "trip_plan": str(state.get("trip_plan", "None")),
        "budget": str(state.get("budget", "None"))
    })
    
    
    # Robustness: If instruction is to finalize, ensure we have a final response
    if ("APPROVED" in instruction or "Finalize" in instruction) and not result.final_response:
        result.final_response = result.thought

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
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CRITIQUE_SYSTEM_PROMPT),
        ("human", "Plan to Review: {trip_plan}")
    ])
    
    chain = prompt | llm.with_structured_output(CritiqueOutput)
    
    result = chain.invoke({
        "instruction": instruction,
        "user_profile": str(state.get("user_profile", "None")),
        "trip_plan": str(state.get("trip_plan", "None")),
        "budget": str(state.get("budget", "None"))
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
