"""Executable dependency rules for the clean architecture."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "src" / "load_balancer"

FORBIDDEN_PREFIXES = {
    "domain": (
        "load_balancer.application",
        "load_balancer.ports",
        "load_balancer.adapters",
        "load_balancer.infrastructure",
    ),
    "ports": (
        "load_balancer.application",
        "load_balancer.adapters",
        "load_balancer.infrastructure",
    ),
    "application": (
        "load_balancer.adapters",
        "load_balancer.infrastructure",
    ),
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_inner_layers_do_not_import_outer_layers() -> None:
    violations: list[str] = []
    for layer, forbidden in FORBIDDEN_PREFIXES.items():
        for path in (PACKAGE / layer).rglob("*.py"):
            for module in imported_modules(path):
                if module.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(PACKAGE)} imports {module}"
                    )
    assert violations == []
