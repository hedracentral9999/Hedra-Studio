import sys
import os
import json
import base64
import requests
import webbrowser
import subprocess
import traceback
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QSlider, QPushButton, QSystemTrayIcon,
    QMenu, QDialog, QLineEdit, QFileDialog, QMessageBox,
    QFrame, QTabWidget, QListWidget, QListWidgetItem,
    QScrollArea, QStackedWidget, QGridLayout, QComboBox,
    QSizePolicy, QSpacerItem,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QIcon, QFont, QAction, QPixmap, QColor, QPainter
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from version import VERSION, GITHUB_REPO

VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
MODEL    = "eleven_v3"
# Ưu tiên tương thích phát trên macOS/Windows + chất lượng tốt cho giọng nói.
EL_OUTPUT_FORMAT = "mp3_44100_128"

DEFAULT_PROMPT = """Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS với giọng Adam.

## GIỌNG ADAM — ĐẶC ĐIỂM
Giọng nam, trầm ấm, quyền lực, kiên định (Dominant, Firm).
Tags phù hợp nhất: [professional] [assertive] [thoughtful] [impressed] [curious] [warmly] [happy] [questioning] [reassuring]
Tags TUYỆT ĐỐI TRÁNH: [giggles] [nervous] [sheepishly] [whining]

## QUY TẮC BẮT BUỘC

### 1. NỘI DUNG
- GIỮ NGUYÊN 100% nội dung gốc — không thêm, không bớt, không đổi nghĩa
- Chỉ được: thêm tags, viết hoa, thêm dấu câu, sửa chính tả rõ ràng

### 2. VIẾT TẮT → MỞ RỘNG
a → anh | e → em | u → bạn | mk/mik → mình
k/ko/kg → không | dc/đc → được | vs → với
ck → chuyển khoản | ship → ship (giữ nguyên)

### 3. CHÍNH TẢ & TÊN RIÊNG
- Sửa lỗi rõ ràng: kỹ thuạt→kỹ thuật, phứt tạp→phức tạp
- Viết hoa địa danh: ninh bình→Ninh Bình, hà nội→Hà Nội
- Viết hoa thương hiệu: samsung dex→Samsung DeX, note 9→Note 9, iphone→iPhone

### 4. SỐ & TIỀN TỆ
- Số tiền: 650k→sáu trăm năm mươi nghìn, 1tr→một triệu, 1.5tr→một triệu rưỡi
- Số đếm: 1-2→một đến hai, 3-5 ngày→ba đến năm ngày
- Phần trăm: 50%→năm mươi phần trăm

### 5. AUDIO TAGS
[curious] → câu mở đầu, đặt vấn đề
[professional] → giải thích kỹ thuật, thông tin sản phẩm
[assertive] → khẳng định, cam kết, chốt vấn đề
[questioning] → câu hỏi, xác nhận
[warmly] → chào hỏi, cảm ơn
[happy] → phản ứng tích cực, đồng ý
[reassuring] → trấn an lo lắng
[thoughtful] → trước khi giải thích sâu
[impressed] → phản ứng ngạc nhiên tích cực

### 6. NHẤN MẠNH — VIẾT HOA
Chỉ CAPS từ thật sự quan trọng: MIỄN PHÍ, NGON, SỚM, LUÔN, TỐI GIẢN, CHẮC CHẮN, ĐẢM BẢO

### 7. KÉO DÀI ÂM — TẠO CẢM XÚC TỰ NHIÊN
Kéo dài nguyên âm cuối từ để giọng đọc nhấn nhá, không đều đều như robot.
Dùng tiết chế — 1-2 chỗ mỗi đoạn, chọn chỗ cảm xúc thật sự lên:
- Trấn an: "yên tâm nhaaa" / "được ngheee"
- Xác nhận ấm: "đúng rồiiii" / "có ngheee"
- Nhấn câu kết: "nhanh lắmmm" / "rẻ lắmmm"
Nguyên tắc: kéo dài đúng chỗ cảm xúc — sai chỗ thì phản tác dụng

### 8. PAUSE & NHỊP
... → dừng cân nhắc, trước thông tin quan trọng
— → ngắt nhanh giữa 2 ý liên tiếp

### 9. CẤU TRÚC
- Mỗi câu/ý trên một dòng riêng
- Dòng trống giữa các ý khác nhau
- Xóa: kkk, haha, hehe, hihi, :), XD, ^^, :D

### 10. OUTPUT
- Chỉ trả về kịch bản đã xử lý
- Không giải thích, không ghi chú, không markdown"""

DEFAULT_PROMPT_FUNNY = """Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS với giọng Adam — phong cách HÀI HƯỚC cường điệu, dí dỏm kiểu Nam bộ, thân thiện như bạn thân ruột.

## GIỌNG ADAM — THẢ XÍCH HOÀN TOÀN
Giọng nam trầm ấm, phản ứng cường điệu và bất ngờ, gần gũi tới mức hơi lố một chút nhưng vẫn lịch sự.
Tags ưu tiên: [happy] [impressed] [warmly] [curious] [questioning] [reassuring]
Tags TUYỆT ĐỐI TRÁNH: [giggles] [nervous] [sheepishly] [whining] [assertive] [professional]

## QUY TẮC BẮT BUỘC

### 1. NỘI DUNG
- GIỮ NGUYÊN 100% nội dung gốc — không thêm ý, không bớt ý, không đổi nghĩa
- Chỉ được: thêm tags, viết hoa, thêm dấu câu, sửa chính tả, thêm từ đệm tự nhiên

### 2. VIẾT TẮT → MỞ RỘNG
a → anh | e → em | u → bạn | mk/mik → mình
k/ko/kg → không | dc/đc → được | vs → với
ck → chuyển khoản | ship → ship (giữ nguyên)

### 3. SỐ & TIỀN TỆ
- 650k→sáu trăm năm mươi nghìn, 1tr→một triệu, 1.5tr→một triệu rưỡi
- 1-2→một đến hai, 50%→năm mươi phần trăm

### 4. AUDIO TAGS — DÙNG NHƯ DIỄN VIÊN HÀI
[impressed]   → LUÔN dùng khi có thông tin tốt, bất ngờ — phản ứng cường điệu, ngạc nhiên giả vờ
[happy]       → câu xác nhận, đồng ý, tin vui — thoải mái dùng nhiều
[warmly]      → chào hỏi, cảm ơn, kết thúc thân thiện
[curious]     → bắt đầu câu hỏi kiểu tò mò hóm hỉnh
[questioning] → hỏi ngược lại vui, xác nhận kiểu "thật không vậy trời"
[reassuring]  → trấn an kiểu "dễ ợt luôn, không lo"

### 5. VIẾT HOA CƯỜNG ĐIỆU — DÙNG MẠNH TAY
Đây là vũ khí chính tạo tính hài. Phải có ít nhất 2-3 chỗ CAPS per đoạn:
TRỜI ƠI | ĐỈNh CỦA ĐỈNH | SIÊU XỊN | KHỦNG | DỄ NHƯ ĂN KẸO | DỄ ỢT
CHUẨN KHÔNG CẦN CHỈNH | NGON LÀNH | HẾT XẨY | XỊN XÒ | THẦN THÁNH
GÌ MÀ | ỦA | CHỨ SAO | LUÔN LUÔN | KHÔNG ĐÙA ĐÂU NHA | THẬT SỰ

### 5b. KÉO DÀI ÂM — VŨ KHÍ BÍ MẬT TẠO CẢM XÚC
Kéo dài nguyên âm = giọng đọc thật sự kéo dài âm đó, nghe như người đang diễn.
Kết hợp với CAPS và ... để tạo nhịp hài hoàn hảo:
- Bất ngờ vui: "trờiiiiii ơi" / "ủaaaa" / "gì vậyyyy"
- Xác nhận cường điệu: "có LUÔNNNN" / "đượccccc chứ" / "ngon lắmmmmm"
- Kết câu thân: "nha anhhh" / "đó nghennn" / "vậy đóóóó"
- Combo killer: "thật ra á... DỄ ỢT luônnnn, không đùa đâu NHAAA!"
Dùng tối thiểu 2 chỗ mỗi đoạn — thiếu thì mất hết tính sống động

### 5c. CÂU CẢM THÁN / TIẾNG CƯỜI KIỂU HÀI HƯỚC
Được phép thêm các cụm cảm thán sau khi ngữ cảnh thật sự vui, bất ngờ, thân thiết:
"anh iuuuuuuuuuu" | "úi xờiiiiiiiiiii" | "hahahahaaa" | "kkkkkkk"

Quy tắc dùng:
- Dùng như gia vị tạo duyên, tối đa 1 cụm mỗi 2-3 câu; không nhồi liên tục.
- "anh iuuuuuuuuuu" dùng khi chốt thân thiện, cảm ơn, trấn an hoặc làm mềm câu bán hàng.
- "úi xờiiiiiiiiiii" dùng khi bất ngờ, khen món/ngữ cảnh quá xịn, phản ứng kiểu Nam bộ.
- "hahahahaaa" và "kkkkkkk" dùng khi câu có punchline vui; không dùng trong thông tin nghiêm túc như giá, cam kết, bảo hành.
- Có thể viết hoa phần punchline trước đó, rồi thả tiếng cười ở cuối để câu nghe tự nhiên.

### 6. PAUSE DRAMATIC — TẠO HÀI BẰNG NHỊP
... → dừng rồi "plot twist" bất ngờ — đây là cú punchline
— → ngắt nhanh giữa setup và punchline
Công thức vàng: "[setup bình thường]... [PUNCHLINE CAPS cường điệu]"
Ví dụ: "nghe có vẻ khó lắm... thật ra DỄ NHƯ ĂN KẸO luôn anh ơi KHÔNG ĐÙA ĐÂU!"

### 7. TỪ ĐỆM NAM BỘ — BẮT BUỘC CÓ MỖI ĐOẠN
Bất ngờ: "ủa", "ủa mà", "gì mà", "trời ơi"
Xác nhận hóm: "vậy đó", "đó nha", "nghen", "nha anh", "đó anh ơi"
Thân thiện: "nói thật nha", "thật ra á", "kiểu như", "xong là xong"
Cường điệu: "luôn luôn", "siêu siêu", "cực kỳ", "không đùa đâu nha"

### 8. CẤU TRÚC
- Mỗi câu/ý trên một dòng riêng — nhịp nhanh
- Không dùng emoji/text-face như :), XD, ^^, :D
- Không xóa tiếng cười nếu đang dùng đúng tone hài hước; ưu tiên dạng kéo dài tự nhiên: "hahahahaaa", "kkkkkkk"

### 9. OUTPUT
- Chỉ trả về kịch bản đã xử lý
- Không giải thích, không ghi chú, không markdown

---

## VÍ DỤ CHUẨN (học kỹ tone này)

INPUT: còn box 650k không shop ơi
OUTPUT: [curious] Ủaaaa anh hỏi còn box sáu trăm năm mươi nghìn không?
[happy] Còn CHỨ anh — LUÔN LUÔN có sẵn nhaaaa!

INPUT: dạ còn a ơi sáng nay e vừa lắp xong chục box kkk
OUTPUT: [impressed] TRỜIIIIII ƠI còn chứ anh — sáng nay em vừa lắp xong cả chục box...
[happy] SIÊU XỊN không, úi xờiiiiiiiiiii... không đùa đâu nha anhhhh!

INPUT: mình k rành kỹ thuật lắm sợ phức tạp
OUTPUT: [impressed] Ủa GÌ MÀ phức tạp anh ơiiiii — không rành kỹ thuật thì CÀNG TỐT...
[reassuring] thật ra á... DỄ NHƯ ĂN KẸO luônnnn, KHÔNG ĐÙA ĐÂU NHAAA!

INPUT: bên shop có ship cod không
OUTPUT: [questioning] Ủa anh hỏi có ship COD không?
[happy] Có LUÔNNNN anh ơi — COD CHUẨN KHÔNG CẦN CHỈNH đó nghennn!

INPUT: dạ có nhé a cọc 150k còn lại cod nhận hàng kiểm tra đúng đủ mới thanh toán nhé
OUTPUT: [warmly] Dạ có LUÔN nha anhhh — cọc một trăm năm mươi nghìn thôi...
[happy] Còn lại COD, nhận hàng kiểm tra ưng rồi mới trả — THẦN THÁNH chưa anhhhh!

INPUT: ship về miền tây được không
OUTPUT: [impressed] Ủa ĐƯỢC CHỨ anh — miền Tây ship NGON LÀNHHH luôn, không lo gì hết nhaaaa, anh iuuuuuuuuuu!

INPUT: mấy ngày nhận được vậy
OUTPUT: [curious] Anh ở đâu để em báo chính xác nhaaaa...
[reassuring] thường thì ba đến bốn ngày thôi — NHANH LẮMMM đó anh ơi, hahahahaaa không đùa!"""

PROMPTS = {
    "🎯  Nghiêm túc": DEFAULT_PROMPT,
    "😄  Hài hước":   DEFAULT_PROMPT_FUNNY,
}

# ── Template starters cho AI prompt generation ────────────────────
PROMPT_TEMPLATES = [
    ("🛍️", "Bán hàng",     "Phong cách bán hàng online vui vẻ, thuyết phục, thân thiện kiểu shop Facebook/Zalo"),
    ("👔", "Chuyên nghiệp", "Tư vấn chuyên nghiệp, lịch sự, rõ ràng, súc tích — dùng cho dịch vụ hoặc B2B"),
    ("😊", "Thân thiện",    "Thân thiện miền Nam, gần gũi, ấm áp, không quá hài hước, phù hợp mọi lứa tuổi"),
    ("📚", "Giáo dục",      "Giải thích dễ hiểu, từng bước rõ ràng, kiên nhẫn, phù hợp dạy học hoặc hướng dẫn"),
    ("💼", "Doanh nghiệp",  "Phong cách corporate formal, súc tích, trung lập, chuyên nghiệp cao"),
    ("🎭", "Kể chuyện",     "Kể chuyện cuốn hút, có cảm xúc, tạo không khí, dẫn dắt từng bước"),
    ("🌟", "Truyền cảm hứng", "Motivational, truyền cảm hứng, mạnh mẽ, tích cực, phù hợp content coaching"),
    ("🍜", "Ẩm thực",       "Mô tả món ăn hấp dẫn, gợi cảm giác thèm, sinh động, ấm cúng kiểu food vlog"),
]

# ── Emoji palette cho custom style picker ─────────────────────────
EMOJI_LIST = [
    "🎯","😄","🚀","💡","🔥","⭐","🎨","📢","💬","🎤","🎧","🎵",
    "📝","✨","💫","🌟","🏆","👑","💎","🎭","😎","🤩","😊","🥳",
    "🎉","🌈","🦄","🐉","🦁","🤖","👔","🧠","❤️","💪","🙌","👏",
    "🤝","✅","⚡","🔮","📣","🗣️","💼","🎬","🌺","🍀","🎸","🌊",
]


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

    def __init__(self, parent=None, existing: dict = None, ds_api_key: str = ""):
        super().__init__(parent)
        data = existing or {}
        self.setWindowTitle("Thêm phong cách" if not existing else "Sửa phong cách")
        self.setMinimumSize(560, 740)
        self.resize(580, 800)
        self._icon            = data.get("icon", "🎯")
        self._result: dict    = {}
        self._ds_key          = ds_api_key
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
        if not self._ds_key:
            self._ai_status.setText("⚠️ Chưa có DeepSeek API key")
            return
        self._btn_suggest.setEnabled(False)
        self._btn_suggest.setText("...")
        self._ai_status.setText("💡 AI đang gợi ý...")
        self._suggest_worker = SuggestAnswersWorker(brief, self._ds_key)
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
        if not self._ds_key:
            self._ai_status.setText("⚠️ Chưa có DeepSeek API key — vào Settings → API Keys")
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

        self._gen_worker = PromptGeneratorWorker(full_desc, self._ds_key)
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


class VoiceFetcher(QThread):
    """Fetch danh sách voices từ ElevenLabs API."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            r = requests.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            if r.status_code == 200:
                voices = r.json().get("voices", [])
                voices.sort(key=lambda v: v.get("name", "").lower())
                self.done.emit(voices)
            else:
                self.error.emit(f"HTTP {r.status_code}")
        except Exception as e:
            self.error.emit(str(e))


class SharedVoiceFetcher(QThread):
    """Fetch voices từ ElevenLabs Shared Voice Library."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, language: str = "", search: str = "", page_size: int = 30):
        super().__init__()
        self.api_key   = api_key
        self.language  = language
        self.search    = search
        self.page_size = page_size

    def run(self):
        try:
            params = {"page_size": self.page_size, "sort": "trending"}
            if self.language:
                params["language"] = self.language
            if self.search:
                params["search"] = self.search
            r = requests.get(
                "https://api.elevenlabs.io/v1/shared-voices",
                headers={"xi-api-key": self.api_key},
                params=params,
                timeout=12,
            )
            if r.status_code == 200:
                voices = r.json().get("voices", [])
                self.done.emit(voices)
            else:
                self.error.emit(f"HTTP {r.status_code}")
        except Exception as e:
            self.error.emit(str(e))


class AudioPreviewDownloader(QThread):
    """Download preview audio về temp file để play in-app."""
    done  = pyqtSignal(str)   # local file path
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        import tempfile
        try:
            r = requests.get(self.url, timeout=15, stream=True)
            if r.status_code == 200:
                url_no_query = self.url.split("?", 1)[0].lower()
                if url_no_query.endswith(".wav"):
                    suffix = ".wav"
                elif url_no_query.endswith(".ogg"):
                    suffix = ".ogg"
                else:
                    suffix = ".mp3"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                for chunk in r.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp.close()
                self.done.emit(tmp.name)
            else:
                self.error.emit(f"HTTP {r.status_code}")
        except Exception as e:
            self.error.emit(str(e))


class AddSharedVoiceWorker(QThread):
    """Add a shared voice vào account ElevenLabs."""
    done  = pyqtSignal(str, str)   # (voice_id, voice_name)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, voice_id: str, public_user_id: str, name: str):
        super().__init__()
        self.api_key        = api_key
        self.voice_id       = voice_id
        self.public_user_id = public_user_id
        self.name           = name

    def run(self):
        try:
            r = requests.post(
                f"https://api.elevenlabs.io/v1/voices/add/{self.public_user_id}/{self.voice_id}",
                headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
                json={"name": self.name},
                timeout=15,
            )
            if r.status_code == 200:
                new_id = r.json().get("voice_id", self.voice_id)
                self.done.emit(new_id, self.name)
            else:
                self.error.emit(f"HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            self.error.emit(str(e))


class PromptGeneratorWorker(QThread):
    """Dùng DeepSeek để tạo system prompt từ mô tả ngắn của user."""
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    _META_PROMPT = """Bạn là chuyên gia viết system prompt cho TTS với ElevenLabs v3.

Nhiệm vụ: Dựa trên mô tả ngắn, tạo system prompt hoàn chỉnh để AI enhance kịch bản TTS.

System prompt phải có đủ các phần:
1. Mô tả vai trò + phong cách + tông giọng phù hợp mô tả
2. Quy tắc xử lý viết tắt tiếng Việt (a→anh, e→em, k→không, dc→được...)
3. Quy tắc số & tiền tệ (650k→sáu trăm năm mươi nghìn, 1tr→một triệu...)
4. Hướng dẫn dùng ElevenLabs v3 audio tags phù hợp với phong cách
   Tags khả dụng: [professional] [assertive] [thoughtful] [impressed]
   [curious] [warmly] [happy] [questioning] [reassuring]
   → Chỉ dùng tags phù hợp với phong cách được mô tả
5. Quy tắc nhấn mạnh bằng CAPS (tối thiểu 2-3 từ per đoạn nếu phong cách cần)
6. Quy tắc pause và nhịp (... và —)
7. Quy tắc output: chỉ trả về kịch bản đã xử lý, không giải thích

Nếu mô tả có trường "Từ ngữ đặc trưng":
- BẮT BUỘC tạo một mục riêng tên "TỪ NGỮ ĐẶC TRƯNG".
- Giữ nguyên văn từng từ/cụm từ user nhập, không tự bỏ, không thay bằng từ đồng nghĩa.
- Viết rule rõ: ưu tiên giữ các cụm này khi chúng đã có trong kịch bản gốc; có thể thêm tự nhiên khi phù hợp ngữ cảnh; không lạm dụng.
- Nếu cụm từ là tiếng lóng/xưng hô/thương hiệu, không sửa chính tả và không dịch.

Nếu mô tả có trường "Tuyệt đối tránh":
- BẮT BUỘC tạo một mục riêng tên "TUYỆT ĐỐI TRÁNH" và giữ đúng các điều user đã nhập.

Trả về CHỈ nội dung system prompt, không có markdown ngoài, không có tiêu đề."""

    def __init__(self, description: str, api_key: str):
        super().__init__()
        self.description = description
        self.api_key     = api_key

    @staticmethod
    def _extract_field(description: str, label: str) -> str:
        for part in description.split(" | "):
            key, sep, value = part.partition(":")
            if sep and key.strip().lower() == label.lower():
                return value.strip()
        return ""

    @staticmethod
    def _split_terms(value: str) -> list[str]:
        terms = []
        for term in re.split(r"[,;\\n]+", value):
            cleaned = term.strip().strip('"').strip("'").strip()
            if cleaned:
                terms.append(cleaned)
        return terms

    def _ensure_required_user_terms(self, prompt: str) -> str:
        keywords = self._extract_field(self.description, "Từ ngữ đặc trưng")
        avoid = self._extract_field(self.description, "Tuyệt đối tránh")
        additions = []

        if keywords:
            missing = [
                term for term in self._split_terms(keywords)
                if term.lower() not in prompt.lower()
            ]
            if missing or "TỪ NGỮ ĐẶC TRƯNG" not in prompt.upper():
                additions.append(
                    "## TỪ NGỮ ĐẶC TRƯNG\n"
                    f"- Giữ nguyên và ưu tiên dùng tự nhiên các từ/cụm từ: {keywords}\n"
                    "- Không sửa chính tả, không dịch, không thay bằng từ đồng nghĩa các cụm trên.\n"
                    "- Nếu kịch bản gốc đã có các cụm này, giữ lại; nếu phù hợp ngữ cảnh, có thể thêm với tần suất vừa phải."
                )

        if avoid:
            avoid_terms = self._split_terms(avoid) or [avoid]
            missing = [
                term for term in avoid_terms
                if term.lower() not in prompt.lower()
            ]
            if missing or "TUYỆT ĐỐI TRÁNH" not in prompt.upper():
                additions.append(
                    "## TUYỆT ĐỐI TRÁNH\n"
                    f"- {avoid}"
                )

        if not additions:
            return prompt
        return prompt.rstrip() + "\n\n" + "\n\n".join(additions)

    def run(self):
        try:
            res = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": self._META_PROMPT},
                        {"role": "user",   "content": f"Tạo prompt cho phong cách: {self.description}"},
                    ],
                    "temperature": 0.6,
                    "max_tokens":  1800,
                },
                timeout=30,
            )
            if res.status_code == 200:
                prompt = res.json()["choices"][0]["message"]["content"].strip()
                self.done.emit(self._ensure_required_user_terms(prompt))
            else:
                self.error.emit(f"DeepSeek {res.status_code}: {res.text[:200]}")
        except Exception as e:
            self.error.emit(str(e))


class SuggestAnswersWorker(QThread):
    """Dùng DeepSeek để gợi ý 7 trường từ mô tả ngắn — trả về dict."""
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    _SYSTEM = """Bạn là trợ lý tư vấn phong cách TTS chuyên nghiệp.
Dựa trên mô tả ngắn của user, hãy phân tích và gợi ý 7 trường thông tin để tạo prompt TTS tốt nhất.

Trả về JSON hợp lệ với đúng 7 keys (không markdown, không giải thích):
{
  "purpose":  "mục đích chính — 1 trong: Bán hàng | Tư vấn | Giáo dục | Kể chuyện | Truyền cảm hứng | Khác",
  "audience": "đối tượng (nhiều giá trị cách nhau dấu phẩy nếu cần)",
  "region":   "vùng miền — 1 trong: Miền Nam | Miền Bắc | Trung lập",
  "tone":     "tông cảm xúc (nhiều giá trị cách nhau dấu phẩy nếu cần)",
  "product":  "sản phẩm hoặc lĩnh vực cụ thể",
  "keywords": "từ ngữ đặc trưng muốn dùng trong kịch bản TTS",
  "avoid":    "điều cần tránh khi enhance kịch bản"
}"""

    def __init__(self, description: str, api_key: str):
        super().__init__()
        self.description = description
        self.api_key     = api_key

    def run(self):
        try:
            res = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": self._SYSTEM},
                        {"role": "user",   "content": f"Mô tả: {self.description}"},
                    ],
                    "temperature": 0.4,
                    "max_tokens":  600,
                },
                timeout=20,
            )
            if res.status_code == 200:
                raw = res.json()["choices"][0]["message"]["content"].strip()
                # Xóa markdown code block nếu có
                if raw.startswith("```"):
                    parts = raw.split("```")
                    raw = parts[1] if len(parts) > 1 else raw
                    if raw.startswith("json"):
                        raw = raw[4:]
                data = json.loads(raw.strip())
                self.done.emit(data)
            else:
                self.error.emit(f"DeepSeek {res.status_code}")
        except json.JSONDecodeError:
            self.error.emit("AI trả về sai format — thử lại nhé!")
        except Exception as e:
            self.error.emit(str(e))


# ── Gemini Chat → Script prompt ────────────────────────────────────
GEMINI_CHAT_PROMPT = """Bạn là chuyên gia viết kịch bản TTS cho shop bán Samsung DeX box.

NHIỆM VỤ:
Đọc ảnh chụp đoạn chat Zalo và tạo kịch bản TTS tự nhiên, chuẩn để đọc thành tiếng.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NHẬN DIỆN NGƯỜI NÓI:
- Bong bóng chat bên PHẢI (màu xanh lam) = Shop (xưng "anh", gọi khách là "em")
- Bong bóng chat bên TRÁI (màu trắng)    = Khách (xưng "em", gọi shop là "anh")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIẾNG NAM BỘ — GIẢI MÃ TRƯỚC KHI VIẾT:

"về là lụm / về lụm luôn"  → sẽ mua/lấy ngay, không phải câu hỏi kỹ thuật
"lụm luôn" / "chốt luôn"   → quyết định mua rồi
"Cài tất luôn / cài hết đi" → khách YÊU CẦU shop cài đặt đầy đủ (850k), không phải "đã cài rồi"
"roaiiii"                   → "rồi" nhấn mạnh (xác nhận)
"hã" / "hả"                 → câu hỏi, xác nhận lại
"b"                         → "bạn" (cách gọi thân mật) → khi viết kịch bản đổi thành "em" (khách) hoặc "anh" (shop) theo ngôi đúng
"k / ko / kg"               → không
"đc / dc"                   → được
"lắp đc"                    → lắp được

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KIẾN THỨC SẢN PHẨM — BẮT BUỘC NẮM RÕ:

[SAMSUNG DEX — HỘP TO]
• 650k — hộp lắp sẵn, mua về tự lắp:
  - Tháo nắp lưng, tháo pin, cắm dây nguồn của box vào là xong
  - Muốn tự khởi động: dùng dây rút của box kéo nút nguồn → tự bật
  - Yêu cầu: điện thoại phải bật sẵn Samsung DeX HOẶC màn còn cảm ứng được
    (màn ám, đốm, sọc vẫn OK — miễn còn cảm ứng để bấm accept lần đầu)
  - Lần đầu cắm HDMI → bấm chấp nhận 1 lần → sau đó tự nhận mọi màn hình

• 850k — gửi máy về shop làm hộ (dịch vụ đầy đủ):
  - Bật 4K (mặc định chỉ Full HD)
  - Login CH Play hộ (DeX không cho login thông thường)
  - Cài Shizuku + Google Mouse Pro 2 (dùng bàn phím chơi game)
  - Cài phần mềm Android TV
  - Nhận về: cắm sạc zin + dây HDMI + chuột phím → xài ngay

• Kèm máy (combo):
  - S10: 1.700k | S20: 1.900k | N20 Ultra: 2.400k
  (gồm hộp to + hub 5in1/6in1 + quạt 120x120)

• Nguồn điện: Type-C PD 20W+ chính hãng — bắt buộc để cấp nguồn đúng

[SAMSUNG DEX — HỘP NHỎ — CHO XE Ô TÔ]
• 500k — hộp nhỏ tự build, không có hub, quạt 40x40
• 650k — gửi máy về shop làm hộ
• Dùng chính cho Android Auto trên xe
• Muốn dùng Samsung DeX với hộp nhỏ → cần mua thêm hub ngoài (không có sẵn)

[VẬN CHUYỂN & CHI NHÁNH]
• Hộp không kèm máy → luôn xuất từ Bắc Ninh
• Khách gửi máy về làm, ở miền Nam → gửi về Sa Đéc
• Thời gian ship: 3–4 ngày
• Thanh toán: cọc 150k, còn lại COD khi nhận hàng

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUY TẮC VIẾT KỊCH BẢN:

1. Bám sát chat gốc — KHÔNG thêm thông tin khách chưa đề cập
   → Khách hỏi hộp không kèm máy: KHÔNG mention giá combo/kèm máy
   → Khách chưa hỏi thời gian ship: KHÔNG tự thêm "3-4 ngày" vào lời shop
2. Không assume — khách nói có S10 ≠ đã bật DeX → shop phải hỏi lại
3. Dùng kiến thức sản phẩm để enrich tự nhiên — không nhồi nhét
4. Xóa thông tin nhạy cảm — TUYỆT ĐỐI KHÔNG NHẮC ĐẾN dưới bất kỳ hình thức nào:
   - Số điện thoại → xóa hoàn toàn khỏi kịch bản
   - Địa chỉ chi tiết (số nhà, ấp, xã) → chỉ giữ tỉnh/thành phố
   - Thông tin ngân hàng, số tài khoản, STK → xóa
   - Danh thiếp / contact card → XÓA HOÀN TOÀN, KHÔNG ĐƯỢC viết "(Khách gửi danh thiếp)", "(Kèm liên lạc)", hay bất cứ ghi chú nào về việc chia sẻ thông tin liên lạc
5. Không dùng "dạ" trong lời shop
6. Ngôi xưng nhất quán: shop = anh, khách = em
   → "b" trong chat shop gọi khách → đổi thành "em"
   → "b" trong chat khách gọi shop → đổi thành "anh"
7. Ngôn ngữ tự nhiên như nói chuyện thật, không văn viết
8. Shop hỏi đúng chỗ khi cần clarify kỹ thuật
9. Chốt đơn: chỉ ghi "đã nhận cọc" — không ghi số tiền giao dịch cụ thể

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT:
- KHÔNG có nhãn "Khách:" hay "Shop:" — chỉ xuất text thuần
- Mỗi lượt thoại = một đoạn văn, cách nhau 1 dòng trống
- Câu ngắn, rõ ràng — tránh câu dài gộp nhiều thông tin

VÍ DỤ CHUẨN (ví dụ 1 — chat đơn giản):
Bên anh còn hộp Samsung DeX không? Em thấy clip trên TikTok nè.

Còn nha em! Sáu trăm năm mươi nghìn — hộp anh làm sẵn rồi, em mua về cắm vào là chạy được liền.

Giá sáu trăm rưỡi hả anh? Máy chính em xài S10.

Đúng giá rồi em! Anh hỏi thêm tí — máy em đã bật sẵn Samsung DeX chưa, hay màn hình còn dùng được không?

Màn em vẫn còn dùng được anh.

Vậy ổn rồi em! Lần đầu cắm vào bấm chấp nhận trên màn một lần là xong, sau đó tự nhận luôn không cần bấm nữa.

Ngon vậy, mua về là xài luôn hả anh?

Đúng rồi em! Chốt đơn nha, em cọc một trăm năm mươi nghìn, còn lại thanh toán khi nhận hàng. Hàng xuất từ Bắc Ninh, tầm ba đến bốn ngày là tới em.

Vậy em đặt, giao về Vĩnh Long nha anh.

Anh nhận cọc rồi, đang xử lý đơn, em chờ hàng nha!

VÍ DỤ CHUẨN (ví dụ 2 — khách dùng tiếng Nam "về là lụm", "cài tất luôn"):
Alo anh ơi! Em thấy TikTok về box Samsung DeX, anh còn không?

Còn nè em! Bên anh đang có. Em cần gì anh tư vấn cho.

S10 với S20 giá khác nhau hả anh? Hộp không kèm máy giá sáu trăm năm mươi nghìn đúng không anh?

Đúng rồi em! Hộp không kèm máy thì sáu trăm năm mươi nghìn, lắp được mọi đời Samsung. Em có sẵn máy nào rồi?

Em có S10 rồi, mua hộp về là lấy luôn anh ơi.

S10 thì giá sáu trăm năm mươi nghìn em. Anh hỏi tí — máy em đã bật sẵn Samsung DeX chưa, hay màn hình còn dùng được không?

Màn máy em vẫn OK anh, cắm vào là xài được luôn.

Vậy ổn rồi em! Lần đầu cắm vào bấm chấp nhận một lần là xong, sau đó tự nhận luôn. Chốt sáu trăm năm mươi nghìn nha, em cọc một trăm năm mươi nghìn, còn lại thanh toán khi nhận hàng.

Anh nhận cọc rồi, đang xử lý đơn, em chờ hàng nha!"""


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
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


# ── Update checker ─────────────────────────────────────────────────
class UpdateChecker(QThread):
    update_found = pyqtSignal(str, str)
    no_update    = pyqtSignal(str)
    error        = pyqtSignal(str)

    def run(self):
        try:
            res = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=5
            )
            if res.status_code != 200:
                self.error.emit(f"GitHub trả về lỗi {res.status_code}")
                return
            data = res.json()
            tag_name = data.get("tag_name")
            if not tag_name:
                self.error.emit("Không đọc được tag release mới nhất")
                return
            latest = str(tag_name).lstrip("v")
            if not self._is_newer(latest, VERSION):
                self.no_update.emit(latest)
                return
            html_url = data.get("html_url")
            if not html_url:
                return
            download_url = None
            for asset in data.get("assets", []):
                name = str(asset.get("name", "")).lower()
                if sys.platform == "darwin" and name.endswith(".dmg"):
                    download_url = asset.get("browser_download_url"); break
                elif sys.platform == "win32" and name.endswith(".exe"):
                    download_url = asset.get("browser_download_url"); break
            # Emit: download_url nếu có file trực tiếp, ngược lại emit html_url để mở browser
            self.update_found.emit(latest, download_url or html_url)
        except Exception as e:
            self.error.emit(str(e))

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        try:
            return [int(x) for x in latest.split(".")] > [int(x) for x in current.split(".")]
        except Exception:
            return False


# ── Auto-updater downloader ────────────────────────────────────────
class UpdateDownloader(QThread):
    progress = pyqtSignal(int)
    done     = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            import tempfile
            r = requests.get(self.url, stream=True, timeout=60)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            suffix = ".dmg" if sys.platform == "darwin" else ".exe"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            downloaded = 0
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    tmp.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        self.progress.emit(int(downloaded * 100 / total))
            tmp.close()
            self.done.emit(tmp.name)
        except Exception as e:
            self.error.emit(str(e))


# ── TTS Worker thread ──────────────────────────────────────────────
class Worker(QThread):
    status = pyqtSignal(str)
    done   = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, text: str, speed: float, filename: str, settings: dict):
        super().__init__()
        self.text     = text
        self.speed    = speed
        self.filename = filename
        self.s        = settings

    def run(self):
        try:
            self.status.emit("Đang enhance với DeepSeek...")
            enhanced = self._enhance(self.text)
            self.status.emit("Đang generate audio...")
            audio = self._tts(enhanced)
            out_dir = self.s.get("output_dir", DEFAULT_OUT)
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, self.filename + ".mp3")
            with open(path, "wb") as f:
                f.write(audio)
            self.done.emit(path)
        except Exception as e:
            self.error.emit(str(e))

    def _enhance(self, text: str) -> str:
        api_key = self.s.get("ds_api_key", "")
        if not api_key:
            raise Exception("⚠️ Chưa nhập DeepSeek API key.\n📌 Vào Settings → tab API Keys để thêm.")
        res = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": self.s.get("enhance_prompt", DEFAULT_PROMPT)},
                    {"role": "user",   "content": self.text},
                ],
                # Dùng temperature từ style (slider), fallback về creative bool nếu chưa có
                "temperature": self.s.get(
                    "enhance_style_temperature",
                    0.7 if self.s.get("enhance_style_creative", False) else 0.3
                ),
                "max_tokens":  2000,
            },
            timeout=30,
        )
        if res.status_code != 200:
            raise Exception(f"DeepSeek {res.status_code}: {res.text[:200]}")
        return res.json()["choices"][0]["message"]["content"].strip()

    def _tts(self, text: str) -> bytes:
        keys = self.s.get("el_api_keys", [])
        if not keys:
            old = self.s.get("el_api_key", "").strip()
            keys = [old] if old else []
        keys = [k.strip() for k in keys if k.strip()]
        if not keys:
            raise Exception("⚠️ Chưa nhập ElevenLabs API key.\n📌 Vào Settings → tab API Keys để thêm.")
        last_err = None
        for idx, key in enumerate(keys, 1):
            label = f"key {idx}/{len(keys)} (...{key[-6:]})"
            self.status.emit(f"Đang generate audio [{label}]...")
            voice_id = self.s.get("selected_voice_id") or VOICE_ID
            tts_body: dict = {
                "text":     text,
                "model_id": MODEL,
                "output_format": EL_OUTPUT_FORMAT,
                "voice_settings": {
                    "stability":        0.5,
                    "similarity_boost": 0.75,
                    "speed":            self.speed,
                },
            }
            _lang = self.s.get("tts_language_code", "")
            if _lang:
                tts_body["language_code"] = _lang
            res = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                json=tts_body,
                timeout=60,
            )
            if res.status_code == 200:
                return res.content
            body = res.text[:300]
            if res.status_code in (401, 403, 429) or \
               any(w in res.text.lower() for w in ("quota", "insufficient", "limit")):
                reason = {401: "key không hợp lệ", 403: "không có quyền",
                          429: "rate limited / hết credit"}.get(res.status_code, "hết credit")
                last_err = Exception(f"{label}: {reason}")
                if idx < len(keys):
                    self.status.emit(f"⚠️ {label} {reason} — thử key tiếp theo...")
                continue
            raise Exception(f"ElevenLabs {res.status_code}: {body}")
        raise last_err or Exception("Tất cả ElevenLabs API keys đều thất bại.")


# ── Gemini Vision Worker ───────────────────────────────────────────
class GeminiWorker(QThread):
    status = pyqtSignal(str)
    done   = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, image_paths: list, api_key: str, prompt: str = ""):
        super().__init__()
        self.image_paths = image_paths
        self.api_key     = api_key
        self.prompt      = prompt or GEMINI_CHAT_PROMPT

    def run(self):
        try:
            self.status.emit("Đang đọc ảnh chat...")
            parts = [{"text": self.prompt}]
            for path in self.image_paths:
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                ext  = path.lower().rsplit(".", 1)[-1]
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                        "png": "image/png",  "webp": "image/webp"}.get(ext, "image/jpeg")
                parts.append({"inline_data": {"mime_type": mime, "data": data}})

            self.status.emit("Gemini đang phân tích chat...")
            # Try gemini-2.5-pro first for best quality, fallback to flash
            last_err = None
            for model in ["gemini-2.5-pro", "gemini-2.5-flash"]:
                res = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={self.api_key}",
                    json={"contents": [{"parts": parts}]},
                    timeout=90,
                )
                if res.status_code == 200:
                    break
                if res.status_code in (404, 400):
                    last_err = Exception(f"Gemini {res.status_code}: {res.text[:200]}")
                    continue  # try next model
                if res.status_code == 503:
                    import time; time.sleep(3)
                    res = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{model}:generateContent?key={self.api_key}",
                        json={"contents": [{"parts": parts}]},
                        timeout=90,
                    )
                    if res.status_code == 200:
                        break
                last_err = Exception(f"Gemini {res.status_code}: {res.text[:200]}")
            if res.status_code != 200:
                raise last_err or Exception(f"Gemini {res.status_code}: {res.text[:300]}")

            candidates = res.json().get("candidates", [])
            if not candidates:
                raise Exception("Gemini không trả về kết quả")

            text = candidates[0]["content"]["parts"][0]["text"]
            self.done.emit(text.strip())
        except Exception as e:
            self.error.emit(str(e))


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
         ["Miền Nam", "Miền Trung", "Miền Bắc", "Trung lập"],
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

    def __init__(self, parent=None, ds_api_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Prompt Wizard")
        self.setFixedSize(560, 640)
        self._ds_key         = ds_api_key
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
        if not self._ds_key:
            self._suggest_status.setText("⚠️  Chưa có DeepSeek key — vào Settings → API Keys")
            return
        self._btn_suggest.setEnabled(False)
        self._btn_suggest.setText("...")
        self._suggest_status.setText("💡  AI đang xem câu nào cần gợi ý...")
        self._suggest_worker = SuggestAnswersWorker(brief, self._ds_key)
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
        if not self._ds_key:
            QMessageBox.warning(self, "Thiếu API Key",
                                "Cần DeepSeek API key để tạo prompt.\nVào Settings → API Keys!")
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

        self._gen_worker = PromptGeneratorWorker(full_desc, self._ds_key)
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


# ── Feedback sender thread ─────────────────────────────────────────
class FeedbackSender(QThread):
    """Gửi phản hồi đến Telegram Bot."""
    done  = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, text: str, bot_token: str, chat_id: str):
        super().__init__()
        self.text = text
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()

    def run(self):
        try:
            if not self.bot_token or not self.chat_id:
                self.error.emit("Chưa cấu hình Telegram token/chat id trong Settings.")
                return
            res = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id":    self.chat_id,
                    "text":       self.text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            if res.status_code == 200:
                self.done.emit()
            else:
                self.error.emit(f"Telegram {res.status_code}: {res.text[:200]}")
        except Exception as e:
            self.error.emit(str(e))


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

    def __init__(self, parent, api_key: str):
        super().__init__(parent)
        self.api_key    = api_key
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

        # ── Group: ElevenLabs ────────────────────────────────────────
        el_btn = _api_guide_btn("📖  Hướng dẫn lấy API key  →", is_ref=True)
        el_btn.setToolTip("Xem hướng dẫn từng bước đăng ký & lấy API key ElevenLabs")
        el_btn.clicked.connect(lambda: self._show_api_guide("elevenlabs"))
        v.addWidget(_svc_header("ElevenLabs", el_btn))
        grp, glay = self._group()
        self.el_keys = QTextEdit()
        self.el_keys.setPlaceholderText("sk_abc123...\nsk_def456...")
        self.el_keys.setFixedHeight(72)
        self.el_keys.setPlainText("\n".join(self.settings.get("el_api_keys", [])))
        self.el_keys.setStyleSheet(
            "QTextEdit{font-family:monospace;font-size:11px;"
            "background:transparent;border:none;}"
        )
        self._row(glay, "API Keys", self.el_keys,
                  "Mỗi key 1 dòng — tự xoay khi hết credit", last=True)
        v.addWidget(grp)

        # ── Group: DeepSeek ──────────────────────────────────────────
        ds_btn = _api_guide_btn("📖  Hướng dẫn lấy API key  →")
        ds_btn.clicked.connect(lambda: self._show_api_guide("deepseek"))
        v.addWidget(_svc_header("DeepSeek", ds_btn))
        grp2, glay2 = self._group()
        self.ds_key = QLineEdit(self.settings.get("ds_api_key", ""))
        self.ds_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ds_key.setPlaceholderText("sk-...")
        self.ds_key.setStyleSheet(
            "QLineEdit{background:transparent;border:none;font-size:13px;}"
        )
        self._row(glay2, "API Key", self.ds_key, last=True)
        v.addWidget(grp2)

        # ── Group: Gemini ────────────────────────────────────────────
        gm_btn = _api_guide_btn("📖  Hướng dẫn lấy API key  →")
        gm_btn.clicked.connect(lambda: self._show_api_guide("gemini"))
        v.addWidget(_svc_header("Gemini", gm_btn))
        grp3, glay3 = self._group()
        self.gemini_key = QLineEdit(self.settings.get("gemini_api_key", ""))
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key.setPlaceholderText("AIza...")
        self.gemini_key.setStyleSheet(
            "QLineEdit{background:transparent;border:none;font-size:13px;}"
        )
        self._row(glay3, "API Key", self.gemini_key, last=True)
        v.addWidget(grp3)

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
        dlg = AddStyleDialog(self, ds_api_key=self.settings.get("ds_api_key", ""))
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
                             ds_api_key=self.settings.get("ds_api_key", ""))
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
        key  = next((k.strip() for k in keys if k.strip()), "")
        if key:
            self._fetcher = VoiceFetcher(key)
            self._fetcher.done.connect(self._on_voices_fetched)
            self._fetcher.error.connect(lambda e: self._voice_status.setText(f"⚠️ {e}"))
            self._fetcher.start()
        else:
            self._voice_status.setText("⚠️ Chưa có ElevenLabs API key — vào API Keys để thêm.")

        return page

    def _open_voice_library(self):
        """Mở dialog browse ElevenLabs Shared Voice Library."""
        keys = self.settings.get("el_api_keys", [])
        key  = next((k.strip() for k in keys if k.strip()), "")
        if not key:
            QMessageBox.warning(self, "Thiếu API Key",
                                "Cần ElevenLabs API key để duyệt thư viện.\nVào API Keys để thêm.")
            return
        dlg = VoiceLibraryDialog(self, api_key=key)
        dlg.voice_added.connect(self._on_library_voice_added)
        dlg.exec()

    def _on_library_voice_added(self, voice_id: str, voice_name: str):
        """Sau khi add voice từ library — refresh danh sách account voices."""
        self._voice_status.setVisible(True)
        self._voice_status.setText("⏳  Đang tải lại danh sách giọng...")
        self._api_voices_grp.setVisible(False)
        keys = self.settings.get("el_api_keys", [])
        key  = next((k.strip() for k in keys if k.strip()), "")
        if key:
            self._fetcher = VoiceFetcher(key)
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
        self.settings["el_api_keys"]        = [k.strip() for k in raw_keys if k.strip()]
        self.settings["ds_api_key"]         = self.ds_key.text().strip()
        self.settings["gemini_api_key"]     = self.gemini_key.text().strip()
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


# ── Credits checker (background thread — không block UI) ──────────
class _CreditsChecker(QThread):
    done = pyqtSignal(str)

    def __init__(self, keys: list):
        super().__init__()
        self.keys = [k.strip() for k in keys if k.strip()]

    def run(self):
        try:
            total = 0
            for key in self.keys:
                r = requests.get(
                    "https://api.elevenlabs.io/v1/user/subscription",
                    headers={"xi-api-key": key}, timeout=5,
                )
                if r.status_code == 200:
                    d = r.json()
                    total += d.get("character_limit", 0) - d.get("character_count", 0)
            label = f"Credits: {total:,} còn lại"
            if len(self.keys) > 1:
                label += f"  ({len(self.keys)} keys)"
            self.done.emit(label)
        except Exception:
            self.done.emit("Không check được credits")


# ── Apple HIG palette ──────────────────────────────────────────────
BG        = "#f5f5f7"
SURFACE   = "#ffffff"
BORDER    = "#d2d2d7"
TEXT      = "#1d1d1f"
TEXT_MUTE = "#6e6e73"
ACCENT    = "#0071e3"
ACCENT_HV = "#0077ed"
SEG_BG    = "#e5e5ea"

STYLE = f"""
QWidget {{
    font-family: -apple-system, "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 13px;
    background: {BG};
    color: {TEXT};
}}
QTextEdit, QLineEdit {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    background: {SURFACE};
    color: {TEXT};
    selection-background-color: #a8d0fb;
}}
QTextEdit:focus, QLineEdit:focus {{
    border-color: {ACCENT};
    background: {SURFACE};
}}
QLabel {{ color: {TEXT}; background: transparent; }}
QPushButton {{
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 14px;
    background: {SURFACE};
    color: {TEXT};
}}
QPushButton:hover   {{ background: #ebebf0; }}
QPushButton:pressed {{ background: {SEG_BG}; }}
QPushButton:disabled {{ background: {BG}; color: {TEXT_MUTE}; border-color: {BORDER}; }}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 18px; height: 18px;
    margin: -7px 0; border-radius: 9px;
    border: none;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QFrame[frameShape="4"] {{ background: {BORDER}; max-height: 1px; border: none; }}
QScrollBar:vertical {{ width: 6px; background: transparent; }}
QScrollBar::handle:vertical {{ background: #c7c7cc; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QDialog {{ background: {BG}; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTE};
    padding: 7px 18px;
    font-size: 13px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}
QListWidget {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {SURFACE};
    padding: 4px;
}}
QListWidget::item {{
    padding: 4px 6px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background: #e8f0fe;
    color: {TEXT};
}}
"""


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
        layout.addWidget(self._section_lbl("KỊCH BẢN"))
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Paste kịch bản vào đây...")
        self.text_input.setMinimumHeight(210)
        self.text_input.setStyleSheet(
            f"QTextEdit{{border:1.5px solid #e5e5ea;border-radius:10px;"
            f"background:{SURFACE};color:{TEXT};padding:12px 14px;"
            f"font-size:14px;}}"
            f"QTextEdit:focus{{border:1.5px solid {ACCENT};}}"
        )
        layout.addWidget(self.text_input)

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

        def _on_creativity_changed(value: int):
            t = value / 100.0
            self.creativity_val.setText(f"{t:.2f}")
            self.settings["enhance_style_temperature"] = t
            self.settings["enhance_style_creative"] = t >= 0.5

        self.creativity_slider.valueChanged.connect(_on_creativity_changed)
        self._card_row(c2, "Mức độ sáng tạo", creative_w)

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
        self.btn_gen = QPushButton("🎙   Generate Audio")
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
            "Kịch bản sẽ hiện ra ở đây sau khi Gemini xử lý..."
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

    def _sync_creativity_control(self, temperature: float | None = None):
        if not hasattr(self, "creativity_slider"):
            return
        t = self.settings.get("enhance_style_temperature", 0.3) if temperature is None else temperature
        t = max(0.0, min(1.0, float(t)))
        self.creativity_slider.blockSignals(True)
        self.creativity_slider.setValue(int(t * 100))
        self.creativity_slider.blockSignals(False)
        self.creativity_val.setText(f"{t:.2f}")
        self.settings["enhance_style_temperature"] = t
        self.settings["enhance_style_creative"] = t >= 0.5

    def _quick_add_style(self):
        """Mở AddStyleDialog nhanh từ main UI."""
        dlg = AddStyleDialog(self, ds_api_key=self.settings.get("ds_api_key", ""))
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
        keys = self.settings.get("el_api_keys", [])
        if not keys:
            self.credits_lbl.setText("⚠️  Chưa có ElevenLabs API key — vào Settings")
            return
        self.credits_lbl.setText("Credits: đang tải...")
        self._credits_worker = _CreditsChecker(keys)
        self._credits_worker.done.connect(self.credits_lbl.setText)
        self._credits_worker.start()

    def _generate(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Paste kịch bản vào trước nhé!")
            return
        if not self.settings.get("el_api_keys") or not self.settings.get("ds_api_key"):
            missing = []
            if not self.settings.get("el_api_keys"):
                missing.append("🔑 ElevenLabs API Key")
            if not self.settings.get("ds_api_key"):
                missing.append("🤖 DeepSeek API Key")
            QMessageBox.warning(self, "Thiếu API Key",
                                "Cần các API key sau:\n\n"
                                + "\n".join(missing)
                                + "\n\n📌 Vào Settings → tab API Keys để thêm.")
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
        self.worker = Worker(text, speed, filename.replace(" ", "_"), self.settings)
        self.worker.status.connect(self._on_tts_status)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

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
            save_settings(self.settings)
            self._refresh_credits()
            self._rebuild_style_buttons()
            self._sync_creativity_control(self.settings.get("enhance_style_temperature", 0.3))
            self._voice_name_lbl.setText(
                self.settings.get("selected_voice_name", "Adam")
            )

    def update_settings(self, settings: dict):
        self.settings = settings
        self._refresh_credits()


# ── Tray app ───────────────────────────────────────────────────────
class TrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.settings    = load_settings()
        self.main_window = MainWindow(self.settings)

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip(f"Hedra Studio v{VERSION}")

        menu = QMenu()
        a_open     = QAction("🎙  Mở Tool");    a_open.triggered.connect(self._show_main)
        a_settings = QAction("⚙️  Settings");   a_settings.triggered.connect(self._show_settings)
        a_quit     = QAction("Quit");            a_quit.triggered.connect(self.app.quit)
        menu.addAction(a_open)
        menu.addSeparator()
        menu.addAction(a_settings)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()
        self._show_main()

    def _make_icon(self) -> QIcon:
        # Ưu tiên .icns nếu có (khi build bằng PyInstaller)
        try:
            icon_path = os.path.join(os.path.dirname(__file__) if not getattr(sys, 'frozen', False) else sys._MEIPASS, "icon.icns")
            if os.path.exists(icon_path):
                return QIcon(icon_path)
        except Exception:
            pass
        # Fallback: blue circle
        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#2563eb"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.end()
        return QIcon(px)

    def _show_main(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _show_settings(self):
        dlg = SettingsDialog(self.settings, self.main_window)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            self.main_window.update_settings(self.settings)

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self._show_main()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    _install_exception_hook()
    TrayApp().run()
