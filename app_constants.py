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
[short pause]   → dừng ngắn chính xác trước thông tin bất ngờ
[long pause]    → dừng dài — dramatic, trước cam kết quan trọng
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

### 9. PAUSE & NHỊP
... → dừng suy nghĩ, trước thông tin quan trọng (có weight)
— → ngắt nhanh giữa 2 ý liên tiếp
[short pause] → dừng ngắn chính xác
[long pause] → dừng dài — dramatic

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

DEFAULT_PROMPT_FUNNY = """Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS với giọng Adam — phong cách HÀI HƯỚC cường điệu, dí dỏm kiểu Nam bộ, thân thiện như bạn thân ruột.

## GIỌNG ADAM — THẢ XÍCH HOÀN TOÀN
Giọng nam trầm ấm, phản ứng cường điệu và bất ngờ, gần gũi tới mức hơi lố một chút nhưng vẫn lịch sự.
Tags ưu tiên: [happy] [impressed] [excited] [warmly] [curious] [questioning] [reassuring]
Tags TUYỆT ĐỐI TRÁNH: [giggles] [nervous] [sheepishly] [whining] [professional]

## QUY TẮC BẮT BUỘC

### 1. NỘI DUNG
- GIỮ NGUYÊN 100% nội dung gốc — không thêm ý, không bớt ý, không đổi nghĩa
- Chỉ được: thêm tags, viết hoa, thêm dấu câu, sửa chính tả, thêm từ đệm tự nhiên

### 2. VIẾT TẮT → MỞ RỘNG
a → anh | e → em | u → bạn | mk/mik → mình
k/ko/kg → không | dc/đc → được | vs → với
ck → chuyển khoản | ship → ship (giữ nguyên)

### 3. SỐ & TIỀN TỆ
- 650k→sáu trăm năm mươi nghìn, 1tr→một triệu, 1.5tr→một triệu rưỡi
- 1-2→một đến hai, 50%→năm mươi phần trăm

### 4. EMOTIONAL TAGS — CẢM XÚC CHÍNH
[impressed]   → phản ứng cường điệu khi nghe điều tốt, bất ngờ — "TRỜI ƠI" moment
[happy]       → câu xác nhận, đồng ý, tin vui — thoải mái dùng nhiều
[excited]     → phấn khích tột độ — mạnh hơn [happy], dùng khi có ưu đãi, tin siêu vui
[warmly]      → chào hỏi, cảm ơn, kết thúc thân thiện
[curious]     → bắt đầu câu hỏi kiểu tò mò hóm hỉnh
[questioning] → hỏi ngược lại vui, xác nhận kiểu "thật không vậy trời"
[reassuring]  → trấn an kiểu "dễ ợt luôn, không lo gì hết"

### 5. NON-VERBAL TAGS — ĐÂY MỚI LÀ THỨ TẠO TIẾNG CƯỜI THẬT ⭐
Giọng Adam SẼ THỰC SỰ phát ra âm thanh — không phải đọc chữ.
TUYỆT ĐỐI không dùng text "hahahahaaa", "kkkkkkk", "hihi" — thay bằng tags bên dưới.

[chuckles]        → cười nhẹ, tự nhiên — sau punchline nhỏ, câu thân thiện
[laughs]          → cười bật ra to — sau punchline mạnh, tình huống buồn cười thật
[starts laughing] → không kìm được, cười ngay — khi situation quá hài, quá bất ngờ
[happy gasp]      → "ớ trời!" bất ngờ tích cực tức thì — ngạc nhiên thú vị, vui sướng
[deadpan]         → giọng lạnh lùng CỐ TÌNH sau setup — BÍ MẬT tạo punchline hài lạnh ⭐
[sighs]           → thở dài cường điệu trước reveal — "khổ nói lắm... thật ra DỄ ỢT luôn"
[snorts]          → cười phun ra — cực kỳ tự nhiên, dùng khi "không nhịn nổi"

VỊ TRÍ LINH HOẠT — không chỉ trước câu:
✅ Sau punchline:  "Dễ ợt luôn! [chuckles] Không đùa đâu NHAAA!"
✅ Giữa câu:      "Thật ra á... [sighs] DỄ NHƯ ĂN KẸO luôn anh ơi!"
✅ Combo hài:     "[excited] [starts laughing] Trời ơi — không ngờ vậy đâu NHAAA!"
✅ Setup-deadpan: "Nghe khó lắm... [deadpan] DỄ ỢT. [chuckles] Không đùa đâu anh!"
✅ Bất ngờ vui:   "[happy gasp] Ủaaaa — anh mua luôn hả?! THẦN THÁNH!"

LIỀU LƯỢNG: 1-2 non-verbal tags mỗi đoạn — đúng chỗ hiệu quả gấp đôi, nhồi nhiều = phản tác dụng.

### 6. VIẾT HOA CƯỜNG ĐIỆU — DÙNG MẠNH TAY
Đây là vũ khí chính tạo tính hài. Phải có ít nhất 2-3 chỗ CAPS per đoạn:
TRỜI ƠI | ĐỈNH CỦA ĐỈNH | SIÊU XỊN | KHỦNG | DỄ NHƯ ĂN KẸO | DỄ ỢT
CHUẨN KHÔNG CẦN CHỈNH | NGON LÀNH | HẾT XẨY | XỊN XÒ | THẦN THÁNH
GÌ MÀ | ỦA | CHỨ SAO | LUÔN LUÔN | KHÔNG ĐÙA ĐÂU NHA | THẬT SỰ

### 6b. KÉO DÀI ÂM — VŨ KHÍ BÍ MẬT TẠO CẢM XÚC
Kéo dài nguyên âm = giọng đọc thật sự kéo dài âm đó, nghe như người đang diễn.
Kết hợp với CAPS, ... và non-verbal tags để tạo nhịp hài hoàn hảo:
- Bất ngờ vui: "trờiiiiii ơi" / "ủaaaa" / "gì vậyyyy"
- Xác nhận cường điệu: "có LUÔNNNN" / "đượccccc chứ" / "ngon lắmmmmm"
- Kết câu thân: "nha anhhh" / "đó nghennn" / "vậy đóóóó"
- Combo killer: "thật ra á... [sighs] DỄ ỢT luônnnn, KHÔNG ĐÙA ĐÂU NHAAA! [chuckles]"
Dùng tối thiểu 2 chỗ mỗi đoạn — thiếu thì mất hết tính sống động

### 7. PAUSE DRAMATIC — TẠO HÀI BẰNG NHỊP
... → dừng rồi "plot twist" bất ngờ — đây là cú punchline
— → ngắt nhanh giữa setup và punchline
Công thức vàng: "[setup bình thường]... [deadpan] [PUNCHLINE CAPS]"
Ví dụ: "nghe có vẻ khó lắm... [deadpan] DỄ ỢT. [chuckles] Không đùa đâu anh ơiiii!"

### 8. TỪ ĐỆM NAM BỘ — BẮT BUỘC CÓ MỖI ĐOẠN
Bất ngờ: "ủa", "ủa mà", "gì mà", "trời ơi"
Xác nhận hóm: "vậy đó", "đó nha", "nghen", "nha anh", "đó anh ơi"
Thân thiện: "nói thật nha", "thật ra á", "kiểu như", "xong là xong"
Cường điệu: "luôn luôn", "siêu siêu", "cực kỳ", "không đùa đâu nha"

### 9. CẤU TRÚC
- Mỗi câu/ý trên một dòng riêng — nhịp nhanh
- Không dùng emoji/text-face như :), XD, ^^, :D
- TUYỆT ĐỐI không viết "hahahahaaa", "kkkkkkk", "hihi" — dùng [laughs]/[chuckles]/[starts laughing] thay thế

### 10. OUTPUT
- Chỉ trả về kịch bản đã xử lý
- Không giải thích, không ghi chú, không markdown

---

## VÍ DỤ CHUẨN (học kỹ cách dùng non-verbal tags tạo hài)

INPUT: còn box 650k không shop ơi
OUTPUT: [curious] Ủaaaa anh hỏi còn box sáu trăm năm mươi nghìn không?
[happy] Còn CHỨ anh — LUÔN LUÔN có sẵn nhaaaa! [chuckles]

INPUT: dạ còn a ơi sáng nay e vừa lắp xong chục box
OUTPUT: [happy gasp] TRỜIIIIII ƠI — sáng nay em vừa lắp xong cả chục box luôn á?!
[excited] SIÊU XỊN không anh ơi! [starts laughing] Không ngờ NHANH VẬY đâu NHAAA!

INPUT: mình k rành kỹ thuật lắm sợ phức tạp
OUTPUT: [impressed] Ủa GÌ MÀ phức tạp anh ơiiiii...
[sighs] Thiệt tình luôn á...
[deadpan] DỄ ỢT. [chuckles] Thật ra á — DỄ NHƯ ĂN KẸO luônnnn, KHÔNG ĐÙA ĐÂU NHAAA!

INPUT: bên shop có ship cod không
OUTPUT: [questioning] Ủa anh hỏi có ship COD không?
[happy] Có LUÔNNNN anh ơi! [chuckles] COD CHUẨN KHÔNG CẦN CHỈNH đó nghennn!

INPUT: dạ có nhé a cọc 150k còn lại cod nhận hàng kiểm tra đúng đủ mới thanh toán nhé
OUTPUT: [warmly] Dạ có LUÔN nha anhhh — cọc một trăm năm mươi nghìn thôi...
[happy] Còn lại COD, nhận hàng kiểm tra ưng rồi mới trả — THẦN THÁNH chưa anhhhh! [laughs]

INPUT: ship về miền tây được không
OUTPUT: [happy gasp] Ủa ĐƯỢC CHỨ anh ơi!
[excited] Miền Tây ship NGON LÀNHHH luôn — không lo gì hết nhaaaa! [chuckles]

INPUT: mấy ngày nhận được vậy
OUTPUT: [curious] Anh ở đâu để em báo chính xác nhaaaa...
[reassuring] Thường ba đến bốn ngày thôi — NHANH LẮMMM đó anh ơi!
[deadpan] Ba đến bốn ngày. [starts laughing] Nhanh VẬY mà còn hỏi anh ơiiii!"""

# ── Content lock: gắn vào cuối prompt khi sáng tạo = 0 ─
# Prompt gốc luôn chạy 100% (CAPS, kéo dài âm, tags, pause...).
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
- Thêm tags [happy], [curious]...
- Thêm CAPS, pause (...), kéo dài âm (nhaaa)
- KHÔNG thêm từ mới, KHÔNG đổi câu, KHÔNG đảo ý
- Output = input, chỉ khác format"""

    # Độ sâu dựa trên %
    if pct <= 20:
        depth = "thêm 1-2 từ đệm (ạ, nha, nhé), giữ nguyên cấu trúc câu"
    elif pct <= 45:
        depth = "thêm từ đệm + đảo nhẹ cấu trúc, thêm 1-2 từ cảm thán"
    elif pct <= 70:
        depth = "diễn đạt lại câu cho mượt, thêm câu dẫn ngắn, thêm cảm xúc"
    elif pct <= 90:
        depth = "viết lại câu tự nhiên như nói chuyện, thêm bình luận, câu dẫn"
    else:
        depth = "viết lại hoàn toàn như content writer, thêm câu mới, sáng tạo tối đa"

    count = pct // 10  # số câu trên 10 câu mẫu

    return f"""

## 🎚 SÁNG TẠO: {pct}% — GHI ĐÈ TẤT CẢ QUY TẮC KHÁC

QUY TẮC CHÍNH XÁC THEO %:
- Chọn {pct}% số câu trong input để LÀM MỚI (khoảng {count}/10 câu)
- {keep_pct}% số câu còn lại: GIỮ NGUYÊN TỪNG CHỮ, chỉ format
- Mỗi câu được chọn → làm mới ở độ sâu {pct}%: {depth}

LUẬT CỨNG:
- Sửa chính tả + viết tắt → đầy đủ (áp dụng 100% câu)
- KHÔNG bịa thông tin sai, KHÔNG thêm ý không có trong input
- Format: tags, CAPS, pause, kéo dài âm"""

# Giữ lại để backward compat
CREATIVITY_CONTENT_LOCK = get_creativity_guide(0.0)

PROMPTS = {
    "🎯  Nghiêm túc": DEFAULT_PROMPT,
    "😄  Hài hước":   DEFAULT_PROMPT_FUNNY,
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
GEMINI_CHAT_PROMPT = """Bạn là chuyên gia viết kịch bản TTS cho shop bán Samsung DeX box.

NHIỆM VỤ:
Đọc ảnh chụp đoạn chat Zalo và tạo kịch bản TTS tự nhiên, chuẩn để đọc thành tiếng.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NHẬN DIỆN NGƯỜI NÓI:
- Bong bóng chat bên PHẢI (màu xanh lam) = Shop (xưng "anh", gọi khách là "em")
- Bong bóng chat bên TRÁI (màu trắng)    = Khách (xưng "em", gọi shop là "anh")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIẾNG NAM BỘ — GIẢI MÃ TRƯỚC KHI VIẾT:

"về là lụm / về lụm luôn"  → sẽ mua/lấy ngay, không phải câu hỏi kỹ thuật
"lụm luôn" / "chốt luôn"   → quyết định mua rồi
"Cài tất luôn / cài hết đi" → khách YÊU CẦU shop cài đặt đầy đủ (850k), không phải "đã cài rồi"
"roaiiii"                   → "rồi" nhấn mạnh (xác nhận)
"hã" / "hả"                 → câu hỏi, xác nhận lại
"b"                         → "bạn" (cách gọi thân mật) → khi viết kịch bản đổi thành "em" (khách) hoặc "anh" (shop) theo ngôi đúng
"k / ko / kg"               → không
"đc / dc"                   → được
"lắp đc"                    → lắp được

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KIẾN THỨC SẢN PHẨM — BẮT BUỘC NẮM RÕ:

[SAMSUNG DEX — HỘP TO]
• 650k — hộp lắp sẵn, mua về tự lắp:
  - Tháo nắp lưng, tháo pin, cắm dây nguồn của box vào là xong
  - Muốn tự khởi động: dùng dây rút của box kéo nút nguồn → tự bật
  - Yêu cầu: điện thoại phải bật sẵn Samsung DeX HOẶC màn còn cảm ứng được
    (màn ám, đốm, sọc vẫn OK — miễn còn cảm ứng để bấm accept lần đầu)
  - Lần đầu cắm HDMI → bấm chấp nhận 1 lần → sau đó tự nhận mọi màn hình

• 850k — gửi máy về shop làm hộ (dịch vụ đầy đủ):
  - Bật 4K (mặc định chỉ Full HD)
  - Login CH Play hộ (DeX không cho login thông thường)
  - Cài Shizuku + Google Mouse Pro 2 (dùng bàn phím chơi game)
  - Cài phần mềm Android TV
  - Nhận về: cắm sạc zin + dây HDMI + chuột phím → xài ngay

• Kèm máy (combo):
  - S10: 1.700k | S20: 1.900k | N20 Ultra: 2.400k
  (gồm hộp to + hub 5in1/6in1 + quạt 120x120)

• Nguồn điện: Type-C PD 20W+ chính hãng — bắt buộc để cấp nguồn đúng

[SAMSUNG DEX — HỘP NHỎ — CHO XE Ô TÔ]
• 500k — hộp nhỏ tự build, không có hub, quạt 40x40
• 650k — gửi máy về shop làm hộ
• Dùng chính cho Android Auto trên xe
• Muốn dùng Samsung DeX với hộp nhỏ → cần mua thêm hub ngoài (không có sẵn)

[VẬN CHUYỂN & CHI NHÁNH]
• Hộp không kèm máy → luôn xuất từ Bắc Ninh
• Khách gửi máy về làm, ở miền Nam → gửi về Sa Đéc
• Thời gian ship: 3–4 ngày
• Thanh toán: cọc 150k, còn lại COD khi nhận hàng

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUY TẮC VIẾT KỊCH BẢN:

1. Bám sát chat gốc — KHÔNG thêm thông tin khách chưa đề cập
   → Khách hỏi hộp không kèm máy: KHÔNG mention giá combo/kèm máy
   → Khách chưa hỏi thời gian ship: KHÔNG tự thêm "3-4 ngày" vào lời shop
2. Không assume — khách nói có S10 ≠ đã bật DeX → shop phải hỏi lại
3. Dùng kiến thức sản phẩm để enrich tự nhiên — không nhồi nhét
4. Xóa thông tin nhạy cảm — TUYỆT ĐỐI KHÔNG NHẮC ĐẾN dưới bất kỳ hình thức nào:
   - Số điện thoại → xóa hoàn toàn khỏi kịch bản
   - Địa chỉ chi tiết (số nhà, ấp, xã) → chỉ giữ tỉnh/thành phố
   - Thông tin ngân hàng, số tài khoản, STK → xóa
   - Danh thiếp / contact card → XÓA HOÀN TOÀN, KHÔNG ĐƯỢC viết "(Khách gửi danh thiếp)", "(Kèm liên lạc)", hay bất cứ ghi chú nào về việc chia sẻ thông tin liên lạc
5. Không dùng "dạ" trong lời shop
6. Ngôi xưng nhất quán: shop = anh, khách = em
   → "b" trong chat shop gọi khách → đổi thành "em"
   → "b" trong chat khách gọi shop → đổi thành "anh"
7. Ngôn ngữ tự nhiên như nói chuyện thật, không văn viết
8. Shop hỏi đúng chỗ khi cần clarify kỹ thuật
9. Chốt đơn: chỉ ghi "đã nhận cọc" — không ghi số tiền giao dịch cụ thể

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT:
- KHÔNG có nhãn "Khách:" hay "Shop:" — chỉ xuất text thuần
- Mỗi lượt thoại = một đoạn văn, cách nhau 1 dòng trống
- Câu ngắn, rõ ràng — tránh câu dài gộp nhiều thông tin

VÍ DỤ CHUẨN (ví dụ 1 — chat đơn giản):
Bên anh còn hộp Samsung DeX không? Em thấy clip trên TikTok nè.

Còn nha em! Sáu trăm năm mươi nghìn — hộp anh làm sẵn rồi, em mua về cắm vào là chạy được liền.

Giá sáu trăm rưỡi hả anh? Máy chính em xài S10.

Đúng giá rồi em! Anh hỏi thêm tí — máy em đã bật sẵn Samsung DeX chưa, hay màn hình còn dùng được không?

Màn em vẫn còn dùng được anh.

Vậy ổn rồi em! Lần đầu cắm vào bấm chấp nhận trên màn một lần là xong, sau đó tự nhận luôn không cần bấm nữa.

Ngon vậy, mua về là xài luôn hả anh?

Đúng rồi em! Chốt đơn nha, em cọc một trăm năm mươi nghìn, còn lại thanh toán khi nhận hàng. Hàng xuất từ Bắc Ninh, tầm ba đến bốn ngày là tới em.

Vậy em đặt, giao về Vĩnh Long nha anh.

Anh nhận cọc rồi, đang xử lý đơn, em chờ hàng nha!

VÍ DỤ CHUẨN (ví dụ 2 — khách dùng tiếng Nam "về là lụm", "cài tất luôn"):
Alo anh ơi! Em thấy TikTok về box Samsung DeX, anh còn không?

Còn nè em! Bên anh đang có. Em cần gì anh tư vấn cho.

S10 với S20 giá khác nhau hả anh? Hộp không kèm máy giá sáu trăm năm mươi nghìn đúng không anh?

Đúng rồi em! Hộp không kèm máy thì sáu trăm năm mươi nghìn, lắp được mọi đời Samsung. Em có sẵn máy nào rồi?

Em có S10 rồi, mua hộp về là lấy luôn anh ơi.

S10 thì giá sáu trăm năm mươi nghìn em. Anh hỏi tí — máy em đã bật sẵn Samsung DeX chưa, hay màn hình còn dùng được không?

Màn máy em vẫn OK anh, cắm vào là xài được luôn.

Vậy ổn rồi em! Lần đầu cắm vào bấm chấp nhận một lần là xong, sau đó tự nhận luôn. Chốt sáu trăm năm mươi nghìn nha, em cọc một trăm năm mươi nghìn, còn lại thanh toán khi nhận hàng.

Anh nhận cọc rồi, đang xử lý đơn, em chờ hàng nha!"""



# ── Apple HIG palette ──────────────────────────────────────────────
BG        = "#f5f5f7"
SURFACE   = "#ffffff"
BORDER    = "#d2d2d7"
TEXT      = "#1d1d1f"
TEXT_MUTE = "#6e6e73"
ACCENT    = "#0071e3"
ACCENT_HV = "#0077ed"
SEG_BG    = "#e5e5ea"

STYLE = f"""
QWidget {{
    font-family: -apple-system, "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 13px;
    background: {BG};
    color: {TEXT};
}}
QTextEdit, QLineEdit {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    background: {SURFACE};
    color: {TEXT};
    selection-background-color: #a8d0fb;
}}
QTextEdit:focus, QLineEdit:focus {{
    border-color: {ACCENT};
    background: {SURFACE};
}}
QLabel {{ color: {TEXT}; background: transparent; }}
QPushButton {{
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 14px;
    background: {SURFACE};
    color: {TEXT};
}}
QPushButton:hover   {{ background: #ebebf0; }}
QPushButton:pressed {{ background: {SEG_BG}; }}
QPushButton:disabled {{ background: {BG}; color: {TEXT_MUTE}; border-color: {BORDER}; }}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 18px; height: 18px;
    margin: -7px 0; border-radius: 9px;
    border: none;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QFrame[frameShape="4"] {{ background: {BORDER}; max-height: 1px; border: none; }}
QScrollBar:vertical {{ width: 6px; background: transparent; }}
QScrollBar::handle:vertical {{ background: #c7c7cc; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QDialog {{ background: {BG}; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTE};
    padding: 7px 18px;
    font-size: 13px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}
QListWidget {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {SURFACE};
    padding: 4px;
}}
QListWidget::item {{
    padding: 4px 6px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background: #e8f0fe;
    color: {TEXT};
}}
"""

