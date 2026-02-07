# Tripzy Agent: Step-by-Step Implementation Plan

**Goal:** Build a "Supervisor" Agent Backend for Travel Agencies.
**Architecture:** Hub-and-Spoke (Supervisor + 3 Sub-Agents).
**Core Constraint:** Must log all steps for grading via `/api/execute`.

---

## Phase 1: Foundation & API Contract (Day 1-2)
*Goal: Get the server running and satisfying the grading bot immediately.*

### 1.1 Project Scaffolding
- [ V] Initialize Python environment (vEnv).
- [ V] Create `requirements.txt`: `fastapi`, `uvicorn`, `langgraph`, `langchain-google-genai`, `pydantic`, `python-dotenv`.
- [ V] Create folder structure: `app/`, `app/main.py`, `app/graph.py`, `app/state.py`.
- [ V] Setup `.env` file for `GOOGLE_API_KEY`.

### 1.2 State Definition (Crucial)
- [V] Define `AgentState` in `app/state.py` matching the GraphPlan:
  - `user_query`: str
  - `active_customer`: dict (The profile)
  - `trip_plan`: dict (The results)
  - `pending_action`: dict (For "Safety Mode")
  - `awaiting_approval`: bool
  - **`steps`: list** (REQUIRED for grading: `[{module, prompt, response}]`)
  - `messages`: list (Chat history)

### 1.3 Mandatory API Endpoints
- [V] [cite_start]Implement `GET /api/team_info`: Return hardcoded student details[cite: 16].
- [V] [cite_start]Implement `GET /api/agent_info`: Return agent description & prompt templates[cite: 31].
- [V] Implement `POST /api/execute`:
  - Accepts `{"prompt": "..."}`.
  - Initializes the Graph (even if empty).
  - [cite_start]Returns `{"status": "ok", "response": "...", "steps": [...]}`[cite: 71].

---

## Phase 2: The Data Layer (Real Data Integration)
*Goal: Ingest your real datasets so the agent has actual "Memory" and "World Knowledge".*

### 2.1 Client Database Setup (Vector Store)
- [ V] **Install Vector DB Dependencies:** Add `langchain-pinecone` and `langchain-community` to `requirements.txt`.
- [ V] **Create Ingestion Script (`app/ingest_clients.py`):**
  - Load your raw **Clients JSON** file. [LATER]
  - Initialize Google Gemini Embeddings (`GoogleGenerativeAIEmbeddings`).
  - **Action:** Loop through clients, embed their `summary` text, and store them in the Vector DB (e.g., ChromaDB local or Pinecone).
  - **Metadata:** Ensure you attach the `client_id`, `name`, and `status` as metadata to each vector for filtering later.

### 2.2 Wikivoyage Data Integration [SKIPED]
- [ ] **Data Loader:**
  - *If using a Dump:* Create a script to load your Wikivoyage data and index it (similar to the clients) so it is searchable by tags (e.g., "beaches", "history").
  - *If using API:* Create a wrapper function in `app/tools.py` to query Wikivoyage dynamically.
- [ ] **Create Search Tool:** Implement `search_destinations_tool(query: str)`:
  - Input: "Italian wine region".
  - Logic: Search the Wikivoyage index/data.
  - Output: Top 3 matching destinations with description and tags.

### 2.3 Verification
- [ ] Create a test script `test_data.py`:
  - Query the Client Vector DB for "Disney family trip" $\rightarrow$ Verify it finds Sarah Jenkins.
  - Query the Destination Tool for "Paris" $\rightarrow$ Verify it returns Wikivoyage data.
---

## Phase 3: Graph Plumbing & Supervisor (Day 4-5)
*Goal: Make the "Brain" that routes traffic.*

### 3.1 The Nodes (Shells)
- [V] Create empty functions for the 3 sub-agents in `app/graph.py`:
  - `crm_retriever_node(state)`
  - `trip_planner_node(state)`
  - `action_executor_node(state)`
- [V] Ensure every node appends a log to `state['steps']` (even if dummy data).

### 3.1 clarifications
- `crm_retriever_node(state)` in `app/graph.py`:
  - **Logic:** This function will *internally* call `app.tools.search_client_vector_db(query)`.
  - **Output:** Returns `{"active_customer": result, "steps": [log_entry]}`.
  - **Constraint:** Do NOT return a `ToolMessage`. Return the data directly to the Supervisor.

- `trip_planner_node(state)` in `app/graph.py`:
  - **Logic:** This function will *internally* call `app.tools.search_destinations_tool(tags)`.
  - **Output:** Returns `{"trip_plan": result, "steps": [log_entry]}`.

- `action_executor_node(state)`: (LLM + Tools)
  - **Setup:** Bind `book_service`, `send_email`, `generate_file` tools to the Gemini model.
  - **Logic Loop (ReAct Pattern):**
    1.  **Thought:** LLM decides which tool to call based on `state['pending_action']` or `user_query`.
    2.  **Action:** Execute the tool.
    3.  **Observation:** Capture the output (or Error Message).
    4.  **Reflection (Retry):**
        - *If Success:* Return `final_response`.
        - *If Error:* LLM reads error, decides to retry (max 2 times) or change parameters.
        - *If Critical Fail:* Return "Failed to execute: [Reason]" to Supervisor.
  - **Logging:** Append **every** tool attempt (success or fail) to `state['steps']`.

### 3.2 The Supervisor Node (Router)
- [V] Implement `supervisor_node(state)` with Gemini.
- [V] **Prompting Strategy:** Give the LLM the 3 modes (Router/Question/Safety).
- [V] **Routing Logic:**
  - If `pending_action` exists $\rightarrow$ Ask user for approval.
  - If `active_customer` is NULL $\rightarrow$ Route to `CRM_Retriever`.
  - Else $\rightarrow$ Route based on user intent.

### 3.3 Graph Construction
- [V] Use `StateGraph` to connect:
  - `START` $\rightarrow$ `Supervisor`.
  - `Supervisor` $\rightarrow$ `Retriever` / `Planner` / `Executor`.
  - All Sub-Agents $\rightarrow$ `Supervisor` (Loop back).
- [V] Compile the graph.
- [V] [cite_start]Implement `GET /api/model_architecture` to return the diagram PNG[cite: 53].

---

## Phase 4: Tools & Sub-Agent Logic (Day 6-7)
*Goal: Make the sub-agents actually "do" things.*

### 4.1 CRM Retriever Logic
- [ ] Connect `crm_retriever_node` to `search_customers_vector` tool.
- [ ] Logic: Update `state['active_customer']` if a match is found.

### 4.2 Trip Planner Logic
- [ ] Connect `trip_planner_node` to `search_destinations` tool.
- [ ] Logic: Read `active_customer` summary $\rightarrow$ Find Destination $\rightarrow$ Update `state['trip_plan']`.

### 4.3 Action Executor (Tools)
- [ ] Implement Mock Tools:
  - `book_service()`: Return a fake confirmation ID.
  - `send_email()`: Return "Email sent to [email]".
  - `generate_file()`: Create a simple text/PDF string.
- [ ] Connect `action_executor_node` to these tools.

---

## Phase 5: Polish & Deployment (Final)
*Goal: Go Live.*

### 5.1 Human-in-the-Loop Testing
- [ ] Test the "Safety Mode":
  - Ask "Book flight".
  - Ensure Supervisor pauses and asks "Do you approve?".
  - User replies "Yes".
  - Ensure Executor runs.

### 5.2 Deployment
- [ ] Create `start.sh` for Render.
- [ ] Push to GitHub.
- [ ] Deploy to Render.com.
- [ ] **Verify:** Call `/api/execute` and check that `steps` are populating correctly in the JSON response.