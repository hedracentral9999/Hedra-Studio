# ELEVENLABS — TỔNG QUAN & CHỌN MODEL
# File: 01-el-overview.md
# Nguồn: https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices

---

## 1. Hai Nhóm Model Chính

```
GROUP A — Legacy (hỗ trợ SSML tags):
  → Eleven Flash v2
  → Eleven English v1
  Hỗ trợ: <break />, <phoneme> SSML tags
  KHÔNG hỗ trợ: audio tags [...]

GROUP B — Eleven v3 (mới nhất):
  Hỗ trợ: [audio tags], punctuation control
  KHÔNG hỗ trợ: SSML break tags <break />
  → Dùng audio tags + dấu câu để kiểm soát pause/pacing
```

---

## 2. Khi Nào Dùng Model Nào

```
Eleven v3:
  ✓ Creative content, podcast, audiobook
  ✓ Nhân vật với cảm xúc đa dạng
  ✓ Multi-speaker dialogue
  ✓ Cần expressive, natural delivery
  ✓ Accent switching

Eleven Flash v2:
  ✓ Low latency, production API call tốc độ cao
  ✓ Cần SSML control (<break />, <phoneme>)
  ✓ Real-time TTS (chatbot, live apps)

Eleven Multilingual v2:
  ✓ Cần đọc số/tiền tệ chính xác (không bị "one thousand thousand")
  ✓ Đa ngôn ngữ
  ✓ Khi Flash v2.5 đọc sai số phức tạp
```

---

## 3. Feature Compatibility Matrix

| Feature | Flash v2 | English v1 | v3 |
|---------|----------|------------|-----|
| SSML `<break />` | ✅ | ✅ | ❌ |
| `<phoneme>` tags | ✅ | ✅ | ❌ |
| Audio tags `[...]` | ❌ | ❌ | ✅ |
| Accent switching | ❌ | ❌ | ✅ |
| Multi-speaker | ❌ | ❌ | ✅ |
| Enhance button | ❌ | ❌ | ✅ |
| Pronunciation dict | ✅ | ✅ | ✅ |
| Alias tags | ✅ | ✅ | ✅ |

---

## 4. Files Trong Bộ Tài Liệu Này

```
01-el-overview.md        ← File này — tổng quan, chọn model
02-el-controls.md        ← Pauses, pronunciation, emotion, pace (Flash v2)
03-el-normalization.md   ← Text normalization + code Python/TS
04-el-v3-voice.md        ← Voice selection, stability settings (v3)
05-el-v3-tags.md         ← Audio tags full list + combinations (v3)
06-el-v3-advanced.md     ← Punctuation, multi-speaker, enhance, examples (v3)
07-el-troubleshooting.md ← Common issues, creative control, lab notes
```
