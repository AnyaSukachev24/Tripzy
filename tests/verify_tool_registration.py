"""Quick sanity check: verify all new tools imported in graph, in tool_map, and callable."""
import sys, os, json, inspect
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

NEW_TOOLS = [
    "resolve_airport_code_tool",
    "get_airline_info_tool",
    "search_tours_activities_tool",
    "search_points_of_interest_tool",
]

passes = 0
fails = 0

def check(label, ok):
    global passes, fails
    if ok:
        passes += 1
        print(f"[PASS] {label}")
    else:
        fails += 1
        print(f"[FAIL] {label}")

# 1. Import from tools.py
from app.tools import (
    resolve_airport_code_tool,
    get_airline_info_tool,
    search_tours_activities_tool,
    search_points_of_interest_tool,
)
check("All 4 new tools importable from app.tools", True)

# 2. Import from graph module (re-exported)
import app.graph as g
for t in NEW_TOOLS:
    check(f"{t} importable from app.graph", hasattr(g, t))

# 3. Researcher tool_map source check
researcher_src = inspect.getsource(g.researcher_node)
for t in NEW_TOOLS:
    check(f"{t} in Researcher tool_map", t in researcher_src)

# 4. Planner tools list source check
planner_src = inspect.getsource(g.planner_node)
for t in NEW_TOOLS:
    check(f"{t} in Planner tools list", t in planner_src)

# 5. Legacy hotel path has adults
check("Legacy hotel path has 'adults' param", "'adults'" in researcher_src)

# 6. Direct tool call: resolve_airport_code_tool
res = resolve_airport_code_tool.invoke({"keyword": "Paris"})
data = json.loads(res)
first = data[0] if data else {}
check("resolve_airport_code returns iataCode", bool(first.get("iataCode")))
print(f"  -> iataCode={first.get('iataCode')}, name={first.get('name')}, type={first.get('type')}")

# 7. Direct tool call: search_tours_activities_tool (Paris lat/lng)
res2 = search_tours_activities_tool.invoke({"latitude": 48.8566, "longitude": 2.3522, "radius": 5})
data2 = json.loads(res2)
if isinstance(data2, list):
    check("search_tours_activities returned list", len(data2) > 0)
    print(f"  -> {len(data2)} activities, first: {data2[0].get('name', 'N/A')}")
else:
    check("search_tours_activities returned list", False)
    print(f"  -> {data2}")

print(f"\n{'='*50}")
print(f"RESULTS: {passes} passed, {fails} failed")
sys.exit(0 if fails == 0 else 1)
