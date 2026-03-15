import sys
import os

sys.path.append(os.getcwd())

from app.graph import graph

def test_graph_structure():
    print("--- Inspecting Graph Structure ---")
    
    # Get the underlying graph definition
    g = graph.get_graph()
    
    # Check edges
    print("\nEdges:")
    for edge in g.edges:
        print(f"  {edge}")
        
    # We expect a conditional edge from Supervisor
    # In LangGraph compiled graph, conditional edges are represented as nodes?
    # Or simpler: verify we can visualize it.
    
    print("\nRepresentation:")
    try:
        g.print_ascii()
    except Exception as e:
        print(f"Could not print ascii: {e}")

if __name__ == "__main__":
    test_graph_structure()
