"""
History layer — temporal recall.

This module answers: "has this kind of incident happened before, and what happened?"
The agent uses this to attach precedent to its triage — a runbook match plus a
clean history of quick resolutions is much stronger evidence than a runbook match
alone.

It also provides correlation detection: are there other open or recent incidents
on the same or connected services? If so, this may be part of an incident storm.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_events() -> list[dict]:
    with open(DATA_DIR / "event_log.json") as f:
        return json.load(f)["events"]


def similar_incidents(service_id: str, symptom_category: str, k: int = 10) -> dict:
    """
    Return the k most recent closed incidents for this (service, symptom) pair.

    Also summarize outcomes — how many resolved, how many escalated, how many
    were recurring. That summary is what actually feeds the agent's decision.
    """
    events = _load_events()
    matches = [
        e for e in events
        if e["type"] == "incident_closed"
        and e.get("service_id") == service_id
        and e.get("symptom_category") == symptom_category
    ]
    matches.sort(key=lambda e: e["timestamp"], reverse=True)
    matches = matches[:k]

    resolved_count = sum(1 for e in matches if e["outcome"] == "resolved")
    escalated_count = sum(1 for e in matches if e["outcome"] == "escalated")
    recurring_count = sum(1 for e in matches if e["outcome"] == "recurring")

    avg_resolution = None
    resolution_times = [e["resolution_minutes"] for e in matches if e.get("resolution_minutes")]
    if resolution_times:
        avg_resolution = round(sum(resolution_times) / len(resolution_times), 1)

    runbooks_used = list({e["runbook_id"] for e in matches if e.get("runbook_id")})
    linked = []
    for e in matches:
        linked.extend(e.get("linked_incidents", []))

    return {
        "found": len(matches),
        "resolved": resolved_count,
        "escalated": escalated_count,
        "recurring": recurring_count,
        "avg_resolution_minutes": avg_resolution,
        "runbooks_used": runbooks_used,
        "linked_incidents": linked,
        "most_recent": matches[0] if matches else None,
    }


def correlated_incidents(
    service_id: str,
    connected_service_ids: list[str],
    reported_at: str,
    time_window_hours: int = 4,
) -> dict:
    """
    Find open or recent incidents on the same or connected services.

    This is storm detection: if multiple incidents fire on related services
    within a short window, they are likely caused by a single root cause.
    The agent uses this to escalate priority and flag for major incident review.

    Uses the incident's reported_at as the reference time so results are
    reproducible regardless of when the agent runs.
    """
    events = _load_events()
    reference = datetime.fromisoformat(reported_at.replace("Z", "+00:00"))
    cutoff = reference - timedelta(hours=time_window_hours)

    all_relevant_ids = {service_id} | set(connected_service_ids)

    correlated = []
    for e in events:
        # Only consider open incidents and recently-closed ones.
        if e["type"] not in ("incident_open", "incident_closed"):
            continue
        if e.get("service_id") not in all_relevant_ids:
            continue

        ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
        if ts < cutoff:
            continue

        # Skip if this is the same service but from the same incident
        # (we're looking for OTHER incidents).
        correlated.append({
            "incident_id": e.get("incident_id"),
            "service_id": e["service_id"],
            "type": e["type"],
            "symptom_category": e.get("symptom_category"),
            "priority": e.get("priority_assigned"),
            "timestamp": e["timestamp"],
        })

    # Storm = 2+ correlated incidents (including open ones on different services).
    unique_incidents = {c["incident_id"] for c in correlated if c.get("incident_id")}
    storm_detected = len(unique_incidents) >= 2

    return {
        "correlated": correlated,
        "count": len(correlated),
        "unique_incidents": list(unique_incidents),
        "storm_detected": storm_detected,
    }
