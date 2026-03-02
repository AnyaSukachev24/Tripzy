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
import time

# Import the Graph
from app.graph import graph
from app.callbacks import CostCallbackHandler
from app.conversation_logger import conversation_logger, _safe_json_default


def _sse(data: dict) -> str:
    """Safely serialize a dict to SSE format, handling Pydantic models."""
    return f"data: {json.dumps(data, default=_safe_json_default)}\n\n"

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
        budget_warning = final_state.get("budget_warning")
        steps = final_state.get("steps", [])

        # Smart response selection: prefer real content over routing tags
        INTERNAL_TAGS = {"Plan Drafted", "Done", "None", ""}

        if plan:
            final_text = format_plan_to_markdown(plan)
            if budget_warning:
                final_text = f"⚠️ **Budget Note:** {budget_warning}\n\n{final_text}"
        elif instruction and instruction not in INTERNAL_TAGS:
            final_text = instruction
        else:
            # Fallback: last step response with real content
            final_text = "Task completed."
            for step in reversed(steps):
                resp = step.get("response", "")
                if resp and not any(resp.startswith(tag) for tag in ["Routing to", "Need more", "Edge Case", "Error"]):
                    final_text = resp
                    break

        return {
            "status": "ok",
            "response": final_text,
            "steps": steps,
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
    Includes heartbeat pings so the browser never drops the connection.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    input_payload = {"user_query": request.prompt}
    
    #  Log the user message
    conversation_logger.log_message(thread_id, "user", request.prompt)

    async def event_generator():
        final_response_content = None
        # Queue to pass events from the graph task to the generator
        queue: asyncio.Queue = asyncio.Queue()
        HEARTBEAT_INTERVAL = 8  # seconds between keepalive pings

        async def run_graph():
            """Runs the graph and puts events into the queue."""
            try:
                snapshot = graph.get_state(config)
                if snapshot.next:
                    # Resume an interrupted graph (e.g., Human Approval)
                    node_to_resume = snapshot.next[0]
                    graph.update_state(config, {"user_query": request.prompt}, as_node=node_to_resume)
                    payload_to_run = None
                else:
                    payload_to_run = input_payload
                    
                async for event in graph.astream_events(payload_to_run, config, version="v2"):
                    kind = event.get("event")
                    
                    if not kind:
                        continue

                    if kind == "on_chain_start" and event.get("name") == "LangGraph":
                        await queue.put({"type": "status", "content": "Starting Graph..."})
                    elif kind == "on_tool_start":
                        tool_name = event.get('name', 'Tool')
                        await queue.put({"type": "status", "content": f"Executing Tool: {tool_name}..."})
                    elif kind == "on_chain_end" and "node" in event.get("metadata", {}):
                        node_name = event["metadata"]["node"]
                        await queue.put({"type": "node_complete", "node": node_name})

                # Graph finished — get final state
                snapshot = graph.get_state(config)
                conversation_logger.log_state_snapshot(thread_id, dict(snapshot.values))

                if snapshot.next:
                    draft_plan = snapshot.values.get("trip_plan")
                    await queue.put({"type": "waiting_for_approval", "thread_id": thread_id, "preview": draft_plan})
                else:
                    final_state = snapshot.values
                    plan = final_state.get("trip_plan")
                    instruction = final_state.get("supervisor_instruction")
                    budget_warning = final_state.get("budget_warning")
                    steps = final_state.get("steps", [])

                    INTERNAL_TAGS = {"Plan Drafted", "Done", "None", "",
                                     "Plan Drafted (fallback - max research iterations reached)",
                                     "Plan Drafted (dedup guard - repeated tool call)",
                                     "Maximum revisions reached. Finalize the plan with the current best effort."}

                    final_text = "Task completed."

                    def _format_destinations_if_json(text: str, trip_type: str = "", preferences: list = None) -> str:
                        """Detect raw JSON destination arrays and format them as markdown."""
                        if not text:
                            return text
                        
                        raw = None
                        if isinstance(text, (list, dict)):
                            raw = text
                        else:
                            try:
                                stripped = text.strip()
                            except Exception:
                                return text
                            if not (stripped.startswith("[") or stripped.startswith("{")):
                                return text
                            try:
                                raw = json.loads(stripped)
                            except Exception:
                                # Fallback for truncated JSON (Azure OpenAI sometimes cuts off at 1000 chars)
                                import re
                                dest_matches = re.findall(r'"destination"\s*:\s*"([^"]+)"', stripped)
                                if dest_matches:
                                    raw = [{"destination": d} for d in dest_matches]
                                else:
                                    return text

                        # Only format if it looks like destination data
                        if isinstance(raw, list):
                            if not raw or not isinstance(raw[0], dict):
                                return text
                            if "destination" not in raw[0] and "title" not in raw[0]:
                                return text
                        elif isinstance(raw, dict):
                            if "destination" not in raw and "suggestions" not in raw:
                                return text
                        else:
                            return text

                        preferences = preferences or []  # Guard against None
                        trip_type = trip_type or ""      # Guard against None
                        print(f"  [FORMAT] Formatting {len(raw) if isinstance(raw, list) else 1} destinations as markdown (trip_type={trip_type!r}, prefs={preferences})")



                        # Emoji by trip type / preferences
                        EMOJI_MAP = {
                            "honeymoon": "💑", "romantic": "💑", "beach": "🏖️", "tropical": "🏖️",
                            "adventure": "🧗", "hiking": "🏔️", "mountain": "🏔️",
                            "cultural": "🏛️", "history": "🏛️", "temple": "🏯",
                            "family": "👨‍👩‍👧‍👦", "luxury": "✨", "budget": "💰",
                            "food": "🍜", "nature": "🌿", "wildlife": "🦁",
                            "ski": "⛷️", "snow": "❄️", "wellness": "🧘",
                        }
                        pref_lower = (trip_type + " " + " ".join(preferences)).lower()
                        icon = "✈️"
                        for kw, em in EMOJI_MAP.items():
                            if kw in pref_lower:
                                icon = em
                                break

                        lines = [f"## {icon} Here are some destination suggestions for you:\n"]
                        shown = []
                        items = raw if isinstance(raw, list) else raw.get("suggestions", [raw])

                        for item in items[:5]:
                            if isinstance(item, str):
                                continue
                            name = item.get("destination", item.get("title", "Unknown"))
                            if name in shown:
                                continue
                            shown.append(name)
                            summary = item.get("summary", item.get("description", ""))
                            summary = summary.replace("==", "").replace("===", "")
                            parts_s = [s.strip() for s in summary.split(".") if len(s.strip()) > 20]
                            blurb = ". ".join(parts_s[:2]).strip()
                            if blurb and not blurb.endswith("."):
                                blurb += "."
                            lines.append(f"### 📍 {name}")
                            if blurb:
                                lines.append(blurb)
                            source = item.get("source", "")
                            if source:
                                lines.append(f"*Source: {source}*")
                            lines.append("")

                        if not shown:
                            return "I couldn't find specific destinations. Could you tell me more about what you're looking for?"

                        if "honeymoon" in pref_lower or "romantic" in pref_lower:
                            q = "Which of these romantic destinations appeals to you most? 💕"
                        elif "adventure" in pref_lower or "hiking" in pref_lower:
                            q = "Which adventure destination sounds exciting to you? 🏔️"
                        elif "beach" in pref_lower or "tropical" in pref_lower:
                            q = "Which beach destination catches your eye? 🌊"
                        elif "cultural" in pref_lower or "history" in pref_lower:
                            q = "Which cultural destination interests you? 🏛️"
                        else:
                            q = "Which of these interests you, or would you like different options?"
                        lines.append(f"---\n{q}")
                        return "\n".join(lines)

                    if plan and plan.get("itinerary"):
                        final_text = format_plan_to_markdown(plan)
                        if budget_warning:
                            final_text = f"⚠️ **Budget Note:** {budget_warning}\n\n{final_text}"
                    elif instruction and instruction not in INTERNAL_TAGS:
                        trip_type = final_state.get("trip_type", "")
                        prefs = final_state.get("preferences", [])
                        final_text = _format_destinations_if_json(instruction, trip_type, prefs)
                    else:
                        for step in reversed(steps):
                            resp = step.get("response", "")
                            if resp and not any(resp.startswith(tag) for tag in
                                               ["Routing to", "Need more", "Edge Case", "Error", "Executing",
                                                "Plan Drafted", "Maximum revisions", "Forced routing"]):
                                trip_type = final_state.get("trip_type", "")
                                prefs = final_state.get("preferences", [])
                                final_text = _format_destinations_if_json(resp, trip_type, prefs)
                                break

                    if "System Error" in final_text and ("429" in final_text or "RESOURCE_EXHAUSTED" in final_text or "Too Many Requests" in final_text):
                        final_text = "⚠️ The AI service is temporarily busy (rate limit). Please wait a moment and try again."

                    conversation_logger.log_message(thread_id, "agent", final_text)
                    await queue.put({"type": "final_response", "content": final_text, "_saved": final_text})


            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f"  [STREAM ERROR] {error_trace}")
                error_msg = str(e)
                if "Errno 22" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "Too Many Requests" in error_msg:
                    error_msg = "⚠️ The AI service is temporarily busy (rate limit). Please wait a moment and try again."
                conversation_logger.log_message(thread_id, "error", f"Error: {error_msg}")
                await queue.put({"type": "error", "content": f"Error: {error_msg}"})
            finally:
                await queue.put(None)  # Sentinel: graph is done

        # Start graph in background
        graph_task = asyncio.create_task(run_graph())

        # Stream events + heartbeats
        last_ping = time.time()
        try:
            while True:
                # Try to get an event with a short timeout (for heartbeat)
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                except asyncio.TimeoutError:
                    # Send keepalive heartbeat comment (SSE comments are ignored by JS but keep connection alive)
                    yield ": heartbeat\n\n"
                    last_ping = time.time()
                    continue

                if event_data is None:  # Sentinel: done
                    break

                # Extract saved content for logging
                saved_content = event_data.pop("_saved", None)
                if saved_content:
                    final_response_content = saved_content
                    saved_path = conversation_logger.save_conversation(thread_id, final_response_content)
                    if saved_path:
                        print(f"[UI RUN SAVED] {saved_path}")

                yield _sse(event_data)

                if event_data.get("type") in ("final_response", "error"):
                    yield _sse({"type": "done"})

        except asyncio.CancelledError:
            graph_task.cancel()
        except Exception as e:
            yield _sse({"type": "error", "content": str(e)})
            yield _sse({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        }
    )

@app.post("/api/approve")
def approve_trip(request: ExecuteRequest):
    """
    Resumes the graph after a human approval interrupt.
    """
    if not request.thread_id:
        return JSONResponse(status_code=400, content={"error": "thread_id is required for approval."})
    
    config = {"configurable": {"thread_id": request.thread_id}}
    
    try:
        # Resuming with None input since we are just triggering the next step,
        # but we must tell the graph we approved the plan via update_state
        snapshot = graph.get_state(config)
        if snapshot.next:
            node_to_resume = snapshot.next[0]
            graph.update_state(config, {"user_query": "approve_trip_plan"}, as_node=node_to_resume)
            
        # Continue execution
        final_state_res = graph.invoke(None, config=config)
        # Note: graph.invoke returns a dict of the final state variables directly, not a snapshot object
        plan = final_state_res.get("trip_plan")
        
        return {
            "status": "ok",
            "response": format_plan_to_markdown(plan) if plan else "Trip finalized.",
            "steps": final_state_res.get("steps", [])
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
