"""Check local Markdown targets without making network requests."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main() -> None:
    root = Path.cwd().resolve()
    files = [
        root / name
        for name in (
            "README.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "RESEARCH.md",
            "ROADMAP.md",
            "CHANGELOG.md",
        )
    ]
    files += list((root / "docs").glob("*.md")) + list((root / "reports").glob("*.md"))
    failures = []
    for path in files:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = target.strip().strip("<>")
            if urlsplit(target).scheme or target.startswith("#"):
                continue
            destination = (path.parent / unquote(target.split("#", 1)[0])).resolve()
            if not destination.is_relative_to(root) or not destination.exists():
                failures.append(f"{path.relative_to(root)} -> {target}")
    if failures:
        raise SystemExit("Missing or out-of-tree Markdown targets:\n" + "\n".join(failures))
    print(f"Local links checked in {len(files)} Markdown files.")


if __name__ == "__main__":
    main()
