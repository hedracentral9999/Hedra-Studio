#!/usr/bin/env python3
"""Split a single voiceover audio file into per-slide segments using Whisper.

Usage:
    python3 split_voiceover.py <slide-dir> <audio-file>

Example:
    python3 split_voiceover.py slide/vu-kien-elon-openai ~/Downloads/elevenlabs.mp3

Requirements:
    pip install faster-whisper
"""

import argparse
import asyncio
from difflib import SequenceMatcher
import json
import re
import shutil
import subprocess
from pathlib import Path

from slide_media import discover_slide_videos


# ============================================
# UTILS
# ============================================

async def get_duration(media_file: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
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
            print(f"🎥 Slide {slide_idx + 1} video: {duration:.2f}s -> {path.relative_to(slide_dir)}")
        if slide_durations:
            durations[slide_idx] = max(slide_durations)
    return durations


def write_silence_file(output_dir: Path, name: str, duration: float) -> Path:
    silence_file = output_dir / name
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono",
            "-t", f"{duration:.3f}",
            "-q:a", "9",
            "-acodec", "libmp3lame",
            str(silence_file),
        ],
        check=True,
        capture_output=True,
    )
    return silence_file


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, strip punctuation."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_word(word: str) -> str:
    """Normalize a single word for comparison."""
    word = word.lower().strip()
    word = re.sub(r"[^\w]", "", word)
    return word


# ============================================
# WHISPER TRANSCRIPTION (with retry)
# ============================================

MAX_RETRIES = 3

WHISPER_MODEL_ESCALATION = ["base", "small", "medium"]


def transcribe_with_whisper(
    audio_file: Path,
    model_size: str = "base",
    language: str = "vi",
) -> list[dict]:
    """Transcribe audio using faster-whisper and return word-level timestamps.

    Returns list of {"word": str, "start": float, "end": float}
    """
    from faster_whisper import WhisperModel

    print(f"  Loading Whisper model '{model_size}'...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("  Transcribing audio...")
    segments, info = model.transcribe(
        str(audio_file),
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                words.append({
                    "word": w.word.strip(),
                    "start": w.start,
                    "end": w.end,
                })

    print(f"  Transcribed {len(words)} words (language: {info.language})")
    return words


def transcribe_with_retry(
    audio_file: Path,
    model_size: str,
    language: str,
    min_words: int,
) -> list[dict]:
    """Try transcription up to MAX_RETRIES times, escalating model size if needed."""
    # Build list of models to try: start with requested, then escalate
    models_to_try = [model_size]
    for m in WHISPER_MODEL_ESCALATION:
        if m not in models_to_try:
            models_to_try.append(m)
    models_to_try = models_to_try[:MAX_RETRIES]

    last_error = None
    for attempt, model in enumerate(models_to_try, 1):
        try:
            print(f"\n--- Attempt {attempt}/{MAX_RETRIES} (model: {model}) ---")
            words = transcribe_with_whisper(audio_file, model, language)

            if len(words) < min_words:
                print(f"  ⚠ Only {len(words)} words detected (need ≥{min_words})")
                if attempt < len(models_to_try):
                    print("  Retrying with larger model...")
                    continue
                else:
                    print("  Using best result available.")

            return words

        except Exception as exc:
            last_error = exc
            print(f"  ⚠ Failed: {exc.__class__.__name__}: {exc}")
            if attempt < len(models_to_try):
                print("  Retrying...")
            else:
                raise RuntimeError(
                    f"Whisper failed after {MAX_RETRIES} attempts. Last error: {last_error}"
                ) from last_error

    # Should not reach here, but just in case
    raise RuntimeError(f"Whisper failed after {MAX_RETRIES} attempts")


# ============================================
# ALIGNMENT
# ============================================

def align_words_to_lines(
    words: list[dict],
    script_lines: list[str],
) -> list[float]:
    """Match transcript words to script lines and return split timestamps.

    Returns a list of N-1 split points for N script lines. Each split point is
    the start timestamp of the next script line in the Whisper transcript.
    """
    line_words = []
    for line in script_lines:
        normalized = normalize_text(line).split()
        line_words.append(normalized)

    total_script_words = sum(len(lw) for lw in line_words)
    total_transcript_words = len(words)
    print(f"  Script words: {total_script_words}")
    print(f"  Transcript words: {total_transcript_words}")

    split_points = []
    word_idx = 0
    script_word_cursor = 0

    for line_idx, lw in enumerate(line_words):
        if line_idx == len(line_words) - 1:
            break

        script_word_cursor += len(lw)
        ratio = total_transcript_words / max(total_script_words, 1)
        target_start_idx = max(1, int(script_word_cursor * ratio))

        best_score = -1
        next_line_words = line_words[line_idx + 1] if line_idx + 1 < len(line_words) else []
        check_count = min(10, len(next_line_words))
        search_radius = max(60, len(lw), check_count * 6)
        search_start = max(word_idx + 1, target_start_idx - search_radius)
        search_end = min(len(words) - 1, target_start_idx + search_radius)
        best_split_idx = min(max(target_start_idx, search_start), search_end)

        if check_count > 0 and search_start <= search_end:
            script_head = next_line_words[:check_count]
            for split_idx in range(search_start, search_end + 1):
                if split_idx + 1 >= len(words):
                    break
                transcript_window = [
                    normalize_word(words[split_idx + k]["word"])
                    for k in range(min(check_count + 4, len(words) - split_idx))
                ]
                positional_score = 0
                for k, sw in enumerate(script_head):
                    if k >= len(transcript_window):
                        break
                    tw = transcript_window[k]
                    if tw == sw:
                        positional_score += 3
                    elif tw and sw and (tw in sw or sw in tw):
                        positional_score += 1
                sequence_score = SequenceMatcher(None, script_head, transcript_window).ratio() * check_count * 2
                first_word_score = 0
                if transcript_window and script_head:
                    tw = transcript_window[0]
                    sw = script_head[0]
                    if tw == sw:
                        first_word_score = 6
                    elif tw and sw and (tw in sw or sw in tw):
                        first_word_score = 2
                distance_penalty = abs(split_idx - target_start_idx) * 0.015
                score = positional_score + sequence_score + first_word_score - distance_penalty
                if score > best_score:
                    best_score = score
                    best_split_idx = split_idx

        if best_split_idx > 0 and best_split_idx < len(words):
            split_time = words[best_split_idx]["start"]
        else:
            split_time = words[min(best_split_idx, len(words) - 1)]["start"]

        matched_words = " ".join(words[i]["word"] for i in range(best_split_idx, min(best_split_idx + 5, len(words))))
        print(
            f"    Match line {line_idx+2} start near word {best_split_idx} "
            f"at {split_time:.2f}s (score {best_score:.1f}): {matched_words}"
        )
        split_points.append(split_time)
        word_idx = best_split_idx

    return split_points


def detect_silences(audio_file: Path, noise: str, min_duration: float) -> list[tuple[float, float, float]]:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner",
            "-i", str(audio_file),
            "-af", f"silencedetect=noise={noise}:d={min_duration}",
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    silences = []
    start = None
    for line in proc.stderr.splitlines():
        start_match = re.search(r"silence_start: ([0-9.]+)", line)
        if start_match:
            start = float(start_match.group(1))
        end_match = re.search(r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)", line)
        if end_match and start is not None:
            end = float(end_match.group(1))
            duration = float(end_match.group(2))
            silences.append((start, end, duration))
            start = None
    return silences


def snap_split_points_to_speech_starts(
    split_points: list[float],
    silences: list[tuple[float, float, float]],
    max_distance: float,
) -> list[float]:
    if not silences:
        print("  ⚠ No silence intervals detected; keeping Whisper split points.")
        return split_points

    snapped_points = []
    for idx, point in enumerate(split_points):
        best = None
        for start, end, duration in silences:
            if start <= point <= end:
                distance = 0.0
            elif point < start:
                distance = start - point
            else:
                distance = point - end
            candidate = (distance, -duration, start, end, duration)
            if best is None or candidate < best:
                best = candidate

        if best is None or best[0] > max_distance:
            snapped = point
            print(f"    Line {idx+1} → {idx+2}: keep {point:.2f}s (no nearby silence)")
        else:
            _, _, start, end, duration = best
            snapped = end
            previous_limit = snapped_points[-1] + 0.15 if snapped_points else 0.0
            next_original = split_points[idx + 1] if idx + 1 < len(split_points) else float("inf")
            if snapped <= previous_limit or snapped >= next_original - 0.15:
                snapped = point
                print(f"    Line {idx+1} → {idx+2}: keep {point:.2f}s (snap would break order)")
            else:
                print(
                    f"    Line {idx+1} → {idx+2}: {point:.2f}s → {snapped:.2f}s "
                    f"(speech starts after silence {start:.2f}-{end:.2f}s, {duration:.2f}s)"
                )
        snapped_points.append(snapped)

    return snapped_points


# ============================================
# AUDIO SPLITTING
# ============================================

def split_audio(
    audio_file: Path,
    split_points: list[float],
    output_dir: Path,
    total_duration: float,
) -> list[Path]:
    """Split audio at the given time points into separate MP3 files."""
    boundaries = [0.0] + split_points + [total_duration]
    output_files = []

    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        duration = boundaries[i + 1] - start
        out = output_dir / f"line_{i}.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(audio_file),
            "-ss", f"{start:.3f}",
            "-t", f"{duration:.3f}",
            "-af", "aresample=async=1",
            "-sample_fmt", "s16p",
            "-c:a", "libmp3lame",
            "-q:a", "2",
            str(out),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        output_files.append(out)

    return output_files


def concat_segments(output_dir: Path, num_segments: int, padding_by_slide: dict[int, float] | None = None) -> Path:
    """Concatenate per-slide audio files into voiceover_concat.mp3."""
    list_file = output_dir / "concat_list.txt"
    lines = []
    padding_by_slide = padding_by_slide or {}
    for i in range(num_segments):
        lines.append(f"file 'line_{i}.mp3'\n")
        padding = float(padding_by_slide.get(i, 0))
        if padding > 0.05:
            lines.append(f"file 'silence_{i}.mp3'\n")
            
    list_file.write_text("".join(lines), encoding="utf-8")
    concat_file = output_dir / "voiceover_concat.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(list_file), "-c:a", "libmp3lame", "-q:a", "2", str(concat_file)],
        check=True,
        capture_output=True,
    )
    return concat_file


# ============================================
# MAIN
# ============================================

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split a single voiceover audio into per-slide segments using Whisper."
    )
    parser.add_argument("slide_dir", help="Path to the slide directory")
    parser.add_argument("audio_file", help="Path to the full voiceover audio file")
    parser.add_argument("--output-dir", help="Output directory (default: <slide_dir>/output)")
    parser.add_argument("--model", default="base",
                        help="Whisper model size: tiny/base/small/medium/large (default: base)")
    parser.add_argument("--language", default="vi", help="Audio language (default: vi)")
    parser.add_argument("--no-speech-start-snap", action="store_true", help="Keep raw Whisper split points")
    parser.add_argument("--silence-noise", default="-35dB", help="ffmpeg silencedetect noise threshold")
    parser.add_argument("--silence-min-duration", type=float, default=0.18, help="Minimum silence duration")
    parser.add_argument("--silence-max-distance", type=float, default=0.9, help="Max seconds from split point to nearby silence")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    slide_dir = (repo_root / args.slide_dir).resolve()
    audio_file = Path(args.audio_file).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else slide_dir / "output"

    script_path = slide_dir / "script-90s.txt"
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script file: {script_path}")
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    lines = [l.strip() for l in script_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    num_slides = len(lines)
    print(f"Script has {num_slides} slides")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy/convert original audio
    full_audio = output_dir / "full_voiceover.mp3"
    if audio_file.suffix.lower() == ".mp3":
        shutil.copy2(audio_file, full_audio)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_file),
             "-c:a", "libmp3lame", "-q:a", "2", str(full_audio)],
            check=True,
        )

    total_duration = await get_duration(full_audio)
    print(f"Total duration: {total_duration:.2f}s")

    # Whisper transcription with retry
    print("\n=== Whisper transcription ===")
    words = transcribe_with_retry(audio_file, args.model, args.language, min_words=num_slides)

    # Align transcript to script
    print("\n=== Aligning transcript to script ===")
    split_points = align_words_to_lines(words, lines)
    if not args.no_speech_start_snap:
        print("\n=== Snapping split points to speech starts ===")
        silences = detect_silences(full_audio, args.silence_noise, args.silence_min_duration)
        print(f"  Detected {len(silences)} silence intervals")
        split_points = snap_split_points_to_speech_starts(split_points, silences, args.silence_max_distance)

    print(f"\n  Final split points ({len(split_points)}):")
    for i, pt in enumerate(split_points):
        print(f"    Line {i+1} → {i+2}: split at {pt:.2f}s")

    # Split audio
    print(f"\n=== Splitting audio into {num_slides} segments ===")
    segment_files = split_audio(audio_file, split_points, output_dir, total_duration)

    video_durations = await get_slide_video_durations(slide_dir)

    # Check for demo.mp4
    demo_video = slide_dir / "demo.mp4"
    if demo_video.exists():
        demo_duration = await get_duration(demo_video)
        video_durations[0] = max(video_durations.get(0, 0.0), demo_duration)
        print(f"🎥 Slide 1 demo.mp4: {demo_duration:.2f}s -> demo.mp4")

    line_durations = []
    for i, (seg_file, text) in enumerate(zip(segment_files, lines)):
        original_duration = await get_duration(seg_file)
        duration = original_duration
        video_duration = video_durations.get(i, 0.0)
        if video_duration > original_duration + 0.05:
            print(
                f"  Slide {i+1}: {duration:.2f}s voice → {seg_file.name} "
                f"(video {video_duration:.2f}s, render keeps voice timing)"
            )
        else:
            print(f"  Slide {i+1}: {duration:.2f}s → {seg_file.name}")
        line_durations.append({
            "line": i,
            "duration": duration,
            "original_audio_duration": original_duration,
            "video_duration": video_duration,
            "text": text
        })

    timing_file = output_dir / "timing.json"
    timing_file.write_text(
        json.dumps(line_durations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ Timing saved: {timing_file}")

    # Concatenate
    print("\n=== Creating voiceover_concat.mp3 ===")
    concat_file = concat_segments(output_dir, num_slides)
    concat_duration = await get_duration(concat_file)
    print(f"Concatenated: {concat_duration:.2f}s → {concat_file}")

    print(f"\n🎬 Done! Now run:")
    print(f"   python3 auto_render.py {args.slide_dir}")


if __name__ == "__main__":
    asyncio.run(main())
