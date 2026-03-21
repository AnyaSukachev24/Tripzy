"""
Wikivoyage Data Ingestion Script
Ingests Wikivoyage articles into Pinecone for RAG-powered destination & attraction suggestions.

Usage:
  python -m app.ingest_wikivoyage --data-path path/to/wikivoyage_dump.jsonl

Supported formats:
  - JSONL: One JSON object per line with {id, title, text}
  - XML: Wikimedia XML dump (auto-detected by .xml or .bz2 extension)
"""

import json
import os
import re
import sys
import bz2
import argparse
import xml.etree.ElementTree as ET
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


def load_wikivoyage_jsonl(data_path: str) -> List[dict]:
    """Load articles from JSONL format (one JSON per line)."""
    articles = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
                # Skip empty, redirect, or meta articles
                title = article.get("title", "")
                text = article.get("text", "")
                if not text or len(text) < 50:
                    continue
                if title.startswith("Wikivoyage:") or title.startswith("Template:"):
                    continue
                if "#REDIRECT" in text.upper():
                    continue
                articles.append(article)
            except json.JSONDecodeError:
                continue
    return articles


def load_wikivoyage_xml(data_path: str) -> List[dict]:
    """
    Load articles from a Wikimedia XML dump (.xml or .xml.bz2).
    Stream-parsed so it works without loading the full file into memory.
    """
    MW_NS = "http://www.mediawiki.org/xml/export-0.11/"
    SKIP_PREFIXES = (
        "Wikivoyage:", "Template:", "User:", "User talk:", "Talk:",
        "File:", "MediaWiki:", "Help:", "Category:",
    )

    articles: List[dict] = []
    open_fn = bz2.open if data_path.endswith(".bz2") else open
    open_kwargs = {"mode": "rt", "encoding": "utf-8"} if data_path.endswith(".bz2") else {"encoding": "utf-8"}

    current_title = ""
    current_ns = "0"
    current_text = ""

    with open_fn(data_path, **open_kwargs) as f:
        context = ET.iterparse(f, events=("end",))
        for event, elem in context:
            tag = elem.tag.replace(f"{{{MW_NS}}}", "")
            if tag == "title":
                current_title = (elem.text or "").strip()
            elif tag == "ns":
                current_ns = (elem.text or "0").strip()
            elif tag == "text":
                current_text = (elem.text or "").strip()
            elif tag == "page":
                if (
                    current_ns == "0"
                    and current_text
                    and len(current_text) > 200
                    and not any(current_title.startswith(p) for p in SKIP_PREFIXES)
                    and "#REDIRECT" not in current_text.upper()
                ):
                    articles.append({"title": current_title, "text": current_text})
                    if len(articles) % 500 == 0:
                        print(f"   Loaded {len(articles):,} articles from XML...", flush=True)
                elem.clear()
                current_title = current_ns = current_text = ""

    return articles


def load_articles(data_path: str) -> List[dict]:
    """Auto-detect format and load articles from JSONL or XML/XML.bz2."""
    if data_path.endswith(".xml") or data_path.endswith(".xml.bz2") or data_path.endswith(".bz2"):
        print(f"   Detected XML/bz2 format.")
        return load_wikivoyage_xml(data_path)
    return load_wikivoyage_jsonl(data_path)


def classify_article(title: str, text: str) -> str:
    """Classify a Wikivoyage article by type."""
    text_lower = text.lower()
    title_lower = title.lower()

    if any(kw in title_lower for kw in ["phrasebook", "phrase"]):
        return "phrasebook"
    if any(kw in title_lower for kw in ["travel topic", "travel tips"]):
        return "travel_topic"
    # Sub-articles like "Paris/Marais" or "Tokyo/Shinjuku" are district pages
    if "/" in title:
        return "district"
    if any(kw in text_lower[:500] for kw in ["is a country", "is a nation"]):
        return "country"
    if any(kw in text_lower[:500] for kw in ["is a region", "is a province", "is a state"]):
        return "region"
    if any(kw in text_lower[:500] for kw in ["is a city", "is a town", "is the capital"]):
        return "city"
    if any(kw in text_lower[:500] for kw in ["is an island", "island"]):
        return "island"

    return "destination"


def extract_sections(text: str) -> List[dict]:
    """Split a Wikivoyage article into meaningful sections."""
    # Common Wikivoyage sections
    section_pattern = re.compile(r"^(={2,3})\s*(.+?)\s*\1", re.MULTILINE)

    sections = []
    matches = list(section_pattern.finditer(text))

    if not matches:
        # No sections found, treat entire text as one chunk
        return [{"section": "overview", "content": text}]

    # Add intro/overview (before first section)
    intro = text[: matches[0].start()].strip()
    if intro and len(intro) > 30:
        sections.append({"section": "overview", "content": intro})

    # Extract each section
    for i, match in enumerate(matches):
        section_name = match.group(2).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        if content and len(content) > 30:
            sections.append({"section": section_name, "content": content})

    return sections


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks by word boundaries."""
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap  # Overlap

    return chunks


def ingest_wikivoyage(data_path: str, batch_size: int = 50, max_articles: int = 0):
    """Main ingestion function."""
    # 1. Load Data
    print(f"1. Loading data from {data_path}...")
    articles = load_articles(data_path)
    if not articles:
        print("No articles found. Exiting.")
        return

    if max_articles > 0:
        articles = articles[:max_articles]
        print(f"   scoping to {max_articles} articles.")

    print(f"   Loaded {len(articles)} articles.")

    # 2. Process & Chunk
    from langchain_core.documents import Document
    
    print(f"\n2. Processing and chunking articles...")
    documents = []
    
    for article in articles:
        title = article.get("title", "")
        text = article.get("text", "")
        
        # Classify
        article_type = classify_article(title, text)
        # Keep destinations, city districts, and travel topics; skip phrasebooks.
        # "district" covers sub-articles like "Paris/Marais" or "Tokyo/Shinjuku".
        if article_type == "phrasebook":
            continue

        # Extract sections
        sections = extract_sections(text)
        
        for section in sections:
            sec_name = section["section"]
            sec_content = section["content"]
            
            # Chunking
            chunks = chunk_text(sec_content, chunk_size=300, overlap=50) # Smaller chunks for better retrieval
            
            for i, chunk in enumerate(chunks):
                # Create Document
                # For district sub-articles (e.g. "Paris/Marais") store the parent
                # city as `title` so RAG filters like `title == "Paris"` still match.
                canonical_title = title.split("/")[0].strip() if "/" in title else title
                metadata = {
                    "title": canonical_title,
                    "sub_title": title if "/" in title else "",
                    "section": sec_name,
                    "type": article_type,
                    "chunk_index": i,
                    "source": "wikivoyage"
                }
                
                doc = Document(page_content=chunk, metadata=metadata)
                documents.append(doc)

    print(f"   Created {len(documents)} chunks from {len(articles)} articles.")

    # Initialize Pinecone
    print(f"\n3. Initializing Pinecone Client...")
    try:
        from pinecone import Pinecone
    except ImportError:
        print("Error: 'pinecone' package not found. Please install it.")
        return

    index_name = os.getenv("PINECONE_INDEX_NAME")
    if not index_name:
        print("Error: PINECONE_INDEX_NAME not found in environment variables.")
        return

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    
    # Check index
    if index_name not in pc.list_indexes().names():
        print(f"Error: Index '{index_name}' not found in Pinecone account.")
        return
        
    index = pc.Index(index_name)

    # Ingest in batches
    print(f"\n4. Ingesting into Pinecone index '{index_name}' (namespace: wikivoyage)...")
    print(f"   Model: llama-text-embed-v2 (Integrated Inference)")
    
    total_ingested = 0
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        batch_texts = [doc.page_content for doc in batch]
        
        import time
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # 1. Generate Embeddings via Pinecone Inference
                # We use the model specified by the user's index configuration request
                embeddings_response = pc.inference.embed(
                    model="llama-text-embed-v2",
                    inputs=batch_texts,
                    parameters={"input_type": "passage", "truncate": "END"}
                )
                
                # 2. Prepare Vectors for Upsert
                vectors = []
                for j, embedding_data in enumerate(embeddings_response):
                    doc = batch[j]
                    # Create a unique ID — use the original (full) title so
                    # "Paris/Marais" and "Paris" don't produce colliding IDs.
                    metadata = doc.metadata
                    # Clean metadata values to ensure they are primitives (str, int, float, bool) or list of strings
                    clean_metadata = {k: v for k, v in metadata.items() if v is not None}
                    # Add text to metadata for retrieval
                    clean_metadata["text"] = doc.page_content

                    raw_id = (
                        f"{clean_metadata.get('sub_title') or clean_metadata.get('title', 'doc')}"
                        f"_{clean_metadata.get('section', 'sec')}"
                        f"_{clean_metadata.get('chunk_index', j)}"
                    )
                    # Sanitize ID
                    vector_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_id)
                    
                    vectors.append({
                        "id": vector_id,
                        "values": embedding_data["values"],
                        "metadata": clean_metadata
                    })
                
                # 3. Upsert
                index.upsert(vectors=vectors, namespace="wikivoyage")
                
                total_ingested += len(batch)
                print(f"   Batch {i // batch_size + 1}: {total_ingested}/{len(documents)} chunks ingested")
                break # Success!
                
            except Exception as e:
                print(f"   Error in batch {i // batch_size + 1} (Attempt {attempt+1}/{max_retries}): {e}")
                # Use string matching to detect 429 from pinecone since status attribute might not be directly accessible
                if "429" in str(e) or "Too Many Requests" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait = (attempt + 1) * 30
                    print(f"   Rate limit hit. Waiting {wait} seconds...")
                    time.sleep(wait)
                elif attempt == max_retries - 1:
                    print("   Max retries reached. Skipping batch.")
                    if hasattr(e, 'body'):
                         print(f"   API Error Body: {e.body}")
                else:
                    time.sleep(5) # short wait for other errors

    print(f"\n{'=' * 60}")
    print(f"  Ingestion Complete: {total_ingested} chunks from {len(articles)} articles")
    print(f"  Note: Used Pinecone 'llama-text-embed-v2' (1024d) for embeddings.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Wikivoyage data into Pinecone")
    parser.add_argument(
        "--data-path",
        type=str,
        required=True,
        help="Path to Wikivoyage JSONL dump file",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of documents per batch (default: 50)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=0,
        help="Max articles to ingest (0 = all)",
    )

    args = parser.parse_args()
    ingest_wikivoyage(args.data_path, args.batch_size, args.max_articles)
