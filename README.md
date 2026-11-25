# IssueScout

**Problem**: Given a GitHub issue URL, return ranked candidate files and functions with verifiable evidence, a plan outline, likely tests, and a deterministic readiness report.

**Core Claim**: Every cited path and symbol is verified to exist at the cited commit.

## Approach

IssueScout is built on a **benchmark-first** philosophy:

1. **Benchmark Dataset**: Curated from real GitHub PRs with ground-truth file changes
2. **Verifiable Citations**: Every candidate cites a path, symbol, and line range that is verified against the base commit
3. **Zero-LLM Readiness Report**: The readiness report contains no LLM calls — it is purely deterministic
4. **Strict Boundaries**: All module boundaries use typed Pydantic models; no untyped dicts cross boundaries

## Architecture

```
src/issuescout/
├── models/      # Pydantic boundary models
├── bench/       # Benchmark infrastructure
├── baselines/   # Baseline methods (BM25, embeddings, etc.)
├── tools/       # Read-only tools + LLM wrapper (litellm)
├── verifier/    # Citation verification against git
├── agent/       # Agent orchestration
├── readiness/   # Deterministic readiness report (zero LLM)
├── api/         # API layer
└── worker/      # Background workers
```

## Development

```bash
# Install dependencies
uv sync --dev

# Run linters and tests
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest -v
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit .env with your keys
```

## License

MIT