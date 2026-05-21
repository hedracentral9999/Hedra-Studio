#!/usr/bin/env python3
"""Security gate for Hedra Studio public releases.

The checks are intentionally conservative: if a file looks like local data,
credentials, private output, or a developer-only artifact, the release should
fail before upload.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SECRET_PATTERNS = [
    ("generic sk token", re.compile(rb"\bsk-[A-Za-z0-9][A-Za-z0-9_\-]{18,}\b")),
    ("anthropic token", re.compile(rb"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("gemini token", re.compile(rb"\bAIza[A-Za-z0-9_\-]{20,}\b")),
    ("telegram bot token", re.compile(rb"\b\d{7,12}:[A-Za-z0-9_\-]{30,}\b")),
    ("slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9\-]{20,}\b")),
    ("license secret", re.compile(rb"(AUTO_VIDEO_LICENSE_SECRET|LICENSE_SIGNING_SECRET|HEDRA_LICENSE_SECRET)")),
    ("known phone/bank data", re.compile(rb"(190355|078806|Techcombank|VCBDigibank)")),
]

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "settings.json",
    "telegram_config.py",
    "HANDOFF.md",
    "CLAUDE.md",
    "AUDIT_REPORT.md",
}

SENSITIVE_SUFFIXES = {
    ".mp3",
    ".mp4",
    ".mov",
    ".m4a",
    ".wav",
    ".dmg",
    ".exe",
    ".msi",
    ".zip",
}

SENSITIVE_PATH_PARTS = {
    ".claude",
    "web",
    "tools",
    "output",
    "ouput",
    "endpoints",
    "Hedra Studio Local.app",
}

TEXT_SUFFIXES = {
    ".py",
    ".pyw",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".plist",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".sh",
    ".bash",
    ".zsh",
    ".bat",
    ".ps1",
    ".iss",
    ".spec",
    ".log",
}

LOCAL_PATH_PATTERNS = [
    re.compile(rb"/Users/admin"),
    re.compile(rb"C:\\Users\\admin", re.I),
]


def run(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=str(cwd), text=True, stderr=subprocess.STDOUT)


def tracked_files(root: Path) -> list[Path]:
    try:
        out = run(["git", "ls-files"], root)
        return [root / line for line in out.splitlines() if line.strip()]
    except Exception:
        return [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]


def should_skip_source_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    if rel.startswith((".git/", "venv/", ".venv/", "dist/", "build/TTS/", ".pyinstaller-cache/")):
        return True
    if rel in {"LICENSE"}:
        return False
    return False


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except Exception:
        return b""


def check_sensitive_path(path: Path, rel: str, errors: list[str], source_mode: bool):
    name = path.name
    parts = set(path.parts)
    if name in SENSITIVE_NAMES:
        errors.append(f"sensitive file present: {rel}")
    if path.suffix.lower() in SENSITIVE_SUFFIXES and source_mode:
        errors.append(f"release/generated media tracked in source: {rel}")
    if any(part in parts for part in SENSITIVE_PATH_PARTS):
        errors.append(f"private/internal path present: {rel}")


def _looks_textual(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    try:
        sample = path.read_bytes()[:4096]
    except Exception:
        return False
    if b"\0" in sample:
        return False
    return True


def scan_file_content(path: Path, rel: str, errors: list[str], include_local_paths: bool, source_mode: bool):
    if rel in {"README.md", "scripts/security_audit_release.py", "app_utils.py"}:
        include_local_paths = False
    if not source_mode and not _looks_textual(path):
        return
    data = read_bytes(path)
    if not data:
        return
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            errors.append(f"{label} pattern found in {rel}")
    if include_local_paths:
        for pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(data):
                errors.append(f"local developer path found in {rel}")


def scan_source(root: Path) -> list[str]:
    errors: list[str] = []
    for path in tracked_files(root):
        if not path.exists() or not path.is_file() or should_skip_source_file(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        check_sensitive_path(path, rel, errors, source_mode=True)
        scan_file_content(path, rel, errors, include_local_paths=True, source_mode=True)
    return errors


def collect_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    return [p for p in path.rglob("*") if p.is_file()]


def scan_artifact_path(path: Path, root: Path | None = None) -> list[str]:
    errors: list[str] = []
    base = root or path
    for file in collect_files(path):
        rel = file.relative_to(base).as_posix() if file.is_relative_to(base) else str(file)
        check_sensitive_path(file, rel, errors, source_mode=False)
        scan_file_content(file, rel, errors, include_local_paths=True, source_mode=False)
    return errors


def exact_secret_values() -> list[bytes]:
    values: list[bytes] = []
    candidates = [
        Path.home() / "Library/Application Support/TTSApp/settings.json",
        Path.home() / "Library/Application Support/Hedra Studio/settings.json",
        Path(os.environ.get("APPDATA", "")) / "TTSApp/settings.json" if os.environ.get("APPDATA") else None,
        Path(os.environ.get("APPDATA", "")) / "Hedra Studio/settings.json" if os.environ.get("APPDATA") else None,
    ]
    keys = {
        "genmax_api_key",
        "ds_api_key",
        "gemini_api_key",
        "claude_api_key",
        "telegram_bot_token",
        "telegram_chat_id",
        "pro_license_key",
        "auto_video_license_key",
    }
    for path in [p for p in candidates if p]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key in keys:
            value = str(data.get(key, "") or "").strip()
            if len(value) >= 8:
                values.append(value.encode())
        for item in data.get("el_api_keys") or []:
            if isinstance(item, str) and len(item.strip()) >= 8:
                values.append(item.strip().encode())
    return values


def scan_exact_values(path: Path, secrets: list[bytes]) -> list[str]:
    if not secrets:
        return []
    errors: list[str] = []
    for file in collect_files(path):
        data = read_bytes(file)
        if not data:
            continue
        for idx, secret in enumerate(secrets, start=1):
            if secret in data:
                errors.append(f"exact local secret #{idx} found in {file}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="Repo root to scan tracked source")
    parser.add_argument("--artifact", type=Path, action="append", default=[], help="Built app/extracted artifact path to scan")
    parser.add_argument("--exact-local", action="store_true", help="Scan artifacts for exact local settings secret values")
    args = parser.parse_args()

    errors: list[str] = []
    if args.source:
        errors.extend(scan_source(args.source.resolve()))
    for artifact in args.artifact:
        errors.extend(scan_artifact_path(artifact.resolve()))
    if args.exact_local and args.artifact:
        secrets = exact_secret_values()
        for artifact in args.artifact:
            errors.extend(scan_exact_values(artifact.resolve(), secrets))

    if errors:
        print("SECURITY AUDIT FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Security audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
