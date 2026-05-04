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

<<<<<<< HEAD
# Design decision: minimum edge confidence for the agent to auto-triage.
# Below this, the refusal ladder fires.
MIN_CONFIDENCE_FOR_AUTO = 0.80
=======
Untrusted input boundary: `rfc["description"]` is engineer-authored free text
and is treated as untrusted — it is deliberately never read by the agent.
Only structured fields (id, title, affected_cis, submitted_at) influence the
classification.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from agent import config, history, meaning, relationships, rules, validation

ROOT_DIR = Path(__file__).parent.parent
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28

# Priority escalation map (one level up).
_ESCALATION_MAP = {"P4": "P3", "P3": "P2", "P2": "P1", "P1": "P1"}


def triage(incident: dict) -> dict:
    """
<<<<<<< HEAD
    Triage an incident: assign priority (P1-P4), route it, and attach context.
=======
    Classify an RFC as standard, normal, emergency, or refused, with a full trace.
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28

    The trace is the audit log for the decision: every entry records which
    layer was called and what it returned. Any reason in the final decision
    must be traceable back to one of these entries.

    Two short-circuits run before the five-step loop:
      - kill-switch: a single config flag stops all auto-approvals instantly
      - emergency: human-declared emergencies bypass agent reasoning entirely
    """
    trace: list[dict] = []

    # ---------- 00 INTAKE ----------
    # Validate the RFC against its canonical schema. A malformed RFC fails
    # loudly here rather than producing a confidently-wrong classification.
    validation.validate_rfc(rfc)

    # Kill-switch: stops the world.
    if config.KILL_SWITCH:
        return _emit(_refuse(trace, "Kill-switch engaged. All auto-classifications disabled."), rfc)

    # Emergency short-circuit: humans declare emergencies, the agent never does.
    if rfc.get("change_type") == "emergency":
        decision = {
            "rfc_id": rfc["id"],
            "classification": "emergency",
            "route": "ECAB_review",
            "reason": "Emergency change declared by human submitter. Agent reasoning bypassed.",
        }
        trace.append({"step": "00_intake", "action": "emergency_short_circuit", "result": decision})
        return _emit({"decision": decision, "trace": trace}, rfc)

    return _emit(_classify_main(rfc, trace), rfc)


def _classify_main(rfc: dict, trace: list) -> dict:
    """The five-step reasoning loop, after intake checks have passed."""
    submitted_at = datetime.fromisoformat(rfc["submitted_at"].replace("Z", "+00:00"))

    # ---------- 01 RESOLVE ----------
<<<<<<< HEAD
    # Find the dominant affected service via the CI -> service graph.
    affected = relationships.affected_services(incident["affected_cis"])

=======
    # Find the affected services for every declared CI. Freshness is judged
    # against the RFC's `submitted_at`, not wall-clock time, so a classification
    # is reproducible: the same RFC always produces the same verdict.
    affected = relationships.affected_services(rfc["affected_cis"], now=submitted_at)
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28
    trace.append({
        "step": "01_resolve",
        "action": f"affected_services({incident['affected_cis']})",
        "result": affected,
    })

<<<<<<< HEAD
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
=======
    if not affected:
        return _refuse(trace, "RFC declared no affected CIs.")

    # Multi-CI refusal ladder: any unknown / low-confidence / stale edge
    # disqualifies the whole change. We will not act on partial context.
    failure = _first_unreliable(affected)
    if failure is not None:
        return _refuse(trace, failure)
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28

    # All edges are reliable. Pick the highest-confidence edge as the primary
    # service for downstream rule evaluation.
    primary = max(affected, key=lambda a: a["confidence"])
    service = meaning.resolve_service(primary["service_id"])
    trace.append({
        "step": "01_resolve",
        "action": f"resolve_service({primary['service_id']})",
        "result": service,
    })

    # ---------- 02 TRAVERSE ----------
<<<<<<< HEAD
    # What depends on this service, and what does it depend on?
    downstream = relationships.downstream_services(service["id"])
    upstream = relationships.upstream_services(service["id"])
    connected_ids = relationships.connected_service_ids(service["id"])

=======
    # What else depends on this service? We resolve each downstream id back to
    # a full Service entity so the rules layer can see tier and DORA status.
    downstream_edges = relationships.downstream_services(service["id"])
    downstream_services = [
        meaning.resolve_service(d["service_id"]) for d in downstream_edges
    ]
    downstream_services = [s for s in downstream_services if s]
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28
    trace.append({
        "step": "02_traverse",
        "action": f"downstream_services({service['id']})",
        "result": [
            {
                "service_id": s["id"],
                "name": s["name"],
                "tier": s["tier"],
                "dora_regulated": s["dora_regulated"],
            }
            for s in downstream_services
        ],
    })
    trace.append({
        "step": "02_traverse",
        "action": f"upstream_services({service['id']})",
        "result": upstream,
    })

    # ---------- 03 EVALUATE ----------
<<<<<<< HEAD
    # Run all rules: priority calculation, runbook matching, SLA check.
    rule_results = rules.evaluate_all(incident, service, downstream, upstream)
=======
    rule_results = rules.evaluate_all(rfc, service)
    rule_results["downstream_blast"] = rules.check_downstream_blast(service, downstream_services)
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28
    trace.append({
        "step": "03_evaluate",
        "action": f"evaluate_all(incident={incident['id']}, service={service['id']})",
        "result": rule_results,
    })

    # ---------- 04 RECALL ----------
<<<<<<< HEAD
    # Find precedent for this type of incident on this service.
    prior = history.similar_incidents(
        service["id"], incident.get("symptom_category", "error")
    )
=======
    template_match = rule_results["template_match"]
    if template_match["template_id"]:
        prior = history.similar_changes(service["id"], template_match["template_id"])
    else:
        prior = {"found": 0, "success": 0, "incident": 0, "linked_incidents": [], "most_recent": None}
    rule_results["precedent_check"] = rules.check_precedent(prior)
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28
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


<<<<<<< HEAD
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
=======
def _emit(result: dict, rfc: dict) -> dict:
    """
    Append the decision to the audit log so the agent's own behaviour becomes
    queryable history. Closes the loop with the history layer: tomorrow's
    classifications can see today's decisions. Returns the result unchanged.
    """
    if config.AUDIT_LOG_PATH is None:
        return result
    audit_path = ROOT_DIR / config.AUDIT_LOG_PATH
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    decision = result["decision"]
    entry = {
        "type": "rfc_classified",
        "rfc_id": rfc.get("id"),
        "classification": decision.get("classification"),
        "route": decision.get("route"),
        "reason": decision.get("reason"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return result


def _first_unreliable(affected: list[dict]) -> str | None:
    """
    Walk every CI -> service edge for the RFC. Return the first reason the
    edge is not safe to act on, or None if every edge is reliable.

    The order of checks (unknown → low confidence → stale) is the refusal
    ladder: each rung is a different way the meaning/relationships layers can
    fail to give the agent confident ground truth.
    """
    for a in affected:
        if a.get("service_id") is None:
            return f"CI {a['ci_id']} not found in CMDB. Refusing to act on incomplete context."
        if a["confidence"] < config.MIN_EDGE_CONFIDENCE:
            return (
                f"CI {a['ci_id']} -> service mapping confidence {a['confidence']:.2f} "
                f"is below threshold {config.MIN_EDGE_CONFIDENCE}. "
                "Refusing to act on unreliable dependency data."
            )
        if not a["fresh"]:
            return (
                f"CI {a['ci_id']} -> service mapping is {a['age_days']} days old "
                f"(threshold: {config.MAX_EDGE_AGE_DAYS}). "
                "Refusing to act on stale context."
            )
    return None


def _decide(rfc: dict, service: dict, rule_results: dict, prior: dict, trace: list) -> dict:
    """
    Turn the gathered context into a classification.

    Rule order is the order of firmness:
      1. DORA — regulatory, non-negotiable
      2. Downstream blast — direct service may be safe, blast radius is not
      3. Freeze window — calendar, non-negotiable
      4. Precedent — risk-based escalation despite a clean template
      5. Template threshold — no template fits, route to CAB
      6. Auto-approve
    """
    # 1. DORA override.
    if rule_results["dora_override"]["override"]:
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_fast_track",
            "reason": rule_results["dora_override"]["reason"],
            "pre_brief": _build_pre_brief(service, rule_results, prior),
        }
        trace.append({"step": "05_act", "action": "decide", "result": decision})
        return {"decision": decision, "trace": trace}

    # 2. Downstream blast.
    blast = rule_results["downstream_blast"]
    if blast["escalate"]:
        names = ", ".join(t["name"] for t in blast["triggers"])
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_review",
            "reason": (
                f"Blast radius: {names} (DORA-regulated or critical) depends on "
                f"{service['name']}. Direct service is safe but downstream impact "
                "requires CAB review."
            ),
            "pre_brief": _build_pre_brief(service, rule_results, prior),
        }
        trace.append({"step": "05_act", "action": "decide", "result": decision})
        return {"decision": decision, "trace": trace}

    # 3. Freeze window.
    fw = rule_results["freeze_window"]
    if fw["in_freeze"]:
        field_label = "Planned execution" if fw["checked_field"] == "planned_start_at" else "Submission time"
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_review",
            "reason": (
                f"{field_label} ({fw['checked_at']}) falls in freeze window: {fw['window']}."
            ),
        }
        trace.append({"step": "05_act", "action": "decide", "result": decision})
        return {"decision": decision, "trace": trace}

    # 4. Precedent gate.
    pc = rule_results["precedent_check"]
    if pc["escalate"]:
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_review",
            "reason": (
                f"Precedent: {pc['incidents']}/{pc['sample_size']} prior changes caused incidents "
                f"(rate {pc['incident_rate']:.2f} > {config.PRECEDENT_INCIDENT_RATE_THRESHOLD}). "
                "Escalating despite template match."
            ),
            "pre_brief": _build_pre_brief(service, rule_results, prior),
        }
        trace.append({"step": "05_act", "action": "decide", "result": decision})
        return {"decision": decision, "trace": trace}

    # 5. Template threshold.
    match = rule_results["template_match"]
    if match["score"] < config.TEMPLATE_MATCH_THRESHOLD:
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_review",
            "reason": f"No standard template matched (best score {match['score']:.2f}).",
        }
        trace.append({"step": "05_act", "action": "decide", "result": decision})
        return {"decision": decision, "trace": trace}

    # 6. Auto-approve.
    decision = {
        "rfc_id": rfc["id"],
        "classification": "standard",
        "route": "auto_approve",
        "template": match["template_id"],
        "template_match_score": match["score"],
        "precedent": f"{prior['success']}/{prior['found']} prior successes",
        "reason": "Template matched, DORA clear, blast clear, freeze clear, precedent acceptable.",
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28
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


<<<<<<< HEAD
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
=======
def _build_pre_brief(service: dict, rule_results: dict, prior: dict) -> dict:
    """Package context for the CAB — the human value the agent adds."""
    brief = {
        "service": service["name"],
        "service_tier": service["tier"],
        "dora_regulated": service.get("dora_regulated", False),
        "template_match": rule_results["template_match"]["template_id"],
        "template_score": rule_results["template_match"]["score"],
    }
    blast = rule_results.get("downstream_blast", {})
    if blast.get("escalate"):
        brief["downstream_triggers"] = blast["triggers"]
    if prior and prior.get("found"):
        brief["prior_changes"] = prior["found"]
        brief["prior_success"] = prior["success"]
        brief["prior_incidents"] = prior["incident"]
        if prior["linked_incidents"]:
            brief["related_incidents"] = prior["linked_incidents"]
    return brief
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28


def _refuse(trace: list, reason: str) -> dict:
    """The refusal ladder. Always return a trace."""
    decision = {
        "priority": "refused",
        "route": "manual_triage",
        "reason": reason,
    }
    trace.append({"step": "05_act", "action": "refuse", "result": decision})
    return {"decision": decision, "trace": trace}
