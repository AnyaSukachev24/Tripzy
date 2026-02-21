
import sys
import os
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.tools import suggest_attractions_tool

def test_rag_retrieval():
    print("=" * 60)
    print("  TEST: RAG Retrieval (Paris)")
    print("=" * 60)
    
    # Paris is in our sample data
    result = suggest_attractions_tool.invoke({
        "destination": "Paris",
        "interests": ["history"]
    })
    
    data = json.loads(result)
    
    # Should be list of dicts from Wikivoyage RAG
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        source = first.get("source", "")
        name = first.get("name", "")
        description = first.get("description", "")
        
        print(f"  [RAG] Source: {source}")
        print(f"  [RAG] Name: {name}")
        print(f"  [RAG] Description: {description[:100]}...")
        
        if source == "Wikivoyage" and "Eiffel Tower" in str(data):
            print("  ✅ RAG retrieval SUCCESS: Found Eiffel Tower from Wikivoyage")
            return True
        else:
            print(f"  ❌ RAG retrieval parsed but unexpected content. Source={source}")
            return False
    else:
        print(f"  ❌ RAG retrieval failed. Result type: {type(data)} Content: {str(data)[:200]}")
        return False

def test_rag_fallback():
    print("\n" + "=" * 60)
    print("  TEST: RAG Fallback (Tokyo - Not in sample)")
    print("=" * 60)
    
    # Tokyo is NOT in our sample data -> should fallback
    result = suggest_attractions_tool.invoke({
        "destination": "Tokyo",
        "interests": ["anime"]
    })
    
    data = json.loads(result)
    
    # Should be dict with source="Wikivoyage (web search)" or similar fallback structure
    if isinstance(data, dict):
        source = data.get("source", "")
        print(f"  [Fallback] Source: {source}")
        
        if "web search" in source.lower():
            print("  ✅ Fallback SUCCESS: Used web search")
            return True
        else:
            print(f"  ❌ Fallback returned dict but unexpected source: {source}")
            return False
            
    # DuckDuckGo might fail if no internet, but assuming it works
    print(f"  ⚠️ Fallback returned unexpected type: {type(data)}")
    return False

if __name__ == "__main__":
    success = True
    if not test_rag_retrieval():
        success = False
    if not test_rag_fallback():
        success = False
        
    if success:
        print("\n✅ All RAG tests PASSED")
        sys.exit(0)
    else:
        print("\n❌ Some RAG tests FAILED")
        sys.exit(1)
