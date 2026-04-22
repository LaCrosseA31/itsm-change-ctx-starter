"""
Meaning layer — canonical entity resolution.

This module answers: "what does this string actually refer to?"
It resolves ambiguous references (names, IDs) into canonical, typed entities.

In a production system this would sit behind a semantic layer or business
glossary service. Here it is backed by simple JSON files.
"""
import json
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_services() -> list[dict]:
    with open(DATA_DIR / "services.json") as f:
        return json.load(f)["services"]


def _load_runbooks() -> list[dict]:
    with open(DATA_DIR / "runbooks.json") as f:
        return json.load(f)["runbooks"]


def _load_sla_definitions() -> dict:
    with open(DATA_DIR / "sla_definitions.json") as f:
        return json.load(f)["sla_targets"]


def resolve_service(reference: str) -> Optional[dict]:
    """
    Resolve a service reference (by id or name) to the canonical Service entity.

    Returns None if the reference cannot be resolved — and that is a deliberate
    signal to the agent, NOT an error to retry.
    """
    services = _load_services()
    ref = reference.strip().lower()
    for svc in services:
        if svc["id"].lower() == ref or svc["name"].lower() == ref:
            return svc
    return None


def resolve_runbook(runbook_id: str) -> Optional[dict]:
    """Resolve a runbook id to its canonical definition."""
    runbooks = _load_runbooks()
    for rb in runbooks:
        if rb["id"] == runbook_id:
            return rb
    return None


def all_runbooks() -> list[dict]:
    """Return all runbooks (used by rules to find best match)."""
    return _load_runbooks()


def resolve_sla(priority: str) -> Optional[dict]:
    """
    Resolve SLA targets for a given priority level (P1-P4).

    Returns the response and resolution time targets, or None if unknown priority.
    """
    targets = _load_sla_definitions()
    return targets.get(priority)
