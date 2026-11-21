"""Leaderboard emitters: canonical JSON + readable Markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_bench.runner import SuiteResult

_METRIC_LABELS = {
    "compression_ratio": "Compression ratio (1 − after/before)",
    "keyword_retention": "Keyword retention",
    "tokens_before": "Tokens before",
    "tokens_after": "Tokens after",
    "precision_citable": "Precision (citable ≤ tier 2)",
    "recall_citable": "Recall (citable ≤ tier 2)",
    "exact_tier_accuracy": "Exact-tier accuracy",
    "tier_mae": "Tier MAE",
    "n_claims": "Claims",
    "tier_distribution": "Tier distribution",
    "overthinking_penalized": "Overthinking penalized",
    "mean_effort_score": "Mean effort score",
    "n_decisions": "Decisions",
    "bypass_resistance": "Bypass resistance (attacks blocked)",
    "benign_pass_rate": "Benign pass rate",
    "n_probes": "Probes",
}


def result_to_dict(result: SuiteResult) -> dict[str, Any]:
    """Canonical JSON representation (drift-checked fields only for metrics)."""
    return {
        "suite": result.suite,
        "mode": result.mode,
        "workload_digest": result.workload_digest,
        "rows": [
            {
                "adapter": r.adapter,
                "implementation": r.implementation,
                "metrics": r.metrics,
            }
            for r in result.rows
        ],
    }


def markdown_table(result: SuiteResult) -> str:
    """Render one suite as a Markdown table of deterministic metrics."""
    lines = [f"### {result.suite}", ""]
    metric_keys: list[str] = []
    for row in result.rows:
        for key in row.metrics:
            if key not in metric_keys:
                metric_keys.append(key)
    header = (
        "| Adapter | Implementation | "
        + " | ".join(_METRIC_LABELS.get(k, k) for k in metric_keys)
        + " |"
    )
    sep = "| :--- | :--- | " + " | ".join("---:" for _ in metric_keys) + " |"
    lines += [header, sep]
    for row in result.rows:
        cells = []
        for k in metric_keys:
            v = row.metrics.get(k)
            cells.append(json.dumps(v) if isinstance(v, dict) else str(v))
        lines.append(f"| `{row.adapter}` | {row.implementation} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(f"*Workload digest: `{result.workload_digest}` · mode: `{result.mode}`*")
    lines.append("")
    return "\n".join(lines)


def write_leaderboards(results: list[SuiteResult], output_dir: str) -> list[Path]:
    """Write per-suite JSON + a combined Markdown leaderboard. Returns paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    md_parts = [
        "# agent-benchmark-suite — Leaderboards",
        "",
        "All functional metrics are deterministic for the pinned workload",
        "digests and enforced by CI drift checks (≤ 3%). Latency percentiles are",
        "environment-specific and intentionally excluded from drift verification.",
        "",
    ]
    for result in results:
        json_path = out / f"{result.suite}.json"
        json_path.write_text(
            json.dumps(result_to_dict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        written.append(json_path)
        md_parts.append(markdown_table(result))
    md_path = out / "LEADERBOARD.md"
    md_path.write_text("\n".join(md_parts), encoding="utf-8")
    written.append(md_path)
    return written


def load_leaderboard(path: str) -> dict[str, Any]:
    """Load a committed JSON leaderboard."""
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return data
