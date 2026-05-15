# HANDOFF.md - Codex Account Switching Guide

File nay la diem bat dau cho moi account Codex moi.
Doc file nay truoc, sau do moi doc `CLAUDE.md`.

Ly do: `CLAUDE.md` co Session Log dai va doi khi update chua chuan. Git status, git log, git diff va file nay la bo nguon dung de noi viec.

---

## Start Here

Khi mo account Codex moi trong `/Users/admin/hedra-studio`, chay cac lenh nay truoc khi sua code:

```bash
cd /Users/admin/hedra-studio
git status --short --branch
git log --oneline --decorate -n 10
git diff --stat
git diff --staged --stat
```

Sau do kiem tra engine:

```bash
cd /Users/admin/Auto-Create-Video
git status --short --branch
git log --oneline --decorate -n 10
git diff --stat
git diff --staged --stat
```

Neu `HANDOFF.md` va git khac nhau, tin git truoc, roi update lai `HANDOFF.md`.

---

## Current Goal

Tich hop Auto Video engine vao Hedra Studio theo huong UI wrapper:

- Hedra Studio chi nhan input, hien config, script, progress, log, result.
- Settings -> Auto Video doc/ghi truc tiep `/Users/admin/Auto-Create-Video/.env.local`.
- Engine `/Users/admin/Auto-Create-Video` la source of truth cho render/config Auto Video.
- GenMax la TTS primary, ElevenLabs/LucyLab la cac provider co preview trong Settings.

---

## Current Verified State

Cap nhat lan cuoi: 12/05/2026.

### Hedra Studio repo

Path:

```bash
/Users/admin/hedra-studio
```

Git state luc ghi handoff:

```text
branch: main...origin/main
modified:
  CLAUDE.md
  app_utils.py
  app_workers.py
  auto_video_workers.py
  main_window.py
  settings_dialog.py
untracked:
  endpoints/
  endpoints 2/
  endpoints.zip
```

Commit gan nhat tren remote/local:

```text
9dcb57a feat: hien kich ban trong Auto Video tab
40460fd feat: progress UI voi % + step label cho Auto Video
63305f0 fix: them GENMAX_POLL_TIMEOUT_MS=300000 vao subprocess env
```

Y nghia: repo Hedra Studio dang co nhieu thay doi chua commit sau commit `9dcb57a`. Khong duoc reset/revert neu chua review diff.

### Auto-Create-Video engine repo

Path:

```bash
/Users/admin/Auto-Create-Video
```

Git state luc ghi handoff:

```text
branch: main...origin/main [ahead 8]
many modified files
many untracked files
```

Commit gan nhat:

```text
14c91f0 feat: them 6 SFX categories con thieu (success/fail/reveal/countdown/cinematic/drumroll)
bbc094b fix: thay Anton/Bebas Neue bang Be Vietnam Pro (ho tro tieng Viet)
2b88cb9 perf: tang hyperframes workers 4->6 cho M1 Pro 6-core
16da4dc perf: them --gpu --workers 4 cho M1 Pro render
cb8949a feat: GenMax auto-retry 7 lan khi scene loi
4d63483 fix: tang GENMAX_POLL_TIMEOUT_MS default len 300s
```

Y nghia: Task 19, 20, 21 da co commit local trong engine, du `CLAUDE.md` Task List co the chua tick dung.

---

## What Was Recently Done

Nhung muc moi nhat trong `CLAUDE.md` Session Log:

- Auto Video Settings page doc/ghi `.env.local`.
- Auto Video tab dung engine config tu `.env.local`.
- Voice presets trong Settings -> Auto Video.
- TikTok avatar settings + outro preview.
- Voice preview cho GenMax, ElevenLabs, LucyLab.
- GenMax preview retry 3 lan.
- GenMax docs alignment: body co `provider`, `model_id`, `language_code`.
- GenMax language fallback theo voice/model.
- Voice preview playback dung `/usr/bin/afplay` tren macOS, QMediaPlayer fallback.

Verify gan nhat da ghi trong `CLAUDE.md`:

```bash
venv/bin/python -m py_compile settings_dialog.py app_workers.py auto_video_workers.py main_window.py
npx tsc --noEmit
```

Can chay lai verify neu tiep tuc sua code vi worktree hien dang dirty.

---

## Important Project Rules

- Khong public source code. Repo private.
- Khong reset/revert thay doi la neu chua biet ai tao.
- Khong tin moi dong trong `CLAUDE.md` neu git/code noi khac.
- Moi task dai phai update `HANDOFF.md` truoc khi ket thuc session.
- Neu bi limit giua chung, ghi muc `[IN PROGRESS]` o duoi voi:
  - da lam toi dau
  - file nao da sua
  - lenh nao da chay
  - buoc tiep theo chinh xac
- Neu task xong, verify bang command roi moi ghi DONE.
- Uu tien commit nho theo tung task. Khong gom 10 viec vao mot commit lon.

---

## Architecture Snapshot

Hedra Studio:

```text
app_constants.py
app_utils.py
app_workers.py
app_dialogs.py
voice_library.py
settings_dialog.py
main_window.py
tts_app.py
auto_video_workers.py
```

Dependency rule:

```text
app_constants -> app_utils -> app_workers -> app_dialogs -> voice_library -> settings_dialog -> main_window -> tts_app
app_constants -> app_utils -> auto_video_workers
```

Never import from the right side back to the left side.

Auto Video engine:

```text
/Users/admin/Auto-Create-Video
```

Important files:

```text
src/config.ts
src/pipeline.ts
src/tts/genmax-client.ts
src/tts/tts-client.ts
src/render/hyperframes-runner.ts
src/render/templates/styles.css
assets/sfx/
.env.local
```

---

## Known Current Risks

- `hedra-studio` has large uncommitted UI/config changes. Review `git diff` before touching same files.
- `Auto-Create-Video` is ahead of origin by 8 commits and also dirty. Do not assume remote has the latest work.
- `endpoints.zip`, `endpoints/`, and `endpoints 2/` exist in `hedra-studio`; likely GenMax docs/reference artifacts. Decide later whether to keep, ignore, or delete.
- Engine push may be blocked depending on repo ownership/permissions.

---

## Next Exact Step

Neu account moi chi can tiep tuc tu day:

1. Run startup commands in both repos.
2. Read latest part of `CLAUDE.md` Session Log.
3. Run:

```bash
cd /Users/admin/hedra-studio
git diff -- settings_dialog.py auto_video_workers.py main_window.py app_workers.py app_utils.py
```

4. Decide whether current uncommitted Hedra changes should become one or more commits.
5. In engine, inspect dirty changes after local commits:

```bash
cd /Users/admin/Auto-Create-Video
git diff --stat
git diff -- src/config.ts src/tts/genmax-client.ts src/pipeline.ts package.json
```

6. Before any commit, run verification:

```bash
cd /Users/admin/hedra-studio
venv/bin/python -m py_compile app_constants.py app_utils.py app_workers.py app_dialogs.py voice_library.py settings_dialog.py main_window.py tts_app.py auto_video_workers.py

cd /Users/admin/Auto-Create-Video
npx tsc --noEmit
```

---

## Session Update Template

Append to this section at end of every account/session:

```md
### [YYYY-MM-DD HH:MM - ACCOUNT HANDOFF]
- Status: IN PROGRESS / DONE / BLOCKED
- Goal:
- Files changed:
- Commands run:
- Verification:
- Problems:
- Next exact step:
```

---

## Account Handoff Log

### [2026-05-13 10:42 - CODEX CONTINUE VERIFY]
- Status: DONE
- Goal: Continue from handoff, verify current dirty worktrees, and reconcile stale task status.
- Files changed: `CLAUDE.md`, `HANDOFF.md`.
- Commands run: Hedra git status/log/diff stats; engine git status/log/diff stats; Hedra full module py_compile; SettingsDialog offscreen smoke test; `git diff --check`; engine `npx tsc --noEmit`; targeted engine vitest for config/html composer/GenMax/ElevenLabs/Eleven v3 style.
- Verification: Hedra Python compile OK; SettingsDialog offscreen OK; diff check OK; engine TypeScript OK; targeted engine tests OK (5 test files, 26 tests).
- Problems: both repos remain intentionally dirty with broad Auto Video/UI/engine changes. No commit was made yet because current diff spans multiple logical tasks.
- Next exact step: manually test real Hedra Studio Settings -> Auto Video preview (`Trung`, then one newly added GenMax Voice ID). If UI is good, split commits by scope: Hedra Settings/Auto Video wrapper, Hedra TTS GenMax/Eleven v3 style, engine config/render/TTS docs alignment.

### [2026-05-13 - GENMAX LANGUAGE DEFAULT VIETNAMESE]
- Status: DONE
- Goal: Make Settings -> Auto Video -> GenMax language default to Vietnamese while still supporting the GenMax API language dropdown.
- Files changed: `settings_dialog.py`, `HANDOFF.md`.
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; SettingsDialog offscreen smoke test for default language, API language list, and MiniMax language; full Hedra module py_compile.
- Verification: UI defaults to `Vietnamese (vi)` for ElevenLabs/GenMax and `_pv_genmax_language()` returns `vi` for saving; simulated API list includes `Japanese (ja)` and keeps Vietnamese selected; MiniMax defaults to `Vietnamese`; Python compile OK.
- Changes: added `_pv_set_genmax_language_choices()` to merge default Vietnamese/English options with GenMax API languages and select Vietnamese by default. Language row help text now says Vietnamese is default and `Kiểm tra` loads GenMax languages for changing.
- Problems: none known.
- Next exact step: reopen Settings -> Auto Video. `Ngôn ngữ` should show `Vietnamese (vi)` by default; after `Kiểm tra`, the dropdown should include GenMax API languages.

### [2026-05-13 - SETTINGS WORKER SAFETY PASS]
- Status: DONE
- Goal: Rerun bug check after GenMax preview changes and harden remaining Settings worker callbacks.
- Files changed: `settings_dialog.py`, `HANDOFF.md`.
- Commands run: full Hedra module py_compile; fresh SettingsDialog init/delete smoke test; worker-finished-after-dialog-delete smoke test; preview flow smoke test; `git diff --check -- settings_dialog.py HANDOFF.md`.
- Verification: compile OK; SettingsDialog can initialize/delete with real settings; worker finishing after dialog delete no longer aborts; current cached GenMax preview plays local file before API key check; uncached GenMax preview triggers catalog lookup and loading state; diff check OK.
- Changes: wrapped VoiceFetcher and voice-list preview downloader in `_keep_preview_thread_alive`; changed their callbacks to `_pv_safe_call`; added `_pv_alive()`/`_pv_safe_call()` for callbacks that may fire after the Settings dialog is closed.
- Problems: no further crash/preview bugs found in smoke coverage. Full manual UI pass still requires reopening the real app.
- Next exact step: reopen Hedra Studio, test Settings -> Auto Video preview with `Trung`, then add one new GenMax Voice ID and press preview once.

### [2026-05-13 - PREVIEW THREAD CRASH FIX]
- Status: DONE
- Goal: Fix macOS `Python quit unexpectedly` crash after opening/closing Settings while GenMax preview/catalog workers are still running.
- Files changed: `settings_dialog.py`, `HANDOFF.md`.
- Commands run: inspected latest macOS crash report; `venv/bin/python tts_app.py`; SettingsDialog offscreen init; preview worker lifetime smoke test; full Hedra module py_compile.
- Verification: crash report showed `QThread::~QThread()` abort, with `_VoicePreviewUrlDownloadWorker` still running. All GenMax catalog/download/generated-preview QThreads are now kept alive in module-level `_LIVE_PREVIEW_THREADS` until they finish. Python compile OK.
- Changes: added `_keep_preview_thread_alive()` and wrapped `_GenMaxCatalogWorker`, `_VoicePreviewUrlDownloadWorker`, and `_PipelineVoicePreviewWorker` creation sites.
- Problems: if Hedra Studio was already running before this fix, close it fully before relaunch.
- Next exact step: reopen Hedra Studio, open/close Settings while preview download is active; Python should not abort from QThread destruction.

### [2026-05-13 - GENMAX NEW VOICE PREVIEW FLOW]
- Status: DONE
- Goal: Make newly added GenMax Voice IDs get a usable preview sample instead of silently failing.
- Files changed: `settings_dialog.py`, `HANDOFF.md`.
- Commands run: full Hedra module py_compile; fresh SettingsDialog smoke test for current cached GenMax preview.
- Verification: current cached preview still resolves to `genmax-10688c2bc2be49fcb953ebc2.wav`; Python compile OK.
- Changes: after adding a GenMax voice, if there is a GenMax API key and no saved sample URL yet, the app triggers `Kiểm tra` to resolve/download its GenMax sample. If the user presses preview for a new uncached GenMax voice, the preview button switches to loading, runs catalog lookup once, downloads the sample, then plays it. If GenMax has no sample for that Voice ID, the button resets and a clear warning is shown.
- Problems: this requires network/API only for the first-time sample download of a newly added voice; after that preview is local.
- Next exact step: add a new GenMax Voice ID, wait for `Kiểm tra` to finish, then press preview. If preview was pressed first, it should play automatically after the sample download completes.

### [2026-05-13 - TRUNG LOCAL PREVIEW VERIFIED]
- Status: DONE
- Goal: Check why preset `Trung` did not play and make its local preview easier to hear.
- Files changed: `settings_dialog.py`, `HANDOFF.md`; normalized local cache file `voice_preview_cache/genmax-10688c2bc2be49fcb953ebc2.wav`.
- Commands run: `afinfo`; `ffprobe`; `ffmpeg volumedetect`; `afplay`; SettingsDialog preview smoke test with `subprocess.Popen` intercepted; full Hedra module py_compile.
- Verification: Trung cache file is valid WAV, 3.668753s, 44100 Hz mono PCM; `afplay` exits 0; preview button path calls `afplay /Users/admin/Library/Application Support/TTSApp/voice_preview_cache/genmax-10688c2bc2be49fcb953ebc2.wav`; Python compile OK.
- Changes: normalized Trung preview loudness from mean `-25.6 dB` to `-16.4 dB` and peak `-1.5 dB`; `_pv_preview_voice()` now checks local cache before requiring API key, so GenMax local sample can play fully offline.
- Problems: if Hedra Studio is already running, it must be restarted to load the updated code.
- Next exact step: close/reopen Hedra Studio, select preset `Trung`, press preview. If still silent, check macOS output device/volume because the app is launching `afplay` with a valid audible WAV.

### [2026-05-13 - GENMAX PREVIEW NO AUTO NETWORK]
- Status: DONE
- Goal: Stop Settings/preview from auto-calling GenMax and make current voice preview play from a local file keyed only by Voice ID.
- Files changed: `settings_dialog.py`, `HANDOFF.md`; local cache file under `~/Library/Application Support/TTSApp/voice_preview_cache/`.
- Commands run: rewrote current voice sample cache from saved GenMax `preview_url`; fresh SettingsDialog smoke test; full Hedra module py_compile.
- Verification: fresh SettingsDialog resolves current GenMax cache to `voice_preview_cache/genmax-10688c2bc2be49fcb953ebc2.wav`; file exists, is 323628 bytes, starts with `RIFF`; Python compile OK.
- Changes: opening Settings no longer auto-runs `_pv_load_genmax_catalog`; selecting/adding GenMax presets no longer auto-runs catalog lookup; pressing preview no longer calls GenMax when no local sample exists. Manual `Kiểm tra` is the only catalog network action. Network/DNS errors now show a short Vietnamese message instead of raw Requests stack text.
- Problems: app must be restarted to pick up this code if Hedra Studio is already running.
- Next exact step: close and reopen Hedra Studio, then press preview. It should play local cached WAV immediately and not hit `api.genmax.io`.

### [2026-05-13 - GENMAX PREVIEW URL DISK CACHE]
- Status: DONE
- Goal: Make GenMax preview truly instant after restart by storing the voice sample URL mapping on disk, not just the downloaded audio file.
- Files changed: `settings_dialog.py`, `HANDOFF.md`; local cache files under `~/Library/Application Support/TTSApp/`.
- Commands run: wrote current voice mapping to `genmax_preview_urls.json`; verified SettingsDialog loads mapping before `Kiểm tra`; verified computed cache file exists; full Hedra module py_compile.
- Verification: fresh SettingsDialog loads current `GENMAX_VOICE_ID` preview URL from disk; `_pv_preview_cache_path()` points to an existing 323628-byte cached sample; Python compile OK.
- Changes: `settings_dialog.py` now persists GenMax `voice_id -> preview_url` in `DATA_DIR/genmax_preview_urls.json`. Catalog lookups update this mapping. On the next app open, preview can resolve the URL and cache path immediately without calling GenMax first.
- Problems: none known for current voice.
- Next exact step: reopen Hedra Studio; Settings -> Auto Video -> preview should play immediately without pressing `Kiểm tra`.

### [2026-05-13 - GENMAX TEXT-PLAIN WAV SAMPLE FIX]
- Status: DONE
- Goal: Fix GenMax preview download rejecting valid sample audio when storage returns the wrong `content-type`.
- Files changed: `settings_dialog.py`, `HANDOFF.md`.
- Commands run: live probe of current GenMax shared voice sample; `_VoicePreviewUrlDownloadWorker` smoke test with current sample URL; full Hedra module py_compile.
- Verification: current GenMax sample URL returns `content-type: text/plain` but bytes start with `RIFF...WAVE`; worker now downloads it successfully and writes 323628-byte WAV data; Python compile OK.
- Changes: preview downloader now detects audio by byte signature (`ID3`, MP3 frame, `RIFF/WAVE`, `OggS`, `fLaC`, MP4 `ftyp`) instead of rejecting solely by HTTP content-type. If a text response is actually a URL, it follows that URL once.
- Problems: none known.
- Next exact step: reopen Hedra Studio, Settings -> Auto Video, click preview; GenMax sample should play without the `Preview không phải audio: text/plain` warning.

### [2026-05-13 - GENMAX SHARED VOICE SAMPLE PREFETCH]
- Status: DONE
- Goal: Make the current GenMax voice preview play immediately by using GenMax's own shared-voice sample URL.
- Files changed: `settings_dialog.py`, `HANDOFF.md`; local cache file under `~/Library/Application Support/TTSApp/voice_preview_cache/`.
- Commands run: live GenMax API probe for current `GENMAX_VOICE_ID`; `_GenMaxCatalogWorker` smoke test; downloaded current voice `preview_url` to cache; full Hedra module py_compile.
- Verification: current voice `FTYCiQ...u0ch` is found via `GET /v1/shared-voices?search=<voice_id>` with `preview_url`; cached sample file exists at `voice_preview_cache/genmax-89f147df7961232d2367d550.mp3`; Python compile OK.
- Changes: `_GenMaxCatalogWorker` now searches shared voices by saved voice IDs as well as names, so shared voices like the current one resolve to their GenMax sample URL. GenMax preview remains sample-only and does not synthesize fallback audio.
- Problems: if a future GenMax voice has no `preview_url` in shared/default/minimax catalogs, the preview button cannot be instant unless a cache file is created some other way.
- Next exact step: reopen Settings -> Auto Video and click the preview button for the current GenMax voice; it should play the cached GenMax sample immediately.

### [2026-05-13 - GENMAX PREVIEW SAMPLE ONLY]
- Status: DONE
- Goal: Make GenMax preview use only GenMax's built-in sample audio for that voice, never synthesize a custom preview sentence as fallback.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; `QT_QPA_PLATFORM=offscreen` SettingsDialog smoke test for GenMax no-sample and sample-url branches.
- Verification: Python compile OK; GenMax config without `preview_url` stays sample-only; GenMax config with `preview_url` creates `_VoicePreviewUrlDownloadWorker`/cache path.
- Changes: pressing preview for GenMax now triggers catalog lookup if sample URL is not loaded; if GenMax returns a sample URL, the app downloads/plays/caches that file; if GenMax does not return a sample URL or download fails, the app shows a warning and does not call the TTS render endpoint.
- Problems: Current `.env.local` `GENMAX_VOICE_ID` was not found in default/shared/minimax catalog checks during manual probe, so GenMax may not expose a sample for that exact ID through the documented endpoints.
- Next exact step: in Settings -> Auto Video, click `Kiểm tra`; if the voice appears with a GenMax sample, preview will play/cache. If it says no sample, the voice ID is usable for TTS render but GenMax does not expose a reusable listen-preview URL through the catalog.

### [2026-05-13 - GENMAX CATALOG PREVIEW CACHE]
- Status: DONE
- Goal: Use GenMax's built-in voice sample audio for Settings preview instead of rendering a new TTS sample whenever possible.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; full Hedra module py_compile; `QT_QPA_PLATFORM=offscreen` SettingsDialog smoke test for GenMax `preview_url` config and URL-download worker.
- Verification: Python compile OK; SettingsDialog initializes; preview config carries GenMax `preview_url`; cache path resolves under `DATA_DIR/voice_preview_cache/*.mp3`.
- Changes: GenMax catalog sample URLs are stored by voice ID; selecting/applying a GenMax voice schedules background download of the sample to persistent cache; pressing preview plays the cached file immediately when present; if the sample URL is missing or download fails, the old generated-preview path is still used as fallback.
- Problems: Some GenMax voices may not expose a sample URL in the catalog; those voices still need fallback synthesis on first preview.
- Next exact step: open Settings -> Auto Video, click `Kiểm tra`/select a GenMax voice, wait briefly for background cache, then press preview. Second press should play instantly from cache.

### [2026-05-13 - VOICE PREVIEW SAMPLE TEXT V2]
- Status: DONE
- Goal: Make cached voice preview sample long enough to judge voice quality.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`.
- Verification: Python compile OK.
- Changes: preview text restored to `Xin chào, đây là giọng đọc mẫu trong Hedra Studio.` and cache sample version changed to `hedra-preview-v2` so old short cached files are not reused.
- Problems: none.
- Next exact step: select/add a favorite voice and let the background cache regenerate the v2 preview.

### [2026-05-13 - PERSISTENT VOICE PREVIEW CACHE]
- Status: DONE
- Goal: Save voice preview audio for favorite voices so the preview button can play immediately after the first successful generation.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; full Hedra module py_compile; `QT_QPA_PLATFORM=offscreen` SettingsDialog smoke test for preview cache path.
- Verification: Python compile OK; cache path resolves under `DATA_DIR/voice_preview_cache/*.mp3`.
- Changes: `_PipelineVoicePreviewWorker` can write directly to cache path; preview cache is keyed by provider/voice/api/model/language/endpoint/sample version; choosing a preset or adding a new favorite voice starts background prefetch; pressing preview uses cached MP3 immediately if present.
- Problems: first preview for a never-cached voice still depends on provider render speed.
- Next exact step: add/select a favorite voice, wait for background prefetch, then press preview; subsequent presses should play immediately.

### [2026-05-13 - VOICE PREVIEW SPEEDUP]
- Status: DONE
- Goal: Make Settings -> Auto Video voice preview faster.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; full Hedra module py_compile; `QT_QPA_PLATFORM=offscreen` SettingsDialog + `_PipelineVoicePreviewWorker` smoke test.
- Verification: Python compile OK; SettingsDialog initializes; preview worker initializes with default GenMax model/language.
- Changes: preview text shortened to `Xin chào.`; GenMax preview retries reduced 3 -> 2; GenMax/LucyLab polling starts at 0.75s and caps at 2s; preview audio is cached by provider/voice/model/language/API config so repeated clicks play immediately.
- Problems: first GenMax/LucyLab preview still depends on API queue speed; cache only helps after the first successful generation for the same voice/config.
- Next exact step: test the preview button with current GenMax voice and compare first click vs second click.

### [2026-05-13 - SOURCE LINK TOGGLE]
- Status: DONE
- Goal: Add Settings -> Auto Video checkbox to show/hide source domain/link in rendered video.
- Files changed: `settings_dialog.py`, `/Users/admin/Auto-Create-Video/src/config.ts`, `/Users/admin/Auto-Create-Video/src/pipeline.ts`, `/Users/admin/Auto-Create-Video/src/render/html-composer.ts`, `/Users/admin/Auto-Create-Video/src/config.test.ts`, `/Users/admin/Auto-Create-Video/src/render/html-composer.test.ts`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; full Hedra module py_compile; `QT_QPA_PLATFORM=offscreen` SettingsDialog smoke test; `npx tsc --noEmit`; `npx vitest run src/config.test.ts src/render/html-composer.test.ts`.
- Verification: Python compile OK; SettingsDialog has `_pv_show_source_link` checked by default; TypeScript OK; 2 test files passed, 14 tests passed.
- Problems: none.
- Next exact step: user can toggle `Nguồn bài báo` in Settings -> Auto Video. When off, engine writes `SHOW_SOURCE_LINK=false` and hides both bottom domain pill and outro `Nguồn: ...` line.

### [2026-05-13 - LOGO SVG SIMPLIFIED]
- Status: DONE
- Goal: Finish logo replace feature so SVG is only a wrapper around generated `avatar.png`, with no border/ring/styling added.
- Files changed: `settings_dialog.py`, `/Users/admin/Auto-Create-Video/assets/logo.svg`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; full Hedra module py_compile; Qt offscreen smoke test generating `/tmp/hedra_logo_replace_final/avatar.png` and `logo.svg`; generated current engine `assets/logo.svg` from current engine `assets/avatar.png`.
- Verification: Python compile OK; generated SVG contains `<image>` and no `<circle>` or `stroke=`.
- Problems: none.
- Next exact step: user can choose any new image and click `Lưu logo`; app overwrites engine `assets/avatar.png` and `assets/logo.svg`, backing up previous files first.

### [2026-05-13 - LOGO ASSET REPLACE TOOL]
- Status: DONE
- Goal: Let user choose an image in Hedra Studio and have the app create/replace engine `assets/avatar.png` and `assets/logo.svg`, without editing engine source code.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; Qt offscreen smoke test generating `/tmp/hedra_logo_feature_test/avatar.png` and `logo.svg`.
- Verification: Python compile OK; generated PNG and SVG both exist and SVG contains embedded image data.
- Problems: Engine tracked source files are not modified by this feature. Replacing `/Users/admin/Auto-Create-Video/assets/avatar.png` and `assets/logo.svg` is an intentional user asset operation. Existing files are backed up to `/Users/admin/Auto-Create-Video/assets/backup/<timestamp>/` before overwrite.
- Next exact step: user can use Settings -> Auto Video -> Chọn logo -> Lưu logo; then render again.

### [2026-05-12 17:42 - ENGINE SOURCE RESTORE]
- Status: DONE
- Goal: Stop touching original Auto-Create-Video source/assets for logo border experiments.
- Files changed: `HANDOFF.md`; restored `/Users/admin/Auto-Create-Video/src/render/templates/styles.css` and `/Users/admin/Auto-Create-Video/assets/logo.svg` back to git state.
- Commands run: backed up custom SVG to `/Users/admin/hedra-studio/local_artifacts/logo-custom-before-source-restore.svg`; `git restore -- src/render/templates/styles.css assets/logo.svg` in engine repo.
- Verification: `git status --short -- src/render/templates/styles.css assets/logo.svg` now has no output.
- Problems: Logo border/render changes that touched engine source are intentionally removed. Settings dialog changes in Hedra Studio still exist because they are app UI changes, not engine source.
- Next exact step: if logo customization should not touch any tracked source file, implement it through a generated/runtime asset path instead of engine tracked `assets/logo.svg`.

### [2026-05-12 17:37 - LOGO RING CLEANUP]
- Status: DONE
- Goal: Make logo/avatar border cleaner in Settings preview and rendered Auto Video output.
- Files changed: `settings_dialog.py`, `/Users/admin/Auto-Create-Video/src/render/templates/styles.css`, `/Users/admin/Auto-Create-Video/assets/logo.svg`, `HANDOFF.md`
- Commands run: regenerated engine `assets/logo.svg` from `assets/avatar.png`; `venv/bin/python -m py_compile settings_dialog.py`; `npx tsc --noEmit`.
- Verification: Python compile OK; TypeScript compile OK.
- Problems: Previous ring stacked SVG stroke + QLabel border + CSS glow, making the logo look heavy.
- Next exact step: reopen Settings preview; if still too visible, reduce SVG stroke opacity below `0.36`.

### [2026-05-12 17:28 - LOGO EDITOR ZOOM ONLY]
- Status: DONE
- Goal: Simplify logo/avatar editor: auto-center logo and expose only Zoom control.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; Qt offscreen render helper smoke test.
- Verification: Python compile OK; render helpers still return expected pixmap sizes.
- Problems: Worktree was already dirty before this fix; not committed separately.
- Next exact step: reopen Settings -> Auto Video -> Chọn logo/Căn lại and confirm only one Zoom slider is visible.

### [2026-05-12 15:58 - LOGO BORDER FIX]
- Status: DONE
- Goal: Restore visible border/ring for logo/avatar in rendered Auto Video banner/outro.
- Files changed: `settings_dialog.py`, `/Users/admin/Auto-Create-Video/src/render/templates/styles.css`, `/Users/admin/Auto-Create-Video/assets/logo.svg`, `HANDOFF.md`
- Commands run: regenerated engine `assets/logo.svg` from `assets/avatar.png`; `venv/bin/python -m py_compile settings_dialog.py`; `npx tsc --noEmit`.
- Verification: Python compile OK; TypeScript compile OK; `assets/logo.svg` now includes circular stroke rings; render CSS adds visible border/shadow to `.brand-icon` and `.tt-avatar`.
- Problems: Worktrees were already dirty before this fix; not committed separately.
- Next exact step: render a short Auto Video sample or inspect output HTML screenshot to visually confirm the ring thickness.

### [2026-05-12 15:50 - LOGO EDITOR FIX]
- Status: DONE
- Goal: Fix Settings -> Auto Video logo/avatar editor so selected logos auto-center and can be adjusted freely.
- Files changed: `settings_dialog.py`, `HANDOFF.md`
- Commands run: `venv/bin/python -m py_compile settings_dialog.py`; full module py_compile; Qt offscreen helper render smoke test.
- Verification: Python compile OK; `_round_logo_pixmap()` returns 180x180 pixmap; `_render_logo_square()` returns 512x512 pixmap.
- Problems: Existing worktree is already dirty from previous Auto Video changes, so this is not committed separately yet.
- Next exact step: user can reopen Settings -> Auto Video -> Chọn logo/Căn lại and verify default centering; if good, include this in the next settings commit.

### [2026-05-12 - HANDOFF BASELINE]
- Status: IN PROGRESS
- Goal: Make handoff reliable for multiple Codex Plus accounts.
- Files changed: `HANDOFF.md`
- Commands run: git status/log/diff-stat in both repos.
- Verification: not a code change.
- Problems: `CLAUDE.md` Task List can be stale; engine has Task 19-21 commits already.
- Next exact step: review dirty diffs and decide commit boundaries.
