"""
triage.py — run the agent against an incident and print a human-readable trace.

Usage:
    python triage.py INC-5010     # P1 critical outage on payment-api
    python triage.py INC-5023     # P3 disk warning — runbook auto-remediation
    python triage.py INC-5031     # P2 correlation escalation (notification delays)
    python triage.py INC-5044     # Refused — low-confidence CMDB edge
    python triage.py INC-5052     # P4 low-impact marketing-site error
    python triage.py INC-5060     # P1 SLA escalation on payment-api
"""
import json
import sys
from pathlib import Path
from agent.harness import triage

DATA_DIR = Path(__file__).parent / "data"


def load_incident(incident_id: str) -> dict:
    with open(DATA_DIR / "incidents.json") as f:
        incidents = json.load(f)["incidents"]
    for inc in incidents:
        if inc["id"] == incident_id:
            return inc
    raise SystemExit(f"Incident {incident_id} not found in data/incidents.json")


def _fmt(val) -> str:
    """Compact pretty-print for trace values."""
    s = json.dumps(val, default=str, indent=2)
    if len(s) <= 200:
        return s.replace("\n", " ").replace("  ", " ")
    return s


def print_trace(result: dict) -> None:
    print()
    print("=" * 70)
    print("  AGENT TRACE")
    print("=" * 70)
    for entry in result["trace"]:
        print(f"\n[{entry['step']}] {entry['action']}")
        print(f"  -> {_fmt(entry['result'])}")

    print()
    print("=" * 70)
    print("  TRIAGE DECISION")
    print("=" * 70)
    d = result["decision"]
    print(f"  Priority       : {d.get('priority', 'UNKNOWN').upper()}")
    print(f"  Route          : {d.get('route', 'n/a')}")
    print(f"  Reason         : {d.get('reason', 'n/a')}")

    if "runbook" in d:
        rb = d["runbook"]
        print(f"  Runbook        : {rb['id']} — {rb['name']} (score: {rb['score']:.2f})")
        if rb.get("auto_remediable"):
            print(f"                   ** AUTO-REMEDIABLE **")
        print(f"  Est. Resolution: {rb.get('estimated_resolution_minutes', 'n/a')} minutes")

    if "sla" in d:
        sla = d["sla"]
        print(f"  SLA Response   : {sla['response_target_minutes']} min target "
              f"({'BREACHED' if sla['response_breached'] else 'NEAR-BREACH' if sla['response_near_breach'] else 'OK'})")
        print(f"  SLA Resolution : {sla['resolution_target_minutes']} min target "
              f"({'BREACHED' if sla['resolution_breached'] else 'NEAR-BREACH' if sla['resolution_near_breach'] else 'OK'})")
        print(f"  Elapsed        : {sla['elapsed_minutes']:.1f} minutes")

    if "correlations" in d:
        corr = d["correlations"]
        print(f"  Correlations   : {len(corr['related_incidents'])} related incident(s): "
              f"{', '.join(corr['related_incidents'])}")
        if corr.get("escalated"):
            print(f"                   ** STORM ESCALATION APPLIED **")

    if "precedent" in d:
        p = d["precedent"]
        print(f"  Precedent      : {p['prior_incidents']} prior — "
              f"{p['resolved']} resolved, {p['escalated']} escalated, "
              f"{p['recurring']} recurring")
        if p.get("avg_resolution_minutes"):
            print(f"  Avg Resolution : {p['avg_resolution_minutes']} minutes")

    print("=" * 70)
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    incident_id = sys.argv[1]
    incident = load_incident(incident_id)
    print(f"\nTriaging {incident['id']} — {incident['title']}")
    result = triage(incident)
    print_trace(result)


if __name__ == "__main__":
    main()
