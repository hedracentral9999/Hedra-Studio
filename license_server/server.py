from __future__ import annotations

import argparse
import html
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .store import DEFAULT_FEATURES, LicenseStore


PUBLIC_VERIFY_BASE = "https://license.boxphonefarm.com.vn"


class LicenseRequestHandler(BaseHTTPRequestHandler):
    store: LicenseStore
    admin_token: str = ""

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/health":
            self._send_json({"ok": True, "service": "hedra-license-server"})
            return
        if path == "/admin":
            self._send_html(self._admin_page(authenticated=self._is_admin_authorized()))
            return
        if path == "/v1/admin/licenses":
            if not self._require_admin():
                return
            rows = [record.__dict__ for record in self.store.list_licenses()]
            self._send_json({"ok": True, "licenses": rows})
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/v1/licenses/verify":
            self._handle_verify()
            return
        if path == "/admin/login":
            self._handle_admin_login()
            return
        if path == "/v1/admin/licenses/create":
            if not self._require_admin():
                return
            self._handle_admin_create()
            return
        if path == "/v1/admin/licenses/revoke":
            if not self._require_admin():
                return
            self._handle_admin_revoke()
            return
        self._send_json({"error": "not_found"}, status=404)

    def _handle_verify(self) -> None:
        try:
            payload = self._read_json()
        except Exception:
            self._send_json({"valid": False, "success": False, "message": "JSON không hợp lệ."}, status=400)
            return
        result = self.store.verify(
            key=str(payload.get("key") or ""),
            feature=str(payload.get("feature") or ""),
            device_id=str(payload.get("device_id") or ""),
            platform=str(payload.get("platform") or ""),
            app_version=str(payload.get("version") or ""),
        )
        self._send_json(result)

    def _handle_admin_login(self) -> None:
        token = self._configured_admin_token()
        if not token:
            self._send_html(self._admin_page(False, "Admin web chưa cấu hình token."), status=503)
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0")).decode("utf-8")
        if "application/json" in self.headers.get("Content-Type", ""):
            try:
                submitted = str(json.loads(raw or "{}").get("token") or "")
            except Exception:
                submitted = ""
        else:
            submitted = str(parse_qs(raw).get("token", [""])[0] or "")
        if not hmac.compare_digest(submitted, token):
            self._send_html(self._admin_page(False, "Sai admin key."), status=403)
            return
        body = self._admin_page(True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Set-Cookie", f"hedra_admin={token}; HttpOnly; Secure; SameSite=Strict; Path=/")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_admin_create(self) -> None:
        try:
            payload = self._read_json()
            key = self.store.create_license(
                customer=str(payload.get("customer") or ""),
                features=payload.get("features") or DEFAULT_FEATURES,
                days=int(payload.get("days") or 0),
                max_devices=int(payload.get("max_devices") or 0),
                notes=str(payload.get("notes") or ""),
            )
        except Exception as exc:
            self._send_json({"ok": False, "message": f"Không tạo được key: {exc}"}, status=400)
            return
        self._send_json({"ok": True, "key": key})

    def _handle_admin_revoke(self) -> None:
        try:
            payload = self._read_json()
            target = str(payload.get("key") or payload.get("key_preview") or "")
        except Exception:
            target = ""
        if not target:
            self._send_json({"ok": False, "message": "Thiếu key/key_preview."}, status=400)
            return
        if not self.store.revoke_license(target):
            self._send_json({"ok": False, "message": "Không tìm thấy key."}, status=404)
            return
        self._send_json({"ok": True})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _configured_admin_token(self) -> str:
        return self.admin_token or os.environ.get("HEDRA_LICENSE_ADMIN_TOKEN", "").strip()

    def _is_admin_authorized(self) -> bool:
        token = self._configured_admin_token()
        if not token:
            return False
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), token):
            return True
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "hedra_admin" and hmac.compare_digest(value, token):
                return True
        return False

    def _require_admin(self) -> bool:
        if not self._configured_admin_token():
            self._send_json({"ok": False, "message": "Admin web chưa cấu hình token."}, status=503)
            return False
        if not self._is_admin_authorized():
            self._send_json({"ok": False, "message": "Chưa đăng nhập admin."}, status=403)
            return False
        return True

    def _admin_page(self, authenticated: bool, message: str = "") -> str:
        msg = html.escape(message)
        if not authenticated:
            return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hedra License Admin</title>{ADMIN_CSS}</head>
<body><main class="login"><h1>Hedra License Admin</h1><p>Đăng nhập để tạo, xem và revoke Pro key.</p>
{f'<div class="alert">{msg}</div>' if msg else ''}
<form method="post" action="/admin/login"><label>Admin key</label><input name="token" type="password" autofocus>
<button type="submit">Đăng nhập</button></form></main></body></html>"""
        return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hedra License Admin</title>{ADMIN_CSS}</head>
<body><main class="app"><header><div><h1>Hedra License Admin</h1><p>Public verify: {PUBLIC_VERIFY_BASE}</p></div><button onclick="loadKeys()">Refresh</button></header>
<section class="card"><h2>Tạo Pro key</h2><div class="grid">
<label>Khách<input id="customer" placeholder="Tên khách / mã đơn"></label>
<label>Hạn dùng<input id="days" type="number" value="365" min="0"></label>
<label>Thiết bị<input id="max_devices" type="number" value="0" min="0"></label>
<label>Ghi chú<input id="notes" placeholder="Ghi chú nội bộ"></label>
</div><div class="checks"><label><input id="chat_script" type="checkbox" checked> Kịch bản</label><label><input id="auto_video" type="checkbox" checked> Auto Video</label><label><input id="all" type="checkbox"> All</label></div>
<button class="primary" onclick="createKey()">Tạo key</button><textarea id="last_key" readonly placeholder="Key plaintext chỉ hiện sau khi tạo."></textarea></section>
<section class="card"><h2>Danh sách key</h2><div id="status"></div><table><thead><tr><th>ID</th><th>Key</th><th>Khách</th><th>Features</th><th>Status</th><th>Hết hạn</th><th>Thiết bị</th><th>Ghi chú</th><th></th></tr></thead><tbody id="rows"></tbody></table></section>
</main>{ADMIN_JS}</body></html>"""

    def log_message(self, fmt: str, *args) -> None:
        print(f"[license-server] {self.address_string()} - {fmt % args}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_body: str, status: int = 200) -> None:
        body = html_body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_server(
    db_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8088,
    admin_token: str = "",
) -> ThreadingHTTPServer:
    store = LicenseStore(db_path)
    store.init_db()

    class Handler(LicenseRequestHandler):
        pass

    Handler.store = store
    Handler.admin_token = admin_token
    return ThreadingHTTPServer((host, int(port)), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Hedra Studio license verify server.")
    parser.add_argument("--db", default="data/licenses.sqlite3", help="SQLite database path.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8088, help="Bind port.")
    parser.add_argument("--admin-token", default="", help="Admin web token. Prefer HEDRA_LICENSE_ADMIN_TOKEN env.")
    args = parser.parse_args(argv)

    httpd = build_server(args.db, args.host, args.port, args.admin_token)
    print(f"License server listening on http://{args.host}:{args.port}")
    print("Verify endpoint: POST /v1/licenses/verify")
    print("Admin web: GET /admin")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping license server.")
    finally:
        httpd.server_close()
    return 0


ADMIN_CSS = """<style>
:root{font-family:Arial,-apple-system,BlinkMacSystemFont,sans-serif;color:#1d1d1f;background:#f5f5f7}
body{margin:0;background:#f5f5f7}.login,.app{max-width:1180px;margin:0 auto;padding:32px}
h1{font-size:28px;margin:0 0 8px}h2{font-size:17px;margin:0 0 14px}p{color:#6e6e73;margin:0 0 18px}
.login{max-width:420px}.card,.login{background:#fff;border:1px solid #e5e5ea;border-radius:14px;margin-top:18px;padding:18px}
label{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:700;color:#424245}
input,textarea{border:1px solid #d2d2d7;border-radius:9px;padding:10px;font-size:14px;background:#fbfbfd;color:#1d1d1f}
textarea{width:100%;height:64px;margin-top:12px;box-sizing:border-box}
button{border:1px solid #d2d2d7;border-radius:9px;background:#fff;color:#1d1d1f;padding:10px 14px;font-weight:700;cursor:pointer}
button.primary{background:#0071e3;border-color:#0071e3;color:#fff;margin-top:12px}button.danger{color:#c1121f;background:#fff5f6;border-color:#f2c6cc}
header{display:flex;align-items:center;justify-content:space-between;gap:16px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.checks{display:flex;gap:18px;margin-top:12px}.checks label{flex-direction:row;align-items:center;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #efeff4;text-align:left;padding:9px;vertical-align:top}th{background:#f5f5f7}
.alert,#status{background:#fff5f6;border:1px solid #f2c6cc;color:#9f1239;border-radius:9px;padding:10px;margin:10px 0}
#status.ok{background:#ecfdf5;border-color:#bbf7d0;color:#166534}
@media(max-width:760px){.grid{grid-template-columns:1fr}.app,.login{padding:16px}table{font-size:12px}}
</style>"""

ADMIN_JS = """<script>
function features(){
  if(document.getElementById('all').checked) return ['all'];
  const out=[]; if(document.getElementById('chat_script').checked) out.push('chat_script');
  if(document.getElementById('auto_video').checked) out.push('auto_video');
  return out.length ? out : ['chat_script','auto_video'];
}
function setStatus(text, ok=false){const el=document.getElementById('status'); el.textContent=text||''; el.className=ok?'ok':'';}
async function api(url, body){
  const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  const data=await res.json(); if(!res.ok||data.ok===false) throw new Error(data.message||res.statusText); return data;
}
async function loadKeys(){
  try{
    const res=await fetch('/v1/admin/licenses'); const data=await res.json(); if(!res.ok||!data.ok) throw new Error(data.message||res.statusText);
    const rows=document.getElementById('rows'); rows.innerHTML='';
    for(const r of data.licenses){
      const tr=document.createElement('tr');
      const vals=[r.id,r.key_preview,r.customer,(r.features||[]).join(', '),r.status,r.expires_at,r.max_devices||'Không giới hạn',r.notes];
      vals.forEach(v=>{const td=document.createElement('td');td.textContent=v||'';tr.appendChild(td)});
      const td=document.createElement('td'); const b=document.createElement('button'); b.textContent='Revoke'; b.className='danger';
      b.onclick=()=>revokeKey(r.key_preview); td.appendChild(b); tr.appendChild(td); rows.appendChild(tr);
    }
    setStatus('Đã tải '+data.licenses.length+' key', true);
  }catch(e){setStatus(e.message)}
}
async function createKey(){
  try{
    const data=await api('/v1/admin/licenses/create',{customer:customer.value,days:Number(days.value||0),max_devices:Number(max_devices.value||0),notes:notes.value,features:features()});
    last_key.value=data.key; await navigator.clipboard.writeText(data.key).catch(()=>{}); setStatus('Đã tạo key và copy vào clipboard', true); loadKeys();
  }catch(e){setStatus(e.message)}
}
async function revokeKey(key){
  if(!confirm('Revoke '+key+'?')) return;
  try{await api('/v1/admin/licenses/revoke',{key_preview:key}); setStatus('Đã revoke '+key, true); loadKeys();}catch(e){setStatus(e.message)}
}
loadKeys();
</script>"""


if __name__ == "__main__":
    raise SystemExit(main())
