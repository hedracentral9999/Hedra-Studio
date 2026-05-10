import sys
import os

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt

from version import VERSION
from app_constants import STYLE
from app_utils import load_settings, save_settings, _install_exception_hook
from main_window import MainWindow
from settings_dialog import SettingsDialog

# ── Tray app ───────────────────────────────────────────────────────
class TrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.settings    = load_settings()
        self.main_window = MainWindow(self.settings)

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip(f"Hedra Studio v{VERSION}")

        menu = QMenu()
        a_open     = QAction("🎙  Mở Tool");    a_open.triggered.connect(self._show_main)
        a_settings = QAction("⚙️  Settings");   a_settings.triggered.connect(self._show_settings)
        a_quit     = QAction("Quit");            a_quit.triggered.connect(self.app.quit)
        menu.addAction(a_open)
        menu.addSeparator()
        menu.addAction(a_settings)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()
        self._show_main()

    def _make_icon(self) -> QIcon:
        # Ưu tiên .icns nếu có (khi build bằng PyInstaller)
        try:
            icon_path = os.path.join(os.path.dirname(__file__) if not getattr(sys, 'frozen', False) else sys._MEIPASS, "icon.icns")
            if os.path.exists(icon_path):
                return QIcon(icon_path)
        except Exception:
            pass
        # Fallback: blue circle
        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#2563eb"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.end()
        return QIcon(px)

    def _show_main(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _show_settings(self):
        dlg = SettingsDialog(self.settings, self.main_window)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            self.main_window.update_settings(self.settings)

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self._show_main()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    _install_exception_hook()
    TrayApp().run()
