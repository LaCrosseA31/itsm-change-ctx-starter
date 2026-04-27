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

Untrusted input boundary: `rfc["description"]` is engineer-authored free text
and is treated as untrusted — it is deliberately never read by the agent.
Only structured fields (id, title, affected_cis, submitted_at) influence the
classification.
"""
from datetime import datetime

from agent import config, history, meaning, relationships, rules


def classify(rfc: dict) -> dict:
    """
    Classify an RFC as standard, normal, or refused, with a full trace.

    The trace is the audit log for the decision: every entry records which
    layer was called and what it returned. Any reason in the final decision
    must be traceable back to one of these entries.
    """
    trace: list[dict] = []
    submitted_at = datetime.fromisoformat(rfc["submitted_at"].replace("Z", "+00:00"))

    # ---------- 01 RESOLVE ----------
    # Find the affected services for every declared CI. Freshness is judged
    # against the RFC's `submitted_at`, not wall-clock time, so a classification
    # is reproducible: the same RFC always produces the same verdict.
    affected = relationships.affected_services(rfc["affected_cis"], now=submitted_at)
    trace.append({
        "step": "01_resolve",
        "action": f"affected_services({rfc['affected_cis']})",
        "result": affected,
    })

    if not affected:
        return _refuse(trace, "RFC declared no affected CIs.")

    # Multi-CI refusal ladder: any unknown / low-confidence / stale edge
    # disqualifies the whole change. We will not act on partial context.
    failure = _first_unreliable(affected)
    if failure is not None:
        return _refuse(trace, failure)

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
    # What else depends on this service? We resolve each downstream id back to
    # a full Service entity so the rules layer can see tier and DORA status.
    downstream_edges = relationships.downstream_services(service["id"])
    downstream_services = [
        meaning.resolve_service(d["service_id"]) for d in downstream_edges
    ]
    downstream_services = [s for s in downstream_services if s]
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

    # ---------- 03 EVALUATE ----------
    rule_results = rules.evaluate_all(rfc, service)
    rule_results["downstream_blast"] = rules.check_downstream_blast(service, downstream_services)
    trace.append({
        "step": "03_evaluate",
        "action": f"evaluate_all(rfc={rfc['id']}, service={service['id']})",
        "result": rule_results,
    })

    # ---------- 04 RECALL ----------
    template_match = rule_results["template_match"]
    if template_match["template_id"]:
        prior = history.similar_changes(service["id"], template_match["template_id"])
    else:
        prior = {"found": 0, "success": 0, "incident": 0, "linked_incidents": [], "most_recent": None}
    rule_results["precedent_check"] = rules.check_precedent(prior)
    trace.append({
        "step": "04_recall",
        "action": f"similar_changes({service['id']}, {template_match['template_id']})",
        "result": prior,
    })

    # ---------- 05 ACT ----------
    return _decide(rfc, service, rule_results, prior, trace)


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
    if rule_results["freeze_window"]["in_freeze"]:
        decision = {
            "rfc_id": rfc["id"],
            "classification": "normal",
            "route": "CAB_review",
            "reason": f"In freeze window: {rule_results['freeze_window']['window']}",
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


def _refuse(trace: list, reason: str) -> dict:
    """The refusal ladder. Always return a trace."""
    decision = {
        "classification": "refused",
        "route": "CAB_review",
        "reason": reason,
    }
    trace.append({"step": "05_act", "action": "refuse", "result": decision})
    return {"decision": decision, "trace": trace}
