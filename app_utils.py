import sys
import os
import json
import subprocess
import traceback
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from PyQt6.QtWidgets import QApplication, QMessageBox

from app_constants import DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY
from version import LICENSE_VERIFY_URL, VERSION

# ── Telegram feedback config ──────────────────────────────────────────
# Ưu tiên: telegram_config.py > biến môi trường > mặc định rỗng
# Tạo file telegram_config.py (đã trong .gitignore) với nội dung:
#   TELEGRAM_BOT_TOKEN = "your_bot_token"
#   TELEGRAM_CHAT_ID   = "your_chat_id"
# Hoặc set biến môi trường: ELEVENLABS_TELEGRAM_BOT_TOKEN, ELEVENLABS_TELEGRAM_CHAT_ID
try:
    from telegram_config import TELEGRAM_BOT_TOKEN as _TG_BOT, TELEGRAM_CHAT_ID as _TG_CHAT
    TELEGRAM_BOT_TOKEN = _TG_BOT
    TELEGRAM_CHAT_ID = _TG_CHAT
except (ImportError, ModuleNotFoundError):
    TELEGRAM_BOT_TOKEN = os.environ.get("ELEVENLABS_TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("ELEVENLABS_TELEGRAM_CHAT_ID", "")


# ── Data directory (persists across updates) ───────────────────────
def get_data_dir() -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "TTSApp"
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "TTSApp"
    else:
        d = Path.home() / ".tts_app"
    d.mkdir(parents=True, exist_ok=True)
    return d

DATA_DIR      = get_data_dir()
SETTINGS_FILE = str(DATA_DIR / "settings.json")
DEFAULT_OUT   = str(DATA_DIR / "output")
ERROR_LOG     = DATA_DIR / "error.log"
LICENSE_CACHE_FILE = DATA_DIR / "license.json"
DEVICE_ID_FILE = DATA_DIR / "device_id"
LICENSE_GRACE_DAYS = 7


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_auto_video_engine_dir(settings: dict | None = None) -> Path:
    """Resolve Auto-Create-Video engine path without hardcoding a macOS user path."""
    env_value = (
        os.environ.get("HEDRA_AUTO_VIDEO_ENGINE_DIR")
        or os.environ.get("AUTO_VIDEO_ENGINE_DIR")
        or ""
    ).strip()
    if env_value:
        return Path(os.path.expanduser(env_value)).resolve()

    if settings and str(settings.get("auto_video_engine_dir", "")).strip():
        return Path(os.path.expanduser(str(settings["auto_video_engine_dir"]))).resolve()

    root = _runtime_root()
    candidates = [
        root / "Auto-Create-Video",
        root.parent / "Auto-Create-Video",
        Path.home() / "Auto-Create-Video",
    ]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return candidates[-1].resolve()


def get_auto_video_env_local(settings: dict | None = None) -> Path:
    return get_auto_video_engine_dir(settings) / ".env.local"


def get_auto_video_assets_dir(settings: dict | None = None) -> Path:
    return get_auto_video_engine_dir(settings) / "assets"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_license_time(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if re.fullmatch(r"\d{8}", raw):
            return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def get_device_id() -> str:
    try:
        if DEVICE_ID_FILE.exists():
            value = DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = str(uuid.uuid4())
        DEVICE_ID_FILE.write_text(value, encoding="utf-8")
        return value
    except Exception:
        return "unknown-device"


def _normalize_features(features) -> set[str]:
    if isinstance(features, str):
        features = [features]
    if not isinstance(features, list):
        return set()
    return {str(item).strip().lower() for item in features if str(item).strip()}


def _license_cache_from_settings(settings: dict | None) -> dict:
    if not isinstance(settings, dict):
        return {}
    cache = settings.get("pro_license_cache")
    if isinstance(cache, dict):
        return cache
    return {
        "valid": bool(settings.get("pro_license_valid", False)),
        "features": settings.get("pro_license_features", []),
        "expires_at": settings.get("pro_license_expires_at", ""),
        "checked_at": settings.get("pro_license_checked_at", ""),
        "message": settings.get("pro_license_message", ""),
    }


def _cache_allows_feature(cache: dict, feature: str) -> bool:
    if not cache or not cache.get("valid"):
        return False
    features = _normalize_features(cache.get("features", []))
    requested = (feature or "").strip().lower()
    if "all" not in features and requested not in features:
        return False
    expires = _parse_license_time(cache.get("expires_at"))
    if expires and _now_utc() > expires:
        return False
    checked_at = _parse_license_time(cache.get("checked_at"))
    if checked_at and _now_utc() - checked_at > timedelta(days=LICENSE_GRACE_DAYS):
        return False
    return True


def is_feature_unlocked(settings: dict | None, feature: str) -> bool:
    feature_key = re.sub(r"[^A-Z0-9]+", "_", (feature or "").upper()).strip("_")
    env_names = ["HEDRA_PRO_UNLOCK", f"HEDRA_{feature_key}_UNLOCK"]
    if any(os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"} for name in env_names):
        return True
    return _cache_allows_feature(_license_cache_from_settings(settings), feature)


def is_chat_script_unlocked(settings: dict | None = None) -> bool:
    return is_feature_unlocked(settings, "chat_script")


def is_auto_video_unlocked(settings: dict | None = None) -> bool:
    return is_feature_unlocked(settings, "auto_video")


def validate_pro_license_key(
    key: str,
    feature: str = "",
    timeout: int = 12,
) -> tuple[bool, str, dict]:
    normalized = re.sub(r"\s+", "", key or "")
    if not normalized:
        return False, "Chưa nhập license key.", {}
    endpoint = os.environ.get("HEDRA_LICENSE_VERIFY_URL", LICENSE_VERIFY_URL).strip()
    if not endpoint:
        return False, "Chưa cấu hình license server.", {}
    try:
        res = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json={
                "key": normalized,
                "feature": feature,
                "app": "hedra-studio",
                "version": VERSION,
                "device_id": get_device_id(),
                "platform": sys.platform,
            },
            timeout=timeout,
        )
        if res.status_code != 200:
            return False, f"License server trả về HTTP {res.status_code}.", {}
        data = res.json()
    except requests.RequestException as e:
        return False, f"Không kết nối được license server: {e}", {}
    except Exception as e:
        return False, f"Không đọc được phản hồi license server: {e}", {}

    valid = bool(data.get("valid", data.get("success", False)))
    features = data.get("features", data.get("allowed_features", []))
    cache = {
        "valid": valid,
        "features": list(_normalize_features(features)),
        "expires_at": data.get("expires_at", data.get("expiry", "")),
        "checked_at": _now_utc().isoformat(),
        "customer": data.get("customer", data.get("customer_id", "")),
        "message": data.get("message", ""),
    }
    if valid and feature and not _cache_allows_feature(cache, feature):
        return False, f"Key hợp lệ nhưng chưa mở tính năng {feature}.", cache
    message = cache["message"] or ("License hợp lệ." if valid else "License không hợp lệ.")
    return valid, message, cache


def validate_auto_video_license_key(key: str) -> tuple[bool, str]:
    ok, msg, _ = validate_pro_license_key(key, "auto_video")
    return ok, msg


def _show_unhandled_error(title: str, message: str):
    print(message, file=sys.stderr)
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(message + "\n\n")
    except Exception:
        pass

    app = QApplication.instance()
    if app is None:
        return
    try:
        QMessageBox.critical(None, title, f"{message}\n\nLog: {ERROR_LOG}")
    except Exception:
        pass


def _install_exception_hook():
    def _hook(exc_type, exc_value, exc_tb):
        message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _show_unhandled_error("Lỗi Hedra Studio", message)

    sys.excepthook = _hook


# ── Settings helpers ───────────────────────────────────────────────
def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                s = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            # File corrupt — backup và trả về defaults
            backup = SETTINGS_FILE + ".corrupt.bak"
            try:
                os.rename(SETTINGS_FILE, backup)
            except Exception:
                pass
            print(f"[WARN] settings.json corrupt ({e}), reset to defaults")
            s = {}
        # Migration: el_api_key → el_api_keys
        if "el_api_key" in s and "el_api_keys" not in s:
            s["el_api_keys"] = [s.pop("el_api_key")] if s["el_api_key"] else []
        # Backfill tất cả key có thể thiếu từ phiên bản cũ
        _DEFAULTS = {
            "el_api_keys":              [],
            "genmax_api_key":           "",
            "ds_api_key":               "",
            "gemini_api_key":           "",
            "gemini_chat_prompt":       "",
            "chat_pronoun_mode":        "auto",
            "telegram_bot_token":       "",
            "telegram_chat_id":         "",
            "output_dir":               DEFAULT_OUT,
            "enhance_prompt":           DEFAULT_PROMPT,
            "default_speed":            1.0,
            "selected_voice_id":        "",
            "selected_voice_name":      "Adam",
            "shared_voice_enabled":     False,
            "av_voice_presets":         {},
            "custom_styles":            [],
            "prompt_preset_overrides":  {},
            "enhance_style_name":       "Nghiêm túc",
            "enhance_style_temperature": 0.3,
            "enhance_style_creative":   False,
            "language_code":            "vi",
            "tts_language_code":        "vi",
            "favorite_voice_ids":       [],
            "favorite_voices":          [],   # [{id, name, lang}] — dùng chung cho tất cả tools
            "tts_voice_id":             "",   # voice riêng cho TTS tab
            "tts_voice_name":           "",
            "av_voice_id":              "",   # voice riêng cho Auto Video tab
            "av_voice_name":            "",
            "av_language_code":         "vi",
            "app_theme":                "system",
            "auto_video_engine_dir":     "",
            "auto_video_license_key":     "",
            "pro_license_key":            "",
            "pro_license_cache":          {},
        }
        for key, default in _DEFAULTS.items():
            if key not in s:
                s[key] = default
        return s
    return {
        "el_api_keys":              [],
        "genmax_api_key":           "",
        "ds_api_key":               "",
        "gemini_api_key":           "",
        "gemini_chat_prompt":       "",
        "chat_pronoun_mode":        "auto",
        "telegram_bot_token":       "",
        "telegram_chat_id":         "",
        "output_dir":               DEFAULT_OUT,
        "enhance_prompt":           DEFAULT_PROMPT,
        "default_speed":            1.0,
        "selected_voice_id":        "",
        "selected_voice_name":      "Adam",
        "shared_voice_enabled":     False,
        "av_voice_presets":         {},
        "custom_styles":            [],
        "prompt_preset_overrides":  {},
        "enhance_style_name":       "Nghiêm túc",
        "enhance_style_temperature": 0.3,
        "enhance_style_creative":   False,
        "language_code":            "vi",
        "tts_language_code":        "vi",
        "favorite_voice_ids":       [],
        "favorite_voices":          [],
        "tts_voice_id":             "",
        "tts_voice_name":           "",
        "av_voice_id":              "",
        "av_voice_name":            "",
        "av_language_code":         "vi",
        "app_theme":                "system",
        "auto_video_engine_dir":     "",
        "auto_video_license_key":     "",
        "pro_license_key":            "",
        "pro_license_cache":          {},
    }

def save_settings(s: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# ── Reveal file cross-platform ─────────────────────────────────────
def reveal_file(path: str):
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    elif sys.platform == "win32":
        subprocess.Popen(f'explorer /select,"{path}"', shell=True)
