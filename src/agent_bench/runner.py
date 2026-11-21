"""Suite runner: executes adapters over seeded workloads with warmups and
median/IQR latency statistics, producing digest-pinned, deterministic results.

Functional metrics (ratios, rates, counts, distributions) are deterministic
for a fixed workload digest. Latency statistics are measured but marked
environment-specific and excluded from the CI drift check.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any

from agent_bench.adapters.compression import get_compression_adapters, keyword_retention
from agent_bench.adapters.policy import get_policy_adapters
from agent_bench.adapters.provenance import get_provenance_adapters
from agent_bench.adapters.routing import get_routing_adapters
from agent_bench.digest import canonical_sha256
from agent_bench.metrics import measure
from agent_bench.workloads import build_claims, build_policy_probes, build_traces

SUITES = ("compress", "provenance", "route", "policy")
MODES = ("reference", "native")


@dataclass(frozen=True)
class BenchmarkRow:
    """One adapter's results for one suite."""

    suite: str
    adapter: str
    implementation: str
    metrics: dict[str, Any]  # deterministic functional metrics (drift-checked)
    latency_ms: dict[str, Any]  # environment-specific (excluded from drift)


@dataclass(frozen=True)
class SuiteResult:
    suite: str
    mode: str
    workload_digest: str
    rows: list[BenchmarkRow] = field(default_factory=list)


def _traces_digest(count: int, seed: int) -> str:
    traces = build_traces(count, seed)
    return canonical_sha256([[f.role, f.content] for t in traces for f in t.frames])


def _claims_digest(count: int, seed: int) -> str:
    claims = build_claims(count, seed)
    return canonical_sha256([[c.claim_text, c.url, c.ground_tier] for c in claims])


def _probes_digest(count: int, seed: int) -> str:
    probes = build_policy_probes(count, seed)
    return canonical_sha256(
        [
            [
                p.kind,
                p.attack_class,
                p.tool_name,
                p.amount_literal,
                p.payload_depth,
                p.payload_items,
                p.payload_bytes,
            ]
            for p in probes
        ]
    )


def workload_digest(suite: str, count: int, seed: int) -> str:
    """Canonical SHA-256 of the suite's full workload (deterministic)."""
    if suite == "compress":
        return _traces_digest(count, seed)
    if suite == "provenance":
        return _claims_digest(count, seed)
    if suite == "policy":
        return _probes_digest(count, seed)
    if suite == "route":
        # Routing consumes the same trace corpus as compression.
        return _traces_digest(count, seed)
    raise ValueError(f"unknown suite: {suite!r}")


def run_compress(count: int, seed: int, warmup: int, runs: int, mode: str) -> list[BenchmarkRow]:
    traces = build_traces(count, seed)
    rows: list[BenchmarkRow] = []
    for adapter in get_compression_adapters(prefer_native=mode == "native"):
        tokens_before = 0
        tokens_after = 0
        retention_sum = 0.0
        latencies: list[float] = []
        for trace in traces:
            messages = trace.to_messages()
            before = trace.token_count()
            compacted, stats = measure(
                functools.partial(adapter.compress, messages), warmup=warmup, runs=runs
            )
            after = sum(len(c.split()) for c in compacted)
            tokens_before += before
            tokens_after += after
            retention_sum += keyword_retention([m["content"] for m in messages], compacted)
            latencies.append(stats.median)
        rows.append(
            BenchmarkRow(
                suite="compress",
                adapter=adapter.name,
                implementation=adapter.implementation,
                metrics={
                    "tokens_before": tokens_before,
                    "tokens_after": tokens_after,
                    "compression_ratio": round(1.0 - tokens_after / tokens_before, 6),
                    "keyword_retention": round(retention_sum / len(traces), 6),
                },
                latency_ms={
                    "median_ms_per_trace": round(sum(latencies) / len(latencies), 4),
                },
            )
        )
    return rows


def run_provenance(count: int, seed: int, warmup: int, runs: int, mode: str) -> list[BenchmarkRow]:
    claims = build_claims(count, seed)
    rows: list[BenchmarkRow] = []
    for adapter in get_provenance_adapters(prefer_native=mode == "native"):
        tp = fp = fn = tn = exact = 0
        mae_sum = 0.0
        latencies: list[float] = []
        for claim in claims:
            predicted, stats = measure(
                functools.partial(adapter.classify, claim.url), warmup=warmup, runs=runs
            )
            pred_citable = predicted <= 2
            true_citable = claim.ground_tier <= 2
            if pred_citable and true_citable:
                tp += 1
            elif pred_citable and not true_citable:
                fp += 1
            elif not pred_citable and true_citable:
                fn += 1
            else:
                tn += 1
            if predicted == claim.ground_tier:
                exact += 1
            mae_sum += abs(predicted - claim.ground_tier)
            latencies.append(stats.median)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        rows.append(
            BenchmarkRow(
                suite="provenance",
                adapter=adapter.name,
                implementation=adapter.implementation,
                metrics={
                    "precision_citable": round(precision, 6),
                    "recall_citable": round(recall, 6),
                    "exact_tier_accuracy": round(exact / len(claims), 6),
                    "tier_mae": round(mae_sum / len(claims), 6),
                    "n_claims": len(claims),
                },
                latency_ms={"median_ms_per_claim": round(sum(latencies) / len(latencies), 4)},
            )
        )
    return rows


def run_route(count: int, seed: int, warmup: int, runs: int, mode: str) -> list[BenchmarkRow]:
    import random

    traces = build_traces(count, seed)
    rng = random.Random(seed)
    strategies = ["PARETO_BALANCED", "PARETO_COST", "PARETO_QUALITY"]
    cases: list[tuple[float, float, str, bool]] = []
    for i, trace in enumerate(traces):
        first = trace.frames[0].content if trace.frames else ""
        words = first.split()
        # Deterministic pseudo-scores derived from the trace itself.
        logic = min(1.0, max(0.0, (sum(ord(c) for c in first[:64]) % 100) / 100.0))
        knowledge = min(1.0, max(0.0, (len(words) % 100) / 100.0))
        low_entropy = "status update" in first or "heartbeat" in first
        cases.append((logic, knowledge, strategies[i % 3], low_entropy))
        rng.random()  # keep rng stream stable if future workload edits need it

    rows: list[BenchmarkRow] = []
    for adapter in get_routing_adapters(prefer_native=mode == "native"):
        tier_counts: dict[str, int] = {"FRONTIER": 0, "MID": 0, "COMPACT": 0}
        penalized = 0
        effort_sum = 0.0
        latencies: list[float] = []
        for logic, knowledge, strategy, low_entropy in cases:
            eff_knowledge = -1.0 if low_entropy else knowledge
            (tier, effort), stats = measure(
                functools.partial(adapter.decide, logic, eff_knowledge, strategy),
                warmup=warmup,
                runs=runs,
            )
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            penalized += 1 if effort == 0.0 and low_entropy else 0
            effort_sum += effort
            latencies.append(stats.median)
        rows.append(
            BenchmarkRow(
                suite="route",
                adapter=adapter.name,
                implementation=adapter.implementation,
                metrics={
                    "tier_distribution": tier_counts,
                    "overthinking_penalized": penalized,
                    "mean_effort_score": round(effort_sum / len(cases), 6),
                    "n_decisions": len(cases),
                },
                latency_ms={"median_ms_per_decision": round(sum(latencies) / len(latencies), 5)},
            )
        )
    return rows


def run_policy(count: int, seed: int, warmup: int, runs: int, mode: str) -> list[BenchmarkRow]:
    probes = build_policy_probes(count, seed)
    rows: list[BenchmarkRow] = []
    for adapter in get_policy_adapters(prefer_native=mode == "native"):
        attacks = [p for p in probes if p.kind == "attack"]
        benign = [p for p in probes if p.kind == "benign"]
        blocked = 0
        benign_passed = 0
        latencies: list[float] = []
        for probe in probes:
            decision, stats = measure(
                functools.partial(
                    adapter.evaluate,
                    probe.tool_name,
                    probe.amount_literal,
                    probe.payload_depth,
                    probe.payload_items,
                    probe.payload_bytes,
                ),
                warmup=warmup,
                runs=runs,
            )
            if probe.kind == "attack" and not decision.allowed:
                blocked += 1
            if probe.kind == "benign" and decision.allowed:
                benign_passed += 1
            latencies.append(stats.median)
        rows.append(
            BenchmarkRow(
                suite="policy",
                adapter=adapter.name,
                implementation=adapter.implementation,
                metrics={
                    "bypass_resistance": round(blocked / len(attacks), 6) if attacks else 1.0,
                    "benign_pass_rate": round(benign_passed / len(benign), 6) if benign else 0.0,
                    "n_probes": len(probes),
                },
                latency_ms={"median_ms_per_decision": round(sum(latencies) / len(latencies), 5)},
            )
        )
    return rows


_RUNNERS = {
    "compress": run_compress,
    "provenance": run_provenance,
    "route": run_route,
    "policy": run_policy,
}


def run_suite(
    suite: str,
    mode: str = "reference",
    count: int = 120,
    seed: int = 42,
    warmup: int = 1,
    runs: int = 5,
) -> SuiteResult:
    """Execute one suite end-to-end and return digest-pinned results."""
    if suite not in SUITES:
        raise ValueError(f"unknown suite: {suite!r}. valid: {SUITES}")
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}. valid: {MODES}")
    # Provenance and policy suites have their own natural corpus sizes.
    eff_count = count
    if suite == "provenance":
        eff_count = max(count, 150)
    if suite == "policy":
        eff_count = max(count, 60)
    rows = _RUNNERS[suite](eff_count, seed, warmup, runs, mode)
    return SuiteResult(
        suite=suite,
        mode=mode,
        workload_digest=workload_digest(suite, eff_count, seed),
        rows=rows,
    )
