# DESIGN PATTERNS — Cách tư duy xây dựng tool
# Dùng cho mọi dự án, không riêng Hedra Studio

---

## 1. WORKFLOW CỐT LÕI

### Trước khi làm gì: ĐỌC CLAUDE.md
Mỗi session bắt đầu bằng việc đọc file "master doc" — nơi chứa:
- Kiến trúc tổng thể
- Dependency chain (ai phụ thuộc ai)
- Rules/quy tắc đã học từ lần trước
- Session state: đang làm dở gì, quyết định quan trọng

### Làm xong: GHI VÀO CLAUDE.md
Mọi bài học, rule mới, bug pattern đều ghi lại. Không để "nhớ trong đầu".

---

## 2. DEBUG PATTERNS

### Pattern A: "Theo vết lỗi từ dưới lên"
Khi app crash, đọc traceback từ CUỐI LÊN:
```
NameError: name 'QWidget' is not defined
  File "voice_library.py", line 243  ← lỗi THẬT SỰ ở đây
  File "settings_dialog.py", line 21 ← import voice_library, nên cũng lỗi
  File "main_window.py", line 28     ← import settings_dialog, nên cũng lỗi
```
→ Fix đúng chỗ gốc (voice_library.py), không fix ở nơi bị ảnh hưởng.

### Pattern B: "Fix một, test một"
Không fix 10 lỗi cùng lúc rồi test. 
→ Fix 1 lỗi → syntax check → run → nếu OK mới fix tiếp.
→ Làm ngược lại: không biết lỗi mới từ đâu ra.

### Pattern C: "So sánh working vs broken"
Khi bản cũ chạy được, bản mới không:
→ Diff xem thay đổi GÌ giữa 2 bản
→ Ở đây: refactor 1 file → 8 file → vấn đề là imports và PyInstaller

### Pattern D: "Suy luận loại trừ"
App crash? Các giả thuyết:
1. Code bug → test từ source → OK → KHÔNG phải code
2. PyInstaller thiếu files → kiểm tra bundle → THIẾU modules → ĐÚNG
3. macOS Gatekeeper → hỏi user thấy popup gì → user bảo "nhấp nháy rồi tắt" → KHÔNG phải Gatekeeper
→ Khoanh vùng chính xác.

---

## 3. THIẾT KẾ HỆ THỐNG SÁNG TẠO (CREATIVITY SYSTEM)

Đây là case study quan trọng nhất — cách đi từ "không hoạt động" đến "hoàn hảo":

### Iteration 1: Binary lock (v1.5.x)
```
0% → lock hoàn toàn
>0% → không lock
```
Vấn đề: user bảo kéo 20% hay 80% thấy giống nhau.

### Iteration 2: 4 tier cố định (v1.6.0)
```
0%, 1-30%, 31-60%, 61-100%
```
Vấn đề: vẫn jump — 29% vs 31% khác hẳn.

### Iteration 3: Scale mô tả (v1.6.2)
Đưa nguyên cái scale cho AI, kêu nó "tự nội suy".
Vấn đề: AI không tự nội suy chính xác.

### Iteration 4: Công thức toán (v1.6.3)
```
filler = pct // 10
rephrase = max(0, pct - 25)
```
Vấn đề: user không biết công thức đang làm gì.

### Iteration 5: UI hiển thị công thức (v1.7.5+)
Thêm label real-time dưới slider → user thấy ngay "23% → thêm 2 từ đệm".
→ ĐẠT: user hiểu và kiểm soát được.

### BÀI HỌC:
- Đừng cố làm hoàn hảo ngay từ đầu. Ra bản nhanh, test, sửa.
- Công thức toán > mô tả mơ hồ (AI làm theo số, không làm theo "cảm nhận")
- User phải THẤY được hệ thống đang làm gì (UI transparency)
- % phải thay đổi LIÊN TỤC, không jump theo bậc

---

## 4. KHÁM PHÁ API (API DISCOVERY)

GenMax không có docs public. Cách tôi tìm ra endpoints:

### Bước 1: Dùng key thật gọi thử
```bash
curl -s https://api.genmax.io/v1/auth/me -H "xi-api-key: $KEY"
```
→ 303 bytes JSON → CÓ endpoint!

### Bước 2: Pattern matching
GenMax là proxy ElevenLabs → thử các endpoint giống ElevenLabs:
/v1/voices, /v1/user/subscription, /v1/models...

### Bước 3: Nhờ user lấy docs từ web
F12 → Console → `copy(document.body.innerText)` → paste

### Bước 4: Verify từng endpoint với key thật
Chỉ tin endpoint nào trả về JSON, không tin HTML.

### BÀI HỌC:
- Không cần docs chính thức nếu biết pattern của API gốc
- Luôn verify bằng key thật, không đoán
- Dùng user làm "cầu nối" vào web dashboard

---

## 5. BUILD PIPELINE

### Local dev:
```bash
python tts_app.py              # Test nhanh
python -m py_compile *.py      # Syntax check
```

### CI build:
```
Push tag v* → GitHub Actions → PyInstaller → DMG/EXE → Release
```

### Quy tắc:
- KHÔNG build DMG local (macOS TCC chặn)
- CI là single source of truth cho production build
- Mỗi lần push tag là 1 release

---

## 6. QUẢN LÝ COMPLEXITY

### "One source of truth"
Mọi constant ở 1 chỗ (app_constants.py).
Không copy-paste giá trị qua các file.

### Dependency chain tuyến tính
A → B → C → D
Không cho phép D import A (circular).
Khi thêm file mới: chèn đúng vị trí trong chain.

### Hidden imports
PyInstaller không auto-detect hết → luôn thêm vào TTS.spec.
Quy tắc: mỗi file .py mới = 1 dòng trong hiddenimports.

---

## 7. COMMUNICATION VỚI USER

- **Hỏi đúng câu:** "App báo lỗi gì?" → không phải "App có chạy không?"
- **Cho chọn:** request_user_input với options cụ thể
- **Xác nhận trước khi làm lớn:** "Có 3 file cần sửa, OK không?"
- **Không giải thích dài dòng:** 1 câu kết quả + link download
- **Khi user nói "vẫn lỗi":** hỏi thêm chi tiết, đừng đoán

---

## 8. ANTI-PATTERNS (những thứ đã làm sai)

1. **git add -A** → commit cả worktrees rác → phải amend + force push
2. **Fix nhiều thứ cùng lúc** → không biết cái nào fix được, cái nào không
3. **Đoán lỗi thay vì đợi error log** → mất 5 version đoán mới có log thật từ user
4. **"Chắc là được rồi"** → không verify trước khi báo user

---

## 9. TEMPLATE CHO DỰ ÁN MỚI

```
1. Tạo CLAUDE.md với:
   - Architecture overview
   - Dependency chain
   - Build/run commands
   - Lab Notes (để trống, sẽ điền dần)

2. Mỗi session:
   - Đọc CLAUDE.md
   - Làm việc
   - Ghi bài học vào Lab Notes
   - Update Session State

3. Mỗi bug:
   - Ghi vào bug pattern để lần sau không lặp lại

4. Mỗi feature:
   - Design doc ngắn (1-2 câu) trước khi code
   - Iterate: bản thô → test → tinh chỉnh
```
