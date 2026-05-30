from __future__ import annotations

import json
import os
import shlex
import sys
import subprocess
import threading
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from version import VERSION
from .server import build_server
from .store import DEFAULT_FEATURES, LicenseRecord, LicenseStore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "licenses.sqlite3"
REMOTE_SSH_HOST = os.environ.get("HEDRA_LICENSE_ADMIN_SSH_HOST", "").strip()
REMOTE_SSH_KEY = Path(os.environ.get("HEDRA_LICENSE_ADMIN_SSH_KEY", "~/.ssh/id_ed25519")).expanduser()
REMOTE_ROOT = os.environ.get("HEDRA_LICENSE_ADMIN_REMOTE_ROOT", "~/hedra-license-server").strip()
PUBLIC_VERIFY_BASE = os.environ.get("HEDRA_LICENSE_PUBLIC_BASE", "https://license.boxphonefarm.com.vn").strip()


class RemoteLicenseStore:
    def _ssh(self, remote_command: str) -> subprocess.CompletedProcess:
        if not REMOTE_SSH_HOST:
            raise RuntimeError("Thiếu HEDRA_LICENSE_ADMIN_SSH_HOST để quản lý remote qua SSH.")
        return subprocess.run(
            [
                "ssh",
                "-i",
                str(REMOTE_SSH_KEY),
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                REMOTE_SSH_HOST,
                remote_command,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _cli(self, args: list[str]) -> str:
        quoted = " ".join(shlex.quote(arg) for arg in args)
        result = self._ssh(f"cd {shlex.quote(REMOTE_ROOT)} && python3 -m license_server.cli {quoted}")
        return result.stdout.strip()

    def init_db(self) -> None:
        self._cli(["init"])

    def create_license(
        self,
        customer: str = "",
        features: list[str] | str | None = None,
        days: int = 365,
        max_devices: int = 0,
        notes: str = "",
    ) -> str:
        if isinstance(features, list):
            features_text = ",".join(features)
        else:
            features_text = str(features or ",".join(DEFAULT_FEATURES))
        return self._cli(
            [
                "create",
                "--customer",
                customer,
                "--features",
                features_text,
                "--days",
                str(days),
                "--max-devices",
                str(max_devices),
                "--notes",
                notes,
            ]
        ).splitlines()[-1].strip()

    def list_licenses(self) -> list[LicenseRecord]:
        payload = self._cli(["list"])
        rows = json.loads(payload or "[]")
        return [
            LicenseRecord(
                id=int(row.get("id") or 0),
                key_preview=str(row.get("key_preview") or ""),
                customer=str(row.get("customer") or ""),
                features=list(row.get("features") or []),
                status=str(row.get("status") or ""),
                expires_at=str(row.get("expires_at") or ""),
                max_devices=int(row.get("max_devices") or 0),
                created_at=str(row.get("created_at") or ""),
                revoked_at=str(row.get("revoked_at") or ""),
                notes=str(row.get("notes") or ""),
            )
            for row in rows
        ]

    def revoke_license(self, key_or_preview: str) -> bool:
        try:
            self._cli(["revoke", key_or_preview])
            return True
        except Exception:
            return False

    def health(self) -> str:
        request = urllib.request.Request(
            f"{PUBLIC_VERIFY_BASE}/health",
            headers={"User-Agent": f"HedraLicenseAdmin/{VERSION}"},
        )
        with urllib.request.urlopen(request, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8") or "{}")
        if not data.get("ok"):
            raise RuntimeError(str(data))
        return "OK"


class LicenseAdminWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._force_light_palette()
        self.store = RemoteLicenseStore()
        self.httpd = None
        self.server_thread = None
        self.setWindowTitle("Hedra License Admin")
        self.resize(1180, 760)
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet(
            """
            QWidget#root { background: #f5f5f7; color: #1d1d1f; }
            QWidget { color: #1d1d1f; background: transparent; }
            QFrame#sidebar {
                background: #fbfbfd; border: none; border-right: 1px solid #e5e5ea;
            }
            QFrame[class="card"] {
                background: #ffffff; border: 1px solid #e5e5ea; border-radius: 12px;
            }
            QLabel { color: #1d1d1f; background: transparent; border: none; }
            QLabel[class="brand"] { color: #1d1d1f; font-size: 15px; font-weight: 800; }
            QLabel[class="navitem"] {
                background: #0071e3; color: white; border-radius: 8px;
                padding: 8px 10px; font-size: 13px; font-weight: 700;
            }
            QLabel[class="title"] { color: #1d1d1f; font-size: 22px; font-weight: 800; }
            QLabel[class="section"] { color: #1d1d1f; font-size: 14px; font-weight: 800; }
            QLabel[class="muted"] { color: #6e6e73; font-size: 12px; }
            QLabel[class="badge"] {
                background: #f5f5f7; border: 1px solid #e5e5ea; border-radius: 8px;
                padding: 6px 10px; color: #6e6e73; font-size: 12px;
            }
            QLineEdit, QTextEdit, QSpinBox {
                background: #f5f5f7; border: 1px solid #d2d2d7; border-radius: 8px;
                padding: 7px 9px; font-size: 13px; color: #1d1d1f;
                selection-background-color: #0071e3; selection-color: #ffffff;
            }
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {
                border-color: #0071e3; background: #ffffff;
            }
            QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled {
                color: #86868b; background: #f2f2f7;
            }
            QCheckBox {
                color: #1d1d1f; spacing: 8px; font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px; height: 18px;
            }
            QPushButton {
                border: 1px solid #d2d2d7; border-radius: 8px; padding: 8px 12px;
                background: #ffffff; color: #1d1d1f; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #f5f5f7; }
            QPushButton[class="primary"] {
                background: #0071e3; color: white; border-color: #0071e3; font-weight: 700;
            }
            QPushButton[class="primary"]:hover { background: #0077ed; }
            QPushButton[class="danger"] {
                color: #c1121f; border-color: #f2c6cc; background: #fff5f6;
            }
            QTableWidget {
                background: #ffffff; color: #1d1d1f; border: 1px solid #e5e5ea; border-radius: 10px;
                gridline-color: #efeff4;
                selection-background-color: #dbeafe;
                selection-color: #1d1d1f;
            }
            QHeaderView::section {
                background: #f5f5f7; color: #1d1d1f; border: none; padding: 7px;
                font-weight: 700;
            }
            QTableCornerButton::section {
                background: #f5f5f7; border: none;
            }
            """
        )
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(214)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 18, 12, 18)
        side.setSpacing(14)
        brand = QLabel("Hedra Studio")
        brand.setProperty("class", "brand")
        side.addWidget(brand)
        nav = QLabel("License Admin")
        nav.setProperty("class", "navitem")
        side.addWidget(nav)
        side.addStretch()
        side_ver = QLabel(f"v{VERSION}\nRemote MacAir · Cloudflare")
        side_ver.setProperty("class", "muted")
        side.addWidget(side_ver)
        shell.addWidget(sidebar)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)
        shell.addWidget(content, 1)

        head = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("License Admin")
        title.setProperty("class", "title")
        subtitle = QLabel("Tạo Pro key và quản lý key trực tiếp trên MacAir public qua Cloudflare.")
        subtitle.setProperty("class", "muted")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        head.addLayout(title_col, 1)
        self.server_status = QLabel("Remote: chưa kiểm tra")
        self.server_status.setProperty("class", "badge")
        head.addWidget(self.server_status)
        self.start_server_btn = QPushButton("Kiểm tra remote")
        self.start_server_btn.clicked.connect(self.start_server)
        head.addWidget(self.start_server_btn)
        outer.addLayout(head)

        create_card = QFrame()
        create_card.setProperty("class", "card")
        create_outer = QVBoxLayout(create_card)
        create_outer.setContentsMargins(14, 14, 14, 14)
        create_outer.setSpacing(12)
        create_title = QLabel("Tạo Pro key")
        create_title.setProperty("class", "section")
        create_outer.addWidget(create_title)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.customer = QLineEdit()
        self.customer.setPlaceholderText("Tên khách / mã đơn")
        self.days = QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setValue(365)
        self.days.setSuffix(" ngày")
        self.max_devices = QSpinBox()
        self.max_devices.setRange(0, 99)
        self.max_devices.setValue(0)
        self.max_devices.setSpecialValueText("Không giới hạn")
        self.feature_chat = QCheckBox("Kịch bản")
        self.feature_chat.setChecked(True)
        self.feature_auto = QCheckBox("Auto Video")
        self.feature_auto.setChecked(True)
        self.feature_all = QCheckBox("All")
        self.feature_all.stateChanged.connect(self._sync_feature_all)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Ghi chú nội bộ")

        form.addWidget(QLabel("Khách"), 0, 0)
        form.addWidget(self.customer, 0, 1)
        form.addWidget(QLabel("Hạn dùng"), 0, 2)
        form.addWidget(self.days, 0, 3)
        form.addWidget(QLabel("Thiết bị"), 0, 4)
        form.addWidget(self.max_devices, 0, 5)
        form.addWidget(QLabel("Tính năng"), 1, 0)
        feature_row = QHBoxLayout()
        feature_row.addWidget(self.feature_chat)
        feature_row.addWidget(self.feature_auto)
        feature_row.addWidget(self.feature_all)
        feature_row.addStretch()
        form.addLayout(feature_row, 1, 1, 1, 3)
        form.addWidget(QLabel("Ghi chú"), 1, 4)
        form.addWidget(self.notes, 1, 5)

        self.create_btn = QPushButton("Tạo key")
        self.create_btn.setProperty("class", "primary")
        self.create_btn.clicked.connect(self.create_key)
        form.addWidget(self.create_btn, 0, 6, 2, 1)
        create_outer.addLayout(form)
        outer.addWidget(create_card)

        key_card = QFrame()
        key_card.setProperty("class", "card")
        key_lay = QVBoxLayout(key_card)
        key_lay.setContentsMargins(14, 14, 14, 14)
        key_lay.setSpacing(8)
        key_head = QHBoxLayout()
        key_title = QLabel("Key vừa tạo")
        key_title.setProperty("class", "section")
        key_head.addWidget(key_title)
        key_head.addStretch()
        copy_btn = QPushButton("Copy key")
        copy_btn.clicked.connect(self.copy_last_key)
        key_head.addWidget(copy_btn)
        key_lay.addLayout(key_head)
        self.last_key = QTextEdit()
        self.last_key.setPlaceholderText("Key plaintext chỉ hiện ở đây một lần sau khi tạo.")
        self.last_key.setFixedHeight(64)
        key_lay.addWidget(self.last_key)
        outer.addWidget(key_card)

        tools = QHBoxLayout()
        list_title = QLabel("Danh sách key")
        list_title.setProperty("class", "section")
        tools.addWidget(list_title)
        tools.addSpacing(6)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        tools.addWidget(self.refresh_btn)
        self.revoke_btn = QPushButton("Revoke key đang chọn")
        self.revoke_btn.setProperty("class", "danger")
        self.revoke_btn.clicked.connect(self.revoke_selected)
        tools.addWidget(self.revoke_btn)
        tools.addStretch()
        self.db_label = QLabel(f"{REMOTE_SSH_HOST}:{REMOTE_ROOT}/data/licenses.sqlite3")
        self.db_label.setProperty("class", "muted")
        tools.addWidget(self.db_label)
        outer.addLayout(tools)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Key", "Khách", "Features", "Status", "Hết hạn", "Thiết bị", "Tạo lúc", "Ghi chú"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        outer.addWidget(self.table, 1)

        self.setCentralWidget(root)

    def _force_light_palette(self) -> None:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#f5f5f7"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#1d1d1f"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f5f5f7"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#1d1d1f"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1d1d1f"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#0071e3"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        QApplication.setPalette(palette)

    def _sync_feature_all(self) -> None:
        enabled = not self.feature_all.isChecked()
        self.feature_chat.setEnabled(enabled)
        self.feature_auto.setEnabled(enabled)

    def selected_features(self) -> list[str]:
        if self.feature_all.isChecked():
            return ["all"]
        features = []
        if self.feature_chat.isChecked():
            features.append("chat_script")
        if self.feature_auto.isChecked():
            features.append("auto_video")
        return features or DEFAULT_FEATURES[:]

    def create_key(self) -> None:
        try:
            key = self.store.create_license(
                customer=self.customer.text().strip(),
                features=self.selected_features(),
                days=self.days.value(),
                max_devices=self.max_devices.value(),
                notes=self.notes.text().strip(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Không tạo được key", f"Không gọi được MacAir qua SSH:\n{exc}")
            return
        self.last_key.setPlainText(key)
        QApplication.clipboard().setText(key)
        self.refresh()
        QMessageBox.information(self, "Đã tạo key", "Key đã được tạo trên MacAir và copy vào clipboard.")

    def copy_last_key(self) -> None:
        key = self.last_key.toPlainText().strip()
        if not key:
            QMessageBox.information(self, "Chưa có key", "Tạo key trước rồi copy.")
            return
        QApplication.clipboard().setText(key)

    def refresh(self) -> None:
        try:
            rows = self.store.list_licenses()
        except Exception as exc:
            QMessageBox.warning(self, "Không tải được danh sách key", f"Không gọi được MacAir qua SSH:\n{exc}")
            rows = []
        self.table.setRowCount(len(rows))
        for r, record in enumerate(rows):
            self._set_row(r, record)
        self.table.resizeColumnsToContents()

    def _set_row(self, row: int, record: LicenseRecord) -> None:
        values = [
            str(record.id),
            record.key_preview,
            record.customer,
            ", ".join(record.features),
            record.status,
            record.expires_at,
            str(record.max_devices or "Không giới hạn"),
            record.created_at,
            record.notes,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, record.key_preview)
            self.table.setItem(row, col, item)

    def revoke_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Chưa chọn key", "Chọn một dòng key để revoke.")
            return
        preview = self.table.item(row, 1).text()
        ret = QMessageBox.question(
            self,
            "Revoke key",
            f"Revoke key {preview}?\nKey này sẽ không verify được nữa.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        if not self.store.revoke_license(preview):
            QMessageBox.warning(self, "Không revoke được", "Không tìm thấy key.")
            return
        self.refresh()

    def start_server(self) -> None:
        try:
            self.store.health()
        except Exception as exc:
            QMessageBox.warning(self, "Remote chưa sẵn sàng", f"Không gọi được license domain:\n{exc}")
            return
        endpoint = f"{PUBLIC_VERIFY_BASE}/v1/licenses/verify"
        QApplication.clipboard().setText(f"HEDRA_LICENSE_VERIFY_URL={endpoint}")
        self.server_status.setText("Remote: OK")
        QMessageBox.information(self, "Remote OK", f"License server public đang chạy:\n{endpoint}")

    def closeEvent(self, event) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Arial", 13))
    win = LicenseAdminWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
