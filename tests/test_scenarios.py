"""
Tests that reproduce the three scenarios from the Worked Example (Phase 5).
Run with: pytest -v
"""
import json
from pathlib import Path
import pytest
from agent.harness import classify

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_rfc(rfc_id: str) -> dict:
    with open(DATA_DIR / "rfcs.json") as f:
        for r in json.load(f)["rfcs"]:
            if r["id"] == rfc_id:
                return r
    pytest.fail(f"RFC {rfc_id} not found")


def test_scenario_1_standard_autoapproved():
    """
    Scenario 1: cert rotation on a non-regulated, non-critical service.
    Expected: auto-approve as standard.
    """
    rfc = _load_rfc("RFC-9812")
    result = classify(rfc)
    assert result["decision"]["classification"] == "standard"
    assert result["decision"]["route"] == "auto_approve"


def test_scenario_2_dora_override_fires():
    """
    Scenario 2: cert rotation on a DORA-regulated critical service.
    Expected: routed to CAB via the DORA override, even though the template matches.
    """
    rfc = _load_rfc("RFC-9847")
    result = classify(rfc)
    assert result["decision"]["classification"] == "normal"
    assert result["decision"]["route"] == "CAB_fast_track"
    assert "DORA" in result["decision"]["reason"]


def test_scenario_3_low_confidence_refusal():
    """
    Scenario 3: change on a service where the CMDB edge has low confidence.
    Expected: refuse rather than classify.
    """
    rfc = _load_rfc("RFC-9903")
    result = classify(rfc)
    assert result["decision"]["classification"] == "refused"
    assert "confidence" in result["decision"]["reason"].lower()


def test_scenario_4_freeze_window_fires():
    """
    Scenario 4: cert rotation submitted during the spring patch freeze window.
    Expected: routed to CAB review with the freeze name in the reason.
    """
    rfc = _load_rfc("RFC-9920")
    result = classify(rfc)
    assert result["decision"]["classification"] == "normal"
    assert result["decision"]["route"] == "CAB_review"
    assert "freeze" in result["decision"]["reason"].lower()


def test_scenario_5_precedent_overrides_template_match():
    """
    Scenario 5: cert rotation on a non-DORA, non-critical service whose recent
    history is dominated by incidents. Template matches and DORA is clear, but
    precedent forces escalation.
    """
    rfc = _load_rfc("RFC-9921")
    result = classify(rfc)
    assert result["decision"]["classification"] == "normal"
    assert result["decision"]["route"] == "CAB_review"
    assert "precedent" in result["decision"]["reason"].lower()


def test_scenario_6_downstream_blast_radius_escalates():
    """
    Scenario 6: cert rotation on a non-DORA service that a DORA-regulated
    service depends on. The direct service is safe to auto-approve, but the
    blast radius requires CAB review.
    """
    rfc = _load_rfc("RFC-9922")
    result = classify(rfc)
    assert result["decision"]["classification"] == "normal"
    assert result["decision"]["route"] == "CAB_review"
    assert "blast radius" in result["decision"]["reason"].lower()


def test_every_decision_has_a_trace():
    """
    The agent must never return a decision without a trace.
    Groundedness is non-negotiable.
    """
    for rfc_id in ["RFC-9812", "RFC-9847", "RFC-9903", "RFC-9920", "RFC-9921", "RFC-9922"]:
        rfc = _load_rfc(rfc_id)
        result = classify(rfc)
        assert "trace" in result
        assert len(result["trace"]) >= 1
        assert any(e["step"].startswith("05") for e in result["trace"])
