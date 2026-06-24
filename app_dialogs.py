import re
import json

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QFrame, QScrollArea, QStackedWidget,
    QGridLayout, QComboBox, QSizePolicy, QSpacerItem,
    QFileDialog, QMessageBox, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QFont

from app_constants import (
    EMOJI_LIST, PROMPTS, PROMPT_TEMPLATES, GEMINI_CHAT_PROMPT,
    DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY, VOICE_ID, get_style, theme_tokens,
)
from app_workers import PromptGeneratorWorker, SuggestAnswersWorker, FeedbackSender


def _tts_deepseek_model(parent=None) -> str:
    settings = getattr(parent, "settings", {}) if parent is not None else {}
    if not isinstance(settings, dict):
        return "deepseek-v4-flash"
    return settings.get("deepseek_tts_model", "deepseek-v4-flash")

def _theme_for(parent=None) -> tuple[str, dict[str, str]]:
    settings = getattr(parent, "settings", {}) if parent is not None else {}
    mode = settings.get("app_theme", "system") if isinstance(settings, dict) else "system"
    return mode, theme_tokens(mode)


class EmojiPickerDialog(QDialog):
    """Bảng chọn emoji — 6 cột, button đủ lớn, full visible không cần scroll."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chọn icon")
        self._theme_mode, self._t = _theme_for(parent)
        self.setStyleSheet(get_style(self._theme_mode))
        self.chosen = ""
        self._build()
        # Center on screen (tránh bị che bởi macOS menu bar)
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = screen.center().x() - self.width() // 2
        y = screen.center().y() - self.height() // 2
        self.move(max(x, screen.left() + 20), max(y, screen.top() + 20))

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(0)

        inner = QWidget()
        inner.setStyleSheet(f"QWidget{{background:{self._t['BG']};border:none;}}")
        grid = QGridLayout(inner)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        cols = 6
        for i, em in enumerate(EMOJI_LIST):
            btn = QPushButton(em)
            btn.setFixedSize(52, 52)
            btn.setStyleSheet(
                f"QPushButton{{font-size:26px;border:1px solid {self._t['BORDER_SOFT']};"
                f"border-radius:10px;background:{self._t['SURFACE']};color:{self._t['TEXT']};}}"
                f"QPushButton:hover{{background:{self._t['CONTROL_HV']};border-color:{self._t['ACCENT']};}}"
                f"QPushButton:pressed{{background:{self._t['CONTROL_DN']};}}"
            )
            btn.clicked.connect(lambda _, e=em: self._pick(e))
            grid.addWidget(btn, i // cols, i % cols)

        v.addWidget(inner)

    def _pick(self, em: str):
        self.chosen = em
        self.accept()


class AddStyleDialog(QDialog):
    """Dialog thêm / sửa phong cách prompt — có AI prompt generator."""

    def __init__(self, parent=None, existing: dict = None, ds_api_key: str = "", gemini_api_key: str = ""):
        super().__init__(parent)
        data = existing or {}
        parent_settings = getattr(parent, "settings", {}) if parent is not None else {}
        self._theme_mode = parent_settings.get("app_theme", "system") if isinstance(parent_settings, dict) else "system"
        self._t = theme_tokens(self._theme_mode)
        self.setStyleSheet(get_style(self._theme_mode))
        self.setWindowTitle("Thêm phong cách" if not existing else "Sửa phong cách")
        self.setMinimumSize(660, 760)
        self.resize(700, 820)
        self._icon            = ""
        self._result: dict    = {}
        self._ds_key          = ds_api_key
        self._gemini_key      = gemini_api_key
        self._deepseek_model  = _tts_deepseek_model(parent)
        self._gen_worker      = None
        self._suggest_worker  = None
        self._wiz_chip_btns:  dict[str, list[QPushButton]] = {}
        self._wiz_text_fields: dict[str, QLineEdit]        = {}
        self._build(data)

    def _build(self, data: dict):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(f"QFrame{{background:{self._t['SURFACE']};border:none;}}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(22, 14, 22, 14)
        hl.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Thêm phong cách" if not data else "Sửa phong cách")
        title.setStyleSheet(f"font-size:17px;font-weight:700;color:{self._t['TEXT']};background:transparent;border:none;")
        subtitle = QLabel("Tạo phong cách đọc riêng. Phong cách này sẽ hiện trong tab TTS.")
        subtitle.setStyleSheet(f"font-size:12px;color:{self._t['TEXT_MUTE']};background:transparent;border:none;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        hl.addLayout(title_col, 1)
        v.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(self._scroll_style())
        body = QWidget()
        body.setStyleSheet("QWidget{background:transparent;border:none;}")
        content = QVBoxLayout(body)
        content.setContentsMargins(28, 22, 28, 22)
        content.setSpacing(18)

        # ── Name ─────────────────────────────────────────────────
        info_card = QFrame()
        info_card.setStyleSheet(self._card_style())
        info = QVBoxLayout(info_card)
        info.setContentsMargins(14, 12, 14, 14)
        info.setSpacing(12)

        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_lbl = QLabel("Tên hiển thị")
        name_lbl.setStyleSheet(self._caption_label_style())
        self._name_edit = QLineEdit(data.get("name", ""))
        self._name_edit.setPlaceholderText("Ví dụ: Chốt đơn vui, Tư vấn miền Tây, Kể chuyện drama...")
        self._name_edit.setStyleSheet(self._field_style())
        name_col.addWidget(name_lbl)
        name_col.addWidget(self._name_edit)
        info.addLayout(name_col)

        self._temp_val = float(data.get("temperature", 0.4) or 0.4)
        content.addWidget(info_card)

        # ── AI Prompt Generator — inline wizard ──────────────────
        content.addWidget(self._section_title("AI gợi ý", "Trả lời nhanh vài mục, tool sẽ dựng prompt hoàn chỉnh."))

        # AI gợi ý nhanh từ mô tả ngắn
        ai_frame = QFrame()
        ai_frame.setStyleSheet(self._card_style())
        af = QHBoxLayout(ai_frame)
        af.setContentsMargins(12, 10, 12, 10)
        af.setSpacing(10)
        self._brief_edit = QLineEdit()
        self._brief_edit.setPlaceholderText(
            "Mô tả ngắn để AI tự chọn mục phù hợp, ví dụ: shop thời trang nữ miền Nam"
        )
        self._brief_edit.setStyleSheet(self._field_style())
        self._brief_edit.returnPressed.connect(self._ai_suggest_wiz)
        af.addWidget(self._brief_edit, 1)
        self._btn_suggest = QPushButton("Gợi ý")
        self._btn_suggest.setFixedHeight(30)
        self._btn_suggest.setFixedWidth(88)
        self._btn_suggest.setStyleSheet(self._primary_button_style())
        self._btn_suggest.clicked.connect(self._ai_suggest_wiz)
        af.addWidget(self._btn_suggest)
        content.addWidget(ai_frame)

        # Câu hỏi inline — scroll area
        wizard_group = QFrame()
        wizard_group.setStyleSheet(self._card_style())
        wiz_v = QVBoxLayout(wizard_group)
        wiz_v.setContentsMargins(12, 12, 12, 12)
        wiz_v.setSpacing(10)

        for key, label, chips, multi, placeholder in PromptWizardDialog._QUESTIONS:
            q_frame = QFrame()
            q_frame.setStyleSheet(
                f"QFrame{{background-color:{self._t['SURFACE']};border:1px solid {self._t['BORDER_SOFT']};border-radius:10px;}}"
            )
            qf = QVBoxLayout(q_frame)
            qf.setContentsMargins(12, 8, 12, 8)
            qf.setSpacing(8)

            q_lbl = QLabel(label)
            q_lbl.setStyleSheet(
                f"QLabel{{font-size:12px;font-weight:600;color:{self._t['TEXT']};"
                "background:transparent;border:none;}"
            )
            qf.addWidget(q_lbl)

            if chips:
                chip_h = QGridLayout()
                chip_h.setHorizontalSpacing(6)
                chip_h.setVerticalSpacing(6)
                chip_h.setContentsMargins(0, 0, 0, 0)
                btns: list[QPushButton] = []
                for chip_text in chips:
                    cb = QPushButton(chip_text)
                    cb.setFixedHeight(28)
                    cb.setCheckable(True)
                    cb.setStyleSheet(self._wiz_chip_style(False))
                    cb.clicked.connect(
                        lambda checked, k=key, c=chip_text, m=multi:
                            self._toggle_wiz_chip(k, c, m)
                    )
                    pos = len(btns)
                    chip_h.addWidget(cb, pos // 4, pos % 4)
                    btns.append(cb)
                self._wiz_chip_btns[key] = btns
                qf.addLayout(chip_h)

            if placeholder:
                txt = QLineEdit()
                txt.setPlaceholderText(placeholder)
                txt.setStyleSheet(self._field_style(compact=True))
                self._wiz_text_fields[key] = txt
                qf.addWidget(txt)

            wiz_v.addWidget(q_frame)

        content.addWidget(wizard_group)

        # Tạo Prompt button + status
        gen_row = QHBoxLayout()
        self._btn_gen = QPushButton("Tạo Prompt")
        self._btn_gen.setFixedHeight(34)
        self._btn_gen.setStyleSheet(self._primary_button_style())
        self._btn_gen.clicked.connect(self._generate_from_wizard)
        gen_row.addStretch()
        gen_row.addWidget(self._btn_gen)
        content.addLayout(gen_row)

        self._ai_status = QLabel("")
        self._ai_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._ai_status.setStyleSheet(
            f"font-size:11px;color:{self._t['TEXT_MUTE']};background:transparent;border:none;"
        )
        content.addWidget(self._ai_status)

        # ── Prompt textarea ───────────────────────────────────────
        content.addWidget(self._section_title("Prompt phong cách", "Có thể sửa thủ công trước khi lưu."))
        prompt_card = QFrame()
        prompt_card.setStyleSheet(self._card_style())
        prompt_lay = QVBoxLayout(prompt_card)
        prompt_lay.setContentsMargins(12, 12, 12, 12)
        prompt_lay.setSpacing(8)
        self._prompt = QTextEdit()
        self._prompt.setPlainText(data.get("prompt", ""))
        self._prompt.setPlaceholderText(
            "Nhập thủ công hoặc nhấn Tạo Prompt để AI viết phong cách đọc cho bạn..."
        )
        self._prompt.setMinimumHeight(150)
        self._prompt.setStyleSheet(self._text_area_style())
        prompt_lay.addWidget(self._prompt)
        content.addWidget(prompt_card)

        scroll.setWidget(body)
        v.addWidget(scroll, 1)

        # ── Footer buttons ────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet(f"QFrame{{background:{self._t['SURFACE']};border:none;}}")
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 12)
        btn_row.setSpacing(8)
        btn_row.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(30)
        btn_cancel.setStyleSheet(self._secondary_button_style())
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Lưu")
        btn_save.setFixedHeight(30)
        btn_save.setDefault(True)
        btn_save.setStyleSheet(self._primary_button_style())
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        footer.setLayout(btn_row)
        v.addWidget(footer)

    def _section_title(self, title: str, subtitle: str = "") -> QWidget:
        box = QWidget()
        box.setStyleSheet("QWidget{background:transparent;border:none;}")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"font-size:13px;font-weight:700;color:{self._t['TEXT']};background:transparent;border:none;")
        lay.addWidget(lbl)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet(f"font-size:11px;color:{self._t['TEXT_MUTE']};background:transparent;border:none;")
            lay.addWidget(sub)
        return box

    def _caption_label_style(self) -> str:
        return f"font-size:12px;font-weight:600;color:{self._t['TEXT_MUTE']};background:transparent;border:none;"

    def _card_style(self) -> str:
        return (
            f"QFrame{{background-color:{self._t['CONTROL_BG']};border:1px solid {self._t['BORDER_SOFT']};"
            "border-radius:12px;}"
        )

    def _field_style(self, compact: bool = False) -> str:
        pad = "4px 8px" if compact else "6px 10px"
        return (
            f"QLineEdit{{background-color:{self._t['SURFACE']};border:1px solid {self._t['BORDER_SOFT']};"
            f"border-radius:8px;padding:{pad};font-size:12px;color:{self._t['TEXT']};}}"
            f"QLineEdit:focus{{border-color:{self._t['ACCENT']};background-color:{self._t['SURFACE']};}}"
            f"QLineEdit:disabled{{background-color:{self._t['CONTROL_BG']};color:{self._t['TEXT_FAINT']};}}"
        )

    def _text_area_style(self) -> str:
        return (
            f"QTextEdit{{background-color:{self._t['SURFACE']};border:1px solid {self._t['BORDER_SOFT']};"
            f"border-radius:10px;padding:10px;color:{self._t['TEXT']};font-size:12px;}}"
            f"QTextEdit:focus{{border-color:{self._t['ACCENT']};}}"
        )

    def _primary_button_style(self) -> str:
        return (
            f"QPushButton{{background-color:{self._t['ACCENT']};color:white;border:none;border-radius:8px;"
            "padding:0 16px;font-size:13px;font-weight:600;}"
            f"QPushButton:hover{{background-color:{self._t['ACCENT_HV']};}}"
            f"QPushButton:pressed{{background-color:{self._t['ACCENT_DN']};}}"
            f"QPushButton:disabled{{background-color:{self._t['CONTROL_DN']};color:{self._t['TEXT_FAINT']};}}"
        )

    def _secondary_button_style(self) -> str:
        return (
            f"QPushButton{{background-color:{self._t['CONTROL_BG']};color:{self._t['TEXT']};"
            f"border:1px solid {self._t['BORDER_SOFT']};border-radius:8px;padding:0 14px;font-size:13px;}}"
            f"QPushButton:hover{{background-color:{self._t['CONTROL_HV']};}}"
            f"QPushButton:pressed{{background-color:{self._t['CONTROL_DN']};}}"
        )

    def _scroll_style(self) -> str:
        return (
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            f"QScrollBar::handle:vertical{{background:{self._t['SCROLL']};border-radius:3px;min-height:30px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{self._t['SCROLL_HV']};}}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

    # ── Wizard chip helpers ───────────────────────────────────────
    def _wiz_chip_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton{{font-size:12px;background-color:{self._t['ACCENT']};color:white;"
                "border:none;border-radius:13px;padding:0 10px;}"
                f"QPushButton:hover{{background-color:{self._t['ACCENT_HV']};}}"
                f"QPushButton:pressed{{background-color:{self._t['ACCENT_DN']};}}"
            )
        return (
            f"QPushButton{{font-size:12px;background-color:{self._t['CONTROL_BG']};color:{self._t['TEXT']};"
            f"border:1px solid {self._t['BORDER']};border-radius:13px;padding:0 10px;}}"
            f"QPushButton:hover{{background-color:{self._t['CONTROL_HV']};}}"
            f"QPushButton:pressed{{background-color:{self._t['CONTROL_DN']};}}"
        )

    def _toggle_wiz_chip(self, key: str, chip: str, multi: bool):
        btns = self._wiz_chip_btns.get(key, [])
        texts = [b.text() for b in btns]
        if chip not in texts:
            return
        idx  = texts.index(chip)
        btn  = btns[idx]
        if multi:
            btn.setStyleSheet(self._wiz_chip_style(btn.isChecked()))
        else:
            for b in btns:
                b.setChecked(False)
                b.setStyleSheet(self._wiz_chip_style(False))
            btn.setChecked(True)
            btn.setStyleSheet(self._wiz_chip_style(True))

    def _gather_wizard_answers(self) -> dict:
        answers: dict[str, str] = {}
        for key, _, chips, _, _ in PromptWizardDialog._QUESTIONS:
            if key in self._wiz_chip_btns:
                selected = [b.text() for b in self._wiz_chip_btns[key] if b.isChecked()]
                answers[key] = ", ".join(selected)
            else:
                answers[key] = ""
            if key in self._wiz_text_fields:
                tf = self._wiz_text_fields[key].text().strip()
                if tf:
                    answers[key] = tf
        return answers

    def _fill_wiz_from_suggestions(self, data: dict):
        """Điền gợi ý AI vào chips/text — chỉ fill chỗ chưa có."""
        for key, value in data.items():
            if not value:
                continue
            val_str = str(value).strip()
            if key in self._wiz_text_fields:
                if not self._wiz_text_fields[key].text().strip():
                    self._wiz_text_fields[key].setText(val_str)
            if key in self._wiz_chip_btns:
                btns = self._wiz_chip_btns[key]
                if any(b.isChecked() for b in btns):
                    continue
                texts     = [b.text() for b in btns]
                is_multi  = key in ("audience", "tone")
                candidates = [v.strip() for v in val_str.split(",")]
                for cand in candidates:
                    for i, chip_text in enumerate(texts):
                        if cand.lower() in chip_text.lower() or chip_text.lower() in cand.lower():
                            btns[i].setChecked(True)
                            btns[i].setStyleSheet(self._wiz_chip_style(True))
                            if not is_multi:
                                break

    def _ai_suggest_wiz(self):
        brief = self._brief_edit.text().strip()
        if not brief:
            self._ai_status.setText("Nhập mô tả ngắn trước.")
            return
        if not self._ds_key and not self._gemini_key:
            self._ai_status.setText("Chưa có AI key. Vào Cài đặt > API để thêm Gemini hoặc DeepSeek.")
            return
        self._btn_suggest.setEnabled(False)
        self._btn_suggest.setText("...")
        self._ai_status.setText("AI đang gợi ý...")
        self._suggest_worker = SuggestAnswersWorker(
            brief, self._ds_key, self._gemini_key,
            deepseek_model=self._deepseek_model,
        )
        self._suggest_worker.done.connect(self._on_suggest_wiz_done)
        self._suggest_worker.error.connect(self._on_suggest_wiz_error)
        self._suggest_worker.start()

    def _on_suggest_wiz_done(self, data: dict):
        self._fill_wiz_from_suggestions(data)
        self._ai_status.setText("Đã gợi ý. Kiểm tra lại rồi nhấn Tạo Prompt.")
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("Gợi ý")

    def _on_suggest_wiz_error(self, err: str):
        self._ai_status.setText(err[:80])
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("Gợi ý")

    def _generate_from_wizard(self):
        if not self._ds_key and not self._gemini_key:
            self._ai_status.setText("Chưa có AI key. Vào Cài đặt > API để thêm Gemini hoặc DeepSeek.")
            return
        answers = self._gather_wizard_answers()
        if not answers.get("product", "").strip():
            self._ai_status.setText("Mục Sản phẩm / Lĩnh vực là bắt buộc.")
            return

        self._btn_gen.setEnabled(False)
        self._btn_gen.setText("Đang tạo...")
        self._ai_status.setText("AI đang viết prompt...")

        labels = {
            "purpose": "Mục đích", "audience": "Đối tượng",
            "region":  "Vùng miền", "tone":    "Tông",
            "product": "Sản phẩm/lĩnh vực",
            "keywords": "Từ ngữ đặc trưng", "avoid": "Tuyệt đối tránh",
            "example": "Ví dụ đúng gu",
        }
        parts = [f"{lbl}: {answers[k]}" for k, lbl in labels.items() if answers.get(k)]
        full_desc = " | ".join(parts)

        self._gen_worker = PromptGeneratorWorker(
            full_desc, self._ds_key, self._gemini_key,
            deepseek_model=self._deepseek_model,
        )
        self._gen_worker.done.connect(self._on_wiz_gen_done)
        self._gen_worker.error.connect(self._on_wiz_gen_error)
        self._gen_worker.start()

    def _on_wiz_gen_done(self, prompt: str):
        self._prompt.setPlainText(prompt)
        self._ai_status.setText("Đã tạo prompt. Bạn có thể chỉnh sửa thêm trước khi lưu.")
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("Tạo Prompt")
        # Auto-fill tên nếu chưa có
        if not self._name_edit.text().strip():
            product = self._gather_wizard_answers().get("product", "")
            words   = product.split()
            self._name_edit.setText(" ".join(words[:2]) if words else product[:20])

    def _on_wiz_gen_error(self, err: str):
        self._ai_status.setText(err[:80])
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("Tạo Prompt")

    def _save(self):
        name   = self._name_edit.text().strip()
        prompt = self._prompt.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Thiếu tên", "Nhập tên phong cách nhé!")
            return
        if not prompt:
            QMessageBox.warning(self, "Thiếu prompt",
                                "Nhập prompt hoặc nhấn Tạo Prompt để AI viết nhé!")
            return
        self._result = {
            "icon":        "",
            "name":        name,
            "prompt":      prompt,
            "temperature": self._temp_val,
            "creative":    False,   # backward compat
        }
        self.accept()

    def get_result(self) -> dict:
        return self._result



# ── Drop Zone widget ───────────────────────────────────────────────
class DropZone(QFrame):
    files_added = pyqtSignal(list)

    def __init__(
        self,
        parent=None,
        label: str = "📷  Kéo thả ảnh vào đây",
        dialog_title: str = "Chọn ảnh chat",
        file_filter: str = "Images (*.png *.jpg *.jpeg *.webp)",
        extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp"),
    ):
        super().__init__(parent)
        self._theme_mode, self._t = _theme_for(parent)
        self.setStyleSheet(get_style(self._theme_mode))
        self._dialog_title = dialog_title
        self._file_filter = file_filter
        self._extensions = tuple(ext.lower() for ext in extensions)
        self.setAcceptDrops(True)
        self.setFixedHeight(90)
        self._set_idle_style()
        lbl = QLabel(label, self)
        self._label = lbl
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color:{self._t['TEXT_MUTE']}; font-size:13px; border:none; background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(lbl)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_idle_style(self):
        self.setStyleSheet(
            f"QFrame{{border:2px dashed {self._t['BORDER']};border-radius:10px;background:{self._t['SURFACE_2']};}}"
            f"QFrame:hover{{border-color:{self._t['ACCENT']};background:{self._t['CONTROL_HV']};}}"
        )

    def _set_hover_style(self):
        self.setStyleSheet(
            f"QFrame{{border:2px dashed {self._t['ACCENT']};border-radius:10px;background:{self._t['CONTROL_HV']};}}"
        )

    def mousePressEvent(self, e):
        paths, _ = QFileDialog.getOpenFileNames(
            self, self._dialog_title, "", self._file_filter
        )
        if paths:
            self.files_added.emit(paths)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._set_hover_style()
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._set_idle_style()

    def dropEvent(self, e):
        self._set_idle_style()
        files = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(self._extensions):
                files.append(p)
        if files:
            self.files_added.emit(files)


# ── Prompt Wizard dialog ───────────────────────────────────────────
class PromptWizardDialog(QDialog):
    """Wizard hỏi nhanh để AI tạo prompt phong cách TTS."""

    _QUESTIONS = [
        # (key, label, chips, multi_select, placeholder)
        ("purpose",  "1. Mục đích chính",
         ["Bán hàng", "Tư vấn", "Giáo dục", "Kể chuyện", "Truyền cảm hứng", "Khác"],
         False, "Không có lựa chọn phù hợp? Nhập tại đây..."),
        ("audience", "2. Đối tượng nghe",
         ["Người trẻ", "Gia đình", "Doanh nhân", "Học sinh / SV", "Tất cả"],
         True, "Không có lựa chọn phù hợp? Nhập tại đây..."),
        ("region",   "3. Vùng miền / Phong cách",
         ["Trung lập", "Miền Nam", "Miền Trung", "Miền Bắc"],
         False, "Không có lựa chọn phù hợp? Nhập tại đây..."),
        ("tone",     "4. Tông cảm xúc",
         ["Vui vẻ", "Nghiêm túc", "Ấm áp", "Hài hước", "Mạnh mẽ", "Chuyên nghiệp"],
         True, "Không có lựa chọn phù hợp? Nhập tại đây..."),
        ("product",  "5. Sản phẩm / Lĩnh vực  ✱",
         [], False, "Vd: shop quần áo nữ, khoá học online, dịch vụ tư vấn..."),
        ("keywords", "6. Từ ngữ đặc trưng muốn dùng",
         [], False, 'Vd: "sis", "chị ơi", "xịn xò"...  (tùy chọn)'),
        ("avoid",    "7. Điều tuyệt đối tránh",
         [], False, 'Vd: không quá formal, không nói "quý khách"...  (tùy chọn)'),
        ("example",  "8. Ví dụ đúng gu",
         [], False, "Dán 1 đoạn bạn thấy đúng phong cách để AI học theo...  (tùy chọn)"),
    ]

    def __init__(self, parent=None, ds_api_key: str = "", gemini_api_key: str = ""):
        super().__init__(parent)
        self._theme_mode, self._t = _theme_for(parent)
        self.setStyleSheet(get_style(self._theme_mode))
        self.setWindowTitle("Prompt Wizard")
        self.setFixedSize(560, 640)
        self._ds_key         = ds_api_key
        self._gemini_key     = gemini_api_key
        self._deepseek_model = _tts_deepseek_model(parent)
        self._suggest_worker = None
        self._gen_worker     = None
        self._chip_btns:  dict[str, list[QPushButton]] = {}
        self._text_fields: dict[str, QLineEdit]         = {}
        self.result_prompt   = ""
        self._build()

    # ── Build UI ──────────────────────────────────────────────────
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        # Header
        h_lbl = QLabel("🧙  Prompt Wizard")
        h_lbl.setFont(QFont("", 15, QFont.Weight.Bold))
        h_lbl.setStyleSheet("background:transparent;border:none;")
        v.addWidget(h_lbl)

        sub = QLabel("Bạn trả lời vài mục chính — AI chỉ gợi ý thêm cho những câu bạn chưa điền.")
        sub.setStyleSheet(
            f"font-size:12px;color:{self._t['TEXT_MUTE']};background:transparent;border:none;"
        )
        sub.setWordWrap(True)
        v.addWidget(sub)

        # AI gợi ý nhanh
        ai_frame = QFrame()
        ai_frame.setStyleSheet(
            f"QFrame{{background:{self._t['CONTROL_BG']};border:1px solid {self._t['BORDER_SOFT']};border-radius:10px;}}"
        )
        af = QHBoxLayout(ai_frame)
        af.setContentsMargins(12, 8, 12, 8)
        af.setSpacing(8)
        self._brief_edit = QLineEdit()
        self._brief_edit.setPlaceholderText(
            "Mô tả ngắn về bạn → AI gợi ý câu chưa trả lời  (vd: shop thời trang nữ miền Nam)"
        )
        self._brief_edit.setStyleSheet(
            f"QLineEdit{{background:{self._t['SURFACE']};border:1px solid {self._t['BORDER_SOFT']};"
            "border-radius:6px;padding:4px 8px;font-size:12px;}"
            f"QLineEdit:focus{{border-color:{self._t['ACCENT']};}}"
        )
        self._brief_edit.returnPressed.connect(self._ai_suggest)
        af.addWidget(self._brief_edit, 1)
        self._btn_suggest = QPushButton("💡 AI gợi ý")
        self._btn_suggest.setFixedHeight(30)
        self._btn_suggest.setFixedWidth(90)
        self._btn_suggest.setStyleSheet(
            f"QPushButton{{background:{self._t['ACCENT']};color:white;border:none;"
            "border-radius:6px;font-size:12px;font-weight:600;}"
            f"QPushButton:hover{{background:{self._t['ACCENT_HV']};}}"
            f"QPushButton:disabled{{background:{self._t['CONTROL_BG']};color:{self._t['TEXT_FAINT']};}}"
        )
        self._btn_suggest.clicked.connect(self._ai_suggest)
        af.addWidget(self._btn_suggest)
        v.addWidget(ai_frame)

        self._suggest_status = QLabel("")
        self._suggest_status.setStyleSheet(
            f"font-size:11px;color:{self._t['TEXT_MUTE']};background:transparent;border:none;"
        )
        v.addWidget(self._suggest_status)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{self._t['BORDER_SOFT']};")
        v.addWidget(sep)

        # Scroll area — câu hỏi
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            f"QScrollBar::handle:vertical{{background:{self._t['SCROLL']};border-radius:3px;}}"
        )
        inner = QWidget()
        inner.setStyleSheet("QWidget{background:transparent;border:none;}")
        qv = QVBoxLayout(inner)
        qv.setContentsMargins(0, 0, 8, 0)
        qv.setSpacing(10)

        for key, label, chips, multi, placeholder in self._QUESTIONS:
            q_frame = QFrame()
            q_frame.setStyleSheet(
                f"QFrame{{background:{self._t['SURFACE']};border:1px solid {self._t['BORDER_SOFT']};border-radius:10px;}}"
            )
            qf = QVBoxLayout(q_frame)
            qf.setContentsMargins(12, 8, 12, 8)
            qf.setSpacing(8)

            q_lbl = QLabel(label)
            q_lbl.setStyleSheet(
                f"QLabel{{font-size:13px;font-weight:600;color:{self._t['TEXT']};"
                "background:transparent;border:none;}"
            )
            qf.addWidget(q_lbl)

            if chips:
                chip_h = QHBoxLayout()
                chip_h.setSpacing(6)
                chip_h.setContentsMargins(0, 0, 0, 0)
                btns: list[QPushButton] = []
                for chip in chips:
                    cb = QPushButton(chip)
                    cb.setFixedHeight(28)
                    cb.setCheckable(True)
                    cb.setStyleSheet(self._chip_style(False))
                    cb.clicked.connect(
                        lambda checked, k=key, c=chip, m=multi: self._toggle_chip(k, c, m)
                    )
                    chip_h.addWidget(cb)
                    btns.append(cb)
                chip_h.addStretch()
                self._chip_btns[key] = btns
                qf.addLayout(chip_h)

            if placeholder:
                txt = QLineEdit()
                txt.setPlaceholderText(placeholder)
                txt.setStyleSheet(
                    f"QLineEdit{{background:{self._t['CONTROL_BG']};border:1px solid {self._t['BORDER_SOFT']};"
                    "border-radius:6px;padding:4px 8px;font-size:12px;}"
                    f"QLineEdit:focus{{border-color:{self._t['ACCENT']};background:{self._t['SURFACE']};}}"
                )
                self._text_fields[key] = txt
                qf.addWidget(txt)

            qv.addWidget(q_frame)

        qv.addStretch()
        scroll.setWidget(inner)
        v.addWidget(scroll)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{self._t['BORDER_SOFT']};")
        v.addWidget(sep2)

        # Footer
        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(32)
        btn_cancel.clicked.connect(self.reject)
        self._btn_gen = QPushButton("✨  Tạo Prompt")
        self._btn_gen.setFixedHeight(32)
        self._btn_gen.setDefault(True)
        self._btn_gen.setStyleSheet(
            f"QPushButton{{background:{self._t['ACCENT']};color:white;border:none;"
            "border-radius:8px;padding:0 20px;font-size:13px;font-weight:600;}"
            f"QPushButton:hover{{background:{self._t['ACCENT_HV']};}}"
            f"QPushButton:disabled{{background:{self._t['CONTROL_BG']};color:{self._t['TEXT_FAINT']};}}"
        )
        self._btn_gen.clicked.connect(self._generate_prompt)
        foot.addWidget(btn_cancel)
        foot.addWidget(self._btn_gen)
        v.addLayout(foot)

    # ── Helpers ───────────────────────────────────────────────────
    def _chip_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton{{font-size:12px;background:{self._t['ACCENT']};color:white;"
                "border:none;border-radius:12px;padding:0 10px;}"
                f"QPushButton:hover{{background:{self._t['ACCENT_HV']};}}"
                f"QPushButton:pressed{{background:{self._t['ACCENT_DN']};}}"
            )
        return (
            f"QPushButton{{font-size:12px;background:{self._t['CONTROL_BG']};color:{self._t['TEXT']};"
            f"border:1px solid {self._t['BORDER_SOFT']};border-radius:12px;padding:0 10px;}}"
            f"QPushButton:hover{{background:{self._t['CONTROL_HV']};}}"
            f"QPushButton:pressed{{background:{self._t['CONTROL_DN']};}}"
        )

    def _toggle_chip(self, key: str, chip: str, multi: bool):
        btns = self._chip_btns.get(key, [])
        texts = [b.text() for b in btns]
        if chip not in texts:
            return
        idx = texts.index(chip)
        btn = btns[idx]
        if multi:
            # Qt đã tự toggle checked state khi click → chỉ cần cập nhật style
            btn.setStyleSheet(self._chip_style(btn.isChecked()))
        else:
            for b in btns:
                b.setChecked(False)
                b.setStyleSheet(self._chip_style(False))
            btn.setChecked(True)
            btn.setStyleSheet(self._chip_style(True))

    def _fill_from_suggestions(self, data: dict):
        """Điền gợi ý AI — chỉ fill những field người dùng chưa trả lời."""
        for key, value in data.items():
            if not value:
                continue
            val_str = str(value).strip()
            # Text field — bỏ qua nếu người dùng đã nhập
            if key in self._text_fields:
                if self._text_fields[key].text().strip():
                    continue          # người dùng đã điền → không ghi đè
                self._text_fields[key].setText(val_str)
            # Chips — bỏ qua nếu người dùng đã chọn ít nhất 1 chip
            if key in self._chip_btns:
                btns = self._chip_btns[key]
                if any(b.isChecked() for b in btns):
                    continue          # đã có lựa chọn → không ghi đè
                texts    = [b.text() for b in btns]
                is_multi = key in ("audience", "tone")
                candidates = [v.strip() for v in val_str.split(",")]
                for cand in candidates:
                    for i, chip_text in enumerate(texts):
                        if cand.lower() in chip_text.lower() or chip_text.lower() in cand.lower():
                            btns[i].setChecked(True)
                            btns[i].setStyleSheet(self._chip_style(True))
                            if not is_multi:
                                break

    def _gather_answers(self) -> dict:
        answers: dict[str, str] = {}
        for key, _, chips, _, _ in self._QUESTIONS:
            if key in self._chip_btns:
                selected = [b.text() for b in self._chip_btns[key] if b.isChecked()]
                answers[key] = ", ".join(selected)
            else:
                answers[key] = ""
            # Text field overrides / extends
            if key in self._text_fields:
                tf = self._text_fields[key].text().strip()
                if tf:
                    answers[key] = tf
        return answers

    # ── AI suggest ────────────────────────────────────────────────
    def _ai_suggest(self):
        brief = self._brief_edit.text().strip()
        if not brief:
            self._suggest_status.setText("⚠️  Nhập mô tả ngắn trước nhé!")
            return
        if not self._ds_key and not self._gemini_key:
            self._suggest_status.setText("⚠️  Chưa có AI key — vào Cài đặt → API Keys → thêm Gemini")
            return
        self._btn_suggest.setEnabled(False)
        self._btn_suggest.setText("...")
        self._suggest_status.setText("💡  AI đang xem câu nào cần gợi ý...")
        self._suggest_worker = SuggestAnswersWorker(
            brief, self._ds_key, self._gemini_key,
            deepseek_model=self._deepseek_model,
        )
        self._suggest_worker.done.connect(self._on_suggest_done)
        self._suggest_worker.error.connect(self._on_suggest_error)
        self._suggest_worker.start()

    def _on_suggest_done(self, data: dict):
        self._fill_from_suggestions(data)
        self._suggest_status.setText("✅  Đã gợi ý xong — đọc lại 1 lượt xem có đúng ý bạn chưa nhé!")
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("💡 AI gợi ý")

    def _on_suggest_error(self, err: str):
        self._suggest_status.setText(f"❌  {err[:60]}")
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("💡 AI gợi ý")

    # ── Generate prompt ───────────────────────────────────────────
    def _generate_prompt(self):
        if not self._ds_key and not self._gemini_key:
            QMessageBox.warning(self, "Thiếu API Key",
                                "Cần Gemini hoặc DeepSeek API key để tạo prompt.\nVào Cài đặt → API Keys để thêm key.")
            return
        answers = self._gather_answers()
        if not answers.get("product", "").strip():
            QMessageBox.warning(self, "Thiếu thông tin",
                                "Mục 5 (Sản phẩm / Lĩnh vực) là bắt buộc nhé!")
            return

        self._btn_gen.setEnabled(False)
        self._btn_gen.setText("✨ Đang tạo...")

        parts = []
        labels = {
            "purpose":  "Mục đích",
            "audience": "Đối tượng",
            "region":   "Vùng miền",
            "tone":     "Tông",
            "product":  "Sản phẩm/lĩnh vực",
            "keywords": "Từ ngữ đặc trưng",
            "avoid":    "Tuyệt đối tránh",
            "example":  "Ví dụ đúng gu",
        }
        for key, lbl in labels.items():
            val = answers.get(key, "").strip()
            if val:
                parts.append(f"{lbl}: {val}")
        full_desc = " | ".join(parts)

        self._gen_worker = PromptGeneratorWorker(
            full_desc, self._ds_key, self._gemini_key,
            deepseek_model=self._deepseek_model,
        )
        self._gen_worker.done.connect(self._on_prompt_done)
        self._gen_worker.error.connect(self._on_prompt_error)
        self._gen_worker.start()

    def _on_prompt_done(self, prompt: str):
        self.result_prompt = prompt
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("✨  Tạo Prompt")
        self.accept()

    def _on_prompt_error(self, err: str):
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("✨  Tạo Prompt")
        QMessageBox.critical(self, "Lỗi AI", err[:200])



# ── Feedback dialog ────────────────────────────────────────────────
class FeedbackDialog(QDialog):
    """In-app feedback form — gửi trực tiếp đến dev qua Telegram."""

    _CATS = ["🐛  Báo lỗi", "💡  Tính năng mới", "💬  Góp ý chung"]

    def __init__(self, parent=None, version: str = "", telegram_cfg: dict | None = None):
        super().__init__(parent)
        self._theme_mode, self._t = _theme_for(parent)
        self.setStyleSheet(get_style(self._theme_mode))
        self.setWindowTitle("Phản hồi")
        self.setFixedSize(460, 390)
        self._version = version
        self._telegram_cfg = telegram_cfg or {}
        self._sender  = None
        self._sel_cat = self._CATS[2]
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(12)

        # Title
        title = QLabel("💬  Gửi phản hồi cho dev")
        title.setFont(QFont("", 15, QFont.Weight.Bold))
        title.setStyleSheet("background:transparent;border:none;")
        v.addWidget(title)

        sub = QLabel("Góp ý, báo lỗi hoặc yêu cầu tính năng mới — sẽ đến thẳng nhà phát triển.")
        sub.setStyleSheet(f"font-size:12px;color:{self._t['TEXT_MUTE']};background:transparent;border:none;")
        sub.setWordWrap(True)
        v.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{self._t['BORDER_SOFT']};")
        v.addWidget(sep)

        # Category
        cat_lbl = QLabel("Loại phản hồi")
        cat_lbl.setStyleSheet(
            "font-size:12px;font-weight:600;background:transparent;border:none;"
        )
        v.addWidget(cat_lbl)
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        self._cat_btns: list[QPushButton] = []
        for cat in self._CATS:
            btn = QPushButton(cat)
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setChecked(cat == self._sel_cat)
            btn.setStyleSheet(self._cat_style(cat == self._sel_cat))
            btn.clicked.connect(lambda _, c=cat: self._select_cat(c))
            self._cat_btns.append(btn)
            chip_row.addWidget(btn)
        chip_row.addStretch()
        v.addLayout(chip_row)

        # Title input
        t_lbl = QLabel("Tiêu đề ngắn")
        t_lbl.setStyleSheet(
            "font-size:12px;font-weight:600;background:transparent;border:none;"
        )
        v.addWidget(t_lbl)
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Tóm tắt vấn đề trong 1 dòng...")
        v.addWidget(self._title_edit)

        # Description
        d_lbl = QLabel("Mô tả chi tiết")
        d_lbl.setStyleSheet(
            "font-size:12px;font-weight:600;background:transparent;border:none;"
        )
        v.addWidget(d_lbl)
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText(
            "Mô tả cụ thể: lỗi xảy ra khi nào, muốn tính năng gì, góp ý gì..."
        )
        self._desc_edit.setMinimumHeight(80)
        v.addWidget(self._desc_edit)

        # Footer
        foot = QHBoxLayout()
        foot.setSpacing(8)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"font-size:11px;color:{self._t['TEXT_MUTE']};background:transparent;border:none;"
        )
        foot.addWidget(self._status_lbl, 1)
        btn_cancel = QPushButton("Đóng")
        btn_cancel.setFixedHeight(32)
        btn_cancel.clicked.connect(self.reject)
        self._btn_send = QPushButton("📨  Gửi phản hồi")
        self._btn_send.setFixedHeight(32)
        self._btn_send.setDefault(True)
        self._btn_send.setStyleSheet(
            f"QPushButton{{background:{self._t['ACCENT']};color:white;border:none;"
            "border-radius:8px;padding:0 16px;font-size:13px;font-weight:600;}"
            f"QPushButton:hover{{background:{self._t['ACCENT_HV']};}}"
            f"QPushButton:disabled{{background:{self._t['CONTROL_BG']};color:{self._t['TEXT_FAINT']};}}"
        )
        self._btn_send.clicked.connect(self._send)
        foot.addWidget(btn_cancel)
        foot.addWidget(self._btn_send)
        v.addLayout(foot)

    def _cat_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton{{font-size:12px;background:{self._t['ACCENT']};color:white;"
                "border:none;border-radius:14px;padding:0 12px;}"
            )
        return (
            f"QPushButton{{font-size:12px;background:{self._t['CONTROL_BG']};color:{self._t['TEXT']};"
            f"border:1px solid {self._t['BORDER_SOFT']};border-radius:14px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{self._t['CONTROL_HV']};}}"
        )

    def _select_cat(self, cat: str):
        self._sel_cat = cat
        for btn, c in zip(self._cat_btns, self._CATS):
            btn.setChecked(c == cat)
            btn.setStyleSheet(self._cat_style(c == cat))

    def _send(self):
        title_text = self._title_edit.text().strip()
        desc_text  = self._desc_edit.toPlainText().strip()
        if not title_text and not desc_text:
            self._status_lbl.setText("⚠️  Nhập tiêu đề hoặc mô tả nhé!")
            return

        msg = (
            f"*{self._sel_cat}*\n\n"
            f"*Phiên bản:* v{self._version}\n"
            f"*Tiêu đề:* {title_text or '(không có)'}\n\n"
            f"{desc_text}"
        )
        self._btn_send.setEnabled(False)
        self._btn_send.setText("Đang gửi...")
        self._status_lbl.setText("")
        self._sender = FeedbackSender(
            msg,
            self._telegram_cfg.get("bot_token", ""),
            self._telegram_cfg.get("chat_id", ""),
        )
        self._sender.done.connect(self._on_sent)
        self._sender.error.connect(self._on_send_error)
        self._sender.start()

    def _on_sent(self):
        self._btn_send.setEnabled(True)
        self._btn_send.setText("✅  Đã gửi!")
        self._status_lbl.setText("Cảm ơn bạn đã phản hồi! 🙏")
        QTimer.singleShot(2500, self.accept)

    def _on_send_error(self, err: str):
        self._btn_send.setEnabled(True)
        self._btn_send.setText("📨  Gửi phản hồi")
        msg = err
        if "Telegram token/chat id" in err or "token/chat" in err:
            msg = "Chưa có cấu hình feedback nội bộ trên máy này."
        self._status_lbl.setText(f"❌  {msg[:80]}")
        self._status_lbl.setToolTip(err)
