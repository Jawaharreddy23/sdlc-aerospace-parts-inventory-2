"""Optional LLM bridge to a Databricks model service.

Every agent in this platform tries the LLM first and falls back to
deterministic, template-based generation when the LLM is not configured or a
call fails. That keeps the whole app runnable offline for demos while making
it fully AI-powered once credentials are provided.

Credentials are resolved in this order:
    1. Environment variables (DATABRICKS_HOST / DATABRICKS_TOKEN / MODEL_SERVICE)
    2. config.json next to app.py (copy config.example.json to config.json
       and fill in your tokens - see README)

Jira connection fields in config.json are reserved for future integration.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _config() -> dict:
    """Load the optional config.json next to the app root. Missing file,
    bad JSON or read errors all degrade to an empty config."""
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - config is optional
        return {}


class LLMError(RuntimeError):
    """Raised when the configured model service cannot be used."""


def _host() -> str:
    value = os.getenv("DATABRICKS_HOST") or _config().get("databricks_host") or ""
    return value.rstrip("/")


def _token() -> str:
    return os.getenv("DATABRICKS_TOKEN") or _config().get("databricks_token") or ""


def llm_enabled() -> bool:
    return bool(_host() and _token())


def model_name() -> str:
    return os.getenv("MODEL_SERVICE") or _config().get("model_service") or "system.ai.gpt-5"


def endpoint_path() -> str:
    return (
        os.getenv("LLM_ENDPOINT_PATH")
        or _config().get("llm_endpoint_path")
        or "/ai-gateway/mlflow/v1/chat/completions"
    )


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 2000) -> str:
    """Single-shot chat completion against the Databricks model service.

    Raises LLMError on any configuration, connection or format problem so
    callers can catch it and use their deterministic fallback.
    """
    if not llm_enabled():
        raise LLMError("DATABRICKS_HOST / DATABRICKS_TOKEN are not set")

    url = _host() + endpoint_path()
    headers = {
        "Authorization": "Bearer " + _token(),
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 - deliberate broad fallback boundary
        raise LLMError(str(exc)) from exc
