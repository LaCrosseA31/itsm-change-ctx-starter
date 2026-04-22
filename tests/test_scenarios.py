"""
Tests that reproduce the six scenarios for the Incident Management context layer.
Run with: pytest -v
"""
import json
from pathlib import Path
import pytest
from agent.harness import triage

DATA_DIR = Path(__file__).parent.parent / "data"


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

def test_every_decision_has_a_trace():
    """
    The agent must never return a decision without a trace.
    Groundedness is non-negotiable.
    """
    for inc_id in ["INC-5010", "INC-5023", "INC-5031", "INC-5044", "INC-5052", "INC-5060"]:
        inc = _load_incident(inc_id)
        result = triage(inc)
        assert "trace" in result
        assert len(result["trace"]) >= 1
        assert any(e["step"].startswith("05") for e in result["trace"])
