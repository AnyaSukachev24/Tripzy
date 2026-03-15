"""
Quick test to verify cost tracking via HTTP request to running server.
"""
import requests
import json

def test_cost_tracking_via_api():
    """Test cost tracking by calling the API endpoint."""
    print("Testing cost tracking via API...")
    
    url = "http://localhost:8000/api/execute"
    payload = {
        "prompt": "Hi",
        "thread_id": "test-cost-tracking"
    }
    
    try:
        print(f"Sending request to {url}...")
        response = requests.post(url, json=payload)
        
        print(f"\nResponse Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {data.get('response', 'No response')[:100]}")
            print(f"Status: {data.get('status')}")
            print("\n✅ API test PASSED!")
            print("\nCheck the server logs above for [COST TRACKING] output")
            return True
        else:
            print(f"❌ API test FAILED: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ API test FAILED: {e}")
        return False

if __name__ == "__main__":
    import sys
    success = test_cost_tracking_via_api()
    sys.exit(0 if success else 1)
