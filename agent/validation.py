"""
Schema validation — enforce the canonical contracts at every layer boundary.

The schemas under `schemas/` are the meaning-layer's job description: they
define what an RFC, Service, or Template *is*. This module turns them from
documentation into runtime checks. A malformed entity is rejected with a
precise error before any reasoning runs.
"""
import json
from functools import lru_cache
from pathlib import Path

import jsonschema

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


@lru_cache(maxsize=None)
def _schema(name: str) -> dict:
    with open(SCHEMAS_DIR / f"{name}.json") as f:
        return json.load(f)


def validate_rfc(rfc: dict) -> None:
    """Raise jsonschema.ValidationError if the RFC is malformed."""
    jsonschema.validate(rfc, _schema("change"))


def validate_service(service: dict) -> None:
    jsonschema.validate(service, _schema("service"))


def validate_template(template: dict) -> None:
    jsonschema.validate(template, _schema("template"))
