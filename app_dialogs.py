import re
import json

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QFrame, QScrollArea, QStackedWidget,
    QGridLayout, QComboBox, QSizePolicy, QSpacerItem,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QIcon

from app_constants import (
    EMOJI_LIST, PROMPTS, PROMPT_TEMPLATES, GEMINI_CHAT_PROMPT,
    DEFAULT_PROMPT, DEFAULT_PROMPT_FUNNY, VOICE_ID,
)
from app_workers import PromptGeneratorWorker, SuggestAnswersWorker, FeedbackSender

class EmojiPickerDialog(QDialog):
    """Bảng chọn emoji — 6 cột, button đủ lớn, full visible không cần scroll."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chọn icon")
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
        inner.setStyleSheet("QWidget{background:#f5f5f7;border:none;}")
        grid = QGridLayout(inner)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        cols = 6
        for i, em in enumerate(EMOJI_LIST):
            btn = QPushButton(em)
            btn.setFixedSize(52, 52)
            btn.setStyleSheet(
                "QPushButton{font-size:26px;border:1.5px solid #e5e5ea;"
                "border-radius:10px;background:#ffffff;}"
                "QPushButton:hover{background:#e8f0fd;border-color:#0071e3;}"
                "QPushButton:pressed{background:#dce9fd;}"
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
        self.setWindowTitle("Thêm phong cách" if not existing else "Sửa phong cách")
        self.setMinimumSize(560, 740)
        self.resize(580, 800)
        self._icon            = data.get("icon", "🎯")
        self._result: dict    = {}
        self._ds_key          = ds_api_key
        self._gemini_key      = gemini_api_key
        self._gen_worker      = None
        self._suggest_worker  = None
        self._wiz_chip_btns:  dict[str, list[QPushButton]] = {}
        self._wiz_text_fields: dict[str, QLineEdit]        = {}
        self._build(data)

    def _build(self, data: dict):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        # ── Icon + Name ───────────────────────────────────────────
        top = QHBoxLayout()
        self._icon_btn = QPushButton(self._icon)
        self._icon_btn.setFixedSize(48, 48)
        self._icon_btn.setStyleSheet(
            "QPushButton{font-size:26px;border:1px solid #d2d2d7;"
            "border-radius:10px;background:#f5f5f7;}"
            "QPushButton:hover{background:#e5e5ea;}"
            "QPushButton:pressed{background:#d2d2d7;}"
        )
        self._icon_btn.clicked.connect(self._pick_icon)
        top.addWidget(self._icon_btn)
        top.addSpacing(10)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_lbl = QLabel("Tên hiển thị  (đặt tùy ý)")
        name_lbl.setStyleSheet(
            "font-size:11px;color:#6e6e73;background:transparent;border:none;"
        )
        self._name_edit = QLineEdit(data.get("name", ""))
        self._name_edit.setPlaceholderText("Vd: Chốt đơn vui, Tư vấn miền Tây, Kể chuyện drama...")
        name_col.addWidget(name_lbl)
        name_col.addWidget(self._name_edit)
        top.addLayout(name_col, 1)
        v.addLayout(top)

        # ── Temperature slider ────────────────────────────────────
        cr_header = QHBoxLayout()
        cr_lbl = QLabel("Mức sáng tạo")
        cr_lbl.setStyleSheet(
            "font-size:13px;color:#1d1d1f;background:transparent;border:none;"
        )
        # Đọc giá trị cũ: ưu tiên temperature float, fallback từ creative bool
        _init_temp = data.get("temperature",
                              0.7 if data.get("creative", False) else 0.3)
        self._temp_val = round(_init_temp, 2)

        self._temp_lbl = QLabel(f"{self._temp_val:.2f}")
        self._temp_lbl.setFixedWidth(36)
        self._temp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._temp_lbl.setStyleSheet(
            "font-size:13px;font-weight:600;color:#0071e3;"
            "background:transparent;border:none;"
        )
        cr_header.addWidget(cr_lbl)
        cr_header.addStretch()
        cr_header.addWidget(self._temp_lbl)
        v.addLayout(cr_header)

        slider_row = QHBoxLayout()
        lbl_l = QLabel("🎯 Nghiêm túc")
        lbl_r = QLabel("🎨 Sáng tạo")
        for l in (lbl_l, lbl_r):
            l.setStyleSheet(
                "font-size:11px;color:#aeaeb2;background:transparent;border:none;"
            )
        self._temp_slider = QSlider(Qt.Orientation.Horizontal)
        self._temp_slider.setRange(0, 100)          # 0–100 = 0.00–1.00
        self._temp_slider.setValue(int(self._temp_val * 100))
        self._temp_slider.setTickInterval(10)
        self._temp_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px; background: #e5e5ea; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 18px; height: 18px; margin: -7px 0;
                background: #0071e3; border-radius: 9px; border: none;
            }
            QSlider::sub-page:horizontal {
                background: #0071e3; border-radius: 2px;
            }
        """)
        self._temp_slider.valueChanged.connect(self._on_temp_changed)
        slider_row.addWidget(lbl_l)
        slider_row.addWidget(self._temp_slider, 1)
        slider_row.addWidget(lbl_r)
        v.addLayout(slider_row)

        # ── AI Prompt Generator — inline wizard ──────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#e5e5ea;")
        v.addWidget(sep)

        ai_lbl = QLabel("✨  Tạo prompt với AI — trả lời nhanh rồi nhấn Tạo")
        ai_lbl.setStyleSheet(
            "font-size:12px;font-weight:600;color:#1d1d1f;"
            "background:transparent;border:none;"
        )
        v.addWidget(ai_lbl)

        # AI gợi ý nhanh từ mô tả ngắn
        ai_frame = QFrame()
        ai_frame.setStyleSheet(
            "QFrame{background:#f0f7ff;border:1px solid #bfdbfe;border-radius:8px;}"
        )
        af = QHBoxLayout(ai_frame)
        af.setContentsMargins(12, 8, 12, 8)
        af.setSpacing(8)
        self._brief_edit = QLineEdit()
        self._brief_edit.setPlaceholderText(
            "Mô tả ngắn → AI điền gợi ý câu chưa chọn  (vd: shop thời trang nữ miền Nam)"
        )
        self._brief_edit.setStyleSheet(
            "QLineEdit{background:#fff;border:1px solid #bfdbfe;"
            "border-radius:6px;padding:4px 8px;font-size:12px;}"
        )
        self._brief_edit.returnPressed.connect(self._ai_suggest_wiz)
        af.addWidget(self._brief_edit, 1)
        self._btn_suggest = QPushButton("💡 AI gợi ý")
        self._btn_suggest.setFixedHeight(28)
        self._btn_suggest.setFixedWidth(86)
        self._btn_suggest.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:6px;font-size:12px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
            "QPushButton:disabled{background:#a8d0fb;}"
        )
        self._btn_suggest.clicked.connect(self._ai_suggest_wiz)
        af.addWidget(self._btn_suggest)
        v.addWidget(ai_frame)

        # 7 câu hỏi inline — scroll area
        wiz_scroll = QScrollArea()
        wiz_scroll.setWidgetResizable(True)
        wiz_scroll.setFrameShape(QFrame.Shape.NoFrame)
        wiz_scroll.setFixedHeight(300)
        wiz_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        wiz_inner = QWidget()
        wiz_inner.setStyleSheet("QWidget{background:transparent;border:none;}")
        wiz_v = QVBoxLayout(wiz_inner)
        wiz_v.setContentsMargins(0, 4, 8, 4)
        wiz_v.setSpacing(8)

        for key, label, chips, multi, placeholder in PromptWizardDialog._QUESTIONS:
            q_frame = QFrame()
            q_frame.setStyleSheet(
                "QFrame{background:#ffffff;border:1px solid #e5e5ea;border-radius:10px;}"
            )
            qf = QVBoxLayout(q_frame)
            qf.setContentsMargins(12, 8, 12, 8)
            qf.setSpacing(8)

            q_lbl = QLabel(label)
            q_lbl.setStyleSheet(
                "QLabel{font-size:12px;font-weight:600;color:#1d1d1f;"
                "background:transparent;border:none;}"
            )
            qf.addWidget(q_lbl)

            if chips:
                chip_h = QHBoxLayout()
                chip_h.setSpacing(6)
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
                    chip_h.addWidget(cb)
                    btns.append(cb)
                chip_h.addStretch()
                self._wiz_chip_btns[key] = btns
                qf.addLayout(chip_h)

            if placeholder:
                txt = QLineEdit()
                txt.setPlaceholderText(placeholder)
                txt.setStyleSheet(
                    "QLineEdit{background:#f5f5f7;border:1px solid #e5e5ea;"
                    "border-radius:6px;padding:4px 8px;font-size:12px;}"
                    "QLineEdit:focus{border-color:#0071e3;background:#fff;}"
                )
                self._wiz_text_fields[key] = txt
                qf.addWidget(txt)

            wiz_v.addWidget(q_frame)

        wiz_v.addStretch()
        wiz_scroll.setWidget(wiz_inner)
        v.addWidget(wiz_scroll)

        # Tạo Prompt button + status
        gen_row = QHBoxLayout()
        self._btn_gen = QPushButton("✨  Tạo Prompt")
        self._btn_gen.setFixedHeight(34)
        self._btn_gen.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:8px;padding:0 20px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:pressed{background:#005bb5;}"
            "QPushButton:disabled{background:#a8d0fb;}"
        )
        self._btn_gen.clicked.connect(self._generate_from_wizard)
        gen_row.addStretch()
        gen_row.addWidget(self._btn_gen)
        v.addLayout(gen_row)

        self._ai_status = QLabel("")
        self._ai_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._ai_status.setStyleSheet(
            "font-size:11px;color:#6e6e73;background:transparent;border:none;"
        )
        v.addWidget(self._ai_status)

        # ── Prompt textarea ───────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#e5e5ea;")
        v.addWidget(sep2)

        p_lbl = QLabel("System prompt  (có thể sửa tự do)")
        p_lbl.setStyleSheet(
            "font-size:11px;color:#6e6e73;background:transparent;border:none;"
        )
        v.addWidget(p_lbl)
        self._prompt = QTextEdit()
        self._prompt.setPlainText(data.get("prompt", ""))
        self._prompt.setPlaceholderText(
            "Nhập thủ công hoặc nhấn ✨ Tạo để AI viết cho bạn..."
        )
        v.addWidget(self._prompt)

        # ── Footer buttons ────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setFixedHeight(28)
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
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        v.addLayout(btn_row)

    # ── Wizard chip helpers ───────────────────────────────────────
    def _wiz_chip_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton{font-size:12px;background:#0071e3;color:white;"
                "border:none;border-radius:12px;padding:0 10px;}"
                "QPushButton:hover{background:#0077ed;}"
                "QPushButton:pressed{background:#005bb5;}"
            )
        return (
            "QPushButton{font-size:12px;background:#f0f0f5;color:#1d1d1f;"
            "border:1px solid #d2d2d7;border-radius:12px;padding:0 10px;}"
            "QPushButton:hover{background:#e5e5ea;}"
            "QPushButton:pressed{background:#d2d2d7;}"
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
            self._ai_status.setText("⚠️ Nhập mô tả ngắn trước nhé!")
            return
        if not self._ds_key and not self._gemini_key:
            self._ai_status.setText("⚠️ Chưa có AI key — vào Settings → API Keys → thêm Gemini (miễn phí)")
            return
        self._btn_suggest.setEnabled(False)
        self._btn_suggest.setText("...")
        self._ai_status.setText("💡 AI đang gợi ý...")
        self._suggest_worker = SuggestAnswersWorker(brief, self._ds_key, self._gemini_key)
        self._suggest_worker.done.connect(self._on_suggest_wiz_done)
        self._suggest_worker.error.connect(self._on_suggest_wiz_error)
        self._suggest_worker.start()

    def _on_suggest_wiz_done(self, data: dict):
        self._fill_wiz_from_suggestions(data)
        self._ai_status.setText("✅ Đã gợi ý — kiểm tra lại rồi nhấn Tạo Prompt nhé!")
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("💡 AI gợi ý")

    def _on_suggest_wiz_error(self, err: str):
        self._ai_status.setText(f"❌ {err[:60]}")
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("💡 AI gợi ý")

    def _generate_from_wizard(self):
        if not self._ds_key and not self._gemini_key:
            self._ai_status.setText("⚠️ Chưa có AI key — vào Settings → API Keys → thêm Gemini (miễn phí)")
            return
        answers = self._gather_wizard_answers()
        if not answers.get("product", "").strip():
            self._ai_status.setText("⚠️ Mục 5 (Sản phẩm / Lĩnh vực) là bắt buộc nhé!")
            return

        self._btn_gen.setEnabled(False)
        self._btn_gen.setText("✨ Đang tạo...")
        self._ai_status.setText("⏳ AI đang viết prompt...")

        labels = {
            "purpose": "Mục đích", "audience": "Đối tượng",
            "region":  "Vùng miền", "tone":    "Tông",
            "product": "Sản phẩm/lĩnh vực",
            "keywords": "Từ ngữ đặc trưng", "avoid": "Tuyệt đối tránh",
        }
        parts = [f"{lbl}: {answers[k]}" for k, lbl in labels.items() if answers.get(k)]
        full_desc = " | ".join(parts)

        self._gen_worker = PromptGeneratorWorker(full_desc, self._ds_key, self._gemini_key)
        self._gen_worker.done.connect(self._on_wiz_gen_done)
        self._gen_worker.error.connect(self._on_wiz_gen_error)
        self._gen_worker.start()

    def _on_wiz_gen_done(self, prompt: str):
        self._prompt.setPlainText(prompt)
        self._ai_status.setText("✅ Xong! Bạn có thể chỉnh sửa thêm.")
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("✨  Tạo Prompt")
        # Auto-fill tên nếu chưa có
        if not self._name_edit.text().strip():
            product = self._gather_wizard_answers().get("product", "")
            words   = product.split()
            self._name_edit.setText(" ".join(words[:2]) if words else product[:20])

    def _on_wiz_gen_error(self, err: str):
        self._ai_status.setText(f"❌ {err[:80]}")
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("✨  Tạo Prompt")

    def _pick_icon(self):
        dlg = EmojiPickerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen:
            self._icon = dlg.chosen
            self._icon_btn.setText(self._icon)

    def _on_temp_changed(self, value: int):
        self._temp_val = value / 100.0
        self._temp_lbl.setText(f"{self._temp_val:.2f}")

    def _save(self):
        name   = self._name_edit.text().strip()
        prompt = self._prompt.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Thiếu tên", "Nhập tên phong cách nhé!")
            return
        if not prompt:
            QMessageBox.warning(self, "Thiếu prompt",
                                "Nhập prompt hoặc nhấn ✨ Tạo để AI viết nhé!")
            return
        self._result = {
            "icon":        self._icon,
            "name":        name,
            "prompt":      prompt,
            "temperature": self._temp_val,
            "creative":    self._temp_val >= 0.5,   # backward compat
        }
        self.accept()

    def get_result(self) -> dict:
        return self._result



# ── Drop Zone widget ───────────────────────────────────────────────
class DropZone(QFrame):
    files_added = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(90)
        self._set_idle_style()
        lbl = QLabel("📷  Kéo thả ảnh vào đây", self)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:#6e6e73; font-size:13px; border:none; background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(lbl)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_idle_style(self):
        self.setStyleSheet(
            "QFrame{border:2px dashed #d2d2d7;border-radius:10px;background:#ffffff;}"
            "QFrame:hover{border-color:#0071e3;}"
        )

    def _set_hover_style(self):
        self.setStyleSheet(
            "QFrame{border:2px dashed #0071e3;border-radius:10px;background:#f0f7ff;}"
        )

    def mousePressEvent(self, e):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn ảnh chat", "",
            "Images (*.png *.jpg *.jpeg *.webp)"
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
            if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                files.append(p)
        if files:
            self.files_added.emit(files)


# ── Prompt Wizard dialog ───────────────────────────────────────────
class PromptWizardDialog(QDialog):
    """Wizard 7 câu hỏi chi tiết — AI tạo system prompt TTS tốt nhất."""

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
    ]

    def __init__(self, parent=None, ds_api_key: str = "", gemini_api_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Prompt Wizard")
        self.setFixedSize(560, 640)
        self._ds_key         = ds_api_key
        self._gemini_key     = gemini_api_key
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

        sub = QLabel("Bạn trả lời 7 câu hỏi — AI chỉ gợi ý thêm cho những câu bạn chưa điền.")
        sub.setStyleSheet(
            "font-size:12px;color:#6e6e73;background:transparent;border:none;"
        )
        sub.setWordWrap(True)
        v.addWidget(sub)

        # AI gợi ý nhanh
        ai_frame = QFrame()
        ai_frame.setStyleSheet(
            "QFrame{background:#f0f7ff;border:1px solid #bfdbfe;border-radius:10px;}"
        )
        af = QHBoxLayout(ai_frame)
        af.setContentsMargins(12, 8, 12, 8)
        af.setSpacing(8)
        self._brief_edit = QLineEdit()
        self._brief_edit.setPlaceholderText(
            "Mô tả ngắn về bạn → AI gợi ý câu chưa trả lời  (vd: shop thời trang nữ miền Nam)"
        )
        self._brief_edit.setStyleSheet(
            "QLineEdit{background:#fff;border:1px solid #bfdbfe;"
            "border-radius:6px;padding:4px 8px;font-size:12px;}"
        )
        self._brief_edit.returnPressed.connect(self._ai_suggest)
        af.addWidget(self._brief_edit, 1)
        self._btn_suggest = QPushButton("💡 AI gợi ý")
        self._btn_suggest.setFixedHeight(30)
        self._btn_suggest.setFixedWidth(90)
        self._btn_suggest.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:6px;font-size:12px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:disabled{background:#a8d0fb;}"
        )
        self._btn_suggest.clicked.connect(self._ai_suggest)
        af.addWidget(self._btn_suggest)
        v.addWidget(ai_frame)

        self._suggest_status = QLabel("")
        self._suggest_status.setStyleSheet(
            "font-size:11px;color:#6e6e73;background:transparent;border:none;"
        )
        v.addWidget(self._suggest_status)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#e5e5ea;")
        v.addWidget(sep)

        # Scroll area — 7 câu hỏi
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#c7c7cc;border-radius:3px;}"
        )
        inner = QWidget()
        inner.setStyleSheet("QWidget{background:transparent;border:none;}")
        qv = QVBoxLayout(inner)
        qv.setContentsMargins(0, 0, 8, 0)
        qv.setSpacing(10)

        for key, label, chips, multi, placeholder in self._QUESTIONS:
            q_frame = QFrame()
            q_frame.setStyleSheet(
                "QFrame{background:#ffffff;border:1px solid #e5e5ea;border-radius:10px;}"
            )
            qf = QVBoxLayout(q_frame)
            qf.setContentsMargins(12, 8, 12, 8)
            qf.setSpacing(8)

            q_lbl = QLabel(label)
            q_lbl.setStyleSheet(
                "QLabel{font-size:13px;font-weight:600;color:#1d1d1f;"
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
                    "QLineEdit{background:#f5f5f7;border:1px solid #e5e5ea;"
                    "border-radius:6px;padding:4px 8px;font-size:12px;}"
                    "QLineEdit:focus{border-color:#0071e3;background:#fff;}"
                )
                self._text_fields[key] = txt
                qf.addWidget(txt)

            qv.addWidget(q_frame)

        qv.addStretch()
        scroll.setWidget(inner)
        v.addWidget(scroll)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#e5e5ea;")
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
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:8px;padding:0 20px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:disabled{background:#a8d0fb;}"
        )
        self._btn_gen.clicked.connect(self._generate_prompt)
        foot.addWidget(btn_cancel)
        foot.addWidget(self._btn_gen)
        v.addLayout(foot)

    # ── Helpers ───────────────────────────────────────────────────
    def _chip_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton{font-size:12px;background:#0071e3;color:white;"
                "border:none;border-radius:12px;padding:0 10px;}"
                "QPushButton:hover{background:#0077ed;}"
                "QPushButton:pressed{background:#005bb5;}"
            )
        return (
            "QPushButton{font-size:12px;background:#f0f0f5;color:#1d1d1f;"
            "border:1px solid #d2d2d7;border-radius:12px;padding:0 10px;}"
            "QPushButton:hover{background:#e5e5ea;}"
            "QPushButton:pressed{background:#d2d2d7;}"
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
            self._suggest_status.setText("⚠️  Chưa có AI key — vào Settings → API Keys → thêm Gemini (miễn phí)")
            return
        self._btn_suggest.setEnabled(False)
        self._btn_suggest.setText("...")
        self._suggest_status.setText("💡  AI đang xem câu nào cần gợi ý...")
        self._suggest_worker = SuggestAnswersWorker(brief, self._ds_key, self._gemini_key)
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
                                "Cần Gemini hoặc DeepSeek API key để tạo prompt.\nVào Settings → API Keys → thêm Gemini (miễn phí)!")
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
        }
        for key, lbl in labels.items():
            val = answers.get(key, "").strip()
            if val:
                parts.append(f"{lbl}: {val}")
        full_desc = " | ".join(parts)

        self._gen_worker = PromptGeneratorWorker(full_desc, self._ds_key, self._gemini_key)
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
        sub.setStyleSheet("font-size:12px;color:#6e6e73;background:transparent;border:none;")
        sub.setWordWrap(True)
        v.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#e5e5ea;")
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
            "font-size:11px;color:#6e6e73;background:transparent;border:none;"
        )
        foot.addWidget(self._status_lbl, 1)
        btn_cancel = QPushButton("Đóng")
        btn_cancel.setFixedHeight(32)
        btn_cancel.clicked.connect(self.reject)
        self._btn_send = QPushButton("📨  Gửi phản hồi")
        self._btn_send.setFixedHeight(32)
        self._btn_send.setDefault(True)
        self._btn_send.setStyleSheet(
            "QPushButton{background:#0071e3;color:white;border:none;"
            "border-radius:8px;padding:0 16px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#0077ed;}"
            "QPushButton:disabled{background:#a8d0fb;}"
        )
        self._btn_send.clicked.connect(self._send)
        foot.addWidget(btn_cancel)
        foot.addWidget(self._btn_send)
        v.addLayout(foot)

    def _cat_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton{font-size:12px;background:#0071e3;color:white;"
                "border:none;border-radius:14px;padding:0 12px;}"
            )
        return (
            "QPushButton{font-size:12px;background:#f0f0f5;color:#1d1d1f;"
            "border:1px solid #d2d2d7;border-radius:14px;padding:0 12px;}"
            "QPushButton:hover{background:#e5e5ea;}"
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
        self._status_lbl.setText(f"❌  {err[:60]}")


