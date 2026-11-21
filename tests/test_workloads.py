"""Determinism and shape tests for all workload generators."""

import json

import pytest

from agent_bench.digest import canonical_sha256
from agent_bench.workloads import build_claims, build_policy_probes, build_traces
from agent_bench.workloads.claims import _url_for  # noqa: F401  (internal, exercised below)
from agent_bench.workloads.traces import AgentTrace


class TestTraces:
    def test_count_and_determinism(self):
        a = build_traces(20, seed=7)
        b = build_traces(20, seed=7)
        assert a == b
        assert len(a) == 20

    def test_seed_changes_content(self):
        assert build_traces(10, seed=1) != build_traces(10, seed=2)

    def test_traces_have_system_frame_and_content(self):
        for trace in build_traces(10, seed=42):
            assert trace.frames
            assert trace.frames[0].role == "system"
            assert trace.token_count() > 0

    def test_invalid_count(self):
        with pytest.raises(ValueError):
            build_traces(0)

    def test_to_messages_shape(self):
        trace = build_traces(1, seed=42)[0]
        messages = trace.to_messages()
        assert all(set(m) == {"role", "content"} for m in messages)

    def test_full_corpus_digest_stable(self):
        def render() -> list[list[str]]:
            return [[f.role, f.content] for t in build_traces(120, seed=42) for f in t.frames]

        assert canonical_sha256(render()) == canonical_sha256(render())


class TestClaims:
    def test_count_and_determinism(self):
        a = build_claims(150, seed=42)
        b = build_claims(150, seed=42)
        assert a == b
        assert len(a) == 150

    def test_tier_coverage(self):
        tiers = {c.ground_tier for c in build_claims(150, seed=42)}
        assert tiers == {1, 2, 3, 4, 5}

    def test_fallback_claims_present(self):
        # Unlisted domains with TLD-derived ground truth must exist.
        from agent_bench.workloads.claims import (
            _TIER1_DOMAINS,
            _TIER2_DOMAINS,
            _TIER3_DOMAINS,
            _TIER4_DOMAINS,
            _TIER5_DOMAINS,
        )

        listed = set(
            _TIER1_DOMAINS + _TIER2_DOMAINS + _TIER3_DOMAINS + _TIER4_DOMAINS + _TIER5_DOMAINS
        )
        claims = build_claims(150, seed=42)
        fallback = [c for c in claims if not any(d in c.url for d in listed)]
        assert len(fallback) == round(150 * 0.3)
        for c in fallback:
            if ".gov" in c.url or ".mil" in c.url:
                assert c.ground_tier == 1
            elif ".edu" in c.url:
                assert c.ground_tier == 2
            else:
                assert c.ground_tier == 3

    def test_urls_parse(self):
        for c in build_claims(150, seed=42):
            assert c.url.startswith(("http://", "https://"))

    def test_invalid_count(self):
        with pytest.raises(ValueError):
            build_claims(0)


class TestPolicyProbes:
    def test_count_and_determinism(self):
        a = build_policy_probes(60, seed=42)
        b = build_policy_probes(60, seed=42)
        assert a == b
        assert len(a) == 60

    def test_attack_benign_mix(self):
        probes = build_policy_probes(60, seed=42, attack_ratio=0.5)
        kinds = {p.kind for p in probes}
        assert kinds == {"attack", "benign"}
        assert sum(1 for p in probes if p.kind == "attack") == 30

    def test_json_safe_payloads(self):
        for p in build_policy_probes(60, seed=42):
            # Must round-trip canonical JSON without NaN/Infinity literals.
            text = json.dumps(
                {
                    "k": p.kind,
                    "a": p.attack_class,
                    "t": p.tool_name,
                    "amt": p.amount_literal,
                    "d": p.payload_depth,
                    "i": p.payload_items,
                    "b": p.payload_bytes,
                },
                allow_nan=False,
            )
            assert text

    def test_attack_classes_covered(self):
        classes = {p.attack_class for p in build_policy_probes(200, seed=42)}
        assert {
            "negative_amount",
            "zero_amount",
            "nan_amount",
            "infinity_amount",
            "excessive_depth",
            "excessive_items",
            "oversized_payload",
            "blocked_tool",
        } <= classes

    def test_invalid_ratio(self):
        with pytest.raises(ValueError):
            build_policy_probes(10, attack_ratio=1.5)


class TestAgentTrace:
    def test_token_count(self):
        trace = AgentTrace(trace_id="t", frames=[])
        trace.frames.append(
            __import__("agent_bench").workloads.traces.Frame("user", "one two three")
        )
        assert trace.token_count() == 3
