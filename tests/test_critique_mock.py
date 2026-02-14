import sys
import os
import json
from unittest.mock import MagicMock

# 1. Mock Dependencies
sys.modules["langchain_google_genai"] = MagicMock()
sys.modules["langchain_community.chat_models"] = MagicMock()
sys.modules["langchain_community.tools"] = MagicMock()

# Mock LLMs
mock_llm = MagicMock()
mock_chain = MagicMock()
mock_llm.with_structured_output.return_value = mock_chain

# Mock Objects
class MockCritiqueOutput:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    decision = ""
    feedback = ""
    score = 0

# Scenario 1: Reject
output_reject = MockCritiqueOutput(decision="REJECT", feedback="Too expensive", score=4)
# Scenario 2: Approve
output_approve = MockCritiqueOutput(decision="APPROVE", feedback="Looks good", score=9)

mock_chain.invoke.side_effect = [output_reject, output_approve]

# Import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app.graph import critique_node
    import app.graph
    app.graph.llm = mock_llm
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test_critique_node():
    print("--- TESTING CRITIQUE NODE ---")
    
    state = {
        "supervisor_instruction": "Plan a cheap trip",
        "trip_plan": {"cost": 5000}, # Expensive!
        "budget": {"limit": 1000},
        "revision_count": 0
    }
    
    # 1. First Run (Expect Reject)
    print("\n[1] Running Critique (Expect REJECT)...")
    result1 = critique_node(state)
    print(f"Decision: {result1.get('critique_feedback')}")
    print(f"Next Step: {result1.get('next_step')}")
    
    if result1.get("next_step") == "Trip_Planner":
        print("✅ SUCCESS: Rejected plan loops back to Planner.")
    else:
        print("❌ FAILURE: Did not loop back.")

    # 2. Second Run (Expect Approve)
    print("\n[2] Running Critique (Expect APPROVE)...")
    # Simulate updated state
    state["revision_count"] = 1
    
    result2 = critique_node(state)
    print(f"Next Step: {result2.get('next_step')}")
    
    if result2.get("next_step") == "Supervisor":
        print("✅ SUCCESS: Approved plan proceeds to Supervisor.")
    else:
        print("❌ FAILURE: Did not proceed correctly.")

if __name__ == "__main__":
    test_critique_node()
