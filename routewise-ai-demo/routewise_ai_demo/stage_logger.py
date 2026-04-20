from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from routewise_ai_demo.schemas import now_iso


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = ROOT / "logs" / "sessions"


def _safe_file_part(value: str, fallback: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value or ""))
    return cleaned.strip("._") or fallback


def _log_dir() -> Path:
    configured = os.environ.get("ROUTEWISE_STAGE_LOG_DIR")
    if configured:
        return Path(configured).expanduser()

    legacy_path = os.environ.get("ROUTEWISE_STAGE_LOG_PATH")
    if legacy_path:
        path = Path(legacy_path).expanduser()
        return path.parent / path.stem if path.suffix else path

    return DEFAULT_LOG_DIR


def _log_path(session_id: str, stage: str) -> Path:
    session_part = _safe_file_part(session_id, "unknown_session")
    stage_part = _safe_file_part(stage, "stage")
    return _log_dir() / session_part / f"{stage_part}.jsonl"


def _state_summary(state: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    flight_search = state.get("flight_search") if isinstance(state.get("flight_search"), dict) else {}
    preferences = state.get("flight_preferences") if isinstance(state.get("flight_preferences"), dict) else {}
    return {
        "origin": state.get("origin") or "",
        "destination": state.get("destination") or "",
        "start_date": state.get("start_date") or "",
        "end_date": state.get("end_date") or "",
        "duration_days": state.get("duration_days"),
        "travelers": state.get("travelers"),
        "interests": state.get("interests") if isinstance(state.get("interests"), list) else [],
        "planning_facts": state.get("planning_facts") if isinstance(state.get("planning_facts"), list) else [],
        "flight_priority": preferences.get("priority") or "",
        "flexible_dates": bool(preferences.get("flexible_dates")),
        "date_window_start": preferences.get("date_window_start") or "",
        "date_window_end": preferences.get("date_window_end") or "",
        "flight_strategy": flight_search.get("strategy") or "",
        "flight_status": flight_search.get("status") or "",
        "flight_option_count": len(flight_search.get("options") or []) if isinstance(flight_search.get("options"), list) else 0,
        "itinerary_days": len(state.get("itinerary") or []) if isinstance(state.get("itinerary"), list) else 0,
    }


def append_stage_log(
    *,
    session_id: str,
    stage: str,
    status: str,
    message: str,
    state: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": now_iso(),
        "session_id": session_id,
        "stage": stage,
        "status": status,
        "message": message,
        "state": _state_summary(state),
        "details": details or {},
    }
    try:
        path = _log_path(session_id, stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, ensure_ascii=True, sort_keys=True) + "\n")
    except Exception:
        # Logging is observational and must never break the demo request path.
        return
