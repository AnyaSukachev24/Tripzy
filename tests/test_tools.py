
import os
import sys
import json
import json
# import pytest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools import search_flights_tool, search_hotels_tool
from app.graph import researcher_node

def test_flight_tool_isolated():
    """Test flight tool in isolation (mock mode)"""
    print("\n=== Testing Flight Tool (Isolated) ===")
    result = search_flights_tool.invoke({
        "origin": "LON",
        "destination": "PAR",
        "departure_date": "2024-06-01"
    })
    print(f"Result: {result}")
    
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) > 0
    assert "price" in data[0]
    assert "airline_name" in data[0]
    print("✅ Flight Tool Structure Verified")

def test_hotel_tool_isolated():
    """Test hotel tool in isolation (mock mode)"""
    print("\n=== Testing Hotel Tool (Isolated) ===")
    result = search_hotels_tool.invoke({
        "city": "Paris",
        "check_in": "2024-06-01",
        "check_out": "2024-06-07",
        "budget": "luxury"
    })
    print(f"Result: {result}")
    
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) > 0
    assert "name" in data[0]
    assert "price_per_night" in data[0]
    print("✅ Hotel Tool Structure Verified")

def test_researcher_node_parsing():
    """Test that researcher node parses instruction strings correctly"""
    print("\n=== Testing Researcher Node Parsing ===")
    
    # Mock state with FLIGHTS instruction
    flight_instruction = 'Check availability. FLIGHTS: {"origin": "NYC", "dest": "LON", "date": "2024-12-25"}'
    state = {"supervisor_instruction": flight_instruction}
    
    result = researcher_node(state)
    steps = result.get("steps", [])
    assert len(steps) > 0
    log = steps[0]
    
    print(f"Researcher Response: {log['response']}")
    assert "Flight Options" in log["response"]
    assert "NYC" in log["response"] # In output or input echo
    assert "LON" in log["response"]
    print("✅ Researcher Node Flight Parsing Verified")
    
    # Mock state with HOTELS instruction
    hotel_instruction = 'Find place. HOTELS: {"city": "London", "in": "2024-12-25", "out": "2024-12-30", "budget": "cheap"}'
    state = {"supervisor_instruction": hotel_instruction}
    
    result = researcher_node(state)
    steps = result.get("steps", [])
    log = steps[0]
    
    print(f"Researcher Response: {log['response']}")
    assert "Hotel Options" in log["response"]
    assert "London" in log["response"]
    print("✅ Researcher Node Hotel Parsing Verified")

if __name__ == "__main__":
    test_flight_tool_isolated()
    test_hotel_tool_isolated()
    test_researcher_node_parsing()
    print("\n🎉 ALL TOOL TESTS PASSED")
