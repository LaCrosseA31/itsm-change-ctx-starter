# Incident Management Context Layer

A working reference implementation of the agentic context layer for ITSM Incident Management. It triages incoming incidents by assigning a priority level (`P1`–`P4`) or `refused` (insufficient context), matches resolution runbooks, tracks SLA compliance, detects correlated incident storms — and produces a full reasoning trace for every decision.

This is a **teaching artifact**, not production code. It uses lightweight libraries so it runs on any laptop without external services.

## What's inside

| Component | Lives in | What it answers |
|---|---|---|
| Meaning | `agent/meaning.py` + `schemas/` | What does this ID or name refer to? |
| Relationships | `agent/relationships.py` | How are these entities connected? (blast radius) |
| Rules | `agent/rules.py` | What priority, runbook, and SLA apply to these facts? |
| History | `agent/history.py` | Has this kind of incident happened before? Are related incidents active? |
| Harness | `agent/harness.py` | The five-step reasoning loop |

## Quick start

```bash
pip install -r requirements.txt
python triage.py INC-5010   # P1 critical outage
python triage.py INC-5023   # P3 runbook auto-remediation
python triage.py INC-5031   # Correlation escalation
python triage.py INC-5044   # Low-confidence refusal
python triage.py INC-5052   # P4 low-impact incident
python triage.py INC-5060   # SLA tracking
pytest -v                   # Run all tests
```

## The six scenarios

| Incident | Service | Key Feature | Result |
|---|---|---|---|
| **INC-5010** | payment-api (critical, DORA) | P1 outage, 12K users, SLA tracking | `P1` / major_incident_manager |
| **INC-5023** | internal-dashboard (non-critical) | Disk warning + runbook auto-remediation | `P3` / auto_remediate |
| **INC-5031** | notification-service (standard) | Correlation with INC-5010 via dependency graph | Escalated / major_incident_manager |
| **INC-5044** | fraud-check (critical, DORA) | CMDB edge confidence 0.72 < 0.80 threshold | `refused` / manual_triage |
| **INC-5052** | marketing-site (non-critical) | Low-impact error, 80 users, no runbook | `P4` / service_desk |
| **INC-5060** | payment-api (critical, DORA) | Degradation with SLA clock ticking | `P1`/`P2` / major_incident_manager |

## Robust features

### Priority calculation
Priority is determined by the **most severe signal** across five factors:
- **Service tier** — critical services floor at P2
- **Symptom category** — outage = P1, degradation = P2, error = P3, threshold_warning = P4
- **Affected user count** — 10K+ = P1, 1K+ = P2, 100+ = P3
- **Blast radius** — downstream service dependencies amplify priority
- **DORA regulation** — DORA-regulated services cannot go below P2

### Runbook matching
Incidents are matched against known runbooks using keyword patterns. If a runbook is marked `auto_remediable`, the agent routes to automated remediation instead of a human responder.

### SLA tracking
Each priority level has response and resolution time targets. The agent calculates elapsed time, flags breaches, and warns when approaching thresholds (80% of target).

### Correlation detection (storm detection)
The agent checks for open or recent incidents on the same or connected services within a 4-hour window. If 2+ correlated incidents are found, it flags an incident storm and escalates priority by one level.

## Where production would differ

- Replace JSON files with real systems: Neo4j for the graph, Open Policy Agent for rules, an event store for history.
- Replace keyword runbook matching with embeddings.
- Wire freshness thresholds to real data-pipeline SLAs.
- Add a kill-switch and audit log.
- Integrate with PagerDuty / Opsgenie for routing.

See the Worked Example document for the design rationale.
