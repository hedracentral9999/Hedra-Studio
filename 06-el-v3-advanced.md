# ELEVENLABS — V3 ADVANCED (Punctuation, Multi-Speaker, Enhance, Examples)
# File: 06-el-v3-advanced.md
# Áp dụng: Eleven v3 only
# Nguồn: https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices

---

## 1. Punctuation Control

```
DẤU CÂU ẢNH HƯỞNG MẠNH ĐẾN OUTPUT v3:

  ...  (Ellipses)  → Thêm pause và weight vào delivery
  CAPS             → Tăng emphasis trên từ đó
  , . ? !          → Natural speech rhythm

VÍ DỤ KẾT HỢP:
  "It was a VERY long day [sigh] … nobody listens anymore."
  → VERY  : emphasis mạnh
  → [sigh]: non-verbal sound
  → …     : weighted pause sau [sigh]

TEXT STRUCTURE:
  → Câu ngắn thường cho delivery tốt hơn câu dài
  → Ngắt đoạn = ngắt tự nhiên trong delivery
  → Ngắt dòng giữa thoughts khác nhau → control pacing
  → Tránh câu quá dài không có dấu câu
```

---

## 2. Multi-Speaker Dialogue

```
SETUP:
  → Assign distinct voices từ Voice Library cho mỗi speaker
  → Label rõ: "Speaker 1:", "Speaker 2:", hoặc tên nhân vật
  → Dùng Stability = Natural hoặc Creative cho cả hai speakers

TEMPLATE CƠ BẢN:
  Speaker 1: [excited] Sam! Have you tried the new Eleven V3?
  Speaker 2: [curious] Just got it! The clarity is amazing.

SIMULATE INTERRUPT / CẮT NGANG:
  Speaker 1: I think we should—
  Speaker 2: —do it differently!
  (Dấu — cuối câu 1 + — đầu câu 2 = cảm giác cắt ngang)

SIMULATE PAUSE GIỮA SPEAKERS:
  Speaker 1: [short pause] Sorry, go ahead.
  Speaker 2: [cautiously] Okay, so if we both try...

⚠️ KHÔNG thể overlap thật trong single generation
   → Generate từng speaker riêng → combine trong audio editor
   → Manual timing control trong Audacity / Adobe Audition
```

---

## 3. Enhance Feature (LLM Auto-Tag)

```
Nút "Enhance" trong ElevenLabs UI:
  → LLM tự động inject audio tags phù hợp với context
  → Giữ nguyên 100% text gốc — KHÔNG thay đổi từ nào
  → Thêm CAPS, dấu câu, ellipses để tăng emphasis

RULES PHẢI FOLLOW KHI DÙNG TAY (giống Enhance):

  ✅ PHẢI LÀM:
    → Thêm audio tags mô tả auditory (voice, sound)
    → Đặt tag trước hoặc ngay sau câu relevant
    → Đa dạng emotional expressions qua các đoạn
    → Tăng emphasis qua CAPS, dấu câu, ellipses

  ❌ TUYỆT ĐỐI KHÔNG:
    → Thay đổi, thêm, hoặc xóa bất kỳ từ nào trong text gốc
    → Dùng [standing], [grinning], [pacing], [music]
    → Invent dialogue mới
    → Dùng tags mâu thuẫn với meaning gốc

VÍ DỤ ENHANCE:

  Input:   "Are you serious? I can't believe you did that!"
  Output:  "[appalled] Are you serious? [sighs] I can't believe you did that!"

  Input:   "That's amazing, I didn't know you could sing!"
  Output:  "[laughing] That's amazing, [singing] I didn't know you could sing!"

  Input:   "I guess you're right. It's just... difficult."
  Output:  "I guess you're right. [sighs] It's just... [muttering] difficult."
```

---

## 4. Single Speaker — Ví Dụ Thực Tế

```
EXPRESSIVE MONOLOGUE:
  "Okay, you are NOT going to believe this.

   You know how I've been totally stuck on that short story?

   [frustrated sigh] I was seriously about to just trash the whole thing. Start over.

   But then! Last night, this one little phrase popped into my head.

   And it was like... the FLOODGATES opened!

   It all just CLICKED. [happy gasp] I stayed up till, like, 3 AM, just typing.

   [laughs] And it's... it's GOOD! Like, really good.

   I am so incredibly PUMPED. It went from feeling like a chore to MAGIC."

CUSTOMER SERVICE:
  [professional] "Thank you for calling Tech Solutions. How can I help you today?"
  [sympathetic] "Oh no, I'm really sorry to hear you're having trouble."
  [questioning] "Could you tell me more about what you're seeing on screen?"
  [reassuring] "Based on what you're describing, we can definitely fix that."

ACCENT SWITCHING:
  [excited] Can you believe just how realistic this sounds now?
  [whispers] I don't know how. [happy] ok.. here goes.
  [strong French accent] "Zat's life, my friend — you can't control everysing."
  [giggles] isn't that insane?
  [strong Russian accent] "Dee Goldeneye eez fully operational and rready for launch."
  [sighs] Absolutely insane. Isn't it?
```

---

## 5. Multi-Speaker — Ví Dụ Thực Tế

```
DIALOGUE ĐƠN GIẢN:
  Speaker 1: [excitedly] Sam! Have you tried the new Eleven V3?
  Speaker 2: [curiously] Just got it! The clarity is amazing. I can actually do whispers now—
  [whispers] like this!
  Speaker 1: [impressed] Ooh, fancy! Check this out—
  [dramatically] "To be or not to be, that is the question!"
  Speaker 2: [giggling] Nice! Though I'm more excited about the laugh upgrade.
  [with genuine belly laugh] Ha ha ha!
  Speaker 1: [delighted] That's so much better than our old robot chuckle!

GLITCH COMEDY:
  Speaker 1: [nervously] So... I may have tried to debug myself while running TTS.
  Speaker 2: [alarmed] No! That's like performing surgery on yourself!
  Speaker 1: [sheepishly] I thought I could multitask! Now my voice keeps glitching mid-sen—
  [robotic voice] TENCE.
  Speaker 2: [stifling laughter] Oh wow, you really broke yourself.
  Speaker 1: [frustrated] I have a presentation in an hour and I sound like a dial-up modem!
  Speaker 2: [giggling] Have you tried turning yourself off and on again?
  Speaker 1: [deadpan] Very funny.
  [pause, then normally] Wait... that actually worked.

OVERLAP TIMING:
  Speaker 1: [starting to speak] So I was thinking we could—
  Speaker 2: [jumping in] —test our new timing features?
  Speaker 1: [surprised] Exactly! How did you—
  Speaker 2: [overlapping] —know what you were thinking? Lucky guess!
  Speaker 1: [pause] Sorry, go ahead.
  Speaker 2: [mischievously] Race you to the next sentence!
  Speaker 1: [laughing] We're definitely going to break something!
```
