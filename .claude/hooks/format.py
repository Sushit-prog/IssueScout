#!/usr/bin/env python3
"""PostToolUse hook to auto-format Python files with ruff."""

import json
import sys
import subprocess
from pathlib import Path


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path.endswith(".py"):
        return 0

    # Resolve path relative to project directory
    project_dir = Path.cwd()
    try:
        full_path = (project_dir / file_path).resolve()
        # Check it's within project
        full_path.relative_to(project_dir)
    except (ValueError, OSError):
        return 0

    # Run ruff format
    try:
        subprocess.run(
            ["uv", "run", "ruff", "format", str(full_path)],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
