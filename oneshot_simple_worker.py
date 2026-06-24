"""
oneshot_simple_worker.py — Hedra Studio UI worker compatibility.
Calls new oneshot_engine CLI.
"""

from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path
import subprocess


class OneShotSimpleRunWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float)

    def __init__(self, path, settings, options):
        super().__init__()
        self.path = path
        self.settings = settings
        self.options = options

    def run(self):
        try:
            venv = Path.home() / "hedra-studio" / "venv" / "bin" / "python"
            engine = Path(__file__).parent / "oneshot_engine"
            cmd = [str(venv), str(engine / "main.py"), str(self.path)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if r.returncode == 0:
                self.finished.emit({"status": "ok"})
            else:
                self.error.emit(r.stderr[:500] or r.stdout[:500])
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self.terminate()


class OneShotSimpleBatchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)

    def __init__(self, paths, settings, options):
        super().__init__()
        self.paths = paths
        self.settings = settings
        self.options = options

    def run(self):
        results = []
        total = len(self.paths)
        for i, path in enumerate(self.paths):
            self.progress.emit(str(path), i + 1, total)
            try:
                venv = Path.home() / "hedra-studio" / "venv" / "bin" / "python"
                engine = Path(__file__).parent / "oneshot_engine"
                cmd = [str(venv), str(engine / "main.py"), str(path)]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                results.append({"path": str(path), "ok": r.returncode == 0})
            except Exception as e:
                results.append({"path": str(path), "ok": False, "error": str(e)})
        self.finished.emit(results)

    def cancel(self):
        self.terminate()
