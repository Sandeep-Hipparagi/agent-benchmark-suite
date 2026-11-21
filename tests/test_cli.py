"""CLI end-to-end tests via typer's CliRunner."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_bench.cli import app

runner = CliRunner()


class TestCliRun:
    def test_run_single_suite_writes_leaderboards(self, tmp_path: Path):
        result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "policy",
                "--runs",
                "2",
                "--warmup",
                "0",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "policy.json").exists()
        assert (tmp_path / "LEADERBOARD.md").exists()

    def test_run_unknown_suite_exits_2(self, tmp_path: Path):
        result = runner.invoke(
            app,
            ["run", "--suite", "bogus", "--output-dir", str(tmp_path)],
        )
        assert result.exit_code == 2

    def test_run_all_suites(self, tmp_path: Path):
        result = runner.invoke(
            app,
            [
                "run",
                "--suite",
                "all",
                "--runs",
                "1",
                "--warmup",
                "0",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        for suite in ("compress", "provenance", "route", "policy"):
            assert (tmp_path / f"{suite}.json").exists()


class TestCliVerify:
    def test_verify_passes_on_fresh_leaderboard(self, tmp_path: Path):
        runner.invoke(
            app,
            [
                "run",
                "--suite",
                "policy",
                "--runs",
                "2",
                "--warmup",
                "0",
                "--output-dir",
                str(tmp_path),
            ],
        )
        result = runner.invoke(
            app,
            [
                "verify-leaderboard",
                str(tmp_path / "policy.json"),
                "--runs",
                "2",
                "--warmup",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "VERIFIED" in result.output

    def test_verify_fails_on_tampered_leaderboard(self, tmp_path: Path):
        runner.invoke(
            app,
            [
                "run",
                "--suite",
                "policy",
                "--runs",
                "2",
                "--warmup",
                "0",
                "--output-dir",
                str(tmp_path),
            ],
        )
        import json

        path = tmp_path / "policy.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        key = next(iter(data["rows"][0]["metrics"]))
        val = data["rows"][0]["metrics"][key]
        data["rows"][0]["metrics"][key] = (val * 2 + 1) if isinstance(val, (int, float)) else "X"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "verify-leaderboard",
                str(path),
                "--runs",
                "2",
                "--warmup",
                "0",
            ],
        )
        assert result.exit_code == 1
        assert "DRIFT" in result.output

    def test_verify_missing_file_errors(self, tmp_path: Path):
        result = runner.invoke(app, ["verify-leaderboard", str(tmp_path / "nope.json")])
        assert result.exit_code != 0


@pytest.mark.parametrize("suite", ["compress", "provenance", "route", "policy"])
def test_each_suite_cli_smoke(suite: str, tmp_path: Path):
    result = runner.invoke(
        app,
        ["run", "--suite", suite, "--runs", "1", "--warmup", "0", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
