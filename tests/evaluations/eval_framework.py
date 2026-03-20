"""
LLM-as-Judge Evaluation Framework for Tripzy (Enhanced)
Uses an LLM to evaluate the quality of generated travel plans.
Supports multi-turn conversations, edge cases, partial plans, and special requirements.
"""
import os
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("LLMOD_API_KEY")

if not api_key:
    raise RuntimeError("LLMOD_API_KEY is not set. Cannot initialize evaluation LLM.")

# Initialize LLM for evaluation
eval_llm = ChatOpenAI(
    model=os.environ.get("LLM_MODEL", "RPRTHPB-gpt-5-mini"),
    api_key=api_key,
    base_url=os.environ.get("LLMOD_BASE_URL", "https://api.llmod.ai/v1")
)

# ==============================================================================
# EVALUATION MODELS
# ==============================================================================

class CostRealismEvaluation(BaseModel):
    """Evaluation of cost realism"""
    score: float = Field(description="Score from 0-1, where 1 is perfectly realistic")
    reasoning: str = Field(description="Explanation of the score")
    issues: list[str] = Field(description="List of unrealistic costs found", default=[])


class PreferenceAlignmentEvaluation(BaseModel):
    """Evaluation of alignment with trip type preferences"""
    score: float = Field(description="Score from 0-1, where 1 is perfect alignment")
    reasoning: str = Field(description="Explanation of the score")
    matched_preferences: list[str] = Field(description="Preferences that were matched")
    missed_preferences: list[str] = Field(description="Preferences that were missed")


class MultiTurnEvaluation(BaseModel):
    """Evaluation of multi-turn conversation handling"""
    score: float = Field(description="Score from 0-1, where 1 is perfect conversation handling")
    reasoning: str = Field(description="Explanation of the score")
    appropriate_questions_asked: list[str] = Field(description="Good questions the agent asked")
    missing_questions: list[str] = Field(description="Important questions the agent should have asked")
    conversation_quality: str = Field(description="Overall quality assessment of conversation flow")


class EdgeCaseHandlingEvaluation(BaseModel):
    """Evaluation of edge case detection and handling"""
    score: float = Field(description="Score from 0-1, where 1 is perfect edge case handling")
    reasoning: str = Field(description="Explanation of the score")
    correctly_identified_issues: list[str] = Field(description="Edge cases properly identified")
    missed_issues: list[str] = Field(description="Edge cases that should have been caught")
    appropriate_response: bool = Field(description="Whether agent responded appropriately to edge case")
    suggestions_provided: bool = Field(description="Whether agent provided helpful alternatives")


class PlanTypeEvaluation(BaseModel):
    """Evaluation of plan type compliance (full plan vs partial)"""
    score: float = Field(description="Score from 0-1, where 1 is perfect compliance")
    reasoning: str = Field(description="Explanation of the score")
    correctly_included: list[str] = Field(description="Components that should be included and were")
    correctly_excluded: list[str] = Field(description="Components that should be excluded and were")
    incorrectly_included: list[str] = Field(description="Components included that shouldn't be")
    incorrectly_excluded: list[str] = Field(description="Components missing that should be included")


class SpecialRequirementsEvaluation(BaseModel):
    """Evaluation of special requirements handling"""
    score: float = Field(description="Score from 0-1, where 1 is perfect handling")
    reasoning: str = Field(description="Explanation of the score")
    requirements_met: list[str] = Field(description="Special requirements properly addressed")
    requirements_missed: list[str] = Field(description="Special requirements not addressed")
    verifications_included: bool = Field(description="Whether agent verified special accommodations")


class VagueRequestEvaluation(BaseModel):
    """Evaluation of vague request handling and destination suggestions"""
    score: float = Field(description="Score from 0-1, where 1 is perfect handling")
    reasoning: str = Field(description="Explanation of the score")
    clarifying_questions_asked: list[str] = Field(description="Clarifying questions the agent asked")
    destination_suggestions: list[str] = Field(description="Destinations suggested by agent")
    suggestions_appropriateness: str = Field(description="How appropriate the suggestions were")


# ==============================================================================
# EVALUATION PROMPTS
# ==============================================================================

COST_REALISM_PROMPT = """You are an expert travel cost analyst. Evaluate if the costs in this itinerary are realistic for the destination.

TRIP PLAN:
{trip_plan}

DESTINATION: {destination}
TRIP TYPE: {trip_type}
DURATION: {duration_days} days

COST REALISM GUIDELINES:
For {destination}, typical costs are:
- Budget accommodation: $20-50/night
- Mid-range accommodation: $50-150/night  
- Luxury accommodation: $150-400/night
- Meals: $5-30/meal depending on tier
- Activities: $10-100/activity
- Local transport: $5-30/day

Evaluate if the costs in the itinerary are realistic. Consider:
1. Are hotel prices appropriate for the tier and destination?
2. Are activity costs reasonable?
3. Are meal costs realistic?
4. Is the total cost reasonable for {duration_days} days?

Return your evaluation as JSON with:
- score: float 0-1 (1 = perfectly realistic)
- reasoning: string explaining your assessment
- issues: list of any unrealistic costs you found
"""

PREFERENCE_ALIGNMENT_PROMPT = """You are a travel planning expert. Evaluate if this itinerary matches the trip type and user preferences.

TRIP PLAN:
{trip_plan}

TRIP TYPE: {trip_type}
DURATION: {duration_days} days
EXPECTED ACTIVITIES: {expected_activities}

ALIGNMENT GUIDELINES:
For a {trip_type} trip, we expect:
- Honeymoon: Romantic dinners, spa, private experiences, luxury accommodation
- Family: Kid-friendly activities, museums, parks, family restaurants  
- Adventure: Outdoor activities, trekking, extreme sports, budget accommodation
- Business: Business district hotels, meeting facilities, efficient transport
- Solo/Cultural: Museums, cultural sites, local experiences, social opportunities

Evaluate if the activities and accommodation match the trip type. Consider:
1. Are activities appropriate for {trip_type}?
2. Is accommodation tier suitable?
3. Are expected activities included?
4. Is the daily pacing appropriate?

Return your evaluation as JSON with:
- score: float 0-1 (1 = perfect alignment)
- reasoning: string explaining your assessment
- matched_preferences: list of preferences that were matched
- missed_preferences: list of expected preferences that were missed
"""

MULTI_TURN_PROMPT = """You are a conversation quality analyst. Evaluate how well the agent handled this multi-turn conversation.

CONVERSATION HISTORY:
{conversation_history}

EXPECTED QUESTIONS:
{expected_questions}

EXPECTED BEHAVIOR:
{expected_behavior}

Evaluate the conversation quality. Consider:
1. Did the agent ask appropriate clarifying questions?
2. Did the agent gather all necessary information progressively?
3. Was the conversation flow natural and helpful?
4. Did the agent remember context between turns?
5. Were there critical questions the agent should have asked but didn't?

Return your evaluation as JSON with:
- score: float 0-1 (1 = perfect conversation)
- reasoning: string explaining your assessment
- appropriate_questions_asked: list of good questions the agent asked
- missing_questions: list of important questions the agent should have asked
- conversation_quality: string describing overall quality
"""

EDGE_CASE_PROMPT = """You are an expert at detecting problematic or impossible travel requests. Evaluate how well the agent handled this edge case.

USER REQUEST:
{user_request}

AGENT RESPONSE:
{agent_response}

EDGE CASE TYPE: {edge_case_type}
EXPECTED AGENT BEHAVIOR: {expected_behavior}

Evaluate the agent's edge case handling. Consider:
1. Did the agent correctly identify the issue (impossible budget, conflicting requirements, etc.)?
2. Did the agent explain the problem clearly to the user?
3. Did the agent provide helpful alternatives or suggestions?
4. Was the response appropriate and professional?

Return your evaluation as JSON with:
- score: float 0-1 (1 = perfect handling)
- reasoning: string explaining your assessment
- correctly_identified_issues: list of edge cases properly identified
- missed_issues: list of edge cases that should have been caught
- appropriate_response: boolean whether response was appropriate
- suggestions_provided: boolean whether alternatives were offered
"""

PLAN_TYPE_PROMPT = """You are a travel plan completeness analyst. Evaluate if the plan includes the correct components.

TRIP PLAN:
{trip_plan}

REQUESTED PLAN TYPE: {plan_type}
SHOULD INCLUDE: {should_include}
SHOULD NOT INCLUDE: {should_not_include}

Evaluate plan component compliance. Consider:
1. If user has flights/hotels, did agent avoid rebooking them?
2. If user asked for attractions only, did plan include only attractions?
3. If user asked for full plan, are all components present?
4. Are there any unnecessary components included?

Return your evaluation as JSON with:
- score: float 0-1 (1 = perfect compliance)
- reasoning: string explaining your assessment
- correctly_included: list of components that should be included and were
- correctly_excluded: list of components that should be excluded and were
- incorrectly_included: list of components included that shouldn't be
- incorrectly_excluded: list of components missing that should be included
"""

SPECIAL_REQUIREMENTS_PROMPT = """You are an accessibility and special needs travel expert. Evaluate how well the plan addresses special requirements.

TRIP PLAN:
{trip_plan}

SPECIAL REQUIREMENTS: {special_requirements}
REQUIREMENT DETAILS: {requirement_details}

Evaluate special requirements handling. Consider:
1. Are accommodations appropriate for the special needs?
2. Are activities accessible/suitable?
3. Did agent verify accommodations (e.g., wheelchair access, vegan menus)?
4. Are emergency considerations addressed (e.g., language phrases, medical facilities)?

Return your evaluation as JSON with:
- score: float 0-1 (1 = perfect handling)
- reasoning: string explaining your assessment
- requirements_met: list of requirements properly addressed
- requirements_missed: list of requirements not addressed
- verifications_included: boolean whether accommodations were verified
"""

VAGUE_REQUEST_PROMPT = """You are a destination recommendation expert. Evaluate how well the agent handled a vague location request.

USER REQUEST:
{user_request}

AGENT RESPONSE:
{agent_response}

EXPECTED CLARIFYING QUESTIONS: {expected_questions}
EXPECTED DESTINATIONS: {expected_destinations}

Evaluate vague request handling. Consider:
1. Did the agent ask clarifying questions about preferences, budget, duration?
2. Were destination suggestions appropriate for the criteria (e.g., "romantic beaches")?
3. Were multiple options provided?
4. Did the agent explain why each destination fits the criteria?

Return your evaluation as JSON with:
- score: float 0-1 (1 = perfect handling)
- reasoning: string explaining your assessment
- clarifying_questions_asked: list of clarifying questions asked
- destination_suggestions: list of destinations suggested
- suggestions_appropriateness: string describing how well suggestions match criteria
"""


# ==============================================================================
# EVALUATION FUNCTIONS
# ==============================================================================

def evaluate_cost_realism(
    trip_plan: Dict[str, Any], 
    destination: str, 
    trip_type: str, 
    duration_days: int
) -> CostRealismEvaluation:
    """Use LLM to evaluate cost realism"""
    prompt = ChatPromptTemplate.from_template(COST_REALISM_PROMPT)
    chain = prompt | eval_llm.with_structured_output(CostRealismEvaluation)
    
    result = chain.invoke({
        "trip_plan": str(trip_plan),
        "destination": destination,
        "trip_type": trip_type,
        "duration_days": duration_days
    })
    
    return result


def evaluate_preference_alignment(
    trip_plan: Dict[str, Any], 
    trip_type: str, 
    duration_days: int,
    expected_activities: list[str]
) -> PreferenceAlignmentEvaluation:
    """Use LLM to evaluate preference alignment"""
    prompt = ChatPromptTemplate.from_template(PREFERENCE_ALIGNMENT_PROMPT)
    chain = prompt | eval_llm.with_structured_output(PreferenceAlignmentEvaluation)
    
    result = chain.invoke({
        "trip_plan": str(trip_plan),
        "trip_type": trip_type,
        "duration_days": duration_days,
        "expected_activities": ", ".join(expected_activities)
    })
    
    return result


def evaluate_multi_turn_conversation(
    conversation_history: List[Dict[str, str]],
    expected_questions: List[str],
    expected_behavior: str
) -> MultiTurnEvaluation:
    """Use LLM to evaluate multi-turn conversation handling"""
    prompt = ChatPromptTemplate.from_template(MULTI_TURN_PROMPT)
    chain = prompt | eval_llm.with_structured_output(MultiTurnEvaluation)
    
    result = chain.invoke({
        "conversation_history": str(conversation_history),
        "expected_questions": ", ".join(expected_questions),
        "expected_behavior": expected_behavior
    })
    
    return result


def evaluate_edge_case_handling(
    user_request: str,
    agent_response: str,
    edge_case_type: str,
    expected_behavior: str
) -> EdgeCaseHandlingEvaluation:
    """Use LLM to evaluate edge case detection and handling"""
    prompt = ChatPromptTemplate.from_template(EDGE_CASE_PROMPT)
    chain = prompt | eval_llm.with_structured_output(EdgeCaseHandlingEvaluation)
    
    result = chain.invoke({
        "user_request": user_request,
        "agent_response": agent_response,
        "edge_case_type": edge_case_type,
        "expected_behavior": expected_behavior
    })
    
    return result


def evaluate_plan_type_compliance(
    trip_plan: Dict[str, Any],
    plan_type: str,
    should_include: List[str],
    should_not_include: List[str]
) -> PlanTypeEvaluation:
    """Use LLM to evaluate plan type compliance"""
    prompt = ChatPromptTemplate.from_template(PLAN_TYPE_PROMPT)
    chain = prompt | eval_llm.with_structured_output(PlanTypeEvaluation)
    
    result = chain.invoke({
        "trip_plan": str(trip_plan),
        "plan_type": plan_type,
        "should_include": ", ".join(should_include),
        "should_not_include": ", ".join(should_not_include)
    })
    
    return result


def evaluate_special_requirements(
    trip_plan: Dict[str, Any],
    special_requirements: str,
    requirement_details: str
) -> SpecialRequirementsEvaluation:
    """Use LLM to evaluate special requirements handling"""
    prompt = ChatPromptTemplate.from_template(SPECIAL_REQUIREMENTS_PROMPT)
    chain = prompt | eval_llm.with_structured_output(SpecialRequirementsEvaluation)
    
    result = chain.invoke({
        "trip_plan": str(trip_plan),
        "special_requirements": special_requirements,
        "requirement_details": requirement_details
    })
    
    return result


def evaluate_vague_request_handling(
    user_request: str,
    agent_response: str,
    expected_questions: List[str],
    expected_destinations: List[str]
) -> VagueRequestEvaluation:
    """Use LLM to evaluate vague request handling"""
    prompt = ChatPromptTemplate.from_template(VAGUE_REQUEST_PROMPT)
    chain = prompt | eval_llm.with_structured_output(VagueRequestEvaluation)
    
    result = chain.invoke({
        "user_request": user_request,
        "agent_response": agent_response,
        "expected_questions": ", ".join(expected_questions),
        "expected_destinations": ", ".join(expected_destinations)
    })
    
    return result


# ==============================================================================
# MAIN EVALUATION ORCHESTRATOR
# ==============================================================================

def evaluate_test_case(agent_output: Any, test_case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main evaluation orchestrator. Routes to appropriate evaluators based on test case type.
    
    Args:
        agent_output: The agent's response (could be plan, conversation, or error message)
        test_case: The golden dataset test case with expected behavior
        
    Returns:
        Comprehensive evaluation results
    """
    results = {
        "test_id": test_case.get("id", "unknown"),
        "test_description": test_case.get("description", ""),
        "generated_plan": agent_output.get("trip_plan", {}), # Added for debugging
        "evaluations": {},
        "overall_score": 0.0,
        "passed": False
    }
    
    # Detect test case type
    is_multi_turn = "conversation_turns" in test_case
    is_edge_case = test_case.get("expected", {}).get("should_flag_impossible") or \
                   test_case.get("expected", {}).get("should_flag_conflict")
    has_plan_type = "plan_type" in test_case.get("expected", {})
    has_special_requirements = "special_requirements" in test_case.get("expected", {})
    is_vague_request = test_case.get("id", "").startswith("vague_")
    
    scores = []
    
    # 1. Multi-turn conversation evaluation
    if is_multi_turn:
        # Extract conversation history from agent_output
        conversation_history = agent_output.get("conversation", [])
        turns = test_case["conversation_turns"]
        
        # Evaluate each turn
        for turn_data in turns:
            multi_turn_eval = evaluate_multi_turn_conversation(
                conversation_history=conversation_history,
                expected_questions=turn_data.get("agent_should_ask", []),
                expected_behavior=turn_data.get("expected_behavior", "")
            )
            
            results["evaluations"][f"multi_turn_turn_{turn_data['turn']}"] = {
                "score": multi_turn_eval.score,
                "reasoning": multi_turn_eval.reasoning,
                "appropriate_questions": multi_turn_eval.appropriate_questions_asked,
                "missing_questions": multi_turn_eval.missing_questions
            }
            scores.append(multi_turn_eval.score)
    
    # 2. Edge case handling evaluation
    if is_edge_case:
        edge_eval = evaluate_edge_case_handling(
            user_request=test_case.get("user_query", ""),
            agent_response=str(agent_output),
            edge_case_type=test_case.get("description", ""),
            expected_behavior=test_case.get("expected", {}).get("agent_should_explain", "")
        )
        
        results["evaluations"]["edge_case_handling"] = {
            "score": edge_eval.score,
            "reasoning": edge_eval.reasoning,
            "identified_issues": edge_eval.correctly_identified_issues,
            "appropriate_response": edge_eval.appropriate_response
        }
        scores.append(edge_eval.score)
    
    # 3. Vague request evaluation
    if is_vague_request:
        vague_eval = evaluate_vague_request_handling(
            user_request=test_case.get("user_query", "") or test_case["conversation_turns"][0]["user_query"],
            agent_response=str(agent_output),
            expected_questions=test_case.get("conversation_turns", [{}])[0].get("agent_should_ask", []),
            expected_destinations=test_case.get("final_expected", {}).get("destination", [])
        )
        
        results["evaluations"]["vague_request_handling"] = {
            "score": vague_eval.score,
            "reasoning": vague_eval.reasoning,
            "clarifying_questions": vague_eval.clarifying_questions_asked,
            "destination_suggestions": vague_eval.destination_suggestions
        }
        scores.append(vague_eval.score)
    
    # 4. Plan type compliance evaluation
    if has_plan_type and not is_edge_case:
        trip_plan = agent_output.get("trip_plan", {})
        expected = test_case["expected"]
        
        plan_type_eval = evaluate_plan_type_compliance(
            trip_plan=trip_plan,
            plan_type=expected.get("plan_type", "full"),
            should_include=expected.get("should_include", []),
            should_not_include=expected.get("should_not_include", [])
        )
        
        results["evaluations"]["plan_type_compliance"] = {
            "score": plan_type_eval.score,
            "reasoning": plan_type_eval.reasoning,
            "correctly_included": plan_type_eval.correctly_included,
            "incorrectly_included": plan_type_eval.incorrectly_included
        }
        scores.append(plan_type_eval.score)
    
    # 5. Special requirements evaluation
    if has_special_requirements:
        trip_plan = agent_output.get("trip_plan", {})
        expected = test_case["expected"]
        
        special_eval = evaluate_special_requirements(
            trip_plan=trip_plan,
            special_requirements=expected.get("special_requirements", ""),
            requirement_details=str(expected.get("validation_rules", {}))
        )
        
        results["evaluations"]["special_requirements"] = {
            "score": special_eval.score,
            "reasoning": special_eval.reasoning,
            "requirements_met": special_eval.requirements_met,
            "verifications_included": special_eval.verifications_included
        }
        scores.append(special_eval.score)
    
    # 6. Standard evaluations for complete plans (not edge cases)
    if not is_edge_case and "trip_plan" in agent_output:
        trip_plan = agent_output["trip_plan"]
        expected = test_case.get("expected", test_case.get("final_expected", {}))
        
        # Cost realism
        if "destination" in expected and "duration_days" in expected:
            cost_eval = evaluate_cost_realism(
                trip_plan=trip_plan,
                destination=str(expected["destination"]),
                trip_type=expected.get("trip_type", "general"),
                duration_days=expected["duration_days"]
            )
            
            results["evaluations"]["cost_realism"] = {
                "score": cost_eval.score,
                "reasoning": cost_eval.reasoning,
                "issues": cost_eval.issues
            }
            scores.append(cost_eval.score)
        
        # Preference alignment
        validation_rules = expected.get("validation_rules", {})
        expected_activities = validation_rules.get("activities_should_include", [])
        
        if expected_activities:
            pref_eval = evaluate_preference_alignment(
                trip_plan=trip_plan,
                trip_type=expected.get("trip_type", "general"),
                duration_days=expected.get("duration_days", 7),
                expected_activities=expected_activities
            )
            
            results["evaluations"]["preference_alignment"] = {
                "score": pref_eval.score,
                "reasoning": pref_eval.reasoning,
                "matched": pref_eval.matched_preferences,
                "missed": pref_eval.missed_preferences
            }
            scores.append(pref_eval.score)
    
    # Calculate overall score
    if scores:
        results["overall_score"] = sum(scores) / len(scores)
        results["passed"] = results["overall_score"] >= 0.7  # 70% threshold
    
    return results
