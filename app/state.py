from typing import TypedDict, List, Dict, Any, Annotated, Optional
import operator
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


from enum import Enum


class Amenity(str, Enum):
    # Core Hotel Amenities
    DISABLED_FACILITIES = "disabled_facilities"
    WIFI = "wifi"
    PARKING = "parking"
    AIR_CONDITIONING = "air_conditioning"
    FITNESS_CENTER = "fitness_center"
    RESTAURANT = "restaurant"
    BUSINESS_CENTER = "business_center"
    BABYSITTING = "babysitting"
    SPA = "spa"
    PETS_ALLOWED = "pets_allowed"
    PETS_NOT_ALLOWED = "pets_not_allowed"
    KOSHER = "kosher"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    GLUTEN_FREE = "gluten_free"
    WHEELCHAIR_ACCESSIBLE = "wheelchair_accessible"


def reduce_amenities(
    left: Optional[List[Amenity]], right: Optional[List[Amenity]]
) -> List[Amenity]:
    left = left or []
    right = right or []
    return list(set(left + right))


# ==============================================================================
# Data Models (Structured Content)
# ==============================================================================


class UserProfile(BaseModel):
    """
    Represents a user's travel preferences and constraints.
    """

    user_id: str = Field(description="Unique identifier for the user (e.g., email)")
    name: Optional[str] = Field(default=None, description="User's display name")
    email: Optional[str] = Field(
        default=None, description="User's email address (may match user_id)"
    )
    travel_style: Optional[str] = Field(
        default=None,
        description="Travel style (e.g., luxury, budget, balanced, adventure)",
    )
    dietary_needs: List[str] = Field(
        default_factory=list, description="List of dietary restrictions"
    )
    accessibility_needs: List[str] = Field(
        default_factory=list, description="List of accessibility requirements"
    )
    interests: List[str] = Field(
        default_factory=list, description="List of improved travel interests"
    )
    home_city: Optional[str] = Field(
        default=None, description="User's home city for flight origins"
    )


# =========================================================
# TripPlan Pydantic Model — structured output schema
# =========================================================
class FlightInfo(BaseModel):
    airline: str = Field(default="", description="Airline name")
    flight_number: str = Field(default="", description="Flight number")
    price: str = Field(default="", description="Price with currency")
    departure: str = Field(default="", description="Departure airport/city and time")
    arrival: str = Field(default="", description="Arrival airport/city and time")
    duration: str = Field(default="", description="Flight duration")
    link: str = Field(default="", description="Booking link")
    source: str = Field(default="", description="Data source (Amadeus/Kiwi/etc)")


class HotelInfo(BaseModel):
    name: str = Field(default="", description="Hotel name")
    rating: str = Field(default="", description="Rating (e.g. 4.5★)")
    price: str = Field(default="", description="Price per night or total")
    location: str = Field(default="", description="Address or area")
    amenities: List[str] = Field(default=[], description="List of amenities")
    booking_link: str = Field(default="", description="Booking link")
    check_in: str = Field(default="", description="Check-in date")
    check_out: str = Field(default="", description="Check-out date")


class ItineraryDay(BaseModel):
    day: int = Field(description="Day number (1-based)")
    activity: str = Field(description="Activities for this day")
    cost: float = Field(default=0.0, description="Estimated cost in trip currency")
    highlights: List[str] = Field(default=[], description="Key highlights for the day")


class TripPlan(BaseModel):
    """Structured trip plan — the canonical output of Trip_Planner."""

    destination: str = Field(default="", description="Trip destination")
    origin_city: str = Field(default="", description="Departure city")
    dates: str = Field(
        default="", description="Trip date range e.g. '2026-06-01 to 2026-06-07'"
    )
    duration_days: int = Field(default=0, description="Number of trip days")
    budget_estimate: float = Field(default=0.0, description="Total estimated cost")
    budget_currency: str = Field(default="USD", description="Currency code")
    trip_type: str = Field(
        default="", description="Type: honeymoon, family, adventure, etc."
    )
    travelers: int = Field(default=1, description="Number of travelers")
    flights: List[Dict[str, Any]] = Field(default=[], description="Flight options")
    hotels: List[Dict[str, Any]] = Field(default=[], description="Hotel options")
    itinerary: List[Dict[str, Any]] = Field(
        default=[], description="Day-by-day itinerary"
    )
    special_notes: str = Field(
        default="", description="Any special requirements or notes"
    )


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

    # --- 4. ROUTING METADATA (new) ---
    request_type: Optional[
        str
    ]  # "Planning", "Discovery", "FlightOnly", "HotelOnly", "AttractionsOnly"
    researcher_calls: Optional[int]  # Count of researcher node invocations (loop guard)
    user_profile: Optional[UserProfile]  # Retrieved user preferences
    budget_warning: Optional[str]  # Budget-aware warning from critique
