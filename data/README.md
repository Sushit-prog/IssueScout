# Benchmark Dataset Format

This directory contains the benchmark dataset produced by `python -m issuescout.bench.mine`.

## File Format: JSONL

Each line is a JSON object representing a single `BenchmarkExample`. The file can be streamed or loaded entirely into memory.

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `issue` | `IssueRef` | Object with `owner`, `repo`, `number` identifying the GitHub issue |
| `base_commit_sha` | `str` | SHA of the base commit (from REST API `/pulls/{n}`) used for git verification |
| `issue_title` | `str` | Title of the closing issue |
| `issue_body` | `str` | Body text of the closing issue |
| `gold_files_all` | `list[str]` | All changed files that are locatable at the base commit (includes removed/renamed-old paths) |
| `gold_files_source` | `list[str]` | Subset of `gold_files_all` excluding tests and docs |
| `pr_number` | `int` | Pull request number |
| `merged_at` | `datetime` | ISO 8601 timestamp when PR was merged |
| `issue_created_at` | `datetime` | ISO 8601 timestamp when issue was created |
| `pr_opened_at` | `datetime` | ISO 8601 timestamp when PR was opened |
| `changed_files` | `list[ChangedFile]` | Array of changed files with path, status, additions, deletions, locatable flag |
| `split_tag` | `str` | `"pre_cutoff"` or `"post_cutoff"` based on `leakage_cutoff` (see below) |

### ChangedFile Structure

```json
{
  "path": "src/auth.py",
  "status": "modified",
  "additions": 10,
  "deletions": 5,
  "locatable_at_base": true
}
```

Valid statuses: `added`, `modified`, `removed`, `renamed`, `copied`, `changed`

## Split Tags

The dataset is split into two disjoint sets based on the **leakage cutoff date**:

- **`pre_cutoff`**: Issues created on or before `2025-06-01T00:00:00Z`
  - These examples represent "past" data from the perspective of a model trained before this date
  - Suitable for evaluation without leakage concerns

- **`post_cutoff`**: Issues created after `2025-06-01T00:00:00Z`
  - These examples may contain information available in training data
  - Should be treated as holdout/validation set

**Note**: The split is determined by `issue.created_at`, not `pr.merged_at` or `pr.opened_at`, ensuring clean separation regardless of PR timing.

## Cutoff Rule

The leakage cutoff is configurable in `configs/bench.toml`:

```toml
[bench]
leakage_cutoff = "2025-06-01T00:00:00Z"
```

Any example where `issue.created_at >= leakage_cutoff` gets `split_tag = "post_cutoff"`. Otherwise, `split_tag = "pre_cutoff"`.

## Example

```json
{
  "issue": {"owner": "django", "repo": "django", "number": 12345},
  "base_commit_sha": "abc123def456...",
  "issue_title": "Fix authentication bug in login flow",
  "issue_body": "When users enter special characters in password field...",
  "gold_files_all": ["django/contrib/auth/views.py"],
  "gold_files_source": ["django/contrib/auth/views.py"],
  "pr_number": 12346,
  "merged_at": "2025-03-15T10:30:00Z",
  "issue_created_at": "2025-03-10T08:00:00Z",
  "pr_opened_at": "2025-03-12T14:00:00Z",
  "changed_files": [
    {
      "path": "django/contrib/auth/views.py",
      "status": "modified",
      "additions": 15,
      "deletions": 5,
      "locatable_at_base": true
    }
  ],
  "split_tag": "pre_cutoff"
}
```

## Loading the Dataset

```python
import json
from pathlib import Path

records = []
for line in open("data/bench.jsonl"):
    records.append(json.loads(line))

# Filter by split
pre_cutoff = [r for r in records if r["split_tag"] == "pre_cutoff"]
post_cutoff = [r for r in records if r["split_tag"] == "post_cutoff"]
```

## Reproducibility

To regenerate the dataset with the same results:
1. Use the same `configs/bench.toml` configuration
2. Clear `.cache/github/` to force fresh GitHub API calls
3. Set `GITHUB_TOKEN` environment variable
4. Run: `uv run python -m issuescout.bench.cli --config configs/bench.toml --out data/bench.jsonl`

The miner is resumable: already-processed PR numbers are tracked via the output JSONL file.