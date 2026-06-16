# Escbase Slide Starter

Copy this folder for new decks unless the user explicitly requests a different template.

Keep these defaults unless asked otherwise:

- `preview-settings.json` subtitles: `enabled: true`, `fontSize: 18`, `bottom: 152`, `maxLines: 1`.
- BGM: custom `preview-assets/bgm/meta.mp3`, volume `0.3`.
- Grid overlay disabled.
- Preview background effect: `backgroundFx: "scan"`; keep the starter mixed per-slide canvas FX unless content requires a change.
- TikTok safezone for normal slide content: `100px 28px 200px` via `pixelle-slide-content`.
- Keep script sentence counts matched to reveal units.
- Replace placeholder source notes in `source/source.md` before writing final deck content.

When copied to `slide/<project>/`, update:

- `index.html` title/meta and slide DOM text/media.
- `script-90s.txt` and `slideScripts` in `app.js` with identical text.
- `preview-settings.json` BGM URL/path only if the copied asset path changes.
- `upload-metadata.json`.
