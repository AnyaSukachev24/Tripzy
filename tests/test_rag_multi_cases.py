import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools import suggest_destination_tool, suggest_attractions_tool
import json
import time

def evaluate_rag_usage():
    print("="*60)
    print("  EVALUATING RAG IN END-TO-END TOOL SCENARIOS")
    print("="*60 + "\n")

    # --- Scenario 1: Vague Destination Request (RAG Only Focus) ---
    print("> SCENARIO 1: Abstract/Vague Destination Request")
    print("  Query: 'I want to go somewhere with ancient ruins and great pasta on a medium budget.'")
    try:
        start_time = time.time()
        result_str = suggest_destination_tool.invoke({
            "preferences": "ancient ruins and great pasta",
            "budget_tier": "medium",
            "trip_type": "cultural",
            "climate": "warm",
            "duration_days": 7
        })
        end_time = time.time()
        results = json.loads(result_str)
        print(f"  Time taken: {end_time - start_time:.2f}s")
        if isinstance(results, list):
            print(f"  Found {len(results)} suggestions:")
            for r in results:
                print(f"    - {r.get('destination', 'Unknown')} (Score: {r.get('score', 0):.3f})")
                print(f"      Snippet: {r.get('summary', '')[:80]}...")
        else:
            print(f"  Result: {results}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "-"*50 + "\n")

    # --- Scenario 2: High-Level Action-Oriented (Attractions) ---
    print("> SCENARIO 2: Finding Attractions for Specific Destination")
    print("  Query: 'Things to do in Kyoto for nature lovers'")
    try:
        start_time = time.time()
        result_str = suggest_attractions_tool.invoke({
            "destination": "Kyoto",
            "interests": ["nature", "gardens", "temples"],
            "trip_type": "relaxing"
        })
        end_time = time.time()
        results = json.loads(result_str)
        print(f"  Time taken: {end_time - start_time:.2f}s")
        if isinstance(results, list):
            print(f"  Found {len(results)} attractions:")
            for r in results:
                name = str(r.get('name', 'Unknown')).encode('cp1255', errors='replace').decode('cp1255')
                section = str(r.get('section', 'N/A')).encode('cp1255', errors='replace').decode('cp1255')
                desc = str(r.get('description', ''))[:80].encode('cp1255', errors='replace').decode('cp1255')
                print(f"    - [{section.upper()}] {name} (Score: {r.get('score', 0):.3f})")
                print(f"      Snippet: {desc}...")
        else:
            print(f"  Result: {results}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "-"*50 + "\n")

    # --- Scenario 3: Niche Activity Search ---
    print("> SCENARIO 3: Strict Search for Specific Trip Type")
    print("  Query: 'Suggest a destination for hiking, trekking, and seeing wildlife.'")
    try:
        start_time = time.time()
        result_str = suggest_destination_tool.invoke({
            "preferences": "hiking trekking wildlife mountains",
            "budget_tier": "medium",
            "trip_type": "adventure",
            "climate": "alpine",
            "duration_days": 10
        })
        end_time = time.time()
        results = json.loads(result_str)
        print(f"  Time taken: {end_time - start_time:.2f}s")
        if isinstance(results, list):
            print(f"  Found {len(results)} suggestions:")
            for r in results:
                print(f"    - {r.get('destination', 'Unknown')} (Score: {r.get('score', 0):.3f})")
        else:
            print(f"  Result: {results}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "="*60 + "\n")

if __name__ == '__main__':
    evaluate_rag_usage()
