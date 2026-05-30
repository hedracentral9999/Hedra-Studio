from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
from pathlib import Path
from typing import Any, Awaitable, Callable

from slide_media import discover_slide_videos

LineGenerator = Callable[[int, str, Path, Path], Awaitable[None] | None]
CacheMetadataBuilder = Callable[[int, str], dict[str, Any]]


async def get_duration(audio_file: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(audio_file),
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
            print(f"🎥 Slide {slide_idx + 1} video: {duration:.2f}s -> {path.relative_to(slide_dir)}")
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


def normalize_speed(speed: float | None) -> float:
    if speed is None:
        return 1.0
    value = float(speed)
    if value <= 0:
        raise ValueError("Audio speed must be greater than 0.")
    return value


def speed_cache_value(speed: float) -> str:
    return f"{speed:.6g}"


def speed_adjust_audio(input_file: Path, output_file: Path, speed: float) -> None:
    tmp_file = output_file.with_name(f"{output_file.stem}.speed-tmp{output_file.suffix}")
    if tmp_file.exists():
        tmp_file.unlink()
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_file),
                "-filter:a",
                f"atempo={speed_cache_value(speed)}",
                "-vn",
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(tmp_file),
            ],
            check=True,
            capture_output=True,
        )
        tmp_file.replace(output_file)
    finally:
        if tmp_file.exists():
            tmp_file.unlink()


def concat_line_audio(output_dir: Path, num_lines: int, padding_by_slide: dict[int, float] | None = None) -> Path:
    list_file = output_dir / "concat_list.txt"
    lines = []
    padding_by_slide = padding_by_slide or {}
    for i in range(num_lines):
        lines.append(f"file 'line_{i}.mp3'\n")
        padding = float(padding_by_slide.get(i, 0))
        if padding > 0.05:
            lines.append(f"file 'silence_{i}.mp3'\n")

    list_file.write_text("".join(lines), encoding="utf-8")

    concat_file = output_dir / "voiceover_concat.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(concat_file),
        ],
        check=True,
    )
    return concat_file


def read_script_lines(script_path: Path) -> list[str]:
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script file: {script_path}")
    lines = [line.strip() for line in script_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"No script lines found in {script_path}")
    return lines


def write_line_srt(subtitle_file: Path, text: str, duration: float) -> None:
    millis = max(1, int(duration * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    subtitle_file.write_text(
        f"1\n00:00:00,000 --> {hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}\n{text}\n",
        encoding="utf-8",
    )


async def maybe_await(value: Awaitable[None] | None) -> None:
    if inspect.isawaitable(value):
        await value


async def generate_project_tts(
    slide_dir: Path,
    output_dir: Path,
    lines: list[str],
    line_generator: LineGenerator,
    *,
    force: bool = False,
    cooldown: float = 5.0,
    post_process_speed: float | None = None,
    cache_metadata: CacheMetadataBuilder | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    line_durations = []
    video_durations = await get_slide_video_durations(slide_dir)
    speed = normalize_speed(post_process_speed)
    use_post_speed = abs(speed - 1.0) > 0.001

    demo_video = slide_dir / "demo.mp4"
    if demo_video.exists():
        demo_duration = await get_duration(demo_video)
        video_durations[0] = max(video_durations.get(0, 0.0), demo_duration)
        print(f"🎥 Slide 1 demo.mp4: {demo_duration:.2f}s -> demo.mp4")

    print("=== Generating per-slide TTS ===")
    padding_by_slide: dict[int, float] = {}
    for i, line in enumerate(lines):
        audio_file = output_dir / f"line_{i}.mp3"
        srt_file = output_dir / f"line_{i}.srt"
        text_cache_file = output_dir / f"line_{i}.txt"
        meta_cache_file = output_dir / f"line_{i}.meta.json"
        text_cache_matches = text_cache_file.exists() and text_cache_file.read_text(encoding="utf-8") == line
        expected_meta = cache_metadata(i, line) if cache_metadata else None
        meta_cache_matches = False
        if expected_meta is not None and meta_cache_file.exists():
            try:
                meta_cache_matches = json.loads(meta_cache_file.read_text(encoding="utf-8")) == expected_meta
            except json.JSONDecodeError:
                meta_cache_matches = False
        elif expected_meta is None:
            meta_cache_matches = text_cache_matches

        if not force and meta_cache_matches and audio_file.exists() and audio_file.stat().st_size > 0:
            original_duration = await get_duration(audio_file)
            print(f"Slide {i + 1} TTS: {original_duration:.2f}s -> {audio_file} (cached)")
        else:
            if srt_file.exists():
                srt_file.unlink()
            generation_file = output_dir / f"line_{i}.raw.mp3" if use_post_speed else audio_file
            if generation_file.exists():
                generation_file.unlink()
            await maybe_await(line_generator(i, line, generation_file, srt_file))
            if use_post_speed:
                speed_adjust_audio(generation_file, audio_file, speed)
                generation_file.unlink(missing_ok=True)
                if srt_file.exists():
                    srt_file.unlink()
                print(f"  ↳ FFmpeg speed {speed_cache_value(speed)}x -> {audio_file}")
            text_cache_file.write_text(line, encoding="utf-8")
            if expected_meta is not None:
                meta_cache_file.write_text(json.dumps(expected_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            original_duration = await get_duration(audio_file)
            print(f"Slide {i + 1} TTS: {original_duration:.2f}s -> {audio_file}")

        if not srt_file.exists() or srt_file.stat().st_size == 0:
            write_line_srt(srt_file, line, original_duration)

        duration = original_duration
        video_duration = video_durations.get(i, 0.0)
        if video_duration > original_duration:
            padding = video_duration - original_duration
            padding_by_slide[i] = padding
            duration = video_duration
            write_silence_file(output_dir, f"silence_{i}.mp3", padding)
            print(f"  ↳ Slide {i + 1} total duration uses video: {duration:.2f}s (+{padding:.2f}s silence)")

        line_durations.append(
            {
                "line": i,
                "duration": duration,
                "original_audio_duration": original_duration,
                "video_duration": video_duration,
                "text": line,
            }
        )

        if i < len(lines) - 1:
            await asyncio.sleep(cooldown)

    timing_file = output_dir / "timing.json"
    timing_file.write_text(json.dumps(line_durations, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Concatenating per-slide audio ===")
    concat_file = concat_line_audio(output_dir, len(lines), padding_by_slide)
    concat_duration = await get_duration(concat_file)
    print(f"Concatenated voiceover: {concat_duration:.2f}s -> {concat_file}")
