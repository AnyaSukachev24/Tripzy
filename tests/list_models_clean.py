import requests
import os
from dotenv import load_dotenv

load_dotenv()

def list_models_clean():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("No API Key")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            
            with open("clean_models.txt", "w", encoding="utf-8") as f:
                for m in models:
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        name = m.get("name").replace("models/", "")
                        f.write(f"{name}\n")
            print("Models saved to clean_models.txt")
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    list_models_clean()
