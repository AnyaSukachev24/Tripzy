# Tripzy ✈️
### Your Luxury AI Travel Agent Dashboard

Tripzy is a state-of-the-art autonomous travel agent built with **LangGraph**, **FastAPI**, and **Gemini**. It doesn't just hallucinate trips; it researches real data, validates costs against your budget, and refine its plans through a Multi-Agent loop.

## ✨ Key Features
- **Multi-Agent Architecture**: Supervisor, Planner, Researcher, and Critique nodes working in harmony.
- **Premium Dashboard**: Glassmorphism design with real-time status updates.
- **SSE Streaming**: Watch the agent "think" and "research" as it builds your itinerary.
- **Human-in-the-Loop**: The agent pauses for your final approval before finalizing the plan.
- **Budget Guardrails**: Strict validation to ensure you stay under your limit.
- **Memory**: Remembers your preferences (RAG via Pinecone).

## 🚀 Getting Started

### 1. Environment Setup
Create a `.env` file:
```env
GOOGLE_API_KEY=your_key_here
PINECONE_API_KEY=your_key_here
PINECONE_INDEX=user-profiles
```

### 2. Local Installation
```bash
pip install -r requirements.txt
python -m app.main
```
Then visit `http://localhost:8000` to start planning.

## 📚 Documentation
For detailed project documentation, architecture details, implementation roadmap, and data strategy, see the **[`docs/`](./docs/)** folder:
- **[Project Plan](./docs/plan.md)** - High-level objectives
- **[Architecture & Graph](./docs/architecture_and_graph.md)** - System design details
- **[Data & Strategy](./docs/data_and_strategy.md)** - Data sources and approach
- **[Implementation Roadmap](./docs/implementation_roadmap.md)** - Development plan and milestones

## 🛠️ Architecture
The agent uses a cyclic graph:
1. **ProfileLoader**: Fetches your preferences.
2. **Supervisor**: Routes tasks based on your naturally spoken request.
3. **Trip_Planner**: Drafts the structured itinerary.
4. **Researcher**: Uses Wikivoyage and real-time search for facts.
5. **Critique**: Self-corrects the plan for budget and realism.
6. **Human_Approval**: Interactive pause for user verification.

## 🎓 Course Requirements Meta
- `GET /api/team_info`: Student details.
- `GET /api/agent_info`: Agent capabilities.
- `GET /api/model_architecture`: Live LangGraph visualization.
- `POST /api/stream`: Full execution trace.
