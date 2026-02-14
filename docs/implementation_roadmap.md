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

### Phase 25: Plan Structure & Tooling
**Goal:** Formalize the trip plan structure and ensure tool reliability.
- [ ] Create `BaseModel` structure for `TripPlan` (strict schema)
- [ ] Fix `SubmitPlan` tool to use the new `TripPlan` model
- [ ] Implement real Amadeus API integration (Secrets: `AMADEUS_API_KEY`, `AMADEUS_API_SECRET`) via `os.getenv`
- [ ] Update `search_flights_tool` and `search_hotels_tool` to use real API
- [ ] Create new tool to discover destinations from Wiki index

### Phase 26: Optimization & Polish
**Goal:** Performance and UX polish.
- [ ] Caching for expensive API calls
- [ ] Cost optimization (prompt compression)
- [ ] Final UI polish

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
                           │                               ├──> Phase 25 (Tooling/API)
                           └──> Phase 26 (Optimization) ───┘
```

> **See `tests/evaluations/EVALUATION_GUIDE.md` for evaluation framework documentation.**

