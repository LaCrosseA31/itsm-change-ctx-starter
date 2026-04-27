"""
Central configuration for the change-management context layer.

All thresholds and policy knobs live here so the design is visible in one place
and there is a single source of truth for the harness, relationships, rules,
and history modules.

Production note: in a real system most of these would be owned by the CAB and
sourced from a policy service (e.g. OPA bundles), not hard-coded in Python.
"""

# Relationships layer.
MIN_EDGE_CONFIDENCE = 0.80
MAX_EDGE_AGE_DAYS = 30

# Rules layer.
TEMPLATE_MATCH_THRESHOLD = 0.20
PRECEDENT_INCIDENT_RATE_THRESHOLD = 0.20
PRECEDENT_MIN_SAMPLE = 3

# History layer.
HISTORY_LOOKBACK_K = 10
