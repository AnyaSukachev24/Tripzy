# Tripzy: Implementation Roadmap (Dependency-Ordered)

This roadmap is ordered by **logical dependencies** - each phase builds on the previous ones.

---

## ✅ COMPLETED PHASES (1-22)

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

### Phase 23: Advanced Amadeus Integration (Completed)
- [x] Implement 8 new Amadeus tools (Activities, Price Metrics, Flight Status, etc.)
- [x] Register new tools in Graph (Planner & Researcher)
- [x] Update Planner Prompts for new capabilities
- [x] Enrich existing tools (Flights, Hotels, Destinations) with price metrics and sentiments
- [x] Comprehensive verification & Golden Dataset testing

---

## 🔧 CURRENT PRIORITIES (Phases 23-26)

### Phase 23: Partial Plan Support (IMPORTANT)
**Goal:** Support different types of plans based on user needs.
- [ ] Detect plan type (attractions-only, flights-only, full plan)
- [ ] Support attractions-only requests (when user has hotel/flights)
- [ ] Support flights-only requests
- [ ] Support full comprehensive plans (everything)
- [ ] Respect existing bookings and don't re-plan those components
- [ ] **Test Coverage:** `attractions_only_request`, `full_plan_request`, `flights_only_request`

### Phase 24: Special Requirements Handling (IMPORTANT)
**Goal:** Accommodate special needs and preferences.
- [x ] Accessibility features (wheelchair access, mobility needs)
- [x ] Dietary restrictions (vegan, allergies, kosher, halal)
- [x ] Pet-friendly accommodations and activities
- [ x] Sustainable/eco-tourism preferences
- [ x] Digital nomad requirements
- [ ] **Test Coverage:** `special_accessibility_needs`, `special_dietary_restrictions`, `pet_friendly_trip`

### Phase 25: Plan Structure & Tooling (Completed)
**Goal:** Formalize the trip plan structure and ensure tool reliability.
- [x] Implement real Amadeus API integration for flights (sandbox verified ✅)
- [x] Implement real Amadeus API integration for hotels (sandbox verified ✅)
- [x] Multi-source flight aggregator: Amadeus + Google Flights (fast_flights) + Kiwi.com (Model Context Protocol)
- [x] New tools: `suggest_destination_tool`, `suggest_attractions_tool`, `create_user_profile_tool`, `create_plan_tool`
- [ ] Create `BaseModel` structure for `TripPlan` (strict schema)
- [ ] Fix `SubmitPlan` tool to use the new `TripPlan` model

### Phase 26: Amadeus API Enrichment (Completed)
- **Goal**: Integrate additional Amadeus APIs (Tours, POI, Cheapest Dates, etc.) and implement rate limiting.
- **Actions**:
  - [x] Create `amadeus_rate_limiter.py` with shared client (10 TPS test / 40 TPS prod).
  - [x] Implement `resolve_airport_code_tool` (City Search).
  - [x] Implement `get_airline_info_tool` (Airline Lookup).
  - [x] Implement `search_tours_activities_tool` (Tours & Activities).
  - [x] Implement `search_points_of_interest_tool` (POI).
  - [x] Implement `search_cheapest_dates_tool` (Flight Cheapest Date).
  - [x] Update `search_flights_tool` and `search_hotels_tool` to use shared client.
  - [x] Register new tools in `graph.py` and prompts.
- **Outcome**: A richer set of travel tools and robust API usage management.

### Phase 30: Vector Knowledge Base Upgrade (Completed)
**Goal:** Transition to Pinecone's Integrated Inference for improved scalability.
- [x] Migrate `ingest_wikivoyage.py` to use Pinecone Inference (1024d) instead of local Google embeddings (768d).
- [x] Update `search_travel_knowledge` tool to match the new embedding dimension.
- [x] Update `create_user_profile_tool` to use Pinecone Inference.
- [x] Verify ingestion and search with sample data.

### Phase 31: Advanced Flight Search via Kiwi MCP (Completed)
**Goal:** Integrate the official Kiwi.com MCP server for expanded flight inventory.
- [x] Implement `KiwiMCPClient` to connect to `https://mcp.kiwi.com` (SSE/RPC).
- [x] Wrap Kiwi MCP tools as `KiwiMCPSearchTool` (sync wrapper) in the agent's toolset.
- [x] Register new tool in `graph.py` for the Planner/Booker.
- [x] Validate flight search results against Amadeus to ensure complementary coverage.

### Phase 27: Smart Graph Flow Redesign
**Goal:** Intelligent routing through Discovery → Research → Planning → Assembly → Approval.
- [ ] Budget-aware planning loop (re-search with tighter constraints if over budget)
- [ ] Partial plan support (flights-only, hotels-only, attractions-only)
- [ ] Smart Supervisor routing: detect request type (Discovery, FlightsOnly, HotelsOnly, FullPlan)
- [ ] Update Supervisor and Planner prompts for new routing logic

### Phase 28: Wikivoyage RAG & Knowledge Base
**Goal:** Populate and leverage the Wikivoyage knowledge base.
- [ ] Obtain complete Wikivoyage data dump
- [ ] Run ingestion script to populate Pinecone index
- [ ] **RAG Enhancement**: Configure `search_travel_knowledge` to support vague requests (e.g., "warm beaches") and result in specific destination/attraction suggestions.
- [ ] Verify RAG-based destination and attraction suggestions

### Phase 29: User Profiles & Personalization
**Goal:** Use stored profiles for personalized recommendations.
- [ ] Configure Pinecone API keys for user_profiles namespace
- [ ] Test create_user_profile_tool with real Pinecone storage
- [ ] Implement personalized recommendations based on stored preferences

---

## 📊 DEPENDENCY DIAGRAM

```
Phase 11-15 (Foundation) ──┐
                           ├──> Phase 16-19 (Core Features) ──┐
                           │                                  │
                           │    ┌─────────────────────────────┘
                           │    │
Phase 20 (Frontend) ───────┼────┼──> Phase 21 (Vague/Discovery)
                           │    │
Phase 22 (Edge Cases) ─────┼────┘
                           │
                           ├──> Phase 23 (Partial Plans) ──┐
                           │                               │
                           ├──> Phase 24 (Special Req) ────┤
                           │                               ├──> Phase 25 (Tooling/API) ✅
                           │                               │        │
                           │                               │        ├──> Phase 27 (Smart Graph)
                           │                               │        ├──> Phase 28 (RAG)
                           └──> Phase 26 (Optimization) ───┘        └──> Phase 29 (Personalization)
```

> **See `tests/evaluations/EVALUATION_GUIDE.md` for evaluation framework documentation.**


