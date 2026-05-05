# Setup hướng dẫn — TTS Web App

## Bước 1 — Tạo Supabase project

1. Vào https://supabase.com → New project
2. Điền tên project, chọn region (Singapore gần nhất)
3. Đợi ~2 phút để project khởi động

## Bước 2 — Lấy API keys

Vào **Settings → API**:
- `SUPABASE_URL` = Project URL (dạng `https://xxxx.supabase.co`)
- `SUPABASE_ANON_KEY` = `anon public` key
- `SUPABASE_SERVICE_ROLE_KEY` = `service_role` key (giữ bí mật)

## Bước 3 — Tạo bảng user_settings

Vào **SQL Editor** → **New query** → paste SQL sau → Run:

```sql
create table public.user_settings (
  id uuid default gen_random_uuid() primary key,
  user_id uuid not null unique references auth.users(id) on delete cascade,
  el_api_key text default '',
  ds_api_key text default '',
  enhance_prompt text default '',
  default_speed float default 1.0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Chỉ cho phép user đọc/sửa settings của chính mình
alter table public.user_settings enable row level security;

create policy "Users manage own settings"
  on public.user_settings
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- Service role bypass RLS (để backend đọc/ghi)
create policy "Service role full access"
  on public.user_settings
  for all
  to service_role
  using (true)
  with check (true);
```

## Bước 4 — Cấu hình Auth

Vào **Authentication → Settings**:
- **Site URL**: `http://localhost:8000` (dev) hoặc URL Cloudflare Tunnel (production)
- **Email confirmations**: Tắt nếu muốn đăng ký không cần verify email (dễ dùng nội bộ hơn)

## Bước 5 — Điền .env

Copy file mẫu và điền keys:

```bash
cp web/.env.example web/.env
```

Mở `web/.env` và điền:
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
APP_SECRET_KEY=random-string-32-chars
```

## Bước 6 — Chạy app

Double-click **"Mở Web TTS.command"** — tự động mở browser tại http://localhost:8000

---

## Bước 7 (tuỳ chọn) — Cloudflare Tunnel (cho nhân sự truy cập từ xa)

### Cài Cloudflare Tunnel

```bash
brew install cloudflare/cloudflare/cloudflared
```

### Chạy tunnel tạm thời (test nhanh, URL thay đổi mỗi lần)

```bash
cloudflared tunnel --url http://localhost:8000
```

Sẽ in ra URL dạng: `https://abc-def-ghi.trycloudflare.com`

### Tunnel cố định (URL không đổi — dùng cho production)

1. Đăng nhập Cloudflare:
   ```bash
   cloudflared tunnel login
   ```

2. Tạo tunnel:
   ```bash
   cloudflared tunnel create tts-app
   ```

3. Tạo file config `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: <TUNNEL_ID>
   credentials-file: /Users/admin/.cloudflared/<TUNNEL_ID>.json

   ingress:
     - hostname: tts.yourdomain.com
       service: http://localhost:8000
     - service: http_status:404
   ```

4. Tạo DNS record:
   ```bash
   cloudflared tunnel route dns tts-app tts.yourdomain.com
   ```

5. Chạy tunnel (có thể thêm vào launchd để tự start khi Mac khởi động):
   ```bash
   cloudflared tunnel run tts-app
   ```

6. Cập nhật Supabase **Site URL** thành `https://tts.yourdomain.com`

### Tự start tunnel khi Mac khởi động

```bash
sudo cloudflared service install
```

---

## Cấu trúc file

```
elevenlabs/
├── web/
│   ├── main.py              ← FastAPI backend
│   ├── requirements.txt
│   ├── .env                 ← Keys (không commit)
│   ├── .env.example
│   ├── SETUP.md             ← File này
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── forgot.html
│   │   ├── index.html
│   │   └── settings.html
│   └── static/              ← (để trống, dùng CDN Tailwind)
└── Mở Web TTS.command       ← Double-click để chạy
```
