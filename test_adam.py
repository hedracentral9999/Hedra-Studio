import requests
import json
import os
from datetime import datetime

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB").strip()  # Adam

# --- Test script với audio tags v3 ---
TEST_TEXT = """[professional] Xin chào. Đây là bài test giọng Adam với ElevenLabs v3.

[thoughtful] Giọng này... được thiết kế để toát lên sự QUYỀN LỰC và kiên định.

[assertive] Nếu bạn đang nghe thấy điều này — thì API đã chạy THÀNH CÔNG."""


def check_credits():
    url = "https://api.elevenlabs.io/v1/user/subscription"
    headers = {"xi-api-key": API_KEY}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json()
        used = data.get("character_count", 0)
        limit = data.get("character_limit", 0)
        remaining = limit - used
        print(f"Credits: {used:,} / {limit:,} đã dùng | Còn lại: {remaining:,}")
    else:
        print(f"Không check được credits: {res.status_code}")


def generate_tts(text, model="eleven_v3", stability=0.5, similarity=0.75):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity
        }
    }

    print(f"\nGọi API... model={model}, {len(text)} ký tự")
    res = requests.post(url, headers=headers, json=payload)

    if res.status_code == 200:
        filename = f"adam_test_{datetime.now().strftime('%H%M%S')}.mp3"
        output_path = os.path.join(os.path.dirname(__file__), filename)
        with open(output_path, "wb") as f:
            f.write(res.content)
        print(f"✅ OK — Lưu tại: {output_path}")
        return output_path
    else:
        print(f"❌ Lỗi {res.status_code}: {res.text[:300]}")
        return None


if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit(
            "Thiếu ELEVENLABS_API_KEY. Hãy export key trước khi chạy test."
        )
    print("=== ElevenLabs Adam v3 Test ===\n")

    # Check credits trước
    check_credits()

    # Test 1: v3 với audio tags
    print("\n[Test 1] v3 + audio tags + emphasis")
    generate_tts(TEST_TEXT, model="eleven_v3", stability=0.5)

    # Test 2: turbo v2.5 cùng text để so sánh
    print("\n[Test 2] turbo_v2_5 để so sánh")
    generate_tts(TEST_TEXT, model="eleven_turbo_v2_5", stability=0.5)

    # Check credits sau
    print("\nCredits sau khi test:")
    check_credits()

    print("\nDone. Nghe 2 file mp3 và so sánh!")
