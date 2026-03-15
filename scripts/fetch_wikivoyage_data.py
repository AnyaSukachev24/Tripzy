import requests
import json
import time
import os

DESTINATIONS = [
    "Paris", "London", "Rome", "Tokyo", "New York City", "Bali", "Dubai", "Barcelona", "Amsterdam", "Istanbul",
    "Bangkok", "Singapore", "Sydney", "Rio de Janeiro", "Cape Town", "Prague", "Berlin", "Venice", "Madrid", 
    "Kyoto", "Honolulu", "Cancun", "Phuket", "Las Vegas", "Miami", "Los Angeles", "San Francisco", "Lisbon",
    "Athens", "Vienna", "Munich", "Florence", "Milan", "Hong Kong", "Seoul", "Budapest", "Edinburgh", "Dublin",
    "Toronto", "Vancouver", "Montreal", "Buenos Aires", "Machu Picchu", "Cusco", "Lima", "Bogota", "Medellin",
    "Santiago", "Havana", "San Juan", "Mexico City", "Oaxaca", "Tulum", "Reykjavik", "Oslo", "Stockholm",
    "Copenhagen", "Helsinki", "Tallinn", "Riga", "Vilnius", "Krakow", "Warsaw", "Brussels", "Bruges", "Geneva",
    "Zurich", "Lucerne", "Salzburg", "Dubrovnik", "Split", "Athens", "Santorini", "Mykonos", "Crete", "Rhodes",
    "Cairo", "Luxor", "Marrakech", "Casablanca", "Fes", "Nairobi", "Zanzibar", "Victoria Falls", "Johannesburg",
    "Durban", "Delhi", "Mumbai", "Jaipur", "Agra", "Goa", "Kerala", "Kathmandu", "Thimphu", "Colombo", "Male",
    "Hanoi", "Ho Chi Minh City", "Hoi An", "Da Nang", "Siem Reap", "Phnom Penh", "Luang Prabang", "Vientiane",
    "Yangon", "Bagan", "Taipei", "Beijing", "Shanghai", "Xi'an", "Chengdu", "Guilin", "Hangzhou", "Macau",
    "Manila", "Cebu", "Boracay", "Palawan", "Kuala Lumpur", "Penang", "Langkawi", "Malacca", "Jakarta", "Yogyakarta",
    "Auckland", "Queenstown", "Wellington", "Christchurch", "Fiji", "Tahiti", "Bora Bora", "Hawaii", "Maui",
    "Maldives", "Seychelles", "Mauritius", "Bermuda", "Bahamas", "Jamaica", "Barbados", "Costa Rica", "Belize",
    "Galapagos Islands", "Easter Island", "Antarctica", "Greenland", "Faroe Islands", "Svalbard", "Canary Islands"
]

def fetch_wikivoyage_article(title):
    url = "https://en.wikivoyage.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "titles": title,
        "explaintext": "1",
        "format": "json",
        "redirects": "1"
    }
    
    headers = {
        "User-Agent": "TripzyDataIngestionBot/1.0 (https://github.com/AnyaSukachev24/Tripzy; admin@tripzy.local)"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                return None
            return page_data.get("extract", "")
    except Exception as e:
        print(f"Error fetching {title}: {e}")
        return None

def main():
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    output_file = "data/wikivoyage_dump.jsonl"
    print(f"Fetching data for {len(DESTINATIONS)} destinations...")
    
    with open(output_file, "w", encoding="utf-8") as f:
        for i, dest in enumerate(DESTINATIONS):
            print(f"[{i+1}/{len(DESTINATIONS)}] Fetching {dest}...")
            text = fetch_wikivoyage_article(dest)
            if text and len(text) > 100:
                article = {"title": dest, "text": text}
                f.write(json.dumps(article) + "\n")
            else:
                print(f"  -> Skipped {dest} (no text or too short)")
            time.sleep(0.1)  # small rate limit
            
    print(f"Data saved to {output_file}")

if __name__ == "__main__":
    main()
