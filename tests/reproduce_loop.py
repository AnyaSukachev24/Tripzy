import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.graph import graph
from langchain_core.messages import HumanMessage

def test_loop():
    print("Starting Loop Reproduction Test...")
    
    # query = "i want to take my husbend to a romantic honymoon - give me ideas"
    query = "Suggest a romantic honeymoon destination" 
    
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "revision_count": 0,
        "steps": []
    }
    
    try:
        # We expect this to fail with recursion limit if not fixed
        config = {"recursion_limit": 10, "configurable": {"thread_id": "test_loop_1"}} # Set low limit to fail fast
        print(f"Invoking graph with query: '{query}' and recursion_limit=10")
        
        events = list(graph.stream(initial_state, config=config))
        
        print("\n--- Execution Finished ---")
        for event in events:
            for key, value in event.items():
                print(f"Node: {key}")
                if "next_step" in value:
                    print(f"  Next Step: {value['next_step']}")
                    
        print("\nSuccess: Graph finished without recursion error.")
        
    except Exception as e:
        print(f"\nCaught Expected Error: {e}")
        if "Recursion limit" in str(e):
             print("SUCCESS: Reproduction confirmed. Recursion limit hit as expected.")
        else:
             print("FAILURE: Unexpected error.")
             raise e

if __name__ == "__main__":
    test_loop()
