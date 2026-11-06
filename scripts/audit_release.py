"""Check a public release tree/history for excluded artifacts and common disclosures."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "local_user_path": re.compile(
        r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\"']+", re.IGNORECASE
    ),
    "chat_attachment": re.compile(
        r"codex[-]clipboard[-]|[.]codex[\\/]attachments[\\/]", re.IGNORECASE
    ),
    "chat_context": re.compile(
        r"<(?:environment_context|send_user_message_question_reply|external_codex_apps_open_page)>",
        re.IGNORECASE,
    ),
    "credential_pattern": re.compile(r"\b(?:sk[-]|gh[pousr]_)[A-Za-z0-9_-]{24,}\b"),
}


def forbidden_path(path: str) -> bool:
    p = Path(path)
    return (
        any(part in {".tmp", ".private", "local-results", "attachments"} for part in p.parts)
        or (p.name.startswith(".env") and p.name != ".env.example")
        or p.suffix.lower() in {".db", ".sqlite", ".log"}
        or (p.parts and p.parts[0] == "reports" and p.suffix.lower() == ".json")
    )


def findings(path: str, content: str) -> list[dict]:
    result = [
        {"path": path, "finding": name}
        for name, pattern in PATTERNS.items()
        if pattern.search(content)
    ]
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
    ):
        value = os.environ.get(name, "")
        if len(value) > 12 and value in content:
            result.append({"path": path, "finding": f"configured_credential:{name}"})
    return result


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history", action="store_true", help="also check every blob reachable from HEAD"
    )
    args = parser.parse_args()
    failures = []
    files = list(filter(None, git("ls-files", "-z").split("\0")))
    for name in files:
        if forbidden_path(name):
            failures.append({"path": name, "finding": "excluded_artifact"})
        try:
            failures.extend(findings(name, Path(name).read_text(encoding="utf-8")))
        except UnicodeError:
            failures.append({"path": name, "finding": "unexpected_binary"})
    historical_blobs = 0
    if args.history:
        for row in git("rev-list", "--objects", "HEAD").splitlines():
            oid, _, name = row.partition(" ")
            if not name or git("cat-file", "-t", oid) != "blob":
                continue
            historical_blobs += 1
            if forbidden_path(name):
                failures.append({"path": name, "finding": "historical_excluded_artifact"})
            try:
                failures.extend(findings(name, git("cat-file", "-p", oid)))
            except UnicodeError:
                failures.append({"path": name, "finding": "historical_binary"})
    print(
        json.dumps(
            {
                "tracked_files": len(files),
                "historical_blobs": historical_blobs,
                "findings": failures,
            },
            indent=2,
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
