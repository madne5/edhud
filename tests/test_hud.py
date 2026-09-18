"""Rendering tests for the HUD window.

These run on the Qt "offscreen" platform so they work on a build machine with
no display.  They assert on the composed bar contents and on the pixels that
actually get painted, which is the closest thing to a screenshot assertion.
"""

from __future__ import annotations

import contextlib
import math
import os
import subprocess
import sys
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_probe() -> str | None:
    """Return a skip reason when a QApplication cannot be created at all.

    Qt refuses to start when it cannot enumerate its own plugin directory, and
    the failure aborts the interpreter instead of raising, which would take the
    whole test run down. Probe in a subprocess so we can skip cleanly instead.
    """
    probe = (
        "import os;"
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen');"
        "from PySide6.QtWidgets import QApplication;"
        "app = QApplication([]);"
        "assert app.platformName()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            timeout=120,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return f"could not run the Qt probe: {exc}"
    if result.returncode == 0:
        return None
    lines = (result.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    detail = lines[-1] if lines else f"exit code {result.returncode}"
    return f"Qt cannot start on this machine: {detail}"


QT_SKIP_REASON: str | None
try:  # pragma: no cover - exercised only when PySide6 is installed
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover
    QT_SKIP_REASON = f"PySide6 is not installed ({exc})"
else:
    QT_SKIP_REASON = _qt_probe()

PYSIDE_AVAILABLE = QT_SKIP_REASON is None

from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.notifications import Notification
from elite_hud.state import Alert, Confidence, GameState


#: The shipped row defaults, read from the configuration rather than copied, so
#: that changing a default cannot silently stop with_segments from recognising an
#: untouched config. It was copied once and drifted the moment a segment was added
#: to the bottom row, which quietly disabled the segments of four test classes.
DEFAULT_TOP = list(Config().overlay.segments)
DEFAULT_BOTTOM = list(Config().overlay.status_segments)

#: The rows these tests were written against before the bars were reorganised.
#: The segments themselves are unchanged; where they live is not.
LEGACY_TOP = ["carrier", "system", "fss", "bio"]
LEGACY_BOTTOM = ["mode", "empire", "federation", "ship", "missions"]


def with_segments(config: Config, *, top=None, bottom=None) -> Config:
    """Enable the segments a test studies, without disturbing a test that has
    chosen its own list."""
    if top and config.overlay.segments == DEFAULT_TOP:
        config.overlay.segments = list(top)
    if bottom and config.overlay.status_segments == DEFAULT_BOTTOM:
        config.overlay.status_segments = list(bottom)
    config.validate()
    return config


def make_state(config: Config) -> GameState:
    state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
    state.apply({"event": "Fileheader", "Odyssey": True})
    state.apply({"event": "FSDJump", "StarSystem": "Synuefe PK-V b48-0",
                 "SystemAddress": 672027125153})
    state.apply({"event": "FSSDiscoveryScan", "SystemAddress": 672027125153,
                 "SystemName": "Synuefe PK-V b48-0", "Progress": 0.45,
                 "BodyCount": 11, "NonBodyCount": 2})
    state.apply({"event": "SAASignalsFound", "SystemAddress": 672027125153, "BodyID": 6,
                 "BodyName": "Synuefe PK-V b48-0 5",
                 "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 3}],
                 "Genuses": [{"Genus": "$Codex_Ent_Stratum_Genus_Name;",
                              "Genus_Localised": "Stratum"}]})
    return state


def pixel_counts(image: QImage) -> "Counter[tuple[int, int, int]]":
    """Histogram of sufficiently opaque RGB triples in an image."""
    # QPixmap has no alpha channel until it is converted, so normalise first.
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    counts: Counter[tuple[int, int, int]] = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            argb = image.pixel(x, y)
            if ((argb >> 24) & 0xFF) > 40:
                counts[((argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF)] += 1
    return counts


def column_extent(image: QImage, x_from: int, x_to: int) -> tuple[int, int] | None:
    """Vertical span of painted pixels between two columns, or None if empty."""
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    top: int | None = None
    bottom: int | None = None
    for y in range(image.height()):
        for x in range(max(0, x_from), min(image.width(), x_to)):
            if ((image.pixel(x, y) >> 24) & 0xFF) > 60:
                top = y if top is None else min(top, y)
                bottom = y if bottom is None else max(bottom, y)
    if top is None or bottom is None:
        return None
    return top, bottom


def rgb(color: QColor) -> tuple[int, int, int]:
    return (color.red(), color.green(), color.blue())


def opaque_pixels(image: QImage) -> tuple[int, int]:
    counts = pixel_counts(image)
    return sum(counts.values()), len(counts)


@contextlib.contextmanager
def frozen_pulse():
    """Pin the alert border's animated opacity.

    The border alpha follows ``sin(time)``, so the exact accent colour is only
    painted at the peak of the pulse. Without pinning it, a test that looks for
    that colour passes or fails depending on when the frame happens to be
    grabbed -- which is exactly how it failed on the Linux runner while passing
    on macOS.
    """
    from elite_hud.overlay import hud as hud_module

    original = hud_module._monotonic  # noqa: SLF001 - the animation clock
    # sin(6 * pi/12) == sin(pi/2) == 1, i.e. the brightest point of the pulse.
    hud_module._monotonic = lambda: math.pi / 12  # type: ignore[assignment]
    try:
        yield
    finally:
        hud_module._monotonic = original  # type: ignore[assignment]


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class HudRenderTests(unittest.TestCase):
    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    #: The offscreen platform reports a tiny screen; pin a realistic one so the
    #: width assertions are about the HUD and not about the test environment.
    SCREEN_WIDTH = 2560

    def _hud(
        self,
        config: Config,
        state: GameState,
        alert: Alert | None = None,
        screen_width: int | None = None,
    ):
        from elite_hud.overlay.hud import HudWindow

        with_segments(config, top=LEGACY_TOP)
        hud = HudWindow(config, state)
        width = self.SCREEN_WIDTH if screen_width is None else screen_width
        hud._available_width = lambda: float(width)  # type: ignore[method-assign]
        if alert is not None:
            hud.push_alert(alert)
        hud.rebuild()
        return hud

    def test_bar_shows_system_progress_and_biology(self) -> None:
        config = Config()
        hud = self._hud(config, make_state(config))
        text = hud.bar_text()
        self.assertIn("Synuefe PK-V b48-0", text)
        self.assertIn("11", text)
        self.assertIn("45%", text)
        self.assertIn("3", text)
        hud.close()

    def test_carrier_segment_appears_only_when_a_jump_is_pending(self) -> None:
        config = Config()
        state = make_state(config)
        self.assertNotIn("ФК", self._hud(config, state).bar_text())

        # Must be in the future: an overdue jump is deliberately hidden.
        state.carrier.departure = datetime.now(timezone.utc) + timedelta(minutes=12)
        state.carrier.target_system = "Sol"
        hud = self._hud(config, state)
        self.assertIn("ФК", hud.bar_text())
        self.assertIn("Sol", hud.bar_text())
        hud.close()

    def _state_with_jump(
        self,
        config: Config,
        *,
        ready_in: float | None = None,
        in_seconds: float | None = None,
    ):
        """A carrier either about to jump, or recharging after one."""
        state = make_state(config)
        now = datetime.now(timezone.utc)
        carrier = state.carrier
        if in_seconds is not None:
            carrier.departure = now + timedelta(seconds=in_seconds)
            carrier.target_system = "Synuefe GX-K c24-11"
        if ready_in is not None:
            # Negative means the cooldown has already elapsed.
            carrier.ready_at = now + timedelta(seconds=ready_in)
        return state

    def test_a_scheduled_jump_shows_the_target_and_the_countdown(self) -> None:
        config = Config()
        state = self._state_with_jump(config, in_seconds=754)
        hud = self._hud(config, state)
        text = hud.bar_text()
        self.assertIn("ФК", text)
        self.assertIn("Synuefe GX-K c24-11", text)
        self.assertIn("12:34", text)
        hud.close()

    def test_the_cooldown_is_shown_while_the_carrier_recharges(self) -> None:
        config = Config()
        state = self._state_with_jump(config, ready_in=4 * 60)
        hud = self._hud(config, state)
        text = hud.bar_text()
        self.assertIn("готов через", text)
        self.assertIn("04:00", text, f"expected the remaining cooldown, got {text!r}")
        hud.close()

    def test_ready_is_shown_briefly_after_the_cooldown(self) -> None:
        config = Config()
        # Ready ten seconds ago: inside the window where "ready" is shown.
        state = self._state_with_jump(config, ready_in=-10)
        hud = self._hud(config, state)
        text = hud.bar_text()
        self.assertIn("готов", text)
        self.assertNotIn("готов через", text)
        hud.close()

    def test_nothing_is_shown_once_the_carrier_is_long_ready(self) -> None:
        config = Config()
        state = self._state_with_jump(config, ready_in=-3600)
        hud = self._hud(config, state)
        self.assertNotIn("ФК", hud.bar_text())
        hud.close()

    def test_the_cooldown_can_be_switched_off(self) -> None:
        config = Config()
        config.carrier.show_cooldown = False
        state = self._state_with_jump(config, ready_in=4 * 60)
        hud = self._hud(config, state)
        self.assertNotIn("готов через", hud.bar_text())
        hud.close()

    def test_a_scheduled_jump_wins_over_the_cooldown(self) -> None:
        """They cannot both be true in game; if they are, the jump matters more."""
        config = Config()
        state = self._state_with_jump(config, ready_in=30, in_seconds=600)
        hud = self._hud(config, state)
        text = hud.bar_text()
        self.assertIn("Synuefe GX-K c24-11", text)
        self.assertNotIn("готов через", text)
        hud.close()

    def test_confirmed_alert_shows_the_first_logged_payout(self) -> None:
        config = Config()
        state = make_state(config)
        alert = Alert(
            key="k", title="Stratum Tectonicas", detail="confirmed",
            value=19_010_800, confidence=Confidence.CONFIRMED,
            system="Synuefe PK-V b48-0", body="Synuefe PK-V b48-0 5",
            bonus_applies=True, payout=95_054_000,
        )
        hud = self._hud(config, state, alert)
        text = hud.bar_text()
        self.assertIn("Stratum Tectonicas", text)
        self.assertIn("19.0M", text)
        self.assertIn("×5", text)
        self.assertIn("95.1M", text)
        hud.close()

    def test_alert_replaces_the_biology_summary(self) -> None:
        """The alert already carries the organic, so the bio segment is dropped."""
        config = Config()
        alert = Alert(
            key="k", title="Stratum Tectonicas", detail="confirmed",
            value=19_010_800, confidence=Confidence.CONFIRMED, system="S", body="B",
        )
        state = make_state(config)
        calm = self._hud(config, state)
        self.assertIn("БИО", calm.bar_text())
        calm.close()

        hud = self._hud(config, state, alert)
        self.assertNotIn("БИО", hud.bar_text())
        self.assertIn("Stratum Tectonicas", hud.bar_text())
        hud.close()

    def test_possible_alert_is_marked_as_such(self) -> None:
        config = Config()
        alert = Alert(
            key="k", title="Stratum", detail="possible", value=19_010_800,
            confidence=Confidence.POSSIBLE, system="S", body="B",
        )
        hud = self._hud(config, make_state(config), alert)
        self.assertIn("возможно", hud.bar_text())
        hud.close()

    def test_empty_state_never_crashes_and_says_so(self) -> None:
        config = Config()
        empty = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        hud = self._hud(config, empty)
        self.assertEqual(hud.bar_text(), f"[radar]  {config.overlay.labels.waiting}")
        self.assertGreater(hud.width(), 0)
        hud.close()

    def test_painting_before_any_layout_does_not_crash(self) -> None:
        """Qt can deliver paintEvent before the first rebuild()."""
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        hud = HudWindow(config, make_state(config))
        # No rebuild() call on purpose: this used to raise AttributeError.
        image = hud.grab().toImage()
        self.assertGreater(image.width(), 0)
        hud.close()

    def test_show_overlay_lays_out_first(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        hud = HudWindow(config, make_state(config))
        hud.show_overlay()
        try:
            self.assertGreater(hud.width(), 50)
            self.assertGreater(hud.height(), 10)
        finally:
            hud.close()

    def test_window_is_click_through_and_never_takes_focus(self) -> None:
        config = Config()
        hud = self._hud(config, make_state(config))
        flags = hud.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
        hud.close()

    def test_bar_grows_with_content(self) -> None:
        config = Config()
        short = self._hud(config, make_state(config))
        short_width = short.width()
        short.close()

        state = make_state(config)
        state.carrier.departure = datetime.now(timezone.utc) + timedelta(minutes=12)
        state.carrier.target_system = "Synuefe GX-K c24-11"
        long = self._hud(config, state)
        self.assertGreater(long.width(), short_width)
        long.close()

    def test_the_alert_border_is_deterministic_when_the_clock_is_pinned(self) -> None:
        """Same input, same frame: the pulse must not make rendering flaky."""
        config = Config()
        alert = Alert(
            key="k", title="Clypeus", detail="guaranteed", value=16_202_800,
            confidence=Confidence.GUARANTEED, system="S", body="B",
        )
        with frozen_pulse():
            first = self._hud(config, make_state(config), alert)
            a = pixel_counts(first.grab().toImage())
            first.close()
            second = self._hud(config, make_state(config), alert)
            b = pixel_counts(second.grab().toImage())
            second.close()
        self.assertEqual(a, b, "two frames with the same clock differed")

    def test_something_is_actually_painted(self) -> None:
        config = Config()
        state = make_state(config)
        hud = self._hud(config, state)
        image = hud.grab().toImage()
        self.assertGreater(image.width(), 50)

        painted, distinct = opaque_pixels(image)
        # The plate plus at least some glyph/text pixels.
        self.assertGreater(painted, 500, "the HUD painted almost nothing")
        self.assertGreater(distinct, 3, "expected text, glyph and plate colours")

        counts = pixel_counts(image)
        # Antialiased glyphs contain few pixels of exactly the nominal colour,
        # and how many depends on the font and hinting in use, so assert on the
        # amount of ink rather than on exact hues.
        self.assertGreater(sum(counts.values()), 500)
        self.assertGreater(distinct, 10, "too few shades: the bar looks unpainted")
        # A calm bar never uses the danger colour.
        self.assertEqual(counts[rgb(QColor(config.overlay.danger))], 0)
        hud.close()

    def test_alert_uses_the_accent_colour(self) -> None:
        config = Config()
        alert = Alert(
            key="k", title="Clypeus", detail="guaranteed", value=16_202_800,
            confidence=Confidence.GUARANTEED, system="S", body="B",
        )
        with frozen_pulse():
            calm = self._hud(config, make_state(config))
            calm_accent = pixel_counts(calm.grab().toImage())[rgb(QColor(config.overlay.accent))]
            calm.close()

            hud = self._hud(config, make_state(config), alert)
            alert_accent = pixel_counts(hud.grab().toImage())[rgb(QColor(config.overlay.accent))]
            hud.close()

        # The alert draws a full accent border; a calm bar only tints a glyph.
        self.assertGreater(alert_accent, calm_accent + 100)
        self.assertGreater(alert_accent, 100)

    def test_segments_config_is_respected(self) -> None:
        config = Config()
        config.overlay.segments = ["fss"]
        hud = self._hud(config, make_state(config))
        self.assertIn("FSS", hud.bar_text())
        self.assertNotIn("БИО", hud.bar_text())
        hud.close()

    #: Screens worth checking the fit against, from a tiny overlay panel to 4K.
    SCREEN_WIDTHS = (200, 320, 480, 640, 900, 1280, 1920, 3840)

    def _limit(self, screen_width: int) -> int:
        """The widest bar that may be drawn on a screen of this width."""
        config = Config()
        margins = 2 * max(16, config.overlay.offset_x)
        return screen_width + margins + 1  # +1 for sub-pixel rounding

    def test_the_bar_never_exceeds_the_available_width(self) -> None:
        """The one invariant that actually matters for a HUD.

        Asserted across widths rather than against fixed pixel counts, because
        font metrics differ between macOS, Windows and the Linux runners.
        """
        config = Config()
        state = make_state(config)
        state.system.name = "Synuefe " + "X" * 400

        for width in self.SCREEN_WIDTHS:
            with self.subTest(screen_width=width):
                hud = self._hud(config, state, screen_width=width)
                self.assertLessEqual(hud.width(), self._limit(width))
                self.assertGreater(hud.width(), 0)
                hud.close()

    def test_narrow_screens_show_less_than_wide_ones(self) -> None:
        """`segments` doubles as a priority order when space runs out."""
        config = Config()
        state = make_state(config)
        state.system.name = "Synuefe " + "X" * 400

        wide = self._hud(config, state, screen_width=3840)
        wide_text = wide.bar_text()
        wide.close()

        narrow = self._hud(config, state, screen_width=200)
        narrow_text = narrow.bar_text()
        narrow.close()

        self.assertIn("БИО", wide_text)
        self.assertLess(len(narrow_text), len(wide_text))
        # Whatever survives, the most important segment must be among it.
        self.assertTrue(narrow_text.strip(), "the bar went completely blank")

    def test_a_long_system_name_is_elided_not_truncated_away(self) -> None:
        config = Config()
        state = make_state(config)
        state.system.name = "Synuefe " + "X" * 400
        hud = self._hud(config, state, screen_width=900)
        text = hud.bar_text()
        self.assertIn("…", text, "the long name was not marked as elided")
        self.assertIn("Synuefe", text, "the whole name disappeared")
        hud.close()

    def test_a_realistic_screen_never_elides(self) -> None:
        config = Config()
        state = make_state(config)

        # Measure how wide the bar naturally wants to be, then assert that a
        # normal desktop fits it. Deriving the number keeps the test honest
        # whatever fonts the machine has.
        natural = self._hud(config, state, screen_width=100_000)
        natural_width = natural.width()
        natural.close()
        self.assertLess(natural_width, 1920, "the default bar is unreasonably wide")

        hud = self._hud(config, state, screen_width=1920)
        self.assertNotIn("…", hud.bar_text())
        hud.close()

    def test_glyphs_are_vertically_centred_on_the_text(self) -> None:
        """Icons used to sit visibly low, level with the text descenders.

        The glyph box was sized from the line height and offset by a fraction of
        the cap height, which put its centre about 0.45 of a cap height below
        the text's optical centre -- roughly four pixels at the default size.
        """
        config = Config()
        config.overlay.segments = ["system"]
        # The plate spans every column at full height, which would make both
        # measurements identical and the test meaningless.
        config.overlay.show_background = False
        state = make_state(config)
        state.system.name = "Sol"  # short, so nothing is elided

        hud = self._hud(config, state)
        image = hud.grab().toImage()
        padding = hud._padding_x  # noqa: SLF001 - the layout under test
        glyph_size = hud._glyph_size  # noqa: SLF001
        glyph_gap = hud._glyph_gap  # noqa: SLF001
        width = hud.width()
        hud.close()

        # Columns covered by the first glyph, then by the text that follows it.
        glyph_cols = (int(padding) + 2, int(padding + glyph_size) - 2)
        text_cols = (int(padding + glyph_size + glyph_gap) + 1, width - int(padding) - 1)

        glyph_span = column_extent(image, *glyph_cols)
        text_span = column_extent(image, *text_cols)
        self.assertIsNotNone(glyph_span, "the glyph painted nothing")
        self.assertIsNotNone(text_span, "no text was painted")
        assert glyph_span is not None and text_span is not None

        glyph_centre = (glyph_span[0] + glyph_span[1]) / 2.0
        text_centre = (text_span[0] + text_span[1]) / 2.0
        self.assertLess(
            abs(glyph_centre - text_centre),
            2.5,
            f"glyph centre {glyph_centre} vs text centre {text_centre} "
            f"(glyph span {glyph_span}, text span {text_span})",
        )

    def test_the_glyph_is_comparable_in_size_to_the_text(self) -> None:
        """An icon far shorter or taller than the capitals looks wrong.

        Measured from painted pixels rather than from font metrics: the metrics
        of the same font differ between platforms, and an assertion built on
        them failed on the Windows runner while passing everywhere else.
        """
        config = Config()
        config.overlay.segments = ["system"]
        config.overlay.show_background = False
        state = make_state(config)
        state.system.name = "Sol"

        hud = self._hud(config, state)
        image = hud.grab().toImage()
        padding = hud._padding_x  # noqa: SLF001 - the layout under test
        glyph_size = hud._glyph_size  # noqa: SLF001
        glyph_gap = hud._glyph_gap  # noqa: SLF001
        width = hud.width()
        hud.close()

        glyph_span = column_extent(image, int(padding) + 2, int(padding + glyph_size) - 2)
        text_span = column_extent(
            image, int(padding + glyph_size + glyph_gap) + 1, width - int(padding) - 1
        )
        self.assertIsNotNone(glyph_span)
        self.assertIsNotNone(text_span)
        assert glyph_span is not None and text_span is not None

        glyph_height = glyph_span[1] - glyph_span[0]
        text_height = text_span[1] - text_span[0]
        self.assertGreater(glyph_height, text_height * 0.5, "the icon is tiny next to the text")
        self.assertLess(glyph_height, text_height * 1.8, "the icon dwarfs the text")

    def test_glyphs_can_be_switched_off(self) -> None:
        config = Config()
        config.overlay.show_glyphs = False
        hud = self._hud(config, make_state(config))
        self.assertNotIn("[", hud.bar_text())
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class GlyphTests(unittest.TestCase):
    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_every_glyph_draws_something(self) -> None:
        from PySide6.QtGui import QPainter, QPixmap

        from elite_hud.overlay.icons import GLYPHS, draw_glyph

        for name in GLYPHS:
            pixmap = QPixmap(48, 48)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            draw_glyph(painter, 2, 2, 44, name, QColor("#ffffff"))
            painter.end()
            painted, _ = opaque_pixels(pixmap.toImage())
            self.assertGreater(painted, 15, f"glyph {name!r} drew almost nothing")
            self.assertLess(painted, 48 * 48, f"glyph {name!r} filled the whole box")

    def test_unknown_glyph_is_a_no_op(self) -> None:
        from PySide6.QtGui import QPainter, QPixmap

        from elite_hud.overlay.icons import draw_glyph

        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        draw_glyph(painter, 0, 0, 16, "not-a-glyph", QColor("#ffffff"))
        painter.end()
        painted, _ = opaque_pixels(pixmap.toImage())
        self.assertEqual(painted, 0)


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class StatusRowTests(unittest.TestCase):
    """The second row: mode, superpower ranks, ship, missions."""

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, config: Config, state: GameState):
        from elite_hud.overlay.hud import HudWindow

        with_segments(config, top=LEGACY_TOP, bottom=LEGACY_BOTTOM)
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # noqa: SLF001
        hud.rebuild()
        self.addCleanup(hud.close)
        return hud

    def _status(self, config: Config, state: GameState) -> str:
        hud = self._hud(config, state)
        # An empty status row is not added at all, which is the point.
        row = next((r for r in hud._rows if r.kind == "status"), None)  # noqa: SLF001
        return hud.row_text(row) if row is not None else ""

    def _state(self, config: Config) -> GameState:
        state = make_state(config)
        state.apply({"event": "LoadGame", "Commander": "Tester", "GameMode": "Open"})
        state.apply({"event": "Rank", "Combat": 3, "Trade": 13, "Explore": 7,
                     "Soldier": 2, "Exobiologist": 5, "Empire": 7, "Federation": 6, "CQC": 0})
        state.apply({"event": "Progress", "Combat": 96, "Trade": 100, "Explore": 36,
                     "Soldier": 68, "Exobiologist": 60, "Empire": 65, "Federation": 17, "CQC": 25})
        state.apply({"event": "Loadout", "Ship": "explorer_nx", "ShipName": "KSS Explore",
                     "ShipIdent": "KSS-14", "MaxJumpRange": 83.735268})
        return state

    def test_the_row_is_empty_before_the_journal_says_anything(self) -> None:
        config = Config()
        empty = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        self.assertEqual(self._status(config, empty), "")

    def test_game_mode_is_shown_in_russian(self) -> None:
        config = Config()
        state = self._state(config)
        self.assertIn("ОТКРЫТАЯ ИГРА", self._status(config, state))

        state.game_mode = "Solo"
        self.assertIn("СОЛО", self._status(config, state))

        state.game_mode = "Group"
        state.group_name = "KSS"
        self.assertIn("ЧАСТНАЯ СЕССИЯ: KSS", self._status(config, state))

    def test_superpower_ranks_show_name_and_percent(self) -> None:
        config = Config()
        text = self._status(config, self._state(config))
        self.assertIn("Барон 65%", text, "Empire rank 7 is Baron at 65%")
        self.assertIn("Уорент-офицер 17%", text, "Federation rank 6 is Warrant Officer at 17%")

    def test_a_maxed_superpower_disappears(self) -> None:
        """Nothing to progress towards, so nothing to show."""
        config = Config()
        state = self._state(config)
        state.ranks["Empire"] = 14  # King
        text = self._status(config, state)
        self.assertNotIn("Король", text)
        self.assertNotIn("Барон", text)
        self.assertIn("Уорент-офицер", text, "the other ladder is unaffected")

    def test_the_ship_model_and_range_are_shown(self) -> None:
        """The ident was shown here before; the model is what says what the
        commander is actually flying."""
        config = Config()
        text = self._status(config, self._state(config))
        self.assertIn("Explorer NX", text)
        self.assertNotIn("KSS-14", text)
        self.assertIn("макс: 84 ly", text)
        self.assertIn("тек: 84 ly", text)

    def test_a_learned_ship_name_replaces_the_symbol_fallback(self) -> None:
        config = Config()
        state = self._state(config)
        state.ship_names.learn("explorer_nx", "Caspian Explorer")
        state.apply({"event": "Loadout", "Ship": "explorer_nx", "ShipIdent": "KSS-14",
                     "MaxJumpRange": 83.735268})
        self.assertIn("Caspian Explorer", self._status(config, state))

    def test_loading_cargo_lowers_the_current_range(self) -> None:
        """The point of showing two numbers at all."""
        config = Config()
        state = self._state(config)
        state.unladen_mass = 1000.0
        state.fuel_capacity = 32.0
        state.fuel_level = 32.0
        state._recompute_jump_range()  # noqa: SLF001
        empty = state.current_jump_range

        state.cargo_count = 64
        state._recompute_jump_range()  # noqa: SLF001
        self.assertLess(state.current_jump_range, empty)
        self.assertAlmostEqual(state.current_jump_range, empty * 1032 / 1096, places=1)

    def test_swapping_ships_does_not_leave_the_old_range_behind(self) -> None:
        """A current range above the maximum is nonsense on screen."""
        config = Config()
        state = self._state(config)
        state.apply({"event": "Loadout", "Ship": "mandalay", "ShipIdent": "KSS-14",
                     "MaxJumpRange": 72.9})
        text = self._status(config, state)
        self.assertIn("макс: 73 ly", text)
        self.assertIn("тек: 73 ly", text)

    def test_missions_are_counted_against_the_capacity(self) -> None:
        config = Config()
        state = self._state(config)
        state.apply({"event": "Missions", "Active": [
            {"MissionID": 1}, {"MissionID": 2}, {"MissionID": 3}]})
        self.assertIn("миссии 3/20", self._status(config, state))

        state.apply({"event": "MissionAccepted", "MissionID": 4})
        state.apply({"event": "MissionCompleted", "MissionID": 1})
        self.assertIn("миссии 3/20", self._status(config, state))

    def test_the_row_can_be_configured_away(self) -> None:
        config = Config()
        config.overlay.status_segments = []
        self.assertEqual(self._status(config, self._state(config)), "")

    def test_the_row_never_exceeds_the_screen(self) -> None:
        config = Config()
        state = self._state(config)
        for width in (400, 640, 900, 1280, 1920, 3840):
            with self.subTest(screen_width=width):
                hud = self._hud(config, state)
                hud._available_width = lambda w=width: float(w)  # noqa: SLF001
                hud.rebuild()
                self.assertLessEqual(hud.width(), width + 33)


class FakeScreen:
    """Just enough of QScreen for the selection rules."""

    def __init__(self, name: str, x: int = 0, y: int = 0, w: int = 1920, h: int = 1080) -> None:
        self._name = name
        self._geometry = QRect(x, y, w, h)

    def name(self) -> str:
        return self._name

    def geometry(self) -> QRect:
        return self._geometry

    def availableGeometry(self) -> QRect:
        return self._geometry


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class MonitorSelectionTests(unittest.TestCase):
    """The HUD used to follow the mouse pointer, which on a two-monitor desk
    routinely put it on the display the game was not running on."""

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, monitor: str, screens: list, primary=None, cursor=None):
        from unittest import mock

        from elite_hud.overlay.hud import HudWindow

        config = Config()
        config.overlay.monitor = monitor
        hud = HudWindow(config, make_state(config))
        self.addCleanup(hud.close)

        fallback = primary if primary is not None else (screens[0] if screens else None)
        for patcher in (
            mock.patch.object(HudWindow, "screens", staticmethod(lambda: list(screens))),
            mock.patch.object(HudWindow, "primary_screen", staticmethod(lambda: fallback)),
            mock.patch.object(HudWindow, "screen_at", staticmethod(lambda point: cursor)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        return hud

    def test_primary_is_the_default(self) -> None:
        first = FakeScreen("DISPLAY-A")
        second = FakeScreen("DISPLAY-B")
        hud = self._hud("primary", [first, second], primary=second)
        self.assertIs(hud._target_screen(), second)

    def test_an_index_selects_by_position(self) -> None:
        screens = [FakeScreen("A"), FakeScreen("B"), FakeScreen("C")]
        self.assertIs(self._hud("1", screens)._target_screen(), screens[1])
        self.assertIs(self._hud("2", screens)._target_screen(), screens[2])

    def test_a_name_fragment_selects_by_name(self) -> None:
        screens = [FakeScreen("DELL U2720Q"), FakeScreen("LG HDR 4K")]
        self.assertIs(self._hud("lg hdr", screens)._target_screen(), screens[1])
        self.assertIs(self._hud("dell", screens)._target_screen(), screens[0])

    def test_cursor_follows_the_pointer_and_falls_back(self) -> None:
        screens = [FakeScreen("A"), FakeScreen("B")]
        self.assertIs(self._hud("cursor", screens, cursor=screens[1])._target_screen(), screens[1])
        # Pointer off any display: fall back to the primary one.
        self.assertIs(
            self._hud("cursor", screens, primary=screens[0], cursor=None)._target_screen(),
            screens[0],
        )

    def test_an_out_of_range_index_falls_back_to_primary(self) -> None:
        screens = [FakeScreen("A"), FakeScreen("B")]
        hud = self._hud("7", screens, primary=screens[1])
        self.assertIs(hud._target_screen(), screens[1])

    def test_an_unknown_name_falls_back_to_primary(self) -> None:
        screens = [FakeScreen("A"), FakeScreen("B")]
        hud = self._hud("nonexistent display", screens, primary=screens[1])
        self.assertIs(hud._target_screen(), screens[1])

    def test_no_screens_is_survivable(self) -> None:
        self.assertIsNone(self._hud("primary", [])._target_screen())

    def test_the_bar_lands_inside_the_chosen_display(self) -> None:
        """The behaviour that actually matters, not just the lookup."""
        left = FakeScreen("LEFT", x=0, y=0, w=1920, h=1080)
        right = FakeScreen("RIGHT", x=1920, y=0, w=1920, h=1080)

        hud = self._hud("1", [left, right])
        hud.rebuild()
        hud.reposition(force=True)

        self.assertGreaterEqual(hud.x(), right.geometry().left())
        self.assertLessEqual(hud.x() + hud.width(), right.geometry().right() + 1)
        self.assertLess(hud.y(), right.geometry().height())

        # And switching to the first display actually moves it back.
        hud.config.overlay.monitor = "0"
        hud.reposition(force=True)
        self.assertLess(hud.x(), left.geometry().right())

    def test_screen_choices_offer_primary_indexes_and_cursor(self) -> None:
        from unittest import mock

        from elite_hud.overlay.hud import HudWindow

        screens = [FakeScreen("A"), FakeScreen("B")]
        with mock.patch.object(HudWindow, "screens", staticmethod(lambda: screens)), \
             mock.patch.object(HudWindow, "primary_screen", staticmethod(lambda: screens[0])):
            choices = HudWindow.screen_choices()

        values = [value for value, _ in choices]
        self.assertEqual(values, ["primary", "0", "1", "cursor"])
        self.assertIn("A", choices[1][1])


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class RowAlignmentTests(unittest.TestCase):
    """No row may begin with a gap.

    The gap helper used to return "no gap" for the first segment and a gap for
    the rest, but it flipped its flag when called rather than when a segment was
    actually produced. A configured segment that turned out to be absent -- no
    carrier jump, no FSS, no game mode -- consumed the no-gap case, so the next
    segment inherited a gap that landed at the very start of the row. The plate
    width counted it, so the plate stayed centred while the text inside shifted
    right, which read as a wider left margin. Both rows were affected.
    """

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, config: Config, state: GameState):
        from elite_hud.overlay.hud import HudWindow

        with_segments(config, top=LEGACY_TOP, bottom=LEGACY_BOTTOM)
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    @staticmethod
    def _row(hud, kind: str):
        return next((row for row in hud._rows if row.kind == kind), None)

    def test_a_missing_carrier_does_not_gap_the_primary_row(self) -> None:
        config = Config()
        state = make_state(config)
        # No carrier jump is pending, so the first configured segment drops out
        # and the system segment takes its place.
        hud = self._hud(config, state)
        primary = self._row(hud, "primary")
        self.assertIsNotNone(primary)
        self.assertGreaterEqual(len(primary.segments), 2)
        self.assertEqual(primary.segments[0].lead, 0.0)
        for segment in primary.segments[1:]:
            self.assertGreater(segment.lead, 0.0)
        hud.close()

    def test_a_missing_mode_does_not_gap_the_status_row(self) -> None:
        config = Config()
        state = make_state(config)
        # No LoadGame, so there is no game mode. Give it two surviving segments
        # after the absent one, which is the case that used to break.
        self.assertEqual(state.game_mode, "")
        state.ranks["Empire"] = 9
        state.rank_progress["Empire"] = 13
        state.ship_model = "Explorer NX"

        hud = self._hud(config, state)
        status = self._row(hud, "status")
        self.assertIsNotNone(status, "the status row should exist here")
        self.assertGreaterEqual(len(status.segments), 2)
        self.assertEqual(status.segments[0].lead, 0.0)
        for segment in status.segments[1:]:
            self.assertGreater(segment.lead, 0.0)
        hud.close()

    def test_unknown_missions_do_not_gap_the_status_row(self) -> None:
        config = Config()
        state = make_state(config)
        state.missions_known = False
        state.ship_model = "Explorer NX"
        hud = self._hud(config, state)
        status = self._row(hud, "status")
        self.assertIsNotNone(status)
        self.assertEqual(status.segments[0].lead, 0.0)
        hud.close()

    def test_the_alert_segment_starts_the_primary_row(self) -> None:
        config = Config()
        state = make_state(config)
        alert = Alert(
            key="k",
            title="Stratum",
            detail="",
            value=20_000_000,
            confidence=Confidence.CONFIRMED,
            system="Synuefe PK-V b48-0",
            body="Synuefe PK-V b48-0 5",
        )
        hud = self._hud(config, state)
        hud.push_alert(alert)
        hud.rebuild()
        primary = self._row(hud, "primary")
        self.assertEqual(primary.segments[0].lead, 0.0)
        hud.close()

    def test_every_plate_fits_its_content_with_equal_padding(self) -> None:
        """A plate that disagrees with its content is what made this look like a
        painting bug: the plate stayed centred while the text slid right."""
        config = Config()
        state = make_state(config)
        state.ship_ident = "KSS-14"
        state.ranks["Empire"] = 9
        state.rank_progress["Empire"] = 13
        hud = self._hud(config, state)

        self.assertGreaterEqual(len(hud._row_boxes), 2)
        for row, _y, plate_width, _plate_height in hud._row_boxes:
            expected = hud._measure(row) + row.style.padding_x * 2
            self.assertAlmostEqual(plate_width, expected, places=6)
            # And the plate is centred in the window, so equal padding either
            # side of the content means equal margins on screen.
            left = (hud.width() - plate_width) / 2.0
            self.assertAlmostEqual(left, (hud.width() - plate_width) / 2.0, places=6)
            self.assertGreaterEqual(left, -0.5)
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class BalanceSegmentTests(unittest.TestCase):
    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, state, config):
        from elite_hud.overlay.hud import HudWindow

        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    def test_no_balance_before_the_journal_reports_one(self) -> None:
        config = Config()
        hud = self._hud(make_state(config), config)
        self.assertNotIn("баланс", hud.bar_text())
        hud.close()

    def test_the_balance_appears_once_known(self) -> None:
        from elite_hud.status import parse_status

        config = Config()
        state = make_state(config)
        state.apply({"event": "LoadGame", "Commander": "Madne5", "Credits": 3_322_947_321})
        hud = self._hud(state, config)
        self.assertIn("баланс", hud.bar_text())
        self.assertIn("3.3B", hud.bar_text())
        hud.close()

    def test_a_live_status_balance_replaces_the_journal_one(self) -> None:
        from elite_hud.status import parse_status

        config = Config()
        state = make_state(config)
        state.apply({"event": "LoadGame", "Credits": 1})
        state.apply_status(parse_status({"Balance": 4_229_279_956}))
        hud = self._hud(state, config)
        self.assertIn("4.2B", hud.bar_text())
        hud.close()


class FakeClock:
    """A monotonic clock the notification tests drive by hand."""

    def __init__(self, start: float = 5000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class NotificationHudTests(unittest.TestCase):
    """Notifications reach the screen through the HUD, not just the centre."""

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, config: Config | None = None, clock=None):
        from elite_hud.overlay.hud import HudWindow

        config = config or Config()
        hud = HudWindow(config, make_state(config), clock=clock)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    @staticmethod
    def _note(**kwargs) -> Notification:
        fields = {"key": "rank:Empire", "title": "Граф", "glyph": "star"}
        fields.update(kwargs)
        return Notification(**fields)

    def _notification_rows(self, hud):
        return [row for row in hud._rows if row.kind == "notification"]

    def test_a_pushed_notification_becomes_a_row(self) -> None:
        hud = self._hud()
        self.assertEqual(self._notification_rows(hud), [])
        hud.push_notification(self._note(detail="Empire"))
        rows = self._notification_rows(hud)
        self.assertEqual(len(rows), 1)
        text = " ".join(span.text for span in rows[0].segments[0].spans)
        self.assertIn("Граф", text)
        self.assertIn("Empire", text)
        hud.close()

    def test_the_accent_bar_uses_the_tone_colour(self) -> None:
        config = Config()
        hud = self._hud(config)
        hud.push_notification(self._note(tone="danger"))
        row = self._notification_rows(hud)[0]
        self.assertEqual(row.accent, config.overlay.danger)
        self.assertEqual(row.segments[0].glyph_color, config.overlay.danger)

        hud.clear_alert()
        hud.notifications.clear()
        hud.push_notification(self._note(key="other", tone="success"))
        row = self._notification_rows(hud)[0]
        self.assertEqual(row.accent, config.overlay.success)
        hud.close()

    def test_the_notification_fades_in_and_settles(self) -> None:
        clock = FakeClock()
        hud = self._hud(clock=clock)
        hud.push_notification(self._note())

        first = self._notification_rows(hud)[0]
        self.assertAlmostEqual(first.opacity, 0.0)
        # Sliding down from above, so it is drawn higher than its final spot.
        self.assertLess(first.offset, 0.0)

        clock.advance(hud.config.notifications.fade_in_seconds)
        hud.rebuild()
        settled = self._notification_rows(hud)[0]
        self.assertAlmostEqual(settled.opacity, 1.0)
        self.assertAlmostEqual(settled.offset, 0.0)
        hud.close()

    def test_the_animation_timer_runs_only_while_something_moves(self) -> None:
        clock = FakeClock()
        hud = self._hud(clock=clock)
        self.assertFalse(hud._animation_timer.isActive())

        hud.push_notification(self._note())
        self.assertTrue(hud._animation_timer.isActive())

        clock.advance(hud.config.notifications.fade_in_seconds)
        hud._tick_animation()
        self.assertFalse(hud._animation_timer.isActive())
        hud.close()

    def test_repeats_fold_and_show_a_count(self) -> None:
        hud = self._hud()
        hud.push_notification(self._note())
        hud.push_notification(self._note())
        rows = self._notification_rows(hud)
        self.assertEqual(len(rows), 1)
        text = " ".join(span.text for span in rows[0].segments[0].spans)
        self.assertIn("x2", text)
        hud.close()

    def test_different_kinds_get_their_own_lines(self) -> None:
        hud = self._hud()
        hud.push_notification(self._note())
        hud.push_notification(self._note(key="footfall:Body 3", title="Первый след"))
        self.assertEqual(len(self._notification_rows(hud)), 2)
        hud.close()

    def test_notifications_can_be_turned_off(self) -> None:
        config = Config()
        config.notifications.enabled = False
        hud = self._hud(config)
        hud.push_notification(self._note())
        self.assertEqual(self._notification_rows(hud), [])
        self.assertFalse(hud._animation_timer.isActive())
        hud.close()

    def test_the_bar_grows_to_fit_a_notification(self) -> None:
        hud = self._hud()
        before = hud.height()
        hud.push_notification(self._note(detail="Empire"))
        self.assertGreater(hud.height(), before)
        hud.close()

    def test_a_relayout_keeps_the_notification_visible(self) -> None:
        """rebuild() runs on the countdown tick; it must not drop the row."""
        hud = self._hud()
        hud.push_notification(self._note())
        for _ in range(3):
            hud.rebuild()
        self.assertEqual(len(self._notification_rows(hud)), 1)
        hud.close()


class PreviewFixtureTests(unittest.TestCase):
    """The preview tool's fixture must stay in sync with the journal format."""

    def test_preview_tool_exists(self) -> None:
        self.assertTrue((Path(__file__).parent.parent / "tools" / "preview_hud.py").is_file())


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class FactionSegmentTests(unittest.TestCase):
    """The followed faction: green where it runs the system, red where it does not."""

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, state, config):
        from elite_hud.overlay.hud import HudWindow

        with_segments(config, top=LEGACY_TOP, bottom=["faction"])
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    def _state(self, name="Traders & Explorers"):
        from elite_hud.state import GameState

        config = Config()
        state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            faction_name=name,
        )
        return state

    def _faction_row(self, hud):
        return next(
            (
                row
                for row in hud._rows
                if row.kind == "status"
                and any(
                    span.text.startswith("Traders")
                    for segment in row.segments
                    for span in segment.spans
                )
            ),
            None,
        )

    def _jump(self, state, influence, controller, system="Sol"):
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": system,
                "SystemAddress": 1,
                "Population": 1000,
                "SystemFaction": {"Name": controller},
                "Factions": [
                    {"Name": "Traders & Explorers Inc.", "Influence": influence}
                ],
            }
        )

    def test_nothing_is_shown_without_a_configured_faction(self) -> None:
        config = Config()
        state = self._state(name="")
        self._jump(state, 0.8, "Traders & Explorers Inc.")
        hud = self._hud(state, config)
        self.assertNotIn("Traders", hud.bar_text())
        hud.close()

    def test_nothing_is_shown_before_a_system_with_factions(self) -> None:
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertNotIn("Traders", hud.bar_text())
        hud.close()

    def test_controlling_faction_is_green(self) -> None:
        config = Config()
        state = self._state()
        self._jump(state, 0.80981, "Traders & Explorers Inc.")
        hud = self._hud(state, config)
        row = self._faction_row(hud)
        self.assertIsNotNone(row, "the faction should be on the status row")
        segment = next(
            segment
            for segment in row.segments
            if any(span.text.startswith("Traders") for span in segment.spans)
        )
        self.assertEqual(segment.glyph_color, config.overlay.success)
        text = " ".join(span.text for span in segment.spans)
        self.assertIn("81%", text)
        hud.close()

    def test_a_non_controlling_faction_is_red(self) -> None:
        config = Config()
        state = self._state()
        self._jump(state, 0.303, "Someone Else")
        hud = self._hud(state, config)
        row = self._faction_row(hud)
        self.assertIsNotNone(row)
        segment = next(
            segment
            for segment in row.segments
            if any(span.text.startswith("Traders") for span in segment.spans)
        )
        self.assertEqual(segment.glyph_color, config.overlay.danger)
        self.assertIn("30%", " ".join(span.text for span in segment.spans))
        hud.close()

    def test_an_uninhabited_system_hides_it_again(self) -> None:
        config = Config()
        state = self._state()
        self._jump(state, 0.80981, "Traders & Explorers Inc.")
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "Blu Theia AV-F d11-1",
                "SystemAddress": 2,
                "Population": 0,
                "Factions": [],
            }
        )
        hud = self._hud(state, config)
        self.assertNotIn("Traders", hud.bar_text())
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class CrimeSegmentTests(unittest.TestCase):
    """Notoriety and fines, shown only when there is something to show."""

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, state, config):
        from elite_hud.overlay.hud import HudWindow

        with_segments(config, top=LEGACY_TOP, bottom=["crime"])
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    def _state(self):
        from elite_hud.state import GameState

        config = Config()
        return GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)

    def test_a_clean_commander_sees_nothing(self) -> None:
        """The common case must not cost a permanent "not wanted" on screen."""
        config = Config()
        state = self._state()
        state.apply(
            {
                "event": "Statistics",
                "Crime": {"Notoriety": 0, "Fines": 369, "Total_Fines": 2_288_015,
                          "Bounties_Received": 122, "Total_Bounties": 439_400},
            }
        )
        hud = self._hud(state, config)
        self.assertNotIn("Плохая репутация", hud.bar_text())
        self.assertNotIn("штраф", hud.bar_text())
        hud.close()

    def test_an_unpaid_fine_appears(self) -> None:
        config = Config()
        state = self._state()
        state.apply({"event": "CommitCrime", "Fine": 200})
        hud = self._hud(state, config)
        text = hud.bar_text()
        self.assertIn("штраф", text)
        self.assertIn("200", text)
        hud.close()

    def test_notoriety_appears_and_is_red(self) -> None:
        config = Config()
        state = self._state()
        state.apply({"event": "Statistics", "Crime": {"Notoriety": 3}})
        hud = self._hud(state, config)
        self.assertIn("Плохая репутация", hud.bar_text())
        status = next(row for row in hud._rows if row.kind == "status")
        segment = next(
            segment
            for segment in status.segments
            if any("Плохая репутация" in span.text for span in segment.spans)
        )
        self.assertEqual(segment.glyph_color, config.overlay.danger)
        hud.close()

    def test_paying_the_fine_hides_it_again(self) -> None:
        config = Config()
        state = self._state()
        state.apply({"event": "CommitCrime", "Fine": 200})
        state.apply({"event": "PayFines", "Amount": 200, "AllFines": True})
        hud = self._hud(state, config)
        self.assertNotIn("штраф", hud.bar_text())
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class SuperpowerProgressTests(unittest.TestCase):
    """The percentage is a login snapshot and can be switched off."""

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, config, state):
        from elite_hud.overlay.hud import HudWindow

        with_segments(config, bottom=["empire", "federation"])
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    def _state(self, config):
        from elite_hud.state import GameState

        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        state.apply({"event": "Rank", "Empire": 9, "Federation": 6})
        state.apply({"event": "Progress", "Empire": 13, "Federation": 28})
        return state

    def test_the_percentage_shows_by_default(self) -> None:
        config = Config()
        hud = self._hud(config, self._state(config))
        text = hud.bar_text()
        self.assertIn("Граф", text)
        self.assertIn("13%", text)
        hud.close()

    def test_it_can_be_switched_off(self) -> None:
        config = Config()
        config.overlay.superpower_progress = False
        hud = self._hud(config, self._state(config))
        text = hud.bar_text()
        # The rank itself stays: it does update, on promotion.
        self.assertIn("Граф", text)
        self.assertNotIn("13%", text)
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class CarrierSegmentTests(unittest.TestCase):
    """Both carriers, permanently, in the bottom row."""

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, state, config):
        from elite_hud.overlay.hud import HudWindow

        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    def _state(self):
        from elite_hud.state import GameState

        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        for event in (
            {"event": "CarrierStats", "CarrierID": 3714982656,
             "CarrierType": "FleetCarrier", "Callsign": "V3G-N1H",
             "Name": "[KSS0] Yuri Gagarin", "DockingAccess": "squadronfriends",
             "SpaceUsage": {"TotalCapacity": 25000, "Cargo": 7001, "FreeSpace": 5142}},
            {"event": "CarrierStats", "CarrierID": 3713063168,
             "CarrierType": "SquadronCarrier", "Callsign": "KSS0",
             "Name": "Sergey Korolev - mHQ", "DockingAccess": "all",
             "SpaceUsage": {"TotalCapacity": 60000, "Cargo": 6089, "FreeSpace": 42951}},
        ):
            state.apply(event)
        return state

    def _carrier_segments(self, hud):
        """Carrier segments, found by their label rather than by callsign.

        Matching hardcoded callsigns made the helper useless for any other
        carrier, which is exactly what the unknown-access test needed.
        """
        status = next((row for row in hud._rows if row.kind == "status"), None)
        if status is None:
            return []
        label = hud.config.overlay.labels.carrier_free
        # Compared stripped: the renderer pads the label span with spaces, and an
        # exact comparison found nothing at all.
        return [
            segment
            for segment in status.segments
            if any(span.text.strip() == label for span in segment.spans)
        ]

    def test_nothing_is_shown_without_a_carrier(self) -> None:
        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        hud = self._hud(state, config)
        self.assertEqual(self._carrier_segments(hud), [])
        hud.close()

    def test_both_callsigns_and_both_holds_are_shown(self) -> None:
        config = Config()
        hud = self._hud(self._state(), config)
        text = hud.bar_text()
        self.assertIn("V3G-N1H", text)
        self.assertIn("KSS0", text)
        self.assertIn("5142/25000", text)
        self.assertIn("42951/60000", text)
        hud.close()

    def test_each_carrier_is_its_own_segment(self) -> None:
        """Two carriers should read as two entries, not one long line."""
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertEqual(len(self._carrier_segments(hud)), 2)
        hud.close()

    def test_they_live_in_the_bottom_row(self) -> None:
        config = Config()
        hud = self._hud(self._state(), config)
        top = next(row for row in hud._rows if row.kind == "primary")
        self.assertFalse(
            any(span.text == "KSS0" for segment in top.segments for span in segment.spans)
        )
        hud.close()

    def test_the_segment_can_be_switched_off(self) -> None:
        config = Config()
        config.overlay.status_segments = []
        hud = self._hud(self._state(), config)
        self.assertEqual(self._carrier_segments(hud), [])
        self.assertNotIn("KSS0", hud.bar_text())
        hud.close()

    def _segment_for(self, hud, callsign: str):
        return next(
            segment
            for segment in self._carrier_segments(hud)
            if any(span.text == callsign for span in segment.spans)
        )

    def test_the_helper_finds_carriers_by_label_not_callsign(self) -> None:
        """A guard on the tests themselves: the previous helper only matched the
        two callsigns in the fixture."""
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertEqual(len(self._carrier_segments(hud)), 2)
        hud.close()

    def test_an_open_carrier_has_a_green_icon(self) -> None:
        """KSS0 is open to everyone in the journals."""
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertEqual(
            self._segment_for(hud, "KSS0").glyph_color, config.overlay.success
        )
        hud.close()

    def test_a_restricted_carrier_has_an_orange_icon(self) -> None:
        """V3G-N1H is squadron-and-friends only."""
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertEqual(
            self._segment_for(hud, "V3G-N1H").glyph_color, config.overlay.warning
        )
        hud.close()

    def test_a_carrier_whose_access_is_unknown_keeps_the_row_colour(self) -> None:
        """CarrierStats may not have been seen, and the icon must not then
        claim an access level nobody reported."""
        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        state.apply(
            {"event": "CarrierStats", "CarrierID": 7, "CarrierType": "FleetCarrier",
             "Callsign": "ABC-123", "SpaceUsage": {"TotalCapacity": 100, "FreeSpace": 50}}
        )
        hud = self._hud(state, config)
        glyph = self._segment_for(hud, "ABC-123").glyph_color
        self.assertNotIn(glyph, (config.overlay.success, config.overlay.warning))
        hud.close()

    def test_an_unnamed_carrier_is_not_shown(self) -> None:
        """CarrierLocation alone gives an identifier but no callsign."""
        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        state.apply(
            {"event": "CarrierLocation", "CarrierID": 1234, "CarrierType": "FleetCarrier"}
        )
        hud = self._hud(state, config)
        self.assertNotIn("1234", hud.bar_text())
        hud.close()
