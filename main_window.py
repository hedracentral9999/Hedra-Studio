import os
import sys
import subprocess
import webbrowser

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QLineEdit, QSlider, QPushButton, QFrame,
    QTabWidget, QScrollArea, QStackedWidget, QFileDialog,
    QMessageBox, QSizePolicy, QSpacerItem, QListWidget,
    QListWidgetItem, QMenu, QGridLayout, QComboBox, QDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QIcon, QFont, QAction, QPixmap, QColor, QPainter
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from app_constants import (
    VOICE_ID, MODEL, EL_OUTPUT_FORMAT, PROMPTS, PROMPT_TEMPLATES,
    VERSION, DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY,
    BG, SURFACE, BORDER, TEXT, TEXT_MUTE, ACCENT, ACCENT_HV, SEG_BG, STYLE,
    get_creativity_guide,
)
from app_utils import load_settings, save_settings, reveal_file, DEFAULT_OUT, DATA_DIR
from app_workers import (
    Worker, _TTSOnlyWorker, PreviewWorker, GeminiWorker,
    UpdateChecker, UpdateDownloader, _CreditsChecker,
    SpeechToTextWorker, words_to_srt,
)
from app_dialogs import AddStyleDialog, FeedbackDialog, DropZone
from settings_dialog import SettingsDialog
from auto_video_workers import AutoScriptWorker, AutoVideoEngineWorker

# ── Telegram config ────────────────────────────────────────────────
try:
    from telegram_config import TELEGRAM_BOT_TOKEN as _TG_BOT, TELEGRAM_CHAT_ID as _TG_CHAT
    TELEGRAM_BOT_TOKEN = _TG_BOT
    TELEGRAM_CHAT_ID = _TG_CHAT
except ImportError:
    TELEGRAM_BOT_TOKEN = os.environ.get("ELEVENLABS_TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("ELEVENLABS_TELEGRAM_CHAT_ID", "")

# ── Main window ────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings      = settings
        self.worker        = None
        self.gemini_worker = None
        self.image_paths   = []
        self._parent_ref   = self          # self-ref cho _open_voices_settings
        self._output_audio = QAudioOutput()
        self._output_audio.setVolume(1.0)
        self._output_player = QMediaPlayer()
        self._output_player.setAudioOutput(self._output_audio)
        self._output_player.playbackStateChanged.connect(self._on_output_playback_state)
        self.setWindowTitle(f"🎙  Hedra Studio  v{VERSION}")
        self.setMinimumSize(540, 640)
        self.resize(580, 740)
        self.setStyleSheet(STYLE)
        # App icon
        try:
            icon_path = os.path.join(os.path.dirname(__file__) if not getattr(sys, 'frozen', False) else sys._MEIPASS, "icon.icns")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass
        self._build()
        self._refresh_credits()
        self._check_update()

    # ── Apple HIG helpers ─────────────────────────────────────────
    def _section_lbl(self, text: str) -> QLabel:
        """Section label — small caps, muted, Apple System Settings style."""
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; font-weight:600;"
            "padding:16px 0 6px 0;"
            "background:transparent; border:none;"
        )
        return lbl

    def _card(self) -> tuple:
        """White card — Apple System Settings style.
        Không có border — dùng contrast trắng-trên-xám để tạo ranh giới."""
        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget{{background:{SURFACE};"
            "border:none;"
            "border-radius:10px;}}"
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
        h = QHBoxLayout(row_w)
        h.setContentsMargins(16, 13, 16, 13)
        h.setSpacing(12)

        lbl = QLabel(label)
        lbl.setFixedWidth(116)
        lbl.setStyleSheet(
            f"QLabel{{font-size:13px;color:{TEXT};"
            "background:transparent;border:none;}"
        )
        h.addWidget(lbl)

        right = QVBoxLayout()
        right.setSpacing(3)
        right.addWidget(widget)
        if note:
            n = QLabel(note)
            n.setStyleSheet(
                f"QLabel{{font-size:11px;color:{TEXT_MUTE};"
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
            sep_line.setStyleSheet("background:#e5e5ea;border:none;")
            sep_h.addWidget(sep_line)
            container_vbox.addWidget(sep_wrap)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(20, 18, 20, 18)

        # ── Header ─────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("🎙  Hedra Studio")
        title_lbl.setFont(QFont("", 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color:{TEXT}; background:transparent;")
        self.credits_lbl = QLabel("Credits: đang tải...")
        self.credits_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; background:transparent;"
        )
        title_col.addWidget(title_lbl)
        title_col.addWidget(self.credits_lbl)
        header_row.addLayout(title_col)
        header_row.addStretch()

        ver_lbl = QLabel(f"v{VERSION}")
        ver_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; background:transparent; padding-right:8px;"
        )
        header_row.addWidget(ver_lbl)

        btn_feedback = QPushButton("Feedback")
        btn_feedback.setFixedHeight(28)
        btn_feedback.setToolTip("Gửi phản hồi / Báo lỗi")
        btn_feedback.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:14px;"
            f"padding:3px 14px;background:{SURFACE};color:{TEXT_MUTE};font-size:12px;}}"
            f"QPushButton:hover{{background:#ebebf0;color:{TEXT};}}"
            f"QPushButton:pressed{{background:{SEG_BG};}}"
        )
        btn_feedback.clicked.connect(self._open_feedback)
        header_row.addWidget(btn_feedback)
        header_row.addSpacing(6)

        self._btn_check_update = QPushButton("Update")
        self._btn_check_update.setFixedHeight(28)
        self._btn_check_update.setToolTip("Kiểm tra và tải bản mới nhất")
        self._btn_check_update.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:14px;"
            f"padding:3px 14px;background:{SURFACE};color:{TEXT_MUTE};font-size:12px;}}"
            f"QPushButton:hover{{background:#ebebf0;color:{TEXT};}}"
            f"QPushButton:pressed{{background:{SEG_BG};}}"
            "QPushButton:disabled{color:#aeaeb2;background:#f5f5f7;}"
        )
        self._btn_check_update.clicked.connect(self._manual_check_update)
        header_row.addWidget(self._btn_check_update)
        header_row.addSpacing(6)

        btn_settings = QPushButton("Settings")
        btn_settings.setFixedHeight(28)
        btn_settings.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:14px;"
            f"padding:3px 14px;background:{SURFACE};color:{TEXT};font-size:12px;}}"
            f"QPushButton:hover{{background:#ebebf0;}}"
            f"QPushButton:pressed{{background:{SEG_BG};}}"
        )
        btn_settings.clicked.connect(self.open_settings)
        header_row.addWidget(btn_settings)
        layout.addLayout(header_row)
        layout.addSpacing(12)

        # ── Update banner ──────────────────────────────────────────
        self.update_banner = QFrame()
        self.update_banner.setVisible(False)
        self.update_banner.setStyleSheet(
            "QFrame{background:#f0f7ff;border:1px solid #bfdbfe;border-radius:10px;}"
        )
        banner_row = QHBoxLayout(self.update_banner)
        banner_row.setContentsMargins(12, 8, 8, 8)
        banner_row.setSpacing(8)
        badge = QLabel("NEW")
        badge.setStyleSheet(
            f"background:{ACCENT};color:white;border-radius:4px;"
            f"padding:1px 7px;font-size:11px;font-weight:bold;"
        )
        badge.setFixedHeight(18)
        self._banner_text = QLabel()
        self._banner_text.setStyleSheet(
            "color:#004499;font-size:12px;background:transparent;border:none;"
        )
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

        # ── Separator ──────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)
        layout.addSpacing(4)

        # ── Tab widget ─────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_chat_tab(), "💬  Chat → Kịch Bản")
        self.tabs.addTab(self._build_tts_tab(),  "🎙  TTS")
        self.tabs.addTab(self._build_stt_tab(),  "📝  STT")
        self.tabs.addTab(self._build_auto_video_tab(), "🎬  Auto Video")
        self.tabs.setCurrentIndex(1)  # TTS mặc định
        layout.addWidget(self.tabs)

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
            "border:1.5px solid #c5d9f8;border-radius:8px;"
            "font-size:12px;font-weight:600;padding:0 14px;}}"
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
            f"QTextEdit{{border:1.5px solid #e5e5ea;border-radius:10px;"
            f"background:{SURFACE};color:{TEXT};padding:12px 14px;"
            f"font-size:14px;}}"
            f"QTextEdit:focus{{border:1.5px solid {ACCENT};}}"
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
            "font-size:10px;font-weight:700;letter-spacing:0.8px;"
            "color:#6e6e73;background:transparent;border:none;"
        )
        pv_h.addWidget(pv_lbl)
        pv_h.addStretch()
        pv_note = QLabel("Có thể chỉnh sửa trước khi gen giọng")
        pv_note.setStyleSheet("font-size:10px;color:#aeaeb2;background:transparent;border:none;")
        pv_h.addWidget(pv_note)
        pv_lay.addWidget(pv_header)

        self.preview_text = QTextEdit()
        self.preview_text.setPlaceholderText("Nhấn \"✨ Xem kịch bản\" để xem kịch bản sau khi AI xử lý...")
        self.preview_text.setMinimumHeight(160)
        self.preview_text.setStyleSheet(
            "QTextEdit{border:1.5px solid #c5d9f8;border-radius:10px;"
            "background:#f0f6ff;color:#1d1d1f;padding:12px 14px;font-size:13px;}"
            f"QTextEdit:focus{{border:1.5px solid {ACCENT};}}"
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
        btn_add_style.setFixedSize(28, 28)
        btn_add_style.setToolTip("Thêm phong cách tùy chỉnh")
        btn_add_style.setStyleSheet(
            f"QPushButton{{background:{SEG_BG};border:1px solid #c7c7cc;"
            f"border-radius:8px;color:{TEXT};font-size:16px;font-weight:400;"
            f"padding:0;}}"
            "QPushButton:hover{background:#d8d8de;border-color:#aeaeb2;}"
            "QPushButton:pressed{background:#c7c7cc;}"
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
            ("🌐  Tự động",       ""),
            ("🇻🇳  Tiếng Việt",   "vi"),
            ("🇺🇸  Tiếng Anh",    "en"),
            ("🇨🇳  Tiếng Trung",  "zh"),
            ("🇯🇵  Tiếng Nhật",   "ja"),
            ("🇰🇷  Tiếng Hàn",    "ko"),
        ]
        _lang_rest = [
            ("🇸🇦  Tiếng Ả Rập",      "ar"),
            ("🇧🇬  Tiếng Bungari",     "bg"),
            ("🇭🇷  Tiếng Croatia",     "hr"),
            ("🇨🇿  Tiếng Séc",         "cs"),
            ("🇩🇰  Tiếng Đan Mạch",    "da"),
            ("🇳🇱  Tiếng Hà Lan",      "nl"),
            ("🇵🇭  Tiếng Philippines", "fil"),
            ("🇫🇮  Tiếng Phần Lan",    "fi"),
            ("🇫🇷  Tiếng Pháp",        "fr"),
            ("🇩🇪  Tiếng Đức",         "de"),
            ("🇬🇷  Tiếng Hy Lạp",      "el"),
            ("🇮🇳  Tiếng Hindi",       "hi"),
            ("🇭🇺  Tiếng Hungary",     "hu"),
            ("🇮🇩  Tiếng Indonesia",   "id"),
            ("🇮🇹  Tiếng Ý",           "it"),
            ("🇲🇾  Tiếng Mã Lai",      "ms"),
            ("🇳🇴  Tiếng Na Uy",       "no"),
            ("🇵🇱  Tiếng Ba Lan",      "pl"),
            ("🇧🇷  Tiếng Bồ Đào Nha", "pt"),
            ("🇷🇴  Tiếng Romania",     "ro"),
            ("🇷🇺  Tiếng Nga",         "ru"),
            ("🇸🇰  Tiếng Slovak",      "sk"),
            ("🇪🇸  Tiếng Tây Ban Nha", "es"),
            ("🇸🇪  Tiếng Thụy Điển",   "sv"),
            ("🇮🇳  Tiếng Tamil",       "ta"),
            ("🇹🇷  Tiếng Thổ Nhĩ Kỳ", "tr"),
            ("🇺🇦  Tiếng Ukraine",     "uk"),
        ]
        _lang_options = _lang_top + _lang_rest

        _saved_lang = self.settings.get("tts_language_code", "")
        self._lang_code = _saved_lang
        _lang_map = {code: lbl for lbl, code in _lang_options}

        def _lang_btn_style(active: bool) -> str:
            # height = 28px → border-radius = 14px (= height/2) để pill đúng
            if active:
                return (
                    f"QPushButton{{background:#e8f0fd;color:{ACCENT};"
                    f"border:1.5px solid {ACCENT};border-radius:14px;"
                    "min-height:28px;padding:0 10px 0 12px;"
                    "font-size:12px;font-weight:600;}}"
                    "QPushButton:hover{background:#dce9fd;}"
                    "QPushButton:pressed{background:#cfe0fc;}"
                )
            return (
                "QPushButton{background:#ebebf0;color:#3c3c43;"
                "border:none;border-radius:14px;"
                "min-height:28px;padding:0 10px 0 12px;"
                "font-size:12px;font-weight:500;}"
                "QPushButton:hover{background:#e0e0e6;}"
                "QPushButton:pressed{background:#d4d4da;}"
            )

        # Pill dropdown button — hiển thị lựa chọn hiện tại + chevron
        _init_label = _lang_map.get(_saved_lang, "🌐  Tự động") + "  ▾"
        self._lang_btn = QPushButton(_init_label)
        self._lang_btn.setFixedHeight(28)
        self._lang_btn.setStyleSheet(_lang_btn_style(_saved_lang != ""))
        self._lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _show_lang_menu():
            menu = QMenu(self._lang_btn)
            menu.setStyleSheet(
                "QMenu{background:#ffffff;border:1px solid #d2d2d7;"
                "border-radius:10px;padding:4px 0;}"
                "QMenu::item{padding:7px 20px;font-size:13px;color:#1d1d1f;}"
                "QMenu::item:selected{background:#e8f0fd;color:#0071e3;}"
                "QMenu::item:checked{font-weight:600;color:#0071e3;}"
                "QMenu::separator{height:1px;background:#e5e5ea;margin:3px 0;}"
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
                self._lang_btn.setText("🌐  Tự động  ▾")
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
        btn_change_voice = QPushButton("Đổi giọng →")
        btn_change_voice.setFixedHeight(28)
        btn_change_voice.setStyleSheet(
            f"QPushButton{{font-size:12px;color:{ACCENT};background:transparent;"
            "border:none;padding:0 4px;}"
            "QPushButton:hover{text-decoration:underline;}"
            "QPushButton:pressed{color:#005bb5;}"
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
        self._stt_drop = DropZone()
        self._stt_drop.files_added.connect(self._stt_file_selected)
        self._stt_drop.setStyleSheet(
            "QFrame{border:1.5px dashed #c7c7cc;border-radius:10px;background:#ffffff;}"
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
            f"QTextEdit{{border:1.5px solid #e5e5ea;border-radius:10px;"
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
            "border-radius:8px;padding:0 16px;font-size:13px;font-weight:600;}}"
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

    def _stt_file_selected(self, paths: list):
        if paths:
            self._stt_path = paths[0]
            self._stt_file_lbl.setText(f"📁 {os.path.basename(paths[0])}")

    def _do_stt(self):
        if not self._stt_path:
            QMessageBox.warning(self, "Chưa có file", "Kéo thả file audio vào trước nhé!")
            return
        gm_key = self.settings.get("genmax_api_key", "").strip()
        if not gm_key:
            QMessageBox.warning(self, "Thiếu GenMax API Key",
                                "Cần GenMax API Key để dùng Speech-to-Text.\nVào Settings → API Keys để thêm.")
            return
        self._stt_btn.setEnabled(False)
        self._stt_status.setText("⏳ Đang nhận diện...")
        self._stt_worker = SpeechToTextWorker(self._stt_path, gm_key)
        self._stt_worker.status.connect(self._stt_status.setText)
        self._stt_worker.done.connect(self._on_stt_done)
        self._stt_worker.error.connect(self._on_stt_error)
        self._stt_worker.start()

    def _on_stt_done(self, text: str, words: list):
        self._stt_btn.setEnabled(True)
        self._stt_text.setPlainText(text)
        self._stt_status.setText("✅ Nhận diện xong!")
        self._stt_words = words
        self._stt_export_btn.setVisible(True)

    def _on_stt_error(self, msg: str):
        self._stt_btn.setEnabled(True)
        self._stt_status.setText(f"❌ {msg[:80]}")

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
            self._stt_status.setText(f"✅ Đã lưu: {os.path.basename(path)}")
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
            "QFrame{border:1.5px dashed #c7c7cc;border-radius:8px;"
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

    # ── Chat tab handlers ──────────────────────────────────────────
    def _add_images(self, paths: list):
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                item = QListWidgetItem(f"🖼  {os.path.basename(p)}")
                item.setData(Qt.ItemDataRole.UserRole, p)
                self.img_list.addItem(item)
        self.img_count_lbl.setText(f"{len(self.image_paths)} ảnh đã chọn")

    def _clear_images(self):
        self.image_paths.clear()
        self.img_list.clear()
        self.img_count_lbl.setText("0 ảnh đã chọn")

    def _generate_script(self):
        if not self.image_paths:
            QMessageBox.warning(self, "Chưa có ảnh", "Thêm ảnh chat vào trước nhé!")
            return
        api_key = self.settings.get("gemini_api_key", "").strip()
        if not api_key:
            QMessageBox.warning(self, "Thiếu Gemini API Key",
                                "Vào Settings → tab API Keys\nnhập Gemini API Key trước nhé!")
            return

        self.btn_gen_script.setEnabled(False)
        gemini_prompt = self.settings.get("gemini_chat_prompt", "").strip() or GEMINI_CHAT_PROMPT
        self.gemini_worker = GeminiWorker(self.image_paths, api_key, gemini_prompt)
        self.gemini_worker.status.connect(self._on_chat_status)
        self.gemini_worker.done.connect(self._on_script_done)
        self.gemini_worker.error.connect(self._on_script_error)
        self.gemini_worker.start()

    def _on_chat_status(self, msg: str):
        self.chat_status_lbl.setText(msg)
        self.chat_status_lbl.setStyleSheet(
            "color:#b45309; font-size:11px; background:transparent;"
        )

    def _on_script_done(self, text: str):
        self.btn_gen_script.setEnabled(True)
        self.script_output.setPlainText(text)
        self.chat_status_lbl.setText("✅  Tạo kịch bản thành công!")
        self.chat_status_lbl.setStyleSheet(
            "color:#15803d; font-size:14px; font-weight:600; background:transparent;"
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
            self.chat_status_lbl.setText("✅  Đã copy!")
            self.chat_status_lbl.setStyleSheet(
                "color:#15803d; font-size:11px; background:transparent;"
            )
            QTimer.singleShot(2000, self._reset_chat_status)

    def _use_for_tts(self):
        text = self.script_output.toPlainText().strip()
        if text:
            self.text_input.setPlainText(text)
            self.tabs.setCurrentIndex(1)   # index 1 = TTS tab

    # ── TTS tab handlers ───────────────────────────────────────────
    def _all_styles(self) -> list[dict]:
        """Trả về toàn bộ styles: built-in + custom."""
        built = [
            {"name": "🎯  Nghiêm túc", "prompt": DEFAULT_PROMPT,       "creative": False, "temperature": 0.3},
            {"name": "😄  Hài hước",   "prompt": DEFAULT_PROMPT_FUNNY,  "creative": True,  "temperature": 0.7},
        ]
        custom = []
        for s in self.settings.get("custom_styles", []):
            icon = s.get("icon", "")
            name = s.get("name", "")
            prompt = s.get("prompt", "")
            if not name or not prompt:
                continue  # bỏ qua entry hỏng
            custom.append({
                "name": f"{icon}  {name}" if icon else name,
                "prompt": prompt,
                "creative": s.get("creative", False),
                "temperature": s.get(
                    "temperature", 0.7 if s.get("creative", False) else 0.3
                ),
            })
        return built + custom

    def _find_active_style_name(self, current_prompt: str) -> str:
        for s in self._all_styles():
            if s["prompt"] == current_prompt:
                return s["name"]
        return "🎯  Nghiêm túc"

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
                self._apply_prompt_btn_styles(name)
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

    def _rebuild_style_buttons(self):
        """Gọi sau khi Settings saved để sync custom styles."""
        current_prompt = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
        active_name    = self._find_active_style_name(current_prompt)
        self._build_style_buttons(self._seg_layout, active_name)
        self._sync_creativity_control(self.settings.get("enhance_style_temperature", 0.3))

    @staticmethod
    def _tier_label(temperature: float) -> str:
        """Trả về nhãn mức độ sáng tạo: chỉ báo khi khóa nội dung."""
        if temperature <= 0.0:
            return "🔒 Khóa nội dung"
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

    def _open_voices_settings(self):
        """Mở Settings dialog và tự nhảy sang tab Voices."""
        dlg = SettingsDialog(self.settings, self._parent_ref)
        dlg._switch(2)   # index 2 = Voices
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            self._voice_name_lbl.setText(
                self.settings.get("selected_voice_name", "Adam")
            )
            self._rebuild_style_buttons()
            self._refresh_credits()

    def _check_update(self):
        self._updater = UpdateChecker()
        self._updater.update_found.connect(self._on_update_found)
        self._updater.start()

    def _manual_check_update(self):
        self._btn_check_update.setEnabled(False)
        self._btn_check_update.setText("Checking...")
        self._manual_updater = UpdateChecker()
        self._manual_updater.update_found.connect(self._on_manual_update_found)
        self._manual_updater.no_update.connect(self._on_manual_no_update)
        self._manual_updater.error.connect(self._on_manual_update_error)
        self._manual_updater.finished.connect(self._reset_update_button)
        self._manual_updater.start()

    def _reset_update_button(self):
        self._btn_check_update.setEnabled(True)
        self._btn_check_update.setText("Update")

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

    def _on_update_found(self, version: str, url: str):
        self._update_url = url
        self._banner_text.setText(f"Có bản cập nhật v{version} — nhấn để tải về")
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
        self._dl.start()

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

            script = f"""#!/bin/bash
# Hedra Studio auto-update script v3
DMG="{file_path}"
APP_DEST="{app_dest}"
APP_PID={current_pid}
MNT="/tmp/hedrastudio_mnt"
LOG="/tmp/hedra_update.log"

echo "$(date): Starting update v3" > "$LOG"
echo "DMG: $DMG" >> "$LOG"
echo "Dest: $APP_DEST" >> "$LOG"
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

# Mở app mới — dùng open -n để force launch instance mới (không reuse cached)
echo "$(date): Launching new app..." >> "$LOG"
open -n "$APP_DEST"
sleep 2
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
        el_keys    = self.settings.get("el_api_keys", [])
        genmax_key = self.settings.get("genmax_api_key", "")
        has_el  = bool(el_keys)
        has_gm  = bool(genmax_key)
        if not has_el and not has_gm:
            self.credits_lbl.setText("⚠️  Chưa có TTS API key — vào Settings")
            return
        self.credits_lbl.setText("Credits: đang tải...")
        self._credits_worker = _CreditsChecker(el_keys, genmax_key)
        self._credits_worker.done.connect(self.credits_lbl.setText)
        self._credits_worker.start()

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
                                "🎙 GenMax API Key (rẻ hơn, khuyến nghị)\n"
                                "  hoặc\n"
                                "🔑 ElevenLabs API Key\n\n"
                                "📌 Vào Settings → tab API Keys để thêm.")
            return

        filename = self.filename_input.text().strip()
        if not filename:
            QMessageBox.warning(self, "Thiếu tên file", "Nhập tên file trước khi generate nhé!")
            self.filename_input.setFocus()
            return
        speed = self.slider.value() / 10
        if hasattr(self, "creativity_slider"):
            t = self.creativity_slider.value() / 100.0
            self.settings["enhance_style_temperature"] = t
            self.settings["enhance_style_creative"] = t >= 0.5
            save_settings(self.settings)
        self.btn_gen.setEnabled(False)

        # Nếu đã có preview text (user đã xem trước) → dùng luôn, không enhance lại
        preview_text = getattr(self, "_enhanced_cache", "").strip()
        if preview_text:
            self.worker = _TTSOnlyWorker(preview_text, speed,
                                         filename.replace(" ", "_"), self.settings)
        else:
            # Chưa preview → enhance + TTS như cũ
            self.worker = Worker(text, speed, filename.replace(" ", "_"), self.settings)

        self.worker.status.connect(self._on_tts_status)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    # ── Preview handlers ──────────────────────────────────────────────
    def _do_preview(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Paste kịch bản vào trước nhé!")
            return
        has_ai = bool(self.settings.get("ds_api_key") or self.settings.get("gemini_api_key"))
        if not has_ai:
            QMessageBox.warning(self, "Thiếu AI Key",
                                "Cần API key AI để xử lý kịch bản:\n\n"
                                "🆓 Gemini API Key (miễn phí — khuyến nghị)\n"
                                "   hoặc\n"
                                "🤖 DeepSeek API Key\n\n"
                                "📌 Vào Settings → tab API Keys để thêm.")
            return
        self._btn_preview.setEnabled(False)
        self._btn_preview.setText("⏳  Đang xử lý...")
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
        self._preview_worker.start()

    def _on_preview_done(self, enhanced: str):
        self._enhanced_cache = enhanced
        self.preview_text.setPlainText(enhanced)
        self._preview_status.setText("✅  Xem xong — chỉnh sửa nếu cần rồi nhấn Tạo Giọng Đọc")
        self._preview_status.setStyleSheet(
            "font-size:11px;color:#15803d;background:transparent;border:none;"
        )
        self._btn_preview.setEnabled(True)
        self._btn_preview.setText("✨  Xem kịch bản")
        # Khi user chỉnh sửa preview → cập nhật cache
        try:
            self.preview_text.textChanged.disconnect()
        except TypeError:
            pass
        self.preview_text.textChanged.connect(
            lambda: setattr(self, "_enhanced_cache", self.preview_text.toPlainText())
        )

    def _on_preview_error_msg(self, msg: str):
        self._preview_status.setText(f"❌  {msg}")
        self._preview_status.setStyleSheet(
            "font-size:11px;color:#dc2626;background:transparent;border:none;"
        )
        self._btn_preview.setEnabled(True)
        self._btn_preview.setText("✨  Xem kịch bản")

    def _on_script_changed(self):
        """Khi sửa kịch bản gốc → reset preview để tránh gen sai."""
        if getattr(self, "_enhanced_cache", ""):
            self._enhanced_cache = ""
            self.preview_text.setPlainText("")
            self._preview_status.setText("⚠️  Kịch bản đã thay đổi — nhấn lại \"Xem kịch bản\" để cập nhật")
            self._preview_status.setStyleSheet(
                "font-size:11px;color:#b45309;background:transparent;border:none;"
            )

    def _on_tts_status(self, msg: str):
        self.tts_status_lbl.setText(msg)
        self.tts_status_lbl.setStyleSheet(
            "color:#b45309; font-size:11px; background:transparent;"
        )

    def _on_done(self, path: str):
        self.btn_gen.setEnabled(True)
        self.tts_status_lbl.setText("✅  Tạo audio thành công!")
        self.tts_status_lbl.setStyleSheet(
            "color:#15803d; font-size:14px; font-weight:600; background:transparent;"
        )
        # Lưu path và hiện nút 📂 — user chủ động mở thư mục nếu muốn
        self._last_audio_path = path
        self._btn_play_audio.setVisible(True)
        self._btn_open_folder.setVisible(True)
        # Disconnect cũ an toàn — tránh TypeError nếu chưa có connection nào
        try:
            self._btn_open_folder.clicked.disconnect()
        except TypeError:
            pass
        self._btn_open_folder.clicked.connect(lambda: reveal_file(self._last_audio_path))
        self._refresh_credits()
        QTimer.singleShot(4000, self._reset_tts_status)

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
        self.tts_status_lbl.setText("Đang phát audio...")
        self.tts_status_lbl.setStyleSheet(
            "color:#15803d; font-size:11px; background:transparent;"
        )

    def _on_output_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState and hasattr(self, "_btn_play_audio"):
            self._btn_play_audio.setText("Phát")

    def _reset_tts_status(self):
        if self._output_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        self.tts_status_lbl.setText("Sẵn sàng")
        self.tts_status_lbl.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:11px; background:transparent;"
        )

    def _on_error(self, msg: str):
        self.btn_gen.setEnabled(True)
        self.tts_status_lbl.setText("Có lỗi xảy ra")
        self.tts_status_lbl.setStyleSheet(
            "color:#dc2626; font-size:11px; background:transparent;"
        )
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
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            try:
                save_settings(self.settings)
            except Exception as e:
                QMessageBox.warning(self, "Lỗi lưu cài đặt", str(e))
            try:
                self._refresh_credits()
                self._rebuild_style_buttons()
                self._sync_creativity_control(self.settings.get("enhance_style_temperature", 0.3))
                self._voice_name_lbl.setText(
                    self.settings.get("selected_voice_name", "Adam")
                )
            except Exception:
                pass  # Không crash app nếu refresh lỗi

    # ── Tab: Auto Video ────────────────────────────────────────────────

    def _build_auto_video_tab(self) -> QWidget:
        outer = QWidget()
        outer.setStyleSheet(f"background:{BG};")
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        # ── Input card ────────────────────────────────────────────────
        input_card, input_vbox = self._card()
        layout.addWidget(input_card)

        self._card_row(input_vbox, "Link bài báo", self._av_url_field(), last=False)
        self._card_row(input_vbox, "Hoặc paste text", self._av_text_field(), last=True)

        # ── Voice provider row ──────────────────────────────────────────
        voice_card, voice_vbox = self._card()
        layout.addWidget(voice_card)

        from PyQt6.QtWidgets import QButtonGroup, QRadioButton
        prov_widget = QWidget()
        prov_h = QHBoxLayout(prov_widget)
        prov_h.setContentsMargins(16, 10, 16, 10)
        prov_h.setSpacing(16)
        self._av_prov_group = QButtonGroup(self)
        for i, label in enumerate(["LucyLab", "GenMax"]):
            rb = QRadioButton(label)
            rb.setStyleSheet(f"color:{TEXT};background:transparent;font-size:13px;")
            self._av_prov_group.addButton(rb, i)
            prov_h.addWidget(rb)
        prov_h.addStretch()
        cur_prov = self.settings.get("av_tts_provider", "lucylab")
        self._av_prov_group.button(0 if cur_prov == "lucylab" else 1).setChecked(True)
        self._av_prov_group.idToggled.connect(self._av_on_provider_change)
        self._card_row(voice_vbox, "TTS Provider", prov_widget, last=False)

        self._av_gm_widget = QWidget()
        gm_h = QHBoxLayout(self._av_gm_widget)
        gm_h.setContentsMargins(0, 0, 0, 0)
        gm_h.setSpacing(8)
        self._av_gm_combo = QComboBox()
        self._av_gm_combo.setMinimumWidth(200)
        self._av_gm_combo.setFixedHeight(28)
        self._av_gm_combo.setStyleSheet(
            f"QComboBox{{background:white;border:1.5px solid {BORDER};"
            f"border-radius:6px;padding:0 10px;color:{TEXT};font-size:12px;}}"
            f"QComboBox:hover{{border-color:#a0aec0;}}"
            f"QComboBox:focus{{border-color:{ACCENT};}}"
            f"QComboBox::drop-down{{border:none;width:20px;}}"
            f"QComboBox::down-arrow{{width:10px;height:10px;}}"
            f"QComboBox QAbstractItemView{{background:white;border:1px solid {BORDER};"
            f"border-radius:6px;selection-background-color:#eff6ff;"
            f"selection-color:{TEXT};font-size:12px;padding:4px;}}")
        self._av_gm_combo.currentIndexChanged.connect(self._av_on_voice_change)
        gm_h.addWidget(self._av_gm_combo)

        btn_add = QPushButton("＋ Thêm giọng")
        btn_add.setFixedHeight(28)
        btn_add.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;"
            f"border-radius:6px;padding:0 10px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}")
        btn_add.clicked.connect(self._av_add_voice)
        gm_h.addWidget(btn_add)

        btn_del = QPushButton("Xoá")
        btn_del.setFixedHeight(28)
        btn_del.setStyleSheet(
            f"QPushButton{{background:white;color:#e0303a;border:1px solid #e0303a;"
            f"border-radius:6px;padding:0 10px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:#fff0f0;}}")
        btn_del.clicked.connect(self._av_del_voice)
        gm_h.addWidget(btn_del)
        gm_h.addStretch()

        self._card_row(voice_vbox, "Giọng GenMax", self._av_gm_widget, last=True)
        self._av_refresh_voice_combo()
        self._av_gm_widget.setVisible(cur_prov == "genmax")

        # ── Status / log ──────────────────────────────────────────────
        self._av_status = QLabel("Nhập link hoặc paste nội dung rồi nhấn Generate")
        self._av_status.setStyleSheet(
            f"color:{TEXT_MUTE}; font-size:12px; background:transparent;"
        )
        self._av_status.setWordWrap(True)
        layout.addWidget(self._av_status)

        self._av_log = QTextEdit()
        self._av_log.setReadOnly(True)
        self._av_log.setFixedHeight(120)
        self._av_log.setStyleSheet(
            f"QTextEdit{{background:#f5f5f7;border:1px solid #e5e5ea;"
            f"border-radius:8px;color:{TEXT_MUTE};font-size:11px;"
            f"font-family:Menlo,Monaco,monospace;padding:8px;}}"
        )
        self._av_log.setVisible(False)
        layout.addWidget(self._av_log)

        # ── Progress section ──────────────────────────────────────────
        from PyQt6.QtWidgets import QProgressBar
        # Step label (ví dụ: "Bước 3/8 — Fetch og:image")
        self._av_step_label = QLabel("")
        self._av_step_label.setStyleSheet(
            f"color:{TEXT_MUTE};font-size:11px;background:transparent;")
        self._av_step_label.setVisible(False)
        layout.addWidget(self._av_step_label)

        # Progress bar + % label cạnh nhau
        prog_row = QWidget()
        prog_h = QHBoxLayout(prog_row)
        prog_h.setContentsMargins(0, 0, 0, 0)
        prog_h.setSpacing(8)

        self._av_progress = QProgressBar()
        self._av_progress.setRange(0, 100)
        self._av_progress.setValue(0)
        self._av_progress.setFixedHeight(10)
        self._av_progress.setTextVisible(False)
        self._av_progress.setStyleSheet(
            "QProgressBar{background:#e5e5ea;border:none;border-radius:5px;}"
            f"QProgressBar::chunk{{background:{ACCENT};border-radius:5px;}}")
        prog_h.addWidget(self._av_progress)

        self._av_pct_label = QLabel("0%")
        self._av_pct_label.setFixedWidth(36)
        self._av_pct_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._av_pct_label.setStyleSheet(
            f"color:{TEXT_MUTE};font-size:11px;font-weight:600;background:transparent;")
        prog_h.addWidget(self._av_pct_label)

        prog_row.setVisible(False)
        self._av_prog_row = prog_row
        layout.addWidget(prog_row)

        # ── Result card (ẩn lúc đầu) ─────────────────────────────────
        self._av_result_card, av_result_vbox = self._card()
        self._av_result_card.setVisible(False)
        self._av_video_path_lbl = QLabel("—")
        self._av_video_path_lbl.setStyleSheet(
            f"color:{TEXT_MUTE};font-size:11px;background:transparent;"
        )
        self._av_video_path_lbl.setWordWrap(True)
        self._card_row(av_result_vbox, "Video output", self._av_video_path_lbl, last=False)

        self._av_btn_open = QPushButton("📂  Open in Finder")
        self._av_btn_open.setFixedHeight(32)
        self._av_btn_open.setStyleSheet(
            f"QPushButton{{border:1px solid {BORDER};border-radius:8px;"
            f"padding:0 14px;background:white;color:{TEXT};font-size:12px;}}"
            f"QPushButton:hover{{background:#f5f5f7;}}"
        )
        self._av_btn_open.clicked.connect(self._av_open_finder)
        btn_row_w = QWidget()
        btn_row_h = QHBoxLayout(btn_row_w)
        btn_row_h.setContentsMargins(16, 8, 16, 12)
        btn_row_h.addWidget(self._av_btn_open)
        btn_row_h.addStretch()
        av_result_vbox.addWidget(btn_row_w)
        layout.addWidget(self._av_result_card)

        layout.addStretch()

        # ── Generate button ───────────────────────────────────────────
        self._av_gen_btn = QPushButton("✨  Generate Video")
        self._av_gen_btn.setFixedHeight(44)
        self._av_gen_btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:white;border:none;"
            f"border-radius:10px;font-size:14px;font-weight:700;padding:0 28px;}}"
            f"QPushButton:hover{{background:{ACCENT_HV};}}"
            f"QPushButton:pressed{{background:#0060cc;}}"
            f"QPushButton:disabled{{background:#a8d0fb;color:white;}}"
        )
        self._av_gen_btn.clicked.connect(self._av_on_generate)
        layout.addWidget(self._av_gen_btn)

        # Workers
        self._av_script_worker = None
        self._av_engine_worker = None

        return outer

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

    def _av_on_generate(self):
        url  = self._av_url.text().strip()
        text = self._av_text.toPlainText().strip()
        inp  = url or text
        if not inp:
            self._av_set_status("Nhập link hoặc paste nội dung trước.", error=True)
            return

        # Check có ít nhất 1 API key (Claude / DeepSeek / Gemini)
        has_key = any([
            self.settings.get("claude_api_key", "").strip(),
            self.settings.get("ds_api_key", "").strip(),
            self.settings.get("gemini_api_key", "").strip(),
        ])
        if not has_key:
            self._av_set_status("Chưa có API key — vào Settings nhập Claude / DeepSeek / Gemini.", error=True)
            return

        self._av_gen_btn.setEnabled(False)
        self._av_gen_btn.setText("⏳  Đang tạo…")
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
        self._av_script_worker.start()

    def _av_on_script_done(self, script_path: str):
        self._av_set_status("Script xong — đang render video…")
        self._av_engine_worker = AutoVideoEngineWorker(script_path)
        self._av_engine_worker.log_line.connect(self._av_append_log)
        self._av_engine_worker.progress.connect(self._av_on_progress)
        self._av_engine_worker.finished.connect(self._av_on_video_done)
        self._av_engine_worker.error.connect(self._av_on_error)
        self._av_engine_worker.start()

    def _av_on_video_done(self, video_path: str):
        self._av_gen_btn.setEnabled(True)
        self._av_gen_btn.setText("✨  Generate Video")
        self._av_on_progress(100)
        self._av_prog_row.setVisible(False)
        self._av_step_label.setVisible(False)
        self._av_set_status("✅  Hoàn thành!")
        self._av_video_path = video_path
        self._av_video_path_lbl.setText(video_path or "Không tìm thấy video.mp4")
        self._av_result_card.setVisible(True)

    def _av_on_error(self, msg: str):
        self._av_gen_btn.setEnabled(True)
        self._av_gen_btn.setText("✨  Generate Video")
        self._av_prog_row.setVisible(False)
        self._av_step_label.setVisible(False)
        self._av_set_status(f"❌  {msg}", error=True)

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

    def _av_open_finder(self):
        import subprocess, os
        path = getattr(self, "_av_video_path", "")
        if path:
            folder = os.path.dirname(path)
            subprocess.run(["open", folder], check=False)

    def _av_on_provider_change(self, btn_id: int, checked: bool):
        if not checked:
            return
        prov = "lucylab" if btn_id == 0 else "genmax"
        self.settings["av_tts_provider"] = prov
        save_settings(self.settings)
        self._av_gm_widget.setVisible(prov == "genmax")

    def _av_refresh_voice_combo(self):
        self._av_gm_combo.blockSignals(True)
        self._av_gm_combo.clear()
        voices = self.settings.get("av_genmax_voices", [])
        for v in voices:
            self._av_gm_combo.addItem(v["name"], v["id"])
        sel = self.settings.get("av_genmax_voice_id", "")
        for i in range(self._av_gm_combo.count()):
            if self._av_gm_combo.itemData(i) == sel:
                self._av_gm_combo.setCurrentIndex(i)
                break
        self._av_gm_combo.blockSignals(False)

    def _av_on_voice_change(self, idx: int):
        voice_id = self._av_gm_combo.itemData(idx) or ""
        self.settings["av_genmax_voice_id"] = voice_id
        save_settings(self.settings)

    def _av_add_voice(self):
        from PyQt6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Thêm giọng GenMax")
        dlg.setMinimumWidth(320)
        form = QFormLayout(dlg)
        id_edit = QLineEdit()
        id_edit.setPlaceholderText("Voice ID từ GenMax")
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Tên hiển thị")
        form.addRow("Voice ID:", id_edit)
        form.addRow("Tên giọng:", name_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vid = id_edit.text().strip()
            name = name_edit.text().strip() or vid
            if vid:
                voices = self.settings.get("av_genmax_voices", [])
                if not any(v["id"] == vid for v in voices):
                    voices.append({"id": vid, "name": name})
                    self.settings["av_genmax_voices"] = voices
                    self.settings["av_genmax_voice_id"] = vid
                    save_settings(self.settings)
                    self._av_refresh_voice_combo()

    def _av_del_voice(self):
        idx = self._av_gm_combo.currentIndex()
        if idx < 0:
            return
        vid = self._av_gm_combo.itemData(idx)
        voices = [v for v in self.settings.get("av_genmax_voices", []) if v["id"] != vid]
        self.settings["av_genmax_voices"] = voices
        if self.settings.get("av_genmax_voice_id") == vid:
            self.settings["av_genmax_voice_id"] = voices[0]["id"] if voices else ""
        save_settings(self.settings)
        self._av_refresh_voice_combo()

    def _av_on_progress(self, val: int):
        self._av_progress.setValue(val)
        self._av_pct_label.setText(f"{val}%")

    def update_settings(self, settings: dict):
        self.settings = settings
        self._refresh_credits()

    def _av_url_field(self):
        self._av_url = QLineEdit()
        self._av_url.setPlaceholderText("https://vnexpress.net/bai-viet...")
        self._av_url.returnPressed.connect(self._av_on_generate)
        return self._av_url

    def _av_text_field(self):
        self._av_text = QTextEdit()
        self._av_text.setPlaceholderText("Paste nội dung bài báo vào đây…\nAI sẽ tự tóm tắt và tạo script.")
        self._av_text.setFixedHeight(100)
        return self._av_text

    def _av_on_generate(self):
        url  = self._av_url.text().strip()
        text = self._av_text.toPlainText().strip()
        inp  = url or text
        if not inp:
            self._av_set_status("Nhập link hoặc paste nội dung trước.", error=True); return
        has_key = any([
            self.settings.get("claude_api_key", "").strip(),
            self.settings.get("ds_api_key", "").strip(),
            self.settings.get("gemini_api_key", "").strip(),
        ])
        if not has_key:
            self._av_set_status("Chưa có API key — vào Settings nhập Claude / DeepSeek / Gemini.", error=True); return
        self._av_gen_btn.setEnabled(False)
        self._av_gen_btn.setText("⏳  Đang tạo…")
        self._av_log.clear(); self._av_log.setVisible(True)
        self._av_progress.setValue(0); self._av_progress.setVisible(True)
        self._av_result_card.setVisible(False)
        self._av_script_worker = AutoScriptWorker(inp)
        self._av_script_worker.progress.connect(self._av_set_status)
        self._av_script_worker.finished.connect(self._av_on_script_done)
        self._av_script_worker.error.connect(self._av_on_error)
        self._av_script_worker.start()

    def _av_on_script_done(self, script_path: str):
        self._av_set_status("Script xong — đang render video…")
        self._av_engine_worker = AutoVideoEngineWorker(script_path)
        self._av_engine_worker.log_line.connect(self._av_append_log)
        self._av_engine_worker.progress.connect(self._av_progress.setValue)
        self._av_engine_worker.finished.connect(self._av_on_video_done)
        self._av_engine_worker.error.connect(self._av_on_error)
        self._av_engine_worker.start()

    def _av_on_video_done(self, video_path: str):
        self._av_gen_btn.setEnabled(True); self._av_gen_btn.setText("✨  Generate Video")
        self._av_progress.setValue(100); self._av_set_status("✅  Hoàn thành!")
        self._av_video_path = video_path
        self._av_video_path_lbl.setText(video_path or "Không tìm thấy video.mp4")
        self._av_result_card.setVisible(True)

    def _av_on_error(self, msg: str):
        self._av_gen_btn.setEnabled(True); self._av_gen_btn.setText("✨  Generate Video")
        self._av_progress.setVisible(False); self._av_set_status(f"❌  {msg}", error=True)

    def _av_set_status(self, msg: str, error: bool = False):
        color = "#e0303a" if error else TEXT_MUTE
        self._av_status.setText(msg)
        self._av_status.setStyleSheet(f"color:{color};font-size:12px;background:transparent;")

    def _av_append_log(self, line: str):
        self._av_log.append(line)

    def _av_open_finder(self):
        import os
        path = getattr(self, "_av_video_path", "")
        if path:
            subprocess.run(["open", os.path.dirname(path)], check=False)


