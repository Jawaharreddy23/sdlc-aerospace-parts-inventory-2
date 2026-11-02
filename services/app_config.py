"""Shared configuration loader.

Reads the optional config.json next to app.py. This is the single place
where external credentials (Databricks, Jira, GitHub) are resolved from;
nothing is hardcoded. A missing, empty or malformed file degrades to an
empty dict so the app always runs in local/deterministic mode.
"""
from __future__ import annotations

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def config() -> dict:
    """Return the parsed config.json ({} when absent or invalid)."""
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - config is optional
        return {}
