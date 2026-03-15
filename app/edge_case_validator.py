"""
Edge Case Validation Module for Tripzy
Detects and handles impossible or problematic travel requests.
"""
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple, Any


def validate_budget(budget_limit: float, duration_days: int, trip_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate if budget is reasonable for the trip.
    
    Returns:
        (is_valid, error_message)
    """
    if budget_limit <= 0:
        return True, None  # No budget specified, ask user
    
    if duration_days <= 0:
        return True, None  # No duration specified, can't validate
    
    # Calculate per-day budget
    per_day_budget = budget_limit / duration_days
    
    # Minimum viable budgets per day (USD)
    MIN_BUDGETS = {
        "luxury": 200,
        "honeymoon": 150,
        "business": 150,
        "mid-range": 50,
        "family": 40,
        "adventure": 30,
        "solo": 25,
        "budget": 20,
    }
    
    # Get minimum for trip type (default to budget tier)
    min_required = MIN_BUDGETS.get(trip_type.lower(), MIN_BUDGETS["budget"])
    
    # CRITICAL: Check if budget is impossibly low
    if per_day_budget < 15:  # $15/day is absolute minimum
        return False, (
            f"Budget of ${budget_limit:.0f} for {duration_days} days (${per_day_budget:.0f}/day) is insufficient for any realistic travel. "
            f"Minimum recommended: ${15 * duration_days:.0f} for ultra-budget camping. "
            f"Consider: (1) Increasing budget to ${min_required * duration_days:.0f}+ ({trip_type} tier), "
            f"(2) Reducing duration to {int(budget_limit / min_required)} days, or "
            f"(3) Local staycation options."
        )
    
    # WARNING: Check if budget is very tight
    if per_day_budget < min_required:
        return False, (
            f"Budget of ${budget_limit:.0f} for {duration_days} days (${per_day_budget:.0f}/day) is very tight for a {trip_type} trip. "
            f"Recommended minimum: ${min_required * duration_days:.0f}. "
            f"Possible options: (1) Increase budget, (2) Choose ultra-budget camping/hostels, "
            f"(3) Reduce duration to {int(budget_limit / min_required)} days."
        )
    
    return True, None


def validate_duration(duration_days: int) -> Tuple[bool, Optional[str]]:
    """
    Validate if duration is reasonable.
    
    Returns:
        (is_valid, error_message)
    """
    if duration_days <= 0:
        return False, "Trip duration not specified. How many days would you like to travel?"
    
    if duration_days > 365:
        # Very long trip - special handling needed
        years = duration_days // 365
        year_label = "years" if years > 1 else "year"
        return False, (
            f"A {duration_days}-day trip ({years} {year_label}) requires special planning. "
            f"Consider: (1) Breaking into multiple trips, (2) World tour itinerary with visa planning, "
            f"(3) Digital nomad setup. Please confirm this duration or provide a shorter timeframe."
        )
    
    return True, None


def validate_conflicting_requirements(
    budget_limit: float,
    duration_days: int,
    trip_type: str,
    destination: str
) -> Tuple[bool, Optional[str]]:
    """
    Detect conflicting requirements (e.g., luxury on tiny budget).
    
    Returns:
        (is_valid, error_message)
    """
    if not budget_limit or not duration_days:
        return True, None  # Can't validate without both
    
    per_day_budget = budget_limit / duration_days
    
    # Luxury/Honeymoon requires high budget
    if trip_type.lower() in ["luxury", "honeymoon"]:
        if per_day_budget < 150:
            estimated_budget = 200 * duration_days
            return False, (
                f"Conflicting requirements: {trip_type.title()} trip typically requires $150-400/day, "
                f"but your budget is ${per_day_budget:.0f}/day. "
                f"Estimated minimum for {duration_days}-day {trip_type} trip: ${estimated_budget:.0f}. "
                f"Options: (1) Increase budget to ${estimated_budget:.0f}+, "
                f"(2) Switch to mid-range accommodations, or (3) Reduce duration to {int(budget_limit / 200)} days."
            )
    
    # Expensive destinations require higher budgets
    expensive_destinations = ["maldives", "switzerland", "norway", "iceland", "dubai", "singapore"]
    if any(dest in destination.lower() for dest in expensive_destinations):
        if per_day_budget < 100:
            return False, (
                f"Conflicting requirements: {destination} is a high-cost destination (typically $100-300/day), "
                f"but your budget is ${per_day_budget:.0f}/day. "
                f"Consider: (1) Increasing budget to ${100 * duration_days:.0f}+, "
                f"(2) Choosing a budget-friendly destination, or (3) Ultra-budget accommodations (hostels, camping)."
            )
    
    return True, None


# Continents / major world regions that are too vague to plan a trip to
_VAGUE_REGIONS = {
    "europe": "Paris (France), Rome (Italy), Prague (Czech Republic), Santorini (Greece), Barcelona (Spain)",
    "asia": "Bali (Indonesia), Tokyo (Japan), Bangkok (Thailand), Kyoto (Japan), Singapore",
    "southeast asia": "Bali (Indonesia), Bangkok (Thailand), Hoi An (Vietnam), Chiang Mai (Thailand), Luang Prabang (Laos)",
    "south america": "Rio de Janeiro (Brazil), Buenos Aires (Argentina), Cartagena (Colombia), Cusco (Peru), Medellin (Colombia)",
    "latin america": "Cancun (Mexico), Cartagena (Colombia), Buenos Aires (Argentina), Lima (Peru)",
    "north america": "New York (USA), Vancouver (Canada), Miami (USA), New Orleans (USA), Quebec City (Canada)",
    "africa": "Cape Town (South Africa), Marrakech (Morocco), Zanzibar (Tanzania), Nairobi (Kenya)",
    "middle east": "Dubai (UAE), Petra (Jordan), Istanbul (Turkey), Tel Aviv (Israel)",
    "oceania": "Sydney (Australia), Auckland (New Zealand), Fiji, Bora Bora (French Polynesia)",
    "caribbean": "Barbados, Aruba, Punta Cana (Dominican Republic), Turks and Caicos, Jamaica",
    "scandinavia": "Copenhagen (Denmark), Stockholm (Sweden), Bergen (Norway), Reykjavik (Iceland)",
    "balkans": "Dubrovnik (Croatia), Kotor (Montenegro), Sofia (Bulgaria), Ljubljana (Slovenia)",
    "central america": "Costa Rica, Panama City (Panama), Antigua (Guatemala)",
    "the world": None,
    "everywhere": None,
    "anywhere": None,
}


def validate_destination_specificity(destination: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if the destination is a continent or major world region — too vague to plan a trip.

    Returns:
        (is_valid, error_message)  —  is_valid=False means we should block planning.
    """
    if not destination:
        return True, None  # Empty is handled elsewhere

    dest_lower = destination.strip().lower()

    # Direct match or "the X" prefix
    check_keys = {dest_lower, dest_lower.lstrip("the ").strip()}
    for vague, examples in _VAGUE_REGIONS.items():
        if vague in check_keys or dest_lower == vague:
            if examples:
                msg = (
                    f'"{destination}" is a whole region — I need a specific city or country to plan your trip! '
                    f"Some great options in {destination}: {examples}. "
                    f"Which city or country would you like to visit?"
                )
            else:
                msg = (
                    "That destination is too broad for me to plan a trip — could you name "
                    "a specific city or country? (e.g., Paris, Tokyo, Bali, Cape Town)"
                )
            return False, msg

    return True, None


def validate_group_size(trip_request: str) -> Tuple[bool, Optional[str]]:
    """
    Detect very large groups that need special handling.
    
    Returns:
        (is_valid, warning_message)
    """
    # Simple detection for large numbers in request
    import re
    numbers = re.findall(r'\b(\d+)\s*(?:people|person|pax|travelers|guests)', trip_request.lower())
    
    if numbers:
        group_size = int(numbers[0])
        if group_size >= 20:
            return False, (
                f"Large group travel ({group_size} people) requires special arrangements. "
                f"Recommendations: (1) Contact group booking specialists, "
                f"(2) Book 6-12 months in advance, (3) Consider group discounts, "
                f"(4) Arrange dedicated tour guides. Would you like assistance with group booking resources?"
            )
    
    return True, None


def validate_travel_dates(trip_request: str) -> Tuple[bool, Optional[str]]:
    """
    Detect impossible travel dates (past dates).
    
    Returns:
        (is_valid, error_message)
    """
    # Simple detection for date-related keywords
    past_indicators = ["yesterday", "last week", "last month", "last year"]
    
    if any(indicator in trip_request.lower() for indicator in past_indicators):
        return False, (
            "Cannot book travel for past dates. Please provide future travel dates. "
            "When would you like to travel?"
        )
    
    return True, None


def process_edge_cases(
    user_query: str,
    duration_days: int,
    budget_limit: float,
    budget_currency: str,
    trip_type: str,
    destination: str,
    is_planning: bool = True
) -> Dict[str, Any]:
    """
    Main edge case processing function.
    
    Args:
        is_planning: If True, enforces strict requirements (must have duration, etc.).
                     If False (e.g., asking clarifying questions), relaxes checks.
    
    Returns:
        {
            "has_edge_case": bool,
            "error_message": str or None,
            "should_block": bool,  # True if we should prevent planning
            "suggestions": list of str
        }
    """
    result: Dict[str, Any] = {
        "has_edge_case": False,
        "error_message": None,
        "should_block": False,
        "suggestions": []
    }
    
    # Run validations
    validations = []

    # --- Destination specificity check (always runs when a destination is given) ---
    # Check FIRST so the user immediately gets redirected to pick a city
    if destination:
        validations.append(validate_destination_specificity(destination))

    # Only validate duration strictly if we are trying to plan
    if is_planning:
        validations.append(validate_duration(duration_days))
    elif duration_days > 365:
         # Even if not planning, > 1 year is too long
         validations.append(validate_duration(duration_days))

    # Only validate budget strictness if planning
    # If planning, budget MUST be > 0. If not planning (just chatting), ignore 0.
    if is_planning and budget_limit <= 0:
        validations.append((False, "To plan your trip, I need a budget estimate. How much are you looking to spend? (e.g. $1000, $3000, $5000)"))
    elif budget_limit > 0:
        validations.append(validate_budget(budget_limit, duration_days, trip_type))
        validations.append(validate_conflicting_requirements(budget_limit, duration_days, trip_type, destination))

    # Always check these
    validations.append(validate_group_size(user_query))
    validations.append(validate_travel_dates(user_query))
    
    # Collect all errors
    errors = [msg for is_valid, msg in validations if not is_valid and msg]
    
    if errors:
        result["has_edge_case"] = True
        result["error_message"] = "\n\n".join(errors)
        result["should_block"] = True
    
    return result
