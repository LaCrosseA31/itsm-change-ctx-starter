"""
Agent harness — the reasoning loop.

Walks the five steps from the deck:
  01 Resolve     — meaning layer resolves the ticket to canonical entities
  02 Traverse    — relationships layer finds what's connected
  03 Evaluate    — rules layer runs policy against facts
  04 Recall      — history layer retrieves precedent
  05 Act         — classification + routing, with a full trace

The key property: every decision is grounded. The trace says exactly which
context item fed which step of the reasoning.
"""
from agent import meaning, relationships, rules, history

# Design decision: minimum edge confidence for the agent to auto-classify.
# Below this, the refusal ladder fires.
MIN_CONFIDENCE_FOR_AUTO = 0.80


def classify(rfc: dict) -> dict:
    """
    Classify an RFC as standard, normal, or route to CAB with a refusal reason.

    Returns a decision dict AND a full trace.
    """
    trace = []

    # ---------- 01 RESOLVE ----------
    # Find the dominant affected service via the CI -> service graph.
    # Meaning resolves each CI; relationships connects CI to service.
    affected = relationships.affected_services(rfc["affected_cis"])

    trace.append({
        "step": "01_resolve",
        "action": f"affected_services({rfc['affected_cis']})",
        "result": affected,
    })

    if not affected or all(a.get("service_id") is None for a in affected):
        return _refuse(trace, "Could not resolve RFC to any known service.")

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
            "Refusing to act on unreliable dependency data.",
        )

    # Refusal 2: stale dependency data.
    if not primary["fresh"]:
        return _refuse(
            trace,
            f"CI-to-service mapping is {primary['age_days']} days old "
            f"(threshold: 30). Refusing to act on stale context.",
        )

    service = meaning.resolve_service(primary["service_id"])
    trace.append({
        "step": "01_resolve",
        "action": f"resolve_service({primary['service_id']})",
        "result": service,
    })

    # ---------- 02 TRAVERSE ----------
    # What else depends on this service?
    downstream = relationships.downstream_services(service["id"])
    trace.append({
        "step": "02_traverse",
        "action": f"downstream_services({service['id']})",
        "result": downstream,
    })

    # ---------- 03 EVALUATE ----------
    # Run all rules.
    rule_results = rules.evaluate_all(rfc, service)
    trace.append({
        "step": "03_evaluate",
        "action": f"evaluate_all(rfc={rfc['id']}, service={service['id']})",
        "result": rule_results,
    })

    # ---------- 04 RECALL ----------
    # Find precedent — but only if a template was matched.
    template_match = rule_results["template_match"]
    if template_match["template_id"]:
        prior = history.similar_changes(service["id"], template_match["template_id"])
    else:
        prior = {"found": 0}
    trace.append({
        "step": "04_recall",
        "action": f"similar_changes({service['id']}, {template_match['template_id']})",
        "result": prior,
    })

    # ---------- 05 ACT ----------
    return _decide(rfc, service, rule_results, prior, trace)


def _decide(rfc: dict, service: dict, rule_results: dict, prior: dict, trace: list) -> dict:
    """Turn the gathered context into a classification."""
    # Non-negotiable: DORA override forces normal.
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

    # Freeze windows always override.
    if rule_results["freeze_window"]["in_freeze"]:
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_review",
            "reason": f"In freeze window: {rule_results['freeze_window']['window']}",
        }
        trace.append({"step": "05_act", "action": "decide", "result": decision})
        return {"decision": decision, "trace": trace}

    # Template must match above threshold.
    match = rule_results["template_match"]
    if match["score"] < rules.TEMPLATE_MATCH_THRESHOLD:
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_review",
            "reason": f"No standard template matched (best score {match['score']:.2f}).",
        }
        trace.append({"step": "05_act", "action": "decide", "result": decision})
        return {"decision": decision, "trace": trace}

    # Auto-approve path.
    decision = {
        "rfc_id": rfc["id"],
        "classification": "standard",
        "route": "auto_approve",
        "template": match["template_id"],
        "template_match_score": match["score"],
        "precedent": f"{prior['success']}/{prior['found']} prior successes",
        "reason": "Template matched above threshold, DORA clear, freeze clear, "
                  "precedent acceptable.",
    }
    trace.append({"step": "05_act", "action": "decide", "result": decision})
    return {"decision": decision, "trace": trace}


def _build_pre_brief(service: dict, rule_results: dict, prior: dict) -> dict:
    """Package context for the CAB — the human value the agent adds."""
    brief = {
        "service": service["name"],
        "service_tier": service["tier"],
        "dora_regulated": service.get("dora_regulated", False),
        "template_match": rule_results["template_match"]["template_id"],
        "template_score": rule_results["template_match"]["score"],
    }
    if prior and prior.get("found"):
        brief["prior_changes"] = prior["found"]
        brief["prior_success"] = prior["success"]
        brief["prior_incidents"] = prior["incident"]
        if prior["linked_incidents"]:
            brief["related_incidents"] = prior["linked_incidents"]
    return brief


def _refuse(trace: list, reason: str) -> dict:
    """The refusal ladder. Always return a trace."""
    decision = {
        "classification": "refused",
        "route": "CAB_review",
        "reason": reason,
    }
    trace.append({"step": "05_act", "action": "refuse", "result": decision})
    return {"decision": decision, "trace": trace}
