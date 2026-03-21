"""
Ingest Kaggle attractions dataset (mrsimple07/rag-data3) into Pinecone.

Usage:
    python scripts/ingest_attractions_kaggle.py
    python scripts/ingest_attractions_kaggle.py --limit 500
    python scripts/ingest_attractions_kaggle.py --limit 100 --batch-size 48
"""

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from pinecone import Pinecone

# ---------------------------------------------------------------------------
# Bootstrap: load .env from project root regardless of where script is run
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PINECONE_API_KEY = os.environ["PINECONE_API_KEY_ATTRACTIONS"]
PINECONE_HOST    = os.environ["PINECONE_INDEX_HOST_ATTRACTIONS"]
NAMESPACE        = "attractions"
EMBED_MODEL      = "llama-text-embed-v2"
EMBED_DIMENSIONS = 1024
CSV_FILENAME     = "16_rag_data.csv"

# Columns we keep from the raw CSV (everything else is dropped)
KEEP_COLS = ["name", "latitude", "longitude", "address", "description",
             "category", "city", "country"]
# combined_field is used as the embedding text override if present & non-empty
COMBINED_FIELD = "combined_field"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def stable_id(row: pd.Series) -> str:
    """Deterministic SHA-256-based vector ID (first 32 hex chars)."""
    raw = f"{row.get('name', '')}|{row.get('city', '')}|{row.get('address', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def build_embedding_text(row: pd.Series) -> str:
    """Build the text that will be embedded (semantic content)."""
    # Use pre-built combined field when available
    combined = str(row.get(COMBINED_FIELD, "")).strip()
    if combined:
        return combined

    name        = str(row.get("name", "")).strip()
    category    = str(row.get("category", "")).strip()
    description = str(row.get("description", "")).strip()
    address     = str(row.get("address", "")).strip()
    city        = str(row.get("city", "")).strip()
    country     = str(row.get("country", "")).strip()

    parts = [f"{name}."]
    if category:
        parts.append(f"Category: {category}.")
    if description:
        parts.append(description)
    location_parts = [p for p in [address, city, country] if p]
    if location_parts:
        parts.append(f"Located in {', '.join(location_parts)}.")
    return " ".join(parts)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Select, coerce types, and drop bad rows."""
    # Include combined_field if it exists (for embedding text override)
    cols = KEEP_COLS + ([COMBINED_FIELD] if COMBINED_FIELD in df.columns else [])
    df = df[[c for c in cols if c in df.columns]].copy()

    # Ensure all expected keep-cols exist (fill missing ones with "")
    for col in KEEP_COLS:
        if col not in df.columns:
            df[col] = ""

    # Drop rows with no name
    df["name"] = df["name"].astype(str).str.strip()
    df = df[df["name"].str.len() > 0].copy()

    # Coerce lat/lon to float
    df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    # Fill NaN string columns
    for col in ["address", "description", "category", "city", "country"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    if COMBINED_FIELD in df.columns:
        df[COMBINED_FIELD] = df[COMBINED_FIELD].fillna("").astype(str).str.strip()

    df = df.reset_index(drop=True)
    return df


def build_records(df: pd.DataFrame) -> list[dict]:
    """Convert cleaned dataframe rows to Pinecone upsert records."""
    records = []
    for _, row in df.iterrows():
        vec_id = stable_id(row)
        text   = build_embedding_text(row)

        # Latitude / longitude: keep None if NaN so Pinecone metadata stays clean
        lat = None if pd.isna(row["latitude"])  else float(row["latitude"])
        lon = None if pd.isna(row["longitude"]) else float(row["longitude"])

        metadata = {
            "text":        text,
            "name":        row["name"],
            "address":     row["address"],
            "city":        row["city"],
            "country":     row["country"],
            "category":    row["category"],
            "description": row["description"],
        }
        if lat is not None:
            metadata["latitude"]  = lat
        if lon is not None:
            metadata["longitude"] = lon

        records.append({"id": vec_id, "text": text, "metadata": metadata})
    return records


def upsert_in_batches(index, records: list[dict], batch_size: int) -> int:
    """
    Embed + upsert records using Pinecone's integrated inference endpoint.
    Returns total number of vectors upserted.
    """
    total = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]

        # upsert_records (integrated inference) expects flat records:
        # _id at top level, all metadata fields also at top level (no nested dict)
        vectors = [
            {
                "_id":  r["id"],
                "text": r["text"],
                **{k: v for k, v in r["metadata"].items() if k != "text"},
            }
            for r in batch
        ]

        retries = 0
        while True:
            try:
                index.upsert_records(
                    namespace=NAMESPACE,
                    records=vectors,
                )
                total += len(batch)
                pct = total / len(records) * 100
                print(f"  Upserted {total}/{len(records)} ({pct:.1f}%)", end="\r")
                break
            except Exception as exc:
                msg = str(exc)
                if "429" in msg or "too many requests" in msg.lower():
                    wait = 2 ** retries
                    print(f"\n  Rate-limited, retrying in {wait}s…")
                    time.sleep(wait)
                    retries += 1
                    if retries > 5:
                        raise
                else:
                    raise
    print()  # newline after \r progress
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ingest Kaggle attractions dataset into Pinecone ATTRACTIONS index."
    )
    parser.add_argument("--limit",      type=int, default=None,
                        help="Limit number of rows (for testing).")
    parser.add_argument("--batch-size", type=int, default=96,
                        help="Vectors per upsert batch (default: 96).")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # 1. Download dataset via kagglehub
    # ------------------------------------------------------------------
    print("Downloading Kaggle dataset mrsimple07/rag-data3 …")
    try:
        import kagglehub  # noqa: PLC0415 — intentional lazy import
    except ImportError:
        print("ERROR: kagglehub not installed. Run: pip install kagglehub")
        sys.exit(1)

    dataset_path = Path(kagglehub.dataset_download("mrsimple07/rag-data3"))
    print(f"  Dataset cached at: {dataset_path}")

    # Find the CSV (handles nested sub-dirs kagglehub may create)
    csv_candidates = list(dataset_path.rglob(CSV_FILENAME))
    if not csv_candidates:
        print(f"ERROR: Could not find {CSV_FILENAME} under {dataset_path}")
        sys.exit(1)
    csv_path = csv_candidates[0]
    print(f"  Loading CSV: {csv_path}")

    # ------------------------------------------------------------------
    # 2. Load + clean
    # ------------------------------------------------------------------
    df_raw = pd.read_csv(csv_path, low_memory=False)
    print(f"  Raw rows: {len(df_raw):,}   columns: {list(df_raw.columns)}")

    df = clean_dataframe(df_raw)
    print(f"  After cleaning: {len(df):,} rows")

    if args.limit:
        df = df.head(args.limit)
        print(f"  Limiting to first {len(df):,} rows (--limit flag)")

    # ------------------------------------------------------------------
    # 3. Build records
    # ------------------------------------------------------------------
    records = build_records(df)
    print(f"  Records to upsert: {len(records):,}")

    # ------------------------------------------------------------------
    # 4. Connect to Pinecone ATTRACTIONS index
    # ------------------------------------------------------------------
    print(f"Connecting to Pinecone ATTRACTIONS index …")
    pc    = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(host=PINECONE_HOST)

    stats = index.describe_index_stats()
    print(f"  Index stats before upsert: {stats}")

    # ------------------------------------------------------------------
    # 5. Upsert
    # ------------------------------------------------------------------
    print(f"Upserting into namespace='{NAMESPACE}' (batch_size={args.batch_size}) …")
    total = upsert_in_batches(index, records, batch_size=args.batch_size)

    print(f"\nDone. Upserted {total:,} vectors into namespace='{NAMESPACE}'.")
    stats_after = index.describe_index_stats()
    print(f"Index stats after upsert: {stats_after}")


if __name__ == "__main__":
    main()
