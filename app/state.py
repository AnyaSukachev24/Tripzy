from typing import TypedDict, List, Dict, Any, Annotated, Optional
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # --- 1. CHAT HISTORY ---
    messages: Annotated[List[BaseMessage], operator.add]
    
    # --- 2. CONTEXT (RAG) ---
    user_profile: Optional[Dict[str, Any]]  # Retrieved from Pinecone (Preferences, Past Trips)

    # --- 3. THE TRIP ---
    trip_plan: Optional[Dict[str, Any]]     # The structured itinerary being built
    budget: Optional[Dict[str, float]]      # {"limit": 2000.0, "current_total": 0.0, "currency": "USD"}
    
    # --- 4. COORDINATION ---
    next_step: str                          # Router decision
    critique_feedback: Optional[str]        # Feedback from the Critic node
    revision_count: int                     # Safety counter for loops
    steps: List[Dict[str, Any]]             # REQUIRED: Grading Log
