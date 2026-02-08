import sys
import os
from unittest.mock import MagicMock

# Mock DuckDuckGoSearchRun before importing app.tools 
# (Optionally, we can try real first, but let's mock for stability in this environment)
sys.modules["langchain_community.tools"] = MagicMock()
mock_ddg = MagicMock()
sys.modules["langchain_community.tools"].DuckDuckGoSearchRun.return_value = mock_ddg
mock_ddg.invoke.return_value = "Paris is the capital of France. Wikivoyage: Paris has many museums."

# Set path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.tools import web_search_tool

def test_web_search():
    print("--- TESTING WEB SEARCH TOOL ---")
    query = "Paris things to do"
    
    try:
        result = web_search_tool.invoke(query)
        print(f"Query: {query}")
        print(f"Result: {result}")
        
        if "Paris" in result:
            print("✅ SUCCESS: Tool returned data.")
        else:
            print("❌ FAILURE: Tool returned unexpected data.")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    test_web_search()
