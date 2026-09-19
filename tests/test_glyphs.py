"""Every glyph must be drawable, and every segment must be renderable.

This file exists because of a crash that shipped. One glyph was written with a
third parameter that draw_glyph never passes, so painting it raised TypeError
from inside paintEvent -- a Qt callback, where PySide6 treats an unhandled
exception as fatal. The HUD drew one frame and the program exited.

The suite stayed green because the HUD tests chose their own rows and none of
them happened to include the segment that used the broken glyph. So these tests
deliberately refuse to choose: they exercise the whole vocabulary.
"""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import unittest
from pathlib import Path

# Qt aborts the interpreter outright when it cannot start, so the platform is
# chosen before any import and the ability to start is probed in a subprocess.
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

from elite_hud.config import (
    SEGMENT_NAMES,
    STATUS_SEGMENT_NAMES,
    VALID_SEGMENTS,
    VALID_STATUS_SEGMENTS,
    Config,
)
from elite_hud.overlay import icons
from elite_hud.state import GameState

REPO = Path(__file__).resolve().parent.parent


class GlyphSignatureTests(unittest.TestCase):
    """A structural check that needs no Qt, so it runs everywhere."""

    def test_every_drawer_takes_the_two_arguments_glyphs_are_called_with(self) -> None:
        tree = ast.parse((REPO / "elite_hud" / "overlay" / "icons.py").read_text(encoding="utf-8"))
        offenders = [
            (node.name, len(node.args.args))
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("_draw_")
            and len(node.args.args) != 2
        ]
        self.assertEqual(offenders, [], "drawers must take exactly (painter, rect)")

    def test_the_registry_and_the_drawers_agree(self) -> None:
        drawers = {
            name for name, _ in inspect.getmembers(icons, inspect.isfunction)
            if name.startswith("_draw_")
        }
        registered = {f"_draw_{name}" for name in icons._DRAWERS}
        # Every registered glyph has an implementation, and no implementation is
        # orphaned -- a typo in either direction means a silent blank.
        self.assertEqual(registered - drawers, set())
        self.assertEqual(drawers - registered, set())

    def test_the_public_list_matches_the_registry(self) -> None:
        """GLYPHS is what callers and tests iterate, so a drawer missing from it
        is a drawer nobody exercises. The cargo glyph was in exactly that state
        while it was broken."""
        self.assertEqual(set(icons.GLYPHS), set(icons._DRAWERS))


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class EveryGlyphTests(unittest.TestCase):
    """Rendering, so this needs Qt and is skipped where it cannot start."""

    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication([])

    def test_every_registered_glyph_draws_without_raising(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPainter, QPixmap

        from elite_hud.overlay.icons import _DRAWERS, draw_glyph

        # The registry, not the public list: iterating GLYPHS is how a glyph
        # that was registered but unlisted went unpainted by every test. A
        # QPixmap target matches the glyph tests that already existed, which is
        # the idiom known to work on both runners.
        for name in sorted(_DRAWERS):
            with self.subTest(glyph=name):
                pixmap = QPixmap(48, 48)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                draw_glyph(painter, 2, 2, 44, name, QColor("#ffffff"))
                painter.end()

    def test_an_unknown_glyph_is_ignored_rather_than_fatal(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPainter, QPixmap

        from elite_hud.overlay.icons import draw_glyph

        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        draw_glyph(painter, 0, 0, 16, "not-a-glyph", QColor("#ffffff"))
        painter.end()


@unittest.skipIf(QT_SKIP_REASON is not None, QT_SKIP_REASON or "")
class EverySegmentTests(unittest.TestCase):
    """The whole vocabulary at once, with data for all of it.

    Choosing a subset is how the broken glyph hid: the row under test simply did
    not contain it.
    """

    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication([])

    def _populated_state(self) -> GameState:
        config = Config()
        state = GameState()
        for event in (
            {"event": "LoadGame", "Commander": "Tester", "GameMode": "Open",
             "Credits": 3_322_947_321},
            {"event": "Rank", "Empire": 7, "Federation": 6},
            {"event": "Progress", "Empire": 65, "Federation": 17},
            {"event": "Statistics", "Crime": {"Notoriety": 3, "Total_Fines": 1_000}},
            {"event": "CommitCrime", "Fine": 200},
            {"event": "FSDJump", "StarSystem": "Achenar", "SystemAddress": 1,
             "Population": 1000, "SystemFaction": {"Name": "Traders & Explorers Inc."},
             "Factions": [{"Name": "Traders & Explorers Inc.", "Influence": 0.3}]},
            {"event": "FSSDiscoveryScan", "SystemAddress": 1, "SystemName": "Achenar",
             "Progress": 0.45, "BodyCount": 15, "NonBodyCount": 2},
            {"event": "SAASignalsFound", "SystemAddress": 1, "BodyID": 6,
             "BodyName": "Achenar 4", "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 3}]},
            {"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 5}]},
            {"event": "ScanOrganic", "SystemAddress": 1, "Body": 6, "ScanType": "Analyse",
             "Species": "$Codex_Ent_Stratum_07_Name;", "WasLogged": False},
            {"event": "Scan", "SystemAddress": 1, "BodyID": 6, "BodyName": "Achenar 4"},
            {"event": "Loadout", "Ship": "panthermkii", "ShipIdent": "KSS-25",
             "CargoCapacity": 1232, "MaxJumpRange": 40.5},
            {"event": "Cargo", "Vessel": "Ship", "Count": 199},
            {"event": "Missions", "Active": [{"MissionID": 1}]},
            {"event": "FSDTarget", "Name": "Sol", "StarClass": "G", "RemainingJumpsInRoute": 5},
            {"event": "CarrierStats", "CarrierID": 1, "CarrierType": "FleetCarrier",
             "Callsign": "V3G-N1H", "SpaceUsage": {"TotalCapacity": 25000, "Cargo": 7001,
                                                   "FreeSpace": 5142}},
        ):
            state.apply(event)
        return state

    def test_every_top_row_segment_renders(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        config.overlay.segments = sorted(VALID_SEGMENTS, key=list(SEGMENT_NAMES).index)
        state = self._populated_state()
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        self.assertGreater(len(hud._row_boxes), 0)
        self.assertTrue(hud.bar_text().strip())
        hud.close()

    def test_every_bottom_row_segment_renders(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        config.overlay.status_segments = list(STATUS_SEGMENT_NAMES)
        state = self._populated_state()
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        self.assertTrue(hud.bar_text().strip())
        hud.close()

    def test_every_segment_paints_without_raising(self) -> None:
        """The actual paint call, which is where the crash happened.

        Grabbed rather than rendered through a QPainter: that is the idiom the
        other HUD tests use, and render() into a hand-made device is what failed
        on the Linux runner while passing on macOS.
        """
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        config.overlay.segments = sorted(VALID_SEGMENTS, key=list(SEGMENT_NAMES).index)
        config.overlay.status_segments = list(STATUS_SEGMENT_NAMES)
        state = self._populated_state()
        hud = HudWindow(config, state)
        hud._available_width = lambda: 4096.0  # type: ignore[method-assign]
        hud.rebuild()
        image = hud.grab().toImage()
        self.assertGreater(image.width(), 50)
        hud.close()

    def test_the_shipped_defaults_paint_without_raising(self) -> None:
        """What a fresh install actually shows, painted for real."""
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        state = self._populated_state()
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0  # type: ignore[method-assign]
        hud.rebuild()
        # The cargo segment is in the shipped defaults, and it was the one that
        # was broken while no test drew it.
        self.assertIn("cargo", config.overlay.segments)
        image = hud.grab().toImage()
        self.assertGreater(image.width(), 50)
        hud.close()


if __name__ == "__main__":
    unittest.main()
