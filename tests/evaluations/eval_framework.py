"""
LLM-as-Judge Evaluation Framework for Tripzy
Uses an LLM to evaluate the quality of generated travel plans.
"""
import os
from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

# Initialize LLM for evaluation
if os.getenv("AZURE_OPENAI_API_KEY"):
    eval_llm = AzureChatOpenAI(
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        temperature=0
    )
else:
    eval_llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)


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


def evaluate_cost_realism(trip_plan: Dict[str, Any], destination: str, trip_type: str, duration_days: int) -> CostRealismEvaluation:
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


def evaluate_complete_plan(trip_plan: Dict[str, Any], test_case: Dict[str, Any]) -> Dict[str, Any]:
    """Run complete LLM-based evaluation"""
    expected = test_case["expected"]
    
    # Cost realism evaluation
    cost_eval = evaluate_cost_realism(
        trip_plan,
        expected["destination"],
        expected.get("trip_type", "general"),
        expected["duration_days"]
    )
    
    # Preference alignment evaluation
    validation_rules = expected.get("validation_rules", {})
    expected_activities = validation_rules.get("activities_should_include", [])
    
    pref_eval = evaluate_preference_alignment(
        trip_plan,
        expected.get("trip_type", "general"),
        expected["duration_days"],
        expected_activities
    )
    
    # Calculate overall LLM score
    llm_score = (cost_eval.score + pref_eval.score) / 2
    
    return {
        "llm_overall_score": llm_score,
        "cost_realism": {
            "score": cost_eval.score,
            "reasoning": cost_eval.reasoning,
            "issues": cost_eval.issues
        },
        "preference_alignment": {
            "score": pref_eval.score,
            "reasoning": pref_eval.reasoning,
            "matched": pref_eval.matched_preferences,
            "missed": pref_eval.missed_preferences
        }
    }
