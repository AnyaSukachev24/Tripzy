import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

def check_models():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("No API Key found.")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    print(f"Querying: {url.replace(api_key, 'API_KEY')}")
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            print(f"Found {len(models)} models:")
            for m in models:
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    print(f"- {m.get('name')} ({m.get('version')})")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    check_models()
