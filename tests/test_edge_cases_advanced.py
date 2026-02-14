
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.edge_case_validator import process_edge_cases

def test_zero_budget_planning():
    """Test that 0 budget blocks planning"""
    print("\n--- TEST: Zero Budget (Planning) ---")
    result = process_edge_cases(
        user_query="Plan a trip",
        duration_days=5,
        budget_limit=0,
        budget_currency="USD",
        trip_type="leisure",
        destination="Paris",
        is_planning=True
    )
    print(f"Result: {result}")
    assert result["has_edge_case"] == True
    assert "budget estimate" in result["error_message"]
    print("PASS")

def test_zero_budget_discovery():
    """Test that 0 budget DOES NOT block discovery"""
    print("\n--- TEST: Zero Budget (Discovery) ---")
    result = process_edge_cases(
        user_query="Where should I go?",
        duration_days=0,
        budget_limit=0,
        budget_currency="USD",
        trip_type="",
        destination="",
        is_planning=False
    )
    print(f"Result: {result}")
    assert result["has_edge_case"] == False
    print("PASS")

def test_extreme_low_budget():
    """Test $20 budget rejection"""
    print("\n--- TEST: Extreme Low Budget ($20) ---")
    result = process_edge_cases(
        user_query="Cheap trip",
        duration_days=7,
        budget_limit=20,
        budget_currency="USD",
        trip_type="budget",
        destination="Anywhere",
        is_planning=True
    )
    print(f"Result: {result}")
    assert result["has_edge_case"] == True
    assert "insufficient" in result["error_message"]
    print("PASS")

def test_conflicting_requirements():
    """Test Luxury on Low Budget"""
    print("\n--- TEST: Luxury on Low Budget ---")
    result = process_edge_cases(
        user_query="Luxury trip",
        duration_days=5,
        budget_limit=500, # $100/day
        budget_currency="USD",
        trip_type="luxury",
        destination="Dubai",
        is_planning=True
    )
    print(f"Result: {result}")
    assert result["has_edge_case"] == True
    assert "Conflicting requirements" in result["error_message"]
    print("PASS")

def test_large_group():
    """Test Large Group detection"""
    print("\n--- TEST: Large Group (100 pax) ---")
    result = process_edge_cases(
        user_query="Trip for 100 people to Costa Rica",
        duration_days=5,
        budget_limit=50000,
        budget_currency="USD",
        trip_type="corporate",
        destination="Costa Rica",
        is_planning=True
    )
    print(f"Result: {result}")
    assert result["has_edge_case"] == True
    assert "Large group" in result["error_message"]
    print("PASS")

def test_past_dates():
    """Test Past Dates detection"""
    print("\n--- TEST: Past Dates ---")
    result = process_edge_cases(
        user_query="I want to leave yesterday",
        duration_days=5,
        budget_limit=5000,
        budget_currency="USD",
        trip_type="leisure",
        destination="Paris",
        is_planning=True
    )
    print(f"Result: {result}")
    assert result["has_edge_case"] == True
    assert "past dates" in result["error_message"]
    print("PASS")

if __name__ == "__main__":
    test_zero_budget_planning()
    test_zero_budget_discovery()
    test_extreme_low_budget()
    test_conflicting_requirements()
    test_large_group()
    test_past_dates()
    print("\nALL TESTS PASSED")
