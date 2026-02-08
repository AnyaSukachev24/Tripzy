from typing import Any, Dict, Literal
from langgraph.checkpoint.memory import MemorySaver
from app.state import AgentState
from langgraph.graph import StateGraph, START, END
from langchain_community.chat_models import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
import os
import json

# Prompts
from app.prompts.supervisor_system_prompt import SUPERVISOR_SYSTEM_PROMPT
from app.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT

# Tools
from app.tools import web_search_tool, search_flights_tool, search_user_profile_tool

# --- LLM Setup ---
# Use .env to decide model. Default to free/local if key missing.
if os.getenv("GOOGLE_API_KEY"):
    llm = ChatGoogleGenerativeAI(model=os.getenv("LLM_MODEL", "gemini-1.5-flash"), temperature=0)
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

# --- NODES ---

# 1. SUPERVISOR NODE
def supervisor_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: SUPERVISOR ---")
    user_query = state.get("user_query", "")
    
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
    
    try:
        result = chain.invoke({"query": user_query})
        
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
        return {"next_step": "End", "steps": [{"module": "Supervisor", "error": str(e)}]}

# 2. PLANNER NODE
def planner_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: PLANNER ---")
    instruction = state.get("supervisor_instruction", "")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_SYSTEM_PROMPT),
        ("human", "Instruction: {instruction}")
    ])
    
    chain = prompt | llm.with_structured_output(PlannerOutput)
    
    result = chain.invoke({
        "instruction": instruction,
        "user_profile": str(state.get("user_profile", "None")),
        "trip_plan": str(state.get("trip_plan", "None")),
        "budget": str(state.get("budget", "None"))
    })
    
    step_log = {
        "module": "Planner",
        "prompt": instruction,
        "response": result.thought
    }
    
    # Update State
    updates = {"steps": [step_log]}
    if result.update_plan:
        updates["trip_plan"] = result.update_plan
        
    return updates

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

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Trip_Planner", planner_node)
workflow.add_node("Researcher", researcher_node)

workflow.add_edge(START, "Supervisor")

# Conditional Edges
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

# Loop back
workflow.add_edge("Trip_Planner", "Supervisor") 
workflow.add_edge("Researcher", "Supervisor")

memory = MemorySaver()

graph = workflow.compile(checkpointer=memory)
