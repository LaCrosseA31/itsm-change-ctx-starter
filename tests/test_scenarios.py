"""
Tests that reproduce the scenarios from the Worked Example (Phase 5).
Run with: pytest -v
"""
import json
from pathlib import Path

import jsonschema
import pytest

from agent import config
from agent.harness import classify

DATA_DIR = Path(__file__).parent.parent / "data"
ROOT_DIR = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _isolate_audit_log(tmp_path, monkeypatch):
    """
    The agent appends every decision to a JSONL audit log. Tests redirect that
    log to a per-test temp file so concurrent runs don't pollute each other and
    no on-disk artifact survives the test run.
    """
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", str(tmp_path / "audit_log.jsonl"))


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
    Scenario 4: cert rotation whose planned execution falls in the spring
    patch freeze window.
    Expected: routed to CAB review with the freeze name in the reason, and
    the trace records that the rule consulted planned_start_at.
    """
    rfc = _load_rfc("RFC-9920")
    result = classify(rfc)
    assert result["decision"]["classification"] == "normal"
    assert result["decision"]["route"] == "CAB_review"
    assert "freeze" in result["decision"]["reason"].lower()
    evaluate_step = next(e for e in result["trace"] if e["step"] == "03_evaluate")
    assert evaluate_step["result"]["freeze_window"]["checked_field"] == "planned_start_at"


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


def test_scenario_7_planned_start_in_freeze_only_caught_by_planned_check():
    """
    Scenario 7: cert rotation submitted *before* the spring patch freeze
    begins, but planned to execute during it. The submission timestamp alone
    would let this auto-approve — only checking planned_start_at catches it.

    This is the lesson behind the planned_start_at field: real CAB freeze
    policy gates on execution time, not on when the engineer typed the RFC.
    """
    rfc = _load_rfc("RFC-9923")
    result = classify(rfc)
    assert result["decision"]["classification"] == "normal"
    assert result["decision"]["route"] == "CAB_review"
    assert "freeze" in result["decision"]["reason"].lower()
    assert "planned execution" in result["decision"]["reason"].lower()
    evaluate_step = next(e for e in result["trace"] if e["step"] == "03_evaluate")
    fw = evaluate_step["result"]["freeze_window"]
    assert fw["checked_field"] == "planned_start_at"
    assert fw["checked_at"] == rfc["planned_start_at"]


def test_freeze_window_falls_back_to_submitted_at_when_planned_absent():
    """
    Legacy RFCs without a planned_start_at field fall back to checking
    submitted_at — a clean fallback so the rule still produces a verdict
    rather than crashing on a missing field.
    """
    from agent.rules import check_freeze_window
    legacy_rfc_in_freeze = {
        "id": "RFC-LEGACY-1",
        "submitted_at": "2026-04-24T10:00:00Z",
    }
    result = check_freeze_window(legacy_rfc_in_freeze)
    assert result["in_freeze"] is True
    assert result["checked_field"] == "submitted_at"

    legacy_rfc_outside_freeze = {
        "id": "RFC-LEGACY-2",
        "submitted_at": "2026-04-21T10:00:00Z",
    }
    result = check_freeze_window(legacy_rfc_outside_freeze)
    assert result["in_freeze"] is False
    assert result["checked_field"] == "submitted_at"


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


def test_emergency_short_circuit_bypasses_reasoning():
    """
    Emergency changes are declared by humans, never by the agent.
    The harness must short-circuit before resolving CIs or evaluating rules.
    """
    rfc = _load_rfc("RFC-9930")
    result = classify(rfc)
    assert result["decision"]["classification"] == "emergency"
    assert result["decision"]["route"] == "ECAB_review"
    # Only the intake step should run.
    steps = [e["step"] for e in result["trace"]]
    assert steps == ["00_intake"]


def test_kill_switch_refuses_everything(monkeypatch):
    """
    When the kill-switch is engaged the agent refuses every classification —
    even on RFCs that would otherwise auto-approve.
    """
    monkeypatch.setattr(config, "KILL_SWITCH", True)
    rfc = _load_rfc("RFC-9812")
    result = classify(rfc)
    assert result["decision"]["classification"] == "refused"
    assert "kill-switch" in result["decision"]["reason"].lower()


def test_schema_validation_rejects_malformed_rfc():
    """
    A malformed RFC fails loudly at the boundary, not deep inside reasoning.
    Here we drop the required `affected_cis` field.
    """
    rfc = _load_rfc("RFC-9812").copy()
    del rfc["affected_cis"]
    with pytest.raises(jsonschema.ValidationError):
        classify(rfc)


def test_audit_log_records_every_decision(tmp_path, monkeypatch):
    """
    Every classification — including refusals and emergencies — must be
    appended to the audit log so the agent's behaviour is reviewable.
    """
    audit_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", str(audit_path))
    for rfc_id in ["RFC-9812", "RFC-9903", "RFC-9930"]:
        classify(_load_rfc(rfc_id))
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    entries = [json.loads(line) for line in lines]
    assert [e["rfc_id"] for e in entries] == ["RFC-9812", "RFC-9903", "RFC-9930"]
    assert {e["classification"] for e in entries} == {"standard", "refused", "emergency"}


def test_every_decision_has_a_trace():
    """
    The agent must never return a decision without a trace.
    Groundedness is non-negotiable.
    """
    for rfc_id in ["RFC-9812", "RFC-9847", "RFC-9903", "RFC-9920", "RFC-9921", "RFC-9922", "RFC-9923", "RFC-9930"]:
        rfc = _load_rfc(rfc_id)
        result = classify(rfc)
        assert "trace" in result
        assert len(result["trace"]) >= 1
