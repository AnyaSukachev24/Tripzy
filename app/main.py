from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from app.graph import graph
from fastapi.responses import Response
import uuid

app = FastAPI(title="Tripzy Travel Agent")

# --- Models ---


class Student(BaseModel):
    name: str
    email: str


class TeamInfoResponse(BaseModel):
    group_batch_order_number: str
    team_name: str
    students: List[Student]


class AgentInfoResponse(BaseModel):
    description: str
    purpose: str
    prompt_template: Dict[str, str]
    prompt_examples: List[Dict[str, Any]]


# --- Endpoints ---


@app.get("/api/team_info", response_model=TeamInfoResponse)
def get_team_info():
    """
    Returns student details.
    """
    return {
        "group_batch_order_number": "1_1",  # Placeholder
        "team_name": "Tripzy Team",
        "students": [
            {"name": "Student A", "email": "a@example.com"},
            {"name": "Student B", "email": "b@example.com"},
            {"name": "Student C", "email": "c@example.com"},
        ],
    }


@app.get("/api/agent_info", response_model=AgentInfoResponse)
def get_agent_info():
    """
    Returns agent meta + how to use it.
    """
    return {
        "description": "Tripzy is an AI travel agent designed to help users plan their perfect trip by understanding their needs, researching options, and drafting personalized proposals.",
        "purpose": "To autonomously solve travel planning problems by leveraging AI reasoning.",
        "prompt_template": {
            "template": "Plan a trip to {destination} for {days} days with a budget of {budget}."
        },
        "prompt_examples": [
            {
                "prompt": "I want to go to Paris for 5 days with $2000.",
                "full_response": "Here is a personalized itinerary for your trip to Paris...",
                "steps": [],
            }
        ],
    }


class ExecuteRequest(BaseModel):
    prompt: str
    thread_id: Optional[str] = "default_thread"


@app.post("/api/execute")
def execute_agent(request: ExecuteRequest):
    """
    Executes the agent. Handles both new requests and 'Resume' approvals.
    """
    # Generate ID if missing (Stateless Bot compatibility)
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Prepare Input
    # We allow 'user_query' to update so "Yes" is injected during resume
    input_payload = {"user_query": request.prompt}

    # Execute Graph
    # If it hits 'Human_Approval', it will stop and return safely.
    final_state = None
    try:
        final_state = graph.invoke(input_payload, config=config)
    except Exception as e:
        # LangGraph might raise an interrupt error in some versions,
        # but usually just stops. We catch generic errors just in case.
        print(f"Graph Execution Interrupted or Error: {e}")

    # Check Status using Snapshot (The Source of Truth)
    snapshot = graph.get_state(config)

    # 1. CHECK FOR PAUSE
    if snapshot.next and "Human_Approval" in snapshot.next:
        # We are paused! Fetch the response from the *previous* node (Action_Executor)
        last_step_response = snapshot.values.get(
            "final_response", "Waiting for approval..."
        )
        return {
            "status": "needs_approval",
            "response": last_step_response,
            "steps": snapshot.values.get("steps", []),
            "thread_id": thread_id,  # Client MUST send this back to resume!
        }

    # 2. NORMAL SUCCESS
    # If final_state is None (due to strict interrupt), use snapshot values
    result_state = final_state if final_state else snapshot.values

    return {
        "status": "success",
        "response": result_state.get("final_response", "Task Complete."),
        "steps": result_state.get("steps", []),
        "thread_id": thread_id,
    }


@app.get("/api/model_architecture", responses={200: {"content": {"image/png": {}}}})
def get_model_architecture():
    """
    Returns the architecture diagram as an image (PNG).
    """
    try:
        image_data = graph.get_graph().draw_mermaid_png()
        return Response(content=image_data, media_type="image/png")
    except Exception as e:
        # Fallback if mermaid rendering fails (e.g. missing tools) or graph issue
        return Response(
            content=f"Error generating graph: {str(e)}".encode(), status_code=500
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
