"""Layer rules from AGENTS.md 3.1 / ARCHITECTURE 3.1, checked on import statements.

Usage (from backend/):  python scripts/check_layers.py [app_dir]
Exit code 1 and one line per violation if a rule is broken.
"""

import ast
import sys
from pathlib import Path

DOMAIN = ("detectors", "fusion", "policy", "graph", "crypto", "parsers", "output", "eval")
DOMAIN_FORBIDDEN = (
    "app.api", "app.services", "app.storage", "app.runtime", "app.main", "app.cli",
    "fastapi", "starlette", "sqlalchemy", "alembic",
)  # fmt: skip
RULES: dict[str, tuple[str, ...]] = {
    **{pkg: DOMAIN_FORBIDDEN for pkg in DOMAIN},
    "api": ("app.storage", "app.runtime", "sqlalchemy"),  # API goes through services
    "storage": ("app.api", "app.services", "app.runtime", "fastapi"),
    "services": ("app.api", "fastapi"),
}


def imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.lineno, node.module))
    return out


def check(app_dir: Path) -> list[str]:
    errors = []
    for pkg, banned in RULES.items():
        for f in sorted((app_dir / pkg).rglob("*.py")):
            for line, mod in imports(f):
                if any(mod == b or mod.startswith(b + ".") for b in banned):
                    errors.append(
                        f"{f.relative_to(app_dir.parent)}:{line}: {pkg} must not import {mod}"
                    )
    return errors


def main() -> int:
    app_dir = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "app"
    )
    errors = check(app_dir)
    for e in errors:
        print(e)
    print(f"layer check: {'FAIL' if errors else 'OK'} ({len(errors)} violation(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
