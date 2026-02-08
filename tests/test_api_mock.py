import sys
import os
from unittest.mock import MagicMock

# 1. Mock app.graph BEFORE importing app.main
# This prevents app.main from triggering graph initialization/imports
mock_graph_module = MagicMock()
sys.modules["app.graph"] = mock_graph_module

# Mock the graph object and its methods
mock_compiled_graph = MagicMock()
mock_graph_module.graph = mock_compiled_graph

# Mock get_graph().draw_mermaid_png()
mock_compiled_graph.get_graph.return_value.draw_mermaid_png.return_value = b"fake_image_data"

# Mock invoke() logic
def mock_invoke(input_payload, config=None):
    # Mimic successful execution
    return {
        "trip_plan": {"destination": "Paris", "cost": 500},
        "supervisor_instruction": "Plan ready.",
        "steps": [{"module": "Planner", "response": "Done"}]
    }
mock_compiled_graph.invoke.side_effect = mock_invoke

# Import app.main
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from fastapi.testclient import TestClient
    from app.main import app
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

client = TestClient(app)

def test_api_endpoints():
    print("--- TESTING API ENDPOINTS ---")
    
    # 1. Team Info
    print("\n[1] GET /api/team_info")
    response = client.get("/api/team_info")
    if response.status_code == 200:
        print("✅ SUCCESS: Team Info returned 200.")
        print(response.json())
    else:
        print(f"❌ FAILURE: {response.status_code}")

    # 2. Agent Info
    print("\n[2] GET /api/agent_info")
    response = client.get("/api/agent_info")
    if response.status_code == 200:
        print("✅ SUCCESS: Agent Info returned 200.")
    else:
        print(f"❌ FAILURE: {response.status_code}")

    # 3. Model Architecture
    print("\n[3] GET /api/model_architecture")
    response = client.get("/api/model_architecture")
    if response.status_code == 200 and response.headers["content-type"] == "image/png":
        print("✅ SUCCESS: Graph Image returned 200 PNG.")
    else:
        print(f"❌ FAILURE: {response.status_code}")

    # 4. Execute (POST)
    print("\n[4] POST /api/execute")
    payload = {"prompt": "Plan a trip to Paris"}
    response = client.post("/api/execute", json=payload)
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "ok" and "Paris" in data["response"]:
            print("✅ SUCCESS: Execution returned valid response.")
            print(f"Response: {data['response']}")
        else:
            print(f"❌ FAILURE: Invalid response body: {data}")
    else:
        print(f"❌ FAILURE: {response.status_code}")

if __name__ == "__main__":
    test_api_endpoints()
