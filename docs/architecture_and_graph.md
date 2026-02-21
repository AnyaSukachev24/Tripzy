# Tripzy: Direct-to-Consumer AI Travel Agent Architecture

## 1. Overview & Vision
Tripzy is evolving from a B2B agent tool to a **Direct-to-Consumer (B2C) "Travel Companion"**. The user *is* the traveler. The goal is to provide a stress-free, end-to-end planning experience that feels like having a knowledgeable, budget-conscious friend plan your trip.

### Key Pain Points Addressed
1.  **"Sticker Shock" (Budget Anxiety)**: Users often plan a dream trip only to realize it's 2x their budget at the end.
    *   *Solution*: A dedicated **Budget Master** agent that continuously monitors costs against the user's hard limit *during* the planning phase, not just at the end.
2.  **Decision Paralysis (Overwhelm)**: Too many flight/hotel options.
    *   *Solution*: The **Planner** agent synthesizes options and presents only the top 3 recommendations based on *personal* history, not just generic "cheapest".
3.  **Fragmentation**: Flights, hotels, and activities are usually planned in silos with disconnected context.
    *   *Solution*: A **StateGraph** that maintains a unified "Trip Context" where flight arrival times directly influence hotel check-in and activity scheduling.
    *   *Course Requirement*: The system supports **multi-turn interactions** and persistent history to handle iterative planning.
4.  **Impersonal Service**: Generic AI doesn't remember you like aisle seats or vegan food.
    *   *Solution*: A **User Profile RAG** module (Pinecone) that injects past preferences into every prompt.

---

## 2. LangGraph Architecture (Optimized)
We utilize **LangGraph** to model the travel planning process as a state machine. This allows for cyclic feedback and human-in-the-loop approval.
*   **Optimization**: We minimize LLM calls by using "Router" nodes that only call searching agents when absolutely necessary, preventing wasted tokens.

### 2.1 The Graph State
The shared state object passed between nodes:
```typescript
interface TravelState {
  // Chat History
  messages: BaseMessage[];
  
  // User Context (Populated by RAG)
  user_profile: {
    id: string;
    preferences: string[]; // e.g., "Aisle seat", "Vegan", "Boutique hotels"
    past_trips: string[];
    loyalty_programs: string[];
  };

  // The Active Trip Plan
  trip_plan: {
    destination: string;
    dates: { start: string; end: string };
    budget: { limit: number; current_total: number; currency: string };
    travelers: number;
    segments: any[]; // Flights, Hotels, Activities
  };

  // Agent Coordination
  next_step: string;
  revision_count: number; // To prevent infinite loops
  error: string | null;
}

### 2.2a State Management Strategy (Insight: *sergio11/langgraph_travel_planner*)
*   **Reducers**: We will use "Reducers" to safely merge data when `FlightSearch` and `HotelSearch` run in parallel. This prevents race conditions where one agent overwrites the other's partial plan.
```

### 2.2 The Nodes (Agents)
The graph consists of specialized nodes.

#### 1. **User Input Analyzer & Profile Loader (The Context Manager)**
*   **Role**: Understands intent ("I want to go to Tokyo") + Retrieves Context.
*   **Action**: 
    1. Parse user query.
    2. Query Vector DB (Chroma/Pinecone) for user history.
    3. **Destination Discovery (RAG)**: If the request is vague (e.g., "warm place in December"), querying the `travel_knowledge` index to retrieve matching destinations and attractions based on semantic similarity.
    4. Output: Up-to-date `user_profile` in state and potential destination candidates.

#### 2. **The Planner (The Brain)**
*   **Role**: Orchestrator. Breaks high-level goals into sub-tasks.
*   **Logic**: 
    *   "First, find flights to Tokyo for under $1000."
    *   "Once flights are locked, find hotels in Shinjuku."
*   **Pattern**: "Supervisor" architecture (inspired by *Azure-Samples*) that delegates to sub-agents but retains control of the overall state.

#### 3. **The Researcher (The Scout)**
*   **Role**: Real-time data fetcher.
*   **Sub-Agents**:
    *   *Flight Scout*: Uses **Amadeus Test API** (Free) + **Kiwi MCP** (Live Search).
    *   *Hotel Scout*: Uses **DuckDuckGo** (Search) + Amadeus (Free).
    *   *Destination Analyst*: Uses **Pinecone Integrated Inference** (RAG) + **DuckDuckGo** for high-quality destination info.
*   **Tools Standard**: MCP (Model Context Protocol) client integrated for Kiwi.com.

#### 4. **The Critic (The Quality Control)**
*   **Role**: Validates the plan *before* it reaches the user (Self-Correction).
*   **Logic**:
    *   Checks if the plan matches the user's constraints (e.g., "Is it really kid-friendly?").
    *   Checks if the budget is realistic (using "Budget Master" logic).
    *   **Action**: If flawed, sends back to `Planner` with specific feedback (`critique_feedback`).

#### 4. **The Budget Master (The CFO)**
*   **Role**: Financial guardrail.
*   **Logic**:
    *   Receives proposed items from Researcher.
    *   Calculates `current_total`.
    *   *Critical Check*: If `current_total` > `budget.limit`, it **rejects** the path and routes back to `Planner` with feedback: "Flights too expensive ($1200 > $1000). Look for cheaper dates or airlines."

#### 5. **The Concierge (The Presenter)**
*   **Role**: UX & Formatting.
*   **Action**: Compiles the final itinerary into a beautiful Markdown proposal with images, daily breakdowns, and booking links.

### 2.3 The Graph Flow (Edges)
1.  **Start** -> `Profile Loader`
2.  `Profile Loader` -> `Planner`
3.  `Planner` -> `Researcher` (or specific sub-researchers: `FlightSearch`, `HotelSearch`)
4.  `Researcher` -> `Budget Master`
5.  `Budget Master` --(Approved)--> `Concierge`
6.  `Budget Master` --(Rejected)--> `Planner` (Loop back for revision)
7.  `Concierge` -> **End**

---

## 4. Mandatory Course API Endpoints
To comply with course requirements, the backend (FastAPI) will expose:

### A. GET `/api/team_info`
*   **Returns**: Student details (JSON).
*   **Format**: `{ "group_batch_order_number": "...", "team_name": "Tripzy", "students": [...] }`

### B. GET `/api/agent_info`
*   **Returns**: Agent metadata, purpose, and prompt templates.
*   **Purpose**: Explains how to use the agent.

### C. GET `/api/model_architecture`
*   **Returns**: `image/png` of the LangGraph structure.
*   **Action**: We will auto-generate this using `graph.get_graph().draw_png()`.

### D. POST `/api/execute` (Main Entry)
*   **Input**: `{ "prompt": "User request..." }`
*   **Output**: 
    ```json
    {
      "status": "ok",
      "response": "Final answer...",
      "steps": [
        { "module": "Planner", "prompt": "...", "response": "..." },
        { "module": "Researcher", "prompt": "...", "response": "..." }
      ]
    }
    ```
*   **Traceability**: We must log every step (LLM call) to the `steps` array.

---

## 5. Implementation Patterns (Agentic)
*   **Human-in-the-Loop**: The `Planner` can interrupt the graph node to ask the user clarifying questions (e.g., "I found flights, but they are 5am. Is that okay?").
*   **Supervisor Pattern**: A "Supervisor" node can route between `FlightExpert`, `HotelExpert`, and `ActivityExpert` if complexity grows (Inspiration: *aakar-mutha/agentic-travel-planner*).

## Reference Repositories
*   **Azure AI Travel Agents**: Multi-agent delegation.
*   **LangGraph Travel Planner**: State management & cycles.
*   **n8n Travel Agent**: Synthesis of sub-agents.
