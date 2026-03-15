import os
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

def test_google_key():
    print("--- Verifying Google API Key ---")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ Error: GOOGLE_API_KEY not found in .env")
        return

    print(f"Key found: {api_key[:5]}...{api_key[-5:]}")
    
    with open("verify_output.txt", "w", encoding="utf-8") as f:
        try:
            f.write("Attempting with gemini-flash-latest...\n")
            llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0)
            response = llm.invoke("Hello")
            f.write(f"Success with gemini-flash-latest! Response: {response.content}\n")
            return
        except Exception as e:
            f.write(f"gemini-flash-latest failed: {str(e)}\n")

if __name__ == "__main__":
    test_google_key()
