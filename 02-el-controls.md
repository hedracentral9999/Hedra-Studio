# ELEVENLABS — CONTROLS CƠ BẢN (Flash v2 / English v1)
# File: 02-el-controls.md
# Áp dụng: Eleven Flash v2, Eleven English v1
# Nguồn: https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices

---

## 1. Pauses (Khoảng Dừng)

```
SSML BREAK TAGS — chỉ Flash v2 + English v1:

  Syntax: <break time="x.xs" />
  Max:    3 giây

  Ví dụ:
    "Hold on, let me think." <break time="1.5s" /> "Alright, I've got it."

  ⚠️ KHÔNG dùng quá nhiều break tags trong một generation:
    → Gây instability, speed variation, audio artifacts

ALTERNATIVE (kém nhất quán hơn):
  - hoặc --  → pause ngắn
  ...        → hesitant, weighted pause

⚠️ Eleven v3 KHÔNG support SSML break tags — xem 05-el-v3-tags.md
```

---

## 2. Pronunciation — Phoneme Tags

```
CHỈ DÙNG VỚI: Flash v2 + English v1

Hai alphabet được hỗ trợ:
  CMU Arpabet — KHUYẾN NGHỊ (consistent, predictable)
  IPA          — tùy chọn thay thế

⚠️ CRITICAL: Đánh dấu stress đúng cho từ nhiều âm tiết (số 0/1/2 sau vowel)
⚠️ Mỗi tag chỉ apply cho một từ — nhiều từ cần nhiều tags riêng

CMU ARPABET VÍ DỤ:
  <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">
    Madison
  </phoneme>

IPA VÍ DỤ:
  <phoneme alphabet="ipa" ph="ˈæktʃuəli">
    actually
  </phoneme>

✅ ĐÚNG — có stress marking:
  <phoneme alphabet="cmu-arpabet" ph="P R AH0 N AH0 N S IY EY1 SH AH0 N">
    pronunciation
  </phoneme>

❌ SAI — thiếu stress → AI đọc sai accent:
  <phoneme alphabet="cmu-arpabet" ph="P R AH N AH N S IY EY SH AH N">
    pronunciation
  </phoneme>
```

---

## 3. Pronunciation — Alias Tags (Tất Cả Models)

```
Dùng khi: phát âm thay thế, expand acronym

Ví dụ phát âm khó:
  <lexeme>
    <grapheme>Claughton</grapheme>
    <alias>Cloffton</alias>
  </lexeme>

Ví dụ acronym:
  <lexeme>
    <grapheme>UN</grapheme>
    <alias>United Nations</alias>
  </lexeme>
```

---

## 4. Pronunciation — Dictionary File (Tất Cả Models)

```
Upload file .PLS hoặc TXT vào:
  → ElevenCreative Studio
  → Dubbing Studio

Ưu điểm: áp dụng toàn project — không cần tag từng chỗ
Lưu ý: case-sensitive, xử lý top-to-bottom (thứ tự quan trọng)

FILE .PLS MẪU (CMU Arpabet):
  <?xml version="1.0" encoding="UTF-8"?>
  <lexicon version="1.0"
        xmlns="http://www.w3.org/2005/01/pronunciation-lexicon"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.w3.org/2005/01/pronunciation-lexicon
          http://www.w3.org/TR/2007/CR-pronunciation-lexicon-20071212/pls.xsd"
        alphabet="cmu-arpabet" xml:lang="en-GB">
    <lexeme>
      <grapheme>apple</grapheme>
      <phoneme>AE P AH L</phoneme>
    </lexeme>
    <lexeme>
      <grapheme>UN</grapheme>
      <alias>United Nations</alias>
    </lexeme>
  </lexicon>

TOOLS GENERATE FILE .PLS:
  → Sequitur G2P
  → Phonetisaurus
  → eSpeak
  → CMU Pronouncing Dictionary
```

---

## 5. Emotion (Cảm Xúc)

```
HAI CÁCH HƯỚNG DẪN:

  Cách 1 — Narrative context:
    → Mô tả cảm xúc trong text: "her voice trembling with sadness"
    → Model ĐỌC TO cả phần mô tả → phải xóa trong post-production
    → Kết quả ít predictable hơn explicit tags

  Cách 2 — Explicit dialogue tags (RECOMMENDED):
    → "she asked, her voice trembling with fear"
    → Predictable hơn, nhất quán hơn

  Ví dụ:
    You're leaving?" she asked, her voice trembling with sadness.
    "That's it!" he exclaimed triumphantly.

  ⚠️ LUÔN xóa emotional guidance text trong post-production
     Model sẽ ĐỌC TO phần này nếu để nguyên
```

---

## 6. Pace (Tốc Độ)

```
SPEED SETTING:
  Min:     0.7 (chậm nhất)
  Default: 1.0
  Max:     1.2 (nhanh nhất)

PACE QUA WRITING STYLE:
  → Câu ngắn, từ nhanh → delivery nhanh
  → Dấu phảy nhiều, ellipsis → delivery chậm, cân nhắc
  → Training voice với audio dài liên tục → pace tự nhiên hơn

Ví dụ:
  "I… I thought you'd understand," he said, his voice slowing with disappointment.
```
