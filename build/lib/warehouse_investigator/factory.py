from __future__ import annotations

import os
from pathlib import Path

from .agent import Investigator
from .ollama import OllamaClient
from .routing import ECONOMY_ROUTING_MODELS, FAST_ROUTING_MODELS, RoutedInvestigator


def create_investigator(
    model: str = "auto",
    host: str | None = None,
    fast_model: str | None = None,
    balanced_model: str | None = None,
    deep_model: str | None = None,
    routing_profile: str = "fast",
    instructions_path: Path | None = None,
) -> Investigator | RoutedInvestigator:
    if model != "auto":
        return Investigator(OllamaClient(model=model, host=host), instructions_path)
    small = fast_model or os.getenv("WAREHOUSE_SMALL_MODEL", ECONOMY_ROUTING_MODELS[0])
    primary = balanced_model or os.getenv("WAREHOUSE_PRIMARY_MODEL", FAST_ROUTING_MODELS[0])
    deep = deep_model or os.getenv("WAREHOUSE_DEEP_MODEL", FAST_ROUTING_MODELS[1])
    if routing_profile == "fast":
        models = (primary, deep)
    elif routing_profile == "economy":
        models = (small, primary, deep)
    else:
        raise ValueError(f"Unknown routing profile: {routing_profile}")
    return RoutedInvestigator(models=models, host=host, instructions_path=instructions_path)
