# OneShot v4.0 — GPU

> Tự động hóa 100% video TikTok. Kéo video vào → ra video hoàn thiện.
> **GPU Metal + VideoToolbox. 3× realtime. M1 Pro/Max/M2/M3/M4.**

```
input/                          output/done/
  video1.mp4  ────⮞              Tiêu Đề Video #hashtag.mp4
  video2.mp4  ────⮞              Tiêu Đề Video #hashtag.mp4
```

## Dùng

```bash
# Double-click run.command → quét input/ chạy hết
# Terminal:
python main.py input/video.mp4

# Tinh chỉnh:
python main.py input/video.mp4 --preset capcut --noise-skill voice_clean
python main.py --list-skills
```

## Kiến trúc

| Module | Vai trò | Backend |
|---|---|---|
| `orchestrator.py` | Nhạc trưởng 7 bước | — |
| `audio.py` | ① Tách audio | FFmpeg |
| `transcribe.py` | ② Whisper transcript | faster-whisper CPU |
| `transcript_fix.py` | ③ Sửa transcript | Regex + AI DeepSeek |
| `title_gen.py` | ④ Tiêu đề + hashtag | AI DeepSeek |
| `thumbnail.py` | ⑤ Vẽ thumbnail | Pillow |
| `render.py` | ⑥ Render video | **GPU Metal + VT** / CPU libx264 |
| `skills.py` | Skill system | JSON presets |

## Cây thư mục

```
oneshot/
├── main.py                  ← CLI
├── orchestrator.py          ← Nhạc trưởng
├── config.py                ← Hằng số
├── skills.py                ← Skill system
├── core/                    ← Foundation (ffmpeg, media, paths)
├── audio.py … render.py     ← 6 chuyên gia
├── native/gpu-renderer/     ← GPU helper (Swift + Metal)
├── prompts/                 ← AI prompts
├── skills/                  ← JSON presets (lut noise render thumbnail)
├── assets/fonts/
├── input/ → output/done/
├── README.md  DEEPSEEK.md  run.command
└── requirements.txt
```

## Hiệu năng (M1 Pro)

| Video | CPU (trước) | GPU (hiện tại) |
|---|---|---|
| 21s | ~50s (0.4×) | ~9s (2.3×) |
| 88s | ~200s (0.4×) | **27s (3.2×)** |

GPU dùng: Metal decode → Core Image filter (scale, LUT, color, sharpen) → VideoToolbox H.264 encode 16 Mbps. CPU fallback: libx264 ultrafast.

## Cài đặt

```bash
cd ~/oneshot
pip install -r requirements.txt
# Cần: faster-whisper, Pillow, requests, ffmpeg
# Cần: DeepSeek API key → ~/Library/.../Hedra Studio/settings.json → ds_api_key
# GPU: tự build Swift helper lần đầu chạy (cần Xcode CLT)
```
