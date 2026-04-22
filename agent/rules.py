"""
Rules layer — policy-as-code.

This module answers: "given the facts, what rules apply, and with what result?"
Rules are layered:
  - PRIORITY rules — determine P1-P4 from multiple signals
  - RUNBOOK rules (defeasible) — suggest a resolution playbook
  - SLA rules — calculate response/resolution targets and breach status
  - DORA floor (non-negotiable) — DORA-regulated services cannot go below P2

Priority is determined by the MOST SEVERE signal. Each factor proposes a
priority; the final priority is the highest (most urgent) across all factors.

In production, these would be Rego policies evaluated by OPA.
Here they are Python functions — the structure is what matters.
"""
from datetime import datetime, timezone
from agent.meaning import all_runbooks, resolve_sla

# Match threshold for runbook matching — part of the design, not the data.
RUNBOOK_MATCH_THRESHOLD = 0.60

# Priority ordering (lower index = more severe).
_PRIORITY_ORDER = ["P1", "P2", "P3", "P4"]


def _most_severe(*priorities: str) -> str:
    """Return the most severe (lowest-numbered) priority from the inputs."""
    best = len(_PRIORITY_ORDER) - 1
    for p in priorities:
        if p in _PRIORITY_ORDER:
            best = min(best, _PRIORITY_ORDER.index(p))
    return _PRIORITY_ORDER[best]


def match_runbook(incident: dict, service: dict) -> dict:
    """
    Score the incident against every runbook and pick the best match.

    Returns the best runbook with a score in [0, 1].
    A score below threshold means no runbook applies.
    """
    text = (incident["title"] + " " + incident.get("description", "")).lower()
    runbooks = all_runbooks()

    best = {"runbook_id": None, "score": 0.0, "runbook": None}
    for rb in runbooks:
        if service["tier"] not in rb["applicable_service_tiers"]:
            continue
        # Simple keyword match — production would use NLP / embeddings.
        hits = sum(1 for pat in rb["match_patterns"] if pat in text)
        score = min(1.0, hits / max(1, len(rb["match_patterns"])) + (0.4 if hits > 0 else 0.0))
        if score > best["score"]:
            best = {"runbook_id": rb["id"], "score": score, "runbook": rb}
    return best


def calculate_priority(
    incident: dict,
    service: dict,
    downstream: list[dict],
    upstream: list[dict],
) -> dict:
    """
    Determine incident priority (P1-P4) from multiple signals.

    Each factor proposes a priority. The final priority is the most severe.
    This produces a full breakdown so the trace shows exactly WHY.
    """
    factors = {}

    # Factor 1: Service tier.
    tier_map = {"critical": "P2", "standard": "P3", "non-critical": "P4"}
    factors["service_tier"] = {
        "proposed": tier_map.get(service["tier"], "P3"),
        "reason": f"Service tier '{service['tier']}' → {tier_map.get(service['tier'], 'P3')}",
    }

    # Factor 2: Symptom category.
    symptom_map = {"outage": "P1", "degradation": "P2", "error": "P3", "threshold_warning": "P4"}
    cat = incident.get("symptom_category", "error")
    factors["symptom"] = {
        "proposed": symptom_map.get(cat, "P3"),
        "reason": f"Symptom '{cat}' → {symptom_map.get(cat, 'P3')}",
    }

    # Factor 3: Affected user count.
    users = incident.get("affected_user_count", 0)
    if users >= 10000:
        user_priority = "P1"
    elif users >= 1000:
        user_priority = "P2"
    elif users >= 100:
        user_priority = "P3"
    else:
        user_priority = "P4"
    factors["user_impact"] = {
        "proposed": user_priority,
        "reason": f"{users} affected users → {user_priority}",
    }

    # Factor 4: Blast radius (downstream dependencies).
    if len(downstream) >= 3:
        blast_priority = "P1"
    elif len(downstream) >= 1:
        blast_priority = "P2"
    else:
        blast_priority = "P4"
    factors["blast_radius"] = {
        "proposed": blast_priority,
        "reason": f"{len(downstream)} downstream service(s) → {blast_priority}",
    }

    # Factor 5: DORA regulatory floor.
    if service.get("dora_regulated", False):
        factors["dora_regulated"] = {
            "proposed": "P2",
            "reason": f"Service {service['id']} is DORA-regulated → floor P2",
        }

    # Final: most severe wins.
    proposed = [f["proposed"] for f in factors.values()]
    final = _most_severe(*proposed)

    return {
        "priority": final,
        "factors": factors,
    }


def check_sla(priority: str, reported_at: str) -> dict:
    """
    Calculate SLA targets and elapsed time for the given priority.

    Returns targets, elapsed minutes, and whether a breach has occurred or is imminent.
    """
    sla = resolve_sla(priority)
    if not sla:
        return {"has_sla": False, "reason": f"No SLA defined for {priority}"}

    now = datetime.now(timezone.utc)
    reported = datetime.fromisoformat(reported_at.replace("Z", "+00:00"))
    elapsed_minutes = (now - reported).total_seconds() / 60

    response_target = sla["response_minutes"]
    resolution_target = sla["resolution_minutes"]

    response_breached = elapsed_minutes > response_target
    resolution_breached = elapsed_minutes > resolution_target
    # "Near breach" = within 80% of target.
    response_near_breach = not response_breached and elapsed_minutes > (response_target * 0.8)
    resolution_near_breach = not resolution_breached and elapsed_minutes > (resolution_target * 0.8)

    return {
        "has_sla": True,
        "priority": priority,
        "response_target_minutes": response_target,
        "resolution_target_minutes": resolution_target,
        "elapsed_minutes": round(elapsed_minutes, 1),
        "response_breached": response_breached,
        "resolution_breached": resolution_breached,
        "response_near_breach": response_near_breach,
        "resolution_near_breach": resolution_near_breach,
    }


def evaluate_all(
    incident: dict,
    service: dict,
    downstream: list[dict],
    upstream: list[dict],
) -> dict:
    """Run every rule for this incident/service pair and return a consolidated result."""
    priority_result = calculate_priority(incident, service, downstream, upstream)
    return {
        "priority": priority_result,
        "runbook_match": match_runbook(incident, service),
        "sla": check_sla(priority_result["priority"], incident["reported_at"]),
    }
