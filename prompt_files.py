from __future__ import annotations

import re
import unicodedata
from pathlib import Path


TTS_PROMPT_DIR = Path(__file__).resolve().parent / "docs" / "tts"


def style_slug(name: str) -> str:
    raw = str(name or "").strip()
    raw = raw.replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw or "prompt"


def style_prompt_path(name: str) -> Path:
    slug = "viral" if str(name or "").strip().lower() == "viral" else style_slug(name)
    return TTS_PROMPT_DIR / f"{slug}.md"


def read_style_prompt_file(name: str, fallback: str = "") -> str:
    path = style_prompt_path(name)
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return str(fallback or "").strip()


def write_style_prompt_file(name: str, prompt: str) -> Path:
    TTS_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    path = style_prompt_path(name)
    path.write_text(str(prompt or "").strip() + "\n", encoding="utf-8")
    return path


def delete_style_prompt_file(name: str) -> None:
    if str(name or "").strip().lower() == "viral":
        return
    path = style_prompt_path(name)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
