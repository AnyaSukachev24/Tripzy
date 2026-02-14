from typing import TypedDict, List, Dict, Any, Annotated, Optional
import operator
from langchain_core.messages import BaseMessage


from enum import Enum


class Amenity(str, Enum):
    DISABLED_FACILITIES = "DISABLED_FACILITIES"
    PETS_ALLOWED = "PETS_ALLOWED"
    WIFI = "WIFI"
    KSML = "KSML"
    VGML = "VGML"
    WCHR = "WCHR"
    PARKING = "PARKING"
    AIR_CONDITIONING = "AIR_CONDITIONING"
    FITNESS_CENTER = "FITNESS_CENTER"
    RESTAURANT = "RESTAURANT"
    BUSINESS_CENTER = "BUSINESS_CENTER"
    BABYSITTING = "BABYSITTING"
    SPA = "SPA"
    MOML = "MOML"
    GFML = "GFML"
    WCHC = "WCHC"
    PETC = "PETC"


def reduce_amenities(
    left: Optional[List[Amenity]], right: Optional[List[Amenity]]
) -> List[Amenity]:
    left = left or []
    right = right or []
    return list(set(left + right))


class AgentState(TypedDict):
    # --- 1. CHAT HISTORY ---
    messages: Annotated[List[BaseMessage], operator.add]

    # --- 2. THE TRIP ---
    trip_plan: Optional[Dict[str, Any]]  # The structured itinerary being built
    duration_days: Optional[
        int
    ]  # Number of days for the trip (extracted from user query)
    destination: Optional[
        str
    ]  # Destination extracted from user query (e.g., "Bali", "Paris")
    origin_city: Optional[
        str
    ]  # Origin city extracted from user query (e.g., "London", "NYC")
    budget_limit: Optional[float]  # User's budget limit (e.g., 5000.0)
    budget_currency: str  # Currency code (e.g., "USD", "EUR")
    trip_type: Optional[
        str
    ]  # Type of trip: honeymoon, family, business, solo, adventure
    budget: Optional[
        Dict[str, float]
    ]  # {"limit": 2000.0, "current_total": 0.0, "currency": "USD"}
    traveling_personas_number: Optional[int]  # Number of people traveling
    amenities: Annotated[
        List[Amenity], reduce_amenities
    ]  # List of requested amenities (Set-like)
    preferences: Annotated[
        List[str], operator.add
    ]  # List of extracted preferences (e.g., 'beach', 'history')

    # --- 3. COORDINATION ---
    next_step: str  # Router decision
    supervisor_instruction: Optional[str]  # Instruction or feedback from Supervisor
    critique_feedback: Optional[str]  # Feedback from the Critic node
    revision_count: int  # Safety counter for loops
    user_query: str  # The original prompt
    steps: Annotated[List[Dict[str, Any]], operator.add]  # REQUIRED: Grading Log
