import sys
import os
import json
import subprocess
import traceback
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from app_constants import DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY

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
            "telegram_bot_token":       "",
            "telegram_chat_id":         "",
            "output_dir":               DEFAULT_OUT,
            "enhance_prompt":           DEFAULT_PROMPT,
            "default_speed":            1.0,
            "selected_voice_id":        "",
            "selected_voice_name":      "Adam",
            "custom_styles":            [],
            "enhance_style_name":       "🎯  Nghiêm túc",
            "enhance_style_temperature": 0.3,
            "enhance_style_creative":   False,
            "language_code":            "vi",
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
        "telegram_bot_token":       "",
        "telegram_chat_id":         "",
        "output_dir":               DEFAULT_OUT,
        "enhance_prompt":           DEFAULT_PROMPT,
        "default_speed":            1.0,
        "selected_voice_id":        "",
        "selected_voice_name":      "Adam",
        "custom_styles":            [],
        "enhance_style_name":       "🎯  Nghiêm túc",
        "enhance_style_temperature": 0.3,
        "enhance_style_creative":   False,
        "language_code":            "vi",
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
