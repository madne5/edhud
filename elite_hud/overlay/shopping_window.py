"""The shopping popup, shown while the galaxy map is open.

It appears when the commander opens the galaxy map, because that is where they
are going to plot a route to a shop, and stays out of the way otherwise. The
trigger is ``GuiFocus == 6`` in Status.json, which is the only way to know: no
journal event reports the map being opened.

Every row carries the system name on a button, so plotting the route is a copy
and a paste rather than reading a name off the screen and typing it.

The window is deliberately the one part of this overlay that accepts the mouse.
Everything else is click-through, but buttons that cannot be clicked would be
pointless, and the window only exists while a full-screen map is up.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..market import Offer
from ..shopping import Need

log = logging.getLogger(__name__)


class ShoppingWindow(QWidget):
    """Lists what the open missions need and where to buy it."""

    MAX_ROWS = 40

    def __init__(self, config: Config) -> None:
        super().__init__(None)
        self.config = config
        self._copied: QLabel | None = None

        self.setWindowTitle("elite-hud — закупка")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # No WindowDoesNotAcceptFocus and no click-through: this window has
        # buttons, and they have to be reachable.

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._panel = QFrame(self)
        self._panel.setObjectName("panel")
        outer.addWidget(self._panel)

        self._layout = QVBoxLayout(self._panel)
        self._layout.setContentsMargins(18, 14, 18, 14)
        self._layout.setSpacing(6)

        self._title = QLabel("Закупка")
        self._layout.addWidget(self._title)

        self._status = QLabel("")
        self._layout.addWidget(self._status)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(4)
        self._body_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._body)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._layout.addWidget(self._scroll, 1)

        self._apply_palette()
        self.resize(560, 460)

    # -- appearance --------------------------------------------------------

    def _apply_palette(self) -> None:
        cfg = self.config.overlay
        self._title.setStyleSheet(
            f"color: {cfg.foreground}; font-size: 15px; font-weight: bold;"
        )
        self._status.setStyleSheet(f"color: {cfg.foreground}; font-size: 11px;")
        self._panel.setStyleSheet(
            f"#panel {{ background: {cfg.background};"
            f" border: 1px solid {cfg.accent}; border-radius: 10px; }}"
        )

    # -- contents ----------------------------------------------------------

    def set_message(self, text: str) -> None:
        """Replace the whole list with a single line, e.g. a loading notice."""
        self._clear()
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {self.config.overlay.foreground};")
        self._body_layout.insertWidget(self._body_layout.count() - 1, label)
        self._status.setText("")

    def _clear(self) -> None:
        while self._body_layout.count() > 1:
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh(self, needs: list[Need], offers: dict[str, list[Offer]], note: str = "") -> None:
        """Rebuild the list from the current needs and whatever was found."""
        self._clear()
        cfg = self.config.overlay
        shown = 0
        for need in needs:
            if shown >= self.MAX_ROWS:
                break
            shown += 1
            found = offers.get(need.commodity, [])

            heading = QLabel(need.describe())
            heading.setStyleSheet(
                f"color: {cfg.accent}; font-weight: bold; font-size: 13px;"
            )
            self._body_layout.insertWidget(self._body_layout.count() - 1, heading)

            if need.destinations:
                where = QLabel("  доставить: " + ", ".join(need.destinations))
                where.setStyleSheet(f"color: {cfg.foreground}; font-size: 11px;")
                where.setWordWrap(True)
                self._body_layout.insertWidget(self._body_layout.count() - 1, where)

            if not found:
                empty = QLabel("  продавцов не найдено")
                empty.setStyleSheet(f"color: {cfg.danger}; font-size: 11px;")
                self._body_layout.insertWidget(self._body_layout.count() - 1, empty)
                continue

            for offer in found:
                self._body_layout.insertWidget(
                    self._body_layout.count() - 1, self._offer_row(offer)
                )

        self._status.setText(note)

    def _offer_row(self, offer: Offer) -> QWidget:
        cfg = self.config.overlay
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        detail = f"{offer.distance:,.1f} ly · {offer.station}"
        if offer.largest_pad:
            detail += f" · {offer.largest_pad}"
        if offer.distance_to_arrival:
            detail += f" · {offer.distance_to_arrival:,.0f} ls"
        label = QLabel(detail)
        label.setStyleSheet(f"color: {cfg.foreground}; font-size: 12px;")
        layout.addWidget(label, 1)

        button = QPushButton(offer.system)
        button.setToolTip(f"Скопировать «{offer.system}»")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ color: {cfg.background}; background: {cfg.success};"
            f" border: none; border-radius: 4px; padding: 3px 10px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {cfg.accent}; }}"
        )
        # The system name is bound as a default argument so every button keeps
        # its own, rather than all of them copying the last one built.
        button.clicked.connect(lambda _checked=False, name=offer.system: self.copy(name))
        layout.addWidget(button)
        return row

    # -- clipboard ---------------------------------------------------------

    def copy(self, text: str) -> None:
        """Put a system name on the clipboard, and say so."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:  # pragma: no cover - only without a GUI
            return
        clipboard.setText(text)
        log.info("shopping: copied %r", text)

    # -- placement and visibility ------------------------------------------

    def show_for_map(self) -> None:
        """Place it beside the HUD and show it, without stealing the game's focus."""
        self._place()
        self.show()
        # Shown but not activated: the commander is flying, and a popup that
        # takes the keyboard would interrupt them mid-route-plot.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:  # pragma: no cover - headless
            return
        area = screen.availableGeometry()
        cfg = self.config.overlay
        x = area.left() + (area.width() - self.width()) // 2
        y = area.top() + max(cfg.offset_y, 40)
        self.move(int(x), int(y))

    def set_accent(self, colour: str) -> None:
        """Recolour the border, used to show a failed lookup."""
        self._panel.setStyleSheet(
            f"#panel {{ background: {self.config.overlay.background};"
            f" border: 1px solid {colour}; border-radius: 10px; }}"
        )
