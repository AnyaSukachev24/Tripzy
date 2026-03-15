import sys
import os
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

from app.tools import get_user_profile
from app.prompts.planner_prompt import get_planner_prompt

def test_tool():
    print("--- Testing get_user_profile Tool ---")
    # Test valid user
    # Note: Dependent on Pinecone data existing (we know 'profile_test_example_com' exists from earlier inspection)
    user_id = "test@example.com"
    print(f"Fetching for: {user_id}")
    try:
        # get_user_profile is a StructuredTool, so we must use .invoke
        profile = get_user_profile.invoke({"user_id": user_id})
        # The tool returns JSON string or dict? 
        # The implementation returns dict.
        
        if profile and profile.get("user_id") == user_id:
            print(f"✅ Tool retrieved profile for {user_id}")
            print(f"   Travel Style: {profile.get('travel_style')}")
            print(f"   Dietary: {profile.get('dietary_needs')}")
        else:
            print(f"❌ Tool failed to retrieve profile for {user_id} (might be empty if ID mismatch logic failed)")
            print(f"   Result: {profile}")
    except Exception as e:
        print(f"❌ Exception in tool: {e}")

    # Test invalid user
    bad_id = "nonexistent@user.com"
    # Again, use .invoke
    p2 = get_user_profile.invoke({"user_id": bad_id})
    if not p2:
        print(f"✅ Tool correctly returned empty/None for {bad_id}")
    else:
        print(f"❌ Tool returned data for nonexistent user: {p2}")

def test_prompt_template():
    print("\n--- Testing Planner Prompt Templates ---")
    types = ["Planning", "FlightOnly", "HotelOnly", "AttractionsOnly"]
    for t in types:
        prompt = get_planner_prompt(t)
        # Check for {user_profile} NOT {{user_profile}} because get_planner_prompt should return the ready-to-format string
        # Wait, f-string with {{var}} returns {var}.
        # So we check for "{user_profile}" literal in the output.
        if "{user_profile}" in prompt:
             print(f"✅ Prompt for '{t}' contains {{user_profile}} placeholder")
        else:
             print(f"❌ Prompt for '{t}' MISSING {{user_profile}} placeholder")

if __name__ == "__main__":
    test_tool()
    test_prompt_template()
