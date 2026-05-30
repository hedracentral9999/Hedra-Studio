#!/usr/bin/env python3
"""Unified script to process ElevenLabs audio (speed up) and render the video.

Usage:
    python3 render_elevenlabs.py <slide-dir> <audio-file> [--speed 1.1]

Example:
    python3 render_elevenlabs.py slide/openclaw-2026-4-29-release ~/Downloads/voiceover.mp3
"""

import argparse
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Render video from ElevenLabs audio with speed adjustment.")
    parser.add_argument("slide_dir", help="Path to the slide directory")
    parser.add_argument("audio_file", help="Path to the ElevenLabs audio file")
    parser.add_argument("--speed", type=float, default=1.1, help="Speedup factor (default: 1.1)")
    parser.add_argument("--size", default="1080x1920", help="Render size passed to auto_render.py (default: 1080x1920)")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable script subtitle overlay")
    args = parser.parse_args()

    slide_dir = Path(args.slide_dir).resolve()
    audio_file = Path(args.audio_file).resolve()

    if not slide_dir.exists():
        print(f"❌ Error: Slide directory {slide_dir} does not exist.")
        sys.exit(1)

    if not audio_file.exists():
        print(f"❌ Error: Audio file {audio_file} does not exist.")
        sys.exit(1)

    repo_root = Path(__file__).resolve().parent

    # 1. Speed up audio
    print(f"\n=== 1. Speeding up audio by {args.speed}x ===")
    output_dir = slide_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    sped_up_audio = output_dir / f"{audio_file.stem}_{args.speed}x.mp3"
    
    cmd_speed = [
        "ffmpeg", "-y",
        "-i", str(audio_file),
        "-filter:a", f"atempo={args.speed}",
        str(sped_up_audio)
    ]
    
    try:
        subprocess.run(cmd_speed, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"✅ Saved sped-up audio to {sped_up_audio.name}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during audio speedup: {e}")
        sys.exit(1)

    # 2. Split voiceover
    print("\n=== 2. Running split_voiceover.py ===")
    cmd_split = [
        sys.executable, str(repo_root / "split_voiceover.py"),
        str(slide_dir), str(sped_up_audio)
    ]
    try:
        subprocess.run(cmd_split, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during split_voiceover: {e}")
        sys.exit(1)

    # 3. Auto render
    print("\n=== 3. Running auto_render.py ===")
    cmd_render = [
        sys.executable, str(repo_root / "auto_render.py"),
        str(slide_dir),
        "--size", args.size,
    ]
    if args.no_subtitles:
        cmd_render.append("--no-subtitles")
    try:
        subprocess.run(cmd_render, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during auto_render: {e}")
        sys.exit(1)

    print("\n🎉 All done! Video rendered successfully.")

if __name__ == "__main__":
    main()
