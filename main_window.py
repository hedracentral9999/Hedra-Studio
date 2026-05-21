import os
import sys
import subprocess
import webbrowser
import shlex
import re
import shutil

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QLineEdit, QSlider, QPushButton, QFrame,
    QTabWidget, QScrollArea, QStackedWidget, QFileDialog,
    QMessageBox, QSizePolicy, QSpacerItem, QListWidget,
    QListWidgetItem, QMenu, QGridLayout, QComboBox, QDialog,
    QStyledItemDelegate,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QIcon, QFont, QAction, QPixmap, QColor, QPainter
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from app_constants import (
    VOICE_ID, MODEL, EL_OUTPUT_FORMAT, PROMPTS, PROMPT_TEMPLATES,
    VERSION, DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY, GEMINI_CHAT_PROMPT,
    BG, SURFACE, SURFACE_2, BORDER, BORDER_SOFT, TEXT, TEXT_MUTE, TEXT_FAINT,
    ACCENT, ACCENT_HV, ACCENT_DN, SEG_BG, CONTROL_BG, CONTROL_HV, CONTROL_DN, STYLE,
    SUCCESS, get_creativity_guide, get_style, apply_theme_globals,
)
from app_utils import (
    DATA_DIR, DEFAULT_OUT,
    get_auto_video_env_local, is_auto_video_unlocked, is_chat_script_unlocked, load_settings, reveal_file, save_settings,
    validate_pro_license_key, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)
from app_workers import (
    Worker, _TTSOnlyWorker, PreviewWorker, GeminiWorker,
    UpdateChecker, UpdateDownloader, _CreditsChecker,
    SpeechToTextWorker, words_to_srt,
)
from app_dialogs import AddStyleDialog, FeedbackDialog, DropZone
from app_icons import icon_size, ui_icon
from settings_dialog import SettingsDialog, _read_env_local, _write_env_local
from auto_video_workers import AutoScriptWorker, AutoVideoEngineWorker

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


# ── Main window ────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings      = settings
        self._theme_mode   = self.settings.get("app_theme", "system")
        apply_theme_globals(globals(), self._theme_mode)
        self.worker        = None
        self.gemini_worker = None
        self._managed_threads = set()
        self._closing = False
        self._credits_worker = None
        self._credits_refresh_pending = False
        self.image_paths   = []
        self._parent_ref   = self          # self-ref cho _open_voices_settings
        self._output_audio = QAudioOutput()
        self._output_audio.setVolume(1.0)
        self._output_player = QMediaPlayer()
        self._output_player.setAudioOutput(self._output_audio)
        self._output_player.playbackStateChanged.connect(self._on_output_playback_state)
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
        self._refresh_credits()
        self._check_update()

    def _is_thread_running(self, worker) -> bool:
        if worker is None:
            return False
        try:
            return bool(worker.isRunning())
        except RuntimeError:
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
        brand.setFont(QFont("", 14, QFont.Weight.Bold))
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
        self._page_title.setFont(QFont("", 13, QFont.Weight.Bold))
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

        btn_feedback = toolbar_button("Feedback", "Gửi phản hồi / Báo lỗi", "message")
        btn_feedback.clicked.connect(self._open_feedback)
        toolbar_row.addWidget(btn_feedback)

        self._btn_check_update = toolbar_button("Update", "Kiểm tra và tải bản mới nhất", "download")
        self._btn_check_update.clicked.connect(self._manual_check_update)
        toolbar_row.addWidget(self._btn_check_update)

        btn_settings = toolbar_button("Settings", "Mở cài đặt", "settings")
        btn_settings.clicked.connect(self.open_settings)
        toolbar_row.addWidget(btn_settings)
        layout.addWidget(toolbar)

        self.update_banner = QFrame()
        self.update_banner.setVisible(False)
        self.update_banner.setStyleSheet(
            "QFrame{background:#f0f7ff;border:none;border-bottom:1px solid #bfdbfe;}"
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
        self._banner_text.setStyleSheet("color:#004499;font-size:12px;background:transparent;border:none;")
        self._btn_dl = QPushButton("Cập nhật ngay")
        self._btn_dl.setFixedHeight(28)
        self._btn_dl.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;"
            f"border-radius:8px;padding:0 14px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            f"QPushButton:disabled{{background:#a8d0fb;color:white;}}"
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

    def _sync_main_nav(self, idx: int):
        titles = ["Chat → Kịch Bản", "TTS", "STT", "Auto Video"]
        if hasattr(self, "_page_title") and 0 <= idx < len(titles):
            self._page_title.setText(titles[idx])
        for i, btn in enumerate(getattr(self, "_main_nav_btns", [])):
            btn.setChecked(i == idx)

    def _student_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setStyleSheet(f"QWidget{{background:{SURFACE};}}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 16, 32, 22)
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
            "QPushButton:disabled{background:#a8d0fb;color:white;}"
        )

    def _compact_secondary_style(self) -> str:
        return (
            f"QPushButton{{background:{CONTROL_BG};color:{TEXT};border:1px solid {BORDER_SOFT};"
            "border-radius:9px;font-size:13px;font-weight:500;padding:0 14px;min-height:32px;}"
            f"QPushButton:hover{{background:{CONTROL_HV};}}"
            f"QPushButton:pressed{{background:{CONTROL_DN};}}"
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
        # Scroll wrapper — nội dung không bao giờ bị cắt
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{BG};border:none;}}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

        w = QWidget()
        w.setStyleSheet(f"background:{BG};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 24)
        layout.setSpacing(0)

        # ══ Section 1: Kịch bản (content chính — không cần card, nổi bật) ═══
        # Header row: label + nút "Xem kịch bản"
        sec1_row = QWidget()
        sec1_row.setStyleSheet("background:transparent;border:none;")
        sec1_lay = QHBoxLayout(sec1_row)
        sec1_lay.setContentsMargins(0, 12, 0, 4)
        sec1_lay.setSpacing(8)
        sec1_lay.addWidget(self._section_lbl("KỊCH BẢN"))
        sec1_lay.addStretch()

        self._btn_preview = QPushButton("✨  Xem kịch bản")
        self._btn_preview.setFixedHeight(30)
        self._btn_preview.setStyleSheet(
            f"QPushButton{{background:#f0f6ff;color:{ACCENT};"
            "border:1px solid #c5d9f8;border-radius:8px;"
            "font-size:12px;font-weight:600;padding:0 14px;}"
            f"QPushButton:hover{{background:#dce9fd;border-color:{ACCENT};}}"
            "QPushButton:pressed{background:#cfe0fc;}"
            "QPushButton:disabled{background:#f5f5f7;color:#aeaeb2;border-color:#e5e5ea;}"
        )
        self._btn_preview.clicked.connect(self._do_preview)
        sec1_lay.addWidget(self._btn_preview)
        layout.addWidget(sec1_row)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Paste kịch bản vào đây...")
        self.text_input.setMinimumHeight(210)
        self.text_input.setStyleSheet(
            f"QTextEdit{{border:1px solid #e5e5ea;border-radius:10px;"
            f"background:{SURFACE};color:{TEXT};padding:12px 14px;"
            f"font-size:14px;}}"
            f"QTextEdit:focus{{border:1px solid {ACCENT};}}"
        )
        # Khi user sửa kịch bản gốc → xóa preview cũ (tránh gen sai)
        self.text_input.textChanged.connect(self._on_script_changed)
        layout.addWidget(self.text_input)

        # ── Kết quả preview (ẩn lúc đầu) ────────────────────────────
        self._preview_box = QWidget()
        self._preview_box.setStyleSheet("background:transparent;border:none;")
        self._preview_box.setVisible(False)
        pv_lay = QVBoxLayout(self._preview_box)
        pv_lay.setContentsMargins(0, 8, 0, 0)
        pv_lay.setSpacing(4)

        pv_header = QWidget()
        pv_header.setStyleSheet("background:transparent;border:none;")
        pv_h = QHBoxLayout(pv_header)
        pv_h.setContentsMargins(0, 0, 0, 0)
        pv_h.setSpacing(8)
        pv_lbl = QLabel("KẾT QUẢ SAU KHI XỬ LÝ")
        pv_lbl.setStyleSheet(
            "font-size:11px;font-weight:700;letter-spacing:0.8px;"
            "color:#6e6e73;background:transparent;border:none;"
        )
        pv_h.addWidget(pv_lbl)
        pv_h.addStretch()
        pv_note = QLabel("Có thể chỉnh sửa trước khi gen giọng")
        pv_note.setStyleSheet("font-size:11px;color:#aeaeb2;background:transparent;border:none;")
        pv_h.addWidget(pv_note)
        pv_lay.addWidget(pv_header)

        self.preview_text = QTextEdit()
        self.preview_text.setPlaceholderText("Nhấn \"✨ Xem kịch bản\" để xem kịch bản sau khi AI xử lý...")
        self.preview_text.setMinimumHeight(160)
        self.preview_text.setStyleSheet(
            "QTextEdit{border:1px solid #c5d9f8;border-radius:10px;"
            "background:#f0f6ff;color:#1d1d1f;padding:12px 14px;font-size:13px;}"
            f"QTextEdit:focus{{border:1px solid {ACCENT};}}"
        )
        pv_lay.addWidget(self.preview_text)

        self._preview_status = QLabel("")
        self._preview_status.setStyleSheet(
            "font-size:11px;color:#6e6e73;background:transparent;border:none;"
        )
        self._preview_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pv_lay.addWidget(self._preview_status)

        layout.addWidget(self._preview_box)
        self._enhanced_cache = ""   # lưu text đã enhance để Worker dùng lại

        # ══ Section 2: Phong cách & Giọng — grouped card ═════════════════
        layout.addWidget(self._section_lbl("PHONG CÁCH & GIỌNG"))
        card1, c1 = self._card()

        # — Style row: segmented + nút + nằm dưới
        seg_frame = QFrame()
        seg_frame.setFixedHeight(36)
        seg_frame.setStyleSheet(
            f"QFrame{{background:{SEG_BG};border-radius:8px;border:none;}}"
        )
        seg_layout = QHBoxLayout(seg_frame)
        seg_layout.setContentsMargins(4, 4, 4, 4)
        seg_layout.setSpacing(2)

        self._prompt_btns: dict[str, QPushButton] = {}
        self._seg_layout = seg_layout
        self._seg_frame  = seg_frame

        current_prompt = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
        active_name = self._find_active_style_name(current_prompt)
        self._build_style_buttons(seg_layout, active_name)

        btn_add_style = QPushButton("+")
        btn_add_style.setFixedHeight(30)
        btn_add_style.setToolTip("Thêm phong cách tùy chỉnh")
        btn_add_style.setStyleSheet(
            f"QPushButton{{font-size:13px;font-weight:500;color:#0071e3;"
            f"background:transparent;border:none;border-radius:9px;padding:6px 10px;}}"
            "QPushButton:hover{background:#dfeeff;}"
            "QPushButton:pressed{background:#cfe3ff;}"
        )
        btn_add_style.clicked.connect(self._quick_add_style)

        style_w = QWidget()
        style_w.setStyleSheet("background:transparent;border:none;")
        sw = QHBoxLayout(style_w)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(6)
        sw.addWidget(seg_frame)
        sw.addWidget(btn_add_style)
        sw.addStretch()
        self._card_row(c1, "Phong cách", style_w)

        # — Row: Giọng đọc (voice name + language pill-dropdown + đổi giọng — 1 hàng)
        # Full ElevenLabs language list — top picks + separator + alphabetical
        _lang_top = [
            ("Tự động",       ""),
            ("Tiếng Việt",    "vi"),
            ("Tiếng Anh",     "en"),
            ("Tiếng Trung",   "zh"),
            ("Tiếng Nhật",    "ja"),
            ("Tiếng Hàn",     "ko"),
        ]
        _lang_rest = [
            ("Tiếng Ả Rập",      "ar"),
            ("Tiếng Bungari",     "bg"),
            ("Tiếng Croatia",     "hr"),
            ("Tiếng Séc",         "cs"),
            ("Tiếng Đan Mạch",    "da"),
            ("Tiếng Hà Lan",      "nl"),
            ("Tiếng Philippines", "fil"),
            ("Tiếng Phần Lan",    "fi"),
            ("Tiếng Pháp",        "fr"),
            ("Tiếng Đức",         "de"),
            ("Tiếng Hy Lạp",      "el"),
            ("Tiếng Hindi",       "hi"),
            ("Tiếng Hungary",     "hu"),
            ("Tiếng Indonesia",   "id"),
            ("Tiếng Ý",           "it"),
            ("Tiếng Mã Lai",      "ms"),
            ("Tiếng Na Uy",       "no"),
            ("Tiếng Ba Lan",      "pl"),
            ("Tiếng Bồ Đào Nha", "pt"),
            ("Tiếng Romania",     "ro"),
            ("Tiếng Nga",         "ru"),
            ("Tiếng Slovak",      "sk"),
            ("Tiếng Tây Ban Nha", "es"),
            ("Tiếng Thụy Điển",   "sv"),
            ("Tiếng Tamil",       "ta"),
            ("Tiếng Thổ Nhĩ Kỳ", "tr"),
            ("Tiếng Ukraine",     "uk"),
        ]
        _lang_options = _lang_top + _lang_rest

        _saved_lang = self.settings.get("tts_language_code", "")
        self._lang_code = _saved_lang
        _lang_map = {code: lbl for lbl, code in _lang_options}

        def _lang_btn_style(active: bool) -> str:
            # height = 28px → border-radius = 14px (= height/2) để pill đúng
            if active:
                return (
                    f"QPushButton{{background:{CONTROL_HV};color:{ACCENT};"
                    f"border:1px solid {ACCENT};border-radius:14px;"
                    "min-height:28px;padding:0 10px 0 12px;"
                    "font-size:12px;font-weight:600;}"
                    f"QPushButton:hover{{background:{CONTROL_DN};}}"
                    f"QPushButton:pressed{{background:{CONTROL_DN};}}"
                )
            return (
                f"QPushButton{{background:{CONTROL_BG};color:{TEXT};"
                "border:none;border-radius:14px;"
                "min-height:28px;padding:0 10px 0 12px;"
                "font-size:12px;font-weight:500;}"
                f"QPushButton:hover{{background:{CONTROL_HV};}}"
                f"QPushButton:pressed{{background:{CONTROL_DN};}}"
            )

        # Pill dropdown button — hiển thị lựa chọn hiện tại + chevron
        _init_label = _lang_map.get(_saved_lang, "Tự động") + "  ▾"
        self._lang_btn = QPushButton(_init_label)
        self._lang_btn.setFixedHeight(28)
        self._lang_btn.setStyleSheet(_lang_btn_style(_saved_lang != ""))
        self._lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _show_lang_menu():
            menu = QMenu(self._lang_btn)
            menu.setStyleSheet(
                f"QMenu{{background:{SURFACE};border:1px solid {BORDER};"
                "border-radius:10px;padding:4px 0;}"
                f"QMenu::item{{padding:7px 20px;font-size:13px;color:{TEXT};}}"
                f"QMenu::item:selected{{background:{CONTROL_HV};color:{ACCENT};}}"
                f"QMenu::item:checked{{font-weight:600;color:{ACCENT};}}"
                f"QMenu::separator{{height:1px;background:{BORDER_SOFT};margin:3px 0;}}"
            )
            # Top picks
            for lbl, code in _lang_top:
                action = QAction(lbl, menu)
                action.setCheckable(True)
                action.setChecked(self._lang_code == code)
                def _pick(checked, c=code, l=lbl):
                    self._lang_code = c
                    self._lang_btn.setText(l + "  ▾")
                    self._lang_btn.setStyleSheet(_lang_btn_style(c != ""))
                    self.settings["tts_language_code"] = c
                    save_settings(self.settings)
                action.triggered.connect(_pick)
                menu.addAction(action)
            # Separator → phần còn lại
            menu.addSeparator()
            for lbl, code in _lang_rest:
                action = QAction(lbl, menu)
                action.setCheckable(True)
                action.setChecked(self._lang_code == code)
                def _pick(checked, c=code, l=lbl):
                    self._lang_code = c
                    self._lang_btn.setText(l + "  ▾")
                    self._lang_btn.setStyleSheet(_lang_btn_style(c != ""))
                    self.settings["tts_language_code"] = c
                    save_settings(self.settings)
                action.triggered.connect(_pick)
                menu.addAction(action)
            # Separator + reset
            menu.addSeparator()
            reset = QAction("↺  Về Tự động", menu)
            def _reset():
                self._lang_code = ""
                self._lang_btn.setText("Tự động  ▾")
                self._lang_btn.setStyleSheet(_lang_btn_style(False))
                self.settings["tts_language_code"] = ""
                save_settings(self.settings)
            reset.triggered.connect(_reset)
            menu.addAction(reset)
            menu.exec(self._lang_btn.mapToGlobal(
                self._lang_btn.rect().bottomLeft()
            ))

        self._lang_btn.clicked.connect(_show_lang_menu)

        # Layout 1 hàng: voice name | lang dropdown | stretch | đổi giọng
        voice_w = QWidget()
        voice_w.setStyleSheet("background:transparent;border:none;")
        vw = QHBoxLayout(voice_w)
        vw.setContentsMargins(0, 0, 0, 0)
        vw.setSpacing(10)

        self._voice_name_lbl = QLabel(self.settings.get("selected_voice_name", "Adam"))
        self._voice_name_lbl.setStyleSheet(
            f"color:{TEXT};font-size:13px;background:transparent;border:none;"
        )
        btn_change_voice = QPushButton("Thiết lập")
        btn_change_voice.setFixedHeight(28)
        btn_change_voice.setMinimumWidth(82)
        btn_change_voice.setStyleSheet(
            f"QPushButton{{font-size:12px;color:{ACCENT};background:{CONTROL_BG};"
            f"border:1px solid {BORDER_SOFT};border-radius:8px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{CONTROL_HV};}}"
            f"QPushButton:pressed{{background:{CONTROL_DN};}}"
        )
        btn_change_voice.clicked.connect(self._open_voices_settings)

        vw.addWidget(self._voice_name_lbl)
        vw.addWidget(self._lang_btn)
        vw.addStretch()
        vw.addWidget(btn_change_voice)

        self._card_row(c1, "Giọng đọc", voice_w, last=True)

        layout.addWidget(card1)

        # ══ Section 3: Cài đặt — grouped card ════════════════════════════
        layout.addWidget(self._section_lbl("CÀI ĐẶT"))
        card2, c2 = self._card()

        # — Row: Tốc độ
        spd_w = QWidget()
        spd_w.setStyleSheet("background:transparent;border:none;")
        spd_lay = QHBoxLayout(spd_w)
        spd_lay.setContentsMargins(0, 0, 0, 0)
        spd_lay.setSpacing(10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(7); self.slider.setMaximum(12)
        default_speed = self.settings.get("default_speed", 1.0)
        self.slider.setValue(int(default_speed * 10))

        self.speed_val = QLabel("1.0×")
        self.speed_val.setFixedWidth(36)
        self.speed_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.speed_val.setStyleSheet(
            f"color:{ACCENT}; font-weight:600; font-size:13px; background:transparent;"
        )
        self.slider.valueChanged.connect(lambda v: self.speed_val.setText(f"{v/10:.1f}×"))

        spd_lay.addWidget(self.slider, 1)
        spd_lay.addWidget(self.speed_val)
        self._card_row(c2, "Tốc độ đọc", spd_w)

        # — Row: Mức độ sáng tạo (sync với Settings → Prompts → TTS)
        creative_w = QWidget()
        creative_w.setStyleSheet("background:transparent;border:none;")
        creative_lay = QHBoxLayout(creative_w)
        creative_lay.setContentsMargins(0, 0, 0, 0)
        creative_lay.setSpacing(10)

        self.creativity_slider = QSlider(Qt.Orientation.Horizontal)
        self.creativity_slider.setRange(0, 100)
        _cur_temp = self.settings.get("enhance_style_temperature", 0.3)
        self.creativity_slider.setValue(int(_cur_temp * 100))
        creative_lay.addWidget(self.creativity_slider, 1)

        self.creativity_val = QLabel(f"{_cur_temp:.2f}")
        self.creativity_val.setFixedWidth(36)
        self.creativity_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.creativity_val.setStyleSheet(
            f"color:{ACCENT}; font-weight:600; font-size:13px; background:transparent;"
        )
        creative_lay.addWidget(self.creativity_val)

        # Label hiển thị tên mức độ (Khóa / Tiết chế / Tự do)
        self.creativity_tier = QLabel(self._tier_label(_cur_temp))
        self.creativity_tier.setFixedWidth(82)
        self.creativity_tier.setStyleSheet(
            "font-size:12px;font-weight:600;color:#6e6e73;background:transparent;"
        )
        creative_lay.addWidget(self.creativity_tier)

        def _on_creativity_changed(value: int):
            t = value / 100.0
            self.creativity_val.setText(f"{t:.2f}")
            self.creativity_tier.setText(self._tier_label(t))
            if hasattr(self, "_creativity_detail"):
                self._creativity_detail.setText(self._creativity_detail_text(t))
            self.settings["enhance_style_temperature"] = t
            self.settings["enhance_style_creative"] = t >= 0.5

        self.creativity_slider.valueChanged.connect(_on_creativity_changed)
        self._card_row(c2, "Mức độ sáng tạo", creative_w)

        # ── Label giải thích công thức sáng tạo ─
        self._creativity_detail = QLabel(self._creativity_detail_text(_cur_temp))
        self._creativity_detail.setWordWrap(True)
        self._creativity_detail.setStyleSheet(
            f"color:{TEXT_MUTE};font-size:11px;background:transparent;padding:2px 16px 0 16px;"
        )
        layout.addWidget(self._creativity_detail)

        # — Row: Tên file
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("box_650k_quang_cao")
        self.filename_input.setStyleSheet(
            f"QLineEdit{{background:{BG};border:1px solid {BORDER};"
            "border-radius:6px;padding:5px 9px;font-size:13px;}"
            f"QLineEdit:focus{{border-color:{ACCENT};background:{SURFACE};}}"
        )
        self._card_row(c2, "Tên file", self.filename_input, last=True)

        layout.addWidget(card2)

        # ══ Generate button — primary CTA ════════════════════════════════
        layout.addSpacing(20)
        self.btn_gen = QPushButton("🎙   Tạo Giọng Đọc")
        self.btn_gen.setMinimumHeight(50)
        self.btn_gen.setFont(QFont("", 15, QFont.Weight.Bold))
        self.btn_gen.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;"
            "border-radius:12px;border:none;}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            "QPushButton:pressed{background:#005bb5;}"
            "QPushButton:disabled{background:#a8d0fb;color:white;}"
        )
        self.btn_gen.clicked.connect(self._generate)
        layout.addWidget(self.btn_gen)
        layout.addSpacing(8)

        # Status row
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.tts_status_lbl = QLabel("Sẵn sàng")
        self.tts_status_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; background:transparent;"
        )
        self.tts_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_row.addWidget(self.tts_status_lbl, 1)

        self._btn_play_audio = QPushButton("Phát")
        self._btn_play_audio.setFixedSize(64, 30)
        self._btn_play_audio.setToolTip("Nghe file vừa tạo")
        self._btn_play_audio.setVisible(False)
        self._btn_play_audio.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:6px;"
            f"background:{SURFACE};color:{TEXT};font-size:12px;font-weight:600;}}"
            "QPushButton:hover{background:#ebebf0;}"
            "QPushButton:pressed{background:#d8d8de;}"
        )
        self._btn_play_audio.clicked.connect(self._toggle_last_audio)
        status_row.addWidget(self._btn_play_audio)

        self._btn_open_folder = QPushButton("Mở file")
        self._btn_open_folder.setFixedSize(76, 30)
        self._btn_open_folder.setToolTip("Mở file audio vừa tạo")
        self._btn_open_folder.setVisible(False)
        self._btn_open_folder.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:6px;"
            f"background:{SURFACE};color:{TEXT};font-size:12px;font-weight:600;}}"
            "QPushButton:hover{background:#ebebf0;}"
            "QPushButton:pressed{background:#d8d8de;}"
        )
        status_row.addWidget(self._btn_open_folder)
        layout.addLayout(status_row)
        self._last_audio_path = ""

        layout.addStretch()
        scroll.setWidget(w)
        outer_lay.addWidget(scroll)
        return outer

    def _build_tts_tab(self) -> QWidget:
        page, layout = self._student_page()

        strip, strip_lay = self._strip_widget()
        style_lbl = QLabel("Phong cách")
        style_lbl.setStyleSheet(f"font-size:12px;font-weight:600;color:{TEXT};background:transparent;border:none;")
        strip_lay.addWidget(style_lbl)

        active_name = self._find_active_style_name(self.settings.get("enhance_prompt", DEFAULT_PROMPT))
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

        strip_lay.addSpacing(6)
        self._btn_preview = QPushButton("Xem kịch bản")
        self._btn_preview.setFixedHeight(30)
        self._btn_preview.setStyleSheet(self._compact_secondary_style())
        self._btn_preview.clicked.connect(self._do_preview)
        strip_lay.addWidget(self._btn_preview)

        self.btn_gen = QPushButton("Tạo audio")
        self.btn_gen.setFixedHeight(30)
        self.btn_gen.setStyleSheet(self._compact_primary_style())
        self.btn_gen.clicked.connect(self._generate)
        strip_lay.addWidget(self.btn_gen)
        layout.addWidget(strip)

        body = QWidget()
        body.setStyleSheet("background:transparent;border:none;")
        body_h = QHBoxLayout(body)
        body_h.setContentsMargins(0, 0, 0, 0)
        body_h.setSpacing(18)

        left = QWidget()
        left.setStyleSheet("background:transparent;border:none;")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(8)
        left_l.addWidget(self._pane_heading("Kịch bản", "Paste hoặc chỉnh nội dung trước khi tạo giọng."))
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Paste kịch bản vào đây...")
        self.text_input.setStyleSheet(self._editor_style())
        self.text_input.textChanged.connect(self._on_script_changed)
        left_l.addWidget(self.text_input, 1)

        self._preview_box = QWidget()
        self._preview_box.setVisible(False)
        self._preview_box.setStyleSheet(f"QWidget{{background:{CONTROL_BG};border:none;border-radius:10px;}}")
        pv_lay = QVBoxLayout(self._preview_box)
        pv_lay.setContentsMargins(12, 10, 12, 12)
        pv_lay.setSpacing(6)
        pv_lay.addWidget(self._pane_heading("Bản đã xử lý", "Có thể chỉnh trước khi tạo audio."))
        self.preview_text = QTextEdit()
        self.preview_text.setPlaceholderText("Bản sau khi AI xử lý sẽ hiện ở đây...")
        self.preview_text.setMinimumHeight(130)
        self.preview_text.setStyleSheet(self._editor_style(True))
        pv_lay.addWidget(self.preview_text)
        self._preview_status = QLabel("")
        self._preview_status.setStyleSheet(f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;")
        pv_lay.addWidget(self._preview_status)
        left_l.addWidget(self._preview_box)
        self._enhanced_cache = ""
        body_h.addWidget(left, 7)

        body_h.addWidget(self._v_divider())

        right = QWidget()
        right.setStyleSheet("background:transparent;border:none;")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(12)
        right_l.addWidget(self._pane_heading("Audio", "Tạo file đọc và nghe lại ngay trong app."))

        self.tts_status_lbl = QLabel("Chưa có audio")
        self.tts_status_lbl.setStyleSheet(f"color:{TEXT_MUTE};font-size:12px;background:transparent;border:none;")

        audio_panel = QWidget()
        audio_panel.setObjectName("audioPanel")
        audio_panel.setStyleSheet(f"#audioPanel{{background:transparent;border:1px solid {BORDER_SOFT};border-radius:12px;}}")
        audio_panel_l = QVBoxLayout(audio_panel)
        audio_panel_l.setContentsMargins(16, 16, 16, 14)
        audio_panel_l.setSpacing(10)
        audio_panel_l.addStretch()

        self._audio_icon_lbl = QLabel()
        self._audio_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._audio_icon_lbl.setPixmap(ui_icon("audio", 34, TEXT_FAINT).pixmap(icon_size(34)))
        self._audio_icon_lbl.setStyleSheet("background:transparent;border:none;")
        audio_panel_l.addWidget(self._audio_icon_lbl)

        self._audio_title_lbl = QLabel("Chưa có audio")
        self._audio_title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._audio_title_lbl.setStyleSheet(f"font-size:22px;font-weight:700;color:{TEXT_FAINT};background:transparent;border:none;")
        audio_panel_l.addWidget(self._audio_title_lbl)

        self._audio_detail_lbl = QLabel("Nhập kịch bản rồi nhấn Tạo audio.")
        self._audio_detail_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._audio_detail_lbl.setWordWrap(True)
        self._audio_detail_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        audio_panel_l.addWidget(self._audio_detail_lbl)
        audio_panel_l.addStretch()

        player_bar = QWidget()
        player_bar.setObjectName("audioPlayerBar")
        player_bar.setStyleSheet(f"#audioPlayerBar{{background:{CONTROL_BG};border:none;border-radius:10px;}}")
        player_l = QHBoxLayout(player_bar)
        player_l.setContentsMargins(10, 8, 10, 8)
        player_l.setSpacing(8)
        player_l.addWidget(self.tts_status_lbl, 1)

        self._btn_play_audio = QPushButton("Nghe lại")
        self._btn_play_audio.setFixedHeight(32)
        self._btn_play_audio.setEnabled(False)
        self._btn_play_audio.setStyleSheet(self._compact_secondary_style())
        self._btn_play_audio.clicked.connect(self._toggle_last_audio)
        player_l.addWidget(self._btn_play_audio)

        self._btn_open_folder = QPushButton("Mở trong Finder")
        self._btn_open_folder.setFixedHeight(32)
        self._btn_open_folder.setEnabled(False)
        self._btn_open_folder.setStyleSheet(self._compact_secondary_style())
        player_l.addWidget(self._btn_open_folder)

        self._btn_export_srt = QPushButton("Xuất SRT")
        self._btn_export_srt.setFixedHeight(32)
        self._btn_export_srt.setEnabled(False)
        self._btn_export_srt.setToolTip("Lưu file phụ đề .srt đi kèm audio")
        self._btn_export_srt.setStyleSheet(self._compact_secondary_style())
        self._btn_export_srt.clicked.connect(self._export_tts_srt)
        player_l.addWidget(self._btn_export_srt)
        audio_panel_l.addWidget(player_bar)

        right_l.addWidget(audio_panel, 1)

        settings_box = QWidget()
        settings_box.setStyleSheet(f"QWidget{{background:{CONTROL_BG};border:none;border-radius:10px;}}")
        sb = QVBoxLayout(settings_box)
        sb.setContentsMargins(12, 10, 12, 12)
        sb.setSpacing(8)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(8)
        speed_row.addWidget(QLabel("Tốc độ"))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(7)
        self.slider.setMaximum(12)
        self.slider.setValue(int(self.settings.get("default_speed", 1.0) * 10))
        speed_row.addWidget(self.slider, 1)
        self.speed_val = QLabel(f"{self.slider.value()/10:.1f}×")
        self.speed_val.setFixedWidth(36)
        self.speed_val.setStyleSheet(f"color:{ACCENT};font-weight:700;background:transparent;border:none;")
        self.slider.valueChanged.connect(lambda v: self.speed_val.setText(f"{v/10:.1f}×"))
        speed_row.addWidget(self.speed_val)
        sb.addLayout(speed_row)

        creative_row = QHBoxLayout()
        creative_row.setSpacing(8)
        creative_row.addWidget(QLabel("Sáng tạo"))
        self.creativity_slider = QSlider(Qt.Orientation.Horizontal)
        self.creativity_slider.setRange(0, 100)
        cur_temp = self.settings.get("enhance_style_temperature", 0.3)
        self.creativity_slider.setValue(int(cur_temp * 100))
        creative_row.addWidget(self.creativity_slider, 1)
        self.creativity_val = QLabel(f"{cur_temp:.2f}")
        self.creativity_val.setFixedWidth(36)
        self.creativity_val.setStyleSheet(f"color:{ACCENT};font-weight:700;background:transparent;border:none;")
        creative_row.addWidget(self.creativity_val)
        self.creativity_tier = QLabel(self._tier_label(cur_temp))
        self.creativity_tier.setStyleSheet(f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;")
        creative_row.addWidget(self.creativity_tier)
        sb.addLayout(creative_row)

        self._creativity_detail = QLabel(self._creativity_detail_text(cur_temp))
        self._creativity_detail.setWordWrap(True)
        self._creativity_detail.setStyleSheet(f"font-size:11px;color:{TEXT_MUTE};background:transparent;border:none;")
        sb.addWidget(self._creativity_detail)

        def _on_creativity_changed(value: int):
            t = value / 100.0
            self.creativity_val.setText(f"{t:.2f}")
            self.creativity_tier.setText(self._tier_label(t))
            self._creativity_detail.setText(self._creativity_detail_text(t))
            self.settings["enhance_style_temperature"] = t
            self.settings["enhance_style_creative"] = t >= 0.5
        self.creativity_slider.valueChanged.connect(_on_creativity_changed)

        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("box_650k_quang_cao")
        sb.addWidget(self.filename_input)
        right_l.addWidget(settings_box)
        self._last_audio_path = ""
        self._last_srt_path = ""

        body_h.addWidget(right, 5)
        layout.addWidget(body, 1)
        return page

    # ── Tab 3: Speech-to-Text ────────────────────────────────────
    def _build_stt_tab(self) -> QWidget:
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{BG};border:none;}}"
        )

        w = QWidget()
        w.setStyleSheet(f"background:{BG};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 24)
        layout.setSpacing(0)

        # ═══ Drop zone / Chọn file ═══
        layout.addWidget(self._section_lbl("FILE AUDIO"))
        self._stt_drop = DropZone(
            label="🎧  Kéo thả file audio vào đây",
            dialog_title="Chọn file audio",
            file_filter="Audio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.webm)",
            extensions=(".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm"),
        )
        self._stt_drop.files_added.connect(self._stt_file_selected)
        self._stt_drop.setStyleSheet(
            "QFrame{border:1px dashed #c7c7cc;border-radius:10px;background:#ffffff;}"
            "QFrame:hover{border-color:#0071e3;}"
        )
        layout.addWidget(self._stt_drop)

        self._stt_file_lbl = QLabel("Chưa chọn file — kéo thả MP3/WAV vào đây")
        self._stt_file_lbl.setStyleSheet(
            f"color:{TEXT_MUTE};font-size:12px;background:transparent;padding:6px 0;"
        )
        layout.addWidget(self._stt_file_lbl)
        self._stt_path = ""

        layout.addSpacing(12)
        self._stt_btn = QPushButton("🎤  Nhận diện giọng nói")
        self._stt_btn.setMinimumHeight(46)
        self._stt_btn.setFont(QFont("", 14, QFont.Weight.Bold))
        self._stt_btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border-radius:10px;border:none;}}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            f"QPushButton:pressed{{background:#005bb5;}}"
            "QPushButton:disabled{background:#a8d0fb;color:white;}"
        )
        self._stt_btn.clicked.connect(self._do_stt)
        layout.addWidget(self._stt_btn)

        self._stt_status = QLabel("")
        self._stt_status.setStyleSheet(
            f"color:{TEXT_MUTE};font-size:11px;background:transparent;padding:4px 0;"
        )
        self._stt_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._stt_status)

        # ═══ Kết quả ═══
        layout.addWidget(self._section_lbl("KẾT QUẢ"))
        self._stt_text = QTextEdit()
        self._stt_text.setPlaceholderText("Nội dung nhận diện sẽ hiện ở đây...")
        self._stt_text.setMinimumHeight(160)
        self._stt_text.setStyleSheet(
            f"QTextEdit{{border:1px solid #e5e5ea;border-radius:10px;"
            f"background:{SURFACE};color:{TEXT};padding:12px 14px;font-size:14px;}}"
        )
        layout.addWidget(self._stt_text)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._stt_export_btn = QPushButton("📥  Xuất SRT")
        self._stt_export_btn.setFixedHeight(32)
        self._stt_export_btn.setStyleSheet(
            f"QPushButton{{background:#f0f6ff;color:{ACCENT};border:1px solid #c5d9f8;"
            "border-radius:8px;padding:0 16px;font-size:13px;font-weight:600;}"
            f"QPushButton:hover{{background:#dbeafe;}}"
            "QPushButton:disabled{background:#f5f5f7;color:#aeaeb2;border-color:#e5e5ea;}"
        )
        self._stt_export_btn.clicked.connect(self._export_srt)
        self._stt_export_btn.setVisible(False)
        btn_row.addWidget(self._stt_export_btn)
        layout.addLayout(btn_row)
        self._stt_words = []

        layout.addStretch()
        scroll.setWidget(w)
        outer_lay.addWidget(scroll)
        return outer

    def _build_stt_tab(self) -> QWidget:
        page, layout = self._student_page()
        body = QWidget()
        body.setStyleSheet("background:transparent;border:none;")
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)

        left = QWidget()
        left.setStyleSheet("background:transparent;border:none;")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
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
            f"QFrame:hover{{border-color:{ACCENT};background:#f7fbff;}}"
        )
        left_l.addWidget(self._stt_drop)
        self._stt_file_lbl = QLabel("Chưa chọn file")
        self._stt_file_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        left_l.addWidget(self._stt_file_lbl)
        self._stt_path = ""
        left_l.addStretch()
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
        h.addWidget(left, 5)

        h.addWidget(self._v_divider())

        right = QWidget()
        right.setStyleSheet("background:transparent;border:none;")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
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
        gm_key = self.settings.get("genmax_api_key", "").strip()
        gemini_key = self.settings.get("gemini_api_key", "").strip()
        if not gm_key and not gemini_key:
            QMessageBox.warning(
                self,
                "Thiếu STT API Key",
                "Cần GenMax hoặc Gemini API Key để dùng Speech-to-Text.\n"
                "Vào Settings → API để thêm.",
            )
            return
        self._stt_btn.setEnabled(False)
        self._stt_status.setText("Đang nhận diện...")
        self._stt_worker = SpeechToTextWorker(self._stt_path, gm_key, gemini_key, self.settings)
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
        # Scroll wrapper
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{BG};border:none;}}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

        w = QWidget()
        w.setStyleSheet(f"background:{BG};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 24)
        layout.setSpacing(0)

        # ══ Section 1: Ảnh chat — card với drop zone bên trong ═══════════
        layout.addWidget(self._section_lbl("ẢNH CHAT"))
        img_card, img_c = self._card()

        img_inner = QWidget()
        img_inner.setStyleSheet("background:transparent;border:none;")
        img_in_lay = QVBoxLayout(img_inner)
        img_in_lay.setContentsMargins(12, 12, 12, 12)
        img_in_lay.setSpacing(8)

        # Drop zone — bên trong card
        self.drop_zone = DropZone()
        self.drop_zone.files_added.connect(self._add_images)
        # Override style để hoà vào card
        self.drop_zone.setStyleSheet(
            "QFrame{border:1px dashed #c7c7cc;border-radius:8px;"
            "background:#f9f9fb;}"
            "QFrame:hover{border-color:#0071e3;background:#f0f7ff;}"
        )
        img_in_lay.addWidget(self.drop_zone)

        # Counter row
        count_row = QHBoxLayout()
        count_row.setSpacing(0)
        self.img_count_lbl = QLabel("0 ảnh đã chọn")
        self.img_count_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:12px; background:transparent;"
        )
        btn_clear_imgs = QPushButton("Xóa tất cả")
        btn_clear_imgs.setFixedHeight(28)
        btn_clear_imgs.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:6px;"
            f"padding:2px 10px;background:{SURFACE};color:{TEXT_MUTE};"
            "font-size:11px;}"
            "QPushButton:hover{background:#ebebf0;}"
            "QPushButton:pressed{background:#d8d8de;}"
        )
        btn_clear_imgs.clicked.connect(self._clear_images)
        count_row.addWidget(self.img_count_lbl)
        count_row.addStretch()
        count_row.addWidget(btn_clear_imgs)
        img_in_lay.addLayout(count_row)

        # Image list
        self.img_list = QListWidget()
        self.img_list.setFixedHeight(68)
        self.img_list.setStyleSheet(
            f"QListWidget{{border:none;background:{BG};border-radius:6px;padding:2px;}}"
            f"QListWidget::item{{padding:3px 6px;border-radius:4px;font-size:12px;"
            f"color:{TEXT};}}"
            f"QListWidget::item:selected{{background:#e8f0fe;color:{TEXT};}}"
        )
        img_in_lay.addWidget(self.img_list)

        img_c.addWidget(img_inner)
        layout.addWidget(img_card)

        # ══ Generate button — primary CTA ════════════════════════════════
        layout.addSpacing(16)
        self.btn_gen_script = QPushButton("✨   Tạo Kịch Bản")
        self.btn_gen_script.setMinimumHeight(50)
        self.btn_gen_script.setFont(QFont("", 15, QFont.Weight.Bold))
        self.btn_gen_script.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;"
            "border-radius:12px;border:none;}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            "QPushButton:pressed{background:#005bb5;}"
            "QPushButton:disabled{background:#a8d0fb;color:white;}"
        )
        self.btn_gen_script.clicked.connect(self._generate_script)
        layout.addWidget(self.btn_gen_script)

        # ══ Section 2: Kịch bản output — card ════════════════════════════
        layout.addWidget(self._section_lbl("KỊCH BẢN"))
        out_card, out_c = self._card()

        out_inner = QWidget()
        out_inner.setStyleSheet("background:transparent;border:none;")
        out_in_lay = QVBoxLayout(out_inner)
        out_in_lay.setContentsMargins(12, 12, 12, 12)
        out_in_lay.setSpacing(10)

        self.script_output = QTextEdit()
        self.script_output.setPlaceholderText(
            "Kịch bản sẽ hiện ra ở đây sau khi AI xử lý..."
        )
        self.script_output.setMinimumHeight(170)
        self.script_output.setStyleSheet(
            f"QTextEdit{{border:none;background:transparent;color:{TEXT};"
            "font-size:14px;padding:2px 0;}"
        )
        out_in_lay.addWidget(self.script_output)

        # Actions: Copy + Dùng cho TTS
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        btn_copy = QPushButton("📋  Copy")
        btn_copy.setFixedHeight(32)
        btn_copy.clicked.connect(self._copy_script)
        btn_copy.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:8px;"
            f"padding:0 14px;background:{SURFACE};color:{TEXT};font-size:13px;}}"
            "QPushButton:hover{background:#ebebf0;}"
            "QPushButton:pressed{background:#d8d8de;}"
        )

        btn_use_tts = QPushButton("→  Dùng cho TTS")
        btn_use_tts.setFixedHeight(32)
        btn_use_tts.clicked.connect(self._use_for_tts)
        btn_use_tts.setStyleSheet(
            f"QPushButton{{border:1px solid {ACCENT};border-radius:8px;"
            f"padding:0 14px;background:#f0f7ff;color:{ACCENT};"
            "font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#dbeafe;}"
            "QPushButton:pressed{background:#c4d9f7;}"
        )

        action_row.addWidget(btn_copy)
        action_row.addWidget(btn_use_tts)
        action_row.addStretch()
        out_in_lay.addLayout(action_row)

        out_c.addWidget(out_inner)
        layout.addWidget(out_card)

        # Status
        layout.addSpacing(8)
        self.chat_status_lbl = QLabel("Sẵn sàng")
        self.chat_status_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; background:transparent;"
        )
        self.chat_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.chat_status_lbl)

        layout.addStretch()
        scroll.setWidget(w)
        outer_lay.addWidget(scroll)
        return outer

    def _build_chat_tab(self) -> QWidget:
        page, layout = self._student_page()
        body = QWidget()
        body.setStyleSheet("background:transparent;border:none;")
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)

        left = QWidget()
        left.setStyleSheet("background:transparent;border:none;")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
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
            f"QFrame:hover{{border-color:{ACCENT};background:#f7fbff;}}"
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
            f"QListWidget::item:selected{{background:#e8f2ff;color:{TEXT};}}"
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

        h.addWidget(self._v_divider())

        right = QWidget()
        right.setStyleSheet("background:transparent;border:none;")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
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
            QMessageBox.warning(self, "Cần license", "Tính năng Kịch bản cần license key để sử dụng.")
            return
        if not self.image_paths:
            QMessageBox.warning(self, "Chưa có ảnh", "Thêm ảnh chat vào trước nhé!")
            return
        api_key = self.settings.get("gemini_api_key", "").strip()
        if not api_key:
            QMessageBox.warning(self, "Thiếu Gemini API Key",
                                "Vào Settings → API để nhập Gemini API Key trước nhé!")
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
            "color:#b45309; font-size:11px; background:transparent;"
        )

    def _on_script_done(self, text: str):
        self.btn_gen_script.setEnabled(True)
        self.script_output.setPlainText(text)
        self.chat_status_lbl.setText("Tạo kịch bản thành công")
        self.chat_status_lbl.setStyleSheet(
            "color:#34c759; font-size:14px; font-weight:600; background:transparent;"
        )
        QTimer.singleShot(4000, self._reset_chat_status)

    def _on_script_error(self, msg: str):
        self.btn_gen_script.setEnabled(True)
        self.chat_status_lbl.setText("Có lỗi xảy ra")
        self.chat_status_lbl.setStyleSheet(
            "color:#dc2626; font-size:11px; background:transparent;"
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
                "color:#34c759; font-size:11px; background:transparent;"
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
        title = QLabel("Mở khóa Kịch bản")
        title.setStyleSheet(f"font-size:15px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        sub = QLabel("TTS và STT dùng bình thường. Tính năng đọc ảnh chat và viết kịch bản cần license key.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        head.addLayout(title_col, 1)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._chat_license_input = QLineEdit()
        self._chat_license_input.setPlaceholderText("Nhập license key")
        self._chat_license_input.setText(self._current_license_key())
        self._chat_license_input.setFixedHeight(34)
        self._chat_license_input.setStyleSheet(
            f"QLineEdit{{background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;"
            f"color:{TEXT};font-size:13px;padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{ACCENT};}}"
        )
        self._chat_license_input.returnPressed.connect(self._chat_unlock_license)
        row.addWidget(self._chat_license_input, 1)

        self._chat_unlock_btn = QPushButton("Mở khóa")
        self._chat_unlock_btn.setFixedHeight(34)
        self._chat_unlock_btn.setStyleSheet(self._compact_primary_style())
        self._chat_unlock_btn.clicked.connect(self._chat_unlock_license)
        row.addWidget(self._chat_unlock_btn)
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
            self.btn_gen_script.setToolTip("" if unlocked else "Nhập license key để mở Kịch bản")
        if hasattr(self, "_chat_license_status"):
            cache = self.settings.get("pro_license_cache", {})
            msg = cache.get("message") if isinstance(cache, dict) else ""
            self._chat_license_status.setText(msg or "Chưa có license key mở Kịch bản.")
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
                f"font-size:12px;color:{SUCCESS if ok else '#ff453a'};background:transparent;border:none;"
            )
        self._chat_unlock_btn.setEnabled(True)
        self._chat_unlock_btn.setText("Mở khóa")
        self._chat_apply_lock_state()
        self._av_apply_lock_state()

    # ── TTS tab handlers ───────────────────────────────────────────
    def _all_styles(self) -> list[dict]:
        """Trả về toàn bộ styles: built-in + custom."""
        overrides = self.settings.get("prompt_preset_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}

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
            return {
                "name": name,
                "prompt": ov.get("prompt") or default_prompt,
                "creative": ov.get("creative", temp >= 0.5),
                "temperature": temp,
                "builtin": True,
            }

        built = [
            _builtin_style("Nghiêm túc", DEFAULT_PROMPT, 0.3),
            _builtin_style("Hài hước", DEFAULT_PROMPT_FUNNY, 0.7),
        ]
        custom = []
        for s in self.settings.get("custom_styles", []):
            icon = s.get("icon", "")
            name = s.get("name", "")
            prompt = s.get("prompt", "")
            if not name or not prompt:
                continue  # bỏ qua entry hỏng
            display_name = re.sub(r"^[^\wÀ-ỹ]+", "", name).strip() or name
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
        if saved_name and any(s["name"] == saved_name for s in self._all_styles()):
            return saved_name
        for s in self._all_styles():
            if s["prompt"] == current_prompt:
                return s["name"]
        return "Nghiêm túc"

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
                    "QPushButton:hover{background:#e5e5ea;}"
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
        current_prompt = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
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
            self.settings.setdefault("custom_styles", []).append(result)
            style_name = (
                f"{result.get('icon', '')}  {result.get('name', '')}"
                if result.get("icon") else result.get("name", "")
            )
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
        provider = (env.get("TTS_PROVIDER", "genmax") or "genmax").strip().lower()
        key_map = {
            "genmax": "GENMAX_VOICE_ID",
            "ai33": "AI33_VOICE_ID",
            "elevenlabs": "ELEVENLABS_VOICE_ID",
            "lucylab": "VIETNAMESE_VOICEID",
        }
        key = key_map.get(provider, "GENMAX_VOICE_ID")
        updates = {key: voice_id}
        if provider == "ai33" and not env.get("GENMAX_VOICE_ID", "").strip():
            updates["GENMAX_VOICE_ID"] = voice_id
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
        self._btn_check_update.setText("Checking...")
        self._manual_updater = UpdateChecker()
        self._manual_updater.update_found.connect(self._on_manual_update_found)
        self._manual_updater.no_update.connect(self._on_manual_no_update)
        self._manual_updater.error.connect(self._on_manual_update_error)
        self._manual_updater.finished.connect(self._reset_update_button)
        self._track_thread("_manual_updater", self._manual_updater)

    def _reset_update_button(self):
        self._btn_check_update.setEnabled(True)
        self._btn_check_update.setText("Update")

    def _restart_local_source_app(self):
        """Relaunch local source build so newly edited code is loaded."""
        self._btn_check_update.setEnabled(False)
        self._btn_check_update.setText("Restarting...")
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
        genmax_key = self.settings.get("genmax_api_key", "")
        has_el  = bool(el_keys)
        has_gm  = bool(genmax_key)
        if not has_el and not has_gm:
            self._credits_refresh_pending = False
            self.credits_lbl.setText("⚠️  Chưa có TTS API key — vào Settings → API")
            return
        if self._is_thread_running(self._credits_worker):
            self._credits_refresh_pending = True
            return
        self._credits_refresh_pending = False
        self.credits_lbl.setText("Credits: đang tải...")
        worker = _CreditsChecker(el_keys, genmax_key)

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

    def _generate(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Paste kịch bản vào trước nhé!")
            return

        # Kiểm tra TTS key (GenMax hoặc ElevenLabs)
        has_tts = bool(self.settings.get("genmax_api_key") or self.settings.get("el_api_keys"))
        if not has_tts:
            QMessageBox.warning(self, "Thiếu TTS API Key",
                                "Cần ít nhất một TTS API Key:\n\n"
                                "GenMax API Key (rẻ hơn, khuyến nghị)\n"
                                "  hoặc\n"
                                "ElevenLabs API Key\n\n"
                                "Vào Settings → API để thêm.")
            return

        filename = self.filename_input.text().strip()
        if not filename:
            QMessageBox.warning(self, "Thiếu tên file", "Nhập tên file trước khi generate nhé!")
            self.filename_input.setFocus()
            return
        safe_filename = os.path.basename(filename).strip()
        if safe_filename.lower().endswith(".mp3"):
            safe_filename = safe_filename[:-4].strip()
        safe_filename = safe_filename.replace(" ", "_")
        if not safe_filename:
            QMessageBox.warning(self, "Tên file không hợp lệ", "Nhập lại tên file ngắn gọn hơn nhé!")
            self.filename_input.setFocus()
            return
        out_dir = self.settings.get("output_dir", DEFAULT_OUT)
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
        if hasattr(self, "_audio_icon_lbl"):
            self._audio_icon_lbl.setPixmap(ui_icon("audio", 34, TEXT_FAINT).pixmap(icon_size(34)))
            self._audio_title_lbl.setText("Đang tạo audio")
            self._audio_title_lbl.setStyleSheet(
                f"font-size:22px;font-weight:700;color:{TEXT};background:transparent;border:none;"
            )
            self._audio_detail_lbl.setText("Tool đang xử lý kịch bản và tạo file đọc.")
        self.tts_status_lbl.setText("Đang khởi động")
        self.tts_status_lbl.setStyleSheet("color:#b45309;font-size:12px;background:transparent;border:none;")
        self._btn_play_audio.setEnabled(False)
        self._btn_open_folder.setEnabled(False)
        if hasattr(self, "_btn_export_srt"):
            self._btn_export_srt.setEnabled(False)

        # Nếu đã có preview text (user đã xem trước) → dùng luôn, không enhance lại
        preview_text = getattr(self, "_enhanced_cache", "").strip()
        if preview_text:
            self.worker = _TTSOnlyWorker(preview_text, speed,
                                         safe_filename, self.settings)
        else:
            # Chưa preview → enhance + TTS như cũ
            self.worker = Worker(text, speed, safe_filename, self.settings)

        self.worker.status.connect(self._on_tts_status)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self._track_thread("worker", self.worker)

    # ── Preview handlers ──────────────────────────────────────────────
    def _do_preview(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Paste kịch bản vào trước nhé!")
            return
        has_ai = bool(
            self.settings.get("claude_api_key")
            or self.settings.get("gemini_api_key")
            or self.settings.get("ds_api_key")
        )
        if not has_ai:
            QMessageBox.warning(self, "Thiếu AI Key",
                                "Cần API key AI để xử lý kịch bản:\n\n"
                                "Claude API Key (khuyến nghị)\n"
                                "   hoặc\n"
                                "Gemini API Key (miễn phí — fallback)\n"
                                "   hoặc\n"
                                "DeepSeek API Key\n\n"
                                "Vào Settings → API để thêm.")
            return
        self._btn_preview.setEnabled(False)
        self._btn_preview.setText("Đang xử lý...")
        self._enhanced_cache = ""
        self._preview_box.setVisible(True)
        self.preview_text.setPlainText("")
        self._preview_status.setText("AI đang xử lý kịch bản...")
        self._preview_status.setStyleSheet(
            "font-size:11px;color:#b45309;background:transparent;border:none;"
        )
        self._preview_worker = PreviewWorker(text, self.settings)
        self._preview_worker.status.connect(lambda m: self._preview_status.setText(m))
        self._preview_worker.done.connect(self._on_preview_done)
        self._preview_worker.error.connect(self._on_preview_error_msg)
        self._track_thread("_preview_worker", self._preview_worker)

    def _on_preview_done(self, enhanced: str):
        self._enhanced_cache = enhanced
        self.preview_text.setPlainText(enhanced)
        self._preview_status.setText("Đã xử lý xong. Chỉnh nếu cần rồi nhấn Tạo audio.")
        self._preview_status.setStyleSheet(
            "font-size:11px;color:#34c759;background:transparent;border:none;"
        )
        self._btn_preview.setEnabled(True)
        self._btn_preview.setText("Xem kịch bản")
        # Khi user chỉnh sửa preview → cập nhật cache
        try:
            self.preview_text.textChanged.disconnect()
        except TypeError:
            pass
        self.preview_text.textChanged.connect(
            lambda: setattr(self, "_enhanced_cache", self.preview_text.toPlainText())
        )

    def _on_preview_error_msg(self, msg: str):
        self._preview_status.setText(msg)
        self._preview_status.setStyleSheet(
            "font-size:11px;color:#dc2626;background:transparent;border:none;"
        )
        self._btn_preview.setEnabled(True)
        self._btn_preview.setText("Xem kịch bản")

    def _on_script_changed(self):
        """Khi sửa kịch bản gốc → reset preview để tránh gen sai."""
        if getattr(self, "_enhanced_cache", ""):
            self._enhanced_cache = ""
            self.preview_text.setPlainText("")
            self._preview_status.setText("Kịch bản đã thay đổi. Nhấn lại Xem kịch bản để cập nhật.")
            self._preview_status.setStyleSheet(
                "font-size:11px;color:#b45309;background:transparent;border:none;"
            )

    def _on_tts_status(self, msg: str):
        self.tts_status_lbl.setText(msg)
        self.tts_status_lbl.setStyleSheet(
            "color:#b45309; font-size:11px; background:transparent;"
        )
        if hasattr(self, "_audio_title_lbl") and not getattr(self, "_last_audio_path", ""):
            self._audio_title_lbl.setText("Đang tạo audio")
            self._audio_title_lbl.setStyleSheet(
                f"font-size:22px;font-weight:700;color:{TEXT};background:transparent;border:none;"
            )
            self._audio_detail_lbl.setText(msg)

    def _on_done(self, path: str):
        self.btn_gen.setEnabled(True)
        self.tts_status_lbl.setText("Tạo audio thành công")
        self.tts_status_lbl.setStyleSheet(
            "color:#34c759; font-size:12px; font-weight:600; background:transparent;"
        )
        self._last_audio_path = path
        self._last_srt_path = os.path.splitext(path)[0] + ".srt"
        filename = os.path.basename(path)
        folder = os.path.dirname(path)
        if hasattr(self, "_audio_icon_lbl"):
            self._audio_icon_lbl.setPixmap(ui_icon("audio", 34, ACCENT).pixmap(icon_size(34)))
            self._audio_title_lbl.setText(filename or "Audio đã tạo")
            self._audio_title_lbl.setStyleSheet(
                f"font-size:18px;font-weight:700;color:{TEXT};background:transparent;border:none;"
            )
            self._audio_detail_lbl.setText(folder)
            self._audio_detail_lbl.setStyleSheet(
                f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;"
            )
        self._btn_play_audio.setEnabled(True)
        self._btn_open_folder.setEnabled(True)
        if hasattr(self, "_btn_export_srt"):
            self._btn_export_srt.setEnabled(os.path.exists(self._last_srt_path))
        self._btn_play_audio.setText("Nghe lại")
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
        self._btn_play_audio.setText("Dừng")
        self.tts_status_lbl.setText("Đang phát")
        self.tts_status_lbl.setStyleSheet(
            "color:#34c759; font-size:12px; font-weight:600; background:transparent;"
        )

    def _on_output_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState and hasattr(self, "_btn_play_audio"):
            self._btn_play_audio.setText("Nghe lại")
            if getattr(self, "_last_audio_path", ""):
                self.tts_status_lbl.setText("Sẵn sàng nghe lại")
                self.tts_status_lbl.setStyleSheet(
                    f"color:{TEXT_MUTE}; font-size:12px; background:transparent;"
                )

    def _reset_tts_status(self):
        if self._output_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        self.tts_status_lbl.setText("Sẵn sàng nghe lại" if getattr(self, "_last_audio_path", "") else "Chưa có audio")
        self.tts_status_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:12px; background:transparent;"
        )

    def _on_error(self, msg: str):
        self.btn_gen.setEnabled(True)
        self.tts_status_lbl.setText("Có lỗi xảy ra")
        self.tts_status_lbl.setStyleSheet(
            "color:#dc2626; font-size:12px; font-weight:600; background:transparent;"
        )
        if hasattr(self, "_audio_icon_lbl"):
            self._audio_icon_lbl.setPixmap(ui_icon("audio", 34, TEXT_FAINT).pixmap(icon_size(34)))
            self._audio_title_lbl.setText("Tạo audio lỗi")
            self._audio_title_lbl.setStyleSheet(
                f"font-size:22px;font-weight:700;color:#dc2626;background:transparent;border:none;"
            )
            self._audio_detail_lbl.setText("Kiểm tra API key, provider hoặc thử tạo lại.")
        has_old_audio = bool(getattr(self, "_last_audio_path", "") and os.path.exists(self._last_audio_path))
        self._btn_play_audio.setEnabled(has_old_audio)
        self._btn_open_folder.setEnabled(has_old_audio)
        if hasattr(self, "_btn_export_srt"):
            old_srt = os.path.splitext(getattr(self, "_last_audio_path", ""))[0] + ".srt"
            self._last_srt_path = old_srt if os.path.exists(old_srt) else ""
            self._btn_export_srt.setEnabled(bool(self._last_srt_path))
        QMessageBox.critical(self, "Lỗi", msg)

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
        row_all.addWidget(_lbl_combo("Preset", self._av_script_preset))

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
        row_all.addWidget(_lbl_combo("Giao diện", self._av_visual_preset))

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
        row_all.addWidget(_lbl_combo("Sub", self._av_sub_toggle))

        row_all.addSpacing(8)

        # Pace
        self._av_pace = self._av_quick_choice(
            [("Dynamic", "dynamic"), ("Chuẩn", "standard")],
            env.get("AUTO_VIDEO_EDITING_PACE", "dynamic"),
        )
        self._av_pace.currentIndexChanged.connect(self._av_save_quick_presets)
        row_all.addWidget(_lbl_combo("Nhịp", self._av_pace))

        # Divider
        sep = QWidget()
        sep.setFixedSize(1, 20)
        sep.setStyleSheet(f"background:{BORDER_SOFT};border:none;")
        row_all.addSpacing(8)
        row_all.addWidget(sep)
        row_all.addSpacing(8)

        # Voice
        self._av_voice_combo = self._make_favorites_combo("av")
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
            "background:#ffffff;color:#1d1d1f;"
            "border:1px solid #d2d2d7;border-radius:10px;"
            "padding:4px;outline:none;}"
            "QComboBox QAbstractItemView::item{min-height:26px;padding:3px 12px;"
            "color:#1d1d1f;border-radius:6px;}"
            "QComboBox QAbstractItemView::item:selected{background:#dbeafe;color:#0071e3;"
            "font-weight:600;}"
        )
        self._av_lang_combo.setItemDelegate(QStyledItemDelegate(self._av_lang_combo))
        self._av_lang_combo.currentIndexChanged.connect(lambda _: self._av_save_language())
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
            f"QPushButton:disabled{{background:#a8d0fb;color:white;}}"
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
            "QScrollBar::handle:horizontal{background:#d2d2d7;border-radius:2px;}"
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
            f"color:{TEXT_MUTE};font-size:11px;font-family:Menlo,Monaco,monospace;padding:10px;}}"
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

        layout.addWidget(body_w, 1)
        self._av_lock_panel = self._build_auto_video_unlock_panel()
        layout.addWidget(self._av_lock_panel)
        self._av_script_worker = None
        self._av_engine_worker = None
        self._av_apply_lock_state()
        return page

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
        title = QLabel("Mở khóa Auto Video")
        title.setStyleSheet(f"font-size:15px;font-weight:700;color:{TEXT};background:transparent;border:none;")
        sub = QLabel("TTS và STT dùng bình thường. Auto Video cần license key online để mở khóa.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size:12px;color:{TEXT_MUTE};background:transparent;border:none;")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        head.addLayout(title_col, 1)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._av_license_input = QLineEdit()
        self._av_license_input.setPlaceholderText("Nhập license key")
        self._av_license_input.setText(self._current_license_key())
        self._av_license_input.setFixedHeight(34)
        self._av_license_input.setStyleSheet(
            f"QLineEdit{{background:{SURFACE};border:1px solid {BORDER_SOFT};border-radius:8px;"
            f"color:{TEXT};font-size:13px;padding:0 10px;}}"
            f"QLineEdit:focus{{border-color:{ACCENT};}}"
        )
        self._av_license_input.returnPressed.connect(self._av_unlock_license)
        row.addWidget(self._av_license_input, 1)

        self._av_unlock_btn = QPushButton("Mở khóa")
        self._av_unlock_btn.setFixedHeight(34)
        self._av_unlock_btn.setStyleSheet(self._compact_primary_style())
        self._av_unlock_btn.clicked.connect(self._av_unlock_license)
        row.addWidget(self._av_unlock_btn)
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
            self._av_gen_btn.setToolTip("" if unlocked else "Nhập license key để mở Auto Video")
        if hasattr(self, "_av_status") and not unlocked:
            self._av_set_status("Auto Video đang khóa. Nhập license key để mở tính năng này.", error=False)
        if hasattr(self, "_av_license_status"):
            key = self._current_license_key()
            if key:
                cache = self.settings.get("pro_license_cache", {})
                ok = is_auto_video_unlocked(self.settings)
                msg = cache.get("message") if isinstance(cache, dict) else ""
                msg = msg or ("Auto Video đã mở khóa." if ok else "License chưa mở Auto Video.")
                self._av_license_status.setText(msg)
                self._av_license_status.setStyleSheet(
                    f"font-size:12px;color:{SUCCESS if ok else '#ff453a'};background:transparent;border:none;"
                )
            else:
                self._av_license_status.setText("Chưa có license key Auto Video.")
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
                f"font-size:12px;color:{SUCCESS if ok else '#ff453a'};background:transparent;border:none;"
            )
        self._av_unlock_btn.setEnabled(True)
        self._av_unlock_btn.setText("Mở khóa")
        self._av_apply_lock_state()
        self._chat_apply_lock_state()
        if ok:
            self._av_set_status("Auto Video đã mở khóa. Bạn có thể nhập link hoặc paste nội dung để tạo video.")

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
            "background:#ffffff;color:#1d1d1f;"
            "border:1px solid #d2d2d7;border-radius:10px;"
            "padding:4px;outline:none;}"
            "QComboBox QAbstractItemView::item{min-height:26px;padding:3px 12px;"
            "color:#1d1d1f;border-radius:6px;}"
            "QComboBox QAbstractItemView::item:selected{background:#dbeafe;color:#0071e3;"
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
        try:
            _write_env_local({"GENMAX_LANGUAGE_CODE": lang or "vi"})
        except Exception as e:
            self._av_set_status(f"Không lưu được ngôn ngữ Auto Video: {e}", error=True)
            return False
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
        if not is_auto_video_unlocked(self.settings):
            self._av_apply_lock_state()
            self._av_set_status("Auto Video đang khóa. Nhập license key để dùng tính năng này.", error=True)
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
            self._av_set_status("Chưa có API key — vào Settings → API để thêm key viết script.", error=True)
            return

        self._av_gen_btn.setEnabled(False)
        self._av_gen_btn.setText("Đang tạo…")
        self._av_script_card.setVisible(False)
        self._av_log.clear()
        self._av_log.setVisible(True)
        self._av_step_label.setText("Đang khởi động…")
        self._av_step_label.setVisible(True)
        self._av_prog_row.setVisible(True)
        self._av_progress.setValue(0)
        self._av_pct_label.setText("0%")
        self._av_result_card.setVisible(False)

        self._av_script_worker = AutoScriptWorker(inp)
        self._av_script_worker.progress.connect(self._av_set_status)
        self._av_script_worker.finished.connect(self._av_on_script_done)
        self._av_script_worker.error.connect(self._av_on_error)
        self._track_thread("_av_script_worker", self._av_script_worker)

    def _av_on_script_done(self, script_path: str):
        self._av_show_script(script_path)
        self._av_set_status("Script xong — đang render video…")
        self._av_engine_worker = AutoVideoEngineWorker(script_path)
        self._av_engine_worker.log_line.connect(self._av_append_log)
        self._av_engine_worker.progress.connect(self._av_on_progress)
        self._av_engine_worker.finished.connect(self._av_on_video_done)
        self._av_engine_worker.error.connect(self._av_on_error)
        self._track_thread("_av_engine_worker", self._av_engine_worker)

    def _av_on_video_done(self, video_path: str):
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
        self._av_gen_btn.setEnabled(True)
        self._av_gen_btn.setText("Generate Video")
        self._av_prog_row.setVisible(False)
        self._av_step_label.setVisible(False)
        self._av_set_status(msg, error=True)

    def _av_set_status(self, msg: str, error: bool = False):
        color = "#e0303a" if error else TEXT_MUTE
        self._av_status.setText(msg)
        self._av_status.setStyleSheet(
            f"color:{color}; font-size:12px; background:transparent;"
        )

    def _av_append_log(self, line: str):
        self._av_log.append(line)
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
        provider = env.get("TTS_PROVIDER", "genmax").strip().lower() or "genmax"
        voice_key = {
            "genmax": "GENMAX_VOICE_ID",
            "ai33": "AI33_VOICE_ID",
            "elevenlabs": "ELEVENLABS_VOICE_ID",
            "lucylab": "VIETNAMESE_VOICEID",
        }.get(provider, "GENMAX_VOICE_ID")
        voice_id = env.get(voice_key, "")
        if provider == "ai33" and not voice_id:
            voice_id = env.get("GENMAX_VOICE_ID", "")
        voice_hint = voice_id[:8] + "..." if len(voice_id) > 8 else (voice_id or "missing")
        fallback_on = str(env.get("GENMAX_FALLBACK_TO_AI33", "true")).strip().lower() in ("1", "true", "yes", "on")
        if provider == "genmax" and fallback_on:
            tts_hint = "genmax → ai33" if env.get("AI33_API_KEY", "").strip() else "genmax → ai33 missing key"
        else:
            tts_hint = provider
        script_provider = env.get("SCRIPT_AI_PROVIDER", "claude").strip().lower() or "claude"
        script_model = {
            "claude": env.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
            "gemini": env.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash"),
            "deepseek": "deepseek-chat",
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
