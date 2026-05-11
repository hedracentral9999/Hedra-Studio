# CLAUDE.md — Hedra Studio (Private)
# Đọc file này ĐẦU MỖI SESSION trước khi làm bất cứ thứ gì

## Overview
PyQt6 desktop tray app — PRIVATE repo (hedracentral9999/Hedra-Studio).
⚠️ KHÔNG public, KHÔNG share source code ra ngoài.
Gồm: TTS (GenMax+ElevenLabs) + Chat/Enhance (Gemini+DeepSeek) + STT + Auto Video.
Platform: macOS (tray app) + Windows. Build: PyInstaller → DMG/EXE.
Current version: xem `version.py`

## Stack
Python 3.11+ · PyQt6 · requests · ElevenLabs API · GenMax API · Gemini API · DeepSeek API · Anthropic API

## Paths
- Project root: `/Users/admin/hedra-studio/`
- Engine (auto-create-video): `/Users/admin/Auto-Create-Video/`
- Engine output: `/Users/admin/Auto-Create-Video/output/`

## Run
```bash
cd /Users/admin/hedra-studio
source venv/bin/activate
python tts_app.py
```

## Syntax Check
```bash
cd /Users/admin/hedra-studio
source venv/bin/activate && python -m py_compile app_constants.py app_utils.py app_workers.py app_dialogs.py voice_library.py settings_dialog.py main_window.py tts_app.py && echo "OK"
```

---

## Module Architecture
```
app_constants.py    → constants, prompts, HIG palette
app_utils.py        → load/save_settings, reveal_file, error hook
app_workers.py      → tất cả QThread workers (TTS, enhance, update...)
app_dialogs.py      → dialogs phụ
voice_library.py    → VoiceLibraryDialog
settings_dialog.py  → SettingsDialog
main_window.py      → MainWindow — tabs: Chat, TTS, STT, Auto Video
tts_app.py          → TrayApp + entry point
auto_video_workers.py → Workers riêng cho tab Auto Video (NEW)
```

Dependency chain (KHÔNG circular):
```
app_constants → app_utils → app_workers → app_dialogs → voice_library → settings_dialog → main_window → tts_app
app_constants → app_utils → auto_video_workers  (song song, không phụ thuộc main_window)
```

---

## ═══════════════════════════════════════════════════════════
## QUY TẮC BẮT BUỘC CHO DEEPSEEK
## ═══════════════════════════════════════════════════════════

### SAU MỖI TASK HOÀN THÀNH — BẮT BUỘC cập nhật CLAUDE.md:

1. **Đánh dấu task hoàn thành**: đổi `[ ]` → `[x]` trong Task List
2. **Ghi vào Session Log** (section bên dưới) theo format:
   ```
   [TASK X - DONE - dd/mm/yyyy]
   - Đã làm: mô tả ngắn gọn những gì đã thay đổi
   - File đã sửa: danh sách file
   - Vấn đề gặp: (nếu có) mô tả lỗi và cách fix
   - Lab Note thêm: (nếu có) rule mới cần nhớ
   ```
3. **Nếu gặp lỗi không giải quyết được**: ghi vào Session Log với tag `[BLOCKED]` và mô tả cụ thể để Claude review

Không được bỏ qua bước này — Claude đọc Session Log để review và plan bước tiếp.

---

## ═══════════════════════════════════════════════════════════
## TASK LIST — THỰC HIỆN THEO THỨ TỰ
## ═══════════════════════════════════════════════════════════

- [x] TASK 1: Thêm Claude API key vào Settings
- [x] TASK 2: Tạo auto_video_workers.py
- [x] TASK 3: Thêm tab Auto Video vào MainWindow
- [x] TASK 4: pip install anthropic beautifulsoup4
- [x] TASK 5: Syntax check + chạy thử
- [ ] TASK 6: Bump v1.8.0 + commit   ← **DEEPSEEK LÀM CÁI NÀY**

---

### TASK 1 — Thêm Claude API key vào Settings

File: `settings_dialog.py`

Trong tab "API Keys", thêm 2 fields mới vào cuối section:
```python
self.claude_key = QLineEdit()
self.claude_key.setEchoMode(QLineEdit.EchoMode.Password)
self.claude_key.setText(self.settings.get("claude_api_key", ""))

self.claude_model = QComboBox()
self.claude_model.addItems([
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
])
self.claude_model.setCurrentText(
    self.settings.get("claude_model", "claude-3-5-haiku-20241022")
)
```
Thêm card_row: `label="Claude API Key"` và `label="Claude Model"`.

Trong `get_settings()` thêm:
```python
"claude_api_key": self.claude_key.text().strip(),
"claude_model":   self.claude_model.currentText(),
```

✅ Syntax check sau khi xong. Cập nhật CLAUDE.md.

---

### TASK 2 — Tạo file `auto_video_workers.py`

Tạo file MỚI: `/Users/admin/hedra-studio/auto_video_workers.py`

KHÔNG import từ `main_window.py` hoặc `settings_dialog.py` (tránh circular).
Engine output dir: `/Users/admin/Auto-Create-Video/output/`
Engine dir: `/Users/admin/Auto-Create-Video/`

```python
"""
auto_video_workers.py — Workers cho tab Auto Video.
Dependency: app_constants → app_utils → auto_video_workers
"""
import json, re, unicodedata, subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PyQt6.QtCore import QThread, pyqtSignal

from app_utils import load_settings

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:40] or "video"

def _make_slug(title: str) -> str:
    return f"{_slugify(title)}-{datetime.now().strftime('%Y%m%d')}"

SCRIPT_SYSTEM_PROMPT = """Bạn là AI chuyên tạo script video ngắn TikTok từ bài báo.
Tạo script JSON cho video ~60-90 giây, đúng 6 scenes: hook + 4 body + outro.

QUY TẮC:
- Scene 1 PHẢI template "hook", scene cuối PHẢI "outro"
- voiceText: tiếng Việt tự nhiên, 15-30 từ/scene
- Hook bắt đầu bằng số, câu hỏi hoặc thông tin gây tò mò
- KHÔNG dùng "Xin chào", "Hôm nay chúng ta"

OUTPUT: Chỉ JSON thuần.

FORMAT:
{
  "title": "tên video ngắn",
  "scenes": [
    {"template":"hook","voiceText":"...","fields":{"headline":"TIÊU ĐỀ","subhead":"phụ đề","kenBurns":"zoom-in"}},
    {"template":"stat-hero","voiceText":"...","fields":{"value":"99%","label":"mô tả","context":"ngữ cảnh"}},
    {"template":"comparison","voiceText":"...","fields":{"leftLabel":"A","leftValue":"x","rightLabel":"B","rightValue":"y","winner":true}},
    {"template":"feature-list","voiceText":"...","fields":{"ftTitle":"Nổi bật","bullets":["điểm 1","điểm 2","điểm 3"]}},
    {"template":"callout","voiceText":"...","fields":{"statement":"Quote quan trọng","tag":"hashtag"}},
    {"template":"outro","voiceText":"...","fields":{"ctaTop":"Theo dõi ngay","channelName":"{{CHANNEL}}","source":"{{DOMAIN}}"}}
  ]
}"""


class AutoScriptWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)   # script.json path
    error    = pyqtSignal(str)

    ENGINE_OUTPUT = Path("/Users/admin/Auto-Create-Video/output")

    def __init__(self, url_or_text: str, parent=None):
        super().__init__(parent)
        self.input = url_or_text.strip()

    def run(self):
        try:
            settings = load_settings()

            if self.input.startswith("http"):
                self.progress.emit("Đang tải bài báo…")
                article = self._fetch(self.input)
            else:
                lines = self.input.split("\n")
                article = {"url":"","domain":"","image":None,
                           "title": lines[0][:120] if lines else "Video",
                           "text": self.input}

            if not article["text"]:
                self.error.emit("Không đọc được nội dung. Thử paste trực tiếp.")
                return

            self.progress.emit("AI đang viết script…")
            raw = self._generate(article, settings)

            self.progress.emit("Đang tạo script.json…")
            script = self._build_script(raw, article, settings)
            path   = self._write_script(script, raw.get("title", article["title"]))
            self.finished.emit(path)

        except ValueError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

    def _fetch(self, url: str) -> dict:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=15)
        resp.raise_for_status()
        soup   = BeautifulSoup(resp.text, "html.parser")
        domain = urlparse(url).netloc.replace("www.", "")
        title  = ""
        og = soup.find("meta", property="og:title")
        if og and og.get("content"): title = og["content"].strip()
        elif soup.title and soup.title.string: title = soup.title.string.strip()
        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"): image = og_img["content"].strip()
        body = ""
        for tag in ["article", "main"]:
            node = soup.find(tag)
            if node:
                body = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
                if len(body) > 200: break
        if not body:
            body = re.sub(r"\s+", " ", " ".join(
                p.get_text(" ", strip=True) for p in soup.find_all("p")))
        return {"url":url,"domain":domain,"title":title,"text":body[:6000],"image":image}

    def _generate(self, article: dict, settings: dict) -> dict:
        import anthropic
        api_key = settings.get("claude_api_key","").strip()
        if not api_key:
            raise ValueError("Chưa có Claude API Key.\nVào Settings → API Keys để nhập.")
        channel = settings.get("channel_name","Hedra Central")
        system  = SCRIPT_SYSTEM_PROMPT.replace("{{CHANNEL}}", channel)
        system  = system.replace("{{DOMAIN}}", article.get("domain",""))
        client  = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=settings.get("claude_model","claude-3-5-haiku-20241022"),
            max_tokens=2048, system=system,
            messages=[{"role":"user","content":
                f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video."}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        return json.loads(raw.strip())

    def _build_script(self, raw: dict, article: dict, settings: dict) -> dict:
        provider = settings.get("tts_provider","genmax")
        voice_id = settings.get("voice_id") or settings.get("genmax_voice_id","")
        channel  = settings.get("channel_name","Hedra Central")
        raw_scenes = raw.get("scenes",[])
        scenes_out = []
        for i, s in enumerate(raw_scenes):
            tpl = s.get("template","callout")
            scenes_out.append({
                "id": tpl if i==0 or tpl=="outro" else f"body-{i}",
                "type": "hook" if i==0 else ("outro" if i==len(raw_scenes)-1 else "body"),
                "voiceText": s.get("voiceText","").strip(),
                "templateData": {"template":tpl, **s.get("fields",{})},
            })
        return {
            "version":"1.0",
            "metadata":{"title":raw.get("title",article.get("title","")),
                        "source":{"url":article["url"],"domain":article["domain"],"image":article.get("image")},
                        "channel":channel},
            "voice":{"provider":provider,"voiceId":voice_id,"speed":1.0},
            "scenes":scenes_out,
        }

    def _write_script(self, script: dict, title: str) -> str:
        out_dir = self.ENGINE_OUTPUT / _make_slug(title)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "script.json"
        path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)


class AutoVideoEngineWorker(QThread):
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    ENGINE_DIR = Path("/Users/admin/Auto-Create-Video")

    def __init__(self, script_path: str, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self._cancelled  = False

    def run(self):
        cmd = ["npm", "run", "pipeline", "--", self.script_path]
        try:
            proc = subprocess.Popen(cmd, cwd=str(self.ENGINE_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
            for line in proc.stdout:
                if self._cancelled:
                    proc.terminate(); self.error.emit("Đã huỷ"); return
                line = line.rstrip()
                self.log_line.emit(line)
                m = re.search(r"\[(\d+)/(\d+)\]", line)
                if m:
                    n, t = int(m.group(1)), int(m.group(2))
                    self.progress.emit(int(n/t*100))
            proc.wait()
            if proc.returncode != 0:
                self.error.emit(f"Engine lỗi (exit {proc.returncode})"); return
            video = Path(self.script_path).parent / "video.mp4"
            self.progress.emit(100)
            self.finished.emit(str(video) if video.exists() else "")
        except FileNotFoundError:
            self.error.emit("Không tìm thấy engine. Chạy: cd Auto-Create-Video && npm install")
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self._cancelled = True
```

✅ Syntax check sau khi tạo: `python -m py_compile auto_video_workers.py`
✅ Cập nhật CLAUDE.md.

---

### TASK 3 — Thêm tab Auto Video vào MainWindow

File: `main_window.py`

**Bước 3.1** — Thêm import vào đầu file:
```python
from auto_video_workers import AutoScriptWorker, AutoVideoEngineWorker
```

**Bước 3.2** — Trong `_build()`, thêm sau `self.tabs.addTab(self._build_stt_tab(), "📝  STT")`:
```python
self.tabs.addTab(self._build_auto_video_tab(), "🎬  Auto Video")
```

**Bước 3.3** — Thêm các methods sau vào cuối class MainWindow:

```python
# ── Tab: Auto Video ─────────────────────────────────────────────────

def _build_auto_video_tab(self) -> QWidget:
    outer = QWidget()
    outer.setStyleSheet(f"background:{BG};")
    layout = QVBoxLayout(outer)
    layout.setContentsMargins(20, 16, 20, 20)
    layout.setSpacing(12)

    input_card, input_vbox = self._card()
    layout.addWidget(input_card)
    self._card_row(input_vbox, "Link bài báo", self._av_url_field(), last=False)
    self._card_row(input_vbox, "Hoặc paste text", self._av_text_field(), last=True)

    self._av_status = QLabel("Nhập link hoặc paste nội dung rồi nhấn Generate")
    self._av_status.setStyleSheet(f"color:{TEXT_MUTE};font-size:12px;background:transparent;")
    self._av_status.setWordWrap(True)
    layout.addWidget(self._av_status)

    self._av_log = QTextEdit()
    self._av_log.setReadOnly(True)
    self._av_log.setFixedHeight(120)
    self._av_log.setStyleSheet(
        "QTextEdit{background:#f5f5f7;border:1px solid #e5e5ea;"
        "border-radius:8px;font-size:11px;font-family:Menlo,monospace;padding:8px;}")
    self._av_log.setVisible(False)
    layout.addWidget(self._av_log)

    from PyQt6.QtWidgets import QProgressBar
    self._av_progress = QProgressBar()
    self._av_progress.setRange(0, 100)
    self._av_progress.setValue(0)
    self._av_progress.setFixedHeight(6)
    self._av_progress.setTextVisible(False)
    self._av_progress.setStyleSheet(
        "QProgressBar{background:#e5e5ea;border:none;border-radius:3px;}"
        f"QProgressBar::chunk{{background:{ACCENT};border-radius:3px;}}")
    self._av_progress.setVisible(False)
    layout.addWidget(self._av_progress)

    self._av_result_card, av_result_vbox = self._card()
    self._av_result_card.setVisible(False)
    self._av_video_path_lbl = QLabel("—")
    self._av_video_path_lbl.setStyleSheet(
        f"color:{TEXT_MUTE};font-size:11px;background:transparent;")
    self._av_video_path_lbl.setWordWrap(True)
    self._card_row(av_result_vbox, "Video output", self._av_video_path_lbl, last=False)
    self._av_btn_open = QPushButton("📂  Open in Finder")
    self._av_btn_open.setFixedHeight(32)
    self._av_btn_open.setStyleSheet(
        f"QPushButton{{border:1px solid {BORDER};border-radius:8px;"
        f"padding:0 14px;background:white;color:{TEXT};font-size:12px;}}"
        f"QPushButton:hover{{background:#f5f5f7;}}")
    self._av_btn_open.clicked.connect(self._av_open_finder)
    btn_w = QWidget(); btn_h = QHBoxLayout(btn_w)
    btn_h.setContentsMargins(16,8,16,12)
    btn_h.addWidget(self._av_btn_open); btn_h.addStretch()
    av_result_vbox.addWidget(btn_w)
    layout.addWidget(self._av_result_card)
    layout.addStretch()

    self._av_gen_btn = QPushButton("✨  Generate Video")
    self._av_gen_btn.setFixedHeight(44)
    self._av_gen_btn.setStyleSheet(
        f"QPushButton{{background:{ACCENT};color:white;border:none;"
        f"border-radius:10px;font-size:14px;font-weight:700;padding:0 28px;}}"
        f"QPushButton:hover{{background:{ACCENT_HV};}}"
        f"QPushButton:pressed{{background:#0060cc;}}"
        f"QPushButton:disabled{{background:#a8d0fb;color:white;}}")
    self._av_gen_btn.clicked.connect(self._av_on_generate)
    layout.addWidget(self._av_gen_btn)

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
    self._av_text.setPlaceholderText("Paste nội dung bài báo vào đây…\nAI sẽ tự tóm tắt và tạo script.")
    self._av_text.setFixedHeight(100)
    return self._av_text

def _av_on_generate(self):
    url  = self._av_url.text().strip()
    text = self._av_text.toPlainText().strip()
    inp  = url or text
    if not inp:
        self._av_set_status("Nhập link hoặc paste nội dung trước.", error=True); return
    if not self.settings.get("claude_api_key","").strip():
        self._av_set_status("Chưa có Claude API Key — vào Settings.", error=True); return
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
```

✅ Syntax check toàn bộ sau khi thêm. Cập nhật CLAUDE.md.

---

### TASK 4 — Cài thêm dependencies

```bash
cd /Users/admin/hedra-studio
source venv/bin/activate
pip install anthropic beautifulsoup4
```

✅ Cập nhật CLAUDE.md.

---

### TASK 5 — Final: Syntax check + chạy thử

```bash
cd /Users/admin/hedra-studio
source venv/bin/activate
python -m py_compile app_constants.py app_utils.py app_workers.py auto_video_workers.py app_dialogs.py voice_library.py settings_dialog.py main_window.py tts_app.py
echo "--- syntax OK ---"
python tts_app.py
```

Nếu lỗi → fix → chạy lại. Ghi rõ lỗi và cách fix vào Session Log.
✅ Cập nhật CLAUDE.md.

---

### TASK 6 — Bump version + commit  ← DEEPSEEK LÀM

⚠️ Hedra Studio là PRIVATE repo — KHÔNG public, KHÔNG tạo repo mới public.
Repo: `https://github.com/hedracentral9999/Hedra-Studio` (private, đã tồn tại).

```bash
cd /Users/admin/hedra-studio
```

**Bước 1** — Sửa `version.py`:
```python
VERSION = "1.8.0"
GITHUB_REPO = "hedracentral9999/Hedra-Studio"
```

**Bước 2** — Syntax check lần cuối:
```bash
venv/bin/python3 -m py_compile app_constants.py app_utils.py app_workers.py auto_video_workers.py app_dialogs.py voice_library.py settings_dialog.py main_window.py tts_app.py && echo "OK"
```

**Bước 3** — Commit & push lên private repo:
```bash
git add -A
git commit -m "feat: add Auto Video tab v1.8.0"
git push
```

✅ Cập nhật CLAUDE.md: đánh dấu TASK 6 `[x]`, ghi Session Log.

---

## ═══════════════════════════════════════════════════════════
## SESSION LOG — DEEPSEEK GHI VÀO ĐÂY SAU MỖI TASK
## ═══════════════════════════════════════════════════════════

<!-- DeepSeek: Thêm log vào đây theo format bên dưới sau mỗi task hoàn thành -->

### [TASK 3+4+5 - DONE - 11/05/2026]
- Đã làm: Thêm tab Auto Video vào main_window.py (import, tab registration, 10 methods)
- File đã sửa: main_window.py, CLAUDE.md
- Packages: anthropic + beautifulsoup4 đã có sẵn trong venv/lib/python3.14/site-packages
- Venv broken shebang (trỏ sai path) → dùng venv/bin/python3.14 trực tiếp để syntax check
- Syntax check: SYNTAX OK trên tất cả 9 modules
- TASK 1 (Claude API key) và TASK 2 (auto_video_workers.py) đã hoàn thành từ trước

### [Chờ implement tiếp]

---

## Lab Notes
<!-- KHÔNG XÓA — chỉ thêm -->
[API]     ALWAYS Gemini first → DeepSeek fallback trong _enhance()
[API]     NEVER dùng "hahahahaaa" trong prompts — dùng [laughs] tags
[EL]      ElevenLabs max 3 API keys — giới hạn tại _save() với [:3]
[HIG]     BG/SURFACE/ACCENT/STYLE defined trong app_constants.py (không main_window) — tránh circular
[BUILD]   CRITICAL: Sau refactor PHẢI thêm TẤT CẢ modules vào hiddenimports trong TTS.spec
[IMPORT]  NEVER import từ file bên phải trong dependency chain — gây circular import crash
[IMPORT]  Dùng python -m py_compile TẤT CẢ modules trước khi tag release
[BUILD]   NEVER build DMG local macOS 15+ — dùng CI GitHub Actions push tag v*
[GENMAX]  GenMax là primary TTS — ElevenLabs chỉ là fallback
[GENMAX]  Endpoints: POST /v1/text-to-speech/{id}, GET /v1/auth/me, GET /v1/default-voices
[AUTO_VIDEO] auto_video_workers.py: ENGINE_DIR = /Users/admin/Auto-Create-Video
[AUTO_VIDEO] auto_video_workers.py KHÔNG import từ main_window — tránh circular
