# DeepSeek Context Loader — OneShot GPU

Paste dòng dưới vào DeepSeek để load toàn bộ codebase.

## Quick Load

```
Đọc /Users/admin/oneshot/README.md trước để hiểu kiến trúc.
Sau đó đọc:
/Users/admin/oneshot/__init__.py
/Users/admin/oneshot/main.py
/Users/admin/oneshot/orchestrator.py
/Users/admin/oneshot/config.py
/Users/admin/oneshot/skills.py
/Users/admin/oneshot/core/ffmpeg.py
/Users/admin/oneshot/core/media.py
/Users/admin/oneshot/core/paths.py
/Users/admin/oneshot/audio.py
/Users/admin/oneshot/transcribe.py
/Users/admin/oneshot/transcript_fix.py
/Users/admin/oneshot/title_gen.py
/Users/admin/oneshot/thumbnail.py
/Users/admin/oneshot/render.py
/Users/admin/oneshot/native/gpu-renderer/Sources/OneShotGPURender/main.swift
/Users/admin/oneshot/native/gpu-renderer/Sources/OneShotGPURender/Renderer.swift
```

## Light Load

```
Đọc /Users/admin/oneshot/README.md
```

## Commands

```
python /Users/admin/oneshot/main.py --list-skills
python /Users/admin/oneshot/main.py --help
python /Users/admin/oneshot/main.py input/video.mp4 --preset capcut
```

## Paths

```
Project:    /Users/admin/oneshot
GPU helper: /Users/admin/oneshot/native/gpu-renderer/
Input:      /Users/admin/oneshot/input/
Output:     /Users/admin/oneshot/output/
Done:       /Users/admin/oneshot/output/done/
Skills:     /Users/admin/oneshot/skills/
Venue:      /Users/admin/hedra-studio/venv/bin/python
API key:    ~/Library/Application Support/Hedra Studio/settings.json → ds_api_key
```
