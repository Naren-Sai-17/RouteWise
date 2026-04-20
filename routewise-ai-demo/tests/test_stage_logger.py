import json
import os
import tempfile
import unittest

from routewise_ai_demo.stage_logger import append_stage_log


class StageLoggerTest(unittest.TestCase):
    def test_writes_summarized_stage_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = os.environ.get("ROUTEWISE_STAGE_LOG_DIR")
            os.environ["ROUTEWISE_STAGE_LOG_DIR"] = tmpdir
            try:
                append_stage_log(
                    session_id="test-session",
                    stage="flight_desk_agent",
                    status="done",
                    message="Flight Desk Agent selected cheaper dates.",
                    state={
                        "origin": "HYD",
                        "destination": "JAPAN",
                        "start_date": "2026-05-12",
                        "end_date": "2026-05-19",
                        "duration_days": 7,
                        "travelers": 1,
                        "interests": ["anime"],
                        "planning_facts": ["audience: teenagers"],
                        "flight_preferences": {
                            "date_window_start": "2026-05-01",
                            "date_window_end": "2026-05-31",
                        },
                        "flight_search": {
                            "status": "done",
                            "strategy": "calendar_then_flight_list",
                            "options": [{"price": 520}],
                        },
                        "itinerary": [{"day": 1}],
                    },
                    details={"tool": "calendar_tool"},
                )
            finally:
                if old_dir is None:
                    os.environ.pop("ROUTEWISE_STAGE_LOG_DIR", None)
                else:
                    os.environ["ROUTEWISE_STAGE_LOG_DIR"] = old_dir

            log_path = os.path.join(tmpdir, "test-session", "flight_desk_agent.jsonl")
            with open(log_path, "r", encoding="utf-8") as handle:
                entry = json.loads(handle.readline())

        self.assertEqual(entry["session_id"], "test-session")
        self.assertEqual(entry["stage"], "flight_desk_agent")
        self.assertEqual(entry["state"]["origin"], "HYD")
        self.assertEqual(entry["state"]["flight_option_count"], 1)
        self.assertEqual(entry["state"]["itinerary_days"], 1)
        self.assertNotIn("options", entry["state"])


if __name__ == "__main__":
    unittest.main()
