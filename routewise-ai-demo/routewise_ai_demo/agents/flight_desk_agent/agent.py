from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from routewise_ai_demo.schemas import apply_trip_patch, has_flight_inputs
from routewise_ai_demo.services.rapidapi_flights import RapidApiConfigurationError, RapidApiFlightsClient, RapidApiTimeoutError


class FlightDeskAgent:
    agent_id = "flight_desk_agent"

    def __init__(self, flights_client: Any):
        self.flights_client = flights_client

    @staticmethod
    def _wants_calendar_reasoning(trip_state: Dict[str, Any]) -> bool:
        preferences = trip_state.get("flight_preferences") if isinstance(trip_state.get("flight_preferences"), dict) else {}
        if preferences.get("priority") == "cheap":
            return True
        if preferences.get("flexible_dates") is True:
            return True
        return bool(preferences.get("date_window_start") and not trip_state.get("start_date"))

    @staticmethod
    def _flight_details(flight_search: Dict[str, Any]) -> Dict[str, Any]:
        selected_option = flight_search.get("selected_option") if isinstance(flight_search.get("selected_option"), dict) else {}
        selected_calendar_pick = (
            flight_search.get("selected_calendar_pick") if isinstance(flight_search.get("selected_calendar_pick"), dict) else {}
        )
        tool_calls = flight_search.get("tool_calls") if isinstance(flight_search.get("tool_calls"), list) else []
        return {
            "strategy": flight_search.get("strategy") or "",
            "tool_names": [
                call.get("name")
                for call in tool_calls
                if isinstance(call, dict) and call.get("name")
            ],
            "option_count": len(flight_search.get("options") or []) if isinstance(flight_search.get("options"), list) else 0,
            "selected_departure_date": selected_calendar_pick.get("departure_date")
            or selected_option.get("departure_date")
            or "",
            "selected_return_date": selected_calendar_pick.get("return_date") or selected_option.get("arrival_date") or "",
            "selected_price": selected_option.get("price") or selected_calendar_pick.get("price"),
            "selected_currency": selected_option.get("currency") or selected_calendar_pick.get("currency") or "",
        }

    @staticmethod
    def _choose_best_calendar_pick(calendar_rows: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        priced = [
            row
            for row in calendar_rows
            if isinstance(row, dict) and isinstance(row.get("price"), (int, float))
        ]
        if not priced:
            return calendar_rows[0] if calendar_rows else None
        return sorted(
            priced,
            key=lambda row: (
                float(row.get("price")),
                int(row.get("total_duration_minutes") or 10**9),
            ),
        )[0]

    @staticmethod
    def _best_exact_option(options: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        priced = [
            option
            for option in options
            if isinstance(option, dict) and isinstance(option.get("price"), (int, float))
        ]
        return priced[0] if priced else (options[0] if options else None)

    @staticmethod
    def _calendar_pick_as_option(trip_state: Dict[str, Any], pick: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not pick:
            return None
        return {
            "id": "calendar-pick",
            "airline": pick.get("airline") or "Calendar price candidate",
            "price": pick.get("price"),
            "currency": pick.get("currency") or trip_state.get("budget_currency") or "USD",
            "origin": str(trip_state.get("origin") or "").upper(),
            "destination": str(trip_state.get("destination") or "").upper(),
            "departure_date": pick.get("departure_date") or "",
            "arrival_date": pick.get("return_date") or "",
            "duration_minutes": pick.get("total_duration_minutes"),
            "stops": pick.get("stops") if isinstance(pick.get("stops"), int) else 0,
            "segments": [],
        }

    @staticmethod
    def _same_route_endpoint(trip_state: Dict[str, Any]) -> bool:
        origin = RapidApiFlightsClient._location_id(trip_state.get("origin"))
        destination = RapidApiFlightsClient._location_id(trip_state.get("destination"))
        return bool(origin and destination and origin == destination)

    @staticmethod
    def _trip_state_for_calendar_pick(trip_state: Dict[str, Any], pick: Dict[str, Any] | None) -> Dict[str, Any]:
        if not pick:
            return trip_state
        next_state = dict(trip_state)
        if pick.get("departure_date"):
            next_state["start_date"] = pick["departure_date"]
        if pick.get("return_date"):
            next_state["end_date"] = pick["return_date"]
        elif pick.get("arrival_date"):
            next_state["end_date"] = pick["arrival_date"]
        elif pick.get("departure_date") and isinstance(trip_state.get("duration_days"), int):
            try:
                departure = datetime.strptime(str(pick["departure_date"]), "%Y-%m-%d")
                next_state["end_date"] = (departure + timedelta(days=int(trip_state["duration_days"]))).strftime("%Y-%m-%d")
            except Exception:
                pass
        return next_state

    def run(self, trip_state: Dict[str, Any]) -> Dict[str, Any]:
        if not has_flight_inputs(trip_state):
            flight_search = {
                "status": "skipped",
                "message": "Flight Desk Agent skipped: origin, destination, and an outbound date or date window are required for live flight search.",
                "strategy": "skipped_missing_inputs",
                "reasoning": "The calendar_tool requires origin, destination, and an outbound date or date window. The flight_list_tool requires exact selected dates.",
                "calendar": [],
                "options": [],
            }
            return {
                "status": "skipped",
                "message": flight_search["message"],
                "trip_state": apply_trip_patch(trip_state, {"flight_search": flight_search}),
                "details": self._flight_details(flight_search),
            }

        if self._same_route_endpoint(trip_state):
            flight_search = {
                "status": "skipped",
                "message": "Flight Desk Agent skipped: origin and destination resolve to the same airport.",
                "strategy": "skipped_same_origin_destination",
                "reasoning": "Flight tools require different origin and destination airports. The itinerary can still be generated as a local trip.",
                "calendar": [],
                "options": [],
            }
            return {
                "status": "skipped",
                "message": flight_search["message"],
                "trip_state": apply_trip_patch(trip_state, {"flight_search": flight_search}),
                "details": self._flight_details(flight_search),
            }

        try:
            if self._wants_calendar_reasoning(trip_state):
                calendar_result = self.flights_client.calendar_tool(trip_state)
                best_pick = self._choose_best_calendar_pick(calendar_result.get("calendar", []))
                if not best_pick:
                    flight_search = {
                        "status": "skipped",
                        "message": "Flight Desk Agent found no normalized calendar prices for the requested route and window.",
                        "strategy": "calendar_no_price_rows",
                        "reasoning": calendar_result.get("reasoning")
                        or "calendar_tool returned no normalized price rows, so exact flight cards were not requested.",
                        "calendar": calendar_result.get("calendar", []),
                        "selected_calendar_pick": None,
                        "selected_option": None,
                        "options": [],
                        "tool_calls": [calendar_result.get("tool_call", {"name": "calendar_tool"})],
                    }
                    return {
                        "status": "skipped",
                        "message": flight_search["message"],
                        "trip_state": apply_trip_patch(trip_state, {"flight_search": flight_search}),
                        "details": self._flight_details(flight_search),
                    }
                exact_state = self._trip_state_for_calendar_pick(trip_state, best_pick)
                exact_options: List[Dict[str, Any]] = []
                best_exact_option: Dict[str, Any] | None = None
                list_result: Dict[str, Any] | None = None
                try:
                    list_result = self.flights_client.flight_list_tool(exact_state)
                    exact_options = list_result.get("options", [])
                    best_exact_option = self._best_exact_option(exact_options)
                except RapidApiTimeoutError:
                    best_exact_option = self._calendar_pick_as_option(exact_state, best_pick)
                    exact_options = [best_exact_option] if best_exact_option else []
                    list_result = {"tool_call": {"name": "flight_list_tool", "timed_out": True}}
                if not exact_options:
                    state_updates = {
                        "flight_search": {},
                        "start_date": exact_state.get("start_date") or trip_state.get("start_date") or "",
                        "end_date": exact_state.get("end_date") or trip_state.get("end_date") or "",
                    }
                    flight_search = {
                        "status": "skipped",
                        "message": "Flight Desk Agent selected calendar dates, but exact flight cards were not available.",
                        "strategy": "flight_list_no_options",
                        "reasoning": (
                            f"{calendar_result.get('reasoning') or 'Calendar prices were ranked by lowest fare.'} "
                            "flight_list_tool returned no normalized exact flight cards for the selected dates."
                        ),
                        "calendar": calendar_result.get("calendar", []),
                        "selected_calendar_pick": best_pick,
                        "selected_option": None,
                        "options": [],
                            "tool_calls": [
                                calendar_result.get("tool_call", {"name": "calendar_tool"}),
                            (list_result or {}).get("tool_call", {"name": "flight_list_tool"}),
                            ],
                        }
                    state_updates["flight_search"] = flight_search
                    return {
                        "status": "skipped",
                        "message": flight_search["message"],
                        "trip_state": apply_trip_patch(trip_state, state_updates),
                        "details": self._flight_details(flight_search),
                    }
                state_updates = {
                    "flight_search": {},
                    "start_date": exact_state.get("start_date") or trip_state.get("start_date") or "",
                    "end_date": exact_state.get("end_date") or trip_state.get("end_date") or "",
                }
                flight_search = {
                    "status": "done",
                    "message": "Flight Desk Agent used calendar_tool to choose cheaper trip dates, then flight_list_tool for exact options.",
                    "strategy": "calendar_then_flight_list",
                    "reasoning": (
                        f"{calendar_result.get('reasoning') or 'Calendar prices were ranked by lowest fare before fetching exact flights.'} "
                        "Exact flight cards are sorted by lowest price, then shorter duration, then fewer stops."
                    ),
                    "calendar": calendar_result.get("calendar", []),
                    "selected_calendar_pick": best_pick,
                    "selected_option": best_exact_option,
                    "options": exact_options,
                    "tool_calls": [
                        calendar_result.get("tool_call", {"name": "calendar_tool"}),
                        (list_result or {}).get("tool_call", {"name": "flight_list_tool"}),
                    ],
                }
            else:
                list_result = self.flights_client.flight_list_tool(trip_state)
                exact_options = list_result.get("options", [])
                state_updates = {"flight_search": {}}
                if not exact_options:
                    flight_search = {
                        "status": "skipped",
                        "message": "Flight Desk Agent found no normalized exact flight cards for the requested dates.",
                        "strategy": "flight_list_no_options",
                        "reasoning": "flight_list_tool completed but returned no normalized flight cards for this route and date selection.",
                        "calendar": [],
                        "selected_option": None,
                        "options": [],
                        "tool_calls": [list_result.get("tool_call", {"name": "flight_list_tool"})],
                    }
                    state_updates["flight_search"] = flight_search
                    return {
                        "status": "skipped",
                        "message": flight_search["message"],
                        "trip_state": apply_trip_patch(trip_state, state_updates),
                        "details": self._flight_details(flight_search),
                    }
                flight_search = {
                    "status": "done",
                    "message": "Flight Desk Agent used flight_list_tool for the exact requested dates.",
                    "strategy": "flight_list_only",
                    "reasoning": "The request did not indicate date flexibility, so no calendar scan was needed. Exact flight cards are sorted by lowest price, then shorter duration, then fewer stops.",
                    "calendar": [],
                    "selected_option": self._best_exact_option(exact_options),
                    "options": exact_options,
                    "tool_calls": [list_result.get("tool_call", {"name": "flight_list_tool"})],
                }
        except RapidApiConfigurationError as exc:
            flight_search = {
                "status": "skipped",
                "message": str(exc),
                "strategy": "skipped_missing_rapidapi_key",
                "reasoning": "Flight reasoning is disabled because RAPIDAPI_KEY is not configured.",
                "calendar": [],
                "options": [],
            }
            return {
                "status": "skipped",
                "message": flight_search["message"],
                "trip_state": apply_trip_patch(trip_state, {"flight_search": flight_search}),
                "details": self._flight_details(flight_search),
            }
        except RapidApiTimeoutError as exc:
            flight_search = {
                "status": "skipped",
                "message": "Flight Desk Agent skipped live flights because RapidAPI timed out.",
                "strategy": "skipped_tool_timeout",
                "reasoning": f"{exc} The itinerary can still be generated from destination and date context.",
                "calendar": [],
                "options": [],
            }
            return {
                "status": "skipped",
                "message": flight_search["message"],
                "trip_state": apply_trip_patch(trip_state, {"flight_search": flight_search}),
                "details": {**self._flight_details(flight_search), "error": str(exc)},
            }
        except Exception as exc:
            flight_search = {
                "status": "error",
                "message": f"Flight search unavailable: {exc}",
                "strategy": "tool_error",
                "reasoning": "A flight tool failed; the itinerary can still be generated from destination and date context.",
                "calendar": [],
                "options": [],
            }
            return {
                "status": "error",
                "message": flight_search["message"],
                "trip_state": apply_trip_patch(trip_state, {"flight_search": flight_search}),
                "details": {**self._flight_details(flight_search), "error": str(exc)},
            }

        state_updates["flight_search"] = flight_search
        return {
            "status": "done",
            "message": flight_search.get("message") or "Flight Desk Agent found flight options.",
            "trip_state": apply_trip_patch(trip_state, state_updates),
            "details": self._flight_details(flight_search),
        }
