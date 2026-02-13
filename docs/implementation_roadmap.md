# Tripzy: Implementation Roadmap (Dependency-Ordered)

This roadmap is ordered by **logical dependencies** - each phase builds on the previous ones.

---

## ✅ COMPLETED PHASES (1-10)

### Phase 1-6: Foundation & Core Features (Completed)
- [x] Repo Setup, Secrets, Observability
- [x] Basic Graph structure & API
- [x] Travel State & Planner Node (Mock Mode)
- [x] Wikivoyage Search Tool & Researcher Node
- [x] Critique Node & Self-Correction Loop
- [x] Pinecone Integration & Memory
- [x] Course Mandatory APIs & Budget Guardrail

### Phase 7: Deployment (Partially Complete)
- [x] Dockerfile created
- [ ] Deploy to Render (User action required)

### Phase 8-10: Premium UI & Streaming (Completed)
- [x] Modern Dashboard UI with glassmorphism
- [x] Real-time streaming with SSE
- [x] Human-in-the-loop approval flow

---

## 🔧 CURRENT PRIORITIES (Phases 11-15)

### Phase 11: Critical Bug Fixes (DO FIRST)
**Goal:** Fix immediate issues blocking quality plans.
- [ ] **Step 11.1: Duration Handling Fix** (CRITICAL)
  - Improve duration extraction from user input (e.g., "2 weeks" → 14 days)
  - Update Planner prompt to enforce exact duration
  - Add Critique validation to reject plans with wrong number of days
  - **Why first:** Affects ALL plans, easy to fix, high impact

### Phase 12: Edge Case Detection & Validation
**Goal:** Prevent wasted computation on impossible requests.
- [ ] Detect impossible budgets (e.g., $20 for a week) and inform user
- [ ] Identify conflicting requirements (luxury on tiny budget)
- [ ] Validate date feasibility (no past dates)
- [ ] Handle extreme group sizes (100+ people) with special booking notes
- [ ] Provide realistic budget estimates when requirements conflict
- [ ] Suggest alternatives instead of failing silently
- [ ] **Test Coverage:** `extreme_budget_impossible`, `extreme_budget_very_tight`, `edge_case_conflicting_requirements`, `edge_case_impossible_dates`, `edge_case_zero_budget`, `edge_case_group_size_100`
- [ ] **Why early:** Saves computation, improves UX, gates bad requests

### Phase 13: Robustness & Error Handling
**Goal:** Make the agent resilient to API failures and user interrupts.
- [x] Global Error Boundary in Supervisor
- [ ] Retry Logic: Implement exponential backoff for API calls
- [x] User Feedback Loop: Ask clarifying questions instead of failing
- [ ] **Why early:** Prevents crashes, improves reliability

### Phase 14: Multi-Turn Conversation Memory (CRITICAL - BLOCKS EVERYTHING)
**Goal:** Enable natural conversation flow with progressive information gathering.
- [ ] Maintain conversation context across multiple turns via thread_id
- [ ] Extract and accumulate user preferences progressively
- [ ] Ask targeted follow-up questions based on previous responses
- [ ] Support iterative refinement of trip requirements
- [ ] Remember partial information from earlier turns
- [ ] Update state with each new piece of information tracked
- [ ] Frontend: Keep thread_id consistent, add "New Trip" button
- [ ] **Test Coverage:** All `conversation_turns` test cases
- [ ] **Why critical:** BLOCKS phases 15, 16, 17, 18. Everything depends on this.
- [ ] **Dependencies:** None (can implement now)

### Phase 15: Golden Dataset Evaluation System
**Goal:** Automated testing and quality assurance.
- [x] Create enriched golden dataset with 30 comprehensive test cases
- [x] Implement enhanced evaluation framework with LLM-as-judge
- [x] Create automated test runner for golden dataset
- [ ] **Step 15.1:** Integrate with agent invocation (currently uses mock)
- [ ] **Step 15.2:** Generate evaluation reports with scores and insights
- [ ] **Step 15.3:** Set up CI/CD integration for automated testing
- [ ] **Step 15.4:** Track evaluation scores over time to measure improvements
- [ ] **Note:** Use OpenAI API key for LLM-as-judge evaluations
- [ ] **Documentation:** See `tests/evaluations/EVALUATION_GUIDE.md`
- [ ] **Why early:** Track progress as we implement features

---

## 🎯 CORE FEATURES (Phases 16-19)

### Phase 16: Conversational Enhancement
**Goal:** Improve information gathering through conversation.
- [ ] Update Supervisor to collect missing information (destination, budget, duration)
- [ ] Detect when information is missing vs when request is vague
- [ ] Ask ONE clarifying question at a time (not overwhelming)
- [ ] Use conversation memory from Phase 14
- [ ] **Dependencies:** Phase 14 (Multi-Turn Memory)
- [ ] **Why here:** Builds directly on conversation memory

### Phase 17: Destination Discovery
**Goal:** Help users discover and choose destinations before planning.
- [ ] Create `Destination_Advisor` node
- [ ] Ask about travel style, interests, climate preferences
- [ ] Generate 3-5 destination suggestions based on preferences
- [ ] Handle user selection and confirm before planning
- [ ] **Dependencies:** Phase 14 (conversation), Phase 16 (information gathering)
- [ ] **Why here:** Needs conversation to gather preferences

### Phase 18: Vague Request & Destination Discovery
**Goal:** Handle requests without specific destinations.
- [ ] Extract location preferences from vague requests ("romantic honeymoon with beaches")
- [ ] Implement destination suggestion logic based on criteria (budget, interests, climate)
- [ ] Suggest 3-5 appropriate destinations with explanations
- [ ] Ask clarifying questions about region, budget, duration
- [ ] Support multi-turn information gathering for destination selection
- [ ] **Test Coverage:** `vague_romantic_honeymoon_beaches`, `vague_family_europe`, `vague_caravan_trip`
- [ ] **Dependencies:** Phase 14 (multi-turn), Phase 16 (conversation), Phase 17 (destination advisor)
- [ ] **Why here:** Combines conversation + destination discovery

### Phase 19: Hotel & Flight Integration
**Goal:** Include accommodation and flights in trip plans.
- [ ] Gather origin city and travel dates from user
- [ ] Create `search_flights_tool()` (mock or Amadeus API)
- [ ] Create `search_hotels_tool()` (mock or Booking.com API)
- [ ] Update Planner schema to include flights and accommodation
- [ ] Update UI formatter to display flights, hotels, and budget breakdown
- [ ] **Dependencies:** Phase 16 (gather missing info like origin city)
- [ ] **Why here:** Need to gather origin/dates via conversation first

---

## 🎨 FLEXIBILITY & PERSONALIZATION (Phases 20-22)

### Phase 20: Partial Plan Support
**Goal:** Support different types of plans based on user needs.
- [ ] Detect plan type from user request (attractions-only, flights-only, full plan)
- [ ] Support attractions-only requests (when user has hotel/flights)
- [ ] Support flights-only requests
- [ ] Support full comprehensive plans (everything)
- [ ] Respect existing bookings and don't re-plan those components
- [ ] Update plan schema to be modular (optional flights, hotels, activities)
- [ ] **Test Coverage:** `attractions_only_request`, `full_plan_request`, `flights_only_request`
- [ ] **Dependencies:** Phase 19 (need all components to exist first)
- [ ] **Why here:** Makes components modular after they all exist

### Phase 21: Special Requirements Handling
**Goal:** Accommodate special needs and preferences.
- [ ] Accessibility features (wheelchair access, mobility needs, elevator requirements)
- [ ] Dietary restrictions (vegan, allergies, kosher, halal, gluten-free)
- [ ] Pet-friendly accommodations and activities
- [ ] Sustainable/eco-tourism preferences (eco-lodges, carbon offset)
- [ ] Digital nomad requirements (WiFi, coworking spaces, desk setup)
- [ ] Verify accommodations meet special requirements
- [ ] Provide emergency language phrases and medical facility info
- [ ] **Test Coverage:** `special_accessibility_needs`, `special_dietary_restrictions`, `pet_friendly_trip`, `sustainable_eco_tourism`, `digital_nomad_month`
- [ ] **Dependencies:** Phase 14 (conversation to extract requirements), Phase 19 (hotels to verify)
- [ ] **Why here:** Enhancement on top of working core features

### Phase 22: User Personalization & Learning
**Goal:** Remember and learn from user preferences.
- [ ] Create user profile database (Supabase)
- [ ] Extract preferences from conversation (dietary, interests, travel style)
- [ ] Personalize destination suggestions and activity recommendations
- [ ] Learn from trip feedback to improve future recommendations
- [ ] **Dependencies:** Phase 14 (conversation), Phase 17 (destination suggestions)
- [ ] **Why here:** Enhancement after core features work

---

## 🚀 OPTIMIZATION & SCALE (Phases 23-25)

### Phase 23: Automated Testing
**Goal:** Ensure stability across updates.
- [ ] Unit Tests: Test individual nodes (Planner, Researcher)
- [ ] Integration Tests: End-to-end flow validation
- [ ] **Dependencies:** Core features should be mostly stable
- [ ] **Why here:** Test stable features, prevent regressions

### Phase 24: Cost Optimization
**Goal:** Reduce token usage while maintaining quality.
- [ ] Prompt Compression: Shorten system prompts without losing context
- [ ] Caching: Implement aggressive caching for Research steps
- [ ] Model Routing: Use cheaper models for simple routing tasks
- [ ] **Dependencies:** Core features complete
- [ ] **Why last:** Optimize after everything works

### Phase 25: Debugging & Stabilization
**Goal:** Continuous improvement and polish.
- [x] Reproduce & Fix "No Answer": SSE stream fixes
- [ ] Verify API Integration: Ensure cost-effective model usage (OpenAI for now)
- [ ] UI Polish: Fix status indicators (`Connecting...` vs `Completed`)
- [ ] **Why continuous:** Ongoing as we develop

---

## 📊 DEPENDENCY DIAGRAM

```
Phase 11 (Bug Fixes) ──┐
Phase 12 (Edge Cases) ─┤
Phase 13 (Robustness) ─┤
                       ├──> Phase 14 (Multi-Turn Memory) ──┐
                       │                                     │
                       │    ┌────────────────────────────────┘
                       │    │
Phase 15 (Evaluation)──┤    ├──> Phase 16 (Conversation) ──┐
                            │                                │
                            ├──> Phase 17 (Dest Discovery) ─┤
                            │                                ├──> Phase 18 (Vague Requests)
                            ├──────────────────────────────> │
                            │                                │
                            ├──> Phase 19 (Hotels/Flights) ─┼──> Phase 20 (Partial Plans)
                            │                                │
                            ├────────────────────────────────┼──> Phase 21 (Special Req)
                            │                                │
                            └────────────────────────────────┴──> Phase 22 (Personalization)
                                                             
                                                             ├──> Phase 23 (Testing)
                                                             ├──> Phase 24 (Optimization)
                                                             └──> Phase 25 (Polish)
```

---

## 🎯 CRITICAL PATH (Recommended Order)

**Week 1-2: Foundation**
1. Phase 11: Bug Fixes (Duration handling) - 2 days
2. Phase 12: Edge Case Detection - 3 days
3. Phase 13: Robustness (complete) - 2 days
4. Phase 14: Multi-Turn Memory - 5 days ⚠️ CRITICAL BLOCKER

**Week 3: Core Conversations**
5. Phase 15: Evaluation Integration - 2 days
6. Phase 16: Conversational Enhancement - 4 days

**Week 4: Destination & Planning**
7. Phase 17: Destination Discovery - 3 days
8. Phase 18: Vague Requests - 4 days

**Week 5: Complete Plans**
9. Phase 19: Hotels & Flights - 5 days

**Week 6: Flexibility**
10. Phase 20: Partial Plans - 3 days
11. Phase 21: Special Requirements - 4 days

**Week 7+: Enhancement**
12. Phase 22: Personalization - 5 days
13. Phase 23: Testing - ongoing
14. Phase 24: Optimization - ongoing
15. Phase 25: Polish - ongoing

---

## 🔑 KEY INSIGHTS

1. **Phase 14 (Multi-Turn Memory) is the biggest blocker** - Most features depend on it
2. **Bug fixes first** - Quick wins improve all tests
3. **Edge cases early** - Prevent wasted computation
4. **Conversation before discovery** - Need to gather info before suggesting
5. **Complete planning before partial** - Need all components before making them optional
6. **Optimization last** - Optimize after it works

---

## 📝 NOTES

- **OpenAI API**: Use OpenAI API key for LLM-as-judge evaluations (Phase 15)
- **Gemini for agent**: Continue using Gemini for the main agent (cost-effective)
- **Test-driven**: Run golden dataset evaluation after each phase
- **Incremental**: Each phase should be small and testable

---

> **See `enhancement_plan.md` for detailed implementation steps and architecture analysis.**
> **See `tests/evaluations/EVALUATION_GUIDE.md` for evaluation framework documentation.**
