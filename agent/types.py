"""
Type contracts published by each layer of the context.

These TypedDicts are documentation, not runtime enforcement — Python's typing
is structural, so a plain dict still works at call sites. The point is that
each layer's input and output shape is visible in one place. Validation against
JSON schemas (see schemas/) is the runtime guarantee.
"""
from typing import Literal, Optional, TypedDict


Tier = Literal["critical", "standard", "non-critical"]
Classification = Literal["standard", "normal", "refused", "emergency"]


class RFC(TypedDict, total=False):
    """A Request for Change as it enters the agent."""
    id: str
    title: str
    description: str  # untrusted free text — never read by the agent
    submitter: str
    submitted_at: str  # ISO-8601
    affected_cis: list[str]
    change_type: Optional[Literal["standard", "normal", "emergency"]]
    proposed_template_id: str


class Service(TypedDict, total=False):
    id: str
    name: str
    tier: Tier
    dora_regulated: bool
    owner_team: str
    last_validated_at: str


class Template(TypedDict, total=False):
    id: str
    name: str
    description: str
    match_patterns: list[str]
    allowed_service_tiers: list[Tier]
    version: int


class CIServiceEdge(TypedDict, total=False):
    """A resolved CI -> service mapping with confidence and freshness."""
    ci_id: str
    service_id: Optional[str]
    confidence: float
    fresh: bool
    age_days: int
    reason: str  # populated only on failures, e.g. "unknown_ci"


class Precedent(TypedDict, total=False):
    """The history layer's summary of prior similar changes."""
    found: int
    success: int
    incident: int
    linked_incidents: list[str]
    most_recent: Optional[dict]


class TraceEntry(TypedDict):
    """One step in the audit trail of a classification."""
    step: str
    action: str
    result: object


class Decision(TypedDict, total=False):
    rfc_id: str
    classification: Classification
    route: str
    reason: str
    template: str
    template_match_score: float
    precedent: str
    pre_brief: dict


class ClassifyResult(TypedDict):
    decision: Decision
    trace: list[TraceEntry]
