from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class CostCallbackHandler(BaseCallbackHandler):
    """Callback handler to track token usage and estimated costs."""
    
    def __init__(self):
        self.total_tokens = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_calls = 0
        self.model_name = "unknown"
        
    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Run when LLM starts running."""
        self.total_calls += 1
        
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        if response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            self.total_tokens += token_usage.get("total_tokens", 0)
            self.total_prompt_tokens += token_usage.get("prompt_tokens", 0)
            self.total_completion_tokens += token_usage.get("completion_tokens", 0)
            self.model_name = response.llm_output.get("model_name", "unknown")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of tracked costs."""
        # Simple cost estimation (example rates)
        cost_per_1k_tokens = 0.002  # $0.002 per 1K tokens (example)
        total_cost = (self.total_tokens / 1000) * cost_per_1k_tokens
        
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "model_name": self.model_name,
            "total_cost": total_cost
        }
