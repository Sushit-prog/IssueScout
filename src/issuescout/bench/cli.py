"""Benchmark mining CLI."""

import argparse
import logging
import sys
from pathlib import Path

from issuescout.bench.config import BenchConfig
from issuescout.bench.mine import run_mining


def setup_logging(verbose: bool) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_config(config_path: Path) -> BenchConfig:
    """Load configuration from TOML file."""
    import tomllib
    from datetime import UTC, datetime

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    # Parse repos
    from issuescout.bench.config import RepoConfig

    repos = []
    for repo_data in data.get("repos", []):
        repo = RepoConfig(
            owner=repo_data["owner"],
            name=repo_data["name"],
            max_prs=repo_data.get("max_prs", 500),
            since=(
                datetime.fromisoformat(repo_data["since"].replace("Z", "+00:00")).replace(
                    tzinfo=UTC
                )
                if repo_data.get("since")
                else None
            ),
            until=(
                datetime.fromisoformat(repo_data["until"].replace("Z", "+00:00")).replace(
                    tzinfo=UTC
                )
                if repo_data.get("until")
                else None
            ),
        )
        repos.append(repo)

    return BenchConfig(
        repos=repos,
        leakage_cutoff=datetime.fromisoformat(
            data["leakage_cutoff"].replace("Z", "+00:00")
        ).replace(tzinfo=UTC),
        out_path=Path(data.get("out_path", "data/bench.jsonl")),
        cache_dir=Path(data.get("cache_dir", ".cache/github")),
        max_concurrent=data.get("max_concurrent", 1),
    )


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m issuescout.bench.mine",
        description="Mine benchmark examples from GitHub PRs",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/bench.toml"),
        help="Path to benchmark config TOML",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Override output JSONL path",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    try:
        config = load_config(args.config)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        return 1

    if args.out:
        config = BenchConfig(
            repos=config.repos,
            leakage_cutoff=config.leakage_cutoff,
            out_path=args.out,
            cache_dir=config.cache_dir,
            max_concurrent=config.max_concurrent,
        )

    # Ensure output directory exists
    config.out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        stats = run_mining(config)
        print("\n=== Mining Complete ===")
        for repo, repo_stats in stats.items():
            print(
                f"  {repo}: processed={repo_stats['processed']} "
                f"kept={repo_stats['kept']} dropped={repo_stats['dropped']} "
                f"errors={repo_stats['errors']}"
            )
        return 0
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130
    except Exception as e:
        logging.error(f"Mining failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
