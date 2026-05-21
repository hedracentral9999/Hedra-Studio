import os
import re
import tempfile
import shutil
import time
import webbrowser
import subprocess
import base64
import hashlib
import json
import traceback
from pathlib import Path

import requests

from app_utils import (
    DEFAULT_OUT, DATA_DIR, ERROR_LOG, SETTINGS_FILE,
    get_auto_video_assets_dir, get_auto_video_env_local, load_settings, save_settings,
)

# ── .env.local helpers (Auto-Create-Video pipeline config) ───────────────────
_ENV_LOCAL = get_auto_video_env_local()
_ENGINE_ASSETS = get_auto_video_assets_dir()


def _env_local_path() -> Path:
    return get_auto_video_env_local(load_settings())


def _engine_assets_dir() -> Path:
    return get_auto_video_assets_dir(load_settings())

_EL_V3_TAG_RE = re.compile(r"\[[a-z][a-z -]{1,40}\]", re.I)
_EL_V3_STYLE_RULES = (
    ("[warmly]", re.compile(r"(follow|đăng ký|xem tiếp|đừng bỏ lỡ|hẹn gặp|cảm ơn)", re.I)),
    ("[curious]", re.compile(r"(\?|bạn có biết|vì sao|tại sao|liệu|điều gì xảy ra)", re.I)),
    ("[impressed]", re.compile(r"(đột phá|kỷ lục|ấn tượng|mới nhất|ra mắt|tăng mạnh|vượt trội|thành công)", re.I)),
    ("[thoughtful]", re.compile(r"(nhưng|tuy nhiên|vấn đề|rủi ro|cảnh báo|sự thật|đáng chú ý|bất ngờ)", re.I)),
    ("[professional]", re.compile(r"(\d|%|usd|đô|triệu|tỷ|nghìn|benchmark|api|ai|model|mô hình)", re.I)),
)

def _style_eleven_v3_text(text: str) -> str:
    trimmed = (text or "").strip()
    if not trimmed or _EL_V3_TAG_RE.search(trimmed):
        return text
    tag = next((t for t, pat in _EL_V3_STYLE_RULES if pat.search(trimmed)), "[thoughtful]")
    return f"{tag} {trimmed}"

def _logo_source_crop(src: QPixmap, crop_bottom: float = 1.0) -> QPixmap:
    """Optionally crop the source when a logo has extra caption text."""
    if src.isNull():
        return src
    crop_bottom = min(1.0, max(0.2, crop_bottom))
    crop_h = max(1, int(src.height() * crop_bottom))
    return src.copy(0, 0, src.width(), crop_h)

def _render_logo_square(
    src: QPixmap,
    size: int,
    scale: float = 1.0,
    crop_bottom: float = 1.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> QPixmap:
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    if src.isNull():
        return out
    src = _logo_source_crop(src, crop_bottom)
    # Fit the whole logo in the square by default. Users can still zoom/pan
    # freely in the editor when they want a tighter crop.
    factor = min(size / src.width(), size / src.height()) * max(scale, 0.05)
    w = max(1, int(src.width() * factor))
    h = max(1, int(src.height() * factor))
    scaled = src.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    x = int((size - scaled.width()) / 2 + offset_x * size)
    y = int((size - scaled.height()) / 2 + offset_y * size)
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return out

def _round_logo_pixmap(
    src: QPixmap,
    size: int,
    scale: float = 1.0,
    crop_bottom: float = 1.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> QPixmap:
    square = _render_logo_square(src, size, scale, crop_bottom, offset_x, offset_y)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, square)
    painter.end()
    return out

def _write_logo_svg_from_png(png_path: Path, svg_path: Path) -> None:
    encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <image href="data:image/png;base64,{encoded}" x="0" y="0" width="512" height="512" preserveAspectRatio="xMidYMid meet"/>
</svg>
'''
    svg_path.write_text(svg, encoding="utf-8")

def _backup_engine_logo_assets() -> Path | None:
    assets = _engine_assets_dir()
    existing = [
        p for p in [assets / "logo.svg"]
        if p.exists()
    ]
    existing.extend(
        p for p in assets.glob("avatar.*")
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and p.exists()
    )
    if not existing:
        return None

    backup_dir = assets / "backup" / time.strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in existing:
        shutil.copy2(p, backup_dir / p.name)
    return backup_dir

def _read_env_local() -> dict:
    """Đọc .env.local thành dict key→value. Comment và dòng trống bị bỏ qua."""
    out: dict = {}
    env_local = _env_local_path()
    if not env_local.exists():
        return out
    for line in env_local.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            k, _, v = stripped.partition("=")
            out[k.strip()] = v.strip()
    return out

def _write_env_local(updates: dict) -> None:
    """Ghi updates vào .env.local — giữ nguyên comments, thứ tự, dòng trống.
    Nếu key chưa tồn tại trong file thì append vào cuối (không tạo section mới)."""
    env_local = _env_local_path()
    env_local.parent.mkdir(parents=True, exist_ok=True)
    lines = (
        env_local.read_text(encoding="utf-8").splitlines(keepends=True)
        if env_local.exists()
        else []
    )
    written = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            new_lines.append(f"{key}={str(updates[key])}\n")
            written.add(key)
        else:
            new_lines.append(line)
    # Append các key mới chưa có trong file
    for k, v in updates.items():
        if k not in written:
            new_lines.append(f"{k}={str(v)}\n")
    env_local.write_text("".join(new_lines), encoding="utf-8")

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QFrame, QScrollArea, QStackedWidget,
    QFileDialog, QMessageBox, QSizePolicy, QSpacerItem,
    QListWidget, QListWidgetItem, QComboBox, QGridLayout,
    QWidget, QSlider, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl, QRectF
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QFont, QIcon, QColor, QPixmap, QPainter, QPainterPath

from app_constants import (
    DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY, GEMINI_CHAT_PROMPT,
    VOICE_ID, PROMPTS, PROMPT_TEMPLATES, VERSION,
    BG, SURFACE, SURFACE_2, BORDER, BORDER_SOFT, TEXT, TEXT_MUTE, TEXT_FAINT,
    ACCENT, ACCENT_HV, ACCENT_DN, SEG_BG, CONTROL_BG, CONTROL_HV, CONTROL_DN,
    get_style, apply_theme_globals,
)
from app_workers import _CreditsChecker, UpdateChecker, VoiceFetcher, AudioPreviewDownloader
from app_dialogs import AddStyleDialog, PromptWizardDialog, FeedbackDialog
from app_icons import icon_size, macos_tile_icon, ui_icon
from voice_library import VoiceLibraryDialog

_GENMAX_PREVIEW_URLS_FILE = DATA_DIR / "genmax_preview_urls.json"
_LIVE_PREVIEW_THREADS = set()
RECOMMENDED_CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MODEL_CHOICES = [
    RECOMMENDED_CLAUDE_MODEL,
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
]
LEGACY_DEFAULT_CLAUDE_MODELS = {"", "claude-3-5-haiku-20241022", "claude-sonnet-4-20250514"}


def _recommended_claude_model(value: str | None) -> str:
    model = (value or "").strip()
    return RECOMMENDED_CLAUDE_MODEL if model in LEGACY_DEFAULT_CLAUDE_MODELS else model


def _keep_preview_thread_alive(worker: QThread) -> QThread:
    _LIVE_PREVIEW_THREADS.add(worker)
    worker.finished.connect(lambda w=worker: _LIVE_PREVIEW_THREADS.discard(w))
    return worker

# ── Language options for voice favorites (ElevenLabs multilingual v2) ─────────
_VOICE_LANG_OPTIONS: list[tuple[str, str]] = [
    ("",    "— Tự động"),
    ("vi",  "Tiếng Việt"),
    ("en",  "Tiếng Anh"),
    ("ar",  "Tiếng Ả Rập"),
    ("bg",  "Tiếng Bulgaria"),
    ("zh",  "Tiếng Trung"),
    ("hr",  "Tiếng Croatia"),
    ("cs",  "Tiếng Séc"),
    ("da",  "Tiếng Đan Mạch"),
    ("nl",  "Tiếng Hà Lan"),
    ("fil", "Tiếng Filipino"),
    ("fi",  "Tiếng Phần Lan"),
    ("fr",  "Tiếng Pháp"),
    ("de",  "Tiếng Đức"),
    ("el",  "Tiếng Hy Lạp"),
    ("hi",  "Tiếng Hindi"),
    ("id",  "Tiếng Indonesia"),
    ("it",  "Tiếng Ý"),
    ("ja",  "Tiếng Nhật"),
    ("ko",  "Tiếng Hàn"),
    ("ms",  "Tiếng Mã Lai"),
    ("pl",  "Tiếng Ba Lan"),
    ("pt",  "Tiếng Bồ Đào Nha"),
    ("ro",  "Tiếng Romania"),
    ("ru",  "Tiếng Nga"),
    ("sk",  "Tiếng Slovakia"),
    ("es",  "Tiếng Tây Ban Nha"),
    ("sv",  "Tiếng Thụy Điển"),
    ("ta",  "Tiếng Tamil"),
    ("tr",  "Tiếng Thổ Nhĩ Kỳ"),
    ("uk",  "Tiếng Ukraine"),
]

# ── Apple HIG — language badge & combo stylesheets (single source of truth) ──
# Badge: pill shape (border-radius = height/2), secondarySystemFill background.
# Rule: mọi nơi dùng badge ngôn ngữ phải import hằng này — không inline riêng.
_LANG_BADGE_HEIGHT = 28          # px — đồng nhất ở add-form và fav-list rows
_LANG_CONTROL_WIDTH = 132        # px — badge và dropdown phải cùng visual width
_LANG_BADGE_SS = (               # QLabel pill — mono / verified subset
    "QLabel{"
    "background:#f2f2f7;"                  # macOS grouped secondary fill
    "border:none;"
    f"border-radius:{_LANG_BADGE_HEIGHT // 2}px;"  # perfect pill
    "padding:0 10px;"
    "font-size:13px;font-weight:500;color:#3c3c43;"
    "}"
)
_LANG_COMBO_SS = (               # QComboBox — multilingual / partial
    "QComboBox{"
    "background:#f2f2f7;"
    "border:none;"
    f"border-radius:{_LANG_BADGE_HEIGHT // 2}px;"
    "padding:0 22px 0 10px;"
    "font-size:13px;font-weight:500;color:#3c3c43;"
    "selection-background-color:#0071e3;}"
    "QComboBox:hover{background:#e9e9ef;}"
    "QComboBox::drop-down{border:none;width:20px;}"
    "QComboBox::down-arrow{"
    "image:none;width:0;height:0;"            # ẩn default arrow
    "border-left:3px solid transparent;"
    "border-right:3px solid transparent;"
    "border-top:4px solid #6e6e73;"           # chevron-down thuần CSS
    "margin-right:7px;}"
    "QComboBox QAbstractItemView{"
    "background:#ffffff;color:#1d1d1f;"
    "border:1px solid #d2d2d7;border-radius:8px;"
    "outline:none;"
    "selection-background-color:#e8f0fe;selection-color:#1d1d1f;}"
    "QComboBox QAbstractItemView::item{min-height:28px;padding:4px 12px;}"
    "QComboBox QAbstractItemView::item:hover{background:#f0f0f5;color:#1d1d1f;}"
)

# ── Helper: null widget dùng làm fallback khi widget chưa được tạo ──
class _NullEdit:
    """QLineEdit/QTextEdit stub — trả về chuỗi rỗng, tránh AttributeError."""
    def text(self) -> str:
        return ""

    def toPlainText(self) -> str:
        return ""


class _PipelineVoicePreviewWorker(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        provider: str,
        api_key: str,
        voice_id: str,
        genmax_provider: str = "elevenlabs",
        genmax_model_id: str = "eleven_v3",
        genmax_language_code: str = "vi",
        eleven_v3_style_enabled: bool = True,
        lucylab_endpoint: str = "https://api.lucylab.io/json-rpc",
        output_path: str = "",
        ai33_model_id: str = "eleven_v3",
        ai33_endpoint: str = "https://api.ai33.pro",
        ai33_output_format: str = "mp3_44100_128",
    ):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.voice_id = voice_id
        self.genmax_provider = (genmax_provider or "elevenlabs").strip().lower()
        self.genmax_model_id = (genmax_model_id or "eleven_v3").strip()
        self.genmax_language_code = (genmax_language_code or "vi").strip()
        self.eleven_v3_style_enabled = bool(eleven_v3_style_enabled)
        self.lucylab_endpoint = (lucylab_endpoint or "https://api.lucylab.io/json-rpc").strip()
        self.output_path = output_path
        self.ai33_model_id = (ai33_model_id or "eleven_v3").strip()
        self.ai33_endpoint = (ai33_endpoint or "https://api.ai33.pro").strip().rstrip("/")
        self.ai33_output_format = (ai33_output_format or "mp3_44100_128").strip()

    def run(self):
        try:
            text = "Xin chào, đây là giọng đọc mẫu trong Hedra Studio."
            if self.provider == "genmax":
                data = self._genmax_with_retry(text)
            elif self.provider == "ai33":
                data = self._ai33(text)
            elif self.provider == "elevenlabs":
                data = self._elevenlabs(text)
            elif self.provider == "lucylab":
                data = self._lucylab(text)
            else:
                raise ValueError("Provider không hỗ trợ nghe thử.")

            if self.output_path:
                path = Path(self.output_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                self.done.emit(str(path))
            else:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tmp.write(data)
                tmp.close()
                self.done.emit(tmp.name)
        except Exception as e:
            self.error.emit(str(e))

    def _genmax_with_retry(self, text: str) -> bytes:
        last_err = None
        for attempt in range(1, 3):
            try:
                return self._genmax(text)
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(1)
        raise RuntimeError(f"GenMax preview lỗi sau 2 lần thử: {last_err}")

    def _genmax(self, text: str) -> bytes:
        is_minimax = self.genmax_provider == "minimax"
        tts_text = (
            _style_eleven_v3_text(text)
            if self.eleven_v3_style_enabled and not is_minimax and self.genmax_model_id.lower() == "eleven_v3"
            else text
        )
        body = {
            "text": tts_text,
            "provider": "minimax" if is_minimax else "elevenlabs",
            "model_id": self.genmax_model_id or ("speech-2.8-turbo" if is_minimax else "eleven_v3"),
            "language_code": self.genmax_language_code or ("Vietnamese" if is_minimax else "vi"),
            "voice_settings": (
                {"speed": 1.0, "pitch": 0, "vol": 1.0}
                if is_minimax
                else {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0}
            ),
        }
        res = self._genmax_submit(body)
        if res.status_code == 200:
            return res.content
        if res.status_code != 202:
            raise RuntimeError(f"GenMax {res.status_code}: {res.text[:200]}")

        task_id = res.json().get("id")
        if not task_id:
            raise RuntimeError("GenMax không trả về task id")

        deadline = time.time() + 90
        interval = 0.75
        while time.time() < deadline:
            time.sleep(interval)
            poll = requests.get(
                f"https://api.genmax.io/v1/history/{task_id}",
                headers={"xi-api-key": self.api_key},
                timeout=15,
            )
            if poll.status_code != 200:
                raise RuntimeError(f"GenMax poll {poll.status_code}: {poll.text[:200]}")
            pdata = poll.json()
            status = pdata.get("status")
            if status == "completed":
                audio_url = (pdata.get("result") or {}).get("audio_url")
                if not audio_url:
                    raise RuntimeError("GenMax completed nhưng không có audio_url")
                dl = requests.get(audio_url, timeout=30)
                if dl.status_code != 200:
                    raise RuntimeError(f"GenMax download {dl.status_code}")
                return dl.content
            if status in ("failed", "error"):
                raise RuntimeError(f"GenMax render lỗi: {pdata}")
            interval = min(interval + 0.5, 2)
        raise RuntimeError("GenMax preview timeout sau 90 giây")

    def _genmax_submit(self, body: dict):
        return requests.post(
            f"https://api.genmax.io/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json=body,
            timeout=30,
        )

    def _elevenlabs(self, text: str) -> bytes:
        tts_text = _style_eleven_v3_text(text) if self.eleven_v3_style_enabled else text
        res = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "text": tts_text,
                "model_id": "eleven_v3",
                "output_format": "mp3_44100_128",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "speed": 1.0,
                },
            },
            timeout=60,
        )
        if res.status_code == 200:
            return res.content
        raise RuntimeError(f"ElevenLabs {res.status_code}: {res.text[:200]}")

    def _ai33(self, text: str) -> bytes:
        tts_text = (
            _style_eleven_v3_text(text)
            if self.eleven_v3_style_enabled and self.ai33_model_id.lower() == "eleven_v3"
            else text
        )
        endpoint = self.ai33_endpoint or "https://api.ai33.pro"
        output_format = self.ai33_output_format or "mp3_44100_128"
        res = requests.post(
            f"{endpoint}/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            params={"output_format": output_format},
            json={
                "text": tts_text,
                "model_id": self.ai33_model_id or "eleven_v3",
                "with_transcript": False,
            },
            timeout=60,
        )
        if res.status_code == 200 and "audio" in (res.headers.get("content-type", "").lower()):
            return res.content
        if res.status_code >= 400:
            raise RuntimeError(f"ai33 {res.status_code}: {res.text[:200]}")
        body = res.json()
        task_id = body.get("task_id") or body.get("id")
        if not task_id:
            raise RuntimeError("ai33 không trả về task_id")

        deadline = time.time() + 90
        interval = 0.75
        while time.time() < deadline:
            time.sleep(interval)
            poll = requests.get(
                f"{endpoint}/v1/task/{task_id}",
                headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
                timeout=15,
            )
            if poll.status_code != 200:
                raise RuntimeError(f"ai33 poll {poll.status_code}: {poll.text[:200]}")
            pdata = poll.json()
            status = str(pdata.get("status") or "").lower()
            if status in ("done", "completed"):
                meta = pdata.get("metadata") or {}
                audio_url = meta.get("audio_url") or meta.get("output_uri") or pdata.get("output_uri")
                if not audio_url:
                    raise RuntimeError("ai33 done nhưng không có audio_url")
                dl = requests.get(audio_url, timeout=60)
                if dl.status_code != 200:
                    raise RuntimeError(f"ai33 download {dl.status_code}")
                return dl.content
            if status in ("error", "failed"):
                raise RuntimeError(f"ai33 render lỗi: {pdata.get('error_message') or pdata}")
            interval = min(interval + 0.5, 2)
        raise RuntimeError("ai33 preview timeout sau 90 giây")

    def _lucylab_rpc(self, method: str, payload: dict) -> dict:
        res = requests.post(
            self.lucylab_endpoint,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "method": method, "input": payload, "id": f"preview-{int(time.time() * 1000)}"},
            timeout=30,
        )
        if res.status_code != 200:
            raise RuntimeError(f"LucyLab {res.status_code}: {res.text[:200]}")
        body = res.json()
        if "error" in body:
            raise RuntimeError(f"LucyLab {method}: {body['error'].get('message', body['error'])}")
        return body.get("result") or {}

    def _lucylab(self, text: str) -> bytes:
        submit = self._lucylab_rpc("ttsLongText", {
            "text": text,
            "userVoiceId": self.voice_id,
            "speed": 1,
        })
        export_id = submit.get("projectExportId")
        if not export_id:
            raise RuntimeError("LucyLab không trả về projectExportId")

        deadline = time.time() + 60
        interval = 0.75
        while time.time() < deadline:
            time.sleep(interval)
            status = self._lucylab_rpc("getExportStatus", {"projectExportId": export_id})
            state = status.get("state")
            if state == "completed":
                url = status.get("url")
                if not url:
                    raise RuntimeError("LucyLab completed nhưng không có audio URL")
                dl = requests.get(url, timeout=60)
                if dl.status_code != 200:
                    raise RuntimeError(f"LucyLab download {dl.status_code}")
                return dl.content
            if state == "failed":
                raise RuntimeError(f"LucyLab render lỗi: {status.get('error', 'unknown')}")
            interval = min(interval + 0.5, 2)
        raise RuntimeError("LucyLab preview timeout")


class _VoicePreviewUrlDownloadWorker(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url: str, output_path: str):
        super().__init__()
        self.url = url
        self.output_path = output_path

    def _looks_like_audio(self, data: bytes) -> bool:
        head = data[:16]
        return (
            head.startswith(b"ID3")
            or head.startswith(b"\xff\xfb")
            or head.startswith(b"\xff\xf3")
            or head.startswith(b"\xff\xf2")
            or (head.startswith(b"RIFF") and data[8:12] == b"WAVE")
            or head.startswith(b"OggS")
            or head.startswith(b"fLaC")
            or b"ftyp" in data[:16]
        )

    def run(self):
        try:
            res = requests.get(self.url, timeout=30)
            if res.status_code != 200:
                raise RuntimeError(f"Preview download {res.status_code}: {res.text[:120]}")
            ct = res.headers.get("content-type", "")
            data = res.content
            if ct.startswith("text/") and not self._looks_like_audio(data):
                maybe_url = res.text.strip()
                if maybe_url.startswith("http://") or maybe_url.startswith("https://"):
                    res = requests.get(maybe_url, timeout=30)
                    if res.status_code != 200:
                        raise RuntimeError(f"Preview download {res.status_code}: {res.text[:120]}")
                    ct = res.headers.get("content-type", "")
                    data = res.content
            if ct and "audio" not in ct and "mpeg" not in ct and "octet-stream" not in ct and not self._looks_like_audio(data):
                raise RuntimeError(f"Preview không phải audio: {ct}")
            path = Path(self.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.done.emit(str(path))
        except Exception as e:
            self.error.emit(str(e))


class _GenMaxCatalogWorker(QThread):
    done = pyqtSignal(list, list, list)
    error = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        provider: str,
        target_ids: list[str] | None = None,
        target_names: list[str] | None = None,
    ):
        super().__init__()
        self.api_key = api_key.strip()
        self.provider = (provider or "elevenlabs").strip().lower()
        self.target_ids = {v.strip() for v in (target_ids or []) if v and v.strip()}
        self.target_names = [v.strip() for v in (target_names or []) if v and v.strip()]

    def run(self):
        try:
            if not self.api_key:
                raise ValueError("Thiếu GenMax API Key")

            headers = {"xi-api-key": self.api_key}
            languages_by_provider: dict[str, list] = {}
            models_by_provider: dict[str, list] = {}

            def load_languages(provider: str) -> list:
                if provider in languages_by_provider:
                    return languages_by_provider[provider]
                params = {"provider": "minimax"} if provider == "minimax" else None
                res = requests.get(
                    "https://api.genmax.io/v1/languages",
                    headers=headers,
                    params=params,
                    timeout=12,
                )
                items = []
                if res.status_code == 200:
                    for item in res.json():
                        if isinstance(item, dict):
                            code = str(item.get("code") or item.get("name") or "").strip()
                            name = str(item.get("name") or code).strip()
                            if code:
                                items.append({"code": code, "name": name})
                languages_by_provider[provider] = items
                return items

            def load_models(provider: str) -> list:
                if provider in models_by_provider:
                    return models_by_provider[provider]
                params = {"provider": "minimax"} if provider == "minimax" else None
                res = requests.get(
                    "https://api.genmax.io/v1/models",
                    headers=headers,
                    params=params,
                    timeout=12,
                )
                items = []
                if res.status_code == 200:
                    for item in res.json():
                        if isinstance(item, dict):
                            model_id = str(item.get("model_id") or "").strip()
                            name = str(item.get("name") or model_id).strip()
                            if model_id:
                                items.append({"id": model_id, "name": name})
                models_by_provider[provider] = items
                return items

            def include_voice(voice_id: str, aliases: list[str] | None = None) -> bool:
                if not self.target_ids:
                    return True
                candidates = {voice_id, *(aliases or [])}
                return bool(candidates & self.target_ids)

            voices = []

            if self.provider in ("elevenlabs", "auto"):
                eleven_languages = load_languages("elevenlabs")
                load_models("elevenlabs")
                seen_eleven_ids = set()

                def add_eleven_voice(v: dict):
                    voice_id = str(v.get("voice_id") or "").strip()
                    if not voice_id or voice_id in seen_eleven_ids or not include_voice(voice_id):
                        return
                    seen_eleven_ids.add(voice_id)
                    verified = []
                    for lang in v.get("verified_languages", []) or []:
                        if not isinstance(lang, dict):
                            continue
                        code = str(lang.get("language_id") or lang.get("language") or "").strip()
                        name = str(lang.get("language") or code).strip()
                        model = str(lang.get("model_id") or "").strip()
                        if code:
                            verified.append({"code": code, "name": name, "model": model})
                    voices.append({
                        "id": voice_id,
                        "name": str(v.get("name") or voice_id),
                        "provider": "elevenlabs",
                        "language": str(v.get("language") or "").strip(),
                        "preview": v.get("preview_url") or "",
                        "model": "eleven_v3",
                        "verified_languages": verified,
                    })

                default_res = requests.get(
                    "https://api.genmax.io/v1/default-voices",
                    headers=headers,
                    params={"page_size": 100},
                    timeout=15,
                )
                if default_res.status_code == 200:
                    for v in default_res.json().get("voices", []):
                        add_eleven_voice(v)
                elif self.provider == "elevenlabs":
                    raise RuntimeError(f"GenMax voices HTTP {default_res.status_code}: {default_res.text[:200]}")

                shared_search_terms = []
                for term in [*self.target_names, *self.target_ids]:
                    if term and term not in shared_search_terms:
                        shared_search_terms.append(term)
                for name in shared_search_terms:
                    shared_res = requests.get(
                        "https://api.genmax.io/v1/shared-voices",
                        headers=headers,
                        params={"page_size": 100, "sort": "trending", "search": name},
                        timeout=15,
                    )
                    if shared_res.status_code != 200:
                        continue
                    for v in shared_res.json().get("voices", []):
                        add_eleven_voice(v)

                languages_by_provider["elevenlabs"] = eleven_languages

            if self.provider in ("minimax", "auto"):
                minimax_languages = load_languages("minimax")
                load_models("minimax")
                minimax_language_codes = {item["code"] for item in minimax_languages}
                voice_res = requests.get(
                    "https://api.genmax.io/v1/minimax/system-voices",
                    headers=headers,
                    params={"page": 1, "page_size": 100},
                    timeout=15,
                )
                if voice_res.status_code != 200 and self.provider == "minimax":
                    raise RuntimeError(f"GenMax MiniMax voices HTTP {voice_res.status_code}: {voice_res.text[:200]}")
                if voice_res.status_code == 200:
                    for v in voice_res.json().get("voice_list", []):
                        tags = [str(t) for t in v.get("tag_list", []) if t]
                        voice_id = str(v.get("voice_id") or "").strip()
                        uniq_id = str(v.get("uniq_id") or "").strip()
                        if not voice_id and not uniq_id:
                            continue
                        canonical_id = voice_id or uniq_id
                        if not include_voice(canonical_id, [uniq_id, voice_id]):
                            continue
                        language = next((t for t in tags if t in minimax_language_codes), "")
                        voices.append({
                            "id": canonical_id,
                            "name": str(v.get("voice_name") or uniq_id or canonical_id),
                            "provider": "minimax",
                            "language": language,
                            "preview": v.get("sample_audio") or "",
                            "model": "speech-2.8-turbo",
                            "verified_languages": [{"code": language, "name": language, "model": "speech-2.8-turbo"}] if language else [],
                        })
                cloned_res = requests.get(
                    "https://api.genmax.io/v1/minimax/voices",
                    headers=headers,
                    timeout=15,
                )
                if cloned_res.status_code == 200:
                    for v in cloned_res.json().get("voices", []):
                        if v.get("status") and v.get("status") != "done":
                            continue
                        voice_id = str(v.get("id") or "").strip()
                        if not voice_id or not include_voice(voice_id):
                            continue
                        language = str(v.get("language_tag") or "").strip()
                        voices.append({
                            "id": voice_id,
                            "name": f"{v.get('voice_name') or voice_id} · cloned",
                            "provider": "minimax",
                            "language": language,
                            "preview": v.get("sample_audio_url") or "",
                            "model": "speech-2.8-turbo",
                            "verified_languages": [{"code": language, "name": language, "model": "speech-2.8-turbo"}] if language else [],
                        })

            voices.sort(key=lambda x: x["name"].lower())
            provider = voices[0].get("provider", self.provider if self.provider != "auto" else "elevenlabs") if voices else (self.provider if self.provider != "auto" else "elevenlabs")
            self.done.emit(voices, load_languages(provider), load_models(provider))
        except Exception as e:
            self.error.emit(str(e))


class _GenMaxLanguagesWorker(QThread):
    done = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, provider: str):
        super().__init__()
        self.api_key = api_key.strip()
        self.provider = (provider or "elevenlabs").strip().lower()

    def run(self):
        try:
            if not self.api_key:
                return
            params = {"provider": "minimax"} if self.provider == "minimax" else None
            res = requests.get(
                "https://api.genmax.io/v1/languages",
                headers={"xi-api-key": self.api_key},
                params=params,
                timeout=12,
            )
            if res.status_code != 200:
                raise RuntimeError(f"GenMax languages HTTP {res.status_code}: {res.text[:200]}")
            items = []
            for item in res.json():
                if isinstance(item, dict):
                    code = str(item.get("code") or item.get("name") or "").strip()
                    name = str(item.get("name") or code).strip()
                    if code:
                        items.append({"code": code, "name": name})
            self.done.emit(items)
        except Exception as e:
            self.error.emit(str(e))


class _VoiceCheckerWorker(QThread):
    """Gọi ElevenLabs API lấy thông tin giọng theo voice_id.

    Emit done({"name": str, "langs": list[str]}) trong đó:
      langs = []          → unknown/full fallback
      langs = ["vi"]      → mono — chỉ hỗ trợ 1 ngôn ngữ
      langs = ["vi","en"] → list ngôn ngữ lấy từ ElevenLabs model API
    """
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    # Map label string → ISO code (ElevenLabs labels dùng tên đầy đủ tiếng Anh)
    _LABEL_MAP: dict[str, str] = {
        "vietnamese": "vi", "english": "en", "japanese": "ja",
        "korean": "ko", "chinese": "zh", "french": "fr",
        "german": "de", "spanish": "es", "italian": "it",
        "portuguese": "pt", "russian": "ru", "arabic": "ar",
        "indonesian": "id", "hindi": "hi", "dutch": "nl",
        "polish": "pl", "turkish": "tr", "swedish": "sv",
        "filipino": "fil", "malay": "ms", "romanian": "ro",
        "ukrainian": "uk", "greek": "el", "czech": "cs",
        "danish": "da", "finnish": "fi", "bulgarian": "bg",
        "slovak": "sk", "croatian": "hr", "tamil": "ta",
    }
    # Models có nghĩa là đa ngôn ngữ thật sự
    _MULTILINGUAL_MODELS = {
        "eleven_multilingual_v2",
        "eleven_multilingual_v1",
        "eleven_turbo_v2_5",
        "eleven_flash_v2_5",
    }
    _SUPPORTED_CODES = {code for code, _label in _VOICE_LANG_OPTIONS if code}

    def __init__(self, voice_id: str, api_keys: list[str]):
        super().__init__()
        self.voice_id = voice_id.strip()
        self.api_keys = [k.strip() for k in api_keys if k and k.strip()]

    @classmethod
    def _clean_codes(cls, codes: list[str]) -> list[str]:
        aliases = {
            "cmn": "zh",
            "zh-cn": "zh",
            "zh-tw": "zh",
            "pt-br": "pt",
            "nb": "no",
        }
        out: list[str] = []
        for raw in codes:
            code = aliases.get(str(raw).strip().lower(), str(raw).strip().lower())
            if code and code in cls._SUPPORTED_CODES and code not in out:
                out.append(code)
        return out

    @classmethod
    def _language_code_from_item(cls, item: dict) -> str:
        for key in ("language_id", "language_code", "code", "id"):
            value = item.get(key)
            if value:
                return str(value).strip().lower()
        return ""

    def _model_language_codes(self, key: str, model_ids: set[str]) -> list[str]:
        if not model_ids:
            return []
        res = requests.get(
            "https://api.elevenlabs.io/v1/models",
            headers={"xi-api-key": key},
            timeout=10,
        )
        if res.status_code != 200:
            return []
        raw = res.json()
        models = raw.get("models", raw) if isinstance(raw, dict) else raw
        if not isinstance(models, list):
            return []

        codes: list[str] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("model_id") or model.get("id") or "").strip()
            if model_id not in model_ids:
                continue
            if model.get("can_do_text_to_speech") is False:
                continue
            for lang in model.get("languages") or []:
                if isinstance(lang, dict):
                    codes.append(self._language_code_from_item(lang))
                else:
                    codes.append(str(lang).strip().lower())
        return self._clean_codes(codes)

    def run(self):
        if not self.api_keys:
            self.error.emit("no_key")
            return
        last_err = "Không kết nối được"
        for key in self.api_keys:
            try:
                res = requests.get(
                    f"https://api.elevenlabs.io/v1/voices/{self.voice_id}",
                    headers={"xi-api-key": key},
                    timeout=10,
                )
                if res.status_code == 404:
                    self.error.emit("Không tìm thấy giọng — kiểm tra lại Voice ID")
                    return
                if res.status_code == 401:
                    last_err = "invalid_key"; continue
                if res.status_code != 200:
                    last_err = f"Lỗi {res.status_code}"; continue

                data = res.json()
                name = data.get("name") or self.voice_id

                # ── 1. verified_languages (nguồn chính xác nhất) ──────────
                verified = data.get("verified_languages") or []
                verified_codes = [
                    v.get("language_id", "").strip().lower()
                    for v in verified if v.get("language_id")
                ]
                verified_codes = self._clean_codes(verified_codes)

                # ── 2. fine_tuning.language (giọng cloned/professional) ───
                ft = data.get("fine_tuning") or {}
                fine_langs = self._clean_codes([(ft.get("language") or "").strip().lower()])

                # ── 3. labels.language (hint only) ────────────────────────
                # ElevenLabs labels often describe the source/accent language
                # of a library voice. They are not a reliable "only supported
                # language" constraint for multilingual models.
                labels = data.get("labels") or {}
                label_lang = (labels.get("language") or "").strip().lower()
                label_codes = self._clean_codes([self._LABEL_MAP.get(label_lang, "")])

                # ── 4. Base model IDs + /v1/models languages ──────────────
                model_ids = set(data.get("high_quality_base_model_ids") or [])
                is_base_multilingual = bool(model_ids & self._MULTILINGUAL_MODELS)
                model_codes = self._model_language_codes(key, model_ids)

                # ── Quyết định langs ──────────────────────────────────────
                if model_codes:
                    # Đây là list ngôn ngữ model ElevenLabs thật sự hỗ trợ.
                    langs = model_codes
                elif verified_codes:
                    # verified_languages là nguồn voice-level tốt nhất nếu model API không trả list.
                    langs = verified_codes
                elif fine_langs:
                    # Giọng fine-tune có ngôn ngữ cụ thể.
                    langs = fine_langs
                elif is_base_multilingual or not model_ids:
                    # Multilingual model, or API did not expose model support.
                    # Treat unknown as selectable full list instead of locking
                    # the voice to labels.language (e.g. Adam -> English).
                    langs = []
                elif label_codes:
                    # Only use label as mono fallback when model metadata exists
                    # and does not indicate multilingual support.
                    langs = label_codes
                else:
                    # Explicit non-multilingual model without better metadata.
                    langs = ["en"]

                self.done.emit({"name": name, "langs": langs})
                return
            except Exception as e:
                last_err = str(e)
        self.error.emit(last_err)


class SettingsDialog(QDialog):
    # Màu sidebar kiểu macOS System Settings
    _SB_BG       = "#f7f7f8"
    _SB_ACTIVE   = ACCENT
    _SB_TEXT     = "#1d1d1f"
    _SB_MUTE     = "#6e6e73"
    _GROUP_BG    = CONTROL_BG
    _GROUP_BORDER= "transparent"
    _LABEL_W     = 154          # chiều rộng cột label trong form
    _LANG_NAMES: dict = {
        "en": "EN",  "vi": "VI",  "zh": "ZH",
        "ja": "JA",  "ko": "KO",  "ar": "AR",
        "bg": "BG",  "hr": "HR",  "cs": "CS",
        "da": "DA",  "nl": "NL",  "fil": "FIL",
        "fi": "FI",  "fr": "FR",  "de": "DE",
        "el": "EL",  "hi": "HI",  "hu": "HU",
        "id": "ID",  "it": "IT",  "ms": "MS",
        "no": "NO",  "pl": "PL",  "pt": "PT",
        "ro": "RO",  "ru": "RU",  "sk": "SK",
        "es": "ES",  "sv": "SV",  "ta": "TA",
        "tr": "TR",  "uk": "UK",
    }

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        # Luôn lấy settings.json mới nhất trước khi dựng UI. Trường hợp user
        # bấm "Lưu" nhỏ trong card prompt rồi đóng/mở Settings ngay, parent
        # window có thể vẫn giữ bản settings cũ trong RAM.
        self.settings = (settings or {}).copy()
        try:
            self.settings.update(load_settings())
        except Exception:
            pass
        self._theme_mode = self.settings.get("app_theme", "system")
        _tokens = apply_theme_globals(globals(), self._theme_mode)
        self._SB_BG = _tokens["SURFACE_2"]
        self._SB_TEXT = _tokens["TEXT"]
        self._SB_MUTE = _tokens["TEXT_MUTE"]
        self._GROUP_BG = _tokens["CONTROL_BG"]
        self.setWindowTitle("Settings")
        self.setMinimumSize(900, 660)
        self.resize(1100, 780)
        self.setStyleSheet(get_style(self._theme_mode))
        # Voice selection state (edited in dialog, saved on accept)
        self._sel_voice_id   = self.settings.get("selected_voice_id") or VOICE_ID
        self._sel_voice_name = self.settings.get("selected_voice_name") or "Adam"
        # AV voice state (initialized in _page_voices from .env.local)
        self._av_sel_id   = ""
        self._av_sel_name = ""
        self._pv_genmax_preview_urls = self._pv_load_genmax_preview_urls()
        self._build()

    def _combo_item_view_style(self, item_height: int = 28) -> str:
        return (
            f"QComboBox QAbstractItemView{{background:{SURFACE};color:{TEXT};"
            f"border:1px solid {BORDER};border-radius:8px;outline:none;padding:2px;"
            f"selection-background-color:{CONTROL_HV};selection-color:{TEXT};}}"
            f"QComboBox QAbstractItemView::item{{min-height:{item_height}px;"
            f"padding:4px 12px;color:{TEXT};border-radius:6px;}}"
            f"QComboBox QAbstractItemView::item:hover{{background:{CONTROL_HV};color:{TEXT};}}"
            f"QComboBox QAbstractItemView::item:selected{{background:{CONTROL_HV};color:{ACCENT};font-weight:600;}}"
        )

    def _prompt_style_data(self) -> dict[str, dict]:
        """Return prompt presets after applying user overrides.

        Built-in presets are editable slots in this app. If the user saves
        "Hài hước" with temperature 0.00, reopening/selecting "Hài hước" must
        return exactly that saved setup, not the factory default 0.70.
        """
        overrides = self.settings.get("prompt_preset_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        default_temps = {"Nghiêm túc": 0.3, "Hài hước": 0.7}
        data: dict[str, dict] = {}
        for name, default_prompt in PROMPTS.items():
            ov = overrides.get(name, {})
            if not isinstance(ov, dict):
                ov = {}
            default_temp = default_temps.get(name, 0.3)
            temp = ov.get("temperature", default_temp)
            try:
                temp = float(temp)
            except (TypeError, ValueError):
                temp = default_temp
            temp = max(0.0, min(1.0, temp))
            data[name] = {
                "prompt": ov.get("prompt") or default_prompt,
                "temperature": temp,
                "creative": ov.get("creative", temp >= 0.5),
                "builtin": True,
            }
        for cs in self.settings.get("custom_styles", []):
            cs_name = cs.get("name", "")
            cs_prompt = cs.get("prompt", "")
            if not cs_name or not cs_prompt:
                continue
            temp = cs.get("temperature", 0.7 if cs.get("creative", False) else 0.3)
            try:
                temp = float(temp)
            except (TypeError, ValueError):
                temp = 0.7 if cs.get("creative", False) else 0.3
            temp = max(0.0, min(1.0, temp))
            data[cs_name] = {
                "prompt": cs_prompt,
                "temperature": temp,
                "creative": cs.get("creative", temp >= 0.5),
                "builtin": False,
            }
        return data

    def _commit_current_prompt_style(self) -> None:
        if not hasattr(self, "prompt"):
            return
        name = (
            getattr(self, "_ep_active_style", "")
            or self.settings.get("enhance_style_name", "")
            or "Nghiêm túc"
        )
        prompt = self.prompt.toPlainText()
        if hasattr(self, "_settings_temp_slider"):
            temp = max(0.0, min(1.0, self._settings_temp_slider.value() / 100.0))
        else:
            saved_temp = self.settings.get("enhance_style_temperature", None)
            temp = 0.3 if saved_temp is None or str(saved_temp).strip() == "" else float(saved_temp)
        creative = temp >= 0.5
        self.settings["enhance_prompt"] = prompt
        self.settings["enhance_style_name"] = name
        self.settings["enhance_style_temperature"] = temp
        self.settings["enhance_style_creative"] = creative

        if name in PROMPTS:
            overrides = self.settings.get("prompt_preset_overrides", {})
            if not isinstance(overrides, dict):
                overrides = {}
            overrides[name] = {
                "prompt": prompt,
                "temperature": temp,
                "creative": creative,
            }
            self.settings["prompt_preset_overrides"] = overrides
            return

        for style in self.settings.get("custom_styles", []):
            if style.get("name") == name:
                style["prompt"] = prompt
                style["temperature"] = temp
                style["creative"] = creative
                break

    def _pv_load_genmax_preview_urls(self) -> dict[str, str]:
        try:
            data = json.loads(_GENMAX_PREVIEW_URLS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(k).strip(): str(v).strip()
            for k, v in data.items()
            if str(k).strip() and str(v).strip().startswith(("http://", "https://"))
        }

    def _pv_save_genmax_preview_urls(self) -> None:
        try:
            _GENMAX_PREVIEW_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _GENMAX_PREVIEW_URLS_FILE.write_text(
                json.dumps(getattr(self, "_pv_genmax_preview_urls", {}), ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _pv_set_genmax_preview_url(self, voice_id: str, preview_url: str) -> None:
        voice_id = (voice_id or "").strip()
        preview_url = (preview_url or "").strip()
        if not voice_id or not preview_url:
            return
        if not hasattr(self, "_pv_genmax_preview_urls"):
            self._pv_genmax_preview_urls = {}
        if self._pv_genmax_preview_urls.get(voice_id) == preview_url:
            return
        self._pv_genmax_preview_urls[voice_id] = preview_url
        self._pv_save_genmax_preview_urls()

    def _pv_alive(self) -> bool:
        try:
            self.objectName()
            return True
        except RuntimeError:
            return False

    def _pv_safe_call(self, fn):
        if not self._pv_alive():
            return None
        return fn()

    # ── Helper: tạo một "grouped section" kiểu macOS ──────────────
    def _group(self, title: str = "") -> tuple:
        """Trả về (outer_widget, form_layout) để thêm rows vào."""
        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget{{background:{self._GROUP_BG};"
            "border:none;"
            "border-radius:12px;}"
        )
        vbox = QVBoxLayout(outer)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        if title:
            hdr = QLabel(title)
            hdr.setStyleSheet(
                f"QLabel{{font-size:11px;font-weight:600;color:{TEXT_MUTE};"
                "letter-spacing:0.4px;background:transparent;border:none;"
                "padding:11px 18px 7px 18px;}"
            )
            vbox.addWidget(hdr)
        return outer, vbox

    def _row(self, container_layout, label: str, widget: QWidget,
             note: str = "", last: bool = False):
        """Thêm một form row vào group: label trái + widget phải."""
        row_w = QWidget()
        row_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        row_w.setMinimumHeight(48)
        h = QHBoxLayout(row_w)
        h.setContentsMargins(14, 9, 14, 9)
        h.setSpacing(14)

        lbl = QLabel(label)
        lbl.setFixedWidth(self._LABEL_W)
        lbl.setStyleSheet(
            f"QLabel{{font-size:13px;color:{TEXT};font-weight:500;"
            "background:transparent;border:none;}"
        )
        lbl.setWordWrap(True)
        h.addWidget(lbl)

        right = QVBoxLayout()
        right.setSpacing(3)
        right.addWidget(widget)
        if note:
            n = QLabel(note)
            n.setStyleSheet(
                f"QLabel{{font-size:11px;color:{TEXT_FAINT};"
                "background:transparent;border:none;}"
            )
            n.setWordWrap(True)
            right.addWidget(n)
        h.addLayout(right)
        container_layout.addWidget(row_w)
        if not last:
            sep_wrap = QWidget()
            sep_wrap.setFixedHeight(1)
            sep_wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
            sep_h = QHBoxLayout(sep_wrap)
            sep_h.setContentsMargins(14, 0, 14, 0)
            sep_h.setSpacing(0)
            sep = QWidget()
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"QWidget{{background:{BORDER_SOFT};border:none;}}")
            sep_h.addWidget(sep)
            container_layout.addWidget(sep_wrap)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"QLabel{{font-size:13px;font-weight:700;color:{TEXT};"
            "padding:22px 0 8px 0;"
            "background:transparent;border:none;}"
        )
        return lbl

    def _section_label_with_icon(self, icon_name: str, text: str) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 22, 0, 8)
        h.setSpacing(8)
        ic_lbl = QLabel()
        pm = ui_icon(icon_name, 18, TEXT).pixmap(18, 18)
        ic_lbl.setPixmap(pm)
        ic_lbl.setFixedSize(18, 18)
        ic_lbl.setStyleSheet("QLabel{background:transparent;border:none;}")
        txt_lbl = QLabel(text)
        txt_lbl.setStyleSheet(
            f"QLabel{{font-size:13px;font-weight:700;color:{TEXT};"
            "background:transparent;border:none;}"
        )
        h.addWidget(ic_lbl)
        h.addWidget(txt_lbl)
        h.addStretch()
        return wrap

    def _page_header(self, icon: str, title: str, subtitle: str = "") -> QWidget:
        """Apple HIG page header — icon + title lớn + optional subtitle muted.
        Hiển thị ở đầu mỗi content page, có border-bottom phân cách."""
        header = QWidget()
        header.setStyleSheet("QWidget{background:transparent;border:none;}")
        h = QHBoxLayout(header)
        h.setContentsMargins(0, 4, 0, 14)
        h.setSpacing(12)
        # Icon tile 28px
        ic = QLabel()
        pm = ui_icon(icon, 22, "#1d1d1f").pixmap(22, 22)
        ic.setPixmap(pm)
        ic.setFixedSize(22, 22)
        ic.setStyleSheet("QLabel{background:transparent;border:none;}")
        h.addWidget(ic)
        # Text block
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setStyleSheet(
            "QLabel{font-size:17px;font-weight:700;color:#1d1d1f;"
            "background:transparent;border:none;}"
        )
        text_col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet(
                f"QLabel{{font-size:12px;color:{TEXT_FAINT};"
                "background:transparent;border:none;}"
            )
            s.setWordWrap(True)
            text_col.addWidget(s)
        h.addLayout(text_col)
        h.addStretch()
        # Bottom divider
        outer = QWidget()
        outer.setStyleSheet("QWidget{background:transparent;border:none;}")
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(0)
        ov.addWidget(header)
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet("QWidget{background:#e5e5ea;border:none;}")
        ov.addWidget(div)
        ov.addSpacing(14)
        return outer

    @staticmethod
    def _add_collapsible(parent_lay: "QVBoxLayout", label: str = "Tuỳ chọn nâng cao") -> "tuple[QWidget, QVBoxLayout]":
        """Tạo nút toggle + container ẩn/hiện.  Dùng ở mọi page.
        Trả về (container_widget, inner_layout)."""
        btn = QPushButton(f"  ▸  {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#0a84ff;"
            "font-size:12px;font-weight:500;text-align:left;padding:10px 0 4px 0;}"
            "QPushButton:hover{color:#0066cc;}"
        )
        container = QWidget()
        container.setStyleSheet("QWidget{background:transparent;border:none;}")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        container.setVisible(False)

        def _toggle(_=False):
            vis = not container.isVisible()
            container.setVisible(vis)
            btn.setText(f"  ▾  {label}" if vis else f"  ▸  {label}")

        btn.clicked.connect(_toggle)
        parent_lay.addWidget(btn)
        parent_lay.addWidget(container)
        return container, cl

    # ── Hướng dẫn lấy API key ─────────────────────────────────────
    def _show_api_guide(self, service: str):
        """Dialog hướng dẫn từng bước lấy API key theo service."""
        _GUIDES = {
            "elevenlabs": {
                "title":     "Hướng dẫn lấy ElevenLabs API Key",
                "subtitle":  "Đăng ký qua link này để hỗ trợ Hedra Studio 🙏",
                "url":       "https://try.elevenlabs.io/rinor1xaj4ze",
                "url_label": "Mở trang đăng ký ElevenLabs",
                "steps": [
                    ("Mở trang đăng ký",
                     "Nhấn nút bên dưới → trình duyệt mở elevenlabs.io"),
                    ("Tạo tài khoản",
                     'Điền email + mật khẩu → nhấn "Create Account"\n'
                     "(hoặc đăng nhập nhanh bằng Google/Apple)"),
                    ("Xác nhận email",
                     "Kiểm tra hộp thư → nhấn link xác nhận từ ElevenLabs\n"
                     "(kiểm tra thư mục Spam nếu không thấy)"),
                    ("Vào API Keys",
                     'Sau khi đăng nhập → vào menu trái "API Keys"\n'
                     '→ nhấn "Create Key"'),
                    ("Chọn quyền đơn giản, đủ dùng",
                     "Trong khung Create API Key, bật như sau:\n"
                     "• Text to Speech: Access\n"
                     "• Voices: Read (hoặc Access nếu bạn cần thêm/sửa voices)\n"
                     "• Models: Read\n"
                     "• History: Read\n"
                     "• Pronunciation Dictionaries: Read (nếu có dùng)\n"
                     "• User: Read\n"
                     "• Các mục còn lại: No Access"),
                    ("Gợi ý an toàn",
                     "Ưu tiên chỉ cấp Read khi có thể.\n"
                     "Chỉ bật Write/Access cho mục bạn thật sự cần thao tác."),
                    ("Tạo key",
                     'Nhấn "Create Key" → đặt tên (ví dụ: Hedra Studio Mac)\n'
                     "→ copy key ngay sau khi tạo"),
                    ("Copy key vào app",
                     "Copy key vừa tạo\n"
                     "→ Paste vào ô API Keys trong Hedra Studio\n"
                     "→ Mỗi key 1 dòng — có thể thêm nhiều key để tự xoay"),
                    ("Kiểm tra nhanh",
                     "Nhấn Generate 1 đoạn ngắn để xác nhận key hoạt động"),
                ],
            },
            "genmax": {
                "title":     "Hướng dẫn lấy GenMax API Key",
                "subtitle":  "GenMax rẻ hơn ElevenLabs nhiều — voice ID giống nhau 100%",
                "url":       "https://genmax.io/?ref=e3tsg8",
                "url_label": "🔗  Đăng ký GenMax (link ưu đãi)",
                "steps": [
                    ("Mở GenMax",
                     "Nhấn nút bên dưới → genmax.io\n"
                     "(Link ưu đãi — đăng ký qua link này để hỗ trợ Hedra Studio 🙏)"),
                    ("Tạo tài khoản",
                     "Nhấn Sign Up → điền email + mật khẩu\n"
                     "(hoặc đăng nhập bằng Google)"),
                    ("Nạp credits",
                     "GenMax tính phí theo số ký tự — rẻ hơn ElevenLabs đáng kể\n"
                     "→ Vào Billing để nạp lần đầu"),
                    ("Lấy API Key",
                     "Vào Dashboard → mục API Keys\n"
                     "→ Nhấn \"Create API Key\" → đặt tên → Copy key"),
                    ("Paste vào app",
                     "Paste key vào ô GenMax API Key trong Hedra Studio\n"
                     "→ nhấn Lưu\n\n"
                     "App sẽ dùng GenMax làm TTS chính,\n"
                     "tự động chuyển sang ElevenLabs nếu GenMax lỗi"),
                    ("Kiểm tra",
                     "Generate 1 đoạn ngắn — nếu thấy \"Đang chờ GenMax render audio\" là đang hoạt động"),
                ],
            },
            "deepseek": {
                "title":     "Hướng dẫn lấy DeepSeek API Key",
                "subtitle":  "DeepSeek tặng free credits khi đăng ký tài khoản mới",
                "url":       "https://platform.deepseek.com/api_keys",
                "url_label": "🔗  Mở DeepSeek Platform",
                "steps": [
                    ("Mở DeepSeek Platform",
                     "Nhấn nút bên dưới → platform.deepseek.com"),
                    ("Tạo tài khoản",
                     'Nhấn "Sign Up" → điền email + mật khẩu\n'
                     "(hoặc đăng nhập bằng Google)"),
                    ("Xác nhận email",
                     "Kiểm tra hộp thư → nhấn link xác nhận"),
                    ("Vào trang API Keys",
                     'Đăng nhập xong → nhấn "API Keys" ở sidebar trái'),
                    ("Tạo API Key",
                     'Nhấn "Create new API key" → đặt tên → nhấn "OK"\n'
                     "→ Chú ý: copy key ngay, sau này không xem lại được"),
                    ("Paste vào app",
                     "Paste key vào ô API Key của DeepSeek trong Hedra Studio\n"
                     "→ nhấn Lưu"),
                ],
            },
            "gemini": {
                "title":     "Hướng dẫn lấy Gemini API Key",
                "subtitle":  "Cần tài khoản Google. Gemini có free tier miễn phí",
                "url":       "https://aistudio.google.com/app/apikey",
                "url_label": "🔗  Mở Google AI Studio",
                "steps": [
                    ("Mở Google AI Studio",
                     "Nhấn nút bên dưới → aistudio.google.com"),
                    ("Đăng nhập Google",
                     "Đăng nhập bằng tài khoản Google của bạn"),
                    ("Vào trang API Keys",
                     'Nhấn "Get API Key" ở sidebar trái\n'
                     "(hoặc vào trực tiếp: aistudio.google.com/app/apikey)"),
                    ("Tạo API Key",
                     '→ Nhấn "Create API key"\n'
                     "→ Chọn project Google Cloud (hoặc tạo mới — nhấn \"New project\")"),
                    ("Copy & Paste vào app",
                     "Copy key → Paste vào ô API Key của Gemini trong Hedra Studio\n"
                     "→ nhấn Lưu"),
                    ("Kiểm tra",
                     "Mở tab Chat → Kịch bản trong app để test Gemini đã hoạt động"),
                ],
            },
        }

        guide = _GUIDES.get(service)
        if not guide:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(guide["title"])
        dlg.setModal(True)
        dlg.setFixedWidth(500)
        dlg.setStyleSheet("QDialog{background:#f5f5f7;}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet(
            "QWidget{background:#ffffff;"
            "border:none;}"
        )
        hlay = QVBoxLayout(hdr)
        hlay.setContentsMargins(24, 20, 24, 16)
        hlay.setSpacing(4)
        ttl = QLabel(guide["title"])
        ttl.setStyleSheet(
            "QLabel{font-size:17px;font-weight:700;color:#1d1d1f;"
            "background:transparent;border:none;}"
        )
        sub = QLabel(guide["subtitle"])
        sub.setStyleSheet(
            "QLabel{font-size:12px;color:#6e6e73;"
            "background:transparent;border:none;}"
        )
        hlay.addWidget(ttl)
        hlay.addWidget(sub)
        root.addWidget(hdr)

        # ── Steps ─────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea{background:#f5f5f7;border:none;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:3px;}"
        )
        steps_w = QWidget()
        steps_w.setStyleSheet("QWidget{background:#f5f5f7;border:none;}")
        sv = QVBoxLayout(steps_w)
        sv.setContentsMargins(20, 16, 20, 16)
        sv.setSpacing(8)

        for idx, (step_title, step_desc) in enumerate(guide["steps"], 1):
            card = QWidget()
            card.setStyleSheet(
                "QWidget{background:#ffffff;border-radius:10px;border:none;}"
            )
            ch = QHBoxLayout(card)
            ch.setContentsMargins(14, 12, 14, 12)
            ch.setSpacing(12)

            # Number badge
            num = QLabel(str(idx))
            num.setFixedSize(28, 28)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(
                "QLabel{background:#0071e3;color:#ffffff;"
                "border-radius:14px;font-size:12px;font-weight:700;"
                "border:none;}"
            )
            ch.addWidget(num)
            ch.setAlignment(num, Qt.AlignmentFlag.AlignTop)

            # Text
            txt = QVBoxLayout()
            txt.setSpacing(3)
            t_lbl = QLabel(step_title)
            t_lbl.setStyleSheet(
                "QLabel{font-size:13px;font-weight:600;color:#1d1d1f;"
                "background:transparent;border:none;}"
            )
            d_lbl = QLabel(step_desc)
            d_lbl.setStyleSheet(
                "QLabel{font-size:12px;color:#6e6e73;"
                "background:transparent;border:none;}"
            )
            d_lbl.setWordWrap(True)
            txt.addWidget(t_lbl)
            txt.addWidget(d_lbl)
            ch.addLayout(txt, 1)
            sv.addWidget(card)

        sv.addStretch()
        scroll.setWidget(steps_w)
        scroll.setMinimumHeight(320)
        root.addWidget(scroll, 1)

        # ── Footer ────────────────────────────────────────────────
        ftr = QWidget()
        ftr.setStyleSheet(
            "QWidget{background:#ffffff;"
            "border:none;}"
        )
        flay = QHBoxLayout(ftr)
        flay.setContentsMargins(20, 12, 20, 12)
        flay.setSpacing(8)

        btn_open = QPushButton(guide["url_label"])
        btn_open.setFixedHeight(34)
        btn_open.setStyleSheet(
            "QPushButton{background:#0071e3;color:#ffffff;border:none;"
            "border-radius:8px;padding:0 16px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
        )
        _url = guide["url"]
        btn_open.clicked.connect(lambda: webbrowser.open(_url))

        btn_close = QPushButton("Đóng")
        btn_close.setFixedHeight(34)
        btn_close.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:8px;padding:0 20px;font-size:13px;color:#1d1d1f;}"
            "QPushButton:hover{background:#e5e5ea;}"
            "QPushButton:pressed{background:#d2d2d7;}"
        )
        btn_close.clicked.connect(dlg.accept)
        btn_open.setDefault(True)

        flay.addWidget(btn_open, 1)
        flay.addWidget(btn_close)
        root.addWidget(ftr)

        dlg.exec()

    # ── Tạo từng trang ────────────────────────────────────────────
    def _page_api(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 18, 20, 20)
        v.setSpacing(10)
        env = _read_env_local()
        el_saved = self.settings.get("el_api_keys", []) or []
        el_primary = (
            env.get("ELEVENLABS_API_KEY", "")
            or (el_saved[0] if el_saved else "")
        )
        api_values = {
            "genmax": env.get("GENMAX_API_KEY", "") or self.settings.get("genmax_api_key", ""),
            "ai33": env.get("AI33_API_KEY", ""),
            "elevenlabs": el_primary,
            "lucylab": env.get("VIETNAMESE_API_KEY", ""),
            "gemini": env.get("GEMINI_API_KEY", "") or self.settings.get("gemini_api_key", ""),
            "deepseek": env.get("DEEPSEEK_API_KEY", "") or self.settings.get("ds_api_key", ""),
            "claude": env.get("CLAUDE_API_KEY", "") or self.settings.get("claude_api_key", ""),
            "telegram_bot_token": self.settings.get("telegram_bot_token", ""),
            "telegram_chat_id": self.settings.get("telegram_chat_id", ""),
        }
        self._api_initial_keys = dict(api_values)

        def _api_guide_btn(service: str) -> QPushButton:
            btn = QPushButton("Hướng dẫn")
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            accent = "#0071e3"
            btn.setIcon(ui_icon("script", 12, accent))
            btn.setIconSize(icon_size(12))
            btn.setStyleSheet(
                f"QPushButton{{font-size:11px;font-weight:600;color:{accent};"
                "background:#edf5ff;border:none;border-radius:8px;padding:0 10px;}"
                "QPushButton:hover{background:#dfeeff;}"
                "QPushButton:pressed{background:#cfe3ff;}"
            )
            btn.clicked.connect(lambda: self._show_api_guide(service))
            return btn

        def _line_key(value: str, placeholder: str, password: bool = True) -> QLineEdit:
            w = QLineEdit(value)
            if password:
                w.setEchoMode(QLineEdit.EchoMode.Password)
            w.setPlaceholderText(placeholder)
            w.setStyleSheet(
                "QLineEdit{background:transparent;border:none;font-size:13px;}"
            )
            return w

        def _field_row(field: QWidget, service: str | None = None) -> QWidget:
            w = QWidget()
            w.setStyleSheet("background:transparent;border:none;")
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            h.addWidget(field, 1)
            status = QLabel()
            status.setFixedWidth(62)
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)

            def _value() -> str:
                if hasattr(field, "text"):
                    return field.text().strip()
                if hasattr(field, "toPlainText"):
                    return field.toPlainText().strip()
                return ""

            def _refresh_status():
                ok = bool(_value())
                status.setText("Đã có" if ok else "Thiếu")
                status.setStyleSheet(
                    "QLabel{font-size:11px;font-weight:600;border-radius:8px;"
                    f"padding:4px 6px;background:{'#eaf8ef' if ok else '#fff5e5'};"
                    f"color:{'#1f7a3b' if ok else '#9a5a00'};border:none;}}"
                )

            if hasattr(field, "textChanged"):
                field.textChanged.connect(lambda *_: _refresh_status())
            _refresh_status()
            h.addWidget(status)
            if service:
                h.addWidget(_api_guide_btn(service))
            return w

        v.addWidget(self._page_header(
            "api", "API",
            "Nhập key một lần — các trang khác chỉ chọn cách dùng, không nhập lại.",
        ))

        # ── NHÓM 1: Giọng đọc (TTS) ────────────────────────────────
        v.addWidget(self._section_label_with_icon("voices", "Giọng đọc (TTS)"))
        grp_tts, glay_tts = self._group()

        self.genmax_key = _line_key(api_values["genmax"], "sk_...")
        self._pv_gm_key = self.genmax_key
        self._row(glay_tts, "① GenMax", _field_row(self.genmax_key, "genmax"),
                  "Chủ đạo — TTS, STT, Auto Video.")

        self._pv_ai33_key = _line_key(api_values["ai33"], "sk_...")
        self._row(glay_tts, "② ai33", _field_row(self._pv_ai33_key, None),
                  "Fallback tự động khi GenMax lỗi.")

        self.el_keys = _line_key(api_values["elevenlabs"], "sk_...")
        self._pv_el_key = self.el_keys
        self._row(glay_tts, "③ ElevenLabs", _field_row(self.el_keys, "elevenlabs"),
                  "Fallback cuối — thư viện voice.", last=True)

        v.addWidget(grp_tts)

        # Dịch vụ legacy — ẩn mặc định
        _coll_tts, _coll_tts_inner = self._add_collapsible(v, "Dịch vụ TTS legacy")
        grp_extra_tts, glay_extra_tts = self._group()
        self._pv_ll_key = _line_key(api_values["lucylab"], "sk_live_...")
        self._row(glay_extra_tts, "LucyLab", _field_row(self._pv_ll_key, None),
                  "Provider tiếng Việt legacy.", last=True)
        _coll_tts_inner.addWidget(grp_extra_tts)

        # ── NHÓM 2: AI — Kịch bản & Enhance ───────────────────────
        v.addWidget(self._section_label_with_icon("spark", "AI — Kịch bản & Enhance"))
        grp_ai, glay_ai = self._group()

        self.claude_key = _line_key(api_values["claude"], "sk-ant-...")
        self._pv_claude_key = self.claude_key
        self._row(glay_ai, "① Claude", _field_row(self.claude_key, None),
                  "Chủ đạo — enhance & viết kịch bản (khuyến nghị).")

        self.ds_key = _line_key(api_values["deepseek"], "sk-...")
        self._pv_deepseek_key = self.ds_key
        self._row(glay_ai, "② DeepSeek", _field_row(self.ds_key, "deepseek"),
                  "Fallback tự động khi Claude lỗi.", last=True)

        v.addWidget(grp_ai)

        # Gemini — dùng riêng cho thumbnail / chat
        _coll_gem, _coll_gem_inner = self._add_collapsible(v, "AI bổ sung (Thumbnail & Chat)")
        grp_gem_extra, glay_gem_extra = self._group()
        self.gemini_key = _line_key(api_values["gemini"], "AIza...")
        self._pv_script_gemini_key = self.gemini_key
        self._row(glay_gem_extra, "Gemini", _field_row(self.gemini_key, "gemini"),
                  "Phân tích thumbnail, Chat AI. Miễn phí.", last=True)
        _coll_gem_inner.addWidget(grp_gem_extra)

        # ── NHÓM 3: Thông báo ───────────────────────────────────────
        v.addWidget(self._section_label_with_icon("message", "Thông báo"))
        grp_notif, glay_notif = self._group()

        self.telegram_bot_token = _line_key(api_values["telegram_bot_token"], "Bot token")
        self._row(glay_notif, "Telegram Bot", self.telegram_bot_token)

        self.telegram_chat_id = _line_key(api_values["telegram_chat_id"], "Chat ID", password=False)
        self._row(glay_notif, "Telegram Chat ID", self.telegram_chat_id,
                  "Nhận thông báo khi render xong.", last=True)

        v.addWidget(grp_notif)

        v.addStretch()
        return page

    def _page_prompts(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(0)

        outer.addWidget(self._page_header(
            "prompts", "Prompts",
            "Prompt hệ thống cho kịch bản Chat và TTS enhance.",
        ))

        _prompt_card_ss = (
            "QFrame{background:#f5f5f7;border:none;border-radius:12px;}"
        )
        _prompt_card_edit_ss = (
            "QFrame{background:#ffffff;border:2px solid #0071e3;border-radius:12px;}"
        )
        _prompt_text_ss = (
            "QTextEdit{font-size:13px;color:#1d1d1f;"
            "background:transparent;border:none;padding:16px 18px;"
            "selection-background-color:#bdd7ff;}"
        )
        _prompt_text_edit_ss = (
            "QTextEdit{font-size:13px;color:#1d1d1f;"
            "background:#ffffff;border:none;padding:16px 18px;"
            "selection-background-color:#bdd7ff;}"
        )
        _secondary_btn_ss = (
            "QPushButton{font-size:12px;font-weight:500;color:#6e6e73;"
            "background:#ffffff;border:none;border-radius:8px;padding:0 12px;}"
            "QPushButton:hover{background:#ececf0;color:#1d1d1f;}"
            "QPushButton:pressed{background:#dedee3;}"
        )
        _primary_btn_ss = (
            "QPushButton{font-size:12px;font-weight:600;color:#ffffff;"
            "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
        )
        _save_btn_ss = (
            "QPushButton{font-size:12px;font-weight:600;color:#ffffff;"
            "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
        )

        # ══ Sub-tab switcher ══════════════════════════════════════
        outer.addSpacing(4)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.setContentsMargins(0, 0, 0, 0)

        self._prompts_stacked = QStackedWidget()
        self._prompts_stacked.setStyleSheet("QStackedWidget{background:transparent;border:none;}")

        def _subtab_style(active: bool) -> str:
            if active:
                return ("QPushButton{background:#ffffff;color:#1d1d1f;"
                        "border:none;font-size:13px;font-weight:600;"
                        "padding:7px 18px;}")
            return ("QPushButton{background:transparent;color:#6e6e73;"
                    "border:none;font-size:13px;font-weight:500;"
                    "padding:7px 18px;}"
                    "QPushButton:hover{background:#e9e9ef;color:#1d1d1f;}")

        btn_tab_chat = QPushButton("Kịch bản")
        btn_tab_chat.setIcon(ui_icon("script", 14))
        btn_tab_chat.setIconSize(icon_size(14))
        btn_tab_chat.setFixedHeight(36)
        btn_tab_chat.setStyleSheet(
            _subtab_style(True) +
            "QPushButton{border-radius:8px;}"
        )
        btn_tab_tts = QPushButton("TTS Enhance")
        btn_tab_tts.setIcon(ui_icon("tts", 14))
        btn_tab_tts.setIconSize(icon_size(14))
        btn_tab_tts.setFixedHeight(36)
        btn_tab_tts.setStyleSheet(
            _subtab_style(False) +
            "QPushButton{border-radius:8px;}"
        )

        def _switch_subtab(idx: int):
            self._prompts_stacked.setCurrentIndex(idx)
            if idx == 0:
                btn_tab_chat.setStyleSheet(
                    _subtab_style(True) +
                    "QPushButton{border-radius:8px;}")
                btn_tab_tts.setStyleSheet(
                    _subtab_style(False) +
                    "QPushButton{border-radius:8px;}")
            else:
                btn_tab_chat.setStyleSheet(
                    _subtab_style(False) +
                    "QPushButton{border-radius:8px;}")
                btn_tab_tts.setStyleSheet(
                    _subtab_style(True) +
                    "QPushButton{border-radius:8px;}")

        btn_tab_chat.clicked.connect(lambda: _switch_subtab(0))
        btn_tab_tts.clicked.connect(lambda: _switch_subtab(1))
        tab_row.addWidget(btn_tab_chat)
        tab_row.addWidget(btn_tab_tts)
        tab_row.addStretch()
        tab_shell = QWidget()
        tab_shell.setStyleSheet("QWidget{background:#f2f2f7;border:none;border-radius:10px;}")
        tab_shell_lay = QHBoxLayout(tab_shell)
        tab_shell_lay.setContentsMargins(3, 3, 3, 3)
        tab_shell_lay.setSpacing(2)
        tab_shell_lay.addLayout(tab_row)
        tab_shell.setFixedHeight(42)
        tab_shell.setMaximumWidth(286)
        outer.addWidget(tab_shell)
        outer.addSpacing(12)

        # ──────────────────────────────────────────────────────────
        # PAGE 0: Chat → Kịch bản
        # ──────────────────────────────────────────────────────────
        page_chat = QWidget()
        page_chat.setStyleSheet("QWidget{background:transparent;border:none;}")
        vc = QVBoxLayout(page_chat)
        vc.setContentsMargins(0, 0, 0, 0)
        vc.setSpacing(0)

        saved_gp = self.settings.get("gemini_chat_prompt", "").strip()
        _gp_init  = saved_gp if saved_gp else GEMINI_CHAT_PROMPT

        gp_card = QFrame()
        gp_card.setStyleSheet(_prompt_card_ss)
        gp_card_v = QVBoxLayout(gp_card)
        gp_card_v.setContentsMargins(0, 0, 0, 0)
        gp_card_v.setSpacing(0)

        self.gemini_prompt = QTextEdit()
        self.gemini_prompt.setPlainText(_gp_init)
        self.gemini_prompt.setReadOnly(True)
        self.gemini_prompt.setMinimumHeight(320)
        self.gemini_prompt.setStyleSheet(_prompt_text_ss)
        gp_card_v.addWidget(self.gemini_prompt, 1)

        gp_div = QFrame(); gp_div.setFrameShape(QFrame.Shape.HLine)
        gp_div.setStyleSheet("QFrame{background:#e5e5ea;border:none;max-height:1px;margin:0;}")
        gp_card_v.addWidget(gp_div)

        gp_foot = QHBoxLayout()
        gp_foot.setContentsMargins(12, 8, 12, 8)
        gp_foot.setSpacing(8)
        btn_cancel_gp = QPushButton("Về mặc định")
        btn_cancel_gp.setFixedHeight(30)
        btn_cancel_gp.setStyleSheet(_secondary_btn_ss)
        gp_foot.addWidget(btn_cancel_gp)
        gp_foot.addStretch()
        btn_edit_gp = QPushButton("Chỉnh sửa")
        btn_edit_gp.setIcon(ui_icon("prompts", 14))
        btn_edit_gp.setIconSize(icon_size(14))
        btn_edit_gp.setFixedHeight(30)
        btn_edit_gp.setStyleSheet(_primary_btn_ss)
        gp_foot.addWidget(btn_edit_gp)
        gp_card_v.addLayout(gp_foot)
        vc.addWidget(gp_card)
        vc.addStretch()

        _gp_snapshot: list[str] = [_gp_init]   # snapshot trước khi edit

        def _toggle_edit_gp():
            if self.gemini_prompt.isReadOnly():
                # → Enter edit mode
                _gp_snapshot[0] = self.gemini_prompt.toPlainText()
                self.gemini_prompt.setReadOnly(False)
                self.gemini_prompt.setStyleSheet(_prompt_text_edit_ss)
                gp_card.setStyleSheet(_prompt_card_edit_ss)
                btn_edit_gp.setText("Lưu")
                btn_edit_gp.setStyleSheet(_save_btn_ss)
                btn_cancel_gp.setText("Hủy")
                self.gemini_prompt.setFocus()
            else:
                # → Save
                gp_text = self.gemini_prompt.toPlainText().strip()
                self.settings["gemini_chat_prompt"] = "" if gp_text == GEMINI_CHAT_PROMPT.strip() else gp_text
                save_settings(self.settings)
                self.gemini_prompt.setReadOnly(True)
                self.gemini_prompt.setStyleSheet(_prompt_text_ss)
                gp_card.setStyleSheet(_prompt_card_ss)
                btn_edit_gp.setText("Chỉnh sửa")
                btn_edit_gp.setStyleSheet(_primary_btn_ss)
                btn_cancel_gp.setText("Về mặc định")

        def _cancel_or_reset_gp():
            if not self.gemini_prompt.isReadOnly():
                # Đang edit → Hủy
                self.gemini_prompt.setPlainText(_gp_snapshot[0])
                self.gemini_prompt.setReadOnly(True)
                self.gemini_prompt.setStyleSheet(_prompt_text_ss)
                gp_card.setStyleSheet(_prompt_card_ss)
                btn_edit_gp.setText("Chỉnh sửa")
                btn_edit_gp.setStyleSheet(_primary_btn_ss)
                btn_cancel_gp.setText("Về mặc định")
            else:
                # Không edit → reset default
                self.gemini_prompt.setPlainText(GEMINI_CHAT_PROMPT)
                self.settings["gemini_chat_prompt"] = ""
                save_settings(self.settings)

        btn_edit_gp.clicked.connect(_toggle_edit_gp)
        btn_cancel_gp.clicked.connect(_cancel_or_reset_gp)

        # ──────────────────────────────────────────────────────────
        # PAGE 1: TTS — Enhance
        # ──────────────────────────────────────────────────────────
        page_tts = QWidget()
        page_tts.setStyleSheet("QWidget{background:transparent;border:none;}")
        vt = QVBoxLayout(page_tts)
        vt.setContentsMargins(0, 0, 0, 0)
        vt.setSpacing(0)

        # ── Enhance card: left style tabs + right prompt ───────────
        ep_card = QFrame()
        ep_card.setStyleSheet(_prompt_card_ss)
        ep_card_h = QVBoxLayout(ep_card)
        ep_card_h.setContentsMargins(0, 0, 0, 0)
        ep_card_h.setSpacing(0)

        # Style presets — Apple-style horizontal pills
        ep_tab_col = QFrame()
        ep_tab_col.setStyleSheet(
            "QFrame{background:transparent;border:none;}"
        )
        ep_tab_v = QHBoxLayout(ep_tab_col)
        ep_tab_v.setContentsMargins(12, 12, 12, 8)
        ep_tab_v.setSpacing(6)
        self._ep_tab_layout = ep_tab_v   # lưu để _refresh_custom_styles dùng

        self._ep_style_tabs: dict[str, QPushButton] = {}
        self._ep_style_data = self._prompt_style_data()
        self._ep_prompts_map = {
            name: item["prompt"]
            for name, item in self._ep_style_data.items()
        }
        ep_temp_map = {
            name: item["temperature"]
            for name, item in self._ep_style_data.items()
        }

        def _ep_tab_style(active: bool) -> str:
            if active:
                return ("QPushButton{background:#ffffff;color:#0071e3;"
                        "border:none;border-radius:9px;"
                        "font-size:12px;font-weight:600;padding:6px 10px;}")
            return ("QPushButton{background:transparent;color:#3c3c43;"
                    "border:none;border-radius:9px;"
                    "font-size:12px;font-weight:500;padding:6px 10px;}"
                    "QPushButton:hover{background:#e9e9ef;}")

        _saved_ep   = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
        _active_ep  = (
            self.settings.get("enhance_style_name", "")
            if self.settings.get("enhance_style_name", "") in self._ep_prompts_map
            else list(self._ep_prompts_map.keys())[0]
        )
        if not self.settings.get("enhance_style_name", ""):
            for _n, _t in self._ep_prompts_map.items():
                if _t.strip() == _saved_ep.strip():
                    _active_ep = _n
                    break
        self._ep_active_style = _active_ep

        def _switch_ep_tab(name: str):
            for n, b in self._ep_style_tabs.items():
                b.setStyleSheet(_ep_tab_style(n == name))
            self.prompt.setPlainText(self._ep_prompts_map[name])
            self._ep_active_style = name
            self.settings["enhance_style_name"] = name
            # Sync theo setup đã lưu của chính preset đó.
            if hasattr(self, "_settings_temp_slider"):
                t = ep_temp_map.get(name, self.settings.get("enhance_style_temperature", 0.3))
                self._settings_temp_slider.setValue(int(t * 100))
                if hasattr(self, "_settings_temp_val_lbl"):
                    self._settings_temp_val_lbl.setText(f"{t:.2f}")
                self.settings["enhance_style_temperature"] = t
                self.settings["enhance_style_creative"] = t >= 0.5

        for name, prompt_text in self._ep_prompts_map.items():
            tb = QPushButton(name)
            tb.setMinimumHeight(30)
            tb.setStyleSheet(_ep_tab_style(name == _active_ep))
            tb.clicked.connect(lambda _, n=name: _switch_ep_tab(n))
            ep_tab_v.addWidget(tb)
            self._ep_style_tabs[name] = tb
        btn_add_pill = QPushButton("+")
        btn_add_pill.setFixedHeight(30)
        btn_add_pill.setStyleSheet(
            "QPushButton{font-size:13px;font-weight:500;color:#0071e3;"
            "background:transparent;border:none;border-radius:9px;padding:6px 10px;}"
            "QPushButton:hover{background:#dfeeff;}"
            "QPushButton:pressed{background:#cfe3ff;}"
        )
        btn_add_pill.clicked.connect(self._add_custom_style)
        ep_tab_v.addWidget(btn_add_pill)
        ep_tab_v.addStretch()
        ep_card_h.addWidget(ep_tab_col)

        # Right: prompt + footer
        ep_right = QVBoxLayout()
        ep_right.setContentsMargins(0, 0, 0, 0)
        ep_right.setSpacing(0)

        self.prompt = QTextEdit()
        self.prompt.setPlainText(self._ep_prompts_map.get(_active_ep, _saved_ep))
        self.prompt.setReadOnly(True)
        self.prompt.setMinimumHeight(320)
        self.prompt.setStyleSheet(_prompt_text_ss)
        ep_right.addWidget(self.prompt, 1)

        ep_div2 = QFrame(); ep_div2.setFrameShape(QFrame.Shape.HLine)
        ep_div2.setStyleSheet("QFrame{background:#e5e5ea;border:none;max-height:1px;margin:0;}")
        ep_right.addWidget(ep_div2)

        ep_foot = QHBoxLayout()
        ep_foot.setContentsMargins(12, 8, 12, 8)
        ep_foot.setSpacing(8)
        btn_cancel_ep = QPushButton("Về mặc định")
        btn_cancel_ep.setFixedHeight(30)
        btn_cancel_ep.setStyleSheet(_secondary_btn_ss)
        ep_foot.addWidget(btn_cancel_ep)
        ep_foot.addStretch()
        btn_edit_ep = QPushButton("Chỉnh sửa")
        btn_edit_ep.setIcon(ui_icon("prompts", 14))
        btn_edit_ep.setIconSize(icon_size(14))
        btn_edit_ep.setFixedHeight(30)
        btn_edit_ep.setStyleSheet(_primary_btn_ss)
        ep_foot.addWidget(btn_edit_ep)
        ep_right.addLayout(ep_foot)
        ep_card_h.addLayout(ep_right, 1)
        vt.addWidget(ep_card, 1)  # stretch → giãn theo cửa sổ

        _ep_snapshot: list[str] = [_saved_ep]

        def _toggle_edit_ep():
            if self.prompt.isReadOnly():
                _ep_snapshot[0] = self.prompt.toPlainText()
                self.prompt.setReadOnly(False)
                self.prompt.setStyleSheet(_prompt_text_edit_ss)
                ep_card.setStyleSheet(_prompt_card_edit_ss)
                btn_edit_ep.setText("Lưu")
                btn_edit_ep.setStyleSheet(_save_btn_ss)
                btn_cancel_ep.setText("Hủy")
                self.prompt.setFocus()
            else:
                self._commit_current_prompt_style()
                save_settings(self.settings)
                self.prompt.setReadOnly(True)
                self.prompt.setStyleSheet(_prompt_text_ss)
                ep_card.setStyleSheet(_prompt_card_ss)
                btn_edit_ep.setText("Chỉnh sửa")
                btn_edit_ep.setStyleSheet(_primary_btn_ss)
                btn_cancel_ep.setText("Về mặc định")

        def _cancel_or_reset_ep():
            if not self.prompt.isReadOnly():
                self.prompt.setPlainText(_ep_snapshot[0])
                self.prompt.setReadOnly(True)
                self.prompt.setStyleSheet(_prompt_text_ss)
                ep_card.setStyleSheet(_prompt_card_ss)
                btn_edit_ep.setText("Chỉnh sửa")
                btn_edit_ep.setStyleSheet(_primary_btn_ss)
                btn_cancel_ep.setText("Về mặc định")
            else:
                self.prompt.setPlainText(DEFAULT_PROMPT)
                self._ep_active_style = "Nghiêm túc"
                self.settings["enhance_prompt"] = DEFAULT_PROMPT
                self.settings["enhance_style_name"] = "Nghiêm túc"
                self.settings["enhance_style_temperature"] = 0.3
                self.settings["enhance_style_creative"] = False
                overrides = self.settings.get("prompt_preset_overrides", {})
                if isinstance(overrides, dict):
                    overrides.pop("Nghiêm túc", None)
                save_settings(self.settings)

        btn_edit_ep.clicked.connect(_toggle_edit_ep)
        btn_cancel_ep.clicked.connect(_cancel_or_reset_ep)

        # ── Mức độ sáng tạo — group card ──────────────────────────
        vt.addSpacing(12)
        vt.addWidget(self._section_label_with_icon("spark", "Mức độ sáng tạo"))
        grp_temp, glay_temp = self._group()

        temp_slider_w = QWidget()
        temp_slider_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        temp_h = QHBoxLayout(temp_slider_w)
        temp_h.setContentsMargins(0, 0, 0, 0)
        temp_h.setSpacing(10)
        lbl_calm = QLabel("Chính xác")
        lbl_calm.setStyleSheet("QLabel{font-size:11px;color:#6e6e73;background:transparent;border:none;}")
        temp_h.addWidget(lbl_calm)
        self._settings_temp_slider = QSlider(Qt.Orientation.Horizontal)
        self._settings_temp_slider.setRange(0, 100)
        # Khi mở lại Settings, luôn ưu tiên giá trị user đã lưu.
        # Preset chỉ set default lúc user bấm đổi style, không được ghi đè
        # slider đã chỉnh thủ công.
        _saved_temp = ep_temp_map.get(_active_ep, self.settings.get("enhance_style_temperature", None))
        if _saved_temp is None or str(_saved_temp).strip() == "":
            _cur_temp = float(ep_temp_map.get(_active_ep, 0.3))
        else:
            _cur_temp = float(_saved_temp)
        self._settings_temp_slider.setValue(int(_cur_temp * 100))
        self._settings_temp_slider.setFixedHeight(20)
        self._settings_temp_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#e5e5ea;border-radius:2px;}"
            "QSlider::handle:horizontal{width:18px;height:18px;margin:-7px 0;"
            "background:#0071e3;border-radius:9px;border:none;}"
            "QSlider::sub-page:horizontal{background:#0071e3;border-radius:2px;}"
        )
        temp_h.addWidget(self._settings_temp_slider, 1)
        lbl_creative = QLabel("Sáng tạo")
        lbl_creative.setStyleSheet("QLabel{font-size:11px;color:#6e6e73;background:transparent;border:none;}")
        temp_h.addWidget(lbl_creative)
        self._settings_temp_val_lbl = QLabel(f"{_cur_temp:.2f}")
        self._settings_temp_val_lbl.setFixedWidth(32)
        self._settings_temp_val_lbl.setStyleSheet(
            "QLabel{font-size:12px;font-weight:600;color:#0071e3;"
            "background:transparent;border:none;}"
        )
        temp_h.addWidget(self._settings_temp_val_lbl)
        self._row(glay_temp, "Mức độ", temp_slider_w, last=True)
        vt.addWidget(grp_temp)

        def _on_settings_temp(val: int):
            t = val / 100.0
            self._settings_temp_val_lbl.setText(f"{t:.2f}")
            self.settings["enhance_style_temperature"] = t
            self.settings["enhance_style_creative"] = t >= 0.5
        self._settings_temp_slider.valueChanged.connect(_on_settings_temp)

        # ── Wire stacked widget ────────────────────────────────────
        self._prompts_stacked.addWidget(page_chat)   # index 0
        self._prompts_stacked.addWidget(page_tts)    # index 1
        outer.addWidget(self._prompts_stacked, 1)

        return page

    def _refresh_custom_styles(self):
        """Rebuild sidebar tabs — built-in + custom styles."""
        if not hasattr(self, "_ep_tab_layout") or not hasattr(self, "_ep_prompts_map"):
            return
        layout = self._ep_tab_layout

        # Xoá tabs cũ
        for btn in list(self._ep_style_tabs.values()):
            try:
                btn.deleteLater()
            except RuntimeError:
                pass
        self._ep_style_tabs.clear()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._ep_style_data = self._prompt_style_data()
        self._ep_prompts_map = {
            name: item["prompt"]
            for name, item in self._ep_style_data.items()
        }
        ep_temp_map = {
            name: item["temperature"]
            for name, item in self._ep_style_data.items()
        }

        # Tìm tab đang active
        _saved = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
        _active = (
            self.settings.get("enhance_style_name", "")
            if self.settings.get("enhance_style_name", "") in self._ep_prompts_map
            else list(self._ep_prompts_map.keys())[0]
        )
        if not self.settings.get("enhance_style_name", ""):
            for n, t in self._ep_prompts_map.items():
                if t.strip() == _saved.strip():
                    _active = n
                    break
        self._ep_active_style = _active

        # Style helper
        def _tab_style(active: bool) -> str:
            if active:
                return ("QPushButton{background:#ffffff;color:#0071e3;"
                        "border:1px solid #d2d2d7;border-radius:6px;"
                        "font-size:11px;font-weight:600;padding:5px 6px;"
                        "text-align:left;}")
            return ("QPushButton{background:transparent;color:#1d1d1f;"
                    "border:none;border-radius:6px;"
                    "font-size:11px;padding:5px 6px;text-align:left;}"
                    "QPushButton:hover{background:#ebebf0;}")

        def _switch(name: str):
            for n, b in self._ep_style_tabs.items():
                b.setStyleSheet(_tab_style(n == name))
            self.prompt.setPlainText(self._ep_prompts_map[name])
            self._ep_active_style = name
            self.settings["enhance_style_name"] = name
            if hasattr(self, "_settings_temp_slider"):
                t = ep_temp_map.get(name, self.settings.get("enhance_style_temperature", 0.3))
                self._settings_temp_slider.setValue(int(t * 100))
                if hasattr(self, "_settings_temp_val_lbl"):
                    self._settings_temp_val_lbl.setText(f"{t:.2f}")
                self.settings["enhance_style_temperature"] = t
                self.settings["enhance_style_creative"] = t >= 0.5

        # Thêm tabs mới
        for name, prompt_text in self._ep_prompts_map.items():
            tb = QPushButton(name)
            tb.setMinimumHeight(28)
            tb.setStyleSheet(_tab_style(name == _active))
            tb.clicked.connect(lambda _, n=name: _switch(n))
            layout.addWidget(tb)
            self._ep_style_tabs[name] = tb
        btn_add_pill = QPushButton("+")
        btn_add_pill.setFixedHeight(30)
        btn_add_pill.setStyleSheet(
            "QPushButton{font-size:13px;font-weight:500;color:#0071e3;"
            "background:transparent;border:none;border-radius:9px;padding:6px 10px;}"
            "QPushButton:hover{background:#dfeeff;}"
            "QPushButton:pressed{background:#cfe3ff;}"
        )
        btn_add_pill.clicked.connect(self._add_custom_style)
        layout.addWidget(btn_add_pill)
        layout.addStretch()

    def _refresh_custom_style_manager(self):
        if not hasattr(self, "_custom_style_list_layout"):
            return
        layout = self._custom_style_list_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        styles = self.settings.get("custom_styles", [])
        if not styles:
            empty = QLabel("Chưa có prompt tùy chỉnh")
            empty.setStyleSheet(
                "QLabel{font-size:13px;color:#8e8e93;background:transparent;border:none;"
                "padding:14px 18px;}"
            )
            layout.addWidget(empty)
            return

        for idx, style in enumerate(styles):
            row = QWidget()
            row.setStyleSheet("QWidget{background:transparent;border:none;}")
            row.setMinimumHeight(44)
            h = QHBoxLayout(row)
            h.setContentsMargins(14, 8, 14, 8)
            h.setSpacing(8)

            label = QLabel(f"{style.get('icon', '')}  {style.get('name', '').strip()}")
            label.setStyleSheet(
                "QLabel{font-size:13px;color:#1d1d1f;background:transparent;border:none;}"
            )
            h.addWidget(label, 1)

            btn_edit = QPushButton("Sửa")
            btn_edit.setFixedHeight(28)
            btn_edit.setStyleSheet(
                "QPushButton{font-size:12px;background:#f5f5f7;border:1px solid #d2d2d7;"
                "border-radius:6px;padding:0 12px;color:#1d1d1f;}"
                "QPushButton:hover{background:#e5e5ea;}"
            )
            btn_edit.clicked.connect(lambda _, i=idx: self._edit_custom_style(i))
            h.addWidget(btn_edit)

            btn_del = QPushButton("Xóa")
            btn_del.setFixedHeight(28)
            btn_del.setStyleSheet(
                "QPushButton{font-size:12px;background:#fff1f2;border:1px solid #fecdd3;"
                "border-radius:6px;padding:0 12px;color:#be123c;}"
                "QPushButton:hover{background:#ffe4e6;}"
            )
            btn_del.clicked.connect(lambda _, i=idx: self._delete_custom_style(i))
            h.addWidget(btn_del)

            layout.addWidget(row)
            # Separator between rows (except last)
            if idx < len(styles) - 1:
                sep_wrap = QWidget()
                sep_wrap.setFixedHeight(1)
                sep_wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
                sep_h = QHBoxLayout(sep_wrap)
                sep_h.setContentsMargins(14, 0, 14, 0)
                sep_h.setSpacing(0)
                sep = QWidget()
                sep.setFixedHeight(1)
                sep.setStyleSheet("QWidget{background:#e7e7ea;border:none;}")
                sep_h.addWidget(sep)
                layout.addWidget(sep_wrap)

    def _expand_prompt_dialog(self, title: str, text_edit: QTextEdit):
        """Mở dialog editor lớn để chỉnh sửa prompt thoải mái."""
        from PyQt6.QtWidgets import QPlainTextEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(700, 540)
        dlg.setStyleSheet("QDialog{background:#f5f5f7;}")

        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(12)

        # Hint bar
        hint = QLabel("💡  Chỉnh sửa xong nhấn Lưu — thay đổi sẽ cập nhật vào Settings")
        hint.setStyleSheet(
            "QLabel{font-size:11px;color:#6e6e73;background:#ebebf0;"
            "border-radius:6px;padding:6px 10px;border:none;}"
        )
        v.addWidget(hint)

        editor = QPlainTextEdit()
        editor.setPlainText(text_edit.toPlainText())
        editor.setStyleSheet(
            "QPlainTextEdit{font-family:'SF Mono',Menlo,monospace;font-size:12px;"
            "background:white;border:1px solid #d2d2d7;border-radius:8px;"
            "padding:12px;color:#1d1d1f;}"
            "QPlainTextEdit:focus{border-color:#0071e3;}"
        )
        v.addWidget(editor, 1)

        # Char count
        char_lbl = QLabel(f"{len(text_edit.toPlainText())} ký tự")
        char_lbl.setStyleSheet("QLabel{font-size:11px;color:#aeaeb2;background:transparent;border:none;}")
        char_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        editor.textChanged.connect(
            lambda: char_lbl.setText(f"{len(editor.toPlainText())} ký tự")
        )
        v.addWidget(char_lbl)

        # Buttons
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;border-radius:8px;"
            "padding:0 16px;font-size:13px;color:#1d1d1f;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        btn_cancel.clicked.connect(dlg.reject)
        btn_save = QPushButton("Lưu")
        btn_save.setFixedHeight(32)
        btn_save.setDefault(True)
        btn_save.setStyleSheet(
            "QPushButton{background:#0071e3;border:none;border-radius:8px;"
            "padding:0 20px;font-size:13px;font-weight:600;color:white;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#006edb;}"
        )
        btn_save.clicked.connect(dlg.accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)
        v.addLayout(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            text_edit.setPlainText(editor.toPlainText())

    def _add_custom_style(self):
        dlg = AddStyleDialog(self, ds_api_key=self.settings.get("ds_api_key", ""), gemini_api_key=self.settings.get("gemini_api_key", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            styles = self.settings.setdefault("custom_styles", [])
            styles.append(result)
            self.settings["enhance_prompt"] = result["prompt"]
            self.settings["enhance_style_name"] = (
                f"{result.get('icon', '')}  {result.get('name', '')}"
                if result.get("icon") else result.get("name", "")
            )
            self.settings["enhance_style_temperature"] = result.get("temperature", 0.3)
            self.settings["enhance_style_creative"] = result.get("creative", False)
            self.prompt.setPlainText(result["prompt"])
            self._refresh_custom_styles()
            self._refresh_custom_style_manager()
            save_settings(self.settings)

    def _edit_custom_style(self, idx: int):
        styles = self.settings.get("custom_styles", [])
        if idx >= len(styles):
            return
        old_prompt = styles[idx].get("prompt", "")
        dlg = AddStyleDialog(self, existing=styles[idx],
                             ds_api_key=self.settings.get("ds_api_key", ""),
                             gemini_api_key=self.settings.get("gemini_api_key", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            styles[idx] = result
            current_matches = (
                self.settings.get("enhance_prompt", "").strip() == old_prompt.strip()
                or self.prompt.toPlainText().strip() == old_prompt.strip()
            )
            if current_matches:
                self.settings["enhance_prompt"] = result["prompt"]
                self.settings["enhance_style_name"] = (
                    f"{result.get('icon', '')}  {result.get('name', '')}"
                    if result.get("icon") else result.get("name", "")
                )
                self.settings["enhance_style_temperature"] = result.get("temperature", 0.3)
                self.settings["enhance_style_creative"] = result.get("creative", False)
                self.prompt.setPlainText(result["prompt"])
            self._refresh_custom_styles()
            self._refresh_custom_style_manager()
            save_settings(self.settings)

    def _delete_custom_style(self, idx: int):
        styles = self.settings.get("custom_styles", [])
        if idx < len(styles):
            style = styles[idx]
            reply = QMessageBox.question(
                self,
                "Xóa prompt",
                f"Xóa prompt \"{style.get('name', '')}\"?",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            removed = styles.pop(idx)
            current_matches = (
                self.settings.get("enhance_prompt", "").strip() == removed.get("prompt", "").strip()
                or self.prompt.toPlainText().strip() == removed.get("prompt", "").strip()
            )
            if current_matches:
                self.settings["enhance_prompt"] = DEFAULT_PROMPT
                self.settings["enhance_style_name"] = "Nghiêm túc"
                self.settings["enhance_style_temperature"] = 0.3
                self.settings["enhance_style_creative"] = False
                self.prompt.setPlainText(DEFAULT_PROMPT)
            self._refresh_custom_styles()
            self._refresh_custom_style_manager()
            save_settings(self.settings)

    def _page_voices(self) -> QWidget:
        """Trang giọng đọc — quản lý yêu thích thủ công."""
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 16, 20, 20)
        v.setSpacing(0)

        v.addWidget(self._page_header(
            "voices", "Giọng đọc",
            "Thêm giọng vào danh sách yêu thích. Mỗi tool chọn giọng riêng trong tab của nó.",
        ))
        v.addSpacing(12)

        # ── Card ──────────────────────────────────────────────────
        card, card_lay = self._group()

        # Header row: title + add button
        hdr_w = QWidget()
        hdr_w.setStyleSheet("background:transparent;border:none;")
        hdr_h = QHBoxLayout(hdr_w)
        hdr_h.setContentsMargins(12, 10, 12, 8)
        hdr_h.setSpacing(8)
        hdr_lbl = QLabel("Giọng yêu thích")
        hdr_lbl.setStyleSheet(
            "QLabel{font-size:13px;font-weight:600;color:#1d1d1f;"
            "background:transparent;border:none;}"
        )
        hdr_h.addWidget(hdr_lbl)
        hdr_h.addStretch()
        btn_add = QPushButton("＋  Thêm giọng")
        btn_add.setFixedHeight(28)
        btn_add.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;border-radius:8px;"
            "font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bbf;}"
        )
        btn_add.clicked.connect(self._v_toggle_add_form)
        hdr_h.addWidget(btn_add)
        card_lay.addWidget(hdr_w)

        # Separator
        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setStyleSheet("QFrame{color:#e5e5ea;background:#e5e5ea;max-height:1px;}")
        card_lay.addWidget(sep0)

        # ── Add form (ẩn mặc định) ─────────────────────────────────
        self._v_add_form = QWidget()
        self._v_add_form.setStyleSheet(
            "QWidget{background:#f9f9fb;border:none;}"
        )
        form_v = QVBoxLayout(self._v_add_form)
        form_v.setContentsMargins(14, 12, 14, 12)
        form_v.setSpacing(8)

        def _field(placeholder: str, mono: bool = False) -> QLineEdit:
            f = QLineEdit()
            f.setPlaceholderText(placeholder)
            f.setFixedHeight(30)
            ff = "font-family:monospace;" if mono else ""
            f.setStyleSheet(
                f"QLineEdit{{background:white;border:1px solid #d2d2d7;border-radius:8px;"
                f"padding:0 10px;font-size:13px;color:#1d1d1f;{ff}}}"
                "QLineEdit:focus{border-color:#0071e3;}"
            )
            return f

        lbl_style = ("QLabel{font-size:12px;color:#3c3c43;"
                     "background:transparent;border:none;}")

        row1 = QHBoxLayout(); row1.setSpacing(8)
        l1 = QLabel("Tên giọng:"); l1.setFixedWidth(80); l1.setStyleSheet(lbl_style)
        self._v_inp_name = _field("Adam - Dominant, Firm")
        row1.addWidget(l1); row1.addWidget(self._v_inp_name)
        form_v.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(8)
        l2 = QLabel("Voice ID:"); l2.setFixedWidth(80); l2.setStyleSheet(lbl_style)
        self._v_inp_id = _field("pNInz6obpgDQGcFmaJgB", mono=True)
        self._v_btn_check = QPushButton("🔍 Kiểm tra")
        self._v_btn_check.setFixedHeight(30)
        self._v_btn_check.setStyleSheet(
            "QPushButton{background:#ebebf0;color:#3c3c43;border:none;border-radius:8px;"
            "font-size:12px;padding:0 12px;white-space:nowrap;}"
            "QPushButton:hover{background:#dcdce0;}"
            "QPushButton:disabled{color:#aeaeb2;}"
        )
        self._v_btn_check.clicked.connect(self._v_check_voice)
        row2.addWidget(l2); row2.addWidget(self._v_inp_id); row2.addWidget(self._v_btn_check)
        form_v.addLayout(row2)

        # Status sau khi check
        self._v_check_status = QLabel("")
        self._v_check_status.setVisible(False)
        self._v_check_status.setWordWrap(True)
        self._v_check_status.setStyleSheet(
            "QLabel{font-size:12px;padding:4px 0 0 88px;background:transparent;border:none;}"
        )
        form_v.addWidget(self._v_check_status)

        row3 = QHBoxLayout(); row3.setSpacing(8)
        l3 = QLabel("Ngôn ngữ:"); l3.setFixedWidth(80); l3.setStyleSheet(lbl_style)
        self._v_inp_lang = QComboBox()
        self._v_inp_lang.setFixedHeight(_LANG_BADGE_HEIGHT)
        self._v_inp_lang.setFixedWidth(_LANG_CONTROL_WIDTH)
        self._v_inp_lang.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._v_inp_lang.setStyleSheet(_LANG_COMBO_SS)
        for code, label in _VOICE_LANG_OPTIONS:
            self._v_inp_lang.addItem(label, code)
        # Default: Vietnamese (index 1)
        self._v_inp_lang.setCurrentIndex(1)
        # Badge hiển thị khi giọng chỉ hỗ trợ 1 ngôn ngữ (mono) — ẩn mặc định
        self._v_lang_badge = QLabel()
        self._v_lang_badge.setFixedHeight(_LANG_BADGE_HEIGHT)
        self._v_lang_badge.setFixedWidth(_LANG_CONTROL_WIDTH)
        self._v_lang_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._v_lang_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._v_lang_badge.setStyleSheet(_LANG_BADGE_SS
        )
        self._v_lang_badge.setVisible(False)
        row3.addWidget(l3)
        row3.addWidget(self._v_inp_lang)
        row3.addWidget(self._v_lang_badge)
        form_v.addLayout(row3)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(28)
        btn_cancel.setStyleSheet(
            "QPushButton{background:#ebebf0;color:#3c3c43;border:none;border-radius:8px;"
            "font-size:12px;padding:0 16px;}"
            "QPushButton:hover{background:#e0e0e6;}"
        )
        btn_cancel.clicked.connect(lambda: self._v_add_form.setVisible(False))
        btn_ok = QPushButton("Thêm")
        btn_ok.setFixedHeight(28)
        btn_ok.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;border-radius:8px;"
            "font-size:12px;font-weight:600;padding:0 16px;}"
            "QPushButton:hover{background:#0077ed;}"
        )
        btn_ok.clicked.connect(self._v_add_voice)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_ok)
        form_v.addLayout(btn_row)

        self._v_add_form.setVisible(False)
        card_lay.addWidget(self._v_add_form)

        # ── Favorites list ─────────────────────────────────────────
        self._v_fav_list_w = QWidget()
        self._v_fav_list_w.setStyleSheet("background:transparent;border:none;")
        self._v_fav_list_v = QVBoxLayout(self._v_fav_list_w)
        self._v_fav_list_v.setContentsMargins(0, 0, 0, 0)
        self._v_fav_list_v.setSpacing(0)
        card_lay.addWidget(self._v_fav_list_w)

        self._v_rebuild_fav_list()

        v.addWidget(card)
        v.addStretch()
        return page

    # ── Favorites management helpers ───────────────────────────────

    def _v_toggle_add_form(self):
        visible = self._v_add_form.isVisible()
        self._v_add_form.setVisible(not visible)
        if not visible:
            self._v_inp_name.clear()
            self._v_inp_id.clear()
            self._v_inp_lang.clear()
            for code, label in _VOICE_LANG_OPTIONS:
                self._v_inp_lang.addItem(label, code)
            self._v_inp_lang.setCurrentIndex(1)  # default Vietnamese
            self._v_inp_lang.setVisible(True)     # reset về full combo
            self._v_lang_badge.setVisible(False)
            self._v_voice_is_multilingual = True
            self._v_checked_langs = None
            self._v_check_status.setVisible(False)
            self._v_btn_check.setEnabled(True)
            self._v_inp_name.setFocus()

    def _v_check_voice(self):
        vid = self._v_inp_id.text().strip()
        if not vid:
            self._v_check_status.setText("⚠️ Nhập Voice ID trước")
            self._v_check_status.setStyleSheet(
                "QLabel{font-size:12px;color:#ff9500;padding:4px 0 0 88px;"
                "background:transparent;border:none;}"
            )
            self._v_check_status.setVisible(True)
            return
        api_keys = self.settings.get("el_api_keys", [])
        self._v_btn_check.setEnabled(False)
        self._v_check_status.setText("⏳ Đang kiểm tra…")
        self._v_check_status.setStyleSheet(
            "QLabel{font-size:12px;color:#8e8e93;padding:4px 0 0 88px;"
            "background:transparent;border:none;}"
        )
        self._v_check_status.setVisible(True)
        self._v_checker = _VoiceCheckerWorker(vid, api_keys)
        self._v_checker.done.connect(self._v_on_voice_checked)
        self._v_checker.error.connect(self._v_on_voice_check_error)
        self._v_checker.start()

    def _v_on_voice_checked(self, result: dict):
        self._v_btn_check.setEnabled(True)
        name  = result.get("name", "")
        langs = result.get("langs", [])   # list[str] — xem _VoiceCheckerWorker
        # Lưu lại để dùng khi save
        self._v_checked_langs = langs
        self._v_voice_is_multilingual = (len(langs) != 1)

        # Auto-fill name
        if name:
            self._v_inp_name.setText(name)

        lang_label_map = {code: lbl for code, lbl in _VOICE_LANG_OPTIONS}

        if len(langs) == 0:
            # Fully multilingual → giữ full combo, auto = index 0
            self._v_inp_lang.setVisible(True)
            self._v_lang_badge.setVisible(False)
            self._v_inp_lang.setCurrentIndex(0)  # "— Tự động"
            note = "🌐 Đa ngôn ngữ (~29 thứ tiếng) — chọn ngôn ngữ mặc định nếu cần"

        elif len(langs) == 1:
            # Mono → ẩn combo, hiện badge
            lang = langs[0]
            # Vẫn set combo để _v_add_voice đọc được
            for i in range(self._v_inp_lang.count()):
                if self._v_inp_lang.itemData(i) == lang:
                    self._v_inp_lang.setCurrentIndex(i)
                    break
            badge_text = lang_label_map.get(lang, lang)
            self._v_lang_badge.setText(badge_text)
            self._v_inp_lang.setVisible(False)
            self._v_lang_badge.setVisible(True)
            note = f"✅ Giọng hỗ trợ: {badge_text}"

        else:
            # Một số ngôn ngữ cụ thể → lọc combo chỉ hiện các ngôn ngữ đó
            self._v_inp_lang.setVisible(True)
            self._v_lang_badge.setVisible(False)
            self._v_inp_lang.clear()
            self._v_inp_lang.addItem("— Tự động", "")
            for code in langs:
                lbl = lang_label_map.get(code, code)
                self._v_inp_lang.addItem(lbl, code)
            self._v_inp_lang.setCurrentIndex(0)
            lang_names = " / ".join(lang_label_map.get(c, c) for c in langs)
            note = f"✅ Giọng hỗ trợ: {lang_names}"

        self._v_check_status.setText(note)
        self._v_check_status.setStyleSheet(
            "QLabel{font-size:12px;color:#34c759;padding:4px 0 0 88px;"
            "background:transparent;border:none;}"
        )

    def _v_on_voice_check_error(self, msg: str):
        self._v_btn_check.setEnabled(True)
        if msg == "no_key":
            text = "⚠️ Chưa có ElevenLabs API key — thêm key vào tab API"
            color = "#ff9500"
        elif msg == "invalid_key":
            text = "⚠️ API key ElevenLabs không hợp lệ — cần key thật từ elevenlabs.io (không phải GenMax key)"
            color = "#ff9500"
        else:
            text = f"❌ {msg}"
            color = "#ff3b30"
        self._v_check_status.setText(text)
        self._v_check_status.setStyleSheet(
            f"QLabel{{font-size:12px;color:{color};padding:4px 0 0 88px;"
            "background:transparent;border:none;}"
        )

    def _v_add_voice(self):
        name = self._v_inp_name.text().strip()
        vid  = self._v_inp_id.text().strip()
        if not name or not vid:
            return
        lang  = self._v_inp_lang.currentData() or ""
        langs = getattr(self, "_v_checked_langs", None)  # list từ API check; None nếu chưa check
        is_multi = getattr(self, "_v_voice_is_multilingual", True)
        favs_full = self.settings.setdefault("favorite_voices", [])
        favs_ids  = self.settings.setdefault("favorite_voice_ids", [])
        if any(v.get("id") == vid for v in favs_full):
            self._v_add_form.setVisible(False)
            return
        entry = {"id": vid, "name": name, "lang": lang, "multilingual": is_multi}
        if langs is not None:
            entry["langs"] = langs   # lưu đầy đủ để _v_rebuild_fav_list dùng
        favs_full.append(entry)
        if vid not in favs_ids:
            favs_ids.append(vid)
        from app_utils import save_settings
        save_settings(self.settings)
        self._v_add_form.setVisible(False)
        self._v_rebuild_fav_list()
        mw = self.parent()
        if mw and hasattr(mw, "_sync_voice_combos"):
            mw._sync_voice_combos()

    def _v_remove_voice(self, vid: str):
        self.settings["favorite_voices"] = [
            v for v in self.settings.get("favorite_voices", [])
            if v.get("id") != vid
        ]
        favs_ids = self.settings.get("favorite_voice_ids", [])
        if vid in favs_ids:
            favs_ids.remove(vid)
        from app_utils import save_settings
        save_settings(self.settings)
        self._v_rebuild_fav_list()
        mw = self.parent()
        if mw and hasattr(mw, "_sync_voice_combos"):
            mw._sync_voice_combos()

    def _v_recheck_existing_voice(self, vid: str, btn: QPushButton | None = None):
        vid = (vid or "").strip()
        if not vid:
            return
        api_keys = self.settings.get("el_api_keys", [])
        if not api_keys:
            QMessageBox.warning(
                self,
                "Thiếu ElevenLabs Key",
                "Vào Settings → API để nhập ElevenLabs key trước khi kiểm tra giọng.",
            )
            return
        if btn:
            btn.setEnabled(False)
            btn.setText("Đang kiểm tra")
        worker = _VoiceCheckerWorker(vid, api_keys)
        if not hasattr(self, "_v_recheck_workers"):
            self._v_recheck_workers = {}
        self._v_recheck_workers[vid] = worker
        worker.done.connect(lambda result, v=vid: self._v_on_existing_voice_rechecked(v, result))
        worker.error.connect(lambda msg, v=vid: self._v_on_existing_voice_recheck_error(v, msg))
        worker.start()

    def _v_on_existing_voice_rechecked(self, vid: str, result: dict):
        workers = getattr(self, "_v_recheck_workers", {})
        workers.pop(vid, None)
        langs = result.get("langs", [])
        if langs is None:
            langs = []
        langs = [str(c).strip().lower() for c in langs if str(c).strip()]
        changed = False
        for entry in self.settings.get("favorite_voices", []):
            if entry.get("id") != vid:
                continue
            entry["name"] = result.get("name") or entry.get("name") or vid
            entry["langs"] = langs
            entry["multilingual"] = len(langs) != 1
            current_lang = (entry.get("lang") or "").strip().lower()
            if langs and current_lang not in langs:
                entry["lang"] = langs[0] if len(langs) == 1 else ""
            elif not langs:
                entry["lang"] = current_lang
            changed = True
            break
        if not changed:
            return
        from app_utils import save_settings
        save_settings(self.settings)
        self._v_rebuild_fav_list()
        mw = self.parent()
        if mw and hasattr(mw, "_sync_voice_combos"):
            mw._sync_voice_combos()

    def _v_on_existing_voice_recheck_error(self, vid: str, msg: str):
        workers = getattr(self, "_v_recheck_workers", {})
        workers.pop(vid, None)
        if msg == "no_key":
            msg = "Thiếu ElevenLabs key. Vào Settings → API để nhập key trước."
        elif msg == "invalid_key":
            msg = "ElevenLabs key không hợp lệ. Kiểm tra lại key trong Settings → API."
        QMessageBox.warning(self, "Không kiểm tra được giọng", msg)
        self._v_rebuild_fav_list()

    def _v_rebuild_fav_list(self):
        lay = getattr(self, "_v_fav_list_v", None)
        if lay is None:
            return
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        favs = self.settings.get("favorite_voices", [])
        if not favs:
            empty = QLabel("Chưa có giọng yêu thích.\nNhấn  ＋ Thêm giọng  để bắt đầu.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                "QLabel{font-size:13px;color:#aeaeb2;padding:36px 20px;"
                "background:transparent;border:none;line-height:1.6;}"
            )
            lay.addWidget(empty)
            return

        lang_label_map = {code: lbl for code, lbl in _VOICE_LANG_OPTIONS}

        for i, fav in enumerate(favs):
            vid   = fav.get("id", "")
            vname = fav.get("name", vid)
            vlang = fav.get("lang", "")
            needs_recheck = fav.get("langs") is None
            # langs: list từ API check. Backward compat: nếu không có, dùng multilingual bool.
            stored_langs = fav.get("langs")
            if stored_langs is None:
                stored_langs = []

            # ── Row wrapper ────────────────────────────────────────
            row_w = QWidget()
            row_w.setFixedHeight(48)
            row_w.setStyleSheet(
                "QWidget#voiceRow{background:white;border:none;}"
                "QWidget#voiceRow:hover{background:#f5f5f7;}"
            )
            row_w.setObjectName("voiceRow")
            rh = QHBoxLayout(row_w)
            rh.setContentsMargins(16, 0, 12, 0)
            rh.setSpacing(10)

            # ── Name ───────────────────────────────────────────────
            name_lbl = QLabel(vname)
            name_lbl.setStyleSheet(
                "QLabel{font-size:13px;font-weight:500;color:#1d1d1f;"
                "background:transparent;border:none;}"
            )
            rh.addWidget(name_lbl, 1)

            # ── Language widget theo số ngôn ngữ hỗ trợ ───────────
            if len(stored_langs) == 1:
                # Mono — Apple pill badge, không dropdown
                lang_display = lang_label_map.get(stored_langs[0], stored_langs[0])
                lang_lbl = QLabel(lang_display)
                lang_lbl.setFixedHeight(_LANG_BADGE_HEIGHT)
                lang_lbl.setFixedWidth(_LANG_CONTROL_WIDTH)
                lang_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                lang_lbl.setStyleSheet(_LANG_BADGE_SS)
                lang_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rh.addWidget(lang_lbl)
            else:
                # Multilingual hoặc partial → Apple-style combo
                lang_cb = QComboBox()
                lang_cb.setFixedWidth(_LANG_CONTROL_WIDTH)
                lang_cb.setFixedHeight(_LANG_BADGE_HEIGHT)
                lang_cb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                lang_cb.setStyleSheet(_LANG_COMBO_SS)
                if stored_langs:
                    # Partial: chỉ thêm các ngôn ngữ được hỗ trợ + "Tự động"
                    lang_cb.addItem("— Tự động", "")
                    for code in stored_langs:
                        lang_cb.addItem(lang_label_map.get(code, code), code)
                else:
                    # Full multilingual: toàn bộ danh sách
                    for code, label in _VOICE_LANG_OPTIONS:
                        lang_cb.addItem(label, code)
                current_idx = 0
                for j in range(lang_cb.count()):
                    if lang_cb.itemData(j) == vlang:
                        current_idx = j
                        break
                lang_cb.setCurrentIndex(current_idx)

                def _on_lang_changed(idx, _vid=vid, _cb=lang_cb):
                    new_lang = _cb.itemData(idx)
                    for fv in self.settings.get("favorite_voices", []):
                        if fv.get("id") == _vid:
                            fv["lang"] = new_lang or ""
                            break
                    from app_utils import save_settings
                    save_settings(self.settings)

                lang_cb.currentIndexChanged.connect(_on_lang_changed)
                rh.addWidget(lang_cb)

            # ── ID chip ────────────────────────────────────────────
            short_id = vid[:18] + "…" if len(vid) > 18 else vid
            id_pill = QLabel(short_id)
            id_pill.setFixedWidth(145)
            id_pill.setToolTip(vid)
            id_pill.setStyleSheet(
                "QLabel{color:#8e8e93;font-size:11px;font-family:monospace;"
                "background:transparent;border:none;}"
            )
            rh.addWidget(id_pill)

            if needs_recheck:
                btn_check = QPushButton("Kiểm tra")
                btn_check.setFixedHeight(26)
                btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_check.setStyleSheet(
                    "QPushButton{background:#f2f2f7;color:#3c3c43;border:none;"
                    "border-radius:8px;font-size:12px;font-weight:500;padding:0 10px;}"
                    "QPushButton:hover{background:#e9e9ef;color:#1d1d1f;}"
                    "QPushButton:disabled{color:#8e8e93;background:#f2f2f7;}"
                )
                btn_check.clicked.connect(lambda _, v=vid, b=btn_check: self._v_recheck_existing_voice(v, b))
                rh.addWidget(btn_check)

            # ── Delete ─────────────────────────────────────────────
            btn_del = QPushButton("−")
            btn_del.setFixedSize(26, 26)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(
                "QPushButton{background:#f2f2f7;color:#8e8e93;border:none;"
                "border-radius:13px;font-size:15px;font-weight:600;padding-bottom:2px;}"
                "QPushButton:hover{background:#ffd7d5;color:#ff3b30;}"
            )
            btn_del.clicked.connect(lambda _, v=vid: self._v_remove_voice(v))
            rh.addWidget(btn_del)

            lay.addWidget(row_w)

            # ── Separator (skip last row) ──────────────────────────
            if i < len(favs) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setFixedHeight(1)
                sep.setStyleSheet(
                    "QFrame{background:#f2f2f7;border:none;margin-left:16px;}"
                )
                lay.addWidget(sep)

    def _make_voice_section_card(self, section: str) -> QWidget:
        """Tạo card danh sách giọng — chỉ dùng để quản lý yêu thích."""
        card, card_lay = self._group()

        # ── Picker area ───────────────────────────────────────────
        picker = QWidget()
        picker.setStyleSheet("QWidget{background:transparent;border:none;}")
        pick_v = QVBoxLayout(picker)
        pick_v.setContentsMargins(12, 10, 12, 12)
        pick_v.setSpacing(8)

        # Search bar
        search = QLineEdit()
        search.setPlaceholderText("Tìm theo tên giọng…")
        search.setFixedHeight(32)
        search.setStyleSheet(
            "QLineEdit{background:white;border:1px solid #d2d2d7;border-radius:8px;"
            "padding:0 10px;font-size:13px;color:#1d1d1f;}"
            "QLineEdit:focus{border-color:#0071e3;}"
        )
        search.textChanged.connect(lambda _, sec=section: self._v_apply_filter(sec))
        setattr(self, f"_v_{section}_search", search)
        pick_v.addWidget(search)

        # Lang chips row
        chips_w = QWidget()
        chips_w.setFixedHeight(32)
        chips_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        chips_h = QHBoxLayout(chips_w)
        chips_h.setContentsMargins(0, 0, 0, 0)
        chips_h.setSpacing(6)
        _has_favs = bool(self.settings.get("favorite_voice_ids", []))
        _default_lang = "__fav__" if _has_favs else "all"
        all_chip = QPushButton("Tất cả")
        all_chip.setFixedHeight(26)
        all_chip.setCheckable(True)
        all_chip.setChecked(_default_lang == "all")
        all_chip.setStyleSheet(self._lang_chip_style(_default_lang == "all"))
        all_chip.clicked.connect(lambda _, sec=section: self._v_set_lang(sec, "all"))
        chips_h.addWidget(all_chip)
        chips_h.addStretch()
        setattr(self, f"_v_{section}_chips_h", chips_h)
        setattr(self, f"_v_{section}_chips_w", chips_w)
        setattr(self, f"_v_{section}_chips_dict", {"all": all_chip})
        setattr(self, f"_v_{section}_active_lang", _default_lang)
        pick_v.addWidget(chips_w)

        # Voice list (fixed-height scroll area)
        list_scroll = QScrollArea()
        list_scroll.setWidgetResizable(True)
        list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        list_scroll.setFixedHeight(220)
        list_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{width:4px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:2px;}"
        )
        list_inner = QWidget()
        list_inner.setStyleSheet("QWidget{background:transparent;border:none;}")
        list_vlay = QVBoxLayout(list_inner)
        list_vlay.setContentsMargins(0, 0, 0, 0)
        list_vlay.setSpacing(0)
        list_vlay.addStretch()
        list_scroll.setWidget(list_inner)
        setattr(self, f"_v_{section}_list_lay", list_vlay)
        setattr(self, f"_v_{section}_rows", [])       # [(widget, vid)]
        setattr(self, f"_v_{section}_rows_lang", [])  # [(widget, vid, lang, name)]
        pick_v.addWidget(list_scroll)

        card_lay.addWidget(picker)
        return card

    def _on_voices_fetched(self, voices: list):
        """Render danh sách voices vào cả hai sections."""
        self._voice_status.setVisible(False)

        # Collect unique languages
        lang_set: list[str] = []
        for voice in voices:
            lng = (voice.get("labels") or {}).get("language", "") or \
                  (voice.get("labels") or {}).get("accent", "")
            if lng and lng not in lang_set:
                lang_set.append(lng)
        lang_set.sort()

        for section in ("tts", "av"):
            self._v_build_chips(section, lang_set)
            list_lay = getattr(self, f"_v_{section}_list_lay", None)
            if list_lay is None:
                continue

            rows      = getattr(self, f"_v_{section}_rows")
            rows_lang = getattr(self, f"_v_{section}_rows_lang")

            # Clear existing rows
            while list_lay.count():
                item = list_lay.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            rows.clear()
            rows_lang.clear()

            # Add voice rows
            for voice in voices:
                vid         = voice.get("voice_id", "")
                vname       = voice.get("name", "")
                lang        = (voice.get("labels") or {}).get("language", "") or \
                              (voice.get("labels") or {}).get("accent", "")
                preview_url = voice.get("preview_url", "")
                row_w = self._v_make_voice_row(section, vid, vname, lang, preview_url)
                list_lay.addWidget(row_w)
                rows.append((row_w, vid))
                rows_lang.append((row_w, vid, lang, vname))
            list_lay.addStretch()

            self._v_update_checkmarks(section)
            self._v_apply_filter(section)

    def _v_build_chips(self, section: str, langs: list):
        """Tạo language filter chips cho một section."""
        chips_h    = getattr(self, f"_v_{section}_chips_h", None)
        chips_dict = getattr(self, f"_v_{section}_chips_dict", {})
        if chips_h is None:
            return

        # Clear existing widgets
        while chips_h.count():
            item = chips_h.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        chips_dict.clear()

        active = getattr(self, f"_v_{section}_active_lang", "all")

        # ── "Yêu thích" chip ──
        fav_btn = QPushButton("⭐  Yêu thích")
        fav_btn.setCheckable(True)
        fav_btn.setChecked(active == "__fav__")
        fav_btn.setFixedHeight(26)
        fav_btn.setStyleSheet(
            "QPushButton{background:#fff8e1;color:#a0522d;border:1px solid #f5c518;"
            "border-radius:13px;font-size:12px;padding:0 12px;font-weight:500;}"
            "QPushButton:checked{background:#f5c518;color:#7a3f00;border-color:#e6b800;}"
            "QPushButton:hover{background:#fff0c0;}"
        )
        def _pick_fav(sec=section, btn=fav_btn):
            setattr(self, f"_v_{sec}_active_lang", "__fav__")
            chips_d = getattr(self, f"_v_{sec}_chips_dict", {})
            for b in chips_d.values():
                try:
                    b.setChecked(False)
                    b.setStyleSheet(self._lang_chip_style(False))
                except RuntimeError:
                    pass
            btn.setChecked(True)
            self._v_apply_filter(sec)
        fav_btn.clicked.connect(_pick_fav)
        chips_h.addWidget(fav_btn)
        setattr(self, f"_v_{section}_fav_btn", fav_btn)

        all_langs = [("all", "Tất cả")] + [(l, self._LANG_NAMES.get(l, l.upper())) for l in langs]
        for code, label in all_langs:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setCheckable(True)
            btn.setChecked(code == active)
            btn.setStyleSheet(self._lang_chip_style(code == active))
            def _on_lang_click(_, c=code, sec=section):
                # Uncheck fav btn when a language chip is clicked
                fav_b = getattr(self, f"_v_{sec}_fav_btn", None)
                if fav_b:
                    try:
                        fav_b.setChecked(False)
                    except RuntimeError:
                        pass
                self._v_set_lang(sec, c)
            btn.clicked.connect(_on_lang_click)
            chips_h.addWidget(btn)
            chips_dict[code] = btn
        chips_h.addStretch()
        setattr(self, f"_v_{section}_chips_dict", chips_dict)

    def _lang_chip_style(self, active: bool) -> str:
        if active:
            return ("QPushButton{background:#e8f0fd;color:#0071e3;"
                    "border:1px solid #0071e3;border-radius:13px;"
                    "padding:0 12px;font-size:12px;font-weight:600;}"
                    "QPushButton:hover{background:#dce9fd;}"
                    "QPushButton:pressed{background:#c8defa;}")
        return ("QPushButton{background:#ebebf0;color:#3c3c43;"
                "border:none;border-radius:13px;"
                "padding:0 12px;font-size:12px;font-weight:500;}"
                "QPushButton:hover{background:#e0e0e6;}"
                "QPushButton:pressed{background:#d4d4da;}")

    def _v_set_lang(self, section: str, lang: str):
        setattr(self, f"_v_{section}_active_lang", lang)
        chips_dict = getattr(self, f"_v_{section}_chips_dict", {})
        for code, btn in chips_dict.items():
            try:
                btn.setStyleSheet(self._lang_chip_style(code == lang))
            except RuntimeError:
                pass
        self._v_apply_filter(section)

    def _v_apply_filter(self, section: str):
        """Hiển thị/ẩn voice rows theo lang + search."""
        search_w  = getattr(self, f"_v_{section}_search", None)
        search    = search_w.text().strip().lower() if search_w else ""
        lang      = getattr(self, f"_v_{section}_active_lang", "all")
        rows_lang = getattr(self, f"_v_{section}_rows_lang", [])

        if lang == "__fav__":
            favs = self.settings.get("favorite_voice_ids", [])
            for row_w, vid, row_lang, vname in rows_lang:
                visible = vid in favs
                if visible and search:
                    visible = search in vname.lower() or search in vid.lower()
                try:
                    row_w.setVisible(visible)
                except RuntimeError:
                    pass
            return

        for row_w, vid, row_lang, vname in rows_lang:
            lang_ok   = (lang == "all") or (row_lang == lang)
            search_ok = (not search) or (search in vname.lower()) or (search in vid.lower())
            try:
                row_w.setVisible(lang_ok and search_ok)
            except RuntimeError:
                pass

    def _v_make_voice_row(self, section: str, vid: str, vname: str,
                          lang: str, preview_url: str) -> QWidget:
        """Tạo một row trong danh sách giọng cho section."""
        row_w = QWidget()
        row_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        rh = QHBoxLayout(row_w)
        rh.setContentsMargins(12, 6, 12, 6)
        rh.setSpacing(8)

        name_lbl = QLabel(vname)
        name_lbl.setStyleSheet(
            "QLabel{font-size:13px;color:#1d1d1f;background:transparent;border:none;}"
        )
        rh.addWidget(name_lbl)

        if lang:
            lang_lbl = QLabel(self._LANG_NAMES.get(lang, lang.upper()))
            lang_lbl.setStyleSheet(
                "QLabel{font-size:11px;font-weight:500;color:#3c3c43;"
                "background:#ebebf0;border:none;border-radius:10px;padding:2px 8px;}"
            )
            rh.addWidget(lang_lbl)

        rh.addStretch()

        # ── Star / Favorite button ──
        favs = self.settings.get("favorite_voice_ids", [])
        is_fav = vid in favs
        star_btn = QPushButton("⭐" if is_fav else "☆")
        star_btn.setFixedSize(28, 28)
        star_btn.setToolTip("Thêm/xóa khỏi yêu thích")
        star_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;"
            "font-size:14px;padding:0;}"
            "QPushButton:hover{background:#fff8e1;border-radius:6px;}"
        )
        def _toggle_fav(checked, v_id=vid, v_name=vname, v_lang=lang, btn=star_btn):
            favs_now = self.settings.setdefault("favorite_voice_ids", [])
            favs_full = self.settings.setdefault("favorite_voices", [])
            if v_id in favs_now:
                favs_now.remove(v_id)
                # Xóa khỏi favorite_voices
                self.settings["favorite_voices"] = [
                    v for v in favs_full if v.get("id") != v_id
                ]
                btn.setText("☆")
            else:
                favs_now.append(v_id)
                # Thêm vào favorite_voices nếu chưa có
                if not any(v.get("id") == v_id for v in favs_full):
                    favs_full.append({"id": v_id, "name": v_name, "lang": v_lang})
                btn.setText("⭐")
            from app_utils import save_settings
            save_settings(self.settings)
            # Sync picker combo trong main window (nếu đang mở)
            mw = self.parent()
            if mw and hasattr(mw, "_sync_voice_combos"):
                mw._sync_voice_combos()
            # Re-apply filter if "Yêu thích" chip is active
            for sec in ("tts", "av"):
                if getattr(self, f"_v_{sec}_active_lang", "") == "__fav__":
                    self._v_apply_filter(sec)
        star_btn.clicked.connect(_toggle_fav)
        rh.addWidget(star_btn)

        if preview_url:
            btn_prev = QPushButton("▶  Nghe")
            btn_prev.setFixedHeight(26)
            btn_prev.setFixedWidth(76)
            btn_prev.setToolTip("Nghe thử giọng này")
            btn_prev.setStyleSheet(
                "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
                "border-radius:6px;font-size:12px;color:#1d1d1f;padding:0 8px;}"
                "QPushButton:hover{background:#e8f0fd;border-color:#0071e3;color:#0071e3;}"
                "QPushButton:pressed{background:#dce9fd;}"
            )
            btn_prev.clicked.connect(
                lambda _, u=preview_url, b=btn_prev: self._toggle_voice_preview(u, b)
            )
            rh.addWidget(btn_prev)

        return row_w

    def _voice_check_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton{background:#0071e3;border:none;"
                "border-radius:10px;color:white;font-size:11px;font-weight:700;}"
            )
        return (
            "QPushButton{background:transparent;border:2px solid #c7c7cc;"
            "border-radius:10px;}"
            "QPushButton:hover{border-color:#0071e3;}"
            "QPushButton:pressed{border-color:#005bb5;}"
        )

    def _v_select_voice(self, section: str, vid: str, vname: str):
        """Cập nhật giọng được chọn cho section."""
        if section == "tts":
            self._sel_voice_id   = vid
            self._sel_voice_name = vname
        else:
            self._av_sel_id   = vid
            self._av_sel_name = vname

        # Update selected display
        name_lbl = getattr(self, f"_v_{section}_name_lbl", None)
        if name_lbl:
            try:
                name_lbl.setText(vname or vid[:16])
            except RuntimeError:
                pass

        id_pill = getattr(self, f"_v_{section}_id_pill", None)
        if id_pill:
            try:
                short = vid[:14] + "…" if len(vid) > 14 else vid
                id_pill.setText(short)
                id_pill.setToolTip(vid)
                id_pill.setVisible(True)
            except RuntimeError:
                pass

        self._v_update_checkmarks(section)

    def _v_update_checkmarks(self, section: str):
        """Cập nhật style checkmark của tất cả rows trong section."""
        sel_id = self._sel_voice_id if section == "tts" else self._av_sel_id
        rows   = getattr(self, f"_v_{section}_rows", [])
        for row_w, vid in rows:
            btn = row_w.findChild(QPushButton, f"vc_{section}_{vid}")
            if btn:
                try:
                    btn.setStyleSheet(self._voice_check_style(vid == sel_id))
                    btn.setText("✓" if vid == sel_id else "")
                except RuntimeError:
                    pass

    # ── In-app voice preview (SettingsDialog) ────────────────────

    def _safe_voice_btn(self, btn: "QPushButton | None") -> "QPushButton | None":
        """Return btn nếu C++ object còn sống, None nếu đã bị deleteLater."""
        if btn is None:
            return None
        try:
            btn.objectName()   # raises RuntimeError nếu C++ object đã bị xóa
            return btn
        except RuntimeError:
            return None

    def _toggle_voice_preview(self, url: str, btn: QPushButton):
        """Play / Stop preview button trong Voices list."""
        # Lazy-init player
        if not hasattr(self, "_v_player"):
            self._v_audio_out = QAudioOutput()
            self._v_audio_out.setVolume(1.0)
            self._v_player = QMediaPlayer()
            self._v_player.setAudioOutput(self._v_audio_out)
            self._v_player.playbackStateChanged.connect(self._on_voice_playback_state)
            self._v_playing_btn: QPushButton | None = None
            self._v_dl_worker = None
            self._v_preview_req_id = 0

        # Toggle — defer stop ra ngoài signal handler để tránh re-entrancy
        if getattr(self, "_v_playing_btn", None) is btn:
            QTimer.singleShot(0, self._stop_voice_preview)
            return

        # Stop bài cũ trước khi play mới
        self._stop_voice_preview()
        self._v_preview_req_id += 1
        req_id = self._v_preview_req_id

        self._v_playing_btn = btn
        try:
            btn.setText("⏳")
            btn.setEnabled(False)
        except RuntimeError:
            self._v_playing_btn = None
            return

        w = _keep_preview_thread_alive(AudioPreviewDownloader(url))
        w.done.connect(lambda path, b=btn, rid=req_id, s=self: s._pv_safe_call(lambda: s._play_voice_preview(path, b, rid)))
        w.error.connect(lambda _e, b=btn, rid=req_id, s=self: s._pv_safe_call(lambda: s._reset_voice_btn(b, rid)))
        w.start()
        self._v_dl_worker = w

    def _stop_voice_preview(self):
        """Stop player an toàn, tránh re-entrancy với blockSignals."""
        if not hasattr(self, "_v_player"):
            return
        self._v_player.blockSignals(True)
        self._v_player.stop()
        self._v_player.blockSignals(False)
        btn = self._safe_voice_btn(getattr(self, "_v_playing_btn", None))
        self._v_playing_btn = None
        if btn:
            try:
                btn.setText("▶  Nghe")
                btn.setEnabled(True)
                btn.setStyleSheet(
                    "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
                    "border-radius:6px;font-size:12px;}"
                    "QPushButton:hover{background:#e5e5ea;}"
                )
            except RuntimeError:
                pass

    def _play_voice_preview(self, path: str, btn: QPushButton, req_id: int):
        if req_id != getattr(self, "_v_preview_req_id", 0):
            return
        if not hasattr(self, "_v_player"):
            return
        safe = self._safe_voice_btn(btn)
        if safe is None:
            return
        self._v_player.setSource(QUrl.fromLocalFile(path))
        self._v_player.play()
        try:
            safe.setText("■  Stop")
            safe.setEnabled(True)
            safe.setStyleSheet(
                "QPushButton{background:#e8f0fd;border:1px solid #0071e3;"
                "border-radius:6px;font-size:13px;color:#0071e3;}"
            )
        except RuntimeError:
            pass

    def _reset_voice_btn(self, btn: QPushButton, req_id: int | None = None):
        if req_id is not None and req_id != getattr(self, "_v_preview_req_id", 0):
            return
        safe = self._safe_voice_btn(btn)
        if safe:
            try:
                safe.setText("▶  Nghe")
                safe.setEnabled(True)
                safe.setStyleSheet(
                    "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
                    "border-radius:6px;font-size:12px;}"
                    "QPushButton:hover{background:#e5e5ea;}"
                )
            except RuntimeError:
                pass
        if getattr(self, "_v_playing_btn", None) is btn:
            self._v_playing_btn = None

    def _reset_voice_after_stop(self):
        """Callback defer từ _on_voice_playback_state để tránh re-entrancy."""
        btn = self._safe_voice_btn(getattr(self, "_v_playing_btn", None))
        self._v_playing_btn = None
        if btn:
            try:
                btn.setText("▶  Nghe")
                btn.setEnabled(True)
                btn.setStyleSheet(
                    "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
                    "border-radius:6px;font-size:12px;}"
                    "QPushButton:hover{background:#e5e5ea;}"
                )
            except RuntimeError:
                pass

    def _on_voice_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            # Defer để tránh crash do gọi stop() từ trong signal handler
            QTimer.singleShot(0, self._reset_voice_after_stop)

    def _page_output(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 16, 20, 20)
        v.setSpacing(0)

        v.addWidget(self._page_header(
            "settings", "Cài đặt chung",
            "Thư mục xuất file và tuỳ chọn chung của app.",
        ))

        # ── Output group ──────────────────────────────────────────
        v.addWidget(self._section_label_with_icon("output", "Xuất file"))
        grp, glay = self._group()

        folder_w = QWidget()
        folder_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        fh = QHBoxLayout(folder_w)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(8)
        self.out_dir = QLineEdit(self.settings.get("output_dir", DEFAULT_OUT))
        self.out_dir.setReadOnly(True)
        self.out_dir.setStyleSheet(
            "QLineEdit{background:#f5f5f7;border:1px solid #e5e5ea;"
            "border-radius:6px;padding:4px 8px;font-size:12px;}"
        )
        btn_browse = QPushButton("Chọn…")
        btn_browse.setFixedWidth(64)
        btn_browse.setFixedHeight(28)
        btn_browse.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:6px;font-size:12px;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        btn_browse.clicked.connect(self._browse)
        fh.addWidget(self.out_dir)
        fh.addWidget(btn_browse)
        self._row(glay, "Thư mục lưu", folder_w)

        # Auto-open folder sau khi xuất
        self._auto_open_folder = QCheckBox()
        self._auto_open_folder.setChecked(self.settings.get("auto_open_folder", False))
        self._auto_open_folder.setStyleSheet(
            "QCheckBox{background:transparent;border:none;}"
            "QCheckBox::indicator{width:16px;height:16px;}"
        )
        self._row(glay, "Tự mở thư mục sau khi xuất", self._auto_open_folder, last=True)
        v.addWidget(grp)

        # ── Appearance group ──────────────────────────────────────
        v.addSpacing(18)
        v.addWidget(self._section_label_with_icon("appearance", "Giao diện"))
        grp_theme, glay_theme = self._group()

        self._app_theme = QComboBox()
        self._app_theme.setFixedHeight(30)
        self._app_theme.addItem("Theo hệ thống", "system")
        self._app_theme.addItem("Sáng", "light")
        self._app_theme.addItem("Tối", "dark")
        current_theme = self.settings.get("app_theme", "system")
        idx = next(
            (i for i in range(self._app_theme.count()) if self._app_theme.itemData(i) == current_theme),
            0,
        )
        self._app_theme.setCurrentIndex(idx)
        self._app_theme.setStyleSheet(
            f"QComboBox{{background:{CONTROL_BG};border:none;border-radius:8px;"
            f"padding:3px 26px 3px 10px;font-size:13px;color:{TEXT};}}"
            f"QComboBox:hover{{background:{CONTROL_HV};}}"
            "QComboBox::drop-down{border:none;}"
            + self._combo_item_view_style(28)
        )
        self._app_theme.view().setMinimumWidth(190)
        self._app_theme.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self._row(
            glay_theme,
            "Chế độ nền",
            self._app_theme,
            "Chọn sáng/tối cho app. Một số vùng cũ sẽ được chuẩn hoá tiếp theo palette này.",
            last=True,
        )
        v.addWidget(grp_theme)

        # ── Thông tin ứng dụng ────────────────────────────────────
        v.addSpacing(18)
        v.addWidget(self._section_label_with_icon("settings", "Ứng dụng"))
        grp_info, glay_info = self._group()

        ver_lbl = QLabel(VERSION)
        ver_lbl.setStyleSheet(
            "QLabel{font-size:13px;color:#6e6e73;background:transparent;border:none;}"
        )
        self._row(glay_info, "Phiên bản", ver_lbl, last=True)
        v.addWidget(grp_info)

        v.addStretch()
        return page

    def _page_pipeline(self) -> QWidget:
        """Trang cài đặt Auto-Create-Video — đọc/ghi trực tiếp .env.local."""
        env = _read_env_local()

        page = QWidget()
        page.setStyleSheet(f"QWidget{{background:{BG};}}")
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 24)
        v.setSpacing(0)

        v.addWidget(self._page_header(
            "video", "Auto Video",
            "Cấu hình pipeline tạo video tự động — TTS, AI script, dựng video.",
        ))

        # Apple-style: panel cho các tuỳ chọn nâng cao, sẽ mở trong dialog riêng
        # khi user bấm "Tuỳ chọn nâng cao…". Panel này được tạo nhưng KHÔNG add
        # vào main layout — _save() vẫn đọc được widgets bên trong vì chúng
        # được gán vào self._pv_*.
        self._pv_advanced_panel = QWidget()
        self._pv_advanced_panel.setStyleSheet(f"QWidget{{background:{BG};}}")
        adv_v = QVBoxLayout(self._pv_advanced_panel)
        adv_v.setContentsMargins(24, 20, 24, 24)
        adv_v.setSpacing(0)

        def _lineedit(val: str = "", placeholder: str = "", password: bool = False) -> QLineEdit:
            w = QLineEdit(val)
            if placeholder:
                w.setPlaceholderText(placeholder)
            if password:
                w.setEchoMode(QLineEdit.EchoMode.Password)
            w.setStyleSheet("QLineEdit{background:transparent;border:none;font-size:13px;}")
            return w

        def _combo(options: list[str], current: str) -> QComboBox:
            w = QComboBox()
            for o in options:
                w.addItem(o)
            idx = options.index(current) if current in options else 0
            w.setCurrentIndex(idx)
            combo_style = (
                f"QComboBox{{background:{CONTROL_BG};border:none;"
                f"border-radius:9px;padding:3px 26px 3px 10px;font-size:13px;color:{TEXT};}}"
                f"QComboBox:hover{{background:{CONTROL_HV};}}"
                f"QComboBox:focus{{background:{CONTROL_HV};}}"
                "QComboBox::drop-down{border:none;}"
                + self._combo_item_view_style(24)
            )
            w.setStyleSheet(combo_style)
            w.view().setTextElideMode(Qt.TextElideMode.ElideNone)
            return w

        def _editable_combo(options: list[str], current: str) -> QComboBox:
            w = _combo(options, current if current in options else (options[0] if options else ""))
            w.setEditable(True)
            if current:
                w.setCurrentText(current)
            return w

        def _env_bool(name: str, default: bool = True) -> bool:
            raw = (env.get(name, "") or "").strip().lower()
            if not raw:
                return default
            return raw in ("1", "true", "yes", "on")

        def _provider_page() -> QWidget:
            page_w = QWidget()
            page_w.setStyleSheet("QWidget{background:transparent;border:none;}")
            lay = QVBoxLayout(page_w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            return page_w

        def _api_note(text: str) -> QLabel:
            note = QLabel(text)
            note.setWordWrap(True)
            note.setStyleSheet("font-size:12px;color:#6e6e73;background:transparent;border:none;")
            return note

        # Alias class method cho local scope
        _add_collapsible = self._add_collapsible

        # ── SECTION: GIỌNG ĐỌC (TTS) — moved to advanced panel ─────
        adv_v.insertWidget(0, self._section_label_with_icon("voices", "Giọng đọc (TTS)"))
        grp_tts, glay_tts = self._group()

        # Provider dropdown
        _providers = ["genmax", "ai33", "elevenlabs", "lucylab"]
        _cur_provider = env.get("TTS_PROVIDER", "genmax")
        if _cur_provider not in _providers:
            _cur_provider = "genmax"
        self._pv_provider = _combo(_providers, _cur_provider)

        # Voice ID fields (1 per provider, chỉ show cái đang chọn)
        self._pv_voices: dict[str, QLineEdit] = {
            "genmax":     _lineedit(env.get("GENMAX_VOICE_ID", ""),     "Voice ID…"),
            "ai33":       _lineedit(env.get("AI33_VOICE_ID", ""),       "Để trống = dùng GENMAX_VOICE_ID"),
            "elevenlabs": _lineedit(env.get("ELEVENLABS_VOICE_ID", ""), "Voice ID…"),
            "lucylab":    _lineedit(env.get("VIETNAMESE_VOICEID", ""),  "Voice ID…"),
        }
        # Stacked widget để swap voice field khi đổi provider
        self._pv_voice_stack = QStackedWidget()
        self._pv_voice_stack.setStyleSheet("QStackedWidget{background:transparent;border:none;}")
        for provider in _providers:
            self._pv_voice_stack.addWidget(self._pv_voices[provider])
        self._pv_voice_stack.setCurrentIndex(
            _providers.index(_cur_provider) if _cur_provider in _providers else 0
        )

        self._row(glay_tts, "Provider", self._pv_provider,
                  "Chọn dịch vụ TTS. API key nhập ở tab API.")
        voice_id_w = QWidget()
        voice_id_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        voice_id_h = QHBoxLayout(voice_id_w)
        voice_id_h.setContentsMargins(0, 0, 0, 0)
        voice_id_h.setSpacing(8)
        voice_id_h.addWidget(self._pv_voice_stack, 1)

        self._pv_voice_preview_btn = QPushButton("▶")
        self._pv_voice_preview_btn.setFixedSize(28, 28)
        self._pv_voice_preview_btn.setToolTip("Nghe thử giọng đang chọn")
        self._pv_voice_preview_btn.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:14px;font-size:12px;padding:0;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        self._pv_voice_preview_btn.clicked.connect(self._pv_preview_voice)
        voice_id_h.addWidget(self._pv_voice_preview_btn)

        self._row(glay_tts, "Voice ID đang dùng", voice_id_w,
                  "ai33 có thể để trống để dùng chung GENMAX_VOICE_ID.")

        preset_w = QWidget()
        preset_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        preset_h = QHBoxLayout(preset_w)
        preset_h.setContentsMargins(0, 0, 0, 0)
        preset_h.setSpacing(8)

        self._pv_voice_preset_combo = _combo([], "")
        self._pv_voice_preset_combo.setMinimumWidth(180)
        self._pv_voice_preset_combo.currentIndexChanged.connect(self._pv_apply_voice_preset)
        preset_h.addWidget(self._pv_voice_preset_combo, 1)

        self._pv_voice_add_btn = QPushButton("+")
        self._pv_voice_add_btn.setFixedSize(28, 28)
        self._pv_voice_add_btn.setToolTip("Thêm giọng yêu thích")
        self._pv_voice_add_btn.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:14px;font-size:18px;font-weight:500;padding:0;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        self._pv_voice_add_btn.clicked.connect(self._pv_add_voice_preset)
        preset_h.addWidget(self._pv_voice_add_btn)

        self._pv_voice_delete_btn = QPushButton("Xóa")
        self._pv_voice_delete_btn.setFixedHeight(28)
        self._pv_voice_delete_btn.setStyleSheet(
            "QPushButton{background:#fff5f5;border:1px solid #ffd6d6;"
            "border-radius:6px;color:#d70015;padding:0 10px;font-size:12px;}"
            "QPushButton:hover{background:#ffecec;}"
        )
        self._pv_voice_delete_btn.clicked.connect(self._pv_delete_voice_preset)
        preset_h.addWidget(self._pv_voice_delete_btn)

        self._row(glay_tts, "Preset nhanh", preset_w,
                  "Danh sách giọng bạn tự lưu trong Hedra Studio; không phải thư viện GenMax.", last=True)

        # Tạo sẵn (gắn vào self để _save() đọc được) — sẽ add vào GenMax setup page bên dưới
        self._pv_eleven_v3_style_enabled = QCheckBox("Bật nhấn nhá Eleven v3")
        self._pv_eleven_v3_style_enabled.setChecked(_env_bool("ELEVEN_V3_STYLE_ENABLED", True))
        self._pv_eleven_v3_style_enabled.setStyleSheet(
            "QCheckBox{background:transparent;border:none;font-size:13px;color:#1d1d1f;}"
            "QCheckBox::indicator{width:16px;height:16px;}"
        )
        self._pv_genmax_fallback_ai33 = QCheckBox("GenMax lỗi thì tự chuyển sang ai33")
        self._pv_genmax_fallback_ai33.setChecked(_env_bool("GENMAX_FALLBACK_TO_AI33", True))
        self._pv_genmax_fallback_ai33.setStyleSheet(
            "QCheckBox{background:transparent;border:none;font-size:13px;color:#1d1d1f;}"
            "QCheckBox::indicator{width:16px;height:16px;}"
        )
        self._pv_seed_selected_elevenlabs_voice()
        self._pv_refresh_voice_presets()
        # grp_tts moved to advanced settings panel — voice selection via favorites picker in tool tabs
        adv_v.insertWidget(1, grp_tts)

        # ── SECTION: PROVIDER SETUP ────────────────────────────────
        # Apple-style: chuyển vào "Tuỳ chọn nâng cao" — phần lớn người dùng
        # chỉ chỉnh Voice ID là đủ, không cần model/endpoint mỗi lần.
        adv_v.addWidget(self._section_label_with_icon("settings", "Setup provider"))
        self._pv_setup_stack = QStackedWidget()
        self._pv_setup_stack.setStyleSheet("QStackedWidget{background:transparent;border:none;}")

        # GenMax page
        page_gm = _provider_page()
        page_gm_lay = page_gm.layout()
        grp_gm, glay_gm = self._group()
        page_gm_lay.addWidget(grp_gm)

        gm_provider = env.get("GENMAX_PROVIDER", "elevenlabs").strip().lower()
        if gm_provider not in ("elevenlabs", "minimax"):
            gm_provider = "elevenlabs"
        default_gm_model = "speech-2.8-turbo" if gm_provider == "minimax" else "eleven_v3"
        default_gm_lang = (env.get("GENMAX_LANGUAGE_CODE", "") or "").strip() or ("Vietnamese" if gm_provider == "minimax" else "vi")

        self._pv_gm_provider = _combo(["elevenlabs", "minimax"], gm_provider)
        self._pv_gm_model = _editable_combo([default_gm_model], env.get("GENMAX_MODEL_ID", default_gm_model))
        self._pv_gm_language = _editable_combo(["Vietnamese (vi)", "English (en)"], "")
        self._pv_set_genmax_language_choices([], default_gm_lang)

        voice_picker = QWidget()
        voice_picker.setStyleSheet("QWidget{background:transparent;border:none;}")
        voice_picker_h = QHBoxLayout(voice_picker)
        voice_picker_h.setContentsMargins(0, 0, 0, 0)
        voice_picker_h.setSpacing(8)

        self._pv_gm_voice_combo = QComboBox()
        self._pv_gm_voice_combo.setMinimumWidth(220)
        self._pv_gm_voice_combo.setStyleSheet(
            "QComboBox{background:#f5f5f7;border:none;"
            "border-radius:9px;padding:3px 26px 3px 10px;font-size:13px;color:#1d1d1f;}"
            "QComboBox:hover{background:#ececf0;}"
            "QComboBox:focus{background:#ececf0;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#ffffff;color:#1d1d1f;"
            "border:1px solid #d2d2d7;border-radius:6px;outline:none;"
            "selection-background-color:#0a84ff;selection-color:#ffffff;padding:2px;}"
            "QComboBox QAbstractItemView::item{min-height:24px;padding:4px 10px;}"
            "QComboBox QAbstractItemView::item:hover{background:#ececf0;color:#1d1d1f;}"
        )
        self._pv_gm_voice_combo.addItem("Chọn voice đã lưu…", "")
        self._pv_gm_voice_combo.currentIndexChanged.connect(self._pv_apply_genmax_voice)
        voice_picker_h.addWidget(self._pv_gm_voice_combo, 1)

        self._pv_gm_load_btn = QPushButton("Kiểm tra")
        self._pv_gm_load_btn.setFixedHeight(28)
        self._pv_gm_load_btn.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:6px;padding:0 12px;font-size:12px;}"
            "QPushButton:hover{background:#e5e5ea;}"
            "QPushButton:disabled{color:#aeaeb2;}"
        )
        self._pv_gm_load_btn.clicked.connect(self._pv_load_genmax_catalog)
        voice_picker_h.addWidget(self._pv_gm_load_btn)

        def _on_gm_provider_change(idx: int):
            provider_name = "minimax" if idx == 1 else "elevenlabs"
            cur_model = self._pv_genmax_model()
            if not cur_model or cur_model in ("eleven_v3", "speech-2.8-turbo"):
                self._pv_gm_model.setCurrentText("speech-2.8-turbo" if provider_name == "minimax" else "eleven_v3")
            cur_lang = self._pv_genmax_language()
            if not cur_lang or cur_lang in ("vi", "en", "Vietnamese"):
                self._pv_set_genmax_language_choices([], "Vietnamese" if provider_name == "minimax" else "vi")
            self._pv_genmax_api_language_values = []
            QTimer.singleShot(100, self._pv_load_genmax_languages)

        self._pv_gm_provider.currentIndexChanged.connect(_on_gm_provider_change)

        self._row(glay_gm, "Loại voice", self._pv_gm_provider,
                  "Tự nhận diện sau khi bấm Kiểm tra.")
        self._row(glay_gm, "Voice đã lưu", voice_picker,
                  "Bấm Kiểm tra để load lại model + loại voice.")
        self._row(glay_gm, "Model TTS", self._pv_gm_model)
        self._row(glay_gm, "Ngôn ngữ", self._pv_gm_language)
        self._row(glay_gm, "Nhấn nhá v3", self._pv_eleven_v3_style_enabled,
                  "Tự thêm tag cảm xúc nhẹ cho eleven_v3.")
        self._row(glay_gm, "Fallback ai33", self._pv_genmax_fallback_ai33,
                  "Tự chuyển sang ai33 khi GenMax lỗi.", last=True)

        # ai33 page
        page_ai33 = _provider_page()
        page_ai33_lay = page_ai33.layout()
        grp_ai33, glay_ai33 = self._group()
        page_ai33_lay.addWidget(grp_ai33)
        self._pv_ai33_model = _lineedit(env.get("AI33_MODEL_ID", "eleven_v3"), "eleven_v3")
        self._pv_ai33_endpoint = _lineedit(env.get("AI33_ENDPOINT", "https://api.ai33.pro"), "https://api.ai33.pro")
        self._pv_ai33_output_format = _lineedit(env.get("AI33_OUTPUT_FORMAT", "mp3_44100_128"), "mp3_44100_128")
        self._row(glay_ai33, "Model TTS", self._pv_ai33_model,
                  "Mặc định eleven_v3.")
        self._row(glay_ai33, "Endpoint", self._pv_ai33_endpoint)
        self._row(glay_ai33, "Output format", self._pv_ai33_output_format,
                  "Giữ mp3_44100_128 nếu không cần đổi.", last=True)

        # ElevenLabs page
        page_el = _provider_page()
        page_el_lay = page_el.layout()
        grp_el, glay_el = self._group()
        page_el_lay.addWidget(grp_el)
        self._pv_el_model = _lineedit(env.get("ELEVENLABS_MODEL_ID", "eleven_v3"), "eleven_v3")
        self._row(glay_el, "Model TTS", self._pv_el_model,
                  "Mặc định eleven_v3.", last=True)

        # LucyLab page
        page_ll = _provider_page()
        page_ll_lay = page_ll.layout()
        grp_ll, glay_ll = self._group()
        page_ll_lay.addWidget(grp_ll)
        self._pv_ll_endpoint = _lineedit(env.get("LUCYLAB_ENDPOINT", "https://api.lucylab.io/json-rpc"), "https://api.lucylab.io/json-rpc")
        self._row(glay_ll, "Endpoint", self._pv_ll_endpoint,
                  "Giữ mặc định nếu không có endpoint riêng.", last=True)

        for page_item in (page_gm, page_ai33, page_el, page_ll):
            self._pv_setup_stack.addWidget(page_item)
        self._pv_setup_stack.setCurrentIndex(self._pv_provider.currentIndex())
        adv_v.addWidget(self._pv_setup_stack)

        def _on_provider_change(idx: int):
            self._pv_voice_stack.setCurrentIndex(idx)
            self._pv_setup_stack.setCurrentIndex(idx)
            self._pv_refresh_voice_presets()
            if self._pv_current_provider() == "genmax":
                self._pv_refresh_genmax_saved_voices()

        self._pv_provider.currentIndexChanged.connect(_on_provider_change)

        self._pv_refresh_genmax_saved_voices()
        QTimer.singleShot(150, self._pv_load_genmax_languages)

        # Khởi tạo các control nâng cao (sẽ add vào collapsible bên dưới)
        _pace_modes = ["dynamic", "standard"]
        _cur_pace = env.get("AUTO_VIDEO_EDITING_PACE", "dynamic").strip().lower()
        if _cur_pace not in _pace_modes:
            _cur_pace = "dynamic"
        self._pv_auto_editing_pace = _combo(_pace_modes, _cur_pace)

        self._pv_auto_burn_captions = QCheckBox("Bật sub trong video")
        self._pv_auto_burn_captions.setChecked(_env_bool("AUTO_VIDEO_BURN_CAPTIONS", False))
        self._pv_auto_burn_captions.setStyleSheet(
            "QCheckBox{font-size:13px;color:#1d1d1f;background:transparent;border:none;}"
            "QCheckBox::indicator{width:16px;height:16px;}"
        )

        _caption_modes = ["word_transcript", "estimated", "off"]
        _cur_caption_mode = env.get("AUTO_VIDEO_CAPTION_MODE", "word_transcript").strip().lower()
        if _cur_caption_mode not in _caption_modes:
            _cur_caption_mode = "word_transcript"
        self._pv_auto_caption_mode = _combo(_caption_modes, _cur_caption_mode)

        _caption_styles = ["capcut_pop", "karaoke_fill", "clean_box"]
        _cur_caption_style = env.get("AUTO_VIDEO_CAPTION_STYLE", "capcut_pop").strip().lower()
        if _cur_caption_style not in _caption_styles:
            _cur_caption_style = "capcut_pop"
        self._pv_auto_caption_style = _combo(_caption_styles, _cur_caption_style)

        # Apple-style: dựng + sub đưa vào panel nâng cao (mở qua dialog)
        adv_v.addWidget(self._section_label_with_icon("video", "Dựng video & Phụ đề"))
        grp_ai_adv, glay_ai_adv = self._group()
        self._row(glay_ai_adv, "Nhịp dựng", self._pv_auto_editing_pace,
                  "dynamic: nhiều cảnh ngắn + motion.")
        self._row(glay_ai_adv, "Sub trong video", self._pv_auto_burn_captions,
                  "Bật để đốt phụ đề vào video.")
        self._row(glay_ai_adv, "Timing sub", self._pv_auto_caption_mode,
                  "word_transcript: bám timing thật.")
        self._row(glay_ai_adv, "Kiểu sub", self._pv_auto_caption_style,
                  "capcut_pop: từ đang đọc highlight vàng.", last=True)
        adv_v.addWidget(grp_ai_adv)

        def _sync_caption_controls():
            enabled = self._pv_auto_burn_captions.isChecked()
            self._pv_auto_caption_mode.setEnabled(enabled)
            self._pv_auto_caption_style.setEnabled(enabled)
        self._pv_auto_burn_captions.stateChanged.connect(lambda _state: _sync_caption_controls())
        _sync_caption_controls()

        # Apple-style: model config của Gemini/Claude — collapsible riêng trong panel nâng cao
        self._pv_script_setup_collapsible_btn, _script_setup_inner = _add_collapsible(adv_v, "Model AI script")
        self._pv_script_setup_label = self._section_label_with_icon("script", "Model AI script")
        self._pv_script_setup_label.setVisible(False)  # tiêu đề đã có trong nút collapsible
        self._pv_script_setup_stack = QStackedWidget()
        self._pv_script_setup_stack.setStyleSheet("QStackedWidget{background:transparent;border:none;}")

        page_ds = _provider_page()  # DeepSeek không cần config riêng — ẩn stack

        page_gem_script = _provider_page()
        page_gem_lay = page_gem_script.layout()
        grp_gem_script, glay_gem_script = self._group()
        page_gem_lay.addWidget(grp_gem_script)
        self._pv_gemini_text_model = _lineedit(
            env.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash"),
            "gemini-2.5-flash",
        )
        self._row(glay_gem_script, "Gemini model", self._pv_gemini_text_model,
                  "Mặc định gemini-2.5-flash.", last=True)

        page_claude = _provider_page()
        page_claude_lay = page_claude.layout()
        grp_claude_script, glay_claude_script = self._group()
        page_claude_lay.addWidget(grp_claude_script)
        self._pv_claude_model = _editable_combo(
            CLAUDE_MODEL_CHOICES,
            _recommended_claude_model(env.get("CLAUDE_MODEL", "") or self.settings.get("claude_model", "")),
        )
        self._row(glay_claude_script, "Claude model", self._pv_claude_model,
                  "Chỉ dùng khi có Claude key trong tab API.", last=True)

        # Claude là provider chủ đạo — chỉ cần page Claude
        for page_item in (page_claude, page_ds, page_gem_script):
            self._pv_script_setup_stack.addWidget(page_item)
        self._pv_script_setup_stack.setCurrentIndex(0)  # luôn dùng Claude page
        _script_setup_inner.addWidget(self._pv_script_setup_stack)

        # ── SECTION: KÊNH TIKTOK (Outro) ───────────────────────────
        v.addWidget(self._section_label_with_icon("video", "Kênh TikTok (Outro)"))
        grp_tt, glay_tt = self._group()

        self._pv_tt_name      = _lineedit(env.get("TIKTOK_DISPLAY_NAME", ""), "Hedra Central")
        self._pv_tt_badge     = _lineedit(env.get("TIKTOK_BADGE_LABEL", ""),   "Để trống nếu không dùng")
        self._pv_tt_tagline   = _lineedit(env.get("TIKTOK_TAGLINE", ""),      "TIN CRYPTO 24H")
        self._pv_tt_handle    = _lineedit(env.get("TIKTOK_HANDLE", ""),       "@hedracentral")
        self._pv_tt_followers = _lineedit(env.get("TIKTOK_FOLLOWERS", ""),    "Follow for more")
        self._pv_tt_avatar_url = _lineedit(env.get("TIKTOK_AVATAR_URL", ""), "https://.../avatar.jpg")
        self._pv_show_source_link = QCheckBox("Hiện link nguồn bài báo trong video")
        self._pv_show_source_link.setChecked(
            env.get("SHOW_SOURCE_LINK", "true").strip().lower() not in {"0", "false", "no", "off"}
        )
        self._pv_show_source_link.setStyleSheet(
            "QCheckBox{font-size:13px;color:#1d1d1f;background:transparent;border:none;}"
            "QCheckBox::indicator{width:16px;height:16px;}"
        )

        avatar_w = QWidget()
        avatar_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        avatar_h = QHBoxLayout(avatar_w)
        avatar_h.setContentsMargins(0, 0, 0, 0)
        avatar_h.setSpacing(8)
        avatar_h.addWidget(self._pv_tt_avatar_url, 1)

        btn_avatar = QPushButton("Chọn logo")
        btn_avatar.setFixedHeight(28)
        btn_avatar.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:6px;padding:0 10px;font-size:12px;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        btn_avatar.clicked.connect(self._pv_choose_tiktok_avatar)
        avatar_h.addWidget(btn_avatar)

        btn_edit_avatar = QPushButton("Căn lại")
        btn_edit_avatar.setFixedHeight(28)
        btn_edit_avatar.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:6px;padding:0 10px;font-size:12px;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        btn_edit_avatar.clicked.connect(self._pv_edit_tiktok_avatar)
        avatar_h.addWidget(btn_edit_avatar)

        self._row(glay_tt, "Tên hiển thị",  self._pv_tt_name)
        self._row(glay_tt, "Badge đầu video", self._pv_tt_badge, "Ví dụ: TIN NHANH, CRYPTO. Để trống thì không hiện.")
        self._row(glay_tt, "Dòng phụ banner", self._pv_tt_tagline, "Ví dụ: TIN CRYPTO 24H")
        self._row(glay_tt, "Handle",         self._pv_tt_handle, "@yourhandle")
        self._row(glay_tt, "Bio / Followers", self._pv_tt_followers)
        self._row(glay_tt, "Nguồn bài báo", self._pv_show_source_link,
                  "Tắt nếu không muốn hiện domain như 5phutcrypto.io ở cuối video và outro.")
        self._row(glay_tt, "Logo / Avatar", avatar_w,
                  "Dán URL logo hoặc chọn file local để dùng làm logo/avatar trong banner và outro.", last=True)
        v.addWidget(grp_tt)

        preview_card = QWidget()
        preview_card.setStyleSheet("QWidget{background:#ffffff;border:1px solid #e5e5ea;border-radius:10px;}")
        preview_v = QVBoxLayout(preview_card)
        preview_v.setContentsMargins(14, 12, 14, 12)
        preview_v.setSpacing(12)

        banner = QWidget()
        banner.setFixedHeight(90)
        banner.setStyleSheet("QWidget{background:#102034;border:1px solid #1c3858;border-radius:8px;}")
        banner_h = QHBoxLayout(banner)
        banner_h.setContentsMargins(18, 10, 18, 10)
        banner_h.setSpacing(14)

        self._pv_tt_banner_avatar = QLabel()
        self._pv_tt_banner_avatar.setFixedSize(58, 58)
        banner_h.addWidget(self._pv_tt_banner_avatar)

        banner_text = QVBoxLayout()
        banner_text.setContentsMargins(0, 0, 0, 0)
        banner_text.setSpacing(2)
        self._pv_tt_banner_name = QLabel()
        self._pv_tt_banner_name.setStyleSheet("font-size:24px;font-weight:800;color:#ffffff;background:transparent;border:none;")
        self._pv_tt_banner_tagline = QLabel()
        self._pv_tt_banner_tagline.setStyleSheet("font-size:15px;font-weight:700;color:#45d9ff;letter-spacing:2px;background:transparent;border:none;")
        banner_text.addWidget(self._pv_tt_banner_name)
        banner_text.addWidget(self._pv_tt_banner_tagline)
        banner_h.addLayout(banner_text)
        banner_h.addStretch()
        preview_v.addWidget(banner)

        outro = QWidget()
        outro.setFixedHeight(118)
        outro.setStyleSheet("QWidget{background:#221b45;border:1px solid #302864;border-radius:8px;}")
        outro_outer = QHBoxLayout(outro)
        outro_outer.setContentsMargins(18, 18, 18, 18)

        follow_card = QWidget()
        follow_card.setStyleSheet("QWidget{background:#181a18;border:none;border-radius:28px;}")
        follow_h = QHBoxLayout(follow_card)
        follow_h.setContentsMargins(18, 12, 18, 12)
        follow_h.setSpacing(14)

        self._pv_tt_avatar_preview = QLabel()
        self._pv_tt_avatar_preview.setFixedSize(62, 62)
        follow_h.addWidget(self._pv_tt_avatar_preview)

        preview_text = QVBoxLayout()
        preview_text.setContentsMargins(0, 0, 0, 0)
        preview_text.setSpacing(2)
        self._pv_tt_preview_name = QLabel()
        self._pv_tt_preview_name.setStyleSheet("font-size:21px;font-weight:800;color:#ffffff;background:transparent;border:none;")
        self._pv_tt_preview_handle = QLabel()
        self._pv_tt_preview_handle.setStyleSheet("font-size:14px;font-weight:600;color:#9b9b9f;background:transparent;border:none;")
        self._pv_tt_preview_bio = QLabel()
        self._pv_tt_preview_bio.setStyleSheet("font-size:13px;color:#7e7e83;background:transparent;border:none;")
        preview_text.addWidget(self._pv_tt_preview_name)
        preview_text.addWidget(self._pv_tt_preview_handle)
        preview_text.addWidget(self._pv_tt_preview_bio)
        follow_h.addLayout(preview_text)
        follow_h.addStretch()

        follow_btn = QLabel("Following ✓")
        follow_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        follow_btn.setFixedSize(118, 44)
        follow_btn.setStyleSheet("QLabel{background:#ff2f68;color:white;border:none;border-radius:22px;font-size:17px;font-weight:800;}")
        follow_h.addWidget(follow_btn)
        outro_outer.addWidget(follow_card)
        preview_v.addWidget(outro)

        v.addSpacing(8)
        v.addWidget(preview_card)

        for w in (self._pv_tt_name, self._pv_tt_badge, self._pv_tt_tagline, self._pv_tt_handle, self._pv_tt_followers, self._pv_tt_avatar_url):
            w.textChanged.connect(self._pv_update_tiktok_preview)
        self._pv_update_tiktok_preview()

        # ── SECTION: THUMBNAIL AI ───────────────────────────────────
        v.addWidget(self._section_label_with_icon("image", "Thumbnail AI"))
        grp_gem, glay_gem = self._group()

        self._pv_gemini_key = self._pv_script_gemini_key
        gemini_hint = QLabel("Dùng Gemini key ở tab API để tạo thumbnail.")
        gemini_hint.setStyleSheet("font-size:12px;color:#6e6e73;background:transparent;border:none;")
        gemini_hint.setWordWrap(True)
        self._row(glay_gem, "Gemini API Key", gemini_hint,
                  "Không cần nhập lại; Auto Video dùng cùng key trong .env.local.", last=True)
        v.addWidget(grp_gem)

        # Apple-style: nút mở "Tuỳ chọn nâng cao" (sheet riêng)
        adv_btn_row = QWidget()
        adv_btn_row.setStyleSheet("QWidget{background:transparent;border:none;}")
        adv_btn_h = QHBoxLayout(adv_btn_row)
        adv_btn_h.setContentsMargins(0, 14, 0, 0)
        adv_btn_h.setSpacing(0)
        adv_btn = QPushButton("Tuỳ chọn nâng cao…")
        adv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        adv_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#0a84ff;"
            "font-size:13px;font-weight:500;text-align:left;padding:6px 0;}"
            "QPushButton:hover{color:#0066cc;}"
        )
        adv_btn.clicked.connect(self._pv_open_advanced_dialog)
        adv_btn_h.addWidget(adv_btn)
        adv_btn_h.addStretch()
        v.addWidget(adv_btn_row)

        adv_v.addStretch()
        # Giữ panel sống nhưng không hiện ra; sẽ được reparent vào dialog khi mở
        self._pv_advanced_panel.setParent(self)
        self._pv_advanced_panel.hide()

        v.addStretch()
        return page

    def _pv_open_advanced_dialog(self):
        """Apple-style sheet hiển thị tất cả tuỳ chọn nâng cao của Auto Video."""
        if not hasattr(self, "_pv_advanced_panel"):
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Tuỳ chọn nâng cao — Auto Video")
        dlg.resize(680, 780)
        dlg.setStyleSheet(f"QDialog{{background:{BG};}}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        container = QWidget()
        container.setStyleSheet(f"QWidget{{background:{BG};}}")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._pv_advanced_panel)
        self._pv_advanced_panel.show()
        scroll.setWidget(container)
        lay.addWidget(scroll, 1)

        btn_bar = QWidget()
        btn_bar.setStyleSheet("QWidget{background:#f5f5f7;border-top:1px solid #e5e5ea;}")
        btn_h = QHBoxLayout(btn_bar)
        btn_h.setContentsMargins(20, 12, 20, 14)
        btn_h.addStretch()
        btn_done = QPushButton("Xong")
        btn_done.setFixedHeight(32)
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.setStyleSheet(
            "QPushButton{background:#0a84ff;color:white;border:none;"
            "border-radius:8px;padding:0 22px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0066cc;}"
        )
        btn_done.clicked.connect(dlg.accept)
        btn_h.addWidget(btn_done)
        lay.addWidget(btn_bar)

        def _detach(_result=0):
            # Tái gắn panel vào dialog cha để không bị huỷ khi dialog đóng
            self._pv_advanced_panel.setParent(self)
            self._pv_advanced_panel.hide()
        dlg.finished.connect(_detach)
        dlg.exec()

    def _pv_current_provider(self) -> str:
        providers = ["genmax", "ai33", "elevenlabs", "lucylab"]
        if not hasattr(self, "_pv_provider"):
            return "genmax"
        idx = self._pv_provider.currentIndex()
        return providers[idx] if 0 <= idx < len(providers) else "genmax"

    def _pv_current_voice_edit(self) -> QLineEdit:
        return getattr(self, "_pv_voices", {}).get(self._pv_current_provider(), _NullEdit())

    def _pv_genmax_language(self) -> str:
        w = getattr(self, "_pv_gm_language", _NullEdit())
        if hasattr(w, "currentText"):
            data = w.currentData()
            if isinstance(data, str) and data.strip():
                return data.strip()
            text = w.currentText().strip()
            m = re.search(r"\(([^()]+)\)\s*$", text)
            if m:
                return m.group(1).strip()
            return text
        return w.text().strip()

    def _pv_genmax_model(self) -> str:
        w = getattr(self, "_pv_gm_model", _NullEdit())
        if hasattr(w, "currentText"):
            data = w.currentData()
            if isinstance(data, str) and data.strip():
                return data.strip()
            text = w.currentText().strip()
            m = re.search(r"\(([^()]+)\)\s*$", text)
            if m:
                return m.group(1).strip()
            return text
        return w.text().strip()

    def _pv_set_combo_values(self, combo: QComboBox, values: list[tuple[str, str]], current: str = ""):
        combo.blockSignals(True)
        combo.clear()
        seen = set()
        selected_idx = 0
        for label, value in values:
            value = (value or label).strip()
            label = (label or value).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            combo.addItem(label, value)
            if current and value == current:
                selected_idx = combo.count() - 1
        if current and current not in seen:
            combo.addItem(current, current)
            selected_idx = combo.count() - 1
        if combo.count() == 0 and current:
            combo.addItem(current, current)
        if combo.count() > 0:
            combo.setCurrentIndex(selected_idx)
        combo.blockSignals(False)

    def _pv_set_genmax_language_choices(self, values: list[tuple[str, str]], current: str = ""):
        provider = (
            getattr(self, "_pv_gm_provider", _NullEdit()).currentText().strip().lower()
            if hasattr(getattr(self, "_pv_gm_provider", None), "currentText") else "elevenlabs"
        )
        default_value = "Vietnamese" if provider == "minimax" else "vi"
        current = (current or "").strip() or default_value
        base = [("Vietnamese (vi)", "vi"), ("English (en)", "en")]
        if provider == "minimax":
            base = [("Vietnamese", "Vietnamese"), ("English", "English")]

        merged = []
        seen = set()
        for label, value in [*base, *(values or [])]:
            value = (value or label or "").strip()
            label = (label or value).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append((label, value))

        if current in ("Vietnamese (vi)", "Vietnamese", "viet", "vietnam", "vi-VN"):
            current = default_value
        self._pv_set_combo_values(self._pv_gm_language, merged, current)

    def _pv_genmax_language_values_from_api(self, languages: list) -> list[tuple[str, str]]:
        values = []
        for item in languages or []:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or code).strip()
            if not code:
                continue
            label = f"{name} ({code})" if name and name != code else code
            values.append((label, code))
        return values

    def _pv_load_genmax_languages(self):
        if getattr(self, "_pv_genmax_languages_loading", False):
            return
        api_key = getattr(self, "_pv_gm_key", _NullEdit()).text().strip()
        if not api_key:
            return
        provider = (
            getattr(self, "_pv_gm_provider", _NullEdit()).currentText().strip().lower()
            if hasattr(getattr(self, "_pv_gm_provider", None), "currentText") else "elevenlabs"
        )
        self._pv_genmax_languages_loading = True
        worker = _keep_preview_thread_alive(_GenMaxLanguagesWorker(api_key, provider))
        worker.done.connect(lambda languages, s=self: s._pv_safe_call(lambda: s._pv_on_genmax_languages(languages)))
        worker.error.connect(lambda _msg, s=self: s._pv_safe_call(s._pv_on_genmax_languages_done))
        self._pv_genmax_languages_worker = worker
        worker.start()

    def _pv_on_genmax_languages(self, languages: list):
        values = self._pv_genmax_language_values_from_api(languages)
        if values:
            self._pv_genmax_api_language_values = values
            provider = (
                getattr(self, "_pv_gm_provider", _NullEdit()).currentText().strip().lower()
                if hasattr(getattr(self, "_pv_gm_provider", None), "currentText") else "elevenlabs"
            )
            current = self._pv_genmax_language() or ("Vietnamese" if provider == "minimax" else "vi")
            self._pv_set_genmax_language_choices(values, current)
        self._pv_on_genmax_languages_done()

    def _pv_on_genmax_languages_done(self):
        self._pv_genmax_languages_loading = False

    def _pv_genmax_voice_is_vietnamese(self, data: dict) -> bool:
        haystack = " ".join(str(data.get(k, "")) for k in ("name", "language", "description", "labels")).lower()
        return any(token in haystack for token in ("việt", "viet", "vietnam", "tiếng việt"))

    def _pv_apply_genmax_preset_defaults(self, voice_id: str = "", name: str = ""):
        if hasattr(self, "_pv_gm_provider"):
            self._pv_gm_provider.setCurrentText("elevenlabs")
        if hasattr(self, "_pv_gm_model"):
            self._pv_gm_model.setCurrentText("eleven_v3")
        if hasattr(self, "_pv_gm_language") and self._pv_genmax_voice_is_vietnamese({"id": voice_id, "name": name}):
            self._pv_set_combo_values(
                self._pv_gm_language,
                [("Vietnamese (vi)", "vi"), ("English (en)", "en")],
                "vi",
            )

    def _pv_genmax_saved_voice_ids(self) -> list[str]:
        ids = []
        current = getattr(self, "_pv_voices", {}).get("genmax", _NullEdit()).text().strip()
        if current:
            ids.append(current)
        for item in self._pv_voice_presets().get("genmax", []):
            if not isinstance(item, dict):
                continue
            voice_id = item.get("id", "").strip()
            if voice_id and voice_id not in ids:
                ids.append(voice_id)
        return ids

    def _pv_genmax_saved_voice_names(self) -> list[str]:
        names = []
        for item in self._pv_voice_presets().get("genmax", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _pv_refresh_genmax_saved_voices(self):
        if not hasattr(self, "_pv_gm_voice_combo"):
            return
        current = getattr(self, "_pv_voices", {}).get("genmax", _NullEdit()).text().strip()
        self._pv_gm_voice_combo.blockSignals(True)
        self._pv_gm_voice_combo.clear()
        self._pv_gm_voice_combo.addItem("Chọn voice đã lưu…", "")
        selected_idx = 0

        items = []
        if current:
            items.append({"name": "Voice ID hiện tại", "id": current})
        for item in self._pv_voice_presets().get("genmax", []):
            if isinstance(item, dict) and item.get("id", "").strip():
                items.append({"name": item.get("name", "").strip() or item["id"], "id": item["id"].strip()})

        seen = set()
        for item in items:
            voice_id = item["id"]
            if voice_id in seen:
                continue
            seen.add(voice_id)
            self._pv_gm_voice_combo.addItem(item["name"], {"id": voice_id, "name": item["name"]})
            if voice_id == current:
                selected_idx = self._pv_gm_voice_combo.count() - 1

        if not seen:
            self._pv_gm_voice_combo.addItem("Chưa có voice GenMax đã lưu", "")
        self._pv_gm_voice_combo.setCurrentIndex(selected_idx)
        self._pv_gm_voice_combo.blockSignals(False)

    def _pv_load_genmax_catalog(self):
        api_key = getattr(self, "_pv_gm_key", _NullEdit()).text().strip()
        if not api_key:
            QMessageBox.warning(self, "Thiếu GenMax API Key", "Vào tab API để nhập GenMax key trước khi tải danh sách giọng.")
            return
        target_ids = self._pv_genmax_saved_voice_ids()
        if not target_ids:
            QMessageBox.warning(self, "Chưa có voice đã lưu", "Lưu hoặc paste ít nhất một GenMax Voice ID trước khi kiểm tra.")
            return

        self._pv_gm_load_btn.setEnabled(False)
        self._pv_gm_load_btn.setText("Đang kiểm…")
        self._pv_gm_voice_combo.blockSignals(True)
        self._pv_gm_voice_combo.clear()
        self._pv_gm_voice_combo.addItem("Đang kiểm tra voice đã lưu…", "")
        self._pv_gm_voice_combo.blockSignals(False)

        worker = _keep_preview_thread_alive(_GenMaxCatalogWorker(api_key, "auto", target_ids, self._pv_genmax_saved_voice_names()))
        worker.done.connect(lambda voices, languages, models, s=self: s._pv_safe_call(lambda: s._pv_on_genmax_catalog(voices, languages, models)))
        worker.error.connect(lambda msg, s=self: s._pv_safe_call(lambda: s._pv_on_genmax_catalog_error(msg)))
        self._pv_genmax_catalog_worker = worker
        worker.start()

    def _pv_on_genmax_catalog(self, voices: list, languages: list, models: list):
        self._pv_gm_load_btn.setEnabled(True)
        self._pv_gm_load_btn.setText("Kiểm tra")
        current_voice = self._pv_voices.get("genmax", _NullEdit()).text().strip()
        if not hasattr(self, "_pv_genmax_preview_urls"):
            self._pv_genmax_preview_urls = self._pv_load_genmax_preview_urls()

        self._pv_gm_voice_combo.blockSignals(True)
        self._pv_gm_voice_combo.clear()
        self._pv_gm_voice_combo.addItem("Chọn voice đã lưu…", "")
        selected_idx = 0
        for v in voices:
            voice_id = v.get("id", "")
            preview_url = v.get("preview", "")
            if voice_id and preview_url:
                self._pv_set_genmax_preview_url(voice_id, preview_url)
            label = v.get("name", "")
            provider = v.get("provider", "")
            lang = v.get("language", "")
            if provider:
                label = f"{label} · {provider}"
            if lang:
                label = f"{label} · {lang}"
            self._pv_gm_voice_combo.addItem(label, v)
            if v.get("id") == current_voice:
                selected_idx = self._pv_gm_voice_combo.count() - 1
        if not voices:
            self._pv_gm_voice_combo.addItem("Không tìm thấy trong GenMax", "")
        self._pv_gm_voice_combo.setCurrentIndex(selected_idx)
        self._pv_gm_voice_combo.blockSignals(False)
        if selected_idx > 0:
            self._pv_apply_genmax_voice(selected_idx)
            if getattr(self, "_pv_play_after_genmax_catalog", False):
                current_after = self._pv_voices.get("genmax", _NullEdit()).text().strip()
                if not self._pv_genmax_preview_urls.get(current_after):
                    self._pv_play_after_genmax_catalog = False
                    self._pv_voice_preview_btn.setEnabled(True)
                    self._pv_voice_preview_btn.setText("▶")
                    QMessageBox.warning(
                        self,
                        "Không có sample GenMax",
                        "GenMax tìm thấy voice này nhưng không trả về sample nghe thử. App sẽ không tự render TTS thay thế.",
                    )
        elif getattr(self, "_pv_play_after_genmax_catalog", False):
            self._pv_play_after_genmax_catalog = False
            self._pv_voice_preview_btn.setEnabled(True)
            self._pv_voice_preview_btn.setText("▶")
            QMessageBox.warning(
                self,
                "Không có sample GenMax",
                "GenMax không trả về sample nghe thử cho Voice ID này. App sẽ không tự render TTS thay thế.",
            )

        current_lang = self._pv_genmax_language()
        lang_values = self._pv_genmax_language_values_from_api(languages)
        self._pv_genmax_api_language_values = lang_values
        self._pv_set_genmax_language_choices(lang_values, current_lang or "vi")

        current_model = self._pv_genmax_model()
        model_values = [(f"{i.get('name')} ({i.get('id')})" if i.get("name") != i.get("id") else i.get("id"), i.get("id")) for i in models]
        if model_values:
            self._pv_set_combo_values(self._pv_gm_model, model_values, current_model)

    def _pv_on_genmax_catalog_error(self, msg: str):
        self._pv_gm_load_btn.setEnabled(True)
        self._pv_gm_load_btn.setText("Kiểm tra")
        self._pv_play_after_genmax_catalog = False
        if hasattr(self, "_pv_voice_preview_btn"):
            self._pv_voice_preview_btn.setEnabled(True)
            self._pv_voice_preview_btn.setText("▶")
        self._pv_refresh_genmax_saved_voices()
        detail = str(msg)
        if "NameResolutionError" in detail or "Failed to resolve" in detail or "Max retries exceeded" in detail:
            detail = "Không kết nối được api.genmax.io. Kiểm tra mạng/DNS rồi bấm Kiểm tra lại."
        QMessageBox.warning(self, "Không tải được GenMax", detail)

    def _pv_apply_genmax_voice(self, idx: int):
        if idx <= 0:
            return
        data = self._pv_gm_voice_combo.itemData(idx)
        if not isinstance(data, dict):
            return
        voice_id = data.get("id", "")
        if voice_id:
            self._pv_voices.get("genmax", _NullEdit()).setText(voice_id)

        provider = data.get("provider", "")
        if provider in ("elevenlabs", "minimax") and hasattr(self, "_pv_gm_provider"):
            self._pv_gm_provider.setCurrentText(provider)
        elif self._pv_genmax_voice_is_vietnamese(data) and hasattr(self, "_pv_gm_provider"):
            self._pv_gm_provider.setCurrentText("elevenlabs")

        model = data.get("model", "")
        if model and hasattr(self, "_pv_gm_model"):
            self._pv_gm_model.setCurrentText(model)
        elif self._pv_genmax_voice_is_vietnamese(data) and hasattr(self, "_pv_gm_model"):
            self._pv_gm_model.setCurrentText("eleven_v3")

        verified = data.get("verified_languages") or []
        preferred_lang = "vi" if self._pv_genmax_voice_is_vietnamese(data) and provider != "minimax" else ""
        if verified:
            current_lang = preferred_lang or self._pv_genmax_language()
            values = list(getattr(self, "_pv_genmax_api_language_values", []))
            for item in verified:
                code = item.get("code", "")
                name = item.get("name", code)
                label = f"{name} ({code})" if name and name != code else code
                values.append((label, code))
            if preferred_lang and all(value != preferred_lang for _, value in values):
                values.insert(0, ("Vietnamese (vi)", "vi"))
            self._pv_set_genmax_language_choices(values, current_lang or verified[0].get("code", "") or "vi")
            first_model = verified[0].get("model", "")
            if first_model:
                model_values = []
                seen_models = set()
                for item in verified:
                    model_id = item.get("model", "")
                    if model_id and model_id not in seen_models:
                        seen_models.add(model_id)
                        model_values.append((model_id, model_id))
                if model_values:
                    self._pv_set_combo_values(self._pv_gm_model, model_values, first_model)
                else:
                    self._pv_gm_model.setCurrentText(first_model)
        elif data.get("language"):
            self._pv_set_genmax_language_choices([], data["language"])
        elif preferred_lang:
            self._pv_set_genmax_language_choices([], "vi")

        preview_url = data.get("preview", "")
        if voice_id and preview_url:
            self._pv_set_genmax_preview_url(voice_id, preview_url)
            if getattr(self, "_pv_play_after_genmax_catalog", False):
                self._pv_play_after_genmax_catalog = False
                self._pv_download_genmax_preview(voice_id, preview_url, play_after=True)
            else:
                self._pv_download_genmax_preview(voice_id, preview_url, play_after=False)

    def _pv_voice_presets(self) -> dict:
        presets = self.settings.setdefault("av_voice_presets", {})
        if not isinstance(presets, dict):
            presets = {}
            self.settings["av_voice_presets"] = presets
        return presets

    def _pv_seed_selected_elevenlabs_voice(self):
        voice_id = self.settings.get("selected_voice_id", "").strip()
        if not voice_id:
            return
        name = self.settings.get("selected_voice_name", "").strip() or "ElevenLabs voice"
        presets = self._pv_voice_presets().setdefault("elevenlabs", [])
        if not isinstance(presets, list):
            presets = []
            self._pv_voice_presets()["elevenlabs"] = presets
        if any(isinstance(p, dict) and p.get("id", "").strip() == voice_id for p in presets):
            return
        presets.append({"name": name, "id": voice_id})
        self._pv_save_voice_presets_now()

    def _pv_save_voice_presets_now(self):
        try:
            save_settings(self.settings)
        except Exception as e:
            QMessageBox.warning(self, "Lỗi lưu giọng", f"Không lưu được danh sách giọng đã lưu:\n{e}")

    def _pv_refresh_voice_presets(self):
        if not hasattr(self, "_pv_voice_preset_combo"):
            return
        provider = self._pv_current_provider()
        items = self._pv_voice_presets().setdefault(provider, [])
        current_voice = self._pv_current_voice_edit().text().strip()

        self._pv_voice_preset_combo.blockSignals(True)
        self._pv_voice_preset_combo.clear()
        self._pv_voice_preset_combo.addItem("Chọn giọng đã lưu…", "")
        selected_idx = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip()
            voice_id = item.get("id", "").strip()
            if not voice_id:
                continue
            self._pv_voice_preset_combo.addItem(name or voice_id, voice_id)
            if voice_id == current_voice:
                selected_idx = self._pv_voice_preset_combo.count() - 1
        self._pv_voice_preset_combo.setCurrentIndex(selected_idx)
        self._pv_voice_preset_combo.blockSignals(False)
        if provider == "genmax":
            self._pv_refresh_genmax_saved_voices()

    def _pv_apply_voice_preset(self, idx: int):
        if idx <= 0:
            return
        voice_id = self._pv_voice_preset_combo.itemData(idx) or ""
        if voice_id:
            self._pv_current_voice_edit().setText(voice_id)
            if self._pv_current_provider() == "genmax":
                self._pv_apply_genmax_preset_defaults(voice_id, self._pv_voice_preset_combo.currentText().strip())
                self._pv_refresh_genmax_saved_voices()
                if getattr(self, "_pv_genmax_preview_urls", {}).get(voice_id):
                    QTimer.singleShot(250, self._pv_prefetch_current_voice_preview)
            else:
                QTimer.singleShot(250, self._pv_prefetch_current_voice_preview)

    def _pv_add_voice_preset(self):
        provider = self._pv_current_provider()
        dlg = QDialog(self)
        dlg.setWindowTitle("Thêm giọng")
        dlg.setFixedSize(420, 190)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        title = QLabel(f"Thêm giọng cho {provider}")
        title.setStyleSheet("font-size:14px;font-weight:600;color:#1d1d1f;background:transparent;")
        v.addWidget(title)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Tên dễ nhớ, ví dụ: Sarah / Nam trầm / Review")
        name_edit.setStyleSheet(
            "QLineEdit{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:7px;padding:6px 10px;font-size:13px;}"
        )
        v.addWidget(name_edit)

        id_edit = QLineEdit(self._pv_current_voice_edit().text().strip())
        id_edit.setPlaceholderText("Voice ID")
        id_edit.setStyleSheet(
            "QLineEdit{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:7px;padding:6px 10px;font-size:13px;}"
        )
        v.addWidget(id_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(28)
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Lưu")
        btn_ok.setFixedHeight(28)
        btn_ok.setDefault(True)
        btn_ok.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:6px;padding:0 16px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
        )
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        v.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        voice_id = id_edit.text().strip()
        if not voice_id:
            QMessageBox.warning(self, "Thiếu Voice ID", "Nhập Voice ID trước khi lưu giọng.")
            return

        name = name_edit.text().strip() or voice_id

        presets = self._pv_voice_presets().setdefault(provider, [])
        presets[:] = [
            p for p in presets
            if isinstance(p, dict) and p.get("id", "").strip() != voice_id
        ]
        presets.append({"name": name, "id": voice_id})
        self._pv_current_voice_edit().setText(voice_id)
        self._pv_save_voice_presets_now()
        self._pv_refresh_voice_presets()
        if provider == "genmax":
            self._pv_refresh_genmax_saved_voices()
            if getattr(self, "_pv_genmax_preview_urls", {}).get(voice_id):
                QTimer.singleShot(250, self._pv_prefetch_current_voice_preview)
            elif getattr(self, "_pv_gm_key", _NullEdit()).text().strip():
                self._pv_play_after_genmax_catalog = False
                QTimer.singleShot(150, self._pv_load_genmax_catalog)
        else:
            QTimer.singleShot(250, self._pv_prefetch_current_voice_preview)

    def _pv_delete_voice_preset(self):
        idx = self._pv_voice_preset_combo.currentIndex()
        if idx <= 0:
            return
        provider = self._pv_current_provider()
        voice_id = self._pv_voice_preset_combo.itemData(idx) or ""
        presets = self._pv_voice_presets().setdefault(provider, [])
        presets[:] = [
            p for p in presets
            if not isinstance(p, dict) or p.get("id", "").strip() != voice_id
        ]
        self._pv_save_voice_presets_now()
        self._pv_refresh_voice_presets()
        if provider == "genmax":
            self._pv_refresh_genmax_saved_voices()

    def _pv_preview_voice(self):
        cfg = self._pv_preview_config()
        provider = cfg["provider"]
        voice_id = cfg["voice_id"]
        api_key = cfg["api_key"]

        if not voice_id:
            QMessageBox.warning(self, "Thiếu Voice ID", "Nhập hoặc chọn Voice ID trước khi nghe thử.")
            return

        if hasattr(self, "_pv_preview_proc") and self._pv_preview_proc and self._pv_preview_proc.poll() is None:
            self._pv_preview_proc.terminate()
            self._pv_voice_preview_btn.setText("▶")
            return

        if not hasattr(self, "_pv_preview_player"):
            self._pv_preview_audio = QAudioOutput()
            self._pv_preview_audio.setVolume(1.0)
            self._pv_preview_player = QMediaPlayer()
            self._pv_preview_player.setAudioOutput(self._pv_preview_audio)
            self._pv_preview_player.playbackStateChanged.connect(self._pv_on_preview_state)

        if self._pv_preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._pv_preview_player.stop()
            self._pv_voice_preview_btn.setText("▶")
            return

        cache_path = self._pv_preview_cache_path(cfg)
        if cache_path.exists():
            self._pv_play_preview_file(str(cache_path))
            return

        if not api_key:
            QMessageBox.warning(self, "Thiếu API Key", "Vào tab API để nhập key của provider trước khi nghe thử.")
            return

        if provider == "genmax" and not cfg.get("preview_url"):
            self._pv_voice_preview_btn.setEnabled(True)
            self._pv_voice_preview_btn.setText("▶")
            if getattr(self, "_pv_gm_key", _NullEdit()).text().strip():
                self._pv_play_after_genmax_catalog = True
                self._pv_voice_preview_btn.setEnabled(False)
                self._pv_voice_preview_btn.setText("…")
                self._pv_load_genmax_catalog()
                return
            QMessageBox.warning(
                self,
                "Chưa có file nghe thử",
                "Giọng GenMax này chưa được tải sẵn sample. Bấm Kiểm tra một lần để tải sample từ GenMax về máy.",
            )
            return

        self._pv_voice_preview_btn.setEnabled(False)
        self._pv_voice_preview_btn.setText("…")
        if cfg.get("preview_url"):
            worker = _keep_preview_thread_alive(_VoicePreviewUrlDownloadWorker(cfg["preview_url"], str(cache_path)))
            worker.done.connect(lambda path, s=self: s._pv_safe_call(lambda: s._pv_play_preview_file(path)))
            if provider == "genmax":
                worker.error.connect(lambda msg, s=self: s._pv_safe_call(lambda: s._pv_preview_error(f"Không tải được sample nghe thử từ GenMax: {msg}")))
            else:
                worker.error.connect(lambda _msg, c=cfg, p=cache_path, s=self: s._pv_safe_call(lambda: s._pv_start_generated_preview(c, p)))
            self._pv_preview_worker = worker
            worker.start()
            return
        self._pv_start_generated_preview(cfg, cache_path)

    def _pv_download_genmax_preview(self, voice_id: str, preview_url: str, play_after: bool = False):
        cfg = self._pv_preview_config()
        cfg["provider"] = "genmax"
        cfg["voice_id"] = voice_id
        cfg["preview_url"] = preview_url
        cache_path = self._pv_preview_cache_path(cfg)
        if cache_path.exists():
            if play_after:
                self._pv_play_preview_file(str(cache_path))
            return
        key = str(cache_path)
        active = getattr(self, "_pv_prefetch_workers", {})
        if key in active and not play_after:
            return
        worker = _keep_preview_thread_alive(_VoicePreviewUrlDownloadWorker(preview_url, str(cache_path)))
        if not hasattr(self, "_pv_prefetch_workers"):
            self._pv_prefetch_workers = {}
        if not play_after:
            self._pv_prefetch_workers[key] = worker
        worker.done.connect(lambda path, k=key, p=play_after, s=self: s._pv_safe_call(lambda: (s._pv_prefetch_workers.pop(k, None), s._pv_play_preview_file(path) if p else None)))
        worker.error.connect(lambda msg, k=key, p=play_after, s=self: s._pv_safe_call(lambda: (s._pv_prefetch_workers.pop(k, None), s._pv_preview_error(f"Không tải được sample nghe thử từ GenMax: {msg}") if p else None)))
        worker.start()
        if play_after:
            self._pv_preview_worker = worker

    def _pv_start_generated_preview(self, cfg: dict, cache_path: Path):
        worker = _keep_preview_thread_alive(_PipelineVoicePreviewWorker(
            cfg["provider"],
            cfg["api_key"],
            cfg["voice_id"],
            cfg["genmax_provider"],
            cfg["genmax_model"],
            cfg["genmax_language"],
            cfg["eleven_v3_style_enabled"],
            cfg["lucylab_endpoint"],
            str(cache_path),
            cfg["ai33_model"],
            cfg["ai33_endpoint"],
            cfg["ai33_output_format"],
        ))
        worker.done.connect(lambda path, s=self: s._pv_safe_call(lambda: s._pv_play_preview_file(path)))
        worker.error.connect(lambda msg, s=self: s._pv_safe_call(lambda: s._pv_preview_error(msg)))
        self._pv_preview_worker = worker
        worker.start()

    def _pv_preview_config(self) -> dict:
        provider = self._pv_current_provider()
        voice_id = self._pv_current_voice_edit().text().strip()
        if provider == "ai33" and not voice_id:
            voice_id = getattr(self, "_pv_voices", {}).get("genmax", _NullEdit()).text().strip()
        key_map = {
            "genmax": getattr(self, "_pv_gm_key", _NullEdit()).text().strip(),
            "ai33": getattr(self, "_pv_ai33_key", _NullEdit()).text().strip(),
            "elevenlabs": getattr(self, "_pv_el_key", _NullEdit()).text().strip(),
            "lucylab": getattr(self, "_pv_ll_key", _NullEdit()).text().strip(),
        }
        return {
            "provider": provider,
            "voice_id": voice_id,
            "api_key": key_map.get(provider, ""),
            "genmax_provider": (
                getattr(self, "_pv_gm_provider", _NullEdit()).currentText().strip()
                if hasattr(getattr(self, "_pv_gm_provider", None), "currentText") else "elevenlabs"
            ),
            "genmax_model": self._pv_genmax_model() or "eleven_v3",
            "genmax_language": self._pv_genmax_language() or "vi",
            "eleven_v3_style_enabled": (
                getattr(self, "_pv_eleven_v3_style_enabled", None) is None
                or self._pv_eleven_v3_style_enabled.isChecked()
            ),
            "lucylab_endpoint": getattr(self, "_pv_ll_endpoint", _NullEdit()).text().strip() or "https://api.lucylab.io/json-rpc",
            "ai33_model": getattr(self, "_pv_ai33_model", _NullEdit()).text().strip() or "eleven_v3",
            "ai33_endpoint": getattr(self, "_pv_ai33_endpoint", _NullEdit()).text().strip() or "https://api.ai33.pro",
            "ai33_output_format": getattr(self, "_pv_ai33_output_format", _NullEdit()).text().strip() or "mp3_44100_128",
            "preview_url": getattr(self, "_pv_genmax_preview_urls", {}).get(voice_id, "") if provider == "genmax" else "",
        }

    def _pv_preview_cache_path(self, cfg: dict) -> Path:
        if cfg.get("provider") == "genmax" and cfg.get("voice_id") and cfg.get("preview_url"):
            digest = hashlib.sha256(cfg["voice_id"].encode("utf-8")).hexdigest()[:24]
            return DATA_DIR / "voice_preview_cache" / f"genmax-{digest}.wav"
        raw = "|".join([
            cfg.get("provider", ""),
            cfg.get("voice_id", ""),
            cfg.get("api_key", ""),
            cfg.get("genmax_provider", ""),
            cfg.get("genmax_model", ""),
            cfg.get("genmax_language", ""),
            "style-on" if cfg.get("eleven_v3_style_enabled", True) else "style-off",
            cfg.get("lucylab_endpoint", ""),
            cfg.get("ai33_model", ""),
            cfg.get("ai33_endpoint", ""),
            cfg.get("ai33_output_format", ""),
            cfg.get("preview_url", ""),
            "hedra-preview-v2",
        ])
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return DATA_DIR / "voice_preview_cache" / f"{cfg.get('provider', 'voice')}-{digest}.mp3"

    def _pv_prefetch_current_voice_preview(self):
        cfg = self._pv_preview_config()
        if not cfg["voice_id"] or not cfg["api_key"]:
            return
        cache_path = self._pv_preview_cache_path(cfg)
        if cache_path.exists():
            return
        if cfg["provider"] == "genmax" and not cfg.get("preview_url"):
            return
        key = str(cache_path)
        active = getattr(self, "_pv_prefetch_workers", {})
        if key in active:
            return
        if cfg.get("preview_url"):
            worker = _keep_preview_thread_alive(_VoicePreviewUrlDownloadWorker(cfg["preview_url"], str(cache_path)))
            if not hasattr(self, "_pv_prefetch_workers"):
                self._pv_prefetch_workers = {}
            self._pv_prefetch_workers[key] = worker
            worker.done.connect(lambda _path, k=key, s=self: s._pv_safe_call(lambda: s._pv_prefetch_workers.pop(k, None)))
            worker.error.connect(lambda _msg, k=key, s=self: s._pv_safe_call(lambda: s._pv_prefetch_workers.pop(k, None)))
            worker.start()
            return
        worker = _keep_preview_thread_alive(_PipelineVoicePreviewWorker(
            cfg["provider"],
            cfg["api_key"],
            cfg["voice_id"],
            cfg["genmax_provider"],
            cfg["genmax_model"],
            cfg["genmax_language"],
            cfg["eleven_v3_style_enabled"],
            cfg["lucylab_endpoint"],
            str(cache_path),
            cfg["ai33_model"],
            cfg["ai33_endpoint"],
            cfg["ai33_output_format"],
        ))
        if not hasattr(self, "_pv_prefetch_workers"):
            self._pv_prefetch_workers = {}
        self._pv_prefetch_workers[key] = worker
        worker.done.connect(lambda _path, k=key, s=self: s._pv_safe_call(lambda: s._pv_prefetch_workers.pop(k, None)))
        worker.error.connect(lambda _msg, k=key, s=self: s._pv_safe_call(lambda: s._pv_prefetch_workers.pop(k, None)))
        worker.start()

    def _pv_play_preview_file(self, path: str):
        self._pv_voice_preview_btn.setEnabled(True)
        self._pv_voice_preview_btn.setText("■")
        if os.name == "posix" and shutil.which("afplay"):
            try:
                self._pv_preview_proc = subprocess.Popen(["afplay", path])
                QTimer.singleShot(500, self._pv_check_afplay_preview)
                return
            except Exception:
                self._pv_preview_proc = None
        self._pv_preview_player.setSource(QUrl.fromLocalFile(path))
        self._pv_preview_player.play()

    def _pv_check_afplay_preview(self):
        proc = getattr(self, "_pv_preview_proc", None)
        if proc and proc.poll() is None:
            QTimer.singleShot(500, self._pv_check_afplay_preview)
            return
        if hasattr(self, "_pv_voice_preview_btn"):
            self._pv_voice_preview_btn.setEnabled(True)
            self._pv_voice_preview_btn.setText("▶")

    def _pv_preview_error(self, msg: str):
        self._pv_voice_preview_btn.setEnabled(True)
        self._pv_voice_preview_btn.setText("▶")
        QMessageBox.warning(self, "Không nghe thử được", msg)

    def _pv_on_preview_state(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState and hasattr(self, "_pv_voice_preview_btn"):
            self._pv_voice_preview_btn.setEnabled(True)
            self._pv_voice_preview_btn.setText("▶")

    def _pv_local_avatar_path(self) -> Path | None:
        assets = _engine_assets_dir()
        logo = assets / "logo.svg"
        if logo.exists():
            return logo
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = assets / f"avatar{ext}"
            if p.exists():
                return p
        return None

    def _pv_editable_logo_path(self) -> Path | None:
        assets = _engine_assets_dir()
        png = assets / "avatar.png"
        if png.exists():
            return png
        for ext in (".jpg", ".jpeg", ".webp"):
            p = assets / f"avatar{ext}"
            if p.exists():
                return p
        return self._pv_local_avatar_path()

    def _pv_update_tiktok_preview(self):
        if not hasattr(self, "_pv_tt_preview_name"):
            return
        name = self._pv_tt_name.text().strip() or "Hedra Central"
        badge = self._pv_tt_badge.text().strip()
        tagline = self._pv_tt_tagline.text().strip() or "TIN CRYPTO 24H"
        handle = self._pv_tt_handle.text().strip() or "@hedracentral"
        bio = self._pv_tt_followers.text().strip() or "Follow for more"

        self._pv_tt_preview_name.setText(name)
        self._pv_tt_preview_handle.setText(handle)
        self._pv_tt_preview_bio.setText(bio)
        self._pv_tt_banner_name.setText(name)
        banner_parts = [p for p in (badge.upper(), tagline.upper()) if p]
        self._pv_tt_banner_tagline.setText("  ·  ".join(banner_parts))

        pix = QPixmap()
        avatar_url = self._pv_tt_avatar_url.text().strip()
        local_avatar = None if avatar_url else self._pv_local_avatar_path()
        if local_avatar:
            pix.load(str(local_avatar))

        if pix.isNull():
            for label, size in ((self._pv_tt_avatar_preview, 62), (self._pv_tt_banner_avatar, 58)):
                label.setText(name[:1].upper())
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setPixmap(QPixmap())
                label.setStyleSheet(
                    f"QLabel{{background:#121a22;border:2px solid #3b4148;border-radius:{size//2}px;"
                    "font-size:22px;font-weight:800;color:#f8c847;}}"
                )
        else:
            for label, size in ((self._pv_tt_avatar_preview, 62), (self._pv_tt_banner_avatar, 58)):
                label.setText("")
                label.setPixmap(_round_logo_pixmap(pix, size))
                label.setStyleSheet(
                    f"QLabel{{background:transparent;border:none;border-radius:{size//2}px;}}"
                )

    def _pv_edit_tiktok_avatar(self):
        local_avatar = self._pv_editable_logo_path()
        if not local_avatar:
            QMessageBox.warning(self, "Chưa có logo PNG", "Chọn một file PNG trước, rồi bấm Căn lại nếu muốn chỉnh tiếp.")
            return
        src = QPixmap(str(local_avatar))
        if src.isNull():
            QMessageBox.warning(self, "Không đọc được logo", f"Không mở được file:\n{local_avatar}")
            return
        self._pv_open_logo_editor(src)

    def _pv_open_logo_editor(self, src: QPixmap):
        dlg = QDialog(self)
        dlg.setWindowTitle("Chỉnh logo/avatar")
        dlg.setFixedSize(380, 340)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        title = QLabel("Căn logo/avatar")
        title.setStyleSheet("font-size:14px;font-weight:700;color:#1d1d1f;background:transparent;")
        lay.addWidget(title)

        preview = QLabel()
        preview.setFixedSize(180, 180)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet("QLabel{background:#181a18;border:2px solid #3b4148;border-radius:90px;}")
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(preview)
        row.addStretch()
        lay.addLayout(row)

        zoom_label = QLabel("Zoom")
        zoom_label.setStyleSheet("font-size:11px;font-weight:600;color:#4b5563;background:transparent;")
        lay.addWidget(zoom_label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(20, 320)
        slider.setValue(100)
        lay.addWidget(slider)

        hint = QLabel("Logo tự căn giữa. Chỉ kéo Zoom nếu muốn phóng to hoặc thu nhỏ.")
        hint.setStyleSheet("font-size:12px;color:#6e6e73;background:transparent;")
        lay.addWidget(hint)

        def update_preview():
            preview.setPixmap(
                _round_logo_pixmap(
                    src,
                    180,
                    slider.value() / 100,
                )
            )

        slider.valueChanged.connect(update_preview)
        update_preview()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(30)
        btn_cancel.clicked.connect(dlg.reject)
        btn_save = QPushButton("Lưu logo")
        btn_save.setFixedHeight(30)
        btn_save.setDefault(True)
        btn_save.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:6px;padding:0 16px;font-size:13px;font-weight:600;}"
        )
        btn_save.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        assets = _engine_assets_dir()
        assets.mkdir(parents=True, exist_ok=True)
        dst = assets / "avatar.png"
        svg_dst = assets / "logo.svg"
        final = _render_logo_square(
            src,
            512,
            slider.value() / 100,
        )
        _backup_engine_logo_assets()
        if not final.save(str(dst), "PNG"):
            QMessageBox.warning(self, "Không lưu được logo", f"Không ghi được file:\n{dst}")
            return
        try:
            _write_logo_svg_from_png(dst, svg_dst)
        except Exception as e:
            QMessageBox.warning(self, "Không tạo được SVG", f"Đã lưu PNG nhưng không tạo được logo.svg:\n{e}")
            return
        for old in assets.glob("avatar.*"):
            if old != dst and old.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                try:
                    old.unlink()
                except Exception:
                    pass
        self._pv_tt_avatar_url.setText("")
        self._pv_update_tiktok_preview()

    def _pv_choose_tiktok_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn logo/avatar",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return

        src = Path(path)
        ext = src.suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            QMessageBox.warning(self, "File không hỗ trợ", "Chỉ chọn ảnh PNG, JPG, JPEG hoặc WebP. App sẽ tự tạo avatar.png và logo.svg.")
            return

        pix = QPixmap(str(src))
        if pix.isNull():
            QMessageBox.warning(self, "Không đọc được logo", f"Không mở được file ảnh:\n{src}")
            return
        self._pv_open_logo_editor(pix)

    def _build(self):
        # ── Root layout: sidebar + content ────────────────────────
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar (Apple macOS System Settings style) ───────────
        # Tile icons có màu (giống Ventura+ System Settings) — sections
        # phân tách bằng khoảng trống nhẹ, không cần section label text.
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"QWidget{{background:{self._SB_BG};}}")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(10, 16, 10, 12)
        sb_layout.setSpacing(2)

        # Nav items nhóm theo Apple HIG (foundation → content → production).
        # Mỗi nhóm = một list; thứ tự FLAT phải khớp với thứ tự pages bên dưới.
        nav_sections = [
            # Tài khoản & kết nối — cài 1 lần
            [
                ("api", "API", "API", "Khóa dịch vụ dùng chung cho toàn bộ app."),
            ],
            # Nội dung sáng tạo — dùng hằng ngày
            [
                ("prompts", "Prompts", "Prompts", "Prompt mặc định cho chat và TTS."),
                ("voices",  "Voices",  "Voices",  "Giọng đọc, provider TTS và preset nhanh."),
            ],
            # Sản xuất / xuất file
            [
                ("video",    "Auto Video", "Auto Video", "Kịch bản, sub, giao diện và render video."),
                ("settings", "Chung",     "Chung",      "Thư mục xuất file và tuỳ chọn chung của app."),
            ],
        ]
        nav_items = [item for section in nav_sections for item in section]
        self._nav_meta = nav_items

        self._nav_btns: list[QPushButton] = []
        for section_idx, section in enumerate(nav_sections):
            if section_idx > 0:
                # Section divider: khoảng trống nhẹ kiểu Apple System Settings
                sb_layout.addSpacing(10)
            for icon, label, _title, _subtitle in section:
                btn = QPushButton(label)
                btn.setIcon(ui_icon(icon, 16, self._SB_TEXT))
                btn.setIconSize(icon_size(16))
                btn.setCheckable(True)
                btn.setFixedHeight(32)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    "QPushButton{text-align:left;border:none;border-radius:7px;"
                    "margin:0;padding:0 10px;font-size:13px;font-weight:500;"
                    f"color:{self._SB_TEXT};background:transparent;"
                    "}"
                    f"QPushButton:hover{{background:{CONTROL_HV};}}"
                    f"QPushButton:pressed{{background:{CONTROL_DN};}}"
                    f"QPushButton:checked{{background:{self._SB_ACTIVE};color:white;}}"
                )
                self._nav_btns.append(btn)
                sb_layout.addWidget(btn)

        sb_layout.addStretch()
        root.addWidget(sidebar)

        # ── Divider ────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"color:{BORDER_SOFT};")
        root.addWidget(div)

        # ── Content area ───────────────────────────────────────────
        content_wrapper = QWidget()
        content_wrapper.setStyleSheet(f"QWidget{{background:{SURFACE};}}")
        cw_layout = QVBoxLayout(content_wrapper)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.setSpacing(0)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget{background:transparent;}")

        # Thứ tự PHẢI khớp với nav_sections flat order ở trên:
        # 0=api, 1=prompts, 2=voices, 3=video(pipeline), 4=output
        pages = [self._page_api(), self._page_prompts(), self._page_voices(), self._page_pipeline(), self._page_output()]
        for p in pages:
            # Wrap mỗi page trong ScrollArea — không bao giờ tràn màn hình
            p.setMaximumWidth(724)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            scroll.setWidget(p)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet(
                f"QScrollArea{{background:{SURFACE};border:none;}}"
                "QScrollBar:vertical{width:6px;background:transparent;}"
                "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:3px;}"
            )
            self._stack.addWidget(scroll)

        cw_layout.addWidget(self._stack)

        # ── Footer: Hủy / Lưu ─────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"QWidget{{background:{SURFACE};"
            f"border-top:1px solid {BORDER_SOFT};}}"
        )
        footer.setFixedHeight(56)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(18, 11, 18, 11)
        fl.setSpacing(8)
        fl.addStretch()

        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setStyleSheet(
            f"QPushButton{{background:{CONTROL_BG};border:1px solid {BORDER};"
            f"border-radius:8px;padding:0 16px;font-size:13px;color:{TEXT};}}"
            f"QPushButton:hover{{background:{CONTROL_HV};}}"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Lưu")
        btn_save.setFixedHeight(32)
        btn_save.setDefault(True)
        btn_save.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:8px;padding:0 20px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
        )
        btn_save.clicked.connect(self._save_clicked)
        fl.addWidget(btn_cancel)
        fl.addWidget(btn_save)
        cw_layout.addWidget(footer)

        root.addWidget(content_wrapper)

        # ── Connect nav ────────────────────────────────────────────
        for i, btn in enumerate(self._nav_btns):
            btn.clicked.connect(lambda checked, idx=i: self._switch(idx))
        self._switch(0)

    def _switch(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == idx)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn output folder")
        if folder:
            self.out_dir.setText(folder)

    def _save_clicked(self):
        try:
            self._save()
        except Exception as e:
            try:
                with open(ERROR_LOG, "a", encoding="utf-8") as f:
                    f.write("Settings save failed:\n")
                    f.write("".join(traceback.format_exception(type(e), e, e.__traceback__)))
                    f.write("\n")
            except Exception:
                pass
            QMessageBox.critical(
                self,
                "Không lưu được Settings",
                f"Tool chưa lưu thay đổi vì gặp lỗi:\n\n{e}",
            )

    def _save(self):
        env = _read_env_local()

        def _widget_value(widget) -> str:
            if hasattr(widget, "currentText"):
                return widget.currentText().strip()
            if hasattr(widget, "text"):
                return widget.text().strip()
            if hasattr(widget, "toPlainText"):
                return widget.toPlainText().strip()
            return ""

        el_value = _widget_value(getattr(self, "el_keys", _NullEdit())).strip()
        if "\n" in el_value:
            raw_keys = el_value.splitlines()
        elif el_value:
            existing_extra = [
                k.strip()
                for k in self.settings.get("el_api_keys", [])[1:]
                if k.strip() and k.strip() != el_value
            ]
            raw_keys = [el_value] + existing_extra
        else:
            raw_keys = []
        self.settings["el_api_keys"] = [k.strip() for k in raw_keys if k.strip()][:3]

        def _merged_key(name: str, api_widget, pipeline_widget) -> str:
            api_value = _widget_value(api_widget)
            pipeline_value = _widget_value(pipeline_widget)
            initial = getattr(self, "_api_initial_keys", {}).get(name, "")
            return api_value if api_value != initial else (pipeline_value or api_value)

        pipeline_gm_key = _merged_key("genmax", getattr(self, "genmax_key", _NullEdit()), getattr(self, "_pv_gm_key", _NullEdit()))
        pipeline_ds_key = _merged_key("deepseek", getattr(self, "ds_key", _NullEdit()), getattr(self, "_pv_deepseek_key", _NullEdit()))
        pipeline_gemini_key = _merged_key("gemini", getattr(self, "gemini_key", _NullEdit()), getattr(self, "_pv_script_gemini_key", _NullEdit()))
        pipeline_claude_key = _merged_key("claude", getattr(self, "claude_key", _NullEdit()), getattr(self, "_pv_claude_key", _NullEdit()))
        pipeline_claude_model = _merged_key("claude_model", getattr(self, "claude_model", _NullEdit()), getattr(self, "_pv_claude_model", _NullEdit()))
        pipeline_claude_model = (
            pipeline_claude_model
            or (
            getattr(self, "_pv_claude_model", _NullEdit()).currentText().strip()
            if hasattr(getattr(self, "_pv_claude_model", None), "currentText")
            else ""
            )
        )
        self.settings["genmax_api_key"]     = pipeline_gm_key
        self.settings["ds_api_key"]         = pipeline_ds_key or self.ds_key.text().strip()
        self.settings["gemini_api_key"]     = pipeline_gemini_key or self.gemini_key.text().strip()
        self.settings["claude_api_key"]     = pipeline_claude_key or getattr(self, "claude_key", _NullEdit()).text().strip()
        self.settings["claude_model"]       = (
            pipeline_claude_model
            or (self.claude_model.currentText() if hasattr(self, "claude_model") else RECOMMENDED_CLAUDE_MODEL)
        )
        self.settings["telegram_bot_token"] = getattr(self, "telegram_bot_token", _NullEdit()).text().strip()
        self.settings["telegram_chat_id"]   = getattr(self, "telegram_chat_id", _NullEdit()).text().strip()
        self.settings["output_dir"]         = self.out_dir.text()
        self.settings["auto_open_folder"]   = getattr(self, "_auto_open_folder", None) is not None and self._auto_open_folder.isChecked()
        self.settings["app_theme"]          = (
            self._app_theme.currentData()
            if hasattr(self, "_app_theme") and self._app_theme.currentData()
            else "system"
        )
        self._commit_current_prompt_style()
        gp = self.gemini_prompt.toPlainText().strip()
        self.settings["gemini_chat_prompt"] = "" if gp == GEMINI_CHAT_PROMPT.strip() else gp
        # Voice selection
        self.settings["selected_voice_id"]   = self._sel_voice_id
        self.settings["selected_voice_name"] = self._sel_voice_name
        self.settings["shared_voice_enabled"] = (
            hasattr(self, "_shared_voice_enabled")
            and self._shared_voice_enabled.isChecked()
        )
        # AV voice is selected in the main Auto Video toolbar. Settings should
        # preserve that choice and only use it to fill an empty provider field.
        _av_voice = (
            self.settings.get("av_voice_id", "").strip()
            or getattr(self, "_av_sel_id", "").strip()
        )
        _av_voice_name = (
            self.settings.get("av_voice_name", "").strip()
            or getattr(self, "_av_sel_name", "").strip()
        )
        self.settings["av_fav_voice_id"]   = _av_voice
        self.settings["av_fav_voice_name"] = _av_voice_name
        if _av_voice and hasattr(self, "_pv_voices"):
            provider_map = {
                "genmax": "genmax",
                "ai33": "ai33",
                "elevenlabs": "elevenlabs",
                "lucylab": "lucylab",
            }
            target_provider = self._pv_current_provider() if hasattr(self, "_pv_current_provider") else "genmax"
            target_key = provider_map.get(target_provider, "genmax")
            if target_key in self._pv_voices and not self._pv_voices[target_key].text().strip():
                self._pv_voices[target_key].setText(_av_voice)
            if "genmax" in self._pv_voices and not self._pv_voices["genmax"].text().strip():
                self._pv_voices["genmax"].setText(_av_voice)
        self.settings["eleven_v3_style_enabled"] = (
            getattr(self, "_pv_eleven_v3_style_enabled", None) is None
            or self._pv_eleven_v3_style_enabled.isChecked()
        )
        # Language code is managed from MainWindow's TTS tab — preserve existing

        # ── Auto Video pipeline — ghi thẳng vào .env.local ─────────
        if hasattr(self, "_pv_provider"):
            _providers = ["genmax", "ai33", "elevenlabs", "lucylab"]
            prov = _providers[self._pv_provider.currentIndex()]
            _write_env_local({
                "TTS_PROVIDER":        prov,
                "GENMAX_VOICE_ID":     getattr(self, "_pv_voices", {}).get("genmax",     _NullEdit()).text().strip(),
                "AI33_VOICE_ID":       getattr(self, "_pv_voices", {}).get("ai33",       _NullEdit()).text().strip(),
                "ELEVENLABS_VOICE_ID": getattr(self, "_pv_voices", {}).get("elevenlabs", _NullEdit()).text().strip(),
                "VIETNAMESE_VOICEID":  getattr(self, "_pv_voices", {}).get("lucylab",    _NullEdit()).text().strip(),
                "GENMAX_PROVIDER":     getattr(self, "_pv_gm_provider", _NullEdit()).currentText().strip()
                                       if hasattr(getattr(self, "_pv_gm_provider", None), "currentText") else "elevenlabs",
                "GENMAX_MODEL_ID":     self._pv_genmax_model(),
                "GENMAX_LANGUAGE_CODE": self._pv_genmax_language(),
                "ELEVEN_V3_STYLE_ENABLED": "true" if getattr(self, "_pv_eleven_v3_style_enabled", None) is None
                                           or self._pv_eleven_v3_style_enabled.isChecked() else "false",
                "GENMAX_FALLBACK_TO_AI33": "true" if getattr(self, "_pv_genmax_fallback_ai33", None) is None
                                           or self._pv_genmax_fallback_ai33.isChecked() else "false",
                "GENMAX_API_KEY":      pipeline_gm_key,
                "GENMAX_POLL_TIMEOUT_MS": "90000",
                "GENMAX_MAX_RETRIES": "3",
                "AI33_API_KEY":        getattr(self, "_pv_ai33_key", _NullEdit()).text().strip(),
                "AI33_MODEL_ID":       getattr(self, "_pv_ai33_model", _NullEdit()).text().strip() or "eleven_v3",
                "AI33_ENDPOINT":       getattr(self, "_pv_ai33_endpoint", _NullEdit()).text().strip() or "https://api.ai33.pro",
                "AI33_OUTPUT_FORMAT":  getattr(self, "_pv_ai33_output_format", _NullEdit()).text().strip() or "mp3_44100_128",
                "AI33_POLL_INTERVAL_MS": "2000",
                "AI33_POLL_TIMEOUT_MS": "300000",
                "ELEVENLABS_API_KEY":  getattr(self, "_pv_el_key",  _NullEdit()).text().strip(),
                "ELEVENLABS_MODEL_ID":  getattr(self, "_pv_el_model", _NullEdit()).text().strip(),
                "VIETNAMESE_API_KEY":  getattr(self, "_pv_ll_key",  _NullEdit()).text().strip(),
                "LUCYLAB_ENDPOINT":     getattr(self, "_pv_ll_endpoint", _NullEdit()).text().strip(),
                "TIKTOK_DISPLAY_NAME": getattr(self, "_pv_tt_name",      _NullEdit()).text().strip(),
                "TIKTOK_BADGE_LABEL":  getattr(self, "_pv_tt_badge",     _NullEdit()).text().strip(),
                "TIKTOK_TAGLINE":      getattr(self, "_pv_tt_tagline",   _NullEdit()).text().strip(),
                "TIKTOK_HANDLE":       getattr(self, "_pv_tt_handle",    _NullEdit()).text().strip(),
                "TIKTOK_FOLLOWERS":    getattr(self, "_pv_tt_followers", _NullEdit()).text().strip(),
                "TIKTOK_AVATAR_URL":   getattr(self, "_pv_tt_avatar_url", _NullEdit()).text().strip(),
                "SHOW_SOURCE_LINK":    "true" if getattr(self, "_pv_show_source_link", None) is None
                                       or self._pv_show_source_link.isChecked() else "false",
                "AUTO_VIDEO_SCRIPT_PRESET": env.get("AUTO_VIDEO_SCRIPT_PRESET", "ai_news_fast"),
                "AUTO_VIDEO_VISUAL_PRESET": env.get("AUTO_VIDEO_VISUAL_PRESET", "ai_news_dark"),
                "AUTO_VIDEO_EDITING_PACE": getattr(self, "_pv_auto_editing_pace", _NullEdit()).currentText().strip()
                                       if hasattr(getattr(self, "_pv_auto_editing_pace", None), "currentText") else "dynamic",
                "AUTO_VIDEO_BURN_CAPTIONS": "true" if getattr(self, "_pv_auto_burn_captions", None) is None
                                       or self._pv_auto_burn_captions.isChecked() else "false",
                "AUTO_VIDEO_CAPTION_MODE": getattr(self, "_pv_auto_caption_mode", _NullEdit()).currentText().strip()
                                       if hasattr(getattr(self, "_pv_auto_caption_mode", None), "currentText") else "word_transcript",
                "AUTO_VIDEO_CAPTION_STYLE": getattr(self, "_pv_auto_caption_style", _NullEdit()).currentText().strip()
                                       if hasattr(getattr(self, "_pv_auto_caption_style", None), "currentText") else "capcut_pop",
                "DEEPSEEK_API_KEY":    pipeline_ds_key,
                "GEMINI_API_KEY":      pipeline_gemini_key,
                "GEMINI_TEXT_MODEL":   getattr(self, "_pv_gemini_text_model", _NullEdit()).text().strip() or "gemini-2.5-flash",
                "CLAUDE_API_KEY":      pipeline_claude_key,
                "CLAUDE_MODEL":        pipeline_claude_model or RECOMMENDED_CLAUDE_MODEL,
            })

        save_settings(self.settings)
        self.accept()

    def get_settings(self) -> dict:
        return self.settings
