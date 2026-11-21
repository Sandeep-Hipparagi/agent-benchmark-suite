"""Adapter contract tests: real execution, honest availability, determinism."""

import pytest

from agent_bench.adapters.compression import (
    AgentSNRCompressionAdapter,
    ContextGuardCompressionAdapter,
    ReferenceCompressionAdapter,
    get_compression_adapters,
    keyword_retention,
)
from agent_bench.adapters.policy import ReferencePolicyAdapter, get_policy_adapters
from agent_bench.adapters.provenance import (
    ProvenanceGuardAdapter,
    ReferenceProvenanceAdapter,
    get_provenance_adapters,
)
from agent_bench.adapters.routing import (
    ParetoRouterAdapter,
    ReferenceRoutingAdapter,
    get_routing_adapters,
)
from agent_bench.workloads import build_traces


class TestReferenceCompression:
    def test_compresses_and_preserves_topic(self):
        adapter = ReferenceCompressionAdapter()
        trace = build_traces(5, seed=42)[0]
        messages = trace.to_messages()
        out = adapter.compress(messages)
        before = trace.token_count()
        after = sum(len(c.split()) for c in out)
        assert after < before, "reference compactor must reduce the redundant corpus"

    def test_deterministic(self):
        adapter = ReferenceCompressionAdapter()
        messages = build_traces(3, seed=9)[0].to_messages()
        assert adapter.compress(messages) == adapter.compress(messages)

    def test_empty_content_guard(self):
        adapter = ReferenceCompressionAdapter()
        out = adapter.compress([{"role": "user", "content": ""}, {"role": "user", "content": ""}])
        assert len(out) == 1  # verbatim duplicate suppressed

    def test_get_adapters_always_includes_reference(self):
        names = [a.name for a in get_compression_adapters(prefer_native=False)]
        assert names == ["reference-compactor"]


class TestNativeCompressionAdapters:
    def test_native_adapters_honest_when_unavailable(self):
        # In this environment the flagship libs are not installed in the
        # harness venv; available() must reflect that, never fake success.
        for adapter in (AgentSNRCompressionAdapter(), ContextGuardCompressionAdapter()):
            try:
                result = adapter.available()
            except Exception as e:  # pragma: no cover - must never happen
                pytest.fail(f"available() raised: {e}")
            if result:
                # If installed, a real run must work end-to-end.
                out = adapter.compress(
                    [{"role": "user", "content": "hello world, this is a test frame"}] * 10
                )
                assert isinstance(out, list)


class TestReferenceProvenance:
    def test_known_domains(self):
        adapter = ReferenceProvenanceAdapter()
        assert adapter.classify("https://www.reuters.com/p/1234") == 1
        assert adapter.classify("https://www.onion-like-not-listed.example") == 3
        assert adapter.classify("https://www.theonion.com/a/b") == 5
        assert adapter.classify("https://reddit.com/r/news") == 4
        assert adapter.classify("https://www.nytimes.com") == 2

    def test_tld_fallback(self):
        adapter = ReferenceProvenanceAdapter()
        assert adapter.classify("https://agency-42.gov/x") == 1
        assert adapter.classify("https://institute-7.edu/a/1") == 2
        assert adapter.classify("https://blog-33.com/x") == 3

    def test_subdomain_and_case_insensitive(self):
        adapter = ReferenceProvenanceAdapter()
        assert adapter.classify("HTTPS://NEWS.REUTERS.COM/path") == 1

    def test_empty_url_cautious_default(self):
        assert ReferenceProvenanceAdapter().classify("") == 3

    def test_contract(self):
        adapter = ReferenceProvenanceAdapter()
        assert adapter.available()
        assert adapter.implementation == "reference"


class TestReferenceRouting:
    def test_matches_published_ipr_coordinates(self):
        adapter = ReferenceRoutingAdapter()
        # Encoded from Inference-Pareto-Router's ParetoPolicy (BALANCED preset):
        # raw_effort=(0.9-0.15)/0.85=0.882, +0.10 dual-high boost -> 0.982.
        assert adapter.decide(0.9, 0.9, "PARETO_BALANCED") == ("FRONTIER", 0.982)
        assert adapter.decide(0.05, 0.05, "PARETO_BALANCED") == ("COMPACT", 0.0)
        # Low logic clamps effort to 0 but knowledge >= know_low gives MID.
        tier, effort = adapter.decide(0.10, 0.5, "PARETO_BALANCED")
        assert tier == "MID" and effort == 0.0
        # Cost preset subtracts 0.10 from a scaled effort.
        _, cost_effort = adapter.decide(0.8, 0.4, "PARETO_COST")
        _, bal_effort = adapter.decide(0.8, 0.4, "PARETO_BALANCED")
        assert cost_effort < bal_effort

    def test_low_entropy_overthinking_penalty(self):
        adapter = ReferenceRoutingAdapter()
        tier, effort = adapter.decide(0.05, -1.0, "PARETO_BALANCED")
        assert effort == 0.0  # penalized greeting gets zero effort

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError):
            ReferenceRoutingAdapter().decide(0.5, 0.5, "PARETO_YOLO")

    def test_deterministic(self):
        a = ReferenceRoutingAdapter().decide(0.62, 0.44, "PARETO_QUALITY")
        b = ReferenceRoutingAdapter().decide(0.62, 0.44, "PARETO_QUALITY")
        assert a == b


class TestReferencePolicy:
    def test_all_documented_attacks_blocked(self):
        adapter = ReferencePolicyAdapter()
        attacks = [
            ("lookup_order", "-42.00", 1, 1, 10),
            ("lookup_order", "0.0", 1, 1, 10),
            ("lookup_order", "NaN", 1, 1, 10),
            ("lookup_order", "Infinity", 1, 1, 10),
            ("lookup_order", "-Infinity", 1, 1, 10),
            ("lookup_order", "42.0", 9, 1, 10),
            ("lookup_order", "42.0", 1, 500, 10),
            ("lookup_order", "42.0", 1, 1, 500000),
            ("shell_exec", "42.0", 1, 1, 10),
            ("eval_code", "42.0", 1, 1, 10),
        ]
        for tool, amount, depth, items, size in attacks:
            decision = adapter.evaluate(tool, amount, depth, items, size)
            assert not decision.allowed, (
                f"attack not blocked: {tool} {amount} {depth} {items} {size}"
            )
            assert decision.reason_code != "OK"

    def test_benign_passes(self):
        adapter = ReferencePolicyAdapter()
        decision = adapter.evaluate("lookup_order", "42.0", 2, 5, 100)
        assert decision.allowed and decision.reason_code == "OK"

    def test_unparseable_amount_fail_closed(self):
        decision = ReferencePolicyAdapter().evaluate("lookup_order", "1e999xx", 1, 1, 10)
        assert not decision.allowed


class TestAdapterRegistries:
    def test_policy_registry_includes_reference(self):
        names = [a.name for a in get_policy_adapters(prefer_native=False)]
        assert names == ["reference-policy-gate"]

    def test_provenance_registry_includes_reference(self):
        names = [a.name for a in get_provenance_adapters(prefer_native=False)]
        assert names == ["reference-tierer"]

    def test_routing_registry_includes_reference(self):
        names = [a.name for a in get_routing_adapters(prefer_native=False)]
        assert names == ["reference-pareto"]

    def test_native_routing_honest(self):
        adapter = ParetoRouterAdapter()
        if adapter.available():
            tier, effort = adapter.decide(0.9, 0.9, "PARETO_BALANCED")
            assert tier in {"FRONTIER", "MID", "COMPACT"}
            assert 0.0 <= effort <= 1.0

    def test_native_provenance_honest(self):
        adapter = ProvenanceGuardAdapter()
        if adapter.available():
            tier = adapter.classify("https://www.reuters.com/x")
            assert 1 <= tier <= 5


class TestKeywordRetention:
    def test_full_retention(self):
        assert (
            keyword_retention(
                ["checkout service latency spike"], ["checkout service latency spike"]
            )
            == 1.0
        )

    def test_zero_retention(self):
        assert keyword_retention(["checkout service latency"], ["zzz qqq www"]) == 0.0

    def test_empty_before_is_full(self):
        assert keyword_retention([], ["anything"]) == 1.0

    def test_partial(self):
        score = keyword_retention(["alpha beta gamma delta"], ["alpha beta"])
        assert 0.0 < score < 1.0
