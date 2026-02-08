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
    - [ ] **Budget Master Implementation**:
    - [ ] Implement logic to check total cost vs budget.
    - [ ] **Feedback Loop**: If over budget, return to Planner with specific critique.
- [ ] **Frontend**: Build a minimal HTML/JS UI (Textarea + Run Button).
- [ ] **LLM Switch**: specific change to **LLMod.ai** API.
- [ ] **Deploy to Render**:
    - [ ] `render.yaml` configuration.
    - [ ] Environment variables setup on Render.
- [ ] **Final Budget Check**: Verify one full run costs < $0.10
