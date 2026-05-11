"""
auto_video_workers.py — Workers cho tab Auto Video.
Dependency: app_constants → app_utils → auto_video_workers
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PyQt6.QtCore import QThread, pyqtSignal

from app_utils import load_settings


# ── Helpers ───────────────────────────────────────────────────────────────

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40] or "video"


def _make_slug(title: str) -> str:
    return f"{_slugify(title)}-{datetime.now().strftime('%Y%m%d')}"


# ── AI Script Generation Prompt ───────────────────────────────────────────

SCRIPT_SYSTEM_PROMPT = """Bạn là AI chuyên tạo script video ngắn TikTok từ bài báo/content.

Nhiệm vụ: Đọc bài báo → tạo script JSON cho video ~60-90 giây.

QUY TẮC CỨNG:
- Đúng 6 scenes: hook + 4 body + outro
- Scene 1 PHẢI template "hook", scene cuối PHẢI "outro"
- voiceText: tiếng Việt tự nhiên, 15-30 từ mỗi scene
- Hook bắt đầu bằng số, câu hỏi hoặc thông tin gây tò mò
- KHÔNG dùng "Xin chào", "Hôm nay chúng ta"

OUTPUT: Chỉ JSON thuần, không có text thêm.

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


# ── Worker 1: Fetch + AI Generate Script ─────────────────────────────────

class AutoScriptWorker(QThread):
    """Fetch URL + gọi Claude API → emit script_dict + script_path."""
    progress = pyqtSignal(str)          # status message
    finished = pyqtSignal(str)          # script.json path
    error    = pyqtSignal(str)

    # Engine output dir — chỉnh lại nếu cần
    ENGINE_OUTPUT = Path.home() / "hedra-short" / "auto-create-video" / "output"

    def __init__(self, url_or_text: str, parent=None):
        super().__init__(parent)
        self.input = url_or_text.strip()

    def run(self):
        try:
            settings = load_settings()

            # 1. Fetch article
            if self.input.startswith("http"):
                self.progress.emit("Đang tải bài báo…")
                article = self._fetch(self.input)
            else:
                lines = self.input.split("\\n")
                article = {
                    "url": "", "domain": "", "image": None,
                    "title": lines[0][:120] if lines else "Video",
                    "text": self.input,
                }

            if not article["text"]:
                self.error.emit("Không đọc được nội dung. Thử paste trực tiếp.")
                return

            # 2. Generate script via Claude
            self.progress.emit("AI đang viết script…")
            raw = self._generate(article, settings)

            # 3. Build script.json
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

        title = ""
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image = og_img["content"].strip()

        body = ""
        for tag in ["article", "main"]:
            node = soup.find(tag)
            if node:
                body = re.sub(r"\\s+", " ", node.get_text(" ", strip=True))
                if len(body) > 200:
                    break
        if not body:
            body = re.sub(r"\\s+", " ", " ".join(
                p.get_text(" ", strip=True) for p in soup.find_all("p")
            ))

        return {"url": url, "domain": domain, "title": title,
                "text": body[:6000], "image": image}

    def _generate(self, article: dict, settings: dict) -> dict:
        import anthropic
        api_key = settings.get("claude_api_key", "").strip()
        if not api_key:
            raise ValueError(
                "Chưa có Claude API Key.\\nVào Settings → API Keys để nhập."
            )
        channel = settings.get("channel_name", "Hedra Central")
        system  = SCRIPT_SYSTEM_PROMPT.replace("{{CHANNEL}}", channel)
        system  = system.replace("{{DOMAIN}}", article.get("domain", ""))

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=settings.get("claude_model", "claude-3-5-haiku-20241022"),
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content":
                f"Tiêu đề: {article['title']}\\n\\nNội dung:\\n{article['text'][:4000]}\\n\\nTạo script video."}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    def _build_script(self, raw: dict, article: dict, settings: dict) -> dict:
        provider = settings.get("tts_provider", "genmax")
        voice_id = settings.get("voice_id") or settings.get("genmax_voice_id", "")
        channel  = settings.get("channel_name", "Hedra Central")

        scenes_out = []
        raw_scenes = raw.get("scenes", [])
        for i, s in enumerate(raw_scenes):
            tpl    = s.get("template", "callout")
            fields = s.get("fields", {})
            scenes_out.append({
                "id":           tpl if i == 0 or tpl == "outro" else f"body-{i}",
                "type":         "hook" if i == 0 else ("outro" if i == len(raw_scenes)-1 else "body"),
                "voiceText":    s.get("voiceText", "").strip(),
                "templateData": {**{"template": tpl}, **fields},
            })

        return {
            "version": "1.0",
            "metadata": {
                "title":  raw.get("title", article.get("title", "")),
                "source": {"url": article["url"], "domain": article["domain"], "image": article.get("image")},
                "channel": channel,
            },
            "voice":  {"provider": provider, "voiceId": voice_id, "speed": 1.0},
            "scenes": scenes_out,
        }

    def _write_script(self, script: dict, title: str) -> str:
        slug    = _make_slug(title)
        out_dir = self.ENGINE_OUTPUT / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "script.json"
        path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)


# ── Worker 2: Run Engine Pipeline ────────────────────────────────────────

class AutoVideoEngineWorker(QThread):
    """Chạy npm engine từ script.json → video.mp4."""
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)   # 0-100
    finished = pyqtSignal(str)   # video path
    error    = pyqtSignal(str)

    ENGINE_DIR = Path.home() / "hedra-short" / "auto-create-video"

    def __init__(self, script_path: str, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self._cancelled  = False

    def run(self):
        import subprocess
        cmd = ["npm", "run", "pipeline", "--", self.script_path]
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(self.ENGINE_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                if self._cancelled:
                    proc.terminate()
                    self.error.emit("Đã huỷ")
                    return
                line = line.rstrip()
                self.log_line.emit(line)
                m = re.search(r"\\[(\\d+)/(\\d+)\\]", line)
                if m:
                    n, t = int(m.group(1)), int(m.group(2))
                    self.progress.emit(int(n / t * 100))

            proc.wait()
            if proc.returncode != 0:
                self.error.emit(f"Engine lỗi (exit {proc.returncode})")
                return

            video = Path(self.script_path).parent / "video.mp4"
            self.progress.emit(100)
            self.finished.emit(str(video) if video.exists() else "")

        except FileNotFoundError:
            self.error.emit("Không tìm thấy engine. Chạy: cd auto-create-video && npm install")
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self._cancelled = True
