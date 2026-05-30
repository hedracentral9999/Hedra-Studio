# Escbase Template 3

Command cheat sheet cho repo tạo video slide 9:16 bằng HTML/CSS/JS thuần.

Phiên bản: `83.v3.86`

Giấy phép: Thương mại. Xem `LICENSE`.

Lưu ý: tài sản bên thứ ba nếu có vẫn thuộc về chủ sở hữu tương ứng; xem `LICENSE`.

## Cài đặt

Chạy nhanh một lệnh để tự tạo `.venv`, cài dependencies, kiểm tra công cụ render rồi mở Web UI:

```bash
./setup_and_run.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_and_run_windows.ps1
```

Hoặc cài thủ công:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

Project sẽ nằm ở `slide/ten-du-an`.

Nếu phát sinh lỗi cài đặt hoặc render, hãy hỏi trực tiếp Antigravity và gửi kèm toàn bộ log lỗi trong Terminal/PowerShell.

## Web UI để preview và render

Chạy local server:

```bash
python3 web_server.py
```

Nếu chưa cài môi trường, dùng:

```bash
./setup_and_run.sh
```

Sau đó mở:

- Dashboard kiêm bộ máy render: `http://localhost:8765`
- Preview slide thuần: `http://localhost:8765/slide/ten-du-an/`

Trên dashboard, chọn project trong dropdown rồi render:

- **ElevenLabs audio upload:** chọn file audio đầy đủ (`mp3`, `wav`, `m4a`, `aac`, `ogg`) rồi bấm render. Server sẽ upload vào `slide/ten-du-an/input_audio/`, chạy `render_elevenlabs.py`, tách audio và xuất `output/final_video.mp4`.
- **Edge TTS:** chọn voice, speed, tuỳ chọn `Tạo lại audio cache`, rồi bấm render. Server sẽ chạy `render_edgetts.py`.
- **Refresh danh sách:** tải lại dashboard để thấy slide mới vừa được agent tạo.
- **Xoá output:** xoá `slide/ten-du-an/output/` sau khi xác nhận popup, dùng khi muốn render lại sạch.

> `slide/ten-du-an/index.html` không cần nhúng thêm script render nào; giữ file slide sạch để agent dựng xong là preview được ngay. Link **Xem slide** và **Mở video** trên dashboard sẽ mở tab mới.

## 1. Render tự động với ElevenLabs (Khuyên dùng)

Script gộp sẽ tự động tăng tốc độ audio gốc, chia nhỏ để khớp với slide, rồi xuất thẳng ra video `final_video.mp4` cuối cùng.

```bash
# Chạy mặc định (tốc độ audio 1.1x)
python3 render_elevenlabs.py slide/ten-du-an /path/to/elevenlabs.mp3

# Hoặc tuỳ chỉnh tốc độ qua tham số --speed
python3 render_elevenlabs.py slide/ten-du-an /path/to/elevenlabs.mp3 --speed 1.15
```

## 2. Render tự động với Edge TTS (Draft)

Script gộp sẽ tự sinh AI voiceover bằng Edge TTS theo tốc độ được chỉ định, sau đó render thành video `final_video.mp4`.

```bash
# Chạy mặc định (tốc độ audio 1.1x)
python3 render_edgetts.py slide/ten-du-an

# Hoặc tuỳ chỉnh tốc độ
python3 render_edgetts.py slide/ten-du-an --speed 1.2

# Thêm --force nếu bạn vừa sửa kịch bản và muốn bắt buộc sinh lại audio mới
python3 render_edgetts.py slide/ten-du-an --speed 1.1 --force
```

> **⚠️ LƯU Ý VỀ GHI ĐÈ AUDIO CACHE:**
> - Nếu chạy **Edge TTS trước ➔ ElevenLabs sau**: Các file sẽ tự động được ghi đè an toàn.
> - Nếu chạy **ElevenLabs trước ➔ Edge TTS sau**: Bắt buộc phải thêm cờ `--force` cho lệnh `render_edgetts.py`. Nếu không có cờ này, script Edge sẽ tái sử dụng nhầm các file âm thanh cũ của ElevenLabs đã sinh ra trước đó thay vì tải audio mới.

## Validate slide-only

Chạy sau khi chỉnh `script-90s.txt`, `app.js`, `index.html`, `style.css`:

```bash
python3 validate_slide.py slide/ten-du-an
```

Lệnh này không tạo TTS và không render video. Mặc định nó cũng mở Chromium headless qua Playwright để kiểm layout safezone theo `.slide-element`: top content phải `>= 100px`, bottom gap phải `>= 200px`.

Để vừa validate mapping vừa rà câu voiceover ↔ reveal trước khi bàn giao:

```bash
python3 validate_slide.py slide/ten-du-an --semantic-report
```

Chỉ dùng `--skip-safezone` khi đang debug môi trường Playwright, không dùng để bàn giao deck.

## Tạo Edge TTS draft

```bash
python3 generate_tts.py slide/ten-du-an
```

Nếu muốn tạo lại từ đầu:

```bash
python3 generate_tts.py slide/ten-du-an --force
```

TTS code được tách theo engine trong `tts/`:

- `tts/edge.py` — Edge TTS draft.
- `tts/elevenlabs.py` — ElevenLabs API TTS.
- `tts/common.py` — timing, video-duration padding, concat audio.

Tạo voiceover bằng ElevenLabs API:

```bash
pip install -r requirements.txt
cp config/tts.example.json config/tts.json
# điền elevenlabs.voice_id và api_key trong config/tts.json
python3 generate_tts.py slide/ten-du-an --engine elevenlabs
```

Mặc định ElevenLabs dùng `model_id: "eleven_v3"` và `output_format: "mp3_44100_128"`.

Có thể dùng biến môi trường thay vì lưu key trong file:

```bash
ELEVENLABS_API_KEY=... python3 generate_tts.py slide/ten-du-an --engine elevenlabs --voice <voice_id>
```

## Render video

```bash
python3 auto_render.py slide/ten-du-an
```

Output: `slide/ten-du-an/output/final_video.mp4`

## Dùng ElevenLabs production

```bash
python3 split_voiceover.py slide/ten-du-an /path/to/elevenlabs.mp3
python3 auto_render.py slide/ten-du-an
```

## Chuyển MOV sang MP4

```bash
ffmpeg -i slide/ten-du-an/a.mov -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k -movflags +faststart slide/ten-du-an/demo.mp4 -y
```

## Lấy nội dung thread X

```bash
bird thread "https://x.com/user/status/id"
```

## Social upload

Upload Center dùng module riêng trong `social_upload/`:

- `social_upload/youtube.py` — Google OAuth + YouTube upload.
- `social_upload/facebook.py` — Facebook Reels upload.
- `social_upload/metadata.py` — đọc/gợi ý `upload-metadata.json`.
- `social_upload/config.py` — config chung `config/social-upload.json`.

Cấu hình bằng cách copy file mẫu rồi làm theo docs chi tiết:

```bash
cp config/social-upload.example.json config/social-upload.json
```

- `docs/youtube-api-upload.md`
- `docs/facebook-api-upload.md`
