from __future__ import annotations

import os
from pathlib import Path

from .agent import Investigator
from .ollama import OllamaClient
from .routing import DEFAULT_ROUTING_MODELS, DEEP_REVIEW_TIMEOUT_SECONDS, PRIMARY_TIMEOUT_SECONDS, RoutedInvestigator


def create_investigator(
    model: str = "auto",
    host: str | None = None,
    primary_model: str | None = None,
    deep_model: str | None = None,
    instructions_path: Path | None = None,
) -> Investigator | RoutedInvestigator:
    if model != "auto":
        timeout_seconds = DEEP_REVIEW_TIMEOUT_SECONDS if "27b" in model else PRIMARY_TIMEOUT_SECONDS
        return Investigator(OllamaClient(model=model, host=host, timeout_seconds=timeout_seconds), instructions_path)
    primary = primary_model or os.getenv("WAREHOUSE_PRIMARY_MODEL", DEFAULT_ROUTING_MODELS[0])
    deep = deep_model or os.getenv("WAREHOUSE_DEEP_MODEL", DEFAULT_ROUTING_MODELS[1])
    return RoutedInvestigator(models=(primary, deep), host=host, instructions_path=instructions_path)
