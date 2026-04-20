import unittest

from routewise_ai_demo.agents.day_plan_agent import DayPlanAgent


class FakeGroqClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = ""
        self.last_payload = None

    def complete_json(self, *, system_prompt, user_payload, temperature=0.2, max_tokens=1800):
        self.last_prompt = system_prompt
        self.last_payload = user_payload
        return self.response


class DayPlanAgentTest(unittest.TestCase):
    def test_applies_named_hotels_and_places(self):
        client = FakeGroqClient(
            {
                "title": "3-Day Hyderabad Teen Trip",
                "summary": "A Hyderabad plan with named stays and youth-focused stops.",
                "hotel_suggestions": [
                    {
                        "name": "Trident Hyderabad",
                        "area": "HITEC City",
                        "type": "business hotel",
                        "why": "Good base for malls, cafes, and Ramoji Film City pickup points.",
                        "budget_level": "upper-mid-range",
                    },
                    {
                        "name": "Marriott Executive Apartments Hyderabad",
                        "area": "Gachibowli",
                        "type": "apartment hotel",
                        "why": "Useful for longer stays and groups.",
                        "budget_level": "upper-mid-range",
                    },
                ],
                "place_shortlist": [
                    {
                        "name": "Ramoji Film City",
                        "area": "Abdullapurmet",
                        "type": "theme park and studio tour",
                        "why": "Full-day teen-friendly attraction.",
                    },
                    {
                        "name": "Inorbit Mall Cyberabad",
                        "area": "Madhapur",
                        "type": "mall",
                        "why": "Easy food, shopping, and indoor break.",
                    },
                ],
                "itinerary": [
                    {
                        "day": 1,
                        "theme": "HITEC City and Inorbit",
                        "morning": "Check in around HITEC City and start with breakfast at Roast CCX.",
                        "afternoon": "Visit Inorbit Mall Cyberabad and nearby Durgam Cheruvu Cable Bridge.",
                        "evening": "Eat at The Fisherman's Wharf or a casual cafe in Madhapur.",
                        "estimated_cost": "USD 45-90 excluding lodging",
                        "pace": "balanced",
                    }
                ],
                "budget_notes": "Hotels are examples; verify live prices and policies before booking.",
                "assistant_message": "I created a specific Hyderabad plan with hotel examples and named stops.",
            }
        )

        result = DayPlanAgent(client).run(
            {
                "destination": "HYDERABAD",
                "duration_days": 3,
                "interests": ["adventure"],
                "planning_facts": ["audience: teenagers"],
                "pace": "balanced",
            }
        )

        state = result["trip_state"]
        self.assertIn("named hotel", client.last_prompt.lower())
        self.assertEqual(state["hotel_suggestions"][0]["name"], "Trident Hyderabad")
        self.assertEqual(state["place_shortlist"][0]["name"], "Ramoji Film City")
        self.assertIn("Inorbit Mall Cyberabad", state["itinerary"][0]["afternoon"])
        self.assertIn("hotel examples", result["assistant_message"])


if __name__ == "__main__":
    unittest.main()
