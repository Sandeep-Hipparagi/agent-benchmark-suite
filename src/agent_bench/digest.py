"""Deterministic canonical serialization and workload hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize to a byte-stable JSON string (sorted keys, tight separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_sha256(obj: Any) -> str:
    """SHA-256 hex digest of the canonical JSON serialization."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    """SHA-256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
