
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from app.prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT
from app.state import AgentState
from typing import Literal, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()
print(f"DEBUG: OPENAI_API_KEY present: {'OPENAI_API_KEY' in os.environ}")
print(f"DEBUG: Current CWD: {os.getcwd()}")
print(f"DEBUG: .env exists: {Path('.env').exists()}")

# Define Supervisor Output Schema (same as in graph.py)
class SupervisorOutput(BaseModel):
    next_step: Literal["Trip_Planner", "Researcher", "End"] = Field(description="The next agent to call")
    reasoning: str = Field(description="Reason for choosing this step")
    instruction: str = Field(description="Instruction for the next agent")
    duration_days: int = Field(description="Trip duration in days", default=0)
    destination: str = Field(description="Trip destination", default="")
    budget_limit: float = Field(description="Budget limit", default=0.0)
    budget_currency: str = Field(description="Currency", default="USD")
    trip_type: str = Field(description="Type of trip", default="")

# Setup LLM
if os.getenv("AZURE_OPENAI_API_KEY"):
    print("DEBUG: Using Azure OpenAI")
    llm = AzureChatOpenAI(
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1-mini"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        temperature=0
    )
else:
    print("DEBUG: Using Standard OpenAI")
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

# Create Chain
prompt = ChatPromptTemplate.from_messages([
    ("system", SUPERVISOR_SYSTEM_PROMPT),
    ("human", "User Input: {query}")
])

chain = prompt | llm.with_structured_output(SupervisorOutput)

def test_query(query):
    print(f"\nQuery: '{query}'")
    try:
        result = chain.invoke({"query": query})
        print(f"Next Step: {result.next_step}")
        print(f"Instruction: {result.instruction}")
        print(f"Reasoning: {result.reasoning}")
        return result
    except Exception as e:
        print(f"Error: {e}")
        return None

# Test Cases
print("=== TESTING DESTINATION DISCOVERY ROUTING ===")
test_query("Where should I go for a beach trip with $2000?")
test_query("I want to go to Paris for 5 days")
test_query("I want to travel somewhere")

