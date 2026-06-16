"""
render.py — Render video specialist.
ffmpeg: LUT + noise filter + thumbnail cover + Full HD 1080×1920.
Config loaded from skills/render/ JSON. Optimized for M1 Pro (libx264 fast).
"""

import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .core import log
from .core.ffmpeg import ff_run, mux_stream_copy, render_audio_track
from .config import NOISE_FILTER, TARGET_W, TARGET_H, COVER_DURATION
from .skills import load_render_skill

_FILTER_THREADS = 6  # M1 Pro: 6 P-cores cho filter_complex
_GPU_BITRATE = 16_000_000
_GPU_PACKAGE = Path(__file__).parent / "native/gpu-renderer"
_GPU_BINARY = _GPU_PACKAGE / ".build/release/oneshot-gpu-render"
_GPU_PREFLIGHT: tuple[bool, str] | None = None
_LAST_RENDER_METRICS: dict = {}


def last_render_metrics() -> dict:
    """Return metrics for the most recent render without changing render()'s tuple."""
    return dict(_LAST_RENDER_METRICS)


def _set_render_metrics(**metrics) -> None:
    global _LAST_RENDER_METRICS
    _LAST_RENDER_METRICS = metrics


def _gpu_preflight() -> tuple[bool, str]:
    global _GPU_PREFLIGHT
    if _GPU_PREFLIGHT is not None:
        return _GPU_PREFLIGHT

    if platform.system() != "Darwin":
        _GPU_PREFLIGHT = (False, "GPU renderer requires macOS")
        return _GPU_PREFLIGHT

    if not _GPU_BINARY.is_file() and (_GPU_PACKAGE / "Package.swift").is_file():
        swift = shutil.which("swift")
        if swift:
            log("Build GPU helper (one-time)...")
            build = subprocess.run(
                [swift, "build", "-c", "release", "--package-path", str(_GPU_PACKAGE)],
                capture_output=True, text=True, timeout=300,
            )
            if build.returncode != 0:
                detail = build.stderr.strip() or build.stdout.strip()
                _GPU_PREFLIGHT = (False, f"GPU helper build failed: {detail[:500]}")
                return _GPU_PREFLIGHT

    if not _GPU_BINARY.is_file():
        _GPU_PREFLIGHT = (False, f"GPU helper not found: {_GPU_BINARY}")
    elif not os.access(_GPU_BINARY, os.X_OK):
        _GPU_PREFLIGHT = (False, f"GPU helper is not executable: {_GPU_BINARY}")
    else:
        try:
            result = subprocess.run(
                [str(_GPU_BINARY), "--preflight"],
                capture_output=True, text=True, timeout=15,
            )
            data = json.loads(result.stdout) if result.stdout.strip() else {}
            if result.returncode == 0 and data.get("success") is True:
                _GPU_PREFLIGHT = (True, "")
            else:
                detail = data.get("error") or result.stderr.strip() or result.stdout.strip()
                _GPU_PREFLIGHT = (False, f"GPU preflight failed: {detail or 'hardware unavailable'}")
        except Exception as exc:
            _GPU_PREFLIGHT = (False, f"GPU preflight failed: {exc}")
    return _GPU_PREFLIGHT


def _resolve_render_skill(preset: str) -> dict:
    sk = load_render_skill(preset)
    if not sk.get("video_enhance"):
        sk = load_render_skill("capcut")
    return sk


def _video_chain(fps: float, lut_path: str, apply_lut: bool, preset: str,
                 label: str, lut_intensity: float = 1.0) -> str:
    sk = _resolve_render_skill(preset)
    enhance = sk["video_enhance"].format(w=TARGET_W, h=TARGET_H)

    if not (apply_lut and lut_path and lut_intensity > 0):
        return f"[0:v]fps={fps},{enhance}[{label}]"

    if lut_intensity >= 1.0:
        return f"[0:v]fps={fps},lut3d=file='{lut_path}',{enhance}[{label}]"

    return (
        f"[0:v]fps={fps},split[{label}_raw][{label}_lut];"
        f"[{label}_lut]lut3d=file='{lut_path}'[{label}_luted];"
        f"[{label}_raw][{label}_luted]blend=all_mode=overlay:all_opacity={lut_intensity:.2f}[{label}_blend];"
        f"[{label}_blend]{enhance}[{label}]"
    )


def _validate_lut(source: Path, lut_path: str, out_dir: Path, duration: float) -> bool:
    if not lut_path or not Path(lut_path).exists():
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    test_frame = out_dir / "lut-preflight.png"
    frame_time = max(0.1, duration * 0.18)
    r = ff_run([
        "ffmpeg", "-y", "-ss", f"{frame_time:.3f}", "-i", str(source),
        "-frames:v", "1", "-vf", f"lut3d=file='{lut_path}'",
        str(test_frame)
    ], timeout=120)
    ok = r.returncode == 0 and test_frame.exists() and test_frame.stat().st_size > 0
    log("LUT preflight OK" if ok else "⚠ LUT preflight fail — bỏ qua LUT")
    return ok


def _render_cpu(source: Path, out_video: Path, thumbnail: Path,
                lut_path: str, apply_lut: bool, apply_noise: bool,
                noise_filter: str, cover: bool, preset: str,
                lut_intensity: float, fps: float) -> tuple[bool, str]:
    sk = _resolve_render_skill(preset)
    encoder_args = sk["encoder_x264"]
    filter_parts = []
    extra_inputs = []

    filter_parts.append(_video_chain(fps, lut_path, apply_lut, preset, "vmain", lut_intensity))

    active_noise = noise_filter or NOISE_FILTER
    if apply_noise and active_noise:
        filter_parts.append(f"[0:a]{active_noise},aformat=sample_rates=48000:channel_layouts=stereo[amain]")
    else:
        filter_parts.append("[0:a]anull,aformat=sample_rates=48000:channel_layouts=stereo[amain]")

    map_v, map_a = "[vmain]", "[amain]"

    if cover and thumbnail.is_file():
        extra_inputs = [
            "-loop", "1", "-t", f"{COVER_DURATION:.2f}", "-i", str(thumbnail),
            "-f", "lavfi", "-t", f"{COVER_DURATION:.2f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]
        filter_parts.append(
            f"[1:v]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
            f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={fps},format=yuv420p,setpts=PTS-STARTPTS[vcover]"
        )
        filter_parts.append("[2:a]aresample=48000,asetpts=PTS-STARTPTS[acover]")
        filter_parts.append("[vcover][acover][vmain][amain]concat=n=2:v=1:a=1[vout][aout]")
        map_v, map_a = "[vout]", "[aout]"

    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        *extra_inputs,
        "-filter_complex", ";".join(filter_parts),
        "-filter_threads", str(_FILTER_THREADS),
        "-threads", "0",
        "-map", map_v, "-map", map_a,
        *encoder_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_video),
    ]

    log(f"Render ffmpeg (libx264, {preset}, {_FILTER_THREADS} threads)...")
    r = ff_run(cmd, timeout=3600)

    if r.returncode != 0:
        err = (r.stderr or '')[:500]
        log(f"❌ Render lỗi: {err}")
        return False, err
    return True, ""


def _run_gpu_video(source: Path, output: Path, thumbnail: Path,
                   lut_path: str, apply_lut: bool, cover: bool,
                   lut_intensity: float) -> tuple[subprocess.CompletedProcess, dict]:
    cmd = [
        str(_GPU_BINARY), "--input", str(source), "--output", str(output),
        "--width", str(TARGET_W), "--height", str(TARGET_H),
        "--bitrate", str(_GPU_BITRATE),
    ]
    if apply_lut and lut_path:
        cmd.extend(["--lut", lut_path, "--lut-intensity", f"{lut_intensity:.3f}"])
    if cover and thumbnail.is_file():
        cmd.extend(["--thumbnail", str(thumbnail), "--cover-duration", f"{COVER_DURATION:.3f}"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    helper_metrics = {}
    if result.returncode == 0:
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GPU helper returned invalid JSON stdout") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("GPU helper JSON stdout must be an object")
        helper_metrics = parsed
    return result, helper_metrics


def render(source: Path, out_video: Path, thumbnail: Path,
           lut_path: str = "", apply_lut: bool = True,
           apply_noise: bool = True, noise_filter: str = "",
           cover: bool = True, out_dir: str = "",
           preset: str = "capcut",
           lut_intensity: float = 1.0) -> tuple[bool, str]:
    from .core import ffprobe_duration, ffprobe_video_info

    started = time.perf_counter()
    _set_render_metrics()
    source = Path(source)
    out_video = Path(out_video)
    thumbnail = Path(thumbnail)
    if not source.is_file():
        err = f"Source video not found: {source}"
        _set_render_metrics(backend="none", seconds=0.0, realtime_factor=None,
                            fallback_reason=None, error=err)
        return False, err

    duration = ffprobe_duration(source)
    info = ffprobe_video_info(source)
    if duration <= 0 or info.get("width", 0) <= 0:
        err = f"Invalid source video: {source}"
        elapsed = time.perf_counter() - started
        _set_render_metrics(backend="none", seconds=elapsed, realtime_factor=None,
                            fallback_reason=None, error=err)
        return False, err
    fps = info.get("fps", 30)

    if apply_lut and lut_path:
        apply_lut = Path(lut_path).is_file()
        if not apply_lut:
            log("⚠ LUT file missing — bỏ qua LUT")

    use_cover = cover and thumbnail.is_file()
    preflight_ok, fallback_reason = _gpu_preflight()
    gpu_metrics = {}
    gpu_seconds = 0.0

    if preflight_ok:
        log("Render GPU video + FFmpeg audio concurrently...")
        gpu_started = time.perf_counter()
        try:
            out_video.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="oneshot-render-", dir=out_video.parent) as temp_dir:
                temp_root = Path(temp_dir)
                temp_video = temp_root / "video.mp4"
                temp_audio = temp_root / "audio.m4a"
                active_noise = (noise_filter or NOISE_FILTER) if apply_noise else ""
                silence_duration = COVER_DURATION if use_cover else 0.0
                with ThreadPoolExecutor(max_workers=2) as executor:
                    video_future = executor.submit(
                        _run_gpu_video, source, temp_video, thumbnail,
                        lut_path, apply_lut, use_cover, lut_intensity,
                    )
                    audio_future = executor.submit(
                        render_audio_track, source, temp_audio,
                        active_noise, silence_duration, 3600,
                    )
                    gpu_result, gpu_metrics = video_future.result()
                    audio_result = audio_future.result()

                if gpu_result.returncode != 0:
                    raise RuntimeError(f"GPU helper failed: {(gpu_result.stderr or gpu_result.stdout).strip()[:500]}")
                if not temp_video.is_file() or temp_video.stat().st_size == 0:
                    raise RuntimeError("GPU helper produced no video")
                if audio_result.returncode != 0:
                    raise RuntimeError(f"FFmpeg audio failed: {(audio_result.stderr or '').strip()[:500]}")
                if not temp_audio.is_file() or temp_audio.stat().st_size == 0:
                    raise RuntimeError("FFmpeg produced no audio")

                mux_result = mux_stream_copy(temp_video, temp_audio, out_video, timeout=600)
                if mux_result.returncode != 0:
                    raise RuntimeError(f"Final stream-copy mux failed: {(mux_result.stderr or '').strip()[:500]}")
                if not out_video.is_file() or out_video.stat().st_size == 0:
                    raise RuntimeError("Final stream-copy mux produced no output")

            elapsed = time.perf_counter() - started
            rendered_duration = duration + silence_duration
            _set_render_metrics(
                backend="gpu", seconds=elapsed,
                realtime_factor=rendered_duration / elapsed if elapsed > 0 else None,
                fallback_reason=None, gpu=gpu_metrics,
                gpu_pipeline_seconds=time.perf_counter() - gpu_started,
            )
            return True, ""
        except Exception as exc:
            gpu_seconds = time.perf_counter() - gpu_started
            fallback_reason = str(exc) or exc.__class__.__name__
            out_video.unlink(missing_ok=True)
            log(f"GPU fallback → CPU: {fallback_reason}")
    else:
        log(f"GPU fallback → CPU: {fallback_reason}")

    cpu_started = time.perf_counter()
    if apply_lut and lut_path:
        apply_lut = _validate_lut(
            source, lut_path,
            Path(out_dir) if out_dir else out_video.parent,
            duration,
        )
    ok, err = _render_cpu(
        source, out_video, thumbnail, lut_path, apply_lut, apply_noise,
        noise_filter, use_cover, preset, lut_intensity, fps,
    )
    elapsed = time.perf_counter() - started
    rendered_duration = duration + (COVER_DURATION if use_cover else 0.0)
    _set_render_metrics(
        backend="cpu", seconds=elapsed,
        realtime_factor=rendered_duration / elapsed if elapsed > 0 else None,
        fallback_reason=fallback_reason,
        gpu=gpu_metrics, gpu_pipeline_seconds=gpu_seconds,
        cpu_seconds=time.perf_counter() - cpu_started,
        error=err if not ok else None,
    )
    return ok, err


def extract_frame(source: Path, out_frame: Path, duration: float, timeout: int = 120) -> bool:
    frame_time = min(max(duration * 0.32, 0.5), max(duration - 0.5, 0.5))
    r = ff_run([
        "ffmpeg", "-y", "-ss", f"{frame_time:.3f}", "-i", str(source),
        "-frames:v", "1", str(out_frame)
    ], timeout=timeout)
    if r.returncode != 0 or not out_frame.exists():
        r = ff_run([
            "ffmpeg", "-y", "-i", str(source),
            "-frames:v", "1", str(out_frame)
        ], timeout=timeout)
    return out_frame.exists() and out_frame.stat().st_size > 0
