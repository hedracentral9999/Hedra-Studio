# CLAUDE.md — Hedra Studio (Private)
# Đọc file này ĐẦU MỖI SESSION trước khi làm bất cứ thứ gì

## CODEX ACCOUNT SWITCHING — ĐỌC TRƯỚC
Nếu mở account Codex mới hoặc đổi account vì bị limit: đọc `/Users/admin/hedra-studio/HANDOFF.md` trước, chạy các lệnh git status/log/diff trong đó để xác minh trạng thái thật, rồi mới dùng Session Log bên dưới. Nếu `CLAUDE.md` lệch với git/code thật, tin git/code trước và cập nhật lại handoff.

## Overview
PyQt6 desktop tray app — PRIVATE repo (hedracentral9999/Hedra-Studio).
⚠️ KHÔNG public, KHÔNG share source code ra ngoài.
Gồm: TTS (GenMax+ElevenLabs) + Chat/Enhance (Gemini+DeepSeek) + STT + Auto Video.
Platform: macOS (tray app) + Windows. Build: PyInstaller → DMG/EXE.
Current version: xem `version.py`

## Stack
Python 3.11+ · PyQt6 · requests · ElevenLabs API · GenMax API · Gemini API · DeepSeek API · Anthropic API

## Paths
- Project root: `/Users/admin/hedra-studio/`
- Engine (auto-create-video): `/Users/admin/Auto-Create-Video/`
- Engine output: `/Users/admin/Auto-Create-Video/output/`

## Run
```bash
cd /Users/admin/hedra-studio
source venv/bin/activate
python tts_app.py
```

## Syntax Check
```bash
cd /Users/admin/hedra-studio
source venv/bin/activate && python -m py_compile app_constants.py app_utils.py app_workers.py app_dialogs.py voice_library.py settings_dialog.py main_window.py tts_app.py auto_video_workers.py && echo "OK"
```

---

## Module Architecture
```
app_constants.py    → constants, prompts, HIG palette
app_utils.py        → load/save_settings, reveal_file, error hook
app_workers.py      → tất cả QThread workers (TTS, enhance, update...)
app_dialogs.py      → dialogs phụ
voice_library.py    → VoiceLibraryDialog
settings_dialog.py  → SettingsDialog
main_window.py      → MainWindow — tabs: Chat, TTS, STT, Auto Video
tts_app.py          → TrayApp + entry point
auto_video_workers.py → Workers riêng cho tab Auto Video
```

Dependency chain (KHÔNG circular):
```
app_constants → app_utils → app_workers → app_dialogs → voice_library → settings_dialog → main_window → tts_app
app_constants → app_utils → auto_video_workers  (song song, không phụ thuộc main_window)
```

---

## ═══════════════════════════════════════════════════════════
## QUY TẮC BẮT BUỘC CHO DEEPSEEK
## ═══════════════════════════════════════════════════════════

### HANDOFF KHI BỊ LIMIT / ĐỔI ACCOUNT — BẮT BUỘC

- Luôn xử lý theo kiểu có thể bị ngắt giữa chừng: làm tới đâu ghi tới đó vào `CLAUDE.md`.
- Nếu đang làm dở, cập nhật Session Log với tag `[IN PROGRESS]` hoặc `[BLOCKED]`, ghi rõ:
  - Đã làm tới bước nào
  - File nào đã sửa
  - Lệnh nào đã chạy và kết quả chính
  - Bước tiếp theo cần làm ngay
- Không giữ context quan trọng chỉ trong chat. Account/session sau phải đọc `CLAUDE.md` là tiếp tục được.

---

## ═══════════════════════════════════════════════════════════
## SESSION LOG — DEEPSEEK GHI VÀO ĐÂY
## ═══════════════════════════════════════════════════════════














### [AUDIT - 12/05/2026]
- TTS hiện tại: GenMax provider · Voice Sarah (ElevenLabs proxy · eleven_v3)
- Voice ID: 14f27892-f796-47ee-9669-fe6dbca517fd


### [AUTO VIDEO SETTINGS - DONE - 12/05/2026]
- Đã làm: Tiếp tục phần Claude bị limit — thêm trang Auto Video trong Settings để đọc/ghi trực tiếp `/Users/admin/Auto-Create-Video/.env.local`, gồm TTS provider/voice IDs, API keys, TikTok outro, Gemini thumbnail key. AutoVideoEngineWorker chuyển sang dùng `.env.local` làm single source of truth và lấy PATH từ login shell.
- File đã sửa: settings_dialog.py, auto_video_workers.py, CLAUDE.md
- Verify: `python -m py_compile` toàn bộ module OK; SettingsDialog khởi tạo được với `QT_QPA_PLATFORM=offscreen`
- Vấn đề gặp: Qt báo parse stylesheet ở vài QPushButton do dư dấu `}`; đã sửa.

### [AUTO VIDEO INTEGRATION - DONE - 12/05/2026]
- Đã làm: Hoàn thiện tích hợp Auto-Create-Video vào Hedra Studio theo hướng UI wrapper: Auto Video tab chỉ nhận input, hiển thị config từ `.env.local`, show script/progress/log/result; Settings → Auto Video là nơi chỉnh engine config. Dọn method `_av_*` bị lặp trong main_window.py để bản UI mới không bị override. AutoScriptWorker đọc provider/voice/channel từ `.env.local`.
- File đã sửa: main_window.py, auto_video_workers.py, settings_dialog.py, CLAUDE.md
- Verify: Python compile OK; SettingsDialog/MainWindow khởi tạo OK; test `_write_env_local()` bằng file tạm OK; test `_build_script()` đọc GenMax voice từ `.env.local` OK; engine `npx tsc --noEmit` OK.
- Vấn đề gặp: engine `src/pipeline.ts` trong worktree đang bị đổi sang bản không export `runPipeline` nên TypeScript fail; đã đưa lại contract CLI hiện có để unblock, sau đó TypeScript OK.

### [AUTO VIDEO VOICE PRESETS - DONE - 12/05/2026]
- Đã làm: Thêm danh sách "Giọng đã lưu" trong Settings → Auto Video. Có thể lưu Voice ID hiện tại với tên dễ nhớ, chọn preset để thay Voice ID nhanh, và xóa preset. Preset lưu trong settings Hedra Studio theo từng provider; Voice ID đang chọn vẫn ghi vào `.env.local` khi bấm Lưu.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: Python compile OK; SettingsDialog khởi tạo OK; chọn preset tự fill Voice ID OK; xóa preset OK.

### [AUTO VIDEO VOICE PRESET ADD FLOW - DONE - 12/05/2026]
- Đã làm: Đổi flow thêm giọng yêu thích: nút tròn `+` mở dialog nhập tên giọng + Voice ID, lưu preset theo provider và tự set Voice ID đó làm giọng đang chọn.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: Python compile OK; SettingsDialog khởi tạo OK; chọn preset tự fill Voice ID OK.

### [AUTO VIDEO TIKTOK AVATAR SETTINGS - DONE - 12/05/2026]
- Đã làm: Thêm cấu hình Avatar trong Settings → Auto Video → Kênh TikTok. Có thể dán `TIKTOK_AVATAR_URL` hoặc bấm Chọn ảnh để copy file local vào `/Users/admin/Auto-Create-Video/assets/avatar.*`; để trống URL thì engine dùng file local đó.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: Python compile OK; SettingsDialog khởi tạo OK; field Avatar hiển thị OK.

### [AUTO VIDEO VOICE PREVIEW - DONE - 12/05/2026]
- Đã làm: Thêm nút nghe thử `▶` cạnh Voice ID trong Settings → Auto Video. Nút dùng provider/API key/Voice ID đang nhập để tạo câu sample ngắn và phát trong app. Hỗ trợ GenMax + ElevenLabs.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: Python compile OK; SettingsDialog khởi tạo OK; nút preview hiển thị OK.

### [AUTO VIDEO GENMAX PREVIEW RETRY - DONE - 12/05/2026]
- Đã làm: GenMax voice preview tự retry tối đa 3 lần, nghỉ 2s giữa các lần. Chỉ hiện lỗi sau khi cả 3 lần fail.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: Python compile OK.

### [AUTO VIDEO LUCYLAB VOICE PREVIEW - DONE - 12/05/2026]
- Đã làm: Bổ sung nghe thử LucyLab cho nút `▶` cạnh Voice ID. Preview gọi JSON-RPC `ttsLongText`, poll `getExportStatus`, tải audio URL rồi phát trong Settings.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: Python compile OK; SettingsDialog chuyển provider lucylab và nút preview hiển thị OK.

### [AUTO VIDEO TIKTOK OUTRO PREVIEW - DONE - 12/05/2026]
- Đã làm: Thêm preview card dưới Kênh TikTok (Outro), hiển thị avatar/tên/handle/bio realtime theo field đang nhập. Nếu dùng avatar local trong engine assets thì preview hiển thị ảnh; nếu dùng URL thì render thật vẫn dùng URL, preview hiển thị chữ cái đầu.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: Python compile OK; SettingsDialog khởi tạo OK; preview cập nhật realtime khi sửa tên.

### [GENMAX DOCS ALIGNMENT - DONE - 12/05/2026]
- Đã làm: Đọc `endpoints.zip` và chỉnh GenMax theo docs: `POST /v1/text-to-speech/{voice_id}` luôn gửi `provider`, `model_id`, `language_code`, voice_settings đúng theo backend `elevenlabs|minimax`, poll kết quả ở `GET /v1/history/{id}`. Settings → Auto Video có thêm GenMax provider/model/language và ghi vào `.env.local`.
- File đã sửa: settings_dialog.py, app_workers.py, /Users/admin/Auto-Create-Video/src/config.ts, /Users/admin/Auto-Create-Video/src/tts/genmax-client.ts, /Users/admin/Auto-Create-Video/src/tts/tts-client.ts, /Users/admin/Auto-Create-Video/.env.local, CLAUDE.md
- Verify: `venv/bin/python -m py_compile settings_dialog.py app_workers.py auto_video_workers.py main_window.py` OK; `npx tsc --noEmit` OK; SettingsDialog offscreen có Auto Video nav OK.

### [GENMAX LANGUAGE FALLBACK - DONE - 12/05/2026]
- Đã làm: Fix lỗi preview `language_code` không khớp model/voice. GenMax ElevenLabs proxy dùng `eleven_v3`; preview lấy language từ voice đã lưu/model trả về thay vì ép tên ngôn ngữ.
- File đã sửa: settings_dialog.py, app_workers.py, /Users/admin/Auto-Create-Video/src/config.ts, /Users/admin/Auto-Create-Video/src/tts/genmax-client.ts, /Users/admin/Auto-Create-Video/.env.local, CLAUDE.md
- Verify: `venv/bin/python -m py_compile settings_dialog.py app_workers.py auto_video_workers.py main_window.py` OK; `npx tsc --noEmit` OK.

### [VOICE PREVIEW PLAYBACK - DONE - 12/05/2026]
- Đã làm: Fix preview tải audio nhưng không nghe thấy bằng cách ưu tiên phát file preview qua `/usr/bin/afplay` trên macOS; giữ QMediaPlayer làm fallback. Nút `■` dừng được preview đang phát.
- File đã sửa: settings_dialog.py, CLAUDE.md
- Verify: `venv/bin/python -m py_compile settings_dialog.py app_workers.py auto_video_workers.py main_window.py` OK; `/usr/bin/afplay` tồn tại.

### [CODEX CONTINUE VERIFY - DONE - 13/05/2026]
- Đã làm: Đọc HANDOFF.md, đối chiếu git/log/diff ở Hedra Studio và Auto-Create-Video, engine đã có commit local `2b88cb9`, `bbc094b`, `14c91f0`.
- File đã sửa: CLAUDE.md, HANDOFF.md
- Verify: Hedra `venv/bin/python -m py_compile app_constants.py app_utils.py app_workers.py app_dialogs.py voice_library.py settings_dialog.py main_window.py tts_app.py auto_video_workers.py` OK; SettingsDialog offscreen OK; `git diff --check` OK; engine `npx tsc --noEmit` OK; targeted `npx vitest run src/config.test.ts src/render/html-composer.test.ts src/tts/genmax-client.test.ts src/tts/elevenlabs-client.test.ts src/tts/eleven-v3-style.test.ts` OK (5 files, 26 tests).
- Vấn đề gặp: Worktree vẫn dirty lớn ở cả hai repo; chưa commit để tránh gom nhầm nhiều thay đổi không cùng phạm vi.

---

## Lab Notes
<!-- KHÔNG XÓA — chỉ thêm -->
[WORKFLOW] ALWAYS cập nhật CLAUDE.md theo kiểu handoff liên tục: làm tới đâu ghi tới đó; nếu bị limit/đổi account/session thì agent sau đọc file này phải tiếp tục được ngay.
[WORKFLOW] ALWAYS DeepSeek báo đầy đủ khi xong việc: ✅/❌ từng bước, file đã sửa, lệnh đã chạy, output thực tế — để Claude review không bị miss
[WORKFLOW] NEVER Claude và DeepSeek cùng commit lên cùng 1 repo trong cùng session — gây duplicate commit, phải squash/rebase sau
[GIT]     NEVER Claude agent tự commit vào repo đang có DeepSeek làm việc — làm bẩn history
[API]     ALWAYS Gemini first → DeepSeek fallback trong _enhance()
[API]     NEVER dùng "hahahahaaa" trong prompts — dùng [laughs] tags
[EL]      ElevenLabs max 3 API keys — giới hạn tại _save() với [:3]
[HIG]     BG/SURFACE/ACCENT/STYLE defined trong app_constants.py (không main_window) — tránh circular
[BUILD]   CRITICAL: Sau refactor PHẢI thêm TẤT CẢ modules vào hiddenimports trong TTS.spec
[IMPORT]  NEVER import từ file bên phải trong dependency chain — gây circular import crash
[IMPORT]  Dùng python -m py_compile TẤT CẢ modules trước khi tag release
[BUILD]   NEVER build DMG local macOS 15+ — dùng CI GitHub Actions push tag v*
[GENMAX]  GenMax là primary TTS — ElevenLabs chỉ là fallback
[GENMAX]  Endpoints: POST /v1/text-to-speech/{id}, GET /v1/auth/me, GET /v1/default-voices
[GENMAX]  TTS request body per docs: include provider (`elevenlabs`/`minimax`), model_id, language_code; ElevenLabs language must match voice verified language (current default `en`), MiniMax language uses name (`Vietnamese`).
[GENMAX]  NEVER để GENMAX_POLL_TIMEOUT_MS < 300000 — scene có thể mất 90s+ (thực tế body-3 mất 92s)
[GENMAX]  ALWAYS retry tối thiểu 7 lần trong genmax-client.ts — API không ổn định, lỗi ngẫu nhiên thường xuyên
[AUTO_VIDEO] auto_video_workers.py: ENGINE_DIR = /Users/admin/Auto-Create-Video
[AUTO_VIDEO] auto_video_workers.py KHÔNG import từ main_window — tránh circular
[AUTO_VIDEO] NEVER dùng ~/hedra-short hay Path.home()/"hedra-short" — engine luôn là /Users/admin/Auto-Create-Video/
[AUTO_VIDEO] Hedra Studio Settings → Auto Video đọc/ghi trực tiếp `/Users/admin/Auto-Create-Video/.env.local`; không lưu override riêng để tránh lệch config.
[AUTO_VIDEO] MainWindow Auto Video tab không lưu provider/voice riêng; chỉ hiển thị tóm tắt `.env.local` và gọi engine bằng cwd `/Users/admin/Auto-Create-Video`.
[AUTO_VIDEO] Voice presets chỉ là metadata trong Hedra Studio settings (`av_voice_presets`); Voice ID active vẫn ghi vào `.env.local`.
[AUTO_VIDEO] TikTok avatar có 2 mode: URL ghi `TIKTOK_AVATAR_URL`; file local copy vào engine `assets/avatar.{png,jpg,jpeg,webp}` và để URL trống.
[RENDER]  M1 Pro: ALWAYS thêm --gpu (VideoToolbox) + --workers 4 vào hyperframes render — nhanh hơn 3-5x
