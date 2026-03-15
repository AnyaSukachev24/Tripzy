# Tripzy ✈️
### Your AI Travel Companion

Tripzy is an autonomous travel agent built with **LangGraph**, **FastAPI**, and **Azure OpenAI (GPT-4.1-mini)**. It researches real data, validates costs against your budget, suggests destinations through natural conversation, and refines plans through multi-agent feedback loops.

## ✨ Key Features

- **Multi-Agent LangGraph Architecture**: Supervisor, Researcher, Trip_Planner, and Critique nodes working in a stateful cycle.
- **🗺️ Destination Discovery**: Don't know where to go? Tripzy suggests destinations through conversational refinement powered by RAG (Pinecone) + LLM reasoning. Supports multi-turn dialogue until the user picks a destination.
- **🔄 Multi-Turn Conversations**: Maintains full conversation history across turns via LangGraph checkpoints — state accumulates naturally across messages.
- **👤 Personalized Profiles**: Remembers your travel style, dietary preferences, and accessibility needs (RAG via Pinecone). Updates continuously as you chat.
- **✈️ Real Data**: Live flights (Amadeus), hotels, tours (Viator/GetYourGuide), and POIs — not hallucinations.
- **💰 Budget Guardrails**: Edge-case validator checks for unrealistic budget/duration combinations before planning begins.
- **📡 SSE Streaming**: Watch the agent think and research in real-time via Server-Sent Events.
- **✅ Human-in-the-Loop**: The agent pauses for final approval before generating the complete itinerary.

## 🚀 Getting Started

### 1. Environment Setup
Create a `.env` file:
```env
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=your_endpoint
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
PINECONE_API_KEY=your_key
PINECONE_INDEX=trip-knowledge
AMADEUS_API_KEY=your_key
AMADEUS_API_SECRET=your_secret
```

### 2. Local Installation
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Then visit `http://localhost:8000` to start planning.

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| [Architecture & Graph](./docs/architecture_and_graph.md) | System design, nodes, and graph flow |
| [Destination Suggestion](./docs/DESTINATION_SUGGESTION.md) | **NEW** — How Discovery mode, RAG, and the loop breaker work |
| [RAG Pipeline](./docs/RAG_README.md) | Pinecone setup and retrieval strategy |
| [Data & Strategy](./docs/data_and_strategy.md) | Data sources and approach |
| [Implementation Roadmap](./docs/implementation_roadmap.md) | Development milestones |

## 🛠️ Graph Architecture

```
User Message
      │
      ▼
 SUPERVISOR ──── Classify request type:
      │          • Discovery (no destination) → Researcher (RAG suggestions)
      │          • Planning (destination set)  → Trip_Planner
      │          • FlightOnly / HotelOnly / AttractionsOnly → Trip_Planner
      │          • GeneralQuestion             → Researcher (web search)
      │
      ├──► RESEARCHER  (suggest_destination_tool / search_flights / web_search)
      │         └──► back to SUPERVISOR
      │
      ├──► TRIP_PLANNER (flights + hotels + activities)
      │         └──► CRITIQUE (self-correction loop)
      │                   └──► HUMAN_APPROVAL → End
      │
      └──► End (direct response / clarifying question)
```

## 💬 Example Conversations

**Destination Discovery:**
> **User:** I want to go to Europe for a honeymoon, 5 days
> **Tripzy:** Paris is classic for honeymooners — iconic landmarks and romantic ambiance. Venice offers serene gondola rides through picturesque canals. Which appeals to you?

> **User:** What about cities in Portugal or Spain instead?
> **Tripzy:** Lisbon offers charming cobblestone streets and beautiful river views. Seville has passionate flamenco culture and stunning Moorish architecture...

**Full Trip Planning:**
> **User:** Plan 7 days in Tokyo with $3000 budget for 2 people
> **Tripzy:** *(searches flights, hotels, attractions → presents full itinerary for approval)*

## 🎓 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/execute` | POST | Execute agent request (sync) |
| `/api/stream` | POST | Execute with SSE streaming |
| `/api/team_info` | GET | Student details |
| `/api/agent_info` | GET | Agent capabilities |
| `/api/model_architecture` | GET | Live LangGraph PNG visualization |
