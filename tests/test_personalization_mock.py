import sys
import os
import json
from unittest.mock import MagicMock

# 1. Mock Dependencies (still need `langchain_community` chat models for graph imports?)
sys.modules["langchain_google_genai"] = MagicMock()
sys.modules["langchain_community.chat_models"] = MagicMock()
# Try to mock ALL tools import if possible
# But app.graph imports `app.tools`.

# 2. Mock app.tools module BEFORE import app.graph
mock_tools = MagicMock()
sys.modules["app.tools"] = mock_tools

# Setup mock function return value
mock_search = MagicMock()
mock_search.invoke.return_value = "User loves Sci-Fi and Sushi."
mock_tools.search_user_profile_tool = mock_search

# Also mock web_search_tool etc if app.graph uses them
mock_tools.web_search_tool = MagicMock()

# Mock dependencies used by app.graph directly
sys.modules["langchain_core"] = MagicMock() 
sys.modules["langchain_core"].__path__ = []
sys.modules["langchain_core.prompts"] = MagicMock() # For ChatPromptTemplate
sys.modules["langchain_core.output_parsers"] = MagicMock() 
# app.graph lines 4-9 imports
# from langgraph.checkpoint.memory import MemorySaver -> Need to mock langgraph too?
sys.modules["langgraph"] = MagicMock()
sys.modules["langgraph.checkpoint"] = MagicMock()
sys.modules["langgraph.checkpoint.memory"] = MagicMock()
sys.modules["langgraph.graph"] = MagicMock()
sys.modules["app.state"] = MagicMock()

# Import app.graph
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # We need to import app.graph logic. But since we mocked everything, can we test logic?
    # If app.graph imports fail, we can't test.
    # But wait, app.graph logic is what we want to test!
    # If we mock `app.graph` itself, we test nothing.
    # We want to import `app.graph`.
    
    # Reload or Import app.graph
    if "app.graph" in sys.modules:
        del sys.modules["app.graph"]
        
    from app.graph import profile_loader_node
    
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test_profile_loader():
    print("--- TESTING PROFILE LOADER ---")
    
    state = {}
    
    # Run Node
    # Since we mocked app.tools, profile_loader_node should use mock_tools.search_user_profile_tool
    result = profile_loader_node(state)
    
    # Verify
    profile = result.get("user_profile")
    if profile and "Sci-Fi" in profile.get("summary", ""):
        print("✅ SUCCESS: Profile loaded into state using Mock Tool.")
        print(f"Profile: {profile['summary']}")
    else:
        print("❌ FAILURE: Profile not loaded correctly.")
        print(result)

if __name__ == "__main__":
    test_profile_loader()
