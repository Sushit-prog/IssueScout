"""Test that network imports are isolated to llm/ and github/ modules."""

import ast
from pathlib import Path

FORBIDDEN_IMPORTS = {
    "httpx",
    "requests",
    "litellm",
    "urllib.request",
    "socket",
}

ALLOWED_MODULES = {
    "issuescout.llm",
    "issuescout.github",
}


def find_python_files(root: Path) -> list[Path]:
    """Find all .py files under root."""
    return list(root.rglob("*.py"))


def get_imports(file_path: Path) -> set[str]:
    """Extract all imported module names from a Python file."""
    imports = set()
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    except SyntaxError:
        pass  # Skip files with syntax errors
    return imports


def get_module_name(file_path: Path, src_root: Path) -> str:
    """Convert file path to module name."""
    rel = file_path.relative_to(src_root)
    parts = rel.with_suffix("").parts
    return ".".join(parts)


def test_network_imports_isolated():
    """Verify that only llm/ and github/ modules import network libraries."""
    src_root = Path("src")
    py_files = find_python_files(src_root)

    violations = []

    for py_file in py_files:
        module_name = get_module_name(py_file, src_root)
        imports = get_imports(py_file)

        # Check if this module is allowed to have network imports
        is_allowed = any(module_name.startswith(allowed) for allowed in ALLOWED_MODULES)

        forbidden_found = imports & FORBIDDEN_IMPORTS
        if forbidden_found and not is_allowed:
            violations.append(f"{module_name} ({py_file}): imports {sorted(forbidden_found)}")

    if violations:
        msg = "Network imports found outside allowed modules (llm/, github/):\n"
        msg += "\n".join(violations)
        raise AssertionError(msg)


if __name__ == "__main__":
    test_network_imports_isolated()
    print("OK: Network imports properly isolated")
