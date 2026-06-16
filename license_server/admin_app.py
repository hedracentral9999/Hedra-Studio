from __future__ import annotations

import json
import os
import sys
import urllib.error
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
from .store import DEFAULT_FEATURES, LicenseRecord


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_VERIFY_BASE = os.environ.get("HEDRA_LICENSE_PUBLIC_BASE", "https://license.boxphonefarm.com.vn").strip()
ADMIN_BASE = os.environ.get("HEDRA_LICENSE_ADMIN_BASE", PUBLIC_VERIFY_BASE).strip().rstrip("/")
ADMIN_TOKEN_ENV = os.environ.get("HEDRA_LICENSE_ADMIN_TOKEN", "").strip()
ADMIN_CONFIG_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Hedra Studio"
    / "license-admin.json"
)


def load_admin_config() -> dict:
    try:
        return json.loads(ADMIN_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_admin_config(config: dict) -> None:
    ADMIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


class HttpLicenseStore:
    def __init__(self, base_url: str = "", token: str = "") -> None:
        config = load_admin_config()
        self.base_url = (base_url or os.environ.get("HEDRA_LICENSE_ADMIN_BASE") or config.get("base_url") or ADMIN_BASE).strip().rstrip("/")
        self.token = (token or ADMIN_TOKEN_ENV or config.get("token") or "").strip()

    def configure(self, base_url: str, token: str) -> None:
        self.base_url = (base_url or PUBLIC_VERIFY_BASE).strip().rstrip("/")
        self.token = str(token or "").strip()
        save_admin_config({"base_url": self.base_url, "token": self.token})

    def _request(self, method: str, path: str, payload: dict | None = None, *, admin: bool = True) -> dict:
        if admin and not self.token:
            raise RuntimeError(
                "Thiếu Admin token. Nhập token ở ô cấu hình rồi bấm Lưu cấu hình."
            )
        data = None
        headers = {"User-Agent": f"HedraLicenseAdmin/{VERSION}"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if admin:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as res:
                return json.loads(res.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(body).get("message") or body
            except Exception:
                message = body or exc.reason
            raise RuntimeError(f"HTTP {exc.code}: {message}") from exc

    def init_db(self) -> None:
        self.health()

    def create_license(
        self,
        customer: str = "",
        features: list[str] | str | None = None,
        days: int = 365,
        max_devices: int = 0,
        notes: str = "",
    ) -> str:
        payload = {
            "customer": customer,
            "features": features or DEFAULT_FEATURES,
            "days": days,
            "max_devices": max_devices,
            "notes": notes,
        }
        data = self._request("POST", "/v1/admin/licenses/create", payload)
        key = str(data.get("key") or "").strip()
        if not key:
            raise RuntimeError(str(data.get("message") or "Server không trả về key."))
        return key

    def list_licenses(self) -> list[LicenseRecord]:
        payload = self._request("GET", "/v1/admin/licenses")
        rows = payload.get("licenses") or []
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
            data = self._request("POST", "/v1/admin/licenses/revoke", {"key_preview": key_or_preview})
            return bool(data.get("ok"))
        except Exception:
            return False

    def health(self) -> str:
        data = self._request("GET", "/health", admin=False)
        if not data.get("ok"):
            raise RuntimeError(str(data))
        return "OK"


class LicenseAdminWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._force_light_palette()
        self.store = HttpLicenseStore()
        self.httpd = None
        self.server_thread = None
        self.setWindowTitle("Hedra License Admin")
        self.resize(1180, 760)
        self._build()
        if self.store.token:
            self.refresh()
        else:
            self.server_status.setText("Remote: cần Admin token")

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
        side_ver = QLabel(f"v{VERSION}\nCloudflare Admin API")
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
        subtitle = QLabel("Tạo Pro key và quản lý key qua license admin API public, không phụ thuộc SSH.")
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

        config_card = QFrame()
        config_card.setProperty("class", "card")
        config_outer = QVBoxLayout(config_card)
        config_outer.setContentsMargins(14, 14, 14, 14)
        config_outer.setSpacing(10)
        config_title = QLabel("Cấu hình admin API")
        config_title.setProperty("class", "section")
        config_outer.addWidget(config_title)
        config_form = QGridLayout()
        config_form.setHorizontalSpacing(10)
        config_form.setVerticalSpacing(10)
        self.admin_base = QLineEdit(self.store.base_url)
        self.admin_base.setPlaceholderText("https://license.boxphonefarm.com.vn")
        self.admin_token = QLineEdit(self.store.token)
        self.admin_token.setPlaceholderText("Admin token")
        self.admin_token.setEchoMode(QLineEdit.EchoMode.Password)
        save_config_btn = QPushButton("Lưu cấu hình")
        save_config_btn.clicked.connect(self.save_admin_config)
        config_form.addWidget(QLabel("Base URL"), 0, 0)
        config_form.addWidget(self.admin_base, 0, 1, 1, 3)
        config_form.addWidget(QLabel("Admin token"), 0, 4)
        config_form.addWidget(self.admin_token, 0, 5)
        config_form.addWidget(save_config_btn, 0, 6)
        config_outer.addLayout(config_form)
        outer.addWidget(config_card)

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
        self.db_label = QLabel(f"{self.store.base_url}/v1/admin/licenses")
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

    def save_admin_config(self) -> None:
        self.store.configure(self.admin_base.text(), self.admin_token.text())
        self.db_label.setText(f"{self.store.base_url}/v1/admin/licenses")
        self.server_status.setText("Remote: đã lưu cấu hình")
        self.start_server()

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
            QMessageBox.warning(self, "Không tạo được key", f"Không gọi được admin API:\n{exc}")
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
            QMessageBox.warning(self, "Không tải được danh sách key", f"Không gọi được admin API:\n{exc}")
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
            if self.store.token:
                self.store.list_licenses()
        except Exception as exc:
            QMessageBox.warning(self, "Remote chưa sẵn sàng", f"Không gọi được license admin API:\n{exc}")
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
