import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json

# Import the Graph
from app.graph import graph

app = FastAPI(title="Tripzy Travel Agent (Course Project)")

# CORS (Allow all for Render/Testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---

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

class ExecuteRequest(BaseModel):
    prompt: str
    thread_id: Optional[str] = None

class ExecuteResponse(BaseModel):
    status: str
    response: str
    steps: List[Dict[str, Any]]
    error: Optional[str] = None

# --- ENDPOINTS ---

@app.get("/api/team_info", response_model=TeamInfoResponse)
def get_team_info():
    """Returns student details (Course Requirement)."""
    return {
        "group_batch_order_number": "BATCH_XX_ORDER_XX", # TODO: User to update
        "team_name": "Tripzy",
        "students": [
            {"name": "Student 1", "email": "s1@example.com"}, # TODO: User to update
            {"name": "Student 2", "email": "s2@example.com"},
        ]
    }

@app.get("/api/agent_info", response_model=AgentInfoResponse)
def get_agent_info():
    """Returns agent metadata (Course Requirement)."""
    return {
        "description": "Tripzy is an autonomous travel companion that plans detailed itineraries while strictly adhering to user budgets.",
        "purpose": "To plan end-to-end travel itineraries with real-time data and budget validation.",
        "prompt_template": {
            "template": "Plan a {days}-day trip to {destination} with a budget of {budget}."
        },
        "prompt_examples": [
            {
                "prompt": "Plan a 3-day trip to Paris for cheap.",
                "full_response": "Here is a budget-friendly Paris itinerary...",
                "steps": [
                    {"module": "Supervisor", "prompt": "...", "response": "Routing to Planner"},
                    {"module": "Planner", "prompt": "...", "response": "Drafting plan"},
                ]
            }
        ]
    }

@app.get("/api/model_architecture")
def get_model_architecture():
    """Returns the graph image (Course Requirement)."""
    try:
        # Generate PNG from LangGraph
        img_data = graph.get_graph().draw_mermaid_png()
        return Response(content=img_data, media_type="image/png")
    except Exception as e:
        return JSONResponse(
            status_code=500, 
            content={"error": f"Failed to generate graph image: {str(e)}"}
        )

@app.post("/api/execute", response_model=ExecuteResponse)
def execute_agent(request: ExecuteRequest):
    """
    Main Execution Endpoint. 
    Runs the LangGraph, captures steps, and returns the final response.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Input State
    input_payload = {"user_query": request.prompt}
    
    print(f"--- EXECUTE: {request.prompt} (Thread: {thread_id}) ---")
    
    try:
        # Run the Graph
        # We use invoke (blocking) for the API to get the final state
        final_state = graph.invoke(input_payload, config=config)
        
        # Extract Response
        # The 'Trip_Planner' usually produces the final plan, 
        # or the 'Supervisor' loops until done.
        # We look for the most specific instruction or plan update.
        
        plan = final_state.get("trip_plan")
        instruction = final_state.get("supervisor_instruction")
        
        # Construct Final Response Text
        if plan:
            final_text = f"Here is the plan: {json.dumps(plan, indent=2)}"
        elif instruction:
            final_text = instruction
        else:
            final_text = "Task completed."
            
        return {
            "status": "ok",
            "response": final_text,
            "steps": final_state.get("steps", []),
            "error": None
        }
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {
            "status": "error",
            "response": "An error occurred during execution.",
            "steps": [], # Should ideally return partial steps if possible
            "error": str(e)
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
