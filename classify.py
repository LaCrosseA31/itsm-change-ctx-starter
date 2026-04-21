"""
classify.py — run the agent against an RFC and print a human-readable trace.

Usage:
    python classify.py RFC-9812
    python classify.py RFC-9847     # triggers DORA override
    python classify.py RFC-9903     # triggers low-confidence refusal
"""
import json
import sys
from pathlib import Path
from agent.harness import classify

DATA_DIR = Path(__file__).parent / "data"


def load_rfc(rfc_id: str) -> dict:
    with open(DATA_DIR / "rfcs.json") as f:
        rfcs = json.load(f)["rfcs"]
    for r in rfcs:
        if r["id"] == rfc_id:
            return r
    raise SystemExit(f"RFC {rfc_id} not found in data/rfcs.json")


def _fmt(val) -> str:
    """Compact pretty-print for trace values."""
    s = json.dumps(val, default=str, indent=2)
    if len(s) <= 200:
        return s.replace("\n", " ").replace("  ", " ")
    return s


def print_trace(result: dict) -> None:
    print()
    print("=" * 70)
    print(f"  AGENT TRACE")
    print("=" * 70)
    for entry in result["trace"]:
        print(f"\n[{entry['step']}] {entry['action']}")
        print(f"  → {_fmt(entry['result'])}")

    print()
    print("=" * 70)
    print(f"  DECISION")
    print("=" * 70)
    d = result["decision"]
    print(f"  Classification : {d.get('classification', 'UNKNOWN').upper()}")
    print(f"  Route          : {d.get('route', 'n/a')}")
    print(f"  Reason         : {d.get('reason', 'n/a')}")
    if "precedent" in d:
        print(f"  Precedent      : {d['precedent']}")
    if "pre_brief" in d:
        print(f"  Pre-brief      : {json.dumps(d['pre_brief'], indent=2)}")
    print("=" * 70)
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    rfc_id = sys.argv[1]
    rfc = load_rfc(rfc_id)
    print(f"\nClassifying {rfc['id']} — {rfc['title']}")
    result = classify(rfc)
    print_trace(result)


if __name__ == "__main__":
    main()
