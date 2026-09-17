"""The always-on-top HUD bar.

One line of text pinned to the top edge of the screen, centred horizontally,
rendered with per-pixel alpha so it blends over the game.  The window is
click-through and never takes focus, so it cannot interfere with flying.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from ..config import Config
from ..exobiology import Confidence
from .. import ranks
from ..formatting import (
    CONFIDENCE_GLYPH,
    CONFIDENCE_LABEL,
    format_countdown,
    format_credits,
)
from ..state import Alert, GameState
from ..notifications import Notification, NotificationCenter
from . import win32
from .icons import draw_glyph

log = logging.getLogger(__name__)

#: Windows ships Consolas; the rest are a graceful fallback chain.
FONT_FALLBACKS = ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Menlo", "monospace")

ELLIPSIS = "…"

#: Glyph box height as a multiple of the font's cap height. Slightly larger than
#: the capitals so an icon reads as an icon, not as a stray letter.
GLYPH_CAPHEIGHT_RATIO = 1.35


def cap_height(metrics: QFontMetricsF) -> float:
    """The font's cap height, with a sane fallback.

    A few fonts report 0, which would collapse every vertical calculation.
    """
    height = metrics.capHeight()
    if height <= 0:
        return metrics.height() * 0.7
    return height


def glyph_top(baseline: float, cap: float, size: float) -> float:
    """Top of a glyph box whose centre matches the text's optical centre.

    Text is centred on its cap height, i.e. the middle of the capitals sits at
    ``baseline - cap / 2``. A glyph placed any other way sits visibly low.
    """
    return baseline - cap / 2.0 - size / 2.0

#: An elided elastic span never shrinks below this many characters.
MIN_ELIDED_CHARS = "XXXXXXXXXX"


@dataclass(slots=True)
class Span:
    text: str
    color: str | None = None
    bold: bool = False
    #: alpha multiplier, used to dim secondary information
    dim: float = 1.0
    #: may be elided with "…" when the bar would overflow the screen
    elastic: bool = False


@dataclass(slots=True)
class Segment:
    glyph: str | None
    spans: list[Span] = field(default_factory=list)
    glyph_color: str | None = None
    #: extra pixels before this segment
    lead: float = 0.0


@dataclass(slots=True)
class RowStyle:
    """Fonts and spacing for one row, so rows can differ in size."""

    font: QFont
    bold_font: QFont
    metrics: QFontMetricsF
    bold_metrics: QFontMetricsF
    padding_x: float
    padding_y: float
    glyph_size: float
    glyph_gap: float
    plate_radius: float
    line_height: float

    @classmethod
    def build(cls, font: QFont, bold_font: QFont, scale: float = 1.0) -> "RowStyle":
        metrics = QFontMetricsF(font)
        height = metrics.height()
        return cls(
            font=font,
            bold_font=bold_font,
            metrics=metrics,
            bold_metrics=QFontMetricsF(bold_font),
            padding_x=height * 0.85 * max(0.6, scale),
            padding_y=height * 0.38 * max(0.6, scale),
            glyph_size=cap_height(metrics) * GLYPH_CAPHEIGHT_RATIO,
            glyph_gap=height * 0.34,
            plate_radius=height * 0.85,
            line_height=height * 1.42,
        )

    def metrics_for(self, bold: bool) -> QFontMetricsF:
        return self.bold_metrics if bold else self.metrics


@dataclass(slots=True)
class Row:
    """One line of the HUD, with its own style and optional plate."""

    style: RowStyle
    segments: list[Segment] = field(default_factory=list)
    #: pixels of blank space above this row
    gap: float = 0.0
    #: draw the rounded plate behind it
    plate: bool = True
    #: name used in tests and logs
    kind: str = "primary"
    #: animation state, applied while painting so the layout never jitters
    opacity: float = 1.0
    offset: float = 0.0
    #: colours a thin bar down the leading edge; "" draws none
    accent: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.segments


class HudWindow(QWidget):
    def __init__(self, config: Config, state: GameState, clock=None) -> None:
        super().__init__(None)
        self.config = config
        self.state = state
        self._alert: Alert | None = None
        self._alert_until = 0.0
        self._alert_pulse = 0.0
        cfg = config.notifications
        self.notifications = NotificationCenter(
            max_visible=cfg.max_visible,
            hold_seconds=cfg.hold_seconds,
            fade_in=cfg.fade_in_seconds,
            fade_out=cfg.fade_out_seconds,
            **({} if clock is None else {"clock": clock}),
        )
        self._segments: list[Segment] = []
        self._rows: list[Row] = []
        self._row_boxes: list[tuple[Row, float, float, float]] = []
        self._last_size: tuple[int, int] = (0, 0)
        self._last_position: tuple[int, int] | None = None

        self._font, self._bold_font = self._build_fonts()
        self._metrics = QFontMetricsF(self._font)
        self._bold_metrics = QFontMetricsF(self._bold_font)
        self._primary_style = RowStyle.build(self._font, self._bold_font, 1.0)
        self._status_style = RowStyle.build(
            self._small_font(), self._small_bold_font(), 0.85
        )

        # Qt can deliver paintEvent before the first rebuild(); seed the layout
        # metrics so painting is always safe.
        height = self._metrics.height()
        cap = cap_height(self._metrics)
        self._padding_x = height * 0.85
        self._padding_y = height * 0.38
        self._glyph_size = cap * GLYPH_CAPHEIGHT_RATIO
        self._glyph_gap = height * 0.34
        self._plate_radius = height * 0.85
        self._segments = self._compose()

        self.setWindowTitle("elite-hud")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._apply_window_flags()

        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(1000)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        if config.overlay.always_on_top:
            self._topmost_timer.start()

        # Displays can be plugged in, unplugged, or rearranged while the HUD
        # runs; re-evaluating is cheap and the move only happens when the spot
        # actually changes.
        self._screen_timer = QTimer(self)
        self._screen_timer.setInterval(3000)
        self._screen_timer.timeout.connect(self._reposition)
        self._screen_timer.start()

        # Notifications animate, which needs a faster repaint than the countdown
        # tick. The timer only runs while something is actually moving: a HUD
        # repainting at 60 Hz for a whole session inside a game is a real cost,
        # and nothing is on screen most of the time.
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(
            max(8, int(1000.0 / max(1.0, config.notifications.animation_hz)))
        )
        self._animation_timer.timeout.connect(self._tick_animation)

    # -- window setup ------------------------------------------------------

    def _apply_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if self.config.overlay.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.config.overlay.click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setWindowOpacity(self.config.overlay.opacity)

    def _build_fonts(self) -> tuple[QFont, QFont]:
        size = self.config.overlay.font_size
        family = self.config.overlay.font_family
        available = set(QFontDatabase.families())
        candidates = (family, *FONT_FALLBACKS)
        chosen = next((name for name in candidates if name in available), None)
        if chosen is None:
            # Nothing on the list exists: take the platform's fixed-width font.
            chosen = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()

        font = QFont(chosen, size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        bold = QFont(font)
        bold.setWeight(QFont.Weight.DemiBold)
        return font, bold

    def _small_font(self) -> QFont:
        """A slightly smaller face for the secondary row."""
        font = QFont(self._font)
        font.setPointSizeF(max(6.0, self._font.pointSizeF() * 0.86))
        return font

    def _small_bold_font(self) -> QFont:
        font = QFont(self._bold_font)
        font.setPointSizeF(max(6.0, self._bold_font.pointSizeF() * 0.86))
        return font

    def show_overlay(self) -> None:
        self.rebuild()
        self.show()
        if win32.IS_WINDOWS:
            win32.make_tool_window(int(self.winId()), click_through=self.config.overlay.click_through)
        self._reposition()

    def _reassert_topmost(self) -> None:
        """Games steal the z-order; quietly take it back."""
        if not self.isVisible():
            return
        if win32.IS_WINDOWS:
            win32.assert_topmost(int(self.winId()))
        else:
            self.raise_()

    # -- public API --------------------------------------------------------

    def push_alert(self, alert: Alert) -> None:
        self._alert = alert
        self._alert_until = _monotonic() + self.config.alerts.display_seconds
        log.info(
            "alert: %s (%s, %s cr) on %s in %s",
            alert.title,
            alert.confidence.value,
            f"{alert.value:,}",
            alert.body or "?",
            alert.system or "?",
        )
        self.update()

    def clear_alert(self) -> None:
        self._alert = None
        self._alert_until = 0.0
        self.update()

    def push_notification(self, notification: Notification) -> None:
        """Show a timed notification, starting the animation timer if needed."""
        if not self.config.notifications.enabled:
            return
        self.notifications.push(notification)
        self._sync_animation_timer()
        self.rebuild()

    def _sync_animation_timer(self) -> None:
        """Run the fast timer only while something is actually animating."""
        wanted = self.config.notifications.enabled and self.notifications.animating()
        if wanted and not self._animation_timer.isActive():
            self._animation_timer.start()
        elif not wanted and self._animation_timer.isActive():
            self._animation_timer.stop()

    def _tick_animation(self) -> None:
        self.notifications.tick()
        self.rebuild()
        self._sync_animation_timer()

    def rebuild(self) -> None:
        """Recompute the bar contents, resizing and repositioning if needed."""
        self._alert_pulse = _monotonic()
        if self._alert is not None and _monotonic() >= self._alert_until:
            self._alert = None

        self._rows = self._compose_rows()
        # Kept as an alias so the primary row's segments remain directly
        # reachable, which the tests and the widen/shrink logic both use.
        primary = next((row for row in self._rows if row.kind == "primary"), None)
        self._segments = primary.segments if primary is not None else []
        self._layout()
        self.update()

    def _compose_rows(self) -> list[Row]:
        """Every row the HUD should draw, top to bottom."""
        rows: list[Row] = []
        primary = Row(style=self._primary_style, kind="primary")
        primary.segments = self._compose()
        rows.append(primary)

        status = Row(style=self._status_style, kind="status", gap=self._metrics.height() * 0.28)
        status.segments = self._status_segments()
        if status.segments:
            rows.append(status)
        rows.extend(self._notification_rows())
        return rows

    def _notification_rows(self) -> list[Row]:
        """One row per live notification, newest last, with its animation."""
        if not self.config.notifications.enabled:
            return []
        rows: list[Row] = []
        for entry in self.notifications.rendered():
            item = entry.notification
            colour = self._tone_colour(item.tone)
            spans = [Span(item.title, color=colour, bold=True)]
            if item.detail:
                spans.append(
                    Span(f"  {item.detail}", color=self.config.overlay.foreground, dim=0.78)
                )
            if item.count > 1:
                spans.append(
                    Span(f"  x{item.count}", color=colour, bold=True, dim=0.9)
                )
            rows.append(
                Row(
                    style=self._status_style,
                    segments=[
                        Segment(
                            glyph=item.glyph if self.config.overlay.show_glyphs else None,
                            spans=spans,
                            glyph_color=colour,
                        )
                    ],
                    kind="notification",
                    gap=self._metrics.height() * 0.22,
                    opacity=entry.opacity,
                    offset=entry.offset,
                    accent=colour,
                )
            )
        return rows

    def _tone_colour(self, tone: str) -> str:
        """Map a notification's colour role onto the overlay palette."""
        cfg = self.config.overlay
        return {
            "success": cfg.success,
            "danger": cfg.danger,
            "foreground": cfg.foreground,
        }.get(tone, cfg.accent)

    def _status_segments(self) -> list[Segment]:
        """The always-visible second row."""
        cfg = self.config.overlay
        style = self._status_style
        segments: list[Segment] = []
        first = True

        def lead() -> float:
            nonlocal first
            value = 0.0 if first else style.metrics.height() * 0.95
            first = False
            return value

        for name in cfg.status_segments:
            segment: Segment | None = None
            if name == "mode":
                segment = self._mode_segment(lead())
            elif name == "empire":
                segment = self._superpower_segment("Empire", lead())
            elif name == "federation":
                segment = self._superpower_segment("Federation", lead())
            elif name == "ship":
                segment = self._ship_segment(lead())
            elif name == "missions":
                segment = self._missions_segment(lead())
            if segment is not None:
                segments.append(segment)
        return segments

    def _mode_segment(self, lead: float) -> Segment | None:
        mode = self.state.game_mode
        if not mode:
            return None
        labels = self.config.overlay.labels
        if mode == "Open":
            text, color = labels.mode_open, self.config.overlay.success
        elif mode == "Solo":
            text, color = labels.mode_solo, self.config.overlay.foreground
        elif mode == "Group":
            text, color = labels.mode_group, self.config.overlay.accent
        else:
            text, color = mode.upper(), self.config.overlay.foreground
        if mode == "Group" and self.state.group_name:
            text = f"{text}: {self.state.group_name}"
        return Segment(
            glyph="globe" if self.config.overlay.show_glyphs else None,
            spans=[Span(text, color=color)],
            glyph_color=color,
            lead=lead,
        )

    def _superpower_segment(self, track: str, lead: float) -> Segment | None:
        """Empire and Federation progress, hidden once the top rank is reached."""
        index = self.state.ranks.get(track)
        if index is None:
            return None
        ladder = ranks.ladder(track)
        if ladder is None or ladder.is_max(index):
            return None
        percent = self.state.rank_progress.get(track)
        color = self.config.overlay.accent
        return Segment(
            glyph=ladder.glyph if self.config.overlay.show_glyphs else None,
            spans=[
                Span(ladder.name(index), color=color),
                Span(f" {percent}%" if percent is not None else "", color=self.config.overlay.foreground, dim=0.75),
            ],
            glyph_color=color,
            lead=lead,
        )

    def _ship_segment(self, lead: float) -> Segment | None:
        ident = self.state.ship_ident
        if not ident:
            return None
        cfg = self.config.overlay
        spans = [Span(ident, color=cfg.foreground, bold=True)]
        if self.state.max_jump_range:
            current = self.state.current_jump_range or self.state.max_jump_range
            spans.append(
                Span(
                    f" ({cfg.labels.jump_max}: {self.state.max_jump_range:.0f} ly"
                    f" | {cfg.labels.jump_current}: {current:.0f} ly)",
                    color=cfg.foreground,
                    dim=0.72,
                    elastic=True,
                )
            )
        return Segment(
            glyph="planet" if cfg.show_glyphs else None,
            spans=spans,
            glyph_color=cfg.foreground,
            lead=lead,
        )

    def _missions_segment(self, lead: float) -> Segment | None:
        capacity = self.config.commander.mission_capacity
        if not capacity or not self.state.missions_known:
            return None
        held = len(self.state.active_missions)
        cfg = self.config.overlay
        color = cfg.danger if held >= capacity else cfg.foreground
        return Segment(
            glyph="signal" if cfg.show_glyphs else None,
            spans=[
                Span(f"{cfg.labels.missions} ", color=cfg.foreground, dim=0.7),
                Span(f"{held}/{capacity}", color=color, bold=True),
            ],
            glyph_color=color,
            lead=lead,
        )

    # -- composition -------------------------------------------------------

    def _compose(self) -> list[Segment]:
        cfg = self.config.overlay
        labels = cfg.labels
        segments: list[Segment] = []
        first = True

        def lead() -> float:
            nonlocal first
            value = 0.0 if first else self._metrics.height() * 0.95
            first = False
            return value

        if self._alert is not None:
            segments.append(self._alert_segment(lead()))
            if not self.state.system.name:
                return segments

        for name in cfg.segments:
            # The alert already names the organic and its value, so the summary
            # segment would only repeat it and push the bar off screen.
            if name == "bio" and self._alert is not None:
                continue
            segment: Segment | None = None
            if name == "carrier":
                segment = self._carrier_segment(lead())
            elif name == "system":
                segment = self._system_segment(lead())
            elif name == "fss":
                segment = self._fss_segment(lead())
            elif name == "bio":
                segment = self._bio_segment(lead())
            if segment is not None:
                segments.append(segment)

        if not segments:
            segments.append(
                Segment(
                    glyph="radar" if cfg.show_glyphs else None,
                    spans=[Span(f" {labels.waiting} ", color=cfg.foreground, dim=0.6)],
                    glyph_color=cfg.foreground,
                    lead=0.0,
                )
            )
        return segments

    def _alert_segment(self, lead: float) -> Segment:
        cfg = self.config.overlay
        alert = self._alert
        assert alert is not None
        color = cfg.accent if alert.confidence is not Confidence.POSSIBLE else cfg.foreground
        spans = [
            Span(f"{alert.title}", color=color, bold=True),
            Span(f"  {format_credits(alert.value)}", color=color, bold=True),
        ]
        if alert.bonus_applies and alert.payout > alert.value:
            spans.append(Span(" ×5 → ", color=cfg.foreground, dim=0.75))
            spans.append(Span(format_credits(alert.payout), color=cfg.success, bold=True))
        if alert.confidence is not Confidence.CONFIRMED:
            spans.append(
                Span(f" {CONFIDENCE_LABEL[alert.confidence]}", color=cfg.foreground, dim=0.7)
            )
        if alert.body:
            spans.append(
                Span(f" · {alert.body}", color=cfg.foreground, dim=0.75, elastic=True)
            )
        return Segment(
            glyph=CONFIDENCE_GLYPH.get(alert.confidence, "star") if cfg.show_glyphs else None,
            spans=spans,
            glyph_color=color,
            lead=lead,
        )

    def _carrier_segment(self, lead: float) -> Segment | None:
        """Either the countdown to a scheduled jump, or the post-jump cooldown.

        The two are mutually exclusive: a jump cannot be requested while the
        carrier is still recharging.
        """
        carrier = self.state.carrier
        cfg = self.config.overlay
        labels = cfg.labels
        remaining = carrier.seconds_until_jump()

        if remaining is not None:
            if remaining <= 60:
                color = cfg.danger
            elif remaining <= 300:
                color = cfg.accent
            else:
                color = cfg.foreground

            spans = [Span(f"{labels.carrier} ", color=cfg.foreground, dim=0.7)]
            if carrier.target_system:
                spans.append(Span(f"{carrier.target_system} ", color=color, bold=True))
            spans.append(Span(format_countdown(remaining), color=color, bold=True))
            return Segment(
                glyph="carrier" if cfg.show_glyphs else None,
                spans=spans,
                glyph_color=color,
                lead=lead,
            )

        if not self.config.carrier.show_cooldown:
            return None

        cooldown = carrier.seconds_until_ready()
        if cooldown is not None:
            # Dim: this is a wait, not an event.
            return Segment(
                glyph="carrier" if cfg.show_glyphs else None,
                spans=[
                    Span(f"{labels.carrier} ", color=cfg.foreground, dim=0.5),
                    Span(f"{labels.carrier_cooldown} ", color=cfg.foreground, dim=0.65),
                    Span(format_countdown(cooldown), color=cfg.foreground, dim=0.85),
                ],
                glyph_color=cfg.foreground,
                lead=lead,
            )

        if carrier.became_ready():
            return Segment(
                glyph="carrier" if cfg.show_glyphs else None,
                spans=[
                    Span(f"{labels.carrier} ", color=cfg.foreground, dim=0.6),
                    Span(labels.carrier_ready, color=cfg.success),
                ],
                glyph_color=cfg.success,
                lead=lead,
            )
        return None

    def _system_segment(self, lead: float) -> Segment | None:
        system = self.state.system
        if not system.name:
            return None
        cfg = self.config.overlay
        spans = [Span(system.name, color=cfg.foreground, bold=True, elastic=True)]
        if system.body_count:
            spans.append(
                Span(f" {system.body_count} {cfg.labels.bodies}", color=cfg.foreground, dim=0.7)
            )
        return Segment(
            glyph="planet" if cfg.show_glyphs else None,
            spans=spans,
            glyph_color=cfg.foreground,
            lead=lead,
        )

    def _fss_segment(self, lead: float) -> Segment | None:
        system = self.state.system
        if not system.name:
            return None
        cfg = self.config.overlay
        percent = system.progress_percent
        color = cfg.success if percent >= 99.5 else cfg.foreground
        return Segment(
            glyph="radar" if cfg.show_glyphs else None,
            spans=[
                Span(f"{cfg.labels.fss} ", color=cfg.foreground, dim=0.7),
                Span(f"{percent:.0f}%", color=color, bold=True),
            ],
            glyph_color=color,
            lead=lead,
        )

    def _bio_segment(self, lead: float) -> Segment | None:
        system = self.state.system
        if not system.name:
            return None
        cfg = self.config.overlay
        total = system.bio_signal_total
        spans: list[Span] = [
            Span(f"{cfg.labels.bio} ", color=cfg.foreground, dim=0.7),
        ]
        if total:
            spans.append(Span(f"{total}", color=cfg.foreground, bold=True))
            if system.bio_body_count > 1:
                spans.append(
                    Span(
                        f" ({system.bio_body_count} {cfg.labels.bio_body})",
                        color=cfg.foreground,
                        dim=0.6,
                    )
                )
        else:
            spans.append(Span("0", color=cfg.foreground, dim=0.55))

        glyph = "bio"
        glyph_color = cfg.foreground
        if system.best_confidence is not Confidence.NONE:
            glyph = CONFIDENCE_GLYPH.get(system.best_confidence, "star")
            glyph_color = (
                cfg.success if system.best_confidence is Confidence.CONFIRMED else cfg.accent
            )
            prefix = (
                "" if system.best_confidence is Confidence.CONFIRMED else cfg.labels.at_least
            )
            label = system.best_species or system.best_genus or system.best_label
            spans.append(
                Span(f"  {prefix}{format_credits(system.best_value)}", color=glyph_color, bold=True)
            )
            if label:
                spans.append(Span(f" {label}", color=cfg.foreground, dim=0.8))

        return Segment(
            glyph=glyph if cfg.show_glyphs else None,
            spans=spans,
            glyph_color=glyph_color,
            lead=lead,
        )

    def row_text(self, row: Row) -> str:
        chunks: list[str] = []
        for segment in row.segments:
            if segment.glyph is not None:
                chunks.append(f"[{segment.glyph}]")
            chunks.append("".join(span.text for span in segment.spans).strip())
        return "  ".join(chunk for chunk in chunks if chunk)

    def bar_text(self) -> str:
        """Every row as one plain string (tests, tooltips, logs)."""
        return " || ".join(
            text for text in (self.row_text(row) for row in self._rows) if text
        )

    def primary_text(self) -> str:
        """Just the main row, which is what most assertions care about."""
        primary = next((row for row in self._rows if row.kind == "primary"), None)
        return self.row_text(primary) if primary is not None else ""

    # -- layout & painting -------------------------------------------------

    def _measure(self, row: Row) -> float:
        """Total width of one row's segments, excluding its padding."""
        style = row.style
        width = 0.0
        for segment in row.segments:
            width += segment.lead
            if segment.glyph is not None:
                width += style.glyph_size + style.glyph_gap
            width += sum(
                style.metrics_for(span.bold).horizontalAdvance(span.text)
                for span in segment.spans
            )
        return width

    def _available_width(self) -> float:
        screen = self._target_screen()
        if screen is None:
            return 4096.0
        margins = 2 * max(16, self.config.overlay.offset_x)
        return float(max(320, screen.availableGeometry().width() - margins))

    def _fit(self, row: Row, limit: float) -> float:
        """Shrink one row until it fits.

        Elastic spans (system and body names) are elided first, each keeping a
        readable floor. If that is still not enough, trailing segments are
        dropped -- so a row's segment order doubles as a priority order, most
        important first.
        """
        style = row.style
        width = self._measure(row)

        elastic: list[tuple[Span, QFontMetricsF, float]] = []
        for segment in row.segments:
            for span in segment.spans:
                if not span.elastic:
                    continue
                metrics = style.metrics_for(span.bold)
                elastic.append((span, metrics, metrics.horizontalAdvance(MIN_ELIDED_CHARS)))

        if width > limit:
            for _ in range(4):
                if width <= limit or not elastic:
                    break
                share = (width - limit) / len(elastic)
                for span, metrics, floor in elastic:
                    current = metrics.horizontalAdvance(span.text)
                    target = int(max(floor, current - share))
                    span.text = metrics.elidedText(span.text, Qt.TextElideMode.ElideRight, target)
                width = self._measure(row)

            dropped: list[str] = []
            while width > limit and len(row.segments) > 1:
                dropped.append(row.segments.pop().glyph or "segment")
                width = self._measure(row)
            if dropped:
                log.debug(
                    "HUD row %s too wide for the screen; dropped %s",
                    row.kind,
                    ", ".join(reversed(dropped)),
                )

            if width > limit:
                # Last resort on a very narrow screen: let the surviving elastic
                # spans shrink past their readable floor. An ellipsis beats
                # drawing off the edge of the display.
                for segment in row.segments:
                    for span in segment.spans:
                        if not span.elastic:
                            continue
                        metrics = style.metrics_for(span.bold)
                        span.text = metrics.elidedText(
                            span.text,
                            Qt.TextElideMode.ElideRight,
                            int(metrics.horizontalAdvance(ELLIPSIS)),
                        )
                width = self._measure(row)
        return width

    def _layout(self) -> None:
        style = self._primary_style
        # Kept for the tests and for the glyph geometry assertions.
        self._padding_x = style.padding_x
        self._padding_y = style.padding_y
        self._glyph_size = style.glyph_size
        self._glyph_gap = style.glyph_gap
        self._plate_radius = style.plate_radius

        limit = self._available_width()
        boxes: list[tuple[Row, float, float, float]] = []
        widest = 0.0
        y = 0.0
        for row in self._rows:
            row_style = row.style
            inner = max(80.0, limit - row_style.padding_x * 2)
            plate_width = self._fit(row, inner) + row_style.padding_x * 2
            plate_height = row_style.line_height + row_style.padding_y * 2
            y += row.gap
            boxes.append((row, y, plate_width, plate_height))
            widest = max(widest, plate_width)
            y += plate_height
        self._row_boxes = boxes

        total_width = int(math.ceil(widest))
        total_height = int(math.ceil(y))

        if self._last_size != (total_width, total_height):
            self._last_size = (total_width, total_height)
            self.resize(total_width, total_height)
            self._reposition()

    # These three are the only places the display logic touches Qt, which keeps
    # the selection rules testable without a real multi-monitor machine.
    @staticmethod
    def screens() -> list:
        """Attached screens, or an empty list where none can be enumerated."""
        try:
            return list(QGuiApplication.screens())
        except Exception:  # pragma: no cover - offscreen platforms
            return []

    @staticmethod
    def primary_screen():
        return QGuiApplication.primaryScreen()

    @staticmethod
    def screen_at(point):
        return QGuiApplication.screenAt(point)

    def _target_screen(self, setting: str | None = None):
        """The display the bar should appear on.

        ``overlay.monitor`` selects it: ``primary`` (the default), ``cursor``
        for the display under the pointer, a zero-based index, or a substring of
        the display name. Anything that cannot be resolved falls back to the
        primary display so a typo in the config never hides the HUD.
        """
        screens = self.screens()
        if not screens:
            return None

        value = (self.config.overlay.monitor if setting is None else setting) or "primary"
        key = value.strip().lower()

        if key in ("cursor", "mouse", "pointer", "auto"):
            try:
                under_cursor = self.screen_at(self.cursor().pos())
            except Exception:  # pragma: no cover - offscreen platforms
                under_cursor = None
            return under_cursor or self.primary_screen()

        if key in ("", "primary", "main", "default"):
            return self.primary_screen()

        if key.lstrip("+-").isdigit():
            index = int(key)
            if 0 <= index < len(screens):
                return screens[index]
            log.warning(
                "overlay.monitor = %s but %d display(s) are attached; using the primary one",
                value,
                len(screens),
            )
            return self.primary_screen()

        for screen in screens:
            if key in screen.name().lower():
                return screen
        log.warning("no display matches overlay.monitor = %r; using the primary one", value)
        return self.primary_screen()

    def reposition(self, *, force: bool = False) -> None:
        """Move the bar now, for callers reacting to a settings change."""
        self._reposition(force=force)

    def screen_label(self) -> str:
        """A short description of where the bar currently is."""
        screen = self._target_screen()
        if screen is None:
            return "нет данных"
        geometry = screen.geometry()
        return f"{screen.name()} ({geometry.width()}x{geometry.height()})"

    @classmethod
    def screen_choices(cls) -> list[tuple[str, str]]:
        """``(value, label)`` pairs for a display picker, primary first."""
        choices: list[tuple[str, str]] = [("primary", "Основной")]
        screens = cls.screens()
        primary = cls.primary_screen() if screens else None
        for index, screen in enumerate(screens):
            geometry = screen.geometry()
            suffix = " — основной" if screen is primary else ""
            choices.append(
                (str(index), f"{index}: {screen.name()} {geometry.width()}x{geometry.height()}{suffix}")
            )
        choices.append(("cursor", "Тот, где курсор мыши"))
        return choices

    def _reposition(self, *, force: bool = False) -> None:
        screen = self._target_screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        cfg = self.config.overlay
        width, height = self.width(), self.height()

        if cfg.position.endswith("left"):
            x = area.left() + cfg.offset_x
        elif cfg.position.endswith("right"):
            x = area.right() - width - cfg.offset_x
        else:
            x = area.left() + (area.width() - width) // 2 + cfg.offset_x

        if cfg.position.startswith("bottom"):
            y = area.bottom() - height - cfg.offset_y
        else:
            y = area.top() + cfg.offset_y

        target = (int(x), int(y))
        # move() on every tick would flicker; only act when the spot changes.
        if force or target != self._last_position:
            self._last_position = target
            self.move(*target)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if not self._row_boxes:
            return
        cfg = self.config.overlay
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        for row, y, plate_width, plate_height in self._row_boxes:
            style = row.style
            if row.opacity <= 0.0:
                continue
            # The offset is applied here rather than in the layout so that a
            # notification sliding into place cannot nudge the rows around it.
            y += row.offset
            left = (self.width() - plate_width) / 2.0
            rect = QRectF(left + 0.5, y + 0.5, plate_width - 1.0, plate_height - 1.0)
            radius = min(rect.height() / 2.0, style.plate_radius)

            if cfg.show_background and row.plate:
                background = QColor(cfg.background)
                background.setAlpha(int(cfg.background_alpha * row.opacity))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(background)
                painter.drawRoundedRect(rect, radius, radius)

            if row.accent:
                accent = QColor(row.accent)
                accent.setAlphaF(row.opacity)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(accent)
                bar = QRectF(
                    rect.left() + style.padding_x * 0.35,
                    rect.top() + rect.height() * 0.26,
                    max(1.5, style.line_height * 0.09),
                    rect.height() * 0.48,
                )
                painter.drawRoundedRect(bar, bar.width() / 2.0, bar.width() / 2.0)

            # The alert outline belongs to the row that carries the alert.
            if row.kind == "primary" and self._alert is not None:
                pulse = 0.55 + 0.45 * math.sin(_monotonic() * 6.0)
                accent = QColor(cfg.accent)
                accent.setAlphaF(min(1.0, 0.45 + 0.55 * pulse))
                pen = QPen(accent)
                pen.setWidthF(1.4)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect, radius, radius)

            cap = cap_height(style.metrics)
            baseline = y + (plate_height + cap) / 2.0
            x = left + style.padding_x

            for segment in row.segments:
                x += segment.lead
                if segment.glyph is not None:
                    glyph_color = QColor(segment.glyph_color or cfg.foreground)
                    if row.opacity < 1.0:
                        glyph_color.setAlphaF(glyph_color.alphaF() * row.opacity)
                    draw_glyph(
                        painter,
                        x,
                        glyph_top(baseline, cap, style.glyph_size),
                        style.glyph_size,
                        segment.glyph,
                        glyph_color,
                    )
                    x += style.glyph_size + style.glyph_gap

                for span in segment.spans:
                    font = style.bold_font if span.bold else style.font
                    metrics = style.metrics_for(span.bold)
                    color = QColor(span.color or cfg.foreground)
                    alpha = color.alphaF() * min(1.0, span.dim) * row.opacity
                    if alpha < 1.0:
                        color.setAlphaF(max(0.0, min(1.0, alpha)))
                    painter.setFont(font)
                    painter.setPen(color)
                    painter.drawText(QPointF(x, baseline), span.text)
                    x += metrics.horizontalAdvance(span.text)

        painter.end()

    # -- Qt overrides ------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._topmost_timer.stop()
        self._screen_timer.stop()
        self._animation_timer.stop()
        super().closeEvent(event)


def _monotonic() -> float:
    import time

    return time.monotonic()
