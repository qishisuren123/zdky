#!/usr/bin/env python3
"""Redacted secret-pattern scan for a sanitized release tree.

This is a lightweight pre-publish guard. It intentionally reports only the file,
line, and rule name, never the matched token text.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".cache",
}

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
    ".db",
}

ALLOW_PLACEHOLDER_PATTERNS = (
    "your_",
    "replace-with-",
    "example",
    "placeholder",
    "sk-your",
    "AIza-your",
)

RULES = [
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{20,}")),
    ("openai-style-key", re.compile(r"\bsk-[0-9A-Za-z_-]{20,}")),
    ("tavily-key", re.compile(r"\btvly-[0-9A-Za-z_-]{20,}")),
    ("anthropic-token", re.compile(r"\bsk-ant-[0-9A-Za-z_-]{20,}")),
    ("bearer-token", re.compile(r"Bearer\s+[0-9A-Za-z._~+/=-]{20,}", re.IGNORECASE)),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("service-account-json", re.compile(r'"type"\s*:\s*"service_account"')),
    ("private-path", re.compile(r"/data/(renyiming|liuxiang|zhangxiao)/")),
]


def should_skip(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def is_placeholder(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in ALLOW_PLACEHOLDER_PATTERNS)


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if path.is_file() and not should_skip(path):
            yield path


def scan_file(path: Path):
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        findings.append((path, 0, "read-error", str(exc)))
        return findings

    for line_no, line in enumerate(text.splitlines(), start=1):
        if is_placeholder(line):
            continue
        for rule_name, pattern in RULES:
            if pattern.search(line):
                findings.append((path, line_no, rule_name, "redacted"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="release tree to scan")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = []
    for path in iter_files(root):
        findings.extend(scan_file(path))

    if findings:
        print("Secret-pattern scan failed; matched content is redacted:", file=sys.stderr)
        for path, line_no, rule_name, _ in findings:
            rel = path.relative_to(root) if path.is_relative_to(root) else path
            print(f"{rel}:{line_no}: {rule_name}", file=sys.stderr)
        return 1

    print("Secret-pattern scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
