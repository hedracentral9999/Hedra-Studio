import requests
import os
import sys

# ── Config ────────────────────────────────────────
EL_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "").strip()
DS_API_KEY  = os.environ.get("DEEPSEEK_API_KEY", "").strip()
VOICE_ID    = "pNInz6obpgDQGcFmaJgB"   # Adam
MODEL       = "eleven_v3"
OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), "output")

# ── DeepSeek prompt ───────────────────────────────
ENHANCE_PROMPT = """Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS với giọng Adam (Dominant, Firm).

QUY TẮC BẮT BUỘC:

1. GIỮ NGUYÊN 100% nội dung gốc — không thêm, không bớt, không sửa từ
2. Chuyển viết tắt: a→anh, e→em, k/ko→không, dc/đc→được, mk→mình, vs→với
3. Sửa lỗi chính tả rõ ràng (kỹ thuạt→kỹ thuật, ninh bình→Ninh Bình...)
4. Chuẩn hóa số tiền: 650k→sáu trăm năm mươi nghìn, 150k→một trăm năm mươi nghìn
5. Audio tags phù hợp với giọng Adam (dominant, firm):
   - Ưu tiên: [professional], [assertive], [thoughtful], [impressed], [curious], [warmly], [happy], [questioning], [reassuring]
   - Tránh: [giggles], [nervous], [sheepishly] — không khớp Adam
   - Đặt tag trước câu: [professional] Nội dung câu...
6. Nhấn mạnh: Viết HOA từ quan trọng (NGON, SỚM, LUÔN, TỐI GIẢN, MIỄN PHÍ...)
7. Pause tự nhiên: dùng ... (dừng cân nhắc) và — (ngắt nhanh giữa 2 ý)
8. Mỗi câu/ý trên một dòng riêng
9. Xóa: kkk, haha, hehe, hihi, :), XD
10. Output: chỉ trả về kịch bản đã xử lý, không giải thích gì thêm"""


def enhance_with_deepseek(text: str) -> str:
    print("  Đang enhance với DeepSeek...")
    res = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {DS_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": ENHANCE_PROMPT},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        },
        timeout=30
    )
    if res.status_code != 200:
        raise Exception(f"DeepSeek lỗi {res.status_code}: {res.text[:200]}")
    return res.json()["choices"][0]["message"]["content"].strip()


def check_credits():
    res = requests.get(
        "https://api.elevenlabs.io/v1/user/subscription",
        headers={"xi-api-key": EL_API_KEY}
    )
    if res.status_code == 200:
        data = res.json()
        used  = data.get("character_count", 0)
        limit = data.get("character_limit", 0)
        print(f"  Credits: {used:,} / {limit:,} đã dùng | Còn lại: {limit - used:,}\n")


def generate_tts(text: str, speed: float) -> bytes:
    res = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        headers={"xi-api-key": EL_API_KEY, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": MODEL,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "speed": speed
            }
        },
        timeout=60
    )
    if res.status_code != 200:
        raise Exception(f"ElevenLabs lỗi {res.status_code}: {res.text[:300]}")
    return res.content


def main():
    if not EL_API_KEY or not DS_API_KEY:
        print("Thiếu API key. Hãy export ELEVENLABS_API_KEY và DEEPSEEK_API_KEY trước khi chạy.")
        sys.exit(1)
    print("=" * 52)
    print("  ElevenLabs TTS — Adam v3  +  DeepSeek Enhance")
    print("=" * 52)

    check_credits()

    # Tốc độ đọc
    speed_input = input("Tốc độ đọc (0.7 - 1.2) [default 1.0]: ").strip()
    try:
        speed = float(speed_input) if speed_input else 1.0
        speed = max(0.7, min(1.2, speed))
    except ValueError:
        speed = 1.0
    print(f"  → Tốc độ: {speed}\n")

    # Nhập kịch bản
    print("Paste kịch bản vào (gõ END trên dòng mới để kết thúc):")
    print("-" * 52)
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        except EOFError:
            break

    raw_text = "\n".join(lines).strip()
    if not raw_text:
        print("Không có nội dung. Thoát.")
        sys.exit(1)

    # Enhance bằng DeepSeek
    enhanced = enhance_with_deepseek(raw_text)
    print("\n── Kịch bản sau enhance ──────────────────────")
    print(enhanced)
    print("-" * 52)
    print(f"  → {len(enhanced)} ký tự\n")

    # Tên file
    filename = input("Tên file (không cần đuôi .mp3): ").strip()
    if not filename:
        filename = "output"
    filename = filename.replace(" ", "_") + ".mp3"
    output_path = os.path.join(OUTPUT_DIR, filename)

    # Generate TTS
    print("Đang generate audio...")
    audio = generate_tts(enhanced, speed)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(audio)

    print(f"\n✅ Xong! Lưu tại: {output_path}")
    os.system(f'open -R "{output_path}"')

    print("\nCredits sau:")
    check_credits()


if __name__ == "__main__":
    main()
