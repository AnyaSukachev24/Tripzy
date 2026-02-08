import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_team_info():
    print(f"\n--- Testing /api/team_info ---")
    try:
        response = requests.get(f"{BASE_URL}/api/team_info")
        print(f"Status: {response.status_code}")
        print(f"Body: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

def test_agent_info():
    print(f"\n--- Testing /api/agent_info ---")
    try:
        response = requests.get(f"{BASE_URL}/api/agent_info")
        print(f"Status: {response.status_code}")
        print(f"Body: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

def test_execute():
    print(f"\n--- Testing /api/execute ---")
    payload = {"prompt": "Plan a 1-day trip to London."}
    try:
        # This might take a while if LLM is slow
        response = requests.post(f"{BASE_URL}/api/execute", json=payload, timeout=60)
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Response: {data.get('response')}")
        print(f"Steps: {len(data.get('steps', []))} steps executed.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Wait a bit for server to be fully ready
    time.sleep(2)
    test_team_info()
    test_agent_info()
    test_execute()
