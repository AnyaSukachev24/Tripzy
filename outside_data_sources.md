# Outside Data Sources

This document outlines the external data sources selected for the Tripzy AI Travel Agent to address core pain points in travel planning.

## 1. Kaggle Hotels Dataset (TBO Hotels)

> [!IMPORTANT]
> **Implementation Note:** We are currently deciding between using this offline dataset (indexed via RAG) or a live external Hotel API. The choice will depend on the required data freshness and performance needs.

Used to address **Pain Point 1: Finding efficient flight and hotel combinations across many sources**.

| Attribute | Details |
| :--- | :--- |
| **Name** | Kaggle Hotels Dataset |
| **Type** | RAG (Vector Search) |
| **Source Link** | [Kaggle TBO Hotels Dataset](https://www.kaggle.com/datasets/raj713335/tbo-hotels-dataset) |
| **Size** | ~2.41 GB (Uncompressed) |
| **Format** | CSV / JSON |

### Key Fields for Implementation
- `HotelName`, `HotelRating`: For filtering and quality matching.
- `cityName`, `countyName`: For geographic filtering.
- `HotelRating`, `Price`: For budget and class matching.
- `HotelFacilities`: Free-text amenities (Wi-Fi, pool, etc.) for semantic search.
- `Description`, `Attractions`: Rich text for RAG context.

### Usage in Tripzy
The `Action_Executor` or a specialized `Hotel_Retriever` node can use this dataset to find specific hotel options once a destination is selected.

---

## 2. Wikivoyage Worldwide City Travel Dataset

Used to address **Pain Point 2: Clients with vague requirements and no fixed destination**.

| Attribute | Details |
| :--- | :--- |
| **Name** | Wikivoyage Worldwide City Travel Dataset |
| **Type** | RAG (Vector Search) |
| **Source Link** | [Wikivoyage Dumps](https://dumps.wikimedia.org/enwikivoyage/latest/) |
| **Size** | ~400 MB |
| **Format** | Processed JSONL |

### Key Fields for Implementation
- `title`, `country`: Destination identifiers.
- `intro`, `understand`, `history`: Context for destination descriptions.
- `climate`: To handle "warm/cold" preferences.
- `see`, `do`, `eat`, `drink`: Activities for matching interests (e.g., "beaches", "museums").
- `stay_safe`, `get_in`, `get_around`: Practical travel info.

### Usage in Tripzy
The `Trip_Planner` node uses this dataset to map vague user preferences (e.g., "somewhere with history and good food") to concrete destination suggestions.

---

## Implementation Strategy (RAG)

1. **Preprocessing**: 
   - Convert CSV/JSONL into a standard internal format.
   - Chunk long descriptions (especially for Wikivoyage).
2. **Embedding**: Use Google Gemini Embeddings (`text-embedding-004`).
3. **Storage**: Index in Pinecone (or local ChromaDB for development).
4. **Retrieval**: Combined keyword filtering (city/country) + semantic search (amenities/interests).
