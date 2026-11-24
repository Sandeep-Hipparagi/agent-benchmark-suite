"""Routing adapters: faithful port of Inference-Pareto-Router's 2D Pareto policy
(reference) plus the real library when importable (native)."""

from __future__ import annotations

from typing import Any

from agent_bench.adapters.base import RoutingTarget

_STRATEGY_PRESETS: dict[str, tuple[float, float, float, float, float]] = {
    "PARETO_BALANCED": (0.15, 0.75, 0.35, 0.65, 0.25),
    "PARETO_COST": (0.25, 0.85, 0.45, 0.75, 0.35),
    "PARETO_QUALITY": (0.10, 0.60, 0.25, 0.50, 0.15),
}


class ReferenceRoutingAdapter:
    """Deterministic 2D Pareto coordinate evaluation.

    Ports the published Inference-Pareto-Router policy: overthinking penalty,
    effort scaling with boosts/clamps, and the 2D frontier tier selection.
    """

    name = "reference-pareto"
    implementation = "reference"

    def available(self) -> bool:
        return True

    def decide(self, logic: float, knowledge: float, strategy: str) -> tuple[str, float]:
        preset = _STRATEGY_PRESETS.get(strategy)
        if preset is None:
            raise ValueError(f"unknown strategy: {strategy!r}")
        t_logic_low, t_logic_high, t_know_low, t_know_high, t_overthinking = preset

        is_low_entropy = knowledge == -1.0  # workload sentinel for greeting/low-entropy turns
        eff_knowledge = 0.5 if is_low_entropy else knowledge

        if is_low_entropy and logic < t_overthinking or logic <= t_logic_low:
            effort_score = 0.0
        else:
            raw_effort = (logic - t_logic_low) / (1.0 - t_logic_low)
            if eff_knowledge > t_know_high and logic > 0.50:
                raw_effort = min(1.0, raw_effort + 0.10)
            if strategy == "PARETO_QUALITY":
                raw_effort = min(1.0, raw_effort + 0.10)
            elif strategy == "PARETO_COST":
                raw_effort = max(0.05, raw_effort - 0.10)
            effort_score = round(max(0.05, min(1.0, raw_effort)), 3)

        if (
            eff_knowledge >= t_know_high
            or logic >= t_logic_high
            or (eff_knowledge >= 0.50 and logic >= 0.50)
        ):
            tier = "FRONTIER"
        elif eff_knowledge >= t_know_low or logic >= t_logic_low:
            tier = "MID"
        else:
            tier = "COMPACT"
        return tier, effort_score


class ParetoRouterAdapter:
    """Wraps Inference-Pareto-Router's ParetoPolicy in-process."""

    name = "pareto-router/policy"
    implementation = "native:pareto-router"

    def __init__(self) -> None:
        self._policy: Any = None
        self._scores_cls: Any = None
        self._strategies: Any = None
        self._tier_map: dict[str, str] = {}

    def available(self) -> bool:
        try:
            from pareto_router.core.policy import ParetoPolicy  # noqa: PLC0415
            from pareto_router.core.schemas import EvaluationScores, ModelTier, RoutingStrategy  # noqa: PLC0415
        except ImportError:
            return False
        if self._policy is None:
            self._policy = ParetoPolicy()
            self._scores_cls = EvaluationScores
            self._strategies = RoutingStrategy
            self._tier_map = {t.value: t for t in ModelTier}
        return True

    def decide(self, logic: float, knowledge: float, strategy: str) -> tuple[str, float]:
        assert self._policy is not None and self._scores_cls is not None
        eff_knowledge = 0.5 if knowledge == -1.0 else knowledge
        metadata: dict[str, Any] = {"is_low_entropy": True} if knowledge == -1.0 else {}
        scores = self._scores_cls(
            logic_score=logic,
            knowledge_score=eff_knowledge,
            latency_ms=0.0,
            evaluator_name="agent-benchmark-suite",
            metadata=metadata,
        )
        decision = self._policy.evaluate_coordinates(scores, self._strategies[strategy])
        # Normalize tier casing to the reference vocabulary (FRONTIER/MID/COMPACT).
        return str(decision.tier.value).upper(), float(decision.effort_score)


def get_routing_adapters(prefer_native: bool) -> list[RoutingTarget]:
    adapters: list[RoutingTarget] = []
    if prefer_native:
        candidate = ParetoRouterAdapter()
        if candidate.available():
            adapters.append(candidate)
    adapters.append(ReferenceRoutingAdapter())
    return adapters
