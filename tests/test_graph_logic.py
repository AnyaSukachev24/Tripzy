import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

# Mock the LLM before importing graph
with patch('langchain_openai.ChatOpenAI.invoke') as mock_llm_invoke:
    # Setup mock response for Supervisor
    # SupervisorOutput structure: next_step, reasoning, instruction
    class MockSupervisorOutput:
        next_step = "Trip_Planner"
        reasoning = "User wants a plan."
        instruction = "Plan a trip to Paris."
        
    class MockPlannerOutput:
        thought = "Planning thoughts..."
        call_researcher = ""
        final_response = "Here is the plan for Paris."
        update_plan = {"destination": "Paris"}

    # We need to mock the chain.invoke, not just llm.invoke, because .with_structured_output is complex
    # But patching llm class is easier if we can control what it returns.
    # Actually, let's just patch the graph nodes? 
    # No, nodes are functions.
    
    from app.graph import graph
    
    # Reset mock to handle different calls if possible, or just be permissive.
    # The graph nodes build chains. 
    # chain = prompt | llm.with_structured_output(...)
    
    # It's cleaner to just patch the 'llm' object in app.graph?
    from app import graph as graph_module
    
    # Mock the LLM object's with_structured_output method to return a runnable that returns our object
    mock_runnable = MagicMock()
    mock_runnable.invoke.side_effect = [
        MockSupervisorOutput(), # First call (Supervisor)
        MockPlannerOutput()     # Second call (Planner)
    ]
    
    # We need to replace the llm object in graph_module so that when nodes loop they use our mock
    # But wait, 'llm' is already used to create chains in the node functions?
    # No, the node functions access the global 'llm' variable.
    graph_module.llm = MagicMock()
    graph_module.llm.with_structured_output.return_value = mock_runnable


    def test_graph_routing():
        print("--- Testing Graph Routing (Mocked) ---")
        
        initial_state = {
            "user_query": "Plan a 3-day trip to Paris.",
            "steps": [],
            "revision_count": 0
        }
        
        config = {"configurable": {"thread_id": "test_thread_mock"}}
        
        print("Invoking graph...")
        try:
            final_state = graph.invoke(initial_state, config=config)
            
            steps = final_state.get("steps", [])
            print(f"Total steps: {len(steps)}")
            
            # Print steps to verify flow
            for i, step in enumerate(steps):
                print(f"Step {i+1}: Node={step.get('module')}")
                
            modules = [s.get("module") for s in steps]
            
            if "Supervisor" in modules and "Planner" in modules:
                print("SUCCESS: Supervisor routed to Planner!")
            else:
                print(f"FAILURE: Execution flow was {modules}")
                
            if "Here is the plan for Paris." in str(steps):
                print("SUCCESS: Final response found in steps.")
                
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_graph_routing()
