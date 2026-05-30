#!/usr/bin/env python3
"""Generate per-slide TTS audio for a slide project."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from tts.common import read_script_lines, speed_adjust_audio, speed_cache_value
from tts.edge import DEFAULT_RATE, DEFAULT_VOICE, generate_edge_full_audio, generate_edge_tts
from tts.elevenlabs import (
    DEFAULT_MODEL_ID,
    elevenlabs_config,
    full_voiceover_model,
    generate_elevenlabs_full_audio,
    generate_elevenlabs_tts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate voiceover audio for script-90s.txt.")
    parser.add_argument("slide_dir", nargs="?", default="template/kimi-k2-6")
    parser.add_argument("--engine", choices=["edge", "edgetts", "edge-tts", "elevenlabs"], default="edge")
    parser.add_argument("--voice", help="Edge voice name or ElevenLabs voice_id")
    parser.add_argument("--rate", default=DEFAULT_RATE, help="Edge TTS rate, e.g. +10%%")
    parser.add_argument("--edge-mode", choices=["full", "per-slide"], default="full", help="Edge TTS mode (default: full)")
    parser.add_argument("--model-id", help="ElevenLabs model id")
    parser.add_argument("--output-format", help="ElevenLabs output format")
    parser.add_argument("--voice-speed", type=float, help="ElevenLabs API audio ffmpeg speed after generation")
    parser.add_argument("--api-key", help="ElevenLabs API key. Prefer ELEVENLABS_API_KEY or config/tts.json.")
    parser.add_argument("--config", help="Path to TTS config JSON. Defaults to config/tts.json for ElevenLabs.")
    parser.add_argument("--output-dir")
    parser.add_argument("--force", action="store_true", help="Re-generate even if audio files exist")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent
    slide_dir = (repo_root / args.slide_dir).resolve()
    script_path = slide_dir / "script-90s.txt"
    output_dir = Path(args.output_dir).resolve() if args.output_dir else slide_dir / "output"
    lines = read_script_lines(script_path)
    engine = str(args.engine or "edge").lower()

    if engine in {"edge", "edgetts", "edge-tts"}:
        if args.edge_mode == "full":
            full_audio = await generate_edge_full_audio(
                slide_dir,
                output_dir,
                lines,
                voice=args.voice or DEFAULT_VOICE,
                rate=args.rate,
                full_text=script_path.read_text(encoding="utf-8"),
                force=args.force,
            )
            print("\n=== Splitting full Edge TTS voiceover like uploaded audio ===")
            try:
                subprocess.run(
                    [
                        sys.executable,
                        str(repo_root / "split_voiceover.py"),
                        str(slide_dir),
                        str(full_audio),
                        "--output-dir",
                        str(output_dir),
                    ],
                    check=True,
                )
                return
            except subprocess.CalledProcessError as exc:
                print(f"⚠ Full Edge split failed ({exc}). Falling back to per-slide Edge TTS.")

        await generate_edge_tts(
            slide_dir,
            output_dir,
            lines,
            voice=args.voice or DEFAULT_VOICE,
            rate=args.rate,
            force=args.force,
        )
        return

    if engine == "elevenlabs":
        config_path = Path(args.config).resolve() if args.config else None
        config = elevenlabs_config(config_path)
        resolved_model = str(args.model_id or config.get("model_id") or DEFAULT_MODEL_ID).strip()
        if full_voiceover_model(resolved_model):
            full_audio = await generate_elevenlabs_full_audio(
                slide_dir,
                output_dir,
                lines,
                voice=args.voice,
                model_id=args.model_id,
                output_format=args.output_format,
                api_key=args.api_key,
                config_path=config_path,
                full_text=script_path.read_text(encoding="utf-8"),
                force=args.force,
            )
            split_audio = full_audio
            speed = float(args.voice_speed) if args.voice_speed else 1.0
            if abs(speed - 1.0) > 0.001:
                split_audio = output_dir / f"{full_audio.stem}_{speed_cache_value(speed)}x.mp3"
                speed_adjust_audio(full_audio, split_audio, speed)
                print(f"FFmpeg speed {speed_cache_value(speed)}x -> {split_audio}")

            print("\n=== Splitting full ElevenLabs voiceover like uploaded audio ===")
            subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "split_voiceover.py"),
                    str(slide_dir),
                    str(split_audio),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
            )
            return

        await generate_elevenlabs_tts(
            slide_dir,
            output_dir,
            lines,
            voice=args.voice,
            model_id=args.model_id,
            output_format=args.output_format,
            speed=args.voice_speed,
            api_key=args.api_key,
            config_path=config_path,
            force=args.force,
        )
        return

    raise ValueError("Unsupported TTS engine.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        raise SystemExit(1)
