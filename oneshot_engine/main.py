#!/usr/bin/env python3
"""
main.py — CLI entry.
orchestrator.run() với tham số từ command line.

Usage:
  python main.py <video.mp4> [--lut-skill dji_dlog_m] [--noise-skill voice_clean]
  python main.py <video.mp4> --list-skills          ← xem danh sách skill
"""

import sys
from pathlib import Path

# Đảm bảo thư mục cha của oneshot nằm trong sys.path để import package
_SCRIPT_DIR = Path(__file__).resolve().parent
_PARENT_DIR = _SCRIPT_DIR.parent
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))

from oneshot.orchestrator import run as run_pipeline  # noqa: E402


def _parse_args():
    import argparse
    p = argparse.ArgumentParser(
        description="OneShot Pipeline v4.0 — Modular",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python main.py input/video.mp4
  python main.py input/video.mp4 --lut-skill dji_dlog_m_to_rec709 --noise-skill outdoor_windy
  python main.py --list-skills
        """,
    )
    p.add_argument("video", nargs="?", help="Path to video file (không cần nếu dùng --list-skills)")
    p.add_argument("--lut", default="", help="Path to LUT .cube file (ghi đè skill)")
    p.add_argument("--lut-skill", default="", help="Tên LUT skill (xem --list-skills)")
    p.add_argument("--noise-skill", default="", help="Tên noise filter skill (xem --list-skills)")
    p.add_argument("--key", default="", help="DeepSeek API key (sk-...)")
    p.add_argument("--no-noise", action="store_true", help="Disable noise reduction")
    p.add_argument("--no-lut", action="store_true", help="Disable LUT")
    p.add_argument("--no-cover", action="store_true", help="Disable thumbnail cover")
    p.add_argument("--preset", default="capcut", choices=["capcut", "standard"],
                   help="Render preset: capcut (chất lượng cao) hoặc standard (Hedra gốc)")
    p.add_argument("--lut-intensity", type=float, default=1.0,
                   help="Cường độ LUT (0.0 - 1.0). Clone CapCut LUT slider. Mặc định: 1.0")
    p.add_argument("--out", default="", help="Output directory")
    p.add_argument("--thumb-style", default="boxphonefarm",
                   help="Thumbnail style skill (xem --list-skills). Mặc định: boxphonefarm")
    p.add_argument("--list-skills", action="store_true", help="Liệt kê tất cả skill đang có")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.list_skills:
        from oneshot.skills import print_skills
        print_skills()
        sys.exit(0)

    if not args.video:
        print("❌ Cần path video. VD: python main.py input/video.mp4")
        print("   Hoặc: python main.py --list-skills")
        sys.exit(1)

    sys.exit(run_pipeline(
        args.video,
        lut_path=args.lut,
        api_key=args.key,
        apply_noise=not args.no_noise,
        apply_lut=not args.no_lut,
        cover=not args.no_cover,
        out_dir=args.out,
        lut_skill=args.lut_skill,
        noise_skill=args.noise_skill,
        preset=args.preset,
        lut_intensity=max(0.0, min(1.0, args.lut_intensity)),
        thumb_style=args.thumb_style,
    ))
