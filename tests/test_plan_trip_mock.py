import sys
import os
import json
from unittest.mock import MagicMock

# 1. Mock Missing Dependencies BEFORE import
sys.modules["langchain_google_genai"] = MagicMock()
sys.modules["langchain_community.chat_models"] = MagicMock()

# Mock Pydantic models used in graph.py
# (Actually, pydantic is likely installed, so we can use real one if needed, but let's just mock output)

# Prepare Mock LLM Chain
mock_llm = MagicMock()
mock_chain = MagicMock()
mock_llm.with_structured_output.return_value = mock_chain

# Structure of PlannerOutput (Pydantic model mock)
class MockPlannerOutput:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    
    thought = "Thinking..."
    call_researcher = ""
    final_response = "Here is the plan."
    update_plan = {"destination": "Paris", "budget": 1000}

mock_chain.invoke.return_value = MockPlannerOutput(
    thought="Thinking...",
    call_researcher="",
    final_response="Here is the plan.",
    update_plan={"destination": "Paris", "budget": 1000}
)

# Inject mock into app.graph (via sys.modules trick requires importing graph first? No)
# We need to ensure when app.graph imports ChatGoogleGenerativeAI, it gets our mock.
# We did that with sys.modules above.

# Ensure we can import app.state
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import Node
try:
    # Use real imports for logic, but mocks for LLM
    from app.graph import planner_node
    # Update global 'llm' in app.graph to be our mock
    import app.graph
    app.graph.llm = mock_llm
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test_planner_node_direct():
    print("--- TESTING PLANNER NODE (MOCKED) ---")
    
    state = {
        "user_query": "Plan a trip",
        "supervisor_instruction": "Plan a trip to Paris",
        "critique_feedback": None,
        "user_profile": None,
        "trip_plan": None,
        "budget": None
    }
    
    try:
        result = planner_node(state)
        # Verify
        if "trip_plan" in result:
            print("\n✅ SUCCESS: Planner Node produced a plan.")
            print(json.dumps(result["trip_plan"], indent=2, default=str))
        else:
            print("\n❌ FAILURE: No plan produced.")
            print(result)
            
    except Exception as e:
        print(f"Execution Error: {e}")

if __name__ == "__main__":
    test_planner_node_direct()
