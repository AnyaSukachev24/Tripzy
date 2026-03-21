import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.tools import suggest_attractions_tool
from app.graph import researcher_node


class TestAttractionsRagFlow(unittest.TestCase):
    def test_suggest_attractions_strict_then_relaxed(self):
        strict_hits = [
            {
                "name": "Louvre Museum",
                "category": "Museum",
                "description": "Art museum",
                "address": "Rue de Rivoli",
                "city": "Paris",
                "country": "France",
                "latitude": 48.86,
                "longitude": 2.33,
                "source": "Pinecone-Attractions",
                "score": 0.91,
                "type": "attraction",
            }
        ]
        relaxed_hits = [
            {
                "name": "Eiffel Tower",
                "category": "Landmark",
                "description": "Landmark",
                "address": "Champ de Mars",
                "city": "Paris",
                "country": "France",
                "latitude": 48.85,
                "longitude": 2.29,
                "source": "Pinecone-Attractions",
                "score": 0.89,
                "type": "attraction",
            }
        ]

        with patch("app.tools._query_attractions_index", side_effect=[strict_hits, relaxed_hits]) as q_mock:
            raw = suggest_attractions_tool.invoke(
                {
                    "destination": "Paris, France",
                    "interests": ["museums"],
                    "trip_type": "culture",
                }
            )

        data = json.loads(raw)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 2)
        self.assertEqual(data[0]["city"], "Paris")
        self.assertEqual(q_mock.call_count, 2)

    def test_suggest_attractions_restaurant_intent_uses_category_terms(self):
        with patch(
            "app.tools._query_attractions_index",
            return_value=[
                {
                    "name": "Vegan Bistro",
                    "category": "Restaurant",
                    "description": "Plant-based dining",
                    "address": "Shibuya",
                    "city": "Tokyo",
                    "country": "Japan",
                    "latitude": None,
                    "longitude": None,
                    "source": "Pinecone-Attractions",
                    "score": 0.88,
                    "type": "dining",
                }
            ],
        ) as q_mock:
            raw = suggest_attractions_tool.invoke(
                {
                    "destination": "Tokyo",
                    "interests": ["food", "restaurants"],
                    "trip_type": "food",
                }
            )

        data = json.loads(raw)
        self.assertTrue(data)
        first_call_kwargs = q_mock.call_args_list[0].kwargs
        self.assertIn("category_terms", first_call_kwargs)
        self.assertIsNotNone(first_call_kwargs["category_terms"])

    def test_researcher_caches_attractions_results(self):
        mock_suggest_tool = MagicMock()
        mock_suggest_tool.invoke.return_value = json.dumps(
            [
                {
                    "name": "Louvre Museum",
                    "category": "Museum",
                    "city": "Paris",
                    "source": "Pinecone-Attractions",
                }
            ]
        )

        state = {
            "supervisor_instruction": "TOOL_CALLS: [{\"name\": \"suggest_attractions_tool\", \"args\": {\"destination\": \"Paris\"}}]",
            "steps": [{"module": "Supervisor", "prompt": "Find attractions in Paris"}],
            "researcher_calls": 0,
        }

        with patch("app.graph.suggest_attractions_tool", mock_suggest_tool):
            out = researcher_node(state)

        self.assertIn("last_attraction_results", out)
        self.assertIsInstance(out["last_attraction_results"], list)
        self.assertGreaterEqual(len(out["last_attraction_results"]), 1)

    def test_researcher_injects_cached_attractions_into_create_plan(self):
        captured_args = {}

        class _CreatePlanToolMock:
            @staticmethod
            def invoke(args):
                captured_args.update(args)
                return json.dumps({"status": "ok"})

        state = {
            "supervisor_instruction": (
                "TOOL_CALLS: [{\"name\": \"create_plan_tool\", \"args\": "
                "{\"destination\": \"Paris\", \"origin\": \"NYC\", \"duration_days\": 3, \"budget\": 1200}}]"
            ),
            "last_attraction_results": [
                {"name": "Louvre Museum", "category": "Museum", "city": "Paris"}
            ],
            "steps": [{"module": "Planner", "prompt": "Build attractions-only plan"}],
            "researcher_calls": 0,
        }

        with patch("app.graph.create_plan_tool", _CreatePlanToolMock):
            researcher_node(state)

        self.assertIn("attractions_data", captured_args)
        parsed = json.loads(captured_args["attractions_data"])
        self.assertTrue(parsed)
        self.assertEqual(parsed[0]["name"], "Louvre Museum")


if __name__ == "__main__":
    unittest.main()
