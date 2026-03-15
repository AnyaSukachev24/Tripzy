import json
from app.tools import resolve_airport_code_tool


def main():
    # Since it's a LangChain @tool, you can call it using the .invoke() method
    # Or try calling it directly depending on the Langchain version.

    keyword = "Prague"
    print(f"Testing resolve_airport_code_tool with keyword: '{keyword}'\n")

    try:
        # LangChain tools typically expect a dictionary for invoke
        result = resolve_airport_code_tool.invoke({"keyword": keyword})
        print("Result:\n")

        # The tool returns a JSON string, let's format it nicely
        parsed_result = json.loads(result)
        print(json.dumps(parsed_result, indent=2))

    except Exception as e:
        print(f"Error testing tool: {e}")


if __name__ == "__main__":
    main()
