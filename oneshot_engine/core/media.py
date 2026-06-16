"""
core/media.py — Xử lý text cho media: slugify, clean title, chia dòng thumbnail.
"""

import re
import unicodedata


def slugify(text: str) -> str:
    """Chuyển tiếng Việt → ASCII slug, dùng đặt tên file."""
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:60].strip("_") or "thumbnail"


def video_filename(title: str) -> str:
    """Tạo tên file video sạch: title case + fix thuật ngữ."""
    from ..config import TRAILING_BAD

    text = title.strip().upper()
    parts = text.split()
    while parts and parts[-1] in TRAILING_BAD:
        parts.pop()
    text = " ".join(parts)[:200]
    if not text:
        text = "Video"
    text = text.title()

    keep_upper = {
        "Hdmi": "HDMI", "Usb": "USB", "2Tb": "2TB", "4G": "4G", "4K120": "4K120",
        "Hub": "HUB", "Ch": "CH", "Qr": "QR", "Vietqr": "VietQR",
        "Momo": "MoMo", "MomO": "MoMo", "Zalopay": "ZaloPay", "Shopeepay": "ShopeePay",
        "Ios": "iOS", "Iphone": "iPhone",
        "4K": "4K", "120Hz": "120Hz", "120hz": "120Hz",
        "60fps": "60FPS", "60Fps": "60FPS",
    }
    for src, repl in keep_upper.items():
        text = re.sub(rf"\b{re.escape(src)}\b", repl, text)

    canonical = (
        (r"\bSamsung\s+Dex\b", "Samsung Dex"),
        (r"\bBox\s+Samsung\s+Dex\b", "Box Samsung Dex"),
        (r"\bSIM\s+4g\b", "SIM 4G"), (r"\bSim\s+4G\b", "SIM 4G"),
        (r"\bLoa\s+MoMo\b", "Loa MoMo"),
        (r"\bHDMI\s+2\.1\b", "HDMI 2.1"), (r"\bHDMI\s+2\.0\b", "HDMI 2.0"),
        (r"\bUSB\s*-\s*C\b", "USB-C"), (r"\bType\s*-\s*C\b", "Type-C"),
        (r"\bCH\s+Play\b", "CH Play"),
    )
    for pat, repl in canonical:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    text = re.sub(r"[/:*?\"<>|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:96].rstrip() or "Video"


def clean_title(text: str) -> str:
    """Làm sạch title: bỏ trailing filler, uppercase."""
    from ..config import TRAILING_BAD

    text = text.strip().upper()
    parts = text.split()
    while parts and parts[-1] in TRAILING_BAD:
        parts.pop()
    text = " ".join(parts)

    prefixes = (
        "CAPTION FULL ", "CAPTION ", "HASHTAGS ", "HASHTAG ",
        "LÀM SAO ĐỂ ", "CÁCH ĐỂ ", "HƯỚNG DẪN ",
        "ANH EM NÈ ", "CÁC BẠN ",
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip()[:200]


def split_lines(title: str, max_lines: int = 3) -> list[str]:
    """Chia title thành các dòng cho thumbnail."""
    title = title.strip().upper()
    parts = re.split(r"\s{2,}|[,;:.-]\s*", title)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= max_lines:
        return parts
    words = title.split()
    n = len(words)
    per_line = max(1, n // max_lines)
    lines = []
    i = 0
    for _ in range(max_lines - 1):
        end = min(i + per_line, n - (max_lines - len(lines) - 1))
        lines.append(" ".join(words[i:end]))
        i = end
    if i < n:
        lines.append(" ".join(words[i:]))
    return [l for l in lines if l]


def thumbnail_line_candidates(title: str) -> list[list[str]]:
    """Tạo các phương án chia dòng cho thumbnail (2, 3, 4 dòng)."""
    words = title.split()
    n = len(words)
    if n <= 3:
        return [[title]]
    candidates = []
    for num_lines in (2, 3, 4):
        if num_lines > n:
            break
        per = max(1, n // num_lines)
        lines = []
        i = 0
        for _ in range(num_lines - 1):
            end = min(i + per, n - (num_lines - len(lines) - 1))
            lines.append(" ".join(words[i:end]))
            i = end
        if i < n:
            lines.append(" ".join(words[i:]))
        candidates.append([l for l in lines if l])
    return candidates if candidates else [split_lines(title, 3)]
