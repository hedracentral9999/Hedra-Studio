#!/usr/bin/env python3
"""Unified script to generate Edge TTS audio (with speed adjustment) and render the video.

Usage:
    python3 render_edgetts.py <slide-dir> [--speed 1.1]

Example:
    python3 render_edgetts.py slide/openclaw-2026-4-29-release --speed 1.1
"""

import argparse
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Generate Edge TTS audio with speed adjustment and render the video.")
    parser.add_argument("slide_dir", help="Path to the slide directory")
    parser.add_argument("--speed", type=float, default=1.1, help="Speedup factor (default: 1.1)")
    parser.add_argument("--size", default="1080x1920", help="Render size passed to auto_render.py (default: 1080x1920)")
    parser.add_argument("--voice", default="vi-VN-HoaiMyNeural", help="Edge TTS Voice")
    parser.add_argument("--edge-mode", choices=["full", "per-slide"], default="full", help="Edge TTS mode (default: full)")
    parser.add_argument("--per-slide", action="store_true", help="Generate Edge TTS per slide instead of full script")
    parser.add_argument("--force", action="store_true", help="Force regenerate audio")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable script subtitle overlay")
    args = parser.parse_args()

    slide_dir = Path(args.slide_dir).resolve()

    if not slide_dir.exists():
        print(f"❌ Error: Slide directory {slide_dir} does not exist.")
        sys.exit(1)

    repo_root = Path(__file__).resolve().parent

    # Calculate Edge TTS rate percentage
    # Example: 1.1 -> +10%, 1.25 -> +25%, 0.9 -> -10%
    percentage = int(round((args.speed - 1.0) * 100))
    rate_str = f"+{percentage}%" if percentage >= 0 else f"{percentage}%"

    # 1. Generate Edge TTS
    edge_mode = "per-slide" if args.per_slide else args.edge_mode
    print(f"\n=== 1. Generating Edge TTS (Voice: {args.voice}, Rate: {rate_str}, Mode: {edge_mode}) ===")
    cmd_tts = [
        sys.executable, str(repo_root / "generate_tts.py"),
        str(slide_dir),
        "--engine", "edge-tts",
        "--voice", args.voice,
        "--rate", rate_str,
        "--edge-mode", edge_mode,
    ]
    if args.force:
        cmd_tts.append("--force")
        
    try:
        subprocess.run(cmd_tts, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during generate_tts: {e}")
        sys.exit(1)

    # 2. Auto render
    print("\n=== 2. Running auto_render.py ===")
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

    print(f"\n🎉 All done! Video rendered successfully at speed {args.speed}x.")

if __name__ == "__main__":
    main()
