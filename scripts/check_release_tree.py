#!/usr/bin/env python3
"""Check that a sanitized release tree does not contain blocked paths."""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

BLOCKED_PATTERNS = [
    ".env",
    ".env.*",
    "config.json",
    "config.local.json",
    "*.local.json",
    ".claude",
    ".claude/*",
    "*/.claude/*",
    "settings.local.json",
    "*/settings.local.json",
    "twitter_cookies.json",
    "*cookie*.json",
    "*cookies*.json",
    "*session*.json",
    "*token*.json",
    "*secret*.json",
    "*credentials*.json",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "logs/*",
    "*/logs/*",
    "outputs/*",
    "*/outputs/*",
    "runs/*",
    "artifacts/*",
    "scratch/*",
    "node_modules/*",
    "*/node_modules/*",
    ".conda-env/*",
    "*/.conda-env/*",
    "*.pt",
    "*.pth",
    "*.ckpt",
    "*.safetensors",
    "AR-in-CC/config/remote.*.json",
]

ALLOW_PATTERNS = [
    ".env.example",
    "gpt-researcher/.env.example",
    "config.example.json",
    "AR-in-CC/config/remote.example.json",
]

DEFAULT_MAX_BYTES = 25 * 1024 * 1024


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="release tree to check")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = []

    for path in root.rglob("*"):
        if path == root:
            continue
        rel = path.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        if matches(rel, ALLOW_PATTERNS):
            continue
        if matches(rel, BLOCKED_PATTERNS):
            findings.append((rel, "blocked-path"))
            continue
        if path.is_file():
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > args.max_bytes:
                findings.append((rel, f"large-file>{args.max_bytes}"))

    if findings:
        print("Release tree check failed:", file=sys.stderr)
        for rel, reason in findings:
            print(f"{rel}: {reason}", file=sys.stderr)
        return 1

    print("Release tree check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
