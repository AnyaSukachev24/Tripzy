"""Quick test: Multi-source flight aggregator."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.tools import search_flights_tool

result = search_flights_tool.invoke({
    "origin": "JFK",
    "destination": "CDG",
    "departure_date": "2026-06-15",
    "return_date": "2026-06-22",
    "adults": 1,
})

data = json.loads(result)
sources = set(f.get("source", "?") for f in data)
print(f"\nTotal flights: {len(data)}")
print(f"Sources: {sources}\n")
for f in data[:8]:
    src = f.get("source", "?")
    price = f.get("price", {}).get("total", "?")
    currency = f.get("price", {}).get("currency", "?")
    fid = f.get("id", "")
    airline = f.get("airline_name", "") or ",".join(f.get("validatingAirlineCodes", []))
    print(f"  {src:16s} {price:>10s} {currency:>4s}  {airline:20s} id={fid}")
