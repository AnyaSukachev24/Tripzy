# Tripzy ✈️
### Your AI Travel Companion

Tripzy is a multi-agent AI travel companion built with **LangGraph**, **FastAPI**, and **LLMod (GPT-5-mini)**. It searches for real-time flights and hotels, discovers local attractions through a semantic RAG pipeline, and plans complete itineraries — all through a conversational interface that asks clarifying questions when needed.

## ✨ Key Features

- **Multi-Agent LangGraph Architecture**: Six specialized nodes — Supervisor, Trip_Planner, Researcher, Attractions, Critique, and Human_Approval — orchestrated in a stateful graph.
- **🔄 Multi-Turn Conversations**: Maintains full conversation history across turns via LangGraph checkpoints. Asks for missing details (origin, date, budget) one step at a time before planning.
- **✈️ Real-Time Flight Search**: Live flight data via the Amadeus API with airport code resolution, multi-source aggregation, and price context.
- **🏨 Real-Time Hotel Search**: Hotel results from Google Hotels (SerpApi), filtered and sorted by rating and amenity match.
- **📍 Attractions & Local Tips**: Semantic search over a curated Pinecone knowledge base to recommend sights, restaurants, and activities.
- **💰 Budget Guardrails**: Edge-case validator catches unrealistic budget/duration combinations before planning begins.
- **🔁 Self-Correction Loop**: Critique node reviews draft plans and sends them back to Trip_Planner for revision if needed.
- **✅ Human-in-the-Loop**: Graph pauses at Human_Approval for user confirmation before finalising a full itinerary.
- **📡 SSE Streaming**: Watch the agent work in real-time via Server-Sent Events (`/api/stream`).

## 🚀 Getting Started

### 1. Environment Setup
Create a `.env` file:
```env
LLMOD_API_KEY=your_key
LLMOD_BASE_URL=https://api.llmod.ai/v1
LLM_MODEL=RPRTHPB-gpt-5-mini
PINECONE_API_KEY=your_key
PINECONE_INDEX=trip-knowledge
AMADEUS_API_KEY=your_key
AMADEUS_API_SECRET=your_secret
SERPAPI_API_KEY=your_key
```

### 2. Local Installation
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Then visit `http://localhost:8000` to start planning.

## 🛠️ Agent Graph

The six nodes and their routing:

```
START
  │
  ▼
Supervisor ──── Classifies intent and collects missing fields via multi-turn Q&A
  │
  ├──► Trip_Planner  (flight search, hotel search, itinerary drafting)
  │         ├──► Researcher      (tool execution: Amadeus, SerpApi, airport codes)
  │         │         └──► Trip_Planner
  │         ├──► Critique        (reviews draft, may loop back to Trip_Planner)
  │         │         └──► Human_Approval
  │         └──► Human_Approval  (user confirms or rejects plan)
  │                   └──► END / Supervisor
  │
  ├──► Researcher  (also reachable directly from Supervisor)
  │         └──► Supervisor
  │
  ├──► Attractions  (semantic RAG over Pinecone → formatted recommendations)
  │         └──► END
  │
  └──► END  (direct response / clarifying question)
```

| Node | Role |
|------|------|
| `Supervisor` | Classifies request type, routes to the right node, asks clarifying questions |
| `Trip_Planner` | Calls tools via Researcher, builds the trip plan, submits via `SubmitPlan` |
| `Researcher` | Executes all external tools (flights, hotels, airport codes) |
| `Attractions` | Queries Pinecone RAG index and formats attraction/restaurant recommendations |
| `Critique` | Reviews draft plans for quality and flags issues for revision |
| `Human_Approval` | Pauses the graph for user confirmation before finalising an itinerary |

## 💬 Example Conversations

**Flight search (multi-turn):**
> **User:** I want a 7-day vacation in Bali, help me find flights
> **Tripzy:** Where will you be flying from?
> **User:** Berlin
> **Tripzy:** What date would you like to fly?
> **User:** 24 March
> **Tripzy:** Found a KLM round-trip BER → DPS departing 24 Mar, returning 31 Mar — EUR 978.49 total.

**Attractions search:**
> **User:** Find me spas in Tokyo, I'm looking for a relaxing weekend with my girlfriend
> **Tripzy:** **Waho-An NATURE Tokyo** — healing treatments for deep relaxation... **LaQua** — Tokyo water complex...

**Combined flights + hotels (multi-turn):**
> **User:** I want a place to snorkel in the Caribbeans. Find me flights and hotels.
> **Tripzy:** Which island did you have in mind? (e.g. Bahamas, Aruba, Barbados)
> **User:** Bahamas. Flying from New York on 12 August.
> **Tripzy:** JetBlue JFK → NAS, $194.50 direct. Top hotel: Warwick Paradise Island $220/night (5 nights = $1,099).

## 🎓 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/execute` | POST | Run the agent synchronously, returns full response + steps |
| `/api/stream` | POST | Run the agent with SSE streaming |
| `/api/approve` | POST | Resume graph after Human_Approval interrupt |
| `/api/team_info` | GET | Student details |
| `/api/agent_info` | GET | Agent description, prompt templates, and real examples |
| `/api/model_architecture` | GET | Live PNG architecture diagram |

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| [Destination Suggestion](./docs/DESTINATION_SUGGESTION.md) | How vague-destination handling and clarification work |
| [Attractions Index](./docs/ATTRACTIONS_INDEX.md) | Pinecone RAG pipeline for attractions data |
| [Conversation Examples](./docs/conversation_examples.md) | Extended multi-turn conversation traces |
