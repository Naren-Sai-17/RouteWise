from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List


RAPIDAPI_HOST = "flights-search3.p.rapidapi.com"
CITY_AIRPORT_CODES = {
    "AHMEDABAD": "AMD",
    "BANGALORE": "BLR",
    "BENGALURU": "BLR",
    "CHENNAI": "MAA",
    "DELHI": "DEL",
    "GOA": "GOI",
    "HYDERABAD": "HYD",
    "INDORE": "IDR",
    "JAIPUR": "JAI",
    "KOCHI": "COK",
    "KOLKATA": "CCU",
    "MUMBAI": "BOM",
    "NEW DELHI": "DEL",
    "PUNE": "PNQ",
    "TOKYO": "TYO",
}


class RapidApiConfigurationError(RuntimeError):
    pass


class RapidApiTimeoutError(RuntimeError):
    pass


class RapidApiFlightsClient:
    def __init__(self, *, timeout_seconds: int | None = None):
        configured_timeout = os.environ.get("RAPIDAPI_TIMEOUT_SECONDS")
        try:
            parsed_timeout = int(configured_timeout) if configured_timeout else None
        except Exception:
            parsed_timeout = None
        self.timeout_seconds = timeout_seconds or parsed_timeout or 8
        self.api_key = os.environ.get("RAPIDAPI_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _require_configured(self) -> None:
        if not self.api_key:
            raise RapidApiConfigurationError("RAPIDAPI_KEY is not configured for flight search.")

    def _get_json(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._require_configured()
        url = f"https://{RAPIDAPI_HOST}/{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "X-RapidAPI-Key": str(self.api_key),
                "X-RapidAPI-Host": RAPIDAPI_HOST,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=ssl._create_unverified_context(),
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"RapidAPI tool error {exc.code}: {error_body}") from exc
        except TimeoutError as exc:
            raise RapidApiTimeoutError(f"RapidAPI tool timed out after {self.timeout_seconds}s.") from exc
        except Exception as exc:
            if "timed out" in str(exc).lower():
                raise RapidApiTimeoutError(f"RapidAPI tool timed out after {self.timeout_seconds}s.") from exc
            raise RuntimeError(f"RapidAPI tool failed: {exc}") from exc

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d")
        except Exception:
            return None

    @staticmethod
    def _date_string(value: datetime) -> str:
        return value.strftime("%Y-%m-%d")

    @classmethod
    def _calendar_window(cls, trip_state: Dict[str, Any]) -> tuple[str, str]:
        preferences = trip_state.get("flight_preferences") if isinstance(trip_state.get("flight_preferences"), dict) else {}
        explicit_start = cls._parse_date(preferences.get("date_window_start"))
        explicit_end = cls._parse_date(preferences.get("date_window_end"))
        if explicit_start and explicit_end and explicit_end >= explicit_start:
            return cls._date_string(explicit_start), cls._date_string(explicit_end)

        start = cls._parse_date(trip_state.get("start_date")) or explicit_start or datetime.utcnow()
        raw_window = preferences.get("flex_window_days", 3)
        try:
            window_days = max(0, min(int(raw_window), 14))
        except Exception:
            window_days = 3
        lower = start - timedelta(days=window_days)
        upper = start + timedelta(days=window_days)
        return cls._date_string(lower), cls._date_string(upper)

    @classmethod
    def _trip_duration_days(cls, trip_state: Dict[str, Any]) -> int | None:
        if isinstance(trip_state.get("duration_days"), int) and trip_state["duration_days"] > 0:
            return int(trip_state["duration_days"])
        start = cls._parse_date(trip_state.get("start_date"))
        end = cls._parse_date(trip_state.get("end_date"))
        if start and end and end > start:
            return (end - start).days
        return None

    @staticmethod
    def _airport_code(value: Any) -> str:
        if isinstance(value, str):
            return value.upper()
        if isinstance(value, dict):
            return str(value.get("code") or value.get("id") or value.get("name") or "").upper()
        return ""

    @staticmethod
    def _location_id(value: Any) -> str:
        raw = str(value or "").strip().upper()
        compact = " ".join(raw.replace(",", " ").split())
        return CITY_AIRPORT_CODES.get(compact, compact)

    @classmethod
    def _normalize_segment(cls, segment: Dict[str, Any]) -> Dict[str, Any]:
        departure = segment.get("departure_airport") or segment.get("from") or segment.get("departure") or {}
        arrival = segment.get("arrival_airport") or segment.get("to") or segment.get("arrival") or {}
        return {
            "from": cls._airport_code(departure),
            "to": cls._airport_code(arrival),
            "airline": segment.get("airline") or segment.get("airline_name") or segment.get("carrier") or "",
            "flight_number": segment.get("flight_number") or segment.get("flight") or "",
            "departure_time": segment.get("departure_time") or segment.get("departureTime") or "",
            "arrival_time": segment.get("arrival_time") or segment.get("arrivalTime") or "",
        }

    @staticmethod
    def _first_number(*values: Any) -> float | None:
        for value in values:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                cleaned = value.replace("$", "").replace(",", "").strip()
                try:
                    return float(cleaned)
                except Exception:
                    continue
            if isinstance(value, dict):
                nested = RapidApiFlightsClient._first_number(
                    value.get("amount"),
                    value.get("total"),
                    value.get("value"),
                )
                if nested is not None:
                    return nested
        return None

    @staticmethod
    def _preferences(trip_state: Dict[str, Any]) -> Dict[str, Any]:
        return trip_state.get("flight_preferences") if isinstance(trip_state.get("flight_preferences"), dict) else {}

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _rapidapi_stops_value(max_stops: int | None) -> int:
        # RapidAPI uses 0 for any, 1 for nonstop, 2 for <=1 stop, 3 for <=2 stops.
        if max_stops is None:
            return 0
        if max_stops == 0:
            return 1
        if max_stops == 1:
            return 2
        if max_stops == 2:
            return 3
        return 0

    @staticmethod
    def _rank_key(item: Dict[str, Any]) -> tuple[float, float, int]:
        price = item.get("price")
        duration = item.get("duration_minutes") or item.get("total_duration_minutes")
        stops = item.get("stops")
        price_rank = float(price) if isinstance(price, (int, float)) else 10**9
        duration_rank = float(duration) if isinstance(duration, (int, float)) else 10**9
        stops_rank = int(stops) if isinstance(stops, int) else 99
        return price_rank, duration_rank, stops_rank

    @classmethod
    def _normalize_flight(cls, item: Dict[str, Any], trip_state: Dict[str, Any]) -> Dict[str, Any]:
        price = cls._first_number(item.get("price"), item.get("total_price"), item.get("cost"))
        segments_raw = item.get("segments") or item.get("flights") or item.get("legs") or []
        segments = [
            cls._normalize_segment(segment)
            for segment in segments_raw
            if isinstance(segment, dict)
        ][:4]
        airlines = item.get("airlines")
        if isinstance(airlines, list):
            airline_label = ", ".join(str(airline.get("name") if isinstance(airline, dict) else airline) for airline in airlines[:2])
        else:
            airline_label = str(item.get("airline") or item.get("airline_name") or "")
        return {
            "id": str(item.get("id") or item.get("token") or item.get("booking_token") or ""),
            "airline": airline_label,
            "price": price,
            "currency": item.get("currency") or trip_state.get("budget_currency") or "USD",
            "origin": cls._airport_code(item.get("origin")) or str(trip_state.get("origin") or "").upper(),
            "destination": cls._airport_code(item.get("destination")) or str(trip_state.get("destination") or "").upper(),
            "departure_date": item.get("departure_date") or item.get("departureDate") or trip_state.get("start_date") or "",
            "arrival_date": item.get("arrival_date") or item.get("arrivalDate") or trip_state.get("end_date") or "",
            "duration_minutes": cls._first_number(item.get("total_duration_minutes"), item.get("duration_minutes"), item.get("duration")),
            "stops": item.get("stops") if isinstance(item.get("stops"), int) else max(0, len(segments) - 1),
            "segments": segments,
        }

    @classmethod
    def _collect_dict_lists(cls, value: Any, output: List[Dict[str, Any]]) -> None:
        if isinstance(value, list):
            dict_items = [item for item in value if isinstance(item, dict)]
            if dict_items and any(("price" in item or "segments" in item or "flights" in item) for item in dict_items):
                output.extend(dict_items)
            for item in dict_items:
                cls._collect_dict_lists(item, output)
        elif isinstance(value, dict):
            for nested in value.values():
                cls._collect_dict_lists(nested, output)

    def _normalize_response(self, raw: Dict[str, Any], trip_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        self._collect_dict_lists(raw, candidates)
        normalized: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            flight = self._normalize_flight(item, trip_state)
            marker = json.dumps(flight, sort_keys=True)
            if marker in seen:
                continue
            seen.add(marker)
            normalized.append(flight)
        return sorted(normalized, key=self._rank_key)[:5]

    @classmethod
    def _normalize_calendar_item(cls, item: Dict[str, Any], trip_state: Dict[str, Any]) -> Dict[str, Any]:
        departure_date = (
            item.get("departure_date")
            or item.get("departureDate")
            or item.get("date")
            or item.get("startDate")
            or trip_state.get("start_date")
            or ""
        )
        return_date = (
            item.get("return_date")
            or item.get("arrival_date")
            or item.get("arrivalDate")
            or item.get("endDate")
            or ""
        )
        return {
            "departure_date": departure_date,
            "return_date": return_date,
            "price": cls._first_number(item.get("price"), item.get("total_price"), item.get("cost")),
            "currency": item.get("currency") or trip_state.get("budget_currency") or "USD",
            "airline": item.get("airline") or item.get("airline_name") or "",
            "stops": item.get("stops") if isinstance(item.get("stops"), int) else None,
            "total_duration_minutes": cls._first_number(
                item.get("total_duration_minutes"),
                item.get("duration_minutes"),
                item.get("duration"),
            ),
        }

    @classmethod
    def _collect_calendar_candidates(cls, value: Any, output: List[Dict[str, Any]]) -> None:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    if cls._first_number(item.get("price"), item.get("total_price"), item.get("cost")) is not None:
                        output.append(item)
                    cls._collect_calendar_candidates(item, output)
        elif isinstance(value, dict):
            for nested in value.values():
                cls._collect_calendar_candidates(nested, output)

    def _normalize_calendar_response(self, raw: Dict[str, Any], trip_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        self._collect_calendar_candidates(raw, candidates)
        normalized: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            row = self._normalize_calendar_item(item, trip_state)
            if not row.get("departure_date") or row.get("price") is None:
                continue
            marker = json.dumps(row, sort_keys=True)
            if marker in seen:
                continue
            seen.add(marker)
            normalized.append(row)
        return sorted(
            normalized,
            key=lambda row: (
                float(row.get("price") if isinstance(row.get("price"), (int, float)) else 10**9),
                str(row.get("departure_date") or ""),
            ),
        )[:8]

    def calendar_tool(self, trip_state: Dict[str, Any]) -> Dict[str, Any]:
        start_date, end_date = self._calendar_window(trip_state)
        duration_days = self._trip_duration_days(trip_state)
        preferences = self._preferences(trip_state)
        cabin_class = self._optional_int(preferences.get("cabin_class"))
        roundtrip = bool(duration_days)
        endpoint = "google/price-calendar/for-roundtrip" if roundtrip else "google/price-calendar/for-one-way"
        params: Dict[str, Any] = {
            "departureId": self._location_id(trip_state.get("origin")),
            "arrivalId": self._location_id(trip_state.get("destination")),
            "departureDate": trip_state.get("start_date") or start_date,
            "startDate": start_date,
            "endDate": end_date,
            "currency": trip_state.get("budget_currency") or "USD",
            "adults": int(trip_state.get("travelers") or 1),
        }
        if cabin_class is not None:
            params["cabinClass"] = cabin_class
        if roundtrip:
            start = self._parse_date(trip_state.get("start_date")) or self._parse_date(start_date)
            anchor = start + timedelta(days=duration_days) if start else None
            params["arrivalDate"] = self._date_string(anchor) if anchor else trip_state.get("end_date")
            params["daysBetween"] = duration_days

        raw = self._get_json(endpoint, params)
        calendar = self._normalize_calendar_response(raw, trip_state)
        if calendar:
            cheapest = calendar[0]
            reasoning = (
                f"calendar_tool scanned {start_date} to {end_date}; "
                f"cheapest normalized candidate is {cheapest.get('departure_date')} "
                f"at {cheapest.get('currency', 'USD')} {cheapest.get('price')}."
            )
        else:
            reasoning = f"calendar_tool scanned {start_date} to {end_date} but found no normalized price rows."
        return {
            "tool_call": {
                "name": "calendar_tool",
                "endpoint": endpoint,
                "args": params,
            },
            "calendar": calendar,
            "reasoning": reasoning,
        }

    def flight_list_tool(self, trip_state: Dict[str, Any]) -> Dict[str, Any]:
        roundtrip = bool(trip_state.get("end_date"))
        preferences = self._preferences(trip_state)
        max_stops = self._optional_int(preferences.get("max_stops"))
        cabin_class = self._optional_int(preferences.get("cabin_class"))
        endpoint = "google/flights/search-roundtrip" if roundtrip else "google/flights/search-one-way"
        params: Dict[str, Any] = {
            "departureId": self._location_id(trip_state.get("origin")),
            "arrivalId": self._location_id(trip_state.get("destination")),
            "departureDate": trip_state.get("start_date"),
            "currency": trip_state.get("budget_currency") or "USD",
            "adults": int(trip_state.get("travelers") or 1),
            "children": 0,
            "infantsInSeat": 0,
            "infantsOnLap": 0,
            "stops": self._rapidapi_stops_value(max_stops),
        }
        if roundtrip:
            params["arrivalDate"] = trip_state.get("end_date")
        if cabin_class is not None:
            params["cabinClass"] = cabin_class

        raw = self._get_json(endpoint, params)

        return {
            "tool_call": {
                "name": "flight_list_tool",
                "endpoint": endpoint,
                "args": params,
            },
            "options": self._normalize_response(raw, trip_state),
            "raw_result_count": len(raw) if isinstance(raw, list) else None,
        }

    def search_flights(self, trip_state: Dict[str, Any]) -> Dict[str, Any]:
        result = self.flight_list_tool(trip_state)
        return {
            "status": "done",
            "message": "flight_list_tool completed with RapidAPI.",
            "strategy": "flight_list_only",
            "reasoning": "Compatibility wrapper around flight_list_tool.",
            "calendar": [],
            "options": result.get("options", []),
            "tool_calls": [result.get("tool_call")],
        }
