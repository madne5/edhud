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
from ..formatting import format_countdown, format_credits
from ..state import GameState
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

    def rebuild(self) -> None:
        """Recompute the bar contents, resizing and repositioning if needed."""
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
        return rows

    def _status_segments(self) -> list[Segment]:
        """The always-visible second row."""
        cfg = self.config.overlay
        style = self._status_style
        segments: list[Segment] = []

        for name in cfg.status_segments:
            segment: Segment | None = None
            if name == "mode":
                segment = self._mode_segment(0.0)
            elif name == "ship":
                segment = self._ship_segment(0.0)
            elif name == "missions":
                segment = self._missions_segment(0.0)
            elif name == "next":
                segment = self._next_segment(0.0)
            elif name == "carriers":
                # One segment per carrier, so two of them read as two entries
                # rather than one long line.
                segments.extend(self._carrier_segments())
            elif name == "crime":
                segment = self._crime_segment(0.0)
            if segment is not None:
                segments.append(segment)
        return self._apply_leads(segments, style.metrics.height() * 0.95)

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

    def _ship_segment(self, lead: float) -> Segment | None:
        """The ship's model, with its jump range.

        The ident ("KSS-14") is the commander's own label and says nothing about
        what they are flying, so the model name is shown instead -- Caspian
        Explorer, Panther Clipper Mk II -- falling back to the journal's symbol
        when no event has named that ship yet.
        """
        model = self.state.ship_model or self.state.ship_type
        if not model:
            return None
        cfg = self.config.overlay
        spans = [Span(model, color=cfg.foreground, bold=True)]
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

    def _crime_segment(self, lead: float) -> Segment | None:
        """Notoriety and unpaid fines.

        Hidden entirely for a clean commander, which is the common case and
        would otherwise be a permanent "not wanted" taking up room. Notoriety
        comes from the Statistics event at login, so it is a snapshot rather
        than a live figure; the fines are the part that moves during a session.
        """
        crime = self.state.crime
        if crime.clean:
            return None
        cfg = self.config.overlay
        # Notoriety is what gets a commander shot at, so it leads and it is red.
        colour = cfg.danger if crime.notorious else cfg.foreground
        spans: list[Span] = []
        if crime.notoriety is not None:
            spans.append(Span(f"{cfg.labels.notoriety} ", color=cfg.foreground, dim=0.7))
            spans.append(Span(str(crime.notoriety), color=colour, bold=True))
        if crime.fines:
            if spans:
                spans.append(Span("  ", color=cfg.foreground))
            spans.append(Span(f"{cfg.labels.fines} ", color=cfg.foreground, dim=0.7))
            spans.append(Span(format_credits(crime.fines), color=cfg.danger, bold=True))
        return Segment(
            glyph="warning" if cfg.show_glyphs else None,
            spans=spans,
            glyph_color=colour,
            lead=lead,
        )

    def _carrier_segments(self) -> list[Segment]:
        """Every carrier the commander has: callsign and free hold space.

        Free space is the game's own ``FreeSpace``, not the capacity minus the
        cargo: those two do not agree -- one carrier in the journals reports
        25000 total, 7001 cargo and 5142 free, leaving 12857 unaccounted for --
        so nothing is derived by subtraction here.
        """
        infos = self.state.carriers.known()
        if not infos:
            return []
        cfg = self.config.overlay
        out: list[Segment] = []
        for info in infos:
            free, total = info.hold()
            # A squadron carrier is not the commander's own, so its callsign
            # reads dimmer. The icon carries a different fact: whether anyone
            # may dock, green for open and orange for restricted.
            colour = cfg.foreground if info.squadron else cfg.accent
            role = info.access_role()
            glyph_colour = (
                cfg.success if role == "success"
                else cfg.warning if role == "warning"
                else colour
            )
            spans = [Span(info.callsign, color=colour, bold=True)]
            if total:
                spans.append(
                    Span(f" {cfg.labels.carrier_free} ", color=cfg.foreground, dim=0.7)
                )
                spans.append(Span(f"{free}/{total}", color=colour))
                spans.append(
                    Span(f" {cfg.labels.tonnes}", color=cfg.foreground, dim=0.7)
                )
            out.append(
                Segment(
                    glyph="carrier" if cfg.show_glyphs else None,
                    spans=spans,
                    glyph_color=glyph_colour,
                    lead=0.0,
                )
            )
        return out

    def _next_segment(self, lead: float) -> Segment | None:
        """Where the commander is heading: current system is already shown."""
        plan = self.state.jump_plan
        if not plan.active:
            return None
        cfg = self.config.overlay
        spans = [Span(cfg.labels.jump_next + " ", color=cfg.foreground, dim=0.7)]
        spans.append(Span(plan.target, color=cfg.accent, bold=True))
        detail: list[str] = []
        if plan.star_class:
            detail.append(plan.star_class)
        if plan.remaining > 1:
            detail.append(f"{plan.remaining} {cfg.labels.jumps}")
        if detail:
            spans.append(
                Span(f" ({', '.join(detail)})", color=cfg.foreground, dim=0.72)
            )
        return Segment(
            glyph="compass" if cfg.show_glyphs else None,
            spans=spans,
            glyph_color=cfg.accent,
            lead=lead,
        )

    def _compose(self) -> list[Segment]:
        cfg = self.config.overlay
        labels = cfg.labels
        segments: list[Segment] = []

        for name in cfg.segments:
            segment: Segment | None = None
            if name == "carrier":
                segment = self._carrier_segment(0.0)
            elif name == "system":
                segment = self._system_segment(0.0)
            elif name == "balance":
                segment = self._balance_segment(0.0)
            elif name == "cargo":
                segment = self._cargo_segment(0.0)
            if segment is not None:
                segments.append(segment)

        self._apply_leads(segments, self._metrics.height() * 0.95)

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

    def _cargo_segment(self, lead: float) -> Segment | None:
        """The hold: tonnes carried of the tonnes available.

        Capacity comes from Loadout and the count from the live status file,
        falling back to the Cargo event. Shown in amber once the hold is full,
        because a full hold is why a mining run ends.
        """
        capacity = self.state.cargo_capacity
        if capacity <= 0:
            return None
        cfg = self.config.overlay
        used = max(0, self.state.cargo_count)
        full = used >= capacity
        colour = cfg.danger if full else cfg.accent
        return Segment(
            glyph="cargo" if cfg.show_glyphs else None,
            spans=[
                Span(f"{used}", color=colour, bold=True),
                Span(f"/{capacity}", color=cfg.foreground, dim=0.75),
                Span(f" {cfg.labels.tonnes}", color=cfg.foreground, dim=0.7),
            ],
            glyph_color=colour,
            lead=lead,
        )

    def _balance_segment(self, lead: float) -> Segment | None:
        """The credit balance.

        Nothing in the journal reports the balance changing, so this comes from
        Status.json. The journal's value from the last LoadGame is used until
        the status file reports one, and status_live records which it is, so a
        stale figure is never presented as live.
        """
        if self.state.credits is None:
            return None
        cfg = self.config.overlay
        colour = cfg.success if self.state.status_live else cfg.foreground
        return Segment(
            glyph="scales" if cfg.show_glyphs else None,
            spans=[
                Span(f"{cfg.labels.balance} ", color=cfg.foreground, dim=0.7),
                Span(format_credits(self.state.credits), color=colour, bold=True),
            ],
            glyph_color=colour,
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

    def _apply_leads(self, segments: list[Segment], gap: float) -> list[Segment]:
        """Give each segment a gap before it, but never at the start of a row.

        Deciding the gap at the moment a segment is built is wrong, because a
        segment that turns out to be absent has already consumed the "no gap"
        case: the next segment then inherits a gap that lands at the start of
        the row. The plate width counts it, so the plate stays centred while the
        text inside it shifts right -- which reads as a bigger left margin than
        right, on both rows. Assigning the gaps once the surviving segments are
        known avoids that entirely.
        """
        for index, segment in enumerate(segments):
            segment.lead = 0.0 if index == 0 else gap
        return segments

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

        try:
            index = int(key)
        except ValueError:
            index = None
        if index is not None:
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
        super().closeEvent(event)


def _monotonic() -> float:
    import time

    return time.monotonic()
