import unittest

from routewise_ai_demo.schemas import blocking_missing_fields, coerce_trip_state, validate_message_payload


class SchemaGuardrailsTest(unittest.TestCase):
    def test_rejects_overlong_message(self):
        message, state, error = validate_message_payload({"message": "x" * 4001})

        self.assertEqual(message, "")
        self.assertIsNone(state)
        self.assertIn("4000", error)

    def test_coerces_bounds_and_drops_unknown_fields(self):
        state = coerce_trip_state(
            {
                "destination": "tokyo",
                "unknown_field": "ignore me",
                "duration_days": 400,
                "travelers": 99,
                "pace": "impossible",
                "budget": -100,
                "interests": ["anime", "anime", "", 7, "gaming"],
                "planning_facts": [f"fact {index}" for index in range(20)],
                "hotel_suggestions": [
                    {"name": "Hotel A", "area": "Area", "type": "hotel", "why": "Good base", "budget_level": "mid"}
                ],
                "place_shortlist": [
                    {"name": "Place A", "area": "Area", "type": "museum", "why": "Good stop"}
                ],
                "flight_preferences": {
                    "priority": "magic",
                    "flex_window_days": 100,
                    "date_window_start": "2026-05-31",
                    "date_window_end": "2026-05-01",
                    "max_stops": 9,
                    "cabin_class": 9,
                },
            }
        )

        self.assertNotIn("unknown_field", state)
        self.assertEqual(state["destination"], "TOKYO")
        self.assertEqual(state["duration_days"], 30)
        self.assertEqual(state["travelers"], 12)
        self.assertEqual(state["pace"], "balanced")
        self.assertIsNone(state["budget"])
        self.assertEqual(state["interests"], ["anime", "gaming"])
        self.assertEqual(len(state["planning_facts"]), 12)
        self.assertEqual(state["hotel_suggestions"][0]["name"], "Hotel A")
        self.assertEqual(state["place_shortlist"][0]["name"], "Place A")
        self.assertEqual(state["flight_preferences"]["priority"], "balanced")
        self.assertEqual(state["flight_preferences"]["flex_window_days"], 14)
        self.assertEqual(state["flight_preferences"]["date_window_start"], "")
        self.assertEqual(state["flight_preferences"]["date_window_end"], "")
        self.assertEqual(state["flight_preferences"]["max_stops"], 2)
        self.assertIsNone(state["flight_preferences"]["cabin_class"])

    def test_missing_fields_are_normalized_from_state(self):
        state = coerce_trip_state(
            {
                "origin": "Indore",
                "destination": "Hyderabad",
                "duration_days": 10,
                "flight_preferences": {
                    "date_window_start": "2026-05-01",
                    "date_window_end": "2026-05-31",
                },
            }
        )

        self.assertEqual(blocking_missing_fields(state, ["start_date", "duration_days"]), [])

    def test_origin_can_still_block_when_flight_date_selection_needs_it(self):
        state = coerce_trip_state(
            {
                "destination": "Japan",
                "duration_days": 7,
                "flight_preferences": {
                    "priority": "cheap",
                    "flexible_dates": True,
                    "date_window_start": "2026-05-01",
                    "date_window_end": "2026-05-31",
                },
            }
        )

        self.assertEqual(blocking_missing_fields(state, ["origin"]), ["origin"])

    def test_same_origin_destination_is_treated_as_local_trip(self):
        state = coerce_trip_state(
            {
                "origin": "HYD",
                "destination": "Hyderabad",
                "duration_days": 7,
            }
        )

        self.assertEqual(state["origin"], "")
        self.assertEqual(state["destination"], "HYDERABAD")


if __name__ == "__main__":
    unittest.main()
