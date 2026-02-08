import requests
import json

BASE_URL = "http://localhost:8000"

def test_detailed_execute():
    print(f"\n--- Detailed Testing /api/execute ---")
    payload = {"prompt": "Plan a 1-day trip to London."}
    try:
        response = requests.post(f"{BASE_URL}/api/execute", json=payload, timeout=60)
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Final Response: {data.get('response')}")
        print("\nInternal Steps:")
        for idx, step in enumerate(data.get('steps', [])):
            print(f"[{idx+1}] Module: {step.get('module')}")
            print(f"    Prompt: {step.get('prompt')}")
            print(f"    Response: {step.get('response')}")
            print("-" * 20)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_detailed_execute()
