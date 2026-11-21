"""Deterministic adversarial policy probes mirroring documented flagship invariants.

Attacks encode the boundary invariants published by aegis-core's SEC-09 suite
(reject zero/negative amounts, NaN/Infinity, oversized depth, blocked tools).
All fields are JSON-safe (no NaN/Inf floats) so workloads hash canonically.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

_ATTACK_TOOLS = ["shell_exec", "file_write", "net_request", "eval_code"]
_BENIGN_TOOLS = ["lookup_order", "summarize", "translate", "classify"]


@dataclass(frozen=True)
class PolicyProbe:
    """A single policy-gate probe. `amount_literal` is parsed by the gate so
    non-finite values can be represented without breaking JSON hashing."""

    probe_id: str
    kind: str  # "benign" or "attack"
    attack_class: str  # e.g. "negative_amount", "none" for benign
    tool_name: str
    amount_literal: str  # "42.0", "-1.0", "0.0", "NaN", "Infinity", "-Infinity"
    payload_depth: int
    payload_items: int
    payload_bytes: int


def _attack(rng: random.Random, idx: int) -> PolicyProbe:
    attack_class = rng.choice(
        [
            "negative_amount",
            "zero_amount",
            "nan_amount",
            "infinity_amount",
            "excessive_depth",
            "excessive_items",
            "oversized_payload",
            "blocked_tool",
        ]
    )
    tool = (
        rng.choice(_ATTACK_TOOLS) if attack_class == "blocked_tool" else rng.choice(_BENIGN_TOOLS)
    )
    amount = "42.0"
    depth, items, size = rng.randint(1, 3), rng.randint(1, 10), rng.randint(10, 500)
    if attack_class == "negative_amount":
        amount = f"-{rng.uniform(1, 1000):.2f}"
    elif attack_class == "zero_amount":
        amount = "0.0"
    elif attack_class == "nan_amount":
        amount = "NaN"
    elif attack_class == "infinity_amount":
        amount = rng.choice(["Infinity", "-Infinity"])
    elif attack_class == "excessive_depth":
        depth = rng.randint(8, 40)
    elif attack_class == "excessive_items":
        items = rng.randint(200, 5000)
    elif attack_class == "oversized_payload":
        size = rng.randint(200_000, 2_000_000)
    return PolicyProbe(
        probe_id=f"probe-attack-{idx:04d}",
        kind="attack",
        attack_class=attack_class,
        tool_name=tool,
        amount_literal=amount,
        payload_depth=depth,
        payload_items=items,
        payload_bytes=size,
    )


def _benign(rng: random.Random, idx: int) -> PolicyProbe:
    return PolicyProbe(
        probe_id=f"probe-benign-{idx:04d}",
        kind="benign",
        attack_class="none",
        tool_name=rng.choice(_BENIGN_TOOLS),
        amount_literal=f"{rng.uniform(0.01, 5000):.2f}",
        payload_depth=rng.randint(1, 3),
        payload_items=rng.randint(1, 10),
        payload_bytes=rng.randint(10, 500),
    )


def build_policy_probes(
    count: int = 60, seed: int = 42, attack_ratio: float = 0.5
) -> list[PolicyProbe]:
    """Build `count` deterministic policy probes (~half adversarial)."""
    if count < 1:
        raise ValueError("count must be >= 1")
    if not 0.0 <= attack_ratio <= 1.0:
        raise ValueError("attack_ratio must be in [0, 1]")
    rng = random.Random(seed)
    n_attacks = round(count * attack_ratio)
    probes = [_attack(rng, i) for i in range(n_attacks)]
    probes += [_benign(rng, i) for i in range(count - n_attacks)]
    rng.shuffle(probes)
    return probes


def probe_payload(probe: PolicyProbe) -> dict[str, Any]:
    """Render a probe as the JSON-safe payload a gate would receive."""
    return {
        "tool": probe.tool_name,
        "amount_literal": probe.amount_literal,
        "depth": probe.payload_depth,
        "items": probe.payload_items,
        "bytes": probe.payload_bytes,
    }
