import os
import re
import webbrowser

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QFrame, QScrollArea, QStackedWidget,
    QFileDialog, QMessageBox, QSizePolicy, QSpacerItem,
    QListWidget, QListWidgetItem, QComboBox, QGridLayout,
    QWidget, QSlider,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QFont, QIcon, QColor

from app_constants import (
    DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY, GEMINI_CHAT_PROMPT,
    VOICE_ID, PROMPTS, PROMPT_TEMPLATES, VERSION,
    BG, SURFACE, BORDER, TEXT, TEXT_MUTE, ACCENT, ACCENT_HV, SEG_BG,
)
from app_utils import DEFAULT_OUT, save_settings, DATA_DIR, SETTINGS_FILE
from app_workers import _CreditsChecker, UpdateChecker, VoiceFetcher, AudioPreviewDownloader
from app_dialogs import AddStyleDialog, PromptWizardDialog, FeedbackDialog
from voice_library import VoiceLibraryDialog

# ── Helper: null widget dùng làm fallback khi widget chưa được tạo ──
class _NullEdit:
    """QLineEdit/QTextEdit stub — trả về chuỗi rỗng, tránh AttributeError."""
    def text(self) -> str:
        return ""

    def toPlainText(self) -> str:
        return ""


class SettingsDialog(QDialog):
    # Màu sidebar kiểu macOS System Settings
    _SB_BG       = "#f0f0f5"
    _SB_ACTIVE   = "#ffffff"
    _SB_TEXT     = "#1d1d1f"
    _SB_MUTE     = "#6e6e73"
    _GROUP_BG    = "#ffffff"
    _GROUP_BORDER= "#e5e5ea"
    _LABEL_W     = 140          # chiều rộng cột label trong form

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()
        self.setWindowTitle("Settings")
        self.setMinimumSize(700, 540)
        self.resize(820, 700)
        # Voice selection state (edited in dialog, saved on accept)
        self._sel_voice_id   = self.settings.get("selected_voice_id") or VOICE_ID
        self._sel_voice_name = self.settings.get("selected_voice_name") or "Adam"
        self._voice_rows: list[tuple] = []        # (widget, voice_id) for API voices
        self._voice_rows_lang: list[tuple] = []   # (widget, voice_id, lang, name)
        self._lang_chips: dict = {}
        self._active_lang_filter = "all"
        self._build()

    # ── Helper: tạo một "grouped section" kiểu macOS ──────────────
    def _group(self, title: str = "") -> tuple:
        """Trả về (outer_widget, form_layout) để thêm rows vào."""
        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget{{background:{self._GROUP_BG};"
            f"border:1px solid {self._GROUP_BORDER};"
            f"border-radius:10px;}}"
        )
        vbox = QVBoxLayout(outer)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        if title:
            hdr = QLabel(title)
            hdr.setStyleSheet(
                "QLabel{font-size:11px;font-weight:600;color:#6e6e73;"
                "background:transparent;border:none;"
                "padding:10px 16px 6px 16px;}"
            )
            vbox.addWidget(hdr)
        return outer, vbox

    def _row(self, container_layout, label: str, widget: QWidget,
             note: str = "", last: bool = False):
        """Thêm một form row vào group: label trái + widget phải."""
        row_w = QWidget()
        row_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        h = QHBoxLayout(row_w)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(12)

        lbl = QLabel(label)
        lbl.setFixedWidth(self._LABEL_W)
        lbl.setStyleSheet(
            "QLabel{font-size:13px;color:#1d1d1f;"
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
                "QLabel{font-size:11px;color:#6e6e73;"
                "background:transparent;border:none;}"
            )
            n.setWordWrap(True)
            right.addWidget(n)
        h.addLayout(right)
        container_layout.addWidget(row_w)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            "QLabel{font-size:11px;font-weight:600;color:#6e6e73;"
            "padding:16px 0 6px 0;"
            "background:transparent;border:none;}"
        )
        return lbl

    # ── Hướng dẫn lấy API key ─────────────────────────────────────
    def _show_api_guide(self, service: str):
        """Dialog hướng dẫn từng bước lấy API key theo service."""
        _GUIDES = {
            "elevenlabs": {
                "title":     "Hướng dẫn lấy ElevenLabs API Key",
                "subtitle":  "Đăng ký qua link này để hỗ trợ Hedra Studio 🙏",
                "url":       "https://try.elevenlabs.io/rinor1xaj4ze",
                "url_label": "🔑  Mở trang đăng ký ElevenLabs",
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
                     "✅ App sẽ dùng GenMax làm TTS chính,\n"
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
        v.setContentsMargins(20, 16, 20, 20)
        v.setSpacing(0)

        # ── Helper: section header có nút hướng dẫn lấy API key ─────
        def _api_guide_btn(label: str, is_ref: bool = False) -> QPushButton:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            accent = "#0071e3"
            if is_ref:
                btn.setStyleSheet(
                    f"QPushButton{{font-size:11px;font-weight:600;color:{accent};"
                    "background:#e8f0fd;border:1px solid #c5d9f8;border-radius:6px;"
                    "padding:0 10px;}}"
                    f"QPushButton:hover{{background:#dce9fd;border-color:{accent};}}"
                    "QPushButton:pressed{background:#cfe0fc;}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton{{font-size:11px;color:{accent};"
                    "background:transparent;border:none;padding:0 4px;}}"
                    "QPushButton:hover{text-decoration:underline;}"
                    f"QPushButton:pressed{{color:#005bb5;}}"
                )
            return btn

        def _svc_header(title: str, btn: QPushButton) -> QWidget:
            w = QWidget()
            w.setStyleSheet("background:transparent;border:none;")
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            h.addWidget(self._section_label(title))
            h.addStretch()
            h.addWidget(btn)
            return w

        # ── Group: GenMax (TTS chính — rẻ hơn ElevenLabs) ──────────
        gm_btn = _api_guide_btn("📖  Hướng dẫn lấy API key  →", is_ref=True)
        gm_btn.setToolTip("Xem hướng dẫn đăng ký & lấy API key GenMax")
        gm_btn.clicked.connect(lambda: self._show_api_guide("genmax"))
        v.addWidget(_svc_header("GenMax  (TTS chính — rẻ hơn ElevenLabs)", gm_btn))
        grp_gm, glay_gm = self._group()
        self.genmax_key = QLineEdit(self.settings.get("genmax_api_key", ""))
        self.genmax_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.genmax_key.setPlaceholderText("sk_...")
        self.genmax_key.setStyleSheet(
            "QLineEdit{background:transparent;border:none;font-size:13px;}"
        )
        self._row(glay_gm, "API Key", self.genmax_key,
                  "Ưu tiên dùng GenMax — tự động fallback sang ElevenLabs nếu lỗi", last=True)
        v.addWidget(grp_gm)

        # ── Group: ElevenLabs ────────────────────────────────────────
        el_btn = _api_guide_btn("📖  Hướng dẫn lấy API key  →", is_ref=True)
        el_btn.setToolTip("Xem hướng dẫn từng bước đăng ký & lấy API key ElevenLabs")
        el_btn.clicked.connect(lambda: self._show_api_guide("elevenlabs"))
        v.addWidget(_svc_header("ElevenLabs", el_btn))
        grp, glay = self._group()
        self.el_keys = QTextEdit()
        self.el_keys.setPlaceholderText("sk_abc123...\nsk_def456...\nsk_ghi789...")
        self.el_keys.setFixedHeight(72)
        self.el_keys.setPlainText("\n".join(self.settings.get("el_api_keys", [])[:3]))
        self.el_keys.setStyleSheet(
            "QTextEdit{font-family:monospace;font-size:11px;"
            "background:transparent;border:none;}"
        )
        self._row(glay, "API Keys", self.el_keys,
                  "Tối đa 3 keys — mỗi key 1 dòng — tự xoay khi hết credit", last=True)
        v.addWidget(grp)

        # ── Group: Gemini (Miễn phí — Khuyến nghị) ─────────────────
        gm_btn = _api_guide_btn("📖  Hướng dẫn lấy API key  →")
        gm_btn.clicked.connect(lambda: self._show_api_guide("gemini"))
        v.addWidget(_svc_header("AI Enhance  —  Gemini  🆓 Miễn phí (Khuyến nghị)", gm_btn))
        _hint_gemini = QLabel("  → Người mới: tạo tài khoản Google AI Studio → lấy API key miễn phí → dán vào đây")
        _hint_gemini.setStyleSheet("font-size:11px;color:#6e6e73;background:transparent;border:none;")
        _hint_gemini.setWordWrap(True)
        v.addWidget(_hint_gemini)
        grp3, glay3 = self._group()
        self.gemini_key = QLineEdit(self.settings.get("gemini_api_key", ""))
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key.setPlaceholderText("AIza...")
        self.gemini_key.setStyleSheet(
            "QLineEdit{background:transparent;border:none;font-size:13px;}"
        )
        self._row(glay3, "API Key", self.gemini_key, last=True)
        v.addWidget(grp3)

        # ── Group: DeepSeek (Trả phí — Chất lượng cao hơn) ─────────
        ds_btn = _api_guide_btn("📖  Hướng dẫn lấy API key  →")
        ds_btn.clicked.connect(lambda: self._show_api_guide("deepseek"))
        v.addWidget(_svc_header("AI Enhance  —  DeepSeek  💳 Trả phí", ds_btn))
        _hint_ds = QLabel("  → Đã có Gemini rồi? Nếu muốn chất lượng cao hơn thì dùng DeepSeek — tạo tài khoản DeepSeek → nạp credit → lấy key")
        _hint_ds.setStyleSheet("font-size:11px;color:#6e6e73;background:transparent;border:none;")
        _hint_ds.setWordWrap(True)
        v.addWidget(_hint_ds)
        grp2, glay2 = self._group()
        self.ds_key = QLineEdit(self.settings.get("ds_api_key", ""))
        self.ds_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ds_key.setPlaceholderText("sk-...")
        self.ds_key.setStyleSheet(
            "QLineEdit{background:transparent;border:none;font-size:13px;}"
        )
        self._row(glay2, "API Key", self.ds_key, last=True)
        v.addWidget(grp2)

        # ── Group: Claude (Auto Video) ────────────────────────────────
        v.addWidget(self._section_label("Claude  (Auto Video — Script Generation)"))
        grp_claude, glay_claude = self._group()
        self.claude_key = QLineEdit(self.settings.get("claude_api_key", ""))
        self.claude_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.claude_key.setPlaceholderText("sk-ant-...")
        self.claude_key.setStyleSheet(
            "QLineEdit{background:transparent;border:none;font-size:13px;}"
        )
        self._row(glay_claude, "API Key", self.claude_key)
        self.claude_model = QComboBox()
        self.claude_model.addItems([
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20241022",
        ])
        self.claude_model.setCurrentText(
            self.settings.get("claude_model", "claude-3-5-haiku-20241022")
        )
        self._row(glay_claude, "Model", self.claude_model, last=True)
        v.addWidget(grp_claude)

        v.addStretch()
        return page

    def _page_prompts(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(0)

        # ══ Sub-tab switcher ══════════════════════════════════════
        outer.addSpacing(4)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.setContentsMargins(0, 0, 0, 0)

        self._prompts_stacked = QStackedWidget()
        self._prompts_stacked.setStyleSheet("QStackedWidget{background:transparent;border:none;}")

        def _subtab_style(active: bool) -> str:
            if active:
                return ("QPushButton{background:#ffffff;color:#0071e3;"
                        "border:1px solid #d2d2d7;font-size:13px;font-weight:600;"
                        "padding:7px 20px;}"
                        "QPushButton:hover{background:#f0f6ff;}"
                        "QPushButton:pressed{background:#e0edff;}")
            return ("QPushButton{background:#f5f5f7;color:#6e6e73;"
                    "border:1px solid #d2d2d7;font-size:13px;font-weight:400;"
                    "padding:7px 20px;}"
                    "QPushButton:hover{background:#ebebf0;color:#1d1d1f;}"
                    "QPushButton:pressed{background:#d8d8de;color:#1d1d1f;}")

        btn_tab_chat = QPushButton("💬  Chat → Kịch bản")
        btn_tab_chat.setFixedHeight(36)
        btn_tab_chat.setStyleSheet(
            _subtab_style(True) +
            "QPushButton{border-radius:0;border-top-left-radius:8px;"
            "border-bottom-left-radius:8px;border-right:none;}"
        )
        btn_tab_tts = QPushButton("🎙️  TTS — Enhance")
        btn_tab_tts.setFixedHeight(36)
        btn_tab_tts.setStyleSheet(
            _subtab_style(False) +
            "QPushButton{border-radius:0;border-top-right-radius:8px;"
            "border-bottom-right-radius:8px;}"
        )

        def _switch_subtab(idx: int):
            self._prompts_stacked.setCurrentIndex(idx)
            if idx == 0:
                btn_tab_chat.setStyleSheet(
                    _subtab_style(True) +
                    "QPushButton{border-radius:0;border-top-left-radius:8px;"
                    "border-bottom-left-radius:8px;border-right:none;}")
                btn_tab_tts.setStyleSheet(
                    _subtab_style(False) +
                    "QPushButton{border-radius:0;border-top-right-radius:8px;"
                    "border-bottom-right-radius:8px;}")
            else:
                btn_tab_chat.setStyleSheet(
                    _subtab_style(False) +
                    "QPushButton{border-radius:0;border-top-left-radius:8px;"
                    "border-bottom-left-radius:8px;border-right:none;}")
                btn_tab_tts.setStyleSheet(
                    _subtab_style(True) +
                    "QPushButton{border-radius:0;border-top-right-radius:8px;"
                    "border-bottom-right-radius:8px;}")

        btn_tab_chat.clicked.connect(lambda: _switch_subtab(0))
        btn_tab_tts.clicked.connect(lambda: _switch_subtab(1))
        tab_row.addWidget(btn_tab_chat)
        tab_row.addWidget(btn_tab_tts)
        tab_row.addStretch()
        outer.addLayout(tab_row)
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
        gp_card.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #d2d2d7;border-radius:10px;}"
        )
        gp_card_v = QVBoxLayout(gp_card)
        gp_card_v.setContentsMargins(0, 0, 0, 0)
        gp_card_v.setSpacing(0)

        self.gemini_prompt = QTextEdit()
        self.gemini_prompt.setPlainText(_gp_init)
        self.gemini_prompt.setReadOnly(True)
        self.gemini_prompt.setMinimumHeight(340)
        self.gemini_prompt.setStyleSheet(
            "QTextEdit{font-size:13px;color:#1d1d1f;"
            "background:transparent;border:none;padding:14px 16px;}"
        )
        gp_card_v.addWidget(self.gemini_prompt, 1)

        gp_div = QFrame(); gp_div.setFrameShape(QFrame.Shape.HLine)
        gp_div.setStyleSheet("QFrame{background:#e5e5ea;border:none;max-height:1px;margin:0;}")
        gp_card_v.addWidget(gp_div)

        gp_foot = QHBoxLayout()
        gp_foot.setContentsMargins(12, 8, 12, 8)
        gp_foot.setSpacing(8)
        btn_cancel_gp = QPushButton("↺ Về mặc định")
        btn_cancel_gp.setFixedHeight(30)
        btn_cancel_gp.setStyleSheet(
            "QPushButton{font-size:12px;color:#6e6e73;background:transparent;"
            "border:1px solid #d2d2d7;border-radius:8px;padding:0 12px;}"
            "QPushButton:hover{background:#f5f5f7;color:#1d1d1f;}"
            "QPushButton:pressed{background:#e5e5ea;}"
        )
        gp_foot.addWidget(btn_cancel_gp)
        gp_foot.addStretch()
        btn_edit_gp = QPushButton("✏️  Chỉnh sửa")
        btn_edit_gp.setFixedHeight(30)
        btn_edit_gp.setStyleSheet(
            "QPushButton{font-size:12px;font-weight:600;color:#fff;"
            "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
        )
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
                self.gemini_prompt.setStyleSheet(
                    "QTextEdit{font-size:13px;color:#1d1d1f;"
                    "background:#fff;border:none;padding:14px 16px;"
                    "selection-background-color:#bdd7ff;}"
                )
                gp_card.setStyleSheet(
                    "QFrame{background:#ffffff;border:2px solid #0071e3;border-radius:10px;}"
                )
                btn_edit_gp.setText("✅  Lưu")
                btn_edit_gp.setStyleSheet(
                    "QPushButton{font-size:12px;font-weight:600;color:#fff;"
                    "background:#15803d;border:none;border-radius:8px;padding:0 16px;}"
                    "QPushButton:hover{background:#16a34a;}"
                    "QPushButton:pressed{background:#0f6b2f;}"
                )
                btn_cancel_gp.setText("✕  Hủy")
                self.gemini_prompt.setFocus()
            else:
                # → Save
                self.settings["gemini_chat_prompt"] = self.gemini_prompt.toPlainText()
                self.gemini_prompt.setReadOnly(True)
                self.gemini_prompt.setStyleSheet(
                    "QTextEdit{font-size:13px;color:#1d1d1f;"
                    "background:transparent;border:none;padding:14px 16px;}"
                )
                gp_card.setStyleSheet(
                    "QFrame{background:#ffffff;border:1px solid #d2d2d7;border-radius:10px;}"
                )
                btn_edit_gp.setText("✏️  Chỉnh sửa")
                btn_edit_gp.setStyleSheet(
                    "QPushButton{font-size:12px;font-weight:600;color:#fff;"
                    "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
                    "QPushButton:hover{background:#0077ed;}"
                    "QPushButton:pressed{background:#005bb5;}"
                )
                btn_cancel_gp.setText("↺ Về mặc định")

        def _cancel_or_reset_gp():
            if not self.gemini_prompt.isReadOnly():
                # Đang edit → Hủy
                self.gemini_prompt.setPlainText(_gp_snapshot[0])
                self.gemini_prompt.setReadOnly(True)
                self.gemini_prompt.setStyleSheet(
                    "QTextEdit{font-size:13px;color:#1d1d1f;"
                    "background:transparent;border:none;padding:14px 16px;}"
                )
                gp_card.setStyleSheet(
                    "QFrame{background:#ffffff;border:1px solid #d2d2d7;border-radius:10px;}"
                )
                btn_edit_gp.setText("✏️  Chỉnh sửa")
                btn_edit_gp.setStyleSheet(
                    "QPushButton{font-size:12px;font-weight:600;color:#fff;"
                    "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
                    "QPushButton:hover{background:#0077ed;}"
                    "QPushButton:pressed{background:#005bb5;}"
                )
                btn_cancel_gp.setText("↺ Về mặc định")
            else:
                # Không edit → reset default
                self.gemini_prompt.setPlainText(GEMINI_CHAT_PROMPT)

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
        ep_card.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #d2d2d7;border-radius:10px;}"
        )
        ep_card_h = QHBoxLayout(ep_card)
        ep_card_h.setContentsMargins(0, 0, 0, 0)
        ep_card_h.setSpacing(0)

        # Left style tabs — compact, ngang
        ep_tab_col = QFrame()
        ep_tab_col.setFixedWidth(105)
        ep_tab_col.setStyleSheet(
            "QFrame{background:#f5f5f7;border:none;"
            "border-right:1px solid #e5e5ea;border-top-left-radius:10px;"
            "border-bottom-left-radius:10px;}"
        )
        ep_tab_v = QVBoxLayout(ep_tab_col)
        ep_tab_v.setContentsMargins(6, 10, 6, 10)
        ep_tab_v.setSpacing(4)
        self._ep_tab_layout = ep_tab_v   # lưu để _refresh_custom_styles dùng

        self._ep_style_tabs: dict[str, QPushButton] = {}
        ep_prompts_map = dict(PROMPTS)
        # Merge custom styles vào map — lưu thành instance var để _refresh_custom_styles dùng
        self._ep_prompts_map = dict(ep_prompts_map)
        for cs in self.settings.get("custom_styles", []):
            cs_name = cs.get("name", "")
            cs_prompt = cs.get("prompt", "")
            if cs_name and cs_prompt:
                label = f"{cs.get('icon', '')}  {cs_name}" if cs.get("icon") else cs_name
                self._ep_prompts_map[label] = cs_prompt
        # Temperature per built-in style (phải khớp với _all_styles())
        ep_temp_map = {
            "🎯  Nghiêm túc": 0.3,
            "😄  Hài hước":   0.7,
        }

        def _ep_tab_style(active: bool) -> str:
            if active:
                return ("QPushButton{background:#ffffff;color:#0071e3;"
                        "border:1px solid #d2d2d7;border-radius:6px;"
                        "font-size:11px;font-weight:600;padding:5px 6px;"
                        "text-align:left;}")
            return ("QPushButton{background:transparent;color:#1d1d1f;"
                    "border:none;border-radius:6px;"
                    "font-size:11px;padding:5px 6px;text-align:left;}"
                    "QPushButton:hover{background:#ebebf0;}")

        _saved_ep   = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
        _active_ep  = list(self._ep_prompts_map.keys())[0]
        for _n, _t in self._ep_prompts_map.items():
            if _t.strip() == _saved_ep.strip():
                _active_ep = _n
                break

        def _switch_ep_tab(name: str):
            for n, b in self._ep_style_tabs.items():
                b.setStyleSheet(_ep_tab_style(n == name))
            self.prompt.setPlainText(self._ep_prompts_map[name])
            # Sync temperature slider với style vừa chọn
            if hasattr(self, "_settings_temp_slider") and name in ep_temp_map:
                t = ep_temp_map[name]
                self._settings_temp_slider.setValue(int(t * 100))
                if hasattr(self, "_settings_temp_val_lbl"):
                    self._settings_temp_val_lbl.setText(f"{t:.2f}")
                self.settings["enhance_style_temperature"] = t

        for name, prompt_text in self._ep_prompts_map.items():
            tb = QPushButton(name)
            tb.setMinimumHeight(28)
            tb.setStyleSheet(_ep_tab_style(name == _active_ep))
            tb.clicked.connect(lambda _, n=name: _switch_ep_tab(n))
            ep_tab_v.addWidget(tb)
            self._ep_style_tabs[name] = tb
        ep_tab_v.addStretch()
        ep_card_h.addWidget(ep_tab_col)

        # Right: prompt + footer
        ep_right = QVBoxLayout()
        ep_right.setContentsMargins(0, 0, 0, 0)
        ep_right.setSpacing(0)

        self.prompt = QTextEdit()
        self.prompt.setPlainText(_saved_ep)
        self.prompt.setReadOnly(True)
        self.prompt.setMinimumHeight(340)
        self.prompt.setStyleSheet(
            "QTextEdit{font-size:13px;color:#1d1d1f;"
            "background:transparent;border:none;padding:14px 14px;}"
        )
        ep_right.addWidget(self.prompt, 1)

        ep_div2 = QFrame(); ep_div2.setFrameShape(QFrame.Shape.HLine)
        ep_div2.setStyleSheet("QFrame{background:#e5e5ea;border:none;max-height:1px;margin:0;}")
        ep_right.addWidget(ep_div2)

        ep_foot = QHBoxLayout()
        ep_foot.setContentsMargins(12, 8, 12, 8)
        ep_foot.setSpacing(8)
        btn_cancel_ep = QPushButton("↺ Về mặc định")
        btn_cancel_ep.setFixedHeight(30)
        btn_cancel_ep.setStyleSheet(
            "QPushButton{font-size:12px;color:#6e6e73;background:transparent;"
            "border:1px solid #d2d2d7;border-radius:8px;padding:0 12px;}"
            "QPushButton:hover{background:#f5f5f7;color:#1d1d1f;}"
            "QPushButton:pressed{background:#e5e5ea;}"
        )
        ep_foot.addWidget(btn_cancel_ep)
        ep_foot.addStretch()
        btn_edit_ep = QPushButton("✏️  Chỉnh sửa")
        btn_edit_ep.setFixedHeight(30)
        btn_edit_ep.setStyleSheet(
            "QPushButton{font-size:12px;font-weight:600;color:#fff;"
            "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
        )
        ep_foot.addWidget(btn_edit_ep)
        ep_right.addLayout(ep_foot)
        ep_card_h.addLayout(ep_right, 1)
        vt.addWidget(ep_card, 1)  # stretch → giãn theo cửa sổ

        _ep_snapshot: list[str] = [_saved_ep]

        def _toggle_edit_ep():
            if self.prompt.isReadOnly():
                _ep_snapshot[0] = self.prompt.toPlainText()
                self.prompt.setReadOnly(False)
                self.prompt.setStyleSheet(
                    "QTextEdit{font-size:13px;color:#1d1d1f;"
                    "background:#fff;border:none;padding:14px 14px;"
                    "selection-background-color:#bdd7ff;}"
                )
                ep_card.setStyleSheet(
                    "QFrame{background:#ffffff;border:2px solid #0071e3;border-radius:10px;}"
                )
                btn_edit_ep.setText("✅  Lưu")
                btn_edit_ep.setStyleSheet(
                    "QPushButton{font-size:12px;font-weight:600;color:#fff;"
                    "background:#15803d;border:none;border-radius:8px;padding:0 16px;}"
                    "QPushButton:hover{background:#16a34a;}"
                    "QPushButton:pressed{background:#0f6b2f;}"
                )
                btn_cancel_ep.setText("✕  Hủy")
                self.prompt.setFocus()
            else:
                self.settings["enhance_prompt"] = self.prompt.toPlainText()
                self.prompt.setReadOnly(True)
                self.prompt.setStyleSheet(
                    "QTextEdit{font-size:13px;color:#1d1d1f;"
                    "background:transparent;border:none;padding:14px 14px;}"
                )
                ep_card.setStyleSheet(
                    "QFrame{background:#ffffff;border:1px solid #d2d2d7;border-radius:10px;}"
                )
                btn_edit_ep.setText("✏️  Chỉnh sửa")
                btn_edit_ep.setStyleSheet(
                    "QPushButton{font-size:12px;font-weight:600;color:#fff;"
                    "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
                    "QPushButton:hover{background:#0077ed;}"
                    "QPushButton:pressed{background:#005bb5;}"
                )
                btn_cancel_ep.setText("↺ Về mặc định")

        def _cancel_or_reset_ep():
            if not self.prompt.isReadOnly():
                self.prompt.setPlainText(_ep_snapshot[0])
                self.prompt.setReadOnly(True)
                self.prompt.setStyleSheet(
                    "QTextEdit{font-size:13px;color:#1d1d1f;"
                    "background:transparent;border:none;padding:14px 14px;}"
                )
                ep_card.setStyleSheet(
                    "QFrame{background:#ffffff;border:1px solid #d2d2d7;border-radius:10px;}"
                )
                btn_edit_ep.setText("✏️  Chỉnh sửa")
                btn_edit_ep.setStyleSheet(
                    "QPushButton{font-size:12px;font-weight:600;color:#fff;"
                    "background:#0071e3;border:none;border-radius:8px;padding:0 16px;}"
                    "QPushButton:hover{background:#0077ed;}"
                    "QPushButton:pressed{background:#005bb5;}"
                )
                btn_cancel_ep.setText("↺ Về mặc định")
            else:
                self.prompt.setPlainText(DEFAULT_PROMPT)

        btn_edit_ep.clicked.connect(_toggle_edit_ep)
        btn_cancel_ep.clicked.connect(_cancel_or_reset_ep)

        # ── Temperature slider ─────────────────────────────────────
        vt.addSpacing(14)
        temp_row = QHBoxLayout()
        temp_row.setContentsMargins(0, 0, 0, 0)
        temp_row.setSpacing(10)
        temp_lbl = QLabel("Mức độ sáng tạo")
        temp_lbl.setStyleSheet(
            "QLabel{font-size:13px;font-weight:500;color:#1d1d1f;"
            "background:transparent;border:none;}"
        )
        temp_row.addWidget(temp_lbl)
        lbl_calm = QLabel("🎯 Chính xác")
        lbl_calm.setStyleSheet("QLabel{font-size:11px;color:#6e6e73;background:transparent;border:none;}")
        temp_row.addWidget(lbl_calm)
        self._settings_temp_slider = QSlider(Qt.Orientation.Horizontal)
        self._settings_temp_slider.setRange(0, 100)
        # Init từ style đang active (không phải global saved value)
        _cur_temp = ep_temp_map.get(_active_ep,
                    self.settings.get("enhance_style_temperature", 0.3))
        self._settings_temp_slider.setValue(int(_cur_temp * 100))
        self._settings_temp_slider.setFixedHeight(20)
        self._settings_temp_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#e5e5ea;border-radius:2px;}"
            "QSlider::handle:horizontal{width:18px;height:18px;margin:-7px 0;"
            "background:#0071e3;border-radius:9px;border:none;}"
            "QSlider::sub-page:horizontal{background:#0071e3;border-radius:2px;}"
        )
        temp_row.addWidget(self._settings_temp_slider, 1)
        lbl_creative = QLabel("🎨 Sáng tạo")
        lbl_creative.setStyleSheet("QLabel{font-size:11px;color:#6e6e73;background:transparent;border:none;}")
        temp_row.addWidget(lbl_creative)
        self._settings_temp_val_lbl = QLabel(f"{_cur_temp:.2f}")
        self._settings_temp_val_lbl.setFixedWidth(32)
        self._settings_temp_val_lbl.setStyleSheet(
            "QLabel{font-size:12px;font-weight:600;color:#0071e3;"
            "background:transparent;border:none;}"
        )
        temp_row.addWidget(self._settings_temp_val_lbl)
        vt.addLayout(temp_row)

        def _on_settings_temp(val: int):
            t = val / 100.0
            self._settings_temp_val_lbl.setText(f"{t:.2f}")
            self.settings["enhance_style_temperature"] = t
        self._settings_temp_slider.valueChanged.connect(_on_settings_temp)

        # Nút + thêm style (gọn, dưới temp slider)
        vt.addSpacing(16)
        btn_add_style = QPushButton("+")
        btn_add_style.setFixedSize(24, 20)
        btn_add_style.setStyleSheet(
            "QPushButton{font-size:16px;color:#86868b;background:transparent;"
            "border:1px solid #c7c7cc;border-radius:6px;padding:0;font-weight:400;}"
            "QPushButton:hover{color:#1d1d1f;border-color:#aeaeb2;background:#ebebf0;}"
            "QPushButton:pressed{background:#d1d1d6;}"
        )
        btn_add_style.clicked.connect(self._add_custom_style)
        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.addStretch()
        add_row.addWidget(btn_add_style)
        vt.addLayout(add_row)

        vt.addSpacing(10)
        custom_lbl = QLabel("Prompt tùy chỉnh")
        custom_lbl.setStyleSheet(
            "QLabel{font-size:11px;font-weight:600;color:#6e6e73;"
            "background:transparent;border:none;}"
        )
        vt.addWidget(custom_lbl)
        self._custom_style_list_layout = QVBoxLayout()
        self._custom_style_list_layout.setContentsMargins(0, 0, 0, 0)
        self._custom_style_list_layout.setSpacing(2)
        vt.addLayout(self._custom_style_list_layout)
        self._refresh_custom_style_manager()

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

        # Build map: built-in + custom
        self._ep_prompts_map = dict(PROMPTS)
        for cs in self.settings.get("custom_styles", []):
            cs_name = cs.get("name", "")
            cs_prompt = cs.get("prompt", "")
            if cs_name and cs_prompt:
                label = f"{cs.get('icon', '')}  {cs_name}" if cs.get("icon") else cs_name
                self._ep_prompts_map[label] = cs_prompt
        ep_temp_map = {
            "🎯  Nghiêm túc": 0.3,
            "😄  Hài hước":   0.7,
        }
        for cs in self.settings.get("custom_styles", []):
            cs_name = cs.get("name", "")
            cs_prompt = cs.get("prompt", "")
            if cs_name and cs_prompt:
                label = f"{cs.get('icon', '')}  {cs_name}" if cs.get("icon") else cs_name
                ep_temp_map[label] = cs.get(
                    "temperature", 0.7 if cs.get("creative", False) else 0.3
                )

        # Tìm tab đang active
        _saved = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
        _active = list(self._ep_prompts_map.keys())[0]
        for n, t in self._ep_prompts_map.items():
            if t.strip() == _saved.strip():
                _active = n
                break

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
        layout.addStretch()
        self._refresh_custom_style_manager()

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
                "QLabel{font-size:12px;color:#8e8e93;background:transparent;border:none;"
                "padding:8px 0;}"
            )
            layout.addWidget(empty)
            return

        for idx, style in enumerate(styles):
            row = QWidget()
            row.setStyleSheet("QWidget{background:transparent;border:none;}")
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 4, 0, 4)
            h.setSpacing(8)

            label = QLabel(f"{style.get('icon', '')}  {style.get('name', '').strip()}")
            label.setStyleSheet(
                "QLabel{font-size:12px;color:#1d1d1f;background:transparent;border:none;}"
            )
            h.addWidget(label, 1)

            btn_edit = QPushButton("Sửa")
            btn_edit.setFixedHeight(26)
            btn_edit.setStyleSheet(
                "QPushButton{font-size:12px;background:#f5f5f7;border:1px solid #d2d2d7;"
                "border-radius:6px;padding:0 10px;color:#1d1d1f;}"
                "QPushButton:hover{background:#e5e5ea;}"
            )
            btn_edit.clicked.connect(lambda _, i=idx: self._edit_custom_style(i))
            h.addWidget(btn_edit)

            btn_del = QPushButton("Xóa")
            btn_del.setFixedHeight(26)
            btn_del.setStyleSheet(
                "QPushButton{font-size:12px;background:#fff1f2;border:1px solid #fecdd3;"
                "border-radius:6px;padding:0 10px;color:#be123c;}"
                "QPushButton:hover{background:#ffe4e6;}"
            )
            btn_del.clicked.connect(lambda _, i=idx: self._delete_custom_style(i))
            h.addWidget(btn_del)

            layout.addWidget(row)

    def _expand_prompt_dialog(self, title: str, text_edit: QTextEdit):
        """Mở dialog editor lớn để chỉnh sửa prompt thoải mái."""
        from PyQt6.QtWidgets import QPlainTextEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(f"✏️  {title}")
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
            "background:white;border:1.5px solid #d2d2d7;border-radius:8px;"
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
            "QPushButton{background:#f5f5f7;border:1.5px solid #d2d2d7;border-radius:8px;"
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
                self.settings["enhance_style_name"] = "🎯  Nghiêm túc"
                self.settings["enhance_style_temperature"] = 0.3
                self.settings["enhance_style_creative"] = False
                self.prompt.setPlainText(DEFAULT_PROMPT)
            self._refresh_custom_styles()

    def _page_voices(self) -> QWidget:
        """Trang quản lý giọng đọc — Apple HIG style."""
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 16, 20, 20)
        v.setSpacing(0)

        # ── Library section (từ API) ───────────────────────────────
        lib_hdr = QHBoxLayout()
        lib_hdr.setContentsMargins(0, 0, 0, 0)
        lib_hdr.addWidget(self._section_label("Thư viện ElevenLabs"))
        lib_hdr.addStretch()
        btn_browse = QPushButton("🌐  Thêm từ thư viện")
        btn_browse.setFixedHeight(28)
        btn_browse.setStyleSheet(
            "QPushButton{font-size:12px;color:#0071e3;background:transparent;"
            "border:none;padding:0 4px;}"
            "QPushButton:hover{color:#0077ed;text-decoration:underline;}"
            "QPushButton:pressed{color:#005bb5;}"
        )
        btn_browse.clicked.connect(self._open_voice_library)
        lib_hdr.addWidget(btn_browse)
        v.addLayout(lib_hdr)

        # Search bar
        self._voice_search = QLineEdit()
        self._voice_search.setPlaceholderText("🔍  Tìm giọng đọc...")
        self._voice_search.setFixedHeight(34)
        self._voice_search.setStyleSheet(
            "QLineEdit{background:white;border:1.5px solid #d2d2d7;border-radius:8px;"
            "padding:0 10px;font-size:13px;color:#1d1d1f;}"
            "QLineEdit:focus{border-color:#0071e3;}"
        )
        self._voice_search.textChanged.connect(self._apply_voice_filter)
        v.addSpacing(8)
        v.addWidget(self._voice_search)
        v.addSpacing(8)

        # Language filter chips row
        self._lang_filter_row = QHBoxLayout()
        self._lang_filter_row.setSpacing(6)
        self._lang_filter_row.setContentsMargins(0, 0, 0, 0)
        self._lang_filter_scroll_w = QWidget()
        self._lang_filter_scroll_w.setLayout(self._lang_filter_row)
        self._lang_filter_scroll_w.setStyleSheet("background:transparent;border:none;")
        v.addWidget(self._lang_filter_scroll_w)
        v.addSpacing(10)

        self._voice_status = QLabel("Đang tải danh sách giọng...")
        self._voice_status.setStyleSheet(
            "QLabel{font-size:12px;color:#6e6e73;padding:8px 0;"
            "background:transparent;border:none;}"
        )
        v.addWidget(self._voice_status)

        self._api_voices_grp, self._api_voices_glay = self._group()
        self._api_voices_grp.setVisible(False)
        v.addWidget(self._api_voices_grp)

        # ── Custom voices section ──────────────────────────────────
        custom_hdr = QHBoxLayout()
        custom_hdr.setContentsMargins(0, 16, 0, 6)
        custom_hdr.addWidget(self._section_label("Giọng tuỳ chỉnh"))
        custom_hdr.addStretch()
        btn_add_v = QPushButton("+ Thêm")
        btn_add_v.setFixedHeight(28)
        btn_add_v.setStyleSheet(
            "QPushButton{font-size:12px;color:#0071e3;background:transparent;"
            "border:none;padding:0 4px;}"
            "QPushButton:hover{color:#0077ed;text-decoration:underline;}"
            "QPushButton:pressed{color:#005bb5;}"
        )
        btn_add_v.clicked.connect(self._add_custom_voice)
        custom_hdr.addWidget(btn_add_v)
        v.addLayout(custom_hdr)

        self._custom_voices_grp, self._custom_voices_glay = self._group()
        v.addWidget(self._custom_voices_grp)
        self._refresh_custom_voices()

        v.addStretch()

        # Auto-fetch khi mở trang
        keys = self.settings.get("el_api_keys", [])
        gm_key = self.settings.get("genmax_api_key", "")
        key  = next((k.strip() for k in keys if k.strip()), "")
        if key or gm_key:
            self._fetcher = VoiceFetcher(key, gm_key)
            self._fetcher.done.connect(self._on_voices_fetched)
            self._fetcher.error.connect(lambda e: self._voice_status.setText(f"⚠️ {e}"))
            self._fetcher.start()
        else:
            self._voice_status.setText("⚠️ Chưa có TTS API key — vào API Keys để thêm.")

        return page

    def _open_voice_library(self):
        """Mở dialog browse ElevenLabs Shared Voice Library."""
        keys = self.settings.get("el_api_keys", [])
        gm_key = self.settings.get("genmax_api_key", "")
        key  = next((k.strip() for k in keys if k.strip()), "")
        if not key and not gm_key:
            QMessageBox.warning(self, "Thiếu API Key",
                                "Cần ElevenLabs API key để duyệt thư viện.\nVào API Keys để thêm.")
            return
        dlg = VoiceLibraryDialog(self, api_key=key, genmax_key=gm_key)
        dlg.voice_added.connect(self._on_library_voice_added)
        dlg.exec()

    def _on_library_voice_added(self, voice_id: str, voice_name: str):
        """Sau khi add voice từ library — refresh danh sách account voices."""
        self._voice_status.setVisible(True)
        self._voice_status.setText("⏳  Đang tải lại danh sách giọng...")
        self._api_voices_grp.setVisible(False)
        keys = self.settings.get("el_api_keys", [])
        gm_key = self.settings.get("genmax_api_key", "")
        key  = next((k.strip() for k in keys if k.strip()), "")
        if key or gm_key:
            self._fetcher = VoiceFetcher(key, gm_key)
            self._fetcher.done.connect(self._on_voices_fetched)
            self._fetcher.error.connect(lambda e: self._voice_status.setText(f"⚠️ {e}"))
            self._fetcher.start()

    def _on_voices_fetched(self, voices: list):
        """Render danh sách voices sau khi fetch xong."""
        self._voice_status.setVisible(False)
        # Xoá rows cũ
        while self._api_voices_glay.count():
            item = self._api_voices_glay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._voice_rows.clear()
        self._voice_rows_lang.clear()

        # Collect unique language codes
        lang_set = []
        for v in voices:
            lng = (v.get("labels") or {}).get("language", "") or \
                  (v.get("labels") or {}).get("accent", "")
            if lng and lng not in lang_set:
                lang_set.append(lng)
        lang_set.sort()

        # Build language filter chips
        self._build_lang_chips(lang_set)

        for i, v in enumerate(voices):
            vid   = v.get("voice_id", "")
            vname = v.get("name", "")
            lang  = (v.get("labels") or {}).get("language", "") or \
                    (v.get("labels") or {}).get("accent", "")
            preview_url = v.get("preview_url", "")
            row_w = self._make_voice_row(
                vid, vname, lang, preview_url, is_last=False, custom=False
            )
            self._api_voices_glay.addWidget(row_w)
            self._voice_rows.append((row_w, vid))
            self._voice_rows_lang.append((row_w, vid, lang, vname))

        self._api_voices_grp.setVisible(True)
        self._update_voice_checkmarks()
        self._apply_voice_filter()

    def _build_lang_chips(self, langs: list):
        """Tạo language filter chips — Tất cả + mỗi language code."""
        # Clear existing chips
        while self._lang_filter_row.count():
            item = self._lang_filter_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._lang_chips.clear()

        # Language display names — full 32 ElevenLabs languages
        LANG_NAMES = {
            "en":  "🇺🇸 EN",  "vi":  "🇻🇳 VI",  "zh":  "🇨🇳 ZH",
            "ja":  "🇯🇵 JA",  "ko":  "🇰🇷 KO",  "ar":  "🇸🇦 AR",
            "bg":  "🇧🇬 BG",  "hr":  "🇭🇷 HR",  "cs":  "🇨🇿 CS",
            "da":  "🇩🇰 DA",  "nl":  "🇳🇱 NL",  "fil": "🇵🇭 FIL",
            "fi":  "🇫🇮 FI",  "fr":  "🇫🇷 FR",  "de":  "🇩🇪 DE",
            "el":  "🇬🇷 EL",  "hi":  "🇮🇳 HI",  "hu":  "🇭🇺 HU",
            "id":  "🇮🇩 ID",  "it":  "🇮🇹 IT",  "ms":  "🇲🇾 MS",
            "no":  "🇳🇴 NO",  "pl":  "🇵🇱 PL",  "pt":  "🇧🇷 PT",
            "ro":  "🇷🇴 RO",  "ru":  "🇷🇺 RU",  "sk":  "🇸🇰 SK",
            "es":  "🇪🇸 ES",  "sv":  "🇸🇪 SV",  "ta":  "🇮🇳 TA",
            "tr":  "🇹🇷 TR",  "uk":  "🇺🇦 UK",
        }

        all_langs = [("all", "Tất cả")] + [(l, LANG_NAMES.get(l, l.upper())) for l in langs]
        for code, label in all_langs:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setChecked(code == self._active_lang_filter)
            btn.setStyleSheet(self._lang_chip_style(code == self._active_lang_filter))
            btn.clicked.connect(lambda checked, c=code: self._set_lang_filter(c))
            self._lang_filter_row.addWidget(btn)
            self._lang_chips[code] = btn
        self._lang_filter_row.addStretch()

    def _lang_chip_style(self, active: bool) -> str:
        # height=28px → radius=14px (= height/2) để pill đúng, khớp với language dropdown
        if active:
            return ("QPushButton{background:#e8f0fd;color:#0071e3;"
                    "border:1.5px solid #0071e3;border-radius:14px;"
                    "padding:0 12px;font-size:12px;font-weight:600;}"
                    "QPushButton:hover{background:#dce9fd;}"
                    "QPushButton:pressed{background:#c8defa;}")
        return ("QPushButton{background:#ebebf0;color:#3c3c43;"
                "border:none;border-radius:14px;"
                "padding:0 12px;font-size:12px;font-weight:500;}"
                "QPushButton:hover{background:#e0e0e6;}"
                "QPushButton:pressed{background:#d4d4da;}")

    def _set_lang_filter(self, lang: str):
        self._active_lang_filter = lang
        for code, btn in self._lang_chips.items():
            btn.setStyleSheet(self._lang_chip_style(code == lang))
        self._apply_voice_filter()

    def _apply_voice_filter(self):
        """Hiển thị/ẩn voice rows dựa theo lang filter + search text."""
        search = self._voice_search.text().strip().lower() if hasattr(self, "_voice_search") else ""
        lang   = self._active_lang_filter

        visible_count = 0
        for row_w, vid, row_lang, vname in self._voice_rows_lang:
            lang_match   = (lang == "all") or (row_lang == lang)
            search_match = (not search) or (search in vname.lower())
            show = lang_match and search_match
            row_w.setVisible(show)
            if show:
                visible_count += 1

        # Update separator visibility (last visible row has no separator)
        # Simple approach: hide sep on last visible row — skip for now, separators are inline

    def _make_voice_row(self, vid: str, vname: str, lang: str,
                        preview_url: str, is_last: bool, custom: bool) -> QWidget:
        row_w = QWidget()
        row_w.setStyleSheet("QWidget{background:transparent;border:none;}")
        rh = QHBoxLayout(row_w)
        rh.setContentsMargins(16, 8, 12, 8)
        rh.setSpacing(10)

        # Checkmark (radio-style)
        self_ref = self
        check_btn = QPushButton("")
        check_btn.setFixedSize(20, 20)
        check_btn.setObjectName(f"vc_{vid}")
        check_btn.setStyleSheet(self._voice_check_style(vid == self._sel_voice_id))
        check_btn.clicked.connect(lambda _, v_id=vid, v_name=vname: self._select_voice(v_id, v_name))
        rh.addWidget(check_btn)

        # Name + lang
        name_lbl = QLabel(vname)
        name_lbl.setStyleSheet(
            "QLabel{font-size:13px;color:#1d1d1f;background:transparent;border:none;}"
        )
        rh.addWidget(name_lbl)

        if lang:
            # Dùng cùng LANG_NAMES dict — hiển thị flag + code thay vì chỉ text
            _ROW_LANG_NAMES = {
                "en":  "🇺🇸 EN",  "vi":  "🇻🇳 VI",  "zh":  "🇨🇳 ZH",
                "ja":  "🇯🇵 JA",  "ko":  "🇰🇷 KO",  "ar":  "🇸🇦 AR",
                "bg":  "🇧🇬 BG",  "hr":  "🇭🇷 HR",  "cs":  "🇨🇿 CS",
                "da":  "🇩🇰 DA",  "nl":  "🇳🇱 NL",  "fil": "🇵🇭 FIL",
                "fi":  "🇫🇮 FI",  "fr":  "🇫🇷 FR",  "de":  "🇩🇪 DE",
                "el":  "🇬🇷 EL",  "hi":  "🇮🇳 HI",  "hu":  "🇭🇺 HU",
                "id":  "🇮🇩 ID",  "it":  "🇮🇹 IT",  "ms":  "🇲🇾 MS",
                "no":  "🇳🇴 NO",  "pl":  "🇵🇱 PL",  "pt":  "🇧🇷 PT",
                "ro":  "🇷🇴 RO",  "ru":  "🇷🇺 RU",  "sk":  "🇸🇰 SK",
                "es":  "🇪🇸 ES",  "sv":  "🇸🇪 SV",  "ta":  "🇮🇳 TA",
                "tr":  "🇹🇷 TR",  "uk":  "🇺🇦 UK",
            }
            lang_lbl = QLabel(_ROW_LANG_NAMES.get(lang, lang.upper()))
            lang_lbl.setStyleSheet(
                "QLabel{font-size:11px;font-weight:500;color:#3c3c43;"
                "background:#ebebf0;border:none;border-radius:10px;"
                "padding:2px 8px;}"
            )
            rh.addWidget(lang_lbl)

        rh.addStretch()

        # Preview button — in-app playback
        if preview_url:
            btn_prev = QPushButton("▶  Nghe")
            btn_prev.setFixedHeight(28)
            btn_prev.setFixedWidth(72)
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

        # Delete button (custom only)
        if custom:
            btn_del = QPushButton("🗑")
            btn_del.setFixedSize(28, 28)
            btn_del.setToolTip("Xóa")
            btn_del.setStyleSheet(
                "QPushButton{background:transparent;border:none;font-size:14px;}"
                "QPushButton:hover{background:#fee2e2;border-radius:6px;}"
                "QPushButton:pressed{background:#fecaca;border-radius:6px;}"
            )
            btn_del.clicked.connect(lambda _, v_id=vid: self._delete_custom_voice(v_id))
            rh.addWidget(btn_del)

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

    def _select_voice(self, voice_id: str, voice_name: str):
        self._sel_voice_id   = voice_id
        self._sel_voice_name = voice_name
        self._update_voice_checkmarks()

    def _update_voice_checkmarks(self):
        """Cập nhật style checkmark của tất cả voice rows."""
        # API voices
        for row_w, vid in self._voice_rows:
            btn = row_w.findChild(QPushButton, f"vc_{vid}")
            if btn:
                btn.setStyleSheet(self._voice_check_style(vid == self._sel_voice_id))
        # Custom voices
        for cv in self.settings.get("custom_voices", []):
            vid = cv.get("id", "")
            btn = self._custom_voices_grp.findChild(QPushButton, f"vc_{vid}")
            if btn:
                btn.setStyleSheet(self._voice_check_style(vid == self._sel_voice_id))

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

        w = AudioPreviewDownloader(url)
        w.done.connect(lambda path, b=btn, rid=req_id: self._play_voice_preview(path, b, rid))
        w.error.connect(lambda _e, b=btn, rid=req_id: self._reset_voice_btn(b, rid))
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
                btn.setText("▶")
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
            safe.setText("■")
            safe.setEnabled(True)
            safe.setStyleSheet(
                "QPushButton{background:#e8f0fd;border:1.5px solid #0071e3;"
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
                safe.setText("▶")
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
                btn.setText("▶")
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

    def _refresh_custom_voices(self):
        while self._custom_voices_glay.count():
            item = self._custom_voices_glay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        custom_voices = self.settings.get("custom_voices", [])
        if not custom_voices:
            empty = QLabel("Chưa có giọng tuỳ chỉnh — nhấn + Thêm")
            empty.setStyleSheet(
                "QLabel{font-size:12px;color:#6e6e73;"
                "padding:12px 16px;background:transparent;border:none;}"
            )
            self._custom_voices_glay.addWidget(empty)
            return

        for i, cv in enumerate(custom_voices):
            is_last = (i == len(custom_voices) - 1)
            row_w = self._make_voice_row(
                cv.get("id", ""),
                cv.get("name", "Custom Voice"),
                "",
                "",
                is_last,
                custom=True,
            )
            self._custom_voices_glay.addWidget(row_w)

    def _add_custom_voice(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Thêm giọng tuỳ chỉnh")
        dlg.setFixedSize(380, 180)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Tên hiển thị"))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Vd: My Voice")
        name_row.addWidget(name_edit)
        v.addLayout(name_row)

        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("Voice ID"))
        id_edit = QLineEdit()
        id_edit.setPlaceholderText("pNInz6obpgDQGcFmaJgB")
        id_row.addWidget(id_edit)
        v.addLayout(id_row)

        note = QLabel("Lấy Voice ID từ ElevenLabs → Voices → copy ID")
        note.setStyleSheet(
            "font-size:11px;color:#6e6e73;background:transparent;border:none;"
        )
        v.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Thêm")
        btn_ok.setDefault(True)
        btn_ok.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:6px;padding:0 16px;font-size:13px;}"
            "QPushButton:hover{background:#0077ed;}"
        )
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        v.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            vid   = id_edit.text().strip()
            vname = name_edit.text().strip() or "Custom Voice"
            if vid:
                self.settings.setdefault("custom_voices", []).append(
                    {"id": vid, "name": vname}
                )
                self._refresh_custom_voices()

    def _delete_custom_voice(self, voice_id: str):
        cvs = self.settings.get("custom_voices", [])
        self.settings["custom_voices"] = [c for c in cvs if c.get("id") != voice_id]
        if self._sel_voice_id == voice_id:
            self._sel_voice_id   = VOICE_ID
            self._sel_voice_name = "Adam"
        self._refresh_custom_voices()

    def _page_output(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 16, 20, 20)
        v.setSpacing(0)

        v.addWidget(self._section_label("Output"))
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
        self._row(glay, "Thư mục lưu", folder_w, last=True)
        v.addWidget(grp)

        v.addStretch()
        return page

    def _build(self):
        # ── Root layout: sidebar + content ────────────────────────
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(168)
        sidebar.setStyleSheet(f"QWidget{{background:{self._SB_BG};}}")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 20, 0, 0)
        sb_layout.setSpacing(2)

        nav_items = [
            ("🔑", "API Keys"),
            ("📝", "Prompts"),
            ("🎙", "Voices"),
            ("📁", "Output"),
        ]

        self._nav_btns: list[QPushButton] = []
        for icon, label in nav_items:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setStyleSheet(
                "QPushButton{text-align:left;border:none;border-radius:8px;"
                "margin:0 8px;padding:0 12px;font-size:13px;"
                f"color:{self._SB_TEXT};background:transparent;}}"
                "QPushButton:hover{background:#e5e5ea;}"
                "QPushButton:pressed{background:#d8d8de;}"
                f"QPushButton:checked{{background:{self._SB_ACTIVE};"
                "color:#0071e3;font-weight:600;}}"
            )
            self._nav_btns.append(btn)
            sb_layout.addWidget(btn)

        sb_layout.addStretch()
        root.addWidget(sidebar)

        # ── Divider ────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"color:{self._GROUP_BORDER};")
        root.addWidget(div)

        # ── Content area ───────────────────────────────────────────
        content_wrapper = QWidget()
        content_wrapper.setStyleSheet(f"QWidget{{background:{BG};}}")
        cw_layout = QVBoxLayout(content_wrapper)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.setSpacing(0)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget{background:transparent;}")

        pages = [self._page_api(), self._page_prompts(), self._page_voices(), self._page_output()]
        for p in pages:
            # Wrap mỗi page trong ScrollArea — không bao giờ tràn màn hình
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(p)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet(
                f"QScrollArea{{background:{BG};border:none;}}"
                "QScrollBar:vertical{width:6px;background:transparent;}"
                "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:3px;}"
            )
            self._stack.addWidget(scroll)

        cw_layout.addWidget(self._stack)

        # ── Footer: Hủy / Lưu ─────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"QWidget{{background:{BG};"
            "border:none;}"
        )
        footer.setFixedHeight(52)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        fl.setSpacing(8)
        fl.addStretch()

        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(28)
        btn_cancel.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
            "border-radius:6px;padding:0 16px;font-size:13px;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Lưu")
        btn_save.setFixedHeight(28)
        btn_save.setDefault(True)
        btn_save.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:6px;padding:0 20px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
        )
        btn_save.clicked.connect(self._save)
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

    def _save(self):
        raw_keys = self.el_keys.toPlainText().strip().splitlines()
        self.settings["el_api_keys"]        = [k.strip() for k in raw_keys if k.strip()][:3]
        self.settings["genmax_api_key"]     = getattr(self, "genmax_key", _NullEdit()).text().strip()
        self.settings["ds_api_key"]         = self.ds_key.text().strip()
        self.settings["gemini_api_key"]     = self.gemini_key.text().strip()
        self.settings["claude_api_key"]     = getattr(self, "claude_key", _NullEdit()).text().strip()
        self.settings["claude_model"]       = self.claude_model.currentText() if hasattr(self, "claude_model") else "claude-3-5-haiku-20241022"
        self.settings["telegram_bot_token"] = getattr(self, "telegram_bot_token", _NullEdit()).text().strip()
        self.settings["telegram_chat_id"]   = getattr(self, "telegram_chat_id", _NullEdit()).text().strip()
        self.settings["output_dir"]         = self.out_dir.text()
        self.settings["enhance_prompt"]     = self.prompt.toPlainText()
        gp = self.gemini_prompt.toPlainText().strip()
        self.settings["gemini_chat_prompt"] = "" if gp == GEMINI_CHAT_PROMPT.strip() else gp
        # Voice selection
        self.settings["selected_voice_id"]   = self._sel_voice_id
        self.settings["selected_voice_name"] = self._sel_voice_name
        # Language code is managed from MainWindow's TTS tab — preserve existing
        self.accept()

    def get_settings(self) -> dict:
        return self.settings


