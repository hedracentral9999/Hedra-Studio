# Prompt tối ưu kịch bản cho ElevenLabs v3 TTS

Dùng prompt này khi bạn muốn tôi (hoặc bất kỳ AI nào) xử lý kịch bản hội thoại thành định dạng chuẩn của ElevenLabs v3, với audio tags, nhấn mạnh, pause tự nhiên và giữ nguyên nội dung gốc.

---

## Cách dùng

1. Copy toàn bộ phần `QUY TẮC` + `KỊCH BẢN GỐC` bên dưới
2. Thay dòng `[Paste nội dung kịch bản của bạn vào đây]` bằng kịch bản thật
3. Gửi cho AI (ChatGPT, Claude, Gemini...)

---

## Nội dung prompt (bản đầy đủ)

```text
Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS. Hãy xử lý kịch bản tôi gửi theo các quy tắc sau:

## QUY TẮC BẮT BUỘC:

1. **Model**: Eleven v3
2. **Chuyển đổi từ viết tắt**:
   - a → anh
   - e → em
   - u → bạn (nếu có)
3. **Audio tags** (dùng `[tag]` đặt trước câu hoặc sau dấu câu):
   - Cảm xúc: `[happy]`, `[excited]`, `[surprised]`, `[curious]`, `[reassuring]`, `[professional]`, `[delighted]`, `[enthusiastic]`, `[questioning]`, `[thoughtful]`, `[impressed]`, `[nervous]`, `[sympathetic]`, `[eager]`, `[eagerly]`
   - Phi âm thanh: `[laughs]`, `[chuckles]`, `[giggles]`, `[starts laughing]`, `[sighs]`, `[short pause]`, `[whispers]`, `[sheepishly]`
4. **Nhấn mạnh**: Viết HOA các từ quan trọng (VD: CHỤC, SẴN, NGON, TUYỆT)
5. **Pause**: Dùng `...` (chậm, cân nhắc) và `—` (ngắt nhanh)
6. **Xuống dòng**: Mỗi câu/ý một dòng riêng
7. **GIỮ NGUYÊN 100% nội dung gốc** (chỉ thêm tag, viết hoa, dấu câu, không thêm/bớt/sửa từ)
8. **Output**: Đặt trong codeblock ```text để dễ copy

## KỊCH BẢN GỐC:

[Paste nội dung kịch bản của bạn vào đây]

## YÊU CẦU BỔ SUNG (nếu có):
- [ ] Thêm accent switching (ghi rõ accent nào)
- [ ] Multi-speaker (ghi rõ tên nhân vật)
- [ ] Dùng stability Creative thay vì Natural
- [ ] Khác: ...