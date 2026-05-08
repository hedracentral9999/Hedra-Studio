# ELEVENLABS — V3 VOICE SELECTION & STABILITY
# File: 04-el-v3-voice.md
# Áp dụng: Eleven v3 only
# Nguồn: https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices

---

## 1. Voice Selection — Quan Trọng Nhất Trong v3

```
TIÊU CHÍ CHỌN VOICE:

  Emotionally diverse IVC (Instant Voice Clone):
    → Training data có nhiều tông cảm xúc: neutral, excited, sad, whispering
    → Phù hợp cho: fiction, nhân vật, expressive content
    → Voice library có 22+ excellent v3 voices

  Targeted niche (VD: sports commentary):
    → Training data nhất quán về emotion đó
    → Không cần đa dạng — cần consistent trong emotion target

  Neutral voice:
    → Stable nhất qua nhiều ngôn ngữ và style
    → Reliable baseline khi không biết chọn voice nào
    → Ít bị hallucinate hơn

⚠️ Professional Voice Clones (PVCs) chưa tối ưu cho v3
   → Clone quality thấp hơn so với models cũ
   → Prefer IVC khi có thể chọn
```

---

## 2. Tạo IVC Cho v3 — Best Practices

```
KHI RECORD VOICE CHO IVC:

  Emotionally diverse (recommended cho expressive content):
    → Ghi âm nhiều tông: neutral, excited, sad, angry, whispering
    → Đừng chỉ ghi một tông — v3 sẽ bị giới hạn theo training data

  Targeted niche:
    → Giữ emotion nhất quán xuyên suốt dataset
    → Ví dụ: sports commentary → luôn energetic, excited

  Chất lượng audio:
    → Phòng yên tĩnh, không echo
    → Micro tốt — noise ảnh hưởng nặng đến clone quality
    → Mẫu dài liên tục → pace tự nhiên hơn
```

---

## 3. Stability Settings

```
BA CHẾ ĐỘ — chọn theo use case:

  Creative  → Biểu cảm mạnh, dễ hallucinate
               Dùng cho: fiction, nhân vật, expressive creative content
               Audio tags responsive NHẤT ở mode này

  Natural   → Cân bằng, gần nhất reference audio (DEFAULT KHUYẾN NGHỊ)
               Dùng cho: podcast, narration, general purpose
               Kết hợp tốt với audio tags

  Robust    → Rất stable, ít responsive với directional prompts
               Dùng cho: production API, cần consistency tuyệt đối
               Audio tags ít hiệu quả hơn ở mode này

RULE:
  → Muốn audio tags work tốt  → Creative hoặc Natural
  → Cần output nhất quán      → Robust
  → Test stability với từng voice cụ thể — behavior khác nhau theo voice
```

---

## 4. Decision Table — Chọn Voice + Stability

| Use case | Voice type | Stability |
|----------|-----------|-----------|
| Audiobook nhân vật | Emotionally diverse IVC | Creative |
| Podcast neutral | Neutral IVC | Natural |
| Customer service | Neutral IVC | Robust |
| TTS real-time app | Neutral IVC | Robust |
| Gaming character | Emotionally diverse IVC | Creative |
| Sports commentary | Targeted niche IVC | Natural |
| Multi-language | Neutral IVC | Natural |
