# Tripzy: Data Strategy & Tools (RAG, APIs, MVP)

## 1. Data Layer: The "Memory" of the Agent
To differentiate from generic tools (ChatGPT/Gemini), Tripzy must remember the user. The "User as Traveler" model relies heavily on **Personalization**.

### A. RAG (Retrieval-Augmented Generation) for User History
We will treat "Client Data" as the primary context source.
*   **Source Data**: 
    1.  **Past Chat Logs**: Previous interactions with the bot.
    2.  **Structured Profile**: Explicit preferences (dietary, seating, budget tier).
    3.  **Past Bookings**: "User usually stays at Marriott" or "User prefers 5-star hotels".
*   **Vector Database**: 
    *   **Tech**: **Pinecone** (Required by Course).
    *   **Embedding Models**:
        *   **tripzy** (Default): 1024 dimensions (Integrated Inference: `llama-text-embed-v2`) - **Active**.
        *   **tripzy-small**: 1024 dimensions (Backup).
        *   *Note*: Local Google embeddings (768d) are no longer used for ingestion/querying in favor of server-side inference.
*   **Workflow**:
    1.  **Vague Request (Discovery)**: "Warm place in December."
        *   *Action*: RAG retrieves "Canary Islands", "Thailand", "Mexico" based on semantic match + "Warm" tag.
        *   *Result*: Agent suggests these options with rich descriptions from Wikivoyage.
    2.  **Specific Planning**: "Trip to Rome."
        *   *Action*: Retriever searches DB for "Rome", "Italy", "European preferences".
        *   *Found Context*: "User hated the small room in Paris (2023)." -> *Agent avoids small boutique hotels.*

### B. Relational Database (Application State)
*   **Tech**: **Supabase** (Required by Course).
*   **Core Tables**:
    *   `users`: (Auth ID, Name, Email)
    *   `preferences`: (JSONB - Flexible storage for inferred preferences)
    *   `trips`: (Trip ID, Status [Draft, Booked], Total Cost, Destination)
    *   `itineraries`: (Day-by-day breakdown linked to `trips`)

---

## 2. Tools & External APIs (The "Hands")
The agents need to interact with the real world.

### A. Search & Real-Time Info (Strictly Free / Open Source)
1.  **DuckDuckGo Search (via `duckduckgo-search` package)**:
    *   *Cost*: **$0 (Truly Free)**. No API key required.
    *   *Use Case*: General research ("Best time to visit Kyoto").
    *   *Trade-off*: Slower than Tavily, but completely free.
2.  **Tavily (Freemium Backup)**:
    *   *Cost*: Free tier (1000 req/month).
    *   *Use Case*: Use only if DuckDuckGo fails or for complex multi-hop reasoning.

### B. Specialized Travel APIs
1.  **Amadeus Self-Service API (Test Environment)**:
    *   *Cost*: **Free** (Limited quota in Test env).
    *   *Use Case*: Flight offers search, Hotel list.
    *   *Limit*: Data may not be 100% real-time (cached or test subset), but sufficient for MVP.
2.  **SerpApi (Google Flights)**:
    *   *Cost*: **Limited Free Tier** (100 searches/mo).
    *   *Status*: **Optional**. We will default to Amadeus or Scraping techniques if strictly $0 is needed.

3.  **Kiwi.com (MCP)**:
    *   *Cost*: **Free** (Public MCP Server).
    *   *Use Case*: Real-time flight search with flexible parameters and booking links.
    *   *Tech*: Model Context Protocol over SSE.

### C. LLM Strategy (Cost Control & Course Budget)
*   **Current (Development)**: **Google Gemini 1.5 Flash** (Free) or **Ollama** (Free).
    *   *Reason*: To avoid wasting the $13 budget during dev/testing.
*   **Final (Submission)**: **LLMod.ai** (Course Provider).
    *   *Action*: In the final phase, switch the API endpoint to LLMod.ai.
    *   *Constraint*: Total budget $13. We must implement **User Proxies** or strict limits to ensure we don't drain this during grading.

---

## 3. MVP Definition (Minimum Viable Product)
We will build this in phases to manage complexity.

### MVP 1: The "Smart Drafter" (Current Goal)
*   **User**: Inputs destination + dates + budget.
*   **Input**: Text chat.
*   **Data**: No RAG yet. Just session memory.
*   **Output**: A Markdown proposal with estimated costs (Static data/Simulated search).
*   **Graph**: Linear (Plan -> Draft -> Critique -> Result).

### MVP 2: The "Real-Time Planner"
*   **Integration**: Connect **SerpApi/Tavily**.
*   **Feature**: Real prices. "This flight is $450 *today*."
*   **Budget Master**: Active cost checking.

### MVP 3: The "Personalized Companion"
*   **Integration**: **RAG + Vector DB**.
*   **Feature**: "Welcome back, Sarah. Want a window seat as usual?"
*   **Authentication**: Login system.

### MVP 4: The "Booker"
*   **Feature**: Deep-links to checkout or API-based booking (Agentic transactions).
*   Note: High risk, requires user trust. Start with "Deep links" first.

---

## 4. Technology Stack Recommendation
*   **Framework**: LangGraph (Python) or LangGraph.js (Node). *Assumption: Python based on usual AI stacks, but user mentioned JS repos too. We will target Python for robust data science tools.*
*   **LLM**: GPT-4o (Reasoning) or Claude 3.5 Sonnet (Coding/Logic).
*   **Frontend**: Streamlit (fastest for MVP) or React/Next.js (for "Premium" consumer feel).
