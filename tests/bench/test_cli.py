"""Tests for benchmark mining CLI."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from issuescout.bench.cli import load_config, main
from issuescout.bench.config import BenchConfig


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_valid(self, tmp_path):
        config_content = """
leakage_cutoff = "2025-06-01"
out_path = "data/bench.jsonl"
cache_dir = ".cache/github"
max_concurrent = 1

[[repos]]
owner = "pallets"
name = "flask"
max_prs = 500
since = "2025-06-01"
until = "2025-12-31"

[[repos]]
owner = "psf"
name = "requests"
max_prs = 300
"""
        config_path = tmp_path / "bench.toml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        assert isinstance(config, BenchConfig)
        assert len(config.repos) == 2
        assert config.repos[0].owner == "pallets"
        assert config.repos[0].name == "flask"
        assert config.repos[0].max_prs == 500
        assert config.repos[0].since == datetime(2025, 6, 1, tzinfo=UTC)
        assert config.repos[0].until == datetime(2025, 12, 31, tzinfo=UTC)
        assert config.repos[1].owner == "psf"
        assert config.repos[1].name == "requests"
        assert config.repos[1].max_prs == 300
        assert config.repos[1].since is None
        assert config.repos[1].until is None
        assert config.leakage_cutoff == datetime(2025, 6, 1, tzinfo=UTC)
        assert config.out_path == Path("data/bench.jsonl")
        assert config.cache_dir == Path(".cache/github")
        assert config.max_concurrent == 1


class TestCliMain:
    """Tests for CLI main function."""

    def test_main_help(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_main_invalid_config(self):
        with patch("issuescout.bench.cli.load_config", side_effect=FileNotFoundError("Not found")):
            exit_code = main(["--config", "nonexistent.toml"])
        assert exit_code == 1

    def test_main_success(self, tmp_path):
        config_content = """
leakage_cutoff = "2025-06-01"
out_path = "data/bench.jsonl"
cache_dir = ".cache/github"
max_concurrent = 1

[[repos]]
owner = "pallets"
name = "flask"
max_prs = 10
"""
        config_path = tmp_path / "bench.toml"
        config_path.write_text(config_content)

        out_path = tmp_path / "bench.jsonl"

        with patch("issuescout.bench.cli.run_mining") as mock_run_mining:
            mock_run_mining.return_value = {
                "pallets/flask": {"processed": 10, "kept": 5, "dropped": 5, "errors": 0}
            }

            exit_code = main(
                [
                    "--config",
                    str(config_path),
                    "--out",
                    str(out_path),
                ]
            )

        assert exit_code == 0
        mock_run_mining.assert_called_once()
        # Check that config was updated with out_path
        called_config = mock_run_mining.call_args[0][0]
        assert called_config.out_path == out_path

    def test_main_keyboard_interrupt(self, tmp_path):
        config_content = """
leakage_cutoff = "2025-06-01"
out_path = "data/bench.jsonl"
cache_dir = ".cache/github"
max_concurrent = 1

[[repos]]
owner = "pallets"
name = "flask"
"""
        config_path = tmp_path / "bench.toml"
        config_path.write_text(config_content)

        with patch("issuescout.bench.cli.run_mining", side_effect=KeyboardInterrupt()):
            exit_code = main(["--config", str(config_path)])

        assert exit_code == 130

    def test_main_exception(self, tmp_path):
        config_content = """
leakage_cutoff = "2025-06-01"
out_path = "data/bench.jsonl"
cache_dir = ".cache/github"
max_concurrent = 1

[[repos]]
owner = "pallets"
name = "flask"
"""
        config_path = tmp_path / "bench.toml"
        config_path.write_text(config_content)

        with patch("issuescout.bench.cli.run_mining", side_effect=Exception("API error")):
            exit_code = main(["--config", str(config_path), "-v"])

        assert exit_code == 1


class TestCliIntegration:
    """Integration test for CLI with mocked GitHub client."""

    def test_cli_runs_and_writes_jsonl(self, tmp_path):
        """End-to-end test: CLI runs mining and produces JSONL output."""
        config_content = """
leakage_cutoff = "2025-06-01"
out_path = "data/bench.jsonl"
cache_dir = ".cache/github"
max_concurrent = 1

[[repos]]
owner = "pallets"
name = "flask"
max_prs = 2
"""
        config_path = tmp_path / "bench.toml"
        config_path.write_text(config_content)

        out_path = tmp_path / "bench.jsonl"

        # Create a mock example that would be written
        mock_example = {
            "issue": {"owner": "pallets", "repo": "flask", "number": 42},
            "base_commit_sha": "abc123def4567890abc123def4567890abc123de",
            "issue_title": "Fix bug",
            "issue_body": "Bug description",
            "gold_files_all": ["src/auth.py"],
            "gold_files_source": ["src/auth.py"],
            "pr_number": 100,
            "merged_at": "2025-07-15T10:30:00+00:00",
            "issue_created_at": "2025-07-10T10:30:00+00:00",
            "pr_opened_at": "2025-07-12T10:30:00+00:00",
            "changed_files": [
                {
                    "path": "src/auth.py",
                    "status": "modified",
                    "old_path": None,
                    "additions": 10,
                    "deletions": 5,
                    "locatable_at_base": True,
                }
            ],
            "split_tag": "post_cutoff",
        }

        with patch("issuescout.bench.cli.run_mining") as mock_run_mining:
            # Simulate writing to the output file
            def side_effect(config):
                out_path.write_text(json.dumps(mock_example) + "\n")
                return {"pallets/flask": {"processed": 2, "kept": 1, "dropped": 1, "errors": 0}}

            mock_run_mining.side_effect = side_effect

            exit_code = main(
                [
                    "--config",
                    str(config_path),
                    "--out",
                    str(out_path),
                ]
            )

        assert exit_code == 0
        assert out_path.exists()

        # Verify output is valid JSONL
        lines = out_path.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["pr_number"] == 100
        assert record["gold_files_all"] == ["src/auth.py"]
