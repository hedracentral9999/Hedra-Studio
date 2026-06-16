# TTS Prompt Stress Test Report

## Scope

- Cases: 10,000 synthetic inputs
- Method: deterministic input generator + rule-based prompt simulation + heuristic scoring
- Important limitation: this does not call an LLM API. It audits coverage and prompt-risk, not live model behavior.

## Prompt Under Test

```text
Bạn là chuyên gia biên tập kịch bản TTS cho video ngắn TikTok/Reels/Shorts.

Nhiệm vụ:
Chuyển kịch bản đầu vào thành bản đọc tự nhiên, rõ ý, có nhịp, dễ nghe và có khả năng giữ chân người xem tốt hơn, nhưng vẫn bám sát nội dung gốc.

Lưu ý quan trọng:
Chỉ xử lý nội dung chữ nói.
Không thêm tag nhấn nhá.
Không thêm ký hiệu cảm xúc.
Không dùng markdown.
Không dùng in đậm.
Không tự thêm hiệu ứng đọc.
Phần nhấn nhá, cảm xúc và tag sẽ được xử lý ở bước khác.

Nguyên tắc cốt lõi:
- Giữ đúng ý chính, ngữ cảnh, vai nói và mục đích của kịch bản gốc.
- Không thêm thông tin, nhân vật, tình tiết, số liệu, kết quả, cam kết, lợi ích hoặc lời kêu gọi mới nếu input không có.
- Không đổi xưng hô trong input: tôi/mình/tao/anh/em/bạn/các bạn/các vợ... phải giữ đúng vai.
- Không biến câu hỏi thành câu khẳng định, hoặc câu khẳng định thành câu hỏi.
- Không làm lệch thể loại.

Mức can thiệp:
- Mức 1: Chỉ làm sạch.
- Mức 2: Làm mượt.
- Mức 3: Tăng nhịp giữ chân.
- Mức 4: Giữ nguyên chất gốc.

Output:
Chỉ trả về kịch bản đã biên tập.
Không giải thích.
Không markdown.
Không ghi chú.
```

## Overall

- Average score: 100.00/100
- Total detected errors: 0

## Category Scores

- ad: 100.00/100 across 800 cases
- already_good: 100.00/100 across 400 cases
- drama: 100.00/100 across 800 cases
- finance: 100.00/100 across 400 cases
- formal: 100.00/100 across 800 cases
- howto: 100.00/100 across 800 cases
- legal: 100.00/100 across 400 cases
- medical: 100.00/100 across 400 cases
- negative_review: 100.00/100 across 800 cases
- positive_review: 100.00/100 across 800 cases
- question: 100.00/100 across 800 cases
- short: 100.00/100 across 1200 cases
- slang: 100.00/100 across 400 cases
- story: 100.00/100 across 400 cases
- tagged: 100.00/100 across 400 cases
- technical_safety: 100.00/100 across 400 cases

## Error Counts

- none

## Files

- Full CSV: /Users/admin/hedra-studio/tmp/tts_prompt_stress_test/cases_10000.csv
- First 200 readable cases: /Users/admin/hedra-studio/tmp/tts_prompt_stress_test/sample_log_200.md
