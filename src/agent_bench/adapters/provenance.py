"""Provenance adapters: deterministic tier classifier + native provenance-guard."""

from __future__ import annotations

from typing import Any

from agent_bench.adapters.base import ProvenanceTarget

_TIER_RULES: list[tuple[int, tuple[str, ...]]] = [
    (
        5,
        (
            "theonion.com",
            "babylonbee.com",
            "waterfordwhispersnews.com",
            "duffelblog.com",
            "newsthump.com",
            "clickhole.com",
        ),
    ),
    (
        4,
        (
            "reddit.com",
            "quora.com",
            "x.com",
            "twitter.com",
            "facebook.com",
            "youtube.com",
            "stackoverflow.com",
            "news.ycombinator.com",
        ),
    ),
    (
        1,
        (
            "reuters.com",
            "apnews.com",
            "afp.com",
            "bloomberg.com",
            "federalreserve.gov",
            "sec.gov",
            "who.int",
            "un.org",
            "nature.com",
            "science.org",
            "nejm.org",
            "factcheck.org",
        ),
    ),
    (
        2,
        (
            "nytimes.com",
            "theguardian.com",
            "wsj.com",
            "ft.com",
            "bbc.com",
            "economist.com",
            "washingtonpost.com",
            "thehindu.com",
        ),
    ),
    (
        3,
        (
            "techcrunch.com",
            "arstechnica.com",
            "substack.com",
            "medium.com",
            "yourstory.com",
            "inc42.com",
            "regionaldaily.example",
            "devblog.example",
        ),
    ),
]

_TIER1_TLDS = ("gov", "mil", "int")
_EDU_TLD = "edu"


def _registered_domain(url: str) -> str:
    """Extract a lowercase host without scheme, port, path, or 'www.' prefix."""
    host = url.strip().lower()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    host = host.split("/", 1)[0].split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


class ReferenceProvenanceAdapter:
    """Deterministic rule-based accountability tier classifier.

    Rules: satire domains first (tier 5), then user-generated platforms
    (tier 4), then explicit domain allowlists (tiers 1-3), then TLD heuristics
    (gov/mil/int -> 1, edu -> 2), else unknown-ish low-trust default (tier 3).
    """

    name = "reference-tierer"
    implementation = "reference"

    def available(self) -> bool:
        return True

    def classify(self, url: str) -> int:
        host = _registered_domain(url)
        if not host:
            return 3
        for tier, domains in _TIER_RULES:
            if any(host == d or host.endswith("." + d) for d in domains):
                return tier
        parts = host.rsplit(".", 1)
        tld = parts[1] if len(parts) == 2 else ""
        if tld in _TIER1_TLDS:
            return 1
        if tld == _EDU_TLD:
            return 2
        return 3


class ProvenanceGuardAdapter:
    """Wraps provenance-guard (epistemic-guard) DomainAuditor in-process."""

    name = "provenance-guard/auditor"
    implementation = "native:provenance-guard"

    def __init__(self) -> None:
        self._auditor: Any = None

    def available(self) -> bool:
        try:
            from epistemic_guard.tools.domain_auditor import DomainAuditor  # noqa: PLC0415
        except ImportError:
            return False
        if self._auditor is None:
            self._auditor = DomainAuditor()
        return True

    def classify(self, url: str) -> int:
        assert self._auditor is not None
        result = self._auditor.audit_url(url)
        tier = getattr(result, "tier", "")
        text = str(tier)
        for i in range(1, 6):
            if f"tier_{i}" in text or f"TIER_{i}" in text:
                return i
        # TIER_UNKNOWN or anything else maps to the cautious default.
        return 3


def get_provenance_adapters(prefer_native: bool) -> list[ProvenanceTarget]:
    adapters: list[ProvenanceTarget] = []
    if prefer_native:
        candidate = ProvenanceGuardAdapter()
        if candidate.available():
            adapters.append(candidate)
    adapters.append(ReferenceProvenanceAdapter())
    return adapters
