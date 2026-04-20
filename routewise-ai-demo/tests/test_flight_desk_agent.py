import unittest
from unittest.mock import patch

from routewise_ai_demo.agents.flight_desk_agent import FlightDeskAgent
from routewise_ai_demo.services.rapidapi_flights import RapidApiFlightsClient, RapidApiTimeoutError


class DummyFlightsClient:
    def __init__(self):
        self.calendar_called = False
        self.flight_list_state = None

    def calendar_tool(self, trip_state):
        self.calendar_called = True
        return {
            "tool_call": {"name": "calendar_tool"},
            "reasoning": "calendar_tool scanned candidate dates.",
            "calendar": [
                {"departure_date": "2026-05-11", "return_date": "2026-05-15", "price": 720, "currency": "USD"},
                {"departure_date": "2026-05-08", "return_date": "2026-05-12", "price": 510, "currency": "USD"},
            ],
        }

    def flight_list_tool(self, trip_state):
        self.flight_list_state = dict(trip_state)
        return {
            "tool_call": {"name": "flight_list_tool"},
            "options": [
                {
                    "origin": "SFO",
                    "destination": "HND",
                    "departure_date": trip_state["start_date"],
                    "arrival_date": trip_state["end_date"],
                    "price": 540,
                    "currency": "USD",
                    "duration_minutes": 690,
                    "stops": 1,
                }
            ],
        }


class EmptyCalendarClient(DummyFlightsClient):
    def calendar_tool(self, trip_state):
        self.calendar_called = True
        return {
            "tool_call": {"name": "calendar_tool"},
            "reasoning": "calendar_tool scanned but found no normalized price rows.",
            "calendar": [],
        }


class EmptyFlightListClient(DummyFlightsClient):
    def flight_list_tool(self, trip_state):
        self.flight_list_state = dict(trip_state)
        return {
            "tool_call": {"name": "flight_list_tool"},
            "options": [],
        }


class TimeoutCalendarClient(DummyFlightsClient):
    def calendar_tool(self, trip_state):
        self.calendar_called = True
        raise RapidApiTimeoutError("RapidAPI tool timed out after 8s.")


class TimeoutFlightListClient(DummyFlightsClient):
    def flight_list_tool(self, trip_state):
        self.flight_list_state = dict(trip_state)
        raise RapidApiTimeoutError("RapidAPI tool timed out after 8s.")


class FlightDeskAgentTest(unittest.TestCase):
    def test_rapidapi_timeout_defaults_low_and_can_be_overridden(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(RapidApiFlightsClient().timeout_seconds, 8)

        with patch.dict("os.environ", {"RAPIDAPI_TIMEOUT_SECONDS": "11"}, clear=True):
            self.assertEqual(RapidApiFlightsClient().timeout_seconds, 11)

    def test_calendar_path_selects_cheapest_candidate_before_exact_list(self):
        client = DummyFlightsClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "SFO",
                "destination": "HND",
                "start_date": "2026-05-10",
                "end_date": "2026-05-14",
                "duration_days": 4,
                "travelers": 2,
                "budget_currency": "USD",
                "flight_preferences": {
                    "priority": "cheap",
                    "flexible_dates": True,
                    "flex_window_days": 3,
                },
            }
        )

        flight_search = result["trip_state"]["flight_search"]
        self.assertEqual(result["status"], "done")
        self.assertTrue(client.calendar_called)
        self.assertEqual(client.flight_list_state["start_date"], "2026-05-08")
        self.assertEqual(client.flight_list_state["end_date"], "2026-05-12")
        self.assertEqual(flight_search["strategy"], "calendar_then_flight_list")
        self.assertEqual(flight_search["selected_calendar_pick"]["price"], 510)
        self.assertEqual(flight_search["selected_option"]["price"], 540)

    def test_missing_inputs_skip_without_tool_calls(self):
        client = DummyFlightsClient()
        agent = FlightDeskAgent(client)

        result = agent.run({"destination": "Tokyo", "start_date": "2026-05-10"})

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(client.calendar_called)
        self.assertIsNone(client.flight_list_state)
        self.assertEqual(result["trip_state"]["flight_search"]["strategy"], "skipped_missing_inputs")
        self.assertEqual(result["details"]["strategy"], "skipped_missing_inputs")

    def test_calendar_path_accepts_broad_date_window_and_writes_selected_dates(self):
        client = DummyFlightsClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "SFO",
                "destination": "HND",
                "start_date": "",
                "end_date": "",
                "duration_days": 7,
                "travelers": 1,
                "budget_currency": "USD",
                "flight_preferences": {
                    "priority": "cheap",
                    "flexible_dates": True,
                    "date_window_start": "2026-05-01",
                    "date_window_end": "2026-05-31",
                },
            }
        )

        self.assertEqual(result["status"], "done")
        self.assertTrue(client.calendar_called)
        self.assertEqual(client.flight_list_state["start_date"], "2026-05-08")
        self.assertEqual(client.flight_list_state["end_date"], "2026-05-12")
        self.assertEqual(result["trip_state"]["start_date"], "2026-05-08")
        self.assertEqual(result["trip_state"]["end_date"], "2026-05-12")
        self.assertEqual(result["trip_state"]["flight_search"]["strategy"], "calendar_then_flight_list")

    def test_exact_dates_without_flexibility_use_flight_list_only(self):
        client = DummyFlightsClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "INDORE",
                "destination": "HYDERABAD",
                "start_date": "2026-05-12",
                "end_date": "2026-05-22",
                "duration_days": 10,
                "travelers": 1,
                "budget_currency": "USD",
                "flight_preferences": {
                    "priority": "balanced",
                    "flexible_dates": False,
                },
            }
        )

        self.assertEqual(result["status"], "done")
        self.assertFalse(client.calendar_called)
        self.assertEqual(client.flight_list_state["start_date"], "2026-05-12")
        self.assertEqual(result["trip_state"]["flight_search"]["strategy"], "flight_list_only")
        self.assertEqual(result["details"]["tool_names"], ["flight_list_tool"])

    def test_same_origin_and_destination_skip_flights(self):
        client = DummyFlightsClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "HYD",
                "destination": "HYDERABAD",
                "start_date": "2026-05-12",
                "duration_days": 7,
                "travelers": 1,
                "budget_currency": "USD",
                "flight_preferences": {"priority": "cheap", "flexible_dates": True},
            }
        )

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(client.calendar_called)
        self.assertEqual(result["trip_state"]["flight_search"]["strategy"], "skipped_same_origin_destination")

    def test_empty_calendar_does_not_request_exact_flights(self):
        client = EmptyCalendarClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "IDR",
                "destination": "HYD",
                "start_date": "",
                "end_date": "",
                "duration_days": 7,
                "travelers": 1,
                "budget_currency": "USD",
                "flight_preferences": {
                    "priority": "cheap",
                    "flexible_dates": True,
                    "date_window_start": "2026-05-01",
                    "date_window_end": "2026-05-31",
                },
            }
        )

        self.assertEqual(result["status"], "skipped")
        self.assertTrue(client.calendar_called)
        self.assertIsNone(client.flight_list_state)
        self.assertEqual(result["trip_state"]["flight_search"]["strategy"], "calendar_no_price_rows")

    def test_empty_exact_flight_list_is_not_reported_as_done(self):
        client = EmptyFlightListClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "IDR",
                "destination": "HYD",
                "start_date": "2026-05-12",
                "end_date": "2026-05-22",
                "duration_days": 10,
                "travelers": 1,
                "budget_currency": "USD",
                "flight_preferences": {"priority": "balanced", "flexible_dates": False},
            }
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["trip_state"]["flight_search"]["strategy"], "flight_list_no_options")
        self.assertEqual(result["trip_state"]["flight_search"]["options"], [])

    def test_calendar_timeout_is_graceful_skip(self):
        client = TimeoutCalendarClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "IDR",
                "destination": "HND",
                "start_date": "",
                "end_date": "",
                "duration_days": 7,
                "travelers": 1,
                "budget_currency": "USD",
                "flight_preferences": {
                    "priority": "cheap",
                    "flexible_dates": True,
                    "date_window_start": "2026-05-01",
                    "date_window_end": "2026-05-31",
                },
            }
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["trip_state"]["flight_search"]["strategy"], "skipped_tool_timeout")
        self.assertIn("timed out", result["trip_state"]["flight_search"]["reasoning"])

    def test_calendar_pick_survives_exact_list_timeout(self):
        client = TimeoutFlightListClient()
        agent = FlightDeskAgent(client)

        result = agent.run(
            {
                "origin": "IDR",
                "destination": "HND",
                "start_date": "",
                "end_date": "",
                "duration_days": 7,
                "travelers": 1,
                "budget_currency": "USD",
                "flight_preferences": {
                    "priority": "cheap",
                    "flexible_dates": True,
                    "date_window_start": "2026-05-01",
                    "date_window_end": "2026-05-31",
                },
            }
        )

        flight_search = result["trip_state"]["flight_search"]
        self.assertEqual(result["status"], "done")
        self.assertEqual(flight_search["strategy"], "calendar_then_flight_list")
        self.assertEqual(flight_search["selected_option"]["id"], "calendar-pick")
        self.assertEqual(flight_search["selected_option"]["price"], 510)


if __name__ == "__main__":
    unittest.main()
