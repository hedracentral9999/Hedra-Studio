import sys
import os
import traceback
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog
from PyQt6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt

from app_utils import DATA_DIR, load_settings, save_settings, _install_exception_hook
_install_exception_hook()

from version import VERSION
from app_constants import get_style
from main_window import MainWindow
from settings_dialog import SettingsDialog


STARTUP_LOG = DATA_DIR / "startup.log"


def _startup_log(message: str) -> None:
    try:
        with open(STARTUP_LOG, "a", encoding="utf-8") as f:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{now}] pid={os.getpid()} {message}\n")
    except Exception:
        pass


# ── Tray app ───────────────────────────────────────────────────────
class TrayApp:
    def __init__(self):
        _startup_log("TRAY_INIT_BEGIN")
        self._shutdown_done = False
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.aboutToQuit.connect(self._before_quit)
        self.settings    = load_settings()
        _startup_log("LOAD_SETTINGS_OK")
        self.app.setStyleSheet(get_style(self.settings.get("app_theme", "system")))
        self.main_window = MainWindow(self.settings)
        _startup_log("MAINWINDOW_OK")

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip(f"Hedra Studio v{VERSION}")

        menu = QMenu()
        a_open     = QAction("🎙  Mở Tool");    a_open.triggered.connect(self._show_main)
        a_settings = QAction("⚙️  Settings");   a_settings.triggered.connect(self._show_settings)
        a_quit     = QAction("Quit");            a_quit.triggered.connect(self._quit)
        menu.addAction(a_open)
        menu.addSeparator()
        menu.addAction(a_settings)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()
        self._show_main()
        _startup_log("TRAY_INIT_DONE")

    def _make_icon(self) -> QIcon:
        # Ưu tiên icon native theo nền tảng khi build bằng PyInstaller.
        try:
            root = os.path.dirname(__file__) if not getattr(sys, 'frozen', False) else sys._MEIPASS
            names = ("icon.ico", "icon.icns") if sys.platform == "win32" else ("icon.icns", "icon.ico")
            for name in names:
                icon_path = os.path.join(root, name)
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
        try:
            self.settings.update(load_settings())
        except Exception:
            pass
        dlg = SettingsDialog(self.settings, self.main_window)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            self.app.setStyleSheet(get_style(self.settings.get("app_theme", "system")))
            self.main_window.update_settings(self.settings)

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self._show_main()

    def _before_quit(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        _startup_log("APP_ABOUT_TO_QUIT")
        try:
            self.app.setProperty("_hedra_quitting", True)
        except Exception:
            pass
        try:
            self.main_window.shutdown_workers()
        except Exception:
            _startup_log("SHUTDOWN_WORKERS_ERROR\n" + traceback.format_exc())

    def _quit(self):
        try:
            self.app.setProperty("_hedra_quitting", True)
        except Exception:
            pass
        self.app.quit()

    def run(self):
        _startup_log("APP_EXEC_BEGIN")
        code = self.app.exec()
        _startup_log(f"APP_EXEC_END code={code}")
        sys.exit(code)


if __name__ == "__main__":
    _startup_log("STARTUP_BEGIN")
    try:
        TrayApp().run()
    except Exception:
        _startup_log("STARTUP_EXCEPTION\n" + traceback.format_exc())
        raise
