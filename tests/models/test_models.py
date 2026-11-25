"""Unit tests for Pydantic boundary models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from issuescout.models import (
    BenchmarkExample,
    Candidate,
    Citation,
    IssueRef,
    LocalizationResult,
)


class TestIssueRef:
    """Tests for IssueRef model."""

    def test_valid_creation(self):
        """Test valid IssueRef creation."""
        ref = IssueRef(owner="octocat", repo="Hello-World", number=42)
        assert ref.owner == "octocat"
        assert ref.repo == "Hello-World"
        assert ref.number == 42

    def test_str_representation(self):
        """Test string representation."""
        ref = IssueRef(owner="octocat", repo="Hello-World", number=42)
        assert str(ref) == "octocat/Hello-World#42"

    def test_validation_rejects_extra_fields(self):
        """Test that extra fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError):
            IssueRef(owner="octocat", repo="Hello-World", number=42, extra_field="bad")

    def test_round_trip_serialization(self):
        """Test JSON round-trip serialization."""
        ref = IssueRef(owner="octocat", repo="Hello-World", number=42)
        json_str = ref.model_dump_json()
        restored = IssueRef.model_validate_json(json_str)
        assert restored == ref

    def test_dict_round_trip(self):
        """Test dict round-trip serialization."""
        ref = IssueRef(owner="octocat", repo="Hello-World", number=42)
        data = ref.model_dump()
        restored = IssueRef.model_validate(data)
        assert restored == ref


class TestBenchmarkExample:
    """Tests for BenchmarkExample model."""

    def test_valid_creation(self):
        """Test valid BenchmarkExample creation."""
        issue = IssueRef(owner="octocat", repo="Hello-World", number=42)
        example = BenchmarkExample(
            issue=issue,
            base_commit_sha="abc123def456",
            issue_title="Fix bug in login",
            issue_body="Login fails when password is empty",
            gold_files_changed=["src/auth.py", "tests/test_auth.py"],
            pr_number=100,
            merged_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )
        assert example.issue == issue
        assert example.base_commit_sha == "abc123def456"
        assert example.pr_number == 100

    def test_validation_rejects_extra_fields(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError):
            BenchmarkExample(
                issue=IssueRef(owner="a", repo="b", number=1),
                base_commit_sha="sha",
                issue_title="t",
                issue_body="b",
                gold_files_changed=[],
                pr_number=1,
                merged_at=datetime.now(UTC),
                extra_field="bad",
            )

    def test_round_trip_serialization(self):
        """Test JSON round-trip serialization."""
        issue = IssueRef(owner="octocat", repo="Hello-World", number=42)
        example = BenchmarkExample(
            issue=issue,
            base_commit_sha="abc123def456",
            issue_title="Fix bug in login",
            issue_body="Login fails when password is empty",
            gold_files_changed=["src/auth.py", "tests/test_auth.py"],
            pr_number=100,
            merged_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )
        json_str = example.model_dump_json()
        restored = BenchmarkExample.model_validate_json(json_str)
        assert restored == example

    def test_dict_round_trip(self):
        """Test dict round-trip serialization."""
        issue = IssueRef(owner="octocat", repo="Hello-World", number=42)
        example = BenchmarkExample(
            issue=issue,
            base_commit_sha="abc123def456",
            issue_title="Fix bug in login",
            issue_body="Login fails when password is empty",
            gold_files_changed=["src/auth.py", "tests/test_auth.py"],
            pr_number=100,
            merged_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )
        data = example.model_dump()
        restored = BenchmarkExample.model_validate(data)
        assert restored == example


class TestCitation:
    """Tests for Citation model."""

    def test_valid_creation(self):
        """Test valid Citation creation."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        assert cite.path == "src/auth.py"
        assert cite.symbol == "validate_password"
        assert cite.line_start == 10
        assert cite.line_end == 25
        assert cite.commit_sha == "abc123def456789"

    def test_valid_without_symbol(self):
        """Test valid Citation without optional symbol."""
        cite = Citation(
            path="src/auth.py",
            line_start=1,
            line_end=50,
            commit_sha="abc123def456789",
            rationale="Entire file relevant",
        )
        assert cite.symbol is None

    def test_str_representation_with_symbol(self):
        """Test string representation with symbol."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        assert str(cite) == "src/auth.py:10-25::validate_password @ abc123def"

    def test_str_representation_without_symbol(self):
        """Test string representation without symbol."""
        cite = Citation(
            path="src/auth.py",
            line_start=1,
            line_end=50,
            commit_sha="abc123def456789",
            rationale="Entire file relevant",
        )
        assert str(cite) == "src/auth.py:1-50 @ abc123def"

    def test_validation_rejects_invalid_line_start(self):
        """Test that line_start must be >= 1."""
        with pytest.raises(ValidationError):
            Citation(
                path="src/auth.py",
                line_start=0,
                line_end=10,
                commit_sha="sha",
                rationale="test",
            )

    def test_validation_rejects_invalid_line_end(self):
        """Test that line_end must be >= 1."""
        with pytest.raises(ValidationError):
            Citation(
                path="src/auth.py",
                line_start=1,
                line_end=0,
                commit_sha="sha",
                rationale="test",
            )

    def test_validation_rejects_extra_fields(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError):
            Citation(
                path="src/auth.py",
                line_start=1,
                line_end=10,
                commit_sha="sha",
                rationale="test",
                extra_field="bad",
            )

    def test_round_trip_serialization(self):
        """Test JSON round-trip serialization."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        json_str = cite.model_dump_json()
        restored = Citation.model_validate_json(json_str)
        assert restored == cite

    def test_dict_round_trip(self):
        """Test dict round-trip serialization."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        data = cite.model_dump()
        restored = Citation.model_validate(data)
        assert restored == cite


class TestCandidate:
    """Tests for Candidate model."""

    def test_valid_creation(self):
        """Test valid Candidate creation."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        candidate = Candidate(
            citation=cite,
            score=0.95,
            evidence=["Directly handles password validation", "Called from login flow"],
        )
        assert candidate.citation == cite
        assert candidate.score == 0.95
        assert len(candidate.evidence) == 2

    def test_default_evidence(self):
        """Test default empty evidence list."""
        cite = Citation(
            path="src/auth.py",
            line_start=1,
            line_end=10,
            commit_sha="sha",
            rationale="test",
        )
        candidate = Candidate(citation=cite, score=0.5)
        assert candidate.evidence == []

    def test_score_bounds(self):
        """Test score must be in [0, 1]."""
        cite = Citation(path="a.py", line_start=1, line_end=1, commit_sha="sha", rationale="t")

        with pytest.raises(ValidationError):
            Candidate(citation=cite, score=-0.1)

        with pytest.raises(ValidationError):
            Candidate(citation=cite, score=1.1)

    def test_validation_rejects_extra_fields(self):
        """Test that extra fields are rejected."""
        cite = Citation(path="a.py", line_start=1, line_end=1, commit_sha="sha", rationale="t")
        with pytest.raises(ValidationError):
            Candidate(citation=cite, score=0.5, extra_field="bad")

    def test_round_trip_serialization(self):
        """Test JSON round-trip serialization."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        candidate = Candidate(
            citation=cite,
            score=0.95,
            evidence=["Directly handles password validation", "Called from login flow"],
        )
        json_str = candidate.model_dump_json()
        restored = Candidate.model_validate_json(json_str)
        assert restored == candidate

    def test_dict_round_trip(self):
        """Test dict round-trip serialization."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        candidate = Candidate(
            citation=cite,
            score=0.95,
            evidence=["Directly handles password validation", "Called from login flow"],
        )
        data = candidate.model_dump()
        restored = Candidate.model_validate(data)
        assert restored == candidate


class TestLocalizationResult:
    """Tests for LocalizationResult model."""

    def test_valid_creation(self):
        """Test valid LocalizationResult creation."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        candidate = Candidate(citation=cite, score=0.95, evidence=["evidence"])
        result = LocalizationResult(
            candidates=[candidate],
            budget_used={"tokens": 1000, "usd": 0.01},
            trace_id="trace-123",
        )
        assert len(result.candidates) == 1
        assert result.budget_used == {"tokens": 1000, "usd": 0.01}
        assert result.trace_id == "trace-123"

    def test_default_budget_used(self):
        """Test default empty budget_used."""
        result = LocalizationResult(candidates=[], trace_id="trace-123")
        assert result.budget_used == {}

    def test_validation_rejects_extra_fields(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError):
            LocalizationResult(candidates=[], trace_id="trace-123", extra_field="bad")

    def test_round_trip_serialization(self):
        """Test JSON round-trip serialization."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        candidate = Candidate(citation=cite, score=0.95, evidence=["evidence"])
        result = LocalizationResult(
            candidates=[candidate],
            budget_used={"tokens": 1000, "usd": 0.01},
            trace_id="trace-123",
        )
        json_str = result.model_dump_json()
        restored = LocalizationResult.model_validate_json(json_str)
        assert restored == result

    def test_dict_round_trip(self):
        """Test dict round-trip serialization."""
        cite = Citation(
            path="src/auth.py",
            symbol="validate_password",
            line_start=10,
            line_end=25,
            commit_sha="abc123def456789",
            rationale="Handles password validation logic",
        )
        candidate = Candidate(citation=cite, score=0.95, evidence=["evidence"])
        result = LocalizationResult(
            candidates=[candidate],
            budget_used={"tokens": 1000, "usd": 0.01},
            trace_id="trace-123",
        )
        data = result.model_dump()
        restored = LocalizationResult.model_validate(data)
        assert restored == result
