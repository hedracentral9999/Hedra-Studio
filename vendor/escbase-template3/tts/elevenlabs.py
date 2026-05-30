from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from .common import generate_project_tts

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "tts.json"
DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
COOLDOWN = 1.0


def full_voiceover_model(model_id: str) -> bool:
    return str(model_id or "").strip() == "eleven_v3"


def text_context_supported(model_id: str) -> bool:
    return not full_voiceover_model(model_id)


def api_safe_config(config: dict) -> dict:
    api_config = dict(config)
    api_config.pop("speed", None)
    if isinstance(api_config.get("voice_settings"), dict):
        settings = dict(api_config["voice_settings"])
        settings.pop("speed", None)
        api_config["voice_settings"] = settings
    return api_config


def full_script_text(lines: list[str]) -> str:
    return "\n\n".join(line.strip() for line in lines if line.strip())


def read_tts_config(config_path: Path | None = None) -> dict:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"TTS config is invalid JSON: {path}") from exc
    return data if isinstance(data, dict) else {}


def write_tts_config(data: dict, config_path: Path | None = None) -> None:
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def elevenlabs_config(config_path: Path | None = None) -> dict:
    config = read_tts_config(config_path)
    data = config.get("elevenlabs", {}) if isinstance(config, dict) else {}
    return data if isinstance(data, dict) else {}


def elevenlabs_public_config(config_path: Path | None = None) -> dict:
    config = elevenlabs_config(config_path)
    return {
        "config_path": str(config_path or DEFAULT_CONFIG_PATH),
        "voice_id": str(config.get("voice_id") or ""),
        "model_id": str(config.get("model_id") or DEFAULT_MODEL_ID),
        "output_format": str(config.get("output_format") or DEFAULT_OUTPUT_FORMAT),
        "api_key_configured": bool(str(config.get("api_key") or os.environ.get("ELEVENLABS_API_KEY") or "").strip()),
    }


def update_elevenlabs_voice_id(voice_id: str, config_path: Path | None = None) -> dict:
    voice_id = str(voice_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", voice_id):
        raise ValueError("Invalid ElevenLabs voice id.")
    config = read_tts_config(config_path)
    elevenlabs = config.get("elevenlabs", {}) if isinstance(config, dict) else {}
    if not isinstance(elevenlabs, dict):
        elevenlabs = {}
    elevenlabs["voice_id"] = voice_id
    elevenlabs.setdefault("model_id", DEFAULT_MODEL_ID)
    elevenlabs.setdefault("output_format", DEFAULT_OUTPUT_FORMAT)
    config["elevenlabs"] = elevenlabs
    write_tts_config(config, config_path)
    return elevenlabs_public_config(config_path)


def elevenlabs_api_key(api_key: str | None = None, config: dict | None = None) -> str:
    key = str(api_key or os.environ.get("ELEVENLABS_API_KEY") or (config or {}).get("api_key") or "").strip()
    if not key:
        raise ValueError("Missing ElevenLabs API key. Set ELEVENLABS_API_KEY or config/tts.json elevenlabs.api_key.")
    return key


def elevenlabs_voice_id(voice: str | None = None, config: dict | None = None) -> str:
    voice_id = str(voice or (config or {}).get("voice_id") or "").strip()
    if not voice_id:
        raise ValueError("Missing ElevenLabs voice id. Pass --voice VOICE_ID or set config/tts.json elevenlabs.voice_id.")
    return voice_id


def voice_settings(config: dict) -> dict:
    raw = config.get("voice_settings", {}) if isinstance(config.get("voice_settings"), dict) else config
    settings = {}
    for key in ("stability", "similarity_boost", "style", "speed"):
        if key in raw and raw[key] not in (None, ""):
            settings[key] = raw[key]
    if "use_speaker_boost" in raw:
        settings["use_speaker_boost"] = bool(raw["use_speaker_boost"])
    return settings


def write_audio_result(audio: object, audio_file: Path) -> None:
    if isinstance(audio, (bytes, bytearray)):
        audio_file.write_bytes(bytes(audio))
        return
    with audio_file.open("wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)


def request_elevenlabs_audio(
    text: str,
    audio_file: Path,
    *,
    api_key: str,
    voice_id: str,
    model_id: str,
    output_format: str,
    config: dict,
    previous_text: str | None = None,
    next_text: str | None = None,
) -> None:
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as exc:
        raise RuntimeError("Missing ElevenLabs SDK. Install requirements with: pip install -r requirements.txt") from exc

    elevenlabs = ElevenLabs(api_key=api_key)
    kwargs = {
        "text": text,
        "voice_id": voice_id,
        "model_id": model_id,
        "output_format": output_format,
    }
    if previous_text:
        kwargs["previous_text"] = previous_text
    if next_text:
        kwargs["next_text"] = next_text
    settings = voice_settings(config)
    if settings:
        try:
            from elevenlabs import VoiceSettings

            kwargs["voice_settings"] = VoiceSettings(**settings)
        except Exception:
            kwargs["voice_settings"] = settings
    try:
        audio = elevenlabs.text_to_speech.convert(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"ElevenLabs API failed: {exc}") from exc
    write_audio_result(audio, audio_file)


async def generate_elevenlabs_full_audio(
    slide_dir: Path,
    output_dir: Path,
    lines: list[str],
    *,
    voice: str | None = None,
    model_id: str | None = None,
    output_format: str | None = None,
    api_key: str | None = None,
    config_path: Path | None = None,
    full_text: str | None = None,
    force: bool = False,
) -> Path:
    del slide_dir
    config = dict(elevenlabs_config(config_path))
    api_config = api_safe_config(config)
    resolved_key = elevenlabs_api_key(api_key, config)
    resolved_voice = elevenlabs_voice_id(voice, config)
    resolved_model = str(model_id or config.get("model_id") or DEFAULT_MODEL_ID).strip()
    resolved_output_format = str(output_format or config.get("output_format") or DEFAULT_OUTPUT_FORMAT).strip()
    text = full_text if full_text is not None else full_script_text(lines)
    if not text.strip():
        raise ValueError("No script text to send to ElevenLabs.")

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_file = output_dir / "elevenlabs_full_voiceover.mp3"
    meta_file = output_dir / "elevenlabs_full_voiceover.meta.json"
    metadata = {
        "engine": "elevenlabs",
        "mode": "full_voiceover",
        "text": text,
        "lines": lines,
        "voice_id": resolved_voice,
        "model_id": resolved_model,
        "output_format": resolved_output_format,
        "voice_settings": voice_settings(api_config),
    }
    cache_matches = False
    if meta_file.exists():
        try:
            cache_matches = json.loads(meta_file.read_text(encoding="utf-8")) == metadata
        except json.JSONDecodeError:
            cache_matches = False
    if not force and cache_matches and audio_file.exists() and audio_file.stat().st_size > 0:
        print(f"Full ElevenLabs TTS: {audio_file} (cached)")
        return audio_file

    if audio_file.exists():
        audio_file.unlink()
    print(
        f"Voice: ElevenLabs {resolved_voice} "
        f"({resolved_model}, {resolved_output_format}, full script in one request)"
    )
    print(f"Sending full script to ElevenLabs: {len(lines)} slides, {len(text)} chars")
    await asyncio.to_thread(
        request_elevenlabs_audio,
        text,
        audio_file,
        api_key=resolved_key,
        voice_id=resolved_voice,
        model_id=resolved_model,
        output_format=resolved_output_format,
        config=api_config,
    )
    meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Full ElevenLabs TTS saved: {audio_file}")
    return audio_file


async def generate_elevenlabs_tts(
    slide_dir: Path,
    output_dir: Path,
    lines: list[str],
    *,
    voice: str | None = None,
    model_id: str | None = None,
    output_format: str | None = None,
    speed: float | None = None,
    api_key: str | None = None,
    config_path: Path | None = None,
    force: bool = False,
) -> None:
    config = dict(elevenlabs_config(config_path))
    api_config = api_safe_config(config)
    post_process_speed = float(speed) if speed is not None else 1.0
    resolved_key = elevenlabs_api_key(api_key, config)
    resolved_voice = elevenlabs_voice_id(voice, config)
    resolved_model = str(model_id or config.get("model_id") or DEFAULT_MODEL_ID).strip()
    resolved_output_format = str(output_format or config.get("output_format") or DEFAULT_OUTPUT_FORMAT).strip()
    use_text_context = text_context_supported(resolved_model)
    context_note = "context on" if use_text_context else "context off for this model"
    print(f"Voice: ElevenLabs {resolved_voice} ({resolved_model}, {resolved_output_format}, ffmpeg speed {post_process_speed:g}x, {context_note})")

    def context_for(index: int) -> tuple[str | None, str | None]:
        if not use_text_context:
            return None, None
        previous_text = lines[index - 1] if index > 0 else None
        next_text = lines[index + 1] if index < len(lines) - 1 else None
        return previous_text, next_text

    async def line_generator(index: int, text: str, audio_file: Path, subtitle_file: Path) -> None:
        previous_text, next_text = context_for(index)
        await asyncio.to_thread(
            request_elevenlabs_audio,
            text,
            audio_file,
            api_key=resolved_key,
            voice_id=resolved_voice,
            model_id=resolved_model,
            output_format=resolved_output_format,
            config=api_config,
            previous_text=previous_text,
            next_text=next_text,
        )

    def cache_metadata(index: int, text: str) -> dict:
        previous_text, next_text = context_for(index)
        return {
            "engine": "elevenlabs",
            "text": text,
            "voice_id": resolved_voice,
            "model_id": resolved_model,
            "output_format": resolved_output_format,
            "voice_settings": voice_settings(api_config),
            "text_context": use_text_context,
            "previous_text": previous_text,
            "next_text": next_text,
            "ffmpeg_speed": f"{post_process_speed:.6g}",
        }

    await generate_project_tts(
        slide_dir,
        output_dir,
        lines,
        line_generator,
        force=force,
        cooldown=float(config.get("cooldown") or COOLDOWN),
        post_process_speed=post_process_speed,
        cache_metadata=cache_metadata,
    )
