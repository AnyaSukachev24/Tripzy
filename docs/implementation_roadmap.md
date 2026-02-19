# Tripzy: Implementation Roadmap (Dependency-Ordered)

This roadmap is ordered by **logical dependencies** - each phase builds on the previous ones.

---

## ✅ COMPLETED PHASES (1-26, 30-31)

### Phase 1-10: Foundation & Core Features (Completed)
- [x] Repo Setup, Secrets, Observability
- [x] Basic Graph structure & API
- [x] Travel State & Planner Node (Mock Mode)
- [x] Wikivoyage Search Tool & Researcher Node
- [x] Critique Node & Self-Correction Loop
- [x] Pinecone Integration & Memory
- [x] Course Mandatory APIs & Budget Guardrail
- [x] Dockerfile created
- [x] Modern Dashboard UI with glassmorphism
- [x] Real-time streaming with SSE
- [x] Human-in-the-loop approval flow

### Phase 11-15: Robustness & Evaluation (Completed)
- [x] Phase 11: Duration Handling Fix (11.1)
- [x] Phase 12: Edge Case Detection & Validation (Basic)
- [x] Phase 13: Robustness & Error Handling (Global Boundary, User Feedback Loop)
- [x] Phase 14: Multi-Turn Conversation Memory (Progressive Info Gathering)
- [x] Phase 15: Golden Dataset Evaluation System (30 test cases + framework)

### Phase 16-19: Core Features & Integration (Completed)
- [x] Phase 16: Conversational Enhancement (Friendly persona, clear questions)
- [x] Phase 17: Destination Discovery (Where should I go?)
- [x] Phase 18: Vague Request Handling (Contextual clarifications)
- [x] Phase 19: Hotel & Flight Integration (Amadeus/SerpApi tools)

### Phase 20: Frontend Integration (Completed)
- [x] Updated specific prompt for structure
- [x] Frontend formatting for flights/hotels
- [x] Streaming response improvements

### Phase 21: Vague Request & Destination Discovery (Advanced) (Completed)
- [x] Extract preferences from vague requests
- [x] Suggest 3-5 appropriate destinations
- [x] Discovery Mode in Supervisor

### Phase 22: Edge Case Detection & Validation (Advanced) (Completed)
- [x] Strict budget enforcement during planning
- [x] Advanced edge case handling (Impossible requests, conflicting constraints)
- [x] Past date rejection
- [x] Large group warning logic

### Phase 24: Special Requirements Handling (Completed)
- [x] Accessibility features (wheelchair access, mobility needs)
- [x] Dietary restrictions (vegan, allergies, kosher, halal)
- [x] Pet-friendly accommodations and activities
- [x] Sustainable/eco-tourism preferences
- [x] Digital nomad requirements

### Phase 25: Plan Structure & Tooling (Completed)
- [x] Real Amadeus API integration for flights (sandbox verified)
- [x] Real Amadeus API integration for hotels (sandbox verified)
- [x] Multi-source flight aggregator: Amadeus + Google Flights (fast_flights) + Kiwi.com (MCP)
- [x] New tools: `suggest_destination_tool`, `suggest_attractions_tool`, `create_user_profile_tool`, `create_plan_tool`

### Phase 26: Amadeus API Enrichment (Completed)
**Goal**: Integrate additional Amadeus APIs and implement rate limiting.
- [x] `amadeus_rate_limiter.py` — thread-safe shared client (10 TPS test / 40 TPS prod)
- [x] `resolve_airport_code_tool` — City/Airport Search (IATA resolution)
- [x] `get_airline_info_tool` — Airline Code Lookup (code → full name)
- [x] `search_tours_activities_tool` — Tours & Activities (Viator/GetYourGuide/Klook)
- [x] `search_points_of_interest_tool` — POI Search (AVUXI TopPlace)
- [x] `cheapest_flights_tool` — Flight Cheapest Date Search
- [x] `hotel_ratings_tool` — Hotel Traveler Sentiment & Ratings
- [x] `search_hotels_tool` enhanced: `sort_by` (price/rating), `sentiment_rating`, `location` fields
- [x] **Fixed**: All new tools registered in Researcher `tool_map` (was missing — gap fixed 2026-02-19)
- [x] **Fixed**: Legacy Researcher hotel path now passes `adults` and `sort_by`

### Phase 30: Vector Knowledge Base Upgrade (Completed)
- [x] Migrate `ingest_wikivoyage.py` to use Pinecone Inference (1024d)
- [x] Update `search_travel_knowledge` tool to match new embedding dimension
- [x] Update `create_user_profile_tool` to use Pinecone Inference
- [x] Verify ingestion and search with sample data

### Phase 31: Advanced Flight Search via Kiwi MCP (Completed)
- [x] `KiwiMCPClient` connecting to `https://mcp.kiwi.com` (SSE/RPC)
- [x] `search_flights_with_kiwi_tool` as sync-wrapped LangChain tool
- [x] Registered in Planner + Researcher tool_map
- [x] Validated alongside Amadeus for complementary coverage

---

## 🔧 CURRENT PRIORITIES (Phases 23, 27-29, 32-33)

### Phase 23: Partial Plan Support
**Goal:** Support different types of plans based on user needs.
- [ ] Detect plan type (attractions-only, flights-only, full plan) in Supervisor
- [ ] Support attractions-only requests (when user has hotel/flights)
- [ ] Support flights-only requests
- [ ] Support full comprehensive plans (everything)
- [ ] Respect existing bookings and don't re-plan those components
- **Test Coverage:** `attractions_only_request`, `full_plan_request`, `flights_only_request`

### Phase 27: Smart Graph Flow Redesign ✅
**Goal:** Intelligent routing with plan-type awareness.
- [x] Budget-aware Critique: if `plan_cost > budget * 1.15` → route back to Planner with specific feedback
- [x] Researcher dynamic routing: goes directly to `Trip_Planner` when called from Planner (TOOL_CALLS:), or back to `Supervisor` for discovery queries
- [x] `researcher_calls` counter added to AgentState — max 4 calls before forced End (loop guard)
- [x] `request_type` field: Planning / Discovery / FlightOnly / HotelOnly / AttractionsOnly (detected by Supervisor)
- [x] Duration mismatch validation hardened: exact day count in feedback message
- [x] `SubmitPlan` tool improved: `trip_plan` field now has rich description + default to avoid crash on partial LLM response
- [x] `content_str` guard: Planner no longer crashes when LLM returns tool_calls with no text content

### Phase 28: Wikivoyage RAG & Knowledge Base ✅
**Goal:** Populate and leverage the Wikivoyage knowledge base.
- [x] Pinecone index configured with Inference API (1024d vectors)
- [x] `suggest_destination_tool` + `suggest_attractions_tool` use Pinecone RAG
- [x] Both tools wired into Planner bind_tools and Researcher tool_map
- [x] Planner prompt updated with explicit RAG tool guidance
- [x] Obtain complete Wikivoyage data dump and run full ingestion (Partially completed with sample data: Paris, London, Bali)
- [x] Verify RAG-based destination/attraction suggestions with real populated index (Verified with `tests/verify_rag_populated.py`)

### Phase 29: User Profiles & Personalization ✅
**Goal:** Use stored profiles for personalized recommendations.
- [x] Configure Pinecone API keys for `user_profiles` namespace
- [x] Test `get_user_profile` tool with real Pinecone storage
- [x] Implement personalized recommendations based on stored preferences (in Supervisor/Planner)

### Phase 32: Full Flow Validation (In Progress)
**Goal:** Validate the complete graph end-to-end with real use cases.
- [x] Created `tests/verify_full_flow.py` — 5 golden use cases via live graph
- [x] Created `tests/verify_hotel_full_flow.py` — hotel tool direct + graph
- [/] Running 5-case full-flow validation (in progress — LLM rate-limit retries)
- [ ] Confirm all tools dispatch correctly from Planner → Researcher
- [ ] Confirm edge case blocking works (budget $20 case)
- [ ] Confirm Discovery mode routes vague queries to Researcher
- [ ] Update walkthrough.md with validation results

### Phase 33: TripPlan Schema & Response Quality ✅
**Goal:** Formalize plan schema and improve user-facing responses.
- [x] `TripPlan` Pydantic model in `state.py` (FlightInfo, HotelInfo, ItineraryDay sub-models)
- [x] Smart response selection in `main.py` (INTERNAL_TAGS filtering)
- [x] Budget warning surfaced to user in final response
- [x] Tests: `verify_graph_improvements.py` (5/5 pass)
- [x] Tests: `verify_graph_flow.py` (real LLM graph flow validation)

---

## 📊 DEPENDENCY DIAGRAM

```
Phase 1-22 (Foundation + Core) ────────────────────────────────────────────────┐
                                                                                │
Phase 25 (API Tooling) ──────────────────────── Phase 26 (Enrichment ✅) ───────┤
                                │                     │                         │
Phase 30 (RAG/Pinecone ✅) ─────┘        Phase 31 (Kiwi MCP ✅) ───────────────┤
                                                       │                         │
                                         Phase 32 (Full Validation 🔧) ─────────┤
                                                                                 │
Phase 23 (Partial Plans) ────────────────────────────────────────────────────── │
Phase 27 (Smart Routing) ──────────────────────────────────────── → NEXT  ──────┤
Phase 28 (RAG Populate)  ──────────────────────────────────────────────────── ──┘
Phase 29 (Personalization) ─────────── (Depends on Phase 28 + 30)
```

> **See `tests/evaluations/EVALUATION_GUIDE.md` for evaluation framework documentation.**
> **See `tests/verify_full_flow.py` for end-to-end graph validation.**
