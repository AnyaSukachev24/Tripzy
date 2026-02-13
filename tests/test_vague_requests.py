
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.graph import graph
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

def run_test(query, description):
    print(f"\n=== TEST: {description} ===")
    print(f"Query: '{query}'")
    
    try:
        # Invoke the graph
        # For a fresh conversation, we just pass dictionaries or list of messages
        # The graph definition expects AgentState which has 'user_query'
        
        initial_state = {
            "user_query": query,
            "revision_count": 0,
            "steps": []
        }
        
        # We need a thread_id for checkpointer
        config = {"configurable": {"thread_id": "test_vague_1"}}
        
        result = graph.invoke(initial_state, config=config)
        
        print(f"Next Step: {result.get('next_step')}")
        print(f"Supervisor Instruction: {result.get('supervisor_instruction')}")
        
        # Check if the instruction is contextual (contains "honeymoon" etc if expected)
        return result
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

# Run tests
if __name__ == "__main__":
    print("Starting Vague Request Tests...")
    
    # 1. Missing Destination & Duration (Contextual: Honeymoon)
    # The topic logic in graph.py uses `trip_type` if detected by Supervisor LLM.
    # Supervisor needs to detect "honeymoon" from query.
    run_test("I want to plan a honeymoon trip.", "Missing Dest+Dur (Honeymoon)")
    
    # 2. Missing Destination (Contextual: Adventure)
    run_test("Plan a 5 day adventure trip.", "Missing Dest (Adventure)")
    
    # 3. Missing Duration (Contextual: Family)
    run_test("I want to take my family to Paris.", "Missing Dur (Family)")
    
    print("\nTests Complete.")
