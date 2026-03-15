# Destination Suggestion (Discovery Flow)

## Overview

When a user doesn't have a specific destination in mind, Tripzy enters **Discovery mode** — a multi-turn conversation that helps them find the perfect destination through natural dialogue, powered by RAG (Retrieval-Augmented Generation), LLM reasoning, and deterministic routing guards.

---

## How It Works

### Step 1 — User Expresses a Vague Intent
The user says something like:
- *"I want to go somewhere warm and cheap for 5 days"*
- *"I want to go to Europe for a honeymoon"*
- *"Suggest a destination for a beach trip under $2000"*

The **Supervisor** detects `request_type = "Discovery"` and routes to the **Researcher**.

### Step 2 — Vague Destination Guard
Before routing to Trip_Planner, the Supervisor checks whether the extracted `destination` is actually a **continent or region** (not a specific city). This is done via a `VAGUE_DESTINATIONS` set that includes:

```python
# Continents / world regions
"europe", "asia", "africa", "south america", "north america",
"middle east", "caribbean", "mediterranean", "scandinavia", ...

# Vague English phrases
"somewhere", "anywhere", "abroad", "somewhere warm", "somewhere exotic", ...
```

If a vague destination is detected, the request is automatically **converted to Discovery** regardless of what the LLM classified it as.

### Step 3 — RAG-Powered Destination Search
The Researcher calls `suggest_destination_tool`, which:
1. **Expands the user's preferences** (e.g., "warm" → "tropical climate", "beach" → "coastal destination")
2. **Queries Pinecone** for semantically matching destinations from the travel knowledge base
3. **Enriches results** with Amadeus data (airport info, flight availability)
4. **Falls back to DuckDuckGo** if RAG matches are below the similarity threshold

The tool returns a ranked list of destination objects:
```json
[
  { "destination": "Bali, Indonesia", "score": 0.87, "summary": "...", "source": "RAG" },
  { "destination": "Lisbon, Portugal", "score": 0.81, "summary": "...", "source": "RAG" }
]
```

### Step 4 — Deterministic Loop Breaker
A key challenge is that the LLM may try to call the Researcher **again** even though results already exist. The system uses a **deterministic Python guard** (not LLM-dependent) to detect this:

```python
# Check if same user_query was already sent to Researcher
already_routed = any(
    s.get("module") == "Supervisor"
    and "Routing to Researcher" in s.get("response", "")
    and s.get("prompt", "").strip().lower() == user_query.strip().lower()
    for s in steps
)

if research_steps and result.next_step == "Researcher" and already_routed:
    # Force End + generate conversational summary
```

**Why query-comparison instead of keywords?**
An earlier keyword-based approach (`if "europe" in query → skip`) failed because "europe" appears in the *initial* query (not just in follow-ups), causing the guard to always skip itself.

### Step 5 — Conversational Summary Generation
When the loop breaker fires (or the LLM correctly routes to `End`), the system:
1. Formats the RAG results as clean bullet points (not raw JSON)
2. Calls the LLM with a focused prompt: *"Pick 2-3 best matches, explain WHY each fits, ask the user to choose"*
3. Returns a natural, conversational response

### Step 6 — Multi-Turn Refinement
If the user asks for options in a **new region** (e.g., *"What about Portugal or Spain instead?"*):
- The new `user_query` is **different** from the query that triggered the first Researcher call
- The loop breaker does **not** fire (different query → no loop detected)
- The Supervisor correctly routes to the Researcher again with updated preferences
- The conversation continues naturally

---

## Graph Flow Diagram

```
User: "Europe honeymoon, 5 days"
          │
          ▼
    ┌─────────────┐
    │  SUPERVISOR  │ ← Detects Discovery + Vague Destination Guard
    └──────┬──────┘
           │ next_step = "Researcher"
           ▼
    ┌─────────────┐
    │  RESEARCHER  │ ← suggest_destination_tool (RAG + Amadeus)
    └──────┬──────┘
           │ Returns: [Paris, Venice, ...]
           ▼
    ┌─────────────┐
    │  SUPERVISOR  │ ← LLM tried to route to Researcher again
    │  (Turn 2)   │ ← LOOP BREAKER fires (same query detected)
    └──────┬──────┘
           │ Forces next_step = "End"
           ▼
    ┌─────────────┐
    │     END      │ ← Natural conversational summary returned to user
    └─────────────┘

User: "What about Portugal or Spain?"  ← New query → loop breaker does NOT fire
          │
          ▼
    ┌─────────────┐
    │  SUPERVISOR  │ ← New user query, Researcher allowed again
    └──────┬──────┘
           │ next_step = "Researcher"
           ▼
    ┌─────────────┐
    │  RESEARCHER  │ ← New RAG search (Portugal/Spain + honeymoon)
    └──────┬──────┘
           │ Returns: [Lisbon, Seville, ...]
           ▼
    ┌─────────────┐
    │  SUPERVISOR  │ ← Loop breaker fires (new query already routed)
    └──────┬──────┘
           │ Forces next_step = "End"
           ▼
    ┌─────────────┐
    │     END      │ ← "Lisbon offers charming cobblestone streets..."
    └─────────────┘
```

---

## Real Example (Live UI)

**User:** *"I want to go to Europe for a honeymoon, 5 days"*

**Tripzy:**
> Europe is such a romantic choice for a honeymoon! For a 5-day trip, I'd suggest places that offer a perfect blend of charm, intimacy, and beautiful scenery.
>
> **Paris** is classic for honeymooners — iconic landmarks, cozy cafes, and a deeply romantic ambiance. **Venice** offers serene gondola rides through picturesque canals and timeless beauty. Both spots offer unforgettable honeymoon experiences. Would you like to explore one of these, or refine your preferences?

**User:** *"What about cities in Portugal or Spain instead?"*

**Tripzy:**
> For a romantic honeymoon in Europe, I'd suggest **Lisbon** in Portugal — charming cobblestone streets, beautiful river views, and a dreamy mix of historic and modern vibes. **Seville** in Spain is bursting with passionate flamenco culture, stunning Moorish architecture, and lovely plazas perfect for romantic strolls. Would you like to explore one of these more?

---

## Key Files

| File | Role |
|------|------|
| `app/graph.py` — `supervisor_node` | Discovery routing, loop breaker, vague destination guard |
| `app/tools.py` — `suggest_destination_tool` | RAG query expansion + Pinecone + Amadeus enrichment |
| `app/prompts/supervisor_prompt.py` | 4-step Discovery flow instructions for the LLM |

---

## Design Decisions

### Why deterministic guards instead of pure LLM routing?
LLMs are non-deterministic. In multi-turn workflows, they sometimes ignore injected system instructions and re-route incorrectly. Deterministic Python guards act as a safety net — the LLM's creativity is preserved for *what to say*, while routing correctness is enforced by code.

### Why query-comparison for loop detection?
- **Keyword matching** (`"europe" in query`) fails when those keywords are in the *original* query
- **Query identity check** (`same_query_already_routed_to_researcher`) is immune to this — it detects loops by checking graph history, not user input content

### Why format RAG results as bullet points?
The LLM reasons more accurately over structured prose than over raw JSON. Formatting `[{"destination":"Bali","score":0.87}]` as `• Bali (relevance=0.87): Great beaches...` significantly improves the LLM's ability to select and describe the best matches.
