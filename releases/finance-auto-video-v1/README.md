# Finance Auto Video v1

Pipeline gốc rễ:

1. Bundled Auto-Create script: article URL -> `script.json` + `script-90s.txt`
2. Escbase: giải nén `template3.zip` riêng cho từng video
3. QA gate: validate script/visual/template trước khi render
4. Escbase render: ElevenLabs v3, voice Nhật Phong, FullHD 1080x1920

## Run

```bash
cd /Users/admin/hedra-studio
python3 releases/finance-auto-video-v1/run_finance_video.py "ARTICLE_URL"
```

Test script/project trước, chưa tốn voice:

```bash
python3 releases/finance-auto-video-v1/run_finance_video.py "ARTICLE_URL" --script-only
```

Output mặc định:

```txt
/Users/admin/hedra-studio/output/final-renders/YYYYMMDD-topic-11labs/
```

Mỗi folder video có:

- `video_fullhd.mp4`
- `voice_11labs_nhatphong.mp3`
- `script.json`
- `script-90s.txt`
- `article.json`
- `preview.png`
- `manifest.json`
- `qa-report.json`
- `escbase/` bản Escbase đã giải nén riêng cho video đó

## QA Gates

Mỗi video phải pass:

- 6 scenes, đúng sentence/reveal counts: `1,3,3,3,4,3`.
- `script-90s.txt` khớp `slideScripts` trong `app.js`.
- Không còn token `{{...}}` chưa bind.
- Không còn chữ demo/template như `1.42B`, `HORMUZ`, `BTC BTC`.
- Visual coverage đạt ngưỡng, các field visual xuất hiện trong HTML.
- Semantic alignment: câu voice chính phải khớp visual reveal tương ứng.
- Escbase `validate_slide.py --semantic-report` pass trước render.
- Slide 1 phải pass TikTok safezone; hero đã được thu gọn để không chạm vùng UI dưới.
- Slide 4 mapping theo reveal thật của Escbase: câu 2/3 khớp workflow grid `bullet1`/`bullet2`.
- Hero headline/subhead/chips có giới hạn ngắn hơn để bài Mỹ-Iran/Hormuz vẫn pass safezone.
- `Hormuz` là nội dung hợp lệ trong bài địa chính trị; QA chỉ cấm cụm demo cũ `2.52T, BTC, HORMUZ`.
- Slide 3 đã giảm gauge/gap để pass safezone với headline dài như stablecoin/tokenization.

## Rules

- Chỉ dùng `elevenlabs`.
- Voice cố định: Nhật Phong `6adFm46eyy74snVn6YrT`.
- Model cố định: `eleven_v3`.
- GenMax và ai33 không nằm trong luồng chính.
- Template finance dùng token binding, không replace theo chữ mẫu.
