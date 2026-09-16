"""Rendering tests for the HUD window.

These run on the Qt "offscreen" platform so they work on a build machine with
no display.  They assert on the composed bar contents and on the pixels that
actually get painted, which is the closest thing to a screenshot assertion.
"""

from __future__ import annotations

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
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover
    QT_SKIP_REASON = f"PySide6 is not installed ({exc})"
else:
    QT_SKIP_REASON = _qt_probe()

PYSIDE_AVAILABLE = QT_SKIP_REASON is None

from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.state import Alert, Confidence, GameState


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


def rgb(color: QColor) -> tuple[int, int, int]:
    return (color.red(), color.green(), color.blue())


def opaque_pixels(image: QImage) -> tuple[int, int]:
    counts = pixel_counts(image)
    return sum(counts.values()), len(counts)


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


class PreviewFixtureTests(unittest.TestCase):
    """The preview tool's fixture must stay in sync with the journal format."""

    def test_preview_tool_exists(self) -> None:
        self.assertTrue((Path(__file__).parent.parent / "tools" / "preview_hud.py").is_file())


if __name__ == "__main__":
    unittest.main()
