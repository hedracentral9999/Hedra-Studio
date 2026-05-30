from __future__ import annotations

import argparse
import json

from .store import DEFAULT_FEATURES, LicenseStore

DEFAULT_DB_PATH = "data/licenses.sqlite3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Hedra Studio Pro license keys.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite database path.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Initialize the license database.")

    create = sub.add_parser("create", help="Create a new Pro key.")
    create.add_argument("--customer", default="", help="Customer name/id.")
    create.add_argument("--features", default=",".join(DEFAULT_FEATURES), help="Comma-separated features or all.")
    create.add_argument("--days", type=int, default=365, help="Days until expiry. Use 0 with --expires-at for fixed expiry.")
    create.add_argument("--expires-at", default="", help="ISO expiry timestamp, e.g. 2026-12-31T23:59:59Z.")
    create.add_argument("--max-devices", type=int, default=0, help="0 means unlimited devices.")
    create.add_argument("--notes", default="", help="Internal note.")

    sub.add_parser("list", help="List license records without plaintext keys.")

    revoke = sub.add_parser("revoke", help="Revoke a key by full key or preview.")
    revoke.add_argument("key", help="Full key or key preview.")

    args = parser.parse_args(argv)
    store = LicenseStore(args.db)

    if args.cmd == "init":
        store.init_db()
        print(f"Initialized {args.db}")
        return 0

    if args.cmd == "create":
        key = store.create_license(
            customer=args.customer,
            features=args.features,
            expires_at=args.expires_at,
            days=args.days,
            max_devices=args.max_devices,
            notes=args.notes,
        )
        print(key)
        return 0

    if args.cmd == "list":
        rows = [record.__dict__ for record in store.list_licenses()]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "revoke":
        if not store.revoke_license(args.key):
            print("Không tìm thấy key.")
            return 1
        print("Đã revoke key.")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
