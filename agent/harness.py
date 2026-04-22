"""
Agent harness — the reasoning loop.

Walks the five steps from the deck:
  01 Resolve     — meaning layer resolves the incident to canonical entities
  02 Traverse    — relationships layer finds what's connected (blast radius)
  03 Evaluate    — rules layer calculates priority, matches runbooks, checks SLA
  04 Recall      — history layer retrieves precedent + detects correlated incidents
  05 Act         — triage decision + routing, with a full trace

The key property: every decision is grounded. The trace says exactly which
context item fed which step of the reasoning.
"""
from agent import meaning, relationships, rules, history

# Design decision: minimum edge confidence for the agent to auto-triage.
# Below this, the refusal ladder fires.
MIN_CONFIDENCE_FOR_AUTO = 0.80

# Priority escalation map (one level up).
_ESCALATION_MAP = {"P4": "P3", "P3": "P2", "P2": "P1", "P1": "P1"}


def triage(incident: dict) -> dict:
    """
    Triage an incident: assign priority (P1-P4), route it, and attach context.

    Returns a decision dict AND a full trace.
    """
    trace = []

    # ---------- 01 RESOLVE ----------
    # Find the dominant affected service via the CI -> service graph.
    affected = relationships.affected_services(incident["affected_cis"])

    trace.append({
        "step": "01_resolve",
        "action": f"affected_services({incident['affected_cis']})",
        "result": affected,
    })

    if not affected or all(a.get("service_id") is None for a in affected):
        return _refuse(trace, "Could not resolve incident to any known service.")

    # Pick the highest-confidence service mapping.
    primary = max(
        (a for a in affected if a["service_id"]),
        key=lambda a: a["confidence"],
    )

    # Refusal 1: CI-to-service edge confidence below threshold.
    if primary["confidence"] < MIN_CONFIDENCE_FOR_AUTO:
        return _refuse(
            trace,
            f"CI-to-service mapping confidence {primary['confidence']:.2f} "
            f"is below threshold {MIN_CONFIDENCE_FOR_AUTO}. "
            "Refusing to auto-triage on unreliable dependency data.",
        )

    # Refusal 2: stale dependency data.
    if not primary["fresh"]:
        return _refuse(
            trace,
            f"CI-to-service mapping is {primary['age_days']} days old "
            f"(threshold: 30). Refusing to auto-triage on stale context.",
        )

    service = meaning.resolve_service(primary["service_id"])
    trace.append({
        "step": "01_resolve",
        "action": f"resolve_service({primary['service_id']})",
        "result": service,
    })

    # ---------- 02 TRAVERSE ----------
    # What depends on this service, and what does it depend on?
    downstream = relationships.downstream_services(service["id"])
    upstream = relationships.upstream_services(service["id"])
    connected_ids = relationships.connected_service_ids(service["id"])

    trace.append({
        "step": "02_traverse",
        "action": f"downstream_services({service['id']})",
        "result": downstream,
    })
    trace.append({
        "step": "02_traverse",
        "action": f"upstream_services({service['id']})",
        "result": upstream,
    })

    # ---------- 03 EVALUATE ----------
    # Run all rules: priority calculation, runbook matching, SLA check.
    rule_results = rules.evaluate_all(incident, service, downstream, upstream)
    trace.append({
        "step": "03_evaluate",
        "action": f"evaluate_all(incident={incident['id']}, service={service['id']})",
        "result": rule_results,
    })

    # ---------- 04 RECALL ----------
    # Find precedent for this type of incident on this service.
    prior = history.similar_incidents(
        service["id"], incident.get("symptom_category", "error")
    )
    trace.append({
        "step": "04_recall",
        "action": f"similar_incidents({service['id']}, {incident.get('symptom_category')})",
        "result": prior,
    })

    # Correlation detection: are there other incidents on connected services?
    correlated = history.correlated_incidents(
        service["id"], connected_ids, incident["reported_at"]
    )
    trace.append({
        "step": "04_recall",
        "action": f"correlated_incidents({service['id']}, {connected_ids})",
        "result": correlated,
    })

    # ---------- 05 ACT ----------
    return _decide(incident, service, rule_results, prior, correlated, trace)


def _decide(
    incident: dict,
    service: dict,
    rule_results: dict,
    prior: dict,
    correlated: dict,
    trace: list,
) -> dict:
    """Turn the gathered context into a triage decision."""
    priority = rule_results["priority"]["priority"]
    runbook_match = rule_results["runbook_match"]
    sla = rule_results["sla"]

    # Storm escalation: if correlated incidents detected, escalate by one level.
    storm_escalated = False
    if correlated["storm_detected"]:
        original = priority
        priority = _ESCALATION_MAP.get(priority, priority)
        if priority != original:
            storm_escalated = True
        # Recalculate SLA with escalated priority.
        sla = rules.check_sla(priority, incident["reported_at"])

    # Determine routing.
    route = _determine_route(priority, runbook_match, correlated)

    decision = {
        "incident_id": incident["id"],
        "priority": priority,
        "route": route,
        "reason": _build_reason(rule_results, runbook_match, correlated, storm_escalated),
    }

    # Attach runbook if matched above threshold.
    if runbook_match["score"] >= rules.RUNBOOK_MATCH_THRESHOLD:
        decision["runbook"] = {
            "id": runbook_match["runbook_id"],
            "name": runbook_match["runbook"]["name"],
            "score": runbook_match["score"],
            "auto_remediable": runbook_match["runbook"].get("auto_remediable", False),
            "estimated_resolution_minutes": runbook_match["runbook"].get("estimated_resolution_minutes"),
        }

    # Attach SLA info.
    if sla.get("has_sla"):
        decision["sla"] = sla

    # Attach correlation info.
    if correlated["storm_detected"]:
        decision["correlations"] = {
            "storm_detected": True,
            "related_incidents": correlated["unique_incidents"],
            "escalated": storm_escalated,
        }

    # Attach precedent summary.
    if prior["found"] > 0:
        decision["precedent"] = {
            "prior_incidents": prior["found"],
            "resolved": prior["resolved"],
            "escalated": prior["escalated"],
            "recurring": prior["recurring"],
            "avg_resolution_minutes": prior["avg_resolution_minutes"],
            "runbooks_used": prior["runbooks_used"],
        }

    trace.append({"step": "05_act", "action": "decide", "result": decision})
    return {"decision": decision, "trace": trace}


def _determine_route(priority: str, runbook_match: dict, correlated: dict) -> str:
    """Determine where to route the incident."""
    # Major incident manager for P1 or storm.
    if priority == "P1" or correlated["storm_detected"]:
        return "major_incident_manager"

    # Auto-remediate if runbook matched and is auto-remediable.
    if (runbook_match["score"] >= rules.RUNBOOK_MATCH_THRESHOLD
            and runbook_match.get("runbook", {}).get("auto_remediable", False)):
        return "auto_remediate"

    # P2 goes to on-call.
    if priority == "P2":
        return "on_call"

    # P3/P4 go to service desk.
    return "service_desk"


def _build_reason(
    rule_results: dict,
    runbook_match: dict,
    correlated: dict,
    storm_escalated: bool,
) -> str:
    """Build a human-readable reason string."""
    parts = []

    # Priority factors.
    factors = rule_results["priority"]["factors"]
    factor_strs = [f["reason"] for f in factors.values()]
    parts.append(f"Priority determined by: {'; '.join(factor_strs)}.")

    # Storm escalation.
    if storm_escalated:
        parts.append(
            f"ESCALATED due to incident storm — "
            f"{len(correlated['unique_incidents'])} correlated incidents detected."
        )

    # Runbook.
    if runbook_match["score"] >= rules.RUNBOOK_MATCH_THRESHOLD:
        rb = runbook_match["runbook"]
        if rb.get("auto_remediable"):
            parts.append(f"Runbook {runbook_match['runbook_id']} matched (auto-remediable).")
        else:
            parts.append(f"Runbook {runbook_match['runbook_id']} matched (manual steps).")
    else:
        parts.append("No runbook matched above threshold.")

    # SLA.
    sla = rule_results["sla"]
    if sla.get("response_breached") or sla.get("resolution_breached"):
        parts.append("WARNING: SLA breach detected.")
    elif sla.get("response_near_breach") or sla.get("resolution_near_breach"):
        parts.append("ALERT: SLA near-breach — approaching target.")

    return " ".join(parts)


def _refuse(trace: list, reason: str) -> dict:
    """The refusal ladder. Always return a trace."""
    decision = {
        "priority": "refused",
        "route": "manual_triage",
        "reason": reason,
    }
    trace.append({"step": "05_act", "action": "refuse", "result": decision})
    return {"decision": decision, "trace": trace}
