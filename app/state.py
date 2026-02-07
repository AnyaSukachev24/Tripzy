from typing import TypedDict, List, Dict, Any, Annotated, Optional
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # --- 1. HUMAN INTERACTION ---
    messages: Annotated[List[BaseMessage], operator.add]  # Full conversation history
    user_query: str  # The LATEST thing the human said ("Yes", "No", "Italy")

    # --- 2. THE PLAN (The Supervisor's Memory) ---

    trip_plan: Optional[Dict[str, Any]]
    active_customer: Optional[Dict[str, Any]]
    mission_context: Optional[str]  # High-level plan/progress summary

    # --- 3. THE IMMEDIATE TASK (For Sub-Agents) ---
    supervisor_instruction: Optional[str]  # Specific command ("Check flights")
    # Internal router state
    next_node: Optional[
        Literal["CRM_Retriever", "Trip_Planner", "Action_Executor", "END"]
    ]
    # --- 4. SAFETY ---
    pending_action: Optional[Dict[str, Any]]
    awaiting_approval: bool
    is_approved: Optional[bool]  # Result from Human_Approval node

    # --- 5. LOGGING ---
    steps: List[Dict[str, Any]]
