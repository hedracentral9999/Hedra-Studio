import re
import base64
import requests

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QFrame, QScrollArea, QListWidget,
    QListWidgetItem, QStackedWidget, QGridLayout, QSizePolicy,
    QMessageBox, QWidget,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QFont, QPixmap

from app_workers import (
    VoiceFetcher, SharedVoiceFetcher, AudioPreviewDownloader, AddSharedVoiceWorker,
)

# ── Settings dialog — Apple HIG style ─────────────────────────────
#
# ─────────────────────────────────────────────────────────────────────────────
class VoiceLibraryDialog(QDialog):
    """Browse ElevenLabs Shared Voice Library — filter by language, add to account."""

    LANG_OPTIONS = [
        ("", "Tất cả"),
        ("en", "🇺🇸 English"),
        ("vi", "🇻🇳 Tiếng Việt"),
        ("zh", "🇨🇳 Tiếng Trung"),
        ("ja", "🇯🇵 Tiếng Nhật"),
        ("ko", "🇰🇷 Tiếng Hàn"),
        ("es", "🇪🇸 Tiếng Tây Ban Nha"),
        ("fr", "🇫🇷 Tiếng Pháp"),
        ("de", "🇩🇪 Tiếng Đức"),
        ("pt", "🇧🇷 Tiếng Bồ Đào Nha"),
        ("it", "🇮🇹 Tiếng Ý"),
        ("ru", "🇷🇺 Tiếng Nga"),
        ("ar", "🇸🇦 Tiếng Ả Rập"),
        ("hi", "🇮🇳 Tiếng Hindi"),
        ("id", "🇮🇩 Tiếng Indonesia"),
        ("tr", "🇹🇷 Tiếng Thổ Nhĩ Kỳ"),
        ("nl", "🇳🇱 Tiếng Hà Lan"),
        ("pl", "🇵🇱 Tiếng Ba Lan"),
        ("sv", "🇸🇪 Tiếng Thụy Điển"),
    ]

    voice_added = pyqtSignal(str, str)  # (voice_id, voice_name) — sau khi add thành công

    def __init__(self, parent, api_key: str, genmax_key: str = ""):
        super().__init__(parent)
        self.api_key    = api_key
        self.genmax_key = genmax_key
        self._workers: list = []
        self._playing_btn: QPushButton | None = None   # nút đang phát
        self._dl_worker: AudioPreviewDownloader | None = None
        self._preview_req_id = 0

        # Shared audio player — 1 giọng tại một thời điểm
        self._audio_out = QAudioOutput()
        self._audio_out.setVolume(1.0)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_out)
        self._player.playbackStateChanged.connect(self._on_playback_state)

        self.setWindowTitle("🌐  Thư viện giọng ElevenLabs")
        self.setMinimumSize(680, 560)
        self.setStyleSheet("QDialog{background:#f5f5f7;}")
        self._build()
        # Auto-search trending
        QTimer.singleShot(100, self._do_search)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # ── Title + subtitle
        title = QLabel("Thư viện giọng đọc")
        title.setStyleSheet(
            "QLabel{font-size:17px;font-weight:700;color:#1d1d1f;"
            "background:transparent;border:none;}"
        )
        sub = QLabel("Tìm và thêm giọng đọc vào account của bạn")
        sub.setStyleSheet(
            "QLabel{font-size:12px;color:#6e6e73;background:transparent;border:none;}"
        )
        root.addWidget(title)
        root.addWidget(sub)

        # ── Search row
        sr = QHBoxLayout()
        sr.setSpacing(8)
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("🔍  Tìm theo tên giọng...")
        self._search_box.setFixedHeight(34)
        self._search_box.setStyleSheet(
            "QLineEdit{background:white;border:1.5px solid #d2d2d7;"
            "border-radius:8px;padding:0 10px;font-size:13px;}"
            "QLineEdit:focus{border-color:#0071e3;}"
        )
        self._search_box.returnPressed.connect(self._do_search)
        sr.addWidget(self._search_box, 1)

        btn_search = QPushButton("Tìm")
        btn_search.setFixedSize(60, 34)
        btn_search.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:8px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#006edb;}"
        )
        btn_search.clicked.connect(self._do_search)
        sr.addWidget(btn_search)
        root.addLayout(sr)

        # ── Language filter chips
        chips_w = QWidget()
        chips_w.setStyleSheet("background:transparent;border:none;")
        chips_lay = QHBoxLayout(chips_w)
        chips_lay.setContentsMargins(0, 0, 0, 0)
        chips_lay.setSpacing(6)
        self._lang_btns: dict = {}
        self._sel_lang = ""
        for code, label in self.LANG_OPTIONS:
            b = QPushButton(label)
            b.setFixedHeight(28)
            b.setStyleSheet(self._chip_style(code == self._sel_lang))
            b.clicked.connect(lambda _, c=code: self._set_lang(c))
            chips_lay.addWidget(b)
            self._lang_btns[code] = b
        chips_lay.addStretch()

        chip_scroll = QScrollArea()
        chip_scroll.setWidget(chips_w)
        chip_scroll.setWidgetResizable(True)
        chip_scroll.setFixedHeight(44)
        chip_scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:horizontal{height:4px;background:transparent;}"
            "QScrollBar::handle:horizontal{background:#c7c7cc;border-radius:2px;}"
            "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;}"
        )
        chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(chip_scroll)

        # ── Status label
        self._status = QLabel("Đang tải...")
        self._status.setStyleSheet(
            "QLabel{font-size:12px;color:#6e6e73;background:transparent;border:none;}"
        )
        root.addWidget(self._status)

        # ── Voice list
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background:transparent;border:none;")
        self._list_lay = QVBoxLayout(self._list_w)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidget(self._list_w)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:1.5px solid #d2d2d7;border-radius:10px;background:white;}"
            "QScrollBar:vertical{width:8px;background:transparent;border-radius:4px;}"
            "QScrollBar::handle:vertical{background:rgba(0,0,0,0.2);border-radius:4px;min-height:20px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        root.addWidget(scroll, 1)

        # ── Close button
        btns = QHBoxLayout()
        btns.addStretch()
        btn_close = QPushButton("Đóng")
        btn_close.setFixedHeight(32)
        btn_close.setStyleSheet(
            "QPushButton{background:#f5f5f7;border:1.5px solid #d2d2d7;"
            "border-radius:8px;padding:0 20px;font-size:13px;}"
            "QPushButton:hover{background:#e5e5ea;}"
        )
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_close)
        root.addLayout(btns)

    def _chip_style(self, active: bool) -> str:
        if active:
            return ("QPushButton{background:#e8f0fd;color:#0071e3;"
                    "border:1.5px solid #0071e3;border-radius:14px;"
                    "padding:0 12px;font-size:12px;font-weight:600;}"
                    "QPushButton:hover{background:#dce9fd;}"
                    "QPushButton:pressed{background:#c8defa;}")
        return ("QPushButton{background:#f5f5f7;color:#1d1d1f;"
                "border:1.5px solid #d2d2d7;border-radius:14px;"
                "padding:0 12px;font-size:12px;}"
                "QPushButton:hover{background:#e5e5ea;}"
                "QPushButton:pressed{background:#d2d2d7;}")

    def _set_lang(self, lang: str):
        self._sel_lang = lang
        for code, btn in self._lang_btns.items():
            btn.setStyleSheet(self._chip_style(code == lang))
        self._do_search()

    def _do_search(self):
        self._status.setText("⏳  Đang tìm kiếm...")
        self._clear_list()
        w = SharedVoiceFetcher(
            self.api_key,
            language=self._sel_lang,
            search=self._search_box.text().strip(),
            page_size=40,
            genmax_key=self.genmax_key,
        )
        w.done.connect(self._on_results)
        w.error.connect(lambda e: self._status.setText(f"⚠️  {e}"))
        w.start()
        self._workers.append(w)

    def _clear_list(self):
        # Stop audio trước khi xóa widgets — tránh dangling pointer
        self._player.stop()
        self._playing_btn = None
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_results(self, voices: list):
        self._clear_list()
        if not voices:
            lbl = QLabel("Không tìm thấy giọng nào — thử ngôn ngữ khác hoặc từ khoá khác")
            lbl.setStyleSheet(
                "QLabel{font-size:13px;color:#6e6e73;padding:24px 16px;"
                "background:transparent;border:none;}"
            )
            self._list_lay.addWidget(lbl)
            self._status.setText("0 kết quả")
            return

        self._status.setText(f"✅  {len(voices)} giọng — nhấn ▶ để nghe thử, + để thêm vào account")
        for i, v in enumerate(voices):
            self._list_lay.addWidget(self._make_row(v, is_last=(i == len(voices)-1)))
        self._list_lay.addStretch()

    def _make_row(self, v: dict, is_last: bool) -> QWidget:
        vid        = v.get("voice_id", "")
        name       = v.get("name", "")
        lang       = v.get("language", "") or v.get("labels", {}).get("language", "")
        desc       = v.get("description", "") or v.get("labels", {}).get("description", "")
        preview    = v.get("preview_url", "")
        owner_id   = v.get("public_owner_id", "")
        category   = v.get("category", "")

        row = QWidget()
        row.setStyleSheet("QWidget{background:white;border:none;}")
        h = QHBoxLayout(row)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(10)

        # Name + meta
        info = QVBoxLayout()
        info.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            "QLabel{font-size:13px;font-weight:600;color:#1d1d1f;"
            "background:transparent;border:none;}"
        )
        info.addWidget(name_lbl)

        meta_parts = []
        if lang:
            meta_parts.append(lang.upper())
        if category:
            meta_parts.append(category)
        if desc:
            meta_parts.append(desc[:60] + ("…" if len(desc) > 60 else ""))
        if meta_parts:
            meta_lbl = QLabel("  ·  ".join(meta_parts))
            meta_lbl.setStyleSheet(
                "QLabel{font-size:11px;color:#6e6e73;background:transparent;border:none;}"
            )
            info.addWidget(meta_lbl)
        h.addLayout(info, 1)

        # Preview button — in-app playback
        if preview:
            btn_prev = QPushButton("▶")
            btn_prev.setFixedSize(30, 30)
            btn_prev.setToolTip("Nghe thử trong app")
            btn_prev.setProperty("preview_url", preview)
            btn_prev.setStyleSheet(self._prev_btn_style(False))
            btn_prev.clicked.connect(
                lambda _, u=preview, b=btn_prev: self._toggle_preview(u, b)
            )
            h.addWidget(btn_prev)

        # Add button
        btn_add = QPushButton("＋ Thêm")
        btn_add.setFixedHeight(30)
        btn_add.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:6px;padding:0 12px;font-size:12px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#006edb;}"
            "QPushButton:disabled{background:#a8d0fb;color:white;}"
        )
        btn_add.clicked.connect(
            lambda _, v_id=vid, o_id=owner_id, n=name, b=btn_add:
                self._add_voice(v_id, o_id, n, b)
        )
        h.addWidget(btn_add)
        return row

    def _add_voice(self, voice_id: str, owner_id: str, name: str, btn: QPushButton):
        btn.setEnabled(False)
        btn.setText("Đang thêm...")
        w = AddSharedVoiceWorker(self.api_key, voice_id, owner_id, name)
        w.done.connect(lambda vid, vn, b=btn: self._on_added(vid, vn, b))
        w.error.connect(lambda e, b=btn: self._on_add_error(e, b))
        w.start()
        self._workers.append(w)

    def _on_added(self, voice_id: str, voice_name: str, btn: QPushButton):
        btn.setText("✅ Đã thêm")
        btn.setStyleSheet(
            "QPushButton{background:#d1fae5;color:#15803d;border:1px solid #86efac;"
            "border-radius:6px;padding:0 12px;font-size:12px;font-weight:600;}"
        )
        self.voice_added.emit(voice_id, voice_name)

    def _on_add_error(self, error: str, btn: QPushButton):
        btn.setEnabled(True)
        btn.setText("＋ Thêm")
        QMessageBox.warning(self, "Lỗi", f"Không thêm được giọng:\n{error}")

    # ── In-app audio preview ──────────────────────────────────────

    def _prev_btn_style(self, playing: bool) -> str:
        if playing:
            return ("QPushButton{background:#e8f0fd;border:1.5px solid #0071e3;"
                    "border-radius:6px;font-size:13px;color:#0071e3;}"
                    "QPushButton:hover{background:#dce9fd;}")
        return ("QPushButton{background:#f5f5f7;border:1px solid #d2d2d7;"
                "border-radius:6px;font-size:12px;color:#1d1d1f;}"
                "QPushButton:hover{background:#e5e5ea;}"
                "QPushButton:pressed{background:#d2d2d7;}")

    def _safe_btn(self, btn: QPushButton | None) -> QPushButton | None:
        """Trả về btn nếu widget còn sống, None nếu đã bị delete."""
        if btn is None:
            return None
        try:
            btn.objectName()   # raises RuntimeError nếu C++ object đã delete
            return btn
        except RuntimeError:
            return None

    def _toggle_preview(self, url: str, btn: QPushButton):
        """Play / Stop toggle cho preview button."""
        # Nếu đang phát cùng 1 bài → stop (defer stop để tránh re-entrancy)
        if self._playing_btn is btn:
            QTimer.singleShot(0, self._stop_preview)
            return

        # Stop bài cũ rồi download bài mới
        self._stop_preview()
        self._preview_req_id += 1
        req_id = self._preview_req_id

        self._playing_btn = btn
        try:
            btn.setText("⏳")
            btn.setEnabled(False)
            btn.setStyleSheet(self._prev_btn_style(True))
        except RuntimeError:
            self._playing_btn = None
            return

        self._dl_worker = AudioPreviewDownloader(url)
        self._dl_worker.done.connect(lambda path, rid=req_id: self._play_file(path, rid))
        self._dl_worker.error.connect(lambda err, rid=req_id: self._on_preview_error(err, rid))
        self._dl_worker.start()

    def _play_file(self, path: str, req_id: int):
        if req_id != self._preview_req_id:
            return
        btn = self._safe_btn(self._playing_btn)
        if not btn:
            self._playing_btn = None
            return
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        try:
            btn.setText("■")
            btn.setEnabled(True)
            btn.setStyleSheet(self._prev_btn_style(True))
        except RuntimeError:
            pass

    def _stop_preview(self):
        # Dùng blockSignals để tránh _on_playback_state re-enter khi stop() gọi synchronous
        self._player.blockSignals(True)
        self._player.stop()
        self._player.blockSignals(False)
        btn = self._safe_btn(self._playing_btn)
        self._playing_btn = None
        if btn:
            try:
                btn.setText("▶")
                btn.setEnabled(True)
                btn.setStyleSheet(self._prev_btn_style(False))
            except RuntimeError:
                pass

    def _on_playback_state(self, state):
        """Tự reset button khi audio kết thúc (natural end, không phải manual stop)."""
        if state == QMediaPlayer.PlaybackState.StoppedState:
            # Defer để tránh re-entrancy trong signal handler
            QTimer.singleShot(0, self._reset_after_stop)

    def _reset_after_stop(self):
        btn = self._safe_btn(self._playing_btn)
        self._playing_btn = None
        if btn:
            try:
                btn.setText("▶")
                btn.setEnabled(True)
                btn.setStyleSheet(self._prev_btn_style(False))
            except RuntimeError:
                pass

    def _on_preview_error(self, err: str, req_id: int):
        if req_id != self._preview_req_id:
            return
        btn = self._safe_btn(self._playing_btn)
        self._playing_btn = None
        if btn:
            try:
                btn.setText("▶")
                btn.setEnabled(True)
                btn.setStyleSheet(self._prev_btn_style(False))
            except RuntimeError:
                pass


# Layout: sidebar trái (nav items) + content phải (scroll area)
# Mỗi section là một "page" — không dump tất cả vào 1 cột
# Fixed window size, content scroll bên trong — không tràn màn hình
#
