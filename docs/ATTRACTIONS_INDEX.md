# ATTRACTIONS Pinecone Index

## Source dataset

| Field | Value |
|---|---|
| Kaggle handle | `mrsimple07/rag-data3` |
| File | `16_rag_data.csv` |
| Download method | `kagglehub.dataset_download()` |

---

## Fields kept vs dropped

### Kept
| Column | Reason |
|---|---|
| `name` | Primary identifier; part of embedding text |
| `latitude` | Stored in metadata for future Pinecone geo-filtering |
| `longitude` | Stored in metadata for future Pinecone geo-filtering |
| `address` | Location context; part of embedding text |
| `description` | Semantic content; core of embedding text |
| `category` | Facet filtering + embedding text |
| `city` | Location filter + embedding text |
| `country` | Location filter + embedding text |
| `combined_field` | Pre-built text; used as embedding override when non-empty |

### Dropped
| Column | Reason |
|---|---|
| `rating` | Stale / unreliable in static snapshot |
| `review_count` | Same as above |
| `price` | Too volatile; would require frequent re-ingestion |
| `contact` | Not useful for trip planning RAG |
| `opening_hours` | Not useful for semantic search |
| `image` | URL; not embedded |
| `reviews` | Long free-text; would dilute embedding signal |

---

## Embedding text formula

```
if combined_field is non-empty:
    text = combined_field
else:
    text = "{name}. Category: {category}. {description}. Located in {address}, {city}, {country}."
```

---

## Metadata schema (per vector)

```json
{
  "text":        "<embedding text>",
  "name":        "Eiffel Tower",
  "address":     "Champ de Mars, 5 Avenue Anatole France",
  "city":        "Paris",
  "country":     "France",
  "category":    "Landmark",
  "description": "Iron lattice tower on the Champ de Mars ...",
  "latitude":    48.8584,
  "longitude":   2.2945
}
```

`latitude` and `longitude` are omitted from metadata when the source value is NaN.

---

## Index configuration

| Setting | Value |
|---|---|
| Pinecone project | ATTRACTIONS (separate API key) |
| Index name | `tripzy` (separate project from the default Wikivoyage index) |
| Host env var | `PINECONE_INDEX_HOST_ATTRACTIONS` |
| API key env var | `PINECONE_API_KEY_ATTRACTIONS` |
| Namespace | `attractions` |
| Embed model | `llama-text-embed-v2` |
| Dimensions | 1024 |
| Metric | cosine (default) |

---

## Vector ID scheme

```python
sha256(f"{name}|{city}|{address}").hexdigest()[:32]
```

Deterministic: re-running the ingest script will overwrite existing vectors (upsert semantics) rather than create duplicates.

---

## How to re-run

```bash
# Full ingest
python scripts/ingest_attractions_kaggle.py

# Test run (first 500 rows only)
python scripts/ingest_attractions_kaggle.py --limit 500

# Custom batch size
python scripts/ingest_attractions_kaggle.py --batch-size 48
```

Required environment variables (in `.env`):
- `KAGGLE_USERNAME`
- `KAGGLE_KEY`
- `PINECONE_API_KEY_ATTRACTIONS`
- `PINECONE_INDEX_HOST_ATTRACTIONS`
