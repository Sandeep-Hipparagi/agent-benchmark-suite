# Contributing to agent-benchmark-suite

Thank you for considering a contribution. This harness exists to make agentic
AI benchmark claims reproducible — please keep it that way.

## Ground rules

1. **Determinism first.** Workload generation, scoring, and leaderboard
   functional metrics must be byte-for-byte reproducible for a fixed seed.
   Never introduce wall-clock time, randomness without a seed, or network
   fetches into scoring paths. Latency is measured but excluded from the
   CI drift check.
2. **No hardcoded scores.** Every number in a leaderboard must be computed by
   executing adapter code against the seeded workloads in that run.
3. **Adapters must degrade honestly.** A native adapter that cannot import its
   target library reports itself unavailable; it never fabricates results.
4. **Zero third-party scaffolding strings** in commits or docs.

## Development setup

```bash
git clone https://github.com/Sandeep-Hipparagi/agent-benchmark-suite.git
cd agent-benchmark-suite
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
```

## Before opening a PR

```bash
ruff check .
ruff format --check .
mypy --strict src tests
pytest
agent-bench verify-leaderboard
```

All five must pass. CI enforces the same checks.

## Adding an adapter

1. Subclass the relevant protocol in `src/agent_bench/adapters/base.py`.
2. Implement `available()` truthfully (import probe, environment probe).
3. Add contract tests: determinism for a fixed seed, correct metric types,
   and honest unavailability when the target library is absent.
4. If your adapter changes any functional metric for the default reference
   mode, bump the workload digest (see README) and regenerate leaderboards in
   the same PR.

## Commit style

Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `bench:`).
