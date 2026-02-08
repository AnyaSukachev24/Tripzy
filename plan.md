# Tripzy: Autonomous Travel Agent (Course Project)

**Goal**: Build a "Travel Companion" Agent that autonomously plans trips, strictly adhering to the Course Project Requirements.

## 1. Core Architecture (B2C Model)
*   **User**: The Traveler (Direct interaction).
*   **Agent**: "Tripzy" - A LangGraph-based autonomous agent.
*   **Key Capabilities**:
    *   **Multi-Turn Memory**: Remembers context across the conversation.
    *   **RAG (Pinecone)**: Personalization based on user history.
    *   **Budget Guardrail**: Strictly enforcing trip costs.

## 2. Course Mandatory Requirements
This project is optimized for grading key/performance indicators:

### A. API Endpoints (FastAPI)
The following endpoints **MUST** act exactly as defined:
1.  `GET /api/team_info`: Returns student details.
2.  `GET /api/agent_info`: Returns prompt templates and description.
3.  `GET /api/model_architecture`: Returns a PNG of the LangGraph.
4.  `POST /api/execute`: input `{"prompt": "..."}` -> output `{"response": "...", "steps": [...]}`.

### B. Tech Stack
*   **Orchestration**: LangGraph (Python).
*   **Database**: Supabase (PostgreSQL) + Pinecone (Vector).
*   **LLM**:
    *   *Dev*: Google Gemini 1.5 Flash / Ollama (Free).
    *   *Prod*: **LLMod.ai** (Paid - Optimization required).
*   **Deployment**: Render.com.

## 3. Execution Roadmap
See `implementation_roadmap.md` for the day-by-day checklist.
1.  **Foundation**: Setup Python, FastAPI, and Free Keys.
2.  **Core Logic**: Planner & Researcher Agents (using `duckduckgo-search`).
3.  **Data Layer**: Connect Supabase & Pinecone.
4.  **Polish**: Build specific API endpoints and minimal UI.
5.  **Ship**: Deploy to Render and switch to LLMod.ai.

## 4. Documentation Links
*   [Architecture & Graph Design](file:///c:/Users/97252/Desktop/projects/Tripzy/architecture_and_graph.md)
*   [Data Strategy & Tools](file:///c:/Users/97252/Desktop/projects/Tripzy/data_and_strategy.md)
*   [Implementation Roadmap](file:///c:/Users/97252/Desktop/projects/Tripzy/implementation_roadmap.md)