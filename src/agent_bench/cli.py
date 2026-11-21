"""agent-bench CLI: run suites, emit leaderboards, verify committed results."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent_bench.runner import SUITES, run_suite

app = typer.Typer(help="Reproducible agentic-AI benchmark harness.", no_args_is_help=True)
console = Console()

_DEFAULT_OUT = str(Path(__file__).resolve().parents[2] / "benchmarks" / "leaderboards")


@app.command()
def run(
    suite: str = typer.Option(
        "all", "--suite", "-s", help="Suite to run: all, compress, provenance, route, policy."
    ),
    mode: str = typer.Option(
        "reference",
        "--mode",
        "-m",
        help="Adapter mode: reference (zero deps) or native (installed flagships).",
    ),
    count: int = typer.Option(120, "--count", "-c", min=1, help="Workload size for corpus suites."),
    seed: int = typer.Option(42, "--seed", help="Deterministic workload seed."),
    warmup: int = typer.Option(2, "--warmup", min=0, help="Warmup runs per item."),
    runs: int = typer.Option(
        5, "--runs", "-n", min=1, help="Timed runs per item (median reported)."
    ),
    output_dir: str = typer.Option(
        _DEFAULT_OUT, "--output-dir", "-o", help="Leaderboard output directory."
    ),
    check_drift: bool = typer.Option(
        False,
        "--check-drift",
        help="After writing, verify the fresh leaderboards self-consistently.",
    ),
) -> None:
    """Run benchmark suites and emit JSON + Markdown leaderboards."""
    selected = list(SUITES) if suite == "all" else [suite]
    for s in selected:
        if s not in SUITES:
            console.print(f"[red]Unknown suite:[/red] {s} (valid: all, {', '.join(SUITES)})")
            raise typer.Exit(code=2)
    results = [
        run_suite(s, mode=mode, count=count, seed=seed, warmup=warmup, runs=runs) for s in selected
    ]

    from agent_bench.report import write_leaderboards  # noqa: PLC0415

    written = write_leaderboards(results, output_dir)
    table = Table(title=f"agent-bench · mode={mode} · seed={seed}")
    table.add_column("Suite")
    table.add_column("Adapter")
    table.add_column("Implementation")
    table.add_column("Key metrics")
    for result in results:
        for row in result.rows:
            metrics = ", ".join(f"{k}={v}" for k, v in row.metrics.items())
            table.add_row(result.suite, row.adapter, row.implementation, metrics)
    console.print(table)
    console.print(f"[green]Wrote:[/green] {', '.join(str(p) for p in written)}")
    if check_drift:
        from agent_bench.verify import verify_leaderboard as _verify  # noqa: PLC0415

        failures: list[str] = []
        for result in results:
            path = Path(output_dir) / f"{result.suite}.json"
            failures.extend(_verify(str(path), runs=runs, warmup=warmup))
        if failures:
            for f in failures:
                console.print(f"[red]DRIFT:[/red] {f}")
            raise typer.Exit(code=1)
        console.print("[green]Drift check passed (<= 3%).[/green]")


@app.command("verify-leaderboard")
def verify_leaderboard(
    leaderboard: str = typer.Argument(..., help="Path to a committed suite JSON leaderboard."),
    runs: int = typer.Option(3, "--runs", min=1),
    warmup: int = typer.Option(1, "--warmup", min=0),
    tolerance: float = typer.Option(0.03, "--tolerance", min=0.0, max=1.0),
) -> None:
    """Verify a committed leaderboard against a fresh deterministic run."""
    from agent_bench.verify import verify_leaderboard as _verify  # noqa: PLC0415

    violations = _verify(leaderboard, runs=runs, warmup=warmup, tolerance=tolerance)
    if violations:
        for v in violations:
            console.print(f"[red]DRIFT:[/red] {v}")
        raise typer.Exit(code=1)
    console.print(f"[green]VERIFIED:[/green] {leaderboard} (tolerance {tolerance:.0%})")


def main() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    main()
