import requests
import json
import uuid
import sys

BASE_URL = "http://localhost:8000"

def run_turn(thread_id, prompt):
    print(f"\n--- User: {prompt} ---")
    url = f"{BASE_URL}/api/stream"
    payload = {"prompt": prompt, "thread_id": thread_id}
    
    response = requests.post(url, json=payload, stream=True)
    
    agent_response = ""
    for line in response.iter_lines():
        if line:
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith("data: "):
                data_str = decoded_line[6:]
                try:
                    data = json.loads(data_str)
                    if data['type'] == 'final_response':
                        agent_response = data['content']
                        print(f"Agent: {agent_response}")
                    elif data['type'] == 'done':
                        break
                    elif data['type'] == 'error':
                        print(f"Error: {data['content']}")
                        break
                except json.JSONDecodeError:
                    pass
    return agent_response

def test_progressive_disclosure():
    thread_id = f"test_session_{uuid.uuid4().hex[:8]}"
    print(f"Starting Session: {thread_id}")
    
    # Turn 1: Vague request
    resp1 = run_turn(thread_id, "I want to go on a trip.")
    
    # Turn 2: Destination
    resp2 = run_turn(thread_id, "Bali")
    
    # Turn 3: Duration
    resp3 = run_turn(thread_id, "2 weeks")
    
    # Turn 4: Budget
    resp4 = run_turn(thread_id, "$5000")
    
    print("\nTest Complete.")

if __name__ == "__main__":
    test_progressive_disclosure()
