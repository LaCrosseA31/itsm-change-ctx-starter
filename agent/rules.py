"""
Rules layer — policy-as-code.

This module answers: "given the facts, what rules apply, and with what result?"
Rules are layered:
  - TEMPLATE rules (defeasible) — can approve a standard change
  - OVERRIDE rules (non-negotiable) — can force a change to normal regardless

The DORA override is the canonical example: even a perfect template match
cannot auto-approve a change to a DORA-regulated service.

In production, these would be Rego policies evaluated by OPA.
Here they are Python functions — the structure is what matters.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from agent.meaning import all_templates

DATA_DIR = Path(__file__).parent.parent / "data"

# Match threshold — part of the design, not the data.
TEMPLATE_MATCH_THRESHOLD = 0.60


def match_template(rfc: dict, service: dict) -> dict:
    """
    Score the RFC against every template and pick the best match.

    Returns the best template with a score in [0, 1].
    A score below threshold means no template applies — route to CAB.
    """
    title = rfc["title"].lower()
    templates = all_templates()

    best = {"template_id": None, "score": 0.0, "template": None}
    for tpl in templates:
        if service["tier"] not in tpl["allowed_service_tiers"]:
            continue
        # Simple keyword match — production would use NLP / embeddings.
        hits = sum(1 for pat in tpl["match_patterns"] if pat in title)
        score = min(1.0, hits / max(1, len(tpl["match_patterns"])) + (0.4 if hits > 0 else 0.0))
        if score > best["score"]:
            best = {"template_id": tpl["id"], "score": score, "template": tpl}
    return best


def check_freeze_window(submitted_at: str) -> dict:
    """Is the RFC submitted during an active freeze window?"""
    with open(DATA_DIR / "freeze_windows.json") as f:
        data = json.load(f)

    now = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
    for fw in data["freeze_windows"]:
        start = datetime.fromisoformat(fw["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(fw["end"].replace("Z", "+00:00"))
        if start <= now <= end:
            return {"in_freeze": True, "window": fw["name"], "reason": fw["reason"]}

    return {"in_freeze": False}


def check_dora_override(service: dict) -> dict:
    """
    The DORA rule: if a change touches a DORA-regulated service, the classification
    is FORCED to normal regardless of template match.

    This is a non-negotiable override. Regulatory context overrides operational efficiency.
    Always.
    """
    if service.get("dora_regulated", False):
        return {
            "override": True,
            "rule": "DORA-CRITICAL-FUNCTION",
            "reason": f"Service {service['id']} ({service['name']}) is DORA-regulated. "
                      f"All changes to this service require CAB review.",
        }
    return {"override": False}


def evaluate_all(rfc: dict, service: dict) -> dict:
    """Run every rule for this RFC/service pair and return a consolidated result."""
    return {
        "template_match": match_template(rfc, service),
        "freeze_window": check_freeze_window(rfc["submitted_at"]),
        "dora_override": check_dora_override(service),
    }
