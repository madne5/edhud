"""The HUD bar: layout, painting, and the segments that remain.

Rewritten after the bar was cut back to the carrier, system, balance, ship, cargo
and missions on the top row and the jump target and fleet carriers below. The
previous version had accumulated fixtures and assertions for segments that no
longer exist, and every one of them still referred to code that had been removed.

Qt is probed in a subprocess: it aborts the interpreter outright when it cannot
start, which would take the whole test run with it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_probe() -> str | None:
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
    return f"Qt cannot start here: {lines[-1] if lines else result.returncode}"


QT_SKIP_REASON = _qt_probe()

if QT_SKIP_REASON is None:
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

from elite_hud.config import Config
from elite_hud.state import GameState

#: The shipped rows, read from the configuration so the sentinels cannot drift
#: away from what the program actually shows.
DEFAULT_TOP = list(Config().overlay.segments)
DEFAULT_BOTTOM = list(Config().overlay.status_segments)


def make_state(config: Config) -> GameState:
    """A state with enough in it for the shipped segments to draw."""
    state = GameState()
    state.apply({"event": "Fileheader", "Odyssey": True})
    state.apply({"event": "LoadGame", "Commander": "Tester", "GameMode": "Open",
                 "Credits": 3_322_947_321})
    state.apply({"event": "FSDJump", "StarSystem": "Achenar", "SystemAddress": 1,
                 "Population": 1000})
    state.apply({"event": "FSSDiscoveryScan", "SystemAddress": 1,
                 "SystemName": "Achenar", "Progress": 0.45,
                 "BodyCount": 15, "NonBodyCount": 2})
    state.apply({"event": "ShipyardSwap", "ShipType": "panthermkii",
                 "ShipType_Localised": "Panther Clipper Mk II"})
    state.apply({"event": "Loadout", "Ship": "panthermkii", "ShipIdent": "KSS-25",
                 "CargoCapacity": 1232, "MaxJumpRange": 40.5})
    state.apply({"event": "Cargo", "Vessel": "Ship", "Count": 199})
    state.apply({"event": "Missions", "Active": [{"MissionID": 1}]})
    state.apply({"event": "CarrierStats", "CarrierID": 1,
                 "CarrierType": "FleetCarrier", "Callsign": "V3G-N1H",
                 "DockingAccess": "all",
                 "SpaceUsage": {"TotalCapacity": 25000, "Cargo": 7001, "FreeSpace": 5142}})
    return state


def pixel_counts(image: QImage) -> "Counter[tuple[int, int, int]]":
    """Histogram of sufficiently opaque RGB triples in an image."""
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    counts: Counter[tuple[int, int, int]] = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            argb = image.pixel(x, y)
            if ((argb >> 24) & 0xFF) > 40:
                counts[((argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF)] += 1
    return counts


def opaque_pixels(image: QImage) -> tuple[int, int]:
    counts = pixel_counts(image)
    return sum(counts.values()), len(counts)


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class HudRenderTests(unittest.TestCase):
    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    #: The offscreen platform reports a tiny screen; pin a realistic one.
    SCREEN_WIDTH = 2560

    def _hud(self, config: Config, state: GameState, screen_width: int | None = None):
        from elite_hud.overlay.hud import HudWindow

        hud = HudWindow(config, state)
        width = self.SCREEN_WIDTH if screen_width is None else screen_width
        hud._available_width = lambda: float(width)  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    def test_the_bar_shows_the_shipped_segments(self) -> None:
        config = Config()
        hud = self._hud(config, make_state(config))
        text = hud.bar_text()
        # Checked one at a time so a failure names the segment that went
        # missing instead of just quoting the whole bar.
        for expected in (
            "Achenar",
            config.overlay.labels.balance,
            "Panther Clipper Mk II",
            "199/1232",
            config.overlay.labels.missions,
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        hud.close()

    def test_nothing_is_drawn_before_the_journal_says_anything(self) -> None:
        config = Config()
        hud = self._hud(config, GameState())
        self.assertEqual(hud.bar_text(), f"[radar]  {config.overlay.labels.waiting}")
        self.assertGreater(hud.width(), 0)
        hud.close()

    def test_something_is_actually_painted(self) -> None:
        config = Config()
        hud = self._hud(config, make_state(config))
        image = hud.grab().toImage()
        self.assertGreater(image.width(), 50)
        painted, distinct = opaque_pixels(image)
        self.assertGreater(painted, 500, "the HUD painted almost nothing")
        self.assertGreater(distinct, 3, "expected text, glyph and plate colours")
        hud.close()

    def test_the_carrier_countdown_appears_only_when_a_jump_is_pending(self) -> None:
        from datetime import datetime, timedelta, timezone

        config = Config()
        state = make_state(config)
        self.assertNotIn("ФК", self._hud(config, state).bar_text())

        state.carrier.departure = datetime.now(timezone.utc) + timedelta(minutes=12)
        state.carrier.target_system = "Sol"
        hud = self._hud(config, state)
        self.assertIn("ФК", hud.bar_text())
        self.assertIn("Sol", hud.bar_text())
        hud.close()

    def test_segments_config_is_respected(self) -> None:
        config = Config()
        config.overlay.segments = ["system"]
        hud = self._hud(config, make_state(config))
        self.assertIn("Achenar", hud.bar_text())
        self.assertNotIn("баланс", hud.bar_text())
        hud.close()

    def test_an_emptied_row_is_allowed(self) -> None:
        config = Config()
        config.overlay.segments = []
        config.validate()
        self.assertEqual(config.overlay.segments, [])
        hud = self._hud(config, make_state(config))
        # An emptied top row still shows the placeholder: it means "the journal
        # has not said anything yet", and the row is not otherwise drawn. Only
        # the top row is asserted on -- the bottom row is a separate setting
        # and keeps whatever it was told to show.
        self.assertEqual(hud.primary_text(), f"[radar]  {config.overlay.labels.waiting}")
        self.assertIn(config.overlay.labels.waiting, hud.bar_text())
        hud.close()

    def test_narrow_screens_show_less_than_wide_ones(self) -> None:
        config = Config()
        state = make_state(config)
        wide = self._hud(config, state, screen_width=3840)
        wide_text = wide.bar_text()
        wide.close()

        narrow = self._hud(config, state, screen_width=400)
        narrow_text = narrow.bar_text()
        narrow.close()
        self.assertLessEqual(len(narrow_text), len(wide_text) + 8)

    def test_unknown_segments_are_dropped(self) -> None:
        config = Config()
        config.overlay.segments = ["system", "bogus"]
        config.validate()
        self.assertEqual(config.overlay.segments, ["system"])

    def test_glyphs_can_be_switched_off(self) -> None:
        config = Config()
        config.overlay.show_glyphs = False
        hud = self._hud(config, make_state(config))
        self.assertNotIn("[", hud.bar_text())
        hud.close()


class SegmentCoverageTests(unittest.TestCase):
    """Every segment name the config accepts must reach a builder.

    The main row used to dispatch through an if/elif chain of its own that
    stopped at carrier, system, balance and cargo. "ship" and "missions" were in
    the shipped top row, were accepted by validate(), and were drawn by nothing
    at all -- the config said one thing and the bar did another, with no warning
    anywhere. Comparing the two sets is what catches that; it needs no
    QApplication, because it only reads the class, so it also runs where Qt
    cannot start.
    """

    def test_the_builder_table_covers_every_accepted_name(self) -> None:
        from elite_hud.config import VALID_SEGMENTS, VALID_STATUS_SEGMENTS
        from elite_hud.overlay.hud import HudWindow

        # "carriers" expands to one segment per carrier, so it has no single
        # builder to point at.
        expected = (VALID_SEGMENTS | VALID_STATUS_SEGMENTS) - {"carriers"}
        self.assertEqual(set(HudWindow.SEGMENT_BUILDERS), expected)

    def test_every_builder_is_a_real_method(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        for name, builder in HudWindow.SEGMENT_BUILDERS.items():
            with self.subTest(name=name):
                self.assertTrue(callable(builder))
                self.assertIs(getattr(HudWindow, builder.__name__, None), builder)

    def test_the_shipped_rows_only_name_segments_that_exist(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        shipped = set(config.overlay.segments) | set(config.overlay.status_segments)
        self.assertLessEqual(shipped - {"carriers"}, set(HudWindow.SEGMENT_BUILDERS))


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class RowAlignmentTests(unittest.TestCase):
    """No row may begin with a gap.

    The gap helper used to return "no gap" for the first segment and a gap for
    the rest, flipping its flag when called rather than when a segment was
    actually produced. An absent segment consumed the no-gap case, so the next
    one inherited a gap that landed at the start of the row; the plate width
    counted it, so the plate stayed centred while the text shifted right.
    """

    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, config: Config, state: GameState):
        from elite_hud.overlay.hud import HudWindow

        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    @staticmethod
    def _row(hud, kind: str):
        return next((row for row in hud._rows if row.kind == kind), None)

    def test_the_primary_row_never_starts_with_a_gap(self) -> None:
        config = Config()
        hud = self._hud(config, make_state(config))
        primary = self._row(hud, "primary")
        self.assertIsNotNone(primary)
        self.assertGreaterEqual(len(primary.segments), 2)
        self.assertEqual(primary.segments[0].lead, 0.0)
        for segment in primary.segments[1:]:
            self.assertGreater(segment.lead, 0.0)
        hud.close()

    def test_the_status_row_never_starts_with_a_gap(self) -> None:
        """The jump-target segment is first and is usually absent."""
        config = Config()
        config.overlay.status_segments = ["next", "carriers", "crime"]
        state = make_state(config)
        state.apply({"event": "CommitCrime", "Fine": 200})

        hud = self._hud(config, state)
        status = self._row(hud, "status")
        self.assertIsNotNone(status, "the status row should exist here")
        self.assertEqual(status.segments[0].lead, 0.0)
        for segment in status.segments[1:]:
            self.assertGreater(segment.lead, 0.0)
        hud.close()

    def test_every_plate_fits_its_content_with_equal_padding(self) -> None:
        config = Config()
        hud = self._hud(config, make_state(config))
        self.assertGreaterEqual(len(hud._row_boxes), 1)
        for row, _y, plate_width, _plate_height in hud._row_boxes:
            expected = hud._measure(row) + row.style.padding_x * 2
            self.assertAlmostEqual(plate_width, expected, places=6)
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
        state = GameState()
        for event in (
            {"event": "CarrierStats", "CarrierID": 3714982656,
             "CarrierType": "FleetCarrier", "Callsign": "V3G-N1H",
             "DockingAccess": "squadronfriends",
             "SpaceUsage": {"TotalCapacity": 25000, "Cargo": 7001, "FreeSpace": 5142}},
            {"event": "CarrierStats", "CarrierID": 3713063168,
             "CarrierType": "SquadronCarrier", "Callsign": "KSS0",
             "DockingAccess": "all",
             "SpaceUsage": {"TotalCapacity": 60000, "Cargo": 6089, "FreeSpace": 42951}},
        ):
            state.apply(event)
        return state

    def _carrier_segments(self, hud):
        """Found by their label rather than by callsign, so any carrier matches."""
        status = next((row for row in hud._rows if row.kind == "status"), None)
        if status is None:
            return []
        label = hud.config.overlay.labels.carrier_free
        return [
            segment
            for segment in status.segments
            if any(span.text.strip() == label for span in segment.spans)
        ]

    def _segment_for(self, hud, callsign: str):
        return next(
            segment
            for segment in self._carrier_segments(hud)
            if any(span.text == callsign for span in segment.spans)
        )

    def test_nothing_is_shown_without_a_carrier(self) -> None:
        config = Config()
        hud = self._hud(GameState(), config)
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
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertEqual(len(self._carrier_segments(hud)), 2)
        hud.close()

    def test_an_open_carrier_has_a_green_icon(self) -> None:
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertEqual(
            self._segment_for(hud, "KSS0").glyph_color, config.overlay.success
        )
        hud.close()

    def test_a_restricted_carrier_has_an_orange_icon(self) -> None:
        config = Config()
        hud = self._hud(self._state(), config)
        self.assertEqual(
            self._segment_for(hud, "V3G-N1H").glyph_color, config.overlay.warning
        )
        hud.close()

    def test_a_carrier_whose_access_is_unknown_keeps_the_row_colour(self) -> None:
        """The access colours are moved off their defaults first: warning and
        accent ship as the same orange, so comparing defaults proves nothing."""
        config = Config()
        config.overlay.success = "#00ff00"
        config.overlay.warning = "#ff00ff"
        state = GameState()
        state.apply({"event": "CarrierStats", "CarrierID": 7,
                     "CarrierType": "FleetCarrier", "Callsign": "ABC-123",
                     "SpaceUsage": {"TotalCapacity": 100, "FreeSpace": 50}})
        hud = self._hud(state, config)
        glyph = self._segment_for(hud, "ABC-123").glyph_color
        self.assertNotIn(glyph, (config.overlay.success, config.overlay.warning))
        hud.close()

    def test_an_unnamed_carrier_is_not_shown(self) -> None:
        """CarrierLocation alone gives an identifier but no callsign."""
        config = Config()
        state = GameState()
        state.apply({"event": "CarrierLocation", "CarrierID": 1234,
                     "CarrierType": "FleetCarrier"})
        hud = self._hud(state, config)
        self.assertNotIn("1234", hud.bar_text())
        hud.close()

    def test_the_segment_can_be_switched_off(self) -> None:
        config = Config()
        config.overlay.status_segments = []
        hud = self._hud(self._state(), config)
        self.assertEqual(self._carrier_segments(hud), [])
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
        hud = self._hud(GameState(), config)
        self.assertNotIn("баланс", hud.bar_text())
        hud.close()

    def test_the_balance_appears_once_known(self) -> None:
        config = Config()
        state = GameState()
        state.apply({"event": "LoadGame", "Commander": "Madne5",
                     "Credits": 3_322_947_321})
        hud = self._hud(state, config)
        self.assertIn("баланс", hud.bar_text())
        self.assertIn("3.3B", hud.bar_text())
        hud.close()

    def test_a_live_status_balance_replaces_the_journal_one(self) -> None:
        from elite_hud.status import parse_status

        config = Config()
        state = GameState()
        state.apply({"event": "LoadGame", "Credits": 1})
        state.apply_status(parse_status({"Balance": 4_229_279_956}))
        hud = self._hud(state, config)
        self.assertIn("4.2B", hud.bar_text())
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class CargoSegmentTests(unittest.TestCase):
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

    def test_no_hold_figure_without_a_loadout(self) -> None:
        config = Config()
        hud = self._hud(GameState(), config)
        self.assertNotIn("/", hud.bar_text())
        hud.close()

    def test_the_hold_reads_used_of_total(self) -> None:
        config = Config()
        state = GameState()
        state.apply({"event": "Loadout", "Ship": "panthermkii",
                     "CargoCapacity": 1232, "MaxJumpRange": 40.5})
        state.apply({"event": "Cargo", "Vessel": "Ship", "Count": 199})
        hud = self._hud(state, config)
        self.assertIn("199/1232", hud.bar_text())
        hud.close()

    def test_a_full_hold_is_flagged(self) -> None:
        config = Config()
        state = GameState()
        state.apply({"event": "Loadout", "Ship": "panthermkii",
                     "CargoCapacity": 100, "MaxJumpRange": 40.5})
        state.apply({"event": "Cargo", "Vessel": "Ship", "Count": 100})
        hud = self._hud(state, config)
        status = next(row for row in hud._rows if row.kind == "primary")
        segment = next(
            segment for segment in status.segments
            if any(span.text == "100" for span in segment.spans)
        )
        self.assertEqual(segment.glyph_color, config.overlay.danger)
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

        config.overlay.status_segments = ["crime"]
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        return hud

    def test_a_clean_commander_sees_nothing(self) -> None:
        config = Config()
        state = GameState()
        state.apply({"event": "Statistics", "Crime": {"Notoriety": 0, "Fines": 369,
                                                     "Total_Fines": 2_288_015}})
        hud = self._hud(state, config)
        self.assertNotIn("Плохая репутация", hud.bar_text())
        self.assertNotIn("штраф", hud.bar_text())
        hud.close()

    def test_an_unpaid_fine_appears(self) -> None:
        config = Config()
        state = GameState()
        state.apply({"event": "CommitCrime", "Fine": 200})
        hud = self._hud(state, config)
        self.assertIn("штраф", hud.bar_text())
        hud.close()

    def test_paying_the_fine_hides_it_again(self) -> None:
        config = Config()
        state = GameState()
        state.apply({"event": "CommitCrime", "Fine": 200})
        state.apply({"event": "PayFines", "Amount": 200, "AllFines": True})
        hud = self._hud(state, config)
        self.assertNotIn("штраф", hud.bar_text())
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class JumpTargetTests(unittest.TestCase):
    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_the_target_and_remaining_jumps_are_shown(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        state = GameState()
        state.apply({"event": "FSDJump", "StarSystem": "Achenar", "SystemAddress": 1})
        state.apply({"event": "FSDTarget", "Name": "Sol", "StarClass": "G",
                     "RemainingJumpsInRoute": 5})
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        self.assertIn("Sol", hud.bar_text())
        self.assertIn("5", hud.bar_text())
        hud.close()

    def test_nothing_is_shown_without_a_target(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        hud = HudWindow(config, GameState())
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        self.assertNotIn("след.", hud.bar_text())
        hud.close()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class GlyphTests(unittest.TestCase):
    app: "QApplication"

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_every_glyph_draws_something(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPainter, QPixmap

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

    def test_an_unknown_glyph_is_a_no_op(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPainter, QPixmap

        from elite_hud.overlay.icons import draw_glyph

        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        draw_glyph(painter, 0, 0, 16, "not-a-glyph", QColor("#ffffff"))
        painter.end()
        painted, _ = opaque_pixels(pixmap.toImage())
        self.assertEqual(painted, 0)


if __name__ == "__main__":
    unittest.main()
