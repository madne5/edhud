"""The application object itself, built the way ``main`` builds it.

This file exists because of a release that would have shipped broken. A cleanup
pass deleted the whole ``HudApp`` class and left ``main`` calling it. Nothing
noticed: every test exercised the state machine, the config or the HUD widgets
in isolation, ``--version`` and ``--self-check`` both return before the window is
created, and the frozen build's smoke test only ran those two flags. The program
would have started, raised ``NameError``, and exited -- with the installer,
the release notes and the auto-update all working perfectly.

So these tests construct the real object and drive the real event path. They
need no QApplication, because ``HudApp.__init__`` builds no Qt widgets: the
window and the tray are created in ``run``. That also means they run on a
machine where Qt cannot start at all, which is where the mistake was made.
"""

from __future__ import annotations

import ast
import builtins
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from elite_hud.app import build_parser
from elite_hud.config import Config

APP_SOURCE = Path(__file__).resolve().parent.parent / "elite_hud" / "app.py"


def make_app(config: Config | None = None):
    """A HudApp with the default options, as ``main`` would build it."""
    from elite_hud.app import HudApp

    options = build_parser().parse_args([])
    return HudApp(config or Config(), options)


def journal_line(**event) -> dict:
    return {"timestamp": "2026-09-19T12:00:00Z", **event}


class HudAppConstructionTests(unittest.TestCase):
    def test_the_application_object_can_be_built(self) -> None:
        app = make_app()
        self.assertIsNotNone(app.state)
        self.assertIsNone(app.hud, "no window before run()")

    def test_the_entry_point_names_something_that_exists(self) -> None:
        """``main`` must not load a module-level name that is not defined.

        ``HudApp`` was deleted while ``main`` kept calling it. An AST walk is
        enough to catch that class of mistake everywhere in ``main``, including
        names no test happens to reach, and it costs nothing to run.
        """
        tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
        defined: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Import):
                defined.update((a.asname or a.name.split(".")[0]) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                defined.update((a.asname or a.name) for a in node.names)
            elif isinstance(node, ast.Assign):
                defined.update(
                    t.id for t in node.targets if isinstance(t, ast.Name)
                )
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                defined.add(node.target.id)

        main_node = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "main"
        )
        # Everything assigned anywhere inside main, so a local is never
        # reported as missing; this deliberately over-approximates.
        local: set[str] = set()
        for node in ast.walk(main_node):
            if isinstance(node, ast.arg):
                local.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                local.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                local.add(node.name)

        missing = sorted(
            {
                node.id
                for node in ast.walk(main_node)
                if isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id not in defined
                and node.id not in local
                and not hasattr(builtins, node.id)
            }
        )
        self.assertEqual(missing, [], f"main() calls names that do not exist: {missing}")


class HudAppEventTests(unittest.TestCase):
    """Events must reach the state through the real app object."""

    def _feed(self, app, *events: dict) -> None:
        for event in events:
            app._on_journal_event(event)
        app._drain()

    def test_the_state_follows_the_journal(self) -> None:
        app = make_app()
        self._feed(
            app,
            journal_line(event="Fileheader", Odyssey=True),
            journal_line(event="LoadGame", Commander="Tester", Credits=1_000_000),
            journal_line(
                event="FSDJump", StarSystem="Achenar", SystemAddress=1, Population=1000
            ),
            journal_line(
                event="FSSDiscoveryScan",
                SystemAddress=1,
                SystemName="Achenar",
                Progress=0.5,
                BodyCount=15,
                NonBodyCount=2,
            ),
            journal_line(event="Scan", SystemAddress=1, BodyID=1, BodyName="Achenar 1"),
        )
        self.assertEqual(app.state.system.name, "Achenar")
        self.assertEqual(app.state.system.body_count, 15)
        self.assertEqual(app.state.system.scanned_bodies, 1)

    def test_ring_and_belt_events_do_not_count_as_bodies(self) -> None:
        """The game reports them through Scan; counting them inflates the total."""
        app = make_app()
        self._feed(
            app,
            journal_line(event="FSDJump", StarSystem="Sol", SystemAddress=2),
            journal_line(event="Scan", SystemAddress=2, BodyID=1, BodyName="Sol A Belt Cluster 1"),
            journal_line(event="Scan", SystemAddress=2, BodyID=2, BodyName="Sol A Ring"),
            journal_line(event="Scan", SystemAddress=2, BodyID=3, BodyName="Sol 1"),
        )
        self.assertEqual(app.state.system.scanned_bodies, 1)

    def test_the_printed_line_reports_the_shipped_fields(self) -> None:
        config = Config()
        app = make_app(config)
        self._feed(
            app,
            journal_line(event="Fileheader", Odyssey=True),
            journal_line(event="LoadGame", Commander="Tester", Credits=3_322_947_321),
            journal_line(event="FSDJump", StarSystem="Achenar", SystemAddress=1),
            journal_line(event="ShipyardSwap", ShipType="panthermkii",
                         ShipType_Localised="Panther Clipper Mk II"),
            journal_line(event="Loadout", Ship="panthermkii", CargoCapacity=1232,
                         MaxJumpRange=40.5),
            journal_line(event="Cargo", Vessel="Ship", Count=199),
            journal_line(event="Missions", Active=[{"MissionID": 1}]),
        )
        line = app.render_text_line()
        for expected in ("Achenar", "3.3B", "Panther Clipper Mk II", "199/1232",
                         config.overlay.labels.missions):
            with self.subTest(expected=expected):
                self.assertIn(expected, line)

    def test_an_empty_state_prints_something_rather_than_failing(self) -> None:
        self.assertEqual(make_app().render_text_line(), "(нет данных)")

    def test_print_state_prints_once_per_batch_of_events(self) -> None:
        import contextlib
        import io

        from elite_hud.app import HudApp

        options = build_parser().parse_args(["--print-state"])
        app = HudApp(Config(), options)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            app._on_journal_event(journal_line(event="FSDJump", StarSystem="Sol"))
            app._on_journal_event(journal_line(event="LoadGame", Credits=1))
            app._drain()
        self.assertIn("Sol", buffer.getvalue())


class HudAppPersistenceTests(unittest.TestCase):
    """A settings change that cannot be written must say so out loud.

    The menu tick moves before the file is written, so a silent failure is
    indistinguishable from success until the next launch, when the setting is
    gone -- which is what "the panels never stick" turned out to be.
    """

    def test_a_failed_save_warns_and_balloons(self) -> None:
        class FakeTray:
            def __init__(self) -> None:
                self.messages: list[tuple[str, str]] = []

            def showMessage(self, title: str, body: str) -> None:  # noqa: N802
                self.messages.append((title, body))

        from elite_hud import app as app_module

        app = make_app()
        tray = FakeTray()
        app.tray = tray
        with TemporaryDirectory() as tmp:
            unwritable = Path(tmp) / "missing" / "config.toml"
            with self.assertLogs("elite_hud", level="WARNING") as logs:
                app._warn_not_saved("overlay.monitor", unwritable)
        self.assertTrue(any("could not be written" in line for line in logs.output))
        self.assertEqual(len(tray.messages), 1, "the commander is never told")
        self.assertIn(str(unwritable), tray.messages[0][1])
        self.assertTrue(hasattr(app_module, "HudApp"))


if __name__ == "__main__":
    unittest.main()
