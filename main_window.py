import os
import sys
import subprocess
import webbrowser
import shlex
import re
import shutil
import json
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
    QTextEdit, QLabel, QLineEdit, QSlider, QPushButton, QFrame,
    QTabWidget, QScrollArea, QStackedWidget, QFileDialog,
    QMessageBox, QSizePolicy, QSpacerItem, QListWidget,
    QListWidgetItem, QMenu, QGridLayout, QComboBox, QDialog, QCheckBox, QToolButton,
    QAbstractButton,
    QStyledItemDelegate, QSplitter,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl, QSize, QRectF
from PyQt6.QtGui import QIcon, QFont, QAction, QPixmap, QColor, QPainter, QDesktopServices
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from app_constants import (
    VOICE_ID, MODEL, EL_OUTPUT_FORMAT, PROMPTS, PROMPT_TEMPLATES,
    VERSION, DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY, GEMINI_CHAT_PROMPT,
    BG, SURFACE, SURFACE_2, BORDER, BORDER_SOFT, TEXT, TEXT_MUTE, TEXT_FAINT,
    ACCENT, ACCENT_HV, ACCENT_DN, SEG_BG, CONTROL_BG, CONTROL_HV, CONTROL_DN, STYLE,
    SUCCESS, WARNING, DESTRUCTIVE, get_creativity_guide, get_style, apply_theme_globals,
)
from app_utils import (
    DATA_DIR, DEFAULT_OUT,
    get_auto_video_env_local, get_tool_output_dir, is_auto_video_unlocked, is_chat_script_unlocked, load_settings, reveal_file, save_settings,
    suggest_tts_filename, validate_pro_license_key, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, perf_log,
)
from app_workers import (
    Worker, _TTSOnlyWorker, PreviewWorker, GeminiWorker,
    UpdateChecker, UpdateDownloader, _CreditsChecker,
    SpeechToTextWorker, humanize_tts_error, words_to_srt,
)
from app_dialogs import AddStyleDialog, FeedbackDialog, DropZone
from app_icons import icon_size, ui_icon
from prompt_files import read_style_prompt_file, write_style_prompt_file
from settings_dialog import SettingsDialog, _read_env_local, _write_env_local
from auto_video_workers import (
    AutoScriptWorker, AutoVideoEngineWorker, OneShotAnalyzeWorker, OneShotRenderWorker,
    OneShotBatchWorker, OneShotTitleWorker, OneShotThumbnailPreviewWorker,
    _clean_thumbnail_title,
    _upload_video_output_path, _build_upload_metadata, _one_shot_exports_dir,
    whisper_runtime_status,
)
from oneshot_engine.simple_pipeline import build_simple_options, is_simple_pipeline
from oneshot_simple_worker import OneShotSimpleBatchWorker, OneShotSimpleRunWorker
# ── ElevenLabs multilingual v2 — full language list ───────────────
_ELEVENLABS_LANGS = [
    ("Tự động",          ""),
    ("Tiếng Việt",       "vi"),
    ("العربية",          "ar"),
    ("Български",        "bg"),
    ("中文",              "zh"),
    ("Hrvatski",         "hr"),
    ("Čeština",          "cs"),
    ("Dansk",            "da"),
    ("Nederlands",       "nl"),
    ("English",          "en"),
    ("Filipino",         "fil"),
    ("Suomi",            "fi"),
    ("Français",         "fr"),
    ("Deutsch",          "de"),
    ("Ελληνικά",         "el"),
    ("हिन्दी",            "hi"),
    ("Bahasa Indonesia", "id"),
    ("Italiano",         "it"),
    ("日本語",            "ja"),
    ("한국어",            "ko"),
    ("Bahasa Melayu",    "ms"),
    ("Polski",           "pl"),
    ("Português",        "pt"),
    ("Română",           "ro"),
    ("Русский",          "ru"),
    ("Slovenčina",       "sk"),
    ("Español",          "es"),
    ("Svenska",          "sv"),
    ("தமிழ்",            "ta"),
    ("Türkçe",           "tr"),
    ("Українська",       "uk"),
]

# ── Apple-style popup combo (frameless, rounded, no dark native border) ───
class _ApplePopupCombo(QComboBox):
    """QComboBox với popup kiểu Apple: frameless, bo góc, viền xám nhạt, không có frame đen của macOS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_styled = False

    def _popup_qss(self) -> str:
        return (
            f"QAbstractItemView{{background:{SURFACE};color:{TEXT};"
            f"border:1px solid {BORDER};border-radius:10px;padding:4px;outline:none;"
            f"selection-background-color:{CONTROL_HV};selection-color:{TEXT};}}"
            "QAbstractItemView::item{min-height:26px;padding:3px 12px;"
            f"border-radius:6px;color:{TEXT};}}"
            f"QAbstractItemView::item:hover{{background:{CONTROL_HV};color:{TEXT};}}"
            f"QAbstractItemView::item:selected{{background:{CONTROL_HV};color:{ACCENT};font-weight:600;}}"
        )

    def showPopup(self):
        view = self.view()
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setStyleSheet(self._popup_qss())
        container = view.window()
        container.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        container.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        container.setStyleSheet(
            "QFrame{background:transparent;border:none;}"
            f"QListView{{background:{SURFACE};border:1px solid {BORDER};border-radius:10px;}}"
        )
        self._popup_styled = True
        super().showPopup()


class _AppleSwitch(QAbstractButton):
    """Small macOS-style switch for binary settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 22)

    def sizeHint(self):
        return QSize(38, 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        checked = self.isChecked()
        enabled = self.isEnabled()

        track = QRectF(1, 2, 36, 18)
        track_color = QColor(ACCENT if checked else CONTROL_DN)
        if not enabled:
            track_color = QColor(CONTROL_BG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 9, 9)

        knob_x = 19 if checked else 3
        knob = QRectF(knob_x, 4, 14, 14)
        painter.setBrush(QColor("#ffffff" if enabled else TEXT_FAINT))
        painter.drawEllipse(knob)


# ── Main window ────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont("Arial"))
        self.setFont(QFont("Arial"))
        self.settings      = settings
        self._theme_mode   = self.settings.get("app_theme", "system")
        apply_theme_globals(globals(), self._theme_mode)
        self.worker        = None
        self.gemini_worker = None
        self._managed_threads = set()
        self._closing = False
        self._credits_worker = None
        self._credits_refresh_pending = False
        self._perf_started = time.perf_counter()
        self._os_log_buffer: list[str] = []
        self._os_log_dropped = 0
        self._os_log_last_flush = time.perf_counter()
        self._os_log_timer = QTimer(self)
        self._os_log_timer.setInterval(250)
        self._os_log_timer.timeout.connect(self._os_flush_log_buffer)
        self._av_log_buffer: list[str] = []
        self._av_log_last_flush = time.perf_counter()
        self._av_log_timer = QTimer(self)
        self._av_log_timer.setInterval(250)
        self._av_log_timer.timeout.connect(self._av_flush_log_buffer)
        self._last_status_update: dict[str, float] = {}
        self._last_progress_value: dict[str, int] = {}
        self._tts_scroll_syncing = False
        self._tts_splitter_save_timer = QTimer(self)
        self._tts_splitter_save_timer.setSingleShot(True)
        self._tts_splitter_save_timer.setInterval(300)
        self._tts_splitter_save_timer.timeout.connect(self._persist_tts_splitter_ratio)
        self.image_paths   = []
        self._parent_ref   = self          # self-ref cho _open_voices_settings
        self._output_audio = QAudioOutput()
        self._output_audio.setVolume(1.0)
        self._output_player = QMediaPlayer()
        self._output_player.setAudioOutput(self._output_audio)
        self._output_player.playbackStateChanged.connect(self._on_output_playback_state)
        self._output_player.positionChanged.connect(self._on_output_position_changed)
        self._output_player.durationChanged.connect(self._on_output_duration_changed)
        self.setWindowTitle(f"Hedra Studio  v{VERSION}")
        self.setMinimumSize(1160, 700)
        self.resize(1480, 820)
        self._apply_theme()
        # App icon
        try:
            root = os.path.dirname(__file__) if not getattr(sys, 'frozen', False) else sys._MEIPASS
            names = ("icon.ico", "icon.icns") if sys.platform == "win32" else ("icon.icns", "icon.ico")
            for name in names:
                icon_path = os.path.join(root, name)
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
                    break
        except Exception:
            pass
        self._build()
        perf_log("main_window_built", elapsed_ms=int((time.perf_counter() - self._perf_started) * 1000))
        self._refresh_credits()
        self._check_update()

    def _is_thread_running(self, worker) -> bool:
        if worker is None:
            return False
        try:
            return bool(worker.isRunning())
        except RuntimeError:
            return False

    def _should_throttle_ui(self, key: str, *, value: int | None = None, interval: float = 0.18) -> bool:
        now = time.perf_counter()
        last_t = float(self._last_status_update.get(key, 0.0))
        if value is not None and value in (0, 100):
            self._last_status_update[key] = now
            self._last_progress_value[key] = value
            return False
        if value is not None and self._last_progress_value.get(key) == value and now - last_t < interval:
            return True
        if now - last_t < interval:
            return True
        self._last_status_update[key] = now
        if value is not None:
            self._last_progress_value[key] = value
        return False

    def _track_thread(self, attr_name: str, worker, *, replace: bool = False):
        """Keep QThread wrappers alive until completion.

        Qt aborts the process if a QThread wrapper is destroyed while its
        native thread is still running. This helper gives every worker one
        owner, clears it only after completion/error, and avoids accidental
        overwrite of an active worker.
        """
        if self._closing:
            return None
        existing = getattr(self, attr_name, None)
        if self._is_thread_running(existing):
            if not replace:
                return existing
            self._stop_thread(existing, timeout_ms=800, terminate_after=True)
        setattr(self, attr_name, worker)
        self._managed_threads.add(worker)

        cleaned = {"done": False}

        def _cleanup(*_args, _worker=worker):
            if cleaned["done"]:
                return
            cleaned["done"] = True
            perf_log("worker_finish", attr=attr_name, worker=type(_worker).__name__)
            self._managed_threads.discard(_worker)
            if getattr(self, attr_name, None) is _worker:
                setattr(self, attr_name, None)

        try:
            worker.finished.connect(_cleanup)
        except Exception:
            pass
        try:
            worker.error.connect(_cleanup)
        except Exception:
            pass
        try:
            worker.start()
            perf_log("worker_start", attr=attr_name, worker=type(worker).__name__)
        except Exception:
            _cleanup()
            raise
        return worker

    def _stop_thread(self, worker, *, timeout_ms: int = 1500, terminate_after: bool = False) -> None:
        if not self._is_thread_running(worker):
            return
        try:
            worker.requestInterruption()
        except Exception:
            pass
        try:
            if hasattr(worker, "cancel"):
                worker.cancel()
        except Exception:
            pass
        try:
            worker.quit()
        except Exception:
            pass
        try:
            if worker.wait(timeout_ms):
                return
        except Exception:
            return
        if terminate_after and self._is_thread_running(worker):
            try:
                worker.terminate()
                worker.wait(1000)
            except Exception:
                pass

    def shutdown_workers(self) -> None:
        self._closing = True
        perf_log("shutdown_workers", workers=len(self._managed_threads))
        self._os_flush_log_buffer(force=True)
        self._av_flush_log_buffer(force=True)
        for worker in list(self._managed_threads):
            self._stop_thread(worker, timeout_ms=1200, terminate_after=True)
        self._managed_threads.clear()

    def closeEvent(self, event):
        app = QApplication.instance()
        if app is not None and app.property("_hedra_quitting"):
            self.shutdown_workers()
            event.accept()
            return
        self.hide()
        event.ignore()

    def _apply_theme(self):
        self._theme_mode = self.settings.get("app_theme", "system")
        apply_theme_globals(globals(), self._theme_mode)
        style = get_style(self._theme_mode)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(style)
        self.setStyleSheet(style)

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

    # ── Apple HIG helpers ─────────────────────────────────────────
    def _section_lbl(self, text: str) -> QLabel:
        """Section label — small caps, muted, Apple System Settings style."""
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; font-weight:700;"
            "letter-spacing:0.4px; padding:18px 0 7px 0;"
            "background:transparent; border:none;"
        )
        return lbl

    def _card(self) -> tuple:
        """White card — Apple System Settings style.
        Không có border — dùng contrast trắng-trên-xám để tạo ranh giới."""
        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget{{background:{SURFACE};"
            f"border:1px solid {BORDER_SOFT};"
            "border-radius:12px;}"
        )
        vbox = QVBoxLayout(outer)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        return outer, vbox

    def _card_row(self, container_vbox, label: str, widget: QWidget,
                  note: str = "", last: bool = False):
        """Form row trong card — 48px height, inset separator."""
        row_w = QWidget()
        row_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        row_w.setMinimumHeight(58)
        h = QHBoxLayout(row_w)
        h.setContentsMargins(18, 12, 18, 12)
        h.setSpacing(14)

        lbl = QLabel(label)
        lbl.setFixedWidth(126)
        lbl.setStyleSheet(
            f"QLabel{{font-size:13px;color:{TEXT};font-weight:500;"
            "background:transparent;border:none;}"
        )
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
        container_vbox.addWidget(row_w)

        # Inset separator
        if not last:
            sep_wrap = QWidget()
            sep_wrap.setFixedHeight(1)
            sep_wrap.setStyleSheet("background:transparent;border:none;")
            sep_h = QHBoxLayout(sep_wrap)
            sep_h.setContentsMargins(16, 0, 0, 0)
            sep_h.setSpacing(0)
            sep_line = QWidget()
            sep_line.setFixedHeight(1)
            sep_line.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
            sep_h.addWidget(sep_line)
            container_vbox.addWidget(sep_wrap)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _app_font(self, point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        font = QFont(QApplication.font())
        font.setPointSize(point_size)
        font.setWeight(weight)
        return font

    def _preview_status_style(self, tone: str = "idle") -> str:
        dark = str(getattr(self, "_theme_mode", "")).lower() == "dark"
        if dark:
            palette = {
                "idle": ("#2c2c2e", BORDER_SOFT, TEXT_MUTE),
                "processing": ("#3a2a10", "#7a4b00", "#ffd60a"),
                "success": ("#12351f", "#1f7a3a", "#7ee787"),
                "warning": ("#3a2a10", "#7a4b00", "#ffd60a"),
                "error": ("#3a1618", "#8f242b", "#ff8a80"),
            }
        else:
            palette = {
                "idle": ("#f5f5f7", BORDER_SOFT, TEXT_MUTE),
                "processing": ("#fff3cd", "#ffcc66", "#8a5a00"),
                "success": ("#e9f8ef", "#9be3ad", "#1f7a3a"),
                "warning": ("#fff3cd", "#ffcc66", "#8a5a00"),
                "error": ("#fff0f0", "#ffb3b3", "#c62828"),
            }
        bg, border, color = palette.get(tone, palette["idle"])
        return (
            "QLabel{"
            f"background:{bg};color:{color};border:1px solid {border};"
            "border-radius:9px;padding:8px 10px;"
            "font-size:13px;font-weight:700;"
            "}"
        )

    def _set_preview_status(self, msg: str, tone: str = "idle") -> None:
        if not hasattr(self, "_preview_status"):
            return
        labels = {
            "idle": "",
            "processing": "Đang xử lý…",
            "success": "✓ Sẵn sàng",
            "warning": "Cần cập nhật",
            "error": "Có lỗi",
        }
        colors = {
            "idle": TEXT_MUTE,
            "processing": WARNING,
            "success": SUCCESS,
            "warning": WARNING,
            "error": DESTRUCTIVE,
        }
        self._preview_status.setText(labels.get(tone, str(msg or "")))
        self._preview_status.setToolTip(str(msg or ""))
        self._preview_status.setStyleSheet(
            f"font-size:11px;font-weight:600;color:{colors.get(tone, TEXT_MUTE)};"
            "background:transparent;border:none;"
        )
        self._preview_status.setVisible(bool(str(msg or "").strip()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_tts_layout()

    def _adjust_tts_layout(self) -> None:
        if not hasattr(self, "_tts_splitter"):
            return
        body_width = max(self._tts_splitter.width(), self.width() - 220)
        narrow = body_width < 760
        compact_audio = body_width < 1100
        layout_unchanged = getattr(self, "_tts_layout_narrow", None) == narrow
        audio_unchanged = getattr(self, "_tts_audio_compact", None) == compact_audio
        if layout_unchanged and audio_unchanged:
            return
        self._tts_layout_narrow = narrow
        self._tts_audio_compact = compact_audio
        if not layout_unchanged:
            self._tts_splitter.setOrientation(Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal)
        if hasattr(self, "_audio_file_info"):
            self._audio_file_info.setMinimumWidth(180 if compact_audio else 285)
            self._audio_file_info.setMaximumWidth(220 if compact_audio else 330)
            self._audio_progress.setMinimumWidth(100 if compact_audio else 220)
            self.slider.setFixedWidth(80 if compact_audio else 115)
        if not layout_unchanged and self._preview_box.isVisible():
            total = max(2, self._tts_splitter.height() if narrow else self._tts_splitter.width())
            self._tts_splitter.setSizes([total // 2, total - total // 2])
        self._set_tts_review_mode(bool(getattr(self, "_preview_box", None) and self._preview_box.isVisible()))

    def _build(self, default_tab: int = 1):
        root = self.layout()
        if root is None:
            root = QHBoxLayout(self)
        else:
            self._clear_layout(root)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        sidebar = QWidget()
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet(f"QWidget{{background:{SURFACE_2};border-right:1px solid {BORDER_SOFT};}}")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(12, 16, 12, 12)
        sb.setSpacing(4)

        brand_row = QWidget()
        brand_row.setStyleSheet("background:transparent;border:none;")
        brand_lay = QHBoxLayout(brand_row)
        brand_lay.setContentsMargins(8, 2, 8, 8)
        brand_lay.setSpacing(8)
        brand_icon = QLabel()
        brand_icon.setPixmap(ui_icon("video", 16).pixmap(icon_size(16)))
        brand_icon.setStyleSheet("background:transparent;border:none;")
        brand = QLabel("Hedra Studio")
        brand.setFont(self._app_font(14, QFont.Weight.Bold))
        brand.setStyleSheet(f"color:{TEXT};background:transparent;border:none;")
        brand_lay.addWidget(brand_icon)
        brand_lay.addWidget(brand, 1)
        sb.addWidget(brand_row)
        self.credits_lbl = QLabel("Credits: đang tải...")
        self.credits_lbl.setStyleSheet(f"color:{TEXT_FAINT};font-size:11px;padding:4px 8px;background:transparent;border:none;")
        self.credits_lbl.setWordWrap(True)
        sb.addSpacing(10)

        nav_items = [
            ("script", "Kịch bản"),
            ("tts", "TTS"),
            ("stt", "STT"),
            ("video", "Auto Video"),
        ]
        self._main_nav_btns: list[QPushButton] = []
        for idx, (icon, label) in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setIcon(ui_icon(icon, 16, TEXT))
            btn.setIconSize(icon_size(16))
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.setStyleSheet(
                "QPushButton{text-align:left;border:none;border-radius:8px;"
                "padding:0 10px;font-size:13px;font-weight:500;"
                f"color:{TEXT};background:transparent;"
                "}"
                f"QPushButton:hover{{background:{CONTROL_HV};}}"
                f"QPushButton:pressed{{background:{CONTROL_DN};}}"
                f"QPushButton:checked{{background:{ACCENT};color:white;font-weight:700;}}"
            )
            btn.clicked.connect(lambda checked, i=idx: self._switch_main_tab(i))
            self._main_nav_btns.append(btn)
            sb.addWidget(btn)
        sb.addStretch()
        sb.addWidget(self.credits_lbl)
        ver_lbl = QLabel(f"v{VERSION}")
        ver_lbl.setStyleSheet(f"color:{TEXT_FAINT};font-size:11px;padding:4px 8px;background:transparent;border:none;")
        sb.addWidget(ver_lbl)
        root.addWidget(sidebar)

        content = QWidget()
        content.setStyleSheet(f"QWidget{{background:{SURFACE};}}")
        layout = QVBoxLayout(content)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(f"QWidget{{background:{SURFACE};border-bottom:1px solid {BORDER_SOFT};}}")
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(20, 8, 14, 8)
        toolbar_row.setSpacing(8)
        self._page_title = QLabel("TTS")
        self._page_title.setFont(self._app_font(13, QFont.Weight.Bold))
        self._page_title.setStyleSheet(f"color:{TEXT};background:transparent;border:none;")
        toolbar_row.addWidget(self._page_title)
        toolbar_row.addStretch()

        def toolbar_button(text: str, tip: str = "", icon: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(30)
            b.setToolTip(tip)
            if icon:
                b.setIcon(ui_icon(icon, 15))
                b.setIconSize(icon_size(15))
            b.setStyleSheet(
                f"QPushButton{{border:1px solid {BORDER_SOFT};border-radius:15px;"
                f"padding:0 13px;background:{SURFACE};color:{TEXT};font-size:12px;}}"
                f"QPushButton:hover{{background:{CONTROL_HV};}}"
                f"QPushButton:pressed{{background:{CONTROL_DN};}}"
                f"QPushButton:disabled{{color:{TEXT_FAINT};background:{CONTROL_BG};}}"
            )
            return b

        btn_feedback = toolbar_button("Phản hồi", "Gửi phản hồi / Báo lỗi", "message")
        btn_feedback.clicked.connect(self._open_feedback)
        toolbar_row.addWidget(btn_feedback)

        self._btn_check_update = toolbar_button("Cập nhật", "Kiểm tra và tải bản mới nhất", "download")
        self._btn_check_update.clicked.connect(self._manual_check_update)
        toolbar_row.addWidget(self._btn_check_update)

        btn_settings = toolbar_button("Cài đặt", "Mở cài đặt", "settings")
        btn_settings.clicked.connect(self.open_settings)
        toolbar_row.addWidget(btn_settings)
        layout.addWidget(toolbar)

        self.update_banner = QFrame()
        self.update_banner.setVisible(False)
        self.update_banner.setStyleSheet(
            f"QFrame{{background:{CONTROL_BG};border:none;border-bottom:1px solid {BORDER_SOFT};}}"
        )
        banner_row = QHBoxLayout(self.update_banner)
        banner_row.setContentsMargins(20, 8, 14, 8)
        banner_row.setSpacing(8)
        badge = QLabel("NEW")
        badge.setStyleSheet(
            f"background:{ACCENT};color:white;border-radius:4px;"
            f"padding:1px 7px;font-size:11px;font-weight:bold;"
        )
        badge.setFixedHeight(18)
        self._banner_text = QLabel()
        self._banner_text.setStyleSheet(f"color:{TEXT};font-size:12px;background:transparent;border:none;")
        self._btn_dl = QPushButton("Cập nhật ngay")
        self._btn_dl.setFixedHeight(28)
        self._btn_dl.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;"
            f"border-radius:8px;padding:0 14px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            f"QPushButton:disabled{{background:{CONTROL_BG};color:{TEXT_FAINT};}}"
        )
        self._btn_dl.clicked.connect(self._do_update)
        banner_row.addWidget(badge)
        banner_row.addWidget(self._banner_text, 1)
        banner_row.addWidget(self._btn_dl)
        layout.addWidget(self.update_banner)
        self._update_url = ""

        self.tabs = QStackedWidget()
        self.tabs.addWidget(self._build_chat_tab())
        self.tabs.addWidget(self._build_tts_tab())
        self.tabs.addWidget(self._build_stt_tab())
        self.tabs.addWidget(self._build_auto_video_tab())
        self.tabs.currentChanged.connect(self._sync_main_nav)
        layout.addWidget(self.tabs)
        root.addWidget(content, 1)
        self._switch_main_tab(default_tab)  # TTS mặc định khi mở app lần đầu

    def _switch_main_tab(self, idx: int):
        if hasattr(self, "tabs"):
            self.tabs.setCurrentIndex(idx)
        self._sync_main_nav(idx)
        perf_log("main_tab_switch", index=idx)

    def _sync_main_nav(self, idx: int):
        titles = ["Kịch bản", "TTS", "STT", "Auto Video"]
        if hasattr(self, "_page_title") and 0 <= idx < len(titles):
            self._page_title.setText(titles[idx])
        for i, btn in enumerate(getattr(self, "_main_nav_btns", [])):
            btn.setChecked(i == idx)

    def _student_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setStyleSheet(f"QWidget{{background:{SURFACE};}}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 16, 22, 22)
        layout.setSpacing(12)
        return page, layout

    def _pane_heading(self, title: str, subtitle: str = "") -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background:transparent;border:none;")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(3)
        t = QLabel(title)
        t.setStyleSheet(f"font-size:13px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setWordWrap(True)
            s.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
            lay.addWidget(s)
        return wrap

    def _v_divider(self) -> QFrame:
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"color:{BORDER_SOFT};")
        return div

    def _strip_widget(self) -> tuple[QWidget, QHBoxLayout]:
        strip = QWidget()
        strip.setStyleSheet(f"QWidget{{background:{CONTROL_BG};border:none;border-radius:10px;}}")
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)
        return strip, lay

    def _empty_state(self, icon: str, title: str, detail: str) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background:transparent;border:none;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(8)
        lay.addStretch()
        icon_name = "audio" if icon in {"◉", "audio"} else icon
        i = QLabel()
        i.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon_name in {"audio", "script", "stt", "video", "image"}:
            i.setPixmap(ui_icon(icon_name, 34, TEXT_FAINT).pixmap(icon_size(34)))
        else:
            i.setText(icon)
            i.setStyleSheet(f"font-size:32px;color:{TEXT_FAINT};background:transparent;border:none;")
        lay.addWidget(i)
        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(f"font-size:22px;font-weight:700;color:{TEXT_FAINT};background:transparent;border:none;")
        lay.addWidget(t)
        d = QLabel(detail)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setWordWrap(True)
        d.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        lay.addWidget(d)
        lay.addStretch()
        return box

    def _compact_primary_style(self) -> str:
        return (
            f"QPushButton{{background:{ACCENT};color:white;border:none;border-radius:9px;"
            "font-size:13px;font-weight:700;padding:0 18px;min-height:32px;}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            f"QPushButton:pressed{{background:{ACCENT_DN};}}"
            f"QPushButton:disabled{{background:{CONTROL_BG};color:{TEXT_FAINT};}}"
        )

    def _compact_secondary_style(self) -> str:
        return (
            f"QPushButton{{background:{CONTROL_BG};color:{TEXT};border:1px solid {BORDER_SOFT};"
            "border-radius:9px;font-size:13px;font-weight:500;padding:0 14px;min-height:32px;}"
            f"QPushButton:hover{{background:{CONTROL_HV};}}"
            f"QPushButton:pressed{{background:{CONTROL_DN};}}"
            f"QPushButton:disabled{{background:{CONTROL_BG};color:{TEXT_FAINT};border:1px solid {BORDER_SOFT};}}"
        )

    def _editor_style(self, bordered: bool = False) -> str:
        if bordered:
            return (
                f"QTextEdit{{background:{SURFACE};border:1px solid {BORDER_SOFT};"
                f"border-radius:10px;color:{TEXT};font-size:14px;padding:12px;}}"
                f"QTextEdit:focus{{border-color:{ACCENT};}}"
            )
        return (
            f"QTextEdit{{background:transparent;border:none;color:{TEXT};"
            "font-size:14px;padding:8px 0;}"
        )

    # ── Tab 1: TTS ─────────────────────────────────────────────────

    def _build_tts_tab(self) -> QWidget:
        page, layout = self._student_page()

        strip, strip_lay = self._strip_widget()
        style_lbl = QLabel("Phong cách")
        style_lbl.setStyleSheet(f"font-size:12px;font-weight:600;color:{TEXT};background:transparent;border:none;")
        strip_lay.addWidget(style_lbl)

        active_name = self._find_active_style_name(self.settings.get("enhance_prompt", DEFAULT_PROMPT_FUNNY))
        self._style_combo = _ApplePopupCombo()
        self._style_combo.setFixedHeight(30)
        self._style_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._style_combo.setStyleSheet(
            f"QComboBox{{background:{CONTROL_BG};border:none;"
            f"border-radius:8px;padding:3px 8px 3px 12px;font-size:13px;"
            f"font-weight:500;color:{TEXT};}}"
            f"QComboBox:hover{{background:{CONTROL_HV};}}"
            "QComboBox QAbstractScrollArea{background:transparent;border:none;}"
            "QComboBox QAbstractItemView{"
            f"background:{SURFACE};color:{TEXT};"
            f"border:1px solid {BORDER};border-radius:10px;"
            "padding:4px;outline:none;}"
            "QComboBox QAbstractItemView::item{min-height:32px;padding:4px 14px;"
            f"color:{TEXT};border-radius:6px;}}"
            f"QComboBox QAbstractItemView::item:selected{{background:{CONTROL_HV};color:{ACCENT};}}"
        )
        self._populate_style_combo(active_name)
        self._style_combo.currentTextChanged.connect(self._set_prompt_style)
        strip_lay.addWidget(self._style_combo)

        btn_add_style = QPushButton("+")
        btn_add_style.setFixedSize(30, 30)
        btn_add_style.setToolTip("Thêm phong cách")
        btn_add_style.setStyleSheet(
            f"QPushButton{{background:{CONTROL_BG};color:{TEXT};border:1px solid {BORDER_SOFT};"
            "border-radius:9px;font-size:16px;font-weight:500;padding:0;}"
            f"QPushButton:hover{{background:{CONTROL_HV};}}"
        )
        btn_add_style.clicked.connect(self._quick_add_style)
        strip_lay.addWidget(btn_add_style)
        strip_lay.addStretch()

        self._tts_voice_combo = self._make_favorites_combo("tts")
        strip_lay.addWidget(self._tts_voice_combo)
        self._voice_name_lbl = self._tts_voice_combo  # kept for compatibility

        self._lang_code = self.settings.get("tts_language_code", "")
        self._lang_combo = _ApplePopupCombo()
        self._lang_combo.setFixedHeight(30)
        self._lang_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._lang_combo.setStyleSheet(
            f"QComboBox{{background:{CONTROL_BG};border:none;"
            f"border-radius:8px;padding:3px 8px 3px 10px;font-size:12px;color:{TEXT};}}"
            f"QComboBox:hover{{background:{CONTROL_HV};}}"
            f"QComboBox:focus{{background:{CONTROL_HV};}}"
            "QComboBox QAbstractScrollArea{background:transparent;border:none;}"
            "QComboBox QAbstractItemView{"
            f"background:{SURFACE};color:{TEXT};"
            f"border:1px solid {BORDER};border-radius:10px;"
            "padding:4px;outline:none;}"
            "QComboBox QAbstractItemView::item{min-height:26px;padding:3px 12px;"
            f"color:{TEXT};border-radius:6px;}}"
            f"QComboBox QAbstractItemView::item:selected{{background:{CONTROL_HV};color:{ACCENT};"
            "font-weight:600;}"
        )
        self._lang_combo.setItemDelegate(QStyledItemDelegate(self._lang_combo))
        self._lang_combo.currentIndexChanged.connect(
            lambda _: (
                self.settings.__setitem__("tts_language_code", self._lang_combo.currentData() or ""),
                save_settings(self.settings),
            )
        )
        strip_lay.addWidget(self._lang_combo)
        self._tts_update_lang_for_voice(self._tts_voice_combo.currentData() or "")

        v3_wrap = QWidget()
        v3_wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
        v3_lay = QHBoxLayout(v3_wrap)
        v3_lay.setContentsMargins(0, 0, 0, 0)
        v3_lay.setSpacing(8)
        v3_label = QLabel("Nhấn nhá v3")
        v3_label.setStyleSheet(
            f"font-size:12px;font-weight:600;color:{TEXT};background:transparent;border:none;"
        )
        v3_lay.addWidget(v3_label)
        self._tts_v3_check = _AppleSwitch()
        self._tts_v3_check.setChecked(bool(self.settings.get("eleven_v3_style_enabled", True)))
        self._tts_v3_check.setToolTip("Bật để AI thêm tag, dấu câu và nhịp đọc phù hợp ElevenLabs v3.")
        self._tts_v3_check.toggled.connect(self._set_tts_v3_enabled)
        v3_lay.addWidget(self._tts_v3_check)
        strip_lay.addWidget(v3_wrap)

        strip_lay.addSpacing(6)
        self._btn_preview = QPushButton("Xem bản đọc")
        self._btn_preview.setFixedHeight(30)
        self._btn_preview.setStyleSheet(self._compact_secondary_style())
        self._btn_preview.clicked.connect(self._do_preview)
        strip_lay.addWidget(self._btn_preview)

        self.btn_gen = QPushButton("Tạo audio")
        self.btn_gen.setFixedHeight(30)
        self.btn_gen.setStyleSheet(self._compact_primary_style())
        self.btn_gen.clicked.connect(self._generate)
        strip_lay.addWidget(self.btn_gen)
        self._sync_tts_audio_button()
        layout.addWidget(strip)

        workspace = QWidget()
        workspace.setObjectName("ttsWorkspace")
        workspace.setStyleSheet(
            f"#ttsWorkspace{{background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;}}"
        )
        workspace_l = QVBoxLayout(workspace)
        workspace_l.setContentsMargins(0, 0, 0, 0)
        workspace_l.setSpacing(0)

        self._tts_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._tts_splitter.setChildrenCollapsible(False)
        self._tts_splitter.setHandleWidth(5)
        self._tts_splitter.setStyleSheet(
            f"QSplitter{{background:transparent;border:none;}}"
            f"QSplitter::handle{{background:{BORDER_SOFT};margin:14px 2px;border-radius:1px;}}"
            f"QSplitter::handle:hover{{background:{ACCENT};}}"
        )
        self._tts_layout_narrow = False

        left = QWidget()
        left.setStyleSheet("background:transparent;border:none;")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(16, 14, 16, 14)
        left_l.setSpacing(8)
        script_head = QWidget()
        script_head.setStyleSheet("background:transparent;border:none;")
        script_head_l = QHBoxLayout(script_head)
        script_head_l.setContentsMargins(0, 0, 0, 0)
        script_head_l.setSpacing(8)
        script_head_l.addWidget(self._pane_heading("Kịch bản", "Paste hoặc chỉnh nội dung trước khi tạo giọng."), 1)
        self._sync_scroll_btn = QToolButton()
        self._sync_scroll_btn.setText("↔")
        self._sync_scroll_btn.setCheckable(True)
        self._sync_scroll_btn.setFixedSize(34, 28)
        self._sync_scroll_btn.setToolTip("Cuộn Kịch bản và Bản đọc cùng nhau")
        self._sync_scroll_btn.setStyleSheet(
            f"QToolButton{{background:{SURFACE};color:{TEXT};border:1px solid {BORDER_SOFT};"
            "border-radius:7px;font-size:15px;font-weight:700;}"
            f"QToolButton:hover{{background:{CONTROL_HV};}}"
            f"QToolButton:checked{{background:{CONTROL_HV};color:{ACCENT};}}"
        )
        script_head_l.addWidget(self._sync_scroll_btn, 0, Qt.AlignmentFlag.AlignTop)
        left_l.addWidget(script_head)
        self.text_input = QTextEdit()
        self.text_input.setAcceptRichText(False)
        self.text_input.setPlaceholderText("Paste kịch bản vào đây...")
        self.text_input.setMinimumHeight(180)
        self.text_input.setStyleSheet(self._editor_style())
        self.text_input.textChanged.connect(self._on_script_changed)
        left_l.addWidget(self.text_input, 1)
        self._tts_splitter.addWidget(left)
        self._tts_left_card = left

        self._preview_box = QWidget()
        self._preview_box.setVisible(False)
        self._preview_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview_box.setStyleSheet("background:transparent;border:none;")
        pv_lay = QVBoxLayout(self._preview_box)
        pv_lay.setContentsMargins(16, 14, 16, 14)
        pv_lay.setSpacing(6)

        preview_head = QWidget()
        preview_head.setStyleSheet("background:transparent;border:none;")
        preview_head_l = QHBoxLayout(preview_head)
        preview_head_l.setContentsMargins(0, 0, 0, 0)
        preview_head_l.setSpacing(7)
        preview_titles = QWidget()
        preview_titles.setStyleSheet("background:transparent;border:none;")
        preview_titles_l = QVBoxLayout(preview_titles)
        preview_titles_l.setContentsMargins(0, 0, 0, 6)
        preview_titles_l.setSpacing(3)
        preview_title_row = QHBoxLayout()
        preview_title_row.setSpacing(7)
        preview_title = QLabel("Bản đọc")
        preview_title.setStyleSheet(f"font-size:13px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        preview_title_row.addWidget(preview_title)
        self._preview_status = QLabel("")
        self._preview_status.setStyleSheet(f"font-size:11px;font-weight:600;color:{TEXT_MUTE};background:transparent;border:none;")
        self._preview_status.setVisible(False)
        preview_title_row.addWidget(self._preview_status)
        preview_title_row.addStretch()
        preview_titles_l.addLayout(preview_title_row)
        preview_subtitle = QLabel("Sửa ở đây. Audio sẽ dùng đúng nội dung này.")
        preview_subtitle.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        preview_titles_l.addWidget(preview_subtitle)
        preview_head_l.addWidget(preview_titles, 1)
        pv_lay.addWidget(preview_head)

        self.preview_text = QTextEdit()
        self.preview_text.setAcceptRichText(False)
        self.preview_text.setPlaceholderText("Bản đọc sau khi AI xử lý sẽ hiện ở đây...")
        self.preview_text.setMinimumHeight(180)
        self.preview_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_text.setStyleSheet(self._editor_style())
        pv_lay.addWidget(self.preview_text, 1)
        self.text_input.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_tts_scroll(self.text_input, self.preview_text, value)
        )
        self.preview_text.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_tts_scroll(self.preview_text, self.text_input, value)
        )
        self._tts_splitter.addWidget(self._preview_box)
        self._tts_splitter.setStretchFactor(0, 1)
        self._tts_splitter.setStretchFactor(1, 1)
        self._tts_splitter.setSizes([1, 1])
        self._tts_splitter.splitterMoved.connect(self._save_tts_splitter_ratio)
        self._enhanced_cache = ""
        workspace_l.addWidget(self._tts_splitter, 1)

        self.tts_status_lbl = QLabel("Chưa có audio")
        self.tts_status_lbl.setMinimumWidth(0)
        self.tts_status_lbl.setStyleSheet(f"color:{TEXT_MUTE};font-size:12px;background:transparent;border:none;")

        audio_bar = QWidget()
        audio_bar.setObjectName("ttsAudioBar")
        audio_bar.setFixedHeight(78)
        audio_bar.setStyleSheet(f"#ttsAudioBar{{background:{CONTROL_BG};border-top:1px solid {BORDER_SOFT};}}")
        audio_l = QHBoxLayout(audio_bar)
        audio_l.setContentsMargins(10, 8, 10, 8)
        audio_l.setSpacing(12)

        audio_icon = QLabel()
        audio_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        audio_icon.setFixedSize(46, 46)
        audio_icon.setPixmap(ui_icon("audio", 23, "#ffffff").pixmap(icon_size(23)))
        audio_icon.setStyleSheet(f"background:{ACCENT};border:none;border-radius:23px;")
        audio_l.addWidget(audio_icon)

        file_info = QWidget()
        file_info.setStyleSheet("background:transparent;border:none;")
        file_info_l = QVBoxLayout(file_info)
        file_info_l.setContentsMargins(0, 0, 0, 0)
        file_info_l.setSpacing(1)
        file_info.setMinimumWidth(285)
        file_info.setMaximumWidth(330)
        self._audio_file_info = file_info
        filename_row = QWidget()
        filename_row.setStyleSheet("background:transparent;border:none;")
        filename_row_l = QHBoxLayout(filename_row)
        filename_row_l.setContentsMargins(0, 0, 0, 0)
        filename_row_l.setSpacing(4)
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("Tên file tự tạo theo bản đọc")
        self.filename_input.setMaximumWidth(300)
        self.filename_input.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{TEXT};font-size:13px;font-weight:700;padding:0;}}"
            f"QLineEdit:focus{{background:{SURFACE};border:1px solid {ACCENT};border-radius:6px;padding:2px 6px;}}"
        )
        filename_row_l.addWidget(self.filename_input, 1)
        filename_edit = QLabel("✎")
        filename_edit.setToolTip("Bấm vào tên để sửa")
        filename_edit.setStyleSheet(f"font-size:14px;color:{TEXT};background:transparent;border:none;")
        filename_row_l.addWidget(filename_edit)
        file_info_l.addWidget(filename_row)
        file_info_l.addWidget(self.tts_status_lbl)
        audio_l.addWidget(file_info, 0)

        self._btn_play_audio = QPushButton("▶")
        self._btn_play_audio.setFixedSize(46, 46)
        self._btn_play_audio.setEnabled(False)
        self._btn_play_audio.setToolTip("Phát hoặc dừng audio")
        self._btn_play_audio.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;border-radius:23px;font-size:17px;padding:0;}}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            f"QPushButton:disabled{{background:{CONTROL_DN};color:{TEXT_FAINT};}}"
        )
        self._btn_play_audio.clicked.connect(self._toggle_last_audio)
        audio_l.addWidget(self._btn_play_audio)

        self._audio_time_lbl = QLabel("00:00 / 00:00")
        self._audio_time_lbl.setMinimumWidth(82)
        self._audio_time_lbl.setStyleSheet(f"font-size:12px;color:{TEXT};background:transparent;border:none;")
        audio_l.addWidget(self._audio_time_lbl)

        self._audio_progress = QSlider(Qt.Orientation.Horizontal)
        self._audio_progress.setRange(0, 1000)
        self._audio_progress.setValue(0)
        self._audio_progress.setEnabled(False)
        self._audio_progress.setMinimumWidth(220)
        self._audio_progress.sliderMoved.connect(self._seek_output_audio)
        audio_l.addWidget(self._audio_progress, 1)

        speed_label = QLabel("◴")
        speed_label.setToolTip("Tốc độ đọc")
        speed_label.setStyleSheet(f"font-size:22px;color:{TEXT};background:transparent;border:none;")
        audio_l.addWidget(speed_label)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(7)
        self.slider.setMaximum(12)
        self.slider.setValue(int(self.settings.get("default_speed", 1.0) * 10))
        self.slider.setFixedWidth(115)
        audio_l.addWidget(self.slider)
        self.speed_val = QLabel(f"{self.slider.value()/10:.1f}×")
        self.speed_val.setFixedWidth(36)
        self.speed_val.setStyleSheet(f"color:{ACCENT};font-weight:700;background:transparent;border:none;")
        self.slider.valueChanged.connect(lambda v: self.speed_val.setText(f"{v/10:.1f}×"))
        audio_l.addWidget(self.speed_val)

        self._btn_open_folder = QToolButton()
        self._btn_open_folder.setIcon(ui_icon("output", 18, TEXT))
        self._btn_open_folder.setIconSize(icon_size(18))
        self._btn_open_folder.setFixedSize(42, 38)
        self._btn_open_folder.setEnabled(False)
        self._btn_open_folder.setToolTip("Mở audio trong Finder")
        self._btn_open_folder.setStyleSheet(
            f"QToolButton{{background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;padding:0;}}"
            f"QToolButton:hover{{background:{CONTROL_HV};}}"
        )
        audio_l.addWidget(self._btn_open_folder)

        self._audio_more_btn = QToolButton()
        self._audio_more_btn.setText("•••")
        self._audio_more_btn.setFixedSize(42, 38)
        self._audio_more_btn.setToolTip("Tác vụ khác")
        self._audio_more_btn.setStyleSheet(
            f"QToolButton{{background:{SURFACE};color:{TEXT};border:1px solid {BORDER_SOFT};border-radius:8px;font-size:13px;}}"
            f"QToolButton:hover{{background:{CONTROL_HV};}}"
        )
        self._audio_menu = QMenu(self._audio_more_btn)
        action_copy_audio = self._audio_menu.addAction("Sao chép đường dẫn audio")
        action_copy_audio.triggered.connect(lambda: self._copy_output_path("audio"))
        action_copy_srt = self._audio_menu.addAction("Sao chép đường dẫn SRT")
        action_copy_srt.triggered.connect(lambda: self._copy_output_path("srt"))
        self._audio_more_btn.clicked.connect(
            lambda: self._audio_menu.exec(self._audio_more_btn.mapToGlobal(self._audio_more_btn.rect().bottomRight()))
        )
        audio_l.addWidget(self._audio_more_btn)

        workspace_l.addWidget(audio_bar)
        self._last_audio_path = ""
        self._last_srt_path = ""

        layout.addWidget(workspace, 1)
        QTimer.singleShot(0, self._adjust_tts_layout)
        return page

    # ── Tab 3: Speech-to-Text ────────────────────────────────────

    def _build_stt_tab(self) -> QWidget:
        page, layout = self._student_page()
        body = QWidget()
        body.setStyleSheet("background:transparent;border:none;")
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)

        left, left_l = self._card()
        left_l.setContentsMargins(16, 14, 16, 14)
        left_l.setSpacing(10)
        left_l.addWidget(self._pane_heading("File audio", "Kéo thả hoặc bấm để chọn file cần nhận diện."))
        self._stt_drop = DropZone(
            label="♬  Kéo thả file audio vào đây",
            dialog_title="Chọn file audio",
            file_filter="Audio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.webm)",
            extensions=(".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm"),
        )
        self._stt_drop.setFixedHeight(72)
        self._stt_drop.files_added.connect(self._stt_file_selected)
        self._stt_drop.setStyleSheet(
            f"QFrame{{border:1px dashed {BORDER};border-radius:10px;background:{SURFACE_2};}}"
            f"QFrame:hover{{border-color:{ACCENT};background:{CONTROL_HV};}}"
        )
        left_l.addWidget(self._stt_drop)
        self._stt_file_lbl = QLabel("Chưa chọn file")
        self._stt_file_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        left_l.addWidget(self._stt_file_lbl)
        self._stt_path = ""
        self._stt_btn = QPushButton("Nhận diện")
        self._stt_btn.setFixedHeight(34)
        self._stt_btn.setStyleSheet(self._compact_primary_style())
        self._stt_btn.clicked.connect(self._do_stt)
        stt_action = QHBoxLayout()
        stt_action.addStretch()
        self._stt_btn.setFixedWidth(140)
        stt_action.addWidget(self._stt_btn)
        left_l.addLayout(stt_action)
        self._stt_status = QLabel("")
        self._stt_status.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        left_l.addWidget(self._stt_status)
        left_l.addStretch()
        h.addWidget(left, 5)

        right, right_l = self._card()
        right_l.setContentsMargins(16, 14, 16, 14)
        right_l.setSpacing(10)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._pane_heading("Kết quả", "Transcript sẽ hiện ở đây."))
        header.addStretch()
        self._stt_export_btn = QPushButton("Xuất SRT")
        self._stt_export_btn.setFixedHeight(32)
        self._stt_export_btn.setStyleSheet(self._compact_secondary_style())
        self._stt_export_btn.clicked.connect(self._export_srt)
        self._stt_export_btn.setVisible(False)
        header.addWidget(self._stt_export_btn)
        right_l.addLayout(header)
        self._stt_text = QTextEdit()
        self._stt_text.setPlaceholderText("Chưa có bản nhận diện")
        self._stt_text.setStyleSheet(self._editor_style())
        right_l.addWidget(self._stt_text, 1)
        self._stt_words = []
        h.addWidget(right, 7)

        layout.addWidget(body, 1)
        return page

    def _stt_file_selected(self, paths: list):
        if paths:
            self._stt_path = paths[0]
            self._stt_file_lbl.setText(os.path.basename(paths[0]))

    def _do_stt(self):
        if not self._stt_path:
            QMessageBox.warning(self, "Chưa có file", "Kéo thả file audio vào trước nhé!")
            return
        gemini_key = self.settings.get("gemini_api_key", "").strip()
        if not gemini_key:
            QMessageBox.warning(
                self,
                "Thiếu STT API Key",
                "Cần Gemini API Key để dùng Speech-to-Text.\n"
                "Vào Cài đặt → API để thêm.",
            )
            return
        self._stt_btn.setEnabled(False)
        self._stt_status.setText("Đang nhận diện...")
        self._stt_worker = SpeechToTextWorker(self._stt_path, gemini_key, self.settings)
        self._stt_worker.status.connect(self._stt_status.setText)
        self._stt_worker.done.connect(self._on_stt_done)
        self._stt_worker.error.connect(self._on_stt_error)
        self._track_thread("_stt_worker", self._stt_worker)

    def _on_stt_done(self, text: str, words: list):
        self._stt_btn.setEnabled(True)
        self._stt_text.setPlainText(text)
        self._stt_status.setText("Nhận diện xong")
        self._stt_words = words
        self._stt_export_btn.setVisible(True)

    def _on_stt_error(self, msg: str):
        self._stt_btn.setEnabled(True)
        self._stt_status.setText(msg[:80])

    def _export_srt(self):
        if not self._stt_words:
            return
        srt = words_to_srt(self._stt_words)
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất SRT", "transcript.srt", "SRT files (*.srt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(srt)
            self._stt_status.setText(f"Đã lưu: {os.path.basename(path)}")
            reveal_file(path)

    # ── Tab 2: Chat → Kịch Bản ────────────────────────────────────

    def _build_chat_tab(self) -> QWidget:
        page, layout = self._student_page()
        body = QWidget()
        body.setStyleSheet("background:transparent;border:none;")
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)

        left, left_l = self._card()
        left_l.setContentsMargins(16, 14, 16, 14)
        left_l.setSpacing(10)
        left_l.addWidget(self._pane_heading("Ảnh chat", "Thả ảnh hội thoại để AI viết lại thành kịch bản."))
        pronoun_row = QHBoxLayout()
        pronoun_row.setContentsMargins(0, 0, 0, 0)
        pronoun_row.setSpacing(8)
        pronoun_lbl = QLabel("Xưng hô")
        pronoun_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        pronoun_row.addWidget(pronoun_lbl)
        self.chat_pronoun_combo = _ApplePopupCombo()
        self.chat_pronoun_combo.addItem("Auto theo chat", "auto")
        self.chat_pronoun_combo.addItem("Cố định anh/em", "fixed_anh_em")
        self.chat_pronoun_combo.addItem("Giữ nguyên chat", "keep_original")
        current_pronoun = self.settings.get("chat_pronoun_mode", "auto")
        for i in range(self.chat_pronoun_combo.count()):
            if self.chat_pronoun_combo.itemData(i) == current_pronoun:
                self.chat_pronoun_combo.setCurrentIndex(i)
                break
        self.chat_pronoun_combo.setFixedHeight(30)
        self.chat_pronoun_combo.setStyleSheet(
            f"QComboBox{{background:{CONTROL_BG};border:none;border-radius:9px;"
            f"padding:3px 24px 3px 10px;font-size:12px;color:{TEXT};}}"
            f"QComboBox:hover{{background:{CONTROL_HV};}}"
            "QComboBox::drop-down{border:none;}"
            + self._combo_item_view_style(28)
        )
        self.chat_pronoun_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self.chat_pronoun_combo.view().setMinimumWidth(180)
        pronoun_row.addWidget(self.chat_pronoun_combo, 1)
        left_l.addLayout(pronoun_row)
        self.drop_zone = DropZone(label="▧  Kéo thả ảnh vào đây")
        self.drop_zone.files_added.connect(self._add_images)
        self.drop_zone.setFixedHeight(72)
        self.drop_zone.setStyleSheet(
            f"QFrame{{border:1px dashed {BORDER};border-radius:10px;background:{SURFACE_2};}}"
            f"QFrame:hover{{border-color:{ACCENT};background:{CONTROL_HV};}}"
        )
        left_l.addWidget(self.drop_zone)
        list_row = QHBoxLayout()
        self.img_count_lbl = QLabel("0 ảnh đã chọn")
        self.img_count_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        list_row.addWidget(self.img_count_lbl)
        list_row.addStretch()
        btn_clear_imgs = QPushButton("Xóa")
        btn_clear_imgs.setFixedHeight(30)
        btn_clear_imgs.setStyleSheet(self._compact_secondary_style())
        btn_clear_imgs.clicked.connect(self._clear_images)
        list_row.addWidget(btn_clear_imgs)
        left_l.addLayout(list_row)
        self.img_list = QListWidget()
        self.img_list.setStyleSheet(
            f"QListWidget{{border:none;background:{CONTROL_BG};border-radius:10px;padding:6px;}}"
            f"QListWidget::item{{padding:5px 7px;border-radius:7px;color:{TEXT};}}"
            f"QListWidget::item:selected{{background:{CONTROL_HV};color:{TEXT};}}"
        )
        left_l.addWidget(self.img_list, 1)
        self.btn_gen_script = QPushButton("Tạo kịch bản")
        self.btn_gen_script.setFixedHeight(34)
        self.btn_gen_script.setStyleSheet(self._compact_primary_style())
        self.btn_gen_script.clicked.connect(self._generate_script)
        gen_row = QHBoxLayout()
        gen_row.addStretch()
        self.btn_gen_script.setFixedWidth(160)
        gen_row.addWidget(self.btn_gen_script)
        left_l.addLayout(gen_row)
        self.chat_status_lbl = QLabel("Sẵn sàng")
        self.chat_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chat_status_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        left_l.addWidget(self.chat_status_lbl)
        h.addWidget(left, 5)

        right, right_l = self._card()
        right_l.setContentsMargins(16, 14, 16, 14)
        right_l.setSpacing(10)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._pane_heading("Kịch bản", "Kết quả có thể dùng ngay cho TTS."))
        header.addStretch()
        btn_copy = QPushButton("Copy")
        btn_copy.setFixedHeight(32)
        btn_copy.setStyleSheet(self._compact_secondary_style())
        btn_copy.clicked.connect(self._copy_script)
        header.addWidget(btn_copy)
        btn_use_tts = QPushButton("Dùng cho TTS")
        btn_use_tts.setFixedHeight(32)
        btn_use_tts.setStyleSheet(self._compact_secondary_style())
        btn_use_tts.clicked.connect(self._use_for_tts)
        header.addWidget(btn_use_tts)
        right_l.addLayout(header)
        self.script_output = QTextEdit()
        self.script_output.setAcceptRichText(False)
        self.script_output.setPlaceholderText("Chưa có kịch bản")
        self.script_output.setStyleSheet(self._editor_style())
        right_l.addWidget(self.script_output, 1)
        h.addWidget(right, 7)

        layout.addWidget(body, 1)
        self._chat_body = body
        self._chat_lock_panel = self._build_chat_unlock_panel()
        layout.addWidget(self._chat_lock_panel)
        self._chat_apply_lock_state()
        return page

    # ── Chat tab handlers ──────────────────────────────────────────
    def _add_images(self, paths: list):
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                item = QListWidgetItem(os.path.basename(p))
                item.setData(Qt.ItemDataRole.UserRole, p)
                self.img_list.addItem(item)
        self.img_count_lbl.setText(f"{len(self.image_paths)} ảnh đã chọn")

    def _clear_images(self):
        self.image_paths.clear()
        self.img_list.clear()
        self.img_count_lbl.setText("0 ảnh đã chọn")

    def _generate_script(self):
        if not is_chat_script_unlocked(self.settings):
            self._chat_apply_lock_state()
            QMessageBox.warning(self, "Cần Pro key", "Kịch bản là tính năng Pro. Nhập key hoặc liên hệ mua key để sử dụng.")
            return
        if not self.image_paths:
            QMessageBox.warning(self, "Chưa có ảnh", "Thêm ảnh chat vào trước nhé!")
            return
        api_key = self.settings.get("gemini_api_key", "").strip()
        if not api_key:
            QMessageBox.warning(self, "Thiếu Gemini API Key",
                                "Vào Cài đặt → API để nhập Gemini API Key trước nhé!")
            return

        self.btn_gen_script.setEnabled(False)
        pronoun_mode = (
            self.chat_pronoun_combo.currentData()
            if hasattr(getattr(self, "chat_pronoun_combo", None), "currentData")
            else "auto"
        ) or "auto"
        self.settings["chat_pronoun_mode"] = pronoun_mode
        save_settings(self.settings)
        gemini_prompt = self.settings.get("gemini_chat_prompt", "").strip() or GEMINI_CHAT_PROMPT
        self.gemini_worker = GeminiWorker(self.image_paths, api_key, gemini_prompt, pronoun_mode)
        self.gemini_worker.status.connect(self._on_chat_status)
        self.gemini_worker.done.connect(self._on_script_done)
        self.gemini_worker.error.connect(self._on_script_error)
        self._track_thread("gemini_worker", self.gemini_worker)

    def _on_chat_status(self, msg: str):
        self.chat_status_lbl.setText(msg)
        self.chat_status_lbl.setStyleSheet(
            f"color:{WARNING}; font-size:11px; background:transparent;"
        )

    def _on_script_done(self, text: str):
        self.btn_gen_script.setEnabled(True)
        self.script_output.setPlainText(text)
        self.chat_status_lbl.setText("Tạo kịch bản thành công")
        self.chat_status_lbl.setStyleSheet(
            f"color:{SUCCESS}; font-size:14px; font-weight:600; background:transparent;"
        )
        QTimer.singleShot(4000, self._reset_chat_status)

    def _on_script_error(self, msg: str):
        self.btn_gen_script.setEnabled(True)
        self.chat_status_lbl.setText("Có lỗi xảy ra")
        self.chat_status_lbl.setStyleSheet(
            f"color:{DESTRUCTIVE}; font-size:11px; background:transparent;"
        )
        QMessageBox.critical(self, "Lỗi Gemini", msg)

    def _reset_chat_status(self):
        self.chat_status_lbl.setText("Sẵn sàng")
        self.chat_status_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; background:transparent;"
        )

    def _copy_script(self):
        text = self.script_output.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.chat_status_lbl.setText("Đã copy")
            self.chat_status_lbl.setStyleSheet(
                f"color:{SUCCESS}; font-size:11px; background:transparent;"
            )
            QTimer.singleShot(2000, self._reset_chat_status)

    def _use_for_tts(self):
        text = self.script_output.toPlainText().strip()
        if text:
            self.text_input.setPlainText(text)
            self.tabs.setCurrentIndex(1)   # index 1 = TTS tab

    def _current_license_key(self) -> str:
        return (
            str(self.settings.get("pro_license_key", "")).strip()
            or str(self.settings.get("auto_video_license_key", "")).strip()
        )

    def _save_license_cache(self, key: str, cache: dict):
        self.settings["pro_license_key"] = key
        self.settings["auto_video_license_key"] = key
        self.settings["pro_license_cache"] = cache or {}
        save_settings(self.settings)

    def _build_chat_unlock_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};border-radius:12px;}}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(ui_icon("api", 22, ACCENT).pixmap(icon_size(22)))
        head.addWidget(icon_lbl)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Cần Pro key")
        title.setStyleSheet(f"font-size:15px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        sub = QLabel("TTS và STT dùng bình thường. Kịch bản là tính năng Pro, cần key để đọc ảnh chat và viết nội dung.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        head.addLayout(title_col, 1)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._chat_license_input = QLineEdit()
        self._chat_license_input.setPlaceholderText("Nhập Pro key")
        self._chat_license_input.setText(self._current_license_key())
        self._chat_license_input.setFixedHeight(34)
        self._chat_license_input.setStyleSheet(
            f"QLineEdit{{background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;"
            f"color:{TEXT};font-size:13px;padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{ACCENT};}}"
        )
        self._chat_license_input.returnPressed.connect(self._chat_unlock_license)
        row.addWidget(self._chat_license_input, 1)

        self._chat_unlock_btn = QPushButton("Kiểm tra key")
        self._chat_unlock_btn.setFixedHeight(34)
        self._chat_unlock_btn.setStyleSheet(self._compact_primary_style())
        self._chat_unlock_btn.clicked.connect(self._chat_unlock_license)
        row.addWidget(self._chat_unlock_btn)
        self._chat_buy_key_btn = QPushButton("Liên hệ mua key")
        self._chat_buy_key_btn.setFixedHeight(34)
        self._chat_buy_key_btn.setStyleSheet(self._compact_secondary_style())
        self._chat_buy_key_btn.clicked.connect(self._open_feedback)
        row.addWidget(self._chat_buy_key_btn)
        lay.addLayout(row)

        self._chat_license_status = QLabel("")
        self._chat_license_status.setWordWrap(True)
        self._chat_license_status.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        lay.addWidget(self._chat_license_status)
        return panel

    def _chat_apply_lock_state(self):
        unlocked = is_chat_script_unlocked(self.settings)
        if hasattr(self, "_chat_lock_panel"):
            self._chat_lock_panel.setVisible(not unlocked)
        if hasattr(self, "_chat_body"):
            self._chat_body.setEnabled(unlocked)
        if hasattr(self, "btn_gen_script"):
            self.btn_gen_script.setEnabled(unlocked)
            self.btn_gen_script.setToolTip("" if unlocked else "Cần Pro key để dùng Kịch bản")
        if hasattr(self, "_chat_license_status"):
            cache = self.settings.get("pro_license_cache", {})
            msg = cache.get("message") if isinstance(cache, dict) else ""
            self._chat_license_status.setText(msg or "Chưa có Pro key cho Kịch bản. Nhập key hoặc liên hệ mua key.")
            self._chat_license_status.setStyleSheet(
                f"font-size:12px;color:{SUCCESS if unlocked else TEXT_MUTE};background:transparent;border:none;"
            )

    def _chat_unlock_license(self):
        key = self._chat_license_input.text().strip() if hasattr(self, "_chat_license_input") else ""
        self._chat_unlock_btn.setEnabled(False)
        self._chat_unlock_btn.setText("Đang kiểm tra…")
        QApplication.processEvents()
        ok, msg, cache = validate_pro_license_key(key, "chat_script")
        self._save_license_cache(key, cache)
        if hasattr(self, "_chat_license_status"):
            self._chat_license_status.setText(msg)
            self._chat_license_status.setStyleSheet(
                f"font-size:12px;color:{SUCCESS if ok else DESTRUCTIVE};background:transparent;border:none;"
            )
        self._chat_unlock_btn.setEnabled(True)
        self._chat_unlock_btn.setText("Kiểm tra key")
        self._chat_apply_lock_state()
        self._av_apply_lock_state()

    # ── TTS tab handlers ───────────────────────────────────────────
    def _set_tts_v3_enabled(self, enabled: bool):
        self.settings["eleven_v3_style_enabled"] = bool(enabled)
        save_settings(self.settings)
        current_preview = getattr(self, "_enhanced_cache", "").strip()
        if not current_preview and hasattr(self, "preview_text"):
            current_preview = self.preview_text.toPlainText().strip()
        if current_preview:
            self._set_preview_status(
                "⚠️  Nhấn nhá v3 đã đổi. Bản đọc hiện tại vẫn giữ nguyên; nhấn Xem bản đọc để tạo lại.",
                "warning",
            )
        self._sync_tts_audio_button()

    def _all_styles(self) -> list[dict]:
        """Trả về toàn bộ styles: built-in + custom."""
        overrides = self.settings.get("prompt_preset_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        if "Viral" not in overrides:
            if "Vivid" in overrides:
                overrides["Viral"] = overrides.get("Vivid")
            elif "Hài hước" in overrides:
                overrides["Viral"] = overrides.get("Hài hước")

        def _builtin_style(name: str, default_prompt: str, default_temp: float) -> dict:
            ov = overrides.get(name, {})
            if not isinstance(ov, dict):
                ov = {}
            temp = ov.get("temperature", default_temp)
            try:
                temp = float(temp)
            except (TypeError, ValueError):
                temp = default_temp
            temp = max(0.0, min(1.0, temp))
            fallback_prompt = ov.get("prompt") or default_prompt
            return {
                "name": name,
                "prompt": read_style_prompt_file(name, fallback_prompt),
                "creative": ov.get("creative", temp >= 0.5),
                "temperature": temp,
                "builtin": True,
            }

        built = [
            _builtin_style("Viral", DEFAULT_PROMPT_FUNNY, 0.7),
        ]
        custom = []
        for s in self.settings.get("custom_styles", []):
            icon = s.get("icon", "")
            name = s.get("name", "")
            prompt = s.get("prompt", "")
            if not name or not prompt:
                continue  # bỏ qua entry hỏng
            display_name = re.sub(r"^[^\wÀ-ỹ]+", "", name).strip() or name
            prompt = read_style_prompt_file(name, prompt)
            custom.append({
                "name": display_name,
                "prompt": prompt,
                "creative": s.get("creative", False),
                "temperature": s.get(
                    "temperature", 0.7 if s.get("creative", False) else 0.3
                ),
            })
        return built + custom

    def _find_active_style_name(self, current_prompt: str) -> str:
        saved_name = self.settings.get("enhance_style_name", "")
        if saved_name in {"Hài hước", "Nghiêm túc", "Vivid"}:
            saved_name = "Viral"
        if saved_name and any(s["name"] == saved_name for s in self._all_styles()):
            return saved_name
        for s in self._all_styles():
            if s["prompt"] == current_prompt:
                return s["name"]
        return "Viral"

    def _build_style_buttons(self, layout: QHBoxLayout, active_name: str):
        """Xây (hoặc rebuild) các nút phong cách — built-in + custom."""
        # Xoá buttons cũ
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._prompt_btns.clear()

        for style in self._all_styles():
            name = style["name"]
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setChecked(name == active_name)
            btn.clicked.connect(lambda checked, n=name: self._set_prompt_style(n))
            self._prompt_btns[name] = btn
            layout.addWidget(btn)

        self._apply_prompt_btn_styles(active_name)

    def _set_prompt_style(self, name: str):
        if not name:
            return
        for s in self._all_styles():
            if s["name"] == name:
                temperature = s.get(
                    "temperature", 0.7 if s.get("creative", False) else 0.3
                )
                self.settings["enhance_prompt"]           = s["prompt"]
                self.settings["enhance_style_name"]       = name
                self.settings["enhance_style_temperature"] = temperature
                self.settings["enhance_style_creative"]   = s.get("creative", False)  # backward compat
                self._sync_creativity_control(temperature)
                save_settings(self.settings)
                return

    def _apply_prompt_btn_styles(self, active: str):
        for name, btn in self._prompt_btns.items():
            btn.setChecked(name == active)
            if name == active:
                btn.setStyleSheet(
                    f"QPushButton{{background:{SURFACE};color:{TEXT};border:none;"
                    f"border-radius:6px;padding:0px 14px;font-size:12px;font-weight:600;}}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{TEXT_MUTE};border:none;"
                    f"border-radius:6px;padding:0px 14px;font-size:12px;}}"
                    f"QPushButton:hover{{background:{CONTROL_HV};}}"
                )

    def _populate_style_combo(self, active_name: str):
        """Đổ toàn bộ styles vào _style_combo và chọn active_name."""
        if not hasattr(self, "_style_combo"):
            return
        combo = self._style_combo
        combo.blockSignals(True)
        combo.clear()
        for s in self._all_styles():
            combo.addItem(s["name"])
        idx = combo.findText(active_name)
        combo.setCurrentIndex(max(0, idx))
        self._fit_style_combo_to_items(combo)
        combo.blockSignals(False)

    def _fit_style_combo_to_items(self, combo: QComboBox) -> None:
        font = combo.font()
        font.setPixelSize(13)
        combo.setFont(font)
        fm = combo.fontMetrics()
        max_w = max(
            (fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())),
            default=84,
        )
        control_w = max(128, max_w + 58)
        popup_w = max(control_w, max_w + 104)
        combo.setMinimumWidth(control_w)
        combo.view().setMinimumWidth(popup_w)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        combo.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        combo.setItemDelegate(QStyledItemDelegate(combo))

    def _rebuild_style_buttons(self):
        """Gọi sau khi Settings saved để sync custom styles."""
        current_prompt = self.settings.get("enhance_prompt", DEFAULT_PROMPT_FUNNY)
        active_name    = self._find_active_style_name(current_prompt)
        self._populate_style_combo(active_name)
        self._sync_creativity_control(self.settings.get("enhance_style_temperature", 0.3))

    @staticmethod
    def _tier_label(temperature: float) -> str:
        """Trả về nhãn mức độ sáng tạo: chỉ báo khi khóa nội dung."""
        if temperature <= 0.0:
            return "Khóa nội dung"
        return ""

    @staticmethod
    def _creativity_detail_text(temperature: float) -> str:
        """Trích dòng 'Độ sâu làm mới' từ guide để hiển thị cho user."""
        guide = get_creativity_guide(temperature)
        for line in guide.split("\n"):
            if "Độ sâu" in line or "làm mới" in line:
                return line.strip("- ").strip()
        return ""

    def _sync_creativity_control(self, temperature: float | None = None):
        if not hasattr(self, "creativity_slider"):
            return
        t = self.settings.get("enhance_style_temperature", 0.3) if temperature is None else temperature
        t = max(0.0, min(1.0, float(t)))
        self.creativity_slider.blockSignals(True)
        self.creativity_slider.setValue(int(t * 100))
        self.creativity_slider.blockSignals(False)
        self.creativity_val.setText(f"{t:.2f}")
        if hasattr(self, "creativity_tier"):
            self.creativity_tier.setText(self._tier_label(t))
        if hasattr(self, "_creativity_detail"):
            self._creativity_detail.setText(self._creativity_detail_text(t))
        self.settings["enhance_style_temperature"] = t
        self.settings["enhance_style_creative"] = t >= 0.5

    def _quick_add_style(self):
        """Mở AddStyleDialog nhanh từ main UI."""
        dlg = AddStyleDialog(self, ds_api_key=self.settings.get("ds_api_key", ""), gemini_api_key=self.settings.get("gemini_api_key", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            write_style_prompt_file(result.get("name", ""), result.get("prompt", ""))
            self.settings.setdefault("custom_styles", []).append(result)
            style_name = result.get("name", "")
            self.settings["enhance_prompt"] = result["prompt"]
            self.settings["enhance_style_name"] = style_name
            self.settings["enhance_style_temperature"] = result.get("temperature", 0.3)
            self.settings["enhance_style_creative"] = result.get("creative", False)
            save_settings(self.settings)
            self._rebuild_style_buttons()

    def _make_favorites_combo(self, tool: str) -> QComboBox:
        """Tạo combo box chọn giọng yêu thích cho một tool ('tts' hoặc 'av')."""
        combo = _ApplePopupCombo()
        combo.setFixedHeight(30)
        combo.setMinimumWidth(140)
        combo.setStyleSheet(
            f"QComboBox{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};"
            f"border-radius:9px;padding:2px 24px 2px 10px;font-size:12px;color:{TEXT};}}"
            f"QComboBox:hover{{background:{CONTROL_HV};}}"
            f"QComboBox::drop-down{{border:none;}}"
            + self._combo_item_view_style(26)
        )
        self._populate_voice_combo(combo, tool)
        self._fit_favorites_combo(combo)

        current_vid = combo.currentData() or ""
        if current_vid and not self.settings.get(f"{tool}_voice_id", "").strip():
            self.settings[f"{tool}_voice_id"] = current_vid
            self.settings[f"{tool}_voice_name"] = combo.currentText()
            if tool == "av":
                self._av_write_voice_to_env(current_vid)
            try:
                save_settings(self.settings)
            except Exception as e:
                print(f"[WARN] cannot persist default {tool} voice: {e}")

        def _on_voice_selected(idx, t=tool, c=combo):
            vid = c.itemData(idx) or ""
            vname = c.itemText(idx)
            if t == "tts":
                self.settings["tts_voice_id"] = vid
                self.settings["tts_voice_name"] = vname
                self._tts_update_lang_for_voice(vid)
            else:
                self.settings["av_voice_id"] = vid
                self.settings["av_voice_name"] = vname
                self._av_write_voice_to_env(vid)
                self._av_update_lang_for_voice(vid)
                if hasattr(self, "_av_config_lbl"):
                    self._av_refresh_config_summary()
            save_settings(self.settings)

        combo.currentIndexChanged.connect(_on_voice_selected)
        return combo

    def _fit_favorites_combo(self, combo: QComboBox) -> None:
        fm = combo.fontMetrics()
        max_w = max(
            (fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())),
            default=120,
        )
        combo.setMinimumWidth(max(150, min(280, max_w + 48)))
        combo.view().setMinimumWidth(max(190, min(340, max_w + 88)))
        combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)

    def _av_write_voice_to_env(self, voice_id: str):
        """Sync Auto Video toolbar voice selection into engine .env.local."""
        if not voice_id:
            return False
        if not is_auto_video_unlocked(self.settings):
            return False
        env_path = get_auto_video_env_local(self.settings)
        explicit_engine = bool(
            os.environ.get("HEDRA_AUTO_VIDEO_ENGINE_DIR", "").strip()
            or os.environ.get("AUTO_VIDEO_ENGINE_DIR", "").strip()
            or str(self.settings.get("auto_video_engine_dir", "")).strip()
        )
        if not env_path.exists() and not explicit_engine:
            return False
        env = _read_env_local()
        provider = "elevenlabs"
        key_map = {
            "elevenlabs": "ELEVENLABS_VOICE_ID",
        }
        key = key_map.get(provider, "ELEVENLABS_VOICE_ID")
        updates = {key: voice_id}
        try:
            _write_env_local(updates)
            return True
        except Exception as e:
            print(f"[WARN] cannot sync Auto Video voice to .env.local: {e}")
            return False

    def _populate_voice_combo(self, combo: QComboBox, tool: str):
        """Đổ danh sách favorite_voices vào combo, chọn voice đang dùng."""
        favs = self.settings.get("favorite_voices", [])
        cur_id = self.settings.get(f"{tool}_voice_id", "")

        combo.blockSignals(True)
        combo.clear()
        if not favs:
            combo.addItem("Chưa có giọng yêu thích", "")
        else:
            for v in favs:
                vid   = v.get("id", "")
                vname = v.get("name", vid[:16] if vid else "?")
                combo.addItem(vname, vid)
            # Select current
            sel_idx = next((i for i in range(combo.count()) if combo.itemData(i) == cur_id), 0)
            combo.setCurrentIndex(sel_idx)
        combo.blockSignals(False)
        self._fit_favorites_combo(combo)

    def _sync_voice_combos(self):
        """Gọi sau khi favorites thay đổi — cập nhật cả hai combos."""
        if hasattr(self, "_tts_voice_combo"):
            try:
                self._populate_voice_combo(self._tts_voice_combo, "tts")
            except RuntimeError:
                pass
        if hasattr(self, "_av_voice_combo"):
            try:
                self._populate_voice_combo(self._av_voice_combo, "av")
            except RuntimeError:
                pass
        if hasattr(self, "_lang_combo") and hasattr(self, "_tts_voice_combo"):
            self._tts_update_lang_for_voice(self._tts_voice_combo.currentData() or "")
        if hasattr(self, "_av_lang_combo") and hasattr(self, "_av_voice_combo"):
            self._av_update_lang_for_voice(self._av_voice_combo.currentData() or "")

    def _av_update_lang_for_voice(self, voice_id: str):
        """Hiện đúng ngôn ngữ voice hỗ trợ (từ langs trong settings)."""
        if not hasattr(self, "_av_lang_combo"):
            return
        favs = self.settings.get("favorite_voices", [])
        voice = next((v for v in favs if v.get("id") == voice_id), None)
        langs = voice.get("langs") if voice else None
        if langs is None:
            langs = []

        self._av_lang_combo.blockSignals(True)
        self._av_lang_combo.clear()
        filtered = [(lbl, code) for lbl, code in _ELEVENLABS_LANGS if code in langs] if langs else list(_ELEVENLABS_LANGS)
        for lbl, code in filtered:
            self._av_lang_combo.addItem(lbl, code)
        saved = self.settings.get("av_language_code", "vi")
        idx = next((i for i in range(self._av_lang_combo.count()) if self._av_lang_combo.itemData(i) == saved), 0)
        self._av_lang_combo.setCurrentIndex(idx)
        self._av_lang_combo.setEnabled(True)
        self._av_lang_combo.blockSignals(False)

    def _tts_update_lang_for_voice(self, voice_id: str):
        """Hiện đúng ngôn ngữ voice hỗ trợ (từ langs trong settings)."""
        if not hasattr(self, "_lang_combo"):
            return
        favs = self.settings.get("favorite_voices", [])
        voice = next((v for v in favs if v.get("id") == voice_id), None)
        langs = voice.get("langs") if voice else None
        if langs is None:
            langs = []

        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        filtered = [(lbl, code) for lbl, code in _ELEVENLABS_LANGS if code in langs] if langs else list(_ELEVENLABS_LANGS)
        for lbl, code in filtered:
            self._lang_combo.addItem(lbl, code)
        saved = self.settings.get("tts_language_code", "vi")
        idx = next((i for i in range(self._lang_combo.count()) if self._lang_combo.itemData(i) == saved), 0)
        self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.setEnabled(True)
        self._lang_combo.blockSignals(False)

    def _open_voices_settings(self):
        """Mở Settings dialog và tự nhảy sang tab Voices."""
        dlg = SettingsDialog(self.settings, self._parent_ref)
        dlg._switch(2)   # index 2 = Voices
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            self._sync_voice_combos()
            self._rebuild_style_buttons()
            self._refresh_credits()

    def _check_update(self):
        self._updater = UpdateChecker()
        self._updater.update_found.connect(self._on_update_found)
        self._updater.no_update.connect(self._on_auto_no_update)
        self._track_thread("_updater", self._updater)

    def _manual_check_update(self):
        if not getattr(sys, "frozen", False):
            self._restart_local_source_app()
            return
        self._btn_check_update.setEnabled(False)
        self._btn_check_update.setText("Đang kiểm tra...")
        self._manual_updater = UpdateChecker()
        self._manual_updater.update_found.connect(self._on_manual_update_found)
        self._manual_updater.no_update.connect(self._on_manual_no_update)
        self._manual_updater.error.connect(self._on_manual_update_error)
        self._manual_updater.finished.connect(self._reset_update_button)
        self._track_thread("_manual_updater", self._manual_updater)

    def _reset_update_button(self):
        self._btn_check_update.setEnabled(True)
        self._btn_check_update.setText("Cập nhật")

    def _restart_local_source_app(self):
        """Relaunch local source build so newly edited code is loaded."""
        self._btn_check_update.setEnabled(False)
        self._btn_check_update.setText("Đang mở lại...")
        app_root = os.path.dirname(os.path.abspath(__file__))
        local_app = os.path.join(app_root, "Hedra Studio Local.app")
        run_command = os.path.join(app_root, "run.command")
        current_pid = os.getpid()
        script = f"""#!/bin/bash
APP_PID={current_pid}
APP_ROOT={shlex.quote(app_root)}
LOCAL_APP={shlex.quote(local_app)}
RUN_COMMAND={shlex.quote(run_command)}
LOG="/tmp/hedra_local_restart.log"

echo "$(date): Restart local Hedra Studio" > "$LOG"
echo "App root: $APP_ROOT" >> "$LOG"
echo "Waiting for PID $APP_PID to exit..." >> "$LOG"

for i in $(seq 1 20); do
    if ! kill -0 $APP_PID 2>/dev/null; then
        echo "$(date): App exited after ${{i}}s" >> "$LOG"
        break
    fi
    sleep 0.5
done

if kill -0 $APP_PID 2>/dev/null; then
    echo "$(date): Force killing PID $APP_PID" >> "$LOG"
    kill -9 $APP_PID 2>/dev/null || true
    sleep 1
fi

if [ -d "$LOCAL_APP" ]; then
    echo "$(date): Opening local app bundle" >> "$LOG"
    open -n "$LOCAL_APP" >> "$LOG" 2>&1 || true
elif [ -f "$RUN_COMMAND" ]; then
    echo "$(date): Opening run.command fallback" >> "$LOG"
    open "$RUN_COMMAND" >> "$LOG" 2>&1 || true
else
    echo "$(date): Running python fallback" >> "$LOG"
    cd "$APP_ROOT" && nohup "$APP_ROOT/venv/bin/python3" "$APP_ROOT/tts_app.py" >> "$LOG" 2>&1 &
fi
"""
        import tempfile
        fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="hedra_restart_")
        with os.fdopen(fd, "w") as f:
            f.write(script)
        os.chmod(script_path, 0o700)
        subprocess.Popen(
            ["/bin/bash", script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        QApplication.instance().quit()

    def _on_manual_update_found(self, version: str, url: str):
        self._on_update_found(version, url)
        QMessageBox.information(
            self,
            "Có bản cập nhật",
            f"Đã tìm thấy v{version}. Nhấn \"Cập nhật ngay\" trên banner để tải và cài đặt.",
        )

    def _on_manual_no_update(self, latest: str):
        QMessageBox.information(
            self,
            "Đã là bản mới nhất",
            f"Bạn đang dùng v{VERSION}. Release mới nhất hiện tại là v{latest}.",
        )

    def _on_manual_update_error(self, msg: str):
        QMessageBox.warning(self, "Không kiểm tra được cập nhật", msg)

    def _on_auto_no_update(self, latest: str):
        if hasattr(self, "_btn_check_update"):
            self._btn_check_update.setText("Mới nhất")
            self._btn_check_update.setToolTip(f"Đang dùng bản mới nhất v{latest}. Nhấn để kiểm tra lại.")

    def _on_update_found(self, version: str, url: str):
        self._update_url = url
        if hasattr(self, "_btn_check_update"):
            self._btn_check_update.setText("Có bản mới")
            self._btn_check_update.setToolTip(f"Có bản v{version}. Nhấn banner để cập nhật.")
        self._banner_text.setText(f"Có bản cập nhật v{version} — nhấn để tải, cài và tự mở lại")
        self.update_banner.setVisible(True)

    def _do_update(self):
        url = self._update_url
        # Nếu URL là trang HTML GitHub (không phải file trực tiếp) → mở browser
        if url and not (url.endswith(".dmg") or url.endswith(".exe")):
            import webbrowser
            webbrowser.open(url)
            return
        self._btn_dl.setEnabled(False)
        self._btn_dl.setText("Đang tải... 0%")
        self._dl = UpdateDownloader(url)
        self._dl.progress.connect(self._on_dl_progress)
        self._dl.done.connect(self._on_dl_done)
        self._dl.error.connect(self._on_dl_error)
        self._track_thread("_dl", self._dl)

    def _on_dl_progress(self, pct: int):
        self._btn_dl.setText(f"Đang tải... {pct}%")

    def _on_dl_done(self, path: str):
        self._btn_dl.setText("Đang cài đặt...")
        try:
            self._install_update(path)
        except Exception as e:
            self._on_dl_error(str(e))

    def _on_dl_error(self, msg: str):
        self._btn_dl.setEnabled(True)
        self._btn_dl.setText("Cập nhật ngay →")
        QMessageBox.critical(self, "Lỗi cập nhật", msg)

    def _install_update(self, file_path: str):
        if sys.platform == "darwin":
            if getattr(sys, "frozen", False):
                app_dest = os.path.normpath(
                    os.path.join(os.path.dirname(sys.executable), "..", "..")
                )
            else:
                app_dest = "/Applications/Hedra Studio.app"

            current_pid = os.getpid()
            source_run_command = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.command")

            script = f"""#!/bin/bash
# Hedra Studio auto-update script v4
DMG={shlex.quote(file_path)}
APP_DEST={shlex.quote(app_dest)}
APP_PID={current_pid}
RUN_COMMAND={shlex.quote(source_run_command)}
BUNDLE_ID="com.hedracentral.hedrastudio"
MNT="/tmp/hedrastudio_mnt"
LOG="/tmp/hedra_update.log"

echo "$(date): Starting update v4" > "$LOG"
echo "DMG: $DMG" >> "$LOG"
echo "Dest: $APP_DEST" >> "$LOG"
echo "Fallback run.command: $RUN_COMMAND" >> "$LOG"
echo "Waiting for PID $APP_PID to exit..." >> "$LOG"

# Chờ app cũ thoát — poll PID thay vì sleep cố định (max 30s)
for i in $(seq 1 30); do
    if ! kill -0 $APP_PID 2>/dev/null; then
        echo "$(date): App exited after ${{i}}s" >> "$LOG"
        break
    fi
    sleep 1
done

# Force kill nếu vẫn còn chạy
if kill -0 $APP_PID 2>/dev/null; then
    echo "$(date): Force killing PID $APP_PID" >> "$LOG"
    kill -9 $APP_PID 2>/dev/null || true
    sleep 2
fi

# Dọn mountpoint cũ nếu còn
if [ -d "$MNT" ]; then
    hdiutil detach "$MNT" -quiet -force 2>>"$LOG" || true
    sleep 1
    rm -rf "$MNT" 2>>"$LOG" || true
fi
mkdir -p "$MNT"

# Mount DMG
echo "$(date): Mounting DMG..." >> "$LOG"
hdiutil attach -nobrowse -mountpoint "$MNT" "$DMG" >> "$LOG" 2>&1
ATTACH_CODE=$?
if [ $ATTACH_CODE -ne 0 ]; then
    echo "ERROR: hdiutil attach failed (code $ATTACH_CODE)" >> "$LOG"
    exit 1
fi

APP_IN_DMG="$MNT/Hedra Studio.app"
if [ ! -d "$APP_IN_DMG" ]; then
    echo "ERROR: App not found in DMG" >> "$LOG"
    ls -la "$MNT" >> "$LOG" 2>&1
    hdiutil detach "$MNT" -quiet 2>>"$LOG" || true
    exit 1
fi

# Xóa app cũ — verify thành công
echo "$(date): Removing old app..." >> "$LOG"
rm -rf "$APP_DEST" 2>>"$LOG"
if [ -d "$APP_DEST" ]; then
    echo "ERROR: Could not remove old app (permission?)" >> "$LOG"
    hdiutil detach "$MNT" -quiet 2>>"$LOG" || true
    exit 1
fi

# Copy bằng ditto (giữ đúng metadata, reliable hơn cp -R)
echo "$(date): Copying new app with ditto..." >> "$LOG"
ditto "$APP_IN_DMG" "$APP_DEST" 2>>"$LOG"

if [ ! -d "$APP_DEST" ]; then
    echo "ERROR: ditto failed — $APP_DEST not found" >> "$LOG"
    hdiutil detach "$MNT" -quiet 2>>"$LOG" || true
    exit 1
fi
echo "$(date): Copy done" >> "$LOG"

# Unmount DMG
hdiutil detach "$MNT" -quiet 2>>"$LOG" || true
rm -rf "$MNT" 2>/dev/null

# Xóa quarantine + extended attributes
xattr -cr "$APP_DEST" 2>>"$LOG" || true

# Đăng ký lại với Launch Services
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DEST" >> "$LOG" 2>&1 || true

# Mở app mới. Thử bằng bundle id trước để Launch Services dùng bản vừa đăng ký,
# sau đó fallback mở trực tiếp app path. Nếu vẫn không thấy process, mở lại
# run.command để người dùng không phải tự bấm thủ công.
echo "$(date): Launching new app..." >> "$LOG"
LAUNCH_OK=0
for attempt in 1 2 3; do
    echo "$(date): Launch attempt $attempt via bundle id" >> "$LOG"
    open -n -b "$BUNDLE_ID" >> "$LOG" 2>&1 || true
    sleep 2
    if pgrep -f "HedraStudio|Hedra Studio|tts_app.py" >/dev/null 2>&1; then
        LAUNCH_OK=1
        echo "$(date): App launch detected after bundle id attempt $attempt" >> "$LOG"
        break
    fi

    echo "$(date): Launch attempt $attempt via app path" >> "$LOG"
    open -n "$APP_DEST" >> "$LOG" 2>&1 || true
    sleep 2
    if pgrep -f "HedraStudio|Hedra Studio|tts_app.py" >/dev/null 2>&1; then
        LAUNCH_OK=1
        echo "$(date): App launch detected after app path attempt $attempt" >> "$LOG"
        break
    fi
done

if [ "$LAUNCH_OK" -ne 1 ] && [ -f "$RUN_COMMAND" ]; then
    echo "$(date): App launch not detected, opening fallback run.command" >> "$LOG"
    open "$RUN_COMMAND" >> "$LOG" 2>&1 || true
    sleep 2
fi

echo "$(date): Done ✅" >> "$LOG"

# Dọn DMG tạm
rm -f "$DMG" 2>/dev/null
"""
            import tempfile
            fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="hedra_update_")
            with os.fdopen(fd, "w") as f:
                f.write(script)
            os.chmod(script_path, 0o700)
            subprocess.Popen(
                ["/bin/bash", script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        elif sys.platform == "win32":
            subprocess.Popen([file_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"])
        QApplication.instance().quit()

    def _refresh_credits(self):
        if self._closing:
            return
        el_keys    = self.settings.get("el_api_keys", [])
        has_el  = bool(el_keys)
        if not has_el:
            self._credits_refresh_pending = False
            self.credits_lbl.setText("⚠️  Chưa có ElevenLabs API key — vào Cài đặt → API")
            return
        if self._is_thread_running(self._credits_worker):
            self._credits_refresh_pending = True
            return
        self._credits_refresh_pending = False
        self.credits_lbl.setText("Credits: đang tải...")
        worker = _CreditsChecker(el_keys)

        def _on_done(text: str):
            if not self._closing and hasattr(self, "credits_lbl"):
                self.credits_lbl.setText(text)

        def _on_finished(_worker=worker):
            self._managed_threads.discard(_worker)
            if self._credits_worker is _worker:
                self._credits_worker = None
            if self._credits_refresh_pending and not self._closing:
                self._credits_refresh_pending = False
                QTimer.singleShot(0, self._refresh_credits)

        worker.done.connect(_on_done)
        worker.finished.connect(_on_finished)
        self._managed_threads.add(worker)
        self._credits_worker = worker
        worker.start()
    def _tts_preview_ready(self) -> bool:
        return bool(getattr(self, "_enhanced_cache", "").strip())

    def _sync_tts_audio_button(self):
        if not hasattr(self, "btn_gen"):
            return
        ready = self._tts_preview_ready()
        self.btn_gen.setEnabled(ready)
        self.btn_gen.setToolTip("Tạo audio từ Bản đọc đang hiển thị." if ready else "Nhấn Xem bản đọc trước để kiểm tra bản đã xử lý.")

    def _on_preview_text_changed(self):
        self._enhanced_cache = self.preview_text.toPlainText()
        self._sync_tts_audio_button()

    def _set_tts_review_mode(self, enabled: bool):
        if not hasattr(self, "_tts_splitter") or not hasattr(self, "_preview_box"):
            return
        self._preview_box.setVisible(enabled)
        if enabled:
            total = max(
                2,
                self._tts_splitter.height()
                if self._tts_splitter.orientation() == Qt.Orientation.Vertical
                else self._tts_splitter.width(),
            )
            ratio = float(self.settings.get("tts_splitter_ratio", 0.5) or 0.5)
            ratio = max(0.25, min(0.75, ratio))
            first = int(total * ratio)
            self._tts_splitter.setSizes([first, total - first])
        else:
            self._tts_splitter.setSizes([1, 0])

    def _save_tts_splitter_ratio(self, *_):
        if hasattr(self, "_tts_splitter_save_timer"):
            self._tts_splitter_save_timer.start()

    def _persist_tts_splitter_ratio(self):
        if not hasattr(self, "_tts_splitter") or not self._preview_box.isVisible():
            return
        sizes = self._tts_splitter.sizes()
        total = sum(sizes)
        if total <= 0:
            return
        self.settings["tts_splitter_ratio"] = round(sizes[0] / total, 3)
        save_settings(self.settings)

    def _sync_tts_scroll(self, source: QTextEdit, target: QTextEdit, value: int):
        if (
            self._tts_scroll_syncing
            or not hasattr(self, "_sync_scroll_btn")
            or not self._sync_scroll_btn.isChecked()
        ):
            return
        source_bar = source.verticalScrollBar()
        target_bar = target.verticalScrollBar()
        if source_bar.maximum() <= 0 or target_bar.maximum() <= 0:
            return
        self._tts_scroll_syncing = True
        try:
            ratio = value / source_bar.maximum()
            target_bar.setValue(round(ratio * target_bar.maximum()))
        finally:
            self._tts_scroll_syncing = False

    @staticmethod
    def _format_audio_time(milliseconds: int) -> str:
        seconds = max(0, int(milliseconds // 1000))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _on_output_position_changed(self, position: int):
        if not hasattr(self, "_audio_progress"):
            return
        duration = max(0, self._output_player.duration())
        if not self._audio_progress.isSliderDown():
            self._audio_progress.setValue(int(position * 1000 / duration) if duration else 0)
        self._audio_time_lbl.setText(
            f"{self._format_audio_time(position)} / {self._format_audio_time(duration)}"
        )

    def _on_output_duration_changed(self, duration: int):
        if not hasattr(self, "_audio_progress"):
            return
        self._audio_progress.setEnabled(duration > 0)
        self._audio_time_lbl.setText(f"00:00 / {self._format_audio_time(duration)}")

    def _seek_output_audio(self, value: int):
        duration = max(0, self._output_player.duration())
        if duration:
            self._output_player.setPosition(int(duration * value / 1000))

    def _copy_output_path(self, kind: str):
        path = self._last_srt_path if kind == "srt" else self._last_audio_path
        if not path or not os.path.exists(path):
            self.tts_status_lbl.setText("Chưa có file để sao chép đường dẫn")
            return
        QApplication.clipboard().setText(path)
        self.tts_status_lbl.setText("Đã sao chép đường dẫn SRT" if kind == "srt" else "Đã sao chép đường dẫn audio")

    def _generate(self):
        if self._is_thread_running(getattr(self, "worker", None)):
            self.tts_status_lbl.setText("Audio đang được tạo, vui lòng chờ hoàn tất.")
            return
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Paste kịch bản vào trước nhé!")
            return
        preview_text = getattr(self, "_enhanced_cache", "").strip()
        if not preview_text:
            self._sync_tts_audio_button()
            QMessageBox.warning(
                self,
                "Cần xem kịch bản trước",
                "Nhấn Xem bản đọc để tool xử lý kịch bản trước, rồi mới tạo audio.",
            )
            self._btn_preview.setFocus()
            return

        # TTS chạy trực tiếp bằng ElevenLabs v3.
        has_tts = bool(self.settings.get("el_api_keys"))
        if not has_tts:
            QMessageBox.warning(self, "Thiếu TTS API Key",
                                "Cần ElevenLabs API Key để tạo audio.\n\n"
                                "Vào Cài đặt → API để thêm.")
            return

        filename = self.filename_input.text().strip() or suggest_tts_filename(preview_text)
        safe_filename = os.path.basename(filename).strip()
        if safe_filename.lower().endswith(".mp3"):
            safe_filename = safe_filename[:-4].strip()
        safe_filename = safe_filename.replace(" ", "_")
        if not safe_filename:
            QMessageBox.warning(self, "Tên file không hợp lệ", "Nhập lại tên file ngắn gọn hơn nhé!")
            self.filename_input.setFocus()
            return
        out_dir = get_tool_output_dir(self.settings, "tts")
        audio_path = os.path.join(out_dir, safe_filename + ".mp3")
        srt_path = os.path.splitext(audio_path)[0] + ".srt"
        existing = [p for p in (audio_path, srt_path) if os.path.exists(p)]
        if existing:
            names = "\n".join(f"• {os.path.basename(p)}" for p in existing)
            reply = QMessageBox.question(
                self,
                "File đã tồn tại",
                f"Các file này đã tồn tại trong thư mục output:\n\n{names}\n\nBạn có muốn lưu đè không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.tts_status_lbl.setText("Đã hủy để tránh ghi đè file.")
                self.filename_input.setFocus()
                return
        if safe_filename != filename:
            self.filename_input.setText(safe_filename)
        speed = self.slider.value() / 10
        if hasattr(self, "creativity_slider"):
            t = self.creativity_slider.value() / 100.0
            self.settings["enhance_style_temperature"] = t
            self.settings["enhance_style_creative"] = t >= 0.5
            save_settings(self.settings)
        self.btn_gen.setEnabled(False)
        if self._output_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._output_player.stop()
        self.tts_status_lbl.setText("Đang khởi động")
        self.tts_status_lbl.setStyleSheet(f"color:{WARNING};font-size:12px;background:transparent;border:none;")
        self._btn_play_audio.setEnabled(False)
        self._btn_open_folder.setEnabled(False)
        self._audio_progress.setEnabled(False)
        self._audio_progress.setValue(0)
        self._audio_time_lbl.setText("00:00 / 00:00")

        self.worker = _TTSOnlyWorker(preview_text, speed, safe_filename, self.settings)

        self.worker.status.connect(self._on_tts_status)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self._track_thread("worker", self.worker)

    # ── Preview handlers ──────────────────────────────────────────────
    def _do_preview(self):
        if self._is_thread_running(getattr(self, "_preview_worker", None)):
            self._set_preview_status("AI đang xử lý kịch bản, vui lòng chờ.", "processing")
            return
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Paste kịch bản vào trước nhé!")
            return
        if not str(self.settings.get("ds_api_key") or "").strip():
            deepseek_model = self.settings.get("deepseek_tts_model", "deepseek-v4-flash")
            QMessageBox.warning(
                self,
                "Thiếu DeepSeek API Key",
                f"Pipeline TTS 2 bước dùng {deepseek_model} để xử lý kịch bản.\n\n"
                "Vào Cài đặt → API và thêm DeepSeek API Key.",
            )
            return
        self._btn_preview.setEnabled(False)
        self._btn_preview.setText("Đang xử lý...")
        self._enhanced_cache = ""
        self._sync_tts_audio_button()
        self._preview_box.setVisible(True)
        self._set_tts_review_mode(True)
        self.preview_text.setPlainText("")
        self._set_preview_status("⏳  AI đang xử lý kịch bản... vui lòng chờ", "processing")
        self._preview_worker = PreviewWorker(text, self.settings)
        self._preview_worker.status.connect(lambda m: self._set_preview_status(m, "processing"))
        self._preview_worker.done.connect(self._on_preview_done)
        self._preview_worker.error.connect(self._on_preview_error_msg)
        self._track_thread("_preview_worker", self._preview_worker)

    def _on_preview_done(self, enhanced: str):
        self._enhanced_cache = enhanced
        self.preview_text.setPlainText(enhanced)
        if hasattr(self, "filename_input") and not self.filename_input.text().strip():
            self.filename_input.setText(suggest_tts_filename(enhanced))
        self._set_preview_status("✅  Bản đọc đã sẵn sàng. Chỉnh ở ô này nếu cần rồi bấm Tạo audio.", "success")
        self._btn_preview.setEnabled(True)
        self._btn_preview.setText("Xem bản đọc")
        # Khi user chỉnh sửa preview → cập nhật cache
        try:
            self.preview_text.textChanged.disconnect()
        except TypeError:
            pass
        self.preview_text.textChanged.connect(self._on_preview_text_changed)
        self._sync_tts_audio_button()
        self.preview_text.setFocus()

    def _on_preview_error_msg(self, msg: str):
        self._enhanced_cache = ""
        self._set_tts_review_mode(False)
        self._sync_tts_audio_button()
        self._set_preview_status(f"❌  {msg}", "error")
        self.tts_status_lbl.setText(f"Không tạo được Bản đọc: {msg}")
        self.tts_status_lbl.setStyleSheet(
            f"color:{DESTRUCTIVE};font-size:11px;background:transparent;border:none;"
        )
        self._btn_preview.setEnabled(True)
        self._btn_preview.setText("Xem bản đọc")

    def _on_script_changed(self):
        """Khi sửa kịch bản gốc → reset preview để tránh gen sai."""
        self._enhanced_cache = ""
        if hasattr(self, "preview_text"):
            self.preview_text.setPlainText("")
        if hasattr(self, "_preview_box"):
            self._preview_box.setVisible(False)
        self._set_tts_review_mode(False)
        self._sync_tts_audio_button()
        if hasattr(self, "_preview_status"):
            self._set_preview_status("", "idle")

    def _on_tts_status(self, msg: str):
        self.tts_status_lbl.setText(msg)
        self.tts_status_lbl.setStyleSheet(
            f"color:{WARNING}; font-size:11px; background:transparent;"
        )

    def _on_done(self, path: str):
        self._sync_tts_audio_button()
        self.tts_status_lbl.setText("Tạo audio thành công")
        self.tts_status_lbl.setStyleSheet(
            f"color:{SUCCESS}; font-size:12px; font-weight:600; background:transparent;"
        )
        self._last_audio_path = path
        self._last_srt_path = os.path.splitext(path)[0] + ".srt"
        self._btn_play_audio.setEnabled(True)
        self._btn_open_folder.setEnabled(True)
        self._btn_play_audio.setText("▶")
        self.tts_status_lbl.setText(
            "Sẵn sàng nghe lại · MP3 và SRT đã lưu tự động"
            if os.path.exists(self._last_srt_path)
            else "Sẵn sàng nghe lại · MP3 đã lưu"
        )
        # Disconnect cũ an toàn — tránh TypeError nếu chưa có connection nào
        try:
            self._btn_open_folder.clicked.disconnect()
        except TypeError:
            pass
        self._btn_open_folder.clicked.connect(lambda: reveal_file(self._last_audio_path))
        self._refresh_credits()
        QTimer.singleShot(4000, self._reset_tts_status)

    def _export_tts_srt(self):
        srt_path = getattr(self, "_last_srt_path", "")
        if not srt_path or not os.path.exists(srt_path):
            QMessageBox.warning(
                self,
                "Chưa có SRT",
                "Audio hiện tại chưa có file phụ đề SRT. Hãy tạo audio lại để tool xuất SRT đi kèm.",
            )
            return
        default_name = os.path.splitext(os.path.basename(srt_path))[0] + ".srt"
        default_path = os.path.join(os.path.dirname(srt_path), default_name)
        target, _ = QFileDialog.getSaveFileName(self, "Xuất file SRT", default_path, "SRT files (*.srt)")
        if not target:
            return
        if not target.lower().endswith(".srt"):
            target += ".srt"
        try:
            shutil.copyfile(srt_path, target)
            reveal_file(target)
        except Exception as e:
            QMessageBox.critical(self, "Không xuất được SRT", str(e))

    def _toggle_last_audio(self):
        if not self._last_audio_path or not os.path.exists(self._last_audio_path):
            QMessageBox.warning(self, "Không thấy file", "File audio vừa tạo không còn tồn tại.")
            return
        if self._output_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._output_player.stop()
            return
        self._output_player.setSource(QUrl.fromLocalFile(self._last_audio_path))
        self._output_player.play()
        self._btn_play_audio.setText("■")
        self.tts_status_lbl.setText("Đang phát")
        self.tts_status_lbl.setStyleSheet(
            f"color:{SUCCESS}; font-size:12px; font-weight:600; background:transparent;"
        )

    def _on_output_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState and hasattr(self, "_btn_play_audio"):
            self._btn_play_audio.setText("▶")
            if getattr(self, "_last_audio_path", ""):
                self.tts_status_lbl.setText("Sẵn sàng nghe lại · MP3 và SRT đã lưu tự động")
                self.tts_status_lbl.setStyleSheet(
                    f"color:{TEXT_MUTE}; font-size:12px; background:transparent;"
                )

    def _reset_tts_status(self):
        if self._output_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        self.tts_status_lbl.setText(
            "Sẵn sàng nghe lại · MP3 và SRT đã lưu tự động"
            if getattr(self, "_last_audio_path", "") else "Chưa có audio"
        )
        self.tts_status_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:12px; background:transparent;"
        )

    def _on_error(self, msg: str):
        self._sync_tts_audio_button()
        self.tts_status_lbl.setText("Có lỗi xảy ra")
        self.tts_status_lbl.setStyleSheet(
            f"color:{DESTRUCTIVE}; font-size:12px; font-weight:600; background:transparent;"
        )
        clean_msg = re.sub(r"(sk-[A-Za-z0-9_\\-]{8,}|sk_[A-Za-z0-9_\\-]{8,}|[A-Fa-f0-9]{32,})", "***", str(msg or ""))
        friendly = humanize_tts_error(clean_msg)
        short_msg = f"{friendly['detail']} {friendly['action']}".strip()
        if len(short_msg) > 320:
            short_msg = short_msg[:317].rstrip() + "..."
        has_old_audio = bool(getattr(self, "_last_audio_path", "") and os.path.exists(self._last_audio_path))
        self._btn_play_audio.setEnabled(has_old_audio)
        self._btn_open_folder.setEnabled(has_old_audio)
        QMessageBox.critical(
            self,
            friendly["title"],
            f"{friendly['detail']}\n\nCách xử lý: {friendly['action']}",
        )

    def _open_feedback(self):
        dlg = FeedbackDialog(
            self,
            version=VERSION,
            telegram_cfg={
                "bot_token": TELEGRAM_BOT_TOKEN,
                "chat_id": TELEGRAM_CHAT_ID,
            },
        )
        dlg.exec()

    def open_settings(self):
        try:
            self.settings.update(load_settings())
        except Exception:
            pass
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_settings = dlg.get_settings()
            try:
                save_settings(new_settings)
            except Exception as e:
                QMessageBox.warning(self, "Lỗi lưu cài đặt", str(e))
            try:
                self.update_settings(new_settings)
                self._refresh_credits()
                self._rebuild_style_buttons()
                self._sync_creativity_control(self.settings.get("enhance_style_temperature", 0.3))
                self._sync_voice_combos()
            except Exception:
                pass  # Không crash app nếu refresh lỗi

    # ── Tab: Auto Video ────────────────────────────────────────────────

    def _build_auto_video_tab(self) -> QWidget:
        page, layout = self._student_page()
        env = _read_env_local()
        self._av_license_unlocked = is_auto_video_unlocked(self.settings)

        # ── Toolbar card (1 row) ──────────────────────────────────────
        toolbar, tc = self._card()
        row_all = QHBoxLayout()
        row_all.setContentsMargins(14, 8, 14, 8)
        row_all.setSpacing(6)

        def _lbl_combo(label_text: str, widget: QWidget) -> QWidget:
            w = QWidget()
            w.setStyleSheet("QWidget{background:transparent;border:none;}")
            h_lay = QHBoxLayout(w)
            h_lay.setContentsMargins(0, 0, 0, 0)
            h_lay.setSpacing(5)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;"
            )
            h_lay.addWidget(lbl)
            h_lay.addWidget(widget)
            return w

        self._av_article_toolbar_widgets = []

        saved_mode = self.settings.get("auto_video_mode", "article")
        if saved_mode not in {"article", "oneshot"}:
            saved_mode = "article"
            self.settings["auto_video_mode"] = saved_mode
        self._av_mode = self._av_quick_choice(
            [("Tạo bài", "article"), ("Edit one-shot", "oneshot")],
            saved_mode,
        )
        self._av_mode.currentIndexChanged.connect(self._av_switch_mode)
        row_all.addWidget(_lbl_combo("Mode", self._av_mode))
        row_all.addSpacing(8)

        self._av_one_shot_toolbar_widgets = []
        self._os_industry_combo = self._av_quick_combo(
            [
                ("Công nghệ", "tech"),
                ("Tài chính", "finance"),
            ],
            self.settings.get("one_shot_industry", "tech"),
        )
        self._os_industry_combo.currentIndexChanged.connect(self._os_save_toolbar_settings)
        industry_wrap = _lbl_combo("Ngành", self._os_industry_combo)
        self._av_one_shot_toolbar_widgets.append(industry_wrap)
        row_all.addWidget(industry_wrap)

        row_all.addSpacing(8)

        self._os_pipeline_combo = self._av_quick_combo(
            [
                ("Đơn giản", "simple"),
                ("Enterprise", "enterprise"),
            ],
            self.settings.get("one_shot_pipeline_mode", "simple"),
        )
        self._os_pipeline_combo.currentIndexChanged.connect(self._os_on_pipeline_mode_changed)
        pipeline_wrap = _lbl_combo("Quy trình", self._os_pipeline_combo)
        self._av_one_shot_toolbar_widgets.append(pipeline_wrap)
        row_all.addWidget(pipeline_wrap)

        row_all.addSpacing(8)

        self._os_render_profile = self._av_quick_combo(
            [
                ("1080 đa nền tảng", "multi_1080"),
                ("1440 nét", "sharp_1440"),
                ("Gốc", "source"),
            ],
            self.settings.get("one_shot_render_profile", "multi_1080"),
        )
        self._os_render_profile.currentIndexChanged.connect(self._os_save_toolbar_settings)
        profile_wrap = _lbl_combo("Xuất", self._os_render_profile)
        self._av_one_shot_toolbar_widgets.append(profile_wrap)
        row_all.addWidget(profile_wrap)

        row_all.addSpacing(8)

        cut_current = "on" if bool(self.settings.get("one_shot_cut_video", False)) else "off"
        self._os_cut_toggle = self._av_quick_choice([("Bật", "on"), ("Tắt", "off")], cut_current)
        self._os_cut_toggle.currentIndexChanged.connect(self._os_save_toolbar_settings)
        cut_wrap = _lbl_combo("Cut", self._os_cut_toggle)
        self._av_one_shot_toolbar_widgets.append(cut_wrap)
        row_all.addWidget(cut_wrap)

        row_all.addSpacing(8)

        noise_current = str(self.settings.get("one_shot_noise_mode") or "").strip().lower()
        if not noise_current:
            noise_current = "auto_gentle" if bool(self.settings.get("one_shot_noise_reduce", True)) else "off"
        if noise_current not in {"auto_gentle", "off", "strong"}:
            noise_current = "auto_gentle"
        self._os_noise_toggle = self._av_quick_choice(
            [("Auto", "auto_gentle"), ("Tắt", "off"), ("Mạnh", "strong")],
            noise_current,
        )
        self._os_noise_toggle.currentIndexChanged.connect(self._os_save_toolbar_settings)
        noise_wrap = _lbl_combo("Noise", self._os_noise_toggle)
        self._av_one_shot_toolbar_widgets.append(noise_wrap)
        row_all.addWidget(noise_wrap)

        row_all.addSpacing(8)

        lut_current = "on" if bool(self.settings.get("one_shot_apply_lut", True)) else "off"
        self._os_lut_toggle = self._av_quick_choice([("Bật", "on"), ("Tắt", "off")], lut_current)
        self._os_lut_toggle.currentIndexChanged.connect(self._os_save_toolbar_settings)
        lut_toggle_wrap = _lbl_combo("LUT", self._os_lut_toggle)
        self._av_one_shot_toolbar_widgets.append(lut_toggle_wrap)
        row_all.addWidget(lut_toggle_wrap)

        row_all.addSpacing(8)

        self._os_lut_btn = QPushButton(self._os_lut_toolbar_text())
        self._os_lut_btn.setFixedHeight(30)
        self._os_lut_btn.setMaximumWidth(210)
        self._os_lut_btn.setToolTip(self._os_lut_display_text())
        self._os_lut_btn.setStyleSheet(self._compact_secondary_style())
        self._os_lut_btn.clicked.connect(self._os_choose_lut)
        lut_file_wrap = self._os_lut_btn
        self._av_one_shot_toolbar_widgets.append(lut_file_wrap)
        row_all.addWidget(lut_file_wrap)

        row_all.addSpacing(8)

        self._os_font_combo = self._av_quick_combo(
            [
                ("Phudu Black", "dt_phudu_black"),
                ("Phudu Bold", "dt_phudu_bold"),
                ("Arial Bold", "arial_bold"),
                ("Arial Unicode", "arial_unicode"),
            ],
            self.settings.get("one_shot_thumbnail_font", "dt_phudu_black"),
        )
        self._os_font_combo.currentIndexChanged.connect(self._os_save_toolbar_settings)
        font_wrap = _lbl_combo("Font", self._os_font_combo)
        self._av_one_shot_toolbar_widgets.append(font_wrap)
        row_all.addWidget(font_wrap)

        row_all.addSpacing(8)

        review_current = "on" if bool(self.settings.get("one_shot_ai_review_thumbnail", True)) else "off"
        self._os_review_toggle = self._av_quick_choice([("Bật", "on"), ("Tắt", "off")], review_current)
        self._os_review_toggle.currentIndexChanged.connect(self._os_save_toolbar_settings)
        review_wrap = _lbl_combo("AI", self._os_review_toggle)
        self._av_one_shot_toolbar_widgets.append(review_wrap)
        row_all.addWidget(review_wrap)

        row_all.addSpacing(8)

        # Script preset — short display labels, real values as data
        self._av_script_preset = self._av_quick_combo(
            [
                ("News nhanh", "ai_news_fast"),
                ("GitHub",     "github_repo_story"),
                ("Research",   "research_explainer"),
                ("Classic",    "classic"),
            ],
            env.get("AUTO_VIDEO_SCRIPT_PRESET", "ai_news_fast"),
        )
        self._av_script_preset.currentIndexChanged.connect(self._av_save_quick_presets)
        preset_wrap = _lbl_combo("Preset", self._av_script_preset)
        self._av_article_toolbar_widgets.append(preset_wrap)
        row_all.addWidget(preset_wrap)

        row_all.addSpacing(8)

        # Visual preset
        self._av_visual_preset = self._av_quick_combo(
            [
                ("Dark",    "ai_news_dark"),
                ("Cream",   "cream_editorial"),
                ("Classic", "classic"),
            ],
            env.get("AUTO_VIDEO_VISUAL_PRESET", "ai_news_dark"),
        )
        self._av_visual_preset.currentIndexChanged.connect(self._av_save_quick_presets)
        visual_wrap = _lbl_combo("Giao diện", self._av_visual_preset)
        self._av_article_toolbar_widgets.append(visual_wrap)
        row_all.addWidget(visual_wrap)

        row_all.addSpacing(8)

        # Subtitle toggle
        caption_on = str(env.get("AUTO_VIDEO_BURN_CAPTIONS", "false")).strip().lower() in (
            "1", "true", "yes", "on"
        )
        self._av_sub_toggle = self._av_quick_choice(
            [("Tắt", "off"), ("Bật", "on")],
            "on" if caption_on else "off",
        )
        self._av_sub_toggle.currentIndexChanged.connect(self._av_save_quick_presets)
        sub_wrap = _lbl_combo("Sub", self._av_sub_toggle)
        self._av_article_toolbar_widgets.append(sub_wrap)
        row_all.addWidget(sub_wrap)

        row_all.addSpacing(8)

        # Pace
        self._av_pace = self._av_quick_choice(
            [("Dynamic", "dynamic"), ("Chuẩn", "standard")],
            env.get("AUTO_VIDEO_EDITING_PACE", "dynamic"),
        )
        self._av_pace.currentIndexChanged.connect(self._av_save_quick_presets)
        pace_wrap = _lbl_combo("Nhịp", self._av_pace)
        self._av_article_toolbar_widgets.append(pace_wrap)
        row_all.addWidget(pace_wrap)

        # Divider
        sep = QWidget()
        sep.setFixedSize(1, 20)
        sep.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        self._av_article_toolbar_widgets.append(sep)
        row_all.addSpacing(8)
        row_all.addWidget(sep)
        row_all.addSpacing(8)

        # Voice
        self._av_voice_combo = self._make_favorites_combo("av")
        self._av_article_toolbar_widgets.append(self._av_voice_combo)
        row_all.addWidget(self._av_voice_combo)
        self._av_write_voice_to_env(self._av_voice_combo.currentData() or "")

        row_all.addSpacing(6)

        # Language
        self._av_lang_code = self.settings.get("av_language_code", self.settings.get("tts_language_code", "vi"))
        self._av_lang_combo = _ApplePopupCombo()
        self._av_lang_combo.setFixedHeight(30)
        self._av_lang_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._av_lang_combo.setStyleSheet(
            f"QComboBox{{background:{CONTROL_BG};border:none;"
            f"border-radius:8px;padding:3px 8px 3px 10px;font-size:12px;color:{TEXT};}}"
            f"QComboBox:hover{{background:{CONTROL_HV};}}"
            f"QComboBox:focus{{background:{CONTROL_HV};}}"
            "QComboBox QAbstractScrollArea{background:transparent;border:none;}"
            "QComboBox QAbstractItemView{"
            f"background:{SURFACE};color:{TEXT};"
            f"border:1px solid {BORDER};border-radius:10px;"
            "padding:4px;outline:none;}"
            "QComboBox QAbstractItemView::item{min-height:26px;padding:3px 12px;"
            f"color:{TEXT};border-radius:6px;}}"
            f"QComboBox QAbstractItemView::item:selected{{background:{CONTROL_HV};color:{ACCENT};"
            "font-weight:600;}"
        )
        self._av_lang_combo.setItemDelegate(QStyledItemDelegate(self._av_lang_combo))
        self._av_lang_combo.currentIndexChanged.connect(lambda _: self._av_save_language())
        self._av_article_toolbar_widgets.append(self._av_lang_combo)
        row_all.addWidget(self._av_lang_combo)
        # Init: filter lang combo theo voice đang chọn ngay khi load
        self._av_update_lang_for_voice(self._av_voice_combo.currentData() or "")

        row_all.addStretch()

        # Generate button
        self._av_gen_btn = QPushButton("✦  Generate Video")
        self._av_gen_btn.setFixedHeight(34)
        self._av_gen_btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;"
            f"border-radius:9px;font-size:13px;font-weight:700;padding:0 18px;}}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            f"QPushButton:pressed{{background:{ACCENT_DN};}}"
            f"QPushButton:disabled{{background:{CONTROL_BG};color:{TEXT_FAINT};}}"
        )
        self._av_gen_btn.clicked.connect(self._av_on_generate)
        row_all.addWidget(self._av_gen_btn)

        row_all.addSpacing(6)

        # Settings button
        btn_settings = QPushButton()
        btn_settings.setIcon(ui_icon("settings", 16, TEXT_MUTE))
        btn_settings.setIconSize(icon_size(16))
        btn_settings.setFixedSize(32, 32)
        btn_settings.setToolTip("Cấu hình pipeline Auto Video")
        btn_settings.setStyleSheet(
            f"QPushButton{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};"
            f"border-radius:8px;padding:0;}}"
            f"QPushButton:hover{{background:{CONTROL_HV};}}"
        )
        btn_settings.clicked.connect(self.open_settings)
        row_all.addWidget(btn_settings)

        tc_wrap = QWidget()
        tc_wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
        tc_wrap.setMinimumWidth(1020)
        tc_wrap.setLayout(row_all)
        toolbar_scroll = QScrollArea()
        toolbar_scroll.setWidgetResizable(True)
        toolbar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        toolbar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        toolbar_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:horizontal{height:5px;background:transparent;}"
            f"QScrollBar::handle:horizontal{{background:{BORDER_SOFT};border-radius:2px;}}"
            "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;height:0;}"
        )
        toolbar_scroll.setWidget(tc_wrap)
        tc.addWidget(toolbar_scroll)
        layout.addWidget(toolbar)

        # ── Two-panel body ────────────────────────────────────────────
        body_w = QWidget()
        body_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        body_lay = QHBoxLayout(body_w)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(14)

        # ── Left panel: Nguồn ─────────────────────────────────────────
        left_card, left_vbox = self._card()

        src_hdr = QWidget()
        src_hdr.setStyleSheet("QWidget{background:transparent;border:none;}")
        src_hdr_h = QHBoxLayout(src_hdr)
        src_hdr_h.setContentsMargins(16, 11, 16, 11)
        src_hdr_h.setSpacing(8)
        src_ico = QLabel()
        src_ico.setPixmap(ui_icon("script", 15, TEXT_MUTE).pixmap(icon_size(15)))
        src_hdr_h.addWidget(src_ico)
        src_title_lbl = QLabel("Nguồn")
        src_title_lbl.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{TEXT};background:transparent;border:none;"
        )
        src_hdr_h.addWidget(src_title_lbl)
        src_hdr_h.addStretch()
        left_vbox.addWidget(src_hdr)

        src_div = QWidget()
        src_div.setFixedHeight(1)
        src_div.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        left_vbox.addWidget(src_div)

        # URL field
        url_wrap = QWidget()
        url_wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
        url_vl = QVBoxLayout(url_wrap)
        url_vl.setContentsMargins(16, 12, 16, 0)
        url_vl.setSpacing(5)
        url_cap = QLabel("Link bài báo")
        url_cap.setStyleSheet(
            f"font-size:11px;font-weight:600;color:{TEXT_MUTE};background:transparent;border:none;"
        )
        url_vl.addWidget(url_cap)
        self._av_url = QLineEdit()
        self._av_url.setPlaceholderText("https://vnexpress.net/bai-viet...")
        self._av_url.setFixedHeight(34)
        self._av_url.setStyleSheet(
            f"QLineEdit{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};"
            f"border-radius:8px;color:{TEXT};font-size:13px;padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{ACCENT};}}"
        )
        self._av_url.returnPressed.connect(self._av_on_generate)
        url_vl.addWidget(self._av_url)
        left_vbox.addWidget(url_wrap)

        # "Hoặc" divider
        or_row = QWidget()
        or_row.setStyleSheet("QWidget{background:transparent;border:none;}")
        or_h = QHBoxLayout(or_row)
        or_h.setContentsMargins(16, 8, 16, 0)
        or_h.setSpacing(8)
        or_ln_l = QWidget()
        or_ln_l.setFixedHeight(1)
        or_ln_l.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        or_lbl = QLabel("hoặc")
        or_lbl.setStyleSheet(
            f"font-size:11px;color:{TEXT_FAINT};background:transparent;border:none;"
        )
        or_ln_r = QWidget()
        or_ln_r.setFixedHeight(1)
        or_ln_r.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        or_h.addWidget(or_ln_l, 1)
        or_h.addWidget(or_lbl)
        or_h.addWidget(or_ln_r, 1)
        left_vbox.addWidget(or_row)

        # Text area
        txt_wrap = QWidget()
        txt_wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
        txt_vl = QVBoxLayout(txt_wrap)
        txt_vl.setContentsMargins(16, 8, 16, 0)
        txt_vl.setSpacing(5)
        txt_cap = QLabel("Paste nội dung")
        txt_cap.setStyleSheet(
            f"font-size:11px;font-weight:600;color:{TEXT_MUTE};background:transparent;border:none;"
        )
        txt_vl.addWidget(txt_cap)
        self._av_text = QTextEdit()
        self._av_text.setPlaceholderText(
            "Hoặc paste nội dung bài báo vào đây…\n"
            "AI sẽ tự tóm tắt và tạo script video."
        )
        self._av_text.setStyleSheet(
            f"QTextEdit{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};"
            f"border-radius:8px;color:{TEXT};font-size:13px;padding:8px 10px;}}"
            f"QTextEdit:focus{{border-color:{ACCENT};}}"
        )
        txt_vl.addWidget(self._av_text)
        left_vbox.addWidget(txt_wrap, 1)

        # Config summary footer
        cfg_wrap = QWidget()
        cfg_wrap.setStyleSheet("QWidget{background:transparent;border:none;}")
        cfg_vl = QVBoxLayout(cfg_wrap)
        cfg_vl.setContentsMargins(16, 8, 16, 12)
        self._av_config_lbl = QLabel("")
        self._av_config_lbl.setWordWrap(True)
        self._av_config_lbl.setStyleSheet(
            f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;"
        )
        cfg_vl.addWidget(self._av_config_lbl)
        left_vbox.addWidget(cfg_wrap)
        self._av_refresh_config_summary()

        body_lay.addWidget(left_card, 5)

        # ── Right panel: Kết quả ──────────────────────────────────────
        right_card, right_vbox = self._card()

        res_hdr = QWidget()
        res_hdr.setStyleSheet("QWidget{background:transparent;border:none;}")
        res_hdr_h = QHBoxLayout(res_hdr)
        res_hdr_h.setContentsMargins(16, 11, 16, 11)
        res_hdr_h.setSpacing(8)
        res_ico = QLabel()
        res_ico.setPixmap(ui_icon("video", 15, TEXT_MUTE).pixmap(icon_size(15)))
        res_hdr_h.addWidget(res_ico)
        res_title_lbl = QLabel("Kết quả")
        res_title_lbl.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{TEXT};background:transparent;border:none;"
        )
        res_hdr_h.addWidget(res_title_lbl)
        res_hdr_h.addStretch()
        right_vbox.addWidget(res_hdr)

        res_div = QWidget()
        res_div.setFixedHeight(1)
        res_div.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        right_vbox.addWidget(res_div)

        # Inner padded content
        ri = QWidget()
        ri.setStyleSheet("QWidget{background:transparent;border:none;}")
        ri_l = QVBoxLayout(ri)
        ri_l.setContentsMargins(16, 12, 16, 12)
        ri_l.setSpacing(10)

        self._av_status = QLabel("Nhập link hoặc paste nội dung rồi nhấn Generate")
        self._av_status.setWordWrap(True)
        self._av_status.setStyleSheet(
            f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;"
        )
        ri_l.addWidget(self._av_status)

        self._av_log = QTextEdit()
        self._av_log.setReadOnly(True)
        self._av_log.setVisible(False)
        self._av_log.setFixedHeight(120)
        self._av_log.setStyleSheet(
            f"QTextEdit{{background:{CONTROL_BG};border:none;border-radius:8px;"
            f"color:{TEXT_MUTE};font-size:11px;font-family:Menlo,Monaco;padding:10px;}}"
        )
        ri_l.addWidget(self._av_log)

        # Script card
        self._av_script_card = QWidget()
        self._av_script_card.setVisible(False)
        self._av_script_card.setStyleSheet(
            f"QWidget#av_script_card{{background:{CONTROL_BG};border:none;border-radius:10px;}}"
        )
        self._av_script_card.setObjectName("av_script_card")
        sc_vl = QVBoxLayout(self._av_script_card)
        sc_vl.setContentsMargins(0, 0, 0, 0)
        sc_vl.setSpacing(0)

        sc_head_w = QWidget()
        sc_head_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        sc_head_h = QHBoxLayout(sc_head_w)
        sc_head_h.setContentsMargins(12, 8, 12, 8)
        sc_head_h.setSpacing(6)
        sc_ico = QLabel()
        sc_ico.setPixmap(ui_icon("script", 14, TEXT_MUTE).pixmap(icon_size(14)))
        sc_head_h.addWidget(sc_ico)
        sc_lbl = QLabel("Kịch bản")
        sc_lbl.setStyleSheet(
            f"font-size:12px;font-weight:600;color:{TEXT};background:transparent;border:none;"
        )
        sc_head_h.addWidget(sc_lbl)
        sc_head_h.addStretch()
        self._av_script_toggle = QPushButton("Thu gọn")
        self._av_script_toggle.setFixedHeight(24)
        self._av_script_toggle.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;color:{ACCENT};"
            f"font-size:11px;font-weight:600;padding:0 4px;}}"
            f"QPushButton:hover{{color:{ACCENT_HV};}}"
        )
        self._av_script_toggle.clicked.connect(self._av_toggle_script)
        sc_head_h.addWidget(self._av_script_toggle)
        sc_vl.addWidget(sc_head_w)

        sc_div = QWidget()
        sc_div.setFixedHeight(1)
        sc_div.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        sc_vl.addWidget(sc_div)

        self._av_script_view = QTextEdit()
        self._av_script_view.setReadOnly(True)
        self._av_script_view.setFixedHeight(160)
        self._av_script_view.setStyleSheet(
            f"QTextEdit{{background:transparent;border:none;"
            f"color:{TEXT};font-size:12px;padding:10px 12px;}}"
        )
        sc_vl.addWidget(self._av_script_view)
        ri_l.addWidget(self._av_script_card)

        # Progress
        from PyQt6.QtWidgets import QProgressBar
        self._av_step_label = QLabel("")
        self._av_step_label.setVisible(False)
        self._av_step_label.setStyleSheet(
            f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;"
        )
        ri_l.addWidget(self._av_step_label)

        prog_row = QWidget()
        prog_row.setStyleSheet("QWidget{background:transparent;border:none;}")
        prog_h_l = QHBoxLayout(prog_row)
        prog_h_l.setContentsMargins(0, 0, 0, 0)
        prog_h_l.setSpacing(8)
        self._av_progress = QProgressBar()
        self._av_progress.setRange(0, 100)
        self._av_progress.setValue(0)
        self._av_progress.setTextVisible(False)
        self._av_progress.setFixedHeight(8)
        self._av_progress.setStyleSheet(
            f"QProgressBar{{background:{SEG_BG};border:none;border-radius:4px;}}"
            f"QProgressBar::chunk{{background:{ACCENT};border-radius:4px;}}"
        )
        prog_h_l.addWidget(self._av_progress)
        self._av_pct_label = QLabel("0%")
        self._av_pct_label.setFixedWidth(36)
        self._av_pct_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._av_pct_label.setStyleSheet(
            f"font-size:11px;font-weight:700;color:{TEXT_MUTE};background:transparent;border:none;"
        )
        prog_h_l.addWidget(self._av_pct_label)
        prog_row.setVisible(False)
        self._av_prog_row = prog_row
        ri_l.addWidget(prog_row)

        # Result card
        self._av_result_card = QWidget()
        self._av_result_card.setVisible(False)
        self._av_result_card.setObjectName("av_result_card")
        self._av_result_card.setStyleSheet(
            f"QWidget#av_result_card{{background:{CONTROL_BG};border:none;border-radius:10px;}}"
        )
        res_inner_h = QHBoxLayout(self._av_result_card)
        res_inner_h.setContentsMargins(12, 10, 12, 10)
        res_inner_h.setSpacing(8)
        self._av_video_path_lbl = QLabel("—")
        self._av_video_path_lbl.setWordWrap(True)
        self._av_video_path_lbl.setStyleSheet(
            f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;"
        )
        res_inner_h.addWidget(self._av_video_path_lbl, 1)
        self._av_btn_open = QPushButton("📂  Finder")
        self._av_btn_open.setFixedHeight(30)
        self._av_btn_open.setStyleSheet(self._compact_secondary_style())
        self._av_btn_open.clicked.connect(self._av_open_finder)
        res_inner_h.addWidget(self._av_btn_open)
        ri_l.addWidget(self._av_result_card)
        ri_l.addStretch()

        right_vbox.addWidget(ri, 1)
        body_lay.addWidget(right_card, 7)

        self._av_article_body = body_w
        layout.addWidget(body_w, 1)
        self._av_one_shot_body = self._build_one_shot_edit_body()
        layout.addWidget(self._av_one_shot_body, 1)
        self._av_lock_panel = self._build_auto_video_unlock_panel()
        layout.addWidget(self._av_lock_panel)
        self._av_script_worker = None
        self._av_engine_worker = None
        self._os_analyze_worker = None
        self._os_render_worker = None
        self._os_batch_worker = None
        self._os_batch_paths = []
        self._os_plan_path = ""
        self._os_report_path = ""
        self._av_apply_lock_state()
        self._av_switch_mode()
        return page

    def _build_one_shot_edit_body(self) -> QWidget:
        body_w = QWidget()
        body_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        body_lay = QHBoxLayout(body_w)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(14)

        left_card, left_vbox = self._card()
        hdr = QWidget()
        hdr.setStyleSheet("QWidget{background:transparent;border:none;}")
        hdr_h = QHBoxLayout(hdr)
        hdr_h.setContentsMargins(16, 11, 16, 11)
        hdr_h.setSpacing(8)
        ico = QLabel()
        ico.setPixmap(ui_icon("video", 15, TEXT_MUTE).pixmap(icon_size(15)))
        hdr_h.addWidget(ico)
        title = QLabel("Nguồn")
        title.setStyleSheet(f"font-size:13px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        hdr_h.addWidget(title)
        hdr_h.addStretch()
        left_vbox.addWidget(hdr)

        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        left_vbox.addWidget(div)

        inner = QWidget()
        inner.setStyleSheet("QWidget{background:transparent;border:none;}")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(16, 16, 16, 16)
        iv.setSpacing(12)

        def section_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size:11px;font-weight:700;color:{TEXT_MUTE};"
                "background:transparent;border:none;padding:4px 0 0 0;"
            )
            return lbl

        def make_group() -> QVBoxLayout:
            group = QFrame()
            group.setObjectName("oneShotGroup")
            group.setStyleSheet(
                f"QFrame#oneShotGroup{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};"
                "border-radius:12px;}"
            )
            gv = QVBoxLayout(group)
            gv.setContentsMargins(0, 0, 0, 0)
            gv.setSpacing(0)
            iv.addWidget(group)
            return gv

        def add_group_row(group_vbox: QVBoxLayout, label: str, widget: QWidget, note: str = "", last: bool = False):
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;border:none;")
            row_w.setMinimumHeight(50 if not note else 58)
            h = QHBoxLayout(row_w)
            h.setContentsMargins(12, 8, 12, 8)
            h.setSpacing(12)
            lbl = QLabel(label)
            lbl.setFixedWidth(74)
            lbl.setStyleSheet(f"font-size:12px;font-weight:600;color:{TEXT};background:transparent;border:none;")
            h.addWidget(lbl)
            right = QVBoxLayout()
            right.setContentsMargins(0, 0, 0, 0)
            right.setSpacing(3)
            right.addWidget(widget)
            if note:
                n = QLabel(note)
                n.setWordWrap(True)
                n.setStyleSheet(f"font-size:10px;color:{TEXT_FAINT};background:transparent;border:none;line-height:13px;")
                right.addWidget(n)
            h.addLayout(right, 1)
            group_vbox.addWidget(row_w)
            if not last:
                sep = QWidget()
                sep.setFixedHeight(1)
                sep.setStyleSheet(f"background:{BORDER_SOFT};border:none;margin-left:86px;")
                group_vbox.addWidget(sep)

        iv.addWidget(section_label("CHỌN NGUỒN"))
        source_group = make_group()
        video_control = QWidget()
        video_h = QHBoxLayout(video_control)
        video_h.setContentsMargins(0, 0, 0, 0)
        video_h.setSpacing(8)
        self._os_video_lbl = QLabel("Chưa chọn")
        self._os_video_lbl.setWordWrap(True)
        self._os_video_lbl.setMinimumHeight(32)
        self._os_video_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;line-height:15px;")
        video_h.addWidget(self._os_video_lbl, 1)
        self._os_pick_video_btn = QPushButton("Chọn video")
        self._os_pick_video_btn.setFixedHeight(32)
        self._os_pick_video_btn.setStyleSheet(self._compact_secondary_style())
        self._os_pick_video_btn.clicked.connect(self._os_choose_video)
        video_h.addWidget(self._os_pick_video_btn)
        add_group_row(source_group, "Một video", video_control, "", last=False)

        batch_control = QWidget()
        batch_h = QHBoxLayout(batch_control)
        batch_h.setContentsMargins(0, 0, 0, 0)
        batch_h.setSpacing(8)
        self._os_batch_lbl = QLabel("Chưa chọn")
        self._os_batch_lbl.setWordWrap(True)
        self._os_batch_lbl.setMinimumHeight(34)
        self._os_batch_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;line-height:15px;")
        batch_h.addWidget(self._os_batch_lbl, 1)
        self._os_batch_files_btn = QPushButton("Chọn nhiều")
        self._os_batch_files_btn.setFixedHeight(32)
        self._os_batch_files_btn.setStyleSheet(self._compact_secondary_style())
        self._os_batch_files_btn.clicked.connect(self._os_choose_batch_videos)
        batch_h.addWidget(self._os_batch_files_btn)
        self._os_batch_folder_btn = QPushButton("Chọn thư mục")
        self._os_batch_folder_btn.setFixedHeight(32)
        self._os_batch_folder_btn.setStyleSheet(self._compact_secondary_style())
        self._os_batch_folder_btn.clicked.connect(self._os_choose_batch_folder)
        batch_h.addWidget(self._os_batch_folder_btn)
        add_group_row(source_group, "Nhiều video", batch_control, "", last=True)

        action_row = QWidget()
        action_row.setStyleSheet("QWidget{background:transparent;border:none;}")
        action_lay = QHBoxLayout(action_row)
        action_lay.setContentsMargins(0, 0, 0, 0)
        action_lay.setSpacing(8)
        self._os_analyze_btn = QPushButton("Phân tích")
        self._os_analyze_btn.setFixedHeight(34)
        self._os_analyze_btn.setMinimumWidth(132)
        self._os_analyze_btn.setStyleSheet(self._compact_primary_style())
        self._os_analyze_btn.setEnabled(False)
        self._os_analyze_btn.clicked.connect(self._os_analyze_video)
        action_lay.addWidget(self._os_analyze_btn)
        self._os_simple_run_btn = QPushButton("Chạy 1 lần")
        self._os_simple_run_btn.setFixedHeight(34)
        self._os_simple_run_btn.setMinimumWidth(132)
        self._os_simple_run_btn.setStyleSheet(self._compact_primary_style())
        self._os_simple_run_btn.setEnabled(False)
        self._os_simple_run_btn.clicked.connect(self._os_run_simple)
        action_lay.addWidget(self._os_simple_run_btn)
        self._os_batch_btn = QPushButton("Chạy tất cả")
        self._os_batch_btn.setFixedHeight(34)
        self._os_batch_btn.setMinimumWidth(132)
        self._os_batch_btn.setStyleSheet(self._compact_secondary_style())
        self._os_batch_btn.setEnabled(False)
        self._os_batch_btn.clicked.connect(self._os_run_batch)
        action_lay.addWidget(self._os_batch_btn)
        iv.addWidget(action_row)
        iv.addStretch()
        left_vbox.addWidget(inner, 1)
        body_lay.addWidget(left_card, 5)

        right_card, right_vbox = self._card()
        rh = QWidget()
        rh.setStyleSheet("QWidget{background:transparent;border:none;}")
        rh_l = QHBoxLayout(rh)
        rh_l.setContentsMargins(16, 11, 16, 11)
        rh_l.setSpacing(8)
        r_ico = QLabel()
        r_ico.setPixmap(ui_icon("script", 15, TEXT_MUTE).pixmap(icon_size(15)))
        rh_l.addWidget(r_ico)
        r_title = QLabel("Tiến trình")
        r_title.setStyleSheet(f"font-size:13px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        rh_l.addWidget(r_title)
        rh_l.addStretch()
        right_vbox.addWidget(rh)

        rdiv = QWidget()
        rdiv.setFixedHeight(1)
        rdiv.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        right_vbox.addWidget(rdiv)

        ri = QWidget()
        ri.setStyleSheet("QWidget{background:transparent;border:none;}")
        rv = QVBoxLayout(ri)
        rv.setContentsMargins(16, 12, 16, 12)
        rv.setSpacing(10)
        self._os_empty_state = QFrame()
        self._os_empty_state.setObjectName("oneShotEmptyState")
        self._os_empty_state.setStyleSheet(
            f"QFrame#oneShotEmptyState{{background:{SURFACE};border:none;border-radius:10px;}}"
        )
        empty_lay = QVBoxLayout(self._os_empty_state)
        empty_lay.setContentsMargins(16, 26, 16, 26)
        empty_lay.setSpacing(8)
        empty_lay.addStretch()
        empty_icon = QLabel()
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setPixmap(ui_icon("video", 34, TEXT_FAINT).pixmap(icon_size(34)))
        empty_lay.addWidget(empty_icon)
        empty_title = QLabel("Sẵn sàng xử lý one-shot")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(f"font-size:16px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        empty_lay.addWidget(empty_title)
        empty_sub = QLabel("Chọn một video để review thủ công hoặc chọn cả thư mục để chạy tự động.")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_sub.setWordWrap(True)
        empty_sub.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        empty_lay.addWidget(empty_sub)
        empty_badges = QWidget()
        empty_badges.setStyleSheet("QWidget{background:transparent;border:none;}")
        empty_badges_lay = QHBoxLayout(empty_badges)
        empty_badges_lay.setContentsMargins(0, 4, 0, 0)
        empty_badges_lay.setSpacing(8)
        empty_badges_lay.addStretch()
        for badge in ("Thumbnail trong frame đầu", "Xuất theo ngày"):
            b = QLabel(badge)
            b.setStyleSheet(
                f"font-size:11px;color:{TEXT_MUTE};background:{CONTROL_BG};"
                f"border:1px solid {BORDER_SOFT};border-radius:10px;padding:4px 9px;"
            )
            empty_badges_lay.addWidget(b)
        empty_badges_lay.addStretch()
        empty_lay.addWidget(empty_badges)
        empty_lay.addStretch()
        rv.addWidget(self._os_empty_state, 1)

        self._os_status_row = QWidget()
        self._os_status_row.setVisible(False)
        self._os_status_row.setStyleSheet("QWidget{background:transparent;border:none;}")
        status_lay = QHBoxLayout(self._os_status_row)
        status_lay.setContentsMargins(0, 0, 0, 0)
        status_lay.setSpacing(8)
        self._os_status = QLabel("Sẵn sàng.")
        self._os_status.setWordWrap(True)
        self._os_status.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        status_lay.addWidget(self._os_status, 1)
        self._os_details_btn = QPushButton("Chi tiết")
        self._os_details_btn.setFixedHeight(28)
        self._os_details_btn.setMinimumWidth(72)
        self._os_details_btn.setStyleSheet(self._compact_secondary_style())
        self._os_details_btn.clicked.connect(self._os_toggle_details)
        status_lay.addWidget(self._os_details_btn)
        rv.addWidget(self._os_status_row)

        self._os_batch_summary = QLabel("")
        self._os_batch_summary.setVisible(False)
        self._os_batch_summary.setWordWrap(True)
        self._os_batch_summary.setStyleSheet(
            f"font-size:12px;font-weight:600;color:{TEXT};background:{CONTROL_BG};"
            f"border:1px solid {BORDER_SOFT};border-radius:10px;padding:9px 11px;"
        )
        rv.addWidget(self._os_batch_summary)

        self._os_log = QTextEdit()
        self._os_log.setReadOnly(True)
        self._os_log.setFixedHeight(96)
        self._os_log.setVisible(False)
        self._os_log.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._os_log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._os_log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._os_log.setStyleSheet(
            f"QTextEdit{{background:{CONTROL_BG};border:none;border-radius:8px;"
            f"color:{TEXT_MUTE};font-size:11px;font-family:Menlo,Monaco;padding:10px;}}"
            "QTextEdit QScrollBar:horizontal{height:0px;background:transparent;}"
        )
        rv.addWidget(self._os_log)
        self._os_debug_folder_btn = QPushButton("Mở thư mục debug")
        self._os_debug_folder_btn.setFixedHeight(28)
        self._os_debug_folder_btn.setVisible(False)
        self._os_debug_folder_btn.setStyleSheet(self._compact_secondary_style())
        self._os_debug_folder_btn.clicked.connect(self._os_open_result_folder)
        rv.addWidget(self._os_debug_folder_btn, 0, Qt.AlignmentFlag.AlignRight)
        self._os_details_visible = False

        self._os_cut_list = QListWidget()
        self._os_cut_list.setVisible(False)
        self._os_cut_list.setWordWrap(True)
        self._os_cut_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._os_cut_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._os_cut_list.setStyleSheet(
            f"QListWidget{{background:{CONTROL_BG};border:none;border-radius:8px;"
            f"color:{TEXT};font-size:12px;padding:6px;}}"
            f"QListWidget::item{{padding:6px;border-radius:6px;}}"
            f"QListWidget::item:selected{{background:{CONTROL_HV};color:{TEXT};}}"
            "QListWidget QScrollBar:horizontal{height:0px;background:transparent;}"
        )
        rv.addWidget(self._os_cut_list, 1)

        self._os_thumb_panel = QFrame()
        self._os_thumb_panel.setObjectName("oneShotReviewGroup")
        self._os_thumb_panel.setVisible(False)
        self._os_thumb_panel.setStyleSheet(
            f"QFrame#oneShotReviewGroup{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};"
            "border-radius:12px;}"
        )
        thumb_panel_lay = QVBoxLayout(self._os_thumb_panel)
        thumb_panel_lay.setContentsMargins(0, 0, 0, 0)
        thumb_panel_lay.setSpacing(0)
        thumb_row = QWidget()
        thumb_row.setStyleSheet("background:transparent;border:none;")
        thumb_row_lay = QHBoxLayout(thumb_row)
        thumb_row_lay.setContentsMargins(12, 9, 12, 8)
        thumb_row_lay.setSpacing(12)
        thumb_lbl = QLabel("Tiêu đề")
        thumb_lbl.setFixedWidth(84)
        thumb_lbl.setStyleSheet(f"font-size:12px;font-weight:600;color:{TEXT};background:transparent;border:none;")
        thumb_row_lay.addWidget(thumb_lbl)
        self._os_thumb_title = QLineEdit()
        self._os_thumb_title.setPlaceholderText("Ví dụ: BOX SAMSUNG DEX S20 CÓ GIÁ 1900K")
        self._os_thumb_title.setFixedHeight(34)
        self._os_thumb_title.setStyleSheet(
            f"QLineEdit{{background:{SURFACE};border:1px solid {BORDER_SOFT};"
            f"border-radius:8px;color:{TEXT};font-size:13px;padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{ACCENT};}}"
        )
        thumb_row_lay.addWidget(self._os_thumb_title, 1)
        self._os_thumb_quality_badge = QLabel("Chưa kiểm tra")
        self._os_thumb_quality_badge.setFixedHeight(26)
        self._os_thumb_quality_badge.setMinimumWidth(112)
        self._os_thumb_quality_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._os_set_thumb_quality_badge("unchecked")
        thumb_row_lay.addWidget(self._os_thumb_quality_badge)
        thumb_panel_lay.addWidget(thumb_row)
        thumb_style = QWidget()
        thumb_style.setStyleSheet("background:transparent;border:none;")
        thumb_style_lay = QHBoxLayout(thumb_style)
        thumb_style_lay.setContentsMargins(108, 0, 12, 8)
        thumb_style_lay.setSpacing(8)

        def add_thumb_style_control(label: str, combo: QComboBox):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;")
            thumb_style_lay.addWidget(lbl)
            thumb_style_lay.addWidget(combo)

        self._os_thumb_size = self._av_quick_choice(
            [("Tự động", "auto"), ("Lớn", "large"), ("Rất lớn", "xlarge")],
            str(self.settings.get("one_shot_thumbnail_size", "large") or "large"),
        )
        self._os_thumb_lines = self._av_quick_choice(
            [("Tự động", "auto"), ("2 dòng", "2"), ("3 dòng", "3")],
            str(self.settings.get("one_shot_thumbnail_lines", "auto") or "auto"),
        )
        self._os_thumb_position = self._av_quick_choice(
            [("Cân giữa", "center"), ("Thấp hơn", "lower"), ("Cao hơn", "higher")],
            str(self.settings.get("one_shot_thumbnail_position", "center") or "center"),
        )
        for combo in (self._os_thumb_size, self._os_thumb_lines, self._os_thumb_position):
            combo.currentIndexChanged.connect(self._os_save_toolbar_settings)
        add_thumb_style_control("Chữ", self._os_thumb_size)
        add_thumb_style_control("Dòng", self._os_thumb_lines)
        add_thumb_style_control("Vị trí", self._os_thumb_position)
        thumb_style_lay.addStretch()
        thumb_panel_lay.addWidget(thumb_style)

        thumb_actions = QWidget()
        thumb_actions.setStyleSheet("background:transparent;border:none;")
        thumb_actions_lay = QHBoxLayout(thumb_actions)
        thumb_actions_lay.setContentsMargins(108, 0, 12, 10)
        thumb_actions_lay.setSpacing(8)
        self._os_thumb_title_status = QLabel("")
        self._os_thumb_title_status.setWordWrap(True)
        self._os_thumb_title_status.setStyleSheet(f"font-size:11px;color:{TEXT_FAINT};background:transparent;border:none;")
        thumb_actions_lay.addWidget(self._os_thumb_title_status, 1)
        self._os_thumb_regen_btn = QPushButton("Tạo lại tiêu đề")
        self._os_thumb_title_mode = str(self.settings.get("one_shot_thumbnail_title_mode", "expert") or "expert")
        self._os_thumb_regen_btn.setFixedHeight(32)
        self._os_thumb_regen_btn.setMinimumWidth(118)
        self._os_thumb_regen_btn.setStyleSheet(self._compact_secondary_style())
        self._os_thumb_regen_btn.clicked.connect(self._os_regenerate_thumbnail_title)
        regen_menu = QMenu(self._os_thumb_regen_btn)
        regen_menu.setStyleSheet(f"QMenu{{background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;padding:4px;}}")
        for label, mode in (
            ("Chuẩn chuyên ngành", "expert"),
            ("Viral hơn", "viral"),
            ("Ngắn gọn hơn", "short"),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, m=mode: self._os_regenerate_thumbnail_title(m))
            regen_menu.addAction(action)
        self._os_thumb_regen_btn.setMenu(regen_menu)
        thumb_actions_lay.addWidget(self._os_thumb_regen_btn)
        self._os_thumb_preview_btn = QPushButton("Preview")
        self._os_thumb_preview_btn.setFixedHeight(32)
        self._os_thumb_preview_btn.setMinimumWidth(82)
        self._os_thumb_preview_btn.setStyleSheet(self._compact_secondary_style())
        self._os_thumb_preview_btn.clicked.connect(self._os_preview_thumbnail)
        thumb_actions_lay.addWidget(self._os_thumb_preview_btn)
        thumb_panel_lay.addWidget(thumb_actions)
        preview_row = QWidget()
        preview_row.setStyleSheet("background:transparent;border:none;")
        preview_row_lay = QHBoxLayout(preview_row)
        preview_row_lay.setContentsMargins(108, 0, 12, 10)
        preview_row_lay.setSpacing(10)
        self._os_thumb_preview_img = QLabel()
        self._os_thumb_preview_img.setFixedSize(90, 160)
        self._os_thumb_preview_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._os_thumb_preview_img.setStyleSheet(
            f"background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;"
            f"color:{TEXT_FAINT};font-size:11px;"
        )
        self._os_thumb_preview_img.setText("Preview")
        preview_row_lay.addWidget(self._os_thumb_preview_img)
        preview_meta = QVBoxLayout()
        preview_meta.setContentsMargins(0, 0, 0, 0)
        preview_meta.setSpacing(5)
        self._os_preview_filename = QLabel("")
        self._os_preview_filename.setWordWrap(True)
        self._os_preview_filename.setStyleSheet(f"font-size:11px;font-weight:600;color:{TEXT};background:transparent;border:none;")
        preview_meta.addWidget(self._os_preview_filename)
        self._os_preview_hashtags = QLabel("")
        self._os_preview_hashtags.setWordWrap(True)
        self._os_preview_hashtags.setStyleSheet(f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;")
        preview_meta.addWidget(self._os_preview_hashtags)
        self._os_preview_status = QLabel("")
        self._os_preview_status.setWordWrap(True)
        self._os_preview_status.setStyleSheet(f"font-size:11px;color:{TEXT_FAINT};background:transparent;border:none;")
        preview_meta.addWidget(self._os_preview_status)
        preview_meta.addStretch()
        preview_row_lay.addLayout(preview_meta, 1)
        thumb_panel_lay.addWidget(preview_row)
        self._os_preview_timer = QTimer(self)
        self._os_preview_timer.setSingleShot(True)
        self._os_preview_timer.setInterval(650)
        self._os_preview_timer.timeout.connect(self._os_preview_thumbnail)
        self._os_thumb_title.textEdited.connect(self._os_schedule_preview_update)
        self._os_thumb_panel.setToolTip("Thumbnail luôn nằm trong vùng an toàn TikTok; font chọn tại thanh tuỳ chọn phía trên.")
        rv.addWidget(self._os_thumb_panel)

        self._os_render_row = QWidget()
        self._os_render_row.setVisible(False)
        self._os_render_row.setStyleSheet("QWidget{background:transparent;border:none;}")
        render_lay = QHBoxLayout(self._os_render_row)
        render_lay.setContentsMargins(0, 0, 0, 0)
        render_lay.setSpacing(0)
        self._os_render_btn = QPushButton("Render")
        self._os_render_btn.setFixedHeight(34)
        self._os_render_btn.setMinimumWidth(132)
        self._os_render_btn.setEnabled(False)
        self._os_render_btn.setStyleSheet(self._compact_primary_style())
        self._os_render_btn.clicked.connect(self._os_render_video)
        render_lay.addStretch()
        render_lay.addWidget(self._os_render_btn)
        rv.addWidget(self._os_render_row)

        self._os_result = QLabel("")
        self._os_result.setWordWrap(True)
        self._os_result.setStyleSheet(f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;")
        rv.addWidget(self._os_result)
        self._os_result_actions = QWidget()
        self._os_result_actions.setVisible(False)
        self._os_result_actions.setStyleSheet("QWidget{background:transparent;border:none;}")
        result_actions_lay = QHBoxLayout(self._os_result_actions)
        result_actions_lay.setContentsMargins(0, 0, 0, 0)
        result_actions_lay.setSpacing(8)
        self._os_open_day_btn = QPushButton("Mở thư mục xuất")
        self._os_open_day_btn.setFixedHeight(32)
        self._os_open_day_btn.setMinimumWidth(132)
        self._os_open_day_btn.setStyleSheet(self._compact_primary_style())
        self._os_open_day_btn.clicked.connect(self._os_open_day_folder)
        result_actions_lay.addStretch()
        result_actions_lay.addWidget(self._os_open_day_btn)
        self._os_copy_results_btn = QPushButton("Copy")
        self._os_copy_results_btn.setFixedHeight(30)
        self._os_copy_results_btn.setMinimumWidth(72)
        self._os_copy_results_btn.setStyleSheet(self._compact_secondary_style())
        self._os_copy_results_btn.clicked.connect(self._os_copy_result_paths)
        result_actions_lay.addWidget(self._os_copy_results_btn)
        self._os_copy_caption_btn = QPushButton("Copy caption")
        self._os_copy_caption_btn.setFixedHeight(30)
        self._os_copy_caption_btn.setMinimumWidth(108)
        self._os_copy_caption_btn.setStyleSheet(self._compact_secondary_style())
        self._os_copy_caption_btn.clicked.connect(self._os_copy_platform_caption)
        result_actions_lay.addWidget(self._os_copy_caption_btn)
        rv.addWidget(self._os_result_actions)
        right_vbox.addWidget(ri, 1)
        body_lay.addWidget(right_card, 7)
        body_w.setVisible(False)
        return body_w

    def _av_switch_mode(self):
        mode = "article"
        if hasattr(self, "_av_mode"):
            mode = self._av_mode.currentData() or "article"
            self.settings["auto_video_mode"] = mode
            try:
                save_settings(self.settings)
            except Exception:
                pass
        if hasattr(self, "_av_article_body"):
            self._av_article_body.setVisible(mode == "article")
        if hasattr(self, "_av_one_shot_body"):
            self._av_one_shot_body.setVisible(mode == "oneshot")
        if hasattr(self, "_av_gen_btn"):
            self._av_gen_btn.setVisible(mode == "article")
        for widget in getattr(self, "_av_article_toolbar_widgets", []):
            try:
                widget.setVisible(mode == "article")
            except RuntimeError:
                pass
        for widget in getattr(self, "_av_one_shot_toolbar_widgets", []):
            try:
                widget.setVisible(mode == "oneshot")
            except RuntimeError:
                pass
        if hasattr(self, "_av_config_lbl") and mode == "oneshot":
            if is_simple_pipeline(self.settings):
                self._os_set_status("Edit one-shot (Simple): chọn video → Chạy 1 lần hoặc Chạy tất cả.")
            else:
                self._os_set_status("Edit one-shot: chọn video để giảm noise, áp LUT, review cut và tạo thumbnail.")
        if mode == "oneshot":
            self._os_update_pipeline_controls()
            self._os_sync_source_actions()
    def _os_lut_display_text(self) -> str:
        path = self.settings.get("one_shot_lut_path") or ""
        if not path:
            default = Path.home() / "Downloads" / "DJI OSMO Osmo Nano D-Log M to Rec.709 V1.cube"
            if default.exists():
                path = str(default)
        return f"LUT: {Path(path).name}" if path else "Chưa chọn LUT .cube"

    def _os_lut_toolbar_text(self) -> str:
        text = self._os_lut_display_text().replace("LUT: ", "").strip()
        if not text or text == "Chưa chọn LUT .cube":
            return "Chọn LUT"
        preferred = "DJI Rec.709" if "DJI" in text and "Rec.709" in text else text
        return preferred if len(preferred) <= 24 else preferred[:21].rstrip() + "…"

    def _os_show_workspace(self, active: bool = True):
        if hasattr(self, "_os_empty_state"):
            self._os_empty_state.setVisible(not active)
        if hasattr(self, "_os_status_row"):
            self._os_status_row.setVisible(active)

    def _os_reset_batch_summary(self):
        self._os_batch_ok = 0
        self._os_batch_failed = 0
        self._os_batch_processed = 0
        if hasattr(self, "_os_batch_summary"):
            self._os_batch_summary.clear()
            self._os_batch_summary.setVisible(False)

    def _os_on_pipeline_mode_changed(self):
        self._os_save_toolbar_settings()
        self._os_update_pipeline_controls()
        self._os_sync_source_actions()

    def _os_sync_source_actions(self, force: bool = False):
        analyze_running = self._is_thread_running(getattr(self, "_os_analyze_worker", None)) and not force
        render_running = self._is_thread_running(getattr(self, "_os_render_worker", None)) and not force
        simple_running = self._is_thread_running(getattr(self, "_os_simple_worker", None)) and not force
        batch_running = self._is_thread_running(getattr(self, "_os_batch_worker", None)) and not force
        if hasattr(self, "_os_analyze_btn") and not batch_running and not analyze_running and not simple_running:
            self._os_analyze_btn.setText("Phân tích")
            self._os_analyze_btn.setEnabled(bool(getattr(self, "_os_video_path", "")))
        if hasattr(self, "_os_simple_run_btn") and not batch_running:
            running = self._is_thread_running(getattr(self, "_os_simple_worker", None)) and not force
            self._os_simple_run_btn.setText("Dừng" if running else "Chạy 1 lần")
            self._os_simple_run_btn.setEnabled(bool(getattr(self, "_os_video_path", "")) or running)
        if hasattr(self, "_os_render_btn") and not render_running:
            self._os_render_btn.setText("Render")
            self._os_render_btn.setEnabled(bool(getattr(self, "_os_plan_path", "")) and not batch_running and not analyze_running and not simple_running)
        if hasattr(self, "_os_batch_btn") and not batch_running:
            self._os_batch_btn.setText("Chạy tất cả")
            self._os_batch_btn.setEnabled(bool(getattr(self, "_os_batch_paths", []) or []))
        self._os_update_pipeline_controls()

    def _os_cancel_worker(self, attr_name: str, button, label: str) -> bool:
        worker = getattr(self, attr_name, None)
        if not self._is_thread_running(worker):
            return False
        try:
            if hasattr(worker, "cancel"):
                worker.cancel()
        except Exception:
            pass
        try:
            worker.requestInterruption()
        except Exception:
            pass
        if button is not None:
            button.setText("Đang dừng…")
            button.setEnabled(False)
        self._os_set_status(f"Đang dừng {label}…")
        return True

    def _os_set_source_controls_enabled(self, enabled: bool):
        for name in ("_os_pick_video_btn", "_os_batch_files_btn", "_os_batch_folder_btn"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(enabled)

    def _os_update_batch_summary(self, total: int, running: bool = True):
        if not hasattr(self, "_os_batch_summary"):
            return
        state = "Đang xử lý" if running else "Hoàn tất"
        self._os_batch_summary.setText(
            f"{state} {self._os_batch_processed}/{total}  ·  "
            f"OK {self._os_batch_ok}  ·  Lỗi {self._os_batch_failed}"
        )
        self._os_batch_summary.setVisible(True)

    def _os_choose_video(self):
        start_dir = str(self.settings.get("one_shot_last_video_dir") or self.settings.get("one_shot_last_batch_dir") or (Path.home() / "Movies"))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn video one-shot",
            start_dir,
            "Video files (*.mp4 *.mov *.m4v *.avi *.mkv);;All files (*)",
        )
        if not path:
            return
        self._os_video_path = path
        self._os_video_lbl.setText(Path(path).name)
        self._os_video_lbl.setToolTip(path)
        self.settings["one_shot_last_video_dir"] = str(Path(path).parent)
        self.settings["one_shot_last_batch_dir"] = str(Path(path).parent)
        save_settings(self.settings)
        self._os_show_workspace(True)
        self._os_sync_source_actions()
        self._os_set_status("Đã chọn video. Nhấn Phân tích để tạo bản xem trước.")

    def _os_video_extensions(self) -> set[str]:
        return {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

    def _os_set_batch_paths(self, paths: list[str]):
        valid = []
        seen = set()
        for raw in paths or []:
            p = Path(raw).expanduser()
            key = str(p)
            if key in seen or p.suffix.lower() not in self._os_video_extensions():
                continue
            seen.add(key)
            valid.append(key)
        valid.sort(key=lambda x: Path(x).name.lower())
        self._os_batch_paths = valid
        if hasattr(self, "_os_batch_lbl"):
            if not valid:
                self._os_batch_lbl.setText("Chưa chọn")
                self._os_batch_lbl.setToolTip("")
            elif len(valid) == 1:
                self._os_batch_lbl.setText(Path(valid[0]).name)
                self._os_batch_lbl.setToolTip(valid[0])
            else:
                first = Path(valid[0]).name
                self._os_batch_lbl.setText(f"{len(valid)} video\n{first}")
                self._os_batch_lbl.setToolTip("\n".join(valid))
        if valid:
            self._os_show_workspace(True)
            self._os_sync_source_actions()
            self._os_set_status(f"Đã chọn {len(valid)} video. Nhấn Chạy tất cả để xuất MP4.")
        else:
            self._os_sync_source_actions()

    def _os_choose_batch_videos(self):
        start_dir = str(self.settings.get("one_shot_last_batch_dir") or self.settings.get("one_shot_last_video_dir") or (Path.home() / "Movies"))
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn nhiều video one-shot",
            start_dir,
            "Video files (*.mp4 *.mov *.m4v *.avi *.mkv);;All files (*)",
        )
        if paths:
            self.settings["one_shot_last_batch_dir"] = str(Path(paths[0]).parent)
            self.settings["one_shot_last_video_dir"] = str(Path(paths[0]).parent)
            save_settings(self.settings)
            self._os_set_batch_paths(paths)

    def _os_choose_batch_folder(self):
        start_dir = str(self.settings.get("one_shot_last_batch_dir") or self.settings.get("one_shot_last_video_dir") or (Path.home() / "Movies"))
        folder = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục kho video",
            start_dir,
        )
        if not folder:
            return
        self.settings["one_shot_last_batch_dir"] = folder
        self.settings["one_shot_last_video_dir"] = folder
        save_settings(self.settings)
        root = Path(folder)
        paths = [
            str(p)
            for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in self._os_video_extensions() and not p.name.startswith(".")
        ]
        self._os_set_batch_paths(paths)

    def _os_choose_lut(self):
        current = str(self.settings.get("one_shot_lut_path") or "")
        saved_dir = str(self.settings.get("one_shot_last_lut_dir") or "")
        start = str(Path(current).expanduser().parent if current else (saved_dir or Path.home() / "Downloads"))
        path, _ = QFileDialog.getOpenFileName(self, "Chọn LUT .cube", start, "LUT files (*.cube);;All files (*)")
        if not path:
            return
        self.settings["one_shot_lut_path"] = path
        self.settings["one_shot_last_lut_dir"] = str(Path(path).parent)
        save_settings(self.settings)
        if hasattr(self, "_os_lut_btn"):
            self._os_lut_btn.setText(self._os_lut_toolbar_text())
            self._os_lut_btn.setToolTip(self._os_lut_display_text())

    def _os_set_thumb_quality_badge(self, status: str, text: str | None = None):
        badge = getattr(self, "_os_thumb_quality_badge", None)
        if badge is None:
            return
        status = status or "unchecked"
        labels = {
            "expert_checked": "Đã kiểm tra",
            "needs_review": "Cần xem lại",
            "fallback": "Fallback",
            "unchecked": "Chưa kiểm tra",
        }
        colors = {
            "expert_checked": (SUCCESS, "#ecfff1"),
            "needs_review": (WARNING, "#fff7e8"),
            "fallback": (TEXT_MUTE, CONTROL_BG),
            "unchecked": (TEXT_MUTE, CONTROL_BG),
        }
        fg, bg = colors.get(status, colors["unchecked"])
        badge.setText(text or labels.get(status, labels["unchecked"]))
        badge.setStyleSheet(
            f"font-size:11px;font-weight:700;color:{fg};background:{bg};"
            f"border:1px solid {BORDER_SOFT};border-radius:13px;padding:0 8px;"
        )

    def _os_save_toolbar_settings(self):
        if hasattr(self, "_os_noise_toggle"):
            noise_mode = self._os_noise_toggle.currentData() or "auto_gentle"
            self.settings["one_shot_noise_mode"] = noise_mode
            self.settings["one_shot_noise_reduce"] = noise_mode != "off"
        if hasattr(self, "_os_cut_toggle"):
            self.settings["one_shot_cut_video"] = (self._os_cut_toggle.currentData() or "on") == "on"
        if hasattr(self, "_os_lut_toggle"):
            self.settings["one_shot_apply_lut"] = (self._os_lut_toggle.currentData() or "on") == "on"
        if hasattr(self, "_os_render_profile"):
            self.settings["one_shot_render_profile"] = self._os_render_profile.currentData() or "multi_1080"
        if hasattr(self, "_os_industry_combo"):
            self.settings["one_shot_industry"] = self._os_industry_combo.currentData() or "tech"
        if hasattr(self, "_os_pipeline_combo"):
            mode = self._os_pipeline_combo.currentData() or "simple"
            self.settings["one_shot_pipeline_mode"] = mode
            simple = mode == "simple"
            self.settings["one_shot_enterprise_pipeline"] = not simple
            self.settings["one_shot_ai_review_thumbnail"] = not simple
        if hasattr(self, "_os_font_combo"):
            self.settings["one_shot_thumbnail_font"] = self._os_font_combo.currentData() or "dt_phudu_black"
        if hasattr(self, "_os_thumb_size"):
            self.settings["one_shot_thumbnail_size"] = self._os_thumb_size.currentData() or "large"
        if hasattr(self, "_os_thumb_lines"):
            self.settings["one_shot_thumbnail_lines"] = self._os_thumb_lines.currentData() or "auto"
        if hasattr(self, "_os_thumb_position"):
            self.settings["one_shot_thumbnail_position"] = self._os_thumb_position.currentData() or "center"
        if hasattr(self, "_os_thumb_title_mode"):
            self.settings["one_shot_thumbnail_title_mode"] = self._os_thumb_title_mode
        if hasattr(self, "_os_review_toggle"):
            self.settings["one_shot_ai_review_thumbnail"] = (self._os_review_toggle.currentData() or "on") == "on"
        try:
            save_settings(self.settings)
        except Exception:
            pass

    def _os_options(self) -> dict:
        self._os_save_toolbar_settings()
        save_settings(self.settings)
        simple = is_simple_pipeline(self.settings)
        if simple:
            return build_simple_options(self.settings, {
                "batch_concurrency": 1,
                "batch_clean_export": True,
            })
        return {
            "noise_reduce": self.settings["one_shot_noise_reduce"],
            "noise_mode": self.settings.get("one_shot_noise_mode", "auto_gentle"),
            "cut_video": self.settings["one_shot_cut_video"],
            "apply_lut": self.settings["one_shot_apply_lut"],
            "lut_path": self.settings.get("one_shot_lut_path", ""),
            "render_profile": self.settings.get("one_shot_render_profile", "multi_1080"),
            "industry": self.settings.get("one_shot_industry", "tech"),
            "thumbnail_font": self.settings.get("one_shot_thumbnail_font", "dt_phudu_black"),
            "thumbnail_size": self.settings.get("one_shot_thumbnail_size", "large"),
            "thumbnail_lines": self.settings.get("one_shot_thumbnail_lines", "auto"),
            "thumbnail_position": self.settings.get("one_shot_thumbnail_position", "center"),
            "thumbnail_title_mode": self.settings.get("one_shot_thumbnail_title_mode", "expert"),
            "enterprise_pipeline": bool(self.settings.get("one_shot_enterprise_pipeline", True)),
            "ai_review_thumbnail": bool(self.settings.get("one_shot_ai_review_thumbnail", True)),
            "prepend_thumbnail_cover": True,
            "batch_concurrency": "auto",
            "batch_review_before_render": True,
            "batch_clean_export": True,
            "batch_deepseek_repair_title": True,
            "settings": self.settings,
        }

    def _os_update_pipeline_controls(self) -> None:
        simple = is_simple_pipeline(self.settings)
        if hasattr(self, "_os_simple_run_btn"):
            self._os_simple_run_btn.setVisible(simple)
            self._os_simple_run_btn.setEnabled(bool(getattr(self, "_os_video_path", "")) and not self._is_thread_running(getattr(self, "_os_simple_worker", None)))
        if hasattr(self, "_os_analyze_btn"):
            self._os_analyze_btn.setVisible(not simple)
        if hasattr(self, "_os_render_row"):
            self._os_render_row.setVisible(not simple and bool(getattr(self, "_os_plan_path", "")))
        if hasattr(self, "_os_batch_btn"):
            self._os_batch_btn.setText("Chạy tất cả" if simple else "Chạy tất cả")

    def _os_analyze_video(self):
        if self._os_cancel_worker("_os_analyze_worker", getattr(self, "_os_analyze_btn", None), "phân tích"):
            return
        if not is_auto_video_unlocked(self.settings):
            self._av_apply_lock_state()
            self._os_set_status("Auto Video là tính năng Pro. Nhập key hoặc liên hệ mua key để dùng Edit one-shot.", error=True)
            return
        path = getattr(self, "_os_video_path", "")
        if not path:
            self._os_set_status("Chọn video trước.", error=True)
            return
        self._os_show_workspace(True)
        self._os_reset_batch_summary()
        self._os_set_source_controls_enabled(False)
        self._os_analyze_btn.setText("Dừng")
        self._os_analyze_btn.setEnabled(True)
        # Cancel sub-workers from previous video to prevent data mixing
        self._os_cancel_worker("_os_preview_worker", None, "preview")
        self._os_cancel_worker("_os_title_worker", None, "title")
        self._os_cancel_worker("_os_render_worker", None, "render")
        self._os_render_btn.setEnabled(False)
        if hasattr(self, "_os_render_row"):
            self._os_render_row.setVisible(False)
        self._os_plan_path = ""
        self._os_cut_list.clear()
        self._os_cut_list.setVisible(False)
        if hasattr(self, "_os_thumb_panel"):
            self._os_thumb_panel.setVisible(False)
        if hasattr(self, "_os_thumb_title"):
            self._os_thumb_title.clear()
        self._os_set_thumb_quality_badge("unchecked")
        self._os_log_buffer.clear()
        self._os_log_dropped = 0
        self._os_log.clear()
        self._os_details_visible = False
        self._os_log.setVisible(False)
        if hasattr(self, "_os_details_btn"):
            self._os_details_btn.setText("Chi tiết")
        self._os_result.setText("")
        self._os_result_paths = []
        self._os_result_folder = ""
        self._os_day_folder = ""
        self._os_platform_caption = ""
        if hasattr(self, "_os_result_actions"):
            self._os_result_actions.setVisible(False)
        if hasattr(self, "_os_debug_folder_btn"):
            self._os_debug_folder_btn.setVisible(False)
        self._os_set_status("Đang phân tích video…")
        perf_log("one_shot_analyze_start", source=Path(path).name)
        self._os_analyze_worker = OneShotAnalyzeWorker(path, self.settings, self._os_options())
        self._os_analyze_worker.log_line.connect(self._os_append_log)
        self._os_analyze_worker.progress.connect(lambda p: self._os_set_status(f"Đang phân tích video… {p}%"))
        self._os_analyze_worker.finished.connect(self._os_on_analyze_done)
        self._os_analyze_worker.error.connect(self._os_on_error)
        self._track_thread("_os_analyze_worker", self._os_analyze_worker, replace=True)

    def _os_run_simple(self):
        if self._os_cancel_worker("_os_simple_worker", getattr(self, "_os_simple_run_btn", None), "simple run"):
            return
        if not is_auto_video_unlocked(self.settings):
            self._av_apply_lock_state()
            self._os_set_status("Auto Video là tính năng Pro.", error=True)
            return
        path = getattr(self, "_os_video_path", "")
        if not path:
            self._os_set_status("Chọn video trước.", error=True)
            return
        self._os_show_workspace(True)
        self._os_reset_batch_summary()
        self._os_set_source_controls_enabled(False)
        self._os_simple_run_btn.setText("Dừng")
        self._os_simple_run_btn.setEnabled(True)
        self._os_log.clear()
        self._os_log_buffer.clear()
        self._os_details_visible = True
        self._os_log.setVisible(True)
        self._os_set_status("Simple pipeline: đang chạy…")
        self._os_simple_worker = OneShotSimpleRunWorker(path, self.settings, self._os_options())
        self._os_simple_worker.log_line.connect(self._os_append_log)
        self._os_simple_worker.progress.connect(lambda p: self._os_set_status(f"Simple pipeline… {p}%"))
        self._os_simple_worker.finished.connect(self._os_on_simple_done)
        self._os_simple_worker.error.connect(self._os_on_simple_error)
        self._track_thread("_os_simple_worker", self._os_simple_worker, replace=True)

    def _os_on_simple_done(self, item: dict):
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_simple_worker", None):
            return
        self._os_flush_log_buffer(force=True)
        self._os_set_source_controls_enabled(True)
        self._os_sync_source_actions(force=True)
        export_video = str(item.get("export_video") or item.get("video") or "")
        export_thumb = str(item.get("export_thumbnail") or item.get("thumbnail") or "")
        title = str(item.get("thumbnail_title") or "")
        warnings = item.get("warnings") or []
        warn_text = f" · {len(warnings)} cảnh báo" if warnings else ""
        self._os_set_status(f"Xong: {Path(export_video).name if export_video else 'video'}{warn_text}")
        if export_video:
            self._os_result_paths = [p for p in [export_video, export_thumb] if p]
            self._os_result_folder = str(Path(export_video).parent)
            self._os_result.setText(f"✓ {title or Path(export_video).name}")
            if hasattr(self, "_os_result_actions"):
                self._os_result_actions.setVisible(True)

    def _os_on_simple_error(self, message: str):
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_simple_worker", None):
            return
        self._os_flush_log_buffer(force=True)
        self._os_set_source_controls_enabled(True)
        self._os_sync_source_actions(force=True)
        self._os_set_status(message, error=True)

    def _os_run_batch(self):
        if not is_auto_video_unlocked(self.settings):
            self._av_apply_lock_state()
            self._os_set_status("Auto Video là tính năng Pro. Nhập key hoặc liên hệ mua key để chạy kho video.", error=True)
            return
        paths = getattr(self, "_os_batch_paths", []) or []
        if not paths:
            self._os_set_status("Chọn nhiều video hoặc chọn thư mục kho video trước.", error=True)
            return
        out_root = Path(self.settings.get("output_dir") or DEFAULT_OUT)
        try:
            out_root.mkdir(parents=True, exist_ok=True)
            probe = out_root / ".hedra_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as e:
            self._os_set_status(f"Không ghi được thư mục xuất: {out_root} ({e})", error=True)
            return
        whisper_status = whisper_runtime_status({**self.settings, "one_shot_whisper_model": "small"})
        if whisper_status.get("status") == "missing_ffmpeg" or whisper_status.get("status") == "missing_ffprobe":
            self._os_set_status(str(whisper_status.get("detail") or "Thiếu ffmpeg/ffprobe."), error=True)
            return
        if self._is_thread_running(getattr(self, "_os_batch_worker", None)):
            try:
                self._os_batch_worker.cancel()
                self._os_batch_worker.requestInterruption()
            except Exception:
                pass
            self._os_batch_btn.setEnabled(False)
            self._os_batch_btn.setText("Đang dừng…")
            self._os_set_status("Đang dừng batch. Job đang chạy sẽ hoàn tất sạch.")
            return
        self._os_show_workspace(True)
        self._os_reset_batch_summary()
        self._os_batch_total = len(paths)
        self._os_set_source_controls_enabled(False)
        self._os_update_batch_summary(self._os_batch_total, True)
        self._os_batch_btn.setEnabled(False)
        self._os_batch_btn.setText("Dừng")
        # Cancel single-video workers to prevent data mixing
        self._os_cancel_worker("_os_analyze_worker", None, "phân tích")
        self._os_cancel_worker("_os_preview_worker", None, "preview")
        self._os_cancel_worker("_os_title_worker", None, "title")
        self._os_cancel_worker("_os_render_worker", None, "render")
        self._os_analyze_btn.setEnabled(False)
        self._os_render_btn.setEnabled(False)
        if hasattr(self, "_os_render_row"):
            self._os_render_row.setVisible(False)
        self._os_cut_list.clear()
        self._os_cut_list.setVisible(True)
        if hasattr(self, "_os_thumb_panel"):
            self._os_thumb_panel.setVisible(False)
        self._os_log.clear()
        self._os_log_buffer.clear()
        self._os_log_dropped = 0
        self._os_details_visible = True
        self._os_log.setVisible(True)
        if hasattr(self, "_os_details_btn"):
            self._os_details_btn.setText("Ẩn")
        self._os_result.setText("")
        self._os_result_paths = []
        self._os_result_folder = ""
        self._os_day_folder = ""
        self._os_platform_caption = ""
        if hasattr(self, "_os_result_actions"):
            self._os_result_actions.setVisible(False)
        if hasattr(self, "_os_debug_folder_btn"):
            self._os_debug_folder_btn.setVisible(False)
        if whisper_status.get("status") == "ready":
            self._os_set_status(f"Đang chạy kho video… 0/{len(paths)} · Whisper local sẵn sàng")
        else:
            self._os_set_status(f"Đang chạy kho video… 0/{len(paths)} · Không có transcript local, vẫn render bằng fallback cắt khoảng lặng")
        perf_log("one_shot_batch_start", total=len(paths))
        if is_simple_pipeline(self.settings):
            self._os_set_status(f"Simple batch: 0/{len(paths)}")
            self._os_batch_worker = OneShotSimpleBatchWorker(paths, self.settings, self._os_options())
        else:
            self._os_batch_worker = OneShotBatchWorker(paths, self.settings, self._os_options())
        self._os_batch_worker.log_line.connect(self._os_append_log)
        self._os_batch_worker.progress.connect(lambda p: self._os_set_status(f"Đang chạy kho video… {p}%"))
        self._os_batch_worker.item_done.connect(self._os_on_batch_item_done)
        self._os_batch_worker.finished.connect(self._os_on_batch_done)
        self._os_batch_worker.error.connect(self._os_on_batch_error)
        self._track_thread("_os_batch_worker", self._os_batch_worker, replace=True)
        self._os_batch_btn.setEnabled(True)

    def _os_on_batch_item_done(self, item: dict):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_batch_worker", None):
            return
        name = str(item.get("source_name") or Path(str(item.get("source") or "")).name or "video")
        if item.get("ok"):
            self._os_batch_ok = getattr(self, "_os_batch_ok", 0) + 1
            final_name = Path(str(item.get("export_video") or item.get("video") or name)).name
            title = str(item.get("thumbnail_render_title") or item.get("thumbnail_title") or "").strip()
            reason = str(item.get("thumbnail_quality_label") or "").strip()
            quality = item.get("thumbnail_quality", {}) if isinstance(item.get("thumbnail_quality"), dict) else {}
            layout_quality = item.get("thumbnail_layout_quality", {}) if isinstance(item.get("thumbnail_layout_quality"), dict) else {}
            publish_label = str(quality.get("publish_label") or layout_quality.get("label") or "OK").strip()
            profile = item.get("render_profile", {}) if isinstance(item, dict) else {}
            speed = ""
            if isinstance(profile, dict) and profile:
                factor = float(profile.get("realtime_factor") or 0)
                method = str(profile.get("render_method") or "").replace("_", " ")
                seconds = float(profile.get("ffmpeg_seconds") or item.get("render_seconds") or 0)
                if factor > 0 or seconds > 0:
                    pieces = []
                    if seconds > 0:
                        pieces.append(f"{seconds:.1f}s")
                    if factor > 0:
                        pieces.append(f"{factor:.2f}x")
                    speed = f" · {method or 'ffmpeg'} " + " · ".join(pieces)
            cost = item.get("ai_cost_total", {}) if isinstance(item.get("ai_cost_total"), dict) else {}
            cost_part = ""
            if cost:
                cost_part = f" · AI ${float(cost.get('estimated_usd') or 0):.6f} ~ {int(cost.get('estimated_vnd') or 0)}đ"
            title_part = f" · {title}" if title else ""
            reason_part = f" · {reason}" if reason else ""
            label = f"{publish_label} · {final_name}{speed}{cost_part}{title_part}{reason_part}"
        elif item.get("cancelled"):
            label = f"Đã dừng · {name}"
        elif item.get("needs_review"):
            label = f"Cần review · {name} · {item.get('thumbnail_title', '')} · {item.get('error', '')}"
        else:
            self._os_batch_failed = getattr(self, "_os_batch_failed", 0) + 1
            label = f"Lỗi · {name} · {item.get('error', 'Lỗi không rõ')}"
        self._os_batch_processed = getattr(self, "_os_batch_processed", 0) + 1
        self._os_update_batch_summary(getattr(self, "_os_batch_total", 0), True)
        self._os_cut_list.addItem(QListWidgetItem(label))

    def _os_on_batch_done(self, summary_path: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_batch_worker", None):
            return
        self._os_flush_log_buffer(force=True)
        self._os_plan_path = ""
        perf_log("one_shot_batch_done", summary=Path(summary_path).name)
        try:
            summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
            items = summary.get("items", []) if isinstance(summary, dict) else []
            export_paths = []
            first_caption = ""
            for item in items:
                if not item.get("ok"):
                    continue
                if item.get("export_video"):
                    export_paths.append(str(item["export_video"]))
                if not first_caption:
                    first_caption = str(item.get("platform_caption") or "")
            export_dir = Path(summary.get("export_dir") or Path(summary_path).parent)
            self._os_set_result_paths(export_paths, Path(summary_path).parent, export_dir)
            cost = summary.get("ai_cost_total", {}) if isinstance(summary, dict) else {}
            cost_text = (
                f"\nAI cost: ${float(cost.get('estimated_usd', 0) or 0):.6f}"
                f" ~ {int(cost.get('estimated_vnd', 0) or 0)}đ"
            ) if cost else ""
            batch_seconds = float(summary.get("batch_total_seconds") or 0)
            render_seconds = float(summary.get("render_total_seconds") or 0)
            render_factor = float(summary.get("render_avg_realtime_factor") or 0)
            render_text = ""
            if batch_seconds > 0 or render_seconds > 0:
                render_text = (
                    f"\nThời gian: batch {batch_seconds:.1f}s"
                    + (f" · render {render_seconds:.1f}s" if render_seconds > 0 else "")
                    + (f" · TB {render_factor:.2f}x realtime" if render_factor > 0 else "")
                )
            processed = int(summary.get("processed", len(items)) or 0)
            total_selected = int(summary.get("total_selected", summary.get("total", 0)) or 0)
            skipped = int(summary.get("skipped", 0) or 0)
            cancelled = bool(summary.get("cancelled"))
            done_label = "Đã dừng" if cancelled else "Hoàn tất"
            if hasattr(self, "_os_batch_summary"):
                summary_state = "Đã dừng" if cancelled else "Hoàn tất"
                self._os_batch_summary.setText(
                    f"{summary_state}  ·  OK {int(summary.get('ok', 0) or 0)}  ·  "
                    f"Lỗi {int(summary.get('failed', 0) or 0)}  ·  Bỏ qua {skipped}"
                )
                self._os_batch_summary.setVisible(True)
            self._os_result.setText(
                f"{done_label}: {int(summary.get('ok', 0) or 0)}/{total_selected} video  ·  "
                f"Đã xử lý {processed}\n"
                f"Thư mục xuất: {export_dir}"
                f"{render_text}"
                f"{cost_text}"
            )
            self._os_platform_caption = first_caption
            self._os_set_status("Batch đã dừng." if cancelled else "Hoàn thành kho video. Mở thư mục xuất để copy toàn bộ file cuối.")
        except Exception as e:
            self._os_set_result_paths([summary_path], Path(summary_path).parent)
            self._os_result.setText(summary_path)
            self._os_set_status(f"Batch xong nhưng không đọc được summary: {e}", error=True)
        self._os_set_source_controls_enabled(True)
        self._os_sync_source_actions(force=True)

    def _os_on_batch_error(self, msg: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_batch_worker", None):
            return
        self._os_flush_log_buffer(force=True)
        perf_log("one_shot_batch_error", message=str(msg)[:180])
        self._os_render_btn.setEnabled(bool(getattr(self, "_os_plan_path", "")))
        self._os_set_status(msg, error=True)
        self._os_set_source_controls_enabled(True)
        self._os_sync_source_actions(force=True)

    def _os_on_analyze_done(self, plan_path: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_analyze_worker", None):
            return
        self._os_flush_log_buffer(force=True)
        perf_log("one_shot_analyze_done", plan=Path(plan_path).name)
        self._os_show_workspace(True)
        if hasattr(self, "_os_render_row"):
            self._os_render_row.setVisible(True)
        if hasattr(self, "_os_analyze_btn"):
            self._os_analyze_btn.setText("Phân tích")
        self._os_sync_source_actions()
        self._os_set_source_controls_enabled(True)
        self._os_plan_path = plan_path
        self._os_load_cut_plan(plan_path)
        if hasattr(self, "_os_thumb_panel"):
            self._os_thumb_panel.setVisible(True)
        self._os_set_status("Phân tích xong. Kiểm tra tiêu đề, preview thumbnail rồi render.")
        self._os_render_btn.setEnabled(True)
        self._os_preview_thumbnail()

    def _os_load_cut_plan(self, plan_path: str):
        self._os_cut_list.clear()
        try:
            plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        except Exception as e:
            self._os_set_status(f"Không đọc được cuts.json: {e}", error=True)
            return
        cuts = plan.get("cuts", [])
        if plan.get("thumbnail_title_suggestion") and not self._os_thumb_title.text().strip():
            source = Path(plan.get("source_video") or "video.mp4")
            segments = plan.get("transcript", [])
            if not isinstance(segments, list):
                segments = []
            title = _clean_thumbnail_title(str(plan.get("thumbnail_title_suggestion", "")).strip(), source.stem, segments)
            self._os_thumb_title.setText(title)
        if hasattr(self, "_os_thumb_title_status"):
            source_map = {
                "deepseek": "DeepSeek đề xuất",
                "deepseek_pro": "DeepSeek Pro đề xuất",
                "gemini": "Gemini đề xuất",
                "ai": "AI đề xuất",
                "rule": "Rule an toàn",
            }
            source_label = source_map.get(plan.get("thumbnail_title_source"), "Fallback nội bộ")
            cost = plan.get("ai_cost_total", {}) if isinstance(plan, dict) else {}
            cost_text = ""
            if cost:
                cost_text = f" · AI ${float(cost.get('estimated_usd', 0) or 0):.6f} ~ {int(cost.get('estimated_vnd', 0) or 0)}đ"
            quality = plan.get("thumbnail_title_quality", {}) if isinstance(plan, dict) else {}
            reasons = quality.get("reasons", []) if isinstance(quality, dict) else []
            reason_text = f" · {', '.join(str(r) for r in reasons[:2])}" if reasons else ""
            self._os_thumb_title_status.setText(f"{source_label}{reason_text}{cost_text}")
            self._os_set_thumb_quality_badge(str(quality.get("status") or ("fallback" if plan.get("thumbnail_title_source") == "fallback" else "expert_checked")))
        self._os_update_preview_metadata_from_plan(plan)
        if not bool(self.settings.get("one_shot_cut_video", True)):
            item = QListWidgetItem("Cut đang tắt. Render sẽ giữ nguyên timeline, chỉ áp noise/LUT/thumbnail.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self._os_cut_list.addItem(item)
            self._os_cut_list.setVisible(True)
            return
        if not cuts:
            item = QListWidgetItem("Không có đoạn chắc chắn cần cắt. Render vẫn sẽ áp noise/LUT/thumbnail.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self._os_cut_list.addItem(item)
        for cut in cuts:
            label = (
                f"{cut.get('start', 0):.2f}s → {cut.get('end', 0):.2f}s · "
                f"{cut.get('reason', 'Đề xuất cắt')} · {cut.get('source', 'auto')}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, cut.get("id", ""))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if cut.get("enabled", True) else Qt.CheckState.Unchecked)
            self._os_cut_list.addItem(item)
        self._os_cut_list.setVisible(True)

    def _os_selected_cut_ids(self) -> list[str]:
        ids = []
        for i in range(self._os_cut_list.count()):
            item = self._os_cut_list.item(i)
            cut_id = item.data(Qt.ItemDataRole.UserRole)
            if cut_id and item.checkState() == Qt.CheckState.Checked:
                ids.append(str(cut_id))
        return ids

    def _os_regenerate_thumbnail_title(self, mode: str | bool = "expert"):
        if not getattr(self, "_os_plan_path", ""):
            self._os_set_status("Phân tích video trước khi tạo lại tiêu đề.", error=True)
            return
        if isinstance(mode, bool):
            mode = str(self.settings.get("one_shot_thumbnail_title_mode", "expert") or "expert")
        mode = str(mode or "expert")
        self._os_thumb_title_mode = mode
        self.settings["one_shot_thumbnail_title_mode"] = mode
        try:
            save_settings(self.settings)
        except Exception:
            pass
        self._os_thumb_regen_btn.setEnabled(False)
        self._os_thumb_regen_btn.setText("Đang tạo…")
        if hasattr(self, "_os_thumb_title_status"):
            label = {"expert": "chuẩn chuyên ngành", "viral": "viral hơn", "short": "ngắn gọn hơn"}.get(mode, "chuẩn chuyên ngành")
            self._os_thumb_title_status.setText(f"Đang kiểm tra lại bằng AI · {label}…")
        self._os_set_thumb_quality_badge("unchecked", "Đang kiểm tra")
        self._os_title_worker = OneShotTitleWorker(self._os_plan_path, self.settings, mode)
        self._os_title_worker.finished.connect(self._os_on_title_regenerated)
        self._os_title_worker.error.connect(self._os_on_title_error)
        self._track_thread("_os_title_worker", self._os_title_worker, replace=True)

    def _os_on_title_regenerated(self, title: str, source: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_title_worker", None):
            return
        self._os_thumb_regen_btn.setEnabled(True)
        self._os_thumb_regen_btn.setText("Tạo lại tiêu đề")
        self._os_thumb_title.setText(title)
        source_map = {
            "deepseek": "DeepSeek đề xuất",
            "deepseek_pro": "DeepSeek Pro đề xuất",
            "gemini": "Gemini đề xuất",
            "ai": "AI đề xuất",
            "rule": "Rule an toàn",
        }
        source_label = source_map.get(source, "Fallback nội bộ")
        if hasattr(self, "_os_thumb_title_status"):
            self._os_thumb_title_status.setText(f"{source_label} · đã kiểm tra")
        try:
            plan = json.loads(Path(self._os_plan_path).read_text(encoding="utf-8"))
            quality = plan.get("thumbnail_title_quality", {}) if isinstance(plan, dict) else {}
            self._os_set_thumb_quality_badge(str(quality.get("status") or ("fallback" if source == "fallback" else "expert_checked")))
            reasons = quality.get("reasons", []) if isinstance(quality, dict) else []
            if hasattr(self, "_os_thumb_title_status") and reasons:
                self._os_thumb_title_status.setText(f"{source_label} · {', '.join(str(r) for r in reasons[:2])}")
        except Exception:
            self._os_set_thumb_quality_badge("fallback" if source == "fallback" else "expert_checked")
        self._os_set_status("Đã tạo lại tiêu đề thumbnail.")
        self._os_preview_thumbnail()

    def _os_on_title_error(self, msg: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_title_worker", None):
            return
        self._os_thumb_regen_btn.setEnabled(True)
        self._os_thumb_regen_btn.setText("Tạo lại tiêu đề")
        self._os_set_thumb_quality_badge("needs_review")
        self._os_set_status(f"Không tạo lại được tiêu đề: {msg}", error=True)

    def _os_schedule_preview_update(self, _text: str = ""):
        if not getattr(self, "_os_plan_path", ""):
            return
        if hasattr(self, "_os_preview_timer"):
            self._os_preview_timer.start()
        if hasattr(self, "_os_preview_status"):
            self._os_preview_status.setText("Đang chờ cập nhật preview…")

    def _os_set_preview_image(self, image_path: str):
        if not hasattr(self, "_os_thumb_preview_img"):
            return
        pix = QPixmap(image_path)
        if pix.isNull():
            self._os_thumb_preview_img.setPixmap(QPixmap())
            self._os_thumb_preview_img.setText("Preview")
            return
        scaled = pix.scaled(
            self._os_thumb_preview_img.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._os_thumb_preview_img.setText("")
        self._os_thumb_preview_img.setPixmap(scaled)

    def _os_update_preview_metadata_from_plan(self, plan: dict | None = None):
        if not getattr(self, "_os_plan_path", ""):
            return
        try:
            if plan is None:
                plan = json.loads(Path(self._os_plan_path).read_text(encoding="utf-8"))
            meta_plan = plan.get("metadata_plan", {}) if isinstance(plan, dict) else {}
            upload_meta = meta_plan.get("upload_metadata", {}) if isinstance(meta_plan, dict) else {}
            final_name = str(meta_plan.get("final_video_name") or "").strip()
            hashtags = meta_plan.get("final_hashtags") or upload_meta.get("hashtags") or []
            final_status = str(plan.get("final_status") or "").strip()
            quality = plan.get("thumbnail_title_quality", {}) if isinstance(plan, dict) else {}
            if not final_status:
                publish = str(quality.get("publish_status") or "")
                final_status = "ready" if publish == "ready" else "needs_review"
            if hasattr(self, "_os_preview_filename"):
                self._os_preview_filename.setText(f"Tên video: {final_name}" if final_name else "")
            if hasattr(self, "_os_preview_hashtags"):
                self._os_preview_hashtags.setText("Hashtag: " + " ".join(str(t) for t in hashtags[:4]) if hashtags else "")
            if hasattr(self, "_os_preview_status"):
                label = {"ready": "Đăng được", "needs_review": "Cần xem lại", "failed": "Lỗi"}.get(final_status, "Cần xem lại")
                reasons = quality.get("reasons", []) if isinstance(quality, dict) else []
                suffix = f" · {', '.join(str(r) for r in reasons[:2])}" if reasons else ""
                self._os_preview_status.setText(f"{label}{suffix}")
            preview = str(plan.get("thumbnail_preview") or "")
            if preview and Path(preview).exists():
                self._os_set_preview_image(preview)
        except Exception:
            pass

    def _os_preview_thumbnail(self):
        if not getattr(self, "_os_plan_path", ""):
            self._os_set_status("Phân tích video trước khi preview thumbnail.", error=True)
            return
        worker = getattr(self, "_os_preview_worker", None)
        if self._is_thread_running(worker):
            self._os_set_status("Preview thumbnail đang chạy…")
            return
        try:
            plan = json.loads(Path(self._os_plan_path).read_text(encoding="utf-8"))
            source = Path(plan.get("source_video") or "video.mp4")
            title = (
                self._os_thumb_title.text().strip()
                or str(plan.get("thumbnail_title_suggestion", "")).strip()
                or source.stem
            )
            segments = plan.get("transcript", [])
            if not isinstance(segments, list):
                segments = []
            title = _clean_thumbnail_title(title, source.stem, segments)
            self._os_thumb_title.setText(title)
            self._os_set_thumb_quality_badge("expert_checked")
            self._os_save_toolbar_settings()
            self._os_thumb_preview_btn.setEnabled(False)
            self._os_set_status("Đang tạo preview thumbnail…")
            perf_log("one_shot_preview_start", plan=Path(self._os_plan_path).name)
            self._os_preview_worker = OneShotThumbnailPreviewWorker(self._os_plan_path, dict(self.settings), title)
            self._os_preview_worker.finished.connect(self._os_on_preview_done)
            self._os_preview_worker.error.connect(self._os_on_preview_error)
            self._track_thread("_os_preview_worker", self._os_preview_worker, replace=True)
        except Exception as e:
            self._os_set_status(f"Không preview được thumbnail: {e}", error=True)

    def _os_on_preview_done(self, preview_path: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_preview_worker", None):
            return
        preview = Path(preview_path)
        out_dir = preview.parent
        self._os_thumb_preview_btn.setEnabled(True)
        self._os_set_preview_image(str(preview))
        try:
            plan = json.loads(Path(self._os_plan_path).read_text(encoding="utf-8"))
            self._os_update_preview_metadata_from_plan(plan)
        except Exception:
            pass
        self._os_set_result_paths([str(preview)], out_dir, _one_shot_exports_dir(out_dir))
        self._os_result.setText(f"Preview thumbnail: {preview.name}\nThư mục preview: {out_dir}")
        self._os_set_status("Đã tạo preview thumbnail.")
        perf_log("one_shot_preview_done", preview=preview.name)

    def _os_on_preview_error(self, msg: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_preview_worker", None):
            return
        self._os_thumb_preview_btn.setEnabled(True)
        perf_log("one_shot_preview_error", message=str(msg)[:180])
        self._os_set_status(f"Không preview được thumbnail: {msg}", error=True)

    def _os_render_video(self):
        if self._os_cancel_worker("_os_render_worker", getattr(self, "_os_render_btn", None), "render"):
            return
        if not is_auto_video_unlocked(self.settings):
            self._av_apply_lock_state()
            self._os_set_status("Auto Video là tính năng Pro. Nhập key hoặc liên hệ mua key để render.", error=True)
            return
        if not getattr(self, "_os_plan_path", ""):
            self._os_set_status("Phân tích video trước khi render.", error=True)
            return
        plan = {}
        try:
            plan = json.loads(Path(self._os_plan_path).read_text(encoding="utf-8"))
            out_dir = Path(plan["output_dir"])
            export_dir = _one_shot_exports_dir(out_dir)
            source_stem = Path(plan.get("source_video") or "edited").stem or "edited"
            segments = plan.get("transcript", [])
            if not isinstance(segments, list):
                segments = []
            thumb_title = _clean_thumbnail_title(
                self._os_thumb_title.text().strip()
                or str(plan.get("thumbnail_title_suggestion", "")).strip()
                or source_stem,
                source_stem,
                segments,
            )
            preview = str(plan.get("thumbnail_preview") or "")
            preview_title = _clean_thumbnail_title(str(plan.get("thumbnail_title_suggestion") or ""), source_stem, segments)
            if not preview or not Path(preview).exists() or preview_title != thumb_title:
                self._os_set_status("Đang tạo preview thumbnail trước khi render…")
                self._os_preview_thumbnail()
                return
            upload_metadata = _build_upload_metadata(thumb_title, source_stem, segments, self.settings)
            output_video = _upload_video_output_path(export_dir, source_stem, upload_metadata)
        except Exception:
            output_video = None
            source_stem = ""
            thumb_title = ""
        overwrite = False
        if output_video and output_video.exists():
            ret = QMessageBox.question(
                self,
                "File đã tồn tại",
                f"{output_video.name} đã tồn tại.\nBạn muốn lưu đè không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            overwrite = ret == QMessageBox.StandardButton.Yes
        self._os_render_btn.setText("Dừng")
        self._os_render_btn.setEnabled(True)
        self._os_analyze_btn.setEnabled(False)
        self._os_set_source_controls_enabled(False)
        self._os_set_status("Đang render video…")
        perf_log("one_shot_render_start", plan=Path(self._os_plan_path).name)
        opts = self._os_options()
        segments = plan.get("transcript", []) if isinstance(plan, dict) else []
        if not isinstance(segments, list):
            segments = []
        thumb_title = _clean_thumbnail_title(thumb_title or self._os_thumb_title.text().strip(), source_stem if output_video else "", segments)
        self._os_thumb_title.setText(thumb_title)
        opts.update({
            "thumbnail_title": thumb_title,
            "overwrite": overwrite,
            "output_video": str(output_video) if output_video else "",
            "export_thumbnail": True,
            "render_to_final": True,
            "keep_debug_audio": False,
        })
        self._os_render_worker = OneShotRenderWorker(self._os_plan_path, self._os_selected_cut_ids(), opts)
        self._os_render_worker.log_line.connect(self._os_append_log)
        self._os_render_worker.progress.connect(lambda p: self._os_set_status(f"Đang render video… {p}%"))
        self._os_render_worker.finished.connect(self._os_on_render_done)
        self._os_render_worker.error.connect(self._os_on_error)
        self._track_thread("_os_render_worker", self._os_render_worker, replace=True)

    def _os_on_render_done(self, report_path: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        if sender is not None and sender is not getattr(self, "_os_render_worker", None):
            return
        self._os_flush_log_buffer(force=True)
        perf_log("one_shot_render_done", report=Path(report_path).name)
        self._os_show_workspace(True)
        if hasattr(self, "_os_render_row"):
            self._os_render_row.setVisible(True)
        self._os_render_btn.setText("Render")
        self._os_render_btn.setEnabled(True)
        self._os_set_source_controls_enabled(True)
        self._os_sync_source_actions()
        self._os_report_path = report_path
        try:
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            export_video = str(report.get("export_video", "") or report.get("video", "") or "")
            export_thumbnail = str(report.get("export_thumbnail", "") or report.get("thumbnail", "") or "")
            quality = report.get("thumbnail_title_quality", {}) if isinstance(report, dict) else {}
            layout_quality = report.get("thumbnail_layout_quality", {}) if isinstance(report, dict) else {}
            if isinstance(quality, dict):
                self._os_set_thumb_quality_badge(str(quality.get("status") or "expert_checked"))
            result_paths = [export_video, export_thumbnail]
            folder = Path(report.get("job_dir") or Path(report_path).parent)
            export_dir = Path(report.get("export_dir") or _one_shot_exports_dir(folder))
            self._os_set_result_paths(result_paths, folder, export_dir)
            cost = report.get("ai_cost_total", {}) if isinstance(report, dict) else {}
            upload_metadata = report.get("upload_metadata", {}) if isinstance(report, dict) else {}
            platform_caption = str(upload_metadata.get("platform_caption") or report.get("platform_caption") or "")
            self._os_platform_caption = platform_caption
            cost_text = ""
            if cost:
                cost_text = (
                    f"\nAI cost: ${float(cost.get('estimated_usd', 0) or 0):.6f}"
                    f" ~ {int(cost.get('estimated_vnd', 0) or 0)}đ"
                )
            caption_text = ""
            if upload_metadata:
                caption_text = (
                    f"\nCaption đăng bài:\n{str(upload_metadata.get('caption_full') or '').strip()}"
                    f"\nHashtag: {' '.join(upload_metadata.get('hashtags', []) or [])}"
                )
            profile = report.get("render_profile", {}) if isinstance(report, dict) else {}
            profile_text = ""
            if isinstance(profile, dict) and profile:
                factor = float(profile.get("realtime_factor") or 0)
                method = str(profile.get("render_method") or "").replace("_", " ")
                bottleneck = str(profile.get("bottleneck") or "").strip()
                seconds = float(profile.get("ffmpeg_seconds") or profile.get("total_seconds") or 0)
                profile_text = f"\nRender: {method or 'ffmpeg'} · {factor:.2f}x realtime · {seconds:.1f}s"
                if bottleneck:
                    profile_text += f"\nBottleneck: {bottleneck}"
            quality_text = ""
            if isinstance(quality, dict) or isinstance(layout_quality, dict):
                title_label = quality.get("publish_label") if isinstance(quality, dict) else ""
                layout_label = layout_quality.get("label") if isinstance(layout_quality, dict) else ""
                render_title = str(report.get("thumbnail_render_title") or report.get("thumbnail_title") or "").strip()
                final_label = str(report.get("final_status_label") or "").strip()
                quality_text = (
                    f"\nChất lượng: {final_label or title_label or 'OK'}"
                    + (f" · Layout {layout_label}" if layout_label else "")
                    + (f"\nTitle thumbnail: {render_title}" if render_title else "")
                    + (f"\nTên video: {str(report.get('final_video_name') or Path(export_video).name)}" if export_video else "")
                )
            self._os_result.setText(
                f"Video đã xuất: {Path(export_video).name}\n"
                f"Thumbnail: {Path(export_thumbnail).name}\n"
                f"Thư mục xuất: {export_dir}"
                f"{quality_text}"
                f"{profile_text}"
                f"{caption_text}"
                f"{cost_text}"
            )
        except Exception:
            self._os_result.setText(report_path)
        self._os_set_status("Hoàn thành edit one-shot.")

    def _os_set_result_paths(self, paths: list[str], folder: Path | str, export_folder: Path | str | None = None):
        clean = [p for p in paths if p]
        self._os_result_paths = clean
        self._os_result_folder = str(folder) if folder else ""
        if export_folder:
            self._os_day_folder = str(export_folder)
        else:
            try:
                self._os_day_folder = str(_one_shot_exports_dir(Path(folder)))
            except Exception:
                self._os_day_folder = ""
        if hasattr(self, "_os_result_actions"):
            self._os_result_actions.setVisible(bool(clean or self._os_day_folder))
        if hasattr(self, "_os_debug_folder_btn"):
            self._os_debug_folder_btn.setVisible(bool(getattr(self, "_os_details_visible", False) and self._os_result_folder))

    def _os_copy_result_paths(self):
        paths = getattr(self, "_os_result_paths", []) or []
        folder = getattr(self, "_os_day_folder", "") or ""
        text = "\n".join(paths or ([folder] if folder else []))
        if not text:
            self._os_set_status("Chưa có kết quả để copy.", error=True)
            return
        QApplication.clipboard().setText(text)
        self._os_set_status("Đã copy đường dẫn file xuất.")

    def _os_copy_platform_caption(self):
        text = getattr(self, "_os_platform_caption", "") or ""
        if not text and getattr(self, "_os_report_path", ""):
            try:
                report = json.loads(Path(self._os_report_path).read_text(encoding="utf-8"))
                meta = report.get("upload_metadata", {}) if isinstance(report, dict) else {}
                text = str(meta.get("platform_caption") or report.get("platform_caption") or "")
            except Exception:
                text = ""
        if not text:
            self._os_set_status("Chưa có caption để copy.", error=True)
            return
        QApplication.clipboard().setText(text)
        self._os_set_status("Đã copy caption đăng bài.")

    def _os_open_result_folder(self):
        folder = getattr(self, "_os_result_folder", "") or ""
        if not folder:
            self._os_set_status("Chưa có thư mục debug.", error=True)
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            reveal_file(folder)

    def _os_open_day_folder(self):
        folder = getattr(self, "_os_day_folder", "") or ""
        if not folder:
            self._os_set_status("Chưa có thư mục xuất.", error=True)
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            reveal_file(folder)

    def _os_on_error(self, msg: str):
        # Guard: ignore stale callback from cancelled worker
        sender = self.sender()
        is_analyze = sender is getattr(self, "_os_analyze_worker", None)
        is_render = sender is getattr(self, "_os_render_worker", None)
        if sender is not None and not is_analyze and not is_render:
            return
        self._os_flush_log_buffer(force=True)
        self._os_show_workspace(True)
        cancelled = "Đã dừng" in str(msg) or "Đã huỷ" in str(msg)
        perf_log("one_shot_error", cancelled=cancelled, message=str(msg)[:180])
        if is_analyze:
            if hasattr(self, "_os_analyze_btn"):
                self._os_analyze_btn.setText("Phân tích")
        if hasattr(self, "_os_render_btn"):
            self._os_render_btn.setText("Render")
        if not is_render:
            self._os_render_btn.setEnabled(bool(getattr(self, "_os_plan_path", "")))
        else:
            self._os_render_btn.setEnabled(True)
        if hasattr(self, "_os_render_row"):
            self._os_render_row.setVisible(bool(getattr(self, "_os_plan_path", "")))
        self._os_set_source_controls_enabled(True)
        self._os_sync_source_actions()
        self._os_set_status("Đã dừng." if cancelled else msg, error=not cancelled)

    def _os_set_status(self, msg: str, error: bool = False):
        if not hasattr(self, "_os_status"):
            return
        if error:
            self._os_show_workspace(True)
        if not error and self._should_throttle_ui("one_shot_status", interval=0.16):
            return
        color = DESTRUCTIVE if error else TEXT_MUTE
        self._os_status.setText(msg)
        self._os_status.setStyleSheet(f"font-size:12px;color:{color};background:transparent;border:none;")

    def _os_append_log(self, line: str):
        if not hasattr(self, "_os_log"):
            return
        text = str(line or "").strip()
        if not text:
            return
        if len(self._os_log_buffer) >= 160:
            self._os_log_dropped += 1
            return
        self._os_log_buffer.append(text[:1200])
        if not self._os_log_timer.isActive():
            self._os_log_timer.start()
        if time.perf_counter() - self._os_log_last_flush > 0.35:
            self._os_flush_log_buffer()

    def _os_flush_log_buffer(self, force: bool = False):
        if not hasattr(self, "_os_log"):
            return
        if not self._os_log_buffer and not self._os_log_dropped:
            if force:
                self._os_log_timer.stop()
            return
        if not force and time.perf_counter() - self._os_log_last_flush < 0.22:
            return
        lines = self._os_log_buffer[:60]
        del self._os_log_buffer[:60]
        if self._os_log_dropped:
            lines.append(f"... đã gộp {self._os_log_dropped} dòng log để tránh lag UI")
            perf_log("one_shot_log_throttled", dropped=self._os_log_dropped)
            self._os_log_dropped = 0
        if lines:
            self._os_log.append("\n".join(lines))
        self._os_log_last_flush = time.perf_counter()
        if force or not self._os_log_buffer:
            self._os_log_timer.stop()

    def _os_toggle_details(self):
        self._os_details_visible = not getattr(self, "_os_details_visible", False)
        if hasattr(self, "_os_log"):
            self._os_log.setVisible(self._os_details_visible)
        if hasattr(self, "_os_debug_folder_btn"):
            self._os_debug_folder_btn.setVisible(bool(self._os_details_visible and getattr(self, "_os_result_folder", "")))
        if hasattr(self, "_os_details_btn"):
            self._os_details_btn.setText("Ẩn" if self._os_details_visible else "Chi tiết")

    def _build_auto_video_unlock_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame{{background:{CONTROL_BG};border:1px solid {BORDER_SOFT};border-radius:12px;}}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(ui_icon("api", 22, ACCENT).pixmap(icon_size(22)))
        head.addWidget(icon_lbl)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Cần Pro key")
        title.setStyleSheet(f"font-size:15px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        sub = QLabel("TTS và STT dùng bình thường. Auto Video là tính năng Pro, cần key để tạo, edit và render video.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        head.addLayout(title_col, 1)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._av_license_input = QLineEdit()
        self._av_license_input.setPlaceholderText("Nhập Pro key")
        self._av_license_input.setText(self._current_license_key())
        self._av_license_input.setFixedHeight(34)
        self._av_license_input.setStyleSheet(
            f"QLineEdit{{background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;"
            f"color:{TEXT};font-size:13px;padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{ACCENT};}}"
        )
        self._av_license_input.returnPressed.connect(self._av_unlock_license)
        row.addWidget(self._av_license_input, 1)

        self._av_unlock_btn = QPushButton("Kiểm tra key")
        self._av_unlock_btn.setFixedHeight(34)
        self._av_unlock_btn.setStyleSheet(self._compact_primary_style())
        self._av_unlock_btn.clicked.connect(self._av_unlock_license)
        row.addWidget(self._av_unlock_btn)
        self._av_buy_key_btn = QPushButton("Liên hệ mua key")
        self._av_buy_key_btn.setFixedHeight(34)
        self._av_buy_key_btn.setStyleSheet(self._compact_secondary_style())
        self._av_buy_key_btn.clicked.connect(self._open_feedback)
        row.addWidget(self._av_buy_key_btn)
        lay.addLayout(row)

        self._av_license_status = QLabel("")
        self._av_license_status.setWordWrap(True)
        self._av_license_status.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        lay.addWidget(self._av_license_status)
        return panel

    def _av_apply_lock_state(self):
        unlocked = is_auto_video_unlocked(self.settings)
        self._av_license_unlocked = unlocked
        if hasattr(self, "_av_lock_panel"):
            self._av_lock_panel.setVisible(not unlocked)
        if hasattr(self, "_av_gen_btn"):
            self._av_gen_btn.setEnabled(unlocked)
            self._av_gen_btn.setToolTip("" if unlocked else "Cần Pro key để dùng Auto Video")
        if hasattr(self, "_av_status") and not unlocked:
            self._av_set_status("Auto Video là tính năng Pro. Nhập key hoặc liên hệ mua key để sử dụng.", error=False)
        if hasattr(self, "_av_license_status"):
            key = self._current_license_key()
            if key:
                cache = self.settings.get("pro_license_cache", {})
                ok = is_auto_video_unlocked(self.settings)
                msg = cache.get("message") if isinstance(cache, dict) else ""
                msg = msg or ("Đã mở khóa Pro cho Auto Video." if ok else "Pro key chưa mở Auto Video.")
                self._av_license_status.setText(msg)
                self._av_license_status.setStyleSheet(
                    f"font-size:12px;color:{SUCCESS if ok else DESTRUCTIVE};background:transparent;border:none;"
                )
            else:
                self._av_license_status.setText("Chưa có Pro key cho Auto Video. Nhập key hoặc liên hệ mua key.")
                self._av_license_status.setStyleSheet(
                    f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;"
                )

    def _av_unlock_license(self):
        key = self._av_license_input.text().strip() if hasattr(self, "_av_license_input") else ""
        self._av_unlock_btn.setEnabled(False)
        self._av_unlock_btn.setText("Đang kiểm tra…")
        QApplication.processEvents()
        ok, msg, cache = validate_pro_license_key(key, "auto_video")
        self._save_license_cache(key, cache)
        if hasattr(self, "_av_license_status"):
            self._av_license_status.setText(msg)
            self._av_license_status.setStyleSheet(
                f"font-size:12px;color:{SUCCESS if ok else DESTRUCTIVE};background:transparent;border:none;"
            )
        self._av_unlock_btn.setEnabled(True)
        self._av_unlock_btn.setText("Kiểm tra key")
        self._av_apply_lock_state()
        self._chat_apply_lock_state()
        if ok:
            self._av_set_status("Đã mở khóa Pro cho Auto Video. Bạn có thể nhập link hoặc paste nội dung để tạo video.")

    def _av_url_field(self):
        self._av_url = QLineEdit()
        self._av_url.setPlaceholderText("https://vnexpress.net/bai-viet...")
        self._av_url.returnPressed.connect(self._av_on_generate)
        return self._av_url

    def _av_text_field(self):
        self._av_text = QTextEdit()
        self._av_text.setPlaceholderText(
            "Paste nội dung bài báo vào đây…\n"
            "AI sẽ tự tóm tắt và tạo script video."
        )
        self._av_text.setFixedHeight(100)
        return self._av_text

    def _av_quick_combo(self, options: list, current: str) -> QComboBox:
        """options: list[str] hoặc list[tuple[str, str]] (label, data)."""
        combo = _ApplePopupCombo()
        combo.setFixedHeight(30)
        combo.setStyleSheet(
            f"QComboBox{{background:{CONTROL_BG};border:none;"
            f"border-radius:8px;padding:3px 8px 3px 10px;font-size:12px;color:{TEXT};}}"
            f"QComboBox:hover{{background:{CONTROL_HV};}}"
            f"QComboBox:focus{{background:{CONTROL_HV};}}"
            "QComboBox QAbstractScrollArea{background:transparent;border:none;}"
            "QComboBox QAbstractItemView{"
            f"background:{SURFACE};color:{TEXT};"
            f"border:1px solid {BORDER};border-radius:10px;"
            "padding:4px;outline:none;}"
            "QComboBox QAbstractItemView::item{min-height:26px;padding:3px 12px;"
            f"color:{TEXT};border-radius:6px;}}"
            f"QComboBox QAbstractItemView::item:selected{{background:{CONTROL_HV};color:{ACCENT};"
            "font-weight:600;}"
        )
        selected = 0
        for i, item in enumerate(options):
            if isinstance(item, tuple):
                label, data = item
                combo.addItem(label, data)
                if data == current:
                    selected = i
            else:
                combo.addItem(item)
                if item == current:
                    selected = i
        combo.setCurrentIndex(selected)
        # Bỏ native checkmark (đẩy text lệch) — dùng highlight màu thay thế
        combo.setItemDelegate(QStyledItemDelegate(combo))
        self._fit_av_combo_to_items(combo, min_width=78)
        return combo

    def _fit_av_combo_to_items(self, combo: QComboBox, min_width: int = 76) -> None:
        """Fit compact Auto Video combos and give the popup enough room for checkmarks."""
        font = combo.font()
        font.setPixelSize(12)
        combo.setFont(font)
        fm = combo.fontMetrics()
        max_w = max(
            (fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())),
            default=min_width,
        )
        control_w = max(min_width, max_w + 56)
        popup_w = max(control_w, max_w + 96)
        combo.setFixedWidth(control_w)
        combo.view().setMinimumWidth(popup_w)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        combo.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _av_quick_choice(self, options: list[tuple[str, str]], current: str) -> QComboBox:
        combo = self._av_quick_combo([label for label, _value in options], "")
        combo.clear()
        selected = 0
        for i, (label, value) in enumerate(options):
            combo.addItem(label, value)
            if value == current:
                selected = i
        combo.setCurrentIndex(selected)
        self._fit_av_combo_to_items(combo, min_width=72)
        return combo

    def _av_save_language(self):
        if not hasattr(self, "_av_lang_combo"):
            return False
        lang = self._av_lang_combo.currentData() or ""
        self.settings["av_language_code"] = lang
        save_settings(self.settings)
        if hasattr(self, "_av_config_lbl"):
            self._av_refresh_config_summary()
        return True

    def _av_save_quick_presets(self):
        if not hasattr(self, "_av_script_preset") or not hasattr(self, "_av_visual_preset"):
            return True
        try:
            caption_state = (
                self._av_sub_toggle.currentData()
                if hasattr(self, "_av_sub_toggle")
                else "off"
            )
            pace = (
                self._av_pace.currentData()
                if hasattr(self, "_av_pace")
                else "dynamic"
            )
            _write_env_local({
                "AUTO_VIDEO_SCRIPT_PRESET": self._av_script_preset.currentData() or "ai_news_fast",
                "AUTO_VIDEO_VISUAL_PRESET": self._av_visual_preset.currentData() or "ai_news_dark",
                "AUTO_VIDEO_BURN_CAPTIONS": "true" if caption_state == "on" else "false",
                "AUTO_VIDEO_EDITING_PACE": pace or "dynamic",
            })
            self._av_refresh_config_summary()
            return True
        except Exception as e:
            self._av_set_status(f"Không lưu được preset nhanh: {e}", error=True)
            return False

    def _av_sync_quick_presets(self):
        if not hasattr(self, "_av_script_preset") or not hasattr(self, "_av_visual_preset"):
            return
        env = _read_env_local()
        caption_on = str(env.get("AUTO_VIDEO_BURN_CAPTIONS", "false")).strip().lower() in ("1", "true", "yes", "on")
        pairs = [
            (self._av_script_preset, env.get("AUTO_VIDEO_SCRIPT_PRESET", "ai_news_fast")),
            (self._av_visual_preset, env.get("AUTO_VIDEO_VISUAL_PRESET", "ai_news_dark")),
        ]
        for combo, value in pairs:
            idx = combo.findData(value)
            if idx >= 0 and idx != combo.currentIndex():
                blocked = combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(blocked)
        if hasattr(self, "_av_sub_toggle"):
            idx = self._av_sub_toggle.findData("on" if caption_on else "off")
            if idx >= 0 and idx != self._av_sub_toggle.currentIndex():
                blocked = self._av_sub_toggle.blockSignals(True)
                self._av_sub_toggle.setCurrentIndex(idx)
                self._av_sub_toggle.blockSignals(blocked)
        if hasattr(self, "_av_pace"):
            idx = self._av_pace.findData(env.get("AUTO_VIDEO_EDITING_PACE", "dynamic"))
            if idx >= 0 and idx != self._av_pace.currentIndex():
                blocked = self._av_pace.blockSignals(True)
                self._av_pace.setCurrentIndex(idx)
                self._av_pace.blockSignals(blocked)

    def _av_on_generate(self):
        if self._av_cancel_current():
            return
        if not is_auto_video_unlocked(self.settings):
            self._av_apply_lock_state()
            self._av_set_status("Auto Video là tính năng Pro. Nhập key hoặc liên hệ mua key để dùng tính năng này.", error=True)
            return

        url  = self._av_url.text().strip()
        text = self._av_text.toPlainText().strip()
        inp  = url or text
        if not inp:
            self._av_set_status("Nhập link hoặc paste nội dung trước.", error=True)
            return

        if not self._av_save_quick_presets():
            return

        # Check có ít nhất 1 API key trong Auto Video config (.env.local), fallback settings cũ.
        env = _read_env_local()
        has_key = any([
            env.get("CLAUDE_API_KEY", "").strip(),
            env.get("DEEPSEEK_API_KEY", "").strip(),
            env.get("GEMINI_API_KEY", "").strip(),
            self.settings.get("claude_api_key", "").strip(),
            self.settings.get("ds_api_key", "").strip(),
            self.settings.get("gemini_api_key", "").strip(),
        ])
        if not has_key:
            self._av_set_status("Chưa có API key — vào Cài đặt → API để thêm key viết script.", error=True)
            return

        self._av_gen_btn.setEnabled(True)
        self._av_gen_btn.setText("Dừng")
        self._av_script_card.setVisible(False)
        self._av_log_buffer.clear()
        self._av_log.clear()
        self._av_log.setVisible(True)
        self._av_step_label.setText("Đang khởi động…")
        self._av_step_label.setVisible(True)
        self._av_prog_row.setVisible(True)
        self._av_progress.setValue(0)
        self._av_pct_label.setText("0%")
        self._av_result_card.setVisible(False)
        perf_log("auto_video_generate_start", input_type="url" if url else "text")

        self._av_script_worker = AutoScriptWorker(inp)
        self._av_script_worker.progress.connect(self._av_set_status)
        self._av_script_worker.finished.connect(self._av_on_script_done)
        self._av_script_worker.error.connect(self._av_on_error)
        self._track_thread("_av_script_worker", self._av_script_worker)

    def _av_cancel_current(self) -> bool:
        workers = [
            getattr(self, "_av_engine_worker", None),
            getattr(self, "_av_script_worker", None),
        ]
        running = [worker for worker in workers if self._is_thread_running(worker)]
        if not running:
            return False
        for worker in running:
            try:
                if hasattr(worker, "cancel"):
                    worker.cancel()
            except Exception:
                pass
            try:
                worker.requestInterruption()
            except Exception:
                pass
        self._av_gen_btn.setEnabled(False)
        self._av_gen_btn.setText("Đang dừng…")
        self._av_set_status("Đang dừng Auto Video…")
        return True

    def _av_on_script_done(self, script_path: str):
        perf_log("auto_video_script_done", script=Path(script_path).name)
        self._av_show_script(script_path)
        self._av_set_status("Script xong — đang render video…")
        self._av_engine_worker = AutoVideoEngineWorker(script_path)
        self._av_engine_worker.log_line.connect(self._av_append_log)
        self._av_engine_worker.progress.connect(self._av_on_progress)
        self._av_engine_worker.finished.connect(self._av_on_video_done)
        self._av_engine_worker.error.connect(self._av_on_error)
        self._track_thread("_av_engine_worker", self._av_engine_worker)

    def _av_on_video_done(self, video_path: str):
        self._av_flush_log_buffer(force=True)
        perf_log("auto_video_done", video=Path(video_path).name if video_path else "")
        self._av_gen_btn.setEnabled(True)
        self._av_gen_btn.setText("Generate Video")
        self._av_on_progress(100)
        self._av_prog_row.setVisible(False)
        self._av_step_label.setVisible(False)
        self._av_set_status("Hoàn thành")
        self._av_video_path = video_path
        self._av_video_path_lbl.setText(video_path or "Không tìm thấy video.mp4")
        self._av_result_card.setVisible(True)

    def _av_on_error(self, msg: str):
        self._av_flush_log_buffer(force=True)
        self._av_gen_btn.setEnabled(True)
        self._av_gen_btn.setText("Generate Video")
        self._av_prog_row.setVisible(False)
        self._av_step_label.setVisible(False)
        cancelled = "Đã dừng" in str(msg) or "Đã huỷ" in str(msg)
        perf_log("auto_video_error", cancelled=cancelled, message=str(msg)[:180])
        self._av_set_status("Đã dừng." if cancelled else msg, error=not cancelled)

    def _av_set_status(self, msg: str, error: bool = False):
        if not error and self._should_throttle_ui("auto_video_status", interval=0.16):
            return
        color = DESTRUCTIVE if error else TEXT_MUTE
        self._av_status.setText(msg)
        self._av_status.setStyleSheet(
            f"color:{color}; font-size:12px; background:transparent;"
        )

    def _av_append_log(self, line: str):
        text = str(line or "").strip()
        if not text:
            return
        self._av_log_buffer.append(text[:1200])
        if not self._av_log_timer.isActive():
            self._av_log_timer.start()
        if time.perf_counter() - self._av_log_last_flush > 0.35:
            self._av_flush_log_buffer()

    def _av_flush_log_buffer(self, force: bool = False):
        if not hasattr(self, "_av_log"):
            return
        if not self._av_log_buffer:
            if force:
                self._av_log_timer.stop()
            return
        if not force and time.perf_counter() - self._av_log_last_flush < 0.22:
            return
        lines = self._av_log_buffer[:60]
        del self._av_log_buffer[:60]
        if lines:
            self._av_log.append("\n".join(lines))
        self._av_log_last_flush = time.perf_counter()
        if force or not self._av_log_buffer:
            self._av_log_timer.stop()
        import re
        m = re.search(r"\[(\d+)/(\d+)\]\s*(.*)", line)
        if m:
            n, t, desc = int(m.group(1)), int(m.group(2)), m.group(3).strip()
            short = desc.split("(")[0].strip()
            self._av_step_label.setText(f"Bước {n}/{t} — {short}")
            self._av_on_progress(int(((n - 1) / t) * 100))
        hf = re.search(r"(\d{1,3})%\s+.*?\bframe\s+(\d+)/(\d+)", line, re.I)
        if hf:
            pct = max(0, min(100, int(hf.group(1))))
            frame = hf.group(2)
            total = hf.group(3)
            overall = int(((6 + pct / 100) / 8) * 100)
            self._av_step_label.setText(
                f"Bước 7/8 — Render with hyperframes ({pct}% · frame {frame}/{total})"
            )
            self._av_set_status(f"Đang render video… {pct}%")
            self._av_on_progress(overall)

    def _av_open_finder(self):
        import subprocess, os
        path = getattr(self, "_av_video_path", "")
        if path:
            folder = os.path.dirname(path)
            subprocess.run(["open", folder], check=False)

    def _av_refresh_config_summary(self):
        env = _read_env_local()
        provider = "elevenlabs"
        voice_key = {
            "elevenlabs": "ELEVENLABS_VOICE_ID",
        }.get(provider, "ELEVENLABS_VOICE_ID")
        voice_id = env.get(voice_key, "")
        voice_hint = voice_id[:8] + "..." if len(voice_id) > 8 else (voice_id or "missing")
        tts_hint = "elevenlabs"
        script_provider = env.get("SCRIPT_AI_PROVIDER", "claude").strip().lower() or "claude"
        script_model = {
            "claude": env.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
            "gemini": env.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash"),
            "deepseek": env.get("DEEPSEEK_SCRIPT_MODEL", "deepseek-v4-flash"),
        }.get(script_provider, "")
        script_hint = script_provider if not script_model else f"{script_provider} {script_model}"
        script_fallback_on = (
            str(env.get("SCRIPT_AI_FALLBACK", "true")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        if script_fallback_on:
            script_hint = f"{script_hint} fallback on"
        script_preset = env.get("AUTO_VIDEO_SCRIPT_PRESET", "ai_news_fast")
        visual_preset = env.get("AUTO_VIDEO_VISUAL_PRESET", "ai_news_dark")
        caption_on = str(env.get("AUTO_VIDEO_BURN_CAPTIONS", "false")).strip().lower() in ("1", "true", "yes", "on")
        caption_mode = env.get("AUTO_VIDEO_CAPTION_MODE", "word_transcript").strip() or "word_transcript"
        caption_style = env.get("AUTO_VIDEO_CAPTION_STYLE", "capcut_pop").strip() or "capcut_pop"
        caption_hint = "Sub off" if (not caption_on or caption_mode == "off") else f"Sub {caption_mode} · {caption_style}"
        pace_hint = env.get("AUTO_VIDEO_EDITING_PACE", "dynamic").strip() or "dynamic"
        self._av_config_lbl.setText(
            f"script {script_hint} · TTS {tts_hint} voice {voice_hint} · {script_preset} · {visual_preset} · Pace {pace_hint} · {caption_hint}"
        )

    def _av_on_progress(self, val: int):
        val = max(0, min(100, int(val)))
        if self._should_throttle_ui("auto_video_progress", value=val, interval=0.12):
            return
        current = self._av_progress.value() if hasattr(self, "_av_progress") else 0
        if val < current and val not in (0, 100):
            return
        self._av_progress.setValue(val)
        self._av_pct_label.setText(f"{val}%")

    def _av_toggle_script(self):
        visible = self._av_script_view.isVisible()
        self._av_script_view.setVisible(not visible)
        self._av_script_toggle.setText("▸ Mở rộng" if visible else "▾ Thu gọn")

    @staticmethod
    def _av_visual_summary_from_voice(voice_text: str, template: str) -> str:
        import re as _re
        clean = _re.sub(r"\[[^\]]+\]", "", voice_text or "")
        clean = _re.sub(r"\s+", " ", clean).strip()
        if not clean:
            return ""
        sentences = [
            s.strip()
            for s in _re.findall(r"[^.!?…]+[.!?…]?", clean)
            if s.strip()
        ] or [clean]

        def trim(text: str, limit: int = 96) -> str:
            text = _re.sub(r"\s+", " ", text).strip()
            if len(text) <= limit:
                return text
            cut = text[:limit].rstrip()
            space = cut.rfind(" ")
            if space >= 30:
                cut = cut[:space].rstrip()
            return cut.rstrip(" ,;:–—-") + "..."

        number = _re.search(
            r"(?:[$]\s*)?\d+(?:[.,]\d+)?\s*(?:%|triệu|tỷ|nghìn|ngàn|USD|đô|sao|người|nhân viên|năm|tuổi|vụ|lần|x|K|M|B)?(?:\s*(?:USD|đô|sao|người|nhân viên|năm|tuổi|vụ|lần))?",
            clean,
            _re.I,
        )
        if template == "stat-hero" and number:
            return trim(f"{number.group(0).strip()} · {sentences[0]}")
        if template == "feature-list":
            return trim(" / ".join(sentences[:3]))
        if template == "comparison":
            return trim(clean)
        if template == "callout":
            risk = next(
                (s for s in sentences if _re.search(r"rủi ro|cảnh báo|nguy|hack|lộ|không|nhưng|tuy nhiên", s, _re.I)),
                sentences[0],
            )
            return trim(risk)
        return trim(sentences[0])

    def _av_show_script(self, script_path: str):
        """Đọc script.json và hiện voiceText + visual summary từng scene."""
        import json as _json
        try:
            with open(script_path, encoding="utf-8") as f:
                data = _json.load(f)
            scenes = data.get("scenes", [])
            lines = []
            for s in scenes:
                sid = s.get("id", "")
                vt  = s.get("voiceText", "").strip()
                td = s.get("templateData", {}) if isinstance(s.get("templateData", {}), dict) else {}
                tpl = td.get("template", "")
                if vt:
                    visual = self._av_visual_summary_from_voice(vt, tpl)
                    lines.append(f"[{sid}] {tpl}\nVoice: {vt}\nVisual sync: {visual}")
            self._av_script_view.setPlainText("\n\n".join(lines))
            self._av_script_toggle.setText("▾ Thu gọn")
            self._av_script_view.setVisible(True)
            self._av_script_card.setVisible(True)
        except Exception:
            pass  # không hiện card nếu lỗi đọc file

    def update_settings(self, settings: dict):
        old_theme = self.settings.get("app_theme", "system")
        current_tab = self.tabs.currentIndex() if hasattr(self, "tabs") else 1
        self.settings = settings
        if self.settings.get("app_theme", "system") != old_theme:
            self._apply_theme()
            self._build(current_tab)
        self._refresh_credits()
        try:
            self._rebuild_style_buttons()
            self._sync_creativity_control(self.settings.get("enhance_style_temperature", 0.3))
            self._sync_voice_combos()
        except Exception:
            pass
        if hasattr(self, "_av_config_lbl"):
            self._av_sync_quick_presets()
            self._av_refresh_config_summary()
