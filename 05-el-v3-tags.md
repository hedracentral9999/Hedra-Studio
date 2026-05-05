# ELEVENLABS — V3 AUDIO TAGS (Full Reference)
# File: 05-el-v3-tags.md
# Áp dụng: Eleven v3 only
# Nguồn: https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices

---

## 1. Cách Đặt Tag

```
SYNTAX: [tag-name] — dấu ngoặc vuông, viết thường

VỊ TRÍ:
  Trước câu  : [whispers] I never knew it could be this way.
  Sau câu    : This is hard. [sighs]
  Kết hợp   : [excited] [laughs] That's amazing!
  Giữa câu  : "I can't believe [sighs] … this is happening."

⚠️ Effectiveness phụ thuộc voice và training data — test kỹ trước production
⚠️ Một số tags ít nhất quán hơn với một số voices — thử nhiều voices
```

---

## 2. Voice-Related Tags — Cảm Xúc & Giọng Điệu

```
CẢM XÚC TÍCH CỰC:
  [happy]       [excited]     [delighted]    [impressed]
  [warmly]      [mischievously]

CẢM XÚC TIÊU CỰC:
  [sad]         [crying]      [angry]        [annoyed]
  [appalled]    [frustrated]  [desperately]

CẢM XÚC TRUNG TÍNH / PHỨC TẠP:
  [curious]     [thoughtful]  [surprised]    [nervous]
  [sheepishly]  [deadpan]     [sarcastic]    [dismissive]

GIỌNG CHUYÊN NGHIỆP:
  [professional] [sympathetic] [reassuring]  [questioning]
```

---

## 3. Non-Verbal Sound Tags

```
CƯỜI:
  [laughs]              [laughs harder]       [starts laughing]
  [laughing hysterically] [chuckles]          [giggles]

HƠI THỞ:
  [sighs]               [exhales]             [exhales sharply]
  [inhales deeply]      [wheezing]

KHÁC:
  [whispers]
  [snorts]
  [clears throat]
  [short pause]         [long pause]
  [happy gasp]
  [swallows]            [gulps]
  [muttering]
```

---

## 4. Sound Effect Tags

```
[gunshot]    [explosion]
[applause]   [clapping]
```

---

## 5. Experimental Tags (Test Kỹ Trước Production)

```
ACCENT SWITCHING:
  [strong X accent] — thay X bằng tên accent
  
  Ví dụ:
    [strong French accent] "Zat's life, my friend — you can't control everysing."
    [strong Russian accent] "Dee Goldeneye eez fully operational and rready for launch."

KHÁC:
  [sings]   → voice chuyển sang hát
  [woo]     → exclamation sound
  [fart]    → sound effect

⚠️ Experimental tags ít nhất quán hơn — không dùng production mà chưa test
```

---

## 6. Tag Combinations — Kết Hợp Phức Tạp

```
VUI VẺ + NGẠC NHIÊN:
  [laughs harder] [giggles] "I can't believe this!"

LO LẮNG + BÍ MẬT:
  [nervous] [whispers] "I don't think they know we're here."

MỈA MAI + KHÓ CHỊU:
  [sarcastic] [annoyed] "Sure, that's DEFINITELY going to work."

PHẤN KHÍCH NHIỀU LAYERS:
  [excited] I mean OH MY GOD... [laughing hysterically] it's so good!

BẤT NGỜ → TIẾC:
  [surprised] "Oh wow, that's... [sighs] actually kind of sad."

TỰ TIN → NHỎ GIỌNG:
  [professional] "We've analyzed the data." [whispers] "And it's not good."

ACCENT + CẢM XÚC:
  [excited] Check this out!
  [strong French accent] "Zat's life, my friend."
  [giggles] isn't that insane?
```

---

## 7. Tags Không Được Dùng

```
❌ [standing]  — không phải auditory
❌ [grinning]  — không phải auditory
❌ [pacing]    — không phải auditory
❌ [music]     — sound effect toàn bộ, không phải voice
❌ Bất kỳ tag nào describe hành động vật lý, không phải âm thanh
```

---

## 8. Tips Chọn Tag Phù Hợp

```
→ Match tags với character của voice:
  Voice serious, professional → tránh [giggles], [mischievously]
  Voice playful, young        → tránh [professional], [deadpan]

→ Text structure ảnh hưởng nhiều đến tag effectiveness:
  Dùng natural speech patterns, proper punctuation để tăng hiệu quả

→ Không dừng ở list có sẵn:
  Thử bất kỳ mô tả auditory nào: [frustrated sigh], [nervous laugh]...
  v3 có thể hiểu nhiều hơn list được document
```
