from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from routewise_ai_demo.orchestrator import RouteWiseDemoOrchestrator
from routewise_ai_demo.schemas import validate_message_payload
from routewise_ai_demo.services import (
    GroqClient,
    GroqConfigurationError,
    GroqResponseError,
    RapidApiFlightsClient,
)


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
HOST = os.environ.get("ROUTEWISE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ROUTEWISE_PORT", "5055"))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


class RouteWiseHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            json_response(
                self,
                200,
                {
                    "ok": True,
                    "groq_configured": GroqClient().is_configured(),
                    "rapidapi_configured": RapidApiFlightsClient().is_configured(),
                },
            )
            return
        self.serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/message":
            json_response(self, 404, {"ok": False, "error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            json_response(self, 400, {"ok": False, "error": "invalid JSON body"})
            return

        user_message, trip_state, error = validate_message_payload(payload)
        if error:
            json_response(self, 400, {"ok": False, "error": error})
            return

        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            session_id = None

        try:
            result = RouteWiseDemoOrchestrator().handle_message(
                message=user_message,
                trip_state=trip_state,
                session_id=session_id,
            )
            json_response(self, 200, result)
        except GroqConfigurationError as exc:
            json_response(self, 500, {"ok": False, "error": str(exc), "errors": [str(exc)]})
        except GroqResponseError as exc:
            json_response(self, 502, {"ok": False, "error": str(exc), "errors": [str(exc)]})
        except Exception as exc:
            json_response(self, 500, {"ok": False, "error": str(exc), "errors": [str(exc)]})

    def serve_static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        if relative == "agentic-trip-planner":
            relative = "index.html"
        file_path = (WEB_ROOT / relative).resolve()
        if WEB_ROOT.resolve() not in file_path.parents and file_path != WEB_ROOT.resolve():
            self.send_error(403)
            return
        if not file_path.exists() or not file_path.is_file():
            file_path = WEB_ROOT / "index.html"

        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    load_dotenv(ROOT / ".env")
    server = ThreadingHTTPServer((HOST, PORT), RouteWiseHandler)
    print(f"RouteWise AI demo running at http://{HOST}:{PORT}/agentic-trip-planner")
    server.serve_forever()


if __name__ == "__main__":
    main()

