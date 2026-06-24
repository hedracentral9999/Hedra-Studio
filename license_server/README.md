# Hedra Studio License Server MVP

Server nhỏ để tạo và verify Pro key cho app desktop. Bản này dùng Python stdlib + SQLite, không cần secret trong app.

## Chạy local

```bash
python3 -m license_server.cli init
python3 -m license_server.cli create --customer "Khach A" --features chat_script,auto_video --days 365
python3 -m license_server.server --host 127.0.0.1 --port 8088
```

Cho app trỏ vào server local:

```bash
HEDRA_LICENSE_VERIFY_URL=http://127.0.0.1:8088/v1/licenses/verify python3 tts_app.py
```

## Quản lý key

```bash
python3 -m license_server.cli list
python3 -m license_server.cli revoke HEDRAPRO...ABCD
```

CLI chỉ in key plaintext một lần lúc tạo. Database chỉ lưu SHA-256 hash và preview.

## Verify API

`POST /v1/licenses/verify`

```json
{
  "key": "HEDRA-PRO-XXXX-XXXX-XXXX-XXXX",
  "feature": "auto_video",
  "app": "hedra-studio",
  "version": "1.8.68",
  "device_id": "device-id",
  "platform": "darwin"
}
```

Response hợp lệ:

```json
{
  "valid": true,
  "success": true,
  "features": ["chat_script", "auto_video"],
  "expires_at": "2027-05-29T12:00:00+00:00",
  "customer": "Khach A",
  "message": "License hợp lệ."
}
```

Features đang dùng trong app:

- `chat_script`
- `auto_video`
- `all`

## Deploy tối giản

- Chạy sau HTTPS reverse proxy như Caddy/Nginx/Cloudflare Tunnel.
- Set app endpoint production bằng `HEDRA_LICENSE_VERIFY_URL`.
- Backup file SQLite định kỳ.
