from __future__ import annotations

from typing import Any, Dict, List

from routewise_ai_demo.agents.central_agent import CentralAgent
from routewise_ai_demo.agents.day_plan_agent import DayPlanAgent
from routewise_ai_demo.agents.edit_agent import EditAgent
from routewise_ai_demo.agents.flight_desk_agent import FlightDeskAgent
from routewise_ai_demo.schemas import (
    agent_trace_event,
    coerce_trip_state,
    has_day_plan_inputs,
    new_session_id,
)
from routewise_ai_demo.services import GroqClient, RapidApiFlightsClient
from routewise_ai_demo.stage_logger import append_stage_log


class RouteWiseDemoOrchestrator:
    def __init__(self, *, groq_client: Any | None = None, flights_client: Any | None = None):
        self.groq_client = groq_client or GroqClient()
        self.flights_client = flights_client or RapidApiFlightsClient()
        self.central_agent = CentralAgent(self.groq_client)
        self.flight_desk_agent = FlightDeskAgent(self.flights_client)
        self.day_plan_agent = DayPlanAgent(self.groq_client)
        self.edit_agent = EditAgent(self.groq_client)

    def handle_message(
        self,
        *,
        message: str,
        trip_state: Dict[str, Any] | None,
        session_id: str | None,
    ) -> Dict[str, Any]:
        request_session_id = session_id or new_session_id()
        state = coerce_trip_state(trip_state)
        append_stage_log(
            session_id=request_session_id,
            stage="request",
            status="received",
            message="Received user message.",
            state=state,
            details={"message_chars": len(message)},
        )
        active_agent = "central_agent"
        trace: List[Dict[str, Any]] = [
            agent_trace_event("central_agent", "thinking", "Central Agent is reading the user request."),
        ]
        append_stage_log(
            session_id=request_session_id,
            stage="central_agent",
            status="thinking",
            message="Central Agent is reading the user request.",
            state=state,
        )

        central_result = self.central_agent.run(message, state)
        state = central_result["trip_state"]
        missing_fields = central_result["missing_fields"]
        trace.append(
            agent_trace_event(
                "central_agent",
                "done",
                "Central Agent normalized intent and selected the next handoff.",
                details={
                    "missing_fields": missing_fields,
                    "orchestration": central_result.get("orchestration", []),
                    "is_edit_request": central_result.get("is_edit_request", False),
                },
            )
        )
        append_stage_log(
            session_id=request_session_id,
            stage="central_agent",
            status="done",
            message="Central Agent normalized intent and selected the next handoff.",
            state=state,
            details={
                "missing_fields": missing_fields,
                "orchestration": central_result.get("orchestration", []),
                "is_edit_request": central_result.get("is_edit_request", False),
            },
        )

        if missing_fields:
            append_stage_log(
                session_id=request_session_id,
                stage="response",
                status="clarification",
                message="Returning clarification because required fields are missing.",
                state=state,
                details={"missing_fields": missing_fields},
            )
            return {
                "ok": True,
                "session_id": request_session_id,
                "assistant_message": central_result.get("assistant_message")
                or "I need a destination and either dates or trip length to build the base trip.",
                "trip_state": state,
                "agent_trace": trace,
                "active_agent": active_agent,
                "missing_fields": missing_fields,
                "errors": [],
            }

        if central_result.get("is_edit_request"):
            active_agent = "edit_agent"
            trace.append(agent_trace_event("edit_agent", "thinking", "Edit Agent is applying the requested change."))
            append_stage_log(
                session_id=request_session_id,
                stage="edit_agent",
                status="thinking",
                message="Edit Agent is applying the requested change.",
                state=state,
            )
            edit_result = self.edit_agent.run(message, state)
            state = edit_result["trip_state"]
            trace.append(
                agent_trace_event(
                    "edit_agent",
                    "done",
                    edit_result.get("edit_summary") or "Edit Agent updated the existing trip.",
                )
            )
            append_stage_log(
                session_id=request_session_id,
                stage="edit_agent",
                status="done",
                message=edit_result.get("edit_summary") or "Edit Agent updated the existing trip.",
                state=state,
            )
            append_stage_log(
                session_id=request_session_id,
                stage="response",
                status="done",
                message="Returning edited trip state.",
                state=state,
            )
            return {
                "ok": True,
                "session_id": request_session_id,
                "assistant_message": edit_result["assistant_message"],
                "trip_state": state,
                "agent_trace": trace,
                "active_agent": active_agent,
                "missing_fields": [],
                "errors": [],
            }

        active_agent = "flight_desk_agent"
        trace.append(agent_trace_event("flight_desk_agent", "thinking", "Flight Desk Agent is checking live flight readiness."))
        append_stage_log(
            session_id=request_session_id,
            stage="flight_desk_agent",
            status="thinking",
            message="Flight Desk Agent is checking live flight readiness.",
            state=state,
        )
        flight_result = self.flight_desk_agent.run(state)
        state = flight_result["trip_state"]
        trace.append(
            agent_trace_event(
                "flight_desk_agent",
                flight_result["status"],
                flight_result["message"],
            )
        )
        append_stage_log(
            session_id=request_session_id,
            stage="flight_desk_agent",
            status=flight_result["status"],
            message=flight_result["message"],
            state=state,
            details=flight_result.get("details") if isinstance(flight_result.get("details"), dict) else {},
        )

        if not has_day_plan_inputs(state):
            append_stage_log(
                session_id=request_session_id,
                stage="response",
                status="clarification",
                message="Returning clarification because day-plan inputs are missing.",
                state=state,
                details={"missing_fields": ["destination", "dates_or_duration"]},
            )
            return {
                "ok": True,
                "session_id": request_session_id,
                "assistant_message": "I still need a destination and either dates or trip length before the Day Plan Agent can build the itinerary.",
                "trip_state": state,
                "agent_trace": trace,
                "active_agent": active_agent,
                "missing_fields": ["destination", "dates_or_duration"],
                "errors": [],
            }

        active_agent = "day_plan_agent"
        trace.append(agent_trace_event("day_plan_agent", "thinking", "Day Plan Agent is drafting the itinerary."))
        append_stage_log(
            session_id=request_session_id,
            stage="day_plan_agent",
            status="thinking",
            message="Day Plan Agent is drafting the itinerary.",
            state=state,
        )
        day_plan_result = self.day_plan_agent.run(state)
        state = day_plan_result["trip_state"]
        trace.append(agent_trace_event("day_plan_agent", "done", "Day Plan Agent generated the base itinerary."))
        append_stage_log(
            session_id=request_session_id,
            stage="day_plan_agent",
            status="done",
            message="Day Plan Agent generated the base itinerary.",
            state=state,
        )
        append_stage_log(
            session_id=request_session_id,
            stage="response",
            status="done",
            message="Returning generated trip plan.",
            state=state,
        )

        return {
            "ok": True,
            "session_id": request_session_id,
            "assistant_message": day_plan_result["assistant_message"],
            "trip_state": state,
            "agent_trace": trace,
            "active_agent": active_agent,
            "missing_fields": [],
            "errors": [],
        }
