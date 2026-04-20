from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqConfigurationError(RuntimeError):
    pass


class GroqResponseError(RuntimeError):
    pass


class GroqClient:
    def __init__(self, *, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.model = os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _require_configured(self) -> None:
        if not self.api_key:
            raise GroqConfigurationError("GROQ_API_KEY is not configured for the RouteWise AI demo.")

    @staticmethod
    def _extract_json_object(content: str) -> Dict[str, Any]:
        text = (content or "").strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            first = text.find("{")
            last = text.rfind("}")
            if first >= 0 and last > first:
                text = text[first : last + 1]

        try:
            parsed = json.loads(text)
        except Exception as exc:
            raise GroqResponseError("Groq returned a non-JSON response.") from exc
        if not isinstance(parsed, dict):
            raise GroqResponseError("Groq JSON response must be an object.")
        return parsed

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: Dict[str, Any],
        temperature: float = 0.2,
        max_tokens: int = 1800,
    ) -> Dict[str, Any]:
        self._require_configured()
        body = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=True, sort_keys=True),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            GROQ_CHAT_COMPLETIONS_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "RouteWise-AI-Demo/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=ssl._create_unverified_context(),
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise GroqResponseError(f"Groq API error {exc.code}: {error_body}") from exc
        except Exception as exc:
            raise GroqResponseError(f"Groq request failed: {exc}") from exc

        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices or not isinstance(choices, list):
            raise GroqResponseError("Groq response did not include choices.")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise GroqResponseError("Groq response did not include message content.")
        return self._extract_json_object(content)
