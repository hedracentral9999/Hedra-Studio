"""
config.py — Hằng số toàn cục cho OneShot.
Skill-driven values (màu thumbnail, render preset, encoder) nằm trong skills/ JSON.
"""

from pathlib import Path

# ── Audio noise filter (fallback mặc định) ───────────────────────────────────
NOISE_FILTER = (
    "highpass=f=40,"
    "afftdn=nr=10:nf=-35:tn=1,"
    "anlmdn=s=0.00015:p=0.03:r=0.015,"
    "equalizer=f=2500:t=q:w=0.8:g=1.5,"
    "equalizer=f=8000:t=q:w=1.0:g=1.0,"
    "acompressor=threshold=-20dB:ratio=1.3:attack=20:release=140,"
    "volume=2dB"
)

# ── Regex sửa lỗi ASR ───────────────────────────────────────────────────────
TECH_TERMS = [
    (r"\bM[ÔO]\s+M[ÔO]\b", "MOMO"),
    (r"\bMO\s+MO\b", "MOMO"),
    (r"\bLOAN\s+MOMO\b", "LOA MOMO"),
    (r"\bZALO\s+PAY\b", "ZALOPAY"),
    (r"\bSHOPEE\s+PAY\b", "SHOPEEPAY"),
    (r"\bSAMSUNGDEX\b", "SAMSUNG DEX"),
    (r"\bSAMSUNG\s+DECK\b", "SAMSUNG DEX"),
    (r"\bCHẾ\s+ĐỘ\s+DECK\b", "CHẾ ĐỘ DEX"),
    (r"\bTYPE\s*[- ]?\s*C\b", "TYPE-C"),
    (r"\bUSB\s*[- ]?\s*C\b", "USB-C"),
    (r"\bHD\s*MI\b", "HDMI"),
    (r"\b4K\s*120\b", "4K 120HZ"),
    (r"\bPOCKET\s+BAR\b", "POCKET 3"),
    (r"\bPOCKET\s+BA\b", "POCKET 3"),
    (r"\bDJI\s+OSMO\s+NANO\b", "DJI OSMO NANO"),
    (r"\bOSMO\s+NANO\b", "OSMO NANO"),
    (r"\bOTMOLANO\b", "OSMO NANO"),
    (r"\bOTMO\s*LANO\b", "OSMO NANO"),
    (r"\bOSMO\s+MỘT\b", "OSMO NANO"),
    (r"\bOSMO\s+MOT\b", "OSMO NANO"),
    (r"\bD\s*[- ]?\s*LOG\s*M\b", "D-LOG M"),
    (r"\bREC\s*[- .]?\s*709\b", "REC.709"),
    (r"\bTU\s+VIT\b", "TUA VÍT"),
    (r"\bTÔ\s+VÍT\b", "TUA VÍT"),
    (r"\bTO\s+VIT\b", "TUA VÍT"),
    (r"\bS[ÉE]T\s*PLAY\b", "CH PLAY"),
    (r"\bSETPLAY\b", "CH PLAY"),
    (r"\bPLAY\s*STORE\b", "CH PLAY"),
    (r"\bBAY\s*FAST\b", "BAYFAST"),
    (r"\bX[ÓO]P\b", "XỐP"),
    (r"\bHUBDEX\b", "HUB DEX"),
    (r"\bXẠC\s*NHANH\b", "SẠC NHANH"),
    (r"\bXAC\s*NHANH\b", "SẠC NHANH"),
    (r"\bGA\s*N\b", "GAN"),
    (r"\bP\s*D\b", "PD"),
    (r"\bK[IÍ]\s*NH\s*C[UƯ][OỜ]NG\s*L[UỰ]C\b", "KÍNH CƯỜNG LỰC"),
    (r"\b[ÔO]P\s*ĐI[ỆE]N\s*THO[ẠA]I\b", "ỐP ĐIỆN THOẠI"),
    (r"\bBOXPHONE\b", "BOX PHONE"),
]

# Từ yếu ở cuối title
TRAILING_BAD = {
    "HOẶC", "VA", "VÀ", "VỚI", "ĐỂ", "DE", "THÌ", "THI", "CỦA", "CUA", "CHO",
    "TRÊN", "TREN", "Ở", "O", "LÀ", "LA", "MÀ", "MA", "GIÁ", "GIA", "CHỈ",
    "CHI", "TỪ", "TU", "CÓ", "CO", "ĐÈN", "DEN", "KHÔNG", "KHONG", "CẦN", "CAN",
    "DÂY", "DAY", "ĐIỆN", "DIEN", "ĐỠ", "DO", "LED", "SẠC", "SAC",
}

# ── Paths ────────────────────────────────────────────────────────────────────
DEFAULT_LUT = str(Path.home() / "Downloads" / "DJI OSMO Osmo Nano D-Log M to Rec.709 V1.cube")

FONT_CANDIDATES = [
    Path(__file__).parent / "assets" / "fonts" / "DTPhudu-Black.otf",
]

# ── Dimensions ───────────────────────────────────────────────────────────────
THUMB_W, THUMB_H = 1080, 1920
TARGET_W, TARGET_H = 1080, 1920
COVER_DURATION = 0.28

# ── APIs ─────────────────────────────────────────────────────────────────────
DS_API_URL = "https://api.deepseek.com/chat/completions"
DS_MODEL = "deepseek-chat"

# ── Whisper ──────────────────────────────────────────────────────────────────
WHISPER_MODEL_SIZE = "small"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE = "int8"
