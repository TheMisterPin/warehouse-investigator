from unittest.mock import patch

from warehouse_investigator.ollama import OllamaClient, OllamaError


def test_chat_timeout_raises_ollama_error() -> None:
    client = OllamaClient(timeout_seconds=1)

    with patch("warehouse_investigator.ollama.urlopen", side_effect=TimeoutError("timed out")):
        try:
            client.chat([], [], None)
        except OllamaError as error:
            assert "timed out" in str(error).lower()
            return
    raise AssertionError("expected OllamaError")
