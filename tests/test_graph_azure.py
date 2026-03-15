import sys
import os
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.graph import graph

def test_graph_azure_integration():
    print("--- Testing Graph with Azure OpenAI ---")
    
    # Check if keys are present
    if not os.getenv("AZURE_OPENAI_API_KEY"):
        print("SKIPPING: AZURE_OPENAI_API_KEY not found in env.")
        return

    initial_state = {
        "user_query": "Plan a 3-day trip to Rome.",
        "steps": [],
        "revision_count": 0
    }
    
    config = {"configurable": {"thread_id": "test_azure_real"}}
    
    print("Invoking graph (this calls real Azure API)...")
    try:
        final_state = graph.invoke(initial_state, config=config)
        steps = final_state.get("steps", [])
        
        print(f"Total steps: {len(steps)}")
        for i, step in enumerate(steps):
             print(f"Step {i+1}: Node={step.get('module')}")
             # Print start of response to verify LLM generated something
             response = step.get('response', '')
             print(f"   Response: {response[:100]}...")

        if any("Planner" in s.get("module") for s in steps):
            print("SUCCESS: Planner executed using Azure!")
        else:
             print("WARNING: Planner did not execute. Check logs.")
             
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAILURE: {e}")

if __name__ == "__main__":
    test_graph_azure_integration()
