from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout_seconds: int = 180,
        max_output_tokens: int = 1024,
    ) -> None:
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3:4b")
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], response_format: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": self.max_output_tokens},
        }
        if response_format is not None:
            payload["format"] = response_format
        request = Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise OllamaError(
                f"Could not reach Ollama at {self.host}. Start it with `ollama serve`. ({error.reason})"
            ) from error
