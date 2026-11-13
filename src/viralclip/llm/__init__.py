"""Integración opcional con modelos locales a través de Ollama."""

from __future__ import annotations

from .ollama import CircuitBreaker, OllamaClient, OllamaHealth
from .prompts import SYSTEM_PROMPT, build_hook_prompt, parse_hook_response

__all__ = [
    "CircuitBreaker",
    "OllamaClient",
    "OllamaHealth",
    "SYSTEM_PROMPT",
    "build_hook_prompt",
    "parse_hook_response",
]
