"""Latency and aggregate metric math (stdlib only, fully deterministic)."""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RunStats:
    """Median and IQR of a series of run measurements."""

    median: float
    iqr: float
    runs: int


def percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interpolated percentile of an ascending-sorted list."""
    if not sorted_values:
        raise ValueError("percentile of empty series")
    if not 0.0 <= p <= 100.0:
        raise ValueError(f"percentile out of range: {p}")
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def median_iqr(values: list[float]) -> RunStats:
    """Median and interquartile range (IQR) of a value series."""
    if not values:
        raise ValueError("empty series")
    ordered = sorted(values)
    q1 = percentile(ordered, 25.0)
    q3 = percentile(ordered, 75.0)
    return RunStats(median=statistics.median(ordered), iqr=q3 - q1, runs=len(ordered))


def measure(
    fn: Callable[[], T],
    warmup: int = 2,
    runs: int = 10,
) -> tuple[T, RunStats]:
    """Run `fn` with warmups and return the last result plus latency stats.

    The return value is taken from the final run so callers get a fresh,
    valid result; latency is recorded for every timed run.
    """
    if warmup < 0:
        raise ValueError("warmup must be non-negative")
    if runs < 1:
        raise ValueError("runs must be >= 1")
    result: T | None = None
    durations: list[float] = []
    for i in range(warmup + runs):
        start = time.perf_counter()
        result = fn()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if i >= warmup:
            durations.append(elapsed_ms)
    assert result is not None  # runs >= 1 guarantees at least one execution
    return result, median_iqr(durations)


def relative_drift(baseline: float, candidate: float) -> float:
    """Relative change of candidate vs baseline as a non-negative fraction.

    Two zeros are considered equal (drift 0.0). A zero baseline with a
    non-zero candidate is an infinite drift reported as 1.0 (max violation).
    """
    if baseline == 0.0:
        return 0.0 if candidate == 0.0 else 1.0
    return abs(candidate - baseline) / abs(baseline)
