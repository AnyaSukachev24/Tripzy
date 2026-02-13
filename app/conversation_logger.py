import json
import os
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path


class ConversationLogger:
    """Logs UI conversation runs to dedicated folder for review and debugging."""
    
    def __init__(self, base_dir: str = "ui-runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        
    def log_message(self, thread_id: str, role: str, content: str, metadata: Dict[str, Any] | None = None):
        """Log a single message to the conversation history."""
        if thread_id not in self.conversations:
            self.conversations[thread_id] = []
            
        message = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content,
            "metadata": metadata or {}
        }
        
        self.conversations[thread_id].append(message)
        
    def log_state_snapshot(self, thread_id: str, state: Dict[str, Any]):
        """Log the full state snapshot at a given point."""
        if thread_id not in self.conversations:
            self.conversations[thread_id] = []
            
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "type": "state_snapshot",
            "state": state
        }
        
        self.conversations[thread_id].append(snapshot)
        
    def save_conversation(self, thread_id: str, final_result: Any = None):
        """Save the full conversation to a JSON file."""
        if thread_id not in self.conversations:
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use only first 8 chars of thread_id safely
        thread_short = str(thread_id)[:8] if len(str(thread_id)) >= 8 else str(thread_id)
        filename = f"run_{timestamp}_{thread_short}.json"
        filepath = self.base_dir / filename
        
        conversation_data = {
            "thread_id": thread_id,
            "started_at": self.conversations[thread_id][0]["timestamp"] if self.conversations[thread_id] else None,
            "ended_at": datetime.now().isoformat(),
            "messages": self.conversations[thread_id],
            "final_result": final_result
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)
            
        return str(filepath)
        
    def get_conversation(self, thread_id: str) -> List[Dict[str, Any]]:
        """Retrieve conversation history for a given thread."""
        return self.conversations.get(thread_id, [])


# Global instance
conversation_logger = ConversationLogger()
