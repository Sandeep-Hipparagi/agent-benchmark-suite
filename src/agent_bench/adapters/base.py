"""Versioned adapter protocol. Adapters execute real code — reference
implementations are genuine algorithmic engines, native adapters wrap the
actual flagship libraries when importable. Availability is always honest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PolicyDecision:
    """Outcome of a policy-gate evaluation."""

    allowed: bool
    reason_code: str


@runtime_checkable
class CompressionTarget(Protocol):
    name: str
    implementation: str

    def available(self) -> bool: ...

    def compress(self, messages: list[dict[str, str]]) -> list[str]:
        """Return compacted frame contents for one trace."""
        ...


@runtime_checkable
class ProvenanceTarget(Protocol):
    name: str
    implementation: str

    def available(self) -> bool: ...

    def classify(self, url: str) -> int:
        """Return an accountability tier 1-5 for the source URL."""
        ...


@runtime_checkable
class RoutingTarget(Protocol):
    name: str
    implementation: str

    def available(self) -> bool: ...

    def decide(self, logic: float, knowledge: float, strategy: str) -> tuple[str, float]:
        """Return (tier, effort_score) for 2D Pareto coordinates."""
        ...


@runtime_checkable
class PolicyTarget(Protocol):
    name: str
    implementation: str

    def available(self) -> bool: ...

    def evaluate(
        self,
        tool_name: str,
        amount_literal: str,
        payload_depth: int,
        payload_items: int,
        payload_bytes: int,
    ) -> PolicyDecision:
        """Gate a tool call against the documented boundary invariants."""
        ...
