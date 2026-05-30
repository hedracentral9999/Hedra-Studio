"""
auto_video_workers.py — Workers cho tab Auto Video.
Dependency: app_constants → app_utils → auto_video_workers
"""

import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import base64
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter

from app_utils import DEFAULT_OUT, get_auto_video_engine_dir, get_auto_video_env_local, load_settings


# ── Helpers ───────────────────────────────────────────────────────────────

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

RECOMMENDED_CLAUDE_MODEL = "claude-sonnet-4-6"
LEGACY_DEFAULT_CLAUDE_MODELS = {
    "",
    "claude-3-5-haiku-20241022",
    "claude-sonnet-4-20250514",
}

ESCBASE_VENDOR_ROOT = Path(__file__).resolve().parent / "vendor" / "escbase-template3"
ESCBASE_TEMPLATE_ID = "escbase-slide-starter"
ESCBASE_SLIDE_COUNTS = [1, 3, 3, 3, 4, 3]
ONE_SHOT_PIPELINE_VERSION = "2.10-industry-toolbar"

_FFMPEG_ENCODERS_CACHE: set[str] | None = None
_WHISPER_MODEL_CACHE: dict[str, object] = {}
_WHISPER_MODEL_LOCK = threading.Lock()
_WHISPER_TRANSCRIBE_LOCK = threading.Lock()
_THUMB_TRAILING_BAD_WORDS = {
    "HOẶC", "VA", "VÀ", "VỚI", "ĐỂ", "DE", "THÌ", "THI", "CỦA", "CUA", "CHO",
    "TRÊN", "TREN", "Ở", "O", "LÀ", "LA", "MÀ", "MA",
}
_THUMB_FILLER_WORDS = {
    "ĐƯỢC", "DUOC", "ĐƯỢC KHÔNG", "KHÔNG", "KHONG", "NHÉ", "NHE", "NHA",
}
_THUMB_GENERIC_PREFIXES = (
    "CAPTION FULL ",
    "CAPTION ",
    "HASHTAGS ",
    "HASHTAG ",
    "LÀM THẾ NÀO ĐỂ ",
    "LAM THE NAO DE ",
    "LÀM SAO ĐỂ ",
    "LAM SAO DE ",
    "CÁCH ĐỂ ",
    "CACH DE ",
    "HƯỚNG DẪN ",
    "HUONG DAN ",
)
_THUMB_TECH_TERM_REPLACEMENTS = [
    (r"\bM[ÔO]\s+M[ÔO]\b", "MOMO"),
    (r"\bMO\s+MO\b", "MOMO"),
    (r"\bMOMO\b", "MOMO"),
    (r"\bZALO\s+PAY\b", "ZALOPAY"),
    (r"\bZALOPAY\b", "ZALOPAY"),
    (r"\bSHOPEE\s+PAY\b", "SHOPEEPAY"),
    (r"\bSHOPPE\s+PAY\b", "SHOPEEPAY"),
    (r"\bSHOPEEPAY\b", "SHOPEEPAY"),
    (r"\bVI[ỆE]T\s*QR\b", "VIETQR"),
    (r"\bVIET\s*QR\b", "VIETQR"),
    (r"\bQR\b", "QR"),
    (r"\bHUBDEX\b", "HUB DEX"),
    (r"\bXẠC\s*NHANH\b", "SẠC NHANH"),
    (r"\bXAC\s*NHANH\b", "SẠC NHANH"),
    (r"\bS[ÉE]T\s*PLAY\b", "CH PLAY"),
    (r"\bSETPLAY\b", "CH PLAY"),
    (r"\bS[ÉE]T\s*PL[AE]Y\b", "CH PLAY"),
    (r"\bCH\s*PL[AE]Y\b", "CH PLAY"),
    (r"\bPLAY\s*STORE\b", "CH PLAY"),
    (r"\bSAMSUNGDEX\b", "SAMSUNG DEX"),
    (r"\bSAMSUNG\s+DEX\b", "SAMSUNG DEX"),
    (r"\bSAMSUNG\s+DECK\b", "SAMSUNG DEX"),
    (r"\bCHẾ\s+ĐỘ\s+DECK\b", "CHẾ ĐỘ DEX"),
    (r"\bDEX\s+MODE\b", "CHẾ ĐỘ DEX"),
    (r"\bTYPE\s*[- ]?\s*C\b", "TYPE-C"),
    (r"\bUSB\s*[- ]?\s*C\b", "USB-C"),
    (r"\bHD\s*MI\b", "HDMI"),
    (r"\b4K\s*120\b", "4K 120HZ"),
    (r"\b4K120HZ\b", "4K 120HZ"),
    (r"\b4K120\b", "4K 120HZ"),
    (r"\bGA\s*N\b", "GAN"),
    (r"\bP\s*D\b", "PD"),
    (r"\bIPHONE\b", "IPHONE"),
    (r"\bANKER\b", "ANKER"),
    (r"\bBASEUS\b", "BASEUS"),
    (r"\bUGREEN\b", "UGREEN"),
    (r"\bBOXPHONE\b", "BOX PHONE"),
    (r"\bBOX\s+PHONE\b", "BOX PHONE"),
    (r"\bPOCKET\s+BAR\b", "POCKET 3"),
    (r"\bPOCKET\s+BA\b", "POCKET 3"),
    (r"\bPOCKET\s+3\s+BAR\b", "POCKET 3"),
    (r"\bTU\s+VIT\b", "TUA VÍT"),
    (r"\bTÔ\s+VÍT\b", "TUA VÍT"),
    (r"\bTO\s+VIT\b", "TUA VÍT"),
    (r"(?<!TUA\s)\bVÍT\s+XIAOMI\b", "TUA VÍT XIAOMI"),
]
_THUMB_KNOWN_BRANDS = {
    "ANKER", "BASEUS", "UGREEN", "XIAOMI", "SAMSUNG", "IPHONE", "APPLE",
    "DJI", "ESR", "MCDODO", "ORICO", "AUKC", "HYPERDRIVE",
}
_THUMB_PROTECTED_PHRASES = (
    "BOX SAMSUNG DEX",
    "SAMSUNG DEX",
    "HDMI 2.1",
    "HDMI 2.0",
    "TYPE-C",
    "USB-C",
    "CH PLAY",
    "SIM 4G",
    "4K 120HZ",
    "LOA MOMO",
    "GIẤY PHÉP",
    "CẦN GIẤY PHÉP",
    "ĐỪNG LÀM",
    "ĐỪNG LÀM Ổ CHÍNH",
    "CHỈ DÙNG",
    "CHỈ DÙNG TẠM",
    "KIỂM TRA",
    "GỌN GÀNG",
    "DỄ HƠN",
    "TỰ LẮP",
    "SẠC NHANH",
)
_USD_TO_VND = 26000
_DEEPSEEK_PRICES = {
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"input": 0.435, "output": 0.87},
}
_GEMINI_PRICES = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
}


def whisper_runtime_status(settings: dict | None = None) -> dict:
    settings = settings or {}
    model = str(settings.get("one_shot_whisper_model", "small") or "small").strip() or "small"
    if shutil.which("ffmpeg", path=_shell_path()) is None:
        return {"status": "missing_ffmpeg", "label": "Thiếu ffmpeg", "detail": "Không tìm thấy ffmpeg để tách audio."}
    if shutil.which("ffprobe", path=_shell_path()) is None:
        return {"status": "missing_ffprobe", "label": "Thiếu ffprobe", "detail": "Không tìm thấy ffprobe để đọc video."}
    missing = []
    for package in ("numpy", "faster_whisper", "ctranslate2", "av"):
        try:
            __import__(package)
        except Exception:
            missing.append(package)
    if missing:
        return {
            "status": "missing_package",
            "label": "Thiếu package",
            "detail": "Thiếu " + ", ".join(missing) + ". App sẽ fallback bằng ffmpeg nếu vẫn chạy được.",
            "model": model,
        }
    try:
        import faster_whisper  # type: ignore
        vad_asset = Path(faster_whisper.__file__).resolve().parent / "assets" / "silero_vad_v6.onnx"
        if not vad_asset.exists():
            return {
                "status": "missing_vad_asset",
                "label": "Thiếu VAD asset",
                "detail": f"Thiếu {vad_asset}. Whisper sẽ retry không VAD nếu vẫn chạy được.",
                "model": model,
            }
    except Exception as exc:
        return {
            "status": "missing_package",
            "label": "Thiếu package",
            "detail": f"Không kiểm tra được faster-whisper asset: {exc}",
            "model": model,
        }
    return {
        "status": "ready",
        "label": "Sẵn sàng",
        "detail": f"Whisper local đã sẵn sàng. Model: {model}.",
        "model": model,
    }


def _load_whisper_model(model_size: str, log=None):
    from faster_whisper import WhisperModel  # type: ignore

    requested = (model_size or "small").strip() or "small"
    candidates = [requested]
    if requested != "small":
        candidates.append("small")
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            with _WHISPER_MODEL_LOCK:
                if candidate not in _WHISPER_MODEL_CACHE:
                    _WHISPER_MODEL_CACHE[candidate] = WhisperModel(candidate, device="cpu", compute_type="int8")
                return _WHISPER_MODEL_CACHE[candidate], candidate
        except Exception as exc:
            last_error = exc
            if log:
                log(f"Whisper model {candidate} lỗi: {exc}")
    if last_error:
        raise last_error
    raise RuntimeError("Không load được Whisper model.")


def _transcribe_with_whisper(model, audio_path: Path, *, vad_filter: bool) -> list:
    with _WHISPER_TRANSCRIBE_LOCK:
        segments, _info = model.transcribe(str(audio_path), language="vi", vad_filter=vad_filter)
        return list(segments)


def _is_whisper_vad_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "silero_vad" in text
        or "vad" in text and "onnx" in text
        or "no_suchfile" in text and "onnx" in text
    )


def _auto_batch_concurrency(total: int) -> int:
    return 1 if total > 0 else 0


def _format_gb(num_bytes: int | float) -> str:
    return f"{float(num_bytes) / (1024 ** 3):.1f}GB"


def _free_disk_bytes(path: Path) -> int:
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    return int(shutil.disk_usage(target).free)


def _render_bitrate_for_profile(profile: str | None) -> int:
    key = str(profile or "multi_1080").strip().lower()
    if key == "sharp_1440":
        return 16_000_000
    if key == "source":
        return 18_000_000
    return 12_000_000


def _estimate_one_shot_batch_disk_bytes(paths: list[str], options: dict | None = None) -> dict:
    opts = options or {}
    bitrate = _render_bitrate_for_profile(opts.get("render_profile"))
    audio_bitrate = 192_000
    output_bytes = 0
    debug_bytes = 0
    max_source_bytes = 0
    durations: list[float] = []
    for raw in paths:
        path = Path(raw)
        try:
            max_source_bytes = max(max_source_bytes, int(path.stat().st_size))
        except Exception:
            pass
        duration = 0.0
        try:
            duration = float(_ffprobe_duration(path) or 0.0)
        except Exception:
            duration = 0.0
        if duration <= 0:
            # Fallback conservative estimate for clips where ffprobe cannot read duration.
            duration = 90.0
        durations.append(duration)
        output_bytes += int(duration * (bitrate + audio_bitrate) / 8)
        # Debug stays lightweight, but audio wav/transcript/frame/thumb still need headroom.
        debug_bytes += int(max(80 * 1024 * 1024, duration * 16000 * 2 * 1.4))
    safety = max(1024 ** 3, int((output_bytes + debug_bytes) * 0.75))
    required = int(output_bytes + debug_bytes + safety)
    return {
        "required_bytes": required,
        "output_bytes": int(output_bytes),
        "debug_bytes": int(debug_bytes),
        "safety_bytes": int(safety),
        "max_source_bytes": int(max_source_bytes),
        "duration_seconds": round(sum(durations), 3),
        "count": len(paths),
    }


def _should_serialize_one_shot_render(
    out_root: Path,
    source_path: str,
    estimate: dict | None = None,
    options: dict | None = None,
) -> tuple[bool, str]:
    free_bytes = _free_disk_bytes(out_root)
    estimate = estimate or {}
    required = int(estimate.get("required_bytes") or 0)
    low_disk_floor = 6 * 1024 ** 3
    if free_bytes < low_disk_floor or (required and free_bytes < required + 2 * 1024 ** 3):
        return True, f"disk thấp ({_format_gb(free_bytes)} trống)"
    try:
        source_size = Path(source_path).stat().st_size
    except Exception:
        source_size = 0
    if source_size >= 1_500 * 1024 ** 2:
        return True, f"file lớn ({_format_gb(source_size)})"
    opts = options or {}
    heavy_encode = (
        bool(opts.get("apply_lut", True))
        or bool(opts.get("noise_reduce", True))
        or bool(opts.get("prepend_thumbnail_cover", True))
        or bool(opts.get("cut_video", True))
    )
    if heavy_encode:
        return True, "render nặng LUT/Noise/Cover dùng chung encoder"
    return False, ""


def _estimate_ai_cost(provider: str, model: str, usage: dict | None, kind: str = "title") -> dict:
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if provider == "deepseek":
        prices = _DEEPSEEK_PRICES.get(model) or _DEEPSEEK_PRICES.get("deepseek-chat", {})
        usd = (prompt_tokens / 1_000_000) * float(prices.get("input", 0))
        usd += (completion_tokens / 1_000_000) * float(prices.get("output", 0))
    else:
        usd = 0.0
    return {
        "provider": provider,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
        "estimated_usd": round(usd, 6),
        "estimated_vnd": int(round(usd * _USD_TO_VND)),
        "kind": kind,
    }


def _empty_ai_cost() -> dict:
    return {
        "provider": "local",
        "model": "fallback",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_usd": 0.0,
        "estimated_vnd": 0,
        "kind": "fallback",
    }


def _estimate_gemini_cost(model: str, usage: dict | None, kind: str = "thumbnail_review") -> dict:
    usage = usage or {}
    prompt_tokens = int(
        usage.get("promptTokenCount")
        or usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or 0
    )
    completion_tokens = int(
        usage.get("candidatesTokenCount")
        or usage.get("completion_tokens")
        or usage.get("output_tokens")
        or 0
    )
    total_tokens = int(usage.get("totalTokenCount") or usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    base_model = "gemini-2.5-flash-lite" if "flash-lite" in model else "gemini-2.5-flash"
    prices = _GEMINI_PRICES.get(base_model, {})
    usage_unavailable = total_tokens <= 0
    usd = 0.0
    if not usage_unavailable:
        usd = (prompt_tokens / 1_000_000) * float(prices.get("input", 0))
        usd += (completion_tokens / 1_000_000) * float(prices.get("output", 0))
    return {
        "provider": "gemini",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_usd": round(usd, 6),
        "estimated_vnd": int(round(usd * _USD_TO_VND)),
        "usage_unavailable": usage_unavailable,
        "kind": kind,
    }


def _read_engine_env(settings: dict | None = None) -> dict:
    env = {}
    env_path = get_auto_video_env_local(settings)
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        env[k.strip()] = v.strip().strip("\"'")
    return env


def _configured_ai_key(settings: dict | None, env_name: str, setting_name: str) -> str:
    """Read AI keys from the Auto Video env first, then legacy app settings."""
    settings = settings or {}
    engine_env = _read_engine_env(settings)
    return (
        str(engine_env.get(env_name, "") or "").strip()
        or str(settings.get(setting_name, "") or "").strip()
    )


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40] or "video"


def _file_slug(text: str, max_len: int = 80) -> str:
    text = (text or "").replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:max_len].strip("_") or "thumbnail"


def _video_file_title(text: str, max_len: int = 96) -> str:
    text = _clean_thumbnail_title(text or "video")
    text = text.title()
    keep_upper = {
        "Hdmi": "HDMI",
        "Usb": "USB",
        "2Tb": "2TB",
        "4G": "4G",
        "4K120": "4K120",
        "Hub": "HUB",
        "Ch": "CH",
        "Qr": "QR",
        "Vietqr": "VietQR",
        "Momo": "MoMo",
        "MomO": "MoMo",
        "Zalopay": "ZaloPay",
        "Shopeepay": "ShopeePay",
        "Ios": "iOS",
        "Iphone": "iPhone",
        "4K": "4K",
        "120Hz": "120Hz",
        "120hz": "120Hz",
        "60fps": "60FPS",
        "60Fps": "60FPS",
    }
    for src, repl in keep_upper.items():
        text = re.sub(rf"\b{re.escape(src)}\b", repl, text)
    canonical_phrases = (
        (r"\bSamsung\s+Dex\b", "Samsung Dex"),
        (r"\bBox\s+Samsung\s+Dex\b", "Box Samsung Dex"),
        (r"\bSIM\s+4g\b", "SIM 4G"),
        (r"\bSim\s+4G\b", "SIM 4G"),
        (r"\bLoa\s+MoMo\b", "Loa MoMo"),
        (r"\bHDMI\s+2\.1\b", "HDMI 2.1"),
        (r"\bHDMI\s+2\.0\b", "HDMI 2.0"),
        (r"\bUSB\s*-\s*C\b", "USB-C"),
        (r"\bType\s*-\s*C\b", "Type-C"),
        (r"\bCH\s+Play\b", "CH Play"),
    )
    for pattern, repl in canonical_phrases:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = re.sub(r"[/:*?\"<>|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len].rstrip() or "Video"


def _source_sequence_suffix(source_stem: str) -> str:
    match = re.search(r"(?:^|_)(\d{4})(?:_|$)", source_stem or "")
    return match.group(1) if match else "0001"


def _thumbnail_output_path(out_dir: Path, source_stem: str, title: str) -> Path:
    title_slug = _file_slug(title or source_stem)
    seq = _source_sequence_suffix(source_stem)
    return out_dir / f"{title_slug}_{seq}_thumbnail.png"


def _video_output_path(out_dir: Path, source_stem: str, title: str) -> Path:
    title_slug = _video_file_title(title or source_stem)
    seq = _source_sequence_suffix(source_stem)
    return out_dir / f"{title_slug} {seq}.mp4"


def _safe_filename_component(text: str, max_len: int = 150) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"[/:*?\"<>|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-_")
    return _truncate_words(text, max_len) or "Video"


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 2
    while True:
        candidate = path.parent / f"{stem}-{n:02d}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _upload_video_output_path(out_dir: Path, source_stem: str, upload_metadata: dict) -> Path:
    upload_title = _video_file_title(str(upload_metadata.get("upload_title") or source_stem), max_len=90)
    hashtags = [
        str(tag).strip()
        for tag in (upload_metadata.get("hashtags") or [])
        if str(tag).strip().startswith("#")
    ][:4]
    base = _safe_filename_component(f"{upload_title} {' '.join(hashtags)}", max_len=180)
    return out_dir / f"{base}.mp4"


def _truncate_words(text: str, max_len: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rstrip()
    space = cut.rfind(" ")
    if space >= max(20, int(max_len * 0.55)):
        cut = cut[:space].rstrip()
    return cut.rstrip(" ,;:-–—")


def _upload_title_from_thumbnail(title: str, max_len: int = 90) -> str:
    clean = _clean_thumbnail_title(title or "video")
    text = _video_file_title(clean, max_len=max_len)
    text = re.sub(r"\b(DJI|IMG|VID|MOV|MP4|M4V|DSC|GOPRO|GH\d+)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -_")
    return _truncate_words(text, max_len) or "Video công nghệ"


def _hashtag_token(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    parts = re.findall(r"[A-Za-z0-9]+", text)
    if not parts:
        return ""
    return "#" + "".join(part[:1].upper() + part[1:] for part in parts)[:42]


def _append_hashtag(tags: list[str], tag: str, context: str = "", require_context: str | None = None) -> None:
    tag = str(tag or "").strip()
    if not tag.startswith("#"):
        tag = _hashtag_token(tag)
    if not tag or tag.lower() in {"#fyp", "#viral", "#trending"}:
        return
    if not re.fullmatch(r"#[A-Za-z0-9]{2,42}", tag):
        return
    if re.match(r"^#\d", tag):
        replacements = {
            "#120Hz": "#ManHinh120Hz",
            "#120hz": "#ManHinh120Hz",
            "#4K120Hz": "#ManHinh4K120Hz",
            "#4k120hz": "#ManHinh4K120Hz",
        }
        tag = replacements.get(tag, "")
        if not tag:
            return
    if require_context and require_context not in context:
        return
    if tag.lower() not in {t.lower() for t in tags}:
        tags.append(tag)


def _normalise_ai_hashtags(hashtags: object) -> list[str]:
    tags: list[str] = []
    if not isinstance(hashtags, list):
        return tags
    for raw in hashtags:
        _append_hashtag(tags, str(raw or ""))
        if len(tags) >= 4:
            break
    return tags


def _valid_ai_upload_title(upload_title: object, thumbnail_title: str, source_title: str, segments: list[dict] | None) -> str:
    title = str(upload_title or "").strip()
    if not title:
        return ""
    title = re.sub(r"\s+", " ", title).strip(" -_")
    if len(title) > 90 or _is_weak_thumbnail_title(title, _thumbnail_context_text(source_title, segments)):
        return ""
    clean_thumb = _upload_title_from_thumbnail(thumbnail_title, 90)
    title_words = set(_ascii_upper(title).split())
    thumb_words = set(_ascii_upper(clean_thumb).split())
    if thumb_words and len(title_words & thumb_words) < max(1, min(3, len(thumb_words) // 2)):
        return ""
    return _truncate_words(title, 90)


def _build_upload_hashtags(title: str, source_title: str, segments: list[dict] | None, settings: dict | None = None) -> list[str]:
    title_context = _fix_common_title_misreads(_ascii_upper(title))
    context = _fix_common_title_misreads(_ascii_upper(_thumbnail_context_text(source_title, segments) + " " + title))
    tags: list[str] = []

    if "SAMSUNG DEX" in title_context or "DEX" in title_context:
        _append_hashtag(tags, "#SamsungDex")
    if "BOX" in title_context and "DEX" in title_context:
        _append_hashtag(tags, "#BoxSamsungDex")
    if "HUB" in title_context and ("DEX" in title_context or "TYPE C" in title_context or "TYPE-C" in title_context):
        _append_hashtag(tags, "#HubTypeC")

    if "HDMI 2 1" in title_context or "HDMI 2.1" in title_context:
        _append_hashtag(tags, "#HDMI21")
    elif ("HDMI 2 0" in title_context or "HDMI 2.0" in title_context) and "2 1" not in title_context and "2.1" not in title_context:
        _append_hashtag(tags, "#HDMI20")
    if "HDMI" in title_context:
        _append_hashtag(tags, "#DayHDMI")

    if "USB" in title_context and ("NHAC" in title_context or "CHEP" in title_context):
        _append_hashtag(tags, "#UsbNhac")
    elif "USB C" in title_context or "USB-C" in title_context:
        _append_hashtag(tags, "#UsbC")
    elif "USB" in title_context:
        _append_hashtag(tags, "#USB")

    if "IPHONE" in title_context:
        _append_hashtag(tags, "#iPhone")
    if "SAC NHANH" in title_context or "SẠC NHANH" in _plain_upper(title):
        _append_hashtag(tags, "#SacNhanh")
    for brand, tag in (
        ("UGREEN", "#Ugreen"),
        ("ANKER", "#Anker"),
        ("BASEUS", "#Baseus"),
        ("XIAOMI", "#Xiaomi"),
    ):
        if brand in title_context:
            _append_hashtag(tags, tag)

    if len(tags) < 3 and any(key in title_context for key in ("ME", "MEO", "CACH", "THU THUAT", "CH PLAY", "DANG NHAP", "BI CHAN")):
        _append_hashtag(tags, "#MeoCongNghe")
    if len(tags) < 3 and any(key in title_context for key in ("MUA", "GIA", "CHON", "NHO", "HON", "GON")):
        _append_hashtag(tags, "#KinhNghiemMuaHang")

    if "MOMO" in context:
        if "LOA" in context:
            _append_hashtag(tags, "#LoaMomo")
        if "THANH TOAN" in context or "QR" in context:
            _append_hashtag(tags, "#ThanhToanQR")
        if "LOA" not in context:
            _append_hashtag(tags, "#Momo")
    if "THANH TOAN" in context:
        _append_hashtag(tags, "#ThanhToanQR" if "QR" in context or "MOMO" in context else "#ThanhToan")
    if "GIAY PHEP KINH DOANH" in context:
        _append_hashtag(tags, "#GiayPhepKinhDoanh")
    if "ZALOPAY" in context:
        _append_hashtag(tags, "#ZaloPay")
    if "SHOPEEPAY" in context:
        _append_hashtag(tags, "#ShopeePay")
    if "VIETQR" in context or "QR" in context:
        _append_hashtag(tags, "#VietQR" if "VIETQR" in context else "#QR")
    if "LOA" in context and "SIM" in context:
        _append_hashtag(tags, "#Sim4G" if "4G" in context else "#LoaCoSim")
    if "4G" in context:
        _append_hashtag(tags, "#Sim4G")
    if len(tags) < 3 and any(key in context for key in ("ME", "MEO", "CACH", "THU THUAT", "CH PLAY", "DANG NHAP")):
        _append_hashtag(tags, "#MeoCongNghe")
    elif len(tags) < 3 and any(key in context for key in ("TEST", "REVIEW", "DUNG THU", "THU")):
        _append_hashtag(tags, "#ReviewNhanh")
    elif len(tags) < 3 and any(key in context for key in ("MUA", "GIA", "CHON", "NHO")):
        _append_hashtag(tags, "#KinhNghiemMuaHang")
    if len(tags) < 3 and ("GON" in context or "TIEN" in context):
        _append_hashtag(tags, "#GonHon")
    if len(tags) < 3 and ("LAM VIEC" in context or "DEX" in context):
        _append_hashtag(tags, "#LamViecDiDong")
    channel = ""
    try:
        env = _read_engine_env(settings)
        channel = env.get("TIKTOK_DISPLAY_NAME", "")
    except Exception:
        channel = ""
    channel_tag = _hashtag_token(channel)
    if channel_tag and channel_tag.lower() not in {"#hedra", "#hedrastudio", "#hedracentral"}:
        _append_hashtag(tags, channel_tag)
    fallback = ["#PhuKienCongNghe", "#DoCongNghe", "#ReviewNhanh", "#MeoCongNghe"]
    for tag in fallback:
        if len(tags) >= 3:
            break
        _append_hashtag(tags, tag)
    return tags[:3]


def _build_upload_metadata(
    thumbnail_title: str,
    source_title: str,
    segments: list[dict] | None = None,
    settings: dict | None = None,
    ai_metadata: dict | None = None,
) -> dict:
    thumbnail_title = _clean_thumbnail_title(thumbnail_title or source_title, source_title, segments)
    if "MOMO" in thumbnail_title and "GIẤY PHÉP KINH DOANH" in thumbnail_title and "LOA" not in thumbnail_title:
        thumbnail_title = re.sub(r"\bMUA\s+MOMO\b", "MUA LOA MOMO", thumbnail_title)
    ai_metadata = ai_metadata if isinstance(ai_metadata, dict) else {}
    upload_title = (
        _valid_ai_upload_title(ai_metadata.get("upload_title"), thumbnail_title, source_title, segments)
        or _upload_title_from_thumbnail(thumbnail_title, 90)
    )
    ai_hashtags = _normalise_ai_hashtags(ai_metadata.get("hashtags"))
    hashtags = ai_hashtags if 3 <= len(ai_hashtags) <= 4 else _build_upload_hashtags(upload_title, source_title, segments, settings)
    caption_short = _truncate_words(upload_title, 120)
    caption_full = _truncate_words(upload_title, 220)
    platform_caption = f"{caption_full}\n{' '.join(hashtags)}".strip()
    return {
        "thumbnail_title": thumbnail_title,
        "upload_title": upload_title,
        "caption_short": caption_short,
        "caption_full": caption_full,
        "hashtags": hashtags,
        "platform_caption": platform_caption,
        "limits": {
            "upload_title_max": 90,
            "caption_short_max": 120,
            "caption_full_max": 220,
            "hashtags_default": 3,
        },
    }


def _plain_upper(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[\"'“”‘’`]+", "", text)
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\wÀ-ỹ\s/+.]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.upper()


def _ascii_upper(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Z0-9\s]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


def _thumbnail_context_text(source_title: str, segments: list[dict] | None = None) -> str:
    transcript = " ".join(str(seg.get("text", "")) for seg in (segments or [])[:80])
    return f"{source_title} {transcript}"


def _early_thumbnail_context(segments: list[dict] | None, max_seconds: float = 18.0) -> str:
    picked: list[str] = []
    for idx, seg in enumerate(segments or []):
        try:
            start = float(seg.get("start", 0.0))
        except Exception:
            start = 0.0
        if idx > 0 and start > max_seconds:
            break
        text = str(seg.get("text", "")).strip()
        if text:
            picked.append(text)
        if len(picked) >= 6:
            break
    return " ".join(picked)


def _title_word_count(title: str) -> int:
    return len(re.findall(r"\w+", title, flags=re.UNICODE))


def _trim_title_words(title: str, max_words: int = 12) -> str:
    words = title.split()
    if len(words) <= max_words:
        return title
    return " ".join(words[:max_words])


def _strip_generic_thumbnail_prefix(title: str) -> str:
    for prefix in _THUMB_GENERIC_PREFIXES:
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title


def _strip_bad_title_tail(title: str) -> str:
    words = title.split()
    while words and words[-1] in _THUMB_TRAILING_BAD_WORDS:
        words.pop()
    return " ".join(words)


def _normalize_tech_terms(title: str) -> str:
    out = title
    for pattern, repl in _THUMB_TECH_TERM_REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip()


def _fix_common_title_misreads(title: str) -> str:
    replacements = [
        (r"\bCẮP\s+HDMI\b", "CÁP HDMI"),
        (r"\bCAP\s+HDMI\b", "CÁP HDMI"),
        (r"\bDÂY\s+HDMI\b", "DÂY HDMI"),
        (r"\bMÁY\s+CẠO\s+DÂU\b", "MÁY CẠO RÂU"),
        (r"\bMAY\s+CAO\s+DAU\b", "MÁY CẠO RÂU"),
        (r"\bCỤC\s+SẠCH\b", "CỤC SẠC"),
        (r"\bCUC\s+SACH\b", "CỤC SẠC"),
        (r"\bTAXI\b", "TYPE-C"),
        (r"\bRẮC\s+(\d)", r"JACK \1"),
        (r"\bRAC\s+(\d)", r"JACK \1"),
        (r"\bLÀN\b", "LÀM"),
        (r"\bLẦN\b", "LÀM"),
        (r"\bLAN\b", "LÀM"),
        (r"\bTH[ÓO]A\s+KHỎI\b", "THOÁT KHỎI"),
        (r"\bTHOA\s+KHOI\b", "THOÁT KHỎI"),
        (r"\bĐANG\s+NHẬP\b", "ĐĂNG NHẬP"),
        (r"\bDANG\s+NHAP\b", "ĐĂNG NHẬP"),
        *_THUMB_TECH_TERM_REPLACEMENTS,
    ]
    out = title
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    if re.search(r"\b(HẤP|HÁP|HAP)\b", out, flags=re.IGNORECASE) and re.search(
        r"\b(SAMSUNG\s+DEX|DEX|HDMI|4K|120HZ|TYPE\s*C|USB\s*C)\b",
        out,
        flags=re.IGNORECASE,
    ):
        out = re.sub(r"\b(HẤP|HÁP|HAP)\b", "HUB", out, flags=re.IGNORECASE)
    if re.search(r"\bCẮP\b", out, flags=re.IGNORECASE) and re.search(r"\b(HDMI|TYPE-C|USB-C|SẠC|SAC)\b", out, flags=re.IGNORECASE):
        out = re.sub(r"\bCẮP\b", "CÁP", out, flags=re.IGNORECASE)
    if re.search(r"\bDÂU\b", out, flags=re.IGNORECASE) and re.search(r"\b(MÁY\s+CẠO|DAO\s+CẠO|LƯỠI\s+DAO)\b", out, flags=re.IGNORECASE):
        out = re.sub(r"\bDÂU\b", "RÂU", out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip()


def _extract_known_product_context(context: str) -> str:
    upper = _fix_common_title_misreads(_plain_upper(context))
    ascii_ctx = _ascii_upper(context)
    if "SAMSUNG DEX" in upper or "SAMSUNGDEX" in upper:
        return "SAMSUNG DEX"
    if "BOX PHONE" in upper or "BOXPHONE" in upper:
        return "BOX PHONE"
    if "IPHONE" in upper:
        match = re.search(r"\bIPHONE\s+\d{1,2}\s*(?:PRO MAX|PRO|PLUS)?\b", ascii_ctx)
        return match.group(0).strip() if match else "IPHONE"
    for brand in ("ANKER", "BASEUS", "UGREEN", "XIAOMI"):
        if brand in ascii_ctx:
            return brand
    match = re.search(r"\b(IPHONE\s+\d{1,2}\s*(?:PRO MAX|PRO|PLUS)?|SAMSUNG\s+[A-Z]?\d{1,3}[A-Z]?|MACBOOK\s+\w+|IPAD\s+\w+)\b", ascii_ctx)
    if match:
        return match.group(1).strip()
    return ""


def _extract_price_token(context: str) -> str:
    raw = str(context or "")
    ascii_ctx = _ascii_upper(raw)
    if re.search(r"\b7\s*[,\.]\s*80\s*[,\.]?\s*000\b", raw, flags=re.IGNORECASE) or "7 80 000" in ascii_ctx:
        return "80K"
    match = re.search(r"\b([1-9]\d{1,3})\s*K\b", ascii_ctx)
    if match:
        return f"{match.group(1)}K"
    match = re.search(r"\b([1-9]\d{1,3})\s*[.,]\s*000\b", raw)
    if match:
        return f"{match.group(1)}K"
    return ""


def _hdmi_title_from_context(source_title: str, segments: list[dict] | None = None) -> str:
    context = _thumbnail_context_text(source_title, segments)
    upper = _fix_common_title_misreads(_plain_upper(context))
    ascii_ctx = _ascii_upper(upper)
    if "HDMI" not in upper:
        return ""
    version = ""
    if re.search(r"\bHDMI\s*2[.,]\s*1\b", upper) or "HDMI 2 1" in ascii_ctx:
        version = "2.1"
    elif re.search(r"\bHDMI\s*2[.,]\s*0\b", upper) or "HDMI 2 0" in ascii_ctx:
        version = "2.0"
    specs: list[str] = []
    if "4K" in upper:
        specs.append("4K")
    if re.search(r"\b120\s*(?:HZ|HÃNG\s*Z|HANG\s*Z)\b", upper, flags=re.IGNORECASE) or "120 HANG Z" in ascii_ctx:
        specs.append("120HZ")
    price = _extract_price_token(context)
    parts = ["CÁP HDMI"]
    if version:
        parts.append(version)
    parts.extend(specs)
    if price:
        parts.extend(["GIÁ", price])
    return " ".join(parts)


def _unsupported_spec_claims(title: str, context: str) -> list[str]:
    clean = _fix_common_title_misreads(_plain_upper(title))
    ctx = _fix_common_title_misreads(_plain_upper(context))
    ctx_ascii = _ascii_upper(ctx)
    ctx_compact = re.sub(r"\s+", "", ctx).upper()
    claims = re.findall(r"\b\d+(?:[.,]\d+)?\s*(?:K|W|HZ|MAH|GB|TB|MM|INCH|X)\b", clean, flags=re.IGNORECASE)
    missing = []
    for claim in claims:
        compact = re.sub(r"\s+", "", claim).upper()
        if compact.endswith("HZ") and compact[:-2] and re.search(rf"\b{re.escape(compact[:-2])}\s*(?:HZ|HÃNG\s*Z|HANG\s*Z)\b", ctx_ascii):
            continue
        if compact.endswith("K") and compact[:-1]:
            amount = compact[:-1]
            if re.search(rf"\b{re.escape(amount)}\s*K\b", ctx_ascii) or re.search(rf"\b{re.escape(amount)}\s*[.,]\s*000\b", context):
                continue
            if amount == "80" and re.search(r"\b7\s*[,\.]\s*80\s*[,.]?\s*000\b", context):
                continue
        if compact and compact not in ctx_compact:
            missing.append(compact)
    return missing


def _thumbnail_title_risk_flags(title: str, context: str = "") -> list[str]:
    clean = _fix_common_title_misreads(_plain_upper(title))
    context_fixed = _fix_common_title_misreads(_plain_upper(context))
    flags: list[str] = []
    if re.search(r"\b(DJI|IMG|VID|MOV|MP4|M4V|DSC|GOPRO|GH\d+)\b", clean, flags=re.IGNORECASE):
        flags.append("camera_filename")
    if re.search(r"\b(HẤP|HÁP|HAP|SET\s*PLAY|SÉT\s*PLAY|SETPLAY|SAMSUNG\s+DECK)\b", _plain_upper(title), flags=re.IGNORECASE):
        flags.append("uncorrected_asr")
    if "GAME CH PLAY" in clean:
        flags.append("awkward_game_ch_play")
    if clean.startswith((
        "ANH EM XEM",
        "ANH EM NÀO",
        "XEM NÀY",
        "ĐÂY NÈ XEM",
        "ĐÂY ĐÂY",
        "ĐÂY MÌNH",
        "HÔM NAY MÌNH",
        "TRÊN TAY MÌNH",
        "MỌI NGƯỜI MUỐN",
        "CÁI DÂY MÌNH",
    )):
        flags.append("generic_viewer_filler")
    if re.search(r"\bGIÁ\s+CHỈ\s*$", clean) or re.search(r"\bCHỈ\s*$", clean):
        flags.append("incomplete_price_hook")
    if re.search(r"\bO\s*[- ]?\s*KRING\b", clean, flags=re.IGNORECASE):
        flags.append("uncertain_brand_asr")
    if clean in {"VIDEO MỚI", "THỦ THUẬT HAY", "MẸO HAY", "SẢN PHẨM HAY"}:
        flags.append("generic")
    if re.search(r"\bRẮC\s+\d", clean):
        flags.append("awkward_term:rac")
    if re.search(r"\b(CÁI|CÁC|NÀY|KIA)\s+(CÁI|CÁC|NÀY|KIA)\b", clean):
        flags.append("awkward_phrase")
    for claim in _unsupported_spec_claims(clean, context_fixed):
        flags.append(f"unsupported_claim:{claim}")
    if "QUẠT" in clean and "QUẠT" not in context_fixed and "FAN" not in _ascii_upper(context_fixed):
        flags.append("unsupported_product:quat")
    return flags


def _is_weak_thumbnail_title(title: str, context: str = "") -> bool:
    clean = _plain_upper(title)
    clean_fixed = _fix_common_title_misreads(clean)
    context_fixed = _fix_common_title_misreads(_plain_upper(context))
    if not clean:
        return True
    words = clean.split()
    if len(words) < 3 or len(words) > 14:
        return True
    if _thumbnail_title_risk_flags(title, context):
        return True
    digits = sum(ch.isdigit() for ch in clean)
    if digits >= 8 and not any(term in clean_fixed for term in ("HDMI", "4K", "120HZ", "GIÁ", "CHỈ", "USB", "2TB")):
        return True
    meaningful_words = [w for w in words if re.search(r"[A-ZÀ-Ỹ]", w) and not re.fullmatch(r"\d+", w)]
    if len(meaningful_words) < 3:
        return True
    if words[-1] in _THUMB_TRAILING_BAD_WORDS:
        return True
    if any(clean.startswith(prefix) for prefix in _THUMB_GENERIC_PREFIXES):
        return True
    if clean in {"VIDEO MỚI", "THỦ THUẬT HAY", "MẸO HAY", "SẢN PHẨM HAY"}:
        return True
    if "LÀM THẾ NÀO" in clean and "?" not in clean:
        return True
    return False


def _clean_thumbnail_title(title: str, source_title: str = "", segments: list[dict] | None = None) -> str:
    context = _thumbnail_context_text(source_title, segments)
    out = _plain_upper(title)
    out = re.sub(r"^(TIÊU ĐỀ|TITLE|THUMBNAIL)\s*:\s*", "", out, flags=re.IGNORECASE).strip()
    out = _fix_common_title_misreads(out)
    out = _normalize_tech_terms(out)
    out = _strip_generic_thumbnail_prefix(out)
    out = re.sub(r"\b(ĐƯỢC|DUOC)\b", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip()
    out = _strip_bad_title_tail(out)

    product = _extract_known_product_context(context)
    if product == "SAMSUNG DEX":
        out = re.sub(r"\bTRÊN\s+DEX\b", "TRÊN SAMSUNG DEX", out)
    has_product = product in out or (product == "SAMSUNG DEX" and "DEX" in out)
    if product and "TRÊN " not in out and not has_product:
        if any(key in out for key in ("ĐĂNG NHẬP", "DANG NHAP", "CÀI", "CAI", "SETUP", "NHẬN", "NHAN", "MỞ", "MO")):
            out = f"{out} TRÊN {product}"

    out = _trim_title_words(out, 12)
    out = _strip_bad_title_tail(out)
    return out or _plain_upper(source_title) or "BOX PHONE"


def _thumbnail_render_title(title: str, source_title: str = "", segments: list[dict] | None = None) -> tuple[str, dict]:
    original = _clean_thumbnail_title(title, source_title, segments)
    words = original.split()
    render = original
    reasons: list[str] = []
    if len(words) > 10:
        upper = _fix_common_title_misreads(_plain_upper(original))
        if "MUA BOX" in upper and "TỰ LẮP" in upper:
            render = "MUA BOX CÓ SẴN HAY TỰ LẮP"
        elif "SAMSUNG DEX" in upper and "MUA BOX" in upper:
            render = "MUA BOX SAMSUNG DEX CÓ SẴN"
        elif "SAMSUNG DEX" in upper and "BOX" in upper:
            render = "BOX SAMSUNG DEX CÓ SẴN"
        else:
            render = " ".join(words[:9])
        render = _strip_bad_title_tail(_clean_thumbnail_title(render, source_title, segments))
        reasons.append("rút gọn title dài cho grid TikTok")
    return render, {
        "original_title": original,
        "render_title": render,
        "changed": render != original,
        "reasons": reasons,
    }


def _make_slug(title: str) -> str:
    return f"{_slugify(title)}-{datetime.now().strftime('%Y%m%d')}"


def _make_one_shot_job_slug(title: str) -> str:
    return f"{_slugify(title)}-{datetime.now().strftime('%H%M%S')}"


def _one_shot_exports_dir(job_dir: Path) -> Path:
    if job_dir.parent.parent.name == "_debug":
        one_shot_root = job_dir.parent.parent.parent
        return one_shot_root / job_dir.parent.name
    return job_dir


def escbase_root() -> Path:
    candidates = [ESCBASE_VENDOR_ROOT]
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(Path(bundle_root) / "vendor" / "escbase-template3")
    candidates.extend([
        Path(sys.executable).resolve().parent / "vendor" / "escbase-template3",
        Path(sys.executable).resolve().parent.parent / "Resources" / "vendor" / "escbase-template3",
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def escbase_manifest(root: Path | None = None) -> dict:
    root = root or escbase_root()
    manifest_path = root / "hedra_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def escbase_required_files(root: Path | None = None) -> list[Path]:
    root = root or escbase_root()
    manifest = escbase_manifest(root)
    required = manifest.get("required_files") if isinstance(manifest, dict) else None
    if not isinstance(required, list) or not required:
        required = [
            "auto_render.py",
            "validate_slide.py",
            "template/escbase-slide-starter/index.html",
            "template/escbase-slide-starter/app.js",
            "template/escbase-slide-starter/style.css",
            "template/escbase-slide-starter/preview-settings.json",
            "template/escbase-slide-starter/script-90s.txt",
            "template/escbase-slide-starter/upload-metadata.json",
        ]
    return [root / str(path) for path in required]


def escbase_template_status(root: Path | None = None) -> dict:
    root = root or escbase_root()
    if not root.exists():
        return {"status": "missing_template", "message": "Chưa có ESCBase Template trong vendor."}
    missing = [str(path.relative_to(root)) for path in escbase_required_files(root) if not path.exists()]
    if missing:
        return {"status": "invalid_template", "message": "Template thiếu file bắt buộc.", "missing": missing}
    return {
        "status": "ok",
        "message": "ESCBase Template sẵn sàng.",
        "template_id": ESCBASE_TEMPLATE_ID,
        "version": escbase_manifest(root).get("version", ""),
    }


def escbase_dependency_status(root: Path | None = None, python_executable: str | None = None) -> dict:
    template = escbase_template_status(root)
    if template.get("status") != "ok":
        return template
    path_env = _shell_path()
    missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool, path=path_env)]
    if missing_tools:
        return {"status": "missing_ffmpeg", "message": "Thiếu ffmpeg/ffprobe để render.", "missing": missing_tools}
    py = python_executable or sys.executable
    try:
        r = subprocess.run(
            [py, "-c", "import playwright.sync_api; print('ok')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return {"status": "missing_playwright", "message": "Thiếu Python package Playwright.", "detail": (r.stderr or r.stdout).strip()[-400:]}
    except Exception as exc:
        return {"status": "missing_playwright", "message": "Không kiểm tra được Playwright.", "detail": str(exc)}
    cache_roots = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
        Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")) if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else None,
    ]
    has_chromium = any(root and root.exists() and list(root.glob("chromium-*")) for root in cache_roots)
    if not has_chromium:
        return {"status": "missing_chromium", "message": "Thiếu Chromium của Playwright."}
    return {"status": "ready", "message": "ESCBase sẵn sàng render.", "version": template.get("version", "")}


def _escbase_slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:48].strip("-") or f"slide-{datetime.now().strftime('%H%M%S')}"


def _escbase_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", cleaned)
    if len(parts) <= 1:
        parts = re.split(r"\s*[;\n]\s*", cleaned)
    out = []
    for part in parts:
        part = part.strip(" -•\t")
        if not part:
            continue
        if not re.search(r"[.!?。！？]$", part):
            part += "."
        out.append(part)
    return out


def escbase_script_lines(source_text: str) -> list[str]:
    sentences = _escbase_sentences(source_text)
    if not sentences:
        sentences = ["Video slide mới đã sẵn sàng."]
    cursor = 0
    lines: list[str] = []
    for count in ESCBASE_SLIDE_COUNTS:
        picked = []
        for _ in range(count):
            picked.append(sentences[cursor % len(sentences)])
            cursor += 1
        lines.append(" ".join(picked))
    return lines


def _escbase_js_array(values: list[str]) -> str:
    return "[\n" + ",\n".join("  " + json.dumps(v, ensure_ascii=False) for v in values) + "\n]"


def _escbase_replace_const_array(text: str, name: str, values: list[str]) -> str:
    pattern = re.compile(rf"(const\s+{re.escape(name)}\s*=\s*)\[(?:.|\n)*?\](\s*;)", re.MULTILINE)
    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{_escbase_js_array(values)}{match.group(2)}"

    new, count = pattern.subn(_replace, text, count=1)
    return new if count else text


def _escbase_sync_project(project_dir: Path, lines: list[str], title: str) -> None:
    (project_dir / "script-90s.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    preview_path = project_dir / "preview-settings.json"
    if preview_path.exists():
        data = json.loads(preview_path.read_text(encoding="utf-8"))
        data.setdefault("slides", {})["scriptLines"] = lines
        preview_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    app_path = project_dir / "app.js"
    if app_path.exists():
        app_text = app_path.read_text(encoding="utf-8")
        app_text = _escbase_replace_const_array(app_text, "slideScripts", lines)
        app_path.write_text(app_text, encoding="utf-8")
    metadata = {
        "template": ESCBASE_TEMPLATE_ID,
        "youtube": {
            "title": _truncate_words(title, 100),
            "description": f"{title}\n\n#HedraStudio #Shorts",
            "tags": ["HedraStudio", "Shorts"],
            "privacyStatus": "private",
        },
        "facebook": {
            "caption": title,
            "videoState": "DRAFT",
        },
        "hedra": {
            "template": ESCBASE_TEMPLATE_ID,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    }
    (project_dir / "upload-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def escbase_create_project(
    source_text: str,
    output_root: str | Path,
    project_name: str = "",
    template_id: str = ESCBASE_TEMPLATE_ID,
    root: Path | None = None,
) -> dict:
    root = root or escbase_root()
    status = escbase_template_status(root)
    if status.get("status") != "ok":
        raise RuntimeError(status.get("message") or "ESCBase template chưa sẵn sàng.")
    if template_id != ESCBASE_TEMPLATE_ID:
        raise ValueError(f"Template chưa hỗ trợ: {template_id}")
    starter = root / "template" / ESCBASE_TEMPLATE_ID
    first_line = _escbase_sentences(source_text)
    title = _truncate_words(project_name or (first_line[0] if first_line else "ESCBase Slide"), 90)
    slug = _escbase_slug(project_name or title)
    out_root = Path(output_root)
    project_dir = out_root / "escbase" / datetime.now().strftime("%Y-%m-%d") / slug
    base = project_dir
    n = 2
    while project_dir.exists():
        project_dir = base.with_name(f"{base.name}-{n}")
        n += 1
    shutil.copytree(starter, project_dir)
    lines = escbase_script_lines(source_text)
    _escbase_sync_project(project_dir, lines, title)
    return {
        "project_dir": str(project_dir),
        "script_path": str(project_dir / "script-90s.txt"),
        "metadata_path": str(project_dir / "upload-metadata.json"),
        "template_id": template_id,
        "title": title,
        "script_lines": lines,
    }


def _shell_path() -> str:
    if os.name == "nt":
        return os.environ.get("PATH", "")
    try:
        r = subprocess.run(
            ["/bin/zsh", "-l", "-c", "echo $PATH"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return os.environ.get("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")


def _terminate_process(proc: subprocess.Popen, *, wait: bool = True) -> None:
    try:
        if os.name != "nt":
            os.killpg(proc.pid, signal.SIGTERM)  # type: ignore[attr-defined]
        else:
            proc.terminate()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    if not wait:
        return
    try:
        proc.wait(timeout=3)
        return
    except Exception:
        pass
    try:
        if os.name != "nt":
            os.killpg(proc.pid, signal.SIGKILL)  # type: ignore[attr-defined]
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _run_media_cmd(
    cmd: list[str],
    *,
    cwd: str | Path | None = None,
    timeout: int | None = None,
    is_cancelled=None,
) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": _shell_path()}
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=(os.name != "nt"),
    )
    started = time.monotonic()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    while True:
        if is_cancelled and is_cancelled():
            _terminate_process(proc)
            stdout, stderr = proc.communicate(timeout=1)
            return subprocess.CompletedProcess(cmd, -15, "".join(stdout_parts) + (stdout or ""), "".join(stderr_parts) + (stderr or "Đã dừng"))
        if timeout is not None and time.monotonic() - started > timeout:
            _terminate_process(proc)
            stdout, stderr = proc.communicate(timeout=1)
            raise subprocess.TimeoutExpired(cmd, timeout, output="".join(stdout_parts) + (stdout or ""), stderr="".join(stderr_parts) + (stderr or ""))
        try:
            stdout, stderr = proc.communicate(timeout=0.25)
            return subprocess.CompletedProcess(cmd, proc.returncode, "".join(stdout_parts) + (stdout or ""), "".join(stderr_parts) + (stderr or ""))
        except subprocess.TimeoutExpired:
            continue


def _ffmpeg_encoders() -> set[str]:
    global _FFMPEG_ENCODERS_CACHE
    if _FFMPEG_ENCODERS_CACHE is not None:
        return _FFMPEG_ENCODERS_CACHE
    try:
        r = _run_media_cmd(["ffmpeg", "-hide_banner", "-encoders"], timeout=20)
        text = (r.stdout or "") + "\n" + (r.stderr or "")
        encoders = set()
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith("V"):
                encoders.add(parts[1])
        _FFMPEG_ENCODERS_CACHE = encoders
    except Exception:
        _FFMPEG_ENCODERS_CACHE = set()
    return _FFMPEG_ENCODERS_CACHE


def _software_h264_args() -> tuple[list[str], str]:
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"], "libx264"


def _best_h264_args() -> tuple[list[str], str]:
    encoders = _ffmpeg_encoders()
    system = platform.system().lower()
    if system == "darwin" and "h264_videotoolbox" in encoders:
        return [
            "-c:v", "h264_videotoolbox",
            "-b:v", "12000k",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-allow_sw", "1",
        ], "h264_videotoolbox"
    if system == "windows":
        if "h264_nvenc" in encoders:
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"], "h264_nvenc"
        if "h264_qsv" in encoders:
            return ["-c:v", "h264_qsv", "-global_quality", "20", "-look_ahead", "1", "-pix_fmt", "nv12"], "h264_qsv"
        if "h264_amf" in encoders:
            return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21", "-pix_fmt", "yuv420p"], "h264_amf"
    return _software_h264_args()


def _one_shot_render_profile(value: str | None, source_info: dict | None = None) -> dict:
    source_info = source_info or {}
    value = str(value or "multi_1080").strip().lower()
    if value in {"source", "full", "original"}:
        return {
            "id": "source",
            "label": "Gốc",
            "width": int(source_info.get("width") or 0),
            "height": int(source_info.get("height") or 0),
            "bitrate": "12000k",
        }
    if value in {"sharp_1440", "1440", "1440x2560"}:
        return {"id": "sharp_1440", "label": "1440 nét", "width": 1440, "height": 2560, "bitrate": "16000k"}
    return {"id": "multi_1080", "label": "1080 đa nền tảng", "width": 1080, "height": 1920, "bitrate": "12000k"}


def _ffprobe_duration(path: str | Path) -> float:
    r = _run_media_cmd([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ], timeout=20)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "ffprobe failed").strip())
    return max(0.0, float((r.stdout or "0").strip() or 0))


def _ffprobe_video_size(path: str | Path) -> tuple[int, int]:
    r = _run_media_cmd([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(path),
    ], timeout=20)
    if r.returncode != 0:
        return 1080, 1920
    text = (r.stdout or "").strip().splitlines()[0] if (r.stdout or "").strip() else ""
    match = re.match(r"(\d+)x(\d+)", text)
    if not match:
        return 1080, 1920
    return max(2, int(match.group(1))), max(2, int(match.group(2)))


def _ffprobe_video_info(path: str | Path) -> dict:
    info = {
        "codec": "",
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "bit_rate": 0,
    }
    try:
        r = _run_media_cmd([
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,r_frame_rate,bit_rate",
            "-of", "json",
            str(path),
        ], timeout=20)
        if r.returncode != 0:
            return info
        data = json.loads(r.stdout or "{}")
        stream = (data.get("streams") or [{}])[0] or {}
        info["codec"] = str(stream.get("codec_name") or "")
        info["width"] = int(stream.get("width") or 0)
        info["height"] = int(stream.get("height") or 0)
        info["bit_rate"] = int(stream.get("bit_rate") or 0)
        rate = str(stream.get("r_frame_rate") or "0/1")
        if "/" in rate:
            num, _, den = rate.partition("/")
            den_f = float(den or 1)
            info["fps"] = round(float(num or 0) / den_f, 3) if den_f else 0.0
        else:
            info["fps"] = round(float(rate or 0), 3)
    except Exception:
        pass
    return info


def _is_full_timeline(segments: list[tuple[float, float]], duration: float) -> bool:
    if len(segments) != 1:
        return False
    start, end = segments[0]
    return start <= 0.01 and abs(float(end) - float(duration)) <= 0.05


def _render_bottleneck(profile: dict) -> str:
    steps = profile.get("steps") if isinstance(profile, dict) else {}
    if not isinstance(steps, dict) or not steps:
        return ""
    slow_key = max(steps, key=lambda key: float(steps.get(key) or 0.0))
    labels = {
        "ffprobe": "đọc thông tin video",
        "thumbnail_frame": "lấy frame thumbnail",
        "thumbnail_draw": "vẽ thumbnail",
        "thumbnail_review": "AI review thumbnail",
        "ffmpeg_render": "ffmpeg render",
        "export_copy": "copy export",
    }
    return labels.get(slow_key, slow_key)


def _processed_thumbnail_frame(
    source: Path,
    source_frame: Path,
    out_dir: Path,
    duration: float,
    lut_path: str,
    is_cancelled=None,
) -> tuple[Path, str, str]:
    """Return a thumbnail frame that matches the rendered video's color pipeline."""
    if not lut_path or not Path(lut_path).exists():
        return source_frame, "source", ""
    processed = out_dir / "thumbnail-frame-processed.png"
    frame_time = min(duration * 0.32, max(duration - 0.5, 0.0))
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, frame_time):.3f}",
        "-i", str(source),
        "-frames:v", "1",
        "-vf", f"lut3d=file='{_escape_filter_path(lut_path)}'",
        str(processed),
    ]
    r = _run_media_cmd(cmd, timeout=120, is_cancelled=is_cancelled)
    if r.returncode == 0 and processed.exists():
        return processed, "lut_processed", str(processed)
    return source_frame, "fallback_source", ""


def _prepend_thumbnail_cover(video_path: Path, thumbnail_path: Path, duration: float = 0.28) -> Path:
    if not video_path.exists() or not thumbnail_path.exists():
        return video_path
    width, height = _ffprobe_video_size(video_path)
    width += width % 2
    height += height % 2
    temp = video_path.with_name(f"{video_path.stem}_with_cover_tmp{video_path.suffix}")
    video_args, video_encoder = _best_h264_args()
    filt = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps=30,format=yuv420p,setpts=PTS-STARTPTS[v0];"
        "[2:a]aresample=48000,asetpts=PTS-STARTPTS[a0];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,setpts=PTS-STARTPTS[v1];"
        "[1:a]aresample=48000,asetpts=PTS-STARTPTS[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{max(0.08, float(duration)):.2f}", "-i", str(thumbnail_path),
        "-i", str(video_path),
        "-f", "lavfi", "-t", f"{max(0.08, float(duration)):.2f}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-filter_complex", filt,
        "-map", "[v]", "-map", "[a]",
        *video_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(temp),
    ]
    r = _run_media_cmd(cmd, timeout=3600)
    if r.returncode != 0 and video_encoder != "libx264":
        fallback_args, _ = _software_h264_args()
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", f"{max(0.08, float(duration)):.2f}", "-i", str(thumbnail_path),
            "-i", str(video_path),
            "-f", "lavfi", "-t", f"{max(0.08, float(duration)):.2f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-filter_complex", filt,
            "-map", "[v]", "-map", "[a]",
            *fallback_args,
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(temp),
        ]
        r = _run_media_cmd(cmd, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "Không chèn được thumbnail vào frame đầu").strip()[-2400:])
    shutil.move(str(temp), str(video_path))
    return video_path


def _srt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(segments: list[dict], path: Path) -> None:
    lines: list[str] = []
    for idx, seg in enumerate(segments, 1):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        lines.extend([
            str(idx),
            f"{_srt_time(float(seg.get('start', 0)))} --> {_srt_time(float(seg.get('end', 0)))}",
            text,
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _default_dji_lut_path() -> str:
    candidate = Path.home() / "Downloads" / "DJI OSMO Osmo Nano D-Log M to Rec.709 V1.cube"
    return str(candidate) if candidate.exists() else ""


def _copy_lut_to_app_data(src: str | Path) -> str:
    src_path = Path(str(src)).expanduser()
    if not src_path.exists():
        return ""
    target_dir = Path(DEFAULT_OUT).parent / "luts"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / src_path.name
    if src_path.resolve() != target.resolve():
        shutil.copy2(src_path, target)
    return str(target)


def _escape_filter_path(path: str | Path) -> str:
    # FFmpeg filter values use ':' as separators, so escape common path chars.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _merge_ranges(ranges: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    clean = []
    for start, end in ranges:
        s = max(0.0, min(duration, float(start)))
        e = max(0.0, min(duration, float(end)))
        if e - s >= 0.08:
            clean.append((s, e))
    clean.sort()
    merged: list[tuple[float, float]] = []
    for s, e in clean:
        if not merged or s > merged[-1][1] + 0.05:
            merged.append((s, e))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
    return merged


def _keep_segments_from_cuts(cuts: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    cuts = _merge_ranges(cuts, duration)
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in cuts:
        if s - cursor >= 0.2:
            keep.append((cursor, s))
        cursor = max(cursor, e)
    if duration - cursor >= 0.2:
        keep.append((cursor, duration))
    return keep or [(0.0, duration)]


def _split_thumbnail_lines(title: str) -> list[str]:
    text = _clean_thumbnail_title(title)
    if not text:
        text = "BOX SAMSUNG DEX"
    words = text.split()
    phrase_patterns = [
        (
            re.compile(r"^(MUA HUB)\s+(SAMSUNG DEX|SAMSUNGDEX|DEX)\s+(.+)$"),
            lambda m: [m.group(1), "SAMSUNG DEX", m.group(3)],
        ),
        (
            re.compile(r"^(.+?)\s+(CHO)\s+(SAMSUNG DEX|SAMSUNGDEX|DEX)\s+(.+)$"),
            lambda m: [m.group(1), f"{m.group(2)} SAMSUNG DEX", m.group(4)],
        ),
        (
            re.compile(r"^(HUB)\s+(SAMSUNG DEX|SAMSUNGDEX|DEX)\s+(4K)\s+(.+)$"),
            lambda m: [m.group(1), "SAMSUNG DEX 4K", m.group(4)],
        ),
        (
            re.compile(r"^(HUB)\s+(TYPE-C|USB-C)\s+(CHO)\s+(.+)$"),
            lambda m: [f"{m.group(1)} {m.group(2)}", f"{m.group(3)} {m.group(4)}"],
        ),
        (
            re.compile(r"^(HUB)\s+(SAMSUNG DEX|SAMSUNGDEX|DEX)\s+(.+)$"),
            lambda m: [m.group(1), "SAMSUNG DEX", m.group(3)],
        ),
        (
            re.compile(r"^(SETUP)\s+(SAMSUNG DEX|SAMSUNGDEX|DEX)\s+(.+)$"),
            lambda m: [m.group(1), "SAMSUNG DEX", m.group(3)],
        ),
        (
            re.compile(r"^(.+?)\s+(LOA MOMO)\s+(.+)$"),
            lambda m: [m.group(1), m.group(2), m.group(3)] if m.group(1).strip() else [m.group(2), m.group(3)],
        ),
        (
            re.compile(r"^(LOA MOMO)\s+(.+)$"),
            lambda m: [m.group(1), m.group(2)],
        ),
        (
            re.compile(r"^(.+?)\s+(SIM 4G)\s*$"),
            lambda m: [m.group(1), m.group(2)],
        ),
        (
            re.compile(r"^(HDMI 2\.[01])\s+(4K 120HZ)\s+(.+)$"),
            lambda m: [m.group(1), m.group(2), m.group(3)],
        ),
        (
            re.compile(r"^(SẠC NHANH)\s+(\d+\s*W)\s+(CHO)\s+(.+)$"),
            lambda m: [m.group(1), m.group(2).replace(" ", ""), f"{m.group(3)} {m.group(4)}"],
        ),
        (
            re.compile(r"^(KHỞI ĐỘNG LẠI)\s+(SAMSUNG DEX|SAMSUNGDEX|DEX)\s+(BỊ ĐƠ|BỊ TREO|BỊ LAG)$"),
            lambda m: [m.group(1), "SAMSUNG DEX" if "DEX" in m.group(2) else m.group(2), m.group(3)],
        ),
        (
            re.compile(r"^(POCKET 3)\s+(.+?)\s+(\d{4})$"),
            lambda m: [m.group(1), m.group(2), m.group(3)],
        ),
        (
            re.compile(r"^(TUA VÍT)\s+(XIAOMI)\s+(SỬA)\s+(.+)$"),
            lambda m: [m.group(1), f"{m.group(2)} {m.group(3)}", m.group(4)],
        ),
    ]
    for pattern, builder in phrase_patterns:
        match = pattern.match(text)
        if match:
            lines = [line.strip() for line in builder(match) if line and line.strip()]
            if lines:
                return lines[:4]
    price_match = re.search(r"\b(CHỈ|CHI|GIÁ|GIA|CÓ GIÁ|CO GIA)\s+(\d{2,5}K)\b$", text)
    if price_match and len(words) >= 5:
        price_words = price_match.group(0).split()
        head_words = words[:-len(price_words)]
        if len(head_words) >= 2:
            if len(head_words) <= 3:
                return [" ".join(head_words), " ".join(price_words)]
            split = max(1, min(len(head_words) - 1, round(len(head_words) / 2)))
            if "SAMSUNG" in head_words and "DEX" in head_words:
                samsung_idx = head_words.index("SAMSUNG")
                dex_idx = head_words.index("DEX")
                if samsung_idx < dex_idx and samsung_idx > 0:
                    return [
                        " ".join(head_words[:samsung_idx]),
                        " ".join(head_words[samsung_idx:]),
                        " ".join(price_words),
                    ]
                split = min(len(head_words) - 1, dex_idx + 1)
            return [
                " ".join(head_words[:split]),
                " ".join(head_words[split:]),
                " ".join(price_words),
            ]
    if len(words) <= 3:
        return [" ".join(words)]
    if len(words) <= 6:
        target_lines = 2
    elif len(words) <= 10:
        target_lines = 3
    else:
        target_lines = 4

    target_chars = max(10, int(sum(len(w) for w in words) / target_lines) + 2)
    lines: list[list[str]] = []
    current: list[str] = []
    for word in words:
        remaining_words = len(words) - sum(len(line) for line in lines) - len(current)
        remaining_lines = target_lines - len(lines)
        trial = " ".join(current + [word])
        should_break = (
            current
            and len(trial) > target_chars
            and remaining_words >= remaining_lines
            and len(lines) < target_lines - 1
        )
        if should_break:
            lines.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(current)

    # Balance short orphan lines by moving one word down from the previous line.
    changed = True
    while changed and len(lines) > 1:
        changed = False
        for idx in range(1, len(lines)):
            prev = lines[idx - 1]
            cur = lines[idx]
            if len(cur) == 1 and len(prev) >= 3:
                cur.insert(0, prev.pop())
                changed = True
    for idx in range(len(lines) - 1):
        cur_text = " ".join(lines[idx])
        if cur_text == "SAMSUNG DEX" and lines[idx + 1] and re.match(r"^S\d", lines[idx + 1][0]):
            lines[idx].append(lines[idx + 1].pop(0))
        if lines[idx] and lines[idx][-1] == "HỎA" and lines[idx + 1] and lines[idx + 1][0] == "TỐC":
            lines[idx].append(lines[idx + 1].pop(0))
        if lines[idx] and lines[idx][-1] in {"ĐỂ", "VỚI", "TRÊN"} and lines[idx + 1]:
            lines[idx + 1].insert(0, lines[idx].pop())
    lines = [line for line in lines if line]
    return [" ".join(line) for line in lines[:4] if line]


def _fallback_thumbnail_title(source_title: str, segments: list[dict] | None = None) -> str:
    context = _thumbnail_context_text(source_title, segments)
    early = _fix_common_title_misreads(_plain_upper(_early_thumbnail_context(segments)))
    upper = _fix_common_title_misreads(_plain_upper(context))
    product = _extract_known_product_context(context)
    hdmi_title = _hdmi_title_from_context(source_title, segments)
    if hdmi_title:
        return hdmi_title
    if (
        ("THOÁT KHỎI CHẾ ĐỘ" in upper or "THOÁ KHỎI CHẾ ĐỘ" in upper or "THOAT KHOI CHE DO" in _ascii_upper(upper))
        and ("ĐĂNG NHẬP" in upper or "LOGIN" in upper)
        and "GAME" in upper
    ):
        return "THOÁT DEX ĐỂ ĐĂNG NHẬP GAME"
    if (
        ("GAME" in early or "GAME" in upper)
        and any(key in early for key in ("BỊ CHẶN", "BI CHAN", "KHÔNG CHO LOGIN", "KHONG CHO LOGIN", "KHÔNG ĐĂNG NHẬP", "KHONG DANG NHAP"))
    ):
        if product:
            return _clean_thumbnail_title(f"ĐĂNG NHẬP GAME BỊ CHẶN TRÊN {product}", source_title, segments)
        return "ĐĂNG NHẬP GAME BỊ CHẶN"
    if ("ĐĂNG NHẬP" in upper or "DANG NHAP" in _ascii_upper(upper)) and "CH PLAY" in upper:
        return _clean_thumbnail_title(
            f"ĐĂNG NHẬP CH PLAY TRÊN {product}" if product else "ĐĂNG NHẬP CH PLAY",
            source_title,
            segments,
        )
    if "SAMSUNG DEX" in upper or "SAMSUNGDEX" in upper:
        if "4K" in upper:
            return "SETUP SAMSUNG DEX NHẬN 4K"
        return "SETUP SAMSUNG DEX DỄ HƠN"

    joined = " ".join(str(seg.get("text", "")) for seg in (segments or [])[:30])
    text = re.sub(r"\s+", " ", joined or source_title or "").strip()
    text = re.sub(r"\b(à|ừ|ờ|ừm|um|uh|thì|là|mà|này|kia|đó)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .,!?:;")
    words = text.split()
    candidate = " ".join(words[:10]) if words else source_title or "BOX PHONE"
    return _clean_thumbnail_title(candidate, source_title, segments)


def _thumbnail_affiliate_candidates(source_title: str, segments: list[dict] | None = None) -> list[str]:
    context = _thumbnail_context_text(source_title, segments)
    early = _fix_common_title_misreads(_plain_upper(_early_thumbnail_context(segments)))
    upper = _fix_common_title_misreads(_plain_upper(context))
    product = _extract_known_product_context(context)
    candidates: list[str] = []

    def add(title: str) -> None:
        clean = _clean_thumbnail_title(title, source_title, segments)
        if clean and clean not in candidates and not _is_weak_thumbnail_title(clean, context):
            candidates.append(clean)

    if (
        ("THOÁT KHỎI CHẾ ĐỘ" in upper or "THOÁ KHỎI CHẾ ĐỘ" in upper or "THOAT KHOI CHE DO" in _ascii_upper(upper))
        and ("ĐĂNG NHẬP" in upper or "LOGIN" in upper)
        and "GAME" in upper
    ):
        add("THOÁT DEX ĐỂ ĐĂNG NHẬP GAME")
    if (
        ("GAME" in early or "GAME" in upper)
        and any(key in early for key in ("BỊ CHẶN", "BI CHAN", "KHÔNG CHO LOGIN", "KHONG CHO LOGIN", "KHÔNG ĐĂNG NHẬP", "KHONG DANG NHAP"))
    ):
        add(f"ĐĂNG NHẬP GAME BỊ CHẶN TRÊN {product}" if product else "ĐĂNG NHẬP GAME BỊ CHẶN")
    if ("ĐĂNG NHẬP" in upper or "DANG NHAP" in _ascii_upper(upper)) and "CH PLAY" in upper:
        add(f"ĐĂNG NHẬP CH PLAY TRÊN {product}" if product else "ĐĂNG NHẬP CH PLAY")
    hdmi_title = _hdmi_title_from_context(source_title, segments)
    if hdmi_title:
        add(hdmi_title)
    if "MOMO" in upper:
        if "GIẤY PHÉP" in upper or "GIAY PHEP" in _ascii_upper(upper):
            add("MUA LOA MOMO CẦN GIẤY PHÉP")
        if "SIM 4G" in upper or "4G" in upper:
            add("LOA THANH TOÁN KÈM SIM 4G")
        if "THANH TOÁN" in upper or "THANH TOAN" in _ascii_upper(upper):
            add("LOA THANH TOÁN MOMO")
    if "USB" in upper:
        if "FAKE" in upper or "4.5" in upper or "TỐC ĐỘ" in upper or "TOC DO" in _ascii_upper(upper):
            add("USB 2TB FAKE TỐC ĐỘ CHẬM")
        if "CHÉP NHẠC" in upper or "CHEP NHAC" in _ascii_upper(upper):
            add("USB GIÁ RẺ CHỈ CHÉP NHẠC")
    if ("SAMSUNG DEX" in upper or "SAMSUNGDEX" in upper) and ("HUB" in upper or "HẤP" in upper or "HAP" in _ascii_upper(upper)):
        add("SAMSUNG DEX CHỈ CẦN 1 HUB")
    add(_fallback_thumbnail_title(source_title, segments))
    return candidates[:5]


def _score_thumbnail_title(title: str, source_title: str, segments: list[dict] | None = None) -> int:
    clean = _fix_common_title_misreads(_plain_upper(title))
    context = _fix_common_title_misreads(_plain_upper(_thumbnail_context_text(source_title, segments)))
    early = _fix_common_title_misreads(_plain_upper(_early_thumbnail_context(segments)))
    score = 0
    words = clean.split()
    if 4 <= len(words) <= 9:
        score += 8
    if "THOÁT DEX" in clean or "THOÁT KHỎI" in clean:
        score += 18
    if "ĐĂNG NHẬP GAME" in clean:
        score += 12
    if "BỊ CHẶN" in clean or "KHÔNG CHO LOGIN" in clean:
        score += 8
    if "SAMSUNG DEX" in clean:
        score += 6
    elif "DEX" in clean:
        score += 4
    if "CH PLAY" in clean:
        score += 2
    if any(term in clean for term in ("HUB", "TYPE-C", "USB-C", "HDMI", "PD", "GAN", "SẠC NHANH")):
        score += 6
    if clean.startswith(("CÁP HDMI", "DÂY HDMI")):
        score += 8
    if "USB" in clean and any(key in clean for key in ("FAKE", "TỐC ĐỘ", "CHÉP NHẠC", "GIÁ RẺ")):
        score += 10
    if ("LOA" in clean or "MOMO" in clean) and any(key in clean for key in ("THANH TOÁN", "GIẤY PHÉP", "SIM 4G", "MOMO")):
        score += 10
    if any(brand in clean for brand in _THUMB_KNOWN_BRANDS if brand not in {"DJI"}):
        score += 4
    if any(key in clean for key in ("BỊ", "KHÔNG", "KẸT", "LỖI", "NHANH", "GỌN", "TIỆN", "CHỈ", "GIÁ")):
        score += 4
    if any(key in clean for key in ("4K", "120HZ", "2.0", "2.1")):
        score += 4
    product = _extract_known_product_context(context)
    if product and product in clean:
        score += 7
    elif product and any(word in clean for word in product.split()):
        score += 3
    if "THOÁT" in context and "ĐĂNG NHẬP" in context and "GAME" in context and "THOÁT" in clean:
        score += 14
    if "KHÔNG CHO LOGIN" in early and "ĐĂNG NHẬP" in clean:
        score += 6
    if "GAME BỊ CHẶN TRÊN" in clean and "ĐĂNG NHẬP" not in clean:
        score -= 20
    if "GAME CH PLAY" in clean:
        score -= 30
    score -= 60 * len(_thumbnail_title_risk_flags(clean, context))
    if len(words) > 12:
        score -= 20
    return score


def _thumbnail_title_quality(title: str, source_title: str, segments: list[dict] | None = None) -> dict:
    context = _thumbnail_context_text(source_title, segments)
    clean = _clean_thumbnail_title(title, source_title, segments)
    flags = _thumbnail_title_risk_flags(clean, context)
    score = _score_thumbnail_title(clean, source_title, segments) if clean else -100
    if not clean or _is_weak_thumbnail_title(clean, context):
        status = "needs_review"
    elif flags:
        status = "needs_review"
    elif score >= 16:
        status = "expert_checked"
    else:
        status = "fallback"
    reasons = []
    for flag in flags[:3]:
        if flag == "camera_filename":
            reasons.append("loại tên file camera")
        elif flag == "uncorrected_asr":
            reasons.append("sửa lỗi ASR")
        elif flag.startswith("awkward_term:"):
            reasons.append("cụm từ chưa tự nhiên")
        elif flag == "awkward_phrase":
            reasons.append("cụm từ bị lặp/ngượng")
        elif flag == "generic_viewer_filler":
            reasons.append("loại câu mở đầu thừa")
        elif flag == "incomplete_price_hook":
            reasons.append("hook giá bị thiếu số")
        elif flag == "uncertain_brand_asr":
            reasons.append("brand ASR chưa chắc")
        elif flag.startswith("unsupported_claim:"):
            reasons.append("loại thông số chưa có bằng chứng")
        elif flag.startswith("unsupported_product:"):
            reasons.append("loại sản phẩm chưa có bằng chứng")
        else:
            reasons.append(flag.replace("_", " "))
    if status == "expert_checked" and not reasons:
        reasons.append("đúng thuật ngữ và bám hook")
    elif status == "fallback" and not reasons:
        reasons.append("fallback an toàn")
    publish_status = {
        "expert_checked": "ready",
        "needs_review": "review",
        "fallback": "fallback",
    }.get(status, "review")
    publish_label = {
        "ready": "Đăng được ngay",
        "review": "Cần xem lại",
        "fallback": "Fallback an toàn",
    }[publish_status]
    return {
        "title": clean,
        "status": status,
        "publish_status": publish_status,
        "publish_label": publish_label,
        "score": score,
        "risk_flags": flags,
        "reasons": reasons,
    }


def _one_shot_final_status(title_quality: dict | None, layout_quality: dict | None, review: dict | None = None) -> str:
    title_publish = str((title_quality or {}).get("publish_status") or "")
    layout_ok = bool((layout_quality or {}).get("ok", True))
    review = review if isinstance(review, dict) else {}
    review_status = str(review.get("status") or "")
    review_blocking = bool(review.get("blocking", False))
    if review_blocking and review_status not in {"network_error", "skipped", "disabled"}:
        return "needs_review"
    if title_publish == "ready" and layout_ok:
        return "ready"
    if layout_ok and bool(review.get("enabled")) and bool(review.get("ok")) and review_status == "ok":
        return "ready"
    if title_publish in {"review", ""} or not layout_ok:
        return "needs_review"
    return "needs_review"


def _one_shot_status_label(status: str) -> str:
    return {
        "ready": "Đăng được",
        "needs_review": "Cần xem lại",
        "failed": "Lỗi",
    }.get(str(status or ""), "Cần xem lại")


def _thumbnail_review_gate(
    title: str,
    source_title: str,
    segments: list[dict] | None,
    title_quality: dict | None,
    layout_quality: dict | None,
    enabled: bool = True,
) -> dict:
    if not enabled:
        return {
            "enabled": False,
            "attempted": False,
            "ok": True,
            "provider": "gemini",
            "status": "disabled",
            "blocking": False,
            "reasons": ["ai_review_disabled"],
            "issues": [],
            "suggested_title": "",
            "error": "",
            "cost": _estimate_gemini_cost("gemini", None),
        }
    title_quality = title_quality if isinstance(title_quality, dict) else {}
    layout_quality = layout_quality if isinstance(layout_quality, dict) else {}
    reasons: list[str] = []
    if str(title_quality.get("publish_status") or "") != "ready":
        reasons.append("title_gate_not_ready")
    severe_layout_issues = {
        str(issue)
        for issue in (layout_quality.get("issues") or [])
        if str(issue) in {"font_not_uniform", "outside_safe_width", "low_layout_score"} or str(issue).startswith("split_")
    }
    if not bool(layout_quality.get("ok", True)) or severe_layout_issues:
        reasons.append("layout_risk")
    context = _plain_upper(f"{title} {_thumbnail_context_text(source_title, segments)}")
    suspicious = ("O KRING", "CHÍNH HẼNG", "CỘNG KINH", "ANH EM XEM", "GIÁ CHỈ")
    if any(token in context for token in suspicious):
        reasons.append("suspicious_asr")
    if len(_clean_thumbnail_title(title, source_title, segments).split()) > 10:
        reasons.append("too_long")
    if not reasons:
        return {
            "enabled": False,
            "attempted": False,
            "ok": True,
            "provider": "gemini",
            "status": "skipped",
            "blocking": False,
            "reasons": ["deterministic_ready"],
            "issues": [],
            "suggested_title": "",
            "error": "",
            "cost": _estimate_gemini_cost("gemini", None),
        }
    return {
        "enabled": True,
        "attempted": False,
        "ok": False,
        "provider": "gemini",
        "status": "needs_review",
        "blocking": True,
        "reasons": reasons,
        "issues": [],
        "suggested_title": "",
        "error": "",
        "cost": _estimate_gemini_cost("gemini", None),
    }


def _one_shot_metadata_plan(
    title: str,
    source_title: str,
    segments: list[dict] | None,
    settings: dict | None = None,
    ai_metadata: dict | None = None,
) -> dict:
    metadata = _build_upload_metadata(title, source_title, segments, settings, ai_metadata)
    filename = _upload_video_output_path(Path("."), source_title, metadata).name
    hashtags = metadata.get("hashtags", []) if isinstance(metadata, dict) else []
    return {
        "upload_metadata": metadata,
        "final_video_name": filename,
        "final_hashtags": hashtags[:4],
        "metadata_gate": {
            "status": "ready" if metadata.get("upload_title") and 2 <= len(hashtags[:4]) <= 4 else "needs_review",
            "hashtag_count": len(hashtags[:4]),
            "filename_length": len(filename),
            "reasons": ["tên video = title thumbnail + hashtag vừa phải"],
        },
    }


def _parse_thumbnail_title_response(raw: str) -> dict:
    raw = raw.strip("` \n\t")
    if raw.startswith("json"):
        raw = raw[4:].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].removeprefix("json").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            out = {
                "titles": [],
                "upload_title": str(parsed.get("upload_title") or "").strip(),
                "hashtags": _normalise_ai_hashtags(parsed.get("hashtags")),
                "detected_product": str(parsed.get("detected_product") or "").strip(),
                "main_hook": str(parsed.get("main_hook") or "").strip(),
                "evidence": parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else [],
                "risk_flags": parsed.get("risk_flags") if isinstance(parsed.get("risk_flags"), list) else [],
            }
            titles = parsed.get("titles", [])
            if isinstance(titles, list):
                out["titles"] = [str(t) for t in titles if str(t).strip()]
                return out
            title = parsed.get("title") or parsed.get("suggested_title")
            out["titles"] = [str(title)] if title else []
            return out
        if isinstance(parsed, list):
            return {"titles": [str(t) for t in parsed if str(t).strip()], "upload_title": "", "hashtags": []}
    except Exception:
        pass
    return {
        "titles": [line.strip(" -•\t\"'") for line in raw.splitlines() if line.strip()],
        "upload_title": "",
        "hashtags": [],
    }


def _parse_thumbnail_title_payload(raw: str) -> list[str]:
    return list(_parse_thumbnail_title_response(raw).get("titles") or [])


def _pick_best_thumbnail_title(titles: list[str], source_title: str, segments: list[dict] | None = None) -> str:
    context = _thumbnail_context_text(source_title, segments)
    valid: list[str] = []
    for title in titles:
        clean = _clean_thumbnail_title(title, source_title, segments)
        if clean and not _is_weak_thumbnail_title(clean, context) and clean not in valid:
            valid.append(clean)
    if not valid:
        return ""
    return max(valid, key=lambda t: _score_thumbnail_title(t, source_title, segments))


def _best_rule_thumbnail_title(source_title: str, segments: list[dict] | None = None) -> str:
    candidates = _thumbnail_affiliate_candidates(source_title, segments)
    ready = [
        title
        for title in candidates
        if _thumbnail_title_quality(title, source_title, segments).get("publish_status") == "ready"
    ]
    if ready:
        return max(ready, key=lambda t: _score_thumbnail_title(t, source_title, segments))
    valid = [
        title
        for title in candidates
        if title and not _is_weak_thumbnail_title(title, _thumbnail_context_text(source_title, segments))
    ]
    return max(valid, key=lambda t: _score_thumbnail_title(t, source_title, segments)) if valid else ""


def _gemini_thumbnail_title_from_settings(
    settings: dict,
    segments: list[dict],
    source_title: str,
    log_cb=None,
    mode: str = "expert",
    provider_state: dict | None = None,
) -> str:
    provider_state = provider_state if isinstance(provider_state, dict) else {}
    api_key = _configured_ai_key(settings, "GEMINI_API_KEY", "gemini_api_key")
    if not api_key:
        return ""
    model = str(settings.get("gemini_text_model", "gemini-2.5-flash-lite") or "gemini-2.5-flash-lite")
    if model == "auto":
        model = "gemini-2.5-flash-lite"
    early_transcript = "\n".join(str(seg.get("text", "")) for seg in segments[:8])
    transcript = "\n".join(str(seg.get("text", "")) for seg in segments[:140])
    candidates = _thumbnail_affiliate_candidates(source_title, segments)
    candidate_text = "\n".join(f"- {title}" for title in candidates) or "- Không có"
    mode_hint = {
        "viral": "Ưu tiên hook mạnh hơn nhưng vẫn đúng transcript, không giật tít sai.",
        "short": "Ưu tiên title cực ngắn 4-6 từ, dễ đọc trong thumbnail.",
        "expert": "Ưu tiên đúng chuyên ngành, tự nhiên, không sai thuật ngữ.",
    }.get(mode, "Ưu tiên đúng chuyên ngành, tự nhiên, không sai thuật ngữ.")
    prompt = f"""
Bạn là strategist thumbnail TikTok cho kênh affiliate bán hàng viral tiếng Việt.
Hãy đọc transcript và tạo title thumbnail tối ưu cho chuyển đổi.

Mục tiêu:
- Mode đang chọn: {mode_hint}
- Ưu tiên hook/pain/use-case chính trong 5-18 giây đầu.
- Không kéo sản phẩm phụ ở cuối video lên thumbnail nếu nó không giải quyết pain chính.
- Nếu video là tutorial/lỗi phần mềm, dùng pain hoặc hành động chính.
- Nếu video là phụ kiện/sản phẩm, dùng sản phẩm + lợi ích cụ thể.
- 4-9 từ là tốt nhất, tối đa 12 từ.
- Ngôn ngữ tự nhiên, dễ đọc trong 1 giây, kiểu thumbnail BoxPhoneFarm.
- Không dùng câu generic kiểu "Làm thế nào để...".
- Không bịa sản phẩm/giá/thông số nếu transcript không nói.
- Tự sửa lỗi ASR rõ ràng: "set play/sét play" = "CH Play", "Samsung Deck" = "Samsung Dex".
- Tự sửa lỗi ASR sản phẩm: "hấp/háp/hap Samsung Dex/4K/120Hz/HDMI" = "hub".
- Từ chuyên ngành đúng: "Pocket Bar" thường là "Pocket 3"; "tu vit/tô vít" = "tua vít".
- Có thể chọn một candidate bên dưới nếu nó tốt nhất, hoặc viết title tốt hơn.
- Trả JSON thuần, không markdown:
{{"titles":["...","...","..."],"upload_title":"...","caption_short":"...","caption_full":"...","hashtags":["#..."],"detected_product":"...","main_hook":"...","evidence":["..."],"risk_flags":[]}}

Ví dụ style:
GAME BỊ CHẶN TRÊN SAMSUNG DEX
THOÁT DEX ĐỂ ĐĂNG NHẬP GAME
DEX KHÔNG ĐĂNG NHẬP ĐƯỢC GAME
HUB 120K CHƠI DEX FULL MÀN

Tên file: {source_title}
Transcript đầu video:
{early_transcript[:2500]}

Candidate từ rule nội bộ:
{candidate_text}

Transcript:
{transcript[:9000]}
""".strip()
    for attempt in range(2):
        if attempt > 0:
            time.sleep(1.2)
            if log_cb:
                log_cb("Gemini tạm lỗi — thử lại 1 lần")
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=45,
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed = _parse_thumbnail_title_response(raw)
            title = _pick_best_thumbnail_title(parsed.get("titles") or [], source_title, segments)
            if not _is_weak_thumbnail_title(title, _thumbnail_context_text(source_title, segments)):
                provider_state["ai_metadata"] = {
                    "provider": "gemini",
                    "upload_title": parsed.get("upload_title", ""),
                    "hashtags": parsed.get("hashtags", []),
                    "detected_product": parsed.get("detected_product", ""),
                    "main_hook": parsed.get("main_hook", ""),
                    "evidence": parsed.get("evidence", []),
                    "risk_flags": parsed.get("risk_flags", []),
                }
                if log_cb:
                    log_cb("Gemini title OK")
                return title
            if log_cb:
                log_cb(f"Gemini title chưa đạt, dùng fallback: {title}")
            return ""
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in {429, 500, 502, 503, 504} and attempt == 0:
                continue
            if log_cb:
                log_cb(f"Gemini thumbnail title lỗi: {e}")
            return ""
    return ""


def _deepseek_thumbnail_title_from_settings(
    settings: dict,
    segments: list[dict],
    source_title: str,
    log_cb=None,
    provider_state: dict | None = None,
    mode: str = "expert",
) -> tuple[str, str, list[dict]]:
    provider_state = provider_state if isinstance(provider_state, dict) else {}
    api_key = _configured_ai_key(settings, "DEEPSEEK_API_KEY", "ds_api_key")
    if not api_key:
        return "", "", []
    early_transcript = "\n".join(str(seg.get("text", "")) for seg in segments[:8])
    transcript = "\n".join(str(seg.get("text", "")) for seg in segments[:140])
    candidates = _thumbnail_affiliate_candidates(source_title, segments)
    candidate_text = "\n".join(f"- {title}" for title in candidates) or "- Không có"
    system = (
        "Bạn là strategist thumbnail TikTok affiliate tiếng Việt. "
        "Chọn hook chính giúp người xem dừng lại và có nhu cầu mua/nhắn hỏi. "
        "Trả JSON hợp lệ, không markdown."
    )
    mode_hint = {
        "viral": "Ưu tiên title viral hơn, nhưng mọi claim vẫn phải có trong transcript.",
        "short": "Ưu tiên title ngắn 4-6 từ, ít chữ, dễ đọc trên màn nhỏ.",
        "expert": "Ưu tiên chuẩn thuật ngữ công nghệ/affiliate, không ngượng tiếng Việt.",
    }.get(mode, "Ưu tiên chuẩn thuật ngữ công nghệ/affiliate, không ngượng tiếng Việt.")
    user = f"""
Đọc transcript video one-shot và tạo 3 tiêu đề thumbnail tối ưu cho chuyển đổi.

Tiêu chí:
- Mode đang chọn: {mode_hint}
- Nếu có một hành động/giải pháp rõ trong transcript, ưu tiên title dạng hành động hơn title chỉ nêu vấn đề.
- Ưu tiên pain/use-case trong 5-18 giây đầu.
- Nếu video là lỗi/tutorial, title phải bám pain hoặc hành động chính.
- Nếu video là sản phẩm/phụ kiện, title phải bám sản phẩm chính + lợi ích chính.
- Không kéo sản phẩm phụ ở cuối video lên thumbnail nếu nó không giải quyết hook chính.
- 4-9 từ là tốt nhất, tối đa 12 từ.
- Tự sửa lỗi ASR rõ ràng: "set play/sét play" = "CH Play", "Samsung Deck" = "Samsung Dex".
- Tự sửa lỗi ASR sản phẩm: "hấp/háp/hap Samsung Dex/4K/120Hz/HDMI" = "hub".
- Từ chuyên ngành đúng: "Pocket Bar" thường là "Pocket 3"; "tu vit/tô vít" = "tua vít".
- Có thể chọn candidate bên dưới nếu nó tốt nhất.
- Tránh title sai/ngượng: "Đăng nhập game CH Play trên Samsung Dex", tên file DJI/IMG/MP4, hoặc title chung chung.
- Trả JSON đúng format:
{{"titles":["...","...","..."],"upload_title":"...","caption_short":"...","caption_full":"...","hashtags":["#..."],"detected_product":"...","main_hook":"...","evidence":["..."],"risk_flags":[]}}

Ví dụ đúng:
THOÁT DEX ĐỂ ĐĂNG NHẬP GAME
ĐĂNG NHẬP GAME BỊ CHẶN TRÊN SAMSUNG DEX
LÊN ĐƠN BOX SAMSUNG DEX S20

Ví dụ sai:
ĐĂNG NHẬP GAME CH PLAY TRÊN SAMSUNG DEX
GAME BỊ CHẶN TRÊN SAMSUNG DEX (sai nếu chỉ login bị chặn)
DJI 20260523090544 0001 D
HUB 120K CHƠI DEX FULL MÀN (sai nếu hook chính là game bị chặn)
HẤP SAMSUNG DEX 4K 120HZ (sai chính tả, phải là HUB)

Tên file: {source_title}

Transcript đầu video:
{early_transcript[:2500]}

Candidate:
{candidate_text}

Transcript đầy đủ:
{transcript[:9000]}
""".strip()
    costs: list[dict] = []
    context = _thumbnail_context_text(source_title, segments)

    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.55,
                "max_tokens": 220,
            },
            timeout=35,
        )
        resp.raise_for_status()
        data = resp.json()
        model = str(data.get("model") or "deepseek-chat")
        costs.append(_estimate_ai_cost("deepseek", model, data.get("usage", {})))
        raw = data["choices"][0]["message"].get("content", "").strip()
        parsed = _parse_thumbnail_title_response(raw)
        title = _pick_best_thumbnail_title(parsed.get("titles") or [], source_title, segments)
        if title:
            provider_state["ai_metadata"] = {
                "provider": "deepseek",
                "upload_title": parsed.get("upload_title", ""),
                "hashtags": parsed.get("hashtags", []),
                "detected_product": parsed.get("detected_product", ""),
                "main_hook": parsed.get("main_hook", ""),
                "evidence": parsed.get("evidence", []),
                "risk_flags": parsed.get("risk_flags", []),
            }
            if log_cb:
                cost = costs[-1]
                log_cb(f"DeepSeek title OK ({model}) · ${cost['estimated_usd']:.6f} ~ {cost['estimated_vnd']}đ")
            return title, "deepseek", costs
        if log_cb:
            log_cb("DeepSeek chat title chưa đạt — thử Pro 1/1")
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 402:
            if log_cb:
                log_cb("DeepSeek hết credit 402 — video này chuyển sang Gemini/fallback")
            return "", "", costs
        if status in (401, 403):
            provider_state["deepseek_auth_failed"] = True
            if log_cb:
                log_cb("DeepSeek key không hợp lệ hoặc chưa có quyền — chuyển sang Gemini/fallback")
            return "", "", costs
        if log_cb:
            log_cb(f"DeepSeek chat title lỗi: {e}")

    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-v4-pro",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.45,
                "max_tokens": 600,
            },
            timeout=35,
        )
        resp.raise_for_status()
        data = resp.json()
        model = str(data.get("model") or "deepseek-v4-pro")
        costs.append(_estimate_ai_cost("deepseek", "deepseek-v4-pro", data.get("usage", {})))
        raw = data["choices"][0]["message"].get("content", "").strip()
        if not raw:
            if log_cb:
                log_cb("DeepSeek Pro không trả content — dùng fallback")
            return "", "", costs
        raw = raw.strip("` \n\t\"'")
        raw = re.sub(r"^[Tt]iêu đề\s*:\s*", "", raw).strip()
        parsed = _parse_thumbnail_title_response(raw)
        title = _pick_best_thumbnail_title(parsed.get("titles") or [], source_title, segments) or _clean_thumbnail_title(raw, source_title, segments)
        if not _is_weak_thumbnail_title(title, context):
            provider_state["ai_metadata"] = {
                "provider": "deepseek_pro",
                "upload_title": parsed.get("upload_title", ""),
                "hashtags": parsed.get("hashtags", []),
                "detected_product": parsed.get("detected_product", ""),
                "main_hook": parsed.get("main_hook", ""),
                "evidence": parsed.get("evidence", []),
                "risk_flags": parsed.get("risk_flags", []),
            }
            if log_cb:
                cost = costs[-1]
                log_cb(f"DeepSeek Pro title OK · ${cost['estimated_usd']:.6f} ~ {cost['estimated_vnd']}đ")
            return title, "deepseek_pro", costs
        if log_cb:
            log_cb(f"DeepSeek title bị loại: {title}")
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 402:
            if log_cb:
                log_cb("DeepSeek Pro hết credit 402 — video này chuyển sang Gemini/fallback")
            return "", "", costs
        if status in (401, 403):
            provider_state["deepseek_auth_failed"] = True
            if log_cb:
                log_cb("DeepSeek Pro key không hợp lệ hoặc chưa có quyền — chuyển sang Gemini/fallback")
            return "", "", costs
        if log_cb:
            log_cb(f"DeepSeek Pro title lỗi: {e}")
    return "", "", costs


def _sum_ai_costs(costs: list[dict] | None) -> dict:
    costs = costs or []
    return {
        "estimated_usd": round(sum(float(c.get("estimated_usd", 0) or 0) for c in costs), 6),
        "estimated_vnd": int(sum(int(c.get("estimated_vnd", 0) or 0) for c in costs)),
        "total_tokens": int(sum(int(c.get("total_tokens", 0) or 0) for c in costs)),
    }


def _sum_ai_costs_by_kind(costs: list[dict] | None) -> dict:
    grouped: dict[str, list[dict]] = {}
    for cost in costs or []:
        kind = str(cost.get("kind") or "unknown")
        grouped.setdefault(kind, []).append(cost)
    return {kind: _sum_ai_costs(items) for kind, items in grouped.items()}


def _build_thumbnail_title(
    settings: dict,
    segments: list[dict] | None,
    source_title: str,
    log_cb=None,
    provider_state: dict | None = None,
    mode: str = "expert",
) -> tuple[str, str, list[dict]]:
    segments = segments or []
    provider_state = provider_state if isinstance(provider_state, dict) else {}
    ai_title, source_kind, costs = (
        _deepseek_thumbnail_title_from_settings(settings, segments, source_title, log_cb, provider_state, mode)
        if segments and not provider_state.get("deepseek_auth_failed") else ("", "", [])
    )
    context = _thumbnail_context_text(source_title, segments)
    if ai_title and _thumbnail_title_quality(ai_title, source_title, segments).get("publish_status") == "ready":
        return ai_title, source_kind or "deepseek", costs
    rule_title = _best_rule_thumbnail_title(source_title, segments)
    if rule_title and _thumbnail_title_quality(rule_title, source_title, segments).get("publish_status") == "ready":
        if log_cb and ai_title:
            log_cb(f"AI title chưa đủ chắc — dùng rule an toàn: {rule_title}")
        return rule_title, "rule", costs
    ai_title = _gemini_thumbnail_title_from_settings(settings, segments, source_title, log_cb, mode, provider_state) if segments else ""
    if ai_title and _thumbnail_title_quality(ai_title, source_title, segments).get("publish_status") == "ready":
        return ai_title, "gemini", costs
    if rule_title:
        if log_cb:
            log_cb(f"Dùng rule title an toàn: {rule_title}")
        return rule_title, "rule", costs
    fallback = _fallback_thumbnail_title(source_title, segments)
    return _clean_thumbnail_title(fallback, source_title, segments), "fallback", costs


def _gemini_review_thumbnail_image(
    settings: dict,
    image_path: Path,
    title: str,
    segments: list[dict] | None,
    source_title: str,
    log_cb=None,
) -> dict:
    api_key = _configured_ai_key(settings, "GEMINI_API_KEY", "gemini_api_key")
    if not api_key:
        if log_cb:
            log_cb("AI Review bỏ qua vì thiếu Gemini key")
        cost = _estimate_gemini_cost("gemini", None)
        return {
            "enabled": False,
            "attempted": False,
            "ok": True,
            "provider": "gemini",
            "status": "disabled",
            "blocking": False,
            "score": 0.0,
            "issues": [],
            "suggested_title": "",
            "error": "missing_gemini_api_key",
            "cost": cost,
        }
    if not image_path.exists():
        if log_cb:
            log_cb("AI Review bỏ qua vì thiếu file thumbnail")
        cost = _estimate_gemini_cost("gemini", None)
        return {
            "enabled": False,
            "attempted": False,
            "ok": True,
            "provider": "gemini",
            "status": "skipped",
            "blocking": False,
            "score": 0.0,
            "issues": [],
            "suggested_title": "",
            "error": "missing_thumbnail_file",
            "cost": cost,
        }
    model = str(settings.get("gemini_text_model", "gemini-2.5-flash-lite") or "gemini-2.5-flash-lite")
    if model == "auto":
        model = "gemini-2.5-flash-lite"
    early_transcript = "\n".join(str(seg.get("text", "")) for seg in (segments or [])[:16])
    prompt = f"""
Bạn là reviewer thumbnail TikTok cho kênh affiliate đồ công nghệ/điện tử.
Hãy nhìn ảnh thumbnail đã render và kiểm tra cả text + layout.

Checklist:
- Text đúng chính tả tiếng Việt và từ chuyên ngành.
- Sửa từ ngành nếu sai: hub, Samsung Dex, HDMI, Type-C, USB-C, Pocket 3, tua vít, iPhone, CH Play.
- Text phải bám đúng sản phẩm chính và pain/hook chính trong 5-18 giây đầu.
- Không chấp nhận title bịa giá/thông số/sản phẩm nếu transcript không có bằng chứng.
- Line break có logic theo cụm nghĩa: sản phẩm / hành động / lỗi / giá.
- Các dòng chữ trong cùng thumbnail phải cùng một size; không chấp nhận dòng ngắn bị phóng to hoặc dòng dài bị co nhỏ riêng.
- Không tách cụm chuyên ngành/hành động sang hai dòng rời rạc: Samsung Dex, Type-C, USB-C, CH Play, kiểm tra 4K.
- Text cân giữa, không lệch trái/phải.
- Text nằm trong vùng an toàn, không quá sát mép, không đè caption đáy.
- Đọc được trong 1 giây, không quá dài.
- Khi xem ở grid 3 cột TikTok, block chữ phải gọn, đều nhịp, không lộn xộn.
- Nếu có giá như CHỈ 80K/CÓ GIÁ 1900K, nên là dòng riêng cuối.

Trả JSON thuần:
{{
  "ok": true,
  "score": 0.0,
  "issues": ["..."],
  "suggested_title": "..."
}}

Quy tắc:
- Nếu title hiện tại đã ổn, để suggested_title rỗng.
- Nếu sai từ ngành/chính tả rõ, suggested_title phải là title đã sửa.
- Nếu title sai sản phẩm chính, suggested_title phải chuyển về sản phẩm/pain chính có bằng chứng.
- Không bịa thông số/giá/sản phẩm ngoài transcript.

Title hiện tại: {title}
Tên file nguồn: {source_title}
Transcript:
{early_transcript[:3500]}
""".strip()
    mime_type = "image/png"
    review_image = image_path
    image_bytes = image_path.read_bytes()
    try:
        from PIL import Image, ImageOps
        with Image.open(image_path) as src:
            img = ImageOps.exif_transpose(src).convert("RGB")
            img.thumbnail((540, 960), Image.Resampling.LANCZOS)
            small_path = image_path.with_name(f"{image_path.stem}_ai_review.jpg")
            img.save(small_path, format="JPEG", quality=82, optimize=True)
            if small_path.exists() and small_path.stat().st_size < len(image_bytes):
                review_image = small_path
                image_bytes = small_path.read_bytes()
                mime_type = "image/jpeg"
    except Exception:
        review_image = image_path
        image_bytes = image_path.read_bytes()
        mime_type = "image/png"
    try:
        data_b64 = base64.b64encode(image_bytes).decode("ascii")
        payload_body = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": data_b64}},
                ]
            }]
        }
        resp = None
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json=payload_body,
                    timeout=35,
                )
                if resp.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                    time.sleep(1.2)
                    continue
                resp.raise_for_status()
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(1.2)
                    continue
                raise
        if resp is None:
            raise last_error or RuntimeError("Gemini review không có phản hồi")
        payload = resp.json()
        raw = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].removeprefix("json").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Gemini review không trả JSON object")
        issues = parsed.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        raw_suggested = str(parsed.get("suggested_title", "") or "").strip()
        suggested = _clean_thumbnail_title(raw_suggested, source_title, segments) if raw_suggested else ""
        result = {
            "enabled": True,
            "provider": "gemini",
            "attempted": True,
            "status": "ok" if bool(parsed.get("ok", False)) else "needs_fix",
            "blocking": not bool(parsed.get("ok", False)),
            "ok": bool(parsed.get("ok", False)),
            "score": float(parsed.get("score", 0) or 0),
            "issues": [str(i)[:160] for i in issues[:6]],
            "suggested_title": suggested if suggested and not _is_weak_thumbnail_title(suggested, _thumbnail_context_text(source_title, segments)) else "",
            "error": "",
            "input_image": str(review_image),
            "input_image_bytes": len(image_bytes),
            "cost": _estimate_gemini_cost(model, payload.get("usageMetadata")),
        }
        if log_cb:
            status = "OK" if result["ok"] else "cần chỉnh"
            log_cb(f"Gemini review thumbnail: {status} · score {result['score']:.2f}")
            if result["issues"]:
                log_cb("Thumbnail issues: " + "; ".join(result["issues"][:3]))
        return result
    except Exception as e:
        network_error = isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError))
        if log_cb:
            if network_error:
                log_cb(f"AI review thumbnail bỏ qua do lỗi mạng/API: {e}")
            else:
                log_cb(f"Gemini review thumbnail lỗi: {e}")
        return {
            "enabled": True,
            "provider": "gemini",
            "attempted": True,
            "status": "network_error" if network_error else "failed",
            "blocking": not network_error,
            "ok": False,
            "score": 0.0,
            "issues": [str(e)[:160]],
            "suggested_title": "",
            "error": str(e)[:240],
            "input_image": str(review_image),
            "input_image_bytes": len(image_bytes),
            "cost": _estimate_gemini_cost(model if "model" in locals() else "gemini", None),
        }


_THUMB_FONT_FAMILIES: dict[str, str] = {}
_THUMB_FONT_FILES: dict[str, str] = {}
_SAFE_THUMB_FONT_FALLBACKS = ("Arial Black", "Arial", "Helvetica Neue", "Helvetica")


def _thumbnail_font_registry() -> dict[str, list[Path]]:
    root = _resource_root()
    return {
        "dt_phudu_black": [
            root / "assets" / "fonts" / "DTPhudu-Black.otf",
            Path.home() / "Downloads" / "DT-Phudu" / "Fonts Files" / "DTPhudu-Black.otf",
        ],
        "dt_phudu_bold": [
            root / "assets" / "fonts" / "DTPhudu-Bold.otf",
            Path.home() / "Downloads" / "DT-Phudu" / "Fonts Files" / "DTPhudu-Bold.otf",
        ],
        "arial_bold": [
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ],
        "arial_unicode": [
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/Library/Fonts/Arial Unicode.ttf"),
        ],
        # Legacy settings aliases kept deterministic.
        "arial_black": [
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ],
        "system_heavy": [
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        ],
    }


def _resource_root() -> Path:
    try:
        import sys
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
    except Exception:
        pass
    return Path(__file__).resolve().parent


def _thumbnail_font_family(font_key: str = "dt_phudu_black") -> str:
    key = (font_key or "dt_phudu_black").strip()
    if key in _THUMB_FONT_FAMILIES:
        return _THUMB_FONT_FAMILIES[key]
    available = set(QFontDatabase.families())

    def _available_or_default(candidates: tuple[str, ...] = _SAFE_THUMB_FONT_FALLBACKS) -> str:
        for family in candidates:
            if family in available:
                return family
        return next(iter(available), "Arial")

    if key == "arial_black":
        _THUMB_FONT_FAMILIES[key] = _available_or_default(("Arial Black", "Arial", "Helvetica"))
        return _THUMB_FONT_FAMILIES[key]
    if key == "system_heavy":
        _THUMB_FONT_FAMILIES[key] = _available_or_default(("Arial", "Helvetica Neue", "Helvetica"))
        return _THUMB_FONT_FAMILIES[key]

    font_file = "DTPhudu-Bold.otf" if key == "dt_phudu_bold" else "DTPhudu-Black.otf"
    candidates = [
        _resource_root() / "assets" / "fonts" / font_file,
        Path.home() / "Downloads" / "DT-Phudu" / "Fonts Files" / font_file,
        _resource_root() / "assets" / "fonts" / "DTPhudu-Black.otf",
        Path.home() / "Downloads" / "DT-Phudu" / "Fonts Files" / "DTPhudu-Black.otf",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _THUMB_FONT_FAMILIES[key] = families[0]
                return _THUMB_FONT_FAMILIES[key]
        except Exception:
            continue
    _THUMB_FONT_FAMILIES[key] = _available_or_default()
    return _THUMB_FONT_FAMILIES[key]


def _thumbnail_font_file(font_key: str = "dt_phudu_black", sample_text: str = "") -> str:
    key = (font_key or "dt_phudu_black").strip()
    cache_key = f"{key}:{unicodedata.normalize('NFC', sample_text or '')}"
    if cache_key in _THUMB_FONT_FILES:
        return _THUMB_FONT_FILES[cache_key]
    if not sample_text and key in _THUMB_FONT_FILES:
        return _THUMB_FONT_FILES[key]
    registry = _thumbnail_font_registry()
    candidates = registry.get(key) or registry["dt_phudu_black"]
    missing_errors: list[str] = []
    for path in candidates:
        if path.exists():
            missing = _font_missing_glyphs(path, sample_text) if sample_text else []
            if missing:
                missing_errors.append(f"{path.name}: {''.join(missing)}")
                continue
            _THUMB_FONT_FILES[cache_key] = str(path)
            if not sample_text:
                _THUMB_FONT_FILES[key] = str(path)
            return _THUMB_FONT_FILES[cache_key]
    detail = f" Thiếu glyph: {'; '.join(missing_errors)}" if missing_errors else ""
    searched = ", ".join(str(path) for path in candidates)
    raise RuntimeError(f"Không tìm thấy font thumbnail hợp lệ cho {key}. Đã tìm: {searched}.{detail}")


def _font_missing_glyphs(font_path: Path, sample_text: str) -> list[str]:
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(str(font_path), 96)
    except Exception:
        return list(dict.fromkeys(ch for ch in unicodedata.normalize("NFC", sample_text or "") if not ch.isspace()))
    missing: list[str] = []
    for ch in unicodedata.normalize("NFC", sample_text or ""):
        if ch.isspace():
            continue
        try:
            if font.getmask(ch).getbbox() is None:
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return list(dict.fromkeys(missing))


def _thumbnail_lines_for_mode(title: str, line_mode: str = "auto") -> list[str]:
    lines = _split_thumbnail_lines(title)
    target = int(line_mode) if str(line_mode) in {"2", "3"} else 0
    if not target or len(lines) == target:
        return lines
    words = " ".join(lines).split()
    if len(words) <= target:
        return lines

    best_lines = lines
    best_score: int | None = None

    def score(parts: list[str]) -> int:
        widths = [len(part) for part in parts]
        return max(widths) * 4 + max(widths) - min(widths) + sum(len(part) < 5 for part in parts) * 8

    if target == 2:
        for first in range(1, len(words)):
            candidate = [" ".join(words[:first]), " ".join(words[first:])]
            value = score(candidate)
            if best_score is None or value < best_score:
                best_lines, best_score = candidate, value
    else:
        for first in range(1, len(words) - 1):
            for second in range(first + 1, len(words)):
                candidate = [" ".join(words[:first]), " ".join(words[first:second]), " ".join(words[second:])]
                value = score(candidate)
                if best_score is None or value < best_score:
                    best_lines, best_score = candidate, value
    return best_lines


def _phrase_is_split(joined_lines: str, phrase: str) -> bool:
    phrase = re.sub(r"\s+", " ", str(phrase or "").strip())
    if not phrase or phrase in joined_lines:
        return False
    tokens = phrase.split()
    if len(tokens) < 2:
        return False
    for i in range(1, len(tokens)):
        if f"{' '.join(tokens[:i])} / {' '.join(tokens[i:])}" in joined_lines:
            return True
    return False


def _thumbnail_line_candidates(title: str, line_mode: str = "auto") -> list[list[str]]:
    base = _thumbnail_lines_for_mode(title, line_mode)
    words = " ".join(base).split()
    if not words:
        return [["BOX SAMSUNG DEX"]]

    forced = int(line_mode) if str(line_mode) in {"2", "3"} else 0
    counts = [forced] if forced else ([2] if len(words) <= 4 else [2, 3, 4, 5])
    candidates: list[list[str]] = []

    def add(parts: list[str]) -> None:
        clean = [re.sub(r"\s+", " ", part).strip() for part in parts if part and part.strip()]
        if not clean:
            return
        key = " / ".join(clean)
        if key not in {" / ".join(existing) for existing in candidates}:
            candidates.append(clean)

    add(base)

    def split_score(parts: list[str]) -> int:
        widths = [len(part) for part in parts]
        bad_tail = sum(part.split()[-1] in _THUMB_TRAILING_BAD_WORDS for part in parts[:-1] if part.split())
        joined_parts = " / ".join(parts)
        split_protected = sum(_phrase_is_split(joined_parts, phrase) for phrase in _THUMB_PROTECTED_PHRASES)
        orphan = sum(len(part) <= 4 for part in parts)
        phrase_bonus = sum(
            any(phrase in part for phrase in (*_THUMB_PROTECTED_PHRASES, "HUB 511"))
            for part in parts
        )
        price_tail_bonus = 10 if re.search(r"\b\d+[.,]?\d*\s*K\b", parts[-1], flags=re.IGNORECASE) else 0
        return (
            (max(widths) - min(widths)) * 7
            + max(widths) * 3
            + bad_tail * 80
            + split_protected * 260
            + orphan * 18
            - phrase_bonus * 8
            - price_tail_bonus
        )

    for count in counts:
        if count <= 1 or len(words) <= count:
            continue
        best: list[tuple[int, list[str]]] = []
        if count == 2:
            for first in range(1, len(words)):
                parts = [" ".join(words[:first]), " ".join(words[first:])]
                best.append((split_score(parts), parts))
        elif count == 3:
            for first in range(1, len(words) - 1):
                for second in range(first + 1, len(words)):
                    parts = [" ".join(words[:first]), " ".join(words[first:second]), " ".join(words[second:])]
                    best.append((split_score(parts), parts))
        elif count == 4:
            for first in range(1, len(words) - 2):
                for second in range(first + 1, len(words) - 1):
                    for third in range(second + 1, len(words)):
                        parts = [
                            " ".join(words[:first]),
                            " ".join(words[first:second]),
                            " ".join(words[second:third]),
                            " ".join(words[third:]),
                        ]
                        best.append((split_score(parts), parts))
        elif count == 5:
            for first in range(1, len(words) - 3):
                for second in range(first + 1, len(words) - 2):
                    for third in range(second + 1, len(words) - 1):
                        for fourth in range(third + 1, len(words)):
                            parts = [
                                " ".join(words[:first]),
                                " ".join(words[first:second]),
                                " ".join(words[second:third]),
                                " ".join(words[third:fourth]),
                                " ".join(words[fourth:]),
                            ]
                            best.append((split_score(parts), parts))
        for _score, parts in sorted(best, key=lambda item: item[0])[:6]:
            add(parts)
    return candidates[:14]


def _thumbnail_layout_quality(style: dict, render_info: dict | None = None) -> dict:
    lines = [str(line) for line in (style.get("lines") or [])]
    joined = " / ".join(lines)
    widths = [int(w) for w in (style.get("line_widths") or []) if str(w).strip()]
    safe = style.get("safe_zone") if isinstance(style.get("safe_zone"), dict) else {}
    safe_w = int(safe.get("right", 0) or 0) - int(safe.get("left", 0) or 0)
    issues: list[str] = []
    if len(set(style.get("font_size_by_line") or [])) > 1:
        issues.append("font_not_uniform")
    forbidden = {
        "SAMSUNG / DEX": "split_samsung_dex",
        "BOX SAMSUNG / DEX": "split_box_samsung_dex",
        "BOX / SAMSUNG DEX": "split_box_samsung_dex",
        "KIỂM / TRA": "split_kiem_tra",
        "GỌN / GÀNG": "split_gon_gang",
        "DỄ / HƠN": "split_de_hon",
        "TỰ / LẮP": "split_tu_lap",
        "CH / PLAY": "split_ch_play",
        "SẠC / NHANH": "split_sac_nhanh",
    }
    for phrase, issue in forbidden.items():
        if phrase in joined:
            issues.append(issue)
    if safe_w > 0 and widths and max(widths) > safe_w:
        issues.append("outside_safe_width")
    if float(style.get("line_width_ratio") or 1.0) < 0.34 and len(lines) >= 3:
        issues.append("unbalanced_line_widths")
    if int(style.get("layout_score") or 0) <= 0:
        issues.append("low_layout_score")
    if render_info and render_info.get("changed"):
        issues.append("render_title_shortened")
    return {
        "ok": not [issue for issue in issues if issue not in {"render_title_shortened"}],
        "issues": issues,
        "label": "OK" if not [issue for issue in issues if issue not in {"render_title_shortened"}] else "Cần xem lại",
    }


def _draw_boxphonefarm_thumbnail(
    frame_path: Path,
    output_path: Path,
    title: str,
    font_key: str = "dt_phudu_black",
    size_preset: str = "large",
    line_mode: str = "auto",
    position: str = "center",
) -> dict:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except Exception as exc:
        raise RuntimeError(f"Thiếu Pillow để render thumbnail tiếng Việt: {exc}") from exc

    try:
        src_img = Image.open(frame_path)
        src_img = ImageOps.exif_transpose(src_img).convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"Không đọc được frame thumbnail: {frame_path}") from exc
    if src_img.width <= 0 or src_img.height <= 0:
        raise RuntimeError(f"Không đọc được frame thumbnail: {frame_path}")

    out_w, out_h = 1080, 1920
    canvas = ImageOps.fit(src_img, (out_w, out_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)).convert("RGBA")
    shade = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 36))
    canvas = Image.alpha_composite(canvas, shade)
    draw = ImageDraw.Draw(canvas)

    # TikTok safe zone: keep the title away from top chrome and bottom caption
    # while centering it on the visual canvas. Avoid over-compensating for the
    # right action rail because that makes the cover feel left-heavy.
    safe_left = 54
    safe_top = 430
    safe_right = out_w - 54
    safe_bottom = 1180
    safe_w = safe_right - safe_left
    safe_h = safe_bottom - safe_top

    normalized_title = unicodedata.normalize("NFC", _clean_thumbnail_title(title))
    font_file = _thumbnail_font_file(font_key, normalized_title)
    stroke_width = 12
    text_w = safe_w - stroke_width * 2
    caps = {
        "auto": {1: 154, 2: 138, 3: 122, 4: 106, 5: 92},
        "large": {1: 166, 2: 150, 3: 134, 4: 116, 5: 100},
        "xlarge": {1: 178, 2: 162, 3: 146, 4: 126, 5: 108},
    }
    size_preset = size_preset if size_preset in caps else "large"

    def make_font(point_size: int):
        if font_file:
            return ImageFont.truetype(font_file, point_size)
        return ImageFont.load_default(point_size)

    def text_bbox(font, line: str, stroke: int = 0) -> tuple[int, int, int, int]:
        return draw.textbbox((0, 0), unicodedata.normalize("NFC", line), font=font, stroke_width=stroke)

    best_layout: dict | None = None
    for candidate in _thumbnail_line_candidates(title, line_mode):
        cap_size = caps[size_preset].get(len(candidate), 106)
        size = cap_size
        stroke = max(6, int(size * 0.075))
        font = make_font(size)
        line_gap = max(16, int(size * 0.12))
        boxes = [text_bbox(font, line, stroke) for line in candidate]
        widths = [box[2] - box[0] for box in boxes]
        heights = [box[3] - box[1] for box in boxes]
        line_slot_h = max(heights or [0])
        total_h = line_slot_h * len(candidate) + line_gap * max(0, len(candidate) - 1)
        while size > 54 and (max(widths or [0]) > text_w or total_h > safe_h):
            size -= 2
            stroke = max(6, int(size * 0.075))
            font = make_font(size)
            line_gap = max(16, int(size * 0.12))
            boxes = [text_bbox(font, line, stroke) for line in candidate]
            widths = [box[2] - box[0] for box in boxes]
            heights = [box[3] - box[1] for box in boxes]
            line_slot_h = max(heights or [0])
            total_h = line_slot_h * len(candidate) + line_gap * max(0, len(candidate) - 1)
        max_w = max(widths or [1])
        min_w = min(widths or [1])
        width_ratio = round(min_w / max_w, 3) if max_w else 1.0
        bad_tail = sum(line.split()[-1] in _THUMB_TRAILING_BAD_WORDS for line in candidate[:-1] if line.split())
        joined_lines = " / ".join(candidate)
        split_phrase = sum(
            _phrase_is_split(joined_lines, phrase)
            for phrase in _THUMB_PROTECTED_PHRASES
        )
        packed_spec_penalty = 1 if re.search(r"\bHDMI\s+2\.[01]\s+4K\s+120HZ\b", joined_lines) else 0
        orphan = sum(len(line) <= 4 for line in candidate)
        word_count = len(" ".join(candidate).split())
        preferred_lines = 2 if word_count <= 6 else (3 if word_count <= 10 else 4)
        layout_score = (
            size * 10
            + int(width_ratio * 120)
            - bad_tail * 140
            - split_phrase * 1000
            - packed_spec_penalty * 520
            - orphan * 22
            - abs(len(candidate) - preferred_lines) * 140
            - max(0, max_w - text_w) // 8
        )
        layout = {
            "lines": candidate,
            "font": font,
            "boxes": boxes,
            "stroke": stroke,
            "font_size": size,
            "line_gap": line_gap,
            "line_slot_h": line_slot_h,
            "total_h": total_h,
            "widths": widths,
            "width_ratio": width_ratio,
            "score": layout_score,
        }
        if best_layout is None or layout_score > int(best_layout["score"]):
            best_layout = layout

    if best_layout is None:
        font = make_font(122)
        box = text_bbox(font, "BOX SAMSUNG DEX", max(6, int(122 * 0.075)))
        best_layout = {
            "lines": ["BOX SAMSUNG DEX"],
            "font": font,
            "boxes": [box],
            "stroke": max(6, int(122 * 0.075)),
            "font_size": 122,
            "line_gap": 10,
            "line_slot_h": box[3] - box[1],
            "total_h": box[3] - box[1],
            "widths": [box[2] - box[0]],
            "width_ratio": 1.0,
            "score": 0,
        }

    lines = list(best_layout["lines"])
    font = best_layout["font"]
    boxes = list(best_layout["boxes"])
    stroke_px = int(best_layout["stroke"])
    line_gap = int(best_layout["line_gap"])
    line_slot_h = int(best_layout["line_slot_h"])
    total_h = int(best_layout["total_h"])
    widths = list(best_layout["widths"])

    position = position if position in {"center", "lower", "higher"} else "center"
    position_factor = {"higher": 0.36, "center": 0.58, "lower": 0.78}[position]
    y0 = int(safe_top + max(0, (safe_h - total_h) * position_factor))
    green = "#20ff28"
    yellow = "#fff12b"
    stroke = "#050505"

    split_at = max(1, (len(lines) + 1) // 2)

    y_cursor = y0
    for i, (line, box) in enumerate(zip(lines, boxes)):
        color = green if i < split_at else yellow
        line_text = unicodedata.normalize("NFC", line)
        line_w = int(box[2] - box[0])
        line_h = int(box[3] - box[1])
        centered_x = int((out_w - line_w) / 2)
        x_text = max(safe_left, min(centered_x, safe_right - line_w)) - int(box[0])
        y_text = int(y_cursor + max(0, (line_slot_h - line_h) / 2)) - int(box[1])
        draw.text(
            (x_text, y_text),
            line_text,
            font=font,
            fill=color,
            stroke_width=stroke_px,
            stroke_fill=stroke,
        )
        y_cursor += line_slot_h + line_gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        canvas.convert("RGB").save(str(output_path), quality=96)
    except Exception as exc:
        raise RuntimeError(f"Không lưu được thumbnail: {output_path}") from exc
    return {
        "size_preset": size_preset,
        "line_mode": str(line_mode) if str(line_mode) in {"auto", "2", "3"} else "auto",
        "position": position,
        "lines": lines,
        "font_size_by_line": [int(best_layout["font_size"]) for _ in lines],
        "uniform_font_size": int(best_layout["font_size"]),
        "text_render_engine": "pillow_freetype_stroke",
        "font_file": font_file,
        "stroke_width": stroke_px,
        "line_gap": line_gap,
        "line_slot_h": line_slot_h,
        "layout_score": int(best_layout["score"]),
        "line_width_ratio": float(best_layout["width_ratio"]),
        "line_widths": [int(width) for width in widths],
        "safe_zone": {"left": safe_left, "top": safe_top, "right": safe_right, "bottom": safe_bottom},
    }


# ── AI Script Generation Prompt ───────────────────────────────────────────

SCRIPT_SYSTEM_PROMPT = """Bạn là AI chuyên tạo script video ngắn TikTok từ bài báo.
Tạo script JSON cho video ngắn TikTok, mặc định 6-8 scenes: 1 hook + body + 1 outro.

QUY TẮC NỘI DUNG:
- voiceText: tiếng Việt tự nhiên, đủ ý nhưng không dài dòng
- Hook bắt đầu bằng số, câu hỏi hoặc thông tin gây tò mò
- KHÔNG dùng "Xin chào", "Hôm nay chúng ta"

QUY TẮC FORMAT — QUAN TRỌNG, tuân thủ tuyệt đối:
- hook.headline: tối đa 40 ký tự
- hook.subhead: tối đa 40 ký tự
- stat-hero.value: tối đa 20 ký tự, label: tối đa 40 ký tự
- feature-list.title: tối đa 40 ký tự, mỗi bullet: tối đa 50 ký tự, tối đa 4 bullets
- callout.statement: tối đa 80 ký tự, tag: tối đa 20 ký tự
- templateData chỉ được tóm tắt trực tiếp từ voiceText của chính scene đó; không thêm fact, claim hoặc ví dụ khác.
- Nếu không chắc templateData, vẫn ưu tiên voiceText đúng sự thật; engine sẽ tự đồng bộ visual từ voiceText.
- Nếu field quá dài, hãy VIẾT LẠI NGẮN HƠN; không được cắt ngang từ/câu.
- outro.ctaTop: tối đa 30 ký tự, channelName: tối đa 30 ký tự, source: tối đa 40 ký tự
- comparison.left và right PHẢI có đủ 3 field: label (max30), value (max20), color ("cyan" hoặc "purple")

OUTPUT: Chỉ JSON thuần, không markdown, không giải thích.

FORMAT CHUẨN (copy chính xác cấu trúc này):
{
  "version": "1.0",
  "metadata": {
    "title": "tên video ngắn",
    "source": {"url": "{{URL}}", "domain": "{{DOMAIN}}", "image": null},
    "channel": "{{CHANNEL}}"
  },
  "voice": {"provider": "lucylab", "voiceId": "${VIETNAMESE_VOICEID}", "speed": 1.0},
  "scenes": [
    {"id":"hook","type":"hook","voiceText":"câu hook hấp dẫn, đúng nhịp dựng",
     "templateData":{"template":"hook","headline":"TIÊU ĐỀ NGẮN <40KÝ","subhead":"phụ đề <40 ký","kenBurns":"zoom-in"}},

    {"id":"body-1","type":"body","voiceText":"nội dung scene 1",
     "templateData":{"template":"stat-hero","value":"99%","label":"mô tả <40 ký","context":"ngữ cảnh <50 ký"}},

    {"id":"body-2","type":"body","voiceText":"nội dung scene 2",
     "templateData":{"template":"comparison",
       "left":{"label":"Trước <30ký","value":"x <20ký","color":"cyan"},
       "right":{"label":"Sau <30ký","value":"y <20ký","color":"purple","winner":true}}},

    {"id":"body-3","type":"body","voiceText":"nội dung scene 3",
     "templateData":{"template":"feature-list","title":"Tiêu đề <40ký","bullets":["điểm 1 <50ký","điểm 2","điểm 3"]}},

    {"id":"body-4","type":"body","voiceText":"nội dung scene 4",
     "templateData":{"template":"callout","statement":"quote quan trọng <80 ký tự","tag":"hashtag<20ký"}},

    {"id":"outro","type":"outro","voiceText":"lời kết kêu gọi follow",
     "templateData":{"template":"outro","ctaTop":"Theo dõi ngay","channelName":"{{CHANNEL}}","source":"{{DOMAIN}}"}}
  ]
}"""


SCRIPT_PRESET_GUIDES = {
    "classic": "",
    "ai_news_fast": """

PRESET ĐANG CHỌN: AI NEWS NHANH.
Các rule dưới đây override rule tổng quát nếu có xung đột:
- Tạo 7-9 scenes ở nhịp standard; nếu nhịp dynamic bật thì tạo 10-12 scenes.
- metadata.title phải là title TikTok ngắn dạng: "Entity: điểm mới gây tò mò".
- hook.headline nên tách được thành 2 dòng: entity/công cụ/công ty + claim gây tò mò.
- Body đi đúng nhịp: cái gì mới → vì sao đáng chú ý → ai dùng được → rủi ro/giới hạn → kết luận nhanh.
- Nếu bài là profile founder/công ty, body phải đi theo nhịp: nhân vật → quyết định khác thường → sản phẩm/công nghệ → số liệu traction → giới hạn/rủi ro. Không biến cả video thành chuyện đời tư/lifestyle.
- Chi tiết đời tư kỳ lạ chỉ dùng làm hook hoặc một điểm tương phản; không dùng quá 1 body scene nếu nó không phải luận điểm chính của bài.
- Mỗi scene body phải trả lời được "vì sao điều này quan trọng?" thay vì chỉ kể một fact gây sốc.
- Mỗi voiceText mở bằng một câu ngắn 6-12 từ có thể dùng làm caption đáy.
- Ưu tiên số liệu, tên công cụ, tên công ty, repo, model, API, benchmark nếu có trong bài.
- Không tự nâng cấp sự kiện: nếu bài nói Olympic Vật lý thì không đổi thành Olympic Toán; nếu bài nói nạn nhân crypto thì không tự đổi thành tỷ phú crypto.
- Outro ngắn, kêu gọi follow tin AI/công nghệ; không dài dòng.
""",
    "github_repo_story": """

PRESET ĐANG CHỌN: GITHUB REPO STORY.
Các rule dưới đây override rule tổng quát nếu có xung đột:
- Tạo 7-9 scenes ở nhịp standard; nếu nhịp dynamic bật thì tạo 10-12 scenes.
- metadata.title dạng: "Tên repo/công ty: con số hoặc lợi ích lạ".
- Hook phải có repo/tên công cụ + star/download/claim nổi bật nếu nội dung có.
- Body đi theo nhịp: repo làm gì → vì sao tăng nhanh → tính năng đáng dùng → cách ai dùng được → caveat/rủi ro.
- Dùng template stat-hero cho star/con số, feature-list cho tính năng, callout cho caveat.
- Mỗi voiceText mở bằng một câu ngắn 6-12 từ có thể dùng làm caption đáy.
""",
    "research_explainer": """

PRESET ĐANG CHỌN: RESEARCH EXPLAINER.
Các rule dưới đây override rule tổng quát nếu có xung đột:
- Tạo 8-10 scenes ở nhịp standard; nếu nhịp dynamic bật thì tạo 11-14 scenes.
- metadata.title dạng: "Tên paper/model: kết quả ngược trực giác".
- Hook nêu kết quả mạnh nhất, không mở bài vòng vo.
- Body đi theo nhịp: bài toán → phương pháp → kết quả → vì sao đáng tin/đáng nghi → ứng dụng → giới hạn.
- Ưu tiên giải thích dễ hiểu, không dùng thuật ngữ mà không giải nghĩa.
- Mỗi voiceText mở bằng một câu ngắn 6-12 từ có thể dùng làm caption đáy.
""",
}

EDITING_PACE_GUIDES = {
    "standard": """

NHỊP DỰNG: STANDARD.
- Giữ nhịp cũ: mỗi voiceText khoảng 18-32 từ.
- Ưu tiên ít scene hơn, mỗi scene giải thích trọn một ý.
""",
    "dynamic": """

NHỊP DỰNG: DYNAMIC 3-5 GIÂY.
- Ưu tiên nhiều scene ngắn, mỗi voiceText khoảng 6-16 từ.
- Mỗi scene chỉ nêu một ý rõ ràng, tránh ghép 2-3 ý vào cùng scene.
- Câu đầu mỗi scene nên là một caption ngắn, dễ đọc trong 1 nhịp.
- Nếu bài có nhiều số liệu, tách từng số liệu quan trọng thành scene riêng.
- Tổng video nên gọn hơn nhịp cũ: tin nhanh khoảng 50-75 giây, explainer khoảng 70-100 giây.
""",
}


# ── Worker 1: Fetch + AI Generate Script ─────────────────────────────────

class AutoScriptWorker(QThread):
    """Fetch URL + gọi Claude API → emit script_dict + script_path."""
    progress = pyqtSignal(str)          # status message
    finished = pyqtSignal(str)          # script.json path
    error    = pyqtSignal(str)

    # Engine output dir — chỉnh lại nếu cần
    ENGINE_OUTPUT = get_auto_video_engine_dir() / "output"

    def __init__(self, url_or_text: str, parent=None):
        super().__init__(parent)
        self.input = url_or_text.strip()
        self._cancelled = False

    def _is_cancelled(self) -> bool:
        return self._cancelled or self.isInterruptionRequested()

    def run(self):
        try:
            settings = load_settings()
            self.ENGINE_OUTPUT = get_auto_video_engine_dir(settings) / "output"
            if self._is_cancelled():
                self.error.emit("Đã dừng")
                return

            # 1. Fetch article
            if self.input.startswith("http"):
                self.progress.emit("Đang tải bài báo…")
                article = self._fetch(self.input)
            else:
                lines = self.input.split("\\n")
                article = {
                    "url": "", "domain": "", "image": None,
                    "title": lines[0][:120] if lines else "Video",
                    "text": self.input,
                }

            if not article["text"]:
                self.error.emit("Không đọc được nội dung. Thử paste trực tiếp.")
                return

            # 2. Generate script via selected AI provider
            env = _read_engine_env(settings)
            provider_hint = env.get("SCRIPT_AI_PROVIDER", "claude").strip().lower() or "claude"
            self.progress.emit(f"AI đang viết script… ({self._provider_label(provider_hint)} đang chọn)")
            if self._is_cancelled():
                self.error.emit("Đã dừng")
                return
            raw = self._generate(article, settings)

            # 3. Build script.json
            self.progress.emit("Đang tạo script.json…")
            if self._is_cancelled():
                self.error.emit("Đã dừng")
                return
            script = self._build_script(raw, article, settings)
            path   = self._write_script(script, raw.get("title", article["title"]))

            self.finished.emit(path)

        except ValueError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def _fetch(self, url: str) -> dict:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=15)
        resp.raise_for_status()
        soup   = BeautifulSoup(resp.text, "html.parser")
        domain = urlparse(url).netloc.replace("www.", "")

        title = ""
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image = og_img["content"].strip()

        body = ""
        for tag in ["article", "main"]:
            node = soup.find(tag)
            if node:
                body = re.sub(r"\\s+", " ", node.get_text(" ", strip=True))
                if len(body) > 200:
                    break
        if not body:
            body = re.sub(r"\\s+", " ", " ".join(
                p.get_text(" ", strip=True) for p in soup.find_all("p")
            ))

        return {"url": url, "domain": domain, "title": title,
                "text": body[:6000], "image": image}

    def _generate(self, article: dict, settings: dict) -> dict:
        """Use the selected script provider; fallback only when explicitly enabled."""
        errors = []
        engine_env = _read_engine_env(settings)
        claude_key = _configured_ai_key(settings, "CLAUDE_API_KEY", "claude_api_key")
        ds_key = _configured_ai_key(settings, "DEEPSEEK_API_KEY", "ds_api_key")
        gemini_key = _configured_ai_key(settings, "GEMINI_API_KEY", "gemini_api_key")

        selected = engine_env.get("SCRIPT_AI_PROVIDER", "claude").strip().lower()
        if selected not in ("deepseek", "gemini", "claude"):
            selected = "claude"
        fallback_enabled = (
            engine_env.get("SCRIPT_AI_FALLBACK", "true").strip().lower()
            in ("1", "true", "yes", "on")
        )
        order = (
            [selected] + [p for p in ("claude", "deepseek", "gemini") if p != selected]
            if fallback_enabled
            else [selected]
        )
        selected_label = self._provider_label(selected)
        for provider in order:
            if self._is_cancelled():
                raise ValueError("Đã dừng")
            try:
                if provider == "deepseek" and ds_key:
                    prefix = f"fallback từ {selected_label} → " if provider != selected else ""
                    self.progress.emit(f"AI đang viết script… ({prefix}DeepSeek · deepseek-chat)")
                    return self._generate_deepseek(article, ds_key, engine_env)
                if provider == "gemini" and gemini_key:
                    model = engine_env.get("GEMINI_TEXT_MODEL", "").strip() or "gemini-2.5-flash"
                    prefix = f"fallback từ {selected_label} → " if provider != selected else ""
                    self.progress.emit(f"AI đang viết script… ({prefix}Gemini · {model})")
                    return self._generate_gemini(
                        article,
                        gemini_key,
                        engine_env,
                        model,
                    )
                if provider == "claude" and claude_key:
                    prefix = f"fallback từ {selected_label} → " if provider != selected else ""
                    self.progress.emit(f"AI đang viết script… ({prefix}Claude · {self._claude_model(settings, engine_env)})")
                    return self._generate_claude(article, settings, claude_key, engine_env)

                if provider == selected:
                    env_path = get_auto_video_env_local(settings)
                    raise ValueError(
                        f"Chưa có API key cho {self._provider_label(provider)} trong "
                        f"{env_path}."
                    )
            except Exception as e:
                label = {"deepseek": "DeepSeek", "gemini": "Gemini", "claude": "Claude"}.get(provider, provider)
                if provider == "deepseek" and ("401" in str(e) or "403" in str(e)):
                    errors.append(f"{label}: key không hợp lệ hoặc chưa có quyền")
                else:
                    errors.append(f"{label}: {e}")
                if fallback_enabled:
                    self.progress.emit(f"{label} lỗi — thử provider khác…")
                else:
                    raise ValueError(
                        f"{label} lỗi, không fallback sang provider khác vì SCRIPT_AI_FALLBACK=false.\n{e}"
                    ) from e

        # ── Tất cả fail ──────────────────────────────────────────────────
        if not errors:
            raise ValueError(
                "Chưa có API key nào.\n"
                "Vào Settings → API để nhập key."
            )
        raise ValueError("Tất cả AI providers đều lỗi:\n" + "\n".join(errors))

    def cancel(self):
        self._cancelled = True

    def _script_preset(self, engine_env: dict) -> str:
        preset = engine_env.get("AUTO_VIDEO_SCRIPT_PRESET", "ai_news_fast").strip().lower()
        return preset if preset in SCRIPT_PRESET_GUIDES else "ai_news_fast"

    def _provider_label(self, provider: str) -> str:
        return {"deepseek": "DeepSeek", "gemini": "Gemini", "claude": "Claude"}.get(provider, provider or "unknown")

    def _system_prompt(self, article: dict, engine_env: dict) -> str:
        channel = engine_env.get("TIKTOK_DISPLAY_NAME", "Hedra Central")
        preset = self._script_preset(engine_env)
        guide = SCRIPT_PRESET_GUIDES.get(preset, "")
        pace = engine_env.get("AUTO_VIDEO_EDITING_PACE", "dynamic").strip().lower()
        pace_guide = EDITING_PACE_GUIDES.get(pace, EDITING_PACE_GUIDES["dynamic"])
        return (
            SCRIPT_SYSTEM_PROMPT
            .replace("{{URL}}", article.get("url", ""))
            .replace("{{DOMAIN}}", article.get("domain", ""))
            .replace("{{CHANNEL}}", channel)
            + guide
            + pace_guide
        )

    def _claude_model(self, settings: dict, engine_env: dict) -> str:
        model = (
            engine_env.get("CLAUDE_MODEL", "").strip()
            or settings.get("claude_model", "").strip()
        )
        return RECOMMENDED_CLAUDE_MODEL if model in LEGACY_DEFAULT_CLAUDE_MODELS else model

    def _generate_claude(self, article: dict, settings: dict, api_key: str, engine_env: dict) -> dict:
        import anthropic
        system = self._system_prompt(article, engine_env)
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=self._claude_model(settings, engine_env),
            max_tokens=3072, system=system,
            messages=[{"role": "user", "content":
                f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video."}],
        )
        return self._parse_json(resp.content[0].text.strip())

    def _generate_deepseek(self, article: dict, api_key: str, engine_env: dict) -> dict:
        system = self._system_prompt(article, engine_env)
        payload = {
            "model": "deepseek-chat",
            "max_tokens": 3072,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content":
                    f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video."},
            ],
        }
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        resp.raise_for_status()
        return self._parse_json(resp.json()["choices"][0]["message"]["content"].strip())

    def _generate_gemini(self, article: dict, api_key: str, engine_env: dict, model: str) -> dict:
        system = self._system_prompt(article, engine_env)
        prompt  = (f"{system}\n\n"
                   f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video.")
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        resp.raise_for_status()
        return self._parse_json(resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip())

    def _parse_json(self, raw: str) -> dict:
        """Parse JSON từ response — handle markdown code block."""
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    # ── Zod field limits (must match script-schema.ts exactly) ──────────
    _ZOD_LIMITS = {
        # hook
        ("hook", "headline"):               40,
        ("hook", "subhead"):                40,
        # stat-hero
        ("stat-hero", "value"):             20,
        ("stat-hero", "label"):             40,
        ("stat-hero", "context"):           50,
        # feature-list
        ("feature-list", "title"):          40,
        # callout
        ("callout", "statement"):           80,
        ("callout", "tag"):                 20,
        # outro
        ("outro", "ctaTop"):                30,
        ("outro", "channelName"):           30,
        ("outro", "source"):                40,
        # comparison sides
        ("comparison", "left_label"):       30,
        ("comparison", "left_value"):       20,
        ("comparison", "right_label"):      30,
        ("comparison", "right_value"):      20,
    }
    _BULLET_MAX_LEN   = 50
    _BULLET_MAX_COUNT = 4

    _DANGLING_TAIL_WORDS = {
        "và", "của", "là", "từ", "vào", "khi", "để", "bị", "với", "theo",
        "không", "chưa", "đang", "sẽ", "có", "một", "này", "đó",
    }

    @staticmethod
    def _strip_vietnamese(text: str) -> str:
        import unicodedata
        normalized = unicodedata.normalize("NFD", text)
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return normalized.replace("đ", "d").replace("Đ", "D")

    def _trim_to_limit(self, value, limit: int, sentence: bool = False):
        """Trim overlong template text without leaving broken words like 'Yan không d'."""
        if not isinstance(value, str) or len(value) <= limit:
            return value

        cut = value[:limit].rstrip()

        if sentence:
            punctuation_positions = [cut.rfind(p) for p in ".!?:;…"]
            punctuation = max(punctuation_positions)
            if punctuation >= int(limit * 0.55):
                return cut[:punctuation + 1].strip()

        space = cut.rfind(" ")
        if space >= max(12, int(limit * 0.45)):
            cut = cut[:space].rstrip()

        cut = cut.rstrip(" ,;:-–—")
        words = cut.split()
        while words:
            tail = re.sub(r"[^a-z0-9]", "", self._strip_vietnamese(words[-1]).lower())
            if (len(tail) == 1 and tail.isalpha()) or tail in self._DANGLING_TAIL_WORDS:
                words.pop()
                continue
            break
        cut = " ".join(words).rstrip(" ,;:-–—")

        if sentence and cut and cut[-1] not in ".!?:;…":
            cut = f"{cut}."
        return cut[:limit].rstrip()

    def _truncate_scene(self, scene: dict) -> dict:
        """Trim templateData fields to Zod limits — rewrite-style trim, not hard cut."""
        td = scene.get("templateData", {})
        tpl = td.get("template", "")

        for (t, field), limit in self._ZOD_LIMITS.items():
            if t != tpl:
                continue
            sentence_field = tpl == "callout" and field == "statement"
            if field.startswith("left_") or field.startswith("right_"):
                side, key = field.split("_", 1)
                if side in td and isinstance(td[side], dict):
                    td[side][key] = self._trim_to_limit(td[side].get(key, ""), limit)
            else:
                if field in td:
                    td[field] = self._trim_to_limit(td[field], limit, sentence_field)

        # feature-list bullets
        if tpl == "feature-list" and "bullets" in td:
            bullets = td["bullets"]
            if isinstance(bullets, list):
                td["bullets"] = [self._trim_to_limit(b, self._BULLET_MAX_LEN) for b in bullets[:self._BULLET_MAX_COUNT]]

        scene["templateData"] = td
        return scene

    def _build_script(self, raw: dict, article: dict, settings: dict) -> dict:
        # Fix image: chỉ giữ nếu là https:// URL hợp lệ
        img = article.get("image")
        if img and not re.match(r'^https?://', img or ''):
            img = None

        # Fix voice from engine .env.local (single source of truth)
        env = _read_engine_env(settings)
        env_path = get_auto_video_env_local(settings)
        provider = env.get("TTS_PROVIDER", "genmax").strip() or "genmax"
        if provider not in {"genmax", "elevenlabs", "lucylab"}:
            provider = "genmax"
        voice_key_map = {
            "lucylab": "VIETNAMESE_VOICEID",
            "elevenlabs": "ELEVENLABS_VOICE_ID",
            "genmax": "GENMAX_VOICE_ID",
        }
        voice_key = voice_key_map.get(provider)
        if not voice_key:
            raise ValueError(
                f"TTS_PROVIDER không hợp lệ trong {env_path}: {provider}"
            )
        voice_id = env.get(voice_key, "").strip()
        if not voice_id:
            raise ValueError(
                f"Thiếu {voice_key} trong {env_path}.\n"
                "Vào Settings → Auto Video để nhập cấu hình engine."
            )

        if "voice" in raw:
            raw["voice"]["provider"] = provider
            raw["voice"]["voiceId"] = voice_id
        else:
            raw["voice"] = {"provider": provider, "voiceId": voice_id, "speed": 1.0}

        # Fix metadata.source.image
        if "metadata" not in raw:
            raw["metadata"] = {}
        raw["metadata"]["channel"] = env.get("TIKTOK_DISPLAY_NAME", raw["metadata"].get("channel", "Hedra Central"))
        if "source" not in raw["metadata"]:
            raw["metadata"]["source"] = {}
        raw["metadata"]["source"]["image"] = img

        # Truncate tất cả fields về đúng Zod limits
        raw["scenes"] = [self._truncate_scene(s) for s in raw.get("scenes", [])]

        return raw

    def _write_script(self, script: dict, title: str) -> str:
        slug    = _make_slug(title)
        out_dir = self.ENGINE_OUTPUT / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "script.json"
        path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)


# ── Worker 2: Run Engine Pipeline ────────────────────────────────────────

class AutoVideoEngineWorker(QThread):
    """Chạy npm engine từ script.json → video.mp4."""
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)   # 0-100
    finished = pyqtSignal(str)   # video path
    error    = pyqtSignal(str)

    def __init__(self, script_path: str, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self._cancelled  = False
        self._proc: subprocess.Popen | None = None
        self.ENGINE_DIR = get_auto_video_engine_dir(load_settings())

    @staticmethod
    def _overall_progress(step: int, total: int, step_pct: int = 0) -> int:
        """Map engine step progress to an overall 0-100 value."""
        if total <= 0:
            return 0
        step_pct = max(0, min(100, step_pct))
        done_before = max(0, step - 1)
        return max(0, min(99, int(((done_before + step_pct / 100) / total) * 100)))

    @staticmethod
    def _hyperframes_pct(line: str) -> int | None:
        """Parse Hyperframes render progress, e.g. '44% Capturing frame 660/1531'."""
        m = re.search(r"(\d{1,3})%\s+.*?\bframe\s+\d+/\d+", line, re.I)
        if not m:
            return None
        return max(0, min(100, int(m.group(1))))

    @staticmethod
    def _shell_path() -> str:
        """Lấy PATH đầy đủ từ login shell — fix lỗi GUI app thiếu node/npx/ffmpeg."""
        import os
        import sys
        if sys.platform == "win32":
            return os.environ.get("PATH", "")
        import subprocess as _sp
        try:
            r = _sp.run(["/bin/zsh", "-l", "-c", "echo $PATH"],
                        capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        return os.environ.get("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin")

    @staticmethod
    def _media_duration(path: Path) -> float | None:
        import subprocess as _sp
        if not path.exists():
            return None
        try:
            r = _sp.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                return None
            return float((r.stdout or "").strip())
        except Exception:
            return None

    @classmethod
    def _partial_video_detail(cls, output_dir: Path) -> str:
        voice_sec = cls._media_duration(output_dir / "voice.mp3")
        candidates = sorted(output_dir.glob("video*.mp4"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        if not candidates:
            return ""
        best = candidates[0]
        video_sec = cls._media_duration(best)
        if video_sec is None:
            return ""
        if voice_sec and video_sec + 0.75 < voice_sec:
            return (
                f"Video render bị cụt: {video_sec:.2f}s / audio {voice_sec:.2f}s.\n"
                f"File partial: {best}"
            )
        if best.name != "video.mp4":
            return f"Render tạo file tạm nhưng chưa hoàn tất: {best} ({video_sec:.2f}s)"
        return ""

    def run(self):
        import os
        import subprocess
        tsx_bin = self.ENGINE_DIR / "node_modules" / ".bin" / "tsx"
        if not tsx_bin.exists() and (self.ENGINE_DIR / "node_modules" / ".bin" / "tsx.cmd").exists():
            tsx_bin = self.ENGINE_DIR / "node_modules" / ".bin" / "tsx.cmd"
        if not tsx_bin.exists():
            self.error.emit(
                f"Không tìm thấy tsx.\n"
                f"Chạy: cd {self.ENGINE_DIR} && npm install\n"
                f"Có thể set HEDRA_AUTO_VIDEO_ENGINE_DIR nếu engine nằm ở thư mục khác."
            )
            return
        cmd = [str(tsx_bin), "src/cli.ts", self.script_path]

        # Toàn bộ config (TTS provider, API keys, voice ID...) đọc từ .env.local
        # của Auto-Create-Video — không inject thêm gì. Hedra Studio chỉ là UI wrapper.
        run_env = {**os.environ, "PATH": self._shell_path()}
        try:
            tail_lines: list[str] = []
            proc = subprocess.Popen(
                cmd, cwd=str(self.ENGINE_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=run_env,
                start_new_session=(os.name != "nt"),
            )
            self._proc = proc
            for line in proc.stdout:
                if self._cancelled:
                    _terminate_process(proc)
                    self._proc = None
                    self.error.emit("Đã dừng")
                    return
                line = line.rstrip()
                if line:
                    tail_lines.append(line)
                    if len(tail_lines) > 50:
                        tail_lines.pop(0)
                self.log_line.emit(line)
                m = re.search(r"\[(\d+)/(\d+)\]", line)
                if m:
                    n, t = int(m.group(1)), int(m.group(2))
                    self.progress.emit(self._overall_progress(n, t, 0))
                hf_pct = self._hyperframes_pct(line)
                if hf_pct is not None:
                    self.progress.emit(self._overall_progress(7, 8, hf_pct))

            proc.wait()
            self._proc = None
            if proc.returncode != 0:
                output_dir = Path(self.script_path).parent
                pieces = [f"Engine lỗi (exit {proc.returncode})"]
                partial = self._partial_video_detail(output_dir)
                if partial:
                    pieces.append(partial)
                if tail_lines:
                    pieces.append("Log cuối:\n" + "\n".join(tail_lines[-40:]))
                self.error.emit("\n\n".join(pieces))
                return

            video = Path(self.script_path).parent / "video.mp4"
            self.progress.emit(100)
            self.finished.emit(str(video) if video.exists() else "")

        except FileNotFoundError:
            self.error.emit(
                f"Không tìm thấy engine. Chạy: cd {self.ENGINE_DIR} && npm install"
            )
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            _terminate_process(proc, wait=False)


# ── Worker 3: One-shot edit analysis ─────────────────────────────────────

class OneShotAnalyzeWorker(QThread):
    """Prepare a one-shot video edit plan: audio extract, transcript/silence cuts, thumbnail frame."""
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)  # cuts.json path
    error = pyqtSignal(str)

    def __init__(self, video_path: str, settings: dict, options: dict | None = None, parent=None):
        super().__init__(parent)
        self.video_path = Path(video_path)
        self.settings = settings or {}
        self.options = options or {}
        self._cancelled = False

    def _log(self, line: str) -> None:
        self.log_line.emit(line)

    def _is_cancelled(self) -> bool:
        return self._cancelled or self.isInterruptionRequested()

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise RuntimeError("Đã dừng")

    def run(self):
        try:
            if not self.video_path.exists():
                raise FileNotFoundError(f"Không tìm thấy video: {self.video_path}")
            self._raise_if_cancelled()
            self.progress.emit(4)
            title = self.video_path.stem
            out_root = Path(self.settings.get("output_dir") or DEFAULT_OUT)
            today = datetime.now().strftime("%Y-%m-%d")
            out_dir = out_root / "one-shot" / "_debug" / today / _make_one_shot_job_slug(title)
            out_dir.mkdir(parents=True, exist_ok=True)
            copy_source = bool(self.options.get("copy_source", True))
            source_copy = out_dir / self.video_path.name
            if copy_source:
                if self.video_path.resolve() != source_copy.resolve():
                    shutil.copy2(self.video_path, source_copy)
                self._log(f"[1/5] Copy source: {source_copy.name}")
            else:
                source_copy = self.video_path
                self._log(f"[1/5] Dùng source gốc: {source_copy.name}")

            duration = _ffprobe_duration(source_copy)
            self._raise_if_cancelled()
            self.progress.emit(16)
            self._log(f"[2/5] Duration: {duration:.2f}s")

            audio_path = out_dir / "source.wav"
            audio_available = False
            transcript_mode = "silence_fallback"
            transcript_detail = ""
            r = _run_media_cmd([
                "ffmpeg", "-y", "-i", str(source_copy),
                "-vn", "-ac", "1", "-ar", "16000", str(audio_path),
            ], timeout=600, is_cancelled=self._is_cancelled)
            self._raise_if_cancelled()
            if r.returncode != 0:
                self._log("Audio: không tách được hoặc video không có audio rõ — vẫn render bằng source gốc")
                audio_path = None
                transcript_segments = []
                transcript_mode = "no_audio"
                transcript_detail = (r.stderr or r.stdout or "no audio").strip()[-500:]
            else:
                audio_available = True
                self._log("[3/5] Extract audio xong")
            self.progress.emit(30)

            if audio_available and audio_path is not None:
                transcript_segments = self._transcribe_local(audio_path, out_dir)
                self._raise_if_cancelled()
                whisper_mode = getattr(self, "_last_transcript_mode", "")
                transcript_detail = getattr(self, "_last_transcript_detail", "")
                if transcript_segments:
                    transcript_mode = "whisper_no_vad" if whisper_mode == "whisper_no_vad" else "whisper"
                    _write_srt(transcript_segments, out_dir / "transcript.srt")
                    label = "Transcript: dùng Whisper local không VAD" if transcript_mode == "whisper_no_vad" else "Transcript: dùng Whisper local"
                    self._log(f"{label} · {len(transcript_segments)} segments")
                elif transcript_segments == []:
                    transcript_mode = "silence_fallback"
                    self._log("Transcript: không nhận ra lời nói rõ, fallback khoảng lặng vẫn render được")
                else:
                    transcript_mode = "silence_fallback"
                    detail = f" ({transcript_detail})" if transcript_detail else ""
                    prefix = "Whisper lỗi" if whisper_mode == "whisper_error" else "Transcript"
                    self._log(f"{prefix}: fallback khoảng lặng, vẫn render được{detail}")
                    transcript_segments = []

            cut_video = bool(self.options.get("cut_video", True))
            if cut_video and audio_available and audio_path is not None:
                silence_cuts = self._detect_silence(audio_path, duration)
                self._raise_if_cancelled()
                ai_cuts = self._gemini_cut_suggestions(transcript_segments, duration) if transcript_segments else []
                cuts = self._normalize_cut_candidates(ai_cuts + silence_cuts, duration)
            else:
                cuts = []
            self._raise_if_cancelled()
            self.progress.emit(68)
            if cut_video:
                self._log(f"[4/5] Đề xuất {len(cuts)} đoạn cần review")
            else:
                self._log("[4/5] Cut đang tắt — bỏ qua đề xuất cắt")

            keep_debug_audio = bool(self.options.get("keep_debug_audio", False))
            audio_debug_removed = False
            if audio_path is not None and Path(audio_path).exists() and not keep_debug_audio:
                try:
                    Path(audio_path).unlink()
                    audio_debug_removed = True
                    self._log("Đã xoá audio debug sau khi tạo transcript")
                    audio_path = None
                except Exception:
                    pass

            frame_path = out_dir / "thumbnail-frame.png"
            frame_time = min(max(duration * 0.32, 0.5), max(duration - 0.5, 0.5))
            r = _run_media_cmd([
                "ffmpeg", "-y", "-ss", f"{frame_time:.3f}",
                "-i", str(source_copy), "-frames:v", "1", str(frame_path),
            ], timeout=120, is_cancelled=self._is_cancelled)
            self._raise_if_cancelled()
            if r.returncode != 0 or not frame_path.exists():
                self._log("Không extract được frame thumbnail, sẽ thử frame đầu")
                _run_media_cmd([
                    "ffmpeg", "-y", "-i", str(source_copy),
                    "-frames:v", "1", str(frame_path),
                ], timeout=120, is_cancelled=self._is_cancelled)
            self._raise_if_cancelled()

            lut_src = self.options.get("lut_path") or self.settings.get("one_shot_lut_path") or _default_dji_lut_path()
            lut_path = _copy_lut_to_app_data(lut_src) if lut_src else ""
            title_provider_state = self.options.get("title_provider_state") if isinstance(self.options, dict) else None
            if not isinstance(title_provider_state, dict):
                title_provider_state = {}
            thumb_suggestion, thumb_source, ai_costs = _build_thumbnail_title(
                self.settings,
                transcript_segments,
                title,
                self._log,
                title_provider_state,
                str(self.options.get("thumbnail_title_mode") or self.settings.get("one_shot_thumbnail_title_mode") or "expert"),
            )
            thumb_quality = _thumbnail_title_quality(thumb_suggestion, title, transcript_segments)
            ai_metadata = title_provider_state.get("ai_metadata") if isinstance(title_provider_state.get("ai_metadata"), dict) else {}
            metadata_plan = _one_shot_metadata_plan(thumb_suggestion, title, transcript_segments, self.settings, ai_metadata)
            self._raise_if_cancelled()
            ai_cost_total = _sum_ai_costs(ai_costs)
            if ai_costs:
                self._log(
                    f"AI title cost: ${ai_cost_total['estimated_usd']:.6f} "
                    f"~ {ai_cost_total['estimated_vnd']}đ"
                )

            plan = {
                "version": "1.0",
                "pipeline_version": ONE_SHOT_PIPELINE_VERSION,
                "industry": str(self.options.get("industry") or self.settings.get("one_shot_industry") or "tech"),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "source_video": str(source_copy),
                "original_video": str(self.video_path),
                "output_dir": str(out_dir),
                "duration": duration,
                "audio_wav": str(audio_path) if audio_path else "",
                "audio_debug_removed": audio_debug_removed,
                "transcript_mode": transcript_mode,
                "transcript_detail": transcript_detail,
                "transcript_srt": str(out_dir / "transcript.srt") if transcript_segments else "",
                "thumbnail_frame": str(frame_path) if frame_path.exists() else "",
                "lut_path": lut_path,
                "cut_video": cut_video,
                "thumbnail_title_suggestion": thumb_suggestion,
                "thumbnail_title_source": thumb_source,
                "thumbnail_title_quality": thumb_quality,
                "title_candidates": [thumb_suggestion] if thumb_suggestion else [],
                "title_evidence": {
                    "source_title": title,
                    "early_transcript": _early_thumbnail_context(transcript_segments),
                    "agent_roles": [
                        "Transcript Analyst",
                        "Title Strategist",
                        "Terminology QA",
                        "Metadata Publisher",
                    ],
                },
                "title_quality": thumb_quality,
                "thumbnail_spec": {
                    "template": "boxphonefarm_grid",
                    "text_fill": ["#20ff28", "#fff12b"],
                    "outline": "#050505",
                    "lines": "auto_2_to_5",
                    "protected_phrases": list(_THUMB_PROTECTED_PHRASES),
                },
                "thumbnail_preview": "",
                "ai_metadata_suggestion": ai_metadata,
                "metadata_plan": metadata_plan,
                "ai_costs": ai_costs,
                "ai_cost_total": ai_cost_total,
                "cuts": cuts,
                "transcript": transcript_segments[:200],
            }
            plan_path = out_dir / "cuts.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            self.progress.emit(100)
            self._log("[5/5] Plan xong")
            self.finished.emit(str(plan_path))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def _transcribe_local(self, audio_path: Path, out_dir: Path) -> list[dict] | None:
        self._last_transcript_mode = "silence_fallback"
        self._last_transcript_detail = ""
        try:
            status = whisper_runtime_status(self.settings)
            if status.get("status") not in {"ready", "missing_vad_asset"}:
                self._last_transcript_mode = str(status.get("status") or "missing_package")
                self._last_transcript_detail = str(status.get("detail") or status.get("label") or "")
                return None
        except Exception as e:
            self._last_transcript_mode = "missing_package"
            self._last_transcript_detail = str(e)[:300]
            return None
        model_size = str(self.options.get("whisper_model") or self.settings.get("one_shot_whisper_model", "small") or "small")
        try:
            model, loaded_model = _load_whisper_model(model_size, self._log)
            used_vad = True
            try:
                segments = _transcribe_with_whisper(model, audio_path, vad_filter=True)
            except Exception as vad_error:
                if not _is_whisper_vad_error(vad_error):
                    raise
                self._log("Whisper VAD lỗi, retry không VAD")
                used_vad = False
                segments = _transcribe_with_whisper(model, audio_path, vad_filter=False)
            result = []
            for seg in segments:
                text = re.sub(r"\s+", " ", getattr(seg, "text", "")).strip()
                if text:
                    result.append({
                        "start": float(getattr(seg, "start", 0.0)),
                        "end": float(getattr(seg, "end", 0.0)),
                        "text": text,
                    })
            (out_dir / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            self._last_transcript_mode = ("whisper" if used_vad else "whisper_no_vad") if result else "no_speech"
            self._last_transcript_detail = f"model={loaded_model}"
            return result
        except Exception as e:
            self._last_transcript_mode = "whisper_error"
            self._last_transcript_detail = str(e)[:300]
            return None

    def _detect_silence(self, audio_path: Path, duration: float) -> list[dict]:
        r = _run_media_cmd([
            "ffmpeg", "-hide_banner", "-i", str(audio_path),
            "-af", "silencedetect=noise=-35dB:d=0.55",
            "-f", "null", "-"
        ], timeout=600, is_cancelled=self._is_cancelled)
        log = (r.stderr or "") + "\n" + (r.stdout or "")
        starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", log)]
        ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", log)]
        cuts = []
        for start, end in zip(starts, ends):
            dur = end - start
            if dur < 0.85:
                continue
            # Keep a tiny breath so cuts don't feel clipped.
            s = max(0.0, start + 0.08)
            e = min(duration, end - 0.08)
            if e - s >= 0.45:
                cuts.append({
                    "start": round(s, 3),
                    "end": round(e, 3),
                    "reason": f"Khoảng lặng {dur:.1f}s",
                    "source": "ffmpeg_silence",
                    "confidence": 0.62,
                })
        return cuts[:40]

    def _gemini_cut_suggestions(self, segments: list[dict], duration: float) -> list[dict]:
        api_key = _configured_ai_key(self.settings, "GEMINI_API_KEY", "gemini_api_key")
        if not api_key:
            return []
        model = str(self.settings.get("gemini_text_model", "gemini-2.5-flash-lite") or "gemini-2.5-flash-lite")
        if model == "auto":
            model = "gemini-2.5-flash-lite"
        transcript = "\n".join(
            f"[{seg['start']:.2f}-{seg['end']:.2f}] {seg['text']}"
            for seg in segments[:500]
        )
        prompt = f"""
Bạn là editor video one-shot tiếng Việt. Dựa trên transcript timestamp, hãy đề xuất đoạn nên cắt bỏ.
Chỉ đề xuất khi rõ: nói lắp, nói lại cùng ý, khoảng thừa, test mic, ngập ngừng dài, câu hỏng.
Không cắt câu đang có ý chính. Trả JSON thuần:
{{"cuts":[{{"start":0.0,"end":1.0,"reason":"...","confidence":0.8}}]}}

Duration: {duration:.2f}s
Transcript:
{transcript[:16000]}
""".strip()
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60,
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].removeprefix("json").strip()
            data = json.loads(raw)
            cuts = data.get("cuts", []) if isinstance(data, dict) else []
            out = []
            for cut in cuts:
                out.append({
                    "start": float(cut.get("start", 0)),
                    "end": float(cut.get("end", 0)),
                    "reason": str(cut.get("reason", "AI đề xuất cắt")).strip()[:160],
                    "source": "gemini",
                    "confidence": float(cut.get("confidence", 0.7)),
                })
            return out
        except Exception as e:
            self._log(f"Gemini cut suggestion lỗi: {e}")
            return []

    def _gemini_thumbnail_title(self, segments: list[dict], source_title: str) -> str:
        return _gemini_thumbnail_title_from_settings(self.settings, segments, source_title, self._log)

    def _normalize_cut_candidates(self, cuts: list[dict], duration: float) -> list[dict]:
        normalized = []
        for idx, cut in enumerate(cuts):
            try:
                start = max(0.0, min(duration, float(cut.get("start", 0))))
                end = max(0.0, min(duration, float(cut.get("end", 0))))
            except Exception:
                continue
            if end - start < 0.25:
                continue
            normalized.append({
                "id": f"cut-{idx+1}",
                "start": round(start, 3),
                "end": round(end, 3),
                "reason": str(cut.get("reason", "Đề xuất cắt")).strip()[:180],
                "source": str(cut.get("source", "auto")),
                "confidence": round(float(cut.get("confidence", 0.5)), 2),
                "enabled": True,
            })
        normalized.sort(key=lambda x: (x["start"], x["end"]))
        # Drop near-duplicates, favor Gemini over silence.
        result = []
        for cut in normalized:
            duplicate = False
            for existing in result:
                if abs(cut["start"] - existing["start"]) < 0.45 and abs(cut["end"] - existing["end"]) < 0.45:
                    duplicate = True
                    if existing["source"] != "gemini" and cut["source"] == "gemini":
                        existing.update(cut)
                    break
            if not duplicate:
                result.append(cut)
        return result[:60]

    def cancel(self):
        self._cancelled = True


# ── Worker 4: One-shot title regeneration ────────────────────────────────

class OneShotTitleWorker(QThread):
    """Regenerate and validate the thumbnail title from a saved one-shot plan."""
    finished = pyqtSignal(str, str)  # title, source
    error = pyqtSignal(str)

    def __init__(self, plan_path: str, settings: dict, mode: str = "expert", parent=None):
        super().__init__(parent)
        self.plan_path = Path(plan_path)
        self.settings = settings or {}
        self.mode = mode or "expert"

    def run(self):
        try:
            if not self.plan_path.exists():
                raise FileNotFoundError(f"Không thấy cuts.json: {self.plan_path}")
            plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
            source = Path(plan.get("source_video") or plan.get("original_video") or "video.mp4")
            segments = plan.get("transcript", [])
            if not isinstance(segments, list):
                segments = []
            title_provider_state: dict = {}
            title, source_kind, ai_costs = _build_thumbnail_title(
                self.settings,
                segments,
                source.stem,
                provider_state=title_provider_state,
                mode=self.mode,
            )
            ai_metadata = title_provider_state.get("ai_metadata") if isinstance(title_provider_state.get("ai_metadata"), dict) else {}
            plan["thumbnail_title_suggestion"] = title
            plan["thumbnail_title_source"] = source_kind
            plan["thumbnail_title_quality"] = _thumbnail_title_quality(title, source.stem, segments)
            plan["title_quality"] = plan["thumbnail_title_quality"]
            plan["title_candidates"] = [title]
            plan["ai_metadata_suggestion"] = ai_metadata
            plan["metadata_plan"] = _one_shot_metadata_plan(title, source.stem, segments, self.settings, ai_metadata)
            plan["ai_costs"] = ai_costs
            plan["ai_cost_total"] = _sum_ai_costs(ai_costs)
            self.plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            self.finished.emit(title, source_kind)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


# ── Worker 4a: One-shot thumbnail preview ────────────────────────────────

class OneShotThumbnailPreviewWorker(QThread):
    """Build thumbnail preview off the UI thread, including optional LUT frame processing."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, plan_path: str, settings: dict, title: str = "", parent=None):
        super().__init__(parent)
        self.plan_path = Path(plan_path)
        self.settings = settings or {}
        self.title = title or ""
        self._cancelled = False

    def _is_cancelled(self) -> bool:
        return self._cancelled or self.isInterruptionRequested()

    def run(self):
        try:
            if not self.plan_path.exists():
                raise FileNotFoundError(f"Không thấy cuts.json: {self.plan_path}")
            plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
            out_dir = Path(plan["output_dir"])
            source = Path(plan.get("source_video") or "video.mp4")
            frame_path = Path(plan.get("thumbnail_frame") or "")
            if not frame_path.exists():
                raise FileNotFoundError("Chưa có frame thumbnail. Hãy phân tích lại video.")
            lut_src = self.settings.get("one_shot_lut_path") or plan.get("lut_path") or ""
            apply_lut = (
                bool(self.settings.get("one_shot_apply_lut", True))
                and bool(lut_src)
                and Path(str(lut_src)).exists()
            )
            if apply_lut:
                processed_frame, _mode, _processed_path = _processed_thumbnail_frame(
                    source,
                    frame_path,
                    out_dir,
                    float(plan.get("duration", 0) or 0),
                    str(lut_src),
                    is_cancelled=self._is_cancelled,
                )
                frame_path = processed_frame
            if self._is_cancelled():
                raise RuntimeError("Đã dừng")
            segments = plan.get("transcript", [])
            if not isinstance(segments, list):
                segments = []
            title = _clean_thumbnail_title(
                self.title.strip()
                or str(plan.get("thumbnail_title_suggestion", "")).strip()
                or source.stem,
                source.stem,
                segments,
            )
            base = _thumbnail_output_path(out_dir, source.stem, title)
            preview = base.with_name(f"{base.stem}_preview{base.suffix}")
            style = _draw_boxphonefarm_thumbnail(
                frame_path,
                preview,
                title,
                str(self.settings.get("one_shot_thumbnail_font", "dt_phudu_black") or "dt_phudu_black"),
                str(self.settings.get("one_shot_thumbnail_size", "large") or "large"),
                str(self.settings.get("one_shot_thumbnail_lines", "auto") or "auto"),
                str(self.settings.get("one_shot_thumbnail_position", "center") or "center"),
            )
            layout_quality = _thumbnail_layout_quality(style, _thumbnail_render_title(title, source.stem, segments)[1])
            title_quality = _thumbnail_title_quality(title, source.stem, segments)
            original_title = _clean_thumbnail_title(str(plan.get("thumbnail_title_suggestion", "")).strip() or source.stem, source.stem, segments)
            ai_metadata = (
                plan.get("ai_metadata_suggestion")
                if title == original_title and isinstance(plan.get("ai_metadata_suggestion"), dict)
                else {}
            )
            metadata_plan = _one_shot_metadata_plan(title, source.stem, segments, self.settings, ai_metadata)
            final_status = _one_shot_final_status(title_quality, layout_quality)
            plan["thumbnail_title_suggestion"] = title
            plan["thumbnail_title_quality"] = title_quality
            plan["title_quality"] = title_quality
            plan["thumbnail_preview"] = str(preview)
            plan["thumbnail_preview_style"] = style
            plan["thumbnail_layout_quality"] = layout_quality
            plan["metadata_plan"] = metadata_plan
            plan["final_status"] = final_status
            self.plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            self.finished.emit(str(preview))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def cancel(self):
        self._cancelled = True


# ── Worker 4b: ESCBase slide template ────────────────────────────────────

class EscbaseSlideWorker(QThread):
    """Create and optionally render an ESCBase slide-video project."""
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)  # hedra-slide-report.json path
    error = pyqtSignal(str)

    def __init__(self, source_text: str, settings: dict, options: dict | None = None, parent=None):
        super().__init__(parent)
        self.source_text = source_text or ""
        self.settings = settings or {}
        self.options = options or {}
        self._cancelled = False
        self._proc: subprocess.Popen | None = None

    def _log(self, line: str) -> None:
        self.log_line.emit(line)

    def _is_cancelled(self) -> bool:
        return self._cancelled or self.isInterruptionRequested()

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise RuntimeError("Đã dừng")

    def _run_cmd(self, cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": _shell_path()}
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=(os.name != "nt"),
        )
        started = time.monotonic()
        try:
            while True:
                if self._is_cancelled():
                    _terminate_process(self._proc)
                    stdout, stderr = self._proc.communicate(timeout=1)
                    return subprocess.CompletedProcess(cmd, -15, stdout or "", stderr or "Đã dừng")
                if time.monotonic() - started > timeout:
                    _terminate_process(self._proc)
                    stdout, stderr = self._proc.communicate(timeout=1)
                    raise subprocess.TimeoutExpired(cmd, timeout, output=stdout or "", stderr=stderr or "")
                try:
                    stdout, stderr = self._proc.communicate(timeout=0.25)
                    return subprocess.CompletedProcess(cmd, self._proc.returncode, stdout or "", stderr or "")
                except subprocess.TimeoutExpired:
                    continue
        finally:
            self._proc = None

    def run(self):
        try:
            if not self.source_text.strip():
                raise ValueError("Nhập script hoặc nội dung trước khi tạo video slide.")
            root = escbase_root()
            py = sys.executable
            dep = escbase_dependency_status(root, py)
            self.progress.emit(8)
            if dep.get("status") in {"missing_template", "invalid_template"}:
                raise RuntimeError(dep.get("message") or "ESCBase template chưa sẵn sàng.")
            self._log(f"ESCBase: {dep.get('message', dep.get('status'))}")
            self._raise_if_cancelled()

            project = escbase_create_project(
                self.source_text,
                self.settings.get("output_dir") or DEFAULT_OUT,
                str(self.options.get("project_name") or ""),
                str(self.options.get("template_id") or ESCBASE_TEMPLATE_ID),
                root,
            )
            project_dir = Path(project["project_dir"])
            self.progress.emit(28)
            self._log(f"Đã tạo project: {project_dir.name}")
            self._raise_if_cancelled()

            validate_cmd = [py, str(root / "validate_slide.py"), str(project_dir), "--semantic-report"]
            if dep.get("status") != "ready":
                validate_cmd.append("--skip-safezone")
            self._log("Đang validate slide…")
            r = self._run_cmd(validate_cmd, root, 300)
            self._raise_if_cancelled()
            validation_ok = r.returncode == 0
            validation_log = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
            if not validation_ok:
                self._log("Validate chưa đạt; vẫn giữ project để chỉnh tiếp.")
            self.progress.emit(56)

            final_video = project_dir / "output" / "final_video.mp4"
            render_status = "skipped"
            render_log = ""
            if dep.get("status") == "ready" and validation_ok:
                self._log("Đang render video slide…")
                render_cmd = [py, str(root / "auto_render.py"), str(project_dir)]
                rr = self._run_cmd(render_cmd, root, 1800)
                self._raise_if_cancelled()
                render_log = ((rr.stdout or "") + "\n" + (rr.stderr or "")).strip()
                render_status = "done" if rr.returncode == 0 and final_video.exists() else "failed"
                if render_status == "failed":
                    self._log("Render chưa thành công; xem Chi tiết kỹ thuật.")
            else:
                self._log("Bỏ qua render vì dependency chưa đủ hoặc validate chưa đạt.")
            self.progress.emit(88)

            report = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "template_status": dep,
                "project": project,
                "project_dir": str(project_dir),
                "metadata_path": str(project_dir / "upload-metadata.json"),
                "final_video": str(final_video) if final_video.exists() else "",
                "validation_ok": validation_ok,
                "validation_log_tail": validation_log[-4000:],
                "render_status": render_status,
                "render_log_tail": render_log[-4000:],
            }
            report_path = project_dir / "hedra-slide-report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.progress.emit(100)
            self._log("Slide Template xong.")
            self.finished.emit(str(report_path))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def cancel(self):
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            _terminate_process(proc, wait=False)


# ── Worker 5: One-shot render ────────────────────────────────────────────

class OneShotRenderWorker(QThread):
    """Render selected cuts + noise/LUT + BoxPhoneFarm thumbnail."""
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)  # edit-report.json path
    error = pyqtSignal(str)

    def __init__(self, plan_path: str, selected_cut_ids: list[str], options: dict | None = None, parent=None):
        super().__init__(parent)
        self.plan_path = Path(plan_path)
        self.selected_cut_ids = set(selected_cut_ids or [])
        self.options = options or {}
        self._cancelled = False

    def _log(self, line: str) -> None:
        self.log_line.emit(line)

    def _is_cancelled(self) -> bool:
        return self._cancelled or self.isInterruptionRequested()

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise RuntimeError("Đã dừng")

    def run(self):
        output_video: Path | None = None
        render_completed = False
        try:
            started_at = time.perf_counter()
            step_times: dict[str, float] = {}
            if not self.plan_path.exists():
                raise FileNotFoundError(f"Không thấy cuts.json: {self.plan_path}")
            self._raise_if_cancelled()
            plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
            source = Path(plan["source_video"])
            out_dir = Path(plan["output_dir"])
            exports_dir = _one_shot_exports_dir(out_dir)
            render_to_final = bool(self.options.get("render_to_final", True))
            render_dir = exports_dir if render_to_final else out_dir
            render_dir.mkdir(parents=True, exist_ok=True)
            probe_t0 = time.perf_counter()
            duration = float(plan.get("duration", 0)) or _ffprobe_duration(source)
            source_info = _ffprobe_video_info(source)
            step_times["ffprobe"] = round(time.perf_counter() - probe_t0, 3)
            cut_video = bool(self.options.get("cut_video", plan.get("cut_video", True)))
            selected_cuts = [
                (float(c["start"]), float(c["end"]))
                for c in plan.get("cuts", [])
                if cut_video and c.get("id") in self.selected_cut_ids
            ]
            keep_segments = _keep_segments_from_cuts(selected_cuts, duration)
            full_timeline = _is_full_timeline(keep_segments, duration)
            self.progress.emit(8)
            self._log(f"[1/4] Keep segments: {len(keep_segments)}")

            plan_segments = plan.get("transcript", [])
            if not isinstance(plan_segments, list):
                plan_segments = []
            thumb_title = _clean_thumbnail_title(
                str(self.options.get("thumbnail_title") or plan.get("thumbnail_title_suggestion") or source.stem).strip(),
                source.stem,
                plan_segments,
            )
            plan_title = _clean_thumbnail_title(str(plan.get("thumbnail_title_suggestion") or source.stem), source.stem, plan_segments)
            ai_metadata = (
                plan.get("ai_metadata_suggestion")
                if thumb_title == plan_title and isinstance(plan.get("ai_metadata_suggestion"), dict)
                else {}
            )
            thumbnail_quality = _thumbnail_title_quality(thumb_title, source.stem, plan_segments)
            render_thumb_title, thumbnail_render_info = _thumbnail_render_title(thumb_title, source.stem, plan_segments)
            if thumbnail_render_info.get("changed"):
                self._log("Đã rút gọn title cho thumbnail")
            metadata_plan = _one_shot_metadata_plan(
                thumb_title,
                source.stem,
                plan_segments,
                self.options.get("settings") or {},
                ai_metadata,
            )
            upload_metadata = metadata_plan["upload_metadata"]
            output_video = Path(self.options.get("output_video") or _upload_video_output_path(render_dir, source.stem, upload_metadata))
            if output_video.exists() and not self.options.get("overwrite", False):
                output_video = _dedupe_path(output_video)

            lut_path = str(self.options.get("lut_path") or plan.get("lut_path") or "").strip()
            apply_lut = bool(self.options.get("apply_lut", True)) and lut_path and Path(lut_path).exists()
            frame_path = Path(plan.get("thumbnail_frame") or "")
            if not frame_path.exists():
                frame_t0 = time.perf_counter()
                frame_path = out_dir / "thumbnail-frame.png"
                _run_media_cmd([
                    "ffmpeg", "-y", "-ss", f"{min(duration * 0.32, max(duration - 0.5, 0.0)):.3f}",
                    "-i", str(source), "-frames:v", "1", str(frame_path),
                ], timeout=120, is_cancelled=self._is_cancelled)
                step_times["thumbnail_frame"] = round(time.perf_counter() - frame_t0, 3)
            else:
                step_times["thumbnail_frame"] = 0.0
            self._raise_if_cancelled()
            thumbnail_frame_source = frame_path
            processed_t0 = time.perf_counter()
            draw_frame_path, thumbnail_frame_mode, thumbnail_frame_processed = _processed_thumbnail_frame(
                source,
                thumbnail_frame_source,
                out_dir,
                duration,
                lut_path if apply_lut else "",
                self._is_cancelled,
            )
            step_times["thumbnail_frame_processed"] = round(time.perf_counter() - processed_t0, 3)
            if thumbnail_frame_mode == "lut_processed":
                self._log("Thumbnail dùng frame đã áp LUT màu")
            elif thumbnail_frame_mode == "fallback_source":
                self._log("Không xử lý được LUT cho thumbnail — dùng frame gốc")
            self._raise_if_cancelled()
            thumbnail = _thumbnail_output_path(out_dir, source.stem, render_thumb_title)
            self._log("[2/5] Tạo thumbnail BoxPhoneFarm")
            thumbnail_font = str(self.options.get("thumbnail_font") or "dt_phudu_black")
            thumbnail_size = str(self.options.get("thumbnail_size") or "large")
            thumbnail_lines = str(self.options.get("thumbnail_lines") or "auto")
            thumbnail_position = str(self.options.get("thumbnail_position") or "center")
            draw_t0 = time.perf_counter()
            thumbnail_style = _draw_boxphonefarm_thumbnail(
                draw_frame_path,
                thumbnail,
                render_thumb_title,
                thumbnail_font,
                thumbnail_size,
                thumbnail_lines,
                thumbnail_position,
            )
            thumbnail_layout_quality = _thumbnail_layout_quality(thumbnail_style, thumbnail_render_info)
            severe_layout_issues = {
                issue
                for issue in thumbnail_layout_quality.get("issues", [])
                if issue in {"font_not_uniform", "outside_safe_width", "low_layout_score"} or str(issue).startswith("split_")
            }
            if severe_layout_issues:
                self._log("Cần xem lại layout thumbnail")
            step_times["thumbnail_draw"] = round(time.perf_counter() - draw_t0, 3)
            self._raise_if_cancelled()
            thumbnail_review = _thumbnail_review_gate(
                thumb_title,
                source.stem,
                plan_segments,
                thumbnail_quality,
                thumbnail_layout_quality,
                bool(self.options.get("ai_review_thumbnail", True)),
            )
            if thumbnail_review.get("enabled"):
                review_t0 = time.perf_counter()
                thumbnail_review = _gemini_review_thumbnail_image(
                    self.options.get("settings") or {},
                    thumbnail,
                    thumb_title,
                    plan_segments,
                    source.stem,
                    self._log,
                )
                suggested_title = str(thumbnail_review.get("suggested_title") or "").strip()
                if suggested_title and suggested_title != thumb_title:
                    suggested_quality = _thumbnail_title_quality(suggested_title, source.stem, plan_segments)
                    if suggested_quality.get("publish_status") == "ready":
                        self._log("AI review sửa thuật ngữ/title — render lại thumbnail")
                        thumb_title = suggested_title
                        thumbnail_quality = suggested_quality
                        render_thumb_title, thumbnail_render_info = _thumbnail_render_title(thumb_title, source.stem, plan_segments)
                        if thumbnail_render_info.get("changed"):
                            self._log("Đã rút gọn title cho thumbnail")
                        metadata_plan = _one_shot_metadata_plan(
                            thumb_title,
                            source.stem,
                            plan_segments,
                            self.options.get("settings") or {},
                            {},
                        )
                        upload_metadata = metadata_plan["upload_metadata"]
                        thumbnail = _thumbnail_output_path(out_dir, source.stem, render_thumb_title)
                        thumbnail_style = _draw_boxphonefarm_thumbnail(
                            draw_frame_path,
                            thumbnail,
                            render_thumb_title,
                            thumbnail_font,
                            thumbnail_size,
                            thumbnail_lines,
                            thumbnail_position,
                        )
                        thumbnail_layout_quality = _thumbnail_layout_quality(thumbnail_style, thumbnail_render_info)
                        output_video = _upload_video_output_path(render_dir, source.stem, upload_metadata)
                        if output_video.exists() and not self.options.get("overwrite", False):
                            output_video = _dedupe_path(output_video)
                    else:
                        self._log("AI review gợi ý title nhưng gate loại vì thiếu an toàn")
                step_times["thumbnail_review"] = round(time.perf_counter() - review_t0, 3)
            else:
                if thumbnail_review.get("status") == "skipped":
                    self._log("AI review thumbnail bỏ qua: deterministic gate đã đạt")
                step_times["thumbnail_review"] = 0.0
            self._raise_if_cancelled()
            prepend_cover = bool(self.options.get("prepend_thumbnail_cover", True))
            ai_costs = list(plan.get("ai_costs", [])) if isinstance(plan.get("ai_costs"), list) else []
            review_cost = thumbnail_review.get("cost") if isinstance(thumbnail_review, dict) else None
            if (
                isinstance(review_cost, dict)
                and bool(thumbnail_review.get("enabled"))
                and review_cost.get("provider")
            ):
                ai_costs.append(review_cost)
            ai_cost_total = _sum_ai_costs(ai_costs)

            noise_reduce = bool(self.options.get("noise_reduce", True))
            prepend_cover = bool(self.options.get("prepend_thumbnail_cover", True))
            render_method = "encode"
            output_profile = _one_shot_render_profile(self.options.get("render_profile"), source_info)

            can_stream_copy = full_timeline and not apply_lut and not noise_reduce and not prepend_cover
            if can_stream_copy:
                render_method = "stream_copy"
                cmd = [
                    "ffmpeg", "-y", "-i", str(source),
                    "-map", "0:v:0", "-map", "0:a?",
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(output_video),
                ]
                video_encoder = "copy"
                self._log("[3/5] Render nhanh bằng stream copy")
                render_t0 = time.perf_counter()
                r = _run_media_cmd(cmd, timeout=3600, is_cancelled=self._is_cancelled)
                step_times["ffmpeg_render"] = round(time.perf_counter() - render_t0, 3)
                self._raise_if_cancelled()
                if r.returncode != 0:
                    raise RuntimeError((r.stderr or r.stdout or "ffmpeg stream copy failed").strip()[-3000:])
            else:
                filter_parts: list[str] = []
                if full_timeline:
                    filter_parts.append("[0:v]null[vcat]")
                    filter_parts.append("[0:a]anull[acat]")
                else:
                    labels: list[str] = []
                    for i, (start, end) in enumerate(keep_segments):
                        filter_parts.append(
                            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}];"
                            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]"
                        )
                        labels.append(f"[v{i}][a{i}]")
                    filter_parts.append("".join(labels) + f"concat=n={len(keep_segments)}:v=1:a=1[vcat][acat]")

                if apply_lut:
                    width = int(output_profile.get("width") or 0)
                    height = int(output_profile.get("height") or 0)
                    if width <= 0 or height <= 0:
                        width = int(source_info.get("width") or 0)
                        height = int(source_info.get("height") or 0)
                    if width <= 0 or height <= 0:
                        width, height = _ffprobe_video_size(source)
                    width += width % 2
                    height += height % 2
                    output_profile["width"] = width
                    output_profile["height"] = height
                    video_tail = (
                        f"fps=30,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
                        f"lut3d=file='{_escape_filter_path(lut_path)}'"
                    )
                    filter_parts.append(f"[vcat]{video_tail}[vmain]")
                else:
                    width = int(output_profile.get("width") or 0)
                    height = int(output_profile.get("height") or 0)
                    if prepend_cover and (width <= 0 or height <= 0):
                        width = int(source_info.get("width") or 0)
                        height = int(source_info.get("height") or 0)
                    if prepend_cover and (width <= 0 or height <= 0):
                        width, height = _ffprobe_video_size(source)
                    if width > 0 and height > 0:
                        width += width % 2
                        height += height % 2
                        output_profile["width"] = width
                        output_profile["height"] = height
                        video_tail = (
                            f"fps=30,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
                        )
                    else:
                        video_tail = "fps=30,format=yuv420p" if prepend_cover else "null"
                    filter_parts.append(f"[vcat]{video_tail}[vmain]")

                audio_tail = ",aformat=sample_rates=48000:channel_layouts=stereo" if prepend_cover else ""
                if noise_reduce:
                    filter_parts.append(
                        f"[acat]highpass=f=80,afftdn=nf=-25,"
                        f"acompressor=threshold=-18dB:ratio=2:attack=20:release=200,"
                        f"alimiter=limit=0.85{audio_tail}[amain]"
                    )
                else:
                    filter_parts.append(f"[acat]anull{audio_tail}[amain]")

                extra_inputs: list[str] = []
                map_v, map_a = "[vmain]", "[amain]"
                if prepend_cover:
                    cover_dur = 0.28
                    width = int(output_profile.get("width") or source_info.get("width") or 0)
                    height = int(output_profile.get("height") or source_info.get("height") or 0)
                    if width <= 0 or height <= 0:
                        width, height = _ffprobe_video_size(source)
                    width += width % 2
                    height += height % 2
                    extra_inputs = [
                        "-loop", "1", "-t", f"{cover_dur:.2f}", "-i", str(thumbnail),
                        "-f", "lavfi", "-t", f"{cover_dur:.2f}",
                        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    ]
                    filter_parts.append(
                        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                        "fps=30,format=yuv420p,setpts=PTS-STARTPTS[vcover]"
                    )
                    filter_parts.append("[2:a]aresample=48000,asetpts=PTS-STARTPTS[acover]")
                    filter_parts.append("[vcover][acover][vmain][amain]concat=n=2:v=1:a=1[vout][aout]")
                    map_v, map_a = "[vout]", "[aout]"

                video_args, video_encoder = _best_h264_args()
                if video_encoder == "h264_videotoolbox" and output_profile.get("bitrate"):
                    video_args = [
                        "-c:v", "h264_videotoolbox",
                        "-b:v", str(output_profile["bitrate"]),
                        "-profile:v", "high",
                        "-pix_fmt", "yuv420p",
                        "-allow_sw", "1",
                    ]
                cmd = [
                    "ffmpeg", "-y", "-i", str(source),
                    *extra_inputs,
                    "-filter_complex", ";".join(filter_parts),
                    "-map", map_v, "-map", map_a,
                    *video_args,
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    str(output_video),
                ]
                self._log(f"[3/5] Render video bằng ffmpeg ({video_encoder})")
                render_t0 = time.perf_counter()
                r = _run_media_cmd(cmd, timeout=3600, is_cancelled=self._is_cancelled)
                step_times["ffmpeg_render"] = round(time.perf_counter() - render_t0, 3)
                self._raise_if_cancelled()
                if r.returncode != 0 and video_encoder != "libx264":
                    self._log(f"{video_encoder} lỗi — fallback libx264")
                    fallback_args, video_encoder = _software_h264_args()
                    cmd = [
                        "ffmpeg", "-y", "-i", str(source),
                        *extra_inputs,
                        "-filter_complex", ";".join(filter_parts),
                        "-map", map_v, "-map", map_a,
                        *fallback_args,
                        "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart",
                        str(output_video),
                    ]
                    render_t0 = time.perf_counter()
                    r = _run_media_cmd(cmd, timeout=3600, is_cancelled=self._is_cancelled)
                    step_times["ffmpeg_render"] = round(time.perf_counter() - render_t0, 3)
                    self._raise_if_cancelled()
                if r.returncode != 0:
                    raise RuntimeError((r.stderr or r.stdout or "ffmpeg render failed").strip()[-3000:])
            render_completed = True
            self.progress.emit(72)
            self.progress.emit(92)
            self._raise_if_cancelled()

            exports_dir.mkdir(parents=True, exist_ok=True)
            export_video = _dedupe_path(exports_dir / output_video.name) if output_video.parent != exports_dir else output_video
            export_thumbnail = _dedupe_path(exports_dir / thumbnail.name) if thumbnail.parent != exports_dir else thumbnail
            export_t0 = time.perf_counter()
            if output_video.resolve() != export_video.resolve():
                shutil.copy2(output_video, export_video)
            export_thumbnail_path = ""
            if bool(self.options.get("export_thumbnail", True)) and thumbnail.resolve() != export_thumbnail.resolve():
                shutil.copy2(thumbnail, export_thumbnail)
                export_thumbnail_path = str(export_thumbnail)
            elif bool(self.options.get("export_thumbnail", True)):
                export_thumbnail_path = str(export_thumbnail)
            step_times["export_copy"] = round(time.perf_counter() - export_t0, 3)

            total_seconds = round(time.perf_counter() - started_at, 3)
            ffmpeg_seconds = float(step_times.get("ffmpeg_render") or 0.0)
            realtime_factor = round(ffmpeg_seconds / duration, 3) if duration > 0 and ffmpeg_seconds > 0 else 0.0
            filter_features = {
                "full_timeline": full_timeline,
                "cut": bool(selected_cuts),
                "lut": apply_lut,
                "noise": noise_reduce,
                "cover": prepend_cover,
                "ai_review": bool(thumbnail_review.get("enabled")) if isinstance(thumbnail_review, dict) else False,
            }
            final_status = _one_shot_final_status(thumbnail_quality, thumbnail_layout_quality, thumbnail_review)
            render_profile = {
                "source": {
                    "duration": round(duration, 3),
                    **source_info,
                },
                "steps": step_times,
                "total_seconds": total_seconds,
                "ffmpeg_seconds": round(ffmpeg_seconds, 3),
                "realtime_factor": realtime_factor,
                "render_method": render_method,
                "encoder": video_encoder,
                "features": filter_features,
                "output_profile": output_profile,
            }
            render_profile["bottleneck"] = _render_bottleneck(render_profile)
            self._log(
                f"Render profile: {render_method} · {realtime_factor:.2f}x realtime"
                + (f" · bottleneck {render_profile['bottleneck']}" if render_profile.get("bottleneck") else "")
            )

            report = {
                "video": str(output_video),
                "thumbnail": str(thumbnail),
                "export_video": str(export_video),
                "export_thumbnail": export_thumbnail_path,
                "export_dir": str(exports_dir),
                "job_dir": str(out_dir),
                "cuts_applied": [
                    c for c in plan.get("cuts", []) if c.get("id") in self.selected_cut_ids
                ],
                "keep_segments": [{"start": s, "end": e} for s, e in keep_segments],
                "noise_reduce": noise_reduce,
                "apply_lut": apply_lut,
                "lut_path": lut_path if apply_lut else "",
                "thumbnail_font": thumbnail_font,
                "thumbnail_style": thumbnail_style,
                "thumbnail_frame_source": str(thumbnail_frame_source),
                "thumbnail_frame_processed": thumbnail_frame_processed,
                "thumbnail_frame_mode": thumbnail_frame_mode,
                "thumbnail_title": thumb_title,
                "thumbnail_render_title": render_thumb_title,
                "thumbnail_render_info": thumbnail_render_info,
                "thumbnail_title_quality": thumbnail_quality,
                "thumbnail_layout_quality": thumbnail_layout_quality,
                "upload_metadata": upload_metadata,
                "upload_title": upload_metadata.get("upload_title", ""),
                "platform_caption": upload_metadata.get("platform_caption", ""),
                "thumbnail_review": thumbnail_review,
                "prepend_thumbnail_cover": prepend_cover,
                "ai_costs": ai_costs,
                "ai_cost_total": ai_cost_total,
                "ai_cost_by_kind": _sum_ai_costs_by_kind(ai_costs),
                "title_gate": thumbnail_quality,
                "layout_gate": thumbnail_layout_quality,
                "metadata_gate": metadata_plan.get("metadata_gate", {}),
                "review_gate": thumbnail_review,
                "final_status": final_status,
                "final_status_label": _one_shot_status_label(final_status),
                "industry": str(self.options.get("industry") or plan.get("industry") or "tech"),
                "final_video_name": Path(export_video).name,
                "final_hashtags": upload_metadata.get("hashtags", []),
                "preview_thumbnail": str(plan.get("thumbnail_preview") or ""),
                "final_thumbnail": export_thumbnail_path or str(thumbnail),
                "cut_video": cut_video,
                "transcript_mode": str(plan.get("transcript_mode") or "silence_fallback"),
                "transcript_detail": str(plan.get("transcript_detail") or ""),
                "video_encoder": video_encoder,
                "render_to_final": render_to_final,
                "render_profile": render_profile,
            }
            report_path = out_dir / "edit-report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.progress.emit(100)
            self._log("[5/5] Render xong" if prepend_cover else "[4/4] Render xong")
            self.finished.emit(str(report_path))
        except Exception as e:
            if not render_completed and bool(self.options.get("cleanup_partial", True)) and output_video and output_video.exists():
                try:
                    output_video.unlink()
                except Exception:
                    pass
            self.error.emit(f"{type(e).__name__}: {e}")

    def cancel(self):
        self._cancelled = True


# ── Worker 6: One-shot batch queue ───────────────────────────────────────

class OneShotBatchWorker(QThread):
    """Run one-shot analyze + render for many videos sequentially."""
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)
    item_done = pyqtSignal(dict)
    finished = pyqtSignal(str)  # batch-summary.json path
    error = pyqtSignal(str)

    def __init__(self, video_paths: list[str], settings: dict, options: dict | None = None, parent=None):
        super().__init__(parent)
        self.video_paths = [str(Path(p)) for p in (video_paths or []) if str(p).strip()]
        self.settings = settings or {}
        self.options = options or {}
        self.options.setdefault("title_provider_state", {})
        self.options.setdefault("whisper_model", "small")
        self._cancelled = False
        self._active_lock = threading.Lock()
        self._active_workers: set[QThread] = set()

    def _log(self, line: str) -> None:
        self.log_line.emit(line)

    def _run_child_worker(self, worker: QThread) -> None:
        with self._active_lock:
            self._active_workers.add(worker)
        try:
            worker.run()
        finally:
            with self._active_lock:
                self._active_workers.discard(worker)

    def _run_analyze(self, video_path: str, index: int, total: int) -> tuple[str, str]:
        result = {"plan": "", "error": ""}
        opts = dict(self.options)
        opts["copy_source"] = False
        opts["title_provider_state"] = self.options.setdefault("title_provider_state", {})
        worker = OneShotAnalyzeWorker(video_path, self.settings, opts)
        worker.log_line.connect(lambda line, i=index, n=total: self._log(f"[{i}/{n}] {line}"))
        worker.progress.connect(
            lambda p, i=index, n=total: self.progress.emit(
                int((((i - 1) + (max(0, min(100, int(p))) / 100.0) * 0.5) / n) * 100)
            )
        )
        worker.finished.connect(lambda plan_path: result.__setitem__("plan", plan_path))
        worker.error.connect(lambda msg: result.__setitem__("error", msg))
        self._run_child_worker(worker)
        return result["plan"], result["error"]

    def _run_render(self, plan_path: str, index: int, total: int) -> tuple[str, str]:
        result = {"report": "", "error": ""}
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        cut_video = bool(self.options.get("cut_video", plan.get("cut_video", True)))
        selected_cut_ids = [
            str(c.get("id", ""))
            for c in plan.get("cuts", [])
            if cut_video and c.get("enabled", True) and c.get("id")
        ]
        source = Path(plan.get("source_video") or "video.mp4")
        segments = plan.get("transcript", [])
        if not isinstance(segments, list):
            segments = []
        title = _clean_thumbnail_title(
            str(plan.get("thumbnail_title_suggestion", "") or source.stem),
            source.stem,
            segments,
        )
        opts = dict(self.options)
        opts.update({
            "thumbnail_title": title,
            "overwrite": False,
            "export_thumbnail": True,
            "render_to_final": True,
            "cleanup_partial": True,
            "keep_debug_audio": False,
        })
        worker = OneShotRenderWorker(plan_path, selected_cut_ids, opts)
        worker.log_line.connect(lambda line, i=index, n=total: self._log(f"[{i}/{n}] {line}"))
        worker.progress.connect(
            lambda p, i=index, n=total: self.progress.emit(
                int((((i - 1) + 0.5 + (max(0, min(100, int(p))) / 100.0) * 0.5) / n) * 100)
            )
        )
        worker.finished.connect(lambda report_path: result.__setitem__("report", report_path))
        worker.error.connect(lambda msg: result.__setitem__("error", msg))
        self._run_child_worker(worker)
        return result["report"], result["error"]

    def run(self):
        try:
            paths = []
            for raw in self.video_paths:
                p = Path(raw).expanduser()
                if p.exists() and p.is_file():
                    paths.append(str(p))
            total = len(paths)
            if total <= 0:
                raise ValueError("Chưa có video hợp lệ để chạy batch.")
            if shutil.which("ffmpeg", path=_shell_path()) is None or shutil.which("ffprobe", path=_shell_path()) is None:
                raise RuntimeError("Thiếu ffmpeg/ffprobe. Cài ffmpeg trước khi chạy batch.")
            out_root = Path(self.settings.get("output_dir") or DEFAULT_OUT)
            try:
                out_root.mkdir(parents=True, exist_ok=True)
                probe_file = out_root / ".hedra_write_test"
                probe_file.write_text("ok", encoding="utf-8")
                probe_file.unlink(missing_ok=True)
            except Exception as exc:
                raise RuntimeError(f"Không ghi được thư mục xuất: {out_root} ({exc})") from exc
            disk_estimate = _estimate_one_shot_batch_disk_bytes(paths, self.options)
            free_bytes = _free_disk_bytes(out_root)
            if free_bytes < int(disk_estimate.get("required_bytes") or 0):
                raise RuntimeError(
                    "Không đủ dung lượng trống để chạy batch: "
                    f"còn {_format_gb(free_bytes)}, ước cần {_format_gb(disk_estimate['required_bytes'])}. "
                    "Hãy xoá bớt output/debug trước khi render."
                )
            whisper_status = whisper_runtime_status({**self.settings, "one_shot_whisper_model": self.options.get("whisper_model", "small")})
            self._log(
                "Preflight: ffmpeg OK · output OK · "
                f"disk {_format_gb(free_bytes)} trống / cần ~{_format_gb(disk_estimate['required_bytes'])} · "
                f"Whisper local: {whisper_status.get('label', 'Không rõ')}"
            )
            if whisper_status.get("status") != "ready":
                self._log(f"Preflight: {whisper_status.get('detail') or 'Whisper chưa sẵn sàng'} Fallback khoảng lặng vẫn render được.")

            raw_concurrency = self.options.get("batch_concurrency", "auto")
            if str(raw_concurrency).strip().lower() == "auto":
                concurrency = _auto_batch_concurrency(total)
            else:
                try:
                    concurrency = int(raw_concurrency or 2)
                except Exception:
                    concurrency = 2
                concurrency = max(1, min(6, concurrency, total))
            mode_label = "chạy tuần tự" if concurrency == 1 else f"chạy song song {concurrency}"
            self._log(f"Batch one-shot: {total} video · {mode_label}")
            items: list[dict] = []
            all_costs: list[dict] = []
            today = datetime.now().strftime("%Y-%m-%d")
            fallback_export_dir = out_root / "one-shot" / today
            export_dir = fallback_export_dir
            render_gate = threading.Lock()

            def process_one(index: int, video_path: str) -> dict:
                if self._cancelled or self.isInterruptionRequested():
                    return {
                        "source": video_path,
                        "source_name": Path(video_path).name,
                        "ok": False,
                        "cancelled": True,
                        "error": "Batch đã dừng theo yêu cầu.",
                    }
                name = Path(video_path).name
                self._log(f"[{index}/{total}] Bắt đầu: {name}")
                item = {
                    "source": video_path,
                    "source_name": name,
                    "ok": False,
                    "plan": "",
                    "report": "",
                    "error": "",
                }
                try:
                    plan_path, analyze_error = self._run_analyze(video_path, index, total)
                    if analyze_error:
                        if self._cancelled or self.isInterruptionRequested() or "Đã dừng" in analyze_error:
                            item["cancelled"] = True
                            item["error"] = "Batch đã dừng trong bước phân tích."
                            return item
                        raise RuntimeError(analyze_error)
                    if self._cancelled or self.isInterruptionRequested():
                        item["cancelled"] = True
                        item["error"] = "Batch đã dừng sau bước phân tích."
                        return item
                    item["plan"] = plan_path
                    try:
                        plan_doc = json.loads(Path(plan_path).read_text(encoding="utf-8"))
                    except Exception:
                        plan_doc = {}
                    serialize_render, serialize_reason = _should_serialize_one_shot_render(
                        out_root,
                        video_path,
                        disk_estimate,
                        self.options,
                    )
                    if serialize_render:
                        self._log(f"[{index}/{total}] Render tuần tự tạm thời vì {serialize_reason}")
                        with render_gate:
                            report_path, render_error = self._run_render(plan_path, index, total)
                    else:
                        report_path, render_error = self._run_render(plan_path, index, total)
                    if render_error:
                        if self._cancelled or self.isInterruptionRequested() or "Đã dừng" in render_error:
                            item["cancelled"] = True
                            item["error"] = "Batch đã dừng trong bước render."
                            return item
                        raise RuntimeError(render_error)
                    item["report"] = report_path
                    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
                    render_profile = report.get("render_profile", {}) if isinstance(report.get("render_profile", {}), dict) else {}
                    item_ai_cost = report.get("ai_cost_total", _empty_ai_cost())
                    render_seconds = float(render_profile.get("ffmpeg_seconds") or 0.0)
                    render_total_seconds = float(render_profile.get("total_seconds") or 0.0)
                    render_realtime_factor = float(render_profile.get("realtime_factor") or 0.0)
                    item.update({
                        "ok": True,
                        "video": report.get("video", ""),
                        "thumbnail": report.get("thumbnail", ""),
                        "export_video": report.get("export_video", ""),
                        "export_thumbnail": report.get("export_thumbnail", ""),
                        "export_dir": report.get("export_dir", ""),
                        "job_dir": report.get("job_dir", ""),
                        "thumbnail_title": report.get("thumbnail_title", ""),
                        "thumbnail_render_title": report.get("thumbnail_render_title", ""),
                        "thumbnail_layout_quality": report.get("thumbnail_layout_quality", {}),
                        "upload_metadata": report.get("upload_metadata", {}),
                        "upload_title": report.get("upload_title", ""),
                        "platform_caption": report.get("platform_caption", ""),
                        "thumbnail_quality": report.get("thumbnail_title_quality", {}),
                        "title_gate": report.get("title_gate", report.get("thumbnail_title_quality", {})),
                        "layout_gate": report.get("layout_gate", report.get("thumbnail_layout_quality", {})),
                        "metadata_gate": report.get("metadata_gate", {}),
                        "review_gate": report.get("review_gate", report.get("thumbnail_review", {})),
                        "final_status": report.get("final_status", "ready"),
                        "final_video_name": report.get("final_video_name", Path(str(report.get("export_video", ""))).name),
                        "final_hashtags": report.get("final_hashtags", []),
                        "preview_thumbnail": report.get("preview_thumbnail", ""),
                        "final_thumbnail": report.get("final_thumbnail", report.get("thumbnail", "")),
                        "thumbnail_quality_label": ", ".join(
                            str(r) for r in (report.get("thumbnail_title_quality", {}) or {}).get("reasons", [])[:2]
                        ) if isinstance(report.get("thumbnail_title_quality", {}), dict) else "",
                        "transcript_mode": report.get("transcript_mode") or plan_doc.get("transcript_mode", ""),
                        "transcript_detail": report.get("transcript_detail") or plan_doc.get("transcript_detail", ""),
                        "ai_cost_total": item_ai_cost,
                        "render_seconds": round(render_seconds, 3),
                        "render_total_seconds": round(render_total_seconds, 3),
                        "render_realtime_factor": round(render_realtime_factor, 3),
                        "render_profile": render_profile,
                    })
                    quality_label = _one_shot_status_label(str(item.get("final_status") or "ready"))
                    cost_label = ""
                    if isinstance(item_ai_cost, dict):
                        cost_label = f" · AI ${float(item_ai_cost.get('estimated_usd') or 0):.6f} ~ {int(item_ai_cost.get('estimated_vnd') or 0)}đ"
                    render_label = f" · render {render_seconds:.1f}s" if render_seconds > 0 else ""
                    self._log(f"[{index}/{total}] Xong: {quality_label}{render_label}{cost_label} · {Path(str(item.get('export_video') or '')).name}")
                except Exception as e:
                    item["error"] = f"{type(e).__name__}: {e}"
                    self._log(f"[{index}/{total}] Lỗi: {item['error']}")
                return item

            def collect_item(item: dict) -> None:
                nonlocal export_dir
                items.append(item)
                self.item_done.emit(item)
                if item.get("ok"):
                    if item.get("export_dir"):
                        export_dir = Path(str(item["export_dir"]))
                    plan_costs = []
                    try:
                        report = json.loads(Path(str(item.get("report", ""))).read_text(encoding="utf-8"))
                        if isinstance(report.get("ai_costs"), list):
                            plan_costs = report.get("ai_costs", [])
                    except Exception:
                        plan_costs = []
                    all_costs.extend(plan_costs)

            batch_started_at = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                pending = set()
                next_pos = 0
                stopping = False
                while next_pos < total and len(pending) < concurrency:
                    index = next_pos + 1
                    pending.add(executor.submit(process_one, index, paths[next_pos]))
                    next_pos += 1

                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        if future.cancelled():
                            continue
                        collect_item(future.result())

                    if not stopping and (self._cancelled or self.isInterruptionRequested()):
                        stopping = True
                        self._log("Batch đang dừng, không submit thêm job mới.")
                        for future in pending:
                            future.cancel()
                        pending = {future for future in pending if not future.cancelled()}
                        continue

                    while not stopping and next_pos < total and len(pending) < concurrency:
                        index = next_pos + 1
                        pending.add(executor.submit(process_one, index, paths[next_pos]))
                        next_pos += 1

            items.sort(key=lambda item: paths.index(item.get("source")) if item.get("source") in paths else 10**9)

            export_dir.mkdir(parents=True, exist_ok=True)
            ok_count = sum(1 for item in items if item.get("ok"))
            ready_count = sum(1 for item in items if item.get("ok") and item.get("final_status") == "ready")
            needs_review_count = sum(1 for item in items if item.get("ok") and item.get("final_status") == "needs_review")
            cancelled_items = sum(1 for item in items if item.get("cancelled"))
            failed_count = sum(1 for item in items if not item.get("ok") and not item.get("cancelled"))
            skipped_count = max(0, total - len(items))
            batch_total_seconds = round(time.perf_counter() - batch_started_at, 3)
            render_total_seconds = round(sum(float(item.get("render_seconds") or 0.0) for item in items), 3)
            render_job_total_seconds = round(sum(float(item.get("render_total_seconds") or 0.0) for item in items), 3)
            rendered_items = [item for item in items if float(item.get("render_realtime_factor") or 0.0) > 0]
            avg_realtime_factor = round(
                sum(float(item.get("render_realtime_factor") or 0.0) for item in rendered_items) / len(rendered_items),
                3,
            ) if rendered_items else 0.0
            ai_cost_total = _sum_ai_costs(all_costs)
            summary = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "total": total,
                "total_selected": total,
                "processed": len(items),
                "ok": ok_count,
                "ready": ready_count,
                "needs_review": needs_review_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "cancelled": bool(self._cancelled or self.isInterruptionRequested() or cancelled_items or skipped_count),
                "export_dir": str(export_dir),
                "batch_total_seconds": batch_total_seconds,
                "render_total_seconds": render_total_seconds,
                "render_job_total_seconds": render_job_total_seconds,
                "render_avg_realtime_factor": avg_realtime_factor,
                "disk_preflight": {
                    "free_bytes": free_bytes,
                    **disk_estimate,
                },
                "ai_cost_total": ai_cost_total,
                "ai_cost_by_kind": _sum_ai_costs_by_kind(all_costs),
                "items": items,
            }
            summary_path = export_dir / f"batch-summary-{datetime.now().strftime('%H%M%S')}.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            self.progress.emit(100)
            self._log(f"Batch xong: {ok_count}/{len(items)} video")
            self.finished.emit(str(summary_path))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def cancel(self):
        self._cancelled = True
        with self._active_lock:
            workers = list(self._active_workers)
        for worker in workers:
            try:
                if hasattr(worker, "cancel"):
                    worker.cancel()
            except Exception:
                pass
            try:
                worker.requestInterruption()
            except Exception:
                pass
