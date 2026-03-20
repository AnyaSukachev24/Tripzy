"""
Enhanced Wikivoyage Data Fetcher for Tripzy RAG
================================================
Two modes:

  1. API mode (default) — fetch specific destinations via the Wikivoyage API.
     Good for targeted updates; ~400-800 articles.

  2. Full-dump mode (--download-dump) — download the COMPLETE Wikivoyage XML dump
     from dumps.wikimedia.org (~300 MB compressed) and convert it to JSONL.
     This gives ALL ~30,000 Wikivoyage articles in one shot and is the
     recommended approach for maximum RAG coverage.

Usage:
    # RECOMMENDED: full dump — all 30,000+ articles (one-time ~300 MB download)
    python scripts/fetch_wikivoyage_data.py --download-dump

    # API mode: fetch 400+ curated destinations
    python scripts/fetch_wikivoyage_data.py

    # API mode + district sub-articles + category discovery
    python scripts/fetch_wikivoyage_data.py --fetch-subpages --use-categories

    # Resume an interrupted API fetch
    python scripts/fetch_wikivoyage_data.py --resume

Output: data/wikivoyage_dump.jsonl  (one JSON object per line: {title, text})
"""

import requests
import json
import time
import os
import re
import argparse
import bz2
import xml.etree.ElementTree as ET
from typing import Optional, List, Set

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = "https://en.wikivoyage.org/w/api.php"
HEADERS = {
    "User-Agent": "TripzyDataIngestionBot/1.0 (https://github.com/AnyaSukachev24/Tripzy; admin@tripzy.local)"
}

# ---------------------------------------------------------------------------
# 400+ Global Destinations
# (Original 148 + ~260 additional cities, regions, and island groups)
# ---------------------------------------------------------------------------
DESTINATIONS = [
    # === Europe ===
    "Paris", "London", "Rome", "Barcelona", "Amsterdam", "Istanbul", "Berlin",
    "Venice", "Madrid", "Prague", "Vienna", "Budapest", "Edinburgh", "Dublin",
    "Lisbon", "Athens", "Munich", "Florence", "Milan", "Brussels", "Bruges",
    "Geneva", "Zurich", "Lucerne", "Salzburg", "Dubrovnik", "Split", "Santorini",
    "Mykonos", "Crete", "Rhodes", "Reykjavik", "Oslo", "Stockholm", "Copenhagen",
    "Helsinki", "Tallinn", "Riga", "Vilnius", "Krakow", "Warsaw",
    # Additional Europe
    "Naples", "Palermo", "Bologna", "Turin", "Verona", "Pisa", "Siena",
    "Amalfi", "Cinque Terre", "Capri", "Porto", "Seville", "Granada",
    "Bilbao", "Valencia", "Malaga", "Ibiza", "Majorca",
    "Lyon", "Marseille", "Nice", "Bordeaux", "Strasbourg", "Montpellier",
    "Cologne", "Hamburg", "Frankfurt", "Stuttgart", "Dresden", "Leipzig",
    "Nuremberg", "Heidelberg",
    "Gothenburg", "Malmo", "Bergen", "Trondheim",
    "Gdansk", "Wroclaw", "Poznan", "Lodz",
    "Bratislava", "Ljubljana", "Sarajevo", "Mostar", "Kotor", "Tirana",
    "Thessaloniki", "Sofia", "Bucharest", "Cluj-Napoca",
    "Valletta", "Nicosia", "Andorra",
    "Bruges", "Ghent", "Antwerp",

    # === Americas ===
    "New York City", "Los Angeles", "San Francisco", "Las Vegas", "Miami",
    "Honolulu", "Cancun", "Mexico City", "Oaxaca", "Tulum",
    "Toronto", "Vancouver", "Montreal",
    "Buenos Aires", "Machu Picchu", "Cusco", "Lima", "Bogota", "Medellin",
    "Santiago", "Havana", "San Juan", "Rio de Janeiro",
    # Additional Americas
    "Chicago", "Boston", "New Orleans", "Seattle", "Portland", "Denver",
    "Nashville", "Austin", "Philadelphia", "Atlanta", "Phoenix", "Minneapolis",
    "Washington, D.C.", "San Diego", "Houston", "Dallas",
    "Salt Lake City", "Kansas City", "Detroit", "Pittsburgh",
    "Quebec City", "Ottawa", "Calgary", "Victoria",
    "Cartagena", "Cali", "Barranquilla", "Medellin",
    "Montevideo", "Asuncion", "La Paz", "Quito", "Guayaquil", "Cuenca",
    "Sao Paulo", "Brasilia", "Florianopolis", "Recife", "Salvador",
    "Manaus", "Belem", "Fortaleza", "Porto Alegre",
    "Guadalajara", "Monterrey", "Merida", "San Cristobal de las Casas",
    "Antigua Guatemala", "San Jose", "Panama City", "Tegucigalpa",
    "Managua", "Roseau", "Bridgetown",

    # === Middle East ===
    "Dubai", "Tel Aviv", "Jerusalem", "Amman", "Beirut", "Muscat",
    "Doha", "Abu Dhabi", "Kuwait City",
    "Riyadh", "Jeddah", "Isfahan", "Shiraz", "Tehran",

    # === Africa ===
    "Cape Town", "Nairobi", "Johannesburg", "Durban",
    "Marrakech", "Casablanca", "Fes", "Cairo", "Luxor", "Zanzibar",
    "Victoria Falls",
    # Additional Africa
    "Dakar", "Accra", "Lagos", "Abuja", "Addis Ababa", "Kampala",
    "Dar es Salaam", "Kigali", "Lusaka", "Harare", "Windhoek",
    "Gaborone", "Maputo", "Tunis", "Algiers", "Tripoli",
    "Djibouti", "Antananarivo", "Port Louis",
    "Swakopmund", "Livingstone",

    # === Asia — South & Southeast ===
    "Bangkok", "Singapore", "Bali", "Jakarta", "Yogyakarta",
    "Kuala Lumpur", "Penang", "Langkawi", "Malacca",
    "Manila", "Cebu", "Boracay", "Palawan",
    "Hanoi", "Ho Chi Minh City", "Hoi An", "Da Nang", "Halong Bay",
    "Siem Reap", "Phnom Penh", "Luang Prabang", "Vientiane",
    "Yangon", "Bagan", "Mandalay",
    "Delhi", "Mumbai", "Jaipur", "Agra", "Goa", "Kerala",
    "Kathmandu", "Thimphu", "Colombo", "Male",
    # Additional South & Southeast Asia
    "Chiang Mai", "Chiang Rai", "Koh Samui", "Phuket", "Krabi", "Koh Phi Phi",
    "Ubud", "Lombok", "Flores", "Komodo",
    "Hue", "Nha Trang", "Phu Quoc",
    "George Town",
    "Varanasi", "Amritsar", "Udaipur", "Jodhpur", "Rishikesh",
    "Darjeeling", "Mumbai", "Hampi",
    "Kandy", "Sigiriya", "Ella",
    "Pokhara",

    # === Asia — East ===
    "Tokyo", "Kyoto", "Hong Kong", "Seoul", "Beijing", "Shanghai",
    "Taipei", "Macau", "Singapore",
    "Xi'an", "Chengdu", "Guilin", "Hangzhou",
    # Additional East Asia
    "Osaka", "Hiroshima", "Nara", "Hakone", "Nikko", "Nagasaki",
    "Fukuoka", "Sapporo", "Okinawa",
    "Busan", "Jeju Island", "Gyeongju",
    "Kaohsiung", "Tainan",
    "Lijiang", "Dali", "Kunming", "Pingyao", "Luoyang",
    "Harbin", "Dalian", "Qingdao",
    "Ulaanbaatar",

    # === Central Asia ===
    "Almaty", "Tashkent", "Samarkand", "Bukhara", "Bishkek", "Ashgabat",

    # === Pacific & Oceania ===
    "Sydney", "Auckland", "Queenstown", "Wellington", "Christchurch",
    "Fiji", "Tahiti", "Bora Bora", "Hawaii", "Maui",
    "Maldives", "Seychelles", "Mauritius",
    # Additional Pacific
    "Melbourne", "Brisbane", "Cairns", "Perth", "Gold Coast",
    "Rotorua", "Milford Sound",
    "Samoa", "Tonga", "Vanuatu", "New Caledonia",

    # === Caribbean ===
    "Bermuda", "Bahamas", "Jamaica", "Barbados",
    "Trinidad and Tobago", "Saint Lucia", "Grenada", "Dominica",
    "Martinique", "Guadeloupe", "Aruba", "Curacao",

    # === Regions & Natural Destinations ===
    "Canary Islands", "Faroe Islands", "Svalbard", "Greenland",
    "Galapagos Islands", "Easter Island",
    "Tuscany", "Provence", "Andalusia", "Cappadocia",
    "Scottish Highlands", "Lake District",
    "Patagonia", "Amazon", "Pantanal",
    "Serengeti", "Okavango Delta",
    "Transylvania", "Black Forest",
    "Aosta Valley", "Dolomites",
]

# Major cities that have rich district/neighborhood sub-articles on Wikivoyage.
# Sub-articles follow the pattern "CityName/DistrictName".
CITIES_WITH_DISTRICTS = [
    "Paris", "London", "New York City", "Tokyo", "Rome", "Barcelona",
    "Amsterdam", "Berlin", "Madrid", "Vienna", "Sydney", "Chicago",
    "Los Angeles", "San Francisco", "Boston", "Washington, D.C.",
    "Buenos Aires", "Mexico City", "Istanbul", "Bangkok", "Singapore",
    "Hong Kong", "Seoul", "Kyoto", "Osaka", "Istanbul", "Athens",
    "Prague", "Budapest", "Lisbon", "Dublin", "Edinburgh",
    "Melbourne", "Dubai", "Mumbai", "Delhi", "Rio de Janeiro",
    "Sao Paulo", "Toronto", "Montreal", "Vancouver",
    "Beijing", "Shanghai", "Ho Chi Minh City", "Hanoi",
    "Kuala Lumpur", "Jakarta", "Manila",
]

# ---------------------------------------------------------------------------
# Full-dump helpers
# ---------------------------------------------------------------------------

# Wikivoyage publishes XML dumps at this URL (updated ~monthly).
DUMP_URL = "https://dumps.wikimedia.org/enwikivoyage/latest/enwikivoyage-latest-pages-articles.xml.bz2"

# Wikivoyage article namespaces to keep (0 = main articles)
KEEP_NAMESPACES = {"0"}

# Titles to skip even from the full dump
SKIP_PREFIXES = (
    "Wikivoyage:", "Template:", "User:", "User talk:", "Talk:",
    "File:", "MediaWiki:", "Help:", "Category:",
)


def _strip_wikitext(text: str) -> str:
    """Light wikitext → plaintext cleaning for Wikivoyage articles."""
    # Remove [[File:...]] and [[Image:...]]
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text, flags=re.IGNORECASE)
    # Convert [[link|label]] → label, [[link]] → link
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    # Remove {{templates}}
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # Remove <ref>...</ref> and bare <tags>
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    # Remove external links [http://... label] → label
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", "", text)
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def download_and_convert_dump(output_path: str) -> int:
    """
    Download the full English Wikivoyage XML dump (bz2) and stream-parse it
    into a JSONL file.  Returns the number of articles saved.

    The dump is parsed incrementally (no full decompression into RAM required)
    so it works even on machines with limited memory.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    dump_path = output_path.replace(".jsonl", ".xml.bz2")

    # 1. Download (stream so we don't load 300 MB at once)
    print(f"[+] Downloading Wikivoyage dump from:\n    {DUMP_URL}")
    print("    This is ~300 MB — may take a few minutes on a slow connection.")
    with requests.get(DUMP_URL, stream=True, timeout=120,
                      headers={"User-Agent": HEADERS["User-Agent"]}) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dump_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"    {downloaded / 1e6:.1f} / {total / 1e6:.1f} MB ({pct:.0f}%)  ",
                          end="\r", flush=True)
    print(f"\n    Download complete → {dump_path}")

    # 2. Stream-parse the bz2 XML and write JSONL
    print(f"\n[+] Parsing XML and writing JSONL → {output_path} ...")
    MW_NS = "http://www.mediawiki.org/xml/export-0.11/"

    saved = 0
    skipped = 0

    with bz2.open(dump_path, "rt", encoding="utf-8") as bz_file, \
         open(output_path, "w", encoding="utf-8") as out_file:

        # iterparse so we never load the whole XML tree
        context = ET.iterparse(bz_file, events=("end",))
        ns_map = {}
        current_title = ""
        current_ns = "0"
        current_text = ""

        for event, elem in context:
            tag = elem.tag.replace(f"{{{MW_NS}}}", "")

            if tag == "title":
                current_title = (elem.text or "").strip()
            elif tag == "ns":
                current_ns = (elem.text or "0").strip()
            elif tag == "text":
                current_text = (elem.text or "").strip()
            elif tag == "page":
                # Process complete page
                if (
                    current_ns in KEEP_NAMESPACES
                    and current_text
                    and not any(current_title.startswith(p) for p in SKIP_PREFIXES)
                    and "#REDIRECT" not in current_text.upper()
                    and len(current_text) > 200
                ):
                    clean = _strip_wikitext(current_text)
                    if len(clean) > 200:
                        article = {"title": current_title, "text": clean}
                        out_file.write(json.dumps(article, ensure_ascii=False) + "\n")
                        saved += 1
                        if saved % 500 == 0:
                            print(f"    {saved:,} articles saved...", flush=True)
                    else:
                        skipped += 1
                else:
                    skipped += 1

                # Free memory for processed element
                elem.clear()
                current_title = current_ns = current_text = ""

    print(f"    Parsing done: {saved:,} articles saved, {skipped:,} skipped.")
    print(f"    You can delete the raw dump to save space: rm '{dump_path}'")
    return saved


# ---------------------------------------------------------------------------
# Wikivoyage API helpers
# ---------------------------------------------------------------------------

def fetch_article(title: str, session: requests.Session) -> Optional[str]:
    """Fetch a single article's full plaintext from the Wikivoyage API."""
    params = {
        "action": "query",
        "prop": "extracts",
        "titles": title,
        "explaintext": "1",
        "format": "json",
        "redirects": "1",
    }
    try:
        r = session.get(API_URL, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                return None
            return page_data.get("extract", "")
    except Exception as e:
        print(f"    [warn] Error fetching '{title}': {e}")
        return None


def fetch_sub_articles(city: str, session: requests.Session) -> List[str]:
    """
    Discover district / neighborhood sub-articles for a major city.
    Wikivoyage stores these as sub-pages: "Paris/Marais", "Tokyo/Shinjuku", etc.
    Uses the 'links' prop and filters for titles starting with 'CityName/'.
    """
    params = {
        "action": "query",
        "prop": "links",
        "titles": city,
        "pllimit": "500",
        "plnamespace": "0",
        "format": "json",
        "redirects": "1",
    }
    try:
        r = session.get(API_URL, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        sub_titles: List[str] = []
        city_lower = city.lower()
        for page_data in pages.values():
            for link in page_data.get("links", []):
                link_title = link.get("title", "")
                # Keep sub-pages of this city, skip other links
                if "/" in link_title and link_title.lower().startswith(city_lower + "/"):
                    sub_titles.append(link_title)
        return sub_titles
    except Exception as e:
        print(f"    [warn] Error fetching sub-articles for '{city}': {e}")
        return []


def discover_via_category(category: str, session: requests.Session, limit: int = 500) -> List[str]:
    """
    Retrieve all article titles from a Wikivoyage category (handles pagination).
    Useful categories: "Cities", "Regions", "Countries", "Islands",  "Beach_destinations"
    """
    titles: List[str] = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": min(limit - len(titles), 500),
            "cmtype": "page",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        try:
            r = session.get(API_URL, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            members = data.get("query", {}).get("categorymembers", [])
            titles.extend(m["title"] for m in members)
            cont = data.get("continue", {})
            cmcontinue = cont.get("cmcontinue")
            if not cmcontinue or len(titles) >= limit:
                break
        except Exception as e:
            print(f"    [warn] Error fetching category '{category}': {e}")
            break
    return titles[:limit]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch Wikivoyage data for Tripzy RAG")
    parser.add_argument("--output", default="data/wikivoyage_dump.jsonl",
                        help="Output JSONL file (default: data/wikivoyage_dump.jsonl)")
    parser.add_argument("--download-dump", action="store_true",
                        help="Download the COMPLETE Wikivoyage XML dump (~300 MB) and convert "
                             "to JSONL. Gives all 30,000+ articles. Recommended for max coverage.")
    parser.add_argument("--fetch-subpages", action="store_true",
                        help="Also fetch district/neighborhood sub-articles for major cities "
                             "(adds 300-600 extra pages with hyper-local info)")
    parser.add_argument("--use-categories", action="store_true",
                        help="Auto-discover additional articles via Wikivoyage categories "
                             "(Cities, Regions, Islands, etc.)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip titles already saved in the output file (safe to re-run)")
    parser.add_argument("--delay", type=float, default=0.15,
                        help="Seconds to wait between API requests (default: 0.15)")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)

    # ---- Full-dump mode: download everything at once ----
    if args.download_dump:
        saved = download_and_convert_dump(args.output)
        print(f"\n{'=' * 60}")
        print(f"  Full dump complete: {saved:,} articles → {args.output}")
        print(f"  Next step: python -m app.ingest_wikivoyage --data-path {args.output}")
        print(f"{'=' * 60}")
        return

    # Build the list of titles to fetch
    all_titles: List[str] = list(DESTINATIONS)

    session = requests.Session()

    # ---- Optional: auto-discover via categories ----
    if args.use_categories:
        categories = [
            "Cities", "Regions", "Countries", "Islands",
            "Beach_destinations", "Mountain_destinations",
        ]
        print("\n[+] Discovering articles via categories...")
        discovered: Set[str] = set(all_titles)
        for cat in categories:
            cat_titles = discover_via_category(cat, session, limit=300)
            new = [t for t in cat_titles if t not in discovered]
            print(f"    Category:{cat} → {len(cat_titles)} articles, {len(new)} new")
            all_titles.extend(new)
            discovered.update(new)
            time.sleep(args.delay)

    # ---- Optional: discover district sub-articles ----
    if args.fetch_subpages:
        print("\n[+] Discovering district sub-articles for major cities...")
        sub_titles_set: Set[str] = set(all_titles)
        for city in CITIES_WITH_DISTRICTS:
            subs = fetch_sub_articles(city, session)
            new_subs = [s for s in subs if s not in sub_titles_set]
            if new_subs:
                print(f"    {city}: found {len(new_subs)} sub-articles "
                      f"({', '.join(new_subs[:4])}{'...' if len(new_subs) > 4 else ''})")
            all_titles.extend(new_subs)
            sub_titles_set.update(new_subs)
            time.sleep(args.delay)

    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique_titles: List[str] = []
    for t in all_titles:
        if t not in seen:
            seen.add(t)
            unique_titles.append(t)
    all_titles = unique_titles

    # ---- Resume: skip already-saved titles ----
    already_saved: Set[str] = set()
    if args.resume and os.path.exists(args.output):
        with open(args.output, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        already_saved.add(json.loads(line)["title"])
                    except Exception:
                        pass
        print(f"\n[+] Resume mode: {len(already_saved)} titles already saved, skipping them.")

    titles_to_fetch = [t for t in all_titles if t not in already_saved]

    print(f"\n{'=' * 60}")
    print(f"  Total unique titles to fetch: {len(titles_to_fetch)}")
    if args.resume:
        print(f"  (Skipping {len(already_saved)} already saved)")
    print(f"{'=' * 60}\n")

    # ---- Fetch and write ----
    write_mode = "a" if args.resume else "w"
    saved = 0
    skipped = 0

    with open(args.output, write_mode, encoding="utf-8") as f:
        for i, title in enumerate(titles_to_fetch):
            print(f"[{i + 1}/{len(titles_to_fetch)}] Fetching: {title}...", end=" ", flush=True)
            text = fetch_article(title, session)

            if text and len(text) > 200:
                article = {"title": title, "text": text}
                f.write(json.dumps(article, ensure_ascii=False) + "\n")
                saved += 1
                print(f"✓ ({len(text):,} chars)")
            else:
                skipped += 1
                print("✗ (skipped — too short or not found)")

            time.sleep(args.delay)

    print(f"\n{'=' * 60}")
    print(f"  Done!  Saved: {saved}  |  Skipped: {skipped}")
    print(f"  Output: {args.output}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

