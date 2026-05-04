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
| Types | `agent/types.py` | Documented contracts each layer publishes |
| Validation | `agent/validation.py` | Enforce schemas at every entity boundary |
| Config | `agent/config.py` | All thresholds and policy knobs in one place |

## Quick start

```bash
pip install -r requirements.txt
<<<<<<< HEAD
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
=======
python classify.py RFC-9812   # Auto-approve scenario
python classify.py RFC-9847   # DORA override scenario
python classify.py RFC-9903   # Low-confidence refusal scenario
python classify.py RFC-9920   # Freeze window scenario (planned execution in freeze)
python classify.py RFC-9921   # Precedent override scenario
python classify.py RFC-9922   # Downstream blast radius scenario
python classify.py RFC-9923   # Submission clean, planned execution in freeze
pytest -v                     # Run all seven as tests
```

## The seven scenarios

- **RFC-9812** — cert rotation on `internal-dashboard` (non-regulated) → `standard` / auto-approve
- **RFC-9847** — cert rotation on `payment-api` (DORA-regulated) → `normal` / CAB fast track. The DORA override fires even though the template matches.
- **RFC-9903** — cert rotation on `fraud-check` (stale CMDB edge, confidence 0.72) → `refused`. The agent refuses to act on unreliable dependency data.
- **RFC-9920** — cert rotation on `internal-dashboard` whose `planned_start_at` falls inside the spring patch freeze → `normal` / CAB review. Calendar policy beats template match.
- **RFC-9921** — cert rotation on `marketing-site` whose recent history is 3-of-5 incidents → `normal` / CAB review. The history layer earns its keep: a clean template plus a bumpy track record is a reason to escalate, not auto-approve.
- **RFC-9922** — cert rotation on `notification-service` (non-DORA, standard tier) on which DORA-regulated `payment-api` depends → `normal` / CAB review. Direct service is safe; blast radius is not.
- **RFC-9923** — cert rotation on `internal-dashboard` submitted *before* the spring patch freeze begins, but with `planned_start_at` inside it → `normal` / CAB review. Demonstrates that freeze policy must gate on planned execution time, not on submission time. Submission timing alone would let this auto-approve.

All design knobs (confidence thresholds, freshness window, precedent rate, template match floor, kill-switch, audit log path) live in `agent/config.py`.

## Boundary controls

- **Schema validation** — every RFC is validated against `schemas/change.json` at the entry to `classify()`; loaded services and templates are validated against their schemas. Malformed entities fail loudly before any reasoning runs.
- **Planned vs submitted time** — RFCs may carry an optional `planned_start_at`. The freeze-window rule consults it when present and falls back to `submitted_at` otherwise, so freeze policy gates on when the change runs, not on when the engineer typed it in. The trace records which timestamp the rule used.
- **Emergency short-circuit** — RFCs with `change_type: "emergency"` bypass the reasoning loop and route straight to the ECAB. Humans declare emergencies; the agent never does.
- **Kill-switch** — set `KILL_SWITCH = True` in `agent/config.py` and every classification refuses. A single flag stops the world.
- **Audit log** — every decision (including refusals and emergencies) is appended to `data/audit_log.jsonl`. The agent's own history becomes queryable context for the history layer.
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28

## Where production would differ

- Replace JSON files with real systems: Neo4j for the graph, Open Policy Agent for rules, an event store for history.
- Replace keyword runbook matching with embeddings.
- Wire freshness thresholds to real data-pipeline SLAs.
<<<<<<< HEAD
- Add a kill-switch and audit log.
- Integrate with PagerDuty / Opsgenie for routing.
=======
- Move the kill-switch behind a centralised feature-flag service.
>>>>>>> 8dbe177952bd4455e20269516099af3c082a3b28

See the Worked Example document for the design rationale.
