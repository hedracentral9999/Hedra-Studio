from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from license_server.server import build_server
from license_server.store import LicenseStore


class LicenseServerTests(unittest.TestCase):
    def test_create_verify_and_revoke_license(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            store = LicenseStore(Path(tmp) / "licenses.sqlite3")
            key = store.create_license(customer="Customer A", features="chat_script,auto_video", days=30)

            ok = store.verify(key=key, feature="auto_video", device_id="mac-1", platform="darwin", app_version="1.0")
            self.assertTrue(ok["valid"])
            self.assertEqual(set(ok["features"]), {"chat_script", "auto_video"})
            self.assertEqual(ok["customer"], "Customer A")

            self.assertTrue(store.revoke_license(key))
            revoked = store.verify(key=key, feature="auto_video")
            self.assertFalse(revoked["valid"])
            self.assertIn("thu hồi", revoked["message"])

    def test_feature_mismatch_keeps_key_valid_but_reports_features(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            store = LicenseStore(Path(tmp) / "licenses.sqlite3")
            key = store.create_license(features="chat_script", days=30)

            result = store.verify(key=key, feature="auto_video")

            self.assertTrue(result["valid"])
            self.assertEqual(result["features"], ["chat_script"])
            self.assertIn("chưa mở tính năng auto_video", result["message"])

    def test_device_limit_blocks_new_device(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            store = LicenseStore(Path(tmp) / "licenses.sqlite3")
            key = store.create_license(features="all", days=30, max_devices=1)

            self.assertTrue(store.verify(key=key, feature="auto_video", device_id="mac-1")["valid"])
            self.assertTrue(store.verify(key=key, feature="auto_video", device_id="mac-1")["valid"])
            blocked = store.verify(key=key, feature="auto_video", device_id="mac-2")
            self.assertFalse(blocked["valid"])
            self.assertIn("giới hạn thiết bị", blocked["message"])

    def test_http_verify_endpoint_matches_desktop_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            db = Path(tmp) / "licenses.sqlite3"
            store = LicenseStore(db)
            key = store.create_license(features="all", days=30)
            httpd = build_server(db, "127.0.0.1", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                body = json.dumps({
                    "key": key,
                    "feature": "auto_video",
                    "app": "hedra-studio",
                    "version": "1.8.68",
                    "device_id": "mac-1",
                    "platform": "darwin",
                }).encode("utf-8")
                req = Request(
                    f"http://{host}:{port}/v1/licenses/verify",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=5) as res:
                    payload = json.loads(res.read().decode("utf-8"))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

            self.assertTrue(payload["valid"])
            self.assertTrue(payload["success"])
            self.assertEqual(payload["features"], ["all"])

    def test_admin_web_requires_token_and_can_create_key(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            db = Path(tmp) / "licenses.sqlite3"
            httpd = build_server(db, "127.0.0.1", 0, admin_token="admin-secret")
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                blocked = Request(f"http://{host}:{port}/v1/admin/licenses")
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(blocked, timeout=5)
                self.assertEqual(ctx.exception.code, 403)

                create_body = json.dumps({
                    "customer": "Web Admin",
                    "features": ["auto_video"],
                    "days": 30,
                    "max_devices": 0,
                    "notes": "test",
                }).encode("utf-8")
                create_req = Request(
                    f"http://{host}:{port}/v1/admin/licenses/create",
                    data=create_body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer admin-secret",
                    },
                    method="POST",
                )
                with urlopen(create_req, timeout=5) as res:
                    created = json.loads(res.read().decode("utf-8"))

                verify_body = json.dumps({
                    "key": created["key"],
                    "feature": "auto_video",
                    "device_id": "mac-1",
                }).encode("utf-8")
                verify_req = Request(
                    f"http://{host}:{port}/v1/licenses/verify",
                    data=verify_body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(verify_req, timeout=5) as res:
                    verified = json.loads(res.read().decode("utf-8"))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

            self.assertTrue(created["ok"])
            self.assertTrue(created["key"].startswith("HEDRA-PRO-"))
            self.assertTrue(verified["valid"])
            self.assertEqual(verified["features"], ["auto_video"])

    def test_admin_app_store_uses_http_admin_api(self) -> None:
        try:
            from license_server.admin_app import HttpLicenseStore
        except ModuleNotFoundError as exc:
            if exc.name == "PyQt6":
                self.skipTest("PyQt6 is not installed in this Python environment")
            raise
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            db = Path(tmp) / "licenses.sqlite3"
            httpd = build_server(db, "127.0.0.1", 0, admin_token="admin-secret")
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                store = HttpLicenseStore(f"http://{host}:{port}", "admin-secret")
                self.assertEqual(store.health(), "OK")
                key = store.create_license(customer="Desktop Admin", features=["all"], days=30)
                rows = store.list_licenses()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

            self.assertTrue(key.startswith("HEDRA-PRO-"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].customer, "Desktop Admin")
            self.assertEqual(rows[0].features, ["all"])


if __name__ == "__main__":
    unittest.main()
