"""
<<<<<<< HEAD
Tests that reproduce the six scenarios for the Incident Management context layer.
=======
Tests that reproduce the scenarios from the Worked Example (Phase 5).
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28
Run with: pytest -v
"""
import json
from pathlib import Path

import jsonschema
import pytest
<<<<<<< HEAD
from agent.harness import triage
=======

from agent import config
from agent.harness import classify
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28

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


def _load_incident(incident_id: str) -> dict:
    with open(DATA_DIR / "incidents.json") as f:
        for inc in json.load(f)["incidents"]:
            if inc["id"] == incident_id:
                return inc
    pytest.fail(f"Incident {incident_id} not found")


# ── Scenario 1: P1 critical outage ─────────────────────────────────

def test_p1_critical_outage():
    """
    INC-5010: payment-api returning 500 errors to 12,000 users.
    Expected: P1 priority, routed to major incident manager.
    """
    inc = _load_incident("INC-5010")
    result = triage(inc)
    assert result["decision"]["priority"] == "P1"
    assert result["decision"]["route"] == "major_incident_manager"


# ── Scenario 2: Runbook auto-remediation ────────────────────────────

def test_runbook_auto_remediation():
    """
    INC-5023: internal-dashboard disk usage at 92%.
    Expected: runbook RB-DISK-CLEANUP matched, auto-remediation suggested.
    """
    inc = _load_incident("INC-5023")
    result = triage(inc)
    d = result["decision"]
    assert d["priority"] in ("P3", "P4")
    assert "runbook" in d
    assert d["runbook"]["id"] == "RB-DISK-CLEANUP"
    assert d["runbook"]["auto_remediable"] is True
    assert d["route"] == "auto_remediate"


# ── Scenario 3: Correlation escalation ──────────────────────────────

def test_correlation_escalation():
    """
    INC-5031: notification-service delivery delays.
    payment-api (svc-042) depends on notification-service (svc-089), so svc-042
    is downstream of svc-089. With INC-5010 open on svc-042 at the same time,
    the correlation detector finds 2 incidents in the cluster → storm detected.
    Expected: correlation detected, storm escalation applied, major incident route.
    """
    inc = _load_incident("INC-5031")
    result = triage(inc)
    d = result["decision"]
    # Should be escalated due to storm detection.
    assert "correlations" in d
    assert d["correlations"]["storm_detected"] is True
    assert d["route"] == "major_incident_manager"


# ── Scenario 4: Low-confidence refusal ──────────────────────────────

def test_low_confidence_refusal():
    """
    INC-5044: fraud-check latency spike.
    CMDB edge for ci-fraud-tls has confidence 0.72 (below 0.80 threshold).
    Expected: refuse to auto-triage.
    """
    inc = _load_incident("INC-5044")
    result = triage(inc)
    assert result["decision"]["priority"] == "refused"
    assert "confidence" in result["decision"]["reason"].lower()


<<<<<<< HEAD
# ── Scenario 5: P4 low-impact incident ──────────────────────────────

def test_p4_low_impact():
    """
    INC-5052: marketing-site 404 errors on /pricing.
    Non-critical service, 80 users, threshold-warning symptom.
    Expected: P4, routed to service desk.
    """
    inc = _load_incident("INC-5052")
    result = triage(inc)
    assert result["decision"]["priority"] == "P4"
    assert result["decision"]["route"] == "service_desk"


# ── Scenario 6: SLA tracking on high-priority incident ──────────────

def test_sla_tracking():
    """
    INC-5060: payment-api degraded response times.
    Expected: SLA information is attached to the decision.
    """
    inc = _load_incident("INC-5060")
    result = triage(inc)
    d = result["decision"]
    assert d["priority"] in ("P1", "P2")
    assert "sla" in d
    assert d["sla"]["has_sla"] is True
    assert "response_target_minutes" in d["sla"]
    assert "resolution_target_minutes" in d["sla"]


# ── Scenario 7: DORA floor ──────────────────────────────────────────

def test_dora_regulated_floor():
    """
    INC-5060: incident on payment-api, which is DORA-regulated.
    DORA-regulated services cannot go below P2 regardless of other factors.
    """
    inc = _load_incident("INC-5060")
    result = triage(inc)
    # payment-api is DORA-regulated, so priority must be P1 or P2.
    assert result["decision"]["priority"] in ("P1", "P2")


# ── Cross-cutting: every decision has a trace ────────────────────────
=======
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

>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28

def test_every_decision_has_a_trace():
    """
    The agent must never return a decision without a trace.
    Groundedness is non-negotiable.
    """
<<<<<<< HEAD
    for inc_id in ["INC-5010", "INC-5023", "INC-5031", "INC-5044", "INC-5052", "INC-5060"]:
        inc = _load_incident(inc_id)
        result = triage(inc)
=======
    for rfc_id in ["RFC-9812", "RFC-9847", "RFC-9903", "RFC-9920", "RFC-9921", "RFC-9922", "RFC-9923", "RFC-9930"]:
        rfc = _load_rfc(rfc_id)
        result = classify(rfc)
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28
        assert "trace" in result
        assert len(result["trace"]) >= 1
