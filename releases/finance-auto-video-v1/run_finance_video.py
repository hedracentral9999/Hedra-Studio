#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEDRA_ROOT = ROOT.parents[1]
AUTO_VIDEO_ROOT = Path("/Users/admin/Auto-Create-Video")
ESCBASE_ZIP = HEDRA_ROOT / "template3.zip"
FINANCE_TEMPLATE = ROOT / "templates" / "finance-slide"
DEFAULT_OUT = HEDRA_ROOT / "output" / "final-renders"
VOICE_ID = "6adFm46eyy74snVn6YrT"
ESCBASE_DOCS_VERSION = "83.v3.86"


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def slugify(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:64] or "finance-video"


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env[key] = value
    return env


def make_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(load_env_file(AUTO_VIDEO_ROOT / ".env.local"))
    env["TTS_PROVIDER"] = "elevenlabs"
    env["ELEVENLABS_VOICE_ID"] = VOICE_ID
    env["ELEVENLABS_MODEL_ID"] = "eleven_v3"
    env["ELEVEN_V3_STYLE_ENABLED"] = "true"
    env.setdefault("TIKTOK_DISPLAY_NAME", "Hedra Central")
    env.setdefault("TIKTOK_HANDLE", "@hedracentral")
    return env


def copytree_clean(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def write_tts_config(escbase_root: Path) -> None:
    config_dir = escbase_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "elevenlabs": {
            "voice_id": VOICE_ID,
            "model_id": "eleven_v3",
            "output_format": "mp3_44100_128",
            "cooldown": 1.0,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True,
            },
        }
    }
    (config_dir / "tts.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replace_first(html: str, old: str, new: str) -> str:
    return html.replace(old, new, 1) if new else html


def htext(text: str, limit: int | None = None, *, upper: bool = False) -> str:
    value = fit(text, limit) if limit else re.sub(r"\s+", " ", str(text or "")).strip()
    if upper:
        value = value.upper()
    return escape(value, quote=True)


def fit(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].strip()
    return cut or text[:limit].strip()


def metric_parts(text: str, default_label: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return default_label, ""
    separators = ["~", ":", " đạt ", " còn ", " chạm "]
    for sep in separators:
        if sep in text:
            left, right = text.split(sep, 1)
            return fit(left.strip(), 14), fit((sep if sep in ["~", ":"] else "") + right.strip(), 18)
    parts = text.rsplit(" ", 2)
    if len(parts) >= 3 and any(ch.isdigit() for ch in " ".join(parts[-2:])):
        return fit(" ".join(parts[:-2]), 14), fit(" ".join(parts[-2:]), 18)
    return default_label, fit(text, 18)


def risk_parts(text: str, default_label: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if ":" in text:
        left, right = text.split(":", 1)
        return fit(left, 14), fit(right, 36)
    words = text.split()
    if len(words) > 4:
        return fit(" ".join(words[:2]), 14), fit(" ".join(words[2:]), 36)
    return default_label, fit(text, 36)


def strip_accents(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower()


def smart_chips(script: dict, hook_visual: dict) -> list[str]:
    raw = hook_visual.get("chips")
    chips = [fit(item, 14) for item in raw if str(item).strip()] if isinstance(raw, list) else []
    text = " ".join(
        [
            script.get("metadata", {}).get("title", ""),
            *[scene.get("voiceText", "") for scene in script.get("scenes", [])],
        ]
    )
    normalized = strip_accents(text)
    keyword_chips = [
        ("ETF", [" etf "]),
        ("BTC", ["bitcoin", " btc "]),
        ("AI", [" ai ", "chip", "nvidia", "micron", "spacex", "cong nghe"]),
        ("Fed", ["fed", "lai suat", "lam phat"]),
        ("Dầu", ["dau", "oil", "hormuz", "iran"]),
        ("Vĩ mô", ["vi mo", "suy thoai", "gdp"]),
        ("Altcoin", ["altcoin", "ethereum", "xrp", "solana"]),
        ("Dòng tiền", ["dong tien", "thanh khoan", "rut rong", "von hoa"]),
        ("Rủi ro", ["rui ro", "chien tranh", "dia chinh tri"]),
    ]
    for label, needles in keyword_chips:
        if len(chips) >= 4:
            break
        if label in chips:
            continue
        if any(needle in f" {normalized} " for needle in needles):
            chips.append(label)
    for fallback in ["BTC", "Dòng tiền", "Vĩ mô", "Rủi ro"]:
        if len(chips) >= 4:
            break
        if fallback not in chips:
            chips.append(fallback)
    return chips[:4]


def replace_chip(html: str, class_name: str, value: str) -> str:
    pattern = rf'(<span class="orbit-chip {re.escape(class_name)}">)(.*?)(</span>)'
    return re.sub(pattern, rf"\g<1>{fit(value, 14)}\g<3>", html, count=1)


def render_tokens(html: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        html = html.replace("{{" + key + "}}", value)
    leftovers = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", html)))
    if leftovers:
        raise ValueError(f"Unbound template tokens: {', '.join(leftovers)}")
    return html


def update_slide_html(project_dir: Path, script: dict) -> None:
    scenes = script["scenes"]
    visuals = [scene.get("visual") or {} for scene in scenes]
    html_path = project_dir / "index.html"
    html = html_path.read_text(encoding="utf-8")
    title = script.get("metadata", {}).get("title") or "Finance Video"
    source = script.get("metadata", {}).get("source", {}).get("domain") or "source"

    hook = visuals[0]
    body1 = visuals[1]
    body2 = visuals[2]
    body3 = visuals[3]
    body4 = visuals[4]
    outro = visuals[5]

    chips = smart_chips(script, hook)
    metric1_label, metric1_value = metric_parts(body1.get("metric1"), "BTC")
    metric2_label, metric2_value = metric_parts(body1.get("metric2"), "Vốn hóa")
    metric3_label, metric3_value = metric_parts(body1.get("metric3"), "Biến động")
    risk1_label, risk1_text = risk_parts(body4.get("risk1"), "Rủi ro 1")
    risk2_label, risk2_text = risk_parts(body4.get("risk2"), "Rủi ro 2")
    risk3_label, risk3_text = risk_parts(body4.get("risk3"), "Rủi ro 3")
    mapping = {
        "PAGE_TITLE": htext(title, 80),
        "META_DESCRIPTION": htext(f"Video tài chính ngắn từ {source}", 140),
        "CHIP_1": htext(chips[0], 12),
        "CHIP_2": htext(chips[1], 12),
        "CHIP_3": htext(chips[2], 12),
        "CHIP_4": htext(chips[3], 12),
        "HOOK_HEADLINE": htext(hook.get("headline") or title, 34, upper=True),
        "HOOK_SUBHEAD": htext(hook.get("subhead"), 58),
        "STAT_1": htext(chips[0], 18),
        "STAT_2": htext(chips[1], 18),
        "STAT_3": htext(chips[2], 18),
        "S2_TITLE": htext(body1.get("title"), 24, upper=True),
        "S2_HIGHLIGHT": htext(body1.get("highlight"), 22, upper=True),
        "M1_LABEL": htext(metric1_label, 14),
        "M1_VALUE": htext(metric1_value, 18),
        "M2_LABEL": htext(metric2_label, 14),
        "M2_VALUE": htext(metric2_value, 18),
        "M3_LABEL": htext(metric3_label, 14),
        "M3_VALUE": htext(metric3_value, 18),
        "S2_FLOW_LEFT": htext(body1.get("metric2"), 26),
        "S2_FLOW_RIGHT": htext(body1.get("metric3"), 26),
        "S3_TITLE": htext(body2.get("title"), 24, upper=True),
        "S3_HIGHLIGHT": htext(body2.get("highlight"), 26, upper=True),
        "S3_CORE": htext(body2.get("title"), 10),
        "S3_CALLOUT_SHORT": htext(body2.get("title"), 24),
        "S3_CALLOUT": htext(body2.get("callout"), 54),
        "S4_TITLE": htext(body3.get("title"), 24, upper=True),
        "S4_HIGHLIGHT": htext(body3.get("left"), 22, upper=True),
        "S4_LEFT": htext(body3.get("left"), 18),
        "S4_RIGHT": htext(body3.get("right"), 18),
        "S4_BULLET1_LABEL": htext(body3.get("bullet1"), 12),
        "S4_BULLET2_LABEL": htext(body3.get("bullet2"), 12),
        "S4_BULLET1": htext(body3.get("bullet1"), 28),
        "S4_BULLET2": htext(body3.get("bullet2"), 28),
        "S5_TITLE": htext(body4.get("title"), 24, upper=True),
        "RISK1_LABEL": htext(risk1_label, 14),
        "RISK1_TEXT": htext(risk1_text, 36),
        "RISK2_LABEL": htext(risk2_label, 14),
        "RISK2_TEXT": htext(risk2_text, 36),
        "RISK3_LABEL": htext(risk3_label, 14),
        "RISK3_TEXT": htext(risk3_text, 36),
        "S6_TITLE": htext(outro.get("title") or "KỊCH BẢN THEO DÕI", 24, upper=True),
        "S6_FOCUS": htext(outro.get("focus"), 30, upper=True),
        "S6_VERDICT": htext(outro.get("verdict"), 76),
        "SOURCE_LABEL": htext(f"Nguồn: {source}", 36),
    }
    html = render_tokens(html, mapping)
    html_path.write_text(html, encoding="utf-8")


def update_slide_scripts(project_dir: Path, script: dict) -> list[str]:
    lines = [str(scene.get("voiceText", "")).strip() for scene in script.get("scenes", [])]
    if len(lines) != 6 or any(not line for line in lines):
        raise ValueError("Expected exactly 6 non-empty voiceText lines for finance template")
    app_path = project_dir / "app.js"
    app = app_path.read_text(encoding="utf-8")
    payload = json.dumps(lines, ensure_ascii=False, indent=2)
    updated, count = re.subn(
        r"const slideScripts = \[[\s\S]*?\];",
        f"const slideScripts = {payload};",
        app,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Could not find slideScripts array in {app_path}")
    app_path.write_text(updated, encoding="utf-8")
    return lines


def qa_project(project_dir: Path, final_dir: Path, env: dict[str, str]) -> None:
    py = Path("/Users/admin/hedra-studio/venv/bin/python")
    if not py.exists():
        py = Path(sys.executable)
    run([str(py), str(ROOT / "qa_finance_project.py"), str(project_dir)], cwd=ROOT, env=env)
    shutil.copy2(project_dir / "qa-report.json", final_dir / "qa-report.json")


def download_image(url: str | None, out: Path) -> None:
    if not url:
        return
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            out.write_bytes(resp.read())
    except Exception as exc:
        print(f"Image download failed: {exc}")


def create_project(args: argparse.Namespace, env: dict[str, str]) -> tuple[Path, Path, dict]:
    stamp = datetime.now().strftime("%Y%m%d")
    scratch = HEDRA_ROOT / "output" / "pipeline-work" / f"{stamp}-{slugify(args.name or args.url)}"
    script_dir = scratch / "auto-script"
    script_dir.mkdir(parents=True, exist_ok=True)

    run([
        "./node_modules/.bin/tsx",
        str(ROOT / "auto-create-video" / "article-to-script.ts"),
        "--url",
        args.url,
        "--out-dir",
        str(script_dir),
    ], cwd=AUTO_VIDEO_ROOT, env=env)

    script = json.loads((script_dir / "script.json").read_text(encoding="utf-8"))
    title = args.name or script.get("metadata", {}).get("title") or "finance-video"
    final_dir = Path(args.out_dir).resolve() if args.out_dir else DEFAULT_OUT / f"{stamp}-{slugify(title)}-11labs"
    if final_dir.exists() and not args.force:
        raise FileExistsError(f"Output folder exists. Use --force or another --out-dir: {final_dir}")
    final_dir.mkdir(parents=True, exist_ok=True)

    zip_extract = final_dir / "escbase"
    if zip_extract.exists():
        shutil.rmtree(zip_extract)
    with zipfile.ZipFile(ESCBASE_ZIP) as zf:
        zf.extractall(zip_extract)
    escbase_root = zip_extract / "escbase_template_main"
    write_tts_config(escbase_root)

    project_name = "finance-video"
    project_dir = escbase_root / "slide" / project_name
    copytree_clean(FINANCE_TEMPLATE, project_dir)
    shutil.copy2(script_dir / "script-90s.txt", project_dir / "script-90s.txt")
    shutil.copy2(script_dir / "script.json", project_dir / "script.json")
    shutil.copy2(script_dir / "article.json", project_dir / "source" / "article.json")
    shutil.copy2(script_dir / "script-90s.txt", final_dir / "script-90s.txt")
    shutil.copy2(script_dir / "script.json", final_dir / "script.json")
    shutil.copy2(script_dir / "article.json", final_dir / "article.json")
    update_slide_html(project_dir, script)
    script_lines = update_slide_scripts(project_dir, script)
    (project_dir / "script-90s.txt").write_text("\n".join(script_lines) + "\n", encoding="utf-8")
    (final_dir / "script-90s.txt").write_text("\n".join(script_lines) + "\n", encoding="utf-8")
    download_image(script.get("metadata", {}).get("source", {}).get("image"), project_dir / "image.png")
    qa_project(project_dir, final_dir, env)
    return final_dir, project_dir, script


def render_project(final_dir: Path, project_dir: Path, env: dict[str, str], *, skip_validation: bool = False) -> None:
    escbase_root = project_dir.parents[1]
    rel_project = f"slide/{project_dir.name}"
    py = Path("/Users/admin/hedra-studio/venv/bin/python")
    if not py.exists():
        py = Path(sys.executable)

    if not skip_validation:
        run([str(py), "validate_slide.py", rel_project, "--semantic-report"], cwd=escbase_root, env=env)
    run([str(py), "generate_tts.py", rel_project, "--engine", "elevenlabs", "--force"], cwd=escbase_root, env=env)
    run([str(py), "auto_render.py", rel_project, "--output-dir", f"{rel_project}/output", "--size", "540x960"], cwd=escbase_root, env=env)

    output_dir = project_dir / "output"
    fullhd = output_dir / "final_video_fullhd.mp4"
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(output_dir / "final_video.mp4"),
        "-vf",
        "scale=1080:1920:flags=lanczos",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "veryfast",
        "-c:a",
        "copy",
        str(fullhd),
    ], cwd=escbase_root, env=env)
    run(["ffmpeg", "-y", "-ss", "00:00:08", "-i", str(fullhd), "-frames:v", "1", "-update", "1", str(output_dir / "preview.png")], cwd=escbase_root, env=env)

    shutil.copy2(fullhd, final_dir / "video_fullhd.mp4")
    shutil.copy2(output_dir / "voiceover_concat.mp3", final_dir / "voice_11labs_nhatphong.mp3")
    shutil.copy2(output_dir / "preview.png", final_dir / "preview.png")
    shutil.copy2(project_dir / "script-90s.txt", final_dir / "script-90s.txt")
    shutil.copy2(project_dir / "script.json", final_dir / "script.json")
    shutil.copy2(project_dir / "source" / "article.json", final_dir / "article.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="URL -> Auto-Create script -> isolated Escbase render.")
    parser.add_argument("url")
    parser.add_argument("--name", help="Optional folder/title slug seed.")
    parser.add_argument("--out-dir", help="Exact final output folder.")
    parser.add_argument("--force", action="store_true", help="Overwrite output folder if it already exists.")
    parser.add_argument("--script-only", action="store_true", help="Stop after creating script and Escbase project.")
    parser.add_argument("--skip-validation", action="store_true", help="Skip Escbase validate_slide.py before render.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = make_env()
    final_dir, project_dir, script = create_project(args, env)
    if not args.script_only:
        render_project(final_dir, project_dir, env, skip_validation=args.skip_validation)
    manifest = {
        "version": "finance-auto-video-v1",
        "escbase_docs_version": ESCBASE_DOCS_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "url": args.url,
        "title": script.get("metadata", {}).get("title"),
        "voice": {"provider": "elevenlabs", "model": "eleven_v3", "voice_id": VOICE_ID, "name": "Nhật Phong"},
        "final_dir": str(final_dir),
        "project_dir": str(project_dir),
    }
    (final_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nDONE")
    print(f"Folder: {final_dir}")
    if args.script_only:
        print(f"Script: {final_dir / 'script.json'}")
        print(f"Escbase project: {project_dir}")
    else:
        print(f"Video:  {final_dir / 'video_fullhd.mp4'}")
        print(f"Voice:  {final_dir / 'voice_11labs_nhatphong.mp3'}")


if __name__ == "__main__":
    main()
