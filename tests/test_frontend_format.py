
import sys
import unittest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.main import format_plan_to_markdown

class TestFrontendFormat(unittest.TestCase):
    def test_basic_formatting(self):
        plan = {
            "destination": "Paris",
            "budget_estimate": 2000,
            "itinerary": [
                {"day": 1, "activity": "Eiffel Tower", "cost": 50}
            ]
        }
        md = format_plan_to_markdown(plan)
        self.assertIn("Trip to Paris", md)
        self.assertIn("$2000", md)
        self.assertIn("Day 1", md)
        self.assertIn("Eiffel Tower", md)

    def test_logistics_formatting(self):
        plan = {
            "destination": "Bali",
            "origin_city": "New York",
            "dates": "2024-12-01 to 2024-12-10",
            "budget_estimate": 5000,
            "flights": [
                {"airline": "Garuda Indonesia", "price": "1200 USD", "flight_number": "GA88", "link": "http://flight"}
            ],
            "hotels": [
                {"name": "Bali Resort", "price": "200 USD/night", "rating": 4.5, "link": "http://hotel"}
            ],
            "itinerary": []
        }
        md = format_plan_to_markdown(plan)
        
        # Check Logistics Summary
        self.assertIn("New York", md) # Origin
        self.assertIn("2024-12-01", md) # Dates
        
        # Check Sections
        self.assertIn("✈️ Flights", md)
        self.assertIn("Garuda Indonesia", md)
        self.assertIn("GA88", md)
        
        self.assertIn("🏨 Accommodation", md)
        self.assertIn("Bali Resort", md)
        self.assertIn("4.5", md)
        
    def test_missing_logistics(self):
        plan = {
            "destination": "Rome",
            "itinerary": []
        }
        md = format_plan_to_markdown(plan)
        # Should not have flight/hotel sections
        self.assertNotIn("#### ✈️ Flight Options", md)
        self.assertNotIn("#### 🏨 Accommodation Options", md)
        
        # Itinerary header is always present
        self.assertIn("#### 📅 Itinerary", md)

if __name__ == '__main__':
    unittest.main()
