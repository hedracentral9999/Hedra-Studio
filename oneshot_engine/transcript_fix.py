"""
transcript_fix.py — Chuyên gia sửa transcript.
Bước 1: Regex local (TECH_TERMS).
Bước 2: AI DeepSeek sửa chuyên sâu (prompt từ prompts/transcript_fix.txt).
"""

import json
import re
from pathlib import Path
import requests
from .core import log, cost_str
from .config import TECH_TERMS, DS_API_URL, DS_MODEL


def fix_regex(segments: list[dict]) -> list[dict]:
    """Sửa lỗi ASR nhanh bằng regex (bước 1, chạy local trước khi gửi AI)."""
    for seg in segments:
        text = seg.get("text", "")
        for pattern, repl in TECH_TERMS:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        seg["text"] = text
    return segments


def load_prompt_template() -> str:
    """Đọc prompt template từ file."""
    prompt_path = Path(__file__).parent / "prompts" / "transcript_fix.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    # Fallback nội tuyến
    return """Sửa transcript thô thành sạch tiếng Việt.
Giữ nguyên timestamp [X.Xs] đầu mỗi dòng.
Trả nguyên transcript đã sửa, không thêm giải thích.

Tên file: {source_stem}

Transcript thô:
{raw_text}"""


def ai_fix(segments: list[dict], source_stem: str, api_key: str,
           max_chars: int = 8000) -> tuple[str, str, str]:
    """
    Prompt DeepSeek: sửa lỗi Whisper → transcript sạch.
    Returns: (cleaned_text, prompt_sent, raw_response_json)
    """
    if not segments:
        return "", "", ""

    raw_lines = []
    for seg in segments[:120]:
        t = seg.get("text", "").strip()
        if t:
            raw_lines.append(f"[{seg['start']:.1f}s] {t}")
    raw_text = "\n".join(raw_lines)[:max_chars]

    template = load_prompt_template()
    prompt = template.format(source_stem=source_stem, raw_text=raw_text)

    try:
        resp = requests.post(
            DS_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": DS_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 2000,
            },
            timeout=45,
        )
        resp.raise_for_status()
        body = resp.json()
        msg = body["choices"][0]["message"]
        cleaned = msg.get("content", "").strip()
        if not cleaned:
            cleaned = msg.get("reasoning_content", "").strip()
        log(f"Transcript sạch · {cost_str(body.get('usage', {}))}")
        return cleaned, prompt, json.dumps(body, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Sửa transcript lỗi: {e} — dùng bản regex")
        return "", prompt, f"ERROR: {e}"
