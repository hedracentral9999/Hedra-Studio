"""
core/paths.py — Path, output dir, API key, recent titles.
"""

import json
from datetime import datetime
from pathlib import Path


def log(msg: str):
    """In log kèm indent 2 spaces."""
    print(f"  {msg}", flush=True)


def api_key_from_settings() -> str:
    """Đọc DeepSeek API key từ settings.json của Hedra Studio."""
    settings_path = Path.home() / "Library" / "Application Support" / "Hedra Studio" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text())
        return settings.get("ds_api_key", "")
    except Exception:
        return ""


def output_root(out_dir: str = "") -> Path:
    if out_dir:
        return Path(out_dir)
    return Path(__file__).parent.parent.parent / "output" / "one-shot"


def make_job_dir(source_stem: str, out_dir: str = "") -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%H%M%S")
    job_dir = output_root(out_dir) / today / f"{source_stem}-{ts}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def resolve_lut(custom_path: str = "") -> str:
    from ..config import DEFAULT_LUT
    candidates = [custom_path] if custom_path else []
    candidates.extend([
        DEFAULT_LUT,
        str(Path.home() / "hedra-studio" / "luts" / "DJI OSMO Osmo Nano D-Log M to Rec.709 V1.cube"),
    ])
    for p in candidates:
        if p and Path(p).exists():
            return str(Path(p).expanduser().resolve())
    return ""


def recent_titles(out_dir: str = "", days: int = 1, limit: int = 50) -> list[str]:
    titles = []
    root = output_root(out_dir)
    if not root.exists():
        return titles
    cutoff = datetime.now().timestamp() - days * 86400
    for date_dir in sorted(root.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        try:
            if date_dir.stat().st_mtime < cutoff:
                continue
        except Exception:
            continue
        for job_dir in sorted(date_dir.iterdir(), reverse=True):
            report = job_dir / "report.json"
            if not report.exists():
                continue
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
                t = str(data.get("title", "")).strip()
                if t and t not in titles:
                    titles.append(t)
                    if len(titles) >= limit:
                        return titles
            except Exception:
                continue
    return titles


def cost_vnd(usage: dict) -> int:
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost_usd = (prompt_tokens * 0.14 + completion_tokens * 0.28) / 1_000_000
    return int(cost_usd * 26000)


def cost_str(usage: dict) -> str:
    return f"~{cost_vnd(usage)}đ"
