# Change Management Context Layer

A working reference implementation of the agentic context layer from the ITSM Senior Track worked example. It classifies incoming Requests for Change (RFCs) as `standard` (auto-approve), `normal` (route to CAB), or `refused` (insufficient context) — and produces a full reasoning trace for every decision.

This is a **teaching artifact**, not production code. It uses lightweight libraries so it runs on any laptop without external services.

## What's inside

| Component | Lives in | What it answers |
|---|---|---|
| Meaning | `agent/meaning.py` + `schemas/` | What does this ID or name refer to? |
| Relationships | `agent/relationships.py` | How are these entities connected? |
| Rules | `agent/rules.py` | What policy applies to these facts? |
| History | `agent/history.py` | Has this kind of change happened before? |
| Harness | `agent/harness.py` | The five-step reasoning loop |
| Types | `agent/types.py` | Documented contracts each layer publishes |
| Validation | `agent/validation.py` | Enforce schemas at every entity boundary |
| Config | `agent/config.py` | All thresholds and policy knobs in one place |

## Quick start

```bash
pip install -r requirements.txt
python classify.py RFC-9812   # Auto-approve scenario
python classify.py RFC-9847   # DORA override scenario
python classify.py RFC-9903   # Low-confidence refusal scenario
python classify.py RFC-9920   # Freeze window scenario
python classify.py RFC-9921   # Precedent override scenario
python classify.py RFC-9922   # Downstream blast radius scenario
pytest -v                     # Run all six as tests
```

## The six scenarios

- **RFC-9812** — cert rotation on `internal-dashboard` (non-regulated) → `standard` / auto-approve
- **RFC-9847** — cert rotation on `payment-api` (DORA-regulated) → `normal` / CAB fast track. The DORA override fires even though the template matches.
- **RFC-9903** — cert rotation on `fraud-check` (stale CMDB edge, confidence 0.72) → `refused`. The agent refuses to act on unreliable dependency data.
- **RFC-9920** — cert rotation on `internal-dashboard` submitted during the spring patch freeze → `normal` / CAB review. Calendar policy beats template match.
- **RFC-9921** — cert rotation on `marketing-site` whose recent history is 3-of-5 incidents → `normal` / CAB review. The history layer earns its keep: a clean template plus a bumpy track record is a reason to escalate, not auto-approve.
- **RFC-9922** — cert rotation on `notification-service` (non-DORA, standard tier) on which DORA-regulated `payment-api` depends → `normal` / CAB review. Direct service is safe; blast radius is not.

All design knobs (confidence thresholds, freshness window, precedent rate, template match floor, kill-switch, audit log path) live in `agent/config.py`.

## Boundary controls

- **Schema validation** — every RFC is validated against `schemas/change.json` at the entry to `classify()`; loaded services and templates are validated against their schemas. Malformed entities fail loudly before any reasoning runs.
- **Emergency short-circuit** — RFCs with `change_type: "emergency"` bypass the reasoning loop and route straight to the ECAB. Humans declare emergencies; the agent never does.
- **Kill-switch** — set `KILL_SWITCH = True` in `agent/config.py` and every classification refuses. A single flag stops the world.
- **Audit log** — every decision (including refusals and emergencies) is appended to `data/audit_log.jsonl`. The agent's own history becomes queryable context for the history layer.

## Where production would differ

- Replace JSON files with real systems: Neo4j for the graph, Open Policy Agent for rules, an event store for history.
- Replace keyword template matching with embeddings.
- Wire freshness thresholds to real data-pipeline SLAs.
- Move the kill-switch behind a centralised feature-flag service.

See the Worked Example document for the design rationale.
