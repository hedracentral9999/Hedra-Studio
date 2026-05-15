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

ENGINE_ENV_LOCAL = Path("/Users/admin/Auto-Create-Video/.env.local")
RECOMMENDED_CLAUDE_MODEL = "claude-sonnet-4-6"
LEGACY_DEFAULT_CLAUDE_MODELS = {
    "",
    "claude-3-5-haiku-20241022",
    "claude-sonnet-4-20250514",
}


def _read_engine_env() -> dict:
    env = {}
    if not ENGINE_ENV_LOCAL.exists():
        return env
    for line in ENGINE_ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        env[k.strip()] = v.strip()
    return env


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
Tạo script JSON cho video ngắn TikTok, mặc định 6-8 scenes: 1 hook + body + 1 outro.

QUY TẮC NỘI DUNG:
- voiceText: tiếng Việt tự nhiên, đủ ý nhưng không dài dòng
- Hook bắt đầu bằng số, câu hỏi hoặc thông tin gây tò mò
- KHÔNG dùng "Xin chào", "Hôm nay chúng ta"

QUY TẮC FORMAT — QUAN TRỌNG, tuân thủ tuyệt đối:
- hook.headline: tối đa 40 ký tự
- hook.subhead: tối đa 40 ký tự
- stat-hero.value: tối đa 20 ký tự, label: tối đa 40 ký tự
- feature-list.title: tối đa 40 ký tự, mỗi bullet: tối đa 50 ký tự, tối đa 4 bullets
- callout.statement: tối đa 80 ký tự, tag: tối đa 20 ký tự
- templateData chỉ được tóm tắt trực tiếp từ voiceText của chính scene đó; không thêm fact, claim hoặc ví dụ khác.
- Nếu không chắc templateData, vẫn ưu tiên voiceText đúng sự thật; engine sẽ tự đồng bộ visual từ voiceText.
- Nếu field quá dài, hãy VIẾT LẠI NGẮN HƠN; không được cắt ngang từ/câu.
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
    {"id":"hook","type":"hook","voiceText":"câu hook hấp dẫn, đúng nhịp dựng",
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


SCRIPT_PRESET_GUIDES = {
    "classic": "",
    "ai_news_fast": """

PRESET ĐANG CHỌN: AI NEWS NHANH.
Các rule dưới đây override rule tổng quát nếu có xung đột:
- Tạo 7-9 scenes ở nhịp standard; nếu nhịp dynamic bật thì tạo 10-12 scenes.
- metadata.title phải là title TikTok ngắn dạng: "Entity: điểm mới gây tò mò".
- hook.headline nên tách được thành 2 dòng: entity/công cụ/công ty + claim gây tò mò.
- Body đi đúng nhịp: cái gì mới → vì sao đáng chú ý → ai dùng được → rủi ro/giới hạn → kết luận nhanh.
- Nếu bài là profile founder/công ty, body phải đi theo nhịp: nhân vật → quyết định khác thường → sản phẩm/công nghệ → số liệu traction → giới hạn/rủi ro. Không biến cả video thành chuyện đời tư/lifestyle.
- Chi tiết đời tư kỳ lạ chỉ dùng làm hook hoặc một điểm tương phản; không dùng quá 1 body scene nếu nó không phải luận điểm chính của bài.
- Mỗi scene body phải trả lời được "vì sao điều này quan trọng?" thay vì chỉ kể một fact gây sốc.
- Mỗi voiceText mở bằng một câu ngắn 6-12 từ có thể dùng làm caption đáy.
- Ưu tiên số liệu, tên công cụ, tên công ty, repo, model, API, benchmark nếu có trong bài.
- Không tự nâng cấp sự kiện: nếu bài nói Olympic Vật lý thì không đổi thành Olympic Toán; nếu bài nói nạn nhân crypto thì không tự đổi thành tỷ phú crypto.
- Outro ngắn, kêu gọi follow tin AI/công nghệ; không dài dòng.
""",
    "github_repo_story": """

PRESET ĐANG CHỌN: GITHUB REPO STORY.
Các rule dưới đây override rule tổng quát nếu có xung đột:
- Tạo 7-9 scenes ở nhịp standard; nếu nhịp dynamic bật thì tạo 10-12 scenes.
- metadata.title dạng: "Tên repo/công ty: con số hoặc lợi ích lạ".
- Hook phải có repo/tên công cụ + star/download/claim nổi bật nếu nội dung có.
- Body đi theo nhịp: repo làm gì → vì sao tăng nhanh → tính năng đáng dùng → cách ai dùng được → caveat/rủi ro.
- Dùng template stat-hero cho star/con số, feature-list cho tính năng, callout cho caveat.
- Mỗi voiceText mở bằng một câu ngắn 6-12 từ có thể dùng làm caption đáy.
""",
    "research_explainer": """

PRESET ĐANG CHỌN: RESEARCH EXPLAINER.
Các rule dưới đây override rule tổng quát nếu có xung đột:
- Tạo 8-10 scenes ở nhịp standard; nếu nhịp dynamic bật thì tạo 11-14 scenes.
- metadata.title dạng: "Tên paper/model: kết quả ngược trực giác".
- Hook nêu kết quả mạnh nhất, không mở bài vòng vo.
- Body đi theo nhịp: bài toán → phương pháp → kết quả → vì sao đáng tin/đáng nghi → ứng dụng → giới hạn.
- Ưu tiên giải thích dễ hiểu, không dùng thuật ngữ mà không giải nghĩa.
- Mỗi voiceText mở bằng một câu ngắn 6-12 từ có thể dùng làm caption đáy.
""",
}

EDITING_PACE_GUIDES = {
    "standard": """

NHỊP DỰNG: STANDARD.
- Giữ nhịp cũ: mỗi voiceText khoảng 18-32 từ.
- Ưu tiên ít scene hơn, mỗi scene giải thích trọn một ý.
""",
    "dynamic": """

NHỊP DỰNG: DYNAMIC 3-5 GIÂY.
- Ưu tiên nhiều scene ngắn, mỗi voiceText khoảng 6-16 từ.
- Mỗi scene chỉ nêu một ý rõ ràng, tránh ghép 2-3 ý vào cùng scene.
- Câu đầu mỗi scene nên là một caption ngắn, dễ đọc trong 1 nhịp.
- Nếu bài có nhiều số liệu, tách từng số liệu quan trọng thành scene riêng.
- Tổng video nên gọn hơn nhịp cũ: tin nhanh khoảng 50-75 giây, explainer khoảng 70-100 giây.
""",
}


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

            # 2. Generate script via selected AI provider
            env = _read_engine_env()
            provider_hint = env.get("SCRIPT_AI_PROVIDER", "deepseek").strip().lower() or "deepseek"
            self.progress.emit(f"AI đang viết script… ({self._provider_label(provider_hint)} đang chọn)")
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
        """Use the selected script provider; fallback only when explicitly enabled."""
        errors = []
        engine_env = _read_engine_env()
        claude_key = (
            engine_env.get("CLAUDE_API_KEY", "").strip()
            or settings.get("claude_api_key", "").strip()
        )
        ds_key = (
            engine_env.get("DEEPSEEK_API_KEY", "").strip()
            or settings.get("ds_api_key", "").strip()
        )
        gemini_key = (
            engine_env.get("GEMINI_API_KEY", "").strip()
            or settings.get("gemini_api_key", "").strip()
        )

        selected = engine_env.get("SCRIPT_AI_PROVIDER", "deepseek").strip().lower()
        if selected not in ("deepseek", "gemini", "claude"):
            selected = "deepseek"
        fallback_enabled = (
            engine_env.get("SCRIPT_AI_FALLBACK", "false").strip().lower()
            in ("1", "true", "yes", "on")
        )
        order = (
            [selected] + [p for p in ("deepseek", "gemini", "claude") if p != selected]
            if fallback_enabled
            else [selected]
        )
        selected_label = self._provider_label(selected)
        for provider in order:
            try:
                if provider == "deepseek" and ds_key:
                    prefix = f"fallback từ {selected_label} → " if provider != selected else ""
                    self.progress.emit(f"AI đang viết script… ({prefix}DeepSeek · deepseek-chat)")
                    return self._generate_deepseek(article, ds_key, engine_env)
                if provider == "gemini" and gemini_key:
                    model = engine_env.get("GEMINI_TEXT_MODEL", "").strip() or "gemini-2.5-flash"
                    prefix = f"fallback từ {selected_label} → " if provider != selected else ""
                    self.progress.emit(f"AI đang viết script… ({prefix}Gemini · {model})")
                    return self._generate_gemini(
                        article,
                        gemini_key,
                        engine_env,
                        model,
                    )
                if provider == "claude" and claude_key:
                    prefix = f"fallback từ {selected_label} → " if provider != selected else ""
                    self.progress.emit(f"AI đang viết script… ({prefix}Claude · {self._claude_model(settings, engine_env)})")
                    return self._generate_claude(article, settings, claude_key, engine_env)

                if provider == selected:
                    raise ValueError(
                        f"Chưa có API key cho {self._provider_label(provider)} trong "
                        f"{ENGINE_ENV_LOCAL}."
                    )
            except Exception as e:
                label = {"deepseek": "DeepSeek", "gemini": "Gemini", "claude": "Claude"}.get(provider, provider)
                errors.append(f"{label}: {e}")
                if fallback_enabled:
                    self.progress.emit(f"{label} lỗi — thử provider khác…")
                else:
                    raise ValueError(
                        f"{label} lỗi, không fallback sang provider khác vì SCRIPT_AI_FALLBACK=false.\n{e}"
                    ) from e

        # ── Tất cả fail ──────────────────────────────────────────────────
        if not errors:
            raise ValueError(
                "Chưa có API key nào.\n"
                "Vào Settings → Auto Video → AI viết script để nhập key."
            )
        raise ValueError("Tất cả AI providers đều lỗi:\n" + "\n".join(errors))

    def _script_preset(self, engine_env: dict) -> str:
        preset = engine_env.get("AUTO_VIDEO_SCRIPT_PRESET", "ai_news_fast").strip().lower()
        return preset if preset in SCRIPT_PRESET_GUIDES else "ai_news_fast"

    def _provider_label(self, provider: str) -> str:
        return {"deepseek": "DeepSeek", "gemini": "Gemini", "claude": "Claude"}.get(provider, provider or "unknown")

    def _system_prompt(self, article: dict, engine_env: dict) -> str:
        channel = engine_env.get("TIKTOK_DISPLAY_NAME", "Hedra Central")
        preset = self._script_preset(engine_env)
        guide = SCRIPT_PRESET_GUIDES.get(preset, "")
        pace = engine_env.get("AUTO_VIDEO_EDITING_PACE", "dynamic").strip().lower()
        pace_guide = EDITING_PACE_GUIDES.get(pace, EDITING_PACE_GUIDES["dynamic"])
        return (
            SCRIPT_SYSTEM_PROMPT
            .replace("{{URL}}", article.get("url", ""))
            .replace("{{DOMAIN}}", article.get("domain", ""))
            .replace("{{CHANNEL}}", channel)
            + guide
            + pace_guide
        )

    def _claude_model(self, settings: dict, engine_env: dict) -> str:
        model = (
            engine_env.get("CLAUDE_MODEL", "").strip()
            or settings.get("claude_model", "").strip()
        )
        return RECOMMENDED_CLAUDE_MODEL if model in LEGACY_DEFAULT_CLAUDE_MODELS else model

    def _generate_claude(self, article: dict, settings: dict, api_key: str, engine_env: dict) -> dict:
        import anthropic
        system = self._system_prompt(article, engine_env)
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=self._claude_model(settings, engine_env),
            max_tokens=3072, system=system,
            messages=[{"role": "user", "content":
                f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video."}],
        )
        return self._parse_json(resp.content[0].text.strip())

    def _generate_deepseek(self, article: dict, api_key: str, engine_env: dict) -> dict:
        system = self._system_prompt(article, engine_env)
        payload = {
            "model": "deepseek-chat",
            "max_tokens": 3072,
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

    def _generate_gemini(self, article: dict, api_key: str, engine_env: dict, model: str) -> dict:
        system = self._system_prompt(article, engine_env)
        prompt  = (f"{system}\n\n"
                   f"Tiêu đề: {article['title']}\n\nNội dung:\n{article['text'][:4000]}\n\nTạo script video.")
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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

    # ── Zod field limits (must match script-schema.ts exactly) ──────────
    _ZOD_LIMITS = {
        # hook
        ("hook", "headline"):               40,
        ("hook", "subhead"):                40,
        # stat-hero
        ("stat-hero", "value"):             20,
        ("stat-hero", "label"):             40,
        ("stat-hero", "context"):           50,
        # feature-list
        ("feature-list", "title"):          40,
        # callout
        ("callout", "statement"):           80,
        ("callout", "tag"):                 20,
        # outro
        ("outro", "ctaTop"):                30,
        ("outro", "channelName"):           30,
        ("outro", "source"):                40,
        # comparison sides
        ("comparison", "left_label"):       30,
        ("comparison", "left_value"):       20,
        ("comparison", "right_label"):      30,
        ("comparison", "right_value"):      20,
    }
    _BULLET_MAX_LEN   = 50
    _BULLET_MAX_COUNT = 4

    _DANGLING_TAIL_WORDS = {
        "và", "của", "là", "từ", "vào", "khi", "để", "bị", "với", "theo",
        "không", "chưa", "đang", "sẽ", "có", "một", "này", "đó",
    }

    @staticmethod
    def _strip_vietnamese(text: str) -> str:
        import unicodedata
        normalized = unicodedata.normalize("NFD", text)
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return normalized.replace("đ", "d").replace("Đ", "D")

    def _trim_to_limit(self, value, limit: int, sentence: bool = False):
        """Trim overlong template text without leaving broken words like 'Yan không d'."""
        if not isinstance(value, str) or len(value) <= limit:
            return value

        cut = value[:limit].rstrip()

        if sentence:
            punctuation_positions = [cut.rfind(p) for p in ".!?:;…"]
            punctuation = max(punctuation_positions)
            if punctuation >= int(limit * 0.55):
                return cut[:punctuation + 1].strip()

        space = cut.rfind(" ")
        if space >= max(12, int(limit * 0.45)):
            cut = cut[:space].rstrip()

        cut = cut.rstrip(" ,;:-–—")
        words = cut.split()
        while words:
            tail = re.sub(r"[^a-z0-9]", "", self._strip_vietnamese(words[-1]).lower())
            if (len(tail) == 1 and tail.isalpha()) or tail in self._DANGLING_TAIL_WORDS:
                words.pop()
                continue
            break
        cut = " ".join(words).rstrip(" ,;:-–—")

        if sentence and cut and cut[-1] not in ".!?:;…":
            cut = f"{cut}."
        return cut[:limit].rstrip()

    def _truncate_scene(self, scene: dict) -> dict:
        """Trim templateData fields to Zod limits — rewrite-style trim, not hard cut."""
        td = scene.get("templateData", {})
        tpl = td.get("template", "")

        for (t, field), limit in self._ZOD_LIMITS.items():
            if t != tpl:
                continue
            sentence_field = tpl == "callout" and field == "statement"
            if field.startswith("left_") or field.startswith("right_"):
                side, key = field.split("_", 1)
                if side in td and isinstance(td[side], dict):
                    td[side][key] = self._trim_to_limit(td[side].get(key, ""), limit)
            else:
                if field in td:
                    td[field] = self._trim_to_limit(td[field], limit, sentence_field)

        # feature-list bullets
        if tpl == "feature-list" and "bullets" in td:
            bullets = td["bullets"]
            if isinstance(bullets, list):
                td["bullets"] = [self._trim_to_limit(b, self._BULLET_MAX_LEN) for b in bullets[:self._BULLET_MAX_COUNT]]

        scene["templateData"] = td
        return scene

    def _build_script(self, raw: dict, article: dict, settings: dict) -> dict:
        # Fix image: chỉ giữ nếu là https:// URL hợp lệ
        img = article.get("image")
        if img and not re.match(r'^https?://', img or ''):
            img = None

        # Fix voice from engine .env.local (single source of truth)
        env = _read_engine_env()
        provider = env.get("TTS_PROVIDER", "genmax").strip() or "genmax"
        voice_key_map = {
            "lucylab": "VIETNAMESE_VOICEID",
            "elevenlabs": "ELEVENLABS_VOICE_ID",
            "genmax": "GENMAX_VOICE_ID",
            "ai33": "AI33_VOICE_ID",
        }
        voice_key = voice_key_map.get(provider)
        if not voice_key:
            raise ValueError(
                f"TTS_PROVIDER không hợp lệ trong {ENGINE_ENV_LOCAL}: {provider}"
            )
        voice_id = env.get(voice_key, "").strip()
        if provider == "ai33" and not voice_id:
            voice_id = env.get("GENMAX_VOICE_ID", "").strip()
            voice_key = "AI33_VOICE_ID hoặc GENMAX_VOICE_ID"
        if not voice_id:
            raise ValueError(
                f"Thiếu {voice_key} trong {ENGINE_ENV_LOCAL}.\n"
                "Vào Settings → Auto Video để nhập cấu hình engine."
            )

        if "voice" in raw:
            raw["voice"]["provider"] = provider
            raw["voice"]["voiceId"] = voice_id
        else:
            raw["voice"] = {"provider": provider, "voiceId": voice_id, "speed": 1.0}

        # Fix metadata.source.image
        if "metadata" not in raw:
            raw["metadata"] = {}
        raw["metadata"]["channel"] = env.get("TIKTOK_DISPLAY_NAME", raw["metadata"].get("channel", "Hedra Central"))
        if "source" not in raw["metadata"]:
            raw["metadata"]["source"] = {}
        raw["metadata"]["source"]["image"] = img

        # Truncate tất cả fields về đúng Zod limits
        raw["scenes"] = [self._truncate_scene(s) for s in raw.get("scenes", [])]

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

    @staticmethod
    def _overall_progress(step: int, total: int, step_pct: int = 0) -> int:
        """Map engine step progress to an overall 0-100 value."""
        if total <= 0:
            return 0
        step_pct = max(0, min(100, step_pct))
        done_before = max(0, step - 1)
        return max(0, min(99, int(((done_before + step_pct / 100) / total) * 100)))

    @staticmethod
    def _hyperframes_pct(line: str) -> int | None:
        """Parse Hyperframes render progress, e.g. '44% Capturing frame 660/1531'."""
        m = re.search(r"(\d{1,3})%\s+.*?\bframe\s+\d+/\d+", line, re.I)
        if not m:
            return None
        return max(0, min(100, int(m.group(1))))

    @staticmethod
    def _shell_path() -> str:
        """Lấy PATH đầy đủ từ login shell — fix lỗi GUI app thiếu node/npx/ffmpeg."""
        import subprocess as _sp
        try:
            r = _sp.run(["/bin/zsh", "-l", "-c", "echo $PATH"],
                        capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        import os
        return os.environ.get("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin")

    @staticmethod
    def _media_duration(path: Path) -> float | None:
        import subprocess as _sp
        if not path.exists():
            return None
        try:
            r = _sp.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                return None
            return float((r.stdout or "").strip())
        except Exception:
            return None

    @classmethod
    def _partial_video_detail(cls, output_dir: Path) -> str:
        voice_sec = cls._media_duration(output_dir / "voice.mp3")
        candidates = sorted(output_dir.glob("video*.mp4"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        if not candidates:
            return ""
        best = candidates[0]
        video_sec = cls._media_duration(best)
        if video_sec is None:
            return ""
        if voice_sec and video_sec + 0.75 < voice_sec:
            return (
                f"Video render bị cụt: {video_sec:.2f}s / audio {voice_sec:.2f}s.\n"
                f"File partial: {best}"
            )
        if best.name != "video.mp4":
            return f"Render tạo file tạm nhưng chưa hoàn tất: {best} ({video_sec:.2f}s)"
        return ""

    def run(self):
        import os
        import subprocess
        tsx_bin = self.ENGINE_DIR / "node_modules" / ".bin" / "tsx"
        if not tsx_bin.exists():
            self.error.emit(
                f"Không tìm thấy tsx.\n"
                f"Chạy: cd /Users/admin/Auto-Create-Video && npm install"
            )
            return
        cmd = [str(tsx_bin), "src/cli.ts", self.script_path]

        # Toàn bộ config (TTS provider, API keys, voice ID...) đọc từ .env.local
        # của Auto-Create-Video — không inject thêm gì. Hedra Studio chỉ là UI wrapper.
        run_env = {**os.environ, "PATH": self._shell_path()}
        try:
            tail_lines: list[str] = []
            proc = subprocess.Popen(
                cmd, cwd=str(self.ENGINE_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=run_env,
            )
            for line in proc.stdout:
                if self._cancelled:
                    proc.terminate()
                    self.error.emit("Đã huỷ")
                    return
                line = line.rstrip()
                if line:
                    tail_lines.append(line)
                    if len(tail_lines) > 50:
                        tail_lines.pop(0)
                self.log_line.emit(line)
                m = re.search(r"\[(\d+)/(\d+)\]", line)
                if m:
                    n, t = int(m.group(1)), int(m.group(2))
                    self.progress.emit(self._overall_progress(n, t, 0))
                hf_pct = self._hyperframes_pct(line)
                if hf_pct is not None:
                    self.progress.emit(self._overall_progress(7, 8, hf_pct))

            proc.wait()
            if proc.returncode != 0:
                output_dir = Path(self.script_path).parent
                pieces = [f"Engine lỗi (exit {proc.returncode})"]
                partial = self._partial_video_detail(output_dir)
                if partial:
                    pieces.append(partial)
                if tail_lines:
                    pieces.append("Log cuối:\n" + "\n".join(tail_lines[-40:]))
                self.error.emit("\n\n".join(pieces))
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
