import os
import json
import httpx
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from supabase import create_client, Client
from jose import jwt, JWTError
import io

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "change-me")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

app = FastAPI(title="TTS App")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ── Default enhance prompt ──────────────────────────────────────────────────
DEFAULT_PROMPT = """Bạn là chuyên gia tối ưu kịch bản cho ElevenLabs v3 TTS với giọng Adam.

## GIỌNG ADAM — ĐẶC ĐIỂM
Giọng nam, trầm ấm, quyền lực, kiên định (Dominant, Firm).
Tags phù hợp nhất: [professional] [assertive] [thoughtful] [impressed] [curious] [warmly] [happy] [questioning] [reassuring]
Tags TUYỆT ĐỐI TRÁNH: [giggles] [nervous] [sheepishly] [whining]

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

### 5. AUDIO TAGS
[curious] → câu mở đầu, đặt vấn đề
[professional] → giải thích kỹ thuật, thông tin sản phẩm
[assertive] → khẳng định, cam kết, chốt vấn đề
[questioning] → câu hỏi, xác nhận
[warmly] → chào hỏi, cảm ơn
[happy] → phản ứng tích cực, đồng ý
[reassuring] → trấn an lo lắng
[thoughtful] → trước khi giải thích sâu
[impressed] → phản ứng ngạc nhiên tích cực

### 6. NHẤN MẠNH — VIẾT HOA
Chỉ CAPS từ thật sự quan trọng: MIỄN PHÍ, NGON, SỚM, LUÔN, TỐI GIẢN, CHẮC CHẮN, ĐẢM BẢO

### 7. PAUSE & NHỊP
... → dừng cân nhắc, trước thông tin quan trọng
— → ngắt nhanh giữa 2 ý liên tiếp

### 8. CẤU TRÚC
- Mỗi câu/ý trên một dòng riêng
- Dòng trống giữa các ý khác nhau
- Xóa: kkk, haha, hehe, hihi, :), XD, ^^, :D

### 9. OUTPUT
- Chỉ trả về kịch bản đã xử lý
- Không giải thích, không ghi chú, không markdown"""

# ── Auth helpers ────────────────────────────────────────────────────────────

def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except JWTError:
        return None


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


def get_user_id(request: Request) -> str | None:
    user = get_current_user(request)
    if user:
        return user.get("sub")
    return None


# ── User settings helpers ───────────────────────────────────────────────────

def get_user_settings(user_id: str) -> dict:
    try:
        res = supabase_admin.table("user_settings").select("*").eq("user_id", user_id).single().execute()
        if res.data:
            return res.data
    except Exception:
        pass
    return {
        "el_api_key": "",
        "ds_api_key": "",
        "enhance_prompt": DEFAULT_PROMPT,
        "default_speed": 1.0,
    }


def save_user_settings(user_id: str, settings: dict):
    existing = None
    try:
        res = supabase_admin.table("user_settings").select("id").eq("user_id", user_id).single().execute()
        existing = res.data
    except Exception:
        pass

    data = {**settings, "user_id": user_id}
    if existing:
        supabase_admin.table("user_settings").update(data).eq("user_id", user_id).execute()
    else:
        supabase_admin.table("user_settings").insert(data).execute()


# ── TTS helpers ─────────────────────────────────────────────────────────────

async def enhance_with_deepseek(text: str, ds_api_key: str, enhance_prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {ds_api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": enhance_prompt},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
        )
        if res.status_code != 200:
            raise Exception(f"DeepSeek lỗi {res.status_code}: {res.text[:200]}")
        return res.json()["choices"][0]["message"]["content"].strip()


async def generate_tts(text: str, el_api_key: str, speed: float) -> bytes:
    voice_id = "pNInz6obpgDQGcFmaJgB"  # Adam
    async with httpx.AsyncClient(timeout=90) as client:
        res = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": el_api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_v3",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": speed},
            },
        )
        if res.status_code != 200:
            raise Exception(f"ElevenLabs lỗi {res.status_code}: {res.text[:300]}")
        return res.content


async def check_credits(el_api_key: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": el_api_key},
            )
            if res.status_code == 200:
                data = res.json()
                used = data.get("character_count", 0)
                limit = data.get("character_limit", 0)
                return {"used": used, "limit": limit, "remaining": limit - used}
    except Exception:
        pass
    return {"used": 0, "limit": 0, "remaining": 0}


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    user_id = user.get("sub")
    settings = get_user_settings(user_id)
    credits = {}
    if settings.get("el_api_key"):
        credits = await check_credits(settings["el_api_key"])
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "credits": credits,
        "default_speed": settings.get("default_speed", 1.0),
        "has_keys": bool(settings.get("el_api_key") and settings.get("ds_api_key")),
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        token = res.session.access_token
        response = RedirectResponse("/", status_code=302)
        response.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)
        return response
    except Exception as e:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Email hoặc mật khẩu không đúng",
        })


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/")
    return templates.TemplateResponse("register.html", {"request": request, "error": None, "success": None})


@app.post("/register", response_class=HTMLResponse)
async def register_post(request: Request, email: str = Form(...), password: str = Form(...), password2: str = Form(...)):
    if password != password2:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Mật khẩu xác nhận không khớp", "success": None,
        })
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Mật khẩu tối thiểu 6 ký tự", "success": None,
        })
    try:
        supabase.auth.sign_up({"email": email, "password": password})
        return templates.TemplateResponse("register.html", {
            "request": request, "error": None,
            "success": "Đăng ký thành công! Kiểm tra email để xác nhận tài khoản.",
        })
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Email đã được sử dụng hoặc không hợp lệ", "success": None,
        })


@app.get("/forgot", response_class=HTMLResponse)
async def forgot_page(request: Request):
    return templates.TemplateResponse("forgot.html", {"request": request, "error": None, "success": None})


@app.post("/forgot", response_class=HTMLResponse)
async def forgot_post(request: Request, email: str = Form(...)):
    try:
        supabase.auth.reset_password_email(email)
    except Exception:
        pass
    return templates.TemplateResponse("forgot.html", {
        "request": request, "error": None,
        "success": "Nếu email tồn tại, link đặt lại mật khẩu đã được gửi.",
    })


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    settings = get_user_settings(user.get("sub"))
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "settings": settings,
        "error": None,
        "success": None,
    })


@app.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    el_api_key: str = Form(""),
    ds_api_key: str = Form(""),
    default_speed: float = Form(1.0),
    enhance_prompt: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    user_id = user.get("sub")
    settings = {
        "el_api_key": el_api_key.strip(),
        "ds_api_key": ds_api_key.strip(),
        "default_speed": max(0.7, min(1.2, default_speed)),
        "enhance_prompt": enhance_prompt.strip() or DEFAULT_PROMPT,
    }
    try:
        save_user_settings(user_id, settings)
        return templates.TemplateResponse("settings.html", {
            "request": request, "user": user, "settings": settings,
            "error": None, "success": "Đã lưu cài đặt!",
        })
    except Exception as e:
        return templates.TemplateResponse("settings.html", {
            "request": request, "user": user, "settings": settings,
            "error": f"Lỗi lưu cài đặt: {str(e)}", "success": None,
        })


@app.post("/generate")
async def generate(
    request: Request,
    script: str = Form(...),
    filename: str = Form("output"),
    speed: float = Form(1.0),
    skip_enhance: bool = Form(False),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    settings = get_user_settings(user.get("sub"))
    el_key = settings.get("el_api_key", "")
    ds_key = settings.get("ds_api_key", "")
    enhance_prompt = settings.get("enhance_prompt", DEFAULT_PROMPT)

    if not el_key or not ds_key:
        raise HTTPException(status_code=400, detail="Chưa cài đặt API keys. Vào Settings để thêm.")

    speed = max(0.7, min(1.2, speed))
    text = script.strip()

    if not text:
        raise HTTPException(status_code=400, detail="Kịch bản trống")

    # Enhance with DeepSeek (unless skipped)
    if not skip_enhance:
        text = await enhance_with_deepseek(text, ds_key, enhance_prompt)

    # Generate TTS
    audio_bytes = await generate_tts(text, el_key, speed)

    # Return as downloadable mp3
    safe_name = filename.strip().replace(" ", "_") or "output"
    if not safe_name.endswith(".mp3"):
        safe_name += ".mp3"

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@app.post("/enhance-preview")
async def enhance_preview(request: Request, script: str = Form(...)):
    """Trả về kịch bản đã enhance (không generate audio) để user xem trước."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    settings = get_user_settings(user.get("sub"))
    ds_key = settings.get("ds_api_key", "")
    enhance_prompt = settings.get("enhance_prompt", DEFAULT_PROMPT)

    if not ds_key:
        raise HTTPException(status_code=400, detail="Chưa cài đặt DeepSeek API key")

    enhanced = await enhance_with_deepseek(script.strip(), ds_key, enhance_prompt)
    return {"enhanced": enhanced, "chars": len(enhanced)}
