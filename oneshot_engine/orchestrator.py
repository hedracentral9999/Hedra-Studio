"""
orchestrator.py — Nhạc trưởng điều phối 7 bước pipeline.
audio → transcribe → fix → title → thumbnail → render → done.
"""

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from .core import (
    log, clean_title, slugify, video_filename,
    ffprobe_duration, make_job_dir, output_root, resolve_lut,
    recent_titles, api_key_from_settings,
)
from .audio import extract_audio, check_audio
from .transcribe import transcribe
from .transcript_fix import fix_regex, ai_fix
from .title_gen import generate as generate_title
from .thumbnail import draw as draw_thumbnail
from .render import render as render_video, extract_frame, last_render_metrics
from .skills import load_lut_skill, load_noise_skill


# ── Pipeline Tracker ─────────────────────────────────────────────────────────

_W = 50  # line width

class PipelineTracker:
    """Apple-style progress: clean, minimal, airy."""

    def __init__(self, source_name: str, duration: float, flags: dict):
        self.source_name = source_name
        self.duration = duration
        self.flags = flags
        self.t0 = time.perf_counter()
        self.steps_done: list[dict] = []
        self._step_t0 = 0.0
        self.step_defs = [
            "Extract audio + transcribe",
            "AI clean transcript",
            "AI generate title",
            "Draw thumbnail",
            "Render video",
            "Save report",
            "Embed cover + move to done/",
        ]

    def print_header(self):
        flags_str = "  ·  ".join(f"{'✓' if v else '—'} {k}" for k, v in self.flags.items())
        print(f"\n{'─' * _W}")
        print(f"  {self.source_name}")
        print(f"  {self.duration:.0f}s  ·  {flags_str}")
        print(f"{'─' * _W}\n")

    def start_step(self, step_idx: int):
        self._current_step = step_idx
        self._step_t0 = time.perf_counter()

    def _emit(self, icon: str, detail: str):
        elapsed = time.perf_counter() - self._step_t0
        name = self.step_defs[self._current_step]
        self.steps_done.append({"name": name, "status": icon, "elapsed": elapsed, "detail": detail})
        d = f"  ·  {detail}" if detail else ""
        print(f"  {icon}  {name:<34s} {elapsed:>5.1f}s{d}")

    def step_ok(self, detail: str = ""):
        self._emit("◉", detail)

    def step_warn(self, detail: str = ""):
        self._emit("◌", detail)

    def step_fail(self, detail: str = "", error_context: str = "", tried: str = ""):
        self._emit("✕", detail)
        if error_context:
            for line in error_context.strip().split("\n"):
                print(f"     {line.strip()}")
        if tried:
            print(f"     Tried: {tried}")

    def summary_ok(self, title: str, hashtags: list[str], cost_vnd: int):
        total_t = time.perf_counter() - self.t0
        tags = "  ".join(str(h) for h in (hashtags or [])[:3])
        print(f"\n{'─' * _W}")
        print(f"  {title}")
        if tags:
            print(f"  {tags}")
        print(f"  {total_t:.0f}s  ·  ~{cost_vnd}đ")
        print(f"{'─' * _W}\n")

    def summary_fail(self, title: str):
        total_t = time.perf_counter() - self.t0
        fails = [s for s in self.steps_done if s["status"] == "✕"]
        print(f"\n{'─' * _W}")
        print(f"  ✕  Failed — {title}")
        print(f"  {total_t:.0f}s")
        for s in fails:
            print(f"     ✕  {s['name']}: {s.get('detail', '')}")
        print(f"{'─' * _W}\n")


# ── Main Pipeline ────────────────────────────────────────────────────────────

def run(video_path: str, lut_path: str = "", api_key: str = "",
        apply_noise: bool = True, apply_lut: bool = True,
        cover: bool = True, out_dir: str = "",
        lut_skill: str = "", noise_skill: str = "",
        preset: str = "capcut",
        lut_intensity: float = 1.0,
        thumb_style: str = "boxphonefarm") -> int:
    """
    Pipeline đầy đủ: video → audio → whisper → AI title → thumbnail → render.
    Returns: exit code (0 = success, 1 = failure).
    """
    source = Path(video_path).expanduser().resolve()
    if not source.exists():
        print(f"❌ Không tìm thấy video: {source}")
        return 1

    # API key
    if not api_key:
        api_key = api_key_from_settings()
    if not api_key:
        print("❌ Cần DEEPSEEK_API_KEY. Đặt trong settings.json (ds_api_key) hoặc truyền --key")
        return 1

    # ── Skill resolution ──
    noise_filter = ""
    if noise_skill:
        ns = load_noise_skill(noise_skill)
        noise_filter = ns.get("filter", "")
        log(f"Noise skill: {ns['label']}")

    # LUT
    if lut_skill:
        ls = load_lut_skill(lut_skill)
        if ls.get("path"):
            lut_path = ls["path"]
            log(f"LUT skill: {ls['label']}")
        elif apply_lut:
            log(f"⚠ LUT skill '{lut_skill}' không tìm thấy file — bỏ qua LUT")
            apply_lut = False
    if apply_lut and not lut_skill:
        lut_path = resolve_lut(lut_path)
        if not lut_path:
            apply_lut = False

    # Output dir
    stem = source.stem
    job_dir = make_job_dir(stem, out_dir)
    duration = ffprobe_duration(source)

    tracker = PipelineTracker(source.name, duration, {
        "LUT": apply_lut,
        "Noise": apply_noise,
        "Cover": cover,
    })
    tracker.print_header()

    # ── Step 1: Tách audio + transcript ──
    tracker.start_step(0)
    audio_path = job_dir / "audio.wav"
    segments: list[dict] = []
    cleaned_transcript = ""
    audio_ok = extract_audio(source, audio_path)

    if not audio_ok:
        _, msg = check_audio(source)
        tracker.step_warn(msg)
    else:
        segments = transcribe(audio_path)

        # Lưu transcript_raw.txt
        raw_lines = [f"[{s['start']:.1f}s] {s['text']}" for s in segments]
        (job_dir / "transcript_raw.txt").write_text("\n".join(raw_lines), encoding="utf-8")

        # Regex fix
        segments = fix_regex(segments)
        regex_lines = [f"[{s['start']:.1f}s] {s['text']}" for s in segments]
        (job_dir / "transcript_regex.txt").write_text("\n".join(regex_lines), encoding="utf-8")

        tracker.step_ok(f"{len(segments)} segments — đã lưu raw + regex")

        # ── Step 2: AI sửa transcript ──
        tracker.start_step(1)
        cleaned_transcript, _, _ = ai_fix(segments, stem, api_key)
        if cleaned_transcript:
            (job_dir / "transcript_clean.txt").write_text(cleaned_transcript, encoding="utf-8")
            # Đếm số dòng AI sửa
            import re
            changes = 0
            clean_stripped = [re.sub(r"^\[\d+\.\d+s\]\s*", "", l).strip()
                              for l in cleaned_transcript.split("\n") if l.strip()]
            for i, cl in enumerate(clean_stripped):
                if i < len(regex_lines):
                    rl = re.sub(r"^\[\d+\.\d+s\]\s*", "", regex_lines[i]).strip()
                    if cl != rl:
                        changes += 1
            tracker.step_ok(f"đã lưu transcript_clean.txt · AI sửa {changes} dòng")
        else:
            tracker.step_warn("dùng bản regex (không gọi được AI)")

    # ── Step 3: AI sinh tiêu đề + hashtag ──
    tracker.start_step(2)
    recent = recent_titles(out_dir, days=1)
    ai = generate_title(segments, stem, api_key, cleaned_transcript, recent)
    title = clean_title(ai.get("title", stem))
    hashtags = ai.get("hashtags", [])
    caption = ai.get("caption", "")
    brief = ai.get("brief", "")
    tag_str = " ".join(hashtags[:3])
    tracker.step_ok(f"{title}" + (f" | {tag_str}" if tag_str else ""))

    # ── Step 4: Thumbnail ──
    tracker.start_step(3)
    frame_path = job_dir / "frame.png"
    frame_ok = extract_frame(source, frame_path, duration)

    thumb_path = job_dir / f"{slugify(title)}_thumbnail.png"
    if frame_ok:
        draw_thumbnail(frame_path, thumb_path, title, style=thumb_style)
        tracker.step_ok()
    else:
        tracker.step_warn("không lấy được frame — bỏ qua thumbnail")
        thumb_path = Path("")

    # ── Step 5: Render video ──
    tracker.start_step(4)
    tag_part = " ".join(str(h) for h in hashtags[:3] if str(h).startswith("#"))
    file_title = video_filename(title)
    if tag_part:
        file_title = f"{file_title} {tag_part}"
    out_video = job_dir / f"{file_title}.mp4"
    ok, err = render_video(
        source, out_video,
        thumb_path if isinstance(thumb_path, Path) else Path(""),
        lut_path, apply_lut, apply_noise,
        noise_filter=noise_filter,
        cover=cover and bool(str(thumb_path)),
        out_dir=str(job_dir),
        preset=preset,
        lut_intensity=lut_intensity,
    )
    if not ok:
        render_metrics = last_render_metrics()
        fallback_reason = render_metrics.get("fallback_reason") or "GPU not attempted"
        tracker.step_fail("Render thất bại", error_context=err,
                          tried=f"GPU ({fallback_reason}) → CPU libx264")
        tracker.summary_fail(title)
        return 1
    render_metrics = last_render_metrics()
    backend = render_metrics.get("backend", "cpu")
    rt = render_metrics.get("realtime_factor")
    speed = f"{backend} {rt:.1f}×" if rt else backend
    tracker.step_ok(speed)

    # ── Step 6: Lưu report ──
    tracker.start_step(5)
    report = {
        "version": "4.0-modular",
        "created_at": datetime.now().isoformat(),
        "source": str(source),
        "title": title,
        "hashtags": hashtags,
        "caption": caption,
        "brief": brief,
        "duration": duration,
        "segments": len(segments),
        "output_video": str(out_video),
        "output_thumbnail": str(thumb_path),
        "transcript_raw": str(job_dir / "transcript_raw.txt"),
        "transcript_regex": str(job_dir / "transcript_regex.txt"),
        "transcript_clean": str(job_dir / "transcript_clean.txt"),
        "lut_applied": apply_lut,
        "lut_skill": lut_skill or None,
        "noise_applied": apply_noise,
        "noise_skill": noise_skill or None,
        "render_preset": preset,
        "cover_applied": cover,
        "render_backend": render_metrics.get("backend"),
        "render_seconds": render_metrics.get("seconds"),
        "render_realtime_factor": render_metrics.get("realtime_factor"),
        "render_fallback_reason": render_metrics.get("fallback_reason"),
        "render_metrics": render_metrics,
    }
    report_path = job_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tracker.step_ok()

    # ── Step 7: Embed cover art + move → done/ ──
    tracker.start_step(6)
    done_dir = output_root(out_dir) / "done"
    done_dir.mkdir(parents=True, exist_ok=True)
    done_video = done_dir / f"{file_title}.mp4"
    try:
        # Embed thumbnail làm cover art metadata (Finder hiển thị preview)
        if thumb_path and Path(str(thumb_path)).is_file():
            tmp_video = done_dir / f"_tmp_{file_title}.mp4"
            from .core.ffmpeg import ff_run
            r = ff_run([
                "ffmpeg", "-y",
                "-i", str(out_video),
                "-i", str(thumb_path),
                "-map", "0:v", "-map", "0:a", "-map", "1:v",
                "-c:v:0", "copy", "-c:a:0", "copy",
                "-c:v:1", "mjpeg",
                "-disposition:v:1", "attached_pic",
                str(tmp_video),
            ], timeout=60)
            if r.returncode == 0:
                out_video.unlink()
                done_video.unlink(missing_ok=True)  # ghi đè nếu trùng tên
                tmp_video.rename(done_video)
                tmp_video.unlink(missing_ok=True)   # cleanup nếu rename thất bại
            else:
                shutil.move(str(out_video), str(done_video))
        else:
            shutil.move(str(out_video), str(done_video))
        tracker.step_ok(f"✔ {done_dir.name}/")
    except Exception as e:
        tracker.step_warn(f"copy lỗi: {e}")

    # Cleanup
    if audio_path.exists():
        audio_path.unlink()
    if frame_path.exists():
        frame_path.unlink()

    cost_vnd = int((len(segments) and 20) or 0)
    tracker.summary_ok(title, hashtags, cost_vnd)
    return 0
