from app.graph import graph

config = {"configurable": {"thread_id": "loop_test_2"}}
inputs = {"user_query": "I want to go on a honeymoon for up to 14 days, somewhere warm, maybe Italy or Greece. Starting from New York. Budget is $8000."}

for event in graph.stream(inputs, config, stream_mode="updates"):
    for node_name, node_state in event.items():
        if node_name == "Trip_Planner":
            print("\n[Trip_Planner]")
            if "steps" in node_state and len(node_state["steps"]) > 0:
                print("Last step:", node_state["steps"][-1])
        elif node_name == "Researcher":
            print("\n[Researcher]")
            if "supervisor_instruction" in node_state:
                print("Instruction:", node_state["supervisor_instruction"][:500])
        elif node_name == "Critique":
            print("\n[Critique]")
            if "critique_feedback" in node_state:
                print("Feedback:", node_state["critique_feedback"][:500])
