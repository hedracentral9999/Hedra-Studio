"""
skills.py — Hệ thống skill: LUT, Noise, Render, Thumbnail.

Mỗi skill là 1 file JSON. Thêm skill mới = thêm file JSON, không cần sửa Python.

Usage:
  from .skills import list_lut_skills, load_lut_skill, load_noise_skill
  path = load_lut_skill("dji_dlog_m_to_rec709")    # → "/path/to/lut.cube"
  filter_str = load_noise_skill("voice_clean")       # → "highpass=f=40,..."
  names = list_lut_skills()                          # → ["dji_dlog_m_to_rec709", ...]
"""

import json
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent / "skills"


def _resolve_path(raw: str) -> str:
    """Expand ~ trong đường dẫn, trả về absolute path nếu tồn tại."""
    if not raw:
        return ""
    p = Path(raw).expanduser().resolve()
    return str(p) if p.exists() else ""


# ── LUT Skills ───────────────────────────────────────────────────────────────

def _lut_dir() -> Path:
    return _SKILLS_DIR / "lut"


def list_lut_skills() -> list[str]:
    """Liệt kê tất cả LUT skill đang có."""
    d = _lut_dir()
    if not d.exists():
        return []
    return sorted(
        f.stem for f in d.glob("*.json")
        if f.is_file() and not f.name.startswith("_")
    )


def load_lut_skill(name: str) -> dict:
    """
    Load LUT skill theo tên (không cần .json).
    Returns: {"name": str, "path": str (resolved), "label": str, "description": str}
    Trả về path="" nếu skill là "no_lut" hoặc không tìm thấy file.
    """
    default = {"name": name, "path": "", "label": name, "description": ""}

    if name in ("no_lut", "none", ""):
        default["label"] = "Không LUT"
        return default

    file_path = _lut_dir() / f"{name}.json"
    if not file_path.exists():
        return default

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default

    # Resolve path: thử path chính → fallback_paths
    raw = data.get("path", "")
    resolved = _resolve_path(raw)
    if not resolved:
        for fb in data.get("fallback_paths", []):
            resolved = _resolve_path(fb)
            if resolved:
                break

    return {
        "name": data.get("name", name),
        "path": resolved,
        "label": data.get("label", name),
        "description": data.get("description", ""),
    }


# ── Noise Skills ─────────────────────────────────────────────────────────────

def _noise_dir() -> Path:
    return _SKILLS_DIR / "noise"


def list_noise_skills() -> list[str]:
    """Liệt kê tất cả noise filter skill."""
    d = _noise_dir()
    if not d.exists():
        return []
    return sorted(
        f.stem for f in d.glob("*.json")
        if f.is_file() and not f.name.startswith("_")
    )


def load_noise_skill(name: str) -> dict:
    """
    Load noise filter skill theo tên.
    Returns: {"name": str, "filter": str, "label": str, "description": str}
    """
    default = {"name": name, "filter": "", "label": name, "description": ""}

    if name in ("no_noise", "none", ""):
        default["label"] = "Không lọc"
        return default

    file_path = _noise_dir() / f"{name}.json"
    if not file_path.exists():
        return default

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default

    return {
        "name": data.get("name", name),
        "filter": data.get("filter", ""),
        "label": data.get("label", name),
        "description": data.get("description", ""),
    }


# ── Render Skills ────────────────────────────────────────────────────────────

def _render_dir() -> Path:
    return _SKILLS_DIR / "render"


def list_render_skills() -> list[str]:
    d = _render_dir()
    if not d.exists():
        return []
    return sorted(f.stem for f in d.glob("*.json") if f.is_file() and not f.name.startswith("_"))


def load_render_skill(name: str) -> dict:
    """
    Load render skill theo tên.
    Returns: {"name", "label", "description", "video_enhance", "encoder_vt", "encoder_x264"}
    """
    default = {"name": name, "label": name, "description": "", "video_enhance": "", "encoder_vt": [], "encoder_x264": []}
    file_path = _render_dir() / f"{name}.json"
    if not file_path.exists():
        return default
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return {
        "name": data.get("name", name),
        "label": data.get("label", name),
        "description": data.get("description", ""),
        "video_enhance": data.get("video_enhance", ""),
        "encoder_vt": data.get("encoder_vt", []),
        "encoder_x264": data.get("encoder_x264", []),
    }


# ── Thumbnail Skills ─────────────────────────────────────────────────────────

def _thumbnail_dir() -> Path:
    return _SKILLS_DIR / "thumbnail"


def list_thumbnail_skills() -> list[str]:
    d = _thumbnail_dir()
    if not d.exists():
        return []
    return sorted(f.stem for f in d.glob("*.json") if f.is_file() and not f.name.startswith("_"))


def load_thumbnail_skill(name: str) -> dict:
    file_path = _thumbnail_dir() / f"{name}.json"
    default = {"name": name, "label": name, "font": "", "color_top": "#20ff28", "color_bottom": "#fff12b",
               "color_stroke": "#050505", "overlay_alpha": 36, "safe_top": 330, "safe_bottom": 1240,
               "safe_margin": 54, "font_sizes": {"1": 166, "2": 150, "3": 134, "4": 116, "5": 100}}
    if not file_path.exists():
        return default
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return {
        "name": data.get("name", name),
        "label": data.get("label", name),
        "font": data.get("font", default["font"]),
        "color_top": data.get("color_top", default["color_top"]),
        "color_bottom": data.get("color_bottom", default["color_bottom"]),
        "color_stroke": data.get("color_stroke", default["color_stroke"]),
        "overlay_alpha": data.get("overlay_alpha", default["overlay_alpha"]),
        "safe_top": data.get("safe_top", default["safe_top"]),
        "safe_bottom": data.get("safe_bottom", default["safe_bottom"]),
        "safe_margin": data.get("safe_margin", default["safe_margin"]),
        "font_sizes": data.get("font_sizes", default["font_sizes"]),
        "description": data.get("description", ""),
    }


# ── Printer ──────────────────────────────────────────────────────────────────

def print_skills():
    """In danh sách skill ra terminal (dùng cho --list-skills)."""
    print("\n🎨 LUT Skills:")
    for name in list_lut_skills():
        s = load_lut_skill(name)
        status = "✅" if s["path"] else "⚠️ (file LUT không tìm thấy)"
        print(f"  {s['name']:30s} {s['label']:30s} {status}")

    print("\n🔊 Noise Skills:")
    for name in list_noise_skills():
        s = load_noise_skill(name)
        has_filter = "✅" if s["filter"] else "—"
        print(f"  {s['name']:30s} {s['label']:30s} {has_filter}")

    print("\n🎬 Render Skills:")
    for name in list_render_skills():
        s = load_render_skill(name)
        has_x264 = "✅ x264" if s["encoder_x264"] else "—"
        print(f"  {s['name']:30s} {s['label']:30s} {has_x264}")

    print("\n🖼️ Thumbnail Skills:")
    for name in list_thumbnail_skills():
        s = load_thumbnail_skill(name)
        print(f"  {s['name']:30s} {s['label']:30s} {s['color_top']} / {s['color_bottom']}")
    print()
