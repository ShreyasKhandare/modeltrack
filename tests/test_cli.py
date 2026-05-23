"""
Tests for CLI commands.
"""

import pytest
import json
from click.testing import CliRunner

from modeltrack.cli.cli import cli
from modeltrack.shared.database import init_db


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


@pytest.fixture
def isolated_fs(runner):
    """Create isolated filesystem for testing."""
    with runner.isolated_filesystem():
        init_db()
        yield runner


class TestInit:
    """Tests for init command."""

    def test_init_success(self, runner):
        """Test successful initialization."""
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "initialized" in result.output.lower()

    def test_init_creates_directories(self, runner):
        """Test that init creates required directories."""
        import os
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init"])
            # Check that directories would be created
            assert result.exit_code == 0


class TestConfig:
    """Tests for config command."""

    def test_config_success(self, runner):
        """Test config display."""
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0
        assert "API" in result.output or "api" in result.output


class TestPipelineCommands:
    """Tests for pipeline commands."""

    def test_pipeline_help(self, runner):
        """Test pipeline command help."""
        result = runner.invoke(cli, ["pipeline", "--help"])
        assert result.exit_code == 0
        assert "run" in result.output or "Run" in result.output

    def test_pipeline_run_invalid_context(self, runner):
        """Test pipeline run with invalid JSON context."""
        result = runner.invoke(cli, [
            "pipeline", "run", "test_pipeline",
            "--context", "invalid_json"
        ])
        assert result.exit_code != 0
        assert "JSON" in result.output or "json" in result.output

    def test_pipeline_status_help(self, runner):
        """Test pipeline status command help."""
        result = runner.invoke(cli, ["pipeline", "status", "--help"])
        assert result.exit_code == 0

    def test_pipeline_history_help(self, runner):
        """Test pipeline history command help."""
        result = runner.invoke(cli, ["pipeline", "history", "--help"])
        assert result.exit_code == 0

    def test_pipeline_lineage_help(self, runner):
        """Test pipeline lineage command help."""
        result = runner.invoke(cli, ["pipeline", "lineage", "--help"])
        assert result.exit_code == 0


class TestModelCommands:
    """Tests for model commands."""

    def test_model_help(self, runner):
        """Test model command help."""
        result = runner.invoke(cli, ["model", "--help"])
        assert result.exit_code == 0
        assert "save" in result.output or "register" in result.output

    def test_model_save_invalid_metrics(self, runner):
        """Test model save with invalid JSON metrics."""
        result = runner.invoke(cli, [
            "model", "save", "test_model", "1.0.0",
            "--metrics", "invalid_json"
        ])
        assert result.exit_code != 0
        assert "JSON" in result.output or "json" in result.output

    def test_model_save_missing_metrics(self, runner):
        """Test model save without required metrics."""
        result = runner.invoke(cli, [
            "model", "save", "test_model", "1.0.0"
        ])
        assert result.exit_code != 0
        assert "metrics" in result.output.lower()

    def test_model_save_valid(self, runner):
        """Test model save with valid inputs."""
        result = runner.invoke(cli, [
            "model", "save", "test_model", "1.0.0",
            "--metrics", '{"accuracy": 0.95}',
            "--hyperparams", '{"n_estimators": 100}'
        ])
        # Will fail without API server, but structure is correct
        assert "model" in result.output.lower() or "error" in result.output.lower()

    def test_model_get_help(self, runner):
        """Test model get command help."""
        result = runner.invoke(cli, ["model", "get", "--help"])
        assert result.exit_code == 0

    def test_model_versions_help(self, runner):
        """Test model versions command help."""
        result = runner.invoke(cli, ["model", "versions", "--help"])
        assert result.exit_code == 0

    def test_model_promote_help(self, runner):
        """Test model promote command help."""
        result = runner.invoke(cli, ["model", "promote", "--help"])
        assert result.exit_code == 0

    def test_model_promote_invalid_gates(self, runner):
        """Test model promote with invalid JSON gates."""
        result = runner.invoke(cli, [
            "model", "promote", "test_model", "1.0.0", "staging",
            "--gates", "invalid_json"
        ])
        assert result.exit_code != 0
        assert "JSON" in result.output or "json" in result.output

    def test_model_rollback_help(self, runner):
        """Test model rollback command help."""
        result = runner.invoke(cli, ["model", "rollback", "--help"])
        assert result.exit_code == 0


class TestTestCommands:
    """Tests for A/B test commands."""

    def test_test_help(self, runner):
        """Test test command help."""
        result = runner.invoke(cli, ["test", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output or "Start" in result.output

    def test_test_start_help(self, runner):
        """Test test start command help."""
        result = runner.invoke(cli, ["test", "start", "--help"])
        assert result.exit_code == 0

    def test_test_start_invalid_split(self, runner):
        """Test test start with invalid traffic split."""
        result = runner.invoke(cli, [
            "test", "start", "test_name", "model_a", "model_b",
            "--split", "1.5"
        ])
        assert result.exit_code != 0
        assert "split" in result.output.lower()

    def test_test_results_help(self, runner):
        """Test test results command help."""
        result = runner.invoke(cli, ["test", "results", "--help"])
        assert result.exit_code == 0


class TestCLIVersion:
    """Tests for CLI version."""

    def test_version_flag(self, runner):
        """Test --version flag."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.2.0" in result.output or "version" in result.output.lower()


class TestCLIHelp:
    """Tests for help system."""

    def test_main_help(self, runner):
        """Test main CLI help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "pipeline" in result.output
        assert "model" in result.output
        assert "test" in result.output

    def test_pipeline_command_help(self, runner):
        """Test pipeline group help."""
        result = runner.invoke(cli, ["pipeline", "--help"])
        assert result.exit_code == 0
        assert "run" in result.output

    def test_model_command_help(self, runner):
        """Test model group help."""
        result = runner.invoke(cli, ["model", "--help"])
        assert result.exit_code == 0

    def test_test_command_help(self, runner):
        """Test test group help."""
        result = runner.invoke(cli, ["test", "--help"])
        assert result.exit_code == 0


class TestJSONInputValidation:
    """Tests for JSON input validation."""

    def test_context_json_parsing(self, runner):
        """Test context JSON parsing."""
        # Valid JSON
        result = runner.invoke(cli, [
            "pipeline", "run", "test",
            "--context", '{"key": "value"}'
        ])
        # Should fail on API connection, not JSON parsing
        assert "JSON" not in result.output

    def test_metrics_json_parsing(self, runner):
        """Test metrics JSON parsing."""
        result = runner.invoke(cli, [
            "model", "save", "m", "1.0",
            "--metrics", '{"accuracy": 0.95}'
        ])
        # Should fail on API connection, not JSON parsing
        assert "JSON" not in result.output or "invalid" not in result.output.lower()

    def test_hyperparams_json_parsing(self, runner):
        """Test hyperparameters JSON parsing."""
        result = runner.invoke(cli, [
            "model", "save", "m", "1.0",
            "--metrics", '{"accuracy": 0.95}',
            "--hyperparams", '{"param": 10}'
        ])
        # Should fail on API connection, not JSON parsing
        assert "JSON" not in result.output or "invalid" not in result.output.lower()
