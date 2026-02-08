# Tripzy: Detailed Implementation Roadmap (Iterative & Testable)

 This roadmap is designed for **incremental development**. You build a small piece, test it, verify it works, then add the next piece.

---

## Phase 1: Foundation (Completed)
- [x] **Repo Setup**: Python environment & `requirements.txt`.
- [x] **Secrets**: `.env` configuration.
- [x] **Observability**: **LangSmith** setup.
- [x] **Hello World**: Basic Graph structure `app/graph.py` & API `app/main.py`.

---

## Phase 2: The "Brain" (Mock Planner)
**Goal**: Get a structured JSON response for a trip request, even if data is fake. Verify the `Planner` node works in isolation.

- [x] **Step 2.1: Define `TravelState`**
    - **Implementation**: Update `app/state.py`.
    - **Details**: Add `trip_plan` (Dict), `budget` (Dict), and `critique_feedback` (Str).
    - **Test**: Run `uvicorn`, call `/api/execute` with "Plan a trip". Check logs for state updates.

- [x] **Step 2.2: Implement `Planner` Node (Mock Mode)**
    - **Implementation**: Update `app/prompts/planner_prompt.py`.
    - **Details**: Use `StructuredOutput` to enforce JSON schema (Destination, Itinerary, Cost).
    - **Prompt**: "You are a travel planner. Create a fake itinerary for testing."
    - **Test**: `/api/execute` -> Returns a perfect JSON trip plan. (Verified via mock test).

---

## Phase 3: The "Eyes" (Real Data Integration)
**Goal**: Replace hallucinations with real data from Wikivoyage & Amadeus.

- [x] **Step 3.1: Wikivoyage Search Tool**
    - **Implementation**: Update `app/tools.py`.
    - **Details**: Use `DuckDuckGoSearchRun` with query `site:wikivoyage.org {destination} "things to do"`.
    - **Test**: Create a script `test_tools.py` and run `print(web_search_tool("Paris"))`. Verify Wikivoyage results. (Verified).

- [x] **Step 3.2: Connect `Planner` to `Researcher`**
    - **Implementation**: Updated `app/graph.py`. `Trip_Planner` routes to `Researcher` if `call_researcher` is populated. `Planner` prompt updated to see `Research Info`.
    - **Details**:
        1. `Planner` outputs `call_researcher="Paris museums"`.
        2. `Planner` routes to `Researcher`.
        3. `Researcher` updates history.
        4. Loop back to `Planner` (or Supervisor).
    - **Test**: `/api/execute` with "Plan a trip to Paris". Verify logic loop.

---

## Phase 4: The "Critic" (Self-Correction)
**Goal**: Add the feedback loop to ensure realistic plans.

- [ ] **Step 4.1: Implement `Critique` Node**
    - **Implementation**: Create `app/prompts/critique_prompt.py` & update `app/graph.py`.
    - **Details**:
        - Prompt: "Review this plan: {plan}. Is it realistic? Is it under budget {budget}?"
        - Logic: If bad -> return `feedback` string. If good -> return "APPROVED".
    - **Wiring**: `Planner` -> `Critique`.
        - If `Approved` -> `End`.
        - If `Feedback` -> `Planner` (with `critique_feedback` in state).
    - **Test**: `/api/execute` with "Plan a $50 trip to Japan".
        - **Expectation**: Critic rejects it. Planner updates to "Camping in Tokyo" or says "Impossible".

---

## Phase 5: The "Memory" (Personalization)
**Goal**: Make the agent remember user preferences across sessions.

- [x] **Step 5.1: Pinecone Integration**
    - **Implementation**: Update `app/tools.py` (`search_user_profile_tool`).
    - **Details**: Connect to real Pinecone index.
    - **Test**: Run `test_tools.py`. Verify it returns "User likes vegan food".

- [x] **Step 5.2: Context Injection**
    - **Implementation**: Update `planner_node` in `app/graph.py`.
    - **Details**: Retrieve profile at start of graph (`ProfileLoader` node) and inject into `system_message`.
    - **Test**: `/api/execute` with "Plan a dinner". Result should include "Vegan restaurants" **automatically**. (Verified).

---

## Phase 6: The "Budget Master" & Course APIs (Mandatory)
**Goal**: Integrate the strict budget logic and expose the required endpoints.

- [ ] **Step 6.1: Course Mandatory APIs**
    - **Implementation**: Update `app/main.py`.
    - **Details**:
        1. `GET /api/team_info`: Returns student details.
        2. `GET /api/agent_info`: Returns agent description & prompt.
        3. `GET /api/model_architecture`: Returns PNG of LangGraph.
        4. `POST /api/execute`: Main entry point with **full step tracing**.
    - **Test**: Open browser `localhost:8000/docs` and test all endpoints.

- [ ] **Step 6.2: The Budget Guardrail (Strict)**
    - **Implementation**: Update `app/graph.py` to route through a dedicated `Budget_Master` node (or enhance Critique).
    - **Logic**: If `total_cost > budget`, REJECT. If `total_cost < 0.10` (LLM cost), PASS.
    - **Feedback Loop**: Return to Planner with specific cutout instructions.

- [ ] **Step 6.3: LLM Switch (to LLMod.ai)**
    - **Implementation**: Update `.env` and `app/graph.py` to use `LLMod.ai` API for final submission.
    - **Budget Check**: Verify entire run costs < $0.10.

## Phase 7: Deployment (Render)
**Goal**: Ship it.

- [ ] **Step 7.1: Deploy to Render**
    - **Details**: `render.yaml` configuration.
    - **Test**: Public URL access.
