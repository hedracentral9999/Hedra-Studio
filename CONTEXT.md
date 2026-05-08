# Hedra Studio — Context cho session mới

## Project
PyQt6 TTS app, file chính: tts_app.py
Version hiện tại: 1.3
Scheme: Apple-style Major.Minor (bỏ số patch, reset từ 1.2.xx)
Repo: https://github.com/hedracentral9999/Hedra-Studio

## Build & Release
bash build_mac.sh  # tạo DMG
GitHub token: osxkeychain (security find-internet-password -s "github.com" -w)

## Key Files
- tts_app.py — toàn bộ app
- version.py — VERSION string
- build_mac.sh — build DMG + release

## Style guide
Apple HIG: pill button = border-radius: height/2, border:none inactive
Accent: #0071e3, Background inactive: #ebf0f0
