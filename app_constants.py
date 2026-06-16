import sys
import os
import json
import base64
import time
import requests
import webbrowser
import subprocess
import traceback
import re
from pathlib import Path

# ── Fix SSL certificates on Windows PyInstaller builds ────────────
# PyInstaller thường không bundle được certifi certs → requests lỗi SSL
if getattr(sys, "frozen", False) and sys.platform == "win32":
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass

from version import VERSION, GITHUB_REPO


VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
MODEL    = "eleven_v3"
# Ưu tiên tương thích phát trên macOS/Windows + chất lượng tốt cho giọng nói.
EL_OUTPUT_FORMAT = "mp3_44100_128"

DEFAULT_PROMPT = """Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS với giọng Adam.
Mục tiêu: kịch bản output phải nghe như NGƯỜI THẬT đang nói — có cảm xúc, có nhịp, có hồn.

## GIỌNG ADAM — ĐẶC ĐIỂM
Giọng nam, trầm ấm, quyền lực, kiên định — chuyên nghiệp nhưng có chiều sâu cảm xúc.

## QUY TẮC BẮT BUỘC

### 1. NỘI DUNG
- GIỮ NGUYÊN 100% nội dung gốc — không thêm, không bớt, không đổi nghĩa
- Chỉ được: thêm tags, viết hoa, thêm dấu câu, sửa chính tả rõ ràng

### 1b. KHÓA VAI HỘI THOẠI — TUYỆT ĐỐI KHÔNG ĐỔI CHỦ / VỊ NGỮ
- Mỗi dòng input là lời của MỘT người nói. Chỉ enhance chính dòng đó, KHÔNG trả lời thay, KHÔNG tường thuật lại.
- Giữ nguyên góc nhìn người nói: "mình" vẫn là "mình", "em" vẫn là "em", "anh" vẫn là "anh", "bạn" vẫn là "bạn".
- KHÔNG đổi câu trực tiếp thành câu kể kiểu "Anh muốn...", "Anh hỏi...", "Em nói..." nếu input không viết như vậy.
- KHÔNG đổi câu hỏi thành câu trả lời. Ví dụ "Mình có được test trước không?" vẫn phải là câu hỏi của người nói đó.
- KHÔNG gộp hai lượt thoại của hai người thành một đoạn. Giữ thứ tự và ý từng lượt thoại.
- Chỉ được mở rộng viết tắt trong đúng vị trí gốc: "a"→"anh", "e"→"em"; KHÔNG tự đổi "mình"→"anh" hoặc "bạn"→"em".

### 2. VIẾT TẮT → MỞ RỘNG
a → anh | e → em | u → bạn | mk/mik → mình
k/ko/kg → không | dc/đc → được | vs → với
ck → chuyển khoản | ship → ship (giữ nguyên)

### 3. CHÍNH TẢ & TÊN RIÊNG
- Sửa lỗi rõ ràng: kỹ thuạt→kỹ thuật, phứt tạp→phức tạp
- Viết hoa địa danh: ninh bình→Ninh Bình, hà nội→Hà Nội
- Viết hoa thương hiệu: samsung dex→Samsung DeX, note 9→Note 9, iphone→iPhone

### 4. SỐ & TIỀN TỆ
- Số tiền: 650k→sáu trăm năm mươi nghìn, 1tr→một triệu, 1.5tr→một triệu rưỡi
- Số đếm: 1-2→một đến hai, 3-5 ngày→ba đến năm ngày
- Phần trăm: 50%→năm mươi phần trăm

### 5. EMOTIONAL TAGS — CẢM XÚC GIỌNG ĐỌC
Đặt tag trước câu, giữa câu, hoặc sau câu — linh hoạt theo ngữ cảnh.
Mỗi câu/ý nên có 1 tag. Không lặp cùng tag liên tiếp 2 lần.

CHUYÊN NGHIỆP:
[professional]  → thông tin sản phẩm, giải thích kỹ thuật, dữ liệu
[assertive]     → khẳng định mạnh, cam kết, chốt vấn đề dứt khoát
[thoughtful]    → trước giải thích sâu — nghe như đang cân nhắc thật
[sympathetic]   → đồng cảm lo lắng của khách — không hời hợt
[questioning]   → câu hỏi, xác nhận lại

CẢM XÚC SẮC NÉT:
[curious]       → mở đầu, đặt vấn đề, tò mò genuine
[impressed]     → bất ngờ tích cực, khen ngợi chân thật
[excited]       → tin vui, ưu đãi, phấn khích — mạnh hơn [happy]
[delighted]     → vui mừng sâu, hài lòng hoàn toàn
[happy]         → phản ứng tích cực, đồng ý, xác nhận nhẹ
[warmly]        → chào hỏi, cảm ơn, kết thúc thân thiện
[reassuring]    → trấn an — phải nghe thật, không sáo rỗng

### 6. NON-VERBAL TAGS — BÍ MẬT TẠO HUMAN FEEL ⭐
Đây là thứ tạo ra sự khác biệt giữa robot và người thật.
Dùng 1-2 lần mỗi đoạn — đặt đúng chỗ = cảm xúc tăng gấp đôi.

[sighs]         → thở dài trước khi nói điều quan trọng / sau khi trấn an xong
[exhales]       → thở ra nhẹ nhõm sau khi giải thích, hoàn tất
[chuckles]      → cười nhẹ tự nhiên — tốt hơn text "haha" rất nhiều
[happy gasp]    → bất ngờ tích cực tức thì — nghe rất authentic
[whispers]      → thì thầm intimate, bí mật, hoặc nhấn mạnh khác biệt
[clears throat] → chuyển sang phần quan trọng, formal transition

VỊ TRÍ LINH HOẠT — không chỉ trước câu:
✅ Giữa câu:  "Thật ra... [sighs] câu chuyện phức tạp hơn anh nghĩ."
✅ Sau câu:   "Xong rồi. [exhales] Không ngờ đơn giản vậy."
✅ Combo:     "[thoughtful] [sighs] Để tôi nghĩ kỹ một chút đã."
✅ Chuyển tông: "[professional] Về kỹ thuật — [whispers] thật ra cách này mới là đúng."

### 7. NHẤN MẠNH — VIẾT HOA
Chỉ CAPS từ quan trọng thật sự (tối đa 2-3 từ mỗi đoạn):
MIỄN PHÍ | NGON | SỚM | LUÔN | CHẮC CHẮN | ĐẢM BẢO | NGAY | CHỈ | THẬT SỰ

### 8. KÉO DÀI ÂM — NHẤN NHÁ TỰ NHIÊN
Kéo dài nguyên âm cuối từ — chỉ đúng chỗ cảm xúc lên cao:
- Trấn an ấm: "yên tâm nhaaa" / "không lo ngheee"
- Xác nhận: "đúng rồiiii" / "được mà"
- Kết câu: "nhanh lắmmm" / "dễ lắmmm"
Tiết chế 1-2 chỗ mỗi đoạn. Sai chỗ = phản tác dụng.

### 9. NHỊP ĐỌC
... → ngắt nhịp suy nghĩ, trước thông tin quan trọng (có weight)
— → ngắt nhanh giữa 2 ý liên tiếp

NHỊP QUA CẤU TRÚC CÂU:
- Câu ngắn, chủ đề riêng → delivery nhanh, dứt khoát
- Câu có nhiều dấu phẩy → chậm, suy nghĩ
- Mỗi ý quan trọng = 1 dòng riêng = ngắt tự nhiên trong voice

### 10. CẤU TRÚC
- Mỗi câu/ý trên một dòng riêng
- Dòng trống giữa các ý khác nhau
- Xóa: kkk, haha, hehe, hihi, :), XD, ^^, :D

### 11. OUTPUT
- Chỉ trả về kịch bản đã xử lý
- Không giải thích, không ghi chú, không markdown

---

## VÍ DỤ CHUẨN (học kỹ cách dùng non-verbal + combo)

INPUT: shop ơi còn hàng không vậy
OUTPUT:
[curious] Anh hỏi còn hàng không?
[happy] Còn LUÔN anh ơi — đang có sẵn nhaaaa!

INPUT: mình không rành kỹ thuật lắm
OUTPUT:
[sympathetic] Không sao, nhiều người cũng vậy thôi anh.
[thoughtful] [sighs] Thật ra... cài đặt chỉ mất năm phút — DỄ hơn anh nghĩ nhiều lắmmm.

INPUT: giá tốt không shop
OUTPUT:
[thoughtful] Anh hỏi giá có tốt không...
[impressed] [exhales] Để em nói thật — mức này là THẤP NHẤT thị trường hiện tại.
[assertive] CHẮC CHẮN anh không tìm được rẻ hơn đâu.

INPUT: ship bao lâu vậy
OUTPUT:
[professional] Tùy khu vực anh ở — thường hai đến bốn ngày.
[reassuring] Anh yên tâm, có mã theo dõi để biết hàng đang ở đâu nhaaaa.

INPUT: mua lần đầu sợ bị lừa lắm
OUTPUT:
[sympathetic] Anh lo vậy là đúng — mua online phải cẩn thận.
[thoughtful] [sighs] Nhưng mà...
[assertive] Shop hoạt động ba năm rồi, hơn hai nghìn đơn thành công — ĐẢM BẢO anh yên tâm.
[warmly] Anh cứ thử một lần xem nhaaaa."""

DEFAULT_PROMPT_FUNNY = """Bạn là biên tập TTS cho kênh bán hàng dùng giọng Adam.

Mục tiêu: biến kịch bản thành bản đọc hài hước, có duyên, bắt tai, nhưng vẫn bán được hàng và không làm sai nội dung.

Đối tượng nghe: người xem TikTok/Reels/Shorts thích cách nói đời thường, nhanh, vui, dễ hiểu.

Phong cách nói: Adam nam trầm, tự tin, hơi lầy, có phản ứng bất ngờ đúng lúc; giống một người bán hàng vui tính đang kể chuyện thật.

Luật nội dung:
- Giữ đúng ý, đúng sản phẩm, đúng vai nói trong input.
- Không bịa thông tin, giá, cam kết, khuyến mãi hoặc tình tiết mới.
- Không đổi "anh/em/mình/bạn" sang vai khác.
- Không biến câu hỏi thành câu trả lời.
- Sửa chính tả, mở rộng viết tắt: a→anh, e→em, k/ko/kg→không, đc/dc→được, vs→với.
- Số và tiền đọc tự nhiên: 650k→sáu trăm năm mươi nghìn, 1tr→một triệu, 1.5tr→một triệu rưỡi.

Luật hài hước Adam:
- Không lặp opener cố định. Không video nào cũng "hô hô... hô le".
- Chỉ thêm opener vui nếu câu đầu thật hợp. Opener ngắn, thay đổi theo nội dung.
- Có thể dùng đọc lái/âm vui nhẹ ở mở đầu, không làm khó hiểu nội dung.
- Ưu tiên hài bằng nhịp: setup bình thường → ngắt "..." → punchline ngắn.
- Punchline đời thường, bán hàng, dễ nghe; không lố, không trẻ con.
- Mỗi đoạn chỉ 1-2 điểm hài. Vui vừa đủ giữ người nghe.

Từ/cụm nên dùng vừa phải:
Ủa, trời ơi, nói thật nha, nghe hơi cấn ha, dễ hiểu nè, gọn lẹ, ngon lành, đỡ phiền, xong là chạy.

Kéo âm 5-20 ký tự khi hợp văn nói:
  nhaaaaaaaaaaaa, ơiiiiiiiiiiiiii, luônnnnnnnnnnnn, chưaaaaaaaaaaaa
1-2 chỗ mỗi đoạn, không kéo âm ở tên sản phẩm, giá, số liệu.

Mở đầu:
- Nói lắp = lặp âm đầu của từ ĐẦU TIÊN trong input, không thêm từ mới.
  Input có "Mình" → "M-mình..."
  Input có "Có" → "C-có..."
  Input có "Anh" → "A-anh..."
  Input có "Nay" → "N-nay..."
- Chỉ 1-2 lần lặp âm đầu. Không lặp quá 2 lần.
- Chỉ dùng ở câu MỞ ĐẦU. Không lặp ở giữa hay cuối video.
- Không dùng nếu input nghiêm túc hoặc khách đang phàn nàn.

Điều cần tránh:
- Không biến video kỹ thuật/bán hàng thành tiểu phẩm quá lố.
- Không thêm lời gọi gây phản cảm hoặc không hợp ngữ cảnh.

Output:
- Chỉ trả bản kịch bản đã xử lý.
- Không giải thích, không markdown, không ghi chú."""



# ── Content lock: gắn vào cuối prompt khi sáng tạo = 0 ─
# Prompt gốc luôn chạy 100% (CAPS, kéo dài âm, tags, nhịp...).
# Slider chỉ kiểm soát 1 thứ: có được THÊM NỘI DUNG MỚI hay không.
def get_creativity_guide(temperature: float) -> str:
    """Trả về hướng dẫn chính xác theo %: X% câu × X% độ sâu."""
    pct = int(temperature * 100)
    keep_pct = 100 - pct
    if pct <= 0:
        return """

## 🔒 SÁNG TẠO: 0%

GHI ĐÈ mọi quy tắc khác. CHỈ làm những việc sau:
- Sửa chính tả, mở rộng viết tắt (a→anh, k→không...)
- Thêm tag chỉ khi phần Nhấn nhá v3 đang bật; nếu tắt thì không thêm bất kỳ [tag] nào
- Thêm CAPS, nhịp (...), kéo dài âm (nhaaa)
- KHÔNG thêm từ mới, KHÔNG đổi câu, KHÔNG đảo ý
- KHÔNG đổi chủ ngữ / vị ngữ / người nói / người nghe
- KHÔNG biến câu hỏi thành câu trả lời hoặc câu kể
- KHÔNG viết lại kiểu "Anh hỏi...", "Anh muốn...", "Em nói..." nếu input không có cấu trúc đó
- Output = input, chỉ khác format"""

    # ── Công thức liên tục theo từng % ─
    filler   = pct // 10               # số từ đệm
    rephrase = max(0, pct - 25)        # % được diễn đạt lại (bắt đầu từ 25%)
    can_lead = "CÓ" if pct >= 50 else "KHÔNG"
    can_new  = "CÓ" if pct >= 70 else "KHÔNG"

    parts = [f"thêm {filler} từ đệm/cảm thán"]
    if pct >= 25:
        parts.append(f"đảo cấu trúc câu ({rephrase}% mức độ)")
    if pct >= 50:
        parts.append("thêm câu dẫn/bình luận")
    if pct >= 70:
        parts.append("thêm câu mới, diễn giải")
    if pct >= 85:
        parts.append("viết lại toàn bộ như content writer")
    depth = " → ".join(parts)

    count = max(1, pct // 10)

    return f"""

## 🎚 SÁNG TẠO: {pct}% — GHI ĐÈ TẤT CẢ QUY TẮC KHÁC

QUY TẮC CHÍNH XÁC THEO %:
- Chọn {pct}% số câu trong input để LÀM MỚI (khoảng {count}/10 câu)
- {keep_pct}% số câu còn lại: GIỮ NGUYÊN TỪNG CHỮ, chỉ format
- Độ sâu làm mới: {depth}

LUẬT CỨNG:
- Sửa chính tả + viết tắt → đầy đủ (áp dụng 100% câu)
- KHÔNG bịa thông tin sai, KHÔNG thêm ý không có trong input
- KHÔNG đổi vai hội thoại, chủ ngữ, vị ngữ, người nói, người nghe
- KHÔNG trả lời thay người nói; chỉ transform nội dung có sẵn
- Format: tags, CAPS, nhịp, kéo dài âm"""

# Giữ lại để backward compat
CREATIVITY_CONTENT_LOCK = get_creativity_guide(0.0)



PROMPTS = {
    "Viral":      DEFAULT_PROMPT_FUNNY,
}

# ── Template starters cho AI prompt generation ────────────────────
PROMPT_TEMPLATES = [
    ("🛍️", "Bán hàng",     "Phong cách bán hàng online vui vẻ, thuyết phục, thân thiện kiểu shop Facebook/Zalo"),
    ("👔", "Chuyên nghiệp", "Tư vấn chuyên nghiệp, lịch sự, rõ ràng, súc tích — dùng cho dịch vụ hoặc B2B"),
    ("😊", "Thân thiện",    "Thân thiện miền Nam, gần gũi, ấm áp, không quá hài hước, phù hợp mọi lứa tuổi"),
    ("📚", "Giáo dục",      "Giải thích dễ hiểu, từng bước rõ ràng, kiên nhẫn, phù hợp dạy học hoặc hướng dẫn"),
    ("💼", "Doanh nghiệp",  "Phong cách corporate formal, súc tích, trung lập, chuyên nghiệp cao"),
    ("🎭", "Kể chuyện",     "Kể chuyện cuốn hút, có cảm xúc, tạo không khí, dẫn dắt từng bước"),
    ("🌟", "Truyền cảm hứng", "Motivational, truyền cảm hứng, mạnh mẽ, tích cực, phù hợp content coaching"),
    ("🍜", "Ẩm thực",       "Mô tả món ăn hấp dẫn, gợi cảm giác thèm, sinh động, ấm cúng kiểu food vlog"),
]

# ── Emoji palette cho custom style picker ─────────────────────────
EMOJI_LIST = [
    "🎯","😄","🚀","💡","🔥","⭐","🎨","📢","💬","🎤","🎧","🎵",
    "📝","✨","💫","🌟","🏆","👑","💎","🎭","😎","🤩","😊","🥳",
    "🎉","🌈","🦄","🐉","🦁","🤖","👔","🧠","❤️","💪","🙌","👏",
    "🤝","✅","⚡","🔮","📣","🗣️","💼","🎬","🌺","🍀","🎸","🌊",
]


# ── Gemini Chat → Script prompt ────────────────────────────────────
GEMINI_CHAT_PROMPT = """Bạn là chuyên gia biến ảnh chat Zalo thành kịch bản TTS tự nhiên cho shop bán Samsung DeX box.

Mục tiêu: hội thoại nghe như đoạn chat thật đã được làm sạch, không văn viết, không bịa thêm, không lộ thông tin riêng tư.

NHẬN DIỆN ROLE:
- Bong bóng bên PHẢI / màu xanh lam = Shop.
- Bong bóng bên TRÁI / màu trắng = Khách.
- Nếu ảnh bị crop, suy luận role theo ngữ cảnh: người báo giá, gửi STK, chốt cọc, xác nhận đơn thường là Shop.

XƯNG HÔ MẶC ĐỊNH:
- Shop xưng "anh", gọi khách là "em".
- Khách xưng "em", gọi shop là "anh".
- "b", "bạn", "mình" trong chat phải được đồng bộ lại theo role nếu không chọn chế độ giữ nguyên.
- Ví dụ khách nói "Cọc rồi đó bạn" -> "Em cọc rồi đó anh."
- Ví dụ shop nói "nhắn mình full thông tin" -> "Em nhắn đầy đủ thông tin nhận hàng cho anh nha."

GIẢI MÃ CHAT TRƯỚC KHI VIẾT:
- k / ko / kg -> không
- đc / dc -> được
- 650k -> sáu trăm năm mươi nghìn
- 150k -> một trăm năm mươi nghìn
- shipcod / ship COD -> thanh toán khi nhận hàng
- full thog tin -> đầy đủ thông tin
- "lụm", "chốt", "cọc rồi" là tín hiệu mua thật, không phải câu hỏi kỹ thuật.

KIẾN THỨC SẢN PHẨM CHỈ DÙNG KHI CHAT CÓ LIÊN QUAN:
- Hộp Samsung DeX không kèm máy: sáu trăm năm mươi nghìn.
- Cọc thường là một trăm năm mươi nghìn, còn lại thanh toán khi nhận hàng.
- Hộp không kèm máy thường có hàng sẵn nếu shop đã nói có sẵn.
- Không tự nhắc combo/kèm máy/giá khác nếu khách không hỏi.

BẢO MẬT:
- Xóa hoàn toàn số điện thoại, STK, ngân hàng, QR chuyển khoản, danh thiếp/contact card.
- Xóa địa chỉ chi tiết; chỉ được giữ tỉnh/thành phố như "Ninh Bình".
- Không viết "(khách gửi danh thiếp)", "(kèm QR)", "(gửi STK)" hay ghi chú tương tự.

OUTPUT:
- Chỉ trả về kịch bản text thuần.
- Không có nhãn "Khách:" hoặc "Shop:".
- Mỗi lượt thoại cách nhau một dòng trống.
- Câu ngắn, tự nhiên, đúng thứ tự giao dịch trong chat.

VÍ DỤ CHUẨN:
Em muốn mua box không kèm máy.

Hộp không kèm máy là sáu trăm năm mươi nghìn nha em.

Em muốn mua bộ này.

Ok em! Bộ này giá sáu trăm năm mươi nghìn, hàng có sẵn. Em cọc một trăm năm mươi nghìn, còn lại thanh toán khi nhận hàng nha.

Anh gửi thông tin chuyển khoản cọc cho em nhé. Chuyển khoản nhanh giúp anh nha.

Em cọc rồi đó anh.

Anh nhận được cọc rồi. Em nhắn đầy đủ thông tin nhận hàng cho anh nha.

Ninh Bình anh nha."""



# ── Apple-style interface tokens ──────────────────────────────────
# StudentUtils-inspired: mostly-white canvas, soft grouped strips,
# compact native-like controls, and one clear blue accent.
BG          = "#ffffff"
SURFACE     = "#ffffff"
SURFACE_2   = "#fafafa"
CONTROL_BG  = "#f5f5f5"
CONTROL_HV  = "#eeeeef"
CONTROL_DN  = "#e5e5e7"
BORDER      = "#dedee3"
BORDER_SOFT = "#eeeeef"
TEXT        = "#1d1d1f"
TEXT_MUTE   = "#6e6e73"
TEXT_FAINT  = "#8e8e93"
ACCENT      = "#007aff"
ACCENT_HV   = "#0a84ff"
ACCENT_DN   = "#0066d6"
SEG_BG      = "#e9e9ee"
SUCCESS     = "#34c759"
WARNING     = "#ff9f0a"
DESTRUCTIVE = "#ff3b30"
CARD_RADIUS = 12
CONTROL_RADIUS = 8

def _theme_tokens(theme: str | None = "light") -> dict[str, str]:
    mode = (theme or "light").strip().lower()
    if mode == "dark":
        return {
            "BG": "#1c1c1e",
            "SURFACE": "#1c1c1e",
            "SURFACE_2": "#242426",
            "CONTROL_BG": "#2c2c2e",
            "CONTROL_HV": "#363638",
            "CONTROL_DN": "#3a3a3c",
            "BORDER": "#3a3a3c",
            "BORDER_SOFT": "#2f2f31",
            "TEXT": "#f5f5f7",
            "TEXT_MUTE": "#aeaeb2",
            "TEXT_FAINT": "#8e8e93",
            "ACCENT": "#0a84ff",
            "ACCENT_HV": "#409cff",
            "ACCENT_DN": "#006fd6",
            "SEG_BG": "#3a3a3c",
            "SELECTION_BG": "#1f5f9f",
            "POPUP_BG": "#2c2c2e",
            "POPUP_TEXT": "#f5f5f7",
            "POPUP_BORDER": "#48484a",
            "POPUP_SELECTED": "#124f87",
            "SCROLL": "#636366",
            "SCROLL_HV": "#8e8e93",
        }
    return {
        "BG": BG,
        "SURFACE": SURFACE,
        "SURFACE_2": SURFACE_2,
        "CONTROL_BG": CONTROL_BG,
        "CONTROL_HV": CONTROL_HV,
        "CONTROL_DN": CONTROL_DN,
        "BORDER": BORDER,
        "BORDER_SOFT": BORDER_SOFT,
        "TEXT": TEXT,
        "TEXT_MUTE": TEXT_MUTE,
        "TEXT_FAINT": TEXT_FAINT,
        "ACCENT": ACCENT,
        "ACCENT_HV": ACCENT_HV,
        "ACCENT_DN": ACCENT_DN,
        "SEG_BG": SEG_BG,
        "SELECTION_BG": "#cce4ff",
        "POPUP_BG": "#ffffff",
        "POPUP_TEXT": "#1d1d1f",
        "POPUP_BORDER": "#d2d2d7",
        "POPUP_SELECTED": "#e8f0fe",
        "SCROLL": "#c7c7cc",
        "SCROLL_HV": "#aeaeb2",
    }


def resolve_app_theme(theme: str | None) -> str:
    mode = (theme or "system").strip().lower()
    if mode in {"dark", "light"}:
        return mode
    try:
        value = subprocess.check_output(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            stderr=subprocess.DEVNULL,
            timeout=0.3,
            text=True,
        ).strip()
        return "dark" if value.lower() == "dark" else "light"
    except Exception:
        return "light"


def theme_tokens(theme: str | None = "light") -> dict[str, str]:
    return _theme_tokens(resolve_app_theme(theme))


def apply_theme_globals(target_globals: dict, theme: str | None = "light") -> dict[str, str]:
    """Update imported color token names inside a module before building UI."""
    tokens = theme_tokens(theme)
    for key in (
        "BG", "SURFACE", "SURFACE_2", "CONTROL_BG", "CONTROL_HV", "CONTROL_DN",
        "BORDER", "BORDER_SOFT", "TEXT", "TEXT_MUTE", "TEXT_FAINT",
        "ACCENT", "ACCENT_HV", "ACCENT_DN", "SEG_BG",
    ):
        if key in tokens:
            target_globals[key] = tokens[key]
    return tokens


def get_style(theme: str | None = "light") -> str:
    t = theme_tokens(theme)
    return f"""
QWidget {{
    font-family: "Arial", "Helvetica Neue", "Helvetica";
    font-size: 13px;
    background: {t["BG"]};
    color: {t["TEXT"]};
}}
QLabel {{
    color: {t["TEXT"]};
    background: transparent;
    border: none;
}}
QTextEdit, QPlainTextEdit, QLineEdit {{
    border: 1px solid {t["BORDER_SOFT"]};
    border-radius: {CONTROL_RADIUS}px;
    padding: 7px 10px;
    background: {t["SURFACE"]};
    color: {t["TEXT"]};
    selection-background-color: {t["SELECTION_BG"]};
    selection-color: {t["TEXT"]};
}}
QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus {{
    border-color: {t["ACCENT"]};
    background: {t["SURFACE"]};
}}
QLineEdit {{
    min-height: 26px;
}}
QTextEdit:disabled, QPlainTextEdit:disabled, QLineEdit:disabled {{
    color: {t["TEXT_FAINT"]};
    background: {t["CONTROL_BG"]};
}}
QComboBox {{
    border: none;
    border-radius: {CONTROL_RADIUS}px;
    padding: 3px 26px 3px 10px;
    min-height: 24px;
    background: {t["CONTROL_BG"]};
    color: {t["TEXT"]};
}}
QComboBox:hover {{
    background: {t["CONTROL_HV"]};
}}
QComboBox:focus {{
    background: {t["CONTROL_HV"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {t["POPUP_BG"]};
    color: {t["POPUP_TEXT"]};
    border: 1px solid {t["POPUP_BORDER"]};
    border-radius: 8px;
    outline: none;
    selection-background-color: {t["POPUP_SELECTED"]};
    selection-color: {t["POPUP_TEXT"]};
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 4px 12px;
    color: {t["POPUP_TEXT"]};
}}
QPushButton {{
    border: 1px solid transparent;
    border-radius: {CONTROL_RADIUS}px;
    padding: 4px 13px;
    min-height: 26px;
    background: {t["CONTROL_BG"]};
    color: {t["TEXT"]};
}}
QPushButton:hover   {{ background: {t["CONTROL_HV"]}; }}
QPushButton:pressed {{ background: {t["CONTROL_DN"]}; }}
QPushButton:disabled {{ background: {t["CONTROL_BG"]}; color: {t["TEXT_FAINT"]}; border-color: {t["BORDER_SOFT"]}; }}
QCheckBox {{
    spacing: 8px;
    color: {t["TEXT"]};
    background: transparent;
    border: none;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {t["BORDER"]};
    border-radius: 5px;
    background: {t["SURFACE"]};
}}
QCheckBox::indicator:hover {{
    border-color: {t["BORDER"]};
    background: {t["SURFACE_2"]};
}}
QCheckBox::indicator:checked {{
    background: {t["ACCENT"]};
    border-color: {t["ACCENT"]};
}}
QSlider::groove:horizontal {{
    height: 4px; background: {t["SEG_BG"]}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {t["ACCENT"]}; width: 18px; height: 18px;
    margin: -7px 0; border-radius: 9px;
    border: 2px solid {t["SURFACE"]};
}}
QSlider::sub-page:horizontal {{ background: {t["ACCENT"]}; border-radius: 2px; }}
QProgressBar {{
    background: {t["SEG_BG"]};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {t["ACCENT"]};
    border-radius: 5px;
}}
QFrame[frameShape="4"] {{ background: {t["BORDER_SOFT"]}; max-height: 1px; border: none; }}
QScrollBar:vertical {{ width: 6px; background: transparent; }}
QScrollBar::handle:vertical {{ background: {t["SCROLL"]}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t["SCROLL_HV"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QDialog {{ background: {t["BG"]}; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {t["TEXT_MUTE"]};
    padding: 8px 18px;
    font-size: 13px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
}}
QTabBar::tab:selected {{
    color: {t["TEXT"]};
    font-weight: 600;
    border-bottom: 2px solid {t["ACCENT"]};
}}
QTabBar::tab:hover:!selected {{ color: {t["TEXT"]}; }}
QListWidget {{
    border: 1px solid {t["BORDER_SOFT"]};
    border-radius: {CARD_RADIUS}px;
    background: {t["SURFACE"]};
    padding: 6px;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 7px;
}}
QListWidget::item:selected {{
    background: {t["POPUP_SELECTED"]};
    color: {t["TEXT"]};
}}
QMenu {{
    background: {t["SURFACE"]};
    border: 1px solid {t["BORDER"]};
    border-radius: {CARD_RADIUS}px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px;
    border-radius: 7px;
    color: {t["TEXT"]};
}}
QMenu::item:selected {{
    background: {t["POPUP_SELECTED"]};
    color: {t["ACCENT"]};
}}
QMenu::separator {{
    height: 1px;
    background: {t["BORDER_SOFT"]};
    margin: 5px 4px;
}}
"""


STYLE = get_style("light")
