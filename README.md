<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Hedra_Studio-v1.8.7-0071e3?style=for-the-badge&labelColor=1d1d1f">
    <img src="https://img.shields.io/badge/Hedra_Studio-v1.8.7-0071e3?style=for-the-badge&labelColor=white" width="400">
  </picture>
</p>

<p align="center">
  <b>Desktop AI voice studio — TTS, STT, script tools and Auto Video</b><br>
  <i>Source public để audit/minh bạch; dùng thương mại cần license riêng.</i>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/github/v/release/hedracentral9999/Hedra-Studio?style=flat&label=Release&color=0071e3"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-0071e3?style=flat"></a>
  <a href="#"><img src="https://img.shields.io/github/license/hedracentral9999/Hedra-Studio?style=flat&color=6e6e73"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.11%2B-0071e3?style=flat"></a>
</p>

---

## Tính năng

| Tính năng | Mô tả |
|-----------|-------|
| **TTS** | Tạo audio, nghe lại trong app, mở file và xuất SRT |
| **STT** | Chuyển audio thành text/SRT |
| **TTS Enhance** | Tối ưu văn bản trước khi TTS: sửa chính tả, mở rộng viết tắt, thêm tags |
| **Kịch bản** | Tính năng Pro: chụp ảnh chat Zalo -> Gemini phân tích -> xuất kịch bản TTS |
| **Auto Video** | Tính năng Pro: link/text -> script -> TTS -> render video |
| **2 phong cách built-in** | `Nghiêm túc` (temp 0.3) và `Hài hước` (temp 0.7) |
| **Style Wizard** | AI hỗ trợ tạo style tuỳ chỉnh với 7 câu hỏi |
| **Đa ngôn ngữ** | Hỗ trợ 60+ ngôn ngữ, dropdown chọn nhanh và tự động |
| **Shared Voice Library** | Duyệt và thêm giọng từ ElevenLabs Shared Voice Library |
| **Output tùy chỉnh** | Chọn thư mục lưu file MP3/SRT |
| **Auto-update** | Kiểm tra bản mới khi khởi động và cập nhật qua GitHub Releases |
| **System Tray** | Thu nhỏ xuống tray, hotkey toàn cục |
| **In-app Feedback** | Gửi phản hồi trực tiếp đến dev qua Telegram |
| **License online** | TTS/STT dùng được miễn phí; Kịch bản/Auto Video cần key Pro |

---

## Screenshots

<p align="center">
  <i>(Thêm ảnh chụp màn hình ở đây)</i>
</p>

| Main Window | Settings | Voice Library |
|:---:|:---:|:---:|
| TTS + Enhance | API Keys, Prompts, Output | Tìm và thêm giọng |

---

## Cài đặt nhanh

### macOS

1. **Tải file DMG** từ [Releases](https://github.com/hedracentral9999/Hedra-Studio/releases)
2. Mở file DMG → kéo **Hedra Studio.app** vào **Applications**
3. Lần đầu chạy: `Ctrl + click` → **Open** (vì app chưa được notarize)

### Windows

1. **Tải file setup `.exe`** từ [Releases](https://github.com/hedracentral9999/Hedra-Studio/releases)
2. Chạy file setup — tự động cài đặt

---

## Hướng dẫn sử dụng

### 1. Lấy API Keys

Bạn cần ít nhất 2 API keys:

| Service | Dùng để | Lấy ở đâu |
|---------|---------|-----------|
| **ElevenLabs** | Generate giọng nói | https://try.elevenlabs.io/rinor1xaj4ze → Sign Up → API Keys |
| **DeepSeek** | Enhance kịch bản | https://platform.deepseek.com/api_keys |
| **Gemini** (tuỳ chọn) | Chat → Kịch bản | https://aistudio.google.com/apikey |

> **Mẹo:** Có thể thêm nhiều ElevenLabs keys — app tự động xoay khi key hết credit.

### 2. Generate giọng nói cơ bản

1. Mở app → tab **TTS**
2. Dán kịch bản vào ô text
3. (Tuỳ chọn) Điều chỉnh **tốc độ đọc** bằng slider
4. Nhấn **Generate**
5. App sẽ: **Enhance với provider AI đã chọn** -> **TTS với provider giọng đọc đã chọn** -> lưu MP3/SRT

### 3. Kịch bản và Auto Video Pro

Hai tab này có trong app nhưng cần license key.

1. Mở tab **Kịch bản** hoặc **Auto Video**
2. Nhập license key đã mua
3. App xác thực online với license server
4. Key hợp lệ sẽ mở đúng tính năng được cấp phép

### 4. Tuỳ chỉnh phong cách

**Built-in:**
- `🎯 Nghiêm túc` — giọng chuyên nghiệp, chuẩn mực
- `😄 Hài hước` — giọng dí dỏm, thoải mái

**Tạo style mới:**
- Mở **Prompt Wizard** → trả lời 7 câu hỏi → AI tự sinh prompt
- Hoặc vào Settings → **Prompts tab** → chỉnh sửa trực tiếp

### 5. Quản lý giọng đọc

- **Đổi giọng:** Nhấn tên giọng ở góc trên → chọn từ danh sách
- **Thêm giọng từ thư viện:** Nút "🌐 Thư viện giọng" → tìm kiếm → thêm vào account
- **Giọng tuỳ chỉnh:** Settings → Voices → nhập Voice ID

---

## Cấu hình nâng cao

### File cấu hình

Settings được lưu tại:

- **macOS:** `~/Library/Application Support/Hedra Studio/settings.json`
- **Windows:** `%APPDATA%/Hedra Studio/settings.json`

### Telegram Feedback (cho dev)

```bash
# Cách 1: Tạo file telegram_config.py (không bị commit)
cp telegram_config.py.example telegram_config.py
# Sửa token + chat ID của bạn

# Cách 2: Dùng biến môi trường
export ELEVENLABS_TELEGRAM_BOT_TOKEN="your_token"
export ELEVENLABS_TELEGRAM_CHAT_ID="your_chat_id"
```

### Biến môi trường

| Biến | Mô tả |
|------|-------|
| `ELEVENLABS_API_KEY` | ElevenLabs API key (CLI) |
| `DEEPSEEK_API_KEY` | DeepSeek API key (CLI) |
| `ELEVENLABS_TELEGRAM_BOT_TOKEN` | Telegram bot token cho feedback |
| `ELEVENLABS_TELEGRAM_CHAT_ID` | Chat ID nhận feedback |

---

## Build từ source

### Requirements

- Python 3.11+
- [create-dmg](https://github.com/create-dmg/create-dmg) (macOS, để tạo DMG)

### macOS

```bash
git clone https://github.com/hedracentral9999/Hedra-Studio.git
cd Hedra-Studio

python3 -m venv venv
source venv/bin/activate
pip install -r requirements_build.txt

# Build DMG
bash build_mac.sh
```

### Windows

```powershell
git clone https://github.com/hedracentral9999/Hedra-Studio.git
cd Hedra-Studio

python -m venv venv
venv\Scripts\activate
pip install -r requirements_build.txt

# Build portable EXE + installer (cần Inno Setup nếu muốn file setup)
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

Output chính:

- `dist\Hedra Studio.exe`: bản portable.
- `Hedra-Studio-<version>-win-setup.exe`: bản cài đặt để gửi người dùng Windows.

### Pro license

Kịch bản và Auto Video là tính năng Pro. App chỉ chứa client xác thực license online; source public không chứa secret ký key hoặc tool tạo key.

License server endpoint mặc định nằm trong `version.py` và có thể override bằng biến môi trường:

```bash
HEDRA_LICENSE_VERIFY_URL=https://your-domain.com/v1/licenses/verify
```

Endpoint nhận `POST` JSON gồm `key`, `feature`, `app`, `version`, `device_id`, `platform` và trả về:

```json
{
  "valid": true,
  "features": ["chat_script", "auto_video"],
  "expires_at": "2026-12-31T23:59:59Z",
  "message": "License hợp lệ"
}
```

### GitHub Actions (tự động)

Push tag `v*` -> tự động build Mac + Windows -> upload lên Release.

```bash
git tag v1.8.7
git push origin v1.8.7
```

---

## 🗂 Cấu trúc project

```
Hedra-Studio/
├── tts_app.py          # App chính (PyQt6) — 5500+ dòng
├── tts.py              # CLI TTS tool
├── version.py          # VERSION string
├── TTS.spec            # PyInstaller spec
├── build_mac.sh        # Build script cho macOS
├── setup.iss           # Inno Setup script cho Windows
├── telegram_config.py.example  # Mẫu config Telegram
├── prompt-*.md         # Prompt mẫu (ElevenLabs, Chat-to-Script)
│
├── web/                # Web TTS app (FastAPI + Supabase)
│   ├── main.py
│   ├── requirements.txt
│   ├── templates/
│   └── static/
│
└── .github/workflows/  # GitHub Actions
    ├── build.yml       # Build Mac DMG
    └── build-windows.yml  # Build Windows EXE
```

---

## Prompt mẫu

| File | Mô tả |
|------|-------|
| `prompt-elevenlabs-v3.md` | Prompt gốc cho ElevenLabs v3 - giọng Adam |
| `prompt-chat-to-script.md` | Prompt cho Gemini chat → kịch bản |

> **Tạo prompt riêng?** Tham khảo [ElevenLabs Docs](https://try.elevenlabs.io/rinor1xaj4ze) về tags, controls, và voice settings để custom prompt theo ý bạn.

---

## Security & Privacy

Hedra Studio được thiết kế **minh bạch** — không có tracking, telemetry, hay hành vi ẩn.

### Network requests

| Gửi đến | Mục đích | Khi nào |
|---------|----------|---------|
| `api.elevenlabs.io` | Generate TTS audio, check credits, tải voices | Khi bạn generate / refresh |
| `api.deepseek.com` | Enhance kịch bản | Khi bạn nhấn Generate |
| `generativelanguage.googleapis.com` | Gemini chat → kịch bản | Khi bạn dùng Chat tab |
| `api.telegram.org` | Gửi feedback đến dev | Chỉ khi bạn nhấn **Gửi phản hồi** |
| `api.github.com` | Kiểm tra bản cập nhật | Khi khởi động app, 1 lần |

### Release sạch

Artifact chính thức nên được tải từ GitHub Releases. Mỗi release được build từ source bằng GitHub Actions và phải qua security audit trước khi upload:

- source scan: chặn token/API key, `.env`, `settings.json`, output cá nhân;
- artifact scan: chặn `telegram_config.py`, local path `/Users/admin`, file audio/video/output;
- checksum SHA256 được phát hành kèm DMG/installer để người dùng đối chiếu.

### Auto-update

App tải DMG từ GitHub Releases về `~/Library/Caches/` và chạy script tự động:
1. Đợi app cũ thoát (max 30s)
2. Mount DMG mới
3. Copy app mới vào `Applications/`
4. Mở app mới

Script ghi log tại `/tmp/hedra_update.log` — bạn có thể kiểm tra bất kỳ lúc nào.

> Script chỉ chạy khi bạn **chủ động nhấn "Cập nhật"** — không tự động cài đặt.

### API Keys

Keys được lưu trong file `settings.json` tại:
- **macOS:** `~/Library/Application Support/Hedra Studio/settings.json`
- **Windows:** `%APPDATA%/Hedra Studio/settings.json`

**Không** được gửi đi đâu ngoài các API bạn đã cấu hình (ElevenLabs, DeepSeek, Gemini).

Bản public không đọc settings cũ từ `TTSApp`, nên API key của máy dev/pro không tự xuất hiện trong app tải về.

### Những gì app KHÔNG làm

- **Không** tracking, analytics, telemetry
- **Không** gửi dữ liệu cá nhân ra ngoài
- **Không** đọc file ngoài thư mục được chỉ định
- **Không** chạy ngầm ẩn (chỉ chạy khi bạn mở)
- **Không** ghi đè hay sửa file hệ thống
- **Không** keylogger, không capture màn hình (trừ Gemini chat bạn tự kéo thả ảnh)

### Build từ source

Nếu bạn lo ngại về bảo mật, hoàn toàn có thể [build từ source](#-build-từ-source) và tự kiểm tra code.

---

## License

Source được publish để người dùng kiểm tra/audit và dùng phi thương mại theo [PolyForm Noncommercial 1.0.0](LICENSE).

Mọi dùng thương mại, bán lại, agency workflow, SaaS hoặc bundle sản phẩm cần license riêng. Xem [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) và [TRADEMARKS.md](TRADEMARKS.md).

---

<p align="center">
  <sub>Made with ❤️ by <a href="https://github.com/hedracentral9999">@hedracentral9999</a></sub>
</p>
