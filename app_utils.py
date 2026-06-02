import sys
import os
import json
import subprocess
import traceback
import re
import uuid
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import importlib

import requests

from PyQt6.QtWidgets import QApplication, QMessageBox

from app_constants import DEFAULT_PROMPT_FUNNY, VOICE_ID
from version import LICENSE_VERIFY_URL, VERSION

# ── Telegram feedback config ──────────────────────────────────────────
# Packaged releases must never bundle local developer credentials.
# Frozen apps read an external per-machine support config, so feedback works
# without exposing the bot token in Settings, the app bundle, or release DMGs.
def _read_external_support_config() -> tuple[str, str]:
    paths: list[Path] = []
    if sys.platform == "darwin":
        paths.append(Path.home() / "Library" / "Application Support" / "Hedra Studio" / "support_config.json")
    elif sys.platform == "win32":
        paths.append(Path(os.environ.get("APPDATA", str(Path.home()))) / "Hedra Studio" / "support_config.json")
    else:
        paths.append(Path.home() / ".hedra_studio" / "support_config.json")

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        token = str(data.get("telegram_bot_token") or data.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat = str(data.get("telegram_chat_id") or data.get("TELEGRAM_CHAT_ID") or "").strip()
        if token and chat:
            return token, chat
    return "", ""


def _load_telegram_config() -> tuple[str, str]:
    env_token = os.environ.get("ELEVENLABS_TELEGRAM_BOT_TOKEN", "").strip()
    env_chat = os.environ.get("ELEVENLABS_TELEGRAM_CHAT_ID", "").strip()
    if env_token and env_chat:
        return env_token, env_chat

    ext_token, ext_chat = _read_external_support_config()
    if ext_token and ext_chat:
        return ext_token, ext_chat

    if getattr(sys, "frozen", False):
        return env_token, env_chat

    # Source/dev runs can still use ignored telegram_config.py for local tests.
    try:
        cfg = importlib.import_module("telegram_config")
        return (
            str(getattr(cfg, "TELEGRAM_BOT_TOKEN", env_token) or "").strip(),
            str(getattr(cfg, "TELEGRAM_CHAT_ID", env_chat) or "").strip(),
        )
    except Exception:
        return env_token, env_chat


TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID = _load_telegram_config()


APP_DATA_NAME = "Hedra Studio"
LEGACY_APP_DATA_NAME = "TTSApp"
DEFAULT_ADAM_VOICE = {
    "id": VOICE_ID,
    "name": "Adam - Dominant, Firm",
    "lang": "vi",
    "langs": [],
    "multilingual": True,
}


# ── Data directory (persists across updates) ───────────────────────
def _platform_data_dir(app_name: str, create: bool = True) -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / app_name
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / app_name
    else:
        d = Path.home() / f".{app_name.lower().replace(' ', '_')}"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def get_data_dir() -> Path:
    return _platform_data_dir(APP_DATA_NAME, create=True)


def get_legacy_data_dir() -> Path:
    return _platform_data_dir(LEGACY_APP_DATA_NAME, create=False)


DATA_DIR      = get_data_dir()
SETTINGS_FILE = str(DATA_DIR / "settings.json")
LEGACY_DEFAULT_OUT = str(DATA_DIR / "output")


def _default_output_dir() -> str:
    env_value = os.environ.get("HEDRA_STUDIO_OUTPUT_DIR", "").strip()
    if env_value:
        return str(Path(os.path.expanduser(env_value)).resolve())
    if sys.platform == "darwin":
        return str(Path.home() / "hedra-studio" / "output")
    return LEGACY_DEFAULT_OUT


DEFAULT_OUT   = _default_output_dir()
ERROR_LOG     = DATA_DIR / "error.log"
PERF_LOG      = DATA_DIR / "performance.log"
LICENSE_CACHE_FILE = DATA_DIR / "license.json"
DEVICE_ID_FILE = DATA_DIR / "device_id"
LICENSE_GRACE_DAYS = 7


def perf_log(event: str, **fields) -> None:
    """Lightweight diagnostics log for macOS lag investigations."""
    try:
        safe_event = re.sub(r"\s+", "_", str(event or "event")).strip("_") or "event"
        parts = [f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]", f"event={safe_event}", f"pid={os.getpid()}"]
        for key, value in fields.items():
            if value is None:
                continue
            text = str(value).replace("\n", " ")[:240]
            parts.append(f"{key}={text}")
        with open(PERF_LOG, "a", encoding="utf-8") as f:
            f.write(" ".join(parts) + "\n")
    except Exception:
        pass


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
        return False, "Chưa nhập Pro key.", {}
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
        return False, f"Không kiểm tra được key: {e}", {}
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
def _default_settings() -> dict:
    return {
        "el_api_keys":              [],
        "genmax_api_key":           "",
        "ds_api_key":               "",
        "gemini_api_key":           "",
        "gemini_text_model":        "auto",
        "gemini_stt_model":         "auto",
        "gemini_chat_prompt":       "",
        "chat_pronoun_mode":        "auto",
        "telegram_bot_token":       "",
        "telegram_chat_id":         "",
        "output_dir":               DEFAULT_OUT,
        "enhance_prompt":           DEFAULT_PROMPT_FUNNY,
        "default_speed":            1.0,
        "selected_voice_id":        VOICE_ID,
        "selected_voice_name":      "Adam - Dominant, Firm",
        "shared_voice_enabled":     False,
        "av_voice_presets":         {},
        "custom_styles":            [],
        "prompt_preset_overrides":  {},
        "enhance_style_name":       "Viral",
        "enhance_style_temperature": 0.7,
        "enhance_style_creative":   True,
        "language_code":            "vi",
        "tts_language_code":        "vi",
        "eleven_v3_style_enabled":  True,
        "favorite_voice_ids":       [VOICE_ID],
        "favorite_voices":          [dict(DEFAULT_ADAM_VOICE)],
        "tts_voice_id":             VOICE_ID,
        "tts_voice_name":           "Adam - Dominant, Firm",
        "av_voice_id":              "",
        "av_voice_name":            "",
        "av_language_code":         "vi",
        "auto_video_mode":          "article",
        "one_shot_industry":        "tech",
        "one_shot_lut_path":        "",
        "one_shot_noise_reduce":    True,
        "one_shot_cut_video":       True,
        "one_shot_apply_lut":       True,
        "one_shot_render_profile":  "multi_1080",
        "one_shot_whisper_model":   "small",
        "one_shot_thumbnail_template": "boxphonefarm",
        "one_shot_thumbnail_font":  "dt_phudu_black",
        "one_shot_thumbnail_size":  "large",
        "one_shot_thumbnail_lines": "auto",
        "one_shot_thumbnail_position": "center",
        "one_shot_thumbnail_title_mode": "expert",
        "one_shot_ai_review_thumbnail": True,
        "one_shot_last_video_dir":  "",
        "one_shot_last_batch_dir":  "",
        "one_shot_last_lut_dir":    "",
        "app_theme":                "system",
        "auto_video_engine_dir":     "",
        "auto_video_license_key":     "",
        "pro_license_key":            "",
        "pro_license_cache":          {},
    }


_SAFE_LEGACY_MIGRATION_KEYS = {
    "app_theme",
    "output_dir",
    "default_speed",
    "selected_voice_id",
    "selected_voice_name",
    "shared_voice_enabled",
    "enhance_style_name",
    "enhance_style_temperature",
    "enhance_style_creative",
    "language_code",
    "tts_language_code",
    "favorite_voice_ids",
    "favorite_voices",
    "tts_voice_id",
    "tts_voice_name",
    "gemini_text_model",
    "gemini_stt_model",
}


def _read_settings_file(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _sanitize_legacy_value(key: str, value):
    if key == "favorite_voices" and isinstance(value, list):
        cleaned = []
        for item in value:
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "id": str(item.get("id", "") or ""),
                "name": str(item.get("name", "") or ""),
                "lang": str(item.get("lang", item.get("language", "")) or ""),
                "langs": item.get("langs", []) if isinstance(item.get("langs", []), list) else [],
            })
        return cleaned
    if key == "favorite_voice_ids" and isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
        return value
    return None


def _normalize_output_dir(value) -> str:
    text = str(value or DEFAULT_OUT).strip() or DEFAULT_OUT
    try:
        path = Path(os.path.expanduser(text))
        if path.name == "ouput":
            path = path.with_name("output")
        try:
            if path.resolve() == Path(LEGACY_DEFAULT_OUT).resolve():
                return DEFAULT_OUT
        except Exception:
            if str(path) == LEGACY_DEFAULT_OUT:
                return DEFAULT_OUT
        return str(path)
    except Exception:
        pass
    return text


def get_tool_output_dir(settings: dict | None, tool: str, day: datetime | None = None) -> str:
    """Return the dated output folder for a tool, e.g. output/tts/2026-06-01."""
    root = DEFAULT_OUT
    if isinstance(settings, dict):
        root = _normalize_output_dir(settings.get("output_dir"))
    safe_tool = re.sub(r"[^A-Za-z0-9_-]+", "-", str(tool or "tool").strip().lower()).strip("-") or "tool"
    stamp = (day or datetime.now()).strftime("%Y-%m-%d")
    return str(Path(root) / safe_tool / stamp)


def suggest_tts_filename(text: str, now: datetime | None = None) -> str:
    """Create a readable, collision-resistant default filename from TTS text."""
    plain = re.sub(r"\[[^\]]+\]", " ", str(text or ""))
    plain = re.sub(r"[*_`~]+", " ", plain)
    plain = plain.replace("đ", "d").replace("Đ", "D")
    plain = unicodedata.normalize("NFKD", plain).encode("ascii", "ignore").decode("ascii")
    plain = plain.lower()
    words = re.findall(r"[a-z0-9]+", plain)
    stem = "_".join(words[:6]).strip("_") or "ban_doc"
    stamp = (now or datetime.now()).strftime("%H%M%S")
    return f"{stem}_{stamp}"


def _backfill_settings(s: dict) -> dict:
    defaults = _default_settings()
    if "el_api_key" in s and "el_api_keys" not in s:
        s["el_api_keys"] = [s.pop("el_api_key")] if s["el_api_key"] else []
    for key, default in defaults.items():
        if key not in s:
            s[key] = default
    style_name = str(s.get("enhance_style_name") or "").strip()
    prompt_text = str(s.get("enhance_prompt") or "")
    legacy_builtin_prompt = (
        not style_name
        and (
            "AUDIO TAGS" in prompt_text
            or "EMOTIONAL TAGS" in prompt_text
            or "Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS" in prompt_text
        )
    )
    if style_name in {"Nghiêm túc", "Hài hước", "Vivid"} or legacy_builtin_prompt:
        s["enhance_prompt"] = DEFAULT_PROMPT_FUNNY
        s["enhance_style_name"] = "Viral"
        s["enhance_style_temperature"] = 0.7
        s["enhance_style_creative"] = True
    if not str(s.get("selected_voice_id", "")).strip():
        s["selected_voice_id"] = VOICE_ID
    if not str(s.get("selected_voice_name", "")).strip() or str(s.get("selected_voice_name", "")).strip() == "Adam":
        s["selected_voice_name"] = "Adam - Dominant, Firm"
    if not str(s.get("tts_voice_id", "")).strip():
        s["tts_voice_id"] = s["selected_voice_id"]
    if not str(s.get("tts_voice_name", "")).strip():
        s["tts_voice_name"] = s["selected_voice_name"]
    s["output_dir"] = _normalize_output_dir(s.get("output_dir"))
    favs = s.get("favorite_voices")
    if not isinstance(favs, list):
        favs = []
        s["favorite_voices"] = favs
    if not any(isinstance(v, dict) and v.get("id") == VOICE_ID for v in favs):
        favs.insert(0, dict(DEFAULT_ADAM_VOICE))
    fav_ids = s.get("favorite_voice_ids")
    if not isinstance(fav_ids, list):
        fav_ids = []
        s["favorite_voice_ids"] = fav_ids
    if VOICE_ID not in fav_ids:
        fav_ids.insert(0, VOICE_ID)
    return s


def _migrate_legacy_non_secret_settings() -> dict:
    settings = _default_settings()
    legacy_file = get_legacy_data_dir() / "settings.json"
    if not legacy_file.exists():
        return settings
    try:
        legacy = _read_settings_file(legacy_file)
    except Exception as e:
        print(f"[WARN] legacy settings migration skipped ({e})")
        return settings
    for key in _SAFE_LEGACY_MIGRATION_KEYS:
        if key in legacy:
            migrated = _sanitize_legacy_value(key, legacy[key])
            if migrated is not None:
                settings[key] = migrated
    try:
        save_settings(settings)
        print(f"[INFO] migrated non-secret preferences from {legacy_file} to {SETTINGS_FILE}")
    except Exception as e:
        print(f"[WARN] cannot write migrated settings ({e})")
    return settings


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            s = _read_settings_file(SETTINGS_FILE)
        except (json.JSONDecodeError, IOError) as e:
            # File corrupt — backup và trả về defaults
            backup = SETTINGS_FILE + ".corrupt.bak"
            try:
                os.rename(SETTINGS_FILE, backup)
            except Exception:
                pass
            print(f"[WARN] settings.json corrupt ({e}), reset to defaults")
            s = {}
        return _backfill_settings(s)
    return _migrate_legacy_non_secret_settings()


def save_settings(s: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# ── Reveal file cross-platform ─────────────────────────────────────
def reveal_file(path: str):
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    elif sys.platform == "win32":
        subprocess.Popen(f'explorer /select,"{path}"', shell=True)
