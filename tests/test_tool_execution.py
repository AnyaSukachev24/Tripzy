import pytest
from app.graph import researcher_node
from typing import Dict, Any

# Mock state
def create_mock_state(instruction: str) -> Dict[str, Any]:
    return {"supervisor_instruction": instruction}

def test_researcher_parses_flight_command():
    # Instruction simulating what Planner node produces
    instruction = 'FLIGHTS: {"origin": "NYC", "dest": "LON", "date": "2024-06-01"} '
    
    result = researcher_node(create_mock_state(instruction))
    
    # Check logs/steps
    steps = result.get("steps", [])
    assert len(steps) > 0
    response = steps[0]["response"]
    
    # Verify tool was called (mock data should be present)
    assert "Flight Options:" in response
    assert "British Airways" in response or "Air France" in response or "EasyJet" in response # specific mock data check
    assert "NYC" in response # origin check

def test_researcher_parses_hotel_command():
    # Instruction simulating what Planner node produces
    instruction = 'HOTELS: {"city": "Paris", "in": "2024-06-01", "out": "2024-06-07", "budget": "luxury"}'
    
    result = researcher_node(create_mock_state(instruction))
    
    steps = result.get("steps", [])
    assert len(steps) > 0
    response = steps[0]["response"]
    
    assert "Hotel Options:" in response
    assert "Paris" in response
    assert "Luxury" in response or "Grand" in response # check for luxury keywords

def test_researcher_parses_combined_command():
    # Combined instruction
    instruction = 'FLIGHTS: {"origin": "LAX", "dest": "TYO", "date": "2024-07-01"} HOTELS: {"city": "Tokyo", "in": "2024-07-01", "out": "2024-07-10", "budget": "medium"}'
    
    result = researcher_node(create_mock_state(instruction))
    
    steps = result.get("steps", [])
    response = steps[0]["response"]
    
    # Should contain BOTH
    assert "Flight Options:" in response
    assert "Hotel Options:" in response
    assert "Tokyo" in response
    assert "LAX" in response

if __name__ == "__main__":
    # Manually run if executed directly
    try:
        test_researcher_parses_flight_command()
        print("✓ Flight command test passed")
        test_researcher_parses_hotel_command()
        print("✓ Hotel command test passed")
        test_researcher_parses_combined_command()
        print("✓ Combined command test passed")
    except AssertionError as e:
        print(f"✗ Test failed: {e}")
    except Exception as e:
        print(f"✗ Runtime error: {e}")
