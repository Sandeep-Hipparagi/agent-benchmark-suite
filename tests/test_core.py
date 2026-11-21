"""Determinism and math tests for metrics and digest utilities."""

import pytest

from agent_bench.digest import canonical_json, canonical_sha256
from agent_bench.metrics import measure, median_iqr, percentile, relative_drift


class TestCanonicalDigest:
    def test_key_order_independent(self):
        assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})

    def test_stable_across_calls(self):
        payload = {"suite": "compress", "rows": [{"adapter": "x", "metrics": {"r": 0.5}}]}
        assert canonical_sha256(payload) == canonical_sha256(payload)

    def test_known_vector(self):
        # sha256 of canonical JSON for {"a":1}
        import hashlib

        expected = hashlib.sha256(b'{"a":1}').hexdigest()
        assert canonical_sha256({"a": 1}) == expected

    def test_non_ascii_is_escaped(self):
        assert "\\u" in canonical_json({"emoji": "🚀"})


class TestPercentile:
    def test_single_value(self):
        assert percentile([5.0], 50.0) == 5.0

    def test_median_of_range(self):
        assert percentile([1.0, 2.0, 3.0, 4.0], 50.0) == 2.5

    def test_quartiles(self):
        vals = [float(v) for v in range(1, 101)]  # 1.0..100.0
        assert percentile(vals, 25.0) == pytest.approx(25.75)
        assert percentile(vals, 75.0) == pytest.approx(75.25)

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            percentile([1.0], 150.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            percentile([], 50.0)


class TestMedianIqr:
    def test_basic(self):
        stats = median_iqr([1.0, 2.0, 3.0, 4.0, 100.0])
        assert stats.median == 3.0
        assert stats.runs == 5
        assert stats.iqr > 0

    def test_constant_series_zero_iqr(self):
        stats = median_iqr([2.0] * 10)
        assert stats.iqr == 0.0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            median_iqr([])


class TestMeasure:
    def test_returns_value_and_stats(self):
        value, stats = measure(lambda: 42, warmup=1, runs=3)
        assert value == 42
        assert stats.runs == 3

    def test_invalid_args(self):
        with pytest.raises(ValueError):
            measure(lambda: 1, runs=0)
        with pytest.raises(ValueError):
            measure(lambda: 1, warmup=-1)


class TestRelativeDrift:
    def test_zero_vs_zero(self):
        assert relative_drift(0.0, 0.0) == 0.0

    def test_zero_baseline_nonzero(self):
        assert relative_drift(0.0, 5.0) == 1.0

    def test_three_percent(self):
        assert relative_drift(100.0, 103.0) == pytest.approx(0.03)

    def test_symmetric(self):
        assert relative_drift(100.0, 97.0) == pytest.approx(0.03)
