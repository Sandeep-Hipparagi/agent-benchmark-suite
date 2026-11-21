"""Deterministic multi-step agent-trajectory workloads for compression and routing."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

# Filler patterns that real agent traces accumulate: repeated tool echoes,
# ANSI-ish noise, pleasantries, and deep JSON payloads.
_FILLER_SENTENCES = [
    "The operation completed successfully without errors.",
    "Let me know if you need anything else.",
    "Retrieved 42 rows from the service in 120ms.",
    "This is an automated status update from the worker pool.",
    "No changes were detected since the previous checkpoint.",
    "The cache was refreshed and warmed for the current session.",
    "Heartbeat received from node {n}.",
    "Retrying with exponential backoff (attempt {n}).",
]

_PAYLOAD_VALUES = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]

_TOPICS = [
    "checkout-service latency spike and 504 timeouts on the payment path",
    "auth token validation failures during token refresh bursts",
    "inventory service lock contention during bulk stock updates",
    "notification queue backlog exceeding 50,000 messages",
    "ledger database connection pool exhaustion under load",
    "api-gateway routing misconfiguration after the config push",
    "redis session cache fragmentation and TTL race conditions",
    "third-party push provider rate limiting without backoff",
]

_ROLES = ["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Frame:
    """One message in an agent trajectory."""

    role: str
    content: str


@dataclass(frozen=True)
class AgentTrace:
    """A multi-step agent trajectory with realistic redundancy."""

    trace_id: str
    frames: list[Frame] = field(default_factory=list)

    def token_count(self) -> int:
        """Whitespace-delimited token estimate across all frames."""
        return sum(len(f.content.split()) for f in self.frames)

    def to_messages(self) -> list[dict[str, str]]:
        """Render as OpenAI-style message dicts."""
        return [{"role": f.role, "content": f.content} for f in self.frames]


def _filler(rng: random.Random, n: int) -> str:
    return rng.choice(_FILLER_SENTENCES).replace("{n}", str(n))


def _payload(rng: random.Random, depth: int) -> dict[str, Any]:
    node: dict[str, Any] = {}
    for i in range(3):
        if depth > 1 and rng.random() < 0.5:
            node[f"nested_{i}"] = _payload(rng, depth - 1)
        else:
            node[f"field_{i}"] = rng.choice(_PAYLOAD_VALUES)
    return node


def build_traces(count: int = 120, seed: int = 42) -> list[AgentTrace]:
    """Build `count` deterministic agent traces."""
    if count < 1:
        raise ValueError("count must be >= 1")
    rng = random.Random(seed)
    traces: list[AgentTrace] = []
    for t in range(count):
        topic = rng.choice(_TOPICS)
        steps = rng.randint(4, 12)
        frames: list[Frame] = [Frame("system", f"You are an SRE triage agent. Incident: {topic}.")]

        for s in range(steps):
            role = rng.choice(_ROLES[1:])
            kind = rng.random()
            if kind < 0.35:
                # Repeated tool echo (the redundancy compressors should kill)
                frames.append(Frame("tool", _filler(rng, s)))
            elif kind < 0.55:
                frames.append(Frame(role, f"{topic}. {_filler(rng, s)}"))
            elif kind < 0.75:
                import json

                frames.append(Frame(role, json.dumps(_payload(rng, rng.randint(2, 5)))))
            elif kind < 0.9:
                # Whitespace/emoji bloat
                pad = "🚀 " * rng.randint(5, 60)
                frames.append(Frame(role, f"{pad}{_filler(rng, s)}"))
            else:
                # Verbatim duplication of an earlier frame
                if len(frames) > 1:
                    frames.append(frames[rng.randrange(1, len(frames))])
                else:
                    frames.append(Frame(role, _filler(rng, s)))
        traces.append(AgentTrace(trace_id=f"trace-{seed}-{t:04d}", frames=frames))
    return traces
