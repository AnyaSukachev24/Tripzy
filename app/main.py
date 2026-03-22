import os
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
from app.graph import graph, _classify_error
from app.callbacks import CostCallbackHandler
from app.conversation_logger import conversation_logger, _safe_json_default


def _sse(data: dict) -> str:
    """Safely serialize a dict to SSE format, handling Pydantic models."""
    return f"data: {json.dumps(data, default=_safe_json_default)}\n\n"


def format_plan_to_markdown(plan: Dict[str, Any]) -> str:
    """Converts the JSON trip plan into a readable Markdown string."""
    if not plan:
        return "No plan available."

    origin_city = plan.get("origin_city", "")
    dates = plan.get("dates", "")
    duration = plan.get("duration_days", "")
    budget_curr = plan.get("budget_currency", "USD")
    trip_type = plan.get("trip_type", "")
    travelers = plan.get("travelers", "")

    md = f"### Trip to {plan.get('destination', 'Unknown')}\n"
    if origin_city:
        md += f"**From:** {origin_city}\n"
    if dates:
        md += f"**Dates:** {dates}\n"
    if duration:
        md += f"**Duration:** {duration} days\n"
    if travelers:
        md += f"**Travelers:** {travelers}\n"
    if trip_type:
        md += f"**Trip Type:** {trip_type}\n"

    md += f"**Budget Estimate:** {plan.get('budget_estimate', 0)} {budget_curr}\n\n"

    # --- FLIGHTS ---
    flights = plan.get("flights", [])
    if not flights:
        # Fallback to the new strongly-typed Flight objects
        if plan.get("outbound_flight"):
            flights.append(plan["outbound_flight"])
        if plan.get("return_flight"):
            flights.append(plan["return_flight"])

    if flights:
        md += "#### ✈️ Flight Options\n"
        for flight in flights:
            airline = flight.get("airline", flight.get("source", "Unknown Airline"))
            orig = flight.get("origin", "")
            dest = flight.get("destination", "")
            price = flight.get("price", "N/A")
            flight_num = flight.get("flight_number", "")
            duration = flight.get("duration", "")
            date = flight.get("date", "")
            is_direct = flight.get("is_direct")
            link = flight.get("link", "#")

            details = f"**{airline}**"
            if flight_num:
                details += f" ({flight_num})"
            if orig and dest:
                details += f" | {orig} ➔ {dest}"
            details += f" - ${price}"
            if date:
                details += f" on {date}"
            if duration:
                details += f" ({duration})"
            if is_direct is not None:
                details += f" {'(Direct)' if is_direct else '(1+ Stops)'}"

            if link and link != "#":
                md += f"- [{details}]({link})\n"
            else:
                md += f"- {details}\n"
        md += "\n"

    # --- HOTELS ---
    hotels = plan.get("hotels", [])
    if hotels:
        md += "#### 🏨 Accommodation Options\n"
        for hotel in hotels:
            name = hotel.get("name", "Unknown Hotel")
            price = hotel.get("price", "N/A")
            rating = hotel.get("rating", "")
            link = hotel.get("booking_link", "#")

            details = f"**{name}**"
            if rating:
                details += f" ({rating}★)"
            details += f" - {price}"

            if link and link != "#":
                md += f"- [{details}]({link})\n"
            else:
                md += f"- {details}\n"
        md += "\n"

    return md


app = FastAPI(title="Tripzy Travel Agent (Course Project)")

# CORS — restrict to known origins; set ALLOWED_ORIGINS env var for production
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_root():
    return FileResponse("static/index.html")


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
    response: Optional[str]
    steps: List[Dict[str, Any]]
    error: Optional[str] = None
    error_code: Optional[str] = None


# --- ENDPOINTS ---


@app.get("/api/team_info")
def get_team_info():
    """Returns student details (Course Requirement)."""
    students = [
        {"name": "Noa Levi", "email": "noa-levi@campus.technion.ac.il"},
        {"name": "Anya Sukachev", "email": "anya.sukachev@campus.technion.ac.il"},
        {"name": "Alexa Birenbaum", "email": "alexab@campus.technion.ac.il"},
        {"name": "Refael Levi", "email": "refaell@campus.technion.ac.il"},
    ]
    students_lines = ",\n    ".join(json.dumps(s) for s in students)
    body = (
        '{\n'
        '  "group_batch_order_number": "3_2",\n'
        '  "team_name": "Tripzy",\n'
        '  "students": [\n'
        f'    {students_lines}\n'
        '  ]\n'
        '}'
    )
    return Response(content=body, media_type="application/json")


@app.get("/api/agent_info", response_model=AgentInfoResponse)
def get_agent_info():
    """Returns agent metadata (Course Requirement)."""
    return {
        "description": (
            "Tripzy is a multi-agent AI travel companion that handles end-to-end trip planning. "
            "It searches for real-time flights (via Amadeus API), hotels (via SerpApi/Google Hotels), "
            "and local attractions (via semantic RAG over a curated knowledge base). "
            "A Supervisor LLM orchestrates a network of specialized agents—Trip_Planner, Researcher, "
            "Attractions, and Critique—managing multi-turn clarification, budget enforcement, and "
            "combined flight+hotel requests across a single conversation."
        ),
        "purpose": (
            "To plan personalized, budget-aware travel itineraries by combining live flight/hotel data "
            "with curated destination knowledge. Tripzy supports flight-only searches, hotel-only searches, "
            "combined flight+hotel planning, full multi-day itinerary generation, and attraction/activity "
            "discovery—all through a conversational interface that asks clarifying questions when needed."
        ),
        "prompt_template": {
            "flight_search": "Find me flights from {origin} to {destination} departing on {date} for {travelers} traveler(s)",
            "hotel_search": "Find me hotels in {destination} from {check_in} to {check_out} with a {budget} budget",
            "full_trip": "Plan a {days}-day trip to {destination} from {origin}, departing {date}, budget {budget}",
            "attractions": "Find {activity_type} activities in {destination}",
        },
        "prompt_examples": [
            # ── Example 1: Multi-turn flight search – Bali from Berlin (run1) ────────
            {
                "prompt": "I want a 7-day vacation in Bali, help me find flights",
                "full_response": (
                    "Recommended flight for your 7-day Bali trip (Berlin \u2192 Bali)\n\n"
                    "I found a round-trip option that matches your dates (departing 24 Mar 2026, returning 31 Mar 2026) "
                    "and a 7-day duration. Summary:\n"
                    "- Total price (round-trip): EUR 978.49\n"
                    "- Travelers: 1\n"
                    "- Outbound: BER \u2192 DPS, 24 Mar 2026, departs BER 16:30, arrives DPS 20:20 (local next day), "
                    "duration ~20h50, 1 connection (AMS) \u2014 operated by KLM. Not direct.\n"
                    "- Return: DPS \u2192 BER, 31 Mar 2026, departs DPS 15:15, arrives BER 11:55 (1 Apr 2026), "
                    "duration ~26h40, 2 connections (SIN, CDG) \u2014 operated by Air France on return CDG\u2192BER. Not direct.\n\n"
                    "Notes:\n"
                    "- Price shown (EUR 978.49) is the total round-trip. "
                    "A checked bag option is listed at an additional EUR 75 on some fares.\n"
                    "- Connection times: outbound has a comfortable ~2h45 connection in Amsterdam (AMS). "
                    "Return has comfortable layovers (including ~4h at CDG before the final leg).\n\n"
                    "If you want, I can hold/book this fare, check baggage options, or show alternative "
                    "times/cheaper carriers (Qatar Airways option available at EUR 1,043.75). "
                    "Which would you like next?"
                ),
                "steps": [
                    {
                        "module": "Supervisor",
                        "prompt": "I want a 7-day vacation in Bali, help me find flights",
                        "response": (
                            "Routing to End: User asked for flights to Bali and gave a 7-day duration but did not "
                            "provide an origin city or departure date, so we must ask for the origin first."
                        ),
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "berlin",
                        "response": (
                            "Routing to End: User answered origin as 'Berlin'; "
                            "departure_date is still missing for the flight search."
                        ),
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "24 march",
                        "response": (
                            "Routing to Trip_Planner: User provided departure date and origin; all required "
                            "flight fields for FlightOnly are present so proceed to Trip_Planner."
                        ),
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": (
                            "Search for round-trip flights from Berlin to Bali departing 2026-03-24 for 1 traveler, "
                            "returning after 7 nights (check 31 March 2026 return), economy class unless specified, "
                            "budget unknown."
                        ),
                        "response": "Executing Tools...",
                    },
                    {
                        "module": "Researcher",
                        "prompt": "Executing resolve_airport_code_tool: {'keyword': 'Berlin'}",
                        "response": '[{"iataCode": "BER", "name": "Berlin", "cityName": "Berlin", "type": "AIRPORT"}]',
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": 'Tool Result (resolve_airport_code_tool): [{"iataCode": "BER", "name": "Berlin", "cityName": "Berlin", "type": "AIRPORT"}]',
                        "response": "Executing Tools...",
                    },
                    {
                        "module": "Researcher",
                        "prompt": "Executing resolve_airport_code_tool: {'keyword': 'Bali'}",
                        "response": '[{"iataCode": "DPS", "name": "Bali", "cityName": "Bali", "type": "AIRPORT"}]',
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": 'Tool Result (resolve_airport_code_tool): [{"iataCode": "DPS", "name": "Bali", "cityName": "Bali", "type": "AIRPORT"}]',
                        "response": "Executing Tools...",
                    },
                    {
                        "module": "Researcher",
                        "prompt": "Executing search_flights_tool: {'origin': 'BER', 'destination': 'DPS', 'departure_date': '2026-03-24', 'return_date': '2026-03-31', 'adults': 1, 'currency': 'EUR'}",
                        "response": (
                            "Aggregated 5 flights from Amadeus "
                            "(best: KLM BER\u2192DPS EUR 978.49 round-trip, 1 connection AMS)"
                        ),
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": "Tool Result (search_flights_tool): [Amadeus round-trip flight data BER\u2192DPS 2026-03-24]",
                        "response": (
                            "Recommended flight for your 7-day Bali trip: KLM round-trip BER\u2192DPS, EUR 978.49, "
                            "departing 24 Mar 2026 16:30. Plan submitted."
                        ),
                    },
                ],
            },
            # ── Example 2: Attractions search – Tokyo spas for couples (run2) ────────
            {
                "prompt": "Find me spas in Tokyo, I'm looking for a relaxing weekend with my girlfriend",
                "full_response": (
                    "**Waho-An NATURE Tokyo** \u2014 A healing-focused spa that offers targeted treatments "
                    "designed to deliver deep relaxation and recovery, perfect for a restorative weekend together.\n\n"
                    "**LaQua** \u2014 A popular Tokyo water and amusement complex with relaxing facilities and "
                    "atmosphere, making it an easy choice for a leisurely, spa-like weekend outing.\n\n"
                    "**ASMR TWIX TOKYO HEAD SPA** \u2014 A specialty head spa that uses ASMR-style techniques "
                    "and calming treatments to create an intimate, deeply relaxing experience for couples.\n\n"
                    "---\n\u2708\ufe0f Enjoy your trip! Safe travels from the Tripzy team. \U0001f30d"
                ),
                "steps": [
                    {
                        "module": "Supervisor",
                        "prompt": "Find me spas in Tokyo, I'm looking for a relaxing weekend with my girlfriend",
                        "response": (
                            "Routing to Attractions: User asked for spas in Tokyo for a relaxing weekend with their "
                            "girlfriend, which is an attractions/activities request with destination provided."
                        ),
                    },
                    {
                        "module": "Attractions",
                        "prompt": "Find me spas in Tokyo, I'm looking for a relaxing weekend with my girlfriend",
                        "response": (
                            "**Waho-An NATURE Tokyo** \u2014 A healing-focused spa that offers targeted treatments "
                            "designed to deliver deep relaxation and recovery, perfect for a restorative weekend together.\n\n"
                            "**LaQua** \u2014 A popular Tokyo water and amusement complex with relaxing facilities and "
                            "atmosphere, making it an easy choice for a leisurely, spa-like weekend outing.\n\n"
                            "**ASMR TWIX TOKYO HEAD SPA** \u2014 A specialty head spa that uses ASMR-style techniques "
                            "and calming treatments to create an intimate, deeply relaxing experience for couples.\n\n"
                            "---\n\u2708\ufe0f Enjoy your trip! Safe travels from the Tripzy team. \U0001f30d"
                        ),
                    },
                ],
            },
            # ── Example 3: Multi-turn attractions – Amsterdam cultural + vegetarian (run3) ──
            {
                "prompt": "Suggest places for a cultural trip in Europe, I love history (so museums) and food (i am vegetarian)",
                "full_response": (
                    "**Spectrum** \u2014 An internationally dynamic kitchen with proud Dutch heritage led by "
                    "Chef Sidney Schutte, great for adventurous diners and likely able to accommodate vegetarian "
                    "requests (best to check the menu or call ahead).\n\n"
                    "**Restaurant DS** \u2014 Offers Dutch, seafood and European dishes and is explicitly listed "
                    "as \"Vegetarian Friendly\" with vegan options, making it a reliable vegetarian-friendly choice.\n\n"
                    "**Restaurant Amsterdam** \u2014 Serves Dutch, seafood and Central European fare and is marked "
                    "\"Vegetarian Friendly\" with gluten-free options, so it's a good spot for varied "
                    "vegetarian-friendly meals.\n\n"
                    "---\n\u2708\ufe0f Enjoy your trip! Safe travels from the Tripzy team. \U0001f30d"
                ),
                "steps": [
                    {
                        "module": "Supervisor",
                        "prompt": "Suggest places for a cultural trip in Europe, I love history (so museums) and food (i am vegetarian)",
                        "response": (
                            "Routing to End: User requested cultural places in Europe but gave only a continent "
                            "(not an acceptable destination); a specific city or destination is required to suggest attractions."
                        ),
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "amsterdam",
                        "response": (
                            "Routing to Attractions: User provided Amsterdam as the destination for an AttractionsOnly "
                            "request focused on cultural/history museums and vegetarian food, so we can proceed to "
                            "generate relevant sights and restaurants."
                        ),
                    },
                    {
                        "module": "Attractions",
                        "prompt": "amsterdam",
                        "response": (
                            "**ARTIS Amsterdam Royal Zoo** \u2014 A historic zoo and botanical park in the heart of "
                            "Amsterdam where you can stroll among shady trees, meet diverse animals, and enjoy the "
                            "aquarium, planetarium, and heritage exhibits.\n\n"
                            "**The Amsterdam Dungeon** \u2014 An interactive, theatrical attraction that brings "
                            "Amsterdam's darker 500 years of history to life with immersive shows, scares, and storytelling.\n\n"
                            "**ARTIS** \u2014 A centrally located Amsterdam attraction combining a zoo, aquarium, "
                            "museum, and park (coordinates: 52.3660003, 4.9165321), ideal for families and culture lovers.\n\n"
                            "---\n\u2708\ufe0f Enjoy your trip! Safe travels from the Tripzy team. \U0001f30d"
                        ),
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "and restaurants? I'm vegetarian so its importantt",
                        "response": (
                            "Routing to Attractions: User is asking for vegetarian restaurant recommendations "
                            "in Amsterdam as a follow-up to the cultural sights already provided."
                        ),
                    },
                    {
                        "module": "Attractions",
                        "prompt": "and restaurants? I'm vegetarian so its importantt",
                        "response": (
                            "**Spectrum** \u2014 An internationally dynamic kitchen with proud Dutch heritage led by "
                            "Chef Sidney Schutte, great for adventurous diners and likely able to accommodate "
                            "vegetarian requests (best to check the menu or call ahead).\n\n"
                            "**Restaurant DS** \u2014 Offers Dutch, seafood and European dishes and is explicitly "
                            "listed as \"Vegetarian Friendly\" with vegan options, making it a reliable choice.\n\n"
                            "**Restaurant Amsterdam** \u2014 Serves Dutch, seafood and Central European fare and is "
                            "marked \"Vegetarian Friendly\" with gluten-free options.\n\n"
                            "---\n\u2708\ufe0f Enjoy your trip! Safe travels from the Tripzy team. \U0001f30d"
                        ),
                    },
                ],
            },
            # ── Example 4: Multi-turn combined flights+hotels – Bahamas snorkeling (run4) ──
            {
                "prompt": "I want a place to snorkel in the caribbeans. So find me flights and hotels.",
                "full_response": (
                    "\u2708\ufe0f Flight: JFK (Terminal 5, New York) \u2192 NAS (Nassau, Terminal C) | "
                    "2026-08-12 | JetBlue B6 121 | 3h07 direct | $194.50 USD\n\n"
                    "\U0001f3e8 Hotels in Nassau, Bahamas (check-in 2026-08-12, check-out 2026-08-17 \u2014 5 nights):\n\n"
                    "Top 3 recommendations:\n"
                    "1) Warwick Paradise Island - Bahamas \u2014 $220/night | Total: $1,099 | Rating: 4.1\u2605 | "
                    "Best value; free breakfast, beach access \u2014 ideal base for snorkeling trips.\n"
                    "2) The Reef at Atlantis \u2014 $345/night | Total: $1,727 | Rating: 4.3\u2605 | "
                    "Atlantis resort with top snorkeling and marine experiences nearby.\n"
                    "3) Sandyport Beach Resort \u2014 $317/night | Total: $1,583 | Rating: 4.3\u2605 | "
                    "Relaxed beachfront with private beach and snorkeling access.\n\n"
                    "Estimated minimum budget: ~$1,294.50 USD (JetBlue flight + Warwick hotel, 5 nights)."
                ),
                "steps": [
                    {
                        "module": "Supervisor",
                        "prompt": "I want a place to snorkel in the caribbeans. So find me flights and hotels.",
                        "response": "Vague destination 'caribbeans' \u2192 asked for specific city.",
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "Bahamas",
                        "response": (
                            "Routing to End: User requested flights (with hotels pending) to Bahamas but "
                            "required flight fields (origin and departure date) are missing, so ask for origin first."
                        ),
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "new york",
                        "response": (
                            "Routing to End: User provided origin_city (new york) for FlightOnly but "
                            "departure_date is still missing; user originally requested flights and hotels "
                            "so HotelOnly remains pending."
                        ),
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "12 august",
                        "response": (
                            "Routing to Trip_Planner: User supplied the departure date, so all required flight "
                            "fields are now present; proceed to Trip_Planner and then handle the pending HotelOnly stage."
                        ),
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": (
                            "Find flights from new york to Bahamas departing 2026-08-12 for 1 traveler "
                            "(preference: snorkeling); after returning flight options, continue with the pending HotelOnly stage."
                        ),
                        "response": "Executing Tools...",
                    },
                    {
                        "module": "Researcher",
                        "prompt": "Executing resolve_airport_code_tool: {'keyword': 'New York'}",
                        "response": '[{"iataCode": "NYC", "name": "New York", "cityName": "New York", "type": "AIRPORT"}]',
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": 'Tool Result (resolve_airport_code_tool): [{"iataCode": "NYC", "name": "New York", "cityName": "New York", "type": "AIRPORT"}]',
                        "response": "Executing Tools...",
                    },
                    {
                        "module": "Researcher",
                        "prompt": "Executing resolve_airport_code_tool: {'keyword': 'Nassau'}",
                        "response": '[{"iataCode": "NAS", "name": "Nassau", "type": "fallback"}]',
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": 'Tool Result (resolve_airport_code_tool): [{"iataCode": "NAS", "name": "Nassau", "type": "fallback"}]',
                        "response": "Executing Tools...",
                    },
                    {
                        "module": "Researcher",
                        "prompt": "Executing search_flights_tool: {'origin': 'NYC', 'destination': 'NAS', 'departure_date': '2026-08-12', 'adults': 1, 'currency': 'USD'}",
                        "response": (
                            "Aggregated 3 direct flights from Amadeus "
                            "(best: JetBlue B6 121 JFK\u2192NAS $194.50 direct)"
                        ),
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": "Tool Result (search_flights_tool): [3 Amadeus direct flights NYC\u2192NAS 2026-08-12]",
                        "response": (
                            "FlightOnly plan submitted: JetBlue JFK\u2192NAS $194.50 direct. "
                            "Continuing to pending HotelOnly stage."
                        ),
                    },
                    {
                        "module": "Supervisor",
                        "prompt": "12 august",
                        "response": "Pending stages detected: auto-routing to Trip_Planner for HotelOnly.",
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": (
                            "Search hotels in Nassau for 1 adult, check-in 2026-08-12, check-out 2026-08-17, "
                            "medium budget, sort by rating."
                        ),
                        "response": "Executing Tools...",
                    },
                    {
                        "module": "Researcher",
                        "prompt": "Executing search_hotels_tool: {'city': 'Nassau', 'check_in': '2026-08-12', 'check_out': '2026-08-17', 'budget': 'medium', 'adults': 1, 'sort_by': 'rating'}",
                        "response": (
                            "SerpApi returned 5 valid hotel offers "
                            "(top: The Reef at Atlantis 4.3\u2605, Sandyport Beach Resort 4.3\u2605, "
                            "Warwick Paradise Island 4.1\u2605 $220/night)"
                        ),
                    },
                    {
                        "module": "Trip_Planner",
                        "prompt": "Tool Result (search_hotels_tool): [5 Nassau hotels sorted by rating]",
                        "response": (
                            "HotelOnly plan submitted: top recommendation Warwick Paradise Island $220/night "
                            "($1,099 total, 5 nights). Estimated combined budget ~$1,294.50 USD."
                        ),
                    },
                ],
            },
        ],
    }


@app.get("/api/model_architecture")
def get_model_architecture():
    """Returns a PNG architecture diagram of the Tripzy agent graph."""
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import networkx as nx

        # --- Build directed graph ---
        G = nx.DiGraph()

        nodes = ["START", "Supervisor", "Trip_Planner", "Researcher",
                 "Attractions", "Critique", "Human_Approval", "END"]
        edges = [
            ("START",         "Supervisor"),
            ("Supervisor",    "Trip_Planner"),
            ("Supervisor",    "Researcher"),
            ("Supervisor",    "Attractions"),
            ("Supervisor",    "END"),
            ("Trip_Planner",  "Researcher"),
            ("Trip_Planner",  "Critique"),
            ("Trip_Planner",  "Human_Approval"),
            ("Trip_Planner",  "Supervisor"),
            ("Trip_Planner",  "END"),
            ("Researcher",    "Trip_Planner"),
            ("Researcher",    "Supervisor"),
            ("Critique",      "Trip_Planner"),
            ("Critique",      "Human_Approval"),
            ("Critique",      "Supervisor"),
            ("Human_Approval","END"),
            ("Human_Approval","Supervisor"),
            ("Attractions",   "END"),
        ]
        G.add_nodes_from(nodes)
        G.add_edges_from(edges)

        # --- Fixed layout for clarity ---
        pos = {
            "START":         (0,  4),
            "Supervisor":    (0,  3),
            "Researcher":    (-2, 2),
            "Trip_Planner":  (0,  2),
            "Attractions":   (2,  2),
            "Critique":      (-1, 1),
            "Human_Approval":(1,  1),
            "END":           (0,  0),
        }

        # --- Node colours by role ---
        color_map = {
            "START":          "#4CAF50",
            "END":            "#F44336",
            "Supervisor":     "#2196F3",
            "Trip_Planner":   "#9C27B0",
            "Researcher":     "#FF9800",
            "Attractions":    "#00BCD4",
            "Critique":       "#795548",
            "Human_Approval": "#607D8B",
        }
        node_colors = [color_map[n] for n in G.nodes()]

        fig, ax = plt.subplots(figsize=(14, 10))
        fig.patch.set_facecolor("#1E1E2E")
        ax.set_facecolor("#1E1E2E")

        nx.draw_networkx_nodes(G, pos, ax=ax, node_size=8000,
                               node_color=node_colors, alpha=0.95)
        nx.draw_networkx_labels(G, pos, ax=ax,
                                font_size=10, font_color="white", font_weight="bold")
        nx.draw_networkx_edges(G, pos, ax=ax,
                               edge_color="#AAAAAA", arrows=True,
                               arrowsize=25, arrowstyle="-|>",
                               connectionstyle="arc3,rad=0.08",
                               width=1.5, min_source_margin=50, min_target_margin=50)

        # --- Legend ---
        legend_handles = [
            mpatches.Patch(color=color_map[n], label=n) for n in nodes
        ]
        ax.legend(handles=legend_handles, loc="lower right",
                  facecolor="#2E2E3E", edgecolor="gray",
                  labelcolor="white", fontsize=8)

        ax.set_title("Tripzy Agent Architecture", color="white",
                     fontsize=14, fontweight="bold", pad=12)
        ax.axis("off")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/png")

    except Exception as e:
        import traceback
        traceback.print_exc()  # Log server-side only
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to generate graph image. Check server logs for details."},
        )


@app.post("/api/execute")
def execute_agent(request: ExecuteRequest):
    """
    Main Execution Endpoint.
    Runs the LangGraph, captures steps, and returns the final response.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"tripzy | {request.prompt[:60]}",
        "metadata": {"thread_id": thread_id, "user_message": request.prompt[:120]},
    }
    input_payload = {"user_query": request.prompt}

    def _sanitize_steps(raw_steps: list) -> list:
        """Keep only the required fields in each step."""
        return [
            {
                "module": s.get("module", ""),
                "prompt": s.get("prompt", ""),
                "response": s.get("response", ""),
            }
            for s in raw_steps
        ]

    try:
        final_state = graph.invoke(input_payload, config=config)
        plan = final_state.get("trip_plan")
        instruction = final_state.get("supervisor_instruction")
        budget_warning = final_state.get("budget_warning")
        steps = _sanitize_steps(final_state.get("steps", []))

        INTERNAL_TAGS = {"Plan Drafted", "Done", "None", ""}

        if plan:
            plan_trip_type = plan.get("trip_type", "") if isinstance(plan, dict) else ""
            if plan_trip_type in ("FlightOnly", "HotelOnly") and instruction and instruction not in INTERNAL_TAGS:
                final_text = instruction
            else:
                final_text = format_plan_to_markdown(plan)
                if budget_warning:
                    final_text = f"⚠️ **Budget Note:** {budget_warning}\n\n{final_text}"
        elif instruction and instruction not in INTERNAL_TAGS:
            final_text = instruction
        else:
            final_text = "Task completed."
            for step in reversed(steps):
                resp = step.get("response", "")
                if resp and not any(
                    resp.startswith(tag)
                    for tag in ["Routing to", "Need more", "Edge Case", "Error"]
                ):
                    final_text = resp
                    break

        # For combined requests (e.g. flights + hotels), surface all stage results
        # so the frontend can render each as a separate bubble.
        completed_stages = final_state.get("completed_stage_responses") or []
        data = {
            "status": "ok",
            "error": None,
            "response": final_text,
            "responses": completed_stages if len(completed_stages) > 1 else None,
            "steps": steps,
        }
        return Response(content=json.dumps(data, indent=2, default=str),
                        media_type="application/json")
    except Exception as e:
        _err = _classify_error(e)
        data = {
            "status": "error",
            "error": str(e),
            "error_code": _err["code"],
            "response": _err["user_msg"],
            "steps": [],
        }
        return Response(content=json.dumps(data, indent=2),
                        media_type="application/json",
                        status_code=500)


@app.post("/api/stream")
async def stream_agent(request: ExecuteRequest):
    """
    Streaming Execution Endpoint (SSE).
    Yields events as they happen in the LangGraph.
    Includes heartbeat pings so the browser never drops the connection.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"tripzy | {request.prompt[:60]}",
        "metadata": {"thread_id": thread_id, "user_message": request.prompt[:120]},
    }
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
                    graph.update_state(
                        config, {"user_query": request.prompt}, as_node=node_to_resume
                    )
                    payload_to_run = None
                else:
                    payload_to_run = input_payload

                async for event in graph.astream_events(
                    payload_to_run, config, version="v2"
                ):
                    kind = event.get("event")

                    if not kind:
                        continue

                    if kind == "on_chain_start" and event.get("name") == "LangGraph":
                        await queue.put(
                            {"type": "status", "content": "Starting Graph..."}
                        )
                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "Tool")
                        await queue.put(
                            {
                                "type": "status",
                                "content": f"Executing Tool: {tool_name}...",
                            }
                        )
                    elif kind == "on_chain_end" and "node" in event.get("metadata", {}):
                        node_name = event["metadata"]["node"]
                        await queue.put({"type": "node_complete", "node": node_name})

                # Graph finished — get final state
                snapshot = graph.get_state(config)
                conversation_logger.log_state_snapshot(thread_id, dict(snapshot.values))

                if snapshot.next:
                    draft_plan = snapshot.values.get("trip_plan")
                    approval_question = snapshot.values.get("supervisor_instruction", "")
                    await queue.put(
                        {
                            "type": "waiting_for_approval",
                            "thread_id": thread_id,
                            "preview": draft_plan,
                            "message": approval_question,
                        }
                    )
                else:
                    final_state = snapshot.values
                    plan = final_state.get("trip_plan")
                    instruction = final_state.get("supervisor_instruction")
                    budget_warning = final_state.get("budget_warning")
                    steps = final_state.get("steps", [])

                    # Extract metadata for UI sidebar
                    destination = final_state.get("destination") or None
                    budget = final_state.get("budget_limit") or None
                    if final_state.get("budget_currency") and budget:
                        budget = f"{budget} {final_state.get('budget_currency')}"
                    duration = final_state.get("duration_days") or None
                    user_profile = final_state.get("user_profile")
                    profile_dict = (
                        user_profile.dict()
                        if user_profile and hasattr(user_profile, "dict")
                        else {}
                    )

                    INTERNAL_TAGS = {
                        "Plan Drafted",
                        "Done",
                        "None",
                        "",
                        "Plan Drafted (fallback - max research iterations reached)",
                        "Plan Drafted (dedup guard - repeated tool call)",
                        "Maximum revisions reached. Finalize the plan with the current best effort.",
                    }

                    final_text = "Task completed."

                    def _format_destinations_if_json(
                        text: str, trip_type: str = "", preferences: list = None
                    ) -> str:
                        """LLM natively formats now. Just return text."""
                        return text

                    if plan and plan.get("itinerary"):
                        final_text = format_plan_to_markdown(plan)
                        if budget_warning:
                            final_text = (
                                f"⚠️ **Budget Note:** {budget_warning}\n\n{final_text}"
                            )
                    elif instruction and instruction not in INTERNAL_TAGS:
                        trip_type = final_state.get("trip_type", "")
                        prefs = final_state.get("preferences", [])
                        final_text = _format_destinations_if_json(
                            instruction, trip_type, prefs
                        )
                    else:
                        for step in reversed(steps):
                            resp = step.get("response", "")
                            if resp and not any(
                                resp.startswith(tag)
                                for tag in [
                                    "Routing to",
                                    "Need more",
                                    "Edge Case",
                                    "Error",
                                    "Executing",
                                    "Plan Drafted",
                                    "Maximum revisions",
                                    "Forced routing",
                                ]
                            ):
                                trip_type = final_state.get("trip_type", "")
                                prefs = final_state.get("preferences", [])
                                final_text = _format_destinations_if_json(
                                    resp, trip_type, prefs
                                )
                                break

                    if "System Error" in final_text and (
                        "429" in final_text
                        or "RESOURCE_EXHAUSTED" in final_text
                        or "Too Many Requests" in final_text
                    ):
                        final_text = "⚠️ The AI service is temporarily busy (rate limit). Please wait a moment and try again."

                    conversation_logger.log_message(thread_id, "agent", final_text)

                    # Ensure we send the full structured state payload
                    final_payload = {
                        "type": "final_response",
                        "content": final_text,
                        "destination": destination,
                        "budget": budget,
                        "duration": duration,
                        "user_profile": profile_dict,
                        "_saved": final_text,
                    }
                    await queue.put(final_payload)

            except Exception as e:
                import traceback

                error_trace = traceback.format_exc()
                print(f"  [STREAM ERROR] {error_trace}")
                _err = _classify_error(e)
                conversation_logger.log_message(
                    thread_id, "error", f"Error [{_err['code']}]: {_err['user_msg']}"
                )
                await queue.put({
                    "type": "error",
                    "content": _err["user_msg"],
                    "error_code": _err["code"],
                })
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
                    event_data = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_INTERVAL
                    )
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
                    saved_path = conversation_logger.save_conversation(
                        thread_id, final_response_content
                    )
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
        },
    )


@app.post("/api/approve")
def approve_trip(request: ExecuteRequest):
    """
    Resumes the graph after a human approval interrupt.
    """
    if not request.thread_id:
        return JSONResponse(
            status_code=400, content={"error": "thread_id is required for approval."}
        )

    config = {"configurable": {"thread_id": request.thread_id}}

    try:
        # Resume from the interrupted node. With interrupt_before, invoking with
        # None is sufficient and avoids brittle node-scoped update_state writes.
        snapshot = graph.get_state(config)
        if not snapshot.next:
            return JSONResponse(
                status_code=400,
                content={"error": "No pending approval found for this thread."},
            )

        # Continue execution
        final_state_res = graph.invoke(None, config=config)

        # Depending on graph/runtime state, invoke can return None; use snapshot values then.
        if isinstance(final_state_res, dict):
            final_state = final_state_res
        else:
            final_state = dict(graph.get_state(config).values)

        plan = final_state.get("trip_plan")
        supervisor_instruction = final_state.get("supervisor_instruction")

        if isinstance(plan, dict) and plan:
            response_text = format_plan_to_markdown(plan)
        elif supervisor_instruction:
            response_text = supervisor_instruction
        else:
            response_text = "Trip finalized."

        return {
            "status": "ok",
            "response": response_text,
            "steps": final_state.get("steps", []),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
