import unittest

from routewise_ai_demo.agents.central_agent import CentralAgent


class FakeGroqClient:
    def __init__(self, response):
        self.response = response

    def complete_json(self, *, system_prompt, user_payload, temperature=0.2, max_tokens=1800):
        return self.response


class CentralAgentTest(unittest.TestCase):
    def test_defaults_date_window_and_duration_for_flight_readiness(self):
        agent = CentralAgent(
            FakeGroqClient(
                {
                    "trip_state_patch": {
                        "destination": "Tokyo",
                        "interests": ["anime"],
                        "planning_facts": ["audience: teenagers"],
                        "flight_preferences": {"priority": "balanced", "flexible_dates": False},
                    },
                    "missing_fields": [],
                    "is_edit_request": False,
                    "assistant_message": "I can plan Tokyo.",
                    "orchestration": ["flight_desk_agent", "day_plan_agent"],
                }
            )
        )

        result = agent.run("Plan Tokyo", {})
        state = result["trip_state"]

        self.assertEqual(state["destination"], "TOKYO")
        self.assertEqual(state["duration_days"], 7)
        self.assertTrue(state["flight_preferences"]["flexible_dates"])
        self.assertTrue(state["flight_preferences"]["date_window_start"])
        self.assertTrue(state["flight_preferences"]["date_window_end"])
        self.assertEqual(result["missing_fields"], ["origin"])
        self.assertIn("starting city or airport", result["assistant_message"])

    def test_origin_allows_flight_handoff_with_default_window(self):
        agent = CentralAgent(
            FakeGroqClient(
                {
                    "trip_state_patch": {
                        "origin": "HYD",
                        "destination": "Tokyo",
                        "duration_days": 5,
                    },
                    "missing_fields": [],
                    "is_edit_request": False,
                    "assistant_message": "I can plan Tokyo.",
                    "orchestration": ["flight_desk_agent", "day_plan_agent"],
                }
            )
        )

        result = agent.run("Plan Tokyo from Hyderabad", {})
        state = result["trip_state"]

        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(state["duration_days"], 5)
        self.assertTrue(state["flight_preferences"]["date_window_start"])


if __name__ == "__main__":
    unittest.main()
