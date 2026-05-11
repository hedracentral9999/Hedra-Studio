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

SCRIPT_SYSTEM_PROMPT = """Bạn là AI chuyên tạo script video ngắn TikTok từ bài báo.
Tạo script JSON cho video ~60-90 giây, đúng 6-7 scenes: 1 hook + 4-5 body + 1 outro.

QUY TẮC NỘI DUNG:
- voiceText: tiếng Việt tự nhiên, 20-40 từ/scene
- Hook bắt đầu bằng số, câu hỏi hoặc thông tin gây tò mò
- KHÔNG dùng "Xin chào", "Hôm nay chúng ta"

QUY TẮC FORMAT — QUAN TRỌNG, tuân thủ tuyệt đối:
- hook.headline: tối đa 40 ký tự
- hook.subhead: tối đa 40 ký tự
- stat-hero.value: tối đa 20 ký tự, label: tối đa 40 ký tự
- feature-list.title: tối đa 40 ký tự, mỗi bullet: tối đa 50 ký tự, tối đa 4 bullets
- callout.statement: tối đa 80 ký tự, tag: tối đa 20 ký tự
- outro.ctaTop: tối đa 30 ký tự, channelName: tối đa 30 ký tự, source: tối đa 40 ký tự
- comparison.left và right PHẢI có đủ 3 field: label (max30), value (max20), color ("cyan" hoặc "purple")

OUTPUT: Chỉ JSON thuần, không markdown, không giải thích.

FORMAT CHUẨN (copy chính xác cấu trúc này):
{
  "version": "1.0",
  "metadata": {
    "title": "tên video ngắn",
    "source": {"url": "{{URL}}", "domain": "{{DOMAIN}}", "image": null},
    "channel": "{{CHANNEL}}"
  },
  "voice": {"provider": "lucylab", "voiceId": "${VIETNAMESE_VOICEID}", "speed": 1.0},
  "scenes": [
    {"id":"hook","type":"hook","voiceText":"câu hook hấp dẫn 20-40 từ",
     "templateData":{"template":"hook","headline":"TIÊU ĐỀ NGẮN <40KÝ","subhead":"phụ đề <40 ký","kenBurns":"zoom-in"}},

    {"id":"body-1","type":"body","voiceText":"nội dung scene 1",
     "templateData":{"template":"stat-hero","value":"99%","label":"mô tả <40 ký","context":"ngữ cảnh <50 ký"}},

    {"id":"body-2","type":"body","voiceText":"nội dung scene 2",
     "templateData":{"template":"comparison",
       "left":{"label":"Trước <30ký","value":"x <20ký","color":"cyan"},
       "right":{"label":"Sau <30ký","value":"y <20ký","color":"purple","winner":true}}},

    {"id":"body-3","type":"body","voiceText":"nội dung scene 3",
     "templateData":{"template":"feature-list","title":"Tiêu đề <40ký","bullets":["điểm 1 <50ký","điểm 2","điểm 3"]}},

    {"id":"body-4","type":"body","voiceText":"nội dung scene 4",
     "templateData":{"template":"callout","statement":"quote quan trọng <80 ký tự","tag":"hashtag<20ký"}},

    {"id":"outro","type":"outro","voiceText":"lời kết kêu gọi follow",
     "templateData":{"template":"outro","ctaTop":"Theo dõi ngay","channelName":"{{CHANNEL}}","source":"{{DOMAIN}}"}}
  ]
}"""


# ── Worker 1: Fetch + AI Generate Script ─────────────────────────────────

class AutoScriptWorker(QThread):
    """Fetch URL + gọi Claude API → emit script_dict + script_path."""
    progress = pyqtSignal(str)          # status message
    finished = pyqtSignal(str)          # script.json path
    error    = pyqtSignal(str)

    # Engine output dir — chỉnh lại nếu cần
    ENGINE_OUTPUT = Path("/Users/admin/Auto-Create-Video/output")

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
        """Try Claude → DeepSeek → Gemini. Raise ValueError nếu tất cả fail."""
        errors = []

        # ── 1. Claude ────────────────────────────────────────────────────
        claude_key = settings.get("claude_api_key", "").strip()
        if claude_key:
            try:
                self.progress.emit("AI đang viết script… (Claude)")
                return self._generate_claude(article, settings, claude_key)
            except Exception as e:
                errors.append(f"Claude: {e}")
                self.progress.emit("Claude lỗi — thử DeepSeek…")

        # ── 2. DeepSeek ──────────────────────────────────────────────────
        ds_key = settings.get("ds_api_key", "").strip()
        if ds_key:
            try:
                self.progress.emit("AI đang viết script… (DeepSeek)")
                return self._generate_deepseek(article, ds_key)
            except Exception as e:
                errors.append(f"DeepSeek: {e}")
                self.progress.emit("DeepSeek lỗi — thử Gemini…")

        # ── 3. Gemini ────────────────────────────────────────────────────
        gemini_key = settings.get("gemini_api_key", "").strip()
        if gemini_key:
            try:
                self.progress.emit("AI đang viết script… (Gemini)")
                return self._generate_gemini(article, gemini_key)
            except Exception as e:
                errors.append(f"Gemini: {e}")

        # ── Tất cả fail ──────────────────────────────────────────────────
        if not errors:
            raise ValueError(
                "Chưa có API key nào.\n"
                "Vào Settings → API Keys → nhập Claude / DeepSeek / Gemini key."
            )
        raise ValueError("Tất cả AI providers đều lỗi:\n" + "\n".join(errors))

    def _generate_claude(self, article: dict, settings: dict, api_key: str) -> dict:
        import anthropic
        channel = settings.get("channel_name", "Hedra Central")
        system = (SCRIPT_SYSTEM_PROMPT
                  .replace("{{URL}}", article.get("url", ""))
                  .replace("{{DOMAIN}}", article.get("domain", ""))
                  .replace("{{CHANNEL}}", channel))
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=settings.get("claude_model", "claude-3-5-haiku-20241022"),
            max_tokens=2048, system=system,
            messages=[{"role": "user", "content":
                f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video."}],
        )
        return self._parse_json(resp.content[0].text.strip())

    def _generate_deepseek(self, article: dict, api_key: str) -> dict:
        channel = "Hedra Central"
        system = (SCRIPT_SYSTEM_PROMPT
                  .replace("{{URL}}", article.get("url", ""))
                  .replace("{{DOMAIN}}", article.get("domain", ""))
                  .replace("{{CHANNEL}}", channel))
        payload = {
            "model": "deepseek-chat",
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content":
                    f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video."},
            ],
        }
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        resp.raise_for_status()
        return self._parse_json(resp.json()["choices"][0]["message"]["content"].strip())

    def _generate_gemini(self, article: dict, api_key: str) -> dict:
        channel = "Hedra Central"
        system = (SCRIPT_SYSTEM_PROMPT
                  .replace("{{URL}}", article.get("url", ""))
                  .replace("{{DOMAIN}}", article.get("domain", ""))
                  .replace("{{CHANNEL}}", channel))
        prompt  = (f"{system}\n\n"
                   f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video.")
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
            f"?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        resp.raise_for_status()
        return self._parse_json(resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip())

    def _parse_json(self, raw: str) -> dict:
        """Parse JSON từ response — handle markdown code block."""
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    def _build_script(self, raw: dict, article: dict, settings: dict) -> dict:
        # Fix image: chỉ giữ nếu là https:// URL hợp lệ
        img = article.get("image")
        if img and not re.match(r'^https?://', img or ''):
            img = None

        # Fix voice (đảm bảo đúng dù AI có generate sai)
        if "voice" in raw:
            raw["voice"]["provider"] = "lucylab"
            raw["voice"]["voiceId"] = "${VIETNAMESE_VOICEID}"
        else:
            raw["voice"] = {"provider": "lucylab", "voiceId": "${VIETNAMESE_VOICEID}", "speed": 1.0}

        # Fix metadata.source.image
        if "metadata" not in raw:
            raw["metadata"] = {}
        if "source" not in raw["metadata"]:
            raw["metadata"]["source"] = {}
        raw["metadata"]["source"]["image"] = img

        return raw

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

    ENGINE_DIR = Path("/Users/admin/Auto-Create-Video")

    def __init__(self, script_path: str, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self._cancelled  = False

    def run(self):
        import subprocess
        tsx_bin = self.ENGINE_DIR / "node_modules" / ".bin" / "tsx"
        if not tsx_bin.exists():
            self.error.emit(
                f"Không tìm thấy tsx.\n"
                f"Chạy: cd /Users/admin/Auto-Create-Video && npm install"
            )
            return
        cmd = [str(tsx_bin), "src/cli.ts", self.script_path]
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
