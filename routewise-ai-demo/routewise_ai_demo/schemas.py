from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Tuple
from uuid import uuid4


AGENTS = (
    {"id": "central_agent", "label": "Central Agent"},
    {"id": "flight_desk_agent", "label": "Flight Desk Agent"},
    {"id": "day_plan_agent", "label": "Day Plan Agent"},
    {"id": "edit_agent", "label": "Edit Agent"},
)

MAX_MESSAGE_CHARS = 4000
MAX_LIST_ITEMS = 12
MAX_LIST_ITEM_CHARS = 80
ALLOWED_PACES = {"relaxed", "balanced", "packed"}
ALLOWED_FLIGHT_PRIORITIES = {"cheap", "fast", "balanced"}
ALLOWED_CABIN_CLASSES = {1, 2, 3, 4}
LOCATION_ALIASES = {
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

DEFAULT_TRIP_STATE: Dict[str, Any] = {
    "title": "",
    "summary": "",
    "origin": "",
    "destination": "",
    "start_date": "",
    "end_date": "",
    "duration_days": None,
    "travelers": 1,
    "interests": [],
    "planning_facts": [],
    "budget": None,
    "budget_currency": "USD",
    "pace": "balanced",
    "flight_preferences": {
        "priority": "balanced",
        "flexible_dates": False,
        "flex_window_days": 3,
        "date_window_start": "",
        "date_window_end": "",
        "max_stops": None,
        "cabin_class": None,
    },
    "flight_search": {
        "status": "idle",
        "message": "",
        "strategy": "idle",
        "reasoning": "",
        "calendar": [],
        "options": [],
    },
    "hotel_suggestions": [],
    "place_shortlist": [],
    "itinerary": [],
    "budget_notes": "",
    "last_edit_summary": "",
}


def new_session_id() -> str:
    return str(uuid4())


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def validate_message_payload(payload: Dict[str, Any] | None) -> Tuple[str, Dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return "", None, "JSON body is required"

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return "", None, "message is required"
    if len(message) > MAX_MESSAGE_CHARS:
        return "", None, f"message must be {MAX_MESSAGE_CHARS} characters or fewer"

    trip_state = payload.get("trip_state")
    if trip_state is not None and not isinstance(trip_state, dict):
        return "", None, "trip_state must be an object when provided"

    return message.strip(), trip_state, None


def _clean_text(value: Any, *, max_chars: int = MAX_LIST_ITEM_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:max_chars]


def _clean_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_text(item)
        key = text.lower()
        if not text or key in seen:
            continue
        cleaned.append(text)
        seen.add(key)
        if len(cleaned) >= MAX_LIST_ITEMS:
            break
    return cleaned


def _clean_named_items(value: Any, *, max_items: int = 12) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    cleaned: List[Dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        row = {
            "name": _clean_text(item.get("name"), max_chars=120),
            "area": _clean_text(item.get("area"), max_chars=100),
            "type": _clean_text(item.get("type"), max_chars=80),
            "why": _clean_text(item.get("why"), max_chars=240),
            "budget_level": _clean_text(item.get("budget_level"), max_chars=80),
        }
        if not row["name"]:
            continue
        cleaned.append(row)
        if len(cleaned) >= max_items:
            break
    return cleaned


def _parse_iso_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except Exception:
        return None


def _iso_date_or_empty(value: Any) -> str:
    parsed = _parse_iso_date(value)
    return parsed.strftime("%Y-%m-%d") if parsed else ""


def _canonical_location(value: Any) -> str:
    text = _clean_text(value, max_chars=80).upper()
    compact = " ".join(text.replace(",", " ").split())
    return LOCATION_ALIASES.get(compact, compact)


def _bounded_int(value: Any, *, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return max(minimum, min(maximum, parsed))


def _bounded_number(value: Any, *, minimum: float, maximum: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    return max(minimum, min(maximum, parsed))


def coerce_trip_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    state = deepcopy(DEFAULT_TRIP_STATE)
    if not isinstance(value, dict):
        return state

    for key, default_value in DEFAULT_TRIP_STATE.items():
        if key not in value:
            continue
        if isinstance(default_value, dict) and isinstance(value[key], dict):
            merged = deepcopy(default_value)
            merged.update(value[key])
            state[key] = merged
        else:
            state[key] = value[key]

    if not isinstance(state.get("interests"), list):
        state["interests"] = []
    state["interests"] = _clean_string_list(state.get("interests"))
    if not isinstance(state.get("planning_facts"), list):
        state["planning_facts"] = []
    state["planning_facts"] = _clean_string_list(state.get("planning_facts"))
    if not isinstance(state.get("itinerary"), list):
        state["itinerary"] = []
    state["hotel_suggestions"] = _clean_named_items(state.get("hotel_suggestions"), max_items=5)
    state["place_shortlist"] = _clean_named_items(state.get("place_shortlist"), max_items=12)
    if not isinstance(state.get("flight_search"), dict):
        state["flight_search"] = deepcopy(DEFAULT_TRIP_STATE["flight_search"])
    if not isinstance(state["flight_search"].get("options"), list):
        state["flight_search"]["options"] = []
    if not isinstance(state["flight_search"].get("calendar"), list):
        state["flight_search"]["calendar"] = []
    if not isinstance(state.get("flight_preferences"), dict):
        state["flight_preferences"] = deepcopy(DEFAULT_TRIP_STATE["flight_preferences"])

    state["title"] = _clean_text(state.get("title"), max_chars=120)
    state["summary"] = _clean_text(state.get("summary"), max_chars=500)
    state["origin"] = _clean_text(state.get("origin"), max_chars=60).upper()
    state["destination"] = _clean_text(state.get("destination"), max_chars=80).upper()
    if state["origin"] and state["destination"] and _canonical_location(state["origin"]) == _canonical_location(state["destination"]):
        state["origin"] = ""
    state["start_date"] = _iso_date_or_empty(state.get("start_date"))
    state["end_date"] = _iso_date_or_empty(state.get("end_date"))
    state["duration_days"] = _bounded_int(state.get("duration_days"), minimum=1, maximum=30)
    state["travelers"] = _bounded_int(state.get("travelers"), minimum=1, maximum=12) or 1
    budget = _bounded_number(state.get("budget"), minimum=0, maximum=1_000_000)
    state["budget"] = budget if budget and budget > 0 else None
    state["budget_currency"] = (_clean_text(state.get("budget_currency"), max_chars=8) or "USD").upper()
    if state.get("pace") not in ALLOWED_PACES:
        state["pace"] = DEFAULT_TRIP_STATE["pace"]

    preferences = deepcopy(DEFAULT_TRIP_STATE["flight_preferences"])
    preferences.update(state.get("flight_preferences") if isinstance(state.get("flight_preferences"), dict) else {})
    if preferences.get("priority") not in ALLOWED_FLIGHT_PRIORITIES:
        preferences["priority"] = DEFAULT_TRIP_STATE["flight_preferences"]["priority"]
    preferences["flexible_dates"] = bool(preferences.get("flexible_dates"))
    preferences["flex_window_days"] = _bounded_int(preferences.get("flex_window_days"), minimum=0, maximum=14) or 3
    preferences["date_window_start"] = _iso_date_or_empty(preferences.get("date_window_start"))
    preferences["date_window_end"] = _iso_date_or_empty(preferences.get("date_window_end"))
    start_window = _parse_iso_date(preferences["date_window_start"])
    end_window = _parse_iso_date(preferences["date_window_end"])
    if start_window and end_window and end_window < start_window:
        preferences["date_window_start"] = ""
        preferences["date_window_end"] = ""
    preferences["max_stops"] = _bounded_int(preferences.get("max_stops"), minimum=0, maximum=2)
    try:
        cabin_class = int(preferences.get("cabin_class"))
    except Exception:
        cabin_class = None
    preferences["cabin_class"] = cabin_class if cabin_class in ALLOWED_CABIN_CLASSES else None
    state["flight_preferences"] = preferences

    return state


def apply_trip_patch(state: Dict[str, Any], patch: Dict[str, Any] | None) -> Dict[str, Any]:
    next_state = coerce_trip_state(state)
    if not isinstance(patch, dict):
        return next_state

    for key, value in patch.items():
        if key not in DEFAULT_TRIP_STATE:
            continue
        if isinstance(DEFAULT_TRIP_STATE[key], dict) and isinstance(value, dict):
            merged = deepcopy(next_state.get(key) or {})
            merged.update(value)
            next_state[key] = merged
        else:
            next_state[key] = value

    return coerce_trip_state(next_state)


def blocking_missing_fields(state: Dict[str, Any], missing_fields: List[str] | None = None) -> List[str]:
    requested = {item for item in (missing_fields or []) if isinstance(item, str) and item}
    missing: List[str] = []
    if not state.get("destination"):
        missing.append("destination")
    if not (state.get("start_date") or state.get("duration_days")):
        missing.append("dates_or_duration")
    if (state.get("destination") or "origin" in requested) and not state.get("origin"):
        missing.append("origin")
    return missing


def has_day_plan_inputs(state: Dict[str, Any]) -> bool:
    return bool(state.get("destination") and (state.get("start_date") or state.get("duration_days")))


def has_flight_inputs(state: Dict[str, Any]) -> bool:
    preferences = state.get("flight_preferences") if isinstance(state.get("flight_preferences"), dict) else {}
    has_outbound_date = bool(state.get("start_date") or preferences.get("date_window_start"))
    return bool(state.get("origin") and state.get("destination") and has_outbound_date)


def agent_trace_event(
    agent_id: str,
    status: str,
    message: str,
    *,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "agent_id": agent_id,
        "status": status,
        "message": message,
        "details": details or {},
        "ts": now_iso(),
    }
