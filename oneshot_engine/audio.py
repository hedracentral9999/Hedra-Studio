"""
audio.py — Chuyên gia tách audio.
Trích xuất audio track từ video → WAV 16kHz mono.
"""

from pathlib import Path
from .core.ffmpeg import ff_run, has_audio


def extract_audio(source: Path, audio_path: Path, timeout: int = 600) -> bool:
    """
    Tách audio từ video thành WAV 16kHz mono.
    Trả về True nếu thành công.
    """
    try:
        r = ff_run([
            "ffmpeg", "-y", "-i", str(source),
            "-vn", "-ac", "1", "-ar", "16000",
            str(audio_path)
        ], timeout=timeout)
        return r.returncode == 0 and audio_path.exists()
    except Exception:
        return False


def check_audio(source: Path) -> tuple[bool, str]:
    """
    Kiểm tra video có audio stream không (dùng ffprobe, không extract).
    Returns: (has_stream, message)
    """
    if has_audio(source):
        return True, "không tách được audio — vẫn render nhưng không transcript"
    return False, "video không có audio track — có thể quên bật mic"
