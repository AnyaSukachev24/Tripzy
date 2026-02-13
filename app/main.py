import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio

# Import the Graph
from app.graph import graph
from app.callbacks import CostCallbackHandler
from app.conversation_logger import conversation_logger

def format_plan_to_markdown(plan: Dict[str, Any]) -> str:
    """Converts the JSON trip plan into a readable Markdown string."""
    if not plan:
        return "No plan available."
        
    origin_city = plan.get('origin_city', '')
    dates = plan.get('dates', '')
    
    md = f"### Trip to {plan.get('destination', 'Unknown')}\n"
    if origin_city:
        md += f"**From:** {origin_city}\n"
    if dates:
        md += f"**Dates:** {dates}\n"
        
    md += f"**Budget Estimate:** ${plan.get('budget_estimate', 0)}\n\n"
    
    # --- FLIGHTS ---
    flights = plan.get('flights', [])
    if flights:
        md += "#### ✈️ Flight Options\n"
        for flight in flights:
            airline = flight.get('airline', 'Unknown Airline')
            price = flight.get('price', 'N/A')
            flight_num = flight.get('flight_number', '')
            link = flight.get('link', '#')
            
            details = f"**{airline}**"
            if flight_num:
                details += f" ({flight_num})"
            details += f" - {price}"
            
            if link and link != '#':
                md += f"- [{details}]({link})\n"
            else:
                md += f"- {details}\n"
        md += "\n"
        
    # --- HOTELS ---
    hotels = plan.get('hotels', [])
    if hotels:
        md += "#### 🏨 Accommodation Options\n"
        for hotel in hotels:
            name = hotel.get('name', 'Unknown Hotel')
            price = hotel.get('price', 'N/A')
            rating = hotel.get('rating', '')
            link = hotel.get('booking_link', '#')
            
            details = f"**{name}**"
            if rating:
                details += f" ({rating}★)"
            details += f" - {price}"
            
            if link and link != '#':
                md += f"- [{details}]({link})\n"
            else:
                md += f"- {details}\n"
        md += "\n"
    
    # --- ITINERARY ---
    md += "#### 📅 Itinerary\n"
    itinerary = plan.get('itinerary', [])
    if isinstance(itinerary, list):
        for item in itinerary:
            day = item.get('day', '?')
            activity = item.get('activity', 'No activity')
            cost = item.get('cost', 0)
            md += f"- **Day {day}**: {activity} (${cost})\n"
    
    return md

app = FastAPI(title="Tripzy Travel Agent (Course Project)")

# CORS (Allow all for Render/Testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

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
        "group_batch_order_number": "BATCH_XX_ORDER_XX", 
        "team_name": "Tripzy",
        "students": [
            {"name": "Student 1", "email": "s1@example.com"}, 
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
    input_payload = {"user_query": request.prompt}
    
    try:
        final_state = graph.invoke(input_payload, config=config)
        plan = final_state.get("trip_plan")
        instruction = final_state.get("supervisor_instruction")
        
        if plan:
            final_text = format_plan_to_markdown(plan)
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
        return {
            "status": "error",
            "response": "An error occurred during execution.",
            "steps": [],
            "error": str(e)
        }

@app.post("/api/stream")
async def stream_agent(request: ExecuteRequest):
    """
    Streaming Execution Endpoint (SSE).
    Yields events as they happen in the LangGraph.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    input_payload = {"user_query": request.prompt}
    
    #  Log the user message
    conversation_logger.log_message(thread_id, "user", request.prompt)

    async def event_generator():
        final_response_content = None
        try:
            async for event in graph.astream_events(input_payload, config, version="v2"):
                kind = event["event"]
                
                if kind == "on_chain_start" and event.get("name") == "LangGraph":
                    msg = {"type": "status", "content": "Starting Graph..."}
                    yield f"data: {json.dumps(msg)}\n\n"
                if kind == "on_chat_model_stream":
                    # We could stream tokens here if we wanted fine-grained output
                    pass
                elif kind == "on_tool_start":
                    tool_name = event.get('name', 'Tool')
                    msg = {"type": "status", "content": f"Executing Tool: {tool_name}..."}
                    yield f"data: {json.dumps(msg)}\n\n"
                elif kind == "on_chain_end" and "node" in event.get("metadata", {}):
                    node_name = event["metadata"]["node"]
                    # Optionally capture the state here if needed
                    yield f"data: {json.dumps({'type': 'node_complete', 'node': node_name})}\n\n"

            # CHECK FOR INTERRUPTS
            snapshot = graph.get_state(config)
            
            # Log state snapshot
            conversation_logger.log_state_snapshot(thread_id, dict(snapshot.values))
            
            if snapshot.next: # If there are nodes pending (like Human_Approval)
                # Send the draft plan for preview
                draft_plan = snapshot.values.get("trip_plan")
                yield f"data: {json.dumps({'type': 'waiting_for_approval', 'thread_id': thread_id, 'preview': draft_plan})}\n\n"
            else:
                # Final state retrieval for last response
                final_state = snapshot.values
                plan = final_state.get("trip_plan")
                instruction = final_state.get("supervisor_instruction")
                
                final_text = "Task completed."
                
                if plan:
                    final_text = format_plan_to_markdown(plan)
                elif instruction and instruction != "Done":
                    final_text = instruction
                else:
                    # Fallback: Content from the last step
                    steps = final_state.get("steps", [])
                    if steps:
                        last_step = steps[-1]
                        if last_step.get("response"):
                            final_text = last_step["response"]

                # Log the agent response
                conversation_logger.log_message(thread_id, "agent", final_text)
                final_response_content = final_text
                
                msg = {"type": "final_response", "content": final_text}
                yield f"data: {json.dumps(msg)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
            # Save conversation to file
            saved_path = conversation_logger.save_conversation(thread_id, final_response_content)
            if saved_path:
                print(f"[UI RUN SAVED] {saved_path}")
            
        except Exception as e:
            error_msg = str(e)
            conversation_logger.log_message(thread_id, "error", error_msg)
            conversation_logger.save_conversation(thread_id, {"error": error_msg})
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/approve")
def approve_trip(request: ExecuteRequest):
    """
    Resumes the graph after a human approval interrupt.
    """
    if not request.thread_id:
        return JSONResponse(status_code=400, content={"error": "thread_id is required for approval."})
    
    config = {"configurable": {"thread_id": request.thread_id}}
    
    try:
        # Resuming with None input since we are just triggering the next step
        final_state = graph.invoke(None, config=config)
        plan = final_state.get("trip_plan")
        
        return {
            "status": "ok",
            "response": format_plan_to_markdown(plan) if plan else "Trip finalized.",
            "steps": final_state.get("steps", [])
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
