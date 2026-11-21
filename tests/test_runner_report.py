"""Runner, report, and leaderboard-drift tests."""

import json
from pathlib import Path

import pytest

from agent_bench.digest import canonical_sha256
from agent_bench.report import load_leaderboard, markdown_table, result_to_dict, write_leaderboards
from agent_bench.runner import SuiteResult, run_suite, workload_digest
from agent_bench.verify import verify_leaderboard


class TestRunSuite:
    def test_all_suites_produce_rows(self):
        for suite in ("compress", "provenance", "route", "policy"):
            result = run_suite(suite, runs=2, warmup=0)
            assert isinstance(result, SuiteResult)
            assert result.rows, f"{suite} produced no rows"
            assert result.workload_digest and len(result.workload_digest) == 64
            for row in result.rows:
                assert row.suite == suite
                assert row.adapter
                assert row.implementation
                assert row.metrics

    def test_determinism_of_functional_metrics(self):
        a = run_suite("compress", runs=2, warmup=0).rows[0].metrics
        b = run_suite("compress", runs=2, warmup=0).rows[0].metrics
        assert a == b

    def test_invalid_suite_rejected(self):
        with pytest.raises(ValueError):
            run_suite("bogus")

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError):
            run_suite("compress", mode="quantum")

    def test_workload_digest_changes_with_seed(self):
        assert workload_digest("compress", 10, 1) != workload_digest("compress", 10, 2)
        assert workload_digest("compress", 10, 1) == workload_digest("compress", 10, 1)


class TestReport:
    def test_roundtrip(self, tmp_path: Path):
        result = run_suite("policy", runs=2, warmup=0)
        paths = write_leaderboards([result], str(tmp_path))
        assert len(paths) == 2  # suite JSON + LEADERBOARD.md
        loaded = load_leaderboard(str(tmp_path / "policy.json"))
        assert loaded["suite"] == "policy"
        assert loaded["workload_digest"] == result.workload_digest
        assert loaded["rows"][0]["metrics"] == result.rows[0].metrics

    def test_markdown_contains_rows_and_digest(self, tmp_path: Path):
        result = run_suite("compress", runs=2, warmup=0)
        md = markdown_table(result)
        assert "### compress" in md
        assert result.rows[0].adapter in md
        assert result.workload_digest[:12] in md

    def test_json_file_is_canonical_sorted(self, tmp_path: Path):
        result = run_suite("compress", runs=2, warmup=0)
        path = write_leaderboards([result], str(tmp_path))[0]
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        # Re-serialized canonically, must hash identically to its canonical form.
        assert canonical_sha256(data["rows"]) == canonical_sha256(
            [r for r in result_to_dict(result)["rows"]]
        )


class TestDriftVerification:
    def _commit(self, tmp_path: Path, suite: str = "compress") -> Path:
        result = run_suite(suite, runs=2, warmup=0)
        write_leaderboards([result], str(tmp_path))
        return tmp_path / f"{suite}.json"

    def test_fresh_run_verifies(self, tmp_path: Path):
        path = self._commit(tmp_path)
        assert verify_leaderboard(str(path), runs=2, warmup=0) == []

    def test_tampered_metric_fails(self, tmp_path: Path):
        path = self._commit(tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        key = next(iter(data["rows"][0]["metrics"]))
        original = data["rows"][0]["metrics"][key]
        if isinstance(original, (int, float)) and not isinstance(original, bool):
            data["rows"][0]["metrics"][key] = original * 1.5 + 1
        else:
            data["rows"][0]["metrics"][key] = "TAMPERED"
        path.write_text(json.dumps(data), encoding="utf-8")
        violations = verify_leaderboard(str(path), runs=2, warmup=0)
        assert violations
        assert any("drifted" in v or "changed" in v for v in violations)

    def test_tampered_digest_requires_acknowledgement(self, tmp_path: Path):
        path = self._commit(tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["workload_digest"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
        violations = verify_leaderboard(str(path), runs=2, warmup=0)
        assert any("digest_bumped" in v for v in violations)

    def test_digest_bump_acknowledgement_short_circuits(self, tmp_path: Path):
        path = self._commit(tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["workload_digest"] = "0" * 64
        data["digest_bumped"] = True
        path.write_text(json.dumps(data), encoding="utf-8")
        assert verify_leaderboard(str(path), runs=2, warmup=0) == []

    def test_missing_adapter_flagged(self, tmp_path: Path):
        path = self._commit(tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["rows"][0]["adapter"] = "vanishing-adapter"
        path.write_text(json.dumps(data), encoding="utf-8")
        violations = verify_leaderboard(str(path), runs=2, warmup=0)
        assert any("adapter missing from fresh run" in v for v in violations)

    def test_extra_committed_metric_missing_in_fresh_flagged(self, tmp_path: Path):
        # A committed metric the fresh run no longer produces is drift.
        path = self._commit(tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["rows"][0]["metrics"]["phantom_metric"] = 1.0
        path.write_text(json.dumps(data), encoding="utf-8")
        violations = verify_leaderboard(str(path), runs=2, warmup=0)
        assert any("'phantom_metric' missing from fresh run" in v for v in violations)
