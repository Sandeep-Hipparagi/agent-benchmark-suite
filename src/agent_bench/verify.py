"""Verification of committed leaderboards against fresh deterministic runs.

Functional metrics must reproduce within `tolerance` for an unchanged
workload digest. Latency fields are excluded (environment-specific).
A changed digest requires an explicit `digest_bumped` acknowledgement in the
committed JSON, preventing silent workload edits.
"""

from __future__ import annotations

from typing import Any

from agent_bench.metrics import relative_drift
from agent_bench.report import load_leaderboard, result_to_dict
from agent_bench.runner import run_suite

_EXCLUDED_KEYS = {"latency_ms"}


def verify_leaderboard(
    path: str,
    runs: int = 3,
    warmup: int = 1,
    tolerance: float = 0.03,
) -> list[str]:
    """Re-run the suite and compare against the committed leaderboard.

    Returns a list of violation strings; empty means verified.
    """
    committed = load_leaderboard(path)
    suite = str(committed["suite"])
    mode = str(committed.get("mode", "reference"))
    digest = str(committed["workload_digest"])
    committed_rows: list[dict[str, Any]] = list(committed["rows"])

    fresh = run_suite(suite, mode=mode, warmup=warmup, runs=runs)
    fresh_dict = result_to_dict(fresh)

    violations: list[str] = []
    if fresh_dict["workload_digest"] != digest:
        if not committed.get("digest_bumped", False):
            old = digest[:12]
            new = fresh_dict["workload_digest"][:12]
            violations.append(
                f"workload digest changed ({old}... -> {new}...) "
                "without 'digest_bumped' acknowledgement"
            )
        return violations

    fresh_by_adapter = {row["adapter"]: row for row in fresh_dict["rows"]}
    committed_by_adapter = {row["adapter"]: row for row in committed_rows}
    for adapter, committed_row in committed_by_adapter.items():
        fresh_row = fresh_by_adapter.get(adapter)
        if fresh_row is None:
            violations.append(f"{suite}/{adapter}: adapter missing from fresh run")
            continue
        for key, baseline in committed_row["metrics"].items():
            if key not in fresh_row["metrics"]:
                violations.append(f"{suite}/{adapter}: metric '{key}' missing from fresh run")
                continue
            candidate = fresh_row["metrics"][key]
            if isinstance(baseline, dict) or isinstance(candidate, dict):
                if baseline != candidate:
                    violations.append(f"{suite}/{adapter}: distribution '{key}' changed")
                continue
            drift = relative_drift(float(baseline), float(candidate))
            if drift > tolerance:
                violations.append(
                    f"{suite}/{adapter}: '{key}' drifted {drift:.2%} "
                    f"({baseline} -> {candidate}) > tolerance {tolerance:.0%}"
                )
    return violations
