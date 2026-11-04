"""Monochrome toolbar icons painted with QPainter (no bitmap assets)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

_GRID = 18.0
_SIZES = (16, 18, 20, 22, 24, 32, 36, 40, 48, 64)

_Draw = Callable[[QPainter, QColor], None]


def _paint(draw: _Draw, size: int, ratio: int, color: QColor) -> QPixmap:
    pixmap = QPixmap(round(size * ratio), round(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / _GRID, size / _GRID)
    pen = QPen(color)
    pen.setWidthF(1.35)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    draw(painter, color)
    painter.end()
    return pixmap


def _icon(draw: _Draw, color: str) -> QIcon:
    icon = QIcon()
    tint = QColor(color)
    for size in _SIZES:
        for ratio in (1, 2):
            icon.addPixmap(_paint(draw, size, ratio, tint))
    return icon


def _draw_open(painter: QPainter, color: QColor) -> None:
    folder = QPainterPath()
    folder.moveTo(2.4, 6.1)
    folder.cubicTo(2.4, 5.15, 3.17, 4.38, 4.12, 4.38)
    folder.lineTo(7.0, 4.38)
    folder.lineTo(8.8, 6.15)
    folder.lineTo(13.9, 6.15)
    folder.cubicTo(14.85, 6.15, 15.62, 6.92, 15.62, 7.87)
    folder.lineTo(15.62, 13.9)
    folder.cubicTo(15.62, 14.85, 14.85, 15.62, 13.9, 15.62)
    folder.lineTo(4.12, 15.62)
    folder.cubicTo(3.17, 15.62, 2.4, 14.85, 2.4, 13.9)
    folder.closeSubpath()
    painter.drawPath(folder)
    painter.drawLine(QPointF(6.1, 9.5), QPointF(12.0, 9.5))
    painter.drawLine(QPointF(6.1, 12.0), QPointF(10.2, 12.0))


def _draw_print(painter: QPainter, color: QColor) -> None:
    body = QPainterPath()
    body.addRoundedRect(QRectF(2.6, 7.0, 12.8, 5.6), 1.3, 1.3)
    painter.drawPath(body)
    painter.drawPolyline(
        QPolygonF(
            [QPointF(5.9, 7.0), QPointF(5.9, 3.6), QPointF(12.1, 3.6), QPointF(12.1, 7.0)]
        )
    )
    painter.drawPolyline(
        QPolygonF(
            [
                QPointF(5.9, 12.6),
                QPointF(5.9, 15.6),
                QPointF(12.1, 15.6),
                QPointF(12.1, 12.6),
            ]
        )
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(13.2, 9.8), 0.55, 0.55)


def open_icon(color: str) -> QIcon:
    """Folder glyph used for the toolbar “open” action."""
    return _icon(_draw_open, color)


def print_icon(color: str) -> QIcon:
    """Printer glyph used for the toolbar “print” action."""
    return _icon(_draw_print, color)
