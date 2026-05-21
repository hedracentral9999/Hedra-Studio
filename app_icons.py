from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


_SF_COLOR_KEYS = {
    "#1d1d1f": "normal",
    "#ffffff": "active",
    "#8e8e93": "disabled",
    "#0071e3": "accent",
    "#007aff": "accent",
}

_TILE_COLORS = {
    "script": ("#0a84ff", "#0066cc"),
    "tts": ("#30d158", "#248a3d"),
    "voices": ("#30d158", "#248a3d"),
    "stt": ("#64d2ff", "#0a84ff"),
    "video": ("#ff9f0a", "#ff6b00"),
    "api": ("#8e8e93", "#636366"),
    "prompts": ("#bf5af2", "#8e44ad"),
    "output": ("#32d74b", "#28a745"),
    "settings": ("#a1a1aa", "#6e6e73"),
    "message": ("#0a84ff", "#0066cc"),
    "download": ("#8e8e93", "#636366"),
    "play": ("#30d158", "#248a3d"),
    "spark": ("#ffcc00", "#ff9f0a"),
    "audio": ("#8e8e93", "#636366"),
    "image": ("#5e5ce6", "#3634a3"),
}


def _asset_roots() -> list[Path]:
    roots = [Path(__file__).resolve().parent]
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", roots[0])))
        roots.append(Path(sys.executable).resolve().parent)
    return [root / "assets" / "sf-symbols" for root in roots]


def _sf_pixmap(name: str, color: str) -> QPixmap | None:
    key = _SF_COLOR_KEYS.get(color.lower())
    if not key:
        return None
    for root in _asset_roots():
        path = root / f"{name}-{key}.png"
        if path.exists():
            pm = QPixmap(str(path))
            if not pm.isNull():
                return pm
    return None


def _pixmap(name: str, size: int, color: str) -> QPixmap:
    sf = _sf_pixmap(name, color)
    if sf is not None:
        return sf

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), max(1.6, size / 12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(x1 * s, y1 * s), QPointF(x2 * s, y2 * s))

    def rect(x, y, w, h, r=0.08):
        p.drawRoundedRect(QRectF(x * s, y * s, w * s, h * s), r * s, r * s)

    def circle(cx, cy, r):
        p.drawEllipse(QPointF(cx * s, cy * s), r * s, r * s)

    if name == "script":
        rect(0.24, 0.15, 0.50, 0.70, 0.06)
        line(0.34, 0.34, 0.62, 0.34)
        line(0.34, 0.48, 0.62, 0.48)
        line(0.34, 0.62, 0.52, 0.62)
        line(0.55, 0.78, 0.76, 0.88)
    elif name == "tts" or name == "voices":
        rect(0.37, 0.16, 0.26, 0.46, 0.13)
        line(0.24, 0.42, 0.24, 0.48)
        line(0.76, 0.42, 0.76, 0.48)
        path = QPainterPath()
        path.moveTo(0.25 * s, 0.47 * s)
        path.cubicTo(0.25 * s, 0.70 * s, 0.75 * s, 0.70 * s, 0.75 * s, 0.47 * s)
        p.drawPath(path)
        line(0.50, 0.72, 0.50, 0.86)
        line(0.38, 0.86, 0.62, 0.86)
    elif name == "stt":
        rect(0.17, 0.24, 0.66, 0.52, 0.06)
        line(0.30, 0.38, 0.70, 0.38)
        line(0.30, 0.50, 0.70, 0.50)
        line(0.30, 0.62, 0.55, 0.62)
        circle(0.23, 0.38, 0.018)
        circle(0.23, 0.50, 0.018)
        circle(0.23, 0.62, 0.018)
    elif name == "video":
        rect(0.18, 0.26, 0.64, 0.48, 0.06)
        line(0.20, 0.38, 0.78, 0.38)
        line(0.30, 0.26, 0.40, 0.38)
        line(0.50, 0.26, 0.60, 0.38)
        path = QPainterPath()
        path.moveTo(0.44 * s, 0.49 * s)
        path.lineTo(0.44 * s, 0.63 * s)
        path.lineTo(0.58 * s, 0.56 * s)
        path.closeSubpath()
        p.setBrush(QBrush(QColor(color)))
        p.drawPath(path)
    elif name == "api":
        circle(0.34, 0.43, 0.14)
        line(0.44, 0.53, 0.76, 0.85)
        line(0.61, 0.70, 0.71, 0.60)
        line(0.69, 0.78, 0.79, 0.68)
    elif name == "prompts":
        line(0.23, 0.72, 0.31, 0.52)
        line(0.31, 0.52, 0.68, 0.15)
        line(0.68, 0.15, 0.82, 0.29)
        line(0.82, 0.29, 0.45, 0.66)
        line(0.23, 0.72, 0.45, 0.66)
    elif name == "output":
        path = QPainterPath()
        path.moveTo(0.15 * s, 0.30 * s)
        path.lineTo(0.40 * s, 0.30 * s)
        path.lineTo(0.48 * s, 0.40 * s)
        path.lineTo(0.85 * s, 0.40 * s)
        path.lineTo(0.85 * s, 0.75 * s)
        path.lineTo(0.15 * s, 0.75 * s)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "settings":
        circle(0.50, 0.50, 0.16)
        for a in range(0, 360, 45):
            import math

            r1, r2 = 0.29, 0.39
            x1 = 0.50 + math.cos(math.radians(a)) * r1
            y1 = 0.50 + math.sin(math.radians(a)) * r1
            x2 = 0.50 + math.cos(math.radians(a)) * r2
            y2 = 0.50 + math.sin(math.radians(a)) * r2
            line(x1, y1, x2, y2)
    elif name == "message":
        rect(0.18, 0.22, 0.64, 0.44, 0.08)
        line(0.33, 0.38, 0.67, 0.38)
        line(0.33, 0.50, 0.56, 0.50)
        line(0.35, 0.66, 0.27, 0.80)
    elif name == "download":
        line(0.50, 0.18, 0.50, 0.60)
        line(0.34, 0.45, 0.50, 0.61)
        line(0.66, 0.45, 0.50, 0.61)
        rect(0.22, 0.70, 0.56, 0.14, 0.04)
    elif name == "play":
        path = QPainterPath()
        path.moveTo(0.35 * s, 0.22 * s)
        path.lineTo(0.35 * s, 0.78 * s)
        path.lineTo(0.78 * s, 0.50 * s)
        path.closeSubpath()
        p.setBrush(QBrush(QColor(color)))
        p.drawPath(path)
    elif name == "spark":
        line(0.50, 0.16, 0.50, 0.34)
        line(0.50, 0.66, 0.50, 0.84)
        line(0.16, 0.50, 0.34, 0.50)
        line(0.66, 0.50, 0.84, 0.50)
        line(0.30, 0.30, 0.38, 0.38)
        line(0.62, 0.62, 0.70, 0.70)
        line(0.70, 0.30, 0.62, 0.38)
        line(0.38, 0.62, 0.30, 0.70)
    elif name == "audio":
        rect(0.18, 0.38, 0.20, 0.24, 0.04)
        line(0.38, 0.38, 0.58, 0.22)
        line(0.58, 0.22, 0.58, 0.78)
        line(0.58, 0.78, 0.38, 0.62)
        path = QPainterPath()
        path.moveTo(0.68 * s, 0.36 * s)
        path.cubicTo(0.78 * s, 0.44 * s, 0.78 * s, 0.56 * s, 0.68 * s, 0.64 * s)
        p.drawPath(path)
    elif name == "image":
        rect(0.18, 0.20, 0.64, 0.58, 0.06)
        circle(0.65, 0.36, 0.05)
        line(0.23, 0.70, 0.42, 0.50)
        line(0.42, 0.50, 0.54, 0.62)
        line(0.54, 0.62, 0.65, 0.50)
        line(0.65, 0.50, 0.79, 0.69)
    else:
        rect(0.24, 0.24, 0.52, 0.52, 0.08)

    p.end()
    return pm


def ui_icon(name: str, size: int = 18, color: str = "#1d1d1f", active: str = "#ffffff") -> QIcon:
    icon = QIcon()
    icon.addPixmap(_pixmap(name, size, color), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_pixmap(name, size, active), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_pixmap(name, size, "#8e8e93"), QIcon.Mode.Disabled, QIcon.State.Off)
    return icon


def _tile_pixmap(name: str, size: int, disabled: bool = False) -> QPixmap:
    top, bottom = _TILE_COLORS.get(name, ("#8e8e93", "#636366"))
    if disabled:
        top, bottom = "#d1d1d6", "#aeaeb2"

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r = QRectF(0, 0, size, size)
    bg = QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0, QColor(top))
    bg.setColorAt(1, QColor(bottom))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), size * 0.22, size * 0.22)

    symbol = _pixmap(name, max(16, int(size * 0.72)), "#ffffff")
    inset = max(3, int(size * 0.18))
    target = QRectF(inset, inset, size - inset * 2, size - inset * 2)
    p.drawPixmap(target, symbol, QRectF(symbol.rect()))
    p.end()
    return pm


def macos_tile_icon(name: str, size: int = 22) -> QIcon:
    icon = QIcon()
    normal = _tile_pixmap(name, size)
    disabled = _tile_pixmap(name, size, disabled=True)
    icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(disabled, QIcon.Mode.Disabled, QIcon.State.Off)
    return icon


def icon_size(size: int = 18) -> QSize:
    return QSize(size, size)
