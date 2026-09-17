"""Vector glyphs drawn with QPainter.

Everything the HUD shows as an "icon" is a small hand-built path, so the
project ships no binary art assets and stays crisp at any DPI.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

GLYPHS = (
    "carrier",
    "planet",
    "radar",
    "bio",
    "star",
    "gem",
    "warning",
    "signal",
    "globe",
    "crossed_swords",
    "scales",
    "compass",
    "rifle",
    "leaf",
    "empire",
    "federation",
    "arena",
)


def _pen(color: QColor, size: float, weight: float = 0.11) -> QPen:
    pen = QPen(color)
    pen.setWidthF(max(1.1, size * weight))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_carrier(painter: QPainter, r: QRectF) -> None:
    """A fleet carrier seen from the side: hull, tower, two outriggers."""
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.06, r.top() + r.height() * 0.62),
        QPointF(r.right() - r.width() * 0.06, r.top() + r.height() * 0.62),
    )
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.24, r.top() + r.height() * 0.62),
        QPointF(r.left() + r.width() * 0.24, r.top() + r.height() * 0.86),
    )
    painter.drawLine(
        QPointF(r.right() - r.width() * 0.24, r.top() + r.height() * 0.62),
        QPointF(r.right() - r.width() * 0.24, r.top() + r.height() * 0.86),
    )
    painter.drawLine(
        QPointF(r.center().x(), r.top() + r.height() * 0.62),
        QPointF(r.center().x(), r.top() + r.height() * 0.16),
    )
    painter.drawEllipse(
        QPointF(r.center().x(), r.top() + r.height() * 0.14), r.width() * 0.09, r.width() * 0.09
    )


def _draw_planet(painter: QPainter, r: QRectF) -> None:
    radius = r.width() * 0.30
    painter.drawEllipse(r.center(), radius, radius)
    ring = QRectF(
        r.left() + r.width() * 0.03,
        r.center().y() - r.height() * 0.16,
        r.width() * 0.94,
        r.height() * 0.32,
    )
    painter.drawArc(ring, 200 * 16, 140 * 16)
    painter.drawArc(ring, 20 * 16, 140 * 16)


def _draw_radar(painter: QPainter, r: QRectF) -> None:
    """FSS: a reticle with a sweep."""
    painter.drawEllipse(r.adjusted(r.width() * 0.12, r.height() * 0.12, -r.width() * 0.12, -r.height() * 0.12))
    painter.drawEllipse(r.center(), r.width() * 0.05, r.width() * 0.05)
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.30, r.bottom() - r.height() * 0.30),
        QPointF(r.right() - r.width() * 0.18, r.top() + r.height() * 0.18),
    )


def _draw_bio(painter: QPainter, r: QRectF) -> None:
    """A leaf, the generic 'organic here' marker."""
    path = QPainterPath()
    path.moveTo(r.left() + r.width() * 0.14, r.bottom() - r.height() * 0.14)
    path.cubicTo(
        r.left() + r.width() * 0.06, r.top() + r.height() * 0.22,
        r.left() + r.width() * 0.52, r.top() + r.height() * 0.02,
        r.right() - r.width() * 0.12, r.top() + r.height() * 0.12,
    )
    path.cubicTo(
        r.right() - r.width() * 0.02, r.top() + r.height() * 0.58,
        r.left() + r.width() * 0.50, r.bottom() - r.height() * 0.02,
        r.left() + r.width() * 0.14, r.bottom() - r.height() * 0.14,
    )
    painter.drawPath(path)
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.18, r.bottom() - r.height() * 0.18),
        QPointF(r.right() - r.width() * 0.24, r.top() + r.height() * 0.26),
    )


def _star_points(center: QPointF, outer: float, inner: float, spikes: int = 4) -> QPainterPath:
    path = QPainterPath()
    for index in range(spikes * 2):
        angle = math.pi * index / spikes - math.pi / 2
        radius = outer if index % 2 == 0 else inner
        point = QPointF(center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle))
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def _draw_star(painter: QPainter, r: QRectF) -> None:
    painter.drawPath(_star_points(r.center(), r.width() * 0.48, r.width() * 0.14, 4))


def _draw_gem(painter: QPainter, r: QRectF) -> None:
    top = r.top() + r.height() * 0.22
    bottom = r.bottom() - r.height() * 0.14
    left, right = r.left() + r.width() * 0.06, r.right() - r.width() * 0.06
    mid_y = r.top() + r.height() * 0.44
    path = QPainterPath()
    path.moveTo(left + r.width() * 0.18, top)
    path.lineTo(right - r.width() * 0.18, top)
    path.lineTo(right, mid_y)
    path.lineTo(r.center().x(), bottom)
    path.lineTo(left, mid_y)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(left + r.width() * 0.18, top), QPointF(r.center().x(), mid_y))
    painter.drawLine(QPointF(right - r.width() * 0.18, top), QPointF(r.center().x(), mid_y))
    painter.drawLine(QPointF(r.center().x(), mid_y), QPointF(r.center().x(), bottom))


def _draw_warning(painter: QPainter, r: QRectF) -> None:
    path = QPainterPath()
    path.moveTo(r.center().x(), r.top() + r.height() * 0.10)
    path.lineTo(r.right() - r.width() * 0.08, r.bottom() - r.height() * 0.12)
    path.lineTo(r.left() + r.width() * 0.08, r.bottom() - r.height() * 0.12)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(
        QPointF(r.center().x(), r.top() + r.height() * 0.36),
        QPointF(r.center().x(), r.top() + r.height() * 0.62),
    )
    painter.drawPoint(QPointF(r.center().x(), r.top() + r.height() * 0.76))


def _draw_signal(painter: QPainter, r: QRectF) -> None:
    """Three rising arcs, the classic 'signals detected' mark."""
    for index, scale in enumerate((0.34, 0.62, 0.92)):
        radius = r.width() * scale * 0.5
        rect = QRectF(r.center().x() - radius, r.bottom() - radius * 0.9, radius * 2, radius * 1.8)
        painter.drawArc(rect, 20 * 16, 140 * 16)
    painter.drawPoint(QPointF(r.center().x(), r.bottom() - r.height() * 0.10))


def _draw_globe(painter: QPainter, r: QRectF) -> None:
    """Game mode: a sphere with a meridian."""
    radius = r.width() * 0.40
    painter.drawEllipse(r.center(), radius, radius)
    painter.drawEllipse(r.center(), radius * 0.42, radius)
    painter.drawLine(
        QPointF(r.center().x() - radius, r.center().y()),
        QPointF(r.center().x() + radius, r.center().y()),
    )


def _draw_crossed_swords(painter: QPainter, r: QRectF) -> None:
    """Combat rank."""
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.16, r.bottom() - r.height() * 0.16),
        QPointF(r.right() - r.width() * 0.16, r.top() + r.height() * 0.16),
    )
    painter.drawLine(
        QPointF(r.right() - r.width() * 0.16, r.bottom() - r.height() * 0.16),
        QPointF(r.left() + r.width() * 0.16, r.top() + r.height() * 0.16),
    )


def _draw_scales(painter: QPainter, r: QRectF) -> None:
    """Trade rank: a balance."""
    painter.drawLine(
        QPointF(r.center().x(), r.top() + r.height() * 0.12),
        QPointF(r.center().x(), r.bottom() - r.height() * 0.16),
    )
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.10, r.top() + r.height() * 0.34),
        QPointF(r.right() - r.width() * 0.10, r.top() + r.height() * 0.34),
    )
    for x in (r.left() + r.width() * 0.10, r.right() - r.width() * 0.10):
        painter.drawArc(
            QRectF(x - r.width() * 0.16, r.top() + r.height() * 0.34, r.width() * 0.32, r.height() * 0.32),
            180 * 16, 180 * 16,
        )


def _draw_compass(painter: QPainter, r: QRectF) -> None:
    """Exploration rank."""
    radius = r.width() * 0.40
    painter.drawEllipse(r.center(), radius, radius)
    painter.drawLine(
        QPointF(r.center().x(), r.center().y() - radius * 0.55),
        QPointF(r.center().x() - radius * 0.35, r.center().y() + radius * 0.55),
    )
    painter.drawLine(
        QPointF(r.center().x(), r.center().y() - radius * 0.55),
        QPointF(r.center().x() + radius * 0.35, r.center().y() + radius * 0.55),
    )


def _draw_rifle(painter: QPainter, r: QRectF) -> None:
    """Mercenary (on-foot combat) rank."""
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.10, r.top() + r.height() * 0.40),
        QPointF(r.right() - r.width() * 0.10, r.top() + r.height() * 0.40),
    )
    painter.drawLine(
        QPointF(r.left() + r.width() * 0.34, r.top() + r.height() * 0.40),
        QPointF(r.left() + r.width() * 0.28, r.bottom() - r.height() * 0.20),
    )


def _draw_leaf(painter: QPainter, r: QRectF) -> None:
    """Exobiologist rank."""
    _draw_bio(painter, r)


def _draw_empire(painter: QPainter, r: QRectF) -> None:
    """Empire: a crown. Placeholder shape, replaced by the game's emblem later."""
    path = QPainterPath()
    path.moveTo(r.left() + r.width() * 0.10, r.bottom() - r.height() * 0.24)
    path.lineTo(r.left() + r.width() * 0.18, r.top() + r.height() * 0.26)
    path.lineTo(r.center().x(), r.top() + r.height() * 0.48)
    path.lineTo(r.right() - r.width() * 0.18, r.top() + r.height() * 0.26)
    path.lineTo(r.right() - r.width() * 0.10, r.bottom() - r.height() * 0.24)
    path.closeSubpath()
    painter.drawPath(path)


def _draw_federation(painter: QPainter, r: QRectF) -> None:
    """Federation: a five-point star. Placeholder for the game's emblem."""
    painter.drawPath(_star_points(r.center(), r.width() * 0.44, r.width() * 0.18, 5))


def _draw_arena(painter: QPainter, r: QRectF) -> None:
    """CQC rank: a laurel wreath, drawn as two arcs."""
    rect = QRectF(r.left() + r.width() * 0.14, r.top() + r.height() * 0.14,
                  r.width() * 0.72, r.height() * 0.72)
    painter.drawArc(rect, 100 * 16, 160 * 16)
    painter.drawArc(rect, 280 * 16, 160 * 16)


_DRAWERS = {
    "globe": _draw_globe,
    "crossed_swords": _draw_crossed_swords,
    "scales": _draw_scales,
    "compass": _draw_compass,
    "rifle": _draw_rifle,
    "leaf": _draw_leaf,
    "empire": _draw_empire,
    "federation": _draw_federation,
    "arena": _draw_arena,
    "carrier": _draw_carrier,
    "planet": _draw_planet,
    "radar": _draw_radar,
    "bio": _draw_bio,
    "star": _draw_star,
    "gem": _draw_gem,
    "warning": _draw_warning,
    "signal": _draw_signal,
}


def draw_glyph(
    painter: QPainter,
    x: float,
    y: float,
    size: float,
    name: str,
    color: QColor,
) -> None:
    """Draw ``name`` inside a ``size`` x ``size`` box whose top-left is (x, y)."""
    drawer = _DRAWERS.get(name)
    if drawer is None:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(_pen(color, size))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    drawer(painter, QRectF(x, y, size, size))
    painter.restore()


def icon_pixmap(size: int, name: str, color: QColor):  # pragma: no cover - GUI helper
    """Render one glyph into a QPixmap (used for the tray icon)."""
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_glyph(painter, size * 0.08, size * 0.08, size * 0.84, name, color)
    painter.end()
    return pixmap
