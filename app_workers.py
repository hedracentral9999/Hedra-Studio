import os
import sys
import re
import json
import time
import base64
import requests
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from app_constants import (
    DEFAULT_PROMPT, get_creativity_guide, CREATIVITY_CONTENT_LOCK,
    DIALOGUE_ROLE_LOCK,
    VERSION, GITHUB_REPO, VOICE_ID, MODEL, EL_OUTPUT_FORMAT,
    GEMINI_CHAT_PROMPT,
)
from app_utils import DEFAULT_OUT, DATA_DIR, SETTINGS_FILE

_ENGINE_ENV_LOCAL = Path("/Users/admin/Auto-Create-Video/.env.local")

def _read_pipeline_env() -> dict:
    out: dict[str, str] = {}
    try:
        if not _ENGINE_ENV_LOCAL.exists():
            return out
        for line in _ENGINE_ENV_LOCAL.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            out[key.strip()] = value.strip()
    except Exception:
        return {}
    return out

_EL_V3_TAG_RE = re.compile(r"\[[a-z][a-z -]{1,40}\]", re.I)
_EL_V3_STYLE_RULES = (
    ("[warmly]", re.compile(r"(follow|đăng ký|xem tiếp|đừng bỏ lỡ|hẹn gặp|cảm ơn)", re.I)),
    ("[curious]", re.compile(r"(\?|bạn có biết|vì sao|tại sao|liệu|điều gì xảy ra)", re.I)),
    ("[impressed]", re.compile(r"(đột phá|kỷ lục|ấn tượng|mới nhất|ra mắt|tăng mạnh|vượt trội|thành công)", re.I)),
    ("[thoughtful]", re.compile(r"(nhưng|tuy nhiên|vấn đề|rủi ro|cảnh báo|sự thật|đáng chú ý|bất ngờ)", re.I)),
    ("[professional]", re.compile(r"(\d|%|usd|đô|triệu|tỷ|nghìn|benchmark|api|ai|model|mô hình)", re.I)),
)

def _style_eleven_v3_text(text: str) -> str:
    trimmed = (text or "").strip()
    if not trimmed or _EL_V3_TAG_RE.search(trimmed):
        return text
    tag = next((t for t, pat in _EL_V3_STYLE_RULES if pat.search(trimmed)), "[thoughtful]")
    return f"{tag} {trimmed}"

def _eleven_v3_style_enabled(settings: dict) -> bool:
    value = settings.get("eleven_v3_style_enabled", os.environ.get("ELEVEN_V3_STYLE_ENABLED", "true"))
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "no", "off")

class VoiceFetcher(QThread):
    """Fetch danh sách voices — ưu tiên GenMax nếu có key, fallback ElevenLabs."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, genmax_key: str = ""):
        super().__init__()
        self.api_key    = api_key
        self.genmax_key = genmax_key

    def run(self):
        try:
            if self.genmax_key:
                r = requests.get(
                    "https://api.genmax.io/v1/default-voices?page_size=100",
                    headers={"xi-api-key": self.genmax_key},
                    timeout=10,
                )
                if r.status_code == 200:
                    voices = r.json().get("voices", [])
                    voices.sort(key=lambda v: v.get("name", "").lower())
                    self.done.emit(voices)
                    return
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
    """Fetch voices từ Shared Voice Library — ưu tiên GenMax, fallback ElevenLabs."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, language: str = "", search: str = "",
                 page_size: int = 30, genmax_key: str = ""):
        super().__init__()
        self.api_key    = api_key
        self.language   = language
        self.search     = search
        self.page_size  = page_size
        self.genmax_key = genmax_key

    def run(self):
        try:
            params = {"page_size": self.page_size, "sort": "trending"}
            if self.language:
                params["required_languages"] = self.language
            if self.search:
                params["search"] = self.search
            if self.genmax_key:
                r = requests.get(
                    "https://api.genmax.io/v1/shared-voices",
                    headers={"xi-api-key": self.genmax_key},
                    params=params,
                    timeout=12,
                )
                if r.status_code == 200:
                    voices = r.json().get("voices", [])
                    self.done.emit(voices)
                    return
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
    """Dùng Claude/DeepSeek để tạo system prompt từ mô tả ngắn của user."""
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
6. Quy tắc nhịp đọc (... và —), không dùng tag dừng/pause dạng ngoặc vuông
7. Quy tắc output: chỉ trả về kịch bản đã xử lý, không giải thích

Nếu mô tả có trường "Từ ngữ đặc trưng":
- BẮT BUỘC tạo một mục riêng tên "TỪ NGỮ ĐẶC TRƯNG".
- Giữ nguyên văn từng từ/cụm từ user nhập, không tự bỏ, không thay bằng từ đồng nghĩa.
- Viết rule rõ: ưu tiên giữ các cụm này khi chúng đã có trong kịch bản gốc; có thể thêm tự nhiên khi phù hợp ngữ cảnh; không lạm dụng.
- Nếu cụm từ là tiếng lóng/xưng hô/thương hiệu, không sửa chính tả và không dịch.

Nếu mô tả có trường "Tuyệt đối tránh":
- BẮT BUỘC tạo một mục riêng tên "TUYỆT ĐỐI TRÁNH" và giữ đúng các điều user đã nhập.

Trả về CHỈ nội dung system prompt, không có markdown ngoài, không có tiêu đề."""

    def __init__(self, description: str, api_key: str, gemini_key: str = "", claude_key: str = ""):
        super().__init__()
        self.description = description
        self.api_key     = api_key
        self.gemini_key  = gemini_key
        self.claude_key  = claude_key

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
            # ── Ưu tiên Claude → fallback Gemini → fallback DeepSeek ─
            if self.claude_key:
                full_prompt = f"Tạo prompt cho phong cách: {self.description}"
                res = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         self.claude_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type":      "application/json",
                    },
                    json={
                        "model":    "claude-haiku-4-5-20251001",
                        "max_tokens": 1800,
                        "system":   self._META_PROMPT,
                        "messages": [{"role": "user", "content": full_prompt}],
                    },
                    timeout=60,
                )
                if res.status_code == 200:
                    prompt = res.json()["content"][0]["text"].strip()
                    self.done.emit(self._ensure_required_user_terms(prompt))
                    return
            if self.gemini_key:
                full_prompt = f"{self._META_PROMPT}\n\nTạo prompt cho phong cách: {self.description}"
                res = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"gemini-2.5-flash:generateContent?key={self.gemini_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": full_prompt}]}]},
                    timeout=60,
                )
                if res.status_code == 200:
                    candidates = res.json().get("candidates", [])
                    if candidates:
                        prompt = candidates[0]["content"]["parts"][0]["text"].strip()
                        self.done.emit(self._ensure_required_user_terms(prompt))
                        return
            if not self.api_key:
                self.error.emit("⚠️ Chưa có AI key — vào Settings → API → thêm Claude hoặc DeepSeek")
                return
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
  "region":   "vùng miền — 1 trong: Trung lập | Miền Nam | Miền Bắc | Miền Trung. Để trống (empty string) nếu mô tả không đề cập vùng miền",
  "tone":     "tông cảm xúc (nhiều giá trị cách nhau dấu phẩy nếu cần)",
  "product":  "sản phẩm hoặc lĩnh vực cụ thể",
  "keywords": "từ ngữ đặc trưng muốn dùng trong kịch bản TTS",
  "avoid":    "điều cần tránh khi enhance kịch bản"
}"""

    def __init__(self, description: str, api_key: str, gemini_key: str = "", claude_key: str = ""):
        super().__init__()
        self.description = description
        self.api_key     = api_key
        self.gemini_key  = gemini_key
        self.claude_key  = claude_key

    @staticmethod
    def _parse_json(raw: str) -> dict:
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    def run(self):
        try:
            # ── Ưu tiên Claude → fallback Gemini → fallback DeepSeek ─
            if self.claude_key:
                res = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         self.claude_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type":      "application/json",
                    },
                    json={
                        "model":    "claude-haiku-4-5-20251001",
                        "max_tokens": 600,
                        "system":   self._SYSTEM,
                        "messages": [{"role": "user", "content": f"Mô tả: {self.description}"}],
                    },
                    timeout=30,
                )
                if res.status_code == 200:
                    raw = res.json()["content"][0]["text"].strip()
                    try:
                        self.done.emit(self._parse_json(raw))
                        return
                    except json.JSONDecodeError:
                        pass  # fallback to Gemini/DeepSeek
            if self.gemini_key:
                full_prompt = f"{self._SYSTEM}\n\nMô tả: {self.description}"
                res = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"gemini-2.5-flash:generateContent?key={self.gemini_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": full_prompt}]}]},
                    timeout=30,
                )
                if res.status_code == 200:
                    candidates = res.json().get("candidates", [])
                    if candidates:
                        raw = candidates[0]["content"]["parts"][0]["text"].strip()
                        try:
                            self.done.emit(self._parse_json(raw))
                            return
                        except json.JSONDecodeError:
                            pass  # fallback to DeepSeek
            if not self.api_key:
                self.error.emit("⚠️ Chưa có AI key — vào Settings → API → thêm Claude hoặc DeepSeek")
                return
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
                self.done.emit(self._parse_json(raw))
            else:
                self.error.emit(f"DeepSeek {res.status_code}")
        except json.JSONDecodeError:
            self.error.emit("AI trả về sai format — thử lại nhé!")
        except Exception as e:
            self.error.emit(str(e))


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
        self._srt_content: str | None = None

    def run(self):
        try:
            self.status.emit("Đang enhance với AI...")
            enhanced = self._enhance(self.text)
            self.status.emit("Đang generate audio...")
            audio = self._tts(enhanced)
            out_dir = self.s.get("output_dir", DEFAULT_OUT)
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, self.filename + ".mp3")
            with open(path, "wb") as f:
                f.write(audio)
            self._write_srt_sidecar(path, enhanced)
            self.done.emit(path)
        except Exception as e:
            self.error.emit(str(e))

    @staticmethod
    def _clean_tts_text(text: str) -> str:
        text = re.sub(r"\[[a-z][a-z -]{1,40}\]", "", text or "", flags=re.I)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _fmt_srt_time(sec: float) -> str:
        sec = max(0.0, float(sec or 0))
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        if ms >= 1000:
            s += 1
            ms -= 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def _estimated_srt(self, text: str) -> str:
        clean = self._clean_tts_text(text)
        parts = [p.strip() for p in re.split(r"(?<=[.!?。！？])\s+|\n+", clean) if p.strip()]
        if not parts:
            parts = [clean] if clean else []
        chunks: list[str] = []
        for part in parts:
            words = part.split()
            cur: list[str] = []
            for word in words:
                if sum(len(x) + 1 for x in cur) + len(word) > 42 and cur:
                    chunks.append(" ".join(cur))
                    cur = [word]
                else:
                    cur.append(word)
            if cur:
                chunks.append(" ".join(cur))
        if not chunks:
            return ""
        cursor = 0.0
        lines: list[str] = []
        words_per_sec = max(1.7, 2.75 * max(0.5, float(self.speed or 1.0)))
        for i, chunk in enumerate(chunks, 1):
            word_count = max(1, len(chunk.split()))
            dur = max(1.25, min(4.5, word_count / words_per_sec + 0.35))
            start, end = cursor, cursor + dur
            lines.extend([
                str(i),
                f"{self._fmt_srt_time(start)} --> {self._fmt_srt_time(end)}",
                chunk,
                "",
            ])
            cursor = end
        return "\n".join(lines).strip() + "\n"

    def _write_srt_sidecar(self, audio_path: str, text: str) -> str | None:
        srt_path = os.path.splitext(audio_path)[0] + ".srt"
        srt = (self._srt_content or "").strip()
        if not srt:
            srt = self._estimated_srt(text).strip()
        if not srt:
            return None
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt + "\n")
        return srt_path

    @staticmethod
    def _find_url(data, keys: set[str]) -> str:
        if isinstance(data, dict):
            for key, value in data.items():
                if str(key).lower() in keys and isinstance(value, str) and value.startswith("http"):
                    return value
                found = Worker._find_url(value, keys)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = Worker._find_url(item, keys)
                if found:
                    return found
        return ""

    def _download_srt_url(self, url: str) -> None:
        if not url:
            return
        dl = requests.get(url, timeout=30)
        if dl.status_code == 200 and dl.text.strip():
            self._srt_content = dl.text

    def _enhance(self, text: str) -> str:
        claude_key = self.s.get("claude_api_key", "").strip()
        ds_key     = self.s.get("ds_api_key", "").strip()
        if not claude_key and not ds_key:
            raise Exception(
                "⚠️ Chưa có AI key để enhance kịch bản.\n"
                "📌 Vào Settings → API:\n"
                "  • Claude API Key (khuyến nghị — chất lượng cao)\n"
                "  • DeepSeek API Key (fallback)"
            )
        temperature = self.s.get(
            "enhance_style_temperature",
            0.7 if self.s.get("enhance_style_creative", False) else 0.3
        )
        system_prompt = self.s.get("enhance_prompt", DEFAULT_PROMPT)
        system_prompt = (
            get_creativity_guide(temperature)
            + "\n\n"
            + system_prompt
            + "\n\n"
            + DIALOGUE_ROLE_LOCK
        )
        claude_model  = self.s.get("claude_model", "claude-sonnet-4-6")

        # ── Ưu tiên Claude → fallback DeepSeek ─
        if claude_key:
            res = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         claude_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type":      "application/json",
                },
                json={
                    "model":       claude_model,
                    "max_tokens":  2000,
                    "temperature": temperature,
                    "system":      system_prompt,
                    "messages":    [{"role": "user", "content": text}],
                },
                timeout=60,
            )
            if res.status_code == 200:
                return res.json()["content"][0]["text"].strip()
            if not ds_key:
                raise Exception(f"Claude {res.status_code}: {res.text[:200]}")
            self.status.emit("⚠️ Claude lỗi — thử DeepSeek...")

        # ── DeepSeek fallback ─
        res = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {ds_key}",
                     "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": text},
                ],
                "temperature": temperature,
                "max_tokens":  2000,
            },
            timeout=30,
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"].strip()
        raise Exception(f"DeepSeek {res.status_code}: {res.text[:200]}")

    def _tts(self, text: str) -> bytes:
        env = _read_pipeline_env()
        provider = (env.get("TTS_PROVIDER") or "genmax").strip().lower()
        if provider not in {"genmax", "ai33", "elevenlabs", "lucylab"}:
            provider = "genmax"

        order = [provider]
        if provider == "genmax" and self._env_bool(env.get("GENMAX_FALLBACK_TO_AI33"), True):
            order.append("ai33")
        for fallback in ("elevenlabs",):
            if fallback not in order:
                order.append(fallback)

        errors: list[str] = []
        for item in order:
            try:
                if item == "genmax":
                    return self._tts_genmax(text, env)
                if item == "ai33":
                    return self._tts_ai33(text, env)
                if item == "elevenlabs":
                    return self._tts_elevenlabs(text, env)
            except Exception as e:
                errors.append(f"{item}: {e}")
                if item != order[-1]:
                    self.status.emit(f"⚠️ {item} lỗi — thử provider tiếp theo...")
        raise Exception("Tất cả TTS provider đều lỗi:\n" + "\n".join(errors))

    @staticmethod
    def _env_bool(value: str | None, default: bool = False) -> bool:
        if value is None or str(value).strip() == "":
            return default
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _common_language(self, env: dict) -> str:
        return (
            self.s.get("tts_language_code", "").strip()
            or self.s.get("language_code", "").strip()
            or env.get("GENMAX_LANGUAGE_CODE", "").strip()
            or "vi"
        )

    def _voice_for(self, provider: str, env: dict) -> str:
        # Priority: per-tool voice from settings > env var > selected_voice_id fallback
        per_tool = self.s.get("tts_voice_id", "").strip()
        selected  = self.s.get("selected_voice_id", "").strip()
        if provider == "genmax":
            return per_tool or env.get("GENMAX_VOICE_ID", "").strip() or selected or VOICE_ID
        if provider == "ai33":
            return per_tool or env.get("AI33_VOICE_ID", "").strip() or env.get("GENMAX_VOICE_ID", "").strip() or selected or VOICE_ID
        if provider == "elevenlabs":
            return per_tool or env.get("ELEVENLABS_VOICE_ID", "").strip() or selected or env.get("GENMAX_VOICE_ID", "").strip() or VOICE_ID
        return per_tool or selected or VOICE_ID

    def _tts_genmax(self, text: str, env: dict) -> bytes:
        gm_key = env.get("GENMAX_API_KEY", "").strip() or self.s.get("genmax_api_key", "").strip()
        if not gm_key:
            raise Exception("thiếu GenMax API key")
        voice_id = self._voice_for("genmax", env)
        gm_provider = env.get("GENMAX_PROVIDER", "").strip() or self.s.get("genmax_provider", "elevenlabs") or "elevenlabs"
        gm_model = env.get("GENMAX_MODEL_ID", "").strip() or self.s.get("genmax_model_id", MODEL) or MODEL
        tts_text = (
            _style_eleven_v3_text(text)
            if _eleven_v3_style_enabled(self.s) and gm_provider == "elevenlabs" and gm_model == "eleven_v3"
            else text
        )
        self.status.emit(f"Đang generate audio [GenMax · {gm_model}]...")
        body: dict = {
            "text": tts_text,
            "provider": gm_provider,
            "model_id": gm_model,
            "language_code": self._common_language(env),
            "with_transcript": True,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "speed": self.speed,
            },
        }
        res = requests.post(
            f"https://api.genmax.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": gm_key, "Content-Type": "application/json"},
            json=body,
            timeout=30,
        )
        if res.status_code == 200:
            return res.content
        if res.status_code != 202:
            raise Exception(f"GenMax {res.status_code}: {res.text[:300]}")
        task_id = res.json().get("id")
        if not task_id:
            raise Exception("GenMax không trả về task_id")
        deadline = time.time() + 300
        poll_interval = 2
        while time.time() < deadline:
            time.sleep(poll_interval)
            self.status.emit("Đang chờ GenMax render audio...")
            poll = requests.get(
                f"https://api.genmax.io/v1/history/{task_id}",
                headers={"xi-api-key": gm_key},
                timeout=15,
            )
            if poll.status_code != 200:
                raise Exception(f"GenMax poll lỗi {poll.status_code}: {poll.text[:200]}")
            pdata = poll.json()
            status = pdata.get("status", "")
            if status == "completed":
                audio_url = (pdata.get("result") or {}).get("audio_url", "")
                if not audio_url:
                    raise Exception("GenMax không trả về audio_url")
                srt_url = self._find_url(
                    pdata,
                    {"srt_url", "subtitle_url", "subtitles_url", "transcript_srt_url"},
                )
                if srt_url:
                    self.status.emit("Đang tải phụ đề SRT từ GenMax...")
                    self._download_srt_url(srt_url)
                self.status.emit("Đang tải audio từ GenMax...")
                dl = requests.get(audio_url, timeout=30)
                if dl.status_code != 200:
                    raise Exception(f"GenMax download lỗi {dl.status_code}")
                return dl.content
            if status in ("failed", "error"):
                raise Exception(f"GenMax render thất bại: {pdata}")
            poll_interval = min(poll_interval + 1, 5)
        raise Exception("GenMax timeout sau 300 giây")

    def _tts_ai33(self, text: str, env: dict) -> bytes:
        key = env.get("AI33_API_KEY", "").strip()
        if not key:
            raise Exception("thiếu ai33 API key")
        voice_id = self._voice_for("ai33", env)
        model = env.get("AI33_MODEL_ID", "").strip() or "eleven_v3"
        endpoint = (env.get("AI33_ENDPOINT", "").strip() or "https://api.ai33.pro").rstrip("/")
        output_format = env.get("AI33_OUTPUT_FORMAT", "").strip() or "mp3_44100_128"
        tts_text = _style_eleven_v3_text(text) if _eleven_v3_style_enabled(self.s) and model == "eleven_v3" else text
        self.status.emit(f"Đang generate audio [ai33 · {model}]...")
        res = requests.post(
            f"{endpoint}/v1/text-to-speech/{voice_id}?output_format={output_format}",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={
                "text": tts_text,
                "model_id": model,
                "with_transcript": True,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "speed": self.speed,
                },
            },
            timeout=30,
        )
        if res.status_code not in (200, 202):
            raise Exception(f"ai33 {res.status_code}: {res.text[:300]}")
        task_id = res.json().get("task_id") or res.json().get("id")
        if not task_id:
            raise Exception("ai33 không trả về task_id")
        deadline = time.time() + 300
        while time.time() < deadline:
            time.sleep(2)
            self.status.emit("Đang chờ ai33 render audio...")
            poll = requests.get(
                f"{endpoint}/v1/task/{task_id}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                timeout=15,
            )
            if poll.status_code != 200:
                raise Exception(f"ai33 poll {poll.status_code}: {poll.text[:200]}")
            pdata = poll.json()
            if pdata.get("status") == "done":
                audio_url = (pdata.get("metadata") or {}).get("audio_url", "")
                if not audio_url:
                    raise Exception("ai33 done nhưng không có audio_url")
                srt_url = self._find_url(
                    pdata,
                    {"srt_url", "subtitle_url", "subtitles_url", "transcript_srt_url"},
                )
                if srt_url:
                    self.status.emit("Đang tải phụ đề SRT từ ai33...")
                    self._download_srt_url(srt_url)
                dl = requests.get(audio_url, timeout=30)
                if dl.status_code != 200:
                    raise Exception(f"ai33 download {dl.status_code}")
                return dl.content
            if pdata.get("status") == "error":
                raise Exception(pdata.get("error_message") or str(pdata)[:300])
        raise Exception("ai33 timeout sau 300 giây")

    def _tts_elevenlabs(self, text: str, env: dict) -> bytes:
        keys = self.s.get("el_api_keys", [])
        env_key = env.get("ELEVENLABS_API_KEY", "").strip()
        old = self.s.get("el_api_key", "").strip()
        keys = [env_key] + list(keys or []) + ([old] if old else [])
        keys = list(dict.fromkeys(k.strip() for k in keys if k and k.strip()))
        if not keys:
            raise Exception("thiếu ElevenLabs API key")
        voice_id = self._voice_for("elevenlabs", env)
        model = env.get("ELEVENLABS_MODEL_ID", "").strip() or MODEL
        last_err = None
        for idx, key in enumerate(keys, 1):
            label = f"key {idx}/{len(keys)} (...{key[-6:]})"
            self.status.emit(f"Đang generate audio [ElevenLabs · {label}]...")
            tts_text = _style_eleven_v3_text(text) if _eleven_v3_style_enabled(self.s) and model == "eleven_v3" else text
            body = {
                "text": tts_text,
                "model_id": model,
                "output_format": EL_OUTPUT_FORMAT,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "speed": self.speed,
                },
            }
            lang = self._common_language(env)
            if lang:
                body["language_code"] = lang
            res = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
            if res.status_code == 200:
                return res.content
            last_err = Exception(f"ElevenLabs {res.status_code}: {res.text[:300]}")
            if idx < len(keys):
                self.status.emit(f"⚠️ ElevenLabs {label} lỗi — thử key tiếp theo...")
        raise last_err or Exception("Tất cả ElevenLabs API keys đều thất bại.")


# ── TTS-Only Worker — chỉ gen audio, không enhance (dùng sau preview) ─
class _TTSOnlyWorker(QThread):
    """Nhận text đã enhance sẵn → chỉ gọi TTS, không gọi AI."""
    status = pyqtSignal(str)
    done   = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, text: str, speed: float, filename: str, settings: dict):
        super().__init__()
        self.text     = text
        self.speed    = speed
        self.filename = filename
        self.s        = settings
        # Mượn TTS core từ Worker và giữ delegate để lấy SRT provider trả về.
        self._delegate = Worker(text, speed, filename, settings)
        self._tts = self._delegate._tts

    def run(self):
        try:
            self.status.emit("Đang generate audio...")
            audio = self._tts(self.text)
            out_dir = self.s.get("output_dir", DEFAULT_OUT)
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, self.filename + ".mp3")
            with open(path, "wb") as f:
                f.write(audio)
            self._delegate._write_srt_sidecar(path, self.text)
            self.done.emit(path)
        except Exception as e:
            self.error.emit(str(e))


# ── Preview Worker — chỉ enhance, không gen audio ─────────────────
class PreviewWorker(QThread):
    """Chạy _enhance() và trả về text đã xử lý để user xem trước."""
    status = pyqtSignal(str)
    done   = pyqtSignal(str)   # enhanced text
    error  = pyqtSignal(str)

    def __init__(self, text: str, settings: dict):
        super().__init__()
        self.text = text
        self.s    = settings
        # Mượn _enhance từ Worker — inject speed=1.0, filename="" để dùng chung
        self._enhance = Worker(text, 1.0, "", settings)._enhance

    def run(self):
        try:
            self.status.emit("⏳  AI đang xử lý kịch bản...")
            result = self._enhance(self.text)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── Gemini Vision Worker ───────────────────────────────────────────
class GeminiWorker(QThread):
    status = pyqtSignal(str)
    done   = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, image_paths: list, api_key: str, prompt: str = "", pronoun_mode: str = "auto"):
        super().__init__()
        self.image_paths = image_paths
        self.api_key     = api_key
        self.prompt      = prompt or GEMINI_CHAT_PROMPT
        self.pronoun_mode = (pronoun_mode or "auto").strip().lower()

    def run(self):
        try:
            self.status.emit("Đang đọc ảnh chat...")
            image_parts = []
            for path in self.image_paths:
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                ext  = path.lower().rsplit(".", 1)[-1]
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                        "png": "image/png",  "webp": "image/webp"}.get(ext, "image/jpeg")
                image_parts.append({"inline_data": {"mime_type": mime, "data": data}})

            self.status.emit("Gemini đang trích hội thoại thật...")
            transcript = self._call_gemini([{"text": self._extract_prompt()}] + image_parts)
            transcript_payload = self._normalise_transcript(transcript)

            self.status.emit("Gemini đang đồng bộ xưng hô...")
            script = self._call_gemini([{"text": self._rewrite_prompt(transcript_payload)}])
            script = self._clean_final_script(script)

            issues = self._script_issues(script)
            if issues:
                self.status.emit("Đang sửa lỗi bảo mật/xưng hô...")
                script = self._repair_script(script, transcript_payload, issues)
                script = self._clean_final_script(script)

            self.done.emit(script.strip())
        except Exception as e:
            self.error.emit(str(e))

    def _call_gemini(self, parts: list[dict], timeout: int = 90) -> str:
        last_err = None
        for model in ["gemini-2.5-pro", "gemini-2.5-flash"]:
            res = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={self.api_key}",
                json={"contents": [{"parts": parts}]},
                timeout=timeout,
            )
            if res.status_code == 503:
                time.sleep(3)
                res = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={self.api_key}",
                    json={"contents": [{"parts": parts}]},
                    timeout=timeout,
                )
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise Exception("Gemini không trả về kết quả")
                content_parts = candidates[0].get("content", {}).get("parts", [])
                text = "\n".join(str(p.get("text", "")) for p in content_parts if p.get("text"))
                if not text.strip():
                    raise Exception("Gemini trả về rỗng")
                return text.strip()
            if res.status_code in (400, 404):
                last_err = Exception(f"Gemini {res.status_code}: {res.text[:240]}")
                continue
            last_err = Exception(f"Gemini {res.status_code}: {res.text[:240]}")
        raise last_err or Exception("Gemini lỗi không rõ")

    def _extract_prompt(self) -> str:
        return """Đọc ảnh chat Zalo và trích hội thoại thật thành JSON.

Quy tắc role:
- Bong bóng PHẢI/màu xanh = shop.
- Bong bóng TRÁI/màu trắng = customer.
- Nếu crop làm mất màu/vị trí, suy luận bằng ngữ cảnh.

Trả về JSON thuần, không markdown:
{
  "pronoun_detected": "mô tả xưng hô thật nếu thấy",
  "messages": [
    {"role":"customer|shop", "text":"nguyên văn đọc được", "time":"nếu thấy", "sensitive":false}
  ],
  "facts": {
    "product": "",
    "price": "",
    "deposit": "",
    "payment": "",
    "shipping_location": "",
    "notes": []
  },
  "privacy_to_remove": ["phone", "bank", "qr", "contact_card", "full_address"]
}

Không tự viết kịch bản ở bước này. Chỉ trích đúng những gì nhìn thấy."""

    def _rewrite_prompt(self, transcript_payload: str) -> str:
        mode_hint = {
            "fixed_anh_em": "BẮT BUỘC dùng shop=anh/em và khách=em/anh, kể cả chat gốc dùng bạn/mình.",
            "keep_original": "Giữ xưng hô gần chat gốc nhất, chỉ sửa lỗi rõ ràng; vẫn phải tự nhiên và không lộ riêng tư.",
            "auto": "Tự nhận diện xưng hô, nhưng mặc định đồng bộ shop=anh/em và khách=em/anh nếu chat không có hệ xưng hô rõ hơn.",
        }.get(self.pronoun_mode, "Tự nhận diện xưng hô, mặc định shop=anh/em và khách=em/anh.")
        return f"""{self.prompt}

CHẾ ĐỘ XƯNG HÔ:
{mode_hint}

TRANSCRIPT ĐÃ TRÍCH:
{transcript_payload}

Hãy viết kịch bản TTS cuối cùng từ transcript trên.
Ràng buộc bắt buộc:
- Chỉ dùng dữ kiện có trong transcript hoặc knowledge sản phẩm khi transcript thật sự cần làm rõ.
- Không nhãn Khách/Shop.
- Không số điện thoại, STK, tên ngân hàng, QR, contact card, địa chỉ chi tiết.
- Nếu có địa chỉ, chỉ giữ tỉnh/thành phố.
- Nếu khách hỏi box không kèm máy, không tự nhắc combo/kèm máy.
- Với giao dịch mẫu: giữ đúng mạch hỏi box -> giá -> cọc -> COD -> nhận cọc -> xin thông tin nhận hàng -> tỉnh/thành.
"""

    def _normalise_transcript(self, text: str) -> str:
        raw = self._strip_fences(text)
        try:
            data = json.loads(raw)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return raw

    def _strip_fences(self, text: str) -> str:
        stripped = (text or "").strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json|text)?\s*", "", stripped, flags=re.I)
            stripped = re.sub(r"\s*```$", "", stripped)
        return stripped.strip()

    def _clean_final_script(self, text: str) -> str:
        cleaned = self._strip_fences(text)
        lines = []
        for line in cleaned.splitlines():
            line = re.sub(r"^\s*(khách|customer|shop|cửa hàng)\s*[:：-]\s*", "", line, flags=re.I).strip()
            lines.append(line)
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def _script_issues(self, script: str) -> list[str]:
        text = script or ""
        issues = []
        if re.search(r"(?<!\d)(?:0|\+84)\d(?:[\s.\-]?\d){7,10}(?!\d)", text):
            issues.append("còn số điện thoại")
        if re.search(r"\b(stk|số tài khoản|ngân hàng|techcombank|vietcombank|vcb|mbbank|bidv|agribank|qr)\b", text, re.I):
            issues.append("còn thông tin ngân hàng/QR")
        if re.search(r"\b(contact card|danh thiếp|kết bạn|số nhà|thôn|xã|phường|ấp)\b", text, re.I):
            issues.append("còn thông tin liên hệ/địa chỉ chi tiết")
        if re.search(r"\b(em nhận (được )?cọc|anh cọc rồi|anh muốn mua)\b", text, re.I):
            issues.append("có dấu hiệu lệch vai/xưng hô")
        if re.search(r"\b(s10|s20|note ?20|n20).{0,20}\b(1\.?7|1\.?9|2\.?4|triệu)\b", text, re.I) and "không kèm máy" in text.lower():
            issues.append("có thể đã thêm giá combo ngoài chat")
        return issues

    def _repair_script(self, script: str, transcript_payload: str, issues: list[str]) -> str:
        repair_prompt = f"""Sửa kịch bản TTS sau. Chỉ trả text thuần, không giải thích.

Lỗi cần sửa: {", ".join(issues)}

TRANSCRIPT GỐC:
{transcript_payload}

KỊCH BẢN CẦN SỬA:
{script}

Yêu cầu:
- Xóa mọi số điện thoại, STK, ngân hàng, QR, contact card, địa chỉ chi tiết.
- Chỉ giữ tỉnh/thành nếu cần.
- Đồng bộ xưng hô: shop xưng anh gọi khách em; khách xưng em gọi shop anh.
- Không thêm dữ kiện ngoài transcript.
"""
        return self._call_gemini([{"text": repair_prompt}], timeout=60)



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



# ── Speech-to-Text Worker ──────────────────────────────────────────
class SpeechToTextWorker(QThread):
    """Gọi GenMax STT API để chuyển audio → text + timestamps."""
    done   = pyqtSignal(str, list)  # (full_text, words)
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, file_path: str, genmax_key: str):
        super().__init__()
        self.file_path  = file_path
        self.genmax_key = genmax_key

    def run(self):
        try:
            self.status.emit("Đang upload audio...")
            with open(self.file_path, "rb") as f:
                r = requests.post(
                    "https://api.genmax.io/v1/speech-to-text",
                    headers={"xi-api-key": self.genmax_key},
                    files={"file": f},
                    data={"model_id": "scribe_v1"},
                    timeout=120,
                )
            if r.status_code != 200:
                self.error.emit(f"GenMax STT lỗi {r.status_code}: {r.text[:200]}")
                return
            data = r.json()
            text  = data.get("text", "")
            words = data.get("words", [])
            self.done.emit(text, words)
        except Exception as e:
            self.error.emit(str(e))


def words_to_srt(words: list) -> str:
    """Chuyển danh sách words (có start/end/text) → chuỗi SRT."""
    # Gộp words thành subtitle lines ~40 ký tự
    lines = []
    current_line = ""
    line_start = None
    line_end = None

    for w in words:
        if w.get("type") == "spacing":
            if current_line:
                current_line += " "
            continue
        word_text = w.get("text", "")
        start = w.get("start", 0)
        end   = w.get("end", 0)

        if line_start is None:
            line_start = start

        if len(current_line) + len(word_text) > 40 and current_line:
            lines.append((line_start, line_end or end, current_line.strip()))
            current_line = word_text
            line_start = start
        else:
            current_line += word_text
        line_end = end

    if current_line.strip():
        lines.append((line_start, line_end or 0, current_line.strip()))

    srt = []
    for i, (start, end, text) in enumerate(lines, 1):
        def _fmt(sec: float) -> str:
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            ms = int((sec % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        srt.append(f"{i}")
        srt.append(f"{_fmt(start)} --> {_fmt(end)}")
        srt.append(text)
        srt.append("")
    return "\n".join(srt)


# ── Credits checker (background thread — không block UI) ──────────
class _CreditsChecker(QThread):
    done = pyqtSignal(str)

    def __init__(self, el_keys: list, genmax_key: str = ""):
        super().__init__()
        self.el_keys     = [k.strip() for k in el_keys if k.strip()]
        self.genmax_key  = genmax_key.strip()

    def run(self):
        try:
            parts = []
            # ── GenMax credits ────────────────────────────────────
            if self.genmax_key:
                try:
                    r = requests.get(
                        "https://api.genmax.io/v1/auth/me",
                        headers={"xi-api-key": self.genmax_key}, timeout=5,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        bal = d.get("credit_balance", 0)
                        parts.append(f"GenMax: {bal:,}")
                    else:
                        parts.append("✅ GenMax")
                except Exception:
                    parts.append("✅ GenMax")
            # ── ElevenLabs credits ────────────────────────────────
            if self.el_keys:
                total = 0
                for key in self.el_keys:
                    r = requests.get(
                        "https://api.elevenlabs.io/v1/user/subscription",
                        headers={"xi-api-key": key}, timeout=5,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        total += d.get("character_limit", 0) - d.get("character_count", 0)
                parts.append(f"EL: {total:,}")
                if len(self.el_keys) > 1:
                    parts[-1] += f" ({len(self.el_keys)} keys)"
            # ── Fallback ──────────────────────────────────────────
            if not parts:
                self.done.emit("⚠️  Chưa có TTS API key — vào Settings")
            else:
                self.done.emit("  ·  ".join(parts))
        except Exception:
            self.done.emit("Không check được credits")
