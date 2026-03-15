# Tripzy: AI Travel Agent — Architecture & Graph

## 1. Overview

Tripzy is a **Direct-to-Consumer AI Travel Companion** built on LangGraph. The user talks to Tripzy naturally — describing where they want to go, their budget, travel style — and the agent coordinates a set of specialized sub-agents to produce a fully researched, validated itinerary.

**Core design principles:**
- **Deterministic routing guards** supplement LLM routing decisions to ensure correctness in multi-turn loops
- **Stateful conversations**: all context accumulates across turns via LangGraph checkpoints
- **RAG-powered personalization**: user profiles and travel knowledge are retrieved from Pinecone on every turn

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| LLM | Azure OpenAI GPT-4.1-mini |
| Orchestration | LangGraph (StateGraph with checkpointing) |
| Backend API | FastAPI + SSE (Server-Sent Events) |
| Vector DB | Pinecone (user profiles + travel knowledge) |
| Flight Data | Amadeus API |
| Fallback Search | DuckDuckGo |
| Frontend | Vanilla HTML/CSS/JS with glassmorphism design |

---

## 3. LangGraph State

The shared state object passed between all graph nodes:

```python
class AgentState(TypedDict):
    messages: list[BaseMessage]      # Full LangGraph chat history
    user_query: str                  # Current user message
    next_step: str                   # "Researcher" | "Trip_Planner" | "End"
    supervisor_instruction: str      # Response or routing instruction
    request_type: str                # "Discovery" | "Planning" | "FlightOnly" | ...
    destination: str
    origin_city: str
    duration_days: int
    budget_limit: float
    budget_currency: str
    trip_type: str
    preferences: list[str]
    amenities: list[str]
    traveling_personas_number: int
    user_profile: UserProfile | None # Loaded from Pinecone
    steps: list[dict]                # Full trace of every module called
    researcher_calls: int            # Rate-limit guard
```

---

## 4. Graph Nodes

### 4.1 Supervisor Node
**Entry/re-entry point** after every sub-agent call. Responsible for:

1. **Profile loading**: Fetches the user's stored profile from Pinecone and injects it into context
2. **Request classification**: Calls the LLM with the `SUPERVISOR_SYSTEM_PROMPT` to determine:
   - `request_type`: Discovery / Planning / FlightOnly / HotelOnly / AttractionsOnly / GeneralQuestion
   - `next_step`: Researcher / Trip_Planner / End
3. **Vague destination guard**: Detects continent/region-level destinations ("Europe", "Asia", "somewhere warm") and automatically converts to Discovery flow
4. **Discovery loop breaker**: Prevents infinite Researcher calls by checking if the same `user_query` was already routed (see Discovery Flow doc)
5. **Edge case validation**: Checks for impossible requests (e.g., $100 budget for Maldives, 1-hour trips)
6. **Multi-turn validation**: Before routing to Trip_Planner, verifies all required fields are present; asks clarifying questions if not

### 4.2 Researcher Node
Executes tool calls delegated by the Supervisor. Has access to:

| Tool | Purpose |
|------|---------|
| `suggest_destination_tool` | RAG-powered destination suggestions (Pinecone → Amadeus enrichment) |
| `web_search_tool` | DuckDuckGo fallback for general questions |
| `search_flights_tool` | Live flight search (Amadeus) |
| `search_hotels_tool` | Hotel search with dates and amenities |
| `create_user_profile_tool` | Save/update user preferences in Pinecone |
| `resolve_airport_code_tool` | City name → IATA code |
| `get_airline_info_tool` | Airline details from IATA code |

### 4.3 Trip_Planner Node
Generates complete itineraries. Has access to:

| Tool | Purpose |
|------|---------|
| `search_flights_tool` | Live flight search |
| `search_hotels_tool` | Hotel search |
| `suggest_attractions_tool` | RAG-powered attraction discovery |
| `create_plan_tool` | Assemble structured trip plan |
| `search_tours_activities_tool` | Viator/GetYourGuide bookable experiences |
| `search_points_of_interest_tool` | Ranked POIs and restaurants |
| `search_cheapest_dates_tool` | Flexible date optimization |

### 4.4 Critique Node
Self-correction loop that validates the generated plan:
- Checks budget realism vs. actual found prices
- Verifies itinerary coherence
- Routes back to Trip_Planner with specific feedback if issues found
- Max 3 revision cycles to prevent infinite loops

### 4.5 Human_Approval Node
Interrupt node — pauses execution and returns the plan to the user for confirmation before finalizing.

---

## 5. Graph Flow

```
START
  │
  ▼
SUPERVISOR
  │
  ├── request_type="Discovery" ──────────────────► RESEARCHER
  │   (no specific destination)                        │
  │                                                    ▼
  │                                              SUPERVISOR ← (loop breaker guards here)
  │                                                    │
  │                                                    └── next_step="End" → END
  │
  ├── request_type="Planning/FlightOnly/..." ──► SUPERVISOR validates fields
  │   (specific destination known)                     │
  │                                            missing fields → END (ask question)
  │                                            all fields present ↓
  │                                                TRIP_PLANNER
  │                                                    │
  │                                                CRITIQUE ────────────────┐
  │                                                    │                    │ issues found
  │                                            approved ↓                   ↓
  │                                           HUMAN_APPROVAL        TRIP_PLANNER (revision)
  │                                                    │
  │                                                   END
  │
  ├── request_type="GeneralQuestion" ──────────► RESEARCHER (web search)
  │                                                    │
  │                                              SUPERVISOR → END
  │
  └── next_step="End" ────────────────────────────────► END
```

---

## 6. Request Type Classification

| Type | Trigger | Routing |
|------|---------|---------|
| `Discovery` | No specific destination; user wants suggestions | Researcher → `suggest_destination_tool` |
| `Planning` | Full trip request with destination | Trip_Planner (requires destination + duration) |
| `FlightOnly` | User explicitly wants only flights | Trip_Planner (requires origin + destination + date) |
| `HotelOnly` | User explicitly wants only hotels | Trip_Planner (requires destination + dates) |
| `AttractionsOnly` | "Things to do" / activities only | Trip_Planner (requires destination) |
| `GeneralQuestion` | Geography/travel facts question | Researcher (web search) |

---

## 7. Multi-Turn Conversation Strategy

State accumulates across turns via LangGraph's checkpointing:
- Each conversation has a `thread_id` that maps to a persistent checkpoint
- Fields like `destination`, `duration_days`, `budget_limit` accumulate progressively
- The Supervisor always checks `CURRENT STATE` before asking for already-known information
- Conversation history is injected into context on every turn

**Example turn-by-turn state accumulation:**
```
Turn 1: "I want to plan a trip" → asks for destination
Turn 2: "I'm thinking Tokyo"   → destination="Tokyo", asks for duration
Turn 3: "For 5 days"           → duration_days=5, routes to Trip_Planner
```

---

## 8. Destination Discovery Flow

See **[DESTINATION_SUGGESTION.md](./DESTINATION_SUGGESTION.md)** for the complete detailed documentation.

**Summary:**
1. Vague destination (continent/region/phrase) → automatically triggers Discovery mode
2. Researcher calls `suggest_destination_tool` with RAG query → returns ranked cities
3. Deterministic loop breaker prevents repeated Researcher calls for the same query
4. LLM generates warm, conversational summary of 2-3 best options
5. User can refine (new query → new Researcher call) or confirm (→ Planning mode)

---

## 9. Key Design Decisions

### Deterministic Guards + LLM Routing
LLMs are non-deterministic. In multi-turn workflows, they sometimes ignore injected system instructions and route incorrectly. Tripzy uses **deterministic Python guards** as a safety net over the LLM's routing decisions:
- LLM decides *what to say* (creative, natural)
- Python code enforces routing *correctness* (loop detection, vague destination interception)

### Research History Formatting
RAG results are formatted as readable bullet points before being injected into the LLM context. Raw JSON degrades reasoning quality; structured prose significantly improves it.

### Profile Updates (Background)
User profile updates to Pinecone happen as **background async tasks** after each turn — they don't block the response, maintaining low latency while continuously personalizing future interactions.
