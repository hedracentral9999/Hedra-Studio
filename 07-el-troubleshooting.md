# ELEVENLABS — TROUBLESHOOTING & CREATIVE CONTROL
# File: 07-el-troubleshooting.md
# Nguồn: https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices

---

## 1. Common Issues & Solutions

| Vấn đề | Nguyên nhân | Giải pháp |
|--------|-------------|-----------|
| Pause không nhất quán | Syntax sai hoặc dùng v3 | Check `<break time="x.xs" />`, dùng `...` cho v3 |
| Phát âm sai | Không có phoneme tag | Dùng CMU Arpabet với stress marking đầy đủ |
| Cảm xúc không khớp | Context không đủ rõ | Thêm narrative context + audio tags |
| Audio artifact | Quá nhiều break tags | Giảm số lượng, dùng alternative (--) |
| Số đọc sai | Model nhỏ (Flash v2.5) | Dùng Multilingual v2 hoặc LLM normalization |
| Tag không hiệu quả | Voice không phù hợp | Test voice khác, dùng Creative/Natural stability |
| PVC chất lượng thấp | v3 chưa tối ưu PVC | Dùng IVC thay thế |
| Emotional guidance bị đọc to | Quên xóa sau record | Remove guidance text trong post-production |
| Pace không đúng | Speed setting hoặc voice | Adjust speed 0.7–1.2, thử voice training dài hơn |
| Accent không hoạt động | Experimental tag, voice không support | Test voice khác, dùng Natural stability |

---

## 2. Creative Control Techniques

```
5 KỸ THUẬT KIỂM SOÁT OUTPUT:

  1. Narrative styling:
     → Viết theo scriptwriting style để hướng dẫn tone/pacing
     → "he said breathlessly, words tumbling over each other"
     → Predictable hơn pure context, nhưng nhớ xóa trong post

  2. Layered outputs:
     → Generate từng segment riêng
     → Combine trong audio editor (Audacity, Adobe Audition)
     → Kiểm soát timing chính xác hơn single generation

  3. Phonetic experimentation:
     → Thử alternate spellings cho desired sound
     → "gonna" thay "going to" cho casual tone
     → "kinda" thay "kind of"

  4. Manual adjustments:
     → Combine sound effects thủ công
     → Precise timing control — đặc biệt cho sound effects

  5. Feedback iteration:
     → Tweak tags, punctuation, emotional cues từng bước nhỏ
     → Không thay đổi nhiều variables cùng lúc — khó isolate vấn đề
     → Lưu version nào work, build từ đó
```

---

## 3. Debug Checklist

```
Khi output không đúng mong muốn:

  □ Đúng model chưa? (v3 cho audio tags, Flash v2 cho SSML)
  □ Stability setting phù hợp? (Creative/Natural cho tags)
  □ Voice có training data phù hợp không?
  □ Tag đặt đúng vị trí chưa? (trước câu vs sau câu)
  □ Text structure rõ ràng không? (câu ngắn, dấu câu đúng)
  □ Dùng PVC thay vì IVC → thử đổi sang IVC
  □ Quá nhiều break tags → reduce
  □ Có emotional guidance text chưa xóa không?
  □ Số/tiền tệ có cần normalize trước không?
```

---

## 4. Lab Notes

```
[TTS] NEVER dùng SSML break tags với Eleven v3 — không support, dùng audio tags + ellipsis
[TTS] ALWAYS đánh stress marking (0/1/2) trong CMU Arpabet — thiếu stress = phát âm sai
[TTS] ALWAYS xóa emotional guidance text sau khi record — model ĐỌC TO phần này
[TTS] ALWAYS normalize số/tiền/URL trước khi gửi Flash v2.5 — đọc sai theo quy tắc riêng
[TTS] NEVER hardcode phoneme tag vào production mà chưa test nghe — verify bằng tai trước
[TTS] NOTE: Pronunciation dictionary case-sensitive, process top-to-bottom
[TTS] NOTE: PVCs chưa tối ưu cho v3 — prefer IVC khi có thể
[TTS] NOTE: Audio tag effectiveness phụ thuộc voice training data — test từng voice riêng
[TTS] NOTE: Stability Creative/Natural → audio tags responsive; Robust → giảm responsiveness
[TTS] NOTE: Text structure (câu ngắn, dấu câu đúng) ảnh hưởng mạnh đến v3 output
[TTS] NOTE: Director's Mode đang được phát triển — sẽ có thêm control trong tương lai
```
