# Tripzy: Detailed Implementation Roadmap (Iterative & Testable)

 This roadmap is designed for **incremental development**. You build a small piece, test it, verify it works, then add the next piece.

---

## Phase 1: Foundation (Completed)
- [x] **Repo Setup**: Python environment & `requirements.txt`.
- [x] **Secrets**: `.env` configuration.
- [x] **Observability**: **LangSmith** setup.
- [x] **Hello World**: Basic Graph structure `app/graph.py` & API `app/main.py`.

---

## Phase 2: The "Brain" (Mock Planner) (Completed)
**Goal**: Get a structured JSON response for a trip request, even if data is fake. Verify the `Planner` node works in isolation.

- [x] **Step 2.1: Define `TravelState`**
    - **Implementation**: Updated `app/state.py`.
    - **Details**: Added `trip_plan` (Dict), `budget` (Dict), and `critique_feedback` (Str).
    - **Test**: Run `uvicorn`, call `/api/execute` with "Plan a trip". Check logs for state updates.

- [x] **Step 2.2: Implement `Planner` Node (Mock Mode)**
    - **Implementation**: Updated `app/prompts/planner_prompt.py`.
    - **Details**: Uses `StructuredOutput` to enforce JSON schema (Destination, Itinerary, Cost).
    - **Prompt**: "You are a travel planner. Create a fake itinerary for testing."
    - **Test**: `/api/execute` -> Returns a perfect JSON trip plan. (Verified via mock test).

---

## Phase 3: The "Eyes" (Real Data Integration) (Completed)
**Goal**: Replace hallucinations with real data from Wikivoyage & Amadeus.

- [x] **Step 3.1: Wikivoyage Search Tool**
    - **Implementation**: Updated `app/tools.py`.
    - **Details**: Uses `DuckDuckGoSearchRun` with query `site:wikivoyage.org {destination} "things to do"`.
    - **Test**: Created a script `test_tools.py` and ran `print(web_search_tool("Paris"))`. Verified Wikivoyage results.

- [x] **Step 3.2: Connect `Planner` to `Researcher`**
    - **Implementation**: Updated `app/graph.py`. `Trip_Planner` routes to `Researcher` if `call_researcher` is populated. `Planner` prompt updated to see `Research Info`.
    - **Details**:
        1. `Planner` outputs `call_researcher="Paris museums"`.
        2. `Planner` routes to `Researcher`.
        3. `Researcher` updates history.
        4. Loop back to `Planner` (or Supervisor).
    - **Test**: `/api/execute` with "Plan a trip to Paris". Verified logic loop.

---

## Phase 4: The "Critic" (Self-Correction) (Completed)
**Goal**: Add the feedback loop to ensure realistic plans.

- [x] **Step 4.1: Implement `Critique` Node**
    - **Implementation**: Created `app/prompts/critique_prompt.py` & updated `app/graph.py`.
    - **Details**:
        - Prompt: "Review this plan: {plan}. Is it realistic? Is it under budget {budget}?"
        - Logic: If bad -> return `feedback` string. If good -> return "APPROVED".
    - **Wiring**: `Planner` -> `Critique`.
        - If `Approved` -> `Supervisor` -> `End`.
        - If `Feedback` -> `Planner` (with `critique_feedback` in state).
    - **Test**: `/api/execute` with "Plan a $50 trip to Japan". Verified via `test_critique_mock.py`.

---

## Phase 5: The "Memory" (Personalization) (Completed)
**Goal**: Make the agent remember user preferences across sessions.

- [x] **Step 5.1: Pinecone Integration**
    - **Implementation**: Updated `app/tools.py` (`search_user_profile_tool`).
    - **Details**: Connects to real Pinecone index.
    - **Test**: Verified via `test_personalization_mock.py`.

- [x] **Step 5.2: Context Injection**
    - **Implementation**: Updated `app/graph.py`.
    - **Details**: Retrieves profile at start of graph (`ProfileLoader` node).
    - **Test**: `/api/execute` with "Plan a dinner". Verified profile injection.

---

## Phase 6: The "Budget Master" & Course APIs (Mandatory) (Completed)
**Goal**: Integrate the strict budget logic and expose the required endpoints.

- [x] **Step 6.1: Course Mandatory APIs**
    - **Implementation**: Updated `app/main.py`.
    - **Details**:
        1. `GET /api/team_info`: Returns student details.
        2. `GET /api/agent_info`: Returns agent description & prompt.
        3. `GET /api/model_architecture`: Returns PNG of LangGraph.
        4. `POST /api/execute`: Main entry point with full step tracing.
    - **Test**: Verified via `test_api_mock.py`.

- [x] **Step 6.2: The Budget Guardrail (Strict)**
    - **Implementation**: Integrated into `Critique` node.
    - **Logic**: If `total_cost > budget`, REJECT.

---

## Phase 7: Deployment (Render)
**Goal**: Ship it.

- [x] **Step 7.1: Dockerfile**
    - **Implementation**: Created `Dockerfile`.
    - **Details**: Optimized for Python/FastAPI deployment.

- [ ] **Step 7.2: Deploy to Render**
    - **Action**: User to push to GitHub and connect to Render.
    - **Action**: User to add `GOOGLE_API_KEY` (and other secrets) in Render Env Vars.

---

## Phase 8: Premium Dashboard UI (Completed)
**Goal**: Transform the UI into a luxury travel agent dashboard.
- [x] **Step 8.1: Modern CSS Foundation**: Implement sleek dark mode, glassmorphism, and Inter typography.
- [x] **Step 8.2: Dashboard Layout**: Create a sidebar for real-time state visualization (Budget, Destination, Profile).
- [x] **Step 8.3: Interactive Chat**: Replace the simple textarea with a dynamic chat interface.

---

## Phase 9: Real-Time Stream & Tracing (Completed)
**Goal**: Show progress updates as the agent works.
- [x] **Step 9.1: SSE/Streaming Endpoint**: Update `app/main.py` to stream LangGraph events.
- [x] **Step 9.2: Frontend Step Rendering**: Display "Researcher is searching..." or "Critic is reviewing..." in the UI.

---

## Phase 10: Human-in-the-Loop (Completed)
**Goal**: Add a final "Approve" button before the trip is fully finalized.
- [x] **Step 10.1: Interrupt State**: Add an interrupt after `Critique` approved.
- [x] **Step 10.2: Approval UI**: Add a "Confirm & Finalize" button to the chat.

---

## Phase 12: Debugging & Stabilization (In Progress)
**Goal**: Fix UI responsiveness and ensure stable execution with Gemini API.
- [x] **Step 12.1: Reproduce & Fix "No Answer"**: Investigate SSE stream and frontend parsing.
- [ ] **Step 12.2: Verify Gemini Integration**: Ensure cost-effective model usage.
- [ ] **Step 12.3: UI Polish**: Fix status indicators (`Connecting...` vs `Completed`).

---

## Phase 13: Robustness & Error Handling (Next Steps)
**Goal**: Make the agent resilient to API failures and user interrupts.
- [x] **Step 13.1: Global Error Boundary**: Catch-all for graph failures in `app/graph.py` (Supervisor).
- [ ] **Step 13.2: Retry Logic**: Implement exponential backoff for Gemini API calls.
- [x] **Step 13.3: User Feedback Loop**: Updated Supervisor prompt to ask clarifying questions instead of failing.

---

## Phase 14: Cost Optimization
**Goal**: Reduce token usage while maintaining quality.
- [ ] **Step 14.1: Prompt Compression**: Shorten system prompts without losing context.
- [ ] **Step 14.2: Caching**: Implement aggressive caching for Research steps.
- [ ] **Step 14.3: Model Routing**: Use cheaper models for simple routing tasks.

---

## Phase 15: Automated Testing
**Goal**: Ensure stability across updates.
- [ ] **Step 15.1: Unit Tests**: Test individual nodes (Planner, Researcher).
- [ ] **Step 15.2: Integration Tests**: End-to-end flow validation.
