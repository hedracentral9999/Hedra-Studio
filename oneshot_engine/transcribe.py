"""
transcribe.py — Chuyên gia transcript.
Chạy faster-whisper local → segments [{start, end, text}].
"""

import re
import threading
from pathlib import Path
from .core import log
from .config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE

_WHISPER_LOCK = threading.Lock()


def transcribe(audio_path: Path) -> list[dict]:
    """
    Chạy Whisper transcript tiếng Việt.
    Trả về list[dict] với keys: start, end, text.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log("⚠ faster_whisper chưa cài. Cài: pip install faster-whisper")
        return []

    log(f"Load Whisper {WHISPER_MODEL_SIZE} ({WHISPER_DEVICE}/{WHISPER_COMPUTE})...")
    with _WHISPER_LOCK:
        model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)

    segments = []
    try:
        segs, _ = model.transcribe(str(audio_path), language="vi", vad_filter=True)
    except Exception:
        log("VAD lỗi, retry không VAD...")
        segs, _ = model.transcribe(str(audio_path), language="vi", vad_filter=False)

    for seg in segs:
        text = re.sub(r"\s+", " ", getattr(seg, "text", "")).strip()
        if text:
            segments.append({
                "start": float(getattr(seg, "start", 0.0)),
                "end": float(getattr(seg, "end", 0.0)),
                "text": text,
            })
    return segments
