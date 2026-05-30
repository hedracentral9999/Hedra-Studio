from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import string
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_FEATURES = ["chat_script", "auto_video"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


def normalize_key(key: str) -> str:
    return "".join(ch for ch in str(key or "").upper() if ch.isalnum())


def hash_key(key: str) -> str:
    normalized = normalize_key(key)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def key_preview(key: str) -> str:
    normalized = normalize_key(key)
    if len(normalized) <= 8:
        return normalized
    return f"{normalized[:8]}...{normalized[-4:]}"


def generate_key(prefix: str = "HEDRA-PRO", groups: int = 4, group_len: int = 4) -> str:
    alphabet = string.ascii_uppercase + string.digits
    chunks = ["".join(secrets.choice(alphabet) for _ in range(group_len)) for _ in range(groups)]
    return "-".join([prefix, *chunks])


def parse_time(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def normalize_features(features: list[str] | str | None) -> list[str]:
    if isinstance(features, str):
        features = [item.strip() for item in features.split(",")]
    if not isinstance(features, list):
        features = DEFAULT_FEATURES
    out = []
    for item in features:
        text = str(item or "").strip().lower()
        if text and text not in out:
            out.append(text)
    return out or DEFAULT_FEATURES[:]


@dataclass(frozen=True)
class LicenseRecord:
    id: int
    key_preview: str
    customer: str
    features: list[str]
    status: str
    expires_at: str
    max_devices: int
    created_at: str
    revoked_at: str
    notes: str


class LicenseStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self):
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_preview TEXT NOT NULL,
                    customer TEXT NOT NULL DEFAULT '',
                    features_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at TEXT NOT NULL DEFAULT '',
                    max_devices INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT '',
                    app_version TEXT NOT NULL DEFAULT '',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE(license_id, device_id),
                    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_licenses_status ON licenses(status);
                CREATE INDEX IF NOT EXISTS idx_activations_license ON activations(license_id);
                """
            )

    def create_license(
        self,
        *,
        customer: str = "",
        features: list[str] | str | None = None,
        expires_at: str = "",
        days: int | None = 365,
        max_devices: int = 0,
        notes: str = "",
    ) -> str:
        self.init_db()
        key = generate_key()
        expiry = str(expires_at or "").strip()
        if not expiry and days:
            expiry = (now_utc() + timedelta(days=int(days))).isoformat()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO licenses
                    (key_hash, key_preview, customer, features_json, status, expires_at, max_devices, created_at, notes)
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    hash_key(key),
                    key_preview(key),
                    str(customer or "").strip(),
                    json.dumps(normalize_features(features), ensure_ascii=False),
                    expiry,
                    int(max_devices or 0),
                    iso_now(),
                    str(notes or "").strip(),
                ),
            )
        return key

    def revoke_license(self, key_or_preview: str) -> bool:
        self.init_db()
        target_hash = hash_key(key_or_preview)
        target_preview = str(key_or_preview or "").strip()
        with self.connection() as conn:
            cur = conn.execute(
                """
                UPDATE licenses
                SET status = 'revoked', revoked_at = ?
                WHERE key_hash = ? OR key_preview = ?
                """,
                (iso_now(), target_hash, target_preview),
            )
            return cur.rowcount > 0

    def list_licenses(self) -> list[LicenseRecord]:
        self.init_db()
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, key_preview, customer, features_json, status, expires_at,
                       max_devices, created_at, revoked_at, notes
                FROM licenses
                ORDER BY id DESC
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def verify(
        self,
        *,
        key: str,
        feature: str = "",
        device_id: str = "",
        platform: str = "",
        app_version: str = "",
    ) -> dict:
        self.init_db()
        requested = str(feature or "").strip().lower()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM licenses WHERE key_hash = ?", (hash_key(key),)).fetchone()
            if not row:
                return self._invalid("License không hợp lệ.")
            record = self._row_to_record(row)
            if record.status != "active":
                return self._invalid("License đã bị thu hồi.", record)
            expires = parse_time(record.expires_at)
            if expires and now_utc() > expires:
                return self._invalid("License đã hết hạn.", record)
            if record.max_devices > 0:
                allowed = self._record_activation(conn, record.id, record.max_devices, device_id, platform, app_version)
                if not allowed:
                    return self._invalid("License đã vượt giới hạn thiết bị.", record)
            elif device_id:
                self._upsert_activation(conn, record.id, device_id, platform, app_version)

        features = record.features
        has_feature = "all" in features or not requested or requested in features
        message = "License hợp lệ." if has_feature else f"License hợp lệ nhưng chưa mở tính năng {requested}."
        return {
            "valid": True,
            "success": True,
            "features": features,
            "expires_at": record.expires_at,
            "customer": record.customer,
            "message": message,
        }

    def _record_activation(
        self,
        conn: sqlite3.Connection,
        license_id: int,
        max_devices: int,
        device_id: str,
        platform: str,
        app_version: str,
    ) -> bool:
        device = str(device_id or "").strip()
        if not device:
            return False
        existing = conn.execute(
            "SELECT id FROM activations WHERE license_id = ? AND device_id = ?",
            (license_id, device),
        ).fetchone()
        if existing:
            self._upsert_activation(conn, license_id, device, platform, app_version)
            return True
        count = int(conn.execute("SELECT COUNT(*) FROM activations WHERE license_id = ?", (license_id,)).fetchone()[0])
        if count >= max_devices:
            return False
        self._upsert_activation(conn, license_id, device, platform, app_version)
        return True

    def _upsert_activation(
        self,
        conn: sqlite3.Connection,
        license_id: int,
        device_id: str,
        platform: str,
        app_version: str,
    ) -> None:
        now = iso_now()
        conn.execute(
            """
            INSERT INTO activations (license_id, device_id, platform, app_version, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(license_id, device_id)
            DO UPDATE SET platform = excluded.platform,
                          app_version = excluded.app_version,
                          last_seen_at = excluded.last_seen_at
            """,
            (license_id, str(device_id or "").strip(), str(platform or ""), str(app_version or ""), now, now),
        )

    def _row_to_record(self, row: sqlite3.Row) -> LicenseRecord:
        try:
            features = json.loads(row["features_json"])
        except Exception:
            features = []
        return LicenseRecord(
            id=int(row["id"]),
            key_preview=str(row["key_preview"] or ""),
            customer=str(row["customer"] or ""),
            features=normalize_features(features),
            status=str(row["status"] or "active"),
            expires_at=str(row["expires_at"] or ""),
            max_devices=int(row["max_devices"] or 0),
            created_at=str(row["created_at"] or ""),
            revoked_at=str(row["revoked_at"] or ""),
            notes=str(row["notes"] or ""),
        )

    def _invalid(self, message: str, record: LicenseRecord | None = None) -> dict:
        return {
            "valid": False,
            "success": False,
            "features": record.features if record else [],
            "expires_at": record.expires_at if record else "",
            "customer": record.customer if record else "",
            "message": message,
        }
