"""
thumbnail.py — Chuyên gia vẽ thumbnail.
Style load từ skills/thumbnail/ JSON — đổi màu/font/safe zone không cần sửa code.
Mặc định: BoxPhoneFarm (xanh/vàng, DT Phudu Black).
"""

import unicodedata
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .core import clean_title, thumbnail_line_candidates
from .config import THUMB_W, THUMB_H, FONT_CANDIDATES
from .skills import load_thumbnail_skill


def _find_font(skill_font: str = "") -> str:
    """Tìm font từ skill hoặc fallback."""
    if skill_font:
        for p in FONT_CANDIDATES:
            if p.exists() and p.name == skill_font:
                return str(p)
    for p in FONT_CANDIDATES:
        if p.exists():
            return str(p)
    return "/System/Library/Fonts/Helvetica.ttc"


def _resolve_style(style: str) -> dict:
    """Load thumbnail skill, fallback boxphonefarm."""
    sk = load_thumbnail_skill(style)
    if not sk.get("color_top"):
        sk = load_thumbnail_skill("boxphonefarm")
    return sk


def draw(frame_path: Path, out_path: Path, title: str, style: str = "boxphonefarm"):
    sk = _resolve_style(style)
    margin = sk["safe_margin"]
    safe_left, safe_top = margin, sk["safe_top"]
    safe_right, safe_bottom = THUMB_W - margin, sk["safe_bottom"]
    color_top, color_bottom = sk["color_top"], sk["color_bottom"]
    color_stroke = sk["color_stroke"]
    overlay_alpha = sk["overlay_alpha"]
    font_sizes = {int(k): v for k, v in sk["font_sizes"].items()}

    src = Image.open(frame_path)
    src = ImageOps.exif_transpose(src).convert("RGB")
    if src.width <= 0 or src.height <= 0:
        raise RuntimeError(f"Không đọc được frame: {frame_path}")

    canvas = ImageOps.fit(src, (THUMB_W, THUMB_H), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)).convert("RGBA")
    shade = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, overlay_alpha))
    canvas = Image.alpha_composite(canvas, shade)
    draw_ctx = ImageDraw.Draw(canvas)

    safe_w = safe_right - safe_left
    safe_h = safe_bottom - safe_top

    font_path = _find_font(sk.get("font", ""))
    title_clean = unicodedata.normalize("NFC", clean_title(title))

    candidates = thumbnail_line_candidates(title_clean)
    if not candidates:
        from .core.media import split_lines
        candidates = [split_lines(title_clean, 3)]

    caps = font_sizes
    best_layout = None

    for candidate in candidates:
        cap_size = caps.get(len(candidate), 106)
        size = cap_size
        stroke = max(6, int(size * 0.075))
        font = ImageFont.truetype(font_path, size)
        line_gap = max(10, int(size * 0.075))

        bboxes = [draw_ctx.textbbox((0, 0), unicodedata.normalize("NFC", ln), font=font, stroke_width=stroke) for ln in candidate]
        widths = [b[2] - b[0] for b in bboxes]
        heights = [b[3] - b[1] for b in bboxes]
        line_slot_h = max(max(heights or [0]), int(size * 0.82) + stroke * 2)
        total_h = line_slot_h * len(candidate) + line_gap * max(0, len(candidate) - 1)
        text_w = safe_w - stroke * 2

        while size > 54 and (max(widths or [0]) > text_w or total_h > safe_h):
            size -= 2
            stroke = max(6, int(size * 0.075))
            font = ImageFont.truetype(font_path, size)
            line_gap = max(10, int(size * 0.075))
            bboxes = [draw_ctx.textbbox((0, 0), unicodedata.normalize("NFC", ln), font=font, stroke_width=stroke) for ln in candidate]
            widths = [b[2] - b[0] for b in bboxes]
            heights = [b[3] - b[1] for b in bboxes]
            line_slot_h = max(max(heights or [0]), int(size * 0.82) + stroke * 2)
            total_h = line_slot_h * len(candidate) + line_gap * max(0, len(candidate) - 1)

        layout = {"lines": candidate, "font": font, "stroke": stroke, "size": size,
                  "line_gap": line_gap, "line_slot_h": line_slot_h, "total_h": total_h,
                  "widths": widths, "boxes": bboxes, "score": size * 10}
        if best_layout is None or layout["score"] > best_layout["score"]:
            best_layout = layout

    if best_layout is None:
        font = ImageFont.truetype(font_path, 122)
        bx = draw_ctx.textbbox((0, 0), "BOX PHONE", font=font, stroke_width=8)
        best_layout = {"lines": ["BOX PHONE"], "font": font, "stroke": 8, "size": 122,
                       "line_gap": 10, "line_slot_h": bx[3] - bx[1], "total_h": bx[3] - bx[1],
                       "widths": [bx[2] - bx[0]], "boxes": [bx]}

    lines = best_layout["lines"]
    font = best_layout["font"]
    stroke_px = best_layout["stroke"]
    line_gap = best_layout["line_gap"]
    line_slot_h = best_layout["line_slot_h"]
    total_h = best_layout["total_h"]

    y0 = int(safe_top + max(0, (safe_h - total_h) * 0.56))
    split_at = max(1, (len(lines) + 1) // 2)

    y_cursor = y0
    for i, line in enumerate(lines):
        color = color_top if i < split_at else color_bottom
        line_nfc = unicodedata.normalize("NFC", line)
        bbox = draw_ctx.textbbox((0, 0), line_nfc, font=font, stroke_width=stroke_px)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x_text = int((THUMB_W - line_w) / 2)
        x_text = max(safe_left, min(x_text, safe_right - line_w))
        y_text = int(y_cursor + max(0, (line_slot_h - line_h) / 2)) - int(bbox[1])
        draw_ctx.text((x_text, y_text), line_nfc, font=font, fill=color,
                      stroke_width=stroke_px, stroke_fill=color_stroke)
        y_cursor += line_slot_h + line_gap

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(str(out_path), "PNG", quality=96)
