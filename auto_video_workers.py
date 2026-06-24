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
from oneshot_engine import (
    build_enterprise_artifacts,
    evaluate_render_gate,
    write_blocked_before_render_report,
)


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

ONE_SHOT_PIPELINE_VERSION = "3.0-certified-script-first"
ONE_SHOT_SIMPLE_PIPELINE_VERSION = "4.0-simple"

_FFMPEG_ENCODERS_CACHE: set[str] | None = None
_WHISPER_MODEL_CACHE: dict[str, object] = {}
_WHISPER_MODEL_LOCK = threading.Lock()
_WHISPER_TRANSCRIBE_LOCK = threading.Lock()
_THUMB_TRAILING_BAD_WORDS = {
    "HOẶC", "VA", "VÀ", "VỚI", "ĐỂ", "DE", "THÌ", "THI", "CỦA", "CUA", "CHO",
    "TRÊN", "TREN", "Ở", "O", "LÀ", "LA", "MÀ", "MA", "GIÁ", "GIA", "CHỈ",
    "CHI", "TỪ", "TU", "CÓ", "CO", "ĐÈN", "DEN", "KHÔNG", "KHONG", "CẦN", "CAN",
    "DÂY", "DAY", "ĐIỆN", "DIEN", "ĐỠ", "DO", "LED", "SẠC", "SAC",
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
    "ANH EM NÈ ",
    "ANH EM NE ",
    "CÁC BẠN ",
    "CAC BAN ",
)
_THUMB_TECH_TERM_REPLACEMENTS = [
    (r"\bM[ÔO]\s+M[ÔO]\b", "MOMO"),
    (r"\bMO\s+MO\b", "MOMO"),
    (r"\bM[ÂA]U\s+M[ÔO]\b", "MOMO"),
    (r"\bM[ÂA]U\s+MO\b", "MOMO"),
    (r"\bLOAN\s+MOMO\b", "LOA MOMO"),
    (r"\bLOAN\s+M[ÂA]U\s+M[ÔO]\b", "LOA MOMO"),
    (r"\bMOMO\b", "MOMO"),
    (r"\bZALO\s+PAY\b", "ZALOPAY"),
    (r"\bZALOPAY\b", "ZALOPAY"),
    (r"\bSHOPEE\s+PAY\b", "SHOPEEPAY"),
    (r"\bSHOPPE\s+PAY\b", "SHOPEEPAY"),
    (r"\bSHOPEEPAY\b", "SHOPEEPAY"),
    (r"\bVI[ỆE]T\s*QR\b", "VIETQR"),
    (r"\bVIET\s*QR\b", "VIETQR"),
    (r"\bQR\b", "QR"),
    (r"\bX[ÓO]P\b", "XỐP"),
    (r"\bC[ỤU]N\s*A\s*6\b", "KHAY A6"),
    (r"\bCUN\s*A\s*6\b", "KHAY A6"),
    (r"\bC[ỤU]N\s*A\s*7\b", "KHAY A7"),
    (r"\bCUN\s*A\s*7\b", "KHAY A7"),
    (r"\bC[ỤU]N\s+TR[ÒO]N\b", "CUỘN TRÒN"),
    (r"\bCUN\s+TRON\b", "CUỘN TRÒN"),
    (r"\bTAC\s+Đ[ỊI]NH\s+V[ỊI]\b", "TAG ĐỊNH VỊ"),
    (r"\bĐ[ỊI]NH\s+V[ỊI]\s+TAC\b", "ĐỊNH VỊ TAG"),
    (r"\bBAY\s*FAST\b", "BAYFAST"),
    (r"\bB[AE]Y\s*FAST\b", "BAYFAST"),
    (r"\bK[IÍ]\s*NH\s*C[UƯ][OỜ]NG\s*L[UỰ]C\b", "KÍNH CƯỜNG LỰC"),
    (r"\bD[ÁA]N\s*K[IÍ]\s*NH\b", "DÁN KÍNH"),
    (r"\bMI[ẾE]NG\s*D[ÁA]N\b", "MIẾNG DÁN"),
    (r"\b[ÔO]P\s*ĐI[ỆE]N\s*THO[ẠA]I\b", "ỐP ĐIỆN THOẠI"),
    (r"\b[ỐÔO]C\s*ĐI[ỆE]N\s*THO[ẠA]I\b", "ỐP ĐIỆN THOẠI"),
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
    (r"\bDJI\s+OSMO\s+NANO\b", "DJI OSMO NANO"),
    (r"\bOSMO\s+NANO\b", "OSMO NANO"),
    (r"\bỐT\s+MUÔN\s+ANO\b", "OSMO NANO"),
    (r"\bOT\s+MUON\s+ANO\b", "OSMO NANO"),
    (r"\bOTMOLANO\b", "OSMO NANO"),
    (r"\bOTMO\s*LANO\b", "OSMO NANO"),
    (r"\bOSMO\s+MỘT\b", "OSMO NANO"),
    (r"\bOSMO\s+MOT\b", "OSMO NANO"),
    (r"\bOSMO\s+ANO\b", "OSMO NANO"),
    (r"\bÔS\s*MÔ\b", "OSMO"),
    (r"\bOSMO\s+ACTION\b", "OSMO ACTION"),
    (r"\bD\s*[- ]?\s*LOG\s*M\b", "D-LOG M"),
    (r"\bREC\s*[- .]?\s*709\b", "REC.709"),
    (r"\bTU\s+VIT\b", "TUA VÍT"),
    (r"\bTÔ\s+VÍT\b", "TUA VÍT"),
    (r"\bTO\s+VIT\b", "TUA VÍT"),
    (r"(?<!TUA\s)\bVÍT\s+XIAOMI\b", "TUA VÍT XIAOMI"),
]
_THUMB_KNOWN_BRANDS = {
    "ANKER", "BASEUS", "UGREEN", "XIAOMI", "SAMSUNG", "IPHONE", "APPLE",
    "DJI", "OSMO", "ESR", "MCDODO", "ORICO", "AUKC", "HYPERDRIVE",
}
_THUMB_PROTECTED_PHRASES = (
    "DJI OSMO NANO",
    "OSMO NANO",
    "OSMO ACTION",
    "POCKET 3",
    "D-LOG M",
    "REC.709",
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
    "LOA THANH TOÁN",
    "GIẤY PHÉP",
    "KÍNH CƯỜNG LỰC",
    "MIẾNG DÁN",
    "DÁN KÍNH",
    "ỐP ĐIỆN THOẠI",
    "BAYFAST",
    "XỐP ĐÓNG GÓI",
    "HÀNG DỄ VỠ",
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
    "TAI NGHE CÓ DÂY",
    "KHÔNG CẦN SẠC PIN",
    "KHÔNG LO SẠC PIN",
    "ĐÈN LED",
    "QUẠT LED",
    "QUẠT RGB",
    "GÓC SETUP",
    "CHO GÓC SETUP",
    "GIÁ ĐỠ ĐIỆN THOẠI",
    "SẠC IPHONE",
    "SẠC MACBOOK",
    "SẠC DỰ PHÒNG",
    "SẠC KHÔNG DÂY",
    "ĐẦU TYPE-C CO GÓC",
    "CO GÓC TYPE-C",
    "HUB 5IN1",
    "HUB USB-C",
    "GIÁ ĐỠ ĐIỆN THOẠI",
    "GIÁ ĐIỆN THOẠI",
    "KẸP DÂY",
    "CÔNG TẮC",
    "CỔ DÊ",
    "CO NHIỆT",
    "BỘ CO NHIỆT",
    "BỌC DÂY CO NHIỆT",
    "TAG ĐỊNH VỊ",
    "THIẾT BỊ ĐỊNH VỊ",
)
_THUMB_SEMANTIC_PHRASES = tuple(
    sorted(set(_THUMB_PROTECTED_PHRASES) | {
        "CHUỘT KHÔNG DÂY",
        "KHÔNG CẦN THAY PIN",
        "KHÔNG CẦN",
        "THAY PIN",
        "SẠC PIN",
        "CẦN THAY PIN",
        "GIÁ RẺ",
        "GIÁ HỢP LÝ",
        "GỌN HƠN",
        "GỌN ĐẸP",
        "LINH HOẠT",
        "DỄ LẮP",
        "DỄ LẮP ĐI",
        "TRANG TRÍ PHÒNG",
        "MÀU SẮC ĐỘC ĐÁO",
    }, key=lambda item: (-len(item.split()), -len(item), item))
)
_FINANCE_TERM_REPLACEMENTS = [
    (r"\bVI\s*N\s*INDEX\b", "VNINDEX"),
    (r"\bVN\s*INDEX\b", "VNINDEX"),
    (r"\bVNI\b", "VNINDEX"),
    (r"\bBIT\s*COIN\b", "BITCOIN"),
    (r"\bBTC\b", "BTC"),
    (r"\bETH\b", "ETH"),
    (r"\bETF\b", "ETF"),
    (r"\bFED\b", "FED"),
    (r"\bCPI\b", "CPI"),
    (r"\bDCA\b", "DCA"),
    (r"\bFUNDING\b", "FUNDING"),
    (r"\bLEVERAGE\b", "LEVERAGE"),
    (r"\bSPOT\b", "SPOT"),
    (r"\bFUTURES?\b", "FUTURES"),
    (r"\bSTOP\s*LOSS\b", "STOP LOSS"),
    (r"\bRISK\s*/\s*REWARD\b", "RISK/REWARD"),
]
_FINANCE_FORBIDDEN_CLAIM_PATTERNS = (
    r"\bCHẮC\s+THẮNG\b",
    r"\bCHAC\s+THANG\b",
    r"\bLỢI\s+NHUẬN\s+ĐẢM\s+BẢO\b",
    r"\bLOI\s+NHUAN\s+DAM\s+BAO\b",
    r"\bCAM\s+KẾT\s+LÃI\b",
    r"\bCAM\s+KET\s+LAI\b",
    r"\bX\s*\d+\s+TÀI\s+KHOẢN\b",
    r"\bX\s*\d+\s+TAI\s+KHOAN\b",
    r"\bALL\s*IN\b",
)
# Natural noise reduction — CapCut-style two-stage:
# 1. Gentle afftdn with noise-floor tracking (spectral subtraction)
# 2. anlmdn for smooth natural cleanup (non-local means)
# 3. Voice EQ to restore clarity lost in denoising
# 4. Soft compressor for consistent loudness
# CapCut-style noise reduction: 2-stage denoise + voice EQ + gentle leveling
_NOISE_FILTER_AUTO_GENTLE = (
    "highpass=f=40,"
    "afftdn=nr=10:nf=-35:tn=1,"
    "anlmdn=s=0.00015:p=0.03:r=0.015,"
    "equalizer=f=2500:t=q:w=0.8:g=1.5,"
    "equalizer=f=8000:t=q:w=1.0:g=1.0,"
    "acompressor=threshold=-20dB:ratio=1.3:attack=20:release=140,"
    "volume=2dB"
)
_NOISE_FILTER_STRONG = (
    "highpass=f=50,"
    "afftdn=nr=15:nf=-30:tn=1,"
    "anlmdn=s=0.0003:p=0.04:r=0.02,"
    "equalizer=f=2500:t=q:w=1.0:g=2.5,"
    "equalizer=f=8000:t=q:w=1.2:g=1.5,"
    "acompressor=threshold=-18dB:ratio=1.6:attack=15:release=130,"
    "volume=3dB"
)
_USD_TO_VND = 26000
_DEEPSEEK_PRICES = {
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"input": 0.435, "output": 0.87},
}


def _deepseek_script_model(settings: dict | None = None, engine_env: dict | None = None) -> str:
    model = ""
    if isinstance(engine_env, dict):
        model = str(engine_env.get("DEEPSEEK_SCRIPT_MODEL", "") or "").strip()
    if not model and isinstance(settings, dict):
        model = str(settings.get("deepseek_script_model", "") or "").strip()
    if model in {"", "deepseek-chat", "deepseek-reasoner"}:
        return "deepseek-v4-flash"
    return model if model in _DEEPSEEK_PRICES else "deepseek-v4-flash"


_GEMINI_PRICES = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
}
_MEDIA_TOOL_NAMES = {"ffmpeg", "ffprobe"}
_MEDIA_TOOL_CACHE: dict[str, str] = {}


def _redact_secret_text(text: object) -> str:
    out = str(text)
    out = re.sub(r"([?&]key=)[^&\s'\"]+", r"\1***", out, flags=re.IGNORECASE)
    out = re.sub(r"(Authorization['\"]?\s*[:=]\s*['\"]?Bearer\s+)[^'\"\s,}]+", r"\1***", out, flags=re.IGNORECASE)
    out = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1***", out, flags=re.IGNORECASE)
    return out


def whisper_runtime_status(settings: dict | None = None) -> dict:
    settings = settings or {}
    model = str(settings.get("one_shot_whisper_model", "small") or "small").strip() or "small"
    media = _media_tools_report(settings)
    if not media.get("ffmpeg"):
        return {"status": "missing_ffmpeg", "label": "Thiếu ffmpeg", "detail": "Không tìm thấy ffmpeg để tách audio.", "media_tools": media}
    if not media.get("ffprobe"):
        return {"status": "missing_ffprobe", "label": "Thiếu ffprobe", "detail": "Không tìm thấy ffprobe để đọc video.", "media_tools": media}
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
        vad_asset = _resolve_faster_whisper_vad_asset()
        if not vad_asset.exists():
            return {
                "status": "missing_vad_asset",
                "label": "Thiếu VAD asset",
                "detail": f"Thiếu {vad_asset}. Whisper sẽ retry không VAD nếu vẫn chạy được.",
                "model": model,
                "media_tools": media,
            }
    except Exception as exc:
        return {
            "status": "missing_package",
            "label": "Thiếu package",
            "detail": f"Không kiểm tra được faster-whisper asset: {exc}",
            "model": model,
            "media_tools": media,
        }
    return {
        "status": "ready",
        "label": "Sẵn sàng",
        "detail": f"Whisper local đã sẵn sàng. Model: {model}.",
        "model": model,
        "media_tools": media,
    }


def _load_whisper_model(model_size: str, log=None):
    _patch_faster_whisper_vad_asset(log)
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


def _resource_roots() -> list[Path]:
    roots: list[Path] = []

    def add(path: Path | str | None) -> None:
        if not path:
            return
        try:
            p = Path(path).resolve()
        except Exception:
            return
        if p not in roots:
            roots.append(p)

    try:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            add(Path(sys._MEIPASS))  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        add(exe_dir)
        add(exe_dir.parent / "Resources")
        add(exe_dir.parent / "Frameworks")
        add(exe_dir.parent)
    except Exception:
        pass
    add(Path(__file__).resolve().parent)
    return roots


def _resource_root() -> Path:
    for root in _resource_roots():
        if (root / "assets").exists() or (root / "luts").exists() or (root / "faster_whisper").exists():
            return root
    return _resource_roots()[0]


def _resource_path_candidates(*parts: str) -> list[Path]:
    return [root.joinpath(*parts) for root in _resource_roots()]


def _configured_media_path(name: str, settings: dict | None = None) -> str:
    settings = settings or {}
    env_key = f"HEDRA_{name.upper()}_PATH"
    for raw in (
        os.environ.get(env_key, ""),
        os.environ.get(f"{name.upper()}_PATH", ""),
        settings.get(f"one_shot_{name}_path", ""),
        settings.get(f"{name}_path", ""),
    ):
        text = str(raw or "").strip()
        if text and Path(text).expanduser().exists():
            return str(Path(text).expanduser().resolve())
    return ""


def _media_binary(name: str, settings: dict | None = None) -> str:
    base = Path(name).name
    if base not in _MEDIA_TOOL_NAMES:
        return name
    cache_key = f"{base}:{id(settings) if settings else 0}"
    if not settings and base in _MEDIA_TOOL_CACHE:
        return _MEDIA_TOOL_CACHE[base]

    candidates: list[str] = []
    configured = _configured_media_path(base, settings)
    if configured:
        candidates.append(configured)
    for path in (
        *_resource_path_candidates("bin", base),
        *_resource_path_candidates("media", base),
        *_resource_path_candidates(base),
        Path("/opt/homebrew/bin") / base,
        Path("/usr/local/bin") / base,
        Path("/usr/bin") / base,
    ):
        candidates.append(str(path))
    shell_found = shutil.which(base, path=_shell_path())
    if shell_found:
        candidates.append(shell_found)

    for raw in candidates:
        try:
            path = Path(raw).expanduser()
            if path.exists() and os.access(path, os.X_OK):
                resolved = str(path.resolve())
                if not settings:
                    _MEDIA_TOOL_CACHE[base] = resolved
                return resolved
        except Exception:
            continue
    return ""


def _media_tools_report(settings: dict | None = None) -> dict:
    ffmpeg_path = _media_binary("ffmpeg", settings)
    ffprobe_path = _media_binary("ffprobe", settings)
    return {
        "ffmpeg": ffmpeg_path,
        "ffprobe": ffprobe_path,
        "ffmpeg_ok": bool(ffmpeg_path),
        "ffprobe_ok": bool(ffprobe_path),
        "shell_path": _shell_path(),
    }


def _resolve_faster_whisper_vad_asset() -> Path:
    candidates: list[Path] = []
    try:
        import faster_whisper  # type: ignore
        candidates.append(Path(faster_whisper.__file__).resolve().parent / "assets" / "silero_vad_v6.onnx")
    except Exception:
        pass
    candidates.extend(_resource_path_candidates("faster_whisper", "assets", "silero_vad_v6.onnx"))
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else Path("faster_whisper/assets/silero_vad_v6.onnx")


def _patch_faster_whisper_vad_asset(log=None) -> Path:
    asset = _resolve_faster_whisper_vad_asset()
    if not asset.exists():
        return asset
    try:
        import faster_whisper.utils as fw_utils  # type: ignore
        import faster_whisper.vad as fw_vad  # type: ignore
        asset_dir = str(asset.parent)
        fw_utils.get_assets_path = lambda: asset_dir  # type: ignore[assignment]
        fw_vad.get_assets_path = lambda: asset_dir  # type: ignore[assignment]
        if log:
            log(f"Whisper VAD asset: {asset}")
    except Exception as exc:
        if log:
            log(f"Không patch được Whisper VAD asset path: {exc}")
    return asset


def _top_disk_usage_hints(root: Path, limit: int = 5) -> list[dict]:
    hints: list[dict] = []
    try:
        candidates = [p for p in root.iterdir() if p.is_dir()]
    except Exception:
        candidates = []
    for path in candidates:
        total = 0
        try:
            for child in path.rglob("*"):
                if child.is_file():
                    try:
                        total += child.stat().st_size
                    except Exception:
                        pass
        except Exception:
            continue
        hints.append({"path": str(path), "bytes": total, "size": _format_gb(total)})
    hints.sort(key=lambda item: int(item.get("bytes") or 0), reverse=True)
    return hints[:limit]


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
        prices = _DEEPSEEK_PRICES.get(model) or _DEEPSEEK_PRICES.get("deepseek-v4-flash", {})
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
    industry = _one_shot_industry(settings)

    if industry == "finance":
        finance_text = _ascii_upper(f"{title} {_thumbnail_context_text(source_title, segments)}")
        if "BTC" in finance_text or "BITCOIN" in finance_text:
            _append_hashtag(tags, "#Bitcoin")
            _append_hashtag(tags, "#BTC")
        if "ETH" in finance_text or "ETHEREUM" in finance_text:
            _append_hashtag(tags, "#Ethereum")
        if "VNINDEX" in finance_text or "CHUNG KHOAN" in finance_text or "CỔ PHIẾU" in _plain_upper(finance_text):
            _append_hashtag(tags, "#ChungKhoan")
            _append_hashtag(tags, "#VNIndex")
        if any(token in finance_text for token in ("FED", "CPI", "LAI SUAT", "LÃI SUẤT", "VI MO")):
            _append_hashtag(tags, "#TaiChinh")
            _append_hashtag(tags, "#ViMo")
        if any(token in finance_text for token in ("RUI RO", "RỦI RO", "STOP LOSS", "DCA", "FUNDING", "LEVERAGE")):
            _append_hashtag(tags, "#QuanTriRuiRo")
        _append_hashtag(tags, "#DauTu")
        _append_hashtag(tags, "#TaiChinh")
        return tags[:3]

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
    title_is_phone_case = (
        title_context.startswith(("ỐP ", "OP "))
        or any(key in title_context for key in ("OP IEN THOAI", "OP DIEN THOAI", "ỐP ĐIỆN THOẠI", "OP LUNG", "ỐP LƯNG"))
    )
    if title_is_phone_case:
        _append_hashtag(tags, "#OpDienThoai")
        _append_hashtag(tags, "#BaoVeDienThoai")
    if not title_is_phone_case and any(key in context for key in ("KINH CUONG LUC", "KÍNH CƯỜNG LỰC", "DAN KINH", "DÁN KÍNH", "MIENG DAN", "MIẾNG DÁN", "BAYFAST")):
        _append_hashtag(tags, "#KinhCuongLuc")
        if "BAYFAST" in context:
            _append_hashtag(tags, "#BayFast")
        if "DAN" in context or "DÁN" in context or "MIENG DAN" in context or "MIẾNG DÁN" in context:
            _append_hashtag(tags, "#DanDienThoai")
    if not title_is_phone_case and any(key in context for key in ("OP DIEN THOAI", "OP IEN THOAI", "ỐP ĐIỆN THOẠI", "OP LUNG", "ỐP LƯNG", "OP BAO VE", "ỐP BẢO VỆ", "OC DIEN THOAI", "OC IEN THOAI")):
        _append_hashtag(tags, "#OpDienThoai")
        _append_hashtag(tags, "#BaoVeDienThoai")
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
    thumbnail_title = _normalize_industry_title_terms(thumbnail_title, settings)
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


def _one_shot_industry(settings: dict | None = None) -> str:
    settings = settings or {}
    industry = str(settings.get("one_shot_industry") or settings.get("industry") or "tech").strip().lower()
    return "finance" if industry == "finance" else "tech"


def _normalize_industry_title_terms(title: str, settings: dict | None = None) -> str:
    out = str(title or "")
    if _one_shot_industry(settings) == "finance":
        for pattern, repl in _FINANCE_TERM_REPLACEMENTS:
            out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip()


def _finance_claim_flags(title: str, context: str = "") -> list[str]:
    clean = _plain_upper(title)
    clean_ascii = _ascii_upper(clean)
    context_fixed = _plain_upper(context)
    context_ascii = _ascii_upper(context_fixed)
    flags: list[str] = []
    for pattern in _FINANCE_FORBIDDEN_CLAIM_PATTERNS:
        if re.search(pattern, clean, flags=re.IGNORECASE) or re.search(pattern, clean_ascii, flags=re.IGNORECASE):
            flags.append("finance_unsafe_profit_claim")
            break
    if re.search(r"\b(?:MUA|BUY|LONG|SHORT|BÁN|SELL)\s+(?:NGAY|GẤP|NOW)\b", clean_ascii):
        if not re.search(r"\b(?:MUA|BUY|LONG|SHORT|BÁN|SELL)\s+(?:NGAY|GẤP|NOW)\b", context_ascii):
            flags.append("finance_action_claim_without_evidence")
    if any(token in clean_ascii for token in ("TIN HIEU MUA", "TIN HIEU BAN", "SIGNAL")) and not any(
        token in context_ascii for token in ("TIN HIEU", "SIGNAL")
    ):
        flags.append("finance_signal_without_evidence")
    if re.search(r"\b\d+\s*%\b", clean_ascii) and not re.search(r"\b\d+\s*%\b", context_ascii):
        flags.append("finance_percent_without_evidence")
    return flags


def _industry_qa_report(
    title: str,
    source_title: str,
    segments: list[dict] | None = None,
    settings: dict | None = None,
) -> dict:
    industry = _one_shot_industry(settings)
    context = _thumbnail_context_text(source_title, segments)
    normalized_title = _normalize_industry_title_terms(title, {"industry": industry})
    flags: list[str] = []
    reasons: list[str] = []
    if normalized_title != title:
        reasons.append("chuẩn hóa thuật ngữ ngành")
    if industry == "finance":
        flags.extend(_finance_claim_flags(normalized_title, context))
        if not flags:
            reasons.append("finance expert: hook chuyển đổi an toàn")
    else:
        reasons.append("tech expert: thuật ngữ công nghệ/affiliate")
    status = "needs_review" if flags else ("auto_repaired" if normalized_title != title else "ready")
    return {
        "industry": industry,
        "status": status,
        "ok": not flags,
        "normalized_title": normalized_title,
        "flags": flags,
        "reasons": reasons or ["industry gate OK"],
    }


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
        text = " ".join(words)
        if any(text.endswith(phrase) for phrase in _THUMB_SEMANTIC_PHRASES):
            break
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
        (r"\bQUẠC\b", "QUẠT"),
        (r"\bQUAC\b", "QUẠT"),
        (r"\bLEP\b", "LED"),
        (r"\bUGRENE\b", "UGREEN"),
        (r"\bMIẾN\s+RÉN\b", "MIẾNG DÁN"),
        (r"\bMIẾNG\s+REN\b", "MIẾNG DÁN"),
        (r"\bCHÁY\s+XƯỚC\b", "TRẦY XƯỚC"),
        (r"\bCHAY\s+XUOC\b", "TRẦY XƯỚC"),
        (r"\bGÓI\s+SETUP\b", "GÓC SETUP"),
        (r"\bGOI\s+SETUP\b", "GÓC SETUP"),
        (r"\bMACBOOK\s+AC\b", "MACBOOK"),
        (r"\bMÀU\s+LÉP\b", "MÀU LED"),
        (r"\bMAU\s+LEP\b", "MÀU LED"),
        (r"\bSỨC\s+NẤM\b", "SỨC NÓNG"),
        (r"\bSUC\s+NAM\b", "SỨC NÓNG"),
        (r"\bĐÁP\s+(DJI|OSMO)\b", r"SETUP \1"),
        (r"\bDAP\s+(DJI|OSMO)\b", r"SETUP \1"),
        (r"\bQUẠC\b", "QUẠT"),
        (r"\bQUAC\b", "QUẠT"),
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
    if "DJI OSMO NANO" in upper or "OSMO NANO" in upper:
        return "DJI OSMO NANO"
    if "OSMO ACTION" in upper:
        return "OSMO ACTION"
    if "POCKET 3" in upper or "DJI POCKET 3" in upper:
        return "DJI POCKET 3"
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


def _full_transcript_text(segments: list[dict] | None = None) -> str:
    return " ".join(str(seg.get("text", "")) for seg in (segments or []) if str(seg.get("text", "")).strip())


def _context_is_fan_or_light(context: str) -> bool:
    ascii_ctx = _ascii_upper(context)
    return bool(re.search(r"\b(QUAT|QUAC|FAN|BONG DEN|DEN LED|LED|TRANG TRI)\b", ascii_ctx))


def _human_content_brief(source_title: str, segments: list[dict] | None = None) -> dict:
    """Summarize the whole video in the same order a human reviewer would."""
    full = _fix_common_title_misreads(_plain_upper(_full_transcript_text(segments) or source_title))
    early = _fix_common_title_misreads(_plain_upper(_early_thumbnail_context(segments)))
    full_ascii = _ascii_upper(full)
    early_ascii = _ascii_upper(early)
    text_for_hook = early or full

    if "BĂNG KEO" in full or "BANG KEO" in full_ascii or re.search(r"\bTAPE\b", full_ascii):
        if any(token in full for token in ("IN SẴN", "IN CHỮ", "IN LOGO", "CHỮ")) or any(
            token in full_ascii for token in ("IN SAN", "IN CHU", "IN LOGO", "CHU")
        ):
            return {"product": "BĂNG KEO", "hook": "IN SẴN CHỮ", "confidence": 0.86}
        if "ĐÓNG GÓI" in full or "DONG GOI" in full_ascii:
            return {"product": "BĂNG KEO", "hook": "ĐÓNG GÓI TIỆN LỢI", "confidence": 0.82}
        return {"product": "BĂNG KEO", "hook": "TIỆN LỢI", "confidence": 0.76}
    if "OSMO NANO" in full or "OSMO ACTION" in full:
        product = _extract_known_product_context(full) or "DJI OSMO"
        if any(key in text_for_hook for key in ("DÁN", "DAN", "BẢO VỆ", "BAO VE", "TRẦY", "TRAY", "XƯỚC", "XUOC")):
            return {"product": product, "hook": "DÁN BẢO VỆ", "confidence": 0.9}
        if any(key in text_for_hook for key in ("SỨC NÓNG", "SUC NONG", "HẾT HOT", "CHÁY HÀNG", "CHAY HANG")):
            return {"product": product, "hook": "SỨC NÓNG", "confidence": 0.84}
        if any(key in full for key in ("LUT", "LÚT", "MÀU", "D-LOG", "REC.709")):
            return {"product": product, "hook": "LUT MÀU ĐẸP", "confidence": 0.78}
        return {"product": product, "hook": "CÓ ĐÁNG MUA", "confidence": 0.74}
    if any(token in full for token in ("ĐÈN", "BÓNG ĐÈN", "VINACO", "VINAKO", "CON ĐEN")) or any(
        token in full_ascii for token in ("DEN LED", "BONG DEN", "CON DEN", "VINACO", "VINAKO")
    ):
        if "30.000" in full or "30000" in full_ascii:
            return {"product": "ĐÈN LED", "hook": "BỀN 30.000 GIỜ", "confidence": 0.82}
        if "BẢO HÀNH" in full or "BAO HANH" in full_ascii:
            return {"product": "BÓNG ĐÈN VINACO", "hook": "CÓ BẢO HÀNH", "confidence": 0.82}
        return {"product": "ĐÈN LED", "hook": "SÁNG BỀN", "confidence": 0.78}
    if "KHAY" in full or "A6" in full_ascii or "KHUNG NHỰA" in full or "KHUNG NHUA" in full_ascii:
        if "KHUNG" in full or "KHUNG NHUA" in full_ascii:
            return {"product": "KHUNG NHỰA A6", "hook": "GỌN QUẦY BÁN", "confidence": 0.8}
        return {"product": "KHAY A6", "hook": "CHIA HÀNG GỌN", "confidence": 0.82}
    if "QUẠT" in full or "QUẠC" in full or re.search(r"\bFAN\b", full_ascii):
        if any(token in full + " " + full_ascii for token in ("NÓNG", "NONG", "MÁT", "MAT", "TẢN NHIỆT", "TAN NHIET", "LÀM MÁT", "LAM MAT")):
            if "DEX" in full_ascii:
                return {"product": "QUẠT LED", "hook": "LÀM MÁT BOX DEX", "confidence": 0.88}
            return {"product": "QUẠT LED", "hook": "LÀM MÁT PC", "confidence": 0.86}
        if "LED" in full_ascii or "MÀU" in full or "MAU" in full_ascii:
            return {"product": "QUẠT LED", "hook": "TRANG TRÍ GÓC SETUP", "confidence": 0.86}
        return {"product": "QUẠT", "hook": "TRANG TRÍ GÓC SETUP", "confidence": 0.82}
    if (
        any(token in full for token in ("TAG ĐỊNH VỊ", "THẺ ĐỊNH VỊ", "THIẾT BỊ ĐỊNH VỊ", "ĐỊNH VỊ", "CÁI TAG", "HAY TAG", "TAG NÀY"))
        or any(token in full_ascii for token in ("TAG DINH VI", "THE DINH VI", "THIET BI DINH VI", "DINH VI", "CAI TAG", "HAY TAG", "TAG NAY", "X8"))
    ) and any(
        token in full + " " + full_ascii
        for token in (
            "IPHONE", "ANDROID", "NGƯỜI GIÀ", "NGƯỜI LỚN TUỔI", "BO ME", "BỐ MẸ",
            "XE", "CHÌA KHÓA", "CHIA KHOA", "VẬT DỤNG", "VAT DUNG", "TÌM", "TIM",
            "THẤT LẠC", "THAT LAC", "CHỈ ĐƯỜNG", "CHI DUONG", "PHÁT ÂM THANH", "PHAT AM THANH",
        )
    ):
        if any(token in full + " " + full_ascii for token in ("NGƯỜI GIÀ", "NGƯỜI LỚN TUỔI", "BO ME", "BỐ MẸ", "NGƯỜI THÂN", "GIA ĐÌNH", "GIA DINH")):
            return {"product": "TAG ĐỊNH VỊ", "hook": "TRÁNH THẤT LẠC NGƯỜI THÂN", "confidence": 0.88}
        if any(token in full + " " + full_ascii for token in ("XE", "CHÌA KHÓA", "CHIA KHOA")):
            return {"product": "TAG ĐỊNH VỊ", "hook": "TÌM XE CHÌA KHÓA", "confidence": 0.86}
        return {"product": "TAG ĐỊNH VỊ", "hook": "HỖ TRỢ IPHONE ANDROID", "confidence": 0.84}
    # Phone case detection — phrases + "ốc ... điện thoại" pattern
    phone_case_full = (
        "ỐP ĐIỆN THOẠI" in full
        or "ỐC ĐIỆN THOẠI" in full
        or "OC DIEN THOAI" in full_ascii
        or "OP DIEN THOAI" in full_ascii
        or "ỐP LƯNG" in full
        or "OP LUNG" in full_ascii
        or ("ỐC" in full and "ĐIỆN THOẠI" in full and "GIÁ ĐỠ" not in full and "GIÁ ĐIỆN THOẠI" not in full)  # "ốc ... điện thoại" but not phone stand
    )
    phone_case_early = (
        "ỐP ĐIỆN THOẠI" in early
        or "ỐC ĐIỆN THOẠI" in early
        or "OC DIEN THOAI" in early_ascii
        or "OP DIEN THOAI" in early_ascii
        or "ỐP LƯNG" in early
        or "OP LUNG" in early_ascii
    )
    if phone_case_full:
        if any(token in full + " " + full_ascii for token in ("TỪ TÍNH", "TU TINH", "HÚT", "HUT", "NAM CHÂM", "NAM CHAM", "DÍNH", "DINH")):
            return {"product": "ỐP ĐIỆN THOẠI TỪ TÍNH", "hook": "BÁM CHẮC KHÔNG RƠI", "confidence": 0.86}
        if "KÍNH" in full or "KINH" in full_ascii:
            return {"product": "ỐP ĐIỆN THOẠI", "hook": "CÓ KÍNH CƯỜNG LỰC", "confidence": 0.84}
        return {"product": "ỐP ĐIỆN THOẠI", "hook": "BẢO VỆ CHẮC CHẮN", "confidence": 0.82}
    if phone_case_early and any(
        token in early + " " + early_ascii
        for token in ("LỜI KHUYÊN", "LOI KHUYEN", "BẢO VỆ", "BAO VE", "RƠI", "ROI", "KHÔNG QUAN TRỌNG BẰNG", "KHONG QUAN TRONG BANG")
    ):
        return {"product": "ỐP ĐIỆN THOẠI", "hook": "BẢO VỆ MÁY KHI RƠI", "confidence": 0.86}
    if (
        "KÍNH CƯỜNG LỰC" in full
        or ("CƯỜNG LỰC" in full and any(token in full for token in ("DÁN", "KHUNG", "ĐIỆN THOẠI", "MIẾNG")))
        or "DÁN KÍNH" in full
        or "MIẾNG DÁN" in full
        or "BAYFAST" in full
        or ("XỐP" in full and any(token in full for token in ("KÍNH", "DÁN", "ĐÓNG GÓI")))
        or re.search(r"\b(KINH CUONG LUC|DAN KINH|MIENG DAN|BAYFAST|XOP)\b", full_ascii)
    ):
        if "XỐP" in full or "XOP" in full_ascii or "ĐÓNG GÓI" in full or "DONG GOI" in full_ascii:
            return {"product": "KÍNH CƯỜNG LỰC", "hook": "ĐÓNG GÓI CẨN THẬN", "confidence": 0.86}
        if "KHUNG" in full or "TỰ DÁN" in full or "TU DAN" in full_ascii:
            return {"product": "KÍNH CƯỜNG LỰC", "hook": "CÓ KHUNG TỰ DÁN", "confidence": 0.86}
        if "BAYFAST" in full:
            return {"product": "KÍNH CƯỜNG LỰC BAYFAST", "hook": "DỄ DÁN HƠN", "confidence": 0.84}
        return {"product": "KÍNH CƯỜNG LỰC", "hook": "BẢO VỆ ĐIỆN THOẠI", "confidence": 0.8}
    if "MOMO" in full or "MO MO" in full_ascii:
        if "GIẤY PHÉP" in full or "GIAY PHEP" in full_ascii:
            return {"product": "LOA MOMO", "hook": "CẦN GIẤY PHÉP", "confidence": 0.86}
        if "SIM 4G" in full or "4G" in full_ascii:
            return {"product": "LOA THANH TOÁN", "hook": "KÈM SIM 4G", "confidence": 0.84}
        return {"product": "LOA MOMO", "hook": "THANH TOÁN GỌN HƠN", "confidence": 0.8}
    context_has_hub = "HUB" in full or re.search(r"\bHAP\b", full_ascii) or re.search(r"\b5\s*(?:IN|IN1|TRONG)\s*1\b", full_ascii)
    if "OSMO NANO" in full or "OSMO ACTION" in full or ("POCKET 3" in full and not context_has_hub):
        product = _extract_known_product_context(full) or "DJI OSMO"
        if any(key in text_for_hook for key in ("DÁN", "DAN", "BẢO VỆ", "BAO VE", "TRẦY", "TRAY", "XƯỚC", "XUOC")):
            return {"product": product, "hook": "DÁN BẢO VỆ", "confidence": 0.9}
        if any(key in text_for_hook for key in ("SỨC NÓNG", "SUC NONG", "HẾT HOT", "CHÁY HÀNG", "CHAY HANG")):
            return {"product": product, "hook": "SỨC NÓNG", "confidence": 0.84}
        if any(key in full for key in ("LUT", "LÚT", "MÀU", "D-LOG", "REC.709")):
            return {"product": product, "hook": "LUT MÀU ĐẸP", "confidence": 0.78}
        return {"product": product, "hook": "CÓ ĐÁNG MUA", "confidence": 0.74}
    if re.search(r"\b(SOI CAP|DAY HDMI|CAP HDMI|DÂY HDMI|CÁP HDMI)\b", full_ascii) or re.search(r"\b(DÂY|CÁP)\s+HDMI\b", full):
        price = _extract_price_token(full)
        if price:
            return {"product": "CÁP HDMI", "hook": f"GIÁ {price}", "confidence": 0.88}
        if "8K" in full or "8K" in full_ascii:
            return {"product": "CÁP HDMI", "hook": "HỖ TRỢ 8K", "confidence": 0.82}
        if "4K" in full or "4K" in full_ascii:
            return {"product": "CÁP HDMI", "hook": "4K", "confidence": 0.8}
        return {"product": "CÁP HDMI", "hook": "GỌN BỀN", "confidence": 0.72}
    if any(term in full for term in ("BỘ CHUYỂN ĐỔI", "BO CHUYEN DOI", "ADAPTER", "DOCK")):
        if "SAMSUNG DEX" in full or "DEX" in full:
            return {"product": "BỘ CHUYỂN ĐỔI SAMSUNG DEX", "hook": "GỌN HƠN", "confidence": 0.8}
        return {"product": "BỘ CHUYỂN ĐỔI", "hook": "GỌN HƠN", "confidence": 0.76}
    if (
        "SAMSUNG DEX" in full
        and ("HUB" in full or re.search(r"\bHAP\b", full_ascii) or re.search(r"\b5\s*(?:IN|IN1|TRONG)\s*1\b", full_ascii))
    ):
        if "4K" in full:
            return {"product": "HUB SAMSUNG DEX", "hook": "XUẤT 4K", "confidence": 0.84}
        return {"product": "HUB SAMSUNG DEX", "hook": "GỌN SETUP", "confidence": 0.8}
    if (
        any(token in full for token in ("CO GÓC", "ĐẦU TYPE-C", "ĐẦU TAY C", "ĐẦU TAY SI", "TYPE-C CO GÓC"))
        or any(token in full_ascii for token in ("CO GOC", "DAU TYPE C", "DAU TAY C", "DAU TAY SI", "TYPE C CO GOC"))
    ) and any(token in full + " " + full_ascii for token in ("SAMSUNG DEX", "DEX", "TYPE-C", "TYPE C", "40GB", "100W")):
        if "100W" in full_ascii or "40GB" in full_ascii:
            return {"product": "ĐẦU TYPE-C CO GÓC", "hook": "100W GỌN SETUP DEX", "confidence": 0.86}
        return {"product": "ĐẦU TYPE-C CO GÓC", "hook": "GỌN SETUP DEX", "confidence": 0.84}
    if (
        any(token in full for token in ("CO NHIỆT", "CON NHIỆT", "BỘ CON NHIỆT", "BỌC DÂY", "CỐ ĐỊNH DÂY"))
        or any(token in full_ascii for token in ("CO NHIET", "CON NHIET", "BO CON NHIET", "BOC DAY", "CO DINH DAY"))
    ):
        if any(token in full + " " + full_ascii for token in ("164", "160", "NHIỀU KÍCH THƯỚC", "NHIEU KICH THUOC")):
            return {"product": "BỘ CO NHIỆT", "hook": "164 CHI TIẾT", "confidence": 0.88}
        return {"product": "BỌC DÂY CO NHIỆT", "hook": "GỌN ĐẸP HƠN", "confidence": 0.84}
    # WEBCAM must be checked BEFORE HUB — "4K" alone can be webcam
    if any(token in full for token in ("WEBCAM", "WEB CAM", "CAMERA", "WEB CAMERA", "CON CAM", "CÔNG CAM", "CONG CAM")) or (
        any(token in full for token in ("CAM", "QUAY", "CHỤP")) and any(token in full for token in ("NÉT", "NET", "CHẤT LƯỢNG", "CHAT LUONG", "ĐỘ PHÂN GIẢI", "DO PHAN GIAI"))
    ) or ("4K" in full and "CAM" in full and "HUB" not in full and "HAP" not in full_ascii):
        if "NẮP ĐẬY" in full or "NAP DAY" in full_ascii or "RIÊNG TƯ" in full or "RIENG TU" in full_ascii:
            return {"product": "WEBCAM 4K", "hook": "CÓ NẮP ĐẬY RIÊNG TƯ", "confidence": 0.86}
        if "BẮT NÉT" in full or "BAT NET" in full_ascii or "AUTO FOCUS" in full_ascii:
            return {"product": "WEBCAM 4K", "hook": "BẮT NÉT NHANH", "confidence": 0.86}
        if "CHÂN TƠ" in full or "CHAN TO" in full_ascii or "KẼ TÓC" in full or "KE TOC" in full_ascii:
            return {"product": "WEBCAM 4K", "hook": "SIÊU NÉT CẬN CẢNH", "confidence": 0.88}
        if "STREAMER" in full_ascii or "STREAM" in full_ascii:
            return {"product": "WEBCAM 4K", "hook": "CHO STREAMER", "confidence": 0.84}
        return {"product": "WEBCAM 4K", "hook": "SIÊU NÉT GIÁ TỐT", "confidence": 0.8}
    # MÁY HÚT BỤI — vacuum cleaner
    if any(token in full for token in ("MÁY HÚT BỤI", "MAY HUT BUI", "HÚT BỤI", "HUT BUI", "HÚT BUỘI")) or (
        "HÚT" in full and "BỤI" in full
    ):
        if any(t in full for t in ("3 TRIỆU", "3TRIỆU", "PHÂN KHÚC 3", "PHAN KHUC 3")):
            return {"product": "MÁY HÚT BỤI", "hook": "3 TRIỆU ĐÁNG MUA", "confidence": 0.84}
        if "MỞ RA" in full or "MO RA" in full_ascii or "BÊN TRONG" in full or "BEN TRONG" in full_ascii:
            return {"product": "MÁY HÚT BỤI", "hook": "KHÁM PHÁ BÊN TRONG", "confidence": 0.84}
        if "TEST" in full_ascii or "TÉT" in full or "KHẢ NĂNG" in full or "KHA NANG" in full_ascii:
            return {"product": "MÁY HÚT BỤI", "hook": "TEST KHẢ NĂNG HÚT", "confidence": 0.86}
        return {"product": "MÁY HÚT BỤI", "hook": "HÚT SẠCH NHANH", "confidence": 0.78}
    # PIN KÌM — lithium battery
    if any(token in full for token in ("PIN KÌM", "PIN KIM", "BIN KÌM", "BIN KIM", "BÍN KÌM", "PIN 3A", "PIN 2A")) or (
        ("PIN" in full or "BIN" in full or "BÍN" in full) and ("10 NĂM" in full or "LƯU TRỮ" in full or "LUU TRU" in full_ascii or "KHÔNG CHẢY" in full or "KHONG CHAY" in full_ascii)
    ):
        if "10 NĂM" in full or "LƯU TRỮ" in full or "LUU TRU" in full_ascii:
            return {"product": "PIN KÌM", "hook": "LƯU TRỮ 10 NĂM", "confidence": 0.86}
        if "3A" in full_ascii and "2A" in full_ascii:
            return {"product": "PIN KÌM", "hook": "3A KHÁC 2A", "confidence": 0.82}
        return {"product": "PIN KÌM", "hook": "KHÔNG LO CHAI PIN", "confidence": 0.78}
    # HUB — only if none of the above matched
    if "HUB" in full or re.search(r"\bHAP\b", full_ascii) or re.search(r"\b5\s*(?:IN|IN1|TRONG)\s*1\b", full_ascii):
        if "4K" in full:
            return {"product": "HUB TYPE-C", "hook": "XUẤT 4K", "confidence": 0.78}
        if "SẠC NGƯỢC" in full or "SAC NGUOC" in full_ascii:
            return {"product": "HUB TYPE-C", "hook": "SẠC NGƯỢC", "confidence": 0.76}
        return {"product": "HUB TYPE-C", "hook": "GỌN SETUP", "confidence": 0.72}
    if "USB" in full:
        if "CHÉP NHẠC" in full or "CHEP NHAC" in full_ascii:
            return {"product": "USB GIÁ RẺ", "hook": "CHỈ CHÉP NHẠC", "confidence": 0.86}
        if "FAKE" in full or "TỐC ĐỘ" in full or "TOC DO" in full_ascii:
            return {"product": "USB 2TB", "hook": "TỐC ĐỘ CHẬM", "confidence": 0.84}
        return {"product": "USB", "hook": "GỌN DỄ DÙNG", "confidence": 0.76}
    if (
        any(token in full for token in ("GIÁ ĐỠ ĐIỆN THOẠI", "GIÁ ĐIỆN THOẠI", "ĐỠ ĐIỆN THOẠI", "ĐỂ ĐIỆN THOẠI"))
        or any(token in full_ascii for token in ("GIA DO DIEN THOAI", "GIA DIEN THOAI", "DO DIEN THOAI", "DE DIEN THOAI", "DAI DO DIEN THOAI"))
    ):
        if any(token in full + " " + full_ascii for token in ("SIẾT", "SIET", "ỐC", "OC", "VÍT", "VIT", "LỎNG", "LONG")):
            return {"product": "GIÁ ĐỠ ĐIỆN THOẠI", "hook": "SIẾT ỐC CHỐNG LỎNG", "confidence": 0.9}
        if any(token in full for token in ("GỖ", "ĐẾ GỖ")) or "GO" in full_ascii:
            return {"product": "GIÁ ĐỠ ĐIỆN THOẠI", "hook": "ĐẾ GỖ CHẮC CHẮN", "confidence": 0.86}
        if any(token in full + " " + full_ascii for token in ("SẠC DỰ PHÒNG", "SAC DU PHONG", "NẶNG", "NANG", "CHỊU", "CHIU", "TẢI", "TAI")):
            return {"product": "GIÁ ĐỠ ĐIỆN THOẠI", "hook": "CHỊU TẢI CHẮC", "confidence": 0.88}
        return {"product": "GIÁ ĐỠ ĐIỆN THOẠI", "hook": "CHỌN LOẠI CHẮC", "confidence": 0.86}
    if (
        any(token in full for token in ("SẠC DỰ PHÒNG", "DỰ PHÒNG", "SẠC KHÔNG DÂY", "KHÔNG DÂY", "MAGSAFE"))
        or any(token in full_ascii for token in ("SAC DU PHONG", "DU PHONG", "SAC KHONG DAY", "KHONG DAY", "MAGSAFE", "MANGO"))
    ) and any(token in full + " " + full_ascii for token in ("ĐIỆN THOẠI", "DIEN THOAI", "IPHONE", "ANKER", "15W", "10.000", "10000")):
        if any(token in full + " " + full_ascii for token in ("BÁM", "BAM", "DÍNH", "DINH", "NHẤC", "NHAC", "RỚT", "ROT")):
            return {"product": "SẠC DỰ PHÒNG MAGSAFE", "hook": "BÁM CHẮC", "confidence": 0.86}
        if "ANKER" in full_ascii:
            return {"product": "SẠC DỰ PHÒNG ANKER", "hook": "ĐỠ ĐIỆN THOẠI CHẮC", "confidence": 0.82}
        return {"product": "SẠC DỰ PHÒNG MAGSAFE", "hook": "BÁM CHẮC", "confidence": 0.8}
    if (
        any(token in full for token in ("GIÁ ĐỠ ĐIỆN THOẠI", "GIÁ ĐIỆN THOẠI", "ĐỠ ĐIỆN THOẠI", "ĐỂ ĐIỆN THOẠI"))
        or any(token in full_ascii for token in ("GIA DO DIEN THOAI", "GIA DIEN THOAI", "DO DIEN THOAI", "DE DIEN THOAI", "DAI DO DIEN THOAI"))
    ):
        if any(token in full + " " + full_ascii for token in ("SIẾT", "SIET", "ỐC", "OC", "VÍT", "VIT", "LỎNG", "LONG")):
            return {"product": "GIÁ ĐỠ ĐIỆN THOẠI", "hook": "SIẾT ỐC CHỐNG LỎNG", "confidence": 0.88}
        if any(token in full for token in ("GỖ", "ĐẾ GỖ")) or "GO" in full_ascii:
            return {"product": "GIÁ ĐỠ ĐIỆN THOẠI", "hook": "ĐẾ GỖ CHẮC CHẮN", "confidence": 0.84}
        return {"product": "GIÁ ĐỠ ĐIỆN THOẠI", "hook": "CHỌN LOẠI CHẮC", "confidence": 0.84}
    if "SẠC" in full or "SAC" in full_ascii or "MACBOOK" in full:
        watt = re.search(r"\b(\d{2,3})\s*W\b", full_ascii)
        return {"product": "SẠC MACBOOK", "hook": f"{watt.group(1)}W GỌN HƠN" if watt else "GỌN HƠN", "confidence": 0.72}
    return {"product": "", "hook": "", "confidence": 0.0}


def _brief_product_category(brief: dict | None, context: str = "") -> str:
    brief = brief if isinstance(brief, dict) else {}
    brief_text = _fix_common_title_misreads(_plain_upper(
        f"{brief.get('product', '')} {brief.get('category', '')} {brief.get('hook', '')}"
    ))
    brief_ascii = _ascii_upper(brief_text)
    if any(token in brief_text for token in ("MOMO", "LOA THANH TOÁN", "THANH TOÁN QR", "VIETQR")):
        return "momo"
    if any(token in brief_text for token in ("ỐP ĐIỆN THOẠI", "ỐP LƯNG", "ỐP BẢO VỆ")) or any(
        token in brief_ascii for token in ("OP DIEN THOAI", "OP LUNG", "OP BAO VE")
    ):
        return "phone_case"
    if any(token in brief_text for token in ("KÍNH CƯỜNG LỰC", "DÁN KÍNH", "MIẾNG DÁN", "BAYFAST", "XỐP ĐÓNG GÓI")) or any(
        token in brief_ascii for token in ("KINH CUONG LUC", "DAN KINH", "MIENG DAN", "BAYFAST", "XOP DONG GOI")
    ):
        return "screen_protector"
    if any(token in brief_text for token in ("BĂNG KEO", "IN SẴN CHỮ", "ĐÓNG GÓI")) or any(
        token in brief_ascii for token in ("BANG KEO", "IN SAN CHU", "DONG GOI", "TAPE")
    ):
        return "tape"
    text = _fix_common_title_misreads(_plain_upper(
        f"{brief.get('product', '')} {brief.get('category', '')} {brief.get('hook', '')} {context}"
    ))
    ascii_text = _ascii_upper(text)
    if any(token in text for token in ("GIÁ ĐỠ ĐIỆN THOẠI", "GIÁ ĐIỆN THOẠI", "ĐỠ ĐIỆN THOẠI")) or any(
        token in ascii_text for token in ("GIA DO DIEN THOAI", "GIA DIEN THOAI", "DO DIEN THOAI", "DAI DO DIEN THOAI")
    ):
        return "phone_stand"
    if any(token in text for token in ("TAG ĐỊNH VỊ", "THẺ ĐỊNH VỊ", "THIẾT BỊ ĐỊNH VỊ", "ĐỊNH VỊ", "CÁI TAG", "TAG NÀY")) or any(
        token in ascii_text for token in ("TAG DINH VI", "THE DINH VI", "THIET BI DINH VI", "DINH VI", "CAI TAG", "TAG NAY", "X8")
    ):
        return "tracker"
    if any(token in text for token in ("CO NHIỆT", "CON NHIỆT", "BỌC DÂY", "CỐ ĐỊNH DÂY")) or any(
        token in ascii_text for token in ("CO NHIET", "CON NHIET", "BOC DAY", "CO DINH DAY")
    ):
        return "heat_shrink"
    if any(token in brief_text for token in ("ĐẦU TYPE-C CO GÓC", "CO GÓC TYPE-C", "SAMSUNG DEX", "DEX")) or any(
        token in brief_ascii for token in ("DAU TYPE C CO GOC", "CO GOC TYPE C", "SAMSUNG DEX", "DEX")
    ):
        return "hub"
    if any(token in brief_text for token in ("CỦ SẠC", "DÂY SẠC", "SẠC", "ANKER", "GAN", "MACBOOK", "MAGSAFE")):
        return "charger"
    if "QUẠT" in text or "QUẠC" in text or re.search(r"\bFAN\b", ascii_text):
        return "fan"
    if any(token in text for token in ("ĐÈN", "BÓNG", "LED", "VINACO", "VINAKO", "CON ĐEN")) or any(
        token in ascii_text for token in ("DEN", "BONG DEN", "CON DEN", "LED", "VINACO", "VINAKO")
    ):
        return "light"
    if any(token in text for token in ("KHAY", "A6", "KHUNG NHỰA", "CHIA NGĂN")) or any(
        token in ascii_text for token in ("KHAY", "KHUNG NHUA", "CHIA NGAN")
    ):
        return "tray"
    if (
        any(token in text for token in ("MOMO", "LOA THANH TOÁN", "THANH TOÁN QR", "VIETQR"))
        or any(token in ascii_text for token in ("MOMO", "LOA THANH TOAN", "THANH TOAN QR", "VIETQR"))
    ):
        return "momo"
    if (
        any(token in text for token in ("ỐP ĐIỆN THOẠI", "ỐP LƯNG", "ỐP BẢO VỆ"))
        or any(token in ascii_text for token in ("OP DIEN THOAI", "OP LUNG", "OP BAO VE", "OC DIEN THOAI"))
    ):
        return "phone_case"
    if (
        any(token in text for token in ("KÍNH CƯỜNG LỰC", "DÁN KÍNH", "MIẾNG DÁN", "BAYFAST", "XỐP ĐÓNG GÓI"))
        or any(token in ascii_text for token in ("KINH CUONG LUC", "DAN KINH", "MIENG DAN", "BAYFAST", "XOP DONG GOI"))
    ):
        return "screen_protector"
    if (
        any(token in text for token in ("BĂNG KEO", "IN SẴN CHỮ", "ĐÓNG GÓI"))
        or any(token in ascii_text for token in ("BANG KEO", "IN SAN CHU", "DONG GOI", "TAPE"))
    ):
        return "tape"
    if any(token in text for token in ("OSMO", "NANO", "POCKET 3")):
        return "osmo"
    if ("HDMI" in text and "HUB" not in text and "SAMSUNG DEX" not in text) or re.search(r"\b(?:DÂY|CÁP)\s+HDMI\b", text):
        return "hdmi"
    if any(token in text for token in ("HUB", "USB-C", "TYPE-C", "SAMSUNG DEX", "DEX", "CO GÓC")):
        return "hub"
    if any(token in text for token in ("CỦ SẠC", "DÂY SẠC", "SẠC", "ANKER", "GAN")) or re.search(r"\b\d{2,3}\s*W\b", ascii_text):
        return "charger"
    if "USB" in text:
        return "usb"
    return ""


def _context_product_category(source_title: str, segments: list[dict] | None = None) -> str:
    context = _thumbnail_context_text(source_title, segments)
    return _brief_product_category(_human_content_brief(source_title, segments), context)


def _category_required_title_terms(category: str) -> tuple[str, ...]:
    return {
        "hub": ("HUB", "USB-C", "TYPE-C", "DEX"),
        "charger": ("SẠC", "ANKER", "GAN"),
        "light": ("ĐÈN", "BÓNG", "LED", "VINACO", "VINAKO"),
        "tray": ("KHAY", "A6", "KHUNG"),
        "fan": ("QUẠT",),
        "osmo": ("OSMO", "DJI", "NANO", "POCKET 3"),
        "hdmi": ("HDMI", "CÁP", "DÂY"),
        "momo": ("MOMO", "LOA THANH TOÁN", "THANH TOÁN"),
        "tape": ("BĂNG KEO", "ĐÓNG GÓI", "TAPE"),
        "screen_protector": ("KÍNH", "CƯỜNG LỰC", "DÁN", "MIẾNG DÁN", "BAYFAST", "XỐP"),
        "phone_case": ("ỐP", "ỐP ĐIỆN THOẠI", "BẢO VỆ"),
        "phone_stand": ("GIÁ", "ĐỠ", "ĐIỆN THOẠI"),
        "heat_shrink": ("CO NHIỆT", "BỌC DÂY", "DÂY"),
        "tracker": ("TAG", "ĐỊNH VỊ", "TÌM", "THẤT LẠC"),
        "usb": ("USB",),
    }.get(category, ())


def _title_matches_product_category(title: str, category: str) -> bool:
    required = _category_required_title_terms(category)
    if not required:
        return True
    clean = _fix_common_title_misreads(_plain_upper(title))
    return any(term in clean for term in required)


def _strip_ai_title_noise(title: str) -> str:
    out = _plain_upper(title)
    out = re.sub(r"^(?:TIÊU ĐỀ|TITLE|THUMBNAIL|HOOK|PRODUCT|ANGLE|BEST)\s*[:：\"'-]*\s*", "", out, flags=re.IGNORECASE).strip()
    out = re.sub(r"\bTEST\b\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\bGOOGLE\s+QUEEN\b", "UGREEN", out, flags=re.IGNORECASE)
    out = re.sub(r"\bHUB\s+UGREEN\s+HUB\b", "HUB UGREEN", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _compact_thumbnail_title_variants(title: str, source_title: str = "", segments: list[dict] | None = None) -> list[str]:
    base = _clean_thumbnail_title(_strip_ai_title_noise(title), source_title, segments)
    variants = [base] if base else []
    exact = {
        "HUB USB-C 5.1 SẠC NGƯỢC CHO POCKET 3 XUẤT 4K": "HUB 5.1 SẠC NGƯỢC POCKET 3",
        "HUB 5 IN 1 SẠC XUẤT 4K CẮM LÀM CHO SAMSUNG DEX": "HUB 5 IN 1 CHO SAMSUNG DEX",
        "HUB DÙNG SAMSUNG DEX MACBOOK MƯỢT": "HUB DEX MACBOOK CẮM LÀ MƯỢT",
        "HUB UGREEN HUB SAMSUNG DEX XUẤT 4K BỀN": "HUB UGREEN DEX XUẤT 4K",
        "HUB UGREEN HUB SAMSUNG DEX XUẤT 4K": "HUB UGREEN DEX XUẤT 4K",
        "SAMSUNG DEX KHÔNG XUẤT 4K/320HZ DO DÂY HDMI CŨ": "DÂY HDMI CŨ LÀM DEX KHÔNG LÊN 4K",
        "SẠC NHANH 90W CHO MACBOOK PRO M1 CHỈ VỚI 1 CỔNG": "SẠC 90W CHO MACBOOK PRO",
        "SẠC GAN 140W SẠC MACBOOK ĐIỆN THOẠI CÙNG LÚC NHỎ GỌN TIỆN": "SẠC GAN 140W NHỎ GỌN",
        "SẠC ANKER 140W SẠC NHANH MACBOOK ĐIỆN THOẠI MÁY QUAY": "ANKER 140W SẠC 4 THIẾT BỊ",
        "DÂY SẠC MACBOOK 240W SẠC NHANH GỌN GÀNG KHÔNG LO BỪA BỘN": "DÂY SẠC MACBOOK 240W GỌN",
        "DJI OSMO NANO BÍ QUYẾT TẠO VIDEO TRIỆU VIEW CHO QUÁN ĂN": "OSMO NANO QUAY QUÁN ĂN VIRAL",
        "MẸO QUAY DJI OSMO NANO 4K 50FPS LÂU HƠN KHÔNG NÓNG MÁY": "OSMO NANO QUAY LÂU KHÔNG NÓNG",
        "CÀI ĐẶT DJI OSMO NANO CỦA MÌNH QUAY TIKTOK YOUTUBE KHÔNG GIẬT": "OSMO NANO CÀI D LOG MƯỢT",
        "SETUP DJI OSMO NANO ĐƠN GIẢN ĐỂ CÓ MÀU ĐẸP NHƯ PRO": "OSMO NANO CÀI D LOG MƯỢT",
        "OSMO NANO CHỈ QUAY 15 PHÚT": "OSMO NANO QUAY LÂU KHÔNG NÓNG",
        "BẢO VỆ DJI OSMO NANO KHỎI TRẦY XƯỚC CHỈ VỚI 2 MÓN": "BẢO VỆ OSMO NANO KHỎI TRẦY",
        "ĐỪNG ĐỂ DJI OSMO NANO 6 10 TRIỆU BỊ TRẦY XƯỚC": "BẢO VỆ OSMO NANO KHỎI TRẦY",
        "ĐỪNG ĐỂ DJI OSMO NANO 6 10 TRIỆU BỊ": "BẢO VỆ OSMO NANO KHỎI TRẦY",
        "BÓNG ĐÈN VINACO SÁNG TỐT GIÁ HỜI CÓ BẢO HÀNH": "BÓNG ĐÈN VINACO SÁNG BỀN",
        "BÓNG ĐÈN LED VIỆT NAM BỀN BỈ 30.000 GIỜ CẦM ĐẦM TAY": "ĐÈN LED VIỆT NAM BỀN 30.000 GIỜ",
        "ĐÈN LED VINACO RẺ MÀ SÁNG": "ĐÈN LED VINACO RẺ MÀ SÁNG",
        "ĐÈN LED TRỤ NHÔM SÁNG ĐẸP SANG NHÀ THAY ĐÈN TRANG TRÍ": "ĐÈN LED TRỤ NHÔM SÁNG ĐẸP",
        "ĐÈN LED THIẾT KẾ THANH THOÁT GỌN GÀNG": "ĐÈN LED GỌN ĐẸP DỄ LẮP",
        "KHAY CHIA NGĂN A6 SẮP XẾP HÀNG HÓA GỌN GÀNG DỄ BÁN": "KHAY A6 CHIA HÀNG GỌN",
        "KHUNG NHỰA A6 TỐI ƯU KHÔNG GIAN LÀM VIỆC/BÁN HÀNG GỌN GÀNG": "KHUNG NHỰA A6 GỌN QUẦY BÁN",
        "QUẠT LED TRANG TRÍ PC/SAMSUNG DEX GIÁ RẺ BÁN CHẠY NHẤT": "QUẠT LED TRANG TRÍ PC DEX",
        "HUB USB-C ĐA NĂNG GIÁ RẺ XUẤT 4K SẠC NGƯỢC CẮM CHUỘT": "HUB USB-C XUẤT 4K SẠC NGƯỢC",
        "CÁP HDMI CHANDRO 8K 60HZ BỀN BỈ DỄ UỐN": "CÁP HDMI CHANDRO 8K BỀN",
        "DJI OSMO POCKET 3 CÁCH KIẾM TIỀN TỪ POV": "OSMO NANO QUAY POV KIẾM TIỀN",
        "GÓC SETUP THIẾU QUẠT LED NÀY": "QUẠT LED RẺ LÀM GÓC SETUP ĐẸP",
        "ĐÈN 60W SÁNG THẬT HAY ẢO": "ĐÈN LED 60W SÁNG THẬT",
        "DÂY HDMI 8K 60FPS THẬT": "CÁP HDMI 8K 60HZ THẬT",
    }
    if base in exact:
        variants.append(exact[base])
    context = _fix_common_title_misreads(_plain_upper(_thumbnail_context_text(source_title, segments)))
    if base == "KHUNG NHỰA A6 GỌN QUẦY BÁN" and "KHAY" in context:
        variants.append("KHAY A6 CHIA HÀNG GỌN")
    if base == "KHUNG A6 GỌN QUẦY BÁN" and "KHAY" in context:
        variants.append("KHAY A6 CHIA HÀNG GỌN")
    filler_terms = (
        "CHẤT LƯỢNG CAO",
        "BỀN BỈ",
        "TIỆN LỢI",
        "GỌN GÀNG",
        "GIÁ RẺ",
        "BÁN CHẠY NHẤT",
        "CÙNG LÚC",
        "KHÔNG LO BỪA BỘN",
        "CHỈ VỚI 1 CỔNG",
        "CHO MỌI THIẾT BỊ",
    )
    shortened = base
    for term in filler_terms:
        shortened = re.sub(rf"\b{re.escape(term)}\b", " ", shortened, flags=re.IGNORECASE)
    shortened = re.sub(r"\s+", " ", shortened).strip()
    if shortened and shortened != base:
        variants.append(shortened)
    words = base.split()
    if len(words) > 10:
        variants.append(" ".join(words[:9]))
    out: list[str] = []
    for variant in variants:
        clean = _clean_thumbnail_title(variant, source_title, segments)
        if clean and clean not in out:
            out.append(clean)
    return out


def _extract_price_token(context: str) -> str:
    raw = str(context or "")
    ascii_ctx = _ascii_upper(raw)
    if re.search(r"\b7\s*[,\.]\s*80\s*[,\.]?\s*000\b", raw, flags=re.IGNORECASE) or "7 80 000" in ascii_ctx:
        return "80K"
    for match in re.finditer(r"\b([1-9]\d{1,3})\s*K\b", ascii_ctx):
        start, end = match.span()
        window = ascii_ctx[max(0, start - 36): min(len(ascii_ctx), end + 36)]
        amount = match.group(1)
        if _looks_like_resolution_or_refresh_token(amount, window):
            continue
        if any(token in window for token in ("GIA", "CHI", "RE", "MUA", "BAN", "TIEN", "DONG", "NGHIN", "KHOANG")):
            return f"{match.group(1)}K"
    match = re.search(r"\b([1-9]\d{1,3})\s*[.,]\s*000\b", raw)
    if match:
        return f"{match.group(1)}K"
    return ""


def _context_has_price_evidence(context: str, amount: str) -> bool:
    ascii_ctx = _ascii_upper(context)
    amount = re.sub(r"\D+", "", str(amount or ""))
    if not amount:
        return False
    if amount == "80" and re.search(r"\b7\s*[,\.]\s*80\s*[,\.]?\s*000\b", context, flags=re.IGNORECASE):
        return True
    if amount == "80" and "7 80 000" in ascii_ctx:
        return True
    patterns = [
        rf"\b{re.escape(amount)}\s*K\b",
        rf"\b{re.escape(amount)}\s*[.,]\s*000\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, ascii_ctx, flags=re.IGNORECASE):
            start, end = match.span()
            window = ascii_ctx[max(0, start - 42): min(len(ascii_ctx), end + 42)]
            if _looks_like_resolution_or_refresh_token(amount, window):
                return False
            if any(token in window for token in ("GIA", "CHI", "RE", "MUA", "BAN", "TIEN", "DONG", "NGHIN", "KHOANG")):
                return True
            if any(token in window for token in ("HZ", "FPS", "TAN SO", "QUET", "60 HZ", "120 HZ")):
                return False
    return False


def _looks_like_resolution_or_refresh_token(amount: str, window: str) -> bool:
    amount = re.sub(r"\D+", "", str(amount or ""))
    window = _ascii_upper(window)
    if amount not in {"24", "30", "50", "60", "90", "120", "144", "165", "240", "320"}:
        return False
    spec_markers = ("4K", "8K", "HZ", "FPS", "TAN SO", "QUET", "CHAT LUONG", "HO TRO")
    if any(marker in window for marker in spec_markers):
        return True
    if re.search(r"\b(?:4K|8K)\s+(?:60|120|144|240)\s*K\b", window):
        return True
    return False


def _context_looks_like_hub_not_hdmi_cable(context: str, segments: list[dict] | None = None) -> bool:
    upper = _fix_common_title_misreads(_plain_upper(context))
    early = _fix_common_title_misreads(_plain_upper(_early_thumbnail_context(segments)))
    ascii_ctx = _ascii_upper(upper)
    hub_hit = (
        "HUB" in upper
        or re.search(r"\b5\s*(?:IN|IN1|TRONG)\s*1\b", ascii_ctx)
        or "5IN1" in ascii_ctx
    )
    multi_port = any(token in upper for token in ("CỔNG", "CONG", "SẠC NGƯỢC", "SAC NGUOC", "TYPE-C", "USB-C", "HDMI", "LAN"))
    first_context = upper[:900]
    first_ascii = _ascii_upper(first_context)
    cable_main = (
        any(token in early for token in ("SỢI CÁP", "SOI CAP", "DÂY HDMI", "DAY HDMI", "CÁP HDMI", "CAP HDMI"))
        or bool(re.search(r"\b(?:SỢI|DÂY|CÁP)\s+(?:DÂY\s+)?HDMI\b", first_context))
        or bool(re.search(r"\b(?:SOI|DAY|CAP)\s+(?:DAY\s+)?HDMI\b", first_ascii))
        or bool(re.search(r"\bHDMI\b.{0,36}\b(?:CŨ|CU|2\.1|2\s*1|BÌNH THƯỜNG|BINH THUONG|NÂNG CẤP|NANG CAP)\b", first_ascii))
    )
    return bool(hub_hit and multi_port and not cable_main)


def _hdmi_title_from_context(source_title: str, segments: list[dict] | None = None) -> str:
    context = _thumbnail_context_text(source_title, segments)
    upper = _fix_common_title_misreads(_plain_upper(context))
    ascii_ctx = _ascii_upper(upper)
    if "HDMI" not in upper:
        return ""
    if _context_looks_like_hub_not_hdmi_cable(context, segments):
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
            if _context_has_price_evidence(context, amount):
                continue
            if amount == "80" and re.search(r"\b7\s*[,\.]\s*80\s*[,.]?\s*000\b", context):
                continue
        if compact and compact not in ctx_compact:
            missing.append(compact)
    return missing


_ENTERPRISE_BAD_VIETNAMESE_PATTERNS = re.compile(
    r"\b(?:MỌI\s+THÙNG|KHÔNG\s+CẦN\s+TRÊN|TRÊN\s+IPHONE|ĐÈN\s+LÉP|NHIỀU\s+ANH|"
    r"ÂM\s+THANH\s+XOAY\s+VUI\s+TAI|NGON\s+BỔ|SÁNG\s+BOX|TÚNG\s+PC|"
    r"KHÔNG\s+DÂY\s+CÓ\s+DÂY|BÂY\s+GIỜ|ANH\s+EM\s+QUAY\s+TRỞ|"
    r"KHÔNG\s+RÕ|BRAND\s*/?\s*MODEL|CHƯA\s+RÕ|PHỤ\s+KIỆN\s+KHÔNG\s+THỂ\s+THIẾU)\b",
    re.IGNORECASE,
)


def _enterprise_repeated_title_issue(title: str) -> str:
    words = [w for w in re.findall(r"[A-ZÀ-Ỹ0-9]+", _plain_upper(title))]
    for left, right in zip(words, words[1:]):
        if left == right:
            return "adjacent_repeated_word"
    for size in (4, 3, 2):
        seen: set[tuple[str, ...]] = set()
        for idx in range(0, max(0, len(words) - size + 1)):
            gram = tuple(words[idx : idx + size])
            if len(set(gram)) == 1:
                continue
            if gram in seen:
                return "repeated_phrase"
            seen.add(gram)
    return ""


def _thumbnail_title_risk_flags(title: str, context: str = "") -> list[str]:
    clean = _fix_common_title_misreads(_plain_upper(title))
    context_fixed = _fix_common_title_misreads(_plain_upper(context))
    flags: list[str] = []
    if _looks_like_camera_filename_title(clean):
        flags.append("camera_filename")
    raw_upper = _plain_upper(title)
    if re.search(r"\b(HẤP|HÁP|HAP|SET\s*PLAY|SÉT\s*PLAY|SETPLAY|SAMSUNG\s+DECK|ỐT\s+MUÔN\s+ANO|OTMOLANO|OTMO\s*LANO|OSMO\s+MỘT|SỨC\s+NẤM|UOC|GILKING|FILET|YOLO)\b", raw_upper, flags=re.IGNORECASE):
        flags.append("uncorrected_asr")
    if _context_looks_like_hub_not_hdmi_cable(context_fixed, None) and re.search(r"\b(CÁP|DÂY)\s+HDMI\b", clean):
        flags.append("product_mismatch:hdmi_feature_not_product")
    if _simple_product_mismatch(clean, context_fixed):
        flags.append("product_mismatch:simple_human_gate")
    category = _brief_product_category(_human_content_brief("", [{"text": context_fixed}]), context_fixed)
    if (
        category == "phone_case"
        and any(term in clean for term in ("TYPE-C", "TYPE C", "CO GÓC", "DEX", "SAMSUNG DEX"))
        and any(term in context_fixed for term in ("CO GÓC", "TYPE-C", "TYPE C", "DEX", "SAMSUNG DEX", "40GB", "100W"))
    ):
        category = "hub"
    if (
        category == "phone_case"
        and any(term in clean for term in ("SẠC DỰ PHÒNG", "MAGSAFE", "SẠC KHÔNG DÂY", "ANKER"))
        and any(term in context_fixed for term in ("SẠC DỰ PHÒNG", "DỰ PHÒNG", "SẠC KHÔNG DÂY", "KHÔNG DÂY", "MAGSAFE", "ANKER", "BÁM", "DÍNH"))
    ):
        category = "charger"
    if (
        category == "phone_case"
        and any(term in clean for term in ("GIÁ ĐỠ", "GIÁ ĐIỆN THOẠI", "ĐỠ ĐIỆN THOẠI"))
        and any(term in context_fixed for term in ("GIÁ ĐỠ", "GIÁ ĐIỆN THOẠI", "ĐỠ ĐIỆN THOẠI", "ĐỂ ĐIỆN THOẠI"))
    ):
        category = "phone_stand"
    if (
        category == "phone_case"
        and any(term in clean for term in ("TAG", "ĐỊNH VỊ", "X8", "TÌM XE", "CHÌA KHÓA"))
        and any(term in context_fixed for term in ("TAG", "ĐỊNH VỊ", "X8", "CHÌA KHÓA", "XE", "VẬT DỤNG", "IPHONE", "ANDROID", "PHÁT ÂM THANH"))
    ):
        category = "tracker"
    if (
        category == "phone_case"
        and any(term in clean for term in ("KÍNH", "CƯỜNG LỰC", "DÁN", "MIẾNG DÁN", "BAYFAST", "XỐP"))
        and any(term in context_fixed for term in ("KÍNH", "CƯỜNG LỰC", "DÁN", "MIẾNG DÁN", "BAYFAST", "XỐP"))
    ):
        category = "screen_protector"
    if category and not _title_matches_product_category(clean, category):
        flags.append(f"product_mismatch:{category}_title_required")
    for price in re.findall(r"\b(?:GIÁ|CHỈ|CÓ GIÁ)?\s*([1-9]\d{1,3})\s*K\b", clean):
        if not _context_has_price_evidence(context_fixed, price):
            flags.append(f"unsupported_price:{price}K")
    if "GAME CH PLAY" in clean:
        flags.append("awkward_game_ch_play")
    if clean.startswith((
        "ANH EM ",
        "ANH EM XEM",
        "ANH EM NÀO",
        "ÂN EM ",
        "NHIỀU ANH EM",
        "KHI ANH EM",
        "NẾU NHƯ",
        "XEM NÀY",
        "ĐÂY NÈ XEM",
        "ĐÂY ĐÂY",
        "ĐÂY MỘT",
        "ĐÂY MÌNH",
        "BÊN TAY TRÁI",
        "GIỚI THIỆU VỚI",
        "HÔM NAY MÌNH",
        "TRÊN TAY MÌNH",
        "MỌI NGƯỜI MUỐN",
        "NGƯỜI VIỆT NAM",
        "CÁI DÂY MÌNH",
    )):
        flags.append("generic_viewer_filler")
    if re.search(r"\bGIÁ\s+CHỈ\s*$", clean) or re.search(r"\bCHỈ\s*$", clean):
        flags.append("incomplete_price_hook")
    if re.search(r"\s[A-ZĐ]$", _ascii_upper(clean)):
        flags.append("truncated_single_letter_tail")
    if re.search(r"\bO\s*[- ]?\s*KRING\b", clean, flags=re.IGNORECASE):
        flags.append("uncertain_brand_asr")
    if clean in {"VIDEO MỚI", "THỦ THUẬT HAY", "MẸO HAY", "SẢN PHẨM HAY"}:
        flags.append("generic")
    if re.search(r"\bRẮC\s+\d", clean):
        flags.append("awkward_term:rac")
    if re.search(r"\bCỤN\b", clean):
        flags.append("uncorrected_asr:cun")
    if re.search(r"\b(CÁI|CÁC|NÀY|KIA)\s+(CÁI|CÁC|NÀY|KIA)\b", clean):
        flags.append("awkward_phrase")
    repeated_issue = _enterprise_repeated_title_issue(clean)
    if repeated_issue:
        flags.append(repeated_issue)
    if _ENTERPRISE_BAD_VIETNAMESE_PATTERNS.search(clean):
        flags.append("bad_vietnamese_phrase")
    if re.search(r"\b(?:KHÔNG\s+RÕ|CHƯA\s+RÕ|BRAND\s*/?\s*MODEL|META|QA)\b", clean, flags=re.IGNORECASE):
        flags.append("meta_note_in_title")
    if re.search(r"\b(?:GIÁ|CHỈ|TỪ)\s+\d{2,4}\b(?!\s*(?:K|NGHÌN|TRIỆU|TR|Đ|VNĐ|USD|USDT|%))", clean, flags=re.IGNORECASE):
        flags.append("incomplete_price_unit")
    price_tokens = re.findall(r"\b\d{2,4}\s*(?:K|NGHÌN|TRIỆU|TR|Đ|VNĐ|USD|USDT)\b", clean, flags=re.IGNORECASE)
    if len(set(t.upper().replace(" ", "") for t in price_tokens)) > 1:
        flags.append("multiple_prices_in_title")
    if re.search(r"\b\d+(?:[.,]\d+)?/\d+\b", clean):
        flags.append("awkward_fraction")
    for claim in _unsupported_spec_claims(clean, context_fixed):
        flags.append(f"unsupported_claim:{claim}")
    if "QUẠT" in clean and "QUẠT" not in context_fixed and "FAN" not in _ascii_upper(context_fixed):
        flags.append("unsupported_product:quat")
    if (
        "QUẠT" in clean
        and "TRANG TRÍ" in clean
        and any(term in context_fixed for term in ("NÓNG", "MÁT", "TẢN NHIỆT", "LÀM MÁT"))
    ):
        flags.append("weak_hook:fan_cooling_context")
    return flags


def _simple_product_mismatch(title: str, context: str) -> bool:
    clean = _fix_common_title_misreads(_plain_upper(title))
    ctx = _fix_common_title_misreads(_plain_upper(context))
    ctx_ascii = _ascii_upper(ctx)
    title_is_dex_hub = "SAMSUNG DEX" in clean or re.search(r"\bHUB\b", clean)
    context_is_fan_or_light = bool(re.search(r"\b(QUAT|QUAC|FAN|BONG DEN|DEN|LED)\b", ctx_ascii))
    if title_is_dex_hub and context_is_fan_or_light:
        return True
    title_is_osmo_lut = "OSMO" in clean and ("LUT" in clean or "MÀU" in clean)
    if title_is_osmo_lut and not any(term in ctx for term in ("LUT", "LÚT", "MÀU", "D-LOG", "REC.709")):
        return True
    return False


def _looks_like_camera_filename_title(title: str) -> bool:
    clean = _ascii_upper(title)
    compact = re.sub(r"[^A-Z0-9]+", "_", clean).strip("_")
    if re.search(r"\b(?:MP4|MOV|M4V|JPG|JPEG|PNG)\b", clean):
        return True
    if re.search(r"\b(?:IMG|VID|DSC|GOPRO|GH\d{3,})[_ -]?\d{3,}\b", clean):
        return True
    if re.search(r"\bDJI[_ -]?\d{8,}[_ -]?\d{3,}", clean):
        return True
    if re.search(r"\bDJI[_ -]?\d{8,}[_ -]?\d{3,}", compact):
        return True
    if re.fullmatch(r"DJI(?:_\d{3,})+(?:_[A-Z])?", compact):
        return True
    digit_count = sum(ch.isdigit() for ch in clean)
    return bool(digit_count >= 8 and re.search(r"\b(?:DJI|IMG|VID|DSC|GOPRO|GH\d+)\b", clean))


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
    out = _strip_ai_title_noise(title)
    out = re.sub(r"^(TIÊU ĐỀ|TITLE|THUMBNAIL|HOOK|PRODUCT)\s*:\s*", "", out, flags=re.IGNORECASE).strip()
    out = _fix_common_title_misreads(out)
    out = _normalize_tech_terms(out)
    context_fixed = _fix_common_title_misreads(_plain_upper(context))
    context_ascii = _ascii_upper(context_fixed)
    if (
        re.search(r"\bHÀNG\s+D$", out)
        and ("DỄ VỠ" in context_fixed or "DE VO" in context_ascii)
        and ("BĂNG KEO" in context_fixed or "BANG KEO" in context_ascii)
    ):
        out = re.sub(r"\bHÀNG\s+D$", "HÀNG DỄ VỠ", out)
    if (
        re.search(r"\bCHỐNG\s+TRÁ$", out)
        and ("TRÁO HÀNG" in context_fixed or "TRAO HANG" in context_ascii)
        and ("BĂNG KEO" in context_fixed or "BANG KEO" in context_ascii)
    ):
        out = re.sub(r"\bCHỐNG\s+TRÁ$", "CHỐNG TRÁO HÀNG", out)
    out = _strip_generic_thumbnail_prefix(out)
    out = re.sub(r"\b(ĐƯỢC|DUOC)\b", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip()
    out = _strip_bad_title_tail(out)

    product = _extract_known_product_context(context)
    if _context_is_fan_or_light(context) and ("QUẠT" in out or "LED" in out):
        product = ""
    if product == "SAMSUNG DEX":
        out = re.sub(r"\bTRÊN\s+DEX\b", "TRÊN SAMSUNG DEX", out)
    if "SAMSUNG DEX" in context_fixed and "DEX" in out and "SAMSUNG DEX" not in out:
        out = re.sub(r"\bDEX\b", "SAMSUNG DEX", out)
    has_product = product in out or (product == "SAMSUNG DEX" and "DEX" in out)
    if product and "TRÊN " not in out and not has_product:
        if any(key in out for key in ("ĐĂNG NHẬP", "DANG NHAP", "CÀI", "CAI", "SETUP", "NHẬN", "NHAN", "MỞ", "MO")):
            out = f"{out} TRÊN {product}"
    if product and has_product:
        out = re.sub(rf"\s+TRÊN\s+{re.escape(product)}$", "", out, flags=re.IGNORECASE).strip()
    if product == "DJI OSMO NANO" and "OSMO NANO" in out:
        out = re.sub(r"\s+TRÊN\s+DJI\s+OSMO\s+NANO$", "", out, flags=re.IGNORECASE).strip()
    if "MACBOOK" in out:
        out = re.sub(r"\s+TRÊN\s+MACBOOK$", "", out, flags=re.IGNORECASE).strip()
    if "IPHONE" not in _fix_common_title_misreads(_plain_upper(context)) and "TRÊN IPHONE" in out:
        out = re.sub(r"\s+TRÊN\s+IPHONE$", "", out, flags=re.IGNORECASE).strip()

    out = _trim_title_words(out, 12)
    out = _strip_bad_title_tail(out)
    return out


def _block_title_quality(quality: dict | None, reason: str, publish_status: str = "review") -> dict:
    quality = dict(quality or {})
    reasons = [str(r) for r in (quality.get("reasons") or []) if str(r).strip()]
    risk_flags = [str(r) for r in (quality.get("risk_flags") or []) if str(r).strip()]
    if reason not in reasons:
        reasons.insert(0, reason)
    if reason not in risk_flags:
        risk_flags.insert(0, reason)
    quality.update({
        "status": "needs_review",
        "publish_status": publish_status,
        "publish_label": "Cần xem lại" if publish_status == "review" else "Chặn trước render",
        "reasons": reasons[:6],
        "risk_flags": risk_flags[:6],
    })
    return quality


def _title_source_is_renderable(source_kind: str) -> bool:
    clean = str(source_kind or "").strip().lower()
    return clean not in {"", "fallback", "blocked_no_title", "source_filename", "legacy_fallback"}


def _batch_title_key(title: str) -> str:
    clean = _fix_common_title_misreads(_plain_upper(title))
    return re.sub(r"[^A-ZÀ-Ỹ0-9]+", " ", clean).strip()


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


def _shell_path() -> str:
    if os.name == "nt":
        return os.environ.get("PATH", "")
    base_paths = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/sbin", "/usr/sbin"]
    try:
        r = subprocess.run(
            ["/bin/zsh", "-l", "-c", "echo $PATH"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            for part in r.stdout.strip().split(os.pathsep):
                if part and part not in base_paths:
                    base_paths.append(part)
    except Exception:
        pass
    env_path = os.environ.get("PATH", "")
    for part in env_path.split(os.pathsep):
        if part and part not in base_paths:
            base_paths.append(part)
    return os.pathsep.join(base_paths)


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
    run_cmd = list(cmd)
    if run_cmd:
        resolved = _media_binary(run_cmd[0])
        if resolved:
            run_cmd[0] = resolved
    env = {**os.environ, "PATH": _shell_path()}
    proc = subprocess.Popen(
        run_cmd,
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
            return subprocess.CompletedProcess(run_cmd, -15, "".join(stdout_parts) + (stdout or ""), "".join(stderr_parts) + (stderr or "Đã dừng"))
        if timeout is not None and time.monotonic() - started > timeout:
            _terminate_process(proc)
            stdout, stderr = proc.communicate(timeout=1)
            raise subprocess.TimeoutExpired(run_cmd, timeout, output="".join(stdout_parts) + (stdout or ""), stderr="".join(stderr_parts) + (stderr or ""))
        try:
            stdout, stderr = proc.communicate(timeout=0.25)
            return subprocess.CompletedProcess(run_cmd, proc.returncode, "".join(stdout_parts) + (stdout or ""), "".join(stderr_parts) + (stderr or ""))
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


def _ffprobe_audio_info(path: str | Path) -> dict:
    info = {"codec": "", "sample_rate": 0, "channels": 0, "bit_rate": 0, "exists": False}
    try:
        r = _run_media_cmd([
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate",
            "-of", "json",
            str(path),
        ], timeout=20)
        if r.returncode != 0:
            return info
        data = json.loads(r.stdout or "{}")
        stream = (data.get("streams") or [{}])[0] or {}
        if not stream:
            return info
        info["exists"] = True
        info["codec"] = str(stream.get("codec_name") or "")
        info["sample_rate"] = int(stream.get("sample_rate") or 0)
        info["channels"] = int(stream.get("channels") or 0)
        info["bit_rate"] = int(stream.get("bit_rate") or 0)
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


def _validate_lut_preflight(
    source: Path,
    *,
    lut_path: str,
    out_dir: Path,
    duration: float,
    is_cancelled=None,
) -> dict:
    if not lut_path:
        return {"ok": False, "status": "missing", "reason": "lut_path_empty", "test_frame": ""}
    path = Path(lut_path)
    if not path.exists():
        return {"ok": False, "status": "missing", "reason": "lut_missing", "test_frame": ""}
    out_dir.mkdir(parents=True, exist_ok=True)
    test_frame = out_dir / "lut-preflight-frame.png"
    frame_time = min(max(float(duration) * 0.18, 0.1), max(float(duration) - 0.2, 0.1)) if duration > 0 else 0.1
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, frame_time):.3f}",
        "-i", str(source),
        "-frames:v", "1",
        "-vf", f"lut3d=file='{_escape_filter_path(str(path))}'",
        str(test_frame),
    ]
    r = _run_media_cmd(cmd, timeout=120, is_cancelled=is_cancelled)
    if r.returncode == 0 and test_frame.exists() and test_frame.stat().st_size > 0:
        return {
            "ok": True,
            "status": "validated",
            "reason": "lut_preflight_ok",
            "test_frame": str(test_frame),
            "lut_path": str(path),
        }
    return {
        "ok": False,
        "status": "invalid",
        "reason": "lut_preflight_failed",
        "test_frame": str(test_frame) if test_frame.exists() else "",
        "lut_path": str(path),
        "error": ((r.stderr or "") + "\n" + (r.stdout or "")).strip()[-1200:],
    }


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
    name = "DJI OSMO Osmo Nano D-Log M to Rec.709 V1.cube"
    candidates = [
        *_resource_path_candidates("luts", name),
        Path(__file__).resolve().parent / "luts" / name,
        Path.home() / "Downloads" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _audio_loudness_metrics(
    source: Path,
    *,
    duration: float = 25.0,
    afilter: str = "",
    is_cancelled=None,
) -> dict:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-t", f"{max(1.0, float(duration)):.2f}", "-i", str(source)]
    if afilter:
        cmd.extend(["-af", f"{afilter},volumedetect"])
    else:
        cmd.extend(["-af", "volumedetect"])
    cmd.extend(["-vn", "-sn", "-dn", "-f", "null", "-"])
    r = _run_media_cmd(cmd, timeout=90, is_cancelled=is_cancelled)
    text = (r.stderr or "") + "\n" + (r.stdout or "")
    if r.returncode != 0:
        return {"ok": False, "error": (text or "volumedetect failed").strip()[-500:]}
    mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
    max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
    return {
        "ok": bool(mean_match or max_match),
        "mean_volume_db": float(mean_match.group(1)) if mean_match else None,
        "max_volume_db": float(max_match.group(1)) if max_match else None,
        "filter": afilter or "original",
    }


def _chain_audio_filter(*parts: str) -> str:
    return ",".join(str(p).strip().strip(",") for p in parts if str(p or "").strip())


def _audio_quality_probe(
    source: Path,
    *,
    duration: float,
    afilter: str = "",
    is_cancelled=None,
) -> dict:
    full = _audio_loudness_metrics(source, duration=duration, afilter=afilter, is_cancelled=is_cancelled)
    voice = _audio_loudness_metrics(
        source,
        duration=duration,
        afilter=_chain_audio_filter(afilter, "highpass=f=120", "lowpass=f=6500"),
        is_cancelled=is_cancelled,
    )
    rumble = _audio_loudness_metrics(
        source,
        duration=duration,
        afilter=_chain_audio_filter(afilter, "lowpass=f=120"),
        is_cancelled=is_cancelled,
    )
    hiss = _audio_loudness_metrics(
        source,
        duration=duration,
        afilter=_chain_audio_filter(afilter, "highpass=f=7000"),
        is_cancelled=is_cancelled,
    )
    return {
        "ok": bool(full.get("ok") and voice.get("ok")),
        "full": full,
        "voice_band": voice,
        "low_rumble_band": rumble,
        "hiss_band": hiss,
        "filter": afilter or "original",
    }


def _export_noise_sample(
    source: Path,
    *,
    output_path: Path,
    duration: float,
    afilter: str = "",
    is_cancelled=None,
) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-t", f"{max(3.0, min(float(duration), 18.0)):.2f}",
        "-i", str(source),
        "-vn", "-sn", "-dn",
    ]
    if afilter:
        cmd.extend(["-af", afilter])
    cmd.extend(["-c:a", "aac", "-b:a", "160k", str(output_path)])
    r = _run_media_cmd(cmd, timeout=120, is_cancelled=is_cancelled)
    if r.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)
    return ""


def _metric_delta(before: dict, after: dict, key: str = "mean_volume_db") -> float | None:
    left = before.get(key)
    right = after.get(key)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(right) - float(left)
    return None


def _resolve_one_shot_noise_mode(options: dict | None = None) -> str:
    options = options or {}
    raw_mode = str(options.get("noise_mode") or "").strip().lower()
    if raw_mode in {"off", "none", "false", "0"}:
        return "off"
    if raw_mode in {"strong", "clean_strong", "manh", "mạnh"}:
        return "strong"
    if raw_mode in {"auto", "auto_gentle", "gentle", "on", "true", "1", ""}:
        return "auto_gentle" if bool(options.get("noise_reduce", True)) else "off"
    return "auto_gentle" if bool(options.get("noise_reduce", True)) else "off"


def _decide_one_shot_noise(
    source: Path,
    *,
    requested_mode: str,
    duration: float,
    out_dir: Path | None = None,
    is_cancelled=None,
) -> dict:
    requested_mode = str(requested_mode or "auto_gentle").strip().lower()
    if requested_mode in {"off", "none", "false", "0"}:
        return {
            "mode": "off",
            "requested": False,
            "applied": False,
            "filter": "",
            "decision": "disabled",
            "reason": "Noise đang tắt",
            "original_metrics": {},
            "processed_metrics": {},
            "noise_sample_original": "",
            "noise_sample_processed": "",
        }
    if requested_mode == "strong":
        sample_seconds = min(max(8.0, float(duration) * 0.35), 25.0) if duration > 0 else 18.0
        sample_original = ""
        sample_processed = ""
        if out_dir:
            sample_original = _export_noise_sample(source, output_path=Path(out_dir) / "noise-original.m4a", duration=sample_seconds, is_cancelled=is_cancelled)
            sample_processed = _export_noise_sample(source, output_path=Path(out_dir) / "noise-processed.m4a", duration=sample_seconds, afilter=_NOISE_FILTER_STRONG, is_cancelled=is_cancelled)
        return {
            "mode": "strong",
            "requested": True,
            "applied": True,
            "filter": _NOISE_FILTER_STRONG,
            "decision": "processed",
            "reason": "Người dùng chọn làm sạch mạnh",
            "original_metrics": {},
            "processed_metrics": {},
            "noise_sample_original": sample_original,
            "noise_sample_processed": sample_processed,
        }
    sample_seconds = min(max(8.0, float(duration) * 0.35), 25.0) if duration > 0 else 18.0
    sample_original = ""
    sample_processed = ""
    if out_dir:
        sample_original = _export_noise_sample(source, output_path=Path(out_dir) / "noise-original.m4a", duration=sample_seconds, is_cancelled=is_cancelled)
        sample_processed = _export_noise_sample(source, output_path=Path(out_dir) / "noise-processed.m4a", duration=sample_seconds, afilter=_NOISE_FILTER_AUTO_GENTLE, is_cancelled=is_cancelled)
    original = _audio_quality_probe(source, duration=sample_seconds, is_cancelled=is_cancelled)
    processed = _audio_quality_probe(
        source,
        duration=sample_seconds,
        afilter=_NOISE_FILTER_AUTO_GENTLE,
        is_cancelled=is_cancelled,
    )
    if not original.get("ok") or not processed.get("ok"):
        return {
            "mode": "auto_gentle",
            "requested": True,
            "applied": False,
            "filter": "",
            "decision": "fallback_original",
            "reason": "Không đo được audio đủ chắc, giữ âm thanh gốc",
            "original_metrics": original,
            "processed_metrics": processed,
            "noise_sample_original": sample_original,
            "noise_sample_processed": sample_processed,
        }
    full_mean_delta = _metric_delta(original.get("full", {}), processed.get("full", {}))
    voice_mean_delta = _metric_delta(original.get("voice_band", {}), processed.get("voice_band", {}))
    voice_peak_delta = _metric_delta(original.get("voice_band", {}), processed.get("voice_band", {}), "max_volume_db")
    rumble_delta = _metric_delta(original.get("low_rumble_band", {}), processed.get("low_rumble_band", {}))
    hiss_delta = _metric_delta(original.get("hiss_band", {}), processed.get("hiss_band", {}))
    if isinstance(full_mean_delta, float) and full_mean_delta < -4.5:
        return {
            "mode": "auto_gentle",
            "requested": True,
            "applied": False,
            "filter": "",
            "decision": "fallback_original",
            "reason": "Bản giảm noise nhỏ tiếng hơn quá nhiều, giữ audio gốc",
            "original_metrics": original,
            "processed_metrics": processed,
            "noise_sample_original": sample_original,
            "noise_sample_processed": sample_processed,
        }
    if isinstance(voice_mean_delta, float) and voice_mean_delta < -3.0:
        return {
            "mode": "auto_gentle",
            "requested": True,
            "applied": False,
            "filter": "",
            "decision": "fallback_original",
            "reason": "Bản giảm noise làm tụt vùng giọng nói, giữ audio gốc",
            "original_metrics": original,
            "processed_metrics": processed,
            "noise_sample_original": sample_original,
            "noise_sample_processed": sample_processed,
        }
    if isinstance(voice_peak_delta, float) and voice_peak_delta < -5.0:
        return {
            "mode": "auto_gentle",
            "requested": True,
            "applied": False,
            "filter": "",
            "decision": "fallback_original",
            "reason": "Bản giảm noise làm mất peak giọng nói, giữ audio gốc",
            "original_metrics": original,
            "processed_metrics": processed,
            "noise_sample_original": sample_original,
            "noise_sample_processed": sample_processed,
        }
    noise_improved = any(isinstance(delta, float) and delta <= -0.8 for delta in (rumble_delta, hiss_delta))
    if not noise_improved:
        return {
            "mode": "auto_gentle",
            "requested": True,
            "applied": False,
            "filter": "",
            "decision": "fallback_original",
            "reason": "Không thấy noise-band giảm đủ rõ, giữ audio gốc",
            "original_metrics": original,
            "processed_metrics": processed,
            "noise_sample_original": sample_original,
            "noise_sample_processed": sample_processed,
        }
    return {
        "mode": "auto_gentle",
        "requested": True,
        "applied": True,
        "filter": _NOISE_FILTER_AUTO_GENTLE,
        "decision": "processed",
        "reason": "Auto nhẹ đạt ngưỡng, dùng audio đã xử lý",
        "original_metrics": original,
        "processed_metrics": processed,
        "noise_sample_original": sample_original,
        "noise_sample_processed": sample_processed,
    }


def _technical_qa_report(
    source: Path,
    *,
    apply_lut_requested: bool,
    lut_path: str,
    noise_decision: dict,
    duration: float = 0.0,
    source_info: dict | None = None,
    audio_info: dict | None = None,
    lut_validation: dict | None = None,
    out_dir: Path | None = None,
) -> dict:
    checks: list[str] = []
    issues: list[str] = []
    if not source.exists():
        issues.append("source_missing")
    else:
        checks.append("source_exists")
    if duration <= 0:
        issues.append("duration_invalid")
    else:
        checks.append("duration_ok")
    source_info = source_info or {}
    if int(source_info.get("width") or 0) <= 0 or int(source_info.get("height") or 0) <= 0:
        issues.append("video_stream_missing")
    else:
        checks.append("video_stream_ok")
    audio_info = audio_info or {}
    if audio_info and audio_info.get("exists"):
        checks.append("audio_stream_ok")
    else:
        issues.append("audio_stream_missing")
    if out_dir:
        try:
            if _free_disk_bytes(out_dir) < 1 * 1024 ** 3:
                issues.append("disk_space_low")
            else:
                checks.append("disk_space_ok")
        except Exception:
            checks.append("disk_space_unknown")
    lut_validation = lut_validation or {}
    if apply_lut_requested:
        if not lut_path:
            issues.append("lut_missing")
        elif not Path(lut_path).exists():
            issues.append("lut_missing")
        elif not lut_validation.get("ok"):
            issues.append(str(lut_validation.get("reason") or "lut_invalid"))
        else:
            checks.append("lut_validated")
    else:
        checks.append("lut_disabled")
    if noise_decision.get("decision") == "fallback_original":
        checks.append("noise_fallback_original")
    elif noise_decision.get("applied"):
        checks.append("noise_applied")
    else:
        checks.append("noise_disabled")
    return {
        "ok": not issues,
        "status": "ready" if not issues else "failed_technical",
        "checks": checks,
        "issues": issues,
        "lut_enabled": bool(apply_lut_requested),
        "lut_path": lut_path if apply_lut_requested else "",
        "lut_validated": bool(lut_validation.get("ok")) if apply_lut_requested else False,
        "lut_failure_reason": "" if (not apply_lut_requested or lut_validation.get("ok")) else str(lut_validation.get("reason") or "lut_invalid"),
        "lut_validation": lut_validation,
        "noise_mode": noise_decision.get("mode", ""),
        "noise_decision": noise_decision.get("decision", ""),
        "noise_reason": noise_decision.get("reason", ""),
    }


def _render_output_qa(
    output_video: Path,
    *,
    expected_duration: float,
    output_profile: dict,
    expect_audio: bool = True,
) -> dict:
    checks: list[str] = []
    issues: list[str] = []
    if not output_video.exists():
        issues.append("output_missing")
        return {"ok": False, "status": "failed_technical", "checks": checks, "issues": issues}
    size = int(output_video.stat().st_size)
    if size <= 0:
        issues.append("output_empty")
    else:
        checks.append("output_non_empty")
    try:
        out_duration = _ffprobe_duration(output_video)
        if expected_duration > 0 and out_duration < max(0.2, expected_duration * 0.75):
            issues.append("duration_too_short")
        else:
            checks.append("duration_ok")
    except Exception:
        out_duration = 0.0
        issues.append("duration_probe_failed")
    video_info = _ffprobe_video_info(output_video)
    if int(video_info.get("width") or 0) <= 0 or int(video_info.get("height") or 0) <= 0:
        issues.append("video_stream_missing")
    else:
        checks.append("video_stream_ok")
    target_w = int(output_profile.get("width") or 0)
    target_h = int(output_profile.get("height") or 0)
    if target_w > 0 and target_h > 0 and int(video_info.get("width") or 0) > 0:
        if int(video_info.get("width") or 0) != target_w or int(video_info.get("height") or 0) != target_h:
            issues.append("resolution_mismatch")
        else:
            checks.append("resolution_ok")
    audio_info = _ffprobe_audio_info(output_video)
    if expect_audio and not audio_info.get("exists"):
        issues.append("audio_stream_missing")
    elif audio_info.get("exists"):
        checks.append("audio_stream_ok")
    return {
        "ok": not issues,
        "status": "ready" if not issues else "failed_technical",
        "checks": checks,
        "issues": issues,
        "file_size": size,
        "duration": round(float(out_duration), 3),
        "video": video_info,
        "audio": audio_info,
        "expected_duration": round(float(expected_duration), 3),
        "expected_profile": output_profile,
    }


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


def _thumbnail_semantic_units(text: str) -> list[str]:
    words = str(text or "").split()
    if not words:
        return []
    units: list[str] = []
    idx = 0
    while idx < len(words):
        matched = ""
        for phrase in _THUMB_SEMANTIC_PHRASES:
            phrase_words = phrase.split()
            if not phrase_words or idx + len(phrase_words) > len(words):
                continue
            if words[idx:idx + len(phrase_words)] == phrase_words:
                matched = phrase
                break
        if matched:
            units.append(matched)
            idx += len(matched.split())
        else:
            units.append(words[idx])
            idx += 1
    return units


def _thumbnail_semantic_lines(text: str, target_lines: int) -> list[str]:
    units = _thumbnail_semantic_units(text)
    if not units:
        return []
    if len(units) <= target_lines:
        return units
    if target_lines == 2 and len(units) == 3 and len(units[0]) <= 4:
        return [f"{units[0]} {units[1]}", units[2]]

    total_chars = sum(len(unit) for unit in units)
    target_chars = max(10, int(total_chars / max(1, target_lines)) + 2)
    lines: list[list[str]] = []
    current: list[str] = []
    for unit in units:
        remaining_units = len(units) - sum(len(line) for line in lines) - len(current)
        remaining_lines = target_lines - len(lines)
        trial = " ".join(current + [unit])
        should_break = (
            current
            and len(trial) > target_chars
            and remaining_units >= remaining_lines
            and len(lines) < target_lines - 1
        )
        if should_break:
            lines.append(current)
            current = [unit]
        else:
            current.append(unit)
    if current:
        lines.append(current)
    return [" ".join(line) for line in lines if line]


def _thumbnail_bad_tail_count(parts: list[str]) -> int:
    bad = 0
    for part in parts[:-1]:
        tokens = part.split()
        if not tokens or tokens[-1] not in _THUMB_TRAILING_BAD_WORDS:
            continue
        if any(part.endswith(phrase) for phrase in _THUMB_SEMANTIC_PHRASES):
            continue
        bad += 1
    return bad


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

    semantic_lines = _thumbnail_semantic_lines(text, target_lines)
    if semantic_lines:
        semantic_joined = " / ".join(semantic_lines)
        split_protected = sum(_phrase_is_split(semantic_joined, phrase) for phrase in _THUMB_SEMANTIC_PHRASES)
        bad_tail = _thumbnail_bad_tail_count(semantic_lines)
        if not split_protected and not bad_tail and len(semantic_lines) <= 4:
            return semantic_lines

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
    brief = _human_content_brief(source_title, segments)
    brief_product = str(brief.get("product") or "")
    brief_hook = str(brief.get("hook") or "")
    if brief_product and brief_hook:
        if brief_hook == "SỨC NÓNG":
            return _clean_thumbnail_title(f"{brief_hook} CỦA {brief_product}", source_title, segments)
        if brief_hook == "DÁN BẢO VỆ":
            return _clean_thumbnail_title(f"{brief_hook} {brief_product}", source_title, segments)
        if brief_hook == "LUT MÀU ĐẸP":
            return _clean_thumbnail_title(f"{brief_hook} CHO {brief_product}", source_title, segments)
        return _clean_thumbnail_title(f"{brief_product} {brief_hook}", source_title, segments)
    hdmi_title = _hdmi_title_from_context(source_title, segments)
    if hdmi_title:
        return hdmi_title
    if _context_is_fan_or_light(early):
        if "LED" in early or "MÀU" in early or "MAU" in _ascii_upper(early):
            return "QUẠT LED TRANG TRÍ GÓC SETUP"
        return "QUẠT TRANG TRÍ GÓC SETUP"
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
    if "OSMO NANO" in upper or "OSMO ACTION" in upper or "POCKET 3" in upper:
        product_name = _extract_known_product_context(context) or "DJI OSMO"
        hook_context = early or upper
        if any(key in hook_context for key in ("DÁN", "DAN", "BẢO VỆ", "BAO VE", "TRẦY", "TRAY", "XƯỚC", "XUOC")):
            return _clean_thumbnail_title(f"DÁN BẢO VỆ {product_name}", source_title, segments)
        if any(key in hook_context for key in ("SỨC NÓNG", "SUC NONG")):
            return _clean_thumbnail_title(f"SỨC NÓNG CỦA {product_name}", source_title, segments)
        if any(key in hook_context for key in ("LUT", "LÚT", "MÀU", "MAU", "D-LOG", "REC.709")):
            return _clean_thumbnail_title(f"LUT MÀU ĐẸP CHO {product_name}", source_title, segments)
        return _clean_thumbnail_title(f"{product_name} CÓ ĐÁNG MUA", source_title, segments)

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
    brief = _human_content_brief(source_title, segments)
    candidates: list[str] = []

    def add(title: str) -> None:
        clean = _clean_thumbnail_title(title, source_title, segments)
        if clean and clean not in candidates and not _is_weak_thumbnail_title(clean, context):
            candidates.append(clean)

    brief_product = str(brief.get("product") or "")
    brief_hook = str(brief.get("hook") or "")
    if brief_product and brief_hook:
        if brief_hook == "SỨC NÓNG":
            add(f"{brief_hook} CỦA {brief_product}")
        elif brief_hook == "DÁN BẢO VỆ":
            add(f"{brief_hook} {brief_product}")
        elif brief_hook == "LUT MÀU ĐẸP":
            add(f"{brief_hook} CHO {brief_product}")
        else:
            add(f"{brief_product} {brief_hook}")

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
    if _context_is_fan_or_light(early):
        if "LED" in early or "MÀU" in early or "MAU" in _ascii_upper(early):
            add("QUẠT LED TRANG TRÍ GÓC SETUP")
        else:
            add("QUẠT TRANG TRÍ GÓC SETUP")
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
    if "OSMO NANO" in upper or "OSMO ACTION" in upper or "POCKET 3" in upper:
        product_name = _extract_known_product_context(context) or "DJI OSMO"
        hook_context = early or upper
        if any(key in hook_context for key in ("DÁN", "DAN", "BẢO VỆ", "BAO VE", "TRẦY", "TRAY", "XƯỚC", "XUOC")):
            add(f"DÁN BẢO VỆ {product_name}")
        if any(key in hook_context for key in ("SỨC NÓNG", "SUC NONG")):
            add(f"SỨC NÓNG CỦA {product_name}")
        if any(key in hook_context for key in ("LUT", "LÚT", "MÀU", "MAU", "D-LOG", "REC.709")):
            add(f"LUT MÀU ĐẸP CHO {product_name}")
        add(f"{product_name} CÓ ĐÁNG MUA")
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
    if any(term in clean for term in ("OSMO NANO", "OSMO ACTION", "POCKET 3", "DJI OSMO", "D-LOG M", "REC.709")):
        score += 10
    if any(term in clean for term in ("DÁN BẢO VỆ", "LUT MÀU", "SỨC NÓNG")):
        score += 8
    if clean.startswith(("CÁP HDMI", "DÂY HDMI")):
        score += 8
    if "USB" in clean and any(key in clean for key in ("FAKE", "TỐC ĐỘ", "CHÉP NHẠC", "GIÁ RẺ")):
        score += 10
    if ("LOA" in clean or "MOMO" in clean) and any(key in clean for key in ("THANH TOÁN", "GIẤY PHÉP", "SIM 4G", "MOMO")):
        score += 10
    if "BĂNG KEO" in clean and any(key in clean for key in ("IN SẴN", "IN CHỮ", "ĐÓNG GÓI", "TIỆN")):
        score += 10
    if any(key in clean for key in ("KÍNH CƯỜNG LỰC", "DÁN KÍNH", "MIẾNG DÁN", "BAYFAST", "XỐP ĐÓNG GÓI")):
        score += 10
    if any(key in clean for key in ("ỐP ĐIỆN THOẠI", "ỐP LƯNG", "ỐP BẢO VỆ")):
        score += 10
    if ("QUẠT" in clean or "LED" in clean) and any(key in clean for key in ("TRANG TRÍ", "SETUP", "GÓC")):
        score += 14
    category = _context_product_category(source_title, segments)
    if category and _title_matches_product_category(clean, category):
        score += 12
        if category == "charger" and any(key in clean for key in ("SẠC", "ANKER", "GAN", "W", "MACBOOK")):
            score += 8
        elif category == "light" and any(key in clean for key in ("ĐÈN", "BÓNG", "LED", "VINACO", "VINAKO", "SÁNG")):
            score += 8
        elif category == "tray" and any(key in clean for key in ("KHAY", "A6", "KHUNG", "CHIA")):
            score += 8
        elif category == "fan" and any(key in clean for key in ("QUẠT", "LED", "TRANG TRÍ")):
            score += 8
        elif category == "momo" and any(key in clean for key in ("LOA", "MOMO", "THANH TOÁN", "SIM 4G", "QR")):
            score += 8
        elif category == "tape" and any(key in clean for key in ("BĂNG KEO", "ĐÓNG GÓI", "IN SẴN", "IN CHỮ")):
            score += 8
        elif category == "screen_protector" and any(key in clean for key in ("KÍNH", "CƯỜNG LỰC", "DÁN", "BAYFAST", "XỐP")):
            score += 8
        elif category == "phone_case" and any(key in clean for key in ("ỐP", "BẢO VỆ", "ĐIỆN THOẠI")):
            score += 8
    elif category:
        score -= 24
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
    if "HUB UGREEN HUB" in clean:
        score -= 18
    if "MACBOOK" in clean and "TRÊN IPHONE" in clean:
        score -= 24
    if "ĐƠN GIẢN ĐỂ CÓ MÀU" in clean:
        score -= 14
    if "CHỈ QUAY 15 PHÚT" in clean:
        score -= 30
    if re.search(r"\bOSMO\b.*\b\d+\s+\d+\s+TRIỆU\b", clean) or "TRIỆU BỊ" in clean:
        score -= 28
    if "DJI OSMO POCKET 3 CÁCH KIẾM TIỀN" in clean:
        score -= 18
    if clean == "GÓC SETUP THIẾU QUẠT LED NÀY":
        score -= 14
    if clean == "ĐÈN 60W SÁNG THẬT HAY ẢO":
        score -= 10
    if "60FPS" in clean and "HDMI" in clean:
        score -= 18
    if "KHAY" in context and "KHUNG" in clean:
        score -= 22
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
        elif flag.startswith("unsupported_price:"):
            reasons.append("loại giá chưa có bằng chứng")
        elif flag.startswith("product_mismatch:"):
            reasons.append("sản phẩm chính chưa khớp transcript")
        else:
            reasons.append(flag.replace("_", " "))
    if status == "expert_checked" and not reasons:
        reasons.append("đúng thuật ngữ và bám hook")
    elif status == "fallback" and not reasons:
        reasons.append("title chưa đạt gate")
    publish_status = {
        "expert_checked": "ready",
        "needs_review": "review",
        "fallback": "fallback",
    }.get(status, "review")
    publish_label = {
        "ready": "Đăng được ngay",
        "review": "Cần xem lại",
        "fallback": "Chặn trước render",
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


def _one_shot_final_status(
    title_quality: dict | None,
    layout_quality: dict | None,
    review: dict | None = None,
    industry_quality: dict | None = None,
    technical_quality: dict | None = None,
) -> str:
    technical_quality = technical_quality if isinstance(technical_quality, dict) else {}
    if technical_quality and not bool(technical_quality.get("ok", True)):
        return "failed_technical"
    industry_quality = industry_quality if isinstance(industry_quality, dict) else {}
    if industry_quality and not bool(industry_quality.get("ok", True)):
        return "needs_human_review"
    title_publish = str((title_quality or {}).get("publish_status") or "")
    layout_ok = bool((layout_quality or {}).get("ok", True))
    review = review if isinstance(review, dict) else {}
    review_status = str(review.get("status") or "")
    review_blocking = bool(review.get("blocking", False))
    if review_blocking and review_status not in {"network_error", "skipped", "disabled"}:
        return "needs_human_review"
    if review_status == "deepseek_repaired" or str(industry_quality.get("status") or "") == "auto_repaired":
        if layout_ok:
            return "auto_repaired"
    if title_publish == "ready" and layout_ok:
        return "ready"
    if layout_ok and bool(review.get("enabled")) and bool(review.get("ok")) and review_status == "ok":
        return "ready"
    if title_publish in {"review", ""} or not layout_ok:
        return "needs_human_review"
    return "needs_human_review"


def _one_shot_status_label(status: str) -> str:
    return {
        "ready": "Đăng được",
        "auto_repaired": "AI đã sửa",
        "needs_review": "Cần xem lại",
        "needs_human_review": "Cần người xem",
        "blocked_before_render": "Chặn trước render",
        "failed_technical": "Lỗi kỹ thuật",
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
                "brief": parsed.get("brief") if isinstance(parsed.get("brief"), dict) else {},
            }
            titles = parsed.get("titles", [])
            if isinstance(titles, list):
                parsed_titles: list[str] = []
                for item in titles:
                    if isinstance(item, dict):
                        text = item.get("title") or item.get("text") or item.get("thumbnail_title")
                        if text:
                            parsed_titles.append(str(text))
                    elif str(item).strip():
                        parsed_titles.append(str(item))
                out["titles"] = parsed_titles
                return out
            title = parsed.get("title") or parsed.get("suggested_title")
            out["titles"] = [str(title)] if title else []
            return out
        if isinstance(parsed, list):
            return {"titles": [str(t) for t in parsed if str(t).strip()], "upload_title": "", "hashtags": []}
    except Exception:
        pass
    title_matches = re.findall(r'"title"\s*:\s*"([^"]+)"', raw, flags=re.IGNORECASE)
    if title_matches:
        return {
            "titles": [str(t).strip() for t in title_matches if str(t).strip()],
            "upload_title": "",
            "hashtags": [],
            "detected_product": "",
            "main_hook": "",
            "evidence": re.findall(r'"evidence"\s*:\s*"([^"]+)"', raw, flags=re.IGNORECASE),
            "risk_flags": [],
            "brief": {},
        }
    return {
        "titles": [
            line.strip(" -•\t\"'")
            for line in raw.splitlines()
            if line.strip()
            and not re.fullmatch(r"[{}\[\],]*", line.strip())
            and not re.match(r"\s*\"?(?:brief|titles|product|category|hook|evidence|risk|angle|best_index|why_best|needs_review|review_reason)\"?\s*[:\]]", line, flags=re.IGNORECASE)
        ],
        "upload_title": "",
        "hashtags": [],
    }


def _parse_thumbnail_title_payload(raw: str) -> list[str]:
    return list(_parse_thumbnail_title_response(raw).get("titles") or [])


def _pick_best_thumbnail_title(titles: list[str], source_title: str, segments: list[dict] | None = None) -> str:
    context = _thumbnail_context_text(source_title, segments)
    category = _context_product_category(source_title, segments)
    valid: list[str] = []
    for title in titles:
        for clean in _compact_thumbnail_title_variants(title, source_title, segments):
            if category and not _title_matches_product_category(clean, category):
                continue
            if clean and not _is_weak_thumbnail_title(clean, context) and clean not in valid:
                valid.append(clean)
    if not valid:
        return ""
    def rank(title: str) -> tuple[int, int]:
        words = len(title.split())
        readability = 12 if 4 <= words <= 9 else (2 if words == 10 else -10)
        return _score_thumbnail_title(title, source_title, segments) + readability, -abs(words - 7)
    return max(valid, key=rank)


def _best_rule_thumbnail_title(source_title: str, segments: list[dict] | None = None) -> str:
    candidates = _thumbnail_affiliate_candidates(source_title, segments)
    ready = [
        title
        for title in candidates
        if _thumbnail_title_quality(title, source_title, segments).get("publish_status") == "ready"
    ]
    if ready:
        return max(ready, key=lambda t: _score_thumbnail_title(t, source_title, segments))
    return ""


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
    brief = _human_content_brief(source_title, segments)
    candidates = _thumbnail_affiliate_candidates(source_title, segments)
    candidate_text = "\n".join(f"- {title}" for title in candidates) or "- Không có"
    mode_hint = {
        "viral": "Ưu tiên hook mạnh hơn nhưng vẫn đúng transcript, không giật tít sai.",
        "short": "Ưu tiên title cực ngắn 4-6 từ, dễ đọc trong thumbnail.",
        "expert": "Ưu tiên đúng chuyên ngành, tự nhiên, không sai thuật ngữ.",
    }.get(mode, "Ưu tiên đúng chuyên ngành, tự nhiên, không sai thuật ngữ.")
    industry = _one_shot_industry(settings)
    industry_hint = (
        "- Ngành tài chính: hook chuyển đổi an toàn; dùng đúng thuật ngữ BTC, ETH, VNINDEX, Fed, CPI, lãi suất, thanh khoản, funding, leverage, spot/futures, DCA, stop loss, risk/reward. "
        "Không viết chắc thắng, lợi nhuận đảm bảo, all-in, x tài khoản, tín hiệu mua/bán nếu transcript không nói rõ."
        if industry == "finance"
        else "- Ngành công nghệ/affiliate: ưu tiên sản phẩm chính + pain/use-case + lợi ích mua hàng có bằng chứng."
    )
    brief_product = str(brief.get("product") or "").strip()
    brief_hook = str(brief.get("hook") or "").strip()
    brief_confidence = float(brief.get("confidence") or 0.0)
    brief_constraint = ""
    if brief_product and brief_confidence >= 0.7:
        brief_constraint = (
            f"BẮT BUỘC: Sản phẩm chính là `{brief_product}`. "
            f"TẤT CẢ title phải chứa hoặc liên quan đến `{brief_product}`. "
            f"Không được đổi sang sản phẩm khác. "
            f"Transcript chỉ dùng để tìm hook/angle cho `{brief_product}`."
        )
    elif brief_product:
        brief_constraint = (
            f"Sản phẩm đoán: `{brief_product}`, hook `{brief_hook}`. "
            f"Chỉ đổi sản phẩm nếu transcript RÕ RÀNG nói về sản phẩm khác."
        )

    prompt = f"""
Bạn là strategist thumbnail TikTok cho kênh affiliate bán hàng viral tiếng Việt.
Hãy đọc hết transcript, hiểu sản phẩm chính trước, rồi tạo title thumbnail tối ưu cho chuyển đổi.

Mục tiêu:
- {brief_constraint}
- Làm đơn giản từ gốc: sản phẩm chính + lợi ích/hook có bằng chứng.
- Mode đang chọn: {mode_hint}
- Ưu tiên hook/pain/use-case chính trong 5-18 giây đầu.
- Không kéo sản phẩm phụ ở cuối video lên thumbnail nếu nó không giải quyết pain chính.
- Nếu video là tutorial/lỗi phần mềm, dùng pain hoặc hành động chính.
- Nếu video là phụ kiện/sản phẩm, dùng sản phẩm + lợi ích cụ thể.
- 4-9 từ là tốt nhất, tối đa 12 từ.
- Ngôn ngữ tự nhiên, dễ đọc trong 1 giây, kiểu thumbnail BoxPhoneFarm.
- Không dùng câu generic kiểu "Làm thế nào để...".
- Không bịa sản phẩm/giá/thông số nếu transcript không nói.
- Tự sửa lỗi ASR rõ ràng: "set play/sét play" = "CH Play", "Samsung Deck" = "Samsung Dex", "xóp" = "xốp".
- Tự sửa lỗi ASR sản phẩm: "hấp/háp/hap Samsung Dex/4K/120Hz/HDMI" = "hub".
- Từ chuyên ngành đúng: "Pocket Bar" thường là "Pocket 3"; "Osmo một/Ốt Muôn Ano/Otmolano" thường là "Osmo Nano" nếu ngữ cảnh DJI; "tu vit/tô vít" = "tua vít"; BayFast, kính cường lực, miếng dán, dán kính, khung tự dán, xốp đóng gói, ốp điện thoại.
- Candidate bên dưới chỉ để tham khảo. Không dùng nếu lệch sản phẩm chính.
- {industry_hint}
- Trả JSON thuần, không markdown:
{{"brief":{{"product":"...","category":"...","hook":"...","evidence":["..."],"risk":"low|medium|high"}},"titles":[{{"title":"...","angle":"bán hàng"}},{{"title":"...","angle":"pain/use-case"}},{{"title":"...","angle":"bằng chứng"}}],"upload_title":"...","caption_short":"...","caption_full":"...","hashtags":["#..."],"detected_product":"...","main_hook":"...","evidence":["..."],"risk_flags":[]}}

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
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.35,
                        "maxOutputTokens": 2048,
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
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
                    "brief": parsed.get("brief", {}),
                    "title_candidates": parsed.get("titles", []),
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
                log_cb(f"Gemini thumbnail title lỗi: {_redact_secret_text(e)}")
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
    brief = _human_content_brief(source_title, segments)
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
    industry = _one_shot_industry(settings)
    industry_hint = (
        "Ngành tài chính: title phải có hook chuyển đổi an toàn, đúng thuật ngữ BTC/ETH/VNINDEX/Fed/CPI/lãi suất/thanh khoản/funding/leverage/spot/futures/DCA/stop loss/risk-reward. "
        "Cấm claim chắc thắng, lợi nhuận đảm bảo, all-in, x tài khoản, tín hiệu mua/bán nếu transcript không có bằng chứng."
        if industry == "finance"
        else "Ngành công nghệ/affiliate: bám sản phẩm chính, pain/use-case, lợi ích mua hàng có bằng chứng."
    )
    user = f"""
Đọc transcript video one-shot và tạo 3 tiêu đề thumbnail tối ưu cho chuyển đổi.

Tiêu chí:
- Brief nội bộ đang đoán: sản phẩm `{brief.get("product", "")}`, hook `{brief.get("hook", "")}`. Nếu transcript cho thấy brief sai, hãy sửa bằng title đúng.
- Làm đơn giản từ gốc: sản phẩm chính + lợi ích/hook có bằng chứng.
- Mode đang chọn: {mode_hint}
- Nếu có một hành động/giải pháp rõ trong transcript, ưu tiên title dạng hành động hơn title chỉ nêu vấn đề.
- Ưu tiên pain/use-case trong 5-18 giây đầu.
- Nếu video là lỗi/tutorial, title phải bám pain hoặc hành động chính.
- Nếu video là sản phẩm/phụ kiện, title phải bám sản phẩm chính + lợi ích chính.
- Không kéo sản phẩm phụ ở cuối video lên thumbnail nếu nó không giải quyết hook chính.
- 4-9 từ là tốt nhất, tối đa 12 từ.
- Tự sửa lỗi ASR rõ ràng: "set play/sét play" = "CH Play", "Samsung Deck" = "Samsung Dex", "xóp" = "xốp".
- Tự sửa lỗi ASR sản phẩm: "hấp/háp/hap Samsung Dex/4K/120Hz/HDMI" = "hub".
- Từ chuyên ngành đúng: "Pocket Bar" thường là "Pocket 3"; "Osmo một/Ốt Muôn Ano/Otmolano" thường là "Osmo Nano" nếu ngữ cảnh DJI; "tu vit/tô vít" = "tua vít"; BayFast, kính cường lực, miếng dán, dán kính, khung tự dán, xốp đóng gói, ốp điện thoại.
- Candidate bên dưới chỉ để tham khảo. Không dùng nếu lệch sản phẩm chính.
- {industry_hint}
- Tránh title sai/ngượng: "Đăng nhập game CH Play trên Samsung Dex", tên file DJI/IMG/MP4, hoặc title chung chung.
- Trả JSON đúng format:
{{"brief":{{"product":"...","category":"...","hook":"...","evidence":["..."],"risk":"low|medium|high"}},"titles":[{{"title":"...","angle":"bán hàng"}},{{"title":"...","angle":"pain/use-case"}},{{"title":"...","angle":"bằng chứng"}}],"upload_title":"...","caption_short":"...","caption_full":"...","hashtags":["#..."],"detected_product":"...","main_hook":"...","evidence":["..."],"risk_flags":[]}}

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
                "model": "deepseek-v4-flash",
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
        model = str(data.get("model") or "deepseek-v4-flash")
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
                "brief": parsed.get("brief", {}),
                "title_candidates": parsed.get("titles", []),
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
            log_cb(f"DeepSeek chat title lỗi: {_redact_secret_text(e)}")

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
                "brief": parsed.get("brief", {}),
                "title_candidates": parsed.get("titles", []),
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
            log_cb(f"DeepSeek Pro title lỗi: {_redact_secret_text(e)}")
    return "", "", costs


def _deepseek_repair_thumbnail_title(
    settings: dict,
    segments: list[dict] | None,
    source_title: str,
    current_title: str,
    reject_reasons: list[str] | None = None,
    log_cb=None,
) -> tuple[str, dict, list[dict]]:
    """Use DeepSeek as a second-pass title reviewer when deterministic gate rejects a title."""
    api_key = _configured_ai_key(settings, "DEEPSEEK_API_KEY", "ds_api_key")
    if not api_key:
        if log_cb:
            log_cb("DeepSeek repair bỏ qua vì thiếu DeepSeek API key")
        return "", {}, []
    segments = segments or []
    context = _thumbnail_context_text(source_title, segments)
    full_transcript = "\n".join(str(seg.get("text", "")) for seg in segments[:180])
    reasons = "; ".join(str(r) for r in (reject_reasons or []) if str(r).strip()) or "gate chưa đạt"
    brief = _human_content_brief(source_title, segments)
    industry = _one_shot_industry(settings)
    industry_hint = (
        "Nếu là tài chính: title được phép hook mạnh nhưng không được cam kết lợi nhuận, chắc thắng, all-in, x tài khoản, tín hiệu mua/bán nếu transcript không có bằng chứng; chuẩn thuật ngữ BTC, ETH, VNINDEX, Fed, CPI, lãi suất, thanh khoản, DCA, stop loss."
        if industry == "finance"
        else "Nếu là công nghệ/affiliate: title phải bám sản phẩm chính + lợi ích/pain có bằng chứng, không bịa giá/thông số."
    )
    system = (
        "Bạn là reviewer title thumbnail TikTok affiliate tiếng Việt. "
        "Nhiệm vụ của bạn giống một editor người thật: đọc transcript, hiểu sản phẩm chính, "
        "sửa title bị gate loại, không bịa sản phẩm/thông số/giá. Trả JSON hợp lệ, không markdown."
    )
    user = f"""
Title hiện tại bị loại bởi gate.

Tên file nguồn: {source_title}
Title hiện tại: {current_title}
Lý do bị loại: {reasons}
Brief nội bộ: product={brief.get("product", "")}, hook={brief.get("hook", "")}

Yêu cầu:
- Đọc transcript rồi trả 2-3 title mới.
- Title phải có sản phẩm chính rõ ràng, không dùng tên file DJI/MP4.
- Không dùng hook chung chung như "đồ công nghệ", "phụ kiện công nghệ" nếu transcript có sản phẩm cụ thể.
- Không bịa brand/sản phẩm/thông số/giá ngoài transcript.
- Sửa lỗi ASR ngành: MagSafe, iPhone, Samsung Dex, Hub, HDMI, Type-C, Osmo Nano, D-LOG M, REC.709, góc setup, BayFast, kính cường lực, dán kính, xốp đóng gói, ốp điện thoại.
- {industry_hint}
- 4-10 từ, đọc được trên thumbnail.
- Nếu title cũ sai vì không bám sản phẩm chính, đổi hẳn sang sản phẩm chính.

Trả JSON:
{{"titles":[{{"title":"...","why":"..."}},{{"title":"...","why":"..."}}],"upload_title":"...","hashtags":["#..."],"detected_product":"...","main_hook":"...","evidence":["..."],"risk_flags":[]}}

Transcript:
{full_transcript[:12000]}

Context gộp:
{context[:2500]}
""".strip()
    costs: list[dict] = []
    for model, temp, max_tokens in (("deepseek-v4-flash", 0.35, 450), ("deepseek-v4-pro", 0.25, 650)):
        try:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temp,
                    "max_tokens": max_tokens,
                },
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()
            actual_model = str(data.get("model") or model)
            cost = _estimate_ai_cost("deepseek", actual_model, data.get("usage", {}))
            costs.append(cost)
            raw = data["choices"][0]["message"].get("content", "").strip()
            parsed = _parse_thumbnail_title_response(raw)
            title = _pick_best_thumbnail_title(parsed.get("titles") or [], source_title, segments)
            quality = _thumbnail_title_quality(title, source_title, segments) if title else {}
            if title and quality.get("publish_status") == "ready":
                metadata = {
                    "provider": f"deepseek_repair:{actual_model}",
                    "upload_title": parsed.get("upload_title", ""),
                    "hashtags": parsed.get("hashtags", []),
                    "detected_product": parsed.get("detected_product", ""),
                    "main_hook": parsed.get("main_hook", ""),
                    "evidence": parsed.get("evidence", []),
                    "risk_flags": parsed.get("risk_flags", []),
                    "brief": parsed.get("brief", {}),
                    "title_candidates": parsed.get("titles", []),
                }
                if log_cb:
                    log_cb(f"DeepSeek repair OK ({actual_model}) · {title} · ${cost['estimated_usd']:.6f} ~ {cost['estimated_vnd']}đ")
                return title, metadata, costs
            if log_cb:
                log_cb(f"DeepSeek repair chưa qua gate ({actual_model}): {title or 'no title'}")
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (401, 403):
                if log_cb:
                    log_cb("DeepSeek repair key không hợp lệ/chưa có quyền")
                return "", {}, costs
            if status == 402:
                if log_cb:
                    log_cb("DeepSeek repair hết credit 402")
                return "", {}, costs
            if log_cb:
                log_cb(f"DeepSeek repair lỗi ({model}): {_redact_secret_text(e)}")
    return "", {}, costs


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


def _validate_thumbnail_lines(title: str, lines: list[str] | None) -> tuple[list[str], dict]:
    expected = _clean_thumbnail_title(title)
    cleaned = [_clean_thumbnail_title(str(line or "").strip()) for line in (lines or [])]
    cleaned = [line for line in cleaned if line]
    issues: list[str] = []
    if not 1 < len(cleaned) <= 4:
        issues.append("line_count_not_2_to_4")
    if _clean_thumbnail_title(" ".join(cleaned)) != expected:
        issues.append("line_words_changed")
    joined = " / ".join(cleaned)
    for phrase in _THUMB_SEMANTIC_PHRASES:
        if _phrase_is_split(joined, phrase):
            issues.append("split_semantic_phrase")
            break
    if _thumbnail_bad_tail_count(cleaned):
        issues.append("bad_line_tail")
    if any(len(line.split()) == 1 and len(line) <= 6 for line in cleaned):
        issues.append("orphan_short_line")
    widths = [len(line) for line in cleaned]
    if widths and len(widths) >= 3 and min(widths) / max(widths) < 0.34:
        issues.append("unbalanced_text_lines")
    return cleaned, {
        "ok": not issues,
        "issues": issues,
        "joined": joined,
        "line_count": len(cleaned),
    }


def _local_thumbnail_line_decision(title: str) -> dict:
    candidates = _thumbnail_line_candidates(title, "auto")
    best_lines: list[str] = []
    best_score: int | None = None
    best_gate: dict = {}
    for lines in candidates:
        _cleaned, gate = _validate_thumbnail_lines(title, lines)
        widths = [len(line) for line in lines]
        balance = int((min(widths) / max(widths)) * 100) if widths and max(widths) else 0
        score = balance + (80 if gate["ok"] else 0) - len(gate["issues"]) * 90 - abs(len(lines) - 2) * 8
        if best_score is None or score > best_score:
            best_lines = list(lines)
            best_score = score
            best_gate = gate
    if not best_lines:
        best_lines = _split_thumbnail_lines(title)
        _cleaned, best_gate = _validate_thumbnail_lines(title, best_lines)
    return {
        "source": "local_semantic",
        "lines": best_lines,
        "validation": best_gate,
        "costs": [],
        "reason": "Local semantic composer giữ cụm nghĩa và loại line-break gãy nghĩa.",
    }


def _deepseek_thumbnail_line_decision(
    settings: dict,
    title: str,
    source_title: str = "",
    segments: list[dict] | None = None,
    log_cb=None,
) -> dict:
    local_decision = _local_thumbnail_line_decision(title)
    api_key = _configured_ai_key(settings, "DEEPSEEK_API_KEY", "ds_api_key")
    if not api_key:
        return {**local_decision, "source": "local_semantic_no_api"}
    transcript = "\n".join(
        f"[{float(seg.get('start', 0.0) or 0.0):.1f}] {str(seg.get('text', '')).strip()}"
        for seg in (segments or [])[:45]
        if str(seg.get("text", "")).strip()
    )
    system = (
        "Bạn là chuyên gia typography thumbnail TikTok tiếng Việt. "
        "Nhiệm vụ duy nhất: chia title đã chốt thành 2-4 dòng theo nghĩa, không viết lại title, "
        "không thêm/bớt từ, không đổi thứ tự từ. Trả JSON hợp lệ, không markdown."
    )
    user = f"""
Title đã chốt: {title}
Tên file/context: {source_title}

Yêu cầu chia dòng:
- Giữ nguyên toàn bộ từ trong title, đúng thứ tự.
- Không bẻ cụm nghĩa. Ví dụ đúng: "CHUỘT KHÔNG DÂY" / "KHÔNG CẦN THAY PIN".
- Ví dụ sai: "CHUỘT KHÔNG" / "DÂY KHÔNG" / "CẦN THAY PIN".
- Không để dòng cụt một từ ngắn nếu còn cách khác.
- Ưu tiên 2 dòng nếu đọc rõ, 3 dòng nếu title dài.
- Mỗi dòng là một ý đọc lướt được trong 1 giây.

Trả JSON:
{{"lines":["...","..."],"reason":"vì sao chia như vậy","confidence":0.0}}

Transcript/context ngắn để hiểu nghĩa:
{transcript[:4000]}
""".strip()
    costs: list[dict] = []
    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.1,
                "max_tokens": 260,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        actual_model = str(data.get("model") or "deepseek-v4-flash")
        costs.append(_estimate_ai_cost("deepseek", actual_model, data.get("usage", {}), kind="typography"))
        raw = data["choices"][0]["message"].get("content", "").strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1].removeprefix("json").strip()
        parsed = json.loads(raw)
        ai_lines = parsed.get("lines") if isinstance(parsed, dict) else []
        cleaned, validation = _validate_thumbnail_lines(title, ai_lines if isinstance(ai_lines, list) else [])
        if validation.get("ok"):
            if log_cb:
                cost = _sum_ai_costs(costs)
                log_cb(f"DeepSeek typography OK · {validation.get('joined')} · ${cost['estimated_usd']:.6f} ~ {cost['estimated_vnd']}đ")
            return {
                "source": "deepseek_typography",
                "lines": cleaned,
                "validation": validation,
                "costs": costs,
                "reason": str(parsed.get("reason") or "AI chia dòng theo nghĩa").strip()[:280],
            }
        if log_cb:
            log_cb("DeepSeek typography bị local gate loại — thử Gemini backup")
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if log_cb and status not in (401, 403):
            log_cb(f"DeepSeek typography lỗi — thử Gemini backup: {_redact_secret_text(exc)}")
    gemini_decision = _gemini_thumbnail_line_decision(settings, title, source_title, segments, log_cb)
    gemini_costs = gemini_decision.get("costs", []) if isinstance(gemini_decision.get("costs"), list) else []
    if gemini_decision.get("source") == "gemini_typography":
        return {**gemini_decision, "costs": costs + gemini_costs}
    return {
        **local_decision,
        "costs": costs + gemini_costs,
        "ai_fallback_reason": "deepseek_failed_or_rejected",
    }


def _gemini_thumbnail_line_decision(
    settings: dict,
    title: str,
    source_title: str = "",
    segments: list[dict] | None = None,
    log_cb=None,
) -> dict:
    api_key = _configured_ai_key(settings, "GEMINI_API_KEY", "gemini_api_key")
    if not api_key:
        return {"source": "gemini_skipped_no_api", "lines": [], "validation": {"ok": False}, "costs": []}
    model = str(settings.get("gemini_text_model", "gemini-2.5-flash-lite") or "gemini-2.5-flash-lite")
    if model == "auto":
        model = "gemini-2.5-flash-lite"
    transcript = "\n".join(
        f"[{float(seg.get('start', 0.0) or 0.0):.1f}] {str(seg.get('text', '')).strip()}"
        for seg in (segments or [])[:45]
        if str(seg.get("text", "")).strip()
    )
    prompt = f"""
Bạn là chuyên gia typography thumbnail TikTok tiếng Việt.
Chia title đã chốt thành 2-4 dòng theo nghĩa.

Luật cứng:
- Giữ nguyên toàn bộ từ trong title, đúng thứ tự.
- Không viết lại title, không thêm từ, không bỏ từ.
- Không để dòng cụt một từ ngắn nếu còn cách tốt hơn.
- Ưu tiên các dòng đọc thành cụm nghĩa tự nhiên.

Title: {title}
Context: {source_title}
Transcript ngắn:
{transcript[:4000]}

Trả JSON thuần:
{{"lines":["...","..."],"reason":"...","confidence":0.0}}
""".strip()
    costs: list[dict] = []
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=35,
        )
        resp.raise_for_status()
        payload = resp.json()
        costs.append(_estimate_gemini_cost(model, payload.get("usageMetadata"), kind="typography"))
        raw = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1].removeprefix("json").strip()
        parsed = json.loads(raw)
        lines = parsed.get("lines") if isinstance(parsed, dict) else []
        cleaned, validation = _validate_thumbnail_lines(title, lines if isinstance(lines, list) else [])
        if validation.get("ok"):
            if log_cb:
                cost = _sum_ai_costs(costs)
                log_cb(f"Gemini typography OK · {validation.get('joined')} · ${cost['estimated_usd']:.6f} ~ {cost['estimated_vnd']}đ")
            return {
                "source": "gemini_typography",
                "lines": cleaned,
                "validation": validation,
                "costs": costs,
                "reason": str(parsed.get("reason") or "Gemini chia dòng theo nghĩa").strip()[:280],
            }
        if log_cb:
            log_cb("Gemini typography bị local gate loại — dùng local fallback")
    except Exception as exc:
        if log_cb:
            log_cb(f"Gemini typography lỗi — dùng local fallback: {_redact_secret_text(exc)}")
    return {"source": "gemini_rejected_or_failed", "lines": [], "validation": {"ok": False}, "costs": costs}


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
    if segments and ai_title:
        if log_cb:
            log_cb("AI title chưa đạt gate — chạy AI nâng cao trước khi fallback")
        provider_state["force_advanced_title"] = True
        gemini_title = _gemini_thumbnail_title_from_settings(settings, segments, source_title, log_cb, mode, provider_state)
        if gemini_title and _thumbnail_title_quality(gemini_title, source_title, segments).get("publish_status") == "ready":
            return gemini_title, "gemini_advanced", costs
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
- Sửa từ ngành nếu sai: hub, Samsung Dex, HDMI, Type-C, USB-C, Pocket 3, tua vít, iPhone, CH Play, BayFast, kính cường lực, dán kính, xốp đóng gói, ốp điện thoại.
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
                log_cb(f"AI review thumbnail bỏ qua do lỗi mạng/API: {_redact_secret_text(e)}")
            else:
                log_cb(f"Gemini review thumbnail lỗi: {_redact_secret_text(e)}")
        error_text = _redact_secret_text(e)
        return {
            "enabled": True,
            "provider": "gemini",
            "attempted": True,
            "status": "network_error" if network_error else "failed",
            "blocking": not network_error,
            "ok": False,
            "score": 0.0,
            "issues": [error_text[:160]],
            "suggested_title": "",
            "error": error_text[:240],
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
        *_resource_path_candidates("assets", "fonts", font_file),
        Path.home() / "Downloads" / "DT-Phudu" / "Fonts Files" / font_file,
        *_resource_path_candidates("assets", "fonts", "DTPhudu-Black.otf"),
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
        bad_tail = _thumbnail_bad_tail_count(parts)
        joined_parts = " / ".join(parts)
        split_protected = sum(_phrase_is_split(joined_parts, phrase) for phrase in _THUMB_SEMANTIC_PHRASES)
        orphan = sum(len(part) <= 4 for part in parts)
        phrase_bonus = sum(
            any(phrase in part for phrase in (*_THUMB_PROTECTED_PHRASES, "HUB 511"))
            for part in parts
        )
        price_tail_bonus = 10 if re.search(r"\b\d+[.,]?\d*\s*K\b", parts[-1], flags=re.IGNORECASE) else 0
        return (
            (max(widths) - min(widths)) * 7
            + max(widths) * 3
            + bad_tail * 190
            + split_protected * 720
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
    for phrase in _THUMB_SEMANTIC_PHRASES:
        if _phrase_is_split(joined, phrase):
            issues.append("split_semantic_phrase")
            break
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
    forced_lines: list[str] | None = None,
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
    safe_top = 330
    safe_right = out_w - 54
    safe_bottom = 1240
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
    forced_clean, forced_validation = _validate_thumbnail_lines(title, forced_lines)
    if not forced_validation.get("ok"):
        local_decision = _local_thumbnail_line_decision(title)
        forced_clean, forced_validation = _validate_thumbnail_lines(
            title,
            local_decision.get("lines") if isinstance(local_decision.get("lines"), list) else [],
        )
    candidate_pool = [forced_clean] if forced_validation.get("ok") else _thumbnail_line_candidates(title, line_mode)

    for candidate in candidate_pool:
        cap_size = caps[size_preset].get(len(candidate), 106)
        size = cap_size
        stroke = max(6, int(size * 0.075))
        font = make_font(size)
        line_gap = max(10, int(size * 0.075))
        boxes = [text_bbox(font, line, stroke) for line in candidate]
        widths = [box[2] - box[0] for box in boxes]
        heights = [box[3] - box[1] for box in boxes]
        line_slot_h = max(max(heights or [0]), int(size * 0.82) + stroke * 2)
        total_h = line_slot_h * len(candidate) + line_gap * max(0, len(candidate) - 1)
        while size > 54 and (max(widths or [0]) > text_w or total_h > safe_h):
            size -= 2
            stroke = max(6, int(size * 0.075))
            font = make_font(size)
            line_gap = max(10, int(size * 0.075))
            boxes = [text_bbox(font, line, stroke) for line in candidate]
            widths = [box[2] - box[0] for box in boxes]
            heights = [box[3] - box[1] for box in boxes]
            line_slot_h = max(max(heights or [0]), int(size * 0.82) + stroke * 2)
            total_h = line_slot_h * len(candidate) + line_gap * max(0, len(candidate) - 1)
        max_w = max(widths or [1])
        min_w = min(widths or [1])
        width_ratio = round(min_w / max_w, 3) if max_w else 1.0
        bad_tail = _thumbnail_bad_tail_count(candidate)
        joined_lines = " / ".join(candidate)
        split_phrase = sum(
            _phrase_is_split(joined_lines, phrase)
            for phrase in _THUMB_SEMANTIC_PHRASES
        )
        packed_spec_penalty = 1 if re.search(r"\bHDMI\s+2\.[01]\s+4K\s+120HZ\b", joined_lines) else 0
        orphan = sum(len(line) <= 4 for line in candidate)
        word_count = len(" ".join(candidate).split())
        preferred_lines = 2 if word_count <= 6 else (3 if word_count <= 10 else 4)
        layout_score = (
            size * 10
            + int(width_ratio * 120)
            - bad_tail * 260
            - split_phrase * 1800
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

    requested_position = str(position or "center").strip().lower()
    position = requested_position if requested_position in {"center", "lower", "higher"} else "center"
    manual_factors = {"higher": 0.26, "center": 0.56, "lower": 0.80}
    y0 = int(safe_top + max(0, (safe_h - total_h) * manual_factors[position]))
    layout_anchor = position
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
        "forced_lines": forced_clean if forced_validation.get("ok") else [],
        "forced_lines_validation": forced_validation,
        "position": position,
        "requested_position": requested_position,
        "layout_anchor": layout_anchor,
        "layout_zone_score": {},
        "layout_zone_candidates": [],
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
  "voice": {"provider": "elevenlabs", "voiceId": "${ELEVENLABS_VOICE_ID}", "speed": 1.0},
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
                    model = _deepseek_script_model(settings, engine_env)
                    prefix = f"fallback từ {selected_label} → " if provider != selected else ""
                    self.progress.emit(f"AI đang viết script… ({prefix}DeepSeek · {model})")
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
        model = _deepseek_script_model({}, engine_env)
        payload = {
            "model": model,
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
        provider = "elevenlabs"
        voice_key = "ELEVENLABS_VOICE_ID"
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
            media_tools = _media_tools_report(self.settings)
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
                simple_pipeline = bool(
                    self.options.get("simple_pipeline")
                    or str(self.settings.get("one_shot_pipeline_mode") or "").strip().lower() in {"simple", "fast", "lite"}
                )
                use_gemini_cuts = bool(self.options.get("use_gemini_cuts", True)) and not simple_pipeline
                if use_gemini_cuts and transcript_segments:
                    ai_cuts = self._gemini_cut_suggestions(transcript_segments, duration)
                    cuts = self._normalize_cut_candidates(ai_cuts + silence_cuts, duration)
                else:
                    cuts = self._normalize_cut_candidates(silence_cuts, duration)
                    if simple_pipeline:
                        self._log("Simple mode: chỉ cắt khoảng lặng, bỏ Gemini cut")
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
            evidence_quotes = [
                {
                    "start": round(float(seg.get("start", 0.0) or 0.0), 2),
                    "end": round(float(seg.get("end", 0.0) or 0.0), 2),
                    "text": str(seg.get("text", "")).strip(),
                }
                for seg in transcript_segments[:18]
                if str(seg.get("text", "")).strip()
            ]
            claim_ledger = {
                "allowed_claims": [
                    {"claim": m.group(0), "source": "transcript"}
                    for m in re.finditer(r"\b\d{1,4}\s*(?:K|NGHÌN|TRIỆU|TR|Đ|VNĐ|USD|USDT|%)\b", _thumbnail_context_text(title, transcript_segments), flags=re.IGNORECASE)
                ][:8],
                "forbidden_claims": [
                    {"claim": "giá thiếu đơn vị", "rule": "price_unit_required"},
                    {"claim": "hot/top/bán chạy nếu không có evidence", "rule": "no_hype_without_evidence"},
                ],
                "review_claims": [],
            }
            certified_script_pack = {
                "pipeline_version": ONE_SHOT_PIPELINE_VERSION,
                "script_status": "certified" if transcript_segments else "needs_repair",
                "script_quality_score": 85 if transcript_segments else 70,
                "main_product": str((metadata_plan.get("upload_metadata") or {}).get("upload_title") or thumb_suggestion),
                "main_hook": thumb_suggestion,
                "evidence_map": evidence_quotes,
                "claim_ledger": claim_ledger,
                "do_not_use": [
                    "transcript thô làm title trực tiếp",
                    "tên file camera",
                    "giá thiếu đơn vị",
                    "sản phẩm phụ thành sản phẩm chính",
                ],
                "title_directions": ["product_benefit", "pain_problem", "price_value", "use_case_setup", "warning_mistake"],
            }
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
                "media_tools": media_tools,
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
                "enterprise_pipeline": bool(self.options.get("enterprise_pipeline", self.settings.get("one_shot_enterprise_pipeline", True))),
                "certified_script_pack": certified_script_pack,
                "claim_ledger": claim_ledger,
                "evidence_map": evidence_quotes,
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
    log_line = pyqtSignal(str)
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

    def _log(self, line: str) -> None:
        try:
            self.log_line.emit(line)
        except Exception:
            pass

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
            if bool(self.settings.get("one_shot_apply_lut", True)) and not lut_src:
                lut_src = _default_dji_lut_path()
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
            industry_qa = _industry_qa_report(title, source.stem, segments, self.settings)
            if str(industry_qa.get("status") or "") == "auto_repaired" and industry_qa.get("normalized_title"):
                title = str(industry_qa["normalized_title"])
            base = _thumbnail_output_path(out_dir, source.stem, title)
            preview = base.with_name(f"{base.stem}_preview{base.suffix}")
            line_decision = _deepseek_thumbnail_line_decision(
                self.settings,
                title,
                source.stem,
                segments,
                self._log,
            )
            style = _draw_boxphonefarm_thumbnail(
                frame_path,
                preview,
                title,
                str(self.settings.get("one_shot_thumbnail_font", "dt_phudu_black") or "dt_phudu_black"),
                str(self.settings.get("one_shot_thumbnail_size", "large") or "large"),
                str(self.settings.get("one_shot_thumbnail_lines", "auto") or "auto"),
                str(self.settings.get("one_shot_thumbnail_position", "center") or "center"),
                line_decision.get("lines") if isinstance(line_decision.get("lines"), list) else None,
            )
            style["line_decision"] = {k: v for k, v in line_decision.items() if k != "costs"}
            layout_quality = _thumbnail_layout_quality(style, _thumbnail_render_title(title, source.stem, segments)[1])
            title_quality = _thumbnail_title_quality(title, source.stem, segments)
            original_title = _clean_thumbnail_title(str(plan.get("thumbnail_title_suggestion", "")).strip() or source.stem, source.stem, segments)
            ai_metadata = (
                plan.get("ai_metadata_suggestion")
                if title == original_title and isinstance(plan.get("ai_metadata_suggestion"), dict)
                else {}
            )
            metadata_plan = _one_shot_metadata_plan(title, source.stem, segments, self.settings, ai_metadata)
            final_status = _one_shot_final_status(title_quality, layout_quality, industry_quality=industry_qa)
            plan["thumbnail_title_suggestion"] = title
            plan["thumbnail_title_quality"] = title_quality
            plan["title_quality"] = title_quality
            plan["thumbnail_preview"] = str(preview)
            plan["thumbnail_preview_style"] = style
            plan["thumbnail_layout_quality"] = layout_quality
            plan["metadata_plan"] = metadata_plan
            plan["industry_qa"] = industry_qa
            plan["final_status"] = final_status
            self.plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            self.finished.emit(str(preview))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def cancel(self):
        self._cancelled = True


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
            media_tools = _media_tools_report(self.options.get("settings") if isinstance(self.options.get("settings"), dict) else None)
            render_gate_decision = plan.get("render_gate_decision") if isinstance(plan.get("render_gate_decision"), dict) else {}
            simple_pipeline = bool(
                self.options.get("simple_pipeline")
                or plan.get("simple_pipeline")
                or str((self.options.get("settings") or {}).get("one_shot_pipeline_mode") or "").strip().lower() in {"simple", "fast", "lite"}
            )
            if render_gate_decision and not bool(render_gate_decision.get("renderable", True)) and not simple_pipeline:
                reasons = ", ".join(str(r) for r in (render_gate_decision.get("blocking_reasons") or [])[:4])
                raise RuntimeError(f"Render gate chặn trước render: {reasons or render_gate_decision.get('status') or 'không renderable'}")
            source = Path(plan["source_video"])
            out_dir = Path(plan["output_dir"])
            exports_dir = _one_shot_exports_dir(out_dir)
            render_to_final = bool(self.options.get("render_to_final", True))
            render_dir = exports_dir if render_to_final else out_dir
            render_dir.mkdir(parents=True, exist_ok=True)
            probe_t0 = time.perf_counter()
            duration = float(plan.get("duration", 0)) or _ffprobe_duration(source)
            source_info = _ffprobe_video_info(source)
            source_audio_info = _ffprobe_audio_info(source)
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
            industry_settings = {
                **(self.options.get("settings") or {}),
                "industry": self.options.get("industry") or plan.get("industry") or "tech",
            }
            industry_qa = _industry_qa_report(thumb_title, source.stem, plan_segments, industry_settings)
            if str(industry_qa.get("status") or "") == "auto_repaired" and industry_qa.get("normalized_title"):
                thumb_title = str(industry_qa["normalized_title"])
                self._log("Industry QA chuẩn hóa thuật ngữ title")
            thumbnail_quality = _thumbnail_title_quality(thumb_title, source.stem, plan_segments)
            enterprise_pipeline = bool(self.options.get("enterprise_pipeline", True)) and not simple_pipeline
            if enterprise_pipeline and str(thumbnail_quality.get("publish_status") or "") != "ready":
                reasons = []
                reasons.extend(str(r) for r in (thumbnail_quality.get("reasons") or [])[:3])
                reasons.extend(str(r) for r in (thumbnail_quality.get("risk_flags") or [])[:3])
                raise RuntimeError(f"Render gate chặn trước render: title chưa đạt gate ({', '.join(reasons) or thumbnail_quality.get('publish_status') or 'unknown'})")
            render_thumb_title, thumbnail_render_info = _thumbnail_render_title(thumb_title, source.stem, plan_segments)
            if thumbnail_render_info.get("changed"):
                self._log("Đã rút gọn title cho thumbnail")
            metadata_plan = _one_shot_metadata_plan(
                thumb_title,
                source.stem,
                plan_segments,
                industry_settings,
                ai_metadata,
            )
            upload_metadata = metadata_plan["upload_metadata"]
            output_video = Path(self.options.get("output_video") or _upload_video_output_path(render_dir, source.stem, upload_metadata))
            if output_video.exists() and not self.options.get("overwrite", False):
                output_video = _dedupe_path(output_video)

            apply_lut_requested = bool(self.options.get("apply_lut", True))
            lut_path = str(self.options.get("lut_path") or plan.get("lut_path") or "").strip()
            if apply_lut_requested and not lut_path:
                lut_path = _default_dji_lut_path()
            lut_validation = (
                _validate_lut_preflight(
                    source,
                    lut_path=lut_path,
                    out_dir=out_dir,
                    duration=duration,
                    is_cancelled=self._is_cancelled,
                )
                if apply_lut_requested else {"ok": False, "status": "disabled", "reason": "lut_disabled", "test_frame": ""}
            )
            apply_lut = apply_lut_requested and bool(lut_validation.get("ok"))
            noise_mode = _resolve_one_shot_noise_mode(self.options)
            noise_decision = _decide_one_shot_noise(
                source,
                requested_mode=noise_mode,
                duration=duration,
                out_dir=out_dir,
                is_cancelled=self._is_cancelled,
            )
            if noise_decision.get("applied"):
                self._log(f"Noise QA: {noise_decision.get('mode')} · dùng audio đã xử lý")
            elif noise_decision.get("requested"):
                self._log(f"Noise QA: giữ audio gốc · {noise_decision.get('reason')}")
            technical_qa = _technical_qa_report(
                source,
                apply_lut_requested=apply_lut_requested,
                lut_path=lut_path,
                noise_decision=noise_decision,
                duration=duration,
                source_info=source_info,
                audio_info=source_audio_info,
                lut_validation=lut_validation,
                out_dir=out_dir,
            )
            if not technical_qa.get("ok"):
                raise RuntimeError("Technical QA fail: " + ", ".join(str(i) for i in technical_qa.get("issues", [])))
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
                if apply_lut_requested:
                    raise RuntimeError("LUT đã bật nhưng không áp được cho thumbnail frame")
            self._raise_if_cancelled()
            thumbnail = _thumbnail_output_path(out_dir, source.stem, render_thumb_title)
            self._log("[2/5] Tạo thumbnail BoxPhoneFarm")
            thumbnail_font = str(self.options.get("thumbnail_font") or "dt_phudu_black")
            thumbnail_size = str(self.options.get("thumbnail_size") or "large")
            thumbnail_lines = str(self.options.get("thumbnail_lines") or "auto")
            thumbnail_position = str(self.options.get("thumbnail_position") or "center")
            typography_costs: list[dict] = []
            line_decision = _deepseek_thumbnail_line_decision(
                self.options.get("settings") or {},
                render_thumb_title,
                source.stem,
                plan_segments,
                self._log,
            )
            typography_costs.extend(line_decision.get("costs", []) if isinstance(line_decision.get("costs"), list) else [])
            draw_t0 = time.perf_counter()
            thumbnail_style = _draw_boxphonefarm_thumbnail(
                draw_frame_path,
                thumbnail,
                render_thumb_title,
                thumbnail_font,
                thumbnail_size,
                thumbnail_lines,
                thumbnail_position,
                line_decision.get("lines") if isinstance(line_decision.get("lines"), list) else None,
            )
            thumbnail_style["line_decision"] = {k: v for k, v in line_decision.items() if k != "costs"}
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
                bool(self.options.get("ai_review_thumbnail", True)) and not simple_pipeline,
            )
            review_extra_costs: list[dict] = []
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
                    suggested_industry_qa = _industry_qa_report(suggested_title, source.stem, plan_segments, industry_settings)
                    suggested_title = str(suggested_industry_qa.get("normalized_title") or suggested_title)
                    suggested_quality = _thumbnail_title_quality(suggested_title, source.stem, plan_segments)
                    if suggested_quality.get("publish_status") == "ready" and suggested_industry_qa.get("ok"):
                        self._log("AI review sửa thuật ngữ/title — render lại thumbnail")
                        thumb_title = suggested_title
                        industry_qa = suggested_industry_qa
                        thumbnail_quality = suggested_quality
                        render_thumb_title, thumbnail_render_info = _thumbnail_render_title(thumb_title, source.stem, plan_segments)
                        if thumbnail_render_info.get("changed"):
                            self._log("Đã rút gọn title cho thumbnail")
                        metadata_plan = _one_shot_metadata_plan(
                            thumb_title,
                            source.stem,
                            plan_segments,
                            industry_settings,
                            {},
                        )
                        upload_metadata = metadata_plan["upload_metadata"]
                        thumbnail = _thumbnail_output_path(out_dir, source.stem, render_thumb_title)
                        line_decision = _deepseek_thumbnail_line_decision(
                            self.options.get("settings") or {},
                            render_thumb_title,
                            source.stem,
                            plan_segments,
                            self._log,
                        )
                        typography_costs.extend(line_decision.get("costs", []) if isinstance(line_decision.get("costs"), list) else [])
                        thumbnail_style = _draw_boxphonefarm_thumbnail(
                            draw_frame_path,
                            thumbnail,
                            render_thumb_title,
                            thumbnail_font,
                            thumbnail_size,
                            thumbnail_lines,
                            thumbnail_position,
                            line_decision.get("lines") if isinstance(line_decision.get("lines"), list) else None,
                        )
                        thumbnail_style["line_decision"] = {k: v for k, v in line_decision.items() if k != "costs"}
                        thumbnail_layout_quality = _thumbnail_layout_quality(thumbnail_style, thumbnail_render_info)
                        output_video = _upload_video_output_path(render_dir, source.stem, upload_metadata)
                        if output_video.exists() and not self.options.get("overwrite", False):
                            output_video = _dedupe_path(output_video)
                    else:
                        self._log("AI review gợi ý title nhưng gate loại vì thiếu an toàn")
                        repair_title, repair_metadata, repair_costs = _deepseek_repair_thumbnail_title(
                            self.options.get("settings") or {},
                            plan_segments,
                            source.stem,
                            suggested_title or thumb_title,
                            list(suggested_quality.get("reasons") or []) + list(suggested_quality.get("risk_flags") or []),
                            self._log,
                        )
                        if repair_title:
                            self._log("DeepSeek repair sửa title sau AI review — render lại thumbnail")
                            review_extra_costs.extend(repair_costs)
                            repair_industry_qa = _industry_qa_report(repair_title, source.stem, plan_segments, industry_settings)
                            thumb_title = str(repair_industry_qa.get("normalized_title") or repair_title)
                            industry_qa = repair_industry_qa
                            thumbnail_quality = _thumbnail_title_quality(thumb_title, source.stem, plan_segments)
                            render_thumb_title, thumbnail_render_info = _thumbnail_render_title(thumb_title, source.stem, plan_segments)
                            if thumbnail_render_info.get("changed"):
                                self._log("Đã rút gọn title cho thumbnail")
                            metadata_plan = _one_shot_metadata_plan(
                                thumb_title,
                                source.stem,
                                plan_segments,
                                industry_settings,
                                repair_metadata,
                            )
                            upload_metadata = metadata_plan["upload_metadata"]
                            thumbnail = _thumbnail_output_path(out_dir, source.stem, render_thumb_title)
                            line_decision = _deepseek_thumbnail_line_decision(
                                self.options.get("settings") or {},
                                render_thumb_title,
                                source.stem,
                                plan_segments,
                                self._log,
                            )
                            typography_costs.extend(line_decision.get("costs", []) if isinstance(line_decision.get("costs"), list) else [])
                            thumbnail_style = _draw_boxphonefarm_thumbnail(
                                draw_frame_path,
                                thumbnail,
                                render_thumb_title,
                                thumbnail_font,
                                thumbnail_size,
                                thumbnail_lines,
                                thumbnail_position,
                                line_decision.get("lines") if isinstance(line_decision.get("lines"), list) else None,
                            )
                            thumbnail_style["line_decision"] = {k: v for k, v in line_decision.items() if k != "costs"}
                            thumbnail_layout_quality = _thumbnail_layout_quality(thumbnail_style, thumbnail_render_info)
                            output_video = _upload_video_output_path(render_dir, source.stem, upload_metadata)
                            if output_video.exists() and not self.options.get("overwrite", False):
                                output_video = _dedupe_path(output_video)
                            thumbnail_review = {
                                **thumbnail_review,
                                "status": "deepseek_repaired",
                                "ok": bool(industry_qa.get("ok", True)),
                                "blocking": not bool(industry_qa.get("ok", True)),
                                "suggested_title": thumb_title,
                                "deepseek_repair": True,
                            }
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
            ai_costs.extend(typography_costs)
            ai_costs.extend(review_extra_costs)
            ai_cost_total = _sum_ai_costs(ai_costs)

            noise_reduce = bool(noise_decision.get("applied"))
            prepend_cover = bool(self.options.get("prepend_thumbnail_cover", True))
            render_method = "encode"
            render_fallback_used = False
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
                    filter_parts.append(f"[acat]{noise_decision.get('filter')}{audio_tail}[amain]")
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
                    render_fallback_used = True
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
            expected_render_duration = sum(max(0.0, e - s) for s, e in keep_segments)
            if bool(self.options.get("prepend_thumbnail_cover", True)):
                expected_render_duration += 0.28
            output_qa = _render_output_qa(
                output_video,
                expected_duration=expected_render_duration or duration,
                output_profile=source_info if render_method == "stream_copy" else output_profile,
                expect_audio=bool(source_audio_info.get("exists", True)),
            )
            if not output_qa.get("ok"):
                raise RuntimeError("Render Output QA fail: " + ", ".join(str(i) for i in output_qa.get("issues", [])))
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
            final_status = _one_shot_final_status(
                thumbnail_quality,
                thumbnail_layout_quality,
                thumbnail_review,
                industry_qa,
                technical_qa,
            )
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
                "encoder_fallback_used": render_fallback_used,
                "features": filter_features,
                "output_profile": output_profile,
                "output_qa": output_qa,
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
                "noise_mode": noise_decision.get("mode", ""),
                "noise_decision": noise_decision.get("decision", ""),
                "noise_reason": noise_decision.get("reason", ""),
                "noise_filter": noise_decision.get("filter", ""),
                "filter_used": noise_decision.get("filter", ""),
                "noise_original_metrics": noise_decision.get("original_metrics", {}),
                "noise_processed_metrics": noise_decision.get("processed_metrics", {}),
                "noise_sample_original": noise_decision.get("noise_sample_original", ""),
                "noise_sample_processed": noise_decision.get("noise_sample_processed", ""),
                "noise_qa": noise_decision,
                "apply_lut": apply_lut,
                "lut_enabled": apply_lut_requested,
                "lut_path": lut_path if apply_lut_requested else "",
                "lut_validated": bool(lut_validation.get("ok")) if apply_lut_requested else False,
                "lut_validation": lut_validation,
                "lut_failure_reason": "" if (not apply_lut_requested or lut_validation.get("ok")) else str(lut_validation.get("reason") or "lut_invalid"),
                "lut_applied_to_video": apply_lut,
                "lut_applied_to_thumbnail": thumbnail_frame_mode == "lut_processed",
                "technical_qa": technical_qa,
                "render_output_qa": output_qa,
                "media_tools": media_tools,
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
                "industry_qa": industry_qa,
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
        except BaseException as e:
            # Catch everything including KeyboardInterrupt to prevent batch crash.
            # Worker's own run() should catch Exception — this is a safety net.
            try:
                if hasattr(worker, "error"):
                    worker.error.emit(f"{type(e).__name__}: {e}")
            except Exception:
                pass
        finally:
            with self._active_lock:
                self._active_workers.discard(worker)

    def _run_analyze(self, video_path: str, index: int, total: int) -> tuple[str, str]:
        result = {"plan": "", "error": ""}
        opts = dict(self.options)
        opts["copy_source"] = False
        shared_state = self.options.setdefault("title_provider_state", {})
        item_state = {"deepseek_auth_failed": bool(shared_state.get("deepseek_auth_failed"))}
        opts["title_provider_state"] = item_state
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
        if not result["plan"] and not result["error"]:
            result["error"] = "Analyze worker completed without emitting result"
        if item_state.get("deepseek_auth_failed"):
            shared_state["deepseek_auth_failed"] = True
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
        if not result["report"] and not result["error"]:
            result["error"] = "Render worker completed without emitting result"
        return result["report"], result["error"]

    def _run_preview_gate(self, plan_path: str, index: int, total: int) -> tuple[dict, str]:
        result = {"preview": "", "error": ""}
        plan_path_obj = Path(plan_path)
        plan = json.loads(plan_path_obj.read_text(encoding="utf-8"))
        source = Path(plan.get("source_video") or plan.get("original_video") or "video.mp4")
        segments = plan.get("transcript", [])
        if not isinstance(segments, list):
            segments = []
        title = _clean_thumbnail_title(
            str(plan.get("thumbnail_title_suggestion", "") or source.stem),
            source.stem,
            segments,
        )
        worker = OneShotThumbnailPreviewWorker(plan_path, self.settings, title=title)
        worker.finished.connect(lambda preview_path: result.__setitem__("preview", preview_path))
        worker.error.connect(lambda msg: result.__setitem__("error", msg))
        self._log(f"[{index}/{total}] Preview gate: {title}")
        self._run_child_worker(worker)
        if not result["preview"] and not result["error"]:
            result["error"] = "Preview worker completed without emitting result"
        if result["error"]:
            return {}, result["error"]
        try:
            updated = json.loads(plan_path_obj.read_text(encoding="utf-8"))
        except Exception as exc:
            return {}, f"{type(exc).__name__}: {exc}"
        title_quality = updated.get("thumbnail_title_quality", {}) if isinstance(updated.get("thumbnail_title_quality"), dict) else {}
        layout_quality = updated.get("thumbnail_layout_quality", {}) if isinstance(updated.get("thumbnail_layout_quality"), dict) else {}
        final_status = str(updated.get("final_status") or _one_shot_final_status(title_quality, layout_quality))
        reasons = []
        if isinstance(title_quality, dict):
            reasons.extend(str(r) for r in (title_quality.get("reasons") or [])[:2])
            reasons.extend(str(r) for r in (title_quality.get("risk_flags") or [])[:2])
        if isinstance(layout_quality, dict):
            reasons.extend(str(r) for r in (layout_quality.get("issues") or [])[:2])
        if not reasons:
            reasons = ["đúng title/thumbnail"]
        gate = {
            "preview": result["preview"],
            "title": str(updated.get("thumbnail_title_suggestion") or title),
            "thumbnail_render_title": _thumbnail_render_title(str(updated.get("thumbnail_title_suggestion") or title), source.stem, segments)[0],
            "title_gate": title_quality,
            "layout_gate": layout_quality,
            "final_status": final_status,
            "final_status_label": _one_shot_status_label(final_status),
            "reasons": reasons[:4],
        }
        if (
            final_status not in {"ready", "auto_repaired"}
            and bool(self.options.get("batch_deepseek_repair_title", True))
            and segments
        ):
            repair_title, repair_metadata, repair_costs = _deepseek_repair_thumbnail_title(
                self.settings,
                segments,
                source.stem,
                str(gate["title"]),
                reasons,
                self._log,
            )
            if repair_title:
                updated["thumbnail_title_suggestion"] = repair_title
                updated["thumbnail_title_source"] = "deepseek_repair"
                updated["thumbnail_title_quality"] = _thumbnail_title_quality(repair_title, source.stem, segments)
                updated["title_quality"] = updated["thumbnail_title_quality"]
                updated["title_candidates"] = [repair_title] + [
                    str(t) for t in (updated.get("title_candidates") or []) if str(t).strip() and str(t).strip() != repair_title
                ][:4]
                updated["ai_metadata_suggestion"] = repair_metadata
                updated["metadata_plan"] = _one_shot_metadata_plan(repair_title, source.stem, segments, self.settings, repair_metadata)
                existing_costs = updated.get("ai_costs", []) if isinstance(updated.get("ai_costs"), list) else []
                updated["ai_costs"] = existing_costs + repair_costs
                updated["ai_cost_total"] = _sum_ai_costs(updated["ai_costs"])
                plan_path_obj.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

                result = {"preview": "", "error": ""}
                worker = OneShotThumbnailPreviewWorker(plan_path, self.settings, title=repair_title)
                worker.finished.connect(lambda preview_path: result.__setitem__("preview", preview_path))
                worker.error.connect(lambda msg: result.__setitem__("error", msg))
                self._log(f"[{index}/{total}] DeepSeek repair → vẽ lại preview: {repair_title}")
                self._run_child_worker(worker)
                if not result["preview"] and not result["error"]:
                    result["error"] = "Repair preview worker completed without emitting result"
                if result["error"]:
                    return {}, result["error"]
                updated = json.loads(plan_path_obj.read_text(encoding="utf-8"))
                title_quality = updated.get("thumbnail_title_quality", {}) if isinstance(updated.get("thumbnail_title_quality"), dict) else {}
                layout_quality = updated.get("thumbnail_layout_quality", {}) if isinstance(updated.get("thumbnail_layout_quality"), dict) else {}
                final_status = str(updated.get("final_status") or _one_shot_final_status(title_quality, layout_quality))
                reasons = []
                if isinstance(title_quality, dict):
                    reasons.extend(str(r) for r in (title_quality.get("reasons") or [])[:2])
                    reasons.extend(str(r) for r in (title_quality.get("risk_flags") or [])[:2])
                if isinstance(layout_quality, dict):
                    reasons.extend(str(r) for r in (layout_quality.get("issues") or [])[:2])
                if not reasons:
                    reasons = ["DeepSeek repair qua gate"]
                gate = {
                    "preview": result["preview"],
                    "title": str(updated.get("thumbnail_title_suggestion") or repair_title),
                    "thumbnail_render_title": _thumbnail_render_title(str(updated.get("thumbnail_title_suggestion") or repair_title), source.stem, segments)[0],
                    "title_gate": title_quality,
                    "layout_gate": layout_quality,
                    "final_status": final_status,
                    "final_status_label": _one_shot_status_label(final_status),
                    "reasons": reasons[:4],
                }
        out_dir = Path(updated.get("output_dir") or plan.get("output_dir") or plan_path_obj.parent)
        industry = str(self.settings.get("one_shot_industry") or self.settings.get("industry") or updated.get("industry") or "tech")
        artifacts = build_enterprise_artifacts(
            plan=updated,
            gate=gate,
            out_dir=out_dir,
            source_stem=source.stem,
            segments=segments,
            industry=industry,
        )
        certified_script = {}
        try:
            certified_script = json.loads(Path(artifacts.get("certified_script", "")).read_text(encoding="utf-8"))
        except Exception:
            certified_script = {}
        render_gate = evaluate_render_gate(
            title_gate=gate.get("title_gate", {}),
            layout_gate=gate.get("layout_gate", {}),
            final_status=str(gate.get("final_status") or ""),
            certified_script=certified_script,
        )
        gate["renderable"] = render_gate.renderable
        gate["render_gate"] = {
            "renderable": render_gate.renderable,
            "status": render_gate.status,
            "blocking_department": render_gate.blocking_department,
            "blocking_reasons": render_gate.blocking_reasons,
        }
        gate["artifacts"] = artifacts
        render_gate_report = out_dir / "render-gate-report.json"
        render_gate_report.write_text(json.dumps(gate["render_gate"], ensure_ascii=False, indent=2), encoding="utf-8")
        gate["render_gate_report"] = str(render_gate_report)
        if not render_gate.renderable:
            blocked_report = write_blocked_before_render_report(
                out_dir=out_dir,
                source_name=source.name,
                gate=gate,
                render_gate=render_gate,
                artifacts=artifacts,
            )
            gate["blocked_report"] = blocked_report
            gate["final_status"] = render_gate.status
            gate["final_status_label"] = _one_shot_status_label(render_gate.status)
            updated["blocked_before_render_report"] = blocked_report
        updated["enterprise_artifacts"] = artifacts
        updated["render_gate_decision"] = gate["render_gate"]
        updated["pipeline_version"] = ONE_SHOT_PIPELINE_VERSION
        plan_path_obj.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"[{index}/{total}] Gate: {gate['final_status_label']} · {gate['title']} · {', '.join(gate['reasons'][:2])}")
        return gate, ""

    def _copy_batch_approved_exports(self, export_dir: Path, items: list[dict]) -> Path:
        ok_items = [item for item in items if item.get("ok") and item.get("export_video")]
        clean_dir = export_dir / f"Exports-approved-{len(ok_items)}"
        clean_dir.mkdir(parents=True, exist_ok=True)
        for item in ok_items:
            for src_key, dst_key in (("export_video", "export_video"), ("export_thumbnail", "export_thumbnail")):
                raw_src = str(item.get(src_key) or "").strip()
                if not raw_src:
                    continue
                src = Path(raw_src)
                if not src.exists() or not src.is_file():
                    continue
                dst = _dedupe_path(clean_dir / src.name)
                if src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
                item[dst_key] = str(dst)
                if src_key == "export_video":
                    item["final_video_name"] = dst.name
                elif src_key == "export_thumbnail":
                    item["final_thumbnail"] = str(dst)
        return clean_dir

    def _write_batch_diagnostics(self, out_root: Path, payload: dict) -> str:
        try:
            diag_dir = out_root / "one-shot" / "_diagnostics"
            diag_dir.mkdir(parents=True, exist_ok=True)
            path = diag_dir / f"batch-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            latest = diag_dir / "batch-diagnostics.json"
            data = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "pipeline_version": ONE_SHOT_PIPELINE_VERSION,
                "media_tools": _media_tools_report(self.settings),
                **payload,
            }
            text = json.dumps(data, ensure_ascii=False, indent=2)
            path.write_text(text, encoding="utf-8")
            latest.write_text(text, encoding="utf-8")
            return str(path)
        except Exception:
            return ""

    def run(self):
        out_root = Path(self.settings.get("output_dir") or DEFAULT_OUT)
        paths: list[str] = []
        disk_estimate: dict = {}
        free_bytes = 0
        media_tools: dict = {}
        items: list[dict] = []
        try:
            for raw in self.video_paths:
                p = Path(raw).expanduser()
                if p.exists() and p.is_file():
                    paths.append(str(p))
            total = len(paths)
            if total <= 0:
                raise ValueError("Chưa có video hợp lệ để chạy batch.")
            media_tools = _media_tools_report(self.settings)
            if not media_tools.get("ffmpeg_ok") or not media_tools.get("ffprobe_ok"):
                self._write_batch_diagnostics(out_root, {
                    "status": "failed_preflight",
                    "error": "missing_media_tools",
                    "paths": paths,
                    "output_dir": str(out_root),
                    "media_tools": media_tools,
                })
                raise RuntimeError(
                    "Thiếu ffmpeg/ffprobe. "
                    f"ffmpeg={media_tools.get('ffmpeg') or 'missing'}, "
                    f"ffprobe={media_tools.get('ffprobe') or 'missing'}."
                )
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
                usage_hints = _top_disk_usage_hints(out_root / "one-shot")
                self._write_batch_diagnostics(out_root, {
                    "status": "failed_preflight",
                    "error": "low_disk",
                    "paths": paths,
                    "output_dir": str(out_root),
                    "disk_preflight": {"free_bytes": free_bytes, **disk_estimate},
                    "disk_usage_hints": usage_hints,
                    "media_tools": media_tools,
                })
                hint_text = "; ".join(f"{Path(str(i.get('path'))).name}: {i.get('size')}" for i in usage_hints[:3])
                raise RuntimeError(
                    "Không đủ dung lượng trống để chạy batch: "
                    f"còn {_format_gb(free_bytes)}, ước cần {_format_gb(disk_estimate['required_bytes'])}. "
                    f"Hãy xoá bớt output/debug trước khi render.{(' Gợi ý: ' + hint_text) if hint_text else ''}"
                )
            whisper_status = whisper_runtime_status({**self.settings, "one_shot_whisper_model": self.options.get("whisper_model", "small")})
            self._log(
                "Preflight: ffmpeg OK · ffprobe OK · output OK · "
                f"disk {_format_gb(free_bytes)} trống / cần ~{_format_gb(disk_estimate['required_bytes'])} · "
                f"Whisper local: {whisper_status.get('label', 'Không rõ')}"
            )
            self._log(f"Media tools: ffmpeg={media_tools.get('ffmpeg')} · ffprobe={media_tools.get('ffprobe')}")
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
            items = []
            all_costs: list[dict] = []
            today = datetime.now().strftime("%Y-%m-%d")
            fallback_export_dir = out_root / "one-shot" / today
            export_dir = fallback_export_dir
            render_gate = threading.Lock()

            enterprise_pipeline = bool(self.options.get("enterprise_pipeline", True))
            if enterprise_pipeline or bool(self.options.get("batch_review_before_render", False)):
                self._log("Workflow: đọc toàn bộ video → tạo title/thumbnail preview → gate OK mới render")
                batch_started_at = time.perf_counter()
                render_candidates: list[dict] = []
                for index, video_path in enumerate(paths, 1):
                    if self._cancelled or self.isInterruptionRequested():
                        break
                    name = Path(video_path).name
                    item = {
                        "source": video_path,
                        "source_name": name,
                        "ok": False,
                        "plan": "",
                        "report": "",
                        "error": "",
                    }
                    try:
                        self._log(f"[{index}/{total}] Phase 1/2 đọc video: {name}")
                        plan_path, analyze_error = self._run_analyze(video_path, index, total)
                        if analyze_error:
                            raise RuntimeError(analyze_error)
                        item["plan"] = plan_path
                        gate, gate_error = self._run_preview_gate(plan_path, index, total)
                        if gate_error:
                            raise RuntimeError(gate_error)
                        item.update({
                            "preview_thumbnail": gate.get("preview", ""),
                            "thumbnail_title": gate.get("title", ""),
                            "thumbnail_render_title": gate.get("thumbnail_render_title", ""),
                            "thumbnail_quality": gate.get("title_gate", {}),
                            "thumbnail_layout_quality": gate.get("layout_gate", {}),
                            "title_gate": gate.get("title_gate", {}),
                            "layout_gate": gate.get("layout_gate", {}),
                            "final_status": gate.get("final_status", "needs_review"),
                            "thumbnail_quality_label": ", ".join(gate.get("reasons", [])[:2]),
                        })
                        gate_renderable = bool(gate.get("renderable", gate.get("final_status") in {"ready", "auto_repaired"}))
                        if gate_renderable and gate.get("final_status") in {"ready", "auto_repaired"}:
                            render_candidates.append(item)
                        else:
                            item["needs_review"] = True
                            item["blocked_before_render"] = True
                            item["blocked_report"] = gate.get("blocked_report", "")
                            item["render_gate"] = gate.get("render_gate", {})
                            item["enterprise_artifacts"] = gate.get("artifacts", {})
                            blocking = (gate.get("render_gate") or {}).get("blocking_reasons") or gate.get("reasons", [])
                            item["review_reason"] = "Chặn trước render: " + ", ".join(str(r) for r in blocking[:3])
                            self._log(f"[{index}/{total}] Chặn render: {item['review_reason']}")
                            items.append(item)
                            self.item_done.emit(item)
                    except Exception as e:
                        item["error"] = f"{type(e).__name__}: {e}"
                        self._log(f"[{index}/{total}] Lỗi phase đọc/preview: {item['error']}")
                        items.append(item)
                        self.item_done.emit(item)
                    self.progress.emit(int((index / max(total, 1)) * 48))

                for render_pos, item in enumerate(render_candidates, 1):
                    if self._cancelled or self.isInterruptionRequested():
                        item["cancelled"] = True
                        item["error"] = "Batch đã dừng trước render."
                        items.append(item)
                        self.item_done.emit(item)
                        continue
                    index = paths.index(item["source"]) + 1
                    try:
                        self._log(f"[{index}/{total}] Phase 2/2 render: {item.get('thumbnail_title') or item.get('source_name')}")
                        with render_gate:
                            report_path, render_error = self._run_render(str(item["plan"]), index, total)
                        if render_error:
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
                            "thumbnail_title": report.get("thumbnail_title", item.get("thumbnail_title", "")),
                            "thumbnail_render_title": report.get("thumbnail_render_title", item.get("thumbnail_render_title", "")),
                            "thumbnail_layout_quality": report.get("thumbnail_layout_quality", item.get("thumbnail_layout_quality", {})),
                            "upload_metadata": report.get("upload_metadata", {}),
                            "upload_title": report.get("upload_title", ""),
                            "platform_caption": report.get("platform_caption", ""),
                            "thumbnail_quality": report.get("thumbnail_title_quality", item.get("thumbnail_quality", {})),
                            "title_gate": report.get("title_gate", report.get("thumbnail_title_quality", item.get("title_gate", {}))),
                            "layout_gate": report.get("layout_gate", report.get("thumbnail_layout_quality", item.get("layout_gate", {}))),
                            "metadata_gate": report.get("metadata_gate", {}),
                            "review_gate": report.get("review_gate", report.get("thumbnail_review", {})),
                            "final_status": report.get("final_status", "ready"),
                            "final_video_name": report.get("final_video_name", Path(str(report.get("export_video", ""))).name),
                            "final_hashtags": report.get("final_hashtags", []),
                            "preview_thumbnail": report.get("preview_thumbnail", item.get("preview_thumbnail", "")),
                            "final_thumbnail": report.get("final_thumbnail", report.get("thumbnail", "")),
                            "thumbnail_quality_label": ", ".join(
                                str(r) for r in (report.get("thumbnail_title_quality", {}) or {}).get("reasons", [])[:2]
                            ) if isinstance(report.get("thumbnail_title_quality", {}), dict) else item.get("thumbnail_quality_label", ""),
                            "transcript_mode": report.get("transcript_mode", ""),
                            "transcript_detail": report.get("transcript_detail", ""),
                            "ai_cost_total": item_ai_cost,
                            "render_seconds": round(render_seconds, 3),
                            "render_total_seconds": round(render_total_seconds, 3),
                            "render_realtime_factor": round(render_realtime_factor, 3),
                            "render_profile": render_profile,
                        })
                        if str(item.get("final_status") or "") in {"ready", "auto_repaired"}:
                            item["ok"] = True
                            item["needs_review"] = False
                            item.pop("review_reason", None)
                        else:
                            item["ok"] = False
                            item["needs_review"] = True
                            item["review_reason"] = f"Render QA chưa đạt: final_status={item.get('final_status')}"
                        if item.get("export_dir"):
                            export_dir = Path(str(item["export_dir"]))
                        try:
                            if isinstance(report.get("ai_costs"), list):
                                all_costs.extend(report.get("ai_costs", []))
                        except Exception:
                            pass
                        self._log(f"[{index}/{total}] Xong render: {Path(str(item.get('export_video') or '')).name}")
                    except Exception as e:
                        item["ok"] = False
                        item["error"] = f"{type(e).__name__}: {e}"
                        self._log(f"[{index}/{total}] Lỗi render: {item['error']}")
                    items.append(item)
                    self.item_done.emit(item)
                    self.progress.emit(48 + int((render_pos / max(len(render_candidates), 1)) * 50))

                items.sort(key=lambda item: paths.index(item.get("source")) if item.get("source") in paths else 10**9)
                export_dir.mkdir(parents=True, exist_ok=True)
                clean_export_dir = self._copy_batch_approved_exports(export_dir, items) if bool(self.options.get("batch_clean_export", True)) else export_dir
                ok_count = sum(1 for item in items if item.get("ok"))
                ready_count = sum(1 for item in items if item.get("ok") and item.get("final_status") == "ready")
                auto_repaired_count = sum(1 for item in items if item.get("ok") and item.get("final_status") == "auto_repaired")
                blocked_before_render_count = sum(1 for item in items if item.get("blocked_before_render") or item.get("final_status") == "blocked_before_render")
                needs_review_count = sum(
                    1 for item in items
                    if (item.get("ok") or item.get("blocked_before_render")) and str(item.get("final_status") or "needs_human_review") not in {"ready", "auto_repaired"}
                )
                failed_technical_count = sum(1 for item in items if str(item.get("final_status") or "") == "failed_technical")
                cancelled_items = sum(1 for item in items if item.get("cancelled"))
                failed_count = sum(1 for item in items if not item.get("ok") and not item.get("cancelled") and not item.get("needs_review") and not item.get("blocked_before_render"))
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
                ai_cost_per_video = {
                    "estimated_usd": round(float(ai_cost_total.get("estimated_usd") or 0.0) / max(total, 1), 6),
                    "estimated_vnd": int(round(float(ai_cost_total.get("estimated_vnd") or 0) / max(total, 1))),
                }
                summary = {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "workflow": "review_before_render",
                    "total": total,
                    "total_selected": total,
                    "processed": len(items),
                    "ok": ok_count,
                    "ready": ready_count,
                    "auto_repaired": auto_repaired_count,
                    "blocked_before_render": blocked_before_render_count,
                    "needs_review": needs_review_count,
                    "failed_technical": failed_technical_count,
                    "failed": failed_count,
                    "skipped": skipped_count,
                    "cancelled": bool(self._cancelled or self.isInterruptionRequested() or cancelled_items),
                    "export_dir": str(clean_export_dir),
                    "raw_export_dir": str(export_dir),
                    "batch_total_seconds": batch_total_seconds,
                    "render_total_seconds": render_total_seconds,
                    "render_job_total_seconds": render_job_total_seconds,
                    "render_avg_realtime_factor": avg_realtime_factor,
                    "disk_preflight": {
                        "free_bytes": free_bytes,
                        **disk_estimate,
                    },
                    "media_tools": media_tools,
                    "whisper_status": whisper_status,
                    "ai_cost_total": ai_cost_total,
                    "ai_cost_per_video": ai_cost_per_video,
                    "ai_cost_by_kind": _sum_ai_costs_by_kind(all_costs),
                    "ready_to_upload": [item for item in items if item.get("ok") and item.get("final_status") == "ready"],
                    "auto_repaired_ready": [item for item in items if item.get("ok") and item.get("final_status") == "auto_repaired"],
                    "blocked_items": [item for item in items if item.get("blocked_before_render") or item.get("final_status") == "blocked_before_render"],
                    "items": items,
                }
                summary_path = clean_export_dir / f"batch-summary-{datetime.now().strftime('%H%M%S')}.json"
                summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                self._write_batch_diagnostics(out_root, {"status": "finished", "summary_path": str(summary_path), **summary})
                self.progress.emit(100)
                self._log(f"Batch xong: OK {ok_count}/{total} · AI sửa {auto_repaired_count} · chặn {blocked_before_render_count} · lỗi {failed_count}")
                self._log(f"Thư mục upload sạch: {clean_export_dir}")
                self.finished.emit(str(summary_path))
                return

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
                    if str(item.get("final_status") or "") in {"ready", "auto_repaired"}:
                        item["ok"] = True
                        item["needs_review"] = False
                        item.pop("review_reason", None)
                    else:
                        item["ok"] = False
                        item["needs_review"] = True
                        item["review_reason"] = f"Render QA chưa đạt: final_status={item.get('final_status')}"
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
            auto_repaired_count = sum(1 for item in items if item.get("ok") and item.get("final_status") == "auto_repaired")
            needs_review_count = sum(
                1 for item in items
                if item.get("ok") and str(item.get("final_status") or "needs_human_review") not in {"ready", "auto_repaired"}
            )
            failed_technical_count = sum(1 for item in items if str(item.get("final_status") or "") == "failed_technical")
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
            ai_cost_per_video = {
                "estimated_usd": round(float(ai_cost_total.get("estimated_usd") or 0.0) / max(total, 1), 6),
                "estimated_vnd": int(round(float(ai_cost_total.get("estimated_vnd") or 0) / max(total, 1))),
            }
            summary = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "total": total,
                "total_selected": total,
                "processed": len(items),
                "ok": ok_count,
                "ready": ready_count,
                "auto_repaired": auto_repaired_count,
                "needs_review": needs_review_count,
                "failed_technical": failed_technical_count,
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
                "media_tools": media_tools,
                "whisper_status": whisper_status,
                "ai_cost_total": ai_cost_total,
                "ai_cost_per_video": ai_cost_per_video,
                "ai_cost_by_kind": _sum_ai_costs_by_kind(all_costs),
                "items": items,
            }
            summary_path = export_dir / f"batch-summary-{datetime.now().strftime('%H%M%S')}.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            self._write_batch_diagnostics(out_root, {"status": "finished", "summary_path": str(summary_path), **summary})
            self.progress.emit(100)
            self._log(f"Batch xong: {ok_count}/{len(items)} video")
            self.finished.emit(str(summary_path))
        except Exception as e:
            self._write_batch_diagnostics(out_root, {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
                "paths": paths,
                "items": items,
                "output_dir": str(out_root),
                "disk_preflight": {"free_bytes": free_bytes, **disk_estimate} if disk_estimate else {},
                "media_tools": media_tools or _media_tools_report(self.settings),
            })
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
