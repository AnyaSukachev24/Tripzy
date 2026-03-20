# Tripzy Retrieval-Augmented Generation (RAG) System

This document outlines the architecture, components, and maintenance procedures for the Tripzy RAG pipeline. The RAG system provides the Tripzy travel agent with accurate, grounded knowledge about global destinations and attractions, reducing LLM hallucinations and improving the quality of travel recommendations.

## 1. Architecture Overview

The RAG system is built on top of **Pinecone** (Vector Database) and uses **Wikivoyage** as its primary source of truth. It consists of three main phases:
1. **Data Acquisition:** Fetching curated travel articles from the Wikivoyage API.
2. **Ingestion & Embedding:** Chunking the articles, generating embeddings using Pinecone's Integrated Inference (`llama-text-embed-v2`), and uploading them to the vector database.
3. **Retrieval (Tooling):** Querying the vector database securely from LangChain tools used by the central LLM agent to construct travel plans.

---

## 2. Pinecone Configuration

All travel data is stored securely in your Pinecone account:
- **Index Name:** Defined in `.env` as `PINECONE_INDEX_NAME` (typically `tripzy`).
- **Namespace:** `wikivoyage`. (Note: user profiles are stored in the same index but under the `user_profiles` namespace to keep them strictly separated).
- **Embedding Model:** `llama-text-embed-v2` (Dimension: 1024).

---

## 3. How Data is Structured

To maintain high context relevance during retrieval, the data is chunked and stored with semantic metadata.

### Data Volume & Coverage
After a full fetch+ingest run, the database will contain roughly:
- **~400 top-level destination articles** (cities, regions, countries, islands) from the static `DESTINATIONS` list.
- **+300–600 district/neighborhood sub-articles** when run with `--fetch-subpages` (e.g. `Paris/Marais`, `Tokyo/Shinjuku`, `London/Notting Hill`). These are the richest source for hyper-local attraction and dining data.
- **+200–400 auto-discovered articles** when run with `--use-categories`.
- **Total estimated chunks:** 30,000–60,000 (each article produces ~60–150 chunks).

### Chunking Strategy
- **Size:** ~300 words per chunk.
- **Overlap:** 50 words (prevents losing context across sentence boundaries).
- **Sectioning:** Chunks respect Wikivoyage article sections (e.g., "Understand", "See", "Do", "Eat", "Sleep").

### Metadata Schema
Each vector in Pinecone contains the following metadata:
- `title`: The city or region name (e.g., "Rome", "Bali").
- `section`: The article section the chunk belongs to (e.g., "eat", "see").
- `type`: Category of the article (e.g., "city", "region").
- `source`: Always `"wikivoyage"`.
- `chunk_index`: Position of the chunk in the document.
- `text`: The raw text content of the chunk (returned to the LLM upon matching).

---

## 4. How the Agent Uses RAG (Retrieval)

The LLM agent interacts with the RAG system through structural LangChain tools defined in `app/tools.py`.

### A. Destination Suggestion (`suggest_destination_tool`)
When a user asks "Where should I go for a relaxing beach trip under $1000?":
1. The tool accepts the arguments (`preferences`, `budget_tier`, `trip_type`, etc.).
2. **Query Expansion:** It converts `trip_type` ("relaxing") into semantic keywords ("wellness spa yoga meditation retreat relaxation mindfulness").
3. **Similarity Search:** It queries the `wikivoyage` namespace for the top 8 matches.
4. **Filtering:** Filters out low-confidence matches (score < 0.35) and deduplicates by City Name.
5. **Amadeus Enrichment:** Takes the top destination and cross-references the Amadeus API to find similar flight-friendly destinations.

### B. Attraction Planning (`suggest_attractions_tool`)
When a user asks "What is there to do in Kyoto for nature lovers?":
1. The tool constructs a targeted query ("Kyoto things to do attractions nature").
2. **Strict Filtering:** To prevent hallucinations (e.g., suggesting the Eiffel Tower while visiting Kyoto), the tool strictly discards any vector where the `title` metadata does not match the requested destination.
3. **Deduplication:** Groups results by `section` to provide a diverse list of activities (some from "See", some from "Do").

*Note: Both tools have a natural fallback to a live DuckDuckGo web search if the Pinecone index is empty or yields no relevant results above the confidence threshold.*

---

## 5. How to Update the Data (Maintenance)

If you need to add new cities, refresh existing data, or do a full rebuild, follow these steps.

### Step 1: Fetch the Raw Data

The fetch script supports several modes. **Run from the project root.**

```bash
# --- Option A: Basic fetch (400+ destinations, ~25 min) ---
python scripts/fetch_wikivoyage_data.py

# --- Option B: Maximum coverage (recommended for first full build) ---
# Adds district/neighborhood sub-articles for major cities (+300-600 pages)
# AND auto-discovers articles via Wikivoyage categories
python scripts/fetch_wikivoyage_data.py --fetch-subpages --use-categories

# --- Option C: Resume an interrupted run ---
# Safe to re-run; already-saved titles are skipped
python scripts/fetch_wikivoyage_data.py --fetch-subpages --use-categories --resume
```

**What `--fetch-subpages` gives you:**  
For major cities like Paris, Tokyo, and London, Wikivoyage has district/neighborhood sub-articles
(`Paris/Marais`, `Tokyo/Shinjuku`, `London/Notting Hill`, etc.).  
These contain hyper-local information — specific restaurants, hidden attractions, exact transit tips —
that the top-level city article doesn't have. This is the single biggest quality boost.

**What `--use-categories` gives you:**  
Auto-discovers additional articles from Wikivoyage category pages (`Category:Cities`,
`Category:Islands`, `Category:Beach_destinations`, etc.) beyond the 400+ static list.

*(Output is saved to `data/wikivoyage_dump.jsonl`)*

### Step 2: Run the Ingestion Pipeline

```bash
python -m app.ingest_wikivoyage --data-path data/wikivoyage_dump.jsonl
```

**Important:** The ingestion script has automated **Exponential Backoff**. Pinecone Free-Tier
restricts embedding to 250,000 tokens per minute. If it hits a `429 Too Many Requests` error,
it will pause automatically and resume. Let it run to completion.

### Step 3: Verify

```bash
python tests/check_pinecone_stats.py
```

---

## 6. Testing and Evaluation

Several scripts are provided in the `tests/` directory to monitor and stress-test the pipeline:

- **`python tests/check_pinecone_stats.py`**
  Quickly verifies if your Pinecone database is online, and prints the exact vector counts per namespace. Use this to confirm updates were successful.

- **`python test_pinecone.py`**
  A sandbox playground for executing raw semantic searches against the vector database to see exactly what Pinecone returns (Score, Title, Text) before the LLM processes it.

- **`python tests/test_rag_multi_cases.py`**
  An end-to-end LangChain evaluation suite. It simulates real agent tool invocations with abstract requirements (e.g., "suggest a destination for hiking and wildlife") and times the performance. Use this to verify that changes to the system didn't break the agent's logic.
