from app.tools import _query_pinecone_inference
import json

def test_rag_query():
    print("Testing Pinecone RAG Retrieval across diverse scenarios...\n")
    
    queries = [
        "romantic honeymoon beach destination",
        "historical attractions in Rome",
        "what to do in Tokyo for anime fans",
        "budget backpacking in Southeast Asia",
        "best places to eat near the Eiffel Tower in Paris",
        "Auckland New Zealand"
    ]
    
    for query in queries:
        print(f"==================================================")
        print(f"QUERY: {query}")
        print(f"==================================================")
        
        matches = _query_pinecone_inference(query, k=3, namespace='wikivoyage')
        
        if not matches:
            print("No matches found.")
        else:
            for i, m in enumerate(matches):
                score = m.get('score', 0)
                meta = m.get('metadata', {})
                title = meta.get('title', 'Unknown').encode('cp1255', errors='replace').decode('cp1255')
                section = meta.get('section', 'Unknown').encode('cp1255', errors='replace').decode('cp1255')
                text = meta.get('text', '')[:150].replace('\n', ' ').encode('cp1255', errors='replace').decode('cp1255')
                print(f"[{i+1}] Score: {score:.3f} | Title: {title} | Section: {section}")
                print(f"    Snippet: {text}...\n")

if __name__ == '__main__':
    test_rag_query()
