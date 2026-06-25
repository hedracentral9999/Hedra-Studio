"""
title_gen.py — Chuyên gia sinh tiêu đề + hashtag.
1 lần gọi DeepSeek V4 Flash: tiêu đề, hashtag, caption, hiểu nội dung.
Prompt từ prompts/title_gen.txt.
"""

import json
import re
from pathlib import Path
import requests
from .core import log, cost_str
from .config import DS_API_URL, DS_MODEL


SYSTEM_PROMPT = (
    "Bạn là strategist thumbnail TikTok affiliate tiếng Việt. "
    "Chọn hook chính giúp người dừng lại và có nhu cầu mua/nhắn hỏi. "
    "QUAN TRỌNG: Trả về CHỈ JSON hợp lệ, không markdown, không giải thích, "
    "không suy nghĩ. Output phải bắt đầu bằng {{ và kết thúc bằng }}."
)


def load_prompt_template() -> str:
    """Đọc prompt template từ file."""
    prompt_path = Path(__file__).parent / "prompts" / "title_gen.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    # Fallback tối giản
    return """Sinh 3 tiêu đề thumbnail TikTok affiliate.
Trả JSON: {{"titles":[{{"title":"...","angle":"bán hàng"}},{{"title":"...","angle":"pain"}},{{"title":"...","angle":"bằng chứng"}}],"upload_title":"...","hashtags":["#..."]}}

Tên file: {source_stem}
Transcript: {full_transcript}"""


def _parse_json(raw: str) -> dict:
    """Parse JSON từ DeepSeek, xử lý reasoning text + JSON lẫn lộn."""
    raw = raw.strip()
    last_brace = raw.rfind("{")
    if last_brace >= 0:
        candidate = raw[last_brace:]
        try:
            json.loads(candidate)
            raw = candidate
        except Exception:
            pass
    if raw.startswith("```"):
        raw = raw.split("```")[1].removeprefix("json").strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            titles = []
            for item in data.get("titles", []):
                if isinstance(item, dict):
                    t = item.get("title", "")
                else:
                    t = str(item)
                if t.strip():
                    titles.append(t.strip())
            return {
                "titles": titles,
                "upload_title": str(data.get("upload_title", "")).strip(),
                "hashtags": data.get("hashtags", []) if isinstance(data.get("hashtags"), list) else [],
                "main_hook": str(data.get("main_hook", "")).strip(),
                "caption_full": str(data.get("caption_full", "")).strip(),
                "caption_short": str(data.get("caption_short", "")).strip(),
            }
        if isinstance(data, list):
            return {"titles": [str(t).strip() for t in data if str(t).strip()], "hashtags": []}
    except Exception:
        pass
    matches = re.findall(r'"title"\s*:\s*"([^"]+)"', raw, flags=re.IGNORECASE)
    if matches:
        return {"titles": [m.strip() for m in matches if m.strip()], "hashtags": []}
    return {"titles": [], "hashtags": []}


def _pick_best(titles: list[str], source_stem: str, segments: list[dict]) -> str:
    """Chọn title tốt nhất từ danh sách ứng viên."""
    if not titles:
        return ""
    context = " ".join(s.get("text", "") for s in (segments or [])[:20]).upper()
    valid = []
    for t in titles:
        t = t.strip()
        if not t or len(t) < 4:
            continue
        if re.match(r"^(DJI|IMG|VID|MOV|DSC|GOPRO|GH\d+)[_\d]", t, re.IGNORECASE):
            continue
        if t not in valid:
            valid.append(t)
    if not valid:
        return ""

    def score(t: str) -> tuple:
        w = len(t.split())
        readability = 10 if 4 <= w <= 9 else (2 if w <= 3 else -5)
        return (readability, -abs(w - 7))
    return max(valid, key=score)


def _fallback(source_stem: str, segments: list[dict]) -> tuple[str, str, list]:
    """Fallback title khi AI lỗi."""
    context = " ".join(s.get("text", "") for s in (segments or [])[:30]).upper()
    if "SAMSUNG DEX" in context or "SAMSUNGDEX" in context:
        if "4K" in context:
            return "SETUP SAMSUNG DEX NHẬN 4K", "rule", []
        return "SETUP SAMSUNG DEX DỄ HƠN", "rule", []
    if "THOÁT" in context and "DEX" in context and "GAME" in context:
        return "THOÁT DEX ĐỂ ĐĂNG NHẬP GAME", "rule", []
    if "GAME" in context and ("BỊ CHẶN" in context or "BI CHAN" in context):
        return "ĐĂNG NHẬP GAME BỊ CHẶN", "rule", []
    if "OSMO NANO" in context or "OSMO ACTION" in context or "POCKET 3" in context:
        if "DÁN" in context or "BẢO VỆ" in context:
            return "DÁN BẢO VỆ DJI OSMO NANO", "rule", []
        return "DJI OSMO NANO CÓ ĐÁNG MUA", "rule", []
    if "HUB" in context or "HDMI" in context:
        if "MACBOOK" in context:
            return "HUB TYPE-C CHO MACBOOK XUẤT 4K", "rule", []
        if "4K" in context:
            return "HUB USB-C XUẤT 4K SIÊU MƯỢT", "rule", []
    if "ĐÈN LED" in context or "QUẠT LED" in context:
        return "ĐÈN LED TRANG TRÍ GÓC SETUP", "rule", []
    words = context.split()[:10]
    return " ".join(words) if words else source_stem, "fallback", []


def generate(segments: list[dict], source_stem: str, api_key: str,
             cleaned_transcript: str = "",
             recent_titles: list[str] | None = None) -> dict:
    """
    1 lần gọi DeepSeek: sinh tiêu đề + hashtag + caption.
    Returns: {"title": str, "brief": str, "hashtags": list, "caption": str}
    """
    if not segments and not cleaned_transcript:
        return {"title": source_stem, "brief": "", "hashtags": [], "caption": ""}

    if cleaned_transcript:
        clean_lines = [re.sub(r"^\[\d+\.\d+s\]\s*", "", line) for line in cleaned_transcript.split("\n")]
        full = "\n".join(clean_lines)[:9000]
        early = "\n".join(clean_lines[:8])
    else:
        full = "\n".join(s.get("text", "") for s in segments[:140])
        early = "\n".join(s.get("text", "") for s in segments[:8])

    dup_block = ""
    if recent_titles:
        dup_list = "\n".join(f"- {t}" for t in recent_titles[:40])
        dup_block = f"""
QUAN TRỌNG — TRÁNH TRÙNG TIÊU ĐỀ:
Dưới đây là các tiêu đề đã dùng hôm nay. Tiêu đề mới PHẢI khác biệt rõ ràng
(không chỉ đảo từ, không chỉ thay 1-2 từ, không cùng cấu trúc câu).
Nếu transcript na ná video cũ, hãy chọn góc nhìn KHÁC (use-case khác, pain khác, hook khác).

Tiêu đề đã dùng:
{dup_list}
"""

    template = load_prompt_template()
    user_prompt = template.format(
        source_stem=source_stem,
        dup_block=dup_block,
        early_transcript=early[:2500],
        full_transcript=full[:9000],
    )

    try:
        resp = requests.post(
            DS_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",  # V3 ổn định hơn cho title gen
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.55,
                "max_tokens": 1200,
            },
            timeout=35,
        )
        resp.raise_for_status()
        body = resp.json()
        msg = body["choices"][0]["message"]
        content_raw = msg.get("content", "").strip()
        reasoning = msg.get("reasoning_content", "").strip()

        # DeepSeek V4 reasoning leak detection
        looks_like_reasoning = content_raw and len(content_raw) > 200 and (
            content_raw.startswith("Chúng ta") or content_raw.startswith("Đọc") or
            content_raw.startswith("Tôi") or content_raw.startswith("We") or
            content_raw.startswith("Let") or content_raw.startswith("I ") or
            content_raw.startswith("First") or "reasoning" in content_raw[:200].lower()
        )

        if looks_like_reasoning and reasoning:
            raw = reasoning
        elif content_raw:
            raw = content_raw
        elif reasoning:
            raw = reasoning
        else:
            raw = ""

        parsed = _parse_json(raw)
        candidates = parsed.get("titles", [])
        best = _pick_best(candidates, source_stem, segments)
        if not best and parsed.get("upload_title"):
            best = parsed["upload_title"]
        if not best and candidates:
            best = candidates[0]

        log(f"DeepSeek OK · {cost_str(body.get('usage', {}))}")
        return {
            "title": best or source_stem,
            "brief": parsed.get("main_hook", ""),
            "hashtags": parsed.get("hashtags", []),
            "caption": parsed.get("caption_full", parsed.get("caption_short", "")),
        }
    except Exception as e:
        log(f"DeepSeek lỗi: {e}")
        title, _, _ = _fallback(source_stem, segments)
        return {"title": title or source_stem, "brief": "", "hashtags": [], "caption": ""}
