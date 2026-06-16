import os
import sys
import re
import json
import time
import base64
import mimetypes
import requests

from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from app_constants import (
    DEFAULT_PROMPT_FUNNY,
    VERSION, GITHUB_REPO, VOICE_ID, MODEL, EL_OUTPUT_FORMAT,
    GEMINI_CHAT_PROMPT,
)
from app_utils import DEFAULT_OUT, DATA_DIR, SETTINGS_FILE, get_auto_video_env_local, get_tool_output_dir, is_auto_video_unlocked, load_settings
from prompt_files import read_style_prompt_file

_ENGINE_ENV_LOCAL = get_auto_video_env_local()
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_AUTO_MODEL_VALUES = {"", "auto", "tự động", "automatic"}
_GEMINI_MODEL_CACHE: dict[str, tuple[float, list[str]]] = {}

def _read_pipeline_env() -> dict:
    out: dict[str, str] = {}
    try:
        if not is_auto_video_unlocked(load_settings()):
            return out
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


def _normalise_gemini_model(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.lower() in GEMINI_AUTO_MODEL_VALUES:
        return ""
    return raw.removeprefix("models/")


def _list_gemini_models(api_key: str) -> list[str]:
    api_key = (api_key or "").strip()
    if not api_key:
        return []
    cached = _GEMINI_MODEL_CACHE.get(api_key)
    now = time.time()
    if cached and now - cached[0] < 3600:
        return cached[1]
    res = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
        timeout=12,
    )
    if res.status_code != 200:
        return []
    models: list[str] = []
    for item in res.json().get("models", []):
        name = str(item.get("name", "")).removeprefix("models/").strip()
        methods = {str(m) for m in item.get("supportedGenerationMethods", [])}
        if name and "generateContent" in methods:
            lowered = name.lower()
            if not any(skip in lowered for skip in ("embedding", "imagen", "image", "veo", "tts", "aqa")):
                models.append(name)
    _GEMINI_MODEL_CACHE[api_key] = (now, models)
    return models


def _choose_gemini_model(api_key: str, preferred: str | None = "", task: str = "text") -> str:
    preferred = _normalise_gemini_model(preferred)
    if preferred:
        return preferred
    models = _list_gemini_models(api_key)
    if not models:
        return GEMINI_DEFAULT_MODEL
    preferred_order = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    lowered_map = {m.lower(): m for m in models}
    for wanted in preferred_order:
        if wanted in lowered_map:
            return lowered_map[wanted]
    for wanted in preferred_order:
        for model in models:
            if model.lower().startswith(wanted):
                return model
    flash = [m for m in models if "flash" in m.lower()]
    return flash[0] if flash else models[0]


def _extract_gemini_text(data: dict) -> str:
    candidates = data.get("candidates", [])
    if not candidates:
        raise Exception("Gemini không trả về kết quả")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(str(part.get("text", "")) for part in parts if part.get("text"))
    if not text.strip():
        raise Exception("Gemini trả về rỗng")
    return text.strip()


def _call_gemini_generate(
    api_key: str,
    parts: list[dict],
    *,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    preferred_model: str | None = "",
    task: str = "text",
    timeout: int = 60,
) -> tuple[str, str]:
    model = _choose_gemini_model(api_key, preferred_model, task=task)
    payload: dict = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": float(temperature or 0),
            "maxOutputTokens": int(max_tokens or 2000),
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    res = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if res.status_code == 503:
        time.sleep(2)
        res = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
    if res.status_code != 200:
        raise Exception(f"Gemini {res.status_code}: {res.text[:240]}")
    return _extract_gemini_text(res.json()), model


def _strip_code_fences(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json|text)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _estimated_words_from_text(text: str) -> list[dict]:
    words = re.findall(r"\S+", text or "")
    out: list[dict] = []
    cursor = 0.0
    for word in words:
        duration = max(0.18, min(0.7, len(word) / 13.0))
        start = cursor
        end = cursor + duration
        out.append({"text": word, "start": start, "end": end, "type": "word"})
        cursor = end
        out.append({"text": " ", "start": cursor, "end": cursor + 0.04, "type": "spacing"})
        cursor += 0.04
    return out

_EL_V3_TAG_RE = re.compile(r"\[[a-z][a-z -]{1,40}\]", re.I)
_EL_V3_STYLE_RULES = (
    ("[happy]", re.compile(r"(follow|đăng ký|xem tiếp|đừng bỏ lỡ|hẹn gặp|cảm ơn|ok|ổn|được)", re.I)),
    ("[curious]", re.compile(r"(\?|bạn có biết|vì sao|tại sao|liệu|điều gì xảy ra)", re.I)),
    ("[impressed]", re.compile(r"(đột phá|kỷ lục|ấn tượng|mới nhất|ra mắt|tăng mạnh|vượt trội|thành công)", re.I)),
    ("[thoughtful]", re.compile(r"(nhưng|tuy nhiên|vấn đề|rủi ro|cảnh báo|sự thật|đáng chú ý|bất ngờ)", re.I)),
    ("[reassuring]", re.compile(r"(yên tâm|không lo|đỡ|ổn rồi|an toàn|dễ|gọn)", re.I)),
    ("[speaking fast]", re.compile(r"(nhanh|gấp|liền|ngay|chạy luôn|xong là)", re.I)),
)

def _tts_supports_v3_tags(provider: str, model: str) -> bool:
    provider = str(provider or "").strip().lower()
    model = str(model or "").strip().lower()
    return "eleven_v3" in model or (provider == "elevenlabs" and model in {"", "eleven_v3"})


def _tts_v3_prompt() -> str:
    return """# ElevenLabs V3 — Official Reference

> Nguồn: [ElevenLabs Text-to-Speech Best Practices](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices)
> Model: Eleven v3
> Dùng cho: nhấn nhá, audio tags, punctuation control, multi-speaker

---

## 1. Model Selection

| Feature | Flash v2 | English v1 | **Eleven v3** |
|---------|----------|------------|---------------|
| SSML `<break />` | ✅ | ✅ | ❌ |
| `<phoneme>` tags | ✅ | ✅ | ❌ |
| Audio tags `[...]` | ❌ | ❌ | ✅ |
| Accent switching | ❌ | ❌ | ✅ |
| Multi-speaker | ❌ | ❌ | ✅ |
| Enhance button | ❌ | ❌ | ✅ |

**Khi nào dùng V3:**
- Creative content, podcast, audiobook
- Nhân vật với cảm xúc đa dạng
- Multi-speaker dialogue
- Cần expressive, natural delivery
- Accent switching

---

## 2. Voice Selection & Stability

### Voice Types

| Use case | Voice type | Stability |
|----------|-----------|-----------|
| Audiobook nhân vật | Emotionally diverse IVC | Creative |
| Podcast neutral | Neutral IVC | Natural |
| Customer service | Neutral IVC | Robust |
| TTS real-time app | Neutral IVC | Robust |
| Gaming character | Emotionally diverse IVC | Creative |
| Sports commentary | Targeted niche IVC | Natural |
| Multi-language | Neutral IVC | Natural |

### Stability Modes

```
Creative  → Biểu cảm mạnh, audio tags responsive NHẤT
Natural   → Cân bằng, gần reference audio nhất (DEFAULT KHUYẾN NGHỊ)
Robust    → Rất ổn định, audio tags ÍT hiệu quả hơn
```

> ⚠️ Professional Voice Clones (PVCs) chưa tối ưu cho V3 — dùng IVC khi có thể.

---

## 3. Audio Tags — Full Reference

### Cú pháp

```
SYNTAX: [tag] — viết thường, đặt trước/sau/giữa câu

VỊ TRÍ:
  Trước câu : [whispers] I never knew it could be this way.
  Sau câu   : This is hard. [sighs]
  Kết hợp   : [excited] [laughs] That's amazing!
  Giữa câu  : \"I can't believe [sighs] … this is happening.\"
```

### Emotion — Positive

```
[happy]       [excited]     [delighted]    [impressed]
[warmly]      [mischievously]
```

### Emotion — Negative

```
[sad]         [crying]      [angry]        [annoyed]
[appalled]    [frustrated]  [desperately]
```

### Emotion — Neutral / Complex

```
[curious]     [thoughtful]  [surprised]    [nervous]
[sheepishly]  [deadpan]     [sarcastic]    [dismissive]
```

### Professional / Consultative

```
[professional] [sympathetic] [reassuring]  [questioning]
```

### Non-Verbal — Laughing

```
[laughs]      [chuckles]    [giggles]
[laughs harder] [starts laughing] [laughing hysterically]
```

### Non-Verbal — Breathing

```
[sighs]       [exhales]     [exhales sharply]
[inhales deeply] [wheezing]
```

### Non-Verbal — Other

```
[whispers]    [clears throat] [short pause] [long pause]
[happy gasp]  [muttering]    [snorts]       [swallows] [gulps]
```

### Sound Effects

```
[gunshot]     [explosion]
[applause]    [clapping]
```

### Experimental (Test kỹ trước production)

```
[strong French accent] \"Zat's life, my friend.\"
[strong Russian accent] \"Dee Goldeneye eez fully operational.\"
[sings]    → voice chuyển sang hát
[woo]      → exclamation sound
[fart]     → sound effect
```

### Tag Combinations

```
VUI VẺ + NGẠC NHIÊN:
  [laughs harder] [giggles] \"I can't believe this!\"

LO LẮNG + BÍ MẬT:
  [nervous] [whispers] \"I don't think they know we're here.\"

MỈA MAI + KHÓ CHỊU:
  [sarcastic] [annoyed] \"Sure, that's DEFINITELY going to work.\"

PHẤN KHÍCH NHIỀU LAYERS:
  [excited] I mean OH MY GOD... [laughing hysterically] it's so good!

BẤT NGỜ → TIẾC:
  [surprised] \"Oh wow, that's... [sighs] actually kind of sad.\"

TỰ TIN → NHỎ GIỌNG:
  [professional] \"We've analyzed the data.\" [whispers] \"And it's not good.\"

ACCENT + CẢM XÚC:
  [excited] Check this out!
  [strong French accent] \"Zat's life, my friend.\"
  [giggles] isn't that insane?
```

### Tags KHÔNG được dùng

```
❌ [standing]  — không phải auditory
❌ [grinning]  — không phải auditory
❌ [pacing]    — không phải auditory
❌ [music]     — sound effect toàn bộ, không phải voice
❌ Bất kỳ tag nào mô tả hành động vật lý thay vì âm thanh
```

> ⚠️ Effectiveness phụ thuộc voice và training data — test kỹ trước production.
> ⚠️ Một số tags ít nhất quán hơn với một số voices — thử nhiều voices.

---

## 4. Punctuation Control

```
...  (Ellipses)  → Thêm pause và weight vào delivery
CAPS             → Tăng emphasis trên từ đó
—   (Em dash)    → Ngắt nhanh giữa 2 ý liên tiếp / cắt ngang
, . ? !          → Natural speech rhythm

VÍ DỤ:
  \"It was a VERY long day [sighs] … nobody listens anymore.\"
  → VERY  : emphasis mạnh
  → [sighs]: non-verbal sound
  → …     : weighted pause sau [sighs]

TEXT STRUCTURE:
  → Câu ngắn cho delivery tốt hơn câu dài
  → Ngắt dòng giữa các thoughts khác nhau → control pacing
  → Tránh câu quá dài không có dấu câu
```

---

## 5. Enhance (LLM Auto-Tag)

Luật của ElevenLabs Enhance — dùng làm reference khi thêm tag thủ công:

```
✅ PHẢI LÀM:
  → Thêm audio tags mô tả auditory (voice, sound)
  → Đặt tag trước hoặc ngay sau câu relevant
  → Đa dạng emotional expressions qua các đoạn
  → Tăng emphasis qua CAPS, dấu câu, ellipses

❌ TUYỆT ĐỐI KHÔNG:
  → Thay đổi, thêm, hoặc xóa bất kỳ từ nào trong text gốc
  → Dùng [standing], [grinning], [pacing], [music]
  → Invent dialogue mới
  → Dùng tags mâu thuẫn với meaning gốc

VÍ DỤ ENHANCE:
  Input:  \"Are you serious? I can't believe you did that!\"
  Output: \"[appalled] Are you serious? [sighs] I can't believe you did that!\"

  Input:  \"That's amazing, I didn't know you could sing!\"
  Output: \"[laughing] That's amazing, [singing] I didn't know you could sing!\"

  Input:  \"I guess you're right. It's just... difficult.\"
  Output: \"I guess you're right. [sighs] It's just... [muttering] difficult.\"
```

---

## 6. Multi-Speaker Dialogue

```
TEMPLATE CƠ BẢN:
  Speaker 1: [excited] Sam! Have you tried the new Eleven V3?
  Speaker 2: [curious] Just got it! The clarity is amazing.

SIMULATE CẮT NGANG:
  Speaker 1: I think we should—
  Speaker 2: —do it differently!
  (Dấu — cuối câu 1 + — đầu câu 2 = cảm giác cắt ngang)

VÍ DỤ THỰC TẾ:
  Speaker 1: [excitedly] Sam! Have you tried the new Eleven V3?
  Speaker 2: [curiously] Just got it! The clarity is amazing.
             I can actually do whispers now — [whispers] like this!
  Speaker 1: [impressed] Ooh, fancy! Check this out —
             [dramatically] \"To be or not to be, that is the question!\"
  Speaker 2: [delighted] That's so much better!
```

> ⚠️ KHÔNG thể overlap thật trong single generation. Generate từng speaker riêng → combine trong audio editor.

---

## 7. Text Normalization

V3 có normalization mặc định, nhưng có thể sai với số/tiền phức tạp.

**Luật normalize trước khi gửi TTS:**

| Input | Output |
|-------|--------|
| `$1,000,000` | \"one million dollars\" |
| `$47,345.67` | \"forty-seven thousand three hundred forty-five dollars and sixty-seven cents\" |
| `123-456-7890` | \"one two three, four five six, seven eight nine zero\" |
| `100km` | \"one hundred kilometers\" |
| `100%` | \"one hundred percent\" |
| `2024-01-01` | \"January first, two-thousand twenty-four\" |
| `14:30` | \"two thirty PM\" |
| `Ctrl + Z` | \"control z\" |

---

## 8. Troubleshooting

| Vấn đề | Giải pháp |
|--------|-----------|
| Tag không hiệu quả | Đổi sang Creative/Natural stability, test voice khác |
| Pause không nhất quán | Dùng `...` (v3 không hỗ trợ `<break />`) |
| Audio artifact | Giảm số lượng tag, tránh tag dày đặc |
| Số đọc sai | Normalize text trước khi gửi |
| PVC chất lượng thấp | Dùng IVC thay PVC |
| Pace không đúng | Adjust speed 0.7–1.2 |

### Debug Checklist

```
□ Đúng model chưa? (v3 cho audio tags)
□ Stability: Creative hoặc Natural?
□ Voice có training data phù hợp không?
□ Tag đặt đúng vị trí chưa? (trước/sau/giữa câu)
□ Text structure rõ ràng không? (câu ngắn, dấu câu đúng)
□ Quá nhiều tag → giảm xuống 2-5 tag/đoạn
□ Số/tiền tệ đã normalize chưa?
```
"""

def _split_api_keys(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_parts = []
        for item in value:
            raw_parts.extend(re.split(r"[\s,;]+", str(item or "")))
    else:
        raw_parts = re.split(r"[\s,;]+", str(value or ""))
    keys: list[str] = []
    for part in raw_parts:
        key = str(part or "").strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _elevenlabs_key_pool(*sources, limit: int = 3) -> list[str]:
    keys: list[str] = []
    for source in sources:
        if not source:
            continue
        if isinstance(source, dict):
            values = [
                source.get("ELEVENLABS_API_KEY"),
                source.get("ELEVENLABS_API_KEYS"),
                source.get("ELEVENLABS_API_KEY_2"),
                source.get("ELEVENLABS_API_KEY_3"),
                source.get("el_api_key"),
                source.get("el_api_keys"),
            ]
        else:
            values = [source]
        for value in values:
            for key in _split_api_keys(value):
                if key not in keys:
                    keys.append(key)
    return keys[:limit] if limit else keys


def _elevenlabs_should_rotate(status_code: int | None, message: str = "") -> bool:
    text = str(message or "").lower()
    return (
        status_code in (401, 402, 403, 429)
        or "quota" in text
        or "credit" in text
        or "character" in text
        or "rate limit" in text
        or "too many requests" in text
        or "billing" in text
    )


def humanize_tts_error(message: str) -> dict:
    """Convert provider/API noise into a user-facing TTS error."""
    raw = str(message or "").strip()
    text = raw.lower()
    title = "Tạo audio lỗi"
    detail = "Tool chưa tạo được audio. Thử lại hoặc kiểm tra cài đặt TTS."
    action = "Mở Cài đặt -> API để kiểm tra key, giọng đọc và credit."
    code = "unknown"

    if not raw:
        return {"code": code, "title": title, "detail": detail, "action": action, "raw": raw}

    if "thiếu genmax api key" in text or "missing genmax" in text:
        code = "missing_genmax_key"
        title = "Thiếu GenMax key"
        detail = "Tool đang ưu tiên GenMax nhưng chưa có GenMax API key."
        action = "Vào Cài đặt -> API, nhập GenMax key hoặc đổi provider sang ElevenLabs."
    elif "thiếu elevenlabs api key" in text or "missing elevenlabs" in text:
        code = "missing_elevenlabs_key"
        title = "Thiếu ElevenLabs key"
        detail = "Tool cần ElevenLabs API key để tạo audio bằng provider này."
        action = "Vào Cài đặt -> API và nhập ElevenLabs key."
    elif "không tìm thấy giọng" in text or "voice_not_found" in text or "voice not found" in text:
        code = "voice_not_found"
        title = "Không tìm thấy giọng"
        detail = "Voice ID này chưa có trong account hoặc là giọng Shared Library chưa được add đúng cách."
        action = "Kiểm tra lại Voice ID. Nếu là Shared Library, dùng nút Kiểm tra/Test giọng trước khi lưu."
    elif "paid_plan_required" in text or "free users cannot use library voices" in text or "library voice" in text:
        code = "voice_needs_plan"
        title = "Giọng này cần nâng gói"
        detail = "Đây là giọng Library/Professional. API key hiện tại chưa được render voice này qua ElevenLabs API."
        action = "Nâng gói ElevenLabs, chọn voice premade như Adam, hoặc test lại qua GenMax trước khi dùng batch."
    elif "missing_permissions" in text or "add_voice_from_voice_library" in text:
        code = "missing_voice_permission"
        title = "Key thiếu quyền giọng đọc"
        detail = "API key chưa có quyền thêm hoặc dùng giọng từ Voice Library."
        action = "Trong ElevenLabs API key, bật Voices = Write và Voice Generation/Text to Speech = Access."
    elif any(token in text for token in ("quota", "credit", "character limit", "billing", "payment_required", "insufficient")):
        code = "credit_or_billing"
        title = "Hết credit hoặc vướng thanh toán"
        detail = "Provider từ chối tạo audio vì credit/quota/gói thanh toán không đủ."
        action = "Kiểm tra credit GenMax/ElevenLabs hoặc nạp thêm/nâng gói."
    elif "rate limit" in text or "too many requests" in text or " 429" in text or "429:" in text:
        code = "rate_limited"
        title = "Provider đang giới hạn tốc độ"
        detail = "Bạn gọi API quá nhanh hoặc provider đang giới hạn key hiện tại."
        action = "Chờ một lúc rồi tạo lại, hoặc đổi key/provider."
    elif "timeout" in text or "processing" in text or "provider_under_maintenance" in text or "service unavailable" in text or "503" in text:
        code = "provider_slow"
        title = "Provider đang chậm"
        detail = "Provider nhận job nhưng xử lý chậm, timeout hoặc đang bảo trì."
        action = "Thử lại sau vài phút. Nếu cần nhanh, đổi sang ElevenLabs direct hoặc voice khác."
    elif "401" in text or "invalid_key" in text or "unauthorized" in text:
        code = "invalid_key"
        title = "API key không hợp lệ"
        detail = "Provider không chấp nhận API key hiện tại."
        action = "Tạo/copy lại key mới rồi dán vào Cài đặt -> API."
    elif "400" in text or "422" in text:
        code = "bad_request"
        title = "Cài đặt voice chưa đúng"
        detail = "Provider báo request chưa hợp lệ. Thường do Voice ID, model, language hoặc quyền voice chưa khớp."
        action = "Bấm Test giọng trước. Nếu là Shared Library, cần add/test voice trước khi render."
    else:
        detail = raw.replace("\n", " · ")
        if len(detail) > 220:
            detail = detail[:217].rstrip() + "..."

    return {"code": code, "title": title, "detail": detail, "action": action, "raw": raw}


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
    """Fetch danh sách voices từ ElevenLabs."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, genmax_key: str = ""):
        super().__init__()
        self.api_key    = api_key
        self.api_keys   = _elevenlabs_key_pool(api_key)
        self.genmax_key = ""

    def run(self):
        try:
            last_err = "Thiếu ElevenLabs API key"
            for key in self.api_keys:
                r = requests.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers={"xi-api-key": key},
                    timeout=10,
                )
                if r.status_code == 200:
                    voices = r.json().get("voices", [])
                    voices.sort(key=lambda v: v.get("name", "").lower())
                    self.done.emit(voices)
                    return
                last_err = f"HTTP {r.status_code}"
                if not _elevenlabs_should_rotate(r.status_code, r.text):
                    break
            self.error.emit(last_err)
        except Exception as e:
            self.error.emit(str(e))


class SharedVoiceFetcher(QThread):
    """Fetch voices từ ElevenLabs Shared Voice Library."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, language: str = "", search: str = "",
                 page_size: int = 30, genmax_key: str = ""):
        super().__init__()
        self.api_key    = api_key
        self.api_keys   = _elevenlabs_key_pool(api_key)
        self.language   = language
        self.search     = search
        self.page_size  = page_size
        self.genmax_key = ""

    def run(self):
        try:
            params = {"page_size": self.page_size, "sort": "trending"}
            if self.language:
                params["required_languages"] = self.language
            if self.search:
                params["search"] = self.search
            last_err = "Thiếu ElevenLabs API key"
            for key in self.api_keys:
                r = requests.get(
                    "https://api.elevenlabs.io/v1/shared-voices",
                    headers={"xi-api-key": key},
                    params=params,
                    timeout=12,
                )
                if r.status_code == 200:
                    voices = r.json().get("voices", [])
                    self.done.emit(voices)
                    return
                last_err = f"HTTP {r.status_code}"
                if not _elevenlabs_should_rotate(r.status_code, r.text):
                    break
            self.error.emit(last_err)
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
        self.api_keys       = _elevenlabs_key_pool(api_key)
        self.voice_id       = voice_id
        self.public_user_id = public_user_id
        self.name           = name

    def run(self):
        try:
            last_err = "Thiếu ElevenLabs API key"
            for key in self.api_keys:
                r = requests.post(
                    f"https://api.elevenlabs.io/v1/voices/add/{self.public_user_id}/{self.voice_id}",
                    headers={"xi-api-key": key, "Content-Type": "application/json"},
                    json={"new_name": self.name},
                    timeout=15,
                )
                if r.status_code == 200:
                    new_id = r.json().get("voice_id", self.voice_id)
                    self.done.emit(new_id, self.name)
                    return
                last_err = f"HTTP {r.status_code}: {r.text[:120]}"
                if not _elevenlabs_should_rotate(r.status_code, r.text):
                    break
            self.error.emit(last_err)
        except Exception as e:
            self.error.emit(str(e))


class PromptGeneratorWorker(QThread):
    """Dùng Claude/DeepSeek để tạo system prompt từ mô tả ngắn của user."""
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    _META_PROMPT = """Bạn là chuyên gia viết prompt phong cách cho TTS.

Nhiệm vụ: Dựa trên mô tả ngắn, tạo prompt phong cách hoàn chỉnh để AI xử lý kịch bản TTS theo đúng gu người dùng.

Prompt phải có đủ các phần:
1. Mô tả vai trò + phong cách + tông giọng phù hợp mô tả
2. Quy tắc xử lý viết tắt tiếng Việt (a→anh, e→em, k→không, dc→được...)
3. Quy tắc số & tiền tệ (650k→sáu trăm năm mươi nghìn, 1tr→một triệu...)
4. Quy tắc nhấn mạnh bằng CAPS nếu phong cách cần, dùng vừa phải
5. Quy tắc nhịp đọc bằng dấu câu thường (... và —) nếu phù hợp phong cách
6. Quy tắc output: chỉ trả về kịch bản đã xử lý, không giải thích

KHÔNG viết luật ElevenLabs v3 audio tags trong prompt phong cách.
KHÔNG liệt kê tag dạng [laughs], [curious], [excited]...
Luật nhấn nhá v3 do tool tự thêm riêng khi người dùng bật công tắc Nhấn nhá v3.

Nếu mô tả có trường "Từ ngữ đặc trưng":
- BẮT BUỘC tạo một mục riêng tên "TỪ NGỮ ĐẶC TRƯNG".
- Giữ nguyên văn từng từ/cụm từ user nhập, không tự bỏ, không thay bằng từ đồng nghĩa.
- Viết rule rõ: ưu tiên giữ các cụm này khi chúng đã có trong kịch bản gốc; có thể thêm tự nhiên khi phù hợp ngữ cảnh; không lạm dụng.
- Nếu cụm từ là tiếng lóng/xưng hô/thương hiệu, không sửa chính tả và không dịch.

Nếu mô tả có trường "Tuyệt đối tránh":
- BẮT BUỘC tạo một mục riêng tên "TUYỆT ĐỐI TRÁNH" và giữ đúng các điều user đã nhập.

Nếu mô tả có trường "Ví dụ đúng gu":
- BẮT BUỘC tạo một mục riêng tên "VÍ DỤ ĐÚNG GU".
- Rút ra nhịp câu, cách xưng hô, mức thân mật, kiểu hài/hook từ ví dụ.
- Không copy máy móc ví dụ vào mọi output; chỉ dùng làm style reference.

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
        example = self._extract_field(self.description, "Ví dụ đúng gu")
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

        if example and "VÍ DỤ ĐÚNG GU" not in prompt.upper():
            additions.append(
                "## VÍ DỤ ĐÚNG GU\n"
                f"- Ví dụ tham chiếu phong cách: {example}\n"
                "- Học nhịp câu, cách xưng hô, mức thân mật và kiểu hook từ ví dụ này.\n"
                "- Không copy máy móc ví dụ vào mọi kịch bản."
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
                try:
                    prompt, _model = _call_gemini_generate(
                        self.gemini_key,
                        [{"text": full_prompt}],
                        max_tokens=1800,
                        preferred_model="auto",
                        timeout=60,
                    )
                    self.done.emit(self._ensure_required_user_terms(prompt))
                    return
                except Exception:
                    pass  # fallback to DeepSeek
            if not self.api_key:
                self.error.emit("⚠️ Chưa có AI key — vào Settings → API → thêm Claude, Gemini hoặc DeepSeek")
                return
            res = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": "deepseek-v4-pro",
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
                try:
                    raw, _model = _call_gemini_generate(
                        self.gemini_key,
                        [{"text": full_prompt}],
                        max_tokens=600,
                        preferred_model="auto",
                        timeout=30,
                    )
                    self.done.emit(self._parse_json(raw))
                    return
                except Exception:
                    pass  # fallback to DeepSeek
            if not self.api_key:
                self.error.emit("⚠️ Chưa có AI key — vào Settings → API → thêm Claude, Gemini hoặc DeepSeek")
                return
            res = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": "deepseek-v4-pro",
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
def _load_prompt(name: str) -> str:
    """Load TTS prompt docs in source and PyInstaller bundles."""
    base_dirs = [
        os.path.dirname(__file__),
        getattr(sys, "_MEIPASS", ""),
        os.path.join(os.path.dirname(sys.executable), "..", "Resources")
        if getattr(sys, "frozen", False)
        else "",
    ]
    for base_dir in base_dirs:
        if not base_dir:
            continue
        path = os.path.join(base_dir, "docs", "tts", name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
    if name == "viral.md":
        return DEFAULT_PROMPT_FUNNY
    if name == "11labs.md":
        return _tts_v3_prompt()
    raise FileNotFoundError(f"Prompt not found: {name}")

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
            out_dir = get_tool_output_dir(self.s, "tts")
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
        ds_key = self.s.get("ds_api_key", "").strip()
        if not ds_key:
            raise Exception(
                "⚠️ Chưa có DeepSeek API Key.\n"
                "📌 Vào Settings → API → thêm DeepSeek API Key."
            )
        temperature = float(self.s.get("enhance_style_temperature", 0.4))

        style_name = str(self.s.get("enhance_style_name", "") or "").strip()
        fallback_prompt = self.s.get("enhance_prompt", _load_prompt("viral.md"))
        style_prompt = (
            read_style_prompt_file(style_name, fallback_prompt)
            if style_name
            else fallback_prompt
        )
        if _eleven_v3_style_enabled(self.s):
            self.status.emit("Đang xử lý style + nhấn nhá V3...")
            system_prompt = f"""{style_prompt}

---

SAU KHI ÁP DỤNG PROMPT STYLE Ở TRÊN, TIẾP TỤC ÁP DỤNG PROMPT ELEVENLABS V3 SAU TRONG CÙNG MỘT LẦN XỬ LÝ.
Output cuối cùng phải là bản đã qua cả hai lớp: style/viral + tag/nhịp/format ElevenLabs V3.

{_load_prompt("11labs.md")}"""
        else:
            self.status.emit("Đang xử lý style...")
            system_prompt = style_prompt

        res = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {ds_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-v4-pro",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": text},
                ],
                "temperature": temperature,
            },
            timeout=90,
        )
        if res.status_code != 200:
            stage = "DeepSeek Style+V3" if _eleven_v3_style_enabled(self.s) else "DeepSeek Viral"
            raise Exception(f"{stage} {res.status_code}: {res.text[:200]}")
        return res.json()["choices"][0]["message"]["content"].strip()

    def _tts(self, text: str) -> bytes:
        env = _read_pipeline_env()
        return self._tts_elevenlabs(text, env)

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
        if provider == "elevenlabs":
            return per_tool or env.get("ELEVENLABS_VOICE_ID", "").strip() or selected or VOICE_ID
        return per_tool or selected or VOICE_ID

    def _tts_elevenlabs(self, text: str, env: dict) -> bytes:
        keys = _elevenlabs_key_pool(env, self.s)
        if not keys:
            raise Exception("thiếu ElevenLabs API key")
        voice_id = self._voice_for("elevenlabs", env)
        model = env.get("ELEVENLABS_MODEL_ID", "").strip() or MODEL

        def _is_library_voice_block(message: str) -> bool:
            lower = (message or "").lower()
            return (
                "paid_plan_required" in lower
                and ("library voice" in lower or "free users cannot use" in lower)
            )

        def _attempt_voice(target_voice_id: str, voice_label: str) -> tuple[bytes | None, Exception | None, bool]:
            last_err: Exception | None = None
            saw_library_block = False
            for idx, key in enumerate(keys, 1):
                key_label = f"key {idx}/{len(keys)} (...{key[-6:]})"
                self.status.emit(f"Đang render bằng ElevenLabs v3 [{voice_label} · {key_label}]...")
                supports_v3_tags = _tts_supports_v3_tags("elevenlabs", model)
                tts_text = text if supports_v3_tags else self._clean_tts_text(text)
                if not supports_v3_tags and tts_text != text:
                    self.status.emit("Model ElevenLabs này không dùng tag v3 — đã làm sạch tag trước khi tạo audio.")
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
                    f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice_id}",
                    headers={"xi-api-key": key, "Content-Type": "application/json"},
                    json=body,
                    timeout=60,
                )
                if res.status_code == 200:
                    return res.content, None, saw_library_block
                error_text = res.text[:500]
                saw_library_block = saw_library_block or _is_library_voice_block(error_text)
                last_err = Exception(f"ElevenLabs {res.status_code}: {error_text[:300]}")
                if idx < len(keys):
                    self.status.emit(f"⚠️ ElevenLabs {voice_label} · {key_label} lỗi — thử key tiếp theo...")
            return None, last_err, saw_library_block

        audio, last_err, library_blocked = _attempt_voice(voice_id, "voice đang chọn")
        if audio is not None:
            return audio

        if library_blocked:
            voice_name = (
                self.s.get("tts_voice_name", "").strip()
                or self.s.get("selected_voice_name", "").strip()
                or voice_id
            )
            raise Exception(
                f"ElevenLabs còn ký tự free nhưng không render được voice '{voice_name}' qua API free "
                "vì đây là shared/library voice. Chọn Adam/premade voice hoặc nâng cấp ElevenLabs."
            )
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
        self._delegate.status.connect(self.status.emit)
        self._tts = self._delegate._tts

    def run(self):
        try:
            self.status.emit("Đang kiểm tra provider TTS...")
            audio = self._tts(self.text)
            out_dir = get_tool_output_dir(self.s, "tts")
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
    """Gọi GenMax STT, fallback Gemini nếu GenMax lỗi hoặc thiếu key."""
    done   = pyqtSignal(str, list)  # (full_text, words)
    status = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(self, file_path: str, genmax_key: str, gemini_key: str = "", settings: dict | None = None):
        super().__init__()
        self.file_path  = file_path
        self.genmax_key = genmax_key
        self.gemini_key = (gemini_key or "").strip()
        self.settings = settings or {}

    def run(self):
        errors: list[str] = []
        try:
            if self.genmax_key:
                try:
                    self.status.emit("Đang upload audio lên GenMax...")
                    with open(self.file_path, "rb") as f:
                        r = requests.post(
                            "https://api.genmax.io/v1/speech-to-text",
                            headers={"xi-api-key": self.genmax_key},
                            files={"file": f},
                            data={"model_id": "scribe_v1"},
                            timeout=120,
                        )
                    if r.status_code == 200:
                        data = r.json()
                        text = data.get("text", "")
                        words = data.get("words", [])
                        self.done.emit(text, words)
                        return
                    errors.append(f"GenMax STT {r.status_code}: {r.text[:200]}")
                except Exception as e:
                    errors.append(f"GenMax STT: {e}")

            if self.gemini_key:
                if errors:
                    self.status.emit("GenMax lỗi — thử Gemini fallback...")
                else:
                    self.status.emit("Đang nhận diện với Gemini...")
                text = self._stt_gemini()
                self.done.emit(text, _estimated_words_from_text(text))
                return

            if not errors:
                self.error.emit("Thiếu STT key: thêm GenMax hoặc Gemini API Key trong Settings → API.")
            else:
                self.error.emit("\n".join(errors))
        except Exception as e:
            self.error.emit(str(e))

    def _stt_gemini(self) -> str:
        mime = mimetypes.guess_type(self.file_path)[0] or "audio/mpeg"
        with open(self.file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        prompt = (
            "Bạn là hệ thống Speech-to-Text. Hãy nghe audio và chép lại thành văn bản thuần.\n"
            "Ưu tiên đúng ngôn ngữ gốc, giữ dấu tiếng Việt, sửa lỗi nghe rõ ràng.\n"
            "Trả về JSON hợp lệ, không markdown, đúng dạng: {\"text\":\"...\"}"
        )
        raw, model = _call_gemini_generate(
            self.gemini_key,
            [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": data}},
            ],
            temperature=0.0,
            max_tokens=4000,
            preferred_model=self.settings.get("gemini_stt_model", "auto"),
            task="stt",
            timeout=180,
        )
        self.status.emit(f"Gemini đã nhận diện ({model})")
        cleaned = _strip_code_fences(raw)
        try:
            parsed = json.loads(cleaned)
            text = str(parsed.get("text", "")).strip()
            if text:
                return text
        except Exception:
            pass
        text = cleaned.strip()
        if not text:
            raise Exception("Gemini STT trả về rỗng")
        return text


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
                total_paid = 0
                total_free = 0
                paid_count = 0
                free_count = 0
                for key in self.el_keys:
                    r = requests.get(
                        "https://api.elevenlabs.io/v1/user/subscription",
                        headers={"xi-api-key": key}, timeout=5,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        remain = max(0, int(d.get("character_limit", 0) - d.get("character_count", 0)))
                        tier = str(d.get("tier", "")).strip().lower()
                        if tier == "free":
                            total_free += remain
                            free_count += 1
                        else:
                            total_paid += remain
                            paid_count += 1
                if paid_count and free_count:
                    parts.append(f"EL: {total_paid:,} paid + {total_free:,} free")
                elif paid_count:
                    suffix = f" ({paid_count} keys)" if paid_count > 1 else ""
                    parts.append(f"EL: {total_paid:,}{suffix}")
                elif free_count:
                    suffix = f" ({free_count} keys)" if free_count > 1 else ""
                    parts.append(f"EL: {total_free:,} free{suffix} · chỉ premade")
            # ── Fallback ──────────────────────────────────────────
            if not parts:
                self.done.emit("⚠️  Chưa có TTS API key — vào Settings")
            else:
                self.done.emit("  ·  ".join(parts))
        except Exception:
            self.done.emit("Không check được credits")
