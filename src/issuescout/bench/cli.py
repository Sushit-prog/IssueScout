"""Benchmark mining CLI (deprecated, use `python -m issuescout.bench.mine` or `issuescout-mine`)."""

import warnings

from issuescout.bench.mine import load_config, main, run_mining

# Re-export for backwards compatibility
__all__ = ["load_config", "main", "run_mining"]


def _deprecated() -> None:
    warnings.warn(
        "issuescout.bench.cli is deprecated; use issuescout.bench.mine instead",
        DeprecationWarning,
        stacklevel=2,
    )


# Trigger deprecation warning on import
_deprecated()
