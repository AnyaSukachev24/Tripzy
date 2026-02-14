import sys
import os
import json
from unittest.mock import MagicMock

# 1. Mock Missing Dependencies
sys.modules["langchain_google_genai"] = MagicMock()
sys.modules["langchain_community.chat_models"] = MagicMock()
sys.modules["langchain_community.tools"] = MagicMock() # For DuckDuckGo

# Mock LLMs
mock_llm = MagicMock()
mock_chain = MagicMock()
mock_llm.with_structured_output.return_value = mock_chain

# Mock Objects
class MockPlannerOutput:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    thought = ""
    call_researcher = ""
    final_response = ""
    update_plan = {}

# Scenario:
# 1. Planner asks for "Paris Museums"
# 2. Researcher runs (returns "Louvre is great")
# 3. Planner plans with "Louvre"

# We need side_effect for mock_chain.invoke to return different things in sequence
# But wait, logic is: Planner -> Researcher -> Supervisor -> Planner?
# In my graph update: Planner -> Researcher -> Supervisor -> Planner (via loop)
# So mock_chain will be called twice.

output_1 = MockPlannerOutput(
    thought="I need to know about museums.",
    call_researcher="Paris Museums",
    final_response="",
    update_plan={}
)

output_2 = MockPlannerOutput(
    thought="I have info about Louvre.",
    call_researcher="",
    final_response="",
    update_plan={"destination": "Paris", "itinerary": [{"activity": "Louvre"}]}
)

mock_chain.invoke.side_effect = [output_1, output_2]

# Ensure we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app.graph import planner_node, researcher_node
    import app.graph
    app.graph.llm = mock_llm
    
    # Mock Web Search Tool
    import app.tools
    app.tools.web_search_tool = MagicMock()
    app.tools.web_search_tool.invoke.return_value = "The Louvre is a famous museum in Paris."
    
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test_research_loop():
    print("--- TESTING PLANNER -> RESEARCHER LOOP ---")
    
    # Initial State
    state = {
        "supervisor_instruction": "Plan a trip to Paris",
        "next_step": "Trip_Planner",
        "steps": []
    }
    
    # 1. Run Planner (Should ask for research)
    print("\n[1] Running Planner...")
    update1 = planner_node(state)
    state.update(update1)
    
    # Custom State Merge Logic (Simplified)
    if "supervisor_instruction" in update1:
        state["supervisor_instruction"] = update1["supervisor_instruction"]
    if "next_step" in update1:
        state["next_step"] = update1["next_step"]
        
    print(f"Planner Output: Next Step = {state.get('next_step')}")
    print(f"Instruction: {state.get('supervisor_instruction')}")
    
    if state.get("next_step") == "Researcher":
        print("✅ Planner correctly requested research.")
    else:
        print("❌ Planner failed to request research.")
        return

    print("\n[2] Running Researcher...")
    # Simulate Researcher Output in State (since we mock Researcher Node or just manually add step)
    # The real Researcher Node adds a step.
    research_step = {"module": "Researcher", "response": "The Louvre is open 9am-6pm."}
    state["steps"].append(research_step)
    
    # 3. Run Planner Again (Should incorporate info)
    print("\n[3] Running Planner (Second Pass)...")
    planner_node(state)
    
    # Verify LLM was called with research_info
    # mock_chain is the chain object. mock_chain.invoke was called.
    # We check the arguments of the LAST call.
    call_args = mock_chain.invoke.call_args
    if call_args:
        inputs = call_args[0][0] # First arg is the dict input
        research_info = inputs.get("research_info")
        print(f"Planner Recieved Research Info: {research_info}")
        
        if "Louvre" in str(research_info):
            print("✅ SUCCESS: Planner received research data.")
        else:
            print("❌ FAILURE: Research data missing from Planner input.")
    else:
        print("❌ FAILURE: Planner chain was not invoked.")
    
if __name__ == "__main__":
    test_research_loop()
