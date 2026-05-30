#!/usr/bin/env python3
"""Render a slide project to video and merge it with Edge TTS voiceover."""

import argparse
import asyncio
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from subtitle_timing import build_karaoke_subtitle_timing, build_script_subtitle_timing
from slide_media import discover_slide_videos


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
BASE_SLIDE_WIDTH = 390
BASE_SLIDE_HEIGHT = 693
RENDER_ZOOM = VIDEO_WIDTH / BASE_SLIDE_WIDTH
TAB_CAPTURE_WINDOW_LEFT = 10000
TAB_CAPTURE_WINDOW_TOP = 40
TAB_CAPTURE_WARMUP = 0.8
ANTICIPATION_OFFSET = -0.5
HOOK_SLIDE_INDEX = 0
HOOK_SENTENCE_COUNTS = {1}


def find_system_chromium() -> Path | None:
    env_path = os.environ.get("ESCBASE_BROWSER_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    if not sys.platform.startswith("win"):
        return None

    candidates = []
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(env_name)
        if not root:
            continue
        candidates.extend(
            [
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def check_render_dependencies() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        print("❌ Thiếu công cụ render:", ", ".join(missing))
        if sys.platform.startswith("win"):
            print("Cách cài trên Windows PowerShell:")
            print("  winget install --id Gyan.FFmpeg -e")
            print("Sau khi cài xong, đóng PowerShell/Web UI cũ, mở PowerShell mới rồi chạy lại.")
        else:
            print("Hãy cài ffmpeg rồi chạy lại.")
        raise SystemExit(1)

    try:
        from playwright.async_api import async_playwright as _async_playwright
        _ = _async_playwright
    except Exception as exc:
        print("❌ Playwright chưa chạy được trong môi trường Python hiện tại.")
        print(f"Chi tiết: {exc.__class__.__name__}: {exc}")
        if sys.platform.startswith("win") and ("greenlet" in str(exc).lower() or "dll load failed" in str(exc).lower()):
            print("")
            print("Nguyên nhân thường gặp trên Windows: thiếu Microsoft Visual C++ Redistributable 2015-2022 x64.")
            print("Cách sửa trong PowerShell:")
            print("  winget install --id Microsoft.VCRedist.2015+.x64 -e")
            print("  .\\.venv\\Scripts\\python.exe -m pip install --force-reinstall --no-cache-dir greenlet playwright")
            print("  .\\.venv\\Scripts\\python.exe -c \"import greenlet; import playwright.async_api; print('OK')\"")
            print("Sau đó mở lại Web UI và render lại.")
        else:
            print("Hãy chạy lại setup để cài Playwright/Chromium rồi thử lại.")
        raise SystemExit(1)


async def launch_chromium(playwright, args: list[str], *, headless: bool = True):
    browser_path = find_system_chromium()
    launch_options = {
        "headless": headless,
        "args": args,
    }
    if browser_path:
        print(f"Using system browser for render: {browser_path}")
        launch_options["executable_path"] = str(browser_path)

    try:
        return await playwright.chromium.launch(**launch_options)
    except Exception as exc:
        if sys.platform.startswith("win"):
            print("❌ Không mở được browser để render slide.")
            print(f"Chi tiết: {exc.__class__.__name__}: {exc}")
            print("")
            print("Cách sửa trên Windows:")
            print("  1. Chạy lại setup:")
            print("     powershell -ExecutionPolicy Bypass -File .\\setup_and_run_windows.ps1")
            print("  2. Nếu vẫn lỗi, cài Microsoft Edge hoặc Google Chrome rồi chạy lại.")
            print("  3. Nếu muốn chỉ định browser thủ công:")
            print("     $env:ESCBASE_BROWSER_PATH='C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'")
        raise

AUDIO_CAPTURE_SCRIPT = """
<script>
(() => {
  const NativeAudioContext = window.AudioContext || window.webkitAudioContext;
  if (!NativeAudioContext || window.__slideAudioPatchInstalled) return;

  window.__slideAudioPatchInstalled = true;
  let captureDestination = null;
  let mediaRecorder = null;
  let chunks = [];
  let armed = false;
  let activeAudioContext = null;
  const mediaSources = new WeakMap();
  const retainedMediaSources = [];

  function connectMediaElements(ctx) {
    if (!ctx) return;
    document.querySelectorAll('video, audio').forEach((element) => {
      if (mediaSources.has(element)) return;
      try {
        const source = ctx.createMediaElementSource(element);
        source.connect(ctx.destination);
        mediaSources.set(element, source);
        retainedMediaSources.push(source);
      } catch (err) {}
    });
  }

  const originalConnect = window.AudioNode && window.AudioNode.prototype.connect;
  if (originalConnect) {
    window.AudioNode.prototype.connect = function(destination, ...args) {
      const result = originalConnect.call(this, destination, ...args);
      if (captureDestination && destination && destination.constructor?.name === 'AudioDestinationNode') {
        try { originalConnect.call(this, captureDestination); } catch (err) {}
      }
      return result;
    };
  }

  function startRecorder() {
    if (!captureDestination || mediaRecorder) return;
    chunks = [];
    const options = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? { mimeType: 'audio/webm;codecs=opus' }
      : {};
    mediaRecorder = new MediaRecorder(captureDestination.stream, options);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    mediaRecorder.start(250);
  }

  function PatchedAudioContext(...args) {
    const ctx = new NativeAudioContext(...args);
    activeAudioContext = ctx;
    captureDestination = ctx.createMediaStreamDestination();
    setTimeout(() => connectMediaElements(ctx), 0);
    if (armed) startRecorder();
    return ctx;
  }
  PatchedAudioContext.prototype = NativeAudioContext.prototype;
  Object.setPrototypeOf(PatchedAudioContext, NativeAudioContext);

  window.AudioContext = PatchedAudioContext;
  if (window.webkitAudioContext) window.webkitAudioContext = PatchedAudioContext;

  window.__armSlideAudioRecording = () => {
    armed = true;
    connectMediaElements(activeAudioContext);
    startRecorder();
  };

  window.__connectSlideMediaAudio = () => {
    connectMediaElements(activeAudioContext);
  };

  window.__stopSlideAudioRecording = async () => {
    if (!mediaRecorder) return '';
    if (mediaRecorder.state !== 'inactive') {
      await new Promise((resolve) => {
        mediaRecorder.onstop = resolve;
        mediaRecorder.stop();
      });
    }
    const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i += 32768) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    }
    return btoa(binary);
  };
})();
</script>
"""

def configure_render_geometry(width: int, height: int) -> None:
    global VIDEO_WIDTH, VIDEO_HEIGHT, RENDER_ZOOM
    VIDEO_WIDTH = int(width)
    VIDEO_HEIGHT = int(height)
    RENDER_ZOOM = VIDEO_WIDTH / BASE_SLIDE_WIDTH


def parse_render_size(value: str) -> tuple[int, int]:
    raw = str(value or "").strip().lower()
    if not raw:
        return VIDEO_WIDTH, VIDEO_HEIGHT
    if re.fullmatch(r"\d+", raw):
        width = int(raw)
        if width <= 0:
            raise ValueError("Render width must be positive.")
        return width, int(round(width * 16 / 9))
    match = re.fullmatch(r"(\d+)\s*[x:]\s*(\d+)", raw)
    if not match:
        raise ValueError("Render size must be WIDTHxHEIGHT or WIDTH for 9:16.")
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError("Render size must be positive.")
    return width, height


def build_display_capture_script() -> str:
    return f"""
<script>
(() => {{
  if (window.__tabCaptureInstalled) return;
  window.__tabCaptureInstalled = true;

  function blobToBase64(blob) {{
    return new Promise((resolve, reject) => {{
      const reader = new FileReader();
      reader.onerror = () => reject(reader.error || new Error('readAsDataURL failed'));
      reader.onload = () => {{
        const result = typeof reader.result === 'string' ? reader.result : '';
        const comma = result.indexOf(',');
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      }};
      reader.readAsDataURL(blob);
    }});
  }}

  window.__startTabVideoCapture = async (options = {{}}) => {{
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {{
      throw new Error('getDisplayMedia is unavailable in this browser');
    }}
    if (window.__tabCaptureState) {{
      throw new Error('tab capture is already running');
    }}

    const frameRate = Math.max(24, Number(options.frameRate || 30));
    const videoBitsPerSecond = Math.max(8_000_000, Number(options.videoBitsPerSecond || 16_000_000));
    const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
      ? 'video/webm;codecs=vp9'
      : (MediaRecorder.isTypeSupported('video/webm;codecs=vp8') ? 'video/webm;codecs=vp8' : 'video/webm');

    const stream = await navigator.mediaDevices.getDisplayMedia({{
      video: {{
        width: {{ ideal: {VIDEO_WIDTH} }},
        height: {{ ideal: {VIDEO_HEIGHT} }},
        frameRate,
        displaySurface: 'browser',
        cursor: 'never',
      }},
      audio: false,
      preferCurrentTab: true,
      selfBrowserSurface: 'include',
      surfaceSwitching: 'exclude',
      systemAudio: 'exclude',
    }});
    const videoTrack = stream.getVideoTracks()[0];
    if (videoTrack && videoTrack.applyConstraints) {{
      try {{
        await videoTrack.applyConstraints({{ width: {VIDEO_WIDTH}, height: {VIDEO_HEIGHT}, cursor: 'never' }});
      }} catch (err) {{}}
    }}

    const recorder = new MediaRecorder(stream, {{
      mimeType,
      videoBitsPerSecond,
    }});
    const state = {{
      stream,
      recorder,
      mimeType,
      byteLength: 0,
      chunks: [],
    }};

    recorder.ondataavailable = (event) => {{
      if (!event.data || !event.data.size) return;
      state.byteLength += event.data.size;
      state.chunks.push(event.data);
    }};

    recorder.start(1000);
    window.__tabCaptureState = state;
    return {{ mimeType }};
  }};

  window.__stopTabVideoCapture = async () => {{
    const state = window.__tabCaptureState;
    if (!state) return null;

    const stopped = new Promise((resolve) => {{
      state.recorder.addEventListener('stop', resolve, {{ once: true }});
    }});
    state.recorder.stop();
    state.stream.getTracks().forEach((track) => track.stop());
    await stopped;
    const wholeBlob = new Blob(state.chunks, {{ type: state.mimeType }});
    const sliceSize = 4 * 1024 * 1024;
    let chunkIndex = 0;
    for (let offset = 0; offset < wholeBlob.size; offset += sliceSize) {{
      const slice = wholeBlob.slice(offset, offset + sliceSize);
      const payload = await blobToBase64(slice);
      await window.__pushTabCaptureChunk({{ index: chunkIndex, payload }});
      chunkIndex += 1;
    }}
    window.__tabCaptureState = null;
    return {{
      mimeType: state.mimeType,
      byteLength: wholeBlob.size,
    }};
  }};
}})();
</script>
"""

def build_recording_css() -> str:
    return f"""
html, body {{
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
  background: #000 !important;
  scrollbar-width: none !important;
  cursor: none !important;
}}
html::-webkit-scrollbar, body::-webkit-scrollbar {{
  display: none !important;
}}
* {{
  cursor: none !important;
}}
.side-controls,
.script-panel,
.audio-panel,
.theme-editor-panel {{
  display: none !important;
}}
.main-wrapper {{
  position: static !important;
  top: auto !important;
  right: auto !important;
  bottom: auto !important;
  left: auto !important;
  display: block !important;
  margin: 0 !important;
  padding: 0 !important;
  transform: none !important;
}}
.slide-container {{
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  width: {BASE_SLIDE_WIDTH}px !important;
  height: {BASE_SLIDE_HEIGHT}px !important;
  border: 0 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  transform: none !important;
  transform-origin: top left !important;
  zoom: {RENDER_ZOOM:.8f} !important;
}}
"""

SUBTITLE_CSS = """
.script-subtitles {
  position: absolute;
  left: 28px;
  right: 28px;
  bottom: var(--subtitle-bottom, 96px);
  z-index: 180;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  outline: 0 !important;
  backdrop-filter: none !important;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.script-subtitles.visible {
  opacity: 1;
}
.script-subtitle-line {
  width: auto;
  max-width: 100%;
  font-family: var(--font, 'Inter', sans-serif);
  font-size: var(--subtitle-font-size, 15px);
  font-weight: 950;
  line-height: 1.25;
  letter-spacing: -0.01em;
  text-align: center;
  display: flex;
  flex-wrap: var(--subtitle-flex-wrap, wrap);
  align-items: center;
  justify-content: center;
  gap: 0.08em 0.24em;
  max-height: calc(var(--subtitle-font-size, 15px) * var(--subtitle-max-lines, 2) * 1.35);
  overflow: hidden;
  white-space: var(--subtitle-white-space, normal);
  padding: 0 !important;
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  border-radius: 0 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.55);
}
.script-subtitle-word {
  color: rgba(255, 255, 255, 0.58);
  background: transparent !important;
  box-shadow: none !important;
  transition: color 0.06s linear, opacity 0.06s linear, text-shadow 0.06s linear;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.55);
}
.script-subtitle-word.past {
  color: var(--subtitle-color, #ffffff);
}
.script-subtitle-word.active {
  color: var(--subtitle-active-color, #ff4d4f);
  text-shadow:
    0 1px 2px rgba(0, 0, 0, 0.55),
    0 0 8px rgba(255, 77, 79, 0.28);
}
"""

SUBTITLE_SCRIPT = """
(() => {
  const data = window.__SCRIPT_SUBTITLE_DATA__;
  if (!data || !Array.isArray(data.captions) || data.captions.length === 0) return;

  let overlay = null;
  let line = null;
  let startedAt = 0;
  let raf = null;
  let lastCaptionIndex = -1;
  let lastActiveWordIndex = -2;

  function ensureOverlay() {
    if (overlay) return overlay;
    const container = document.getElementById('slideContainer') || document.body;
    overlay = document.createElement('div');
    overlay.className = 'script-subtitles';
    line = document.createElement('div');
    line.className = 'script-subtitle-line';
    overlay.appendChild(line);
    container.appendChild(overlay);
    return overlay;
  }

  function subtitleMaxLines() {
    const raw = getComputedStyle(document.documentElement).getPropertyValue('--subtitle-max-lines').trim();
    const value = Number(raw);
    return Number.isFinite(value) && value > 0 ? value : 2;
  }

  function fitSubtitleLine() {
    if (!line) return;
    line.style.transform = '';
    line.style.transformOrigin = '';
    if (subtitleMaxLines() > 1) return;
    const overlayRect = overlay?.getBoundingClientRect();
    const availableWidth = Math.max(0, (overlayRect?.width || line.parentElement?.getBoundingClientRect().width || line.getBoundingClientRect().width || 0) - 8);
    if (!availableWidth) return;
    const range = document.createRange();
    range.selectNodeContents(line);
    const measuredWidth = range.getBoundingClientRect().width || 0;
    if (!availableWidth || !measuredWidth || measuredWidth <= availableWidth) return;
    const scale = Math.min(1, availableWidth / measuredWidth);
    line.style.transformOrigin = 'center center';
    line.style.transform = `scale(${scale})`;
  }

  function findCaptionIndex(time) {
    const captions = data.captions;
    let candidate = -1;
    for (let i = 0; i < captions.length; i += 1) {
      const caption = captions[i];
      if (time >= caption.start && time <= caption.end + 0.18) return i;
      if (caption.start <= time) candidate = i;
      if (caption.start > time) break;
    }
    return candidate;
  }

  function findActiveWordIndex(words, time) {
    let candidate = -1;
    for (let i = 0; i < words.length; i += 1) {
      const word = words[i];
      if (time >= word.start && time <= word.end + 0.08) return i;
      if (word.start <= time) candidate = i;
      if (word.start > time) break;
    }
    return candidate;
  }

  function renderWords(caption, activeWordIndex) {
    line.replaceChildren();
    caption.words.forEach((word, idx) => {
      const span = document.createElement('span');
      span.className = 'script-subtitle-word';
      if (idx < activeWordIndex) {
        span.classList.add('past');
      } else if (idx === activeWordIndex) {
        span.classList.add('active');
      }
      span.textContent = word.text;
      line.appendChild(span);
    });
    fitSubtitleLine();
  }

  function render(time) {
    ensureOverlay();
    const captions = data.captions;
    const idx = findCaptionIndex(time);
    if (idx < 0 || time > captions[captions.length - 1].end + 0.65) {
      overlay.classList.remove('visible');
      line.replaceChildren();
      lastCaptionIndex = -1;
      lastActiveWordIndex = -2;
      return;
    }

    const caption = captions[idx];
    const hasWords = Array.isArray(caption.words) && caption.words.length > 0;
    const activeWordIndex = hasWords ? findActiveWordIndex(caption.words, time) : -1;
    if (idx !== lastCaptionIndex || activeWordIndex !== lastActiveWordIndex) {
      if (hasWords) {
        renderWords(caption, activeWordIndex);
      } else {
        line.textContent = caption.text;
        fitSubtitleLine();
      }
      lastCaptionIndex = idx;
      lastActiveWordIndex = activeWordIndex;
    }
    overlay.classList.add('visible');
  }

  function loop() {
    const time = (performance.now() - startedAt) / 1000;
    render(time);
    raf = requestAnimationFrame(loop);
  }

  window.__startScriptSubtitles = () => {
    startedAt = performance.now();
    ensureOverlay();
    if (raf) cancelAnimationFrame(raf);
    loop();
  };

  window.__stopScriptSubtitles = () => {
    if (raf) cancelAnimationFrame(raf);
    raf = null;
    if (overlay) overlay.classList.remove('visible');
  };
})();
"""

def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


async def get_duration(media_file: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(media_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", "ignore"))
    return float(stdout.decode().strip())


async def get_slide_video_durations(slide_dir: Path) -> dict[int, float]:
    durations: dict[int, float] = {}
    for slide_idx, paths in discover_slide_videos(slide_dir).items():
        slide_durations = []
        for path in paths:
            duration = await get_duration(path)
            slide_durations.append(duration)
            print(f"Slide {slide_idx + 1} video duration: {duration:.2f}s ({path.relative_to(slide_dir)})")
        if slide_durations:
            durations[slide_idx] = max(slide_durations)
    return durations


def write_silence_file(output_dir: Path, name: str, duration: float) -> Path:
    silence_file = output_dir / name
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(silence_file),
        ],
        check=True,
        capture_output=True,
    )
    return silence_file


async def annotate_slide_video_durations(slide_dir: Path, timing_data: list[dict]) -> None:
    video_durations = await get_slide_video_durations(slide_dir)
    for item in timing_data:
        slide_idx = int(item["line"])
        video_duration = float(video_durations.get(slide_idx, 0.0))
        if video_duration <= 0:
            continue
        voice_duration = float(item["duration"])
        item["video_duration"] = video_duration
        if video_duration > voice_duration + 0.05:
            print(
                f"Slide {slide_idx + 1}: video is {video_duration:.2f}s, "
                f"render uses voice timing {voice_duration:.2f}s"
            )


async def ensure_voiceover_matches_timing(output_dir: Path, timing_data: list[dict], tts_path: Path) -> Path:
    expected_duration = sum(float(item["duration"]) for item in timing_data)
    actual_duration = await get_duration(tts_path)
    if actual_duration + 0.35 >= expected_duration:
        return tts_path

    concat_list = output_dir / "concat_render_list.txt"
    entries = []
    for item in timing_data:
        slide_idx = int(item["line"])
        line_file = output_dir / f"line_{slide_idx}.mp3"
        if not line_file.exists():
            print(f"Voiceover is shorter than render timing, but {line_file.name} is missing; using existing concat audio.")
            return tts_path
        entries.append(line_file)
        line_duration = await get_duration(line_file)
        padding = float(item["duration"]) - line_duration
        if padding > 0.05:
            entries.append(write_silence_file(output_dir, f"silence_render_{slide_idx}.mp3", padding))

    concat_list.write_text("".join(f"file '{path.as_posix()}'\n" for path in entries), encoding="utf-8")
    padded_path = output_dir / "voiceover_concat_render.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(padded_path),
        ],
        check=True,
        capture_output=True,
    )
    padded_duration = await get_duration(padded_path)
    print(f"Voiceover padded for render timing: {actual_duration:.2f}s → {padded_duration:.2f}s")
    return padded_path


def load_preview_settings(slide_dir: Path) -> dict:
    settings_file = slide_dir / "preview-settings.json"
    if not settings_file.exists():
        return {}
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def theme_css_from_settings(settings: dict) -> str:
    variables = settings.get("theme", {}).get("variables", {}) if isinstance(settings, dict) else {}
    if not isinstance(variables, dict):
        return ""
    lines = []
    for name, value in variables.items():
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        if not re.fullmatch(r"--[A-Za-z0-9_-]+", name):
            continue
        if re.search(r"[;{}<>]", value) or len(value) > 80:
            continue
        lines.append(f"  {name}: {value};")
    if not lines:
        return ""
    return ":root {\n" + "\n".join(lines) + "\n}"


def subtitle_css_from_settings(settings: dict) -> str:
    subtitles = settings.get("subtitles", {}) if isinstance(settings, dict) else {}
    if not isinstance(subtitles, dict):
        return ""
    lines = []
    color = subtitles.get("color")
    if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        lines.append(f"  --subtitle-color: {color};")
    try:
        font_size = float(subtitles.get("fontSize", 0))
    except (TypeError, ValueError):
        font_size = 0
    if 12 <= font_size <= 28:
        lines.append(f"  --subtitle-font-size: {font_size:g}px;")
    try:
        bottom = float(subtitles.get("bottom", 0))
    except (TypeError, ValueError):
        bottom = 0
    if 40 <= bottom <= 180:
        lines.append(f"  --subtitle-bottom: {bottom:g}px;")
    try:
        max_lines = int(subtitles.get("maxLines", 0))
    except (TypeError, ValueError):
        max_lines = 0
    if 1 <= max_lines <= 3:
        lines.append(f"  --subtitle-max-lines: {max_lines};")
        if max_lines <= 1:
            lines.append("  --subtitle-flex-wrap: nowrap;")
            lines.append("  --subtitle-white-space: nowrap;")
    return ":root {\n" + "\n".join(lines) + "\n}" if lines else ""


def prepare_recording_html(
    slide_dir: Path,
    output_dir: Path,
    subtitle_data: dict | None = None,
    theme_css: str = "",
    preview_settings: dict | None = None,
) -> Path:
    html_path = slide_dir / "index.html"
    html = html_path.read_text(encoding="utf-8")
    base_tag = f'<base href="{slide_dir.as_uri()}/" />'
    settings_payload = json.dumps(preview_settings or {}, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("<head>", f"<head>\n{base_tag}", 1)
    html = html.replace(
        "</head>",
        f"<script>window.__RENDER_MODE__ = true; window.__PREVIEW_SETTINGS__ = {settings_payload};</script>\n</head>",
        1,
    )
    html = html.replace("</head>", f"{AUDIO_CAPTURE_SCRIPT}\n</head>", 1)
    html = html.replace("</head>", f"<style>{build_recording_css()}</style>\n</head>", 1)
    html = html.replace("</body>", f"{build_display_capture_script()}\n</body>", 1)
    if theme_css:
        html = html.replace("</head>", f"<style>{theme_css}</style>\n</head>", 1)
    if subtitle_data:
        payload = json.dumps(subtitle_data, ensure_ascii=False).replace("</", "<\\/")
        html = html.replace("</head>", f"<style>{SUBTITLE_CSS}</style>\n</head>", 1)
        html = html.replace(
            "</body>",
            f"<script>window.__SCRIPT_SUBTITLE_DATA__ = {payload};</script>\n"
            f"<script>{SUBTITLE_SCRIPT}</script>\n</body>",
            1,
        )
    recording_html = output_dir / "_recording.html"
    recording_html.write_text(html, encoding="utf-8")
    return recording_html


async def inspect_reveal_units(recording_html: Path) -> list[int]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await launch_chromium(p, ["--allow-file-access-from-files"])
        page = await browser.new_page(viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT})
        await page.goto(recording_html.as_uri())
        units = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('.slide')).map((slide) => {
              let count = slide.querySelectorAll('.slide-element').length;
              if (slide.dataset.mode === 'highlight') {
                count += slide.querySelectorAll('.highlightable').length;
              }
              if (slide.dataset.mode === 'traffic-light') {
                count += slide.querySelectorAll('.lightable').length;
              }
              return count;
            })
            """
        )
        await browser.close()
        return [int(unit) for unit in units]


def validate_mapping(timing_data: list[dict], reveal_units: list[int]) -> None:
    errors = []
    if len(timing_data) != len(reveal_units):
        errors.append(f"script has {len(timing_data)} lines but HTML has {len(reveal_units)} slides")

    for item in timing_data:
        idx = int(item["line"])
        if idx >= len(reveal_units):
            continue
        sentence_count = len(split_sentences(item["text"]))
        reveal_count = reveal_units[idx]
        # Hook slide reveals all elements at once — skip strict 1:1 check
        if idx == HOOK_SLIDE_INDEX and sentence_count in HOOK_SENTENCE_COUNTS:
            continue
        if sentence_count != reveal_count:
            errors.append(
                f"Slide {idx + 1}: {sentence_count} script sentences != {reveal_count} reveal units"
            )

    if errors:
        joined = "\n  - ".join(errors)
        raise ValueError(f"Script/UI mapping is not 1:1:\n  - {joined}")


def sentence_start_positions(text: str) -> list[int]:
    positions = []
    cursor = 0
    for sentence in split_sentences(text):
        pos = text.find(sentence, cursor)
        positions.append(max(pos, 0))
        cursor = pos + len(sentence) if pos >= 0 else cursor
    return positions


def build_click_timeline(timing_data: list[dict], reveal_units: list[int]) -> list[dict]:
    timeline = []
    cumulative_time = 0.0

    for item in timing_data:
        slide_idx = int(item["line"])
        duration = float(item["duration"])
        original_audio_duration = float(item.get("original_audio_duration", duration))
        text = item["text"]
        num_actions = reveal_units[slide_idx]
        sentence_count = len(split_sentences(text))
        positions = sentence_start_positions(text)

        if slide_idx == HOOK_SLIDE_INDEX:
            timeline.append(
                {"time": 0.0, "action": "click", "desc": "Start presentation"}
            )
            # Hook slide reveals all elements at once — use sentence count as action count
            if sentence_count in HOOK_SENTENCE_COUNTS and sentence_count < num_actions:
                num_actions = sentence_count
            
        action_range = range(1, num_actions)

        for action_idx in action_range:
            if action_idx < len(positions):
                ratio = positions[action_idx] / max(len(text), 1)
            else:
                ratio = action_idx / max(num_actions, 1)
                
            if slide_idx == HOOK_SLIDE_INDEX and action_idx == 1 and "original_audio_duration" in item:
                # Nếu có thông tin giọng đọc gốc (nghĩa là có demo video), click ngay khi vừa dứt giọng đọc
                click_time = cumulative_time + original_audio_duration
            else:
                # Dùng original_audio_duration để chia tỉ lệ (tránh bị nhiễu do âm thanh câm ở đuôi file)
                click_time = cumulative_time + max(0.55, ratio * original_audio_duration - ANTICIPATION_OFFSET)
                
            timeline.append(
                {
                    "time": round(click_time, 2),
                    "action": "click",
                    "desc": f"Slide {slide_idx + 1}: reveal {action_idx + 1}/{num_actions}",
                }
            )

        cumulative_time += duration
        if slide_idx < len(timing_data) - 1:
            timeline.append(
                {
                    "time": round(cumulative_time, 2),
                    "action": "click",
                    "desc": f"Slide {slide_idx + 1}→{slide_idx + 2}: transition",
                }
            )

    return sorted(timeline, key=lambda event: event["time"])


async def record_video_playwright(recording_html: Path, timeline: list[dict], output_dir: Path, voiceover_duration: float = 0) -> tuple[Path, Path, float]:
    from playwright.async_api import async_playwright

    video_dir = output_dir / "playwright-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    # Ensure recording covers the full voiceover, not just the last click
    total_duration = max(timeline[-1]["time"] + 0.5, voiceover_duration + 0.5)

    async with async_playwright() as p:
        browser = await launch_chromium(
            p,
            [
                "--allow-file-access-from-files",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            record_video_dir=str(video_dir),
            record_video_size={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
        )

        recording_started_at = time.monotonic()
        page = await context.new_page()
        await page.goto(recording_html.as_uri())
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(0.8)

        print(f"Recording {total_duration:.1f}s with {len(timeline)} click events...")
        await page.evaluate("() => window.__armSlideAudioRecording()")
        await page.evaluate(
            "() => window.__startScriptSubtitles && window.__startScriptSubtitles()"
        )
        trim_start = time.monotonic() - recording_started_at
        start_time = asyncio.get_running_loop().time()
        for event in timeline:
            wait_time = event["time"] - (asyncio.get_running_loop().time() - start_time)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            await page.click("#slideContainer", force=True)
            print(f"  [{event['time']:6.2f}s] {event['desc']}")

        remaining = total_duration - (asyncio.get_running_loop().time() - start_time)
        if remaining > 0:
            await asyncio.sleep(remaining)

        encoded_audio = await page.evaluate("() => window.__stopSlideAudioRecording()")
        video = page.video
        await context.close()
        await browser.close()

        if video is None:
            raise RuntimeError("Playwright did not produce a video")
        if not encoded_audio:
            raise RuntimeError("Browser did not capture slide audio")

        raw_video = Path(await video.path())
        app_audio = output_dir / "slide_audio.webm"
        app_audio.write_bytes(base64.b64decode(encoded_audio))
        return raw_video, app_audio, trim_start


async def record_video_tab_capture(
    recording_html: Path,
    timeline: list[dict],
    output_dir: Path,
    voiceover_duration: float = 0,
) -> tuple[Path, Path, float]:
    from playwright.async_api import async_playwright

    video_dir = output_dir / "tab-capture-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    raw_video = video_dir / "tab_capture_raw.webm"
    if raw_video.exists():
        raw_video.unlink()

    total_duration = max(timeline[-1]["time"] + 0.5, voiceover_duration + 0.5)
    capture_title = f"ESCBASE_TAB_CAPTURE_{int(time.time())}"
    trim_start = TAB_CAPTURE_WARMUP

    async with async_playwright() as p:
        browser = await launch_chromium(
            p,
            [
                "--allow-file-access-from-files",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-dev-shm-usage",
                "--enable-usermedia-screen-capturing",
                "--allow-http-screen-capture",
                "--use-fake-ui-for-media-stream",
                f"--auto-select-desktop-capture-source={capture_title}",
                "--window-size=1200,2000",
                f"--window-position={TAB_CAPTURE_WINDOW_LEFT},{TAB_CAPTURE_WINDOW_TOP}",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling",
            ],
            headless=False,
        )
        context = await browser.new_context(viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT})

        chunk_writer = raw_video.open("wb")

        async def push_tab_capture_chunk(_source, payload: dict):
            chunk_b64 = str(payload["payload"])
            chunk_writer.write(base64.b64decode(chunk_b64))
            chunk_writer.flush()
            return None

        await context.expose_binding("__pushTabCaptureChunk", push_tab_capture_chunk)
        page = await context.new_page()
        try:
            await page.goto(recording_html.as_uri())
            await page.wait_for_load_state("networkidle")
            await page.evaluate("(title) => { document.title = title; }", capture_title)
            session = await context.new_cdp_session(page)
            try:
                window_info = await session.send("Browser.getWindowForTarget")
                await session.send(
                    "Browser.setWindowBounds",
                    {
                        "windowId": window_info["windowId"],
                        "bounds": {
                            "left": TAB_CAPTURE_WINDOW_LEFT,
                            "top": TAB_CAPTURE_WINDOW_TOP,
                            "width": window_info["bounds"]["width"],
                            "height": window_info["bounds"]["height"],
                            "windowState": "normal",
                        },
                    },
                )
            except Exception:
                pass
            await asyncio.sleep(0.6)

            print(
                f"Recording {total_duration:.1f}s with {len(timeline)} click events via tab capture "
                f"(warmup {TAB_CAPTURE_WARMUP:.1f}s)..."
            )
            await page.evaluate(
                "(opts) => window.__startTabVideoCapture(opts)",
                {
                    "frameRate": 30,
                    "videoBitsPerSecond": 16_000_000,
                },
            )
            await asyncio.sleep(TAB_CAPTURE_WARMUP)
            await page.evaluate("() => window.__armSlideAudioRecording()")
            await page.evaluate(
                "() => window.__startScriptSubtitles && window.__startScriptSubtitles()"
            )

            start_time = asyncio.get_running_loop().time()
            for event in timeline:
                wait_time = event["time"] - (asyncio.get_running_loop().time() - start_time)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                await page.click("#slideContainer", force=True)
                print(f"  [{event['time']:6.2f}s] {event['desc']}")

            remaining = total_duration - (asyncio.get_running_loop().time() - start_time)
            if remaining > 0:
                await asyncio.sleep(remaining)

            await page.evaluate("() => window.__stopScriptSubtitles && window.__stopScriptSubtitles()")
            encoded_audio = await page.evaluate("() => window.__stopSlideAudioRecording()")
            capture_result = await page.evaluate("() => window.__stopTabVideoCapture()")
        finally:
            chunk_writer.close()
            await context.close()
            await browser.close()

        if not encoded_audio:
            raise RuntimeError("Browser did not capture slide audio")
        if not capture_result:
            raise RuntimeError("Tab capture did not produce a video")
        if raw_video.stat().st_size == 0:
            raise RuntimeError("Tab capture produced an empty video")

        print(
            f"Tab capture wrote {raw_video.stat().st_size / (1024 * 1024):.1f} MB "
            f"({capture_result.get('mimeType', 'unknown mime')})"
        )
        app_audio = output_dir / "slide_audio.webm"
        app_audio.write_bytes(base64.b64decode(encoded_audio))
        return raw_video, app_audio, trim_start


async def record_video(recording_html: Path, timeline: list[dict], output_dir: Path, voiceover_duration: float = 0) -> tuple[Path, Path, float]:
    return await record_video_tab_capture(recording_html, timeline, output_dir, voiceover_duration)


async def merge_final_video(
    raw_video: Path,
    tts_path: Path,
    app_audio_path: Path,
    output_path: Path,
    trim_start: float,
) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{trim_start:.3f}",
        "-i",
        str(raw_video),
        "-i",
        str(tts_path),
        "-i",
        str(app_audio_path),
        "-filter_complex",
        "[0:v]fps=30,format=yuv420p[v];"
        "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[tts];"
        f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        "aresample=async=1:first_pts=0,volume=1.0[slide];"
        "[tts][slide]amix=inputs=2:duration=longest:dropout_transition=0[audio]",
        "-map",
        "[v]",
        "-map",
        "[audio]",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", "ignore")[-1000:])
    return output_path


async def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-render a slide project to video.")
    parser.add_argument("slide_dir", nargs="?", default="template/kimi-k2-6")
    parser.add_argument("--output-dir")
    parser.add_argument("--size", default=f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}", help="Render size: WIDTHxHEIGHT or WIDTH for 9:16.")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable script subtitle overlay")
    args = parser.parse_args()

    render_width, render_height = parse_render_size(args.size)
    configure_render_geometry(render_width, render_height)

    repo_root = Path(__file__).resolve().parent
    slide_dir = (repo_root / args.slide_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else slide_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    check_render_dependencies()

    timing_file = output_dir / "timing.json"
    tts_path = output_dir / "voiceover_concat.mp3"
    if not timing_file.exists() or not tts_path.exists():
        raise FileNotFoundError("Run generate_tts.py first to create timing.json and voiceover_concat.mp3")

    timing_data = json.loads(timing_file.read_text(encoding="utf-8"))
    await annotate_slide_video_durations(slide_dir, timing_data)
    tts_path = await ensure_voiceover_matches_timing(output_dir, timing_data, tts_path)
    preview_settings = load_preview_settings(slide_dir)
    subtitle_data = None
    subtitles_enabled = preview_settings.get("subtitles", {}).get("enabled", True) is not False
    subtitle_max_lines = int(preview_settings.get("subtitles", {}).get("maxLines", 2) or 2)
    if not args.no_subtitles and subtitles_enabled:
        try:
            subtitle_data = build_karaoke_subtitle_timing(output_dir, timing_data, max_lines=subtitle_max_lines)
            print("=== Subtitles ===\nUsing word-level karaoke captions")
        except Exception as exc:
            subtitle_data = build_script_subtitle_timing(timing_data, max_lines=subtitle_max_lines)
            print(f"=== Subtitles ===\nKaraoke unavailable ({exc.__class__.__name__}: {exc}). Falling back to static captions")
    elif not args.no_subtitles:
        print("=== Subtitles ===\nDisabled by preview-settings.json")

    theme_css = theme_css_from_settings(preview_settings)
    subtitle_css = subtitle_css_from_settings(preview_settings)
    settings_css = "\n".join(part for part in [theme_css, subtitle_css] if part)
    if theme_css:
        print("=== Theme ===\nUsing preview-settings.json")

    recording_html = prepare_recording_html(slide_dir, output_dir, subtitle_data, settings_css, preview_settings)
    reveal_units = await inspect_reveal_units(recording_html)

    print("=== Mapping check ===")
    for idx, item in enumerate(timing_data):
        sentence_count = len(split_sentences(item["text"]))
        reveal_count = reveal_units[idx] if idx < len(reveal_units) else "?"
        print(f"Slide {idx + 1}: {sentence_count} script sentences / {reveal_count} reveal units")

    if not args.skip_validation:
        validate_mapping(timing_data, reveal_units)

    print("\n=== Click timeline ===")
    timeline = build_click_timeline(timing_data, reveal_units)
    for event in timeline:
        print(f"  [{event['time']:6.2f}s] {event['desc']}")

    voiceover_duration = sum(float(item["duration"]) for item in timing_data)
    print(f"\n=== Recording slides (voiceover: {voiceover_duration:.1f}s) ===")
    raw_video, app_audio_path, trim_start = await record_video(recording_html, timeline, output_dir, voiceover_duration)
    print(f"Raw video: {raw_video}")
    print(f"Original slide audio: {app_audio_path}")

    print("\n=== Merging voiceover + original slide audio ===")
    final_video = output_dir / "final_video.mp4"
    await merge_final_video(raw_video, tts_path, app_audio_path, final_video, trim_start)
    duration = await get_duration(final_video)
    print(f"Final video: {final_video} ({duration:.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())
