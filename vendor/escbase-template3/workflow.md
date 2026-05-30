# Quy trình dựng Escbase slide — v2 gọn

Tài liệu này là bản workflow ngắn để tạo/sửa deck trong repo Escbase. Khi có chi tiết mâu thuẫn, ưu tiên theo `AGENTS.md`, starter hiện tại, và kết quả `validate_slide.py`.

## Nguyên tắc mặc định

- Deck mới copy từ `template/escbase-slide-starter`.
- Không start `web_server.py` sau khi dựng slide, trừ khi user yêu cầu.
- Dùng `.venv/bin/python` cho lệnh Python nếu có.
- Giữ default starter trừ khi user yêu cầu:
  - grid off
  - `backgroundFx: "particles"`
  - subtitle bật, `fontSize: 18`, `bottom: 152`, `maxLines: 1`
  - BGM custom `preview-assets/bgm/meta.mp3`
  - TikTok safezone: top `100px`, left/right `28px`, bottom gap tối thiểu `200px`
- Vì subtitle bật mặc định, slide phải **visual-first**: không chép lại toàn bộ voiceover lên canvas.

## Bước 1 — Lưu và phân tích source

Trước khi viết `script-90s.txt` hoặc sửa DOM cho source bên ngoài:

1. Tạo `slide/<project>/source/`.
2. Lưu source gốc:
   - bài web: lưu URL + facts chính; nếu fetch được thì lưu `article.html` / `article.txt`
   - X/Twitter: dùng workflow trong skill `x-media-tools`, lưu `thread.txt`, `links.txt`, media local
   - video/media: tải về local, không hotlink trong slide
3. Viết `source/source.md` gồm:
   - URL/tác giả/ngày nếu có
   - facts quan trọng
   - phân biệt fact từ nguồn và bình luận/góc nhìn
   - media local đã dùng

Nếu source có nhiều video từ tác giả/chủ thread, tải và review các video cần cho deck, không chỉ video đầu tiên.

## Bước 2 — Chốt toàn bộ script chuẩn trước khi dựng

Script là phần quan trọng nhất của deck. Ở bước này phải chốt **toàn bộ `script-90s.txt` chuẩn final** trước khi dựng visual/DOM: số slide, số câu từng slide, nhịp reveal, câu nào ứng với reveal nào, và script đã đọc trôi miệng. Không chỉ chốt tone/hướng chung rồi vừa dựng vừa viết lại script.

1. Đọc `script-writing/START_HERE.md`.
2. Đọc `script-writing/SCRIPT_RULES.md`.
3. Đọc `script-writing/STYLE_INDEX.md`, chọn các style phù hợp nhất với source/tone user muốn, rồi đọc các file `style*.md` liên quan đó. Không đọc/trộn bừa toàn bộ style nếu không cần.
4. Nếu user chưa chốt sẵn script/tone, đưa nhiều phương án script để chọn:
   - thường là **5 bản `script-90s` đầy đủ** theo các style khác nhau
   - mỗi bản phải có đủ số dòng/slide dự kiến, viết như nội dung final có thể copy vào `script-90s.txt` nếu user chọn
   - mỗi bản phải thể hiện rõ số câu mỗi slide, tránh bản nháp chỉ là outline/hook rời
   - ghi rõ style/tone, hook, và khác biệt chính giữa các phương án
5. Khi user chọn một option, trước khi sửa DOM/CSS phải chốt bản final cuối cùng vào `script-90s.txt`; nếu cần chỉnh độ dài, số câu, demo-video pacing, hoặc reveal count thì làm ngay ở bước này.
6. Chỉ sau khi `script-90s.txt` final đã ổn mới sync `app.js`/`preview-settings.json` và dựng DOM.

Có thể bỏ qua bước nhiều phương án nếu user đã đưa script, hook, hoặc style rất cụ thể, nhưng vẫn phải kiểm tra/chốt format final của `script-90s.txt` trước khi dựng DOM.

### Format script chuẩn

- Mỗi dòng trong `script-90s.txt` = 1 slide.
- Mỗi dòng nên là một ý lớn.
- Số câu trong dòng = số reveal units của slide đó.
- Format mặc định nên giống starter/reference deck: slide 1 là một câu hook vừa, giật gân, hiểu ngay chủ đề; các slide giải thích sau hook thường có 3–4 câu vừa để visual có thời gian reveal. Không nén mọi slide thành 1 câu chỉ để mapping dễ pass.
- Slide 1 phải tránh giải thích dài: hook chỉ nên là một câu vừa có lực; nếu cần ngắt nhịp nhưng vẫn là 1 reveal ở các slide khác, dùng dấu phẩy, dấu hai chấm, hoặc gạch ngang thay vì dấu chấm.
- Khi tăng số câu, phải tăng đúng số `.slide-element` / `highlightable` / `lightable` tương ứng, và mỗi reveal phải khớp semantic với câu đó.
- Giọng final: văn nói, dễ hiểu, không robotic, không tóm tắt bài báo kiểu bản tin.
- Nội dung slide và script phải viết bằng tiếng Việt. Chỉ giữ tiếng Anh cho tên riêng, thuật ngữ kỹ thuật/chuyên ngành mà dịch ra sẽ mất nghĩa hoặc khó hiểu; các từ dev quen thuộc như `desktop`, `tool stack`, `source`, `coder` nên giữ nguyên khi đúng ngữ cảnh.

### Demo video trong script

Nếu source có demo video:

- Slide 1 là một câu hook vừa, giật gân, không giải thích dài.
- Demo đầu tiên đặt ngay sau hook, thường là slide 2.
- Demo dùng file local, không hotlink.
- Không hiển thị chi tiết hậu trường như “downloaded local”, “video muted”, “source file”.
- Nếu video có audio meaningful, ưu tiên audio gốc và tránh BGM đè.
- Script demo phải đủ dài để video “thở”: render mặc định ưu tiên thời lượng voice/TTS hơn độ dài clip, nên nếu muốn xem nhiều hơn thì kéo dài voice/script; nếu clip dài hơn voice, clip có thể bị cắt hoặc loop trong slide.

## Bước 3 — Tạo/cập nhật project từ starter

Deck mới nằm ở:

```text
slide/<project>/
```

Copy tối thiểu từ `template/escbase-slide-starter`:

- `index.html`
- `app.js`
- `style.css`
- `preview-settings.json`
- `script-90s.txt`
- `logo-escbase.ico`
- `preview-assets/bgm/meta.mp3`
- `source/`
- `upload-metadata.json`

Sau khi copy, thay placeholder bằng nội dung thật. Không copy lẫn source/media cũ từ deck khác.

## Bước 4 — Metadata sau khi script final

Không viết lại script ở bước này. `script-90s.txt` đã phải được chốt ở Bước 2; bước này chỉ tạo/cập nhật `upload-metadata.json` dựa trên script final và source đã phân tích.

- YouTube:
  - `title` tối đa 100 ký tự
  - `description` chia đoạn, có icon lead, nguồn, `#Escbase`, hashtag liên quan
  - `privacyStatus`
  - `tags` không có dấu `#`
- Facebook Reels:
  - `caption` không có title
  - không chứa source link trong caption
  - `videoState: "DRAFT"`
  - `sourceComment: "Nguồn: <url>"`

## Bước 5 — Dựng visual (`index.html` + `style.css`)

Visual là phần quan trọng thứ hai sau script. Trước khi code DOM/CSS, đọc `docs/visual-patterns/README.md` và lập **visual plan** ngắn cho từng slide: pattern nào, vì sao hợp câu voiceover, và twist sáng tạo riêng của deck là gì.

Mỗi deck nên có ít nhất một visual twist mới hoặc biến thể sáng tạo riêng, không chỉ copy lại template/card cũ. Có thể reuse component đẹp trong `template/` và `slide/`, nhưng phải đổi semantic/composition/motion cho đúng câu chuyện.

### Visual-first

- Mỗi slide nên có visual minh hoạ rõ ý: icon, shape, metric, ảnh/source media nhỏ, SVG, hoặc motion graphic.
- Slide 1 mặc định nên bám layout starter/reference: có logo/mark lớn làm visual trung tâm kèm hook. Nếu user không cung cấp logo/ảnh nhận diện, tự tạo logo/mark đơn giản phù hợp chủ đề hoặc tìm nguồn phù hợp rồi lưu vào `source/`/assets trước khi đưa vào slide.
- Khi slide nhắc đến thương hiệu/sản phẩm cụ thể, ưu tiên tìm hoặc tự tạo logo/mark nhận diện của thương hiệu đó và chèn vào visual thay vì chỉ viết text; nếu subtitle/voiceover đã đọc tên brand thì chỉ logo/mark là đủ. Lưu asset/source vào `source/` hoặc assets local trước khi dùng.
- Không dùng stack text card dài chỉ để lặp lại subtitle.
- Text hiển thị trên canvas cũng theo rule tiếng Việt ở phần script: viết tiếng Việt là mặc định, chỉ giữ tiếng Anh cho tên riêng/thuật ngữ/dev terms khi tự nhiên và rõ nghĩa hơn.
- Mỗi reveal nên tương ứng 1 ý rõ:
  - 1 visual chính
  - 1 metric
  - 1 keyword
  - 1 card rất ngắn
- Nếu slide đã rõ qua subtitle, thêm chữ trên canvas là phương án cuối.

### Mapping/reveal

- Slide thường: reveal units = số `.slide-element`.
- Slide `data-mode="highlight"`: reveal units = `.slide-element` + `.highlightable`.
- Slide `data-mode="traffic-light"`: reveal units = `.slide-element` + `.lightable`.
- Nếu dùng highlight/traffic-light, bắt buộc đặt `data-mode` trên `.slide`.
- Không gộp 2 câu voiceover vào 1 reveal nếu màn hình chỉ hiện 1 ý.
- Không để 1 câu voiceover nói về 2–3 card hiện lần lượt.

### Layout/safezone

- Giữ safezone starter:

```css
.slide-content {
  padding: 100px 28px 200px;
  justify-content: flex-start;
}
```

- Không đặt text/CTA/metric quan trọng sát đáy hoặc sát mép phải.
- Trong vùng safezone còn lại sau padding top `100px` và bottom `200px`, cố căn visual/text card/animation lấp đầy hợp lý: tránh để trống quá nhiều phía trên/dưới hoặc làm visual quá nhỏ, vì người xem không thích slide bị rỗng.
- Nếu nội dung chật, rút chữ, gộp visual, hoặc chia slide; không bỏ safezone.
- `validate_slide.py` là source of truth cho safezone: top `>= 100px`, bottom gap `>= 200px`.

### DOM/CSS

- Mỗi slide có background dạng `<div class="slide-bg slide-bg-N"></div>`.
- Mỗi `.slide-element` có animation class như `fade-up` hoặc `scale-in`.
- Animation custom trigger qua parent visible:

```css
.slide-element.visible .my-animation {
  animation: ...;
}
```

- Append CSS custom ở cuối `style.css`.
- Dùng biến theme (`--primary`, `--accent`, `--success`) thay vì hardcode màu khi hợp lý.
- Reuse component/pattern có sẵn nếu đúng nghĩa: `flow-diagram`, `split-panel`, `workflow-grid`, `risk-cards-container`, `premium-traffic-box`, `glowing-conclusion`, `source-tag`, `hero-orbit`, hoặc pattern trong `docs/visual-patterns/`.
- Chỉ custom component mới khi component có sẵn không diễn đạt đúng ý.
- Nếu dùng counter/progress động, kiểm tra `animateCounters()` / reset state trong `app.js`.

## Bước 6 — Preview settings, audio, subtitle

Preview Editor hiện sync nhiều file. Khi sửa trong Preview Editor:

- script sẽ sync:
  - `script-90s.txt`
  - `upload-metadata.json`
  - `preview-settings.json -> slides.scriptLines`
  - `app.js -> slideScripts`
  - `app.js -> defaultPreviewSettings.slides.scriptLines`
- theme/BGM/subtitle sẽ sync:
  - `preview-settings.json`
  - `app.js -> defaultPreviewSettings`
- âm thanh từng slide sẽ sync:
  - `preview-settings.json -> slides.transitionSounds`
  - `preview-settings.json -> slides.revealSounds`
  - `app.js -> slideTransitions`
  - `app.js -> slideReveals`
  - `app.js -> defaultPreviewSettings.slides.transitionSounds/revealSounds`

Nếu sửa thủ công, đảm bảo các mảng sau có đúng N phần tử:

- `slideScripts`
- `slideTransitions`
- `slideReveals`
- `preview-settings.json.slides.scriptLines`
- `preview-settings.json.slides.transitionSounds`
- `preview-settings.json.slides.revealSounds`

Giá trị audio hợp lệ:

- transition: `gong`, `rise`, `bass`, `chime`, `sweep`, `boom`, `alarm`, `chord`, `ascending`, `retro`, `minimal`, `dramatic`
- reveal: `ping`, `pop`, `chime`, `click`, `bubble`, `woosh`, `sparkle`, `drop`, `tick`, `bell`, `blip`, `snap`

## Bước 7 — Validate bắt buộc

Trước khi bàn giao, chạy:

```bash
.venv/bin/python validate_slide.py slide/<project> --semantic-report
```

Validator kiểm:

- số dòng `script-90s.txt`
- số phần tử `slideScripts`
- số `.slide`
- số câu voiceover vs reveal units
- `highlight` / `traffic-light`
- safezone layout-box: top `>= 100px`, bottom gap `>= 200px`

Nếu FAIL, sửa `script-90s.txt`, `app.js`, `preview-settings.json`, `index.html`, hoặc `style.css`, rồi chạy lại.

Không bàn giao bằng `--skip-safezone`.

Khi báo xong cho user, ghi rõ:

- validate PASS
- mapping PASS
- safezone PASS
- semantic 1:1 đã rà theo thứ tự reveal

## Checklist bàn giao nhanh

- [ ] Source đã lưu trong `source/` và có `source/source.md`
- [ ] Script đã chốt với user
- [ ] `script-90s.txt` đúng N dòng
- [ ] `index.html` đúng N slide
- [ ] Đã lập visual plan và tham khảo `docs/visual-patterns/`
- [ ] Deck có ít nhất một visual twist/biến thể sáng tạo riêng
- [ ] Visual-first, không chép subtitle thành card dài
- [ ] `upload-metadata.json` đã cập nhật
- [ ] Preview settings/script/audio arrays đã đồng bộ
- [ ] `validate_slide.py --semantic-report` PASS
