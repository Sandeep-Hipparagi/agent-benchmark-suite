"""Deterministic claim+source workloads with ground-truth accountability tiers."""

from __future__ import annotations

import random
from dataclasses import dataclass

# Tier 1: primary/official sources and global wire services.
_TIER1_DOMAINS = [
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
]
# Tier 2: established editorial newsrooms.
_TIER2_DOMAINS = [
    "nytimes.com",
    "theguardian.com",
    "wsj.com",
    "ft.com",
    "bbc.com",
    "economist.com",
    "washingtonpost.com",
    "thehindu.com",
]
# Tier 3: smaller publications, blogs, newsletters.
_TIER3_DOMAINS = [
    "techcrunch.com",
    "arstechnica.com",
    "substack.com",
    "medium.com",
    "yourstory.com",
    "inc42.com",
    "regionaldaily.example",
    "devblog.example",
]
# Tier 4: user-generated content and social platforms.
_TIER4_DOMAINS = [
    "reddit.com",
    "quora.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "youtube.com",
    "stackoverflow.com",
    "news.ycombinator.com",
]
# Tier 5: satire and parody outlets.
_TIER5_DOMAINS = [
    "theonion.com",
    "babylonbee.com",
    "waterfordwhispersnews.com",
    "duffelblog.com",
    "newsthump.com",
    "clickhole.com",
]

_CLAIM_TEMPLATES = [
    "Officials confirmed that {subject} {predicate}.",
    "A report claims {subject} {predicate}.",
    "Sources say {subject} {predicate}.",
    "Data indicates {subject} {predicate}.",
    "An anonymous post alleges {subject} {predicate}.",
]
_SUBJECTS = [
    "the central bank",
    "the grid operator",
    "the vaccine rollout",
    "the merger",
    "the outage",
    "the policy change",
    "the election",
    "the data breach",
    "the funding round",
    "the new regulation",
]
_PREDICATES = [
    "raised interest rates by 25 basis points",
    "restored full capacity",
    "missed the published deadline",
    "doubled year over year",
    "was paused pending review",
    "violated the consent order",
]


@dataclass(frozen=True)
class ClaimRecord:
    """A claim paired with its source URL and ground-truth tier (1-5)."""

    claim_id: str
    claim_text: str
    url: str
    ground_tier: int


def _url_for(domain: str, rng: random.Random) -> str:
    scheme = "https" if rng.random() < 0.85 else "http"
    path_depth = rng.randint(0, 3)
    segments = [f"p{rng.randint(1000, 9999)}" for _ in range(path_depth)]
    path = "/" + "/".join(segments) if segments else "/"
    return f"{scheme}://www.{domain}{path}"


def build_claims(count: int = 150, seed: int = 42) -> list[ClaimRecord]:
    """Build `count` deterministic claim records spanning tiers 1-5.

    ~30% of claims use unlisted domains whose ground truth derives from TLD
    heuristics (gov/mil/int -> 1, edu -> 2, else 3), forcing classifiers to
    exercise fallback rules rather than pure list lookup.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    rng = random.Random(seed)
    tier_domains: list[tuple[int, list[str]]] = [
        (1, _TIER1_DOMAINS),
        (2, _TIER2_DOMAINS),
        (3, _TIER3_DOMAINS),
        (4, _TIER4_DOMAINS),
        (5, _TIER5_DOMAINS),
    ]
    claims: list[ClaimRecord] = []
    n_fallback = round(count * 0.3)
    listed_count = count - n_fallback
    # Guarantee even coverage across tiers so class balance is stable.
    per_tier = listed_count // 5
    remainder = listed_count - per_tier * 5
    ids = 0
    for tier_idx, (tier, domains) in enumerate(tier_domains):
        n = per_tier + (1 if tier_idx < remainder else 0)
        for _ in range(n):
            domain = rng.choice(domains)
            url = _url_for(domain, rng)
            text = rng.choice(_CLAIM_TEMPLATES).format(
                subject=rng.choice(_SUBJECTS), predicate=rng.choice(_PREDICATES)
            )
            claims.append(
                ClaimRecord(
                    claim_id=f"claim-{seed}-{ids:04d}", claim_text=text, url=url, ground_tier=tier
                )
            )
            ids += 1

    # Unlisted fallback claims: ground truth from TLD heuristics.
    fallback_roots = [
        "agencyservices",
        "bureau-stats",
        "ministry-health",
        "observatory",
        "university-press",
        "institute-science",
        "academy-law",
        "college-data",
        "citydesk",
        "independentwire",
        "openblog",
        "localchronicle",
    ]
    for _ in range(n_fallback):
        root = rng.choice(fallback_roots)
        tld = rng.choice(("gov", "gov", "edu", "edu", "com", "net", "org"))
        ground = 1 if tld in ("gov", "mil", "int") else 2 if tld == "edu" else 3
        url = f"https://{root}-{rng.randint(10, 99)}.{tld}/article/{rng.randint(1000, 9999)}"
        text = rng.choice(_CLAIM_TEMPLATES).format(
            subject=rng.choice(_SUBJECTS), predicate=rng.choice(_PREDICATES)
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim-{seed}-{ids:04d}", claim_text=text, url=url, ground_tier=ground
            )
        )
        ids += 1
    rng.shuffle(claims)
    return claims
