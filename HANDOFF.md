# HANDOFF: Hedra Studio TTS App
# Paste this ENTIRE document into a new chat with any AI tool.
# The AI will understand the project and continue building it.

---

## Quick Facts
- **Project:** Hedra Studio — PyQt6 desktop TTS app
- **Platform:** macOS (tray app) + Windows (.exe)
- **Build:** PyInstaller → GitHub Actions CI
- **Repo:** hedracentral9999/Hedra-Studio
- **Current version:** 1.7.6
- **Python version:** 3.11+ (CI uses 3.11, local dev 3.14)

---

## File Architecture (8 core .py files)

```
app_constants.py    → constants, prompts, get_creativity_guide(), HIG palette
app_utils.py        → data_dir, load/save_settings, reveal_file, exception hook
app_workers.py      → ALL QThread workers (15 classes + words_to_srt function)
app_dialogs.py      → dialogs: EmojiPicker, AddStyle, PromptWizard, Feedback, DropZone
voice_library.py    → VoiceLibraryDialog (browse ElevenLabs/GenMax voices)
settings_dialog.py  → SettingsDialog (4 tabs: API Keys, Prompts, Voices, Output)
main_window.py      → MainWindow (3 tabs: Chat, TTS, STT + creativity UI)
tts_app.py          → TrayApp + entry point (~84 lines)
```

## Dependency Chain (NEVER import right-to-left — causes circular import)
```
app_constants → app_utils → app_workers → app_dialogs → voice_library → settings_dialog → main_window → tts_app
```

---

## Entry Point: tts_app.py (84 lines)

```python
import sys, os
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog
from PyQt6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt
from version import VERSION
from app_constants import STYLE
from app_utils import load_settings, save_settings, _install_exception_hook
from main_window import MainWindow
from settings_dialog import SettingsDialog

class TrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.settings = load_settings()
        self.main_window = MainWindow(self.settings)
        # Creates QSystemTrayIcon with context menu (Open, Settings, Quit)
        # Shows main window on startup

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    _install_exception_hook()
    TrayApp().run()
```

---

## API Providers

| Provider | Role | Settings Key | Notes |
|----------|------|-------------|-------|
| GenMax | TTS PRIMARY | genmax_api_key | Proxy of ElevenLabs, cheaper |
| ElevenLabs | TTS fallback | el_api_keys (list, max 3) | Direct API |
| Gemini | Enhance/Chat PRIMARY | gemini_api_key | Free tier |
| DeepSeek | Enhance/Chat fallback | ds_api_key | Paid |

### GenMax API Endpoints (discovered 2026-05-10)
```
POST   /v1/text-to-speech/{voice_id}    ← TTS (primary usage)
GET    /v1/history/{task_id}            ← check task status
GET    /v1/auth/me                      ← user info + credit_balance
GET    /v1/default-voices               ← ElevenLabs built-in voices (paginated)
GET    /v1/shared-voices                ← shared voice library (paginated)
GET    /v1/models                       ← available models
GET    /v1/languages                    ← supported languages
POST   /v1/speech-to-text              ← audio → text + word timestamps (STT)
```

### Voice Fetching Logic
VoiceFetcher & SharedVoiceFetcher auto-prioritize GenMax if genmax_key is set, fallback to ElevenLabs.

---

## App Workers (app_workers.py — 15 classes)

```
VoiceFetcher(QThread)         ← fetch voices (GenMax first → ElevenLabs)
SharedVoiceFetcher(QThread)   ← fetch shared voices
AudioPreviewDownloader(QThread) ← download voice preview audio
AddSharedVoiceWorker(QThread)   ← add shared voice to account
PromptGeneratorWorker(QThread)  ← Gemini/DeepSeek generate script ideas
SuggestAnswersWorker(QThread)   ← suggest chat replies
UpdateChecker(QThread)          ← check GitHub releases
UpdateDownloader(QThread)       ← download update installer
Worker(QThread)                 ← FULL pipeline: enhance + TTS
_TTSOnlyWorker(QThread)        ← TTS only (no enhance)
PreviewWorker(QThread)          ← preview enhance result
GeminiWorker(QThread)           ← Chat tab: Gemini/DeepSeek conversation
FeedbackSender(QThread)         ← send feedback via Telegram
SpeechToTextWorker(QThread)     ← GenMax STT: audio → text + timestamps
_CreditsChecker(QThread)        ← check GenMax + ElevenLabs credits
words_to_srt(words)             ← convert word timestamps → SRT string
```

### Worker._enhance() Flow
1. Gets temperature from settings (0.0-1.0)
2. Prepends `get_creativity_guide(temperature)` to system prompt (GHI ĐÈ rule)
3. Calls Gemini API (primary) or DeepSeek (fallback)
4. Returns enhanced script

---

## Creativity System (get_creativity_guide in app_constants.py)

**Formula:** X% = choose X% of sentences to rewrite, each at X% depth

```python
def get_creativity_guide(temperature: float) -> str:
    pct = int(temperature * 100)
    filler   = pct // 10               # filler words
    rephrase = max(0, pct - 25)        # rephrase% (starts at 25%)
    can_lead = "CÓ" if pct >= 50 else "KHÔNG"
    can_new  = "CÓ" if pct >= 70 else "KHÔNG"
    # Builds depth description + returns GHI ĐÈ instructions
```

### Example outputs:
- 0%: format only, no changes
- 23%: 2/10 sentences → "thêm 2 từ đệm/cảm thán"
- 43%: 4/10 sentences → "thêm 4 từ đệm → đảo cấu trúc câu (18%)"
- 67%: 6/10 sentences → "thêm 6 từ đệm → đảo cấu trúc (42%) → thêm câu dẫn"
- 89%: 8/10 sentences → "thêm 8 từ đệm → ... → câu mới → content writer"

Guide is PREPENDED to system prompt with explicit "GHI ĐÈ" directive.

---

## STT/Speech-to-Text Feature (v1.7.0)

- Tab 3 in MainWindow: "📝 STT"
- Drop zone for MP3/WAV files
- Calls GenMax POST /v1/speech-to-text (multipart form: file + model_id)
- Returns: text + words array [{text, start, end, type}]
- words_to_srt() converts to SRT format
- Export button opens QFileDialog → saves .srt file

---

## UI Layout (main_window.py)

### Tab 1: 💬 Chat → Kịch Bản
- Chat interface with Gemini/DeepSeek
- Generate script ideas
- Send to TTS tab

### Tab 2: 🎙 TTS
- Script editor (QTextEdit)
- Voice selector + preview
- Style buttons (emoji, add style, prompt wizard)
- Creativity slider (0-100%) with real-time depth label underneath
- Enhance button → Preview → TTS
- Output filename field
- Credits display (GenMax + ElevenLabs)

### Tab 3: 📝 STT
- Drop zone for audio files
- "Nhận diện giọng nói" button
- Result text area
- "Xuất SRT" export button

---

## Settings (settings_dialog.py — 4 tabs)

### Tab: API Keys
- GenMax API Key (xi-api-key)
- ElevenLabs API Keys (up to 3, add/remove buttons)
- Gemini API Key
- DeepSeek API Key
- Guide links

### Tab: Prompts
- Prompt presets (Nghiêm túc, Funny, v.v.)
- Custom prompt editor
- Prompt wizard dialog

### Tab: Voices
- Auto-fetch voices (GenMax first → ElevenLabs)
- Voice list with search
- Voice preview (play sample)
- Add from shared library
- Selected voice display

### Tab: Output
- Output directory
- Voice ID
- Model selection

---

## Build System (TTS.spec)

```python
# macOS: .app bundle → DMG
# Windows: single .exe (console=False, windowed=True)
# CI: GitHub Actions triggered by tag v*
hiddenimports = [
    'PyQt6.sip', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'PyQt6.QtMultimedia', 'PyQt6.QtNetwork',
    'app_constants', 'app_utils', 'app_workers', 'app_dialogs',
    'voice_library', 'settings_dialog', 'main_window', 'version',
    'telegram_config', 'certifi',
]
```

---

## Critical Rules

1. **[IMPORT]** After ANY refactor: `python -m py_compile ALL files` + run app test
2. **[BUILD]** ALWAYS add new .py modules to hiddenimports in TTS.spec
3. **[IMPORT]** NEVER import from right-side modules (see dependency chain)
4. **[API]** Gemini first → DeepSeek fallback, GenMax first → ElevenLabs fallback
5. **[GENMAX]** Use GenMax proxy for voices/STT when key available (cheaper)
6. **[CREATIVITY]** Guide PREPENDED to system prompt with GHI ĐÈ
7. **[RELEASE]** Push tag v* → CI builds and publishes DMG+EXE automatically
8. **[GATEKEEPER]** macOS blocks unsigned app → Ctrl+click → Open

---

## Common Bug Patterns (FIXED in v1.5.1→v1.7.6)

- Missing Qt imports after refactor: QWidget, QLineEdit, QMenu, QSlider, QTimer, QUrl, QAction
- Missing worker imports: _CreditsChecker, VoiceFetcher, AudioPreviewDownloader
- Missing stdlib imports: sys, subprocess, webbrowser
- Missing config: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- PyInstaller not detecting new modules → add to hiddenimports
- Windows SSL: need certifi in hiddenimports
- Save settings crash on Windows → wrapped in try/except

---

## Session State (2026-05-11)

**Done:**
- All imports fixed across all 8 .py files
- TTS.spec hiddenimports complete + certifi
- GenMax credits via /v1/auth/me
- VoiceFetcher/SharedVoiceFetcher use GenMax proxy
- Speech-to-Text tab + SRT export
- Creativity: exact % formula (X% sentences × X% depth), continuous generation
- Creativity depth shown in UI under slider
- Settings save wrapped in try/except for Windows safety
- Current version: v1.7.6

**Next:**
- Customer testing on Windows
- Integrate GenMax models/languages endpoints
