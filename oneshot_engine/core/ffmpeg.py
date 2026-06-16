"""
core/ffmpeg.py — Mọi thứ liên quan ffmpeg/ffprobe:
run command, probe duration/video info, check audio stream.
"""

import json
import subprocess
from pathlib import Path


def ff_run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """Chạy lệnh shell, trả về CompletedProcess."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def render_audio_track(source: str | Path, output: str | Path,
                       noise_filter: str = "", cover_duration: float = 0.0,
                       timeout: int = 3600) -> subprocess.CompletedProcess:
    """Render AAC audio, optionally prepending silence for a video cover."""
    audio_filter = noise_filter or "anull"
    main_filter = (
        f"[0:a]{audio_filter},aformat=sample_rates=48000:channel_layouts=stereo,"
        "asetpts=PTS-STARTPTS[amain]"
    )
    cmd = ["ffmpeg", "-y", "-i", str(source)]

    if cover_duration > 0:
        cmd.extend([
            "-f", "lavfi", "-t", f"{cover_duration:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-filter_complex",
            f"{main_filter};[1:a]aresample=48000,asetpts=PTS-STARTPTS[acover];"
            "[acover][amain]concat=n=2:v=0:a=1[aout]",
            "-map", "[aout]",
        ])
    else:
        cmd.extend(["-filter_complex", main_filter, "-map", "[amain]"])

    cmd.extend(["-c:a", "aac", "-b:a", "192k", str(output)])
    return ff_run(cmd, timeout=timeout)


def mux_stream_copy(video: str | Path, audio: str | Path, output: str | Path,
                    timeout: int = 600) -> subprocess.CompletedProcess:
    """Mux separately rendered video and audio without re-encoding."""
    return ff_run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c", "copy", "-movflags", "+faststart", str(output),
    ], timeout=timeout)


def duration(path: str | Path) -> float:
    """Lấy duration video bằng ffprobe. Trả về 0.0 nếu lỗi."""
    try:
        r = ff_run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(path)], timeout=120)
        if r.returncode == 0:
            return float(r.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return 0.0


def video_info(path: str | Path) -> dict:
    """Lấy width, height, codec, fps của video stream đầu tiên."""
    try:
        r = ff_run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,codec_name,r_frame_rate",
                    "-of", "json", str(path)], timeout=120)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            s = data.get("streams", [{}])[0]
            w, h = int(s.get("width", 0)), int(s.get("height", 0))
            fps_str = s.get("r_frame_rate", "30/1")
            num, _, den = fps_str.partition("/")
            fps = float(num) / float(den or 1)
            return {"width": w, "height": h, "codec": s.get("codec_name", ""), "fps": round(fps, 2)}
    except Exception:
        pass
    return {}


def has_audio(path: str | Path) -> bool:
    """Kiểm tra video có audio stream không."""
    try:
        r = ff_run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                    "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)], timeout=20)
        return r.returncode == 0 and r.stdout.strip() != ""
    except Exception:
        return False
