from langchain_openai import AzureChatOpenAI
import os

# Provided keys
os.environ["AZURE_OPENAI_API_KEY"] = "41HFNBBQi6QbE2fCBk892d8pxAJoC0Wcom01tXjqB8tZujM1geZiJQQJ99BFACYeBjFXJ3w3AAABACOG6TPA"
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://queen-n.openai.azure.com/"
os.environ["AZURE_OPENAI_API_VERSION"] = "2025-01-01-preview"
os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"] = "gpt-4.1-mini" # User provided this, might be typo

def test_azure():
    print("--- Testing Azure OpenAI Keys ---")
    try:
        llm = AzureChatOpenAI(
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            temperature=0
        )
        response = llm.invoke("Hello, are you working?")
        print(f"SUCCESS: {response.content}")
    except Exception as e:
        print(f"FAILURE: {e}")

if __name__ == "__main__":
    test_azure()
