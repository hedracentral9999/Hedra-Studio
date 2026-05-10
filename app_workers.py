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
    DEFAULT_PROMPT, CREATIVITY_CONTENT_LOCK,
    VERSION, GITHUB_REPO, VOICE_ID, MODEL, EL_OUTPUT_FORMAT,
    GEMINI_CHAT_PROMPT,
)
from app_utils import DEFAULT_OUT, DATA_DIR, SETTINGS_FILE

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

    def __init__(self, description: str, api_key: str, gemini_key: str = ""):
        super().__init__()
        self.description = description
        self.api_key     = api_key
        self.gemini_key  = gemini_key

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
            # Ưu tiên Gemini (miễn phí) → fallback DeepSeek
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
                self.error.emit("⚠️ Chưa có AI key — vào Settings → API Keys → thêm Gemini (miễn phí) hoặc DeepSeek")
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

    def __init__(self, description: str, api_key: str, gemini_key: str = ""):
        super().__init__()
        self.description = description
        self.api_key     = api_key
        self.gemini_key  = gemini_key

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
            # Ưu tiên Gemini (miễn phí) → fallback DeepSeek
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
                self.error.emit("⚠️ Chưa có AI key — vào Settings → API Keys → thêm Gemini (miễn phí) hoặc DeepSeek")
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
            self.done.emit(path)
        except Exception as e:
            self.error.emit(str(e))

    def _enhance(self, text: str) -> str:
        ds_key     = self.s.get("ds_api_key", "").strip()
        gemini_key = self.s.get("gemini_api_key", "").strip()
        if not ds_key and not gemini_key:
            raise Exception(
                "⚠️ Chưa có AI key để enhance kịch bản.\n"
                "📌 Vào Settings → tab API Keys:\n"
                "  • Gemini API Key (miễn phí — khuyến nghị cho người mới)\n"
                "  • DeepSeek API Key (trả phí, chất lượng cao)"
            )
        # ── Lấy temperature từ style (slider), fallback về creative bool nếu chưa có
        temperature = self.s.get(
            "enhance_style_temperature",
            0.7 if self.s.get("enhance_style_creative", False) else 0.3
        )
        # ── Lấy base prompt
        system_prompt = self.s.get("enhance_prompt", DEFAULT_PROMPT)
        # ── Khi sáng tạo = 0: gắn content lock, cấm thêm nội dung mới ─
        if temperature <= 0.0:
            system_prompt += CREATIVITY_CONTENT_LOCK

        # ── Ưu tiên Gemini (miễn phí) → fallback DeepSeek (trả phí) ─
        if gemini_key:
            full_prompt = f"{system_prompt}\n\n{text}"
            res = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": full_prompt}]}]},
                timeout=60,
            )
            if res.status_code == 200:
                candidates = res.json().get("candidates", [])
                if candidates:
                    return candidates[0]["content"]["parts"][0]["text"].strip()
            # Gemini lỗi → thử DeepSeek nếu có
            if not ds_key:
                raise Exception(f"Gemini {res.status_code}: {res.text[:200]}")

        # ── DeepSeek (trả phí, dùng khi không có Gemini hoặc Gemini lỗi) ─
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
        voice_id = self.s.get("selected_voice_id") or VOICE_ID

        # ── Thử GenMax trước ─────────────────────────────────────
        gm_key = self.s.get("genmax_api_key", "").strip()
        if gm_key:
            try:
                self.status.emit("Đang generate audio [GenMax]...")
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
                    f"https://api.genmax.io/v1/text-to-speech/{voice_id}",
                    headers={"xi-api-key": gm_key, "Content-Type": "application/json"},
                    json=tts_body,
                    timeout=30,
                )
                if res.status_code == 202:
                    task_id = res.json().get("id")
                    if not task_id:
                        raise Exception("GenMax không trả về task_id")
                    # Poll cho đến khi hoàn thành (tối đa 90 giây)
                    deadline = time.time() + 90
                    poll_interval = 2
                    while time.time() < deadline:
                        time.sleep(poll_interval)
                        self.status.emit("Đang chờ GenMax render audio...")
                        p = requests.get(
                            f"https://api.genmax.io/v1/history/{task_id}",
                            headers={"xi-api-key": gm_key},
                            timeout=15,
                        )
                        if p.status_code != 200:
                            raise Exception(f"GenMax poll lỗi {p.status_code}: {p.text[:200]}")
                        pdata = p.json()
                        status = pdata.get("status", "")
                        if status == "completed":
                            audio_url = (pdata.get("result") or {}).get("audio_url", "")
                            if not audio_url:
                                raise Exception("GenMax không trả về audio_url")
                            self.status.emit("Đang tải audio từ GenMax...")
                            dl = requests.get(audio_url, timeout=30)
                            if dl.status_code != 200:
                                raise Exception(f"GenMax download lỗi {dl.status_code}")
                            return dl.content
                        elif status in ("failed", "error"):
                            raise Exception(f"GenMax render thất bại: {pdata}")
                        # pending/processing — tiếp tục poll
                        poll_interval = min(poll_interval + 1, 5)
                    raise Exception("GenMax timeout sau 90 giây")
                elif res.status_code == 200:
                    # Một số response trả về audio trực tiếp
                    return res.content
                else:
                    raise Exception(f"GenMax {res.status_code}: {res.text[:300]}")
            except Exception as gm_err:
                self.status.emit(f"⚠️ GenMax lỗi — chuyển sang ElevenLabs... ({gm_err})")

        # ── Fallback ElevenLabs ───────────────────────────────────
        keys = self.s.get("el_api_keys", [])
        if not keys:
            old = self.s.get("el_api_key", "").strip()
            keys = [old] if old else []
        keys = [k.strip() for k in keys if k.strip()]
        if not keys:
            if gm_key:
                raise Exception("⚠️ GenMax lỗi và chưa có ElevenLabs API key.\n📌 Vào Settings → tab API Keys để thêm.")
            raise Exception("⚠️ Chưa nhập API key.\n📌 Vào Settings → tab API Keys để thêm GenMax hoặc ElevenLabs key.")
        last_err = None
        for idx, key in enumerate(keys, 1):
            label = f"key {idx}/{len(keys)} (...{key[-6:]})"
            self.status.emit(f"Đang generate audio ElevenLabs [{label}]...")
            tts_body = {
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
                detail_msg = f"{label}: {reason}"
                if body:
                    try:
                        err_data = res.json()
                        detail = err_data.get("detail", "")
                        if isinstance(detail, str):
                            err_msg = detail
                        elif isinstance(detail, list) and detail:
                            err_msg = detail[0].get("msg", str(detail[0]))
                        elif isinstance(detail, dict):
                            err_msg = detail.get("message", str(detail))
                        else:
                            err_msg = str(err_data)
                        if err_msg and err_msg != "None":
                            detail_msg += f"\n→ {err_msg[:200]}"
                    except Exception:
                        detail_msg += f"\n→ {body[:200]}"
                last_err = Exception(detail_msg)
                if idx < len(keys):
                    self.status.emit(f"⚠️ {label} {reason} — thử key tiếp theo...")
                continue
            # Lỗi không rõ — hiển thị chi tiết để debug
            reason_map = {
                400: "sai request (có thể model/voice không tồn tại)",
                422: "dữ liệu không hợp lệ (có thể text quá dài hoặc ký tự đặc biệt)",
            }
            hint = reason_map.get(res.status_code, "")
            detail = f"ElevenLabs {res.status_code}"
            if hint:
                detail += f" — {hint}"
            detail += f"\n\n{body}"
            raise Exception(detail)
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
        # Mượn _tts từ Worker
        self._tts = Worker(text, speed, filename, settings)._tts

    def run(self):
        try:
            self.status.emit("Đang generate audio...")
            audio = self._tts(self.text)
            out_dir = self.s.get("output_dir", DEFAULT_OUT)
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, self.filename + ".mp3")
            with open(path, "wb") as f:
                f.write(audio)
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
                        "https://api.genmax.io/v1/user/subscription",
                        headers={"xi-api-key": self.genmax_key}, timeout=5,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        limit = d.get("character_limit", 0)
                        count = d.get("character_count", 0)
                        parts.append(f"GenMax: {limit - count:,} còn lại")
                    else:
                        parts.append("GenMax: đã kết nối")
                except Exception:
                    parts.append("GenMax: đã kết nối")
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
                parts.append(f"EL: {total:,} còn lại")
                if len(self.el_keys) > 1:
                    parts[-1] += f" ({len(self.el_keys)} keys)"
            # ── Fallback ──────────────────────────────────────────
            if not parts:
                self.done.emit("⚠️  Chưa có TTS API key — vào Settings")
            else:
                self.done.emit("  ·  ".join(parts))
        except Exception:
            self.done.emit("Không check được credits")


