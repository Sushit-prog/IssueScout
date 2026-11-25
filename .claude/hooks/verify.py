#!/usr/bin/env python3
"""Stop hook that runs lint, type-check, and tests before stopping."""

import json
import subprocess
import sys


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    # If stop_hook_active is true, exit immediately to prevent loops
    if data.get("stop_hook_active"):
        return 0

    checks = [
        ("ruff check", ["uv", "run", "ruff", "check"]),
        ("mypy", ["uv", "run", "mypy", "src"]),
        ("pytest", ["uv", "run", "pytest", "-q", "-x"]),
    ]

    for name, cmd in checks:
        returncode, stdout, stderr = run_cmd(cmd, timeout=120)
        if returncode != 0:
            # Print short summary to stderr
            output = (stdout + "\n" + stderr).strip()
            lines = [line for line in output.split("\n") if line.strip()]
            # Show last 20 lines of output
            summary = "\n".join(lines[-20:]) if lines else "No output"
            print(f"[verify hook] FAILED: {name}", file=sys.stderr)
            print(f"[verify hook] --- {name} output (tail) ---", file=sys.stderr)
            print(summary, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
