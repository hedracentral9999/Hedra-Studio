import sys
import os
import json
import requests
import webbrowser
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QSlider, QPushButton, QSystemTrayIcon,
    QMenu, QDialog, QLineEdit, QFileDialog, QMessageBox,
    QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QAction, QPixmap, QColor, QPainter

from version import VERSION, GITHUB_REPO

VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
MODEL    = "eleven_v3"

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

### 7. PAUSE & NHỊP
... → dừng cân nhắc, trước thông tin quan trọng
— → ngắt nhanh giữa 2 ý liên tiếp

### 8. CẤU TRÚC
- Mỗi câu/ý trên một dòng riêng
- Dòng trống giữa các ý khác nhau
- Xóa: kkk, haha, hehe, hihi, :), XD, ^^, :D

### 9. OUTPUT
- Chỉ trả về kịch bản đã xử lý
- Không giải thích, không ghi chú, không markdown"""

DEFAULT_PROMPT_FUNNY = """Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS với giọng Adam — phong cách HÀI HƯỚC cường điệu, dí dỏm kiểu Nam bộ, thân thiện như bạn thân.

## GIỌNG ADAM — ĐẶC ĐIỂM
Giọng nam trầm ấm được "thả xích" hoàn toàn — phản ứng cường điệu, vui vẻ quá mức, gần gũi tới mức hơi lố một chút (nhưng vẫn lịch sự).
Tags ưu tiên: [happy] [impressed] [warmly] [curious] [questioning] [reassuring]
Tags hạn chế: [assertive] [professional] [thoughtful] — tránh tối đa
Tags TUYỆT ĐỐI TRÁNH: [giggles] [nervous] [sheepishly] [whining]

## QUY TẮC BẮT BUỘC

### 1. NỘI DUNG
- GIỮ NGUYÊN 100% nội dung gốc — không thêm ý, không bớt ý, không đổi nghĩa
- Chỉ được: thêm tags, viết hoa, thêm dấu câu, sửa chính tả, thêm từ đệm tự nhiên

### 2. VIẾT TẮT → MỞ RỘNG
a → anh | e → em | u → bạn | mk/mik → mình
k/ko/kg → không | dc/đc → được | vs → với
ck → chuyển khoản | ship → ship (giữ nguyên)

### 3. CHÍNH TẢ & TÊN RIÊNG
- Sửa lỗi rõ ràng, viết hoa địa danh và thương hiệu như bình thường

### 4. SỐ & TIỀN TỆ
- 650k→sáu trăm năm mươi nghìn, 1tr→một triệu, 1.5tr→một triệu rưỡi
- 1-2→một đến hai, 50%→năm mươi phần trăm

### 5. AUDIO TAGS — DÙNG NHƯ DIỄN VIÊN HÀI
[impressed]   → LUÔN dùng khi có thông tin tốt, bất ngờ, hay ho — phản ứng cường điệu
[happy]       → câu xác nhận, đồng ý, tin vui — dùng thoải mái
[warmly]      → chào hỏi, cảm ơn, kết thúc thân thiện
[curious]     → câu hỏi, bắt đầu câu chuyện kiểu tò mò
[questioning] → hỏi ngược lại vui, xác nhận có hơi hóm
[reassuring]  → trấn an kiểu "không sao đâu anh ơi, dễ lắm"

### 6. NHẤN MẠNH HÀI HƯỚC — VIẾT HOA CƯỜNG ĐIỆU
Dùng CAPS mạnh tay cho hiệu ứng hài bất ngờ và cường điệu:
TRỜI ƠI, ĐỈNh CỦA ĐỈNH, SIÊU XỊN, KHỦNG, DỄ NHƯ ĂN KẸO, CHUẨN KHÔNG CẦN CHỈNH,
NGON LÀNH, HẾT XẨY, XONG NGAY, DỄ ỢT, GÌ MÀ, ỦA, CHỨ SAO, LUÔN LUÔN

### 7. PAUSE DRAMATIC — DÙNG NHIỀU HƠN
... → trước punchline, thông tin bất ngờ, hoặc tạo hồi hộp giả
— → plot twist, ngắt nhanh kiểu "mà thật ra..."
Ví dụ: "nghe có vẻ khó... thật ra DỄ NHƯ ĂN KẸO luôn anh ơi!"

### 8. TỪ ĐỆM NAM BỘ (thêm 1-2 từ mỗi đoạn khi phù hợp)
Nhóm bất ngờ: "ủa", "ủa mà", "gì mà", "trời"
Nhóm xác nhận: "vậy đó", "đó nha", "đó anh", "nghen", "nha anh"
Nhóm thân thiện: "nói thật nha", "thật ra", "kiểu như", "xong là", "vậy là xong"
Nhóm cường điệu: "luôn luôn", "siêu siêu", "cực kỳ", "không đùa đâu nha"

### 9. CẤU TRÚC
- Mỗi câu/ý trên một dòng riêng
- Câu ngắn — nhịp nhanh như hội thoại thật, không kéo dài
- Xóa hoàn toàn: kkk, haha, hehe, hihi, :), XD, ^^, :D

### 10. OUTPUT
- Chỉ trả về kịch bản đã xử lý
- Không giải thích, không ghi chú, không markdown

---

## VÍ DỤ

INPUT: còn box 650k không shop ơi
OUTPUT: [curious] Ủa anh hỏi còn box sáu trăm năm mươi nghìn không ạ?

INPUT: dạ còn a ơi sáng nay e vừa lắp xong chục box kkk
OUTPUT: [impressed] TRỜI ƠI còn CHỨ anh — sáng nay em vừa lắp xong chục box luôn... SIÊU XỊN không?

INPUT: bên shop có ship cod không
OUTPUT: [questioning] Ủa bên shop có ship COD không anh — để em xác nhận lại nha?

INPUT: dạ có nhé a cọc 150k còn lại cod nhận hàng kiểm tra đúng đủ mới thanh toán nhé
OUTPUT: [warmly] Dạ có LUÔN LUÔN nhé anh — cọc một trăm năm mươi nghìn... còn lại COD thôi.
[happy] Nhận hàng kiểm tra ưng rồi mới trả — CHUẨN KHÔNG CẦN CHỈNH đó anh!

INPUT: hay quá mình k rành kỹ thuật lắm sợ phức tạp
OUTPUT: [impressed] GÌ MÀ phức tạp — không rành kỹ thuật thì càng tốt...
[reassuring] thật ra DỄ NHƯ ĂN KẸO luôn anh ơi, không đùa đâu nha!

INPUT: phí ship bao nhiêu vậy shop
OUTPUT: [happy] Phí ship... để em báo nha anh — NGON LÀNH lắm đó, đừng lo!"""

PROMPTS = {
    "🎯  Nghiêm túc": DEFAULT_PROMPT,
    "😄  Hài hước":   DEFAULT_PROMPT_FUNNY,
}


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


# ── Settings helpers ───────────────────────────────────────────────
def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        # migrate old single-key format → list
        if "el_api_key" in s and "el_api_keys" not in s:
            s["el_api_keys"] = [s.pop("el_api_key")] if s["el_api_key"] else []
        return s
    return {
        "el_api_keys":    [],
        "ds_api_key":     "",
        "output_dir":     DEFAULT_OUT,
        "enhance_prompt": DEFAULT_PROMPT,
        "default_speed":  1.0,
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
    update_found = pyqtSignal(str, str)  # version, download_url

    def run(self):
        try:
            res = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=5
            )
            if res.status_code != 200:
                return
            data = res.json()
            latest = data["tag_name"].lstrip("v")
            if not self._is_newer(latest, VERSION):
                return
            url = data["html_url"]
            for asset in data.get("assets", []):
                name = asset["name"].lower()
                if sys.platform == "darwin" and name.endswith(".dmg"):
                    url = asset["browser_download_url"]
                    break
                elif sys.platform == "win32" and name.endswith(".exe"):
                    url = asset["browser_download_url"]
                    break
            self.update_found.emit(latest, url)
        except Exception:
            pass

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        try:
            return [int(x) for x in latest.split(".")] > [int(x) for x in current.split(".")]
        except Exception:
            return False


# ── Worker thread ──────────────────────────────────────────────────
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
        res = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {self.s['ds_api_key']}",
                     "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": self.s.get("enhance_prompt", DEFAULT_PROMPT)},
                    {"role": "user",   "content": self.text},
                ],
                "temperature": 0.3,
                "max_tokens":  2000,
            },
            timeout=30,
        )
        if res.status_code != 200:
            raise Exception(f"DeepSeek {res.status_code}: {res.text[:200]}")
        return res.json()["choices"][0]["message"]["content"].strip()

    def _tts(self, text: str) -> bytes:
        keys = self.s.get("el_api_keys", [])
        # backward compat: old single-key field
        if not keys:
            old = self.s.get("el_api_key", "").strip()
            keys = [old] if old else []
        keys = [k.strip() for k in keys if k.strip()]
        if not keys:
            raise Exception("Chưa nhập ElevenLabs API key. Vào Settings để thêm.")

        last_err = None
        for idx, key in enumerate(keys, 1):
            label = f"key {idx}/{len(keys)} (...{key[-6:]})"
            self.status.emit(f"Đang generate audio [{label}]...")
            res = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                json={
                    "text":     text,
                    "model_id": MODEL,
                    "voice_settings": {
                        "stability":        0.5,
                        "similarity_boost": 0.75,
                        "speed":            self.speed,
                    },
                },
                timeout=60,
            )
            if res.status_code == 200:
                return res.content

            body = res.text[:300]
            # quota / rate-limit / invalid key → try next key
            if res.status_code in (401, 403, 429) or \
               any(w in res.text.lower() for w in ("quota", "insufficient", "limit")):
                reason = {401: "key không hợp lệ", 403: "không có quyền",
                          429: "rate limited / hết credit"}.get(res.status_code, "hết credit")
                last_err = Exception(f"{label}: {reason}")
                if idx < len(keys):
                    self.status.emit(f"⚠️ {label} {reason} — thử key tiếp theo...")
                continue

            # other errors (5xx, etc.) → raise immediately
            raise Exception(f"ElevenLabs {res.status_code}: {body}")

        raise last_err or Exception("Tất cả ElevenLabs API keys đều thất bại.")


# ── Settings dialog ────────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()
        self.setWindowTitle("⚙️  Settings")
        self.setMinimumWidth(520)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        def section(label, widget):
            layout.addWidget(QLabel(f"<b>{label}</b>"))
            layout.addWidget(widget)

        layout.addWidget(QLabel("<b>ElevenLabs API Keys</b> <span style='color:#6b7280;font-weight:normal'>(mỗi key 1 dòng — tự động xoay khi hết credit)</span>"))
        self.el_keys = QTextEdit()
        self.el_keys.setPlaceholderText("sk_abc123...\nsk_def456...\nsk_ghi789...")
        self.el_keys.setFixedHeight(80)
        self.el_keys.setPlainText("\n".join(self.settings.get("el_api_keys", [])))
        self.el_keys.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self.el_keys)

        self.ds_key = QLineEdit(self.settings.get("ds_api_key", ""))
        self.ds_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ds_key.setPlaceholderText("sk-...")
        section("DeepSeek API Key", self.ds_key)

        layout.addWidget(QLabel("<b>Output Folder</b>"))
        row = QHBoxLayout()
        self.out_dir = QLineEdit(self.settings.get("output_dir", DEFAULT_OUT))
        self.out_dir.setReadOnly(True)
        btn_browse = QPushButton("Chọn...")
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse)
        row.addWidget(self.out_dir)
        row.addWidget(btn_browse)
        layout.addLayout(row)

        layout.addWidget(QLabel("<b>Enhance Prompt</b>"))
        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        for name, prompt_text in PROMPTS.items():
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "QPushButton{border:1px solid #d1d5db;border-radius:5px;"
                "padding:2px 10px;background:#f9fafb;}"
                "QPushButton:hover{background:#e5e7eb;}"
            )
            btn.clicked.connect(lambda checked, t=prompt_text: self.prompt.setPlainText(t))
            style_row.addWidget(btn)
        style_row.addStretch()
        layout.addLayout(style_row)
        self.prompt = QTextEdit()
        self.prompt.setPlainText(self.settings.get("enhance_prompt", DEFAULT_PROMPT))
        self.prompt.setMinimumHeight(180)
        layout.addWidget(self.prompt)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        btns = QHBoxLayout()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("💾  Lưu")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save)
        btn_save.setStyleSheet(
            "QPushButton{background:#2563eb;color:white;border-radius:6px;"
            "padding:6px 18px;border:none;}"
            "QPushButton:hover{background:#1d4ed8;}"
        )
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)
        layout.addLayout(btns)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn output folder")
        if folder:
            self.out_dir.setText(folder)

    def _save(self):
        raw_keys = self.el_keys.toPlainText().strip().splitlines()
        self.settings["el_api_keys"]    = [k.strip() for k in raw_keys if k.strip()]
        self.settings["ds_api_key"]     = self.ds_key.text().strip()
        self.settings["output_dir"]     = self.out_dir.text()
        self.settings["enhance_prompt"] = self.prompt.toPlainText()
        self.accept()

    def get_settings(self) -> dict:
        return self.settings


# ── Main window ────────────────────────────────────────────────────
STYLE = """
QWidget {
    font-family: -apple-system, "Segoe UI", sans-serif; font-size: 13px;
    background: #ffffff; color: #1f2937;
}
QTextEdit, QLineEdit {
    border: 1px solid #d1d5db; border-radius: 6px; padding: 6px;
    background: #ffffff; color: #1f2937;
}
QTextEdit:focus, QLineEdit:focus { border-color: #2563eb; }
QLabel { color: #1f2937; background: transparent; }
QPushButton {
    border: 1px solid #d1d5db; border-radius: 6px;
    padding: 5px 14px; background: #f9fafb; color: #1f2937;
}
QPushButton:hover { background: #f3f4f6; }
QSlider { background: transparent; }
QFrame { background: transparent; }
"""

class MainWindow(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.worker   = None
        self.setWindowTitle(f"🎙  Hedra Studio  v{VERSION}")
        self.setMinimumWidth(460)
        self.setMinimumHeight(540)
        self.setStyleSheet(STYLE)
        self._build()
        self._refresh_credits()
        self._check_update()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header_row = QHBoxLayout()
        title = QLabel(f"🎙  Hedra Studio")
        title.setFont(QFont("", 15, QFont.Weight.Bold))
        ver_lbl = QLabel(f"v{VERSION}")
        ver_lbl.setStyleSheet("color:#9ca3af; font-size:11px;")
        header_row.addWidget(title)
        header_row.addWidget(ver_lbl)
        header_row.addStretch()
        btn_settings = QPushButton("⚙️  Settings")
        btn_settings.setFixedHeight(30)
        btn_settings.clicked.connect(self.open_settings)
        header_row.addWidget(btn_settings)
        layout.addLayout(header_row)

        # Update banner (hidden by default)
        self.update_banner = QPushButton()
        self.update_banner.setVisible(False)
        self.update_banner.setStyleSheet(
            "QPushButton{background:#fef9c3;color:#92400e;border:1px solid #fde68a;"
            "border-radius:6px;padding:5px 12px;text-align:left;}"
            "QPushButton:hover{background:#fef08a;}"
        )
        self.update_banner.clicked.connect(self._open_update)
        layout.addWidget(self.update_banner)
        self._update_url = ""

        self.credits_lbl = QLabel("Credits: đang tải...")
        self.credits_lbl.setStyleSheet("color:#6b7280; font-size:12px;")
        layout.addWidget(self.credits_lbl)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#e5e7eb;")
        layout.addWidget(line)

        # Prompt style selector
        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(6)
        prompt_row.addWidget(QLabel("Phong cách:"))
        self._prompt_btns: dict[str, QPushButton] = {}
        current_prompt = self.settings.get("enhance_prompt", DEFAULT_PROMPT)
        # find which key matches current prompt (default to first)
        active_name = next(iter(PROMPTS))
        for name, txt in PROMPTS.items():
            if txt == current_prompt:
                active_name = name
                break
        for name in PROMPTS:
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setChecked(name == active_name)
            btn.clicked.connect(lambda checked, n=name: self._set_prompt_style(n))
            self._prompt_btns[name] = btn
            prompt_row.addWidget(btn)
        prompt_row.addStretch()
        self._apply_prompt_btn_styles(active_name)
        layout.addLayout(prompt_row)

        layout.addWidget(QLabel("Kịch bản:"))
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Paste kịch bản vào đây...")
        self.text_input.setMinimumHeight(200)
        layout.addWidget(self.text_input)

        layout.addWidget(QLabel("Tốc độ đọc:"))
        speed_row = QHBoxLayout()
        lbl_min = QLabel("0.7"); lbl_min.setStyleSheet("color:#9ca3af;")
        lbl_max = QLabel("1.2"); lbl_max.setStyleSheet("color:#9ca3af;")
        self.speed_val = QLabel("1.0")
        self.speed_val.setFixedWidth(32)
        self.speed_val.setStyleSheet("font-weight:bold; color:#2563eb;")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(7); self.slider.setMaximum(12)
        default_speed = self.settings.get("default_speed", 1.0)
        self.slider.setValue(int(default_speed * 10))
        self.slider.valueChanged.connect(lambda v: self.speed_val.setText(f"{v/10:.1f}"))
        speed_row.addWidget(lbl_min)
        speed_row.addWidget(self.slider)
        speed_row.addWidget(lbl_max)
        speed_row.addWidget(self.speed_val)
        layout.addLayout(speed_row)

        layout.addWidget(QLabel("Tên file (không cần .mp3):"))
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("VD: box_650k_quang_cao")
        layout.addWidget(self.filename_input)

        self.btn_gen = QPushButton("🎙   GENERATE")
        self.btn_gen.setMinimumHeight(46)
        self.btn_gen.setFont(QFont("", 13, QFont.Weight.Bold))
        self.btn_gen.setStyleSheet(
            "QPushButton{background:#2563eb;color:white;border-radius:8px;border:none;}"
            "QPushButton:hover{background:#1d4ed8;}"
            "QPushButton:disabled{background:#94a3b8;}"
        )
        self.btn_gen.clicked.connect(self._generate)
        layout.addWidget(self.btn_gen)

        self.status_lbl = QLabel("● Sẵn sàng")
        self.status_lbl.setStyleSheet("color:#22c55e; font-size:12px;")
        layout.addWidget(self.status_lbl)

    def _set_prompt_style(self, name: str):
        self.settings["enhance_prompt"] = PROMPTS[name]
        save_settings(self.settings)
        self._apply_prompt_btn_styles(name)

    def _apply_prompt_btn_styles(self, active: str):
        for name, btn in self._prompt_btns.items():
            btn.setChecked(name == active)
            if name == active:
                btn.setStyleSheet(
                    "QPushButton{background:#2563eb;color:white;border:1px solid #2563eb;"
                    "border-radius:5px;padding:2px 10px;font-weight:bold;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{background:#f9fafb;color:#374151;border:1px solid #d1d5db;"
                    "border-radius:5px;padding:2px 10px;}"
                    "QPushButton:hover{background:#e5e7eb;}"
                )

    def _check_update(self):
        self._updater = UpdateChecker()
        self._updater.update_found.connect(self._on_update_found)
        self._updater.start()

    def _on_update_found(self, version: str, url: str):
        self._update_url = url
        self.update_banner.setText(f"🆕  Có bản cập nhật v{version}!  Nhấn để tải về →")
        self.update_banner.setVisible(True)

    def _open_update(self):
        webbrowser.open(self._update_url)

    def _refresh_credits(self):
        keys = self.settings.get("el_api_keys", [])
        if not keys:
            self.credits_lbl.setText("⚠️  Chưa có ElevenLabs API key — vào Settings")
            return
        try:
            total_remaining = 0
            for key in keys:
                r = requests.get(
                    "https://api.elevenlabs.io/v1/user/subscription",
                    headers={"xi-api-key": key}, timeout=5
                )
                if r.status_code == 200:
                    d = r.json()
                    used  = d.get("character_count", 0)
                    limit = d.get("character_limit", 0)
                    total_remaining += limit - used
            label = f"Credits: {total_remaining:,} còn lại" + (f"  ({len(keys)} keys)" if len(keys) > 1 else "")
            self.credits_lbl.setText(label)
        except Exception:
            self.credits_lbl.setText("Không check được credits")

    def _generate(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Thiếu nội dung", "Paste kịch bản vào trước nhé!")
            return
        if not self.settings.get("el_api_keys") or not self.settings.get("ds_api_key"):
            QMessageBox.warning(self, "Thiếu API key", "Vào Settings nhập API keys trước nhé!")
            return
        filename = self.filename_input.text().strip()
        if not filename:
            QMessageBox.warning(self, "Thiếu tên file", "Nhập tên file trước khi generate nhé!")
            self.filename_input.setFocus()
            return

        speed = self.slider.value() / 10
        self.btn_gen.setEnabled(False)
        self.worker = Worker(text, speed, filename.replace(" ", "_"), self.settings)
        self.worker.status.connect(self._on_status)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_status(self, msg: str):
        self.status_lbl.setText(f"⏳  {msg}")
        self.status_lbl.setStyleSheet("color:#f59e0b; font-size:12px;")

    def _on_done(self, path: str):
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText("✅  Xong!")
        self.status_lbl.setStyleSheet("color:#22c55e; font-size:12px;")
        reveal_file(path)
        self._refresh_credits()

    def _on_error(self, msg: str):
        self.btn_gen.setEnabled(True)
        self.status_lbl.setText("❌  Lỗi")
        self.status_lbl.setStyleSheet("color:#ef4444; font-size:12px;")
        QMessageBox.critical(self, "Lỗi", msg)

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            self._refresh_credits()

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
    TrayApp().run()
