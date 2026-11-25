# Renamed File Handling in IssueScout

## Overview
When a PR renames a file, GitHub's REST API `/repos/{owner}/{repo}/pulls/{number}/files` returns a single entry with:
- `filename`: the new path
- `status`: "renamed"
- `previous_filename`: the old path

## Where Renamed Old Paths Come From

### 1. GitHub API Response (REST)
**Field**: `previous_filename` in the file object from `/repos/{owner}/{repo}/pulls/{number}/files`
**File**: `src/issuescout/github/models.py:77`
```python
previous_filename: str | None = None
```

### 2. ChangedFileData Model
**File**: `src/issuescout/github/models.py:70-82`
The `ChangedFileData` Pydantic model captures `previous_filename` from the REST API response.

### 3. Client Parsing
**File**: `src/issuescout/github/client.py:327`
```python
previous_filename=item.get("previous_filename"),
```

### 4. Gold File Computation (filters.py)
**File**: `src/issuescout/bench/filters.py:216-217`
```python
if f.status == FileStatus.RENAMED and f.previous_filename:
    gold.append(f.previous_filename)
```
For `gold_files_all`, the **old path** (`previous_filename`) is used because that's the path that existed at the base commit.

### 5. Locatable File Computation (filters.py)
**File**: `src/issuescout/bench/filters.py:245-248`
```python
if f.status == FileStatus.RENAMED and f.previous_filename:
    # Renamed files: old path exists at base, new path doesn't
    result.append((f.previous_filename, True))   # old path - locatable at base
    result.append((f.filename, False))           # new path - NOT locatable at base
```
For `changed_files_with_locatable`, **two entries** are produced:
1. `(old_path, True)` - the old path exists at the base commit
2. `(new_path, False)` - the new path does NOT exist at the base commit

This correctly models the git history: at the base commit, only the old path exists.

## Test That Pins This Behavior

**File**: `tests/bench/test_filters.py:311-338`
**Test**: `TestGoldComputation.test_compute_changed_files_with_locatable`

```python
def test_compute_changed_files_with_locatable(self):
    files = [
        ChangedFileData(filename="src/a.py", status=FileStatus.MODIFIED, additions=1, deletions=1),
        ChangedFileData(
            filename="src/new.py",
            status=FileStatus.RENAMED,
            previous_filename="src/old.py",
            additions=1,
            deletions=1,
        ),
        ChangedFileData(filename="src/deleted.py", status=FileStatus.REMOVED, additions=0, deletions=10),
        ChangedFileData(filename="src/added.py", status=FileStatus.ADDED, additions=10, deletions=0),
    ]
    result = _compute_changed_files_with_locatable(files)
    # Renamed files produce TWO entries: old_path (True) and new_path (False)
    assert result == [
        ("src/a.py", True),
        ("src/old.py", True),      # <-- old path from previous_filename
        ("src/new.py", False),     # <-- new path from filename
        ("src/deleted.py", True),
        ("src/added.py", False),
    ]
```

This test explicitly verifies that:
1. Renamed files produce **two** entries in the result
2. The first entry uses `previous_filename` ("src/old.py") with `locatable_at_base=True`
3. The second entry uses `filename` ("src/new.py") with `locatable_at_base=False`

## Fixture That Provides Test Data

**File**: `tests/fixtures/github/pr_files_response.json:29-38`
```json
{
  "sha": "jkl012",
  "filename": "src/utils.py",
  "status": "renamed",
  "previous_filename": "src/helpers.py",
  "additions": 0,
  "deletions": 0,
  "changes": 0,
  "patch": ""
}
```

This fixture is used by `tests/github/test_client.py::TestGitHubClient::test_fetch_pr_files_parses_all_statuses` (line 82-84) to verify the client correctly parses renamed files with `previous_filename`.

## Summary

| Step | Source | Field/Method |
|------|--------|--------------|
| 1. GitHub REST API | `/pulls/{n}/files` | `previous_filename` in response |
| 2. Model | `src/issuescout/github/models.py:77` | `ChangedFileData.previous_filename` |
| 3. Client | `src/issuescout/github/client.py:327` | `item.get("previous_filename")` |
| 4. Gold files (all) | `src/issuescout/bench/filters.py:216-217` | Uses `f.previous_filename` for RENAMED |
| 5. Locatable files | `src/issuescout/bench/filters.py:245-248` | Produces 2 entries: (old, True), (new, False) |
| 6. Test | `tests/bench/test_filters.py:311-338` | `test_compute_changed_files_with_locatable` |
| 7. Fixture | `tests/fixtures/github/pr_files_response.json:29-38` | `previous_filename: "src/helpers.py"` |