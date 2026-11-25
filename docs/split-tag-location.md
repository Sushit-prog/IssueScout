# SplitTag Location Verification

## Summary
`SplitTag` is correctly located in `src/issuescout/models/benchmark.py` (the `models` package), NOT in `github/models.py`.

## Current Location
- **File**: `src/issuescout/models/benchmark.py:11-15`
- **Package**: `issuescout.models` (exported via `src/issuescout/models/__init__.py`)

```python
class SplitTag(StrEnum):
    """Split tag for train/test leakage control."""
    PRE_CUTOFF = "pre_cutoff"
    POST_CUTOFF = "post_cutoff"
```

## Import Usage
All imports correctly use `issuescout.models`:
- `src/issuescout/bench/mine.py:18`: `from issuescout.models import BenchmarkExample, ChangedFile, IssueRef, SplitTag`
- `tests/bench/test_mine.py:25`: `from issuescout.models import BenchmarkExample, IssueRef, SplitTag`
- `src/issuescout/models/__init__.py:3`: Re-exports `SplitTag` from `issuescout.models.benchmark`

## Verification
No references to `issuescout.github.models.SplitTag` exist in the codebase:
- `grep -r "issuescout.github.models.*SplitTag" src/ tests/` → **No matches**
- `grep -r "from issuescout.github.models import.*SplitTag" src/ tests/` → **No matches**
- `grep -r "class SplitTag" src/issuescout/github/` → **No matches**

## Git History
- `SplitTag` was introduced in commit `f3b1d30` directly in `src/issuescout/models/benchmark.py`
- `src/issuescout/github/models.py` has never contained `SplitTag` (verified via `git log --all --oneline -S "SplitTag" -- src/issuescout/github/models.py`)

## Conclusion
Fix-up Item 6 ("Move SplitTag out of github/models.py into bench or models package") is **already satisfied** - `SplitTag` is already in the `models` package, not in `github/models.py`. No action needed.