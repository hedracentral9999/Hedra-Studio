"""
simple_pipeline.py — Hedra Studio UI compatibility.
"""


def is_simple_pipeline(settings) -> bool:
    return True


def build_simple_options(settings: dict, extra: dict = None) -> dict:
    options = {
        "preset": str(settings.get("one_shot_preset") or "capcut"),
        "noise_skill": str(settings.get("one_shot_noise_skill") or ""),
        "lut_skill": str(settings.get("one_shot_lut_skill") or ""),
        "lut_intensity": float(settings.get("one_shot_lut_intensity") or 1.0),
        "thumb_style": str(settings.get("one_shot_thumb_style") or "boxphonefarm"),
        "cover": bool(settings.get("one_shot_cover", True)),
    }
    if extra:
        options.update(extra)
    return options
