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

## Quick start

```bash
pip install -r requirements.txt
python classify.py RFC-9812   # Auto-approve scenario
python classify.py RFC-9847   # DORA override scenario
python classify.py RFC-9903   # Low-confidence refusal scenario
pytest -v                     # Run all three as tests
```

## The three scenarios

- **RFC-9812** — cert rotation on `internal-dashboard` (non-regulated) → `standard` / auto-approve
- **RFC-9847** — cert rotation on `payment-api` (DORA-regulated) → `normal` / CAB fast track. The DORA override fires even though the template matches.
- **RFC-9903** — cert rotation on `fraud-check` (stale CMDB edge, confidence 0.72) → `refused`. The agent refuses to act on unreliable dependency data.

## Where production would differ

- Replace JSON files with real systems: Neo4j for the graph, Open Policy Agent for rules, an event store for history.
- Replace keyword template matching with embeddings.
- Wire freshness thresholds to real data-pipeline SLAs.
- Add a kill-switch and audit log.

See the Worked Example document for the design rationale.
