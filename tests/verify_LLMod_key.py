import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def test_llmod():
    print("--- Verifying LLMOD Connection ---")

    api_key = os.getenv("LLMOD_API_KEY")
    base_url = os.getenv("LLMOD_BASE_URL")
    model = os.getenv("LLM_MODEL")

    print(f"Using model: {model}")
    print(f"API URL: {base_url}")

    with open("verify_output.txt", "w", encoding="utf-8") as f:
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url
            )

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "Hello"}
                ],
                temperature=1
            )

            answer = response.choices[0].message.content

            f.write(f"Success! Response: {answer}\n")

            print("SUCCESS: LLMOD responded.")
            print(answer)

        except Exception as e:
            f.write(f"LLMOD test failed: {str(e)}\n")
            print(f"ERROR: {e}")

if __name__ == "__main__":
    test_llmod()