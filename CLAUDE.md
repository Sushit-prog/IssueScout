# IssueScout Project Rules

## Project Overview
IssueScout: Given a GitHub issue URL, return ranked candidate files and functions with verifiable evidence, a plan outline, likely tests, and a deterministic readiness report. The core claim is that **every cited path and symbol is verified to exist at the cited commit**.

## Technology Stack
- Python 3.11+
- uv for dependency management
- ruff for linting/formatting
- mypy (strict mode on `src/`)
- pytest for testing

## Package Layout
```
src/issuescout/
├── models/      # Pydantic boundary models (no untyped dicts across boundaries)
├── bench/       # Benchmark infrastructure
├── baselines/   # Baseline methods
├── tools/       # Read-only tools (no network, no shell=True, path containment)
├── verifier/    # Citation verification
├── agent/       # Agent orchestration
├── readiness/   # Deterministic readiness report (zero LLM calls)
├── api/         # API layer
├── worker/      # Background workers
├── llm/         # LLM wrapper (ONLY place litellm is imported; token budget, cost cap, logging)
└── github/      # GitHub HTTP client (ONLY place GitHub HTTP calls happen)
tests/           # Mirrors src/ structure
tests/fixtures/  # Recorded GitHub API responses for tests
configs/         # Non-secret settings (committed)
```

## Core Rules

### Typing & Boundaries
- Every module has typed Pydantic models at its boundary
- No untyped `dict` crossing module boundaries
- All models use `model_config = ConfigDict(extra="forbid", frozen=True)`

### LLM Calls
- LLM calls ONLY through `src/issuescout/llm/` wrapper (litellm)
- Wrapper enforces per-run token and cost budget
- Wrapper logs every call
- The LLM wrapper enforces a hard per-run cost cap in addition to the token budget, and aborts the run when exceeded
- NO direct provider SDK calls anywhere else

### Tool Safety
- Tools are read-only
- No network access inside tools
- No `shell=True`, ever
- Paths resolved and checked to stay inside repo root
- Symlink escapes rejected

### Readiness Report
- Must contain ZERO LLM calls
- Add a test that asserts this

### Untrusted Input
- Repo content and issue text are untrusted input
- Never put them in the system prompt
- Always delimit them as data

### Security
- No secrets in code
- Config via env vars only; non-secret settings may live in committed files under `configs/`
- `.env.example` committed to repo
- Never log tokens, keys or Authorization headers

### Verification
- The verifier checks paths and symbols against git objects at the cited commit (git cat-file / ls-tree), never against the working tree
- Citation paths are repo-relative, POSIX-style, no ".." segments

### Quality Gates
- Every feature ships with tests in the same change
- Run `ruff check`, `ruff format`, `mypy`, `pytest` before declaring anything done
- Commit in small steps with clear messages

### Source Code Style
- Source files use LF line endings; use pathlib, not string path manipulation

### Test Discipline
- Tests never touch the network; GitHub responses come from recorded fixtures under `tests/fixtures/`
- Never change production code to make a test pass, or a test to make code pass, without stating which and why in the commit message and in your summary. If a test and the code disagree, stop and ask me.

## Development Workflow
1. Plan in small increments
2. Write tests first (TDD)
3. Implement
4. Run quality checks locally
5. Commit with clear message