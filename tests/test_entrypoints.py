"""Both entry points must work the way their real callers invoke them.

This exists because they differ in a way that is easy to get wrong and hard to
notice: ``python -m elite_hud`` gives the package a ``__package__``, while
PyInstaller executes the entry script directly as ``__main__``. A relative
import works in the first case and fails in the second -- and in a windowed
build that failure appears as a dialog nobody can dismiss, so the release
pipeline hangs instead of reporting an error.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRY_SCRIPT = REPO_ROOT / "tools" / "entrypoint.py"


def run(args: list[str], *, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.update(env_extra or {})
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=REPO_ROOT,
    )


class CarrierReportTests(unittest.TestCase):
    """The cooldown is not in the journal, so the only ground truth is what the
    commander actually did. This tool reads that back."""

    def _journal(self, tmp: Path, gap_seconds: float, jumps: int = 3) -> Path:
        base = datetime.now(timezone.utc) - timedelta(hours=6)

        def ts(offset: float) -> str:
            return (base + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")

        events = [{"timestamp": ts(0), "event": "Fileheader", "part": 1, "Odyssey": True}]
        moment = 600.0
        for index in range(jumps):
            departure = moment + 900
            events.append({"timestamp": ts(moment), "event": "CarrierJumpRequest",
                           "CarrierID": 1, "SystemName": f"System {index}",
                           "DepartureTime": ts(departure)})
            events.append({"timestamp": ts(departure + 72), "event": "CarrierJump",
                           "StarSystem": f"System {index}", "SystemAddress": 100 + index})
            moment = departure + gap_seconds

        path = tmp / "Journal.2026-09-16T120000.01.log"
        path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        return tmp

    def _report(self, directory: Path) -> str:
        from elite_hud.app import main

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--carrier-report", "--journal-dir", str(directory)])
        self.assertEqual(code, 0)
        return buffer.getvalue()

    def test_it_recovers_the_gap_the_commander_actually_left(self) -> None:
        with TemporaryDirectory() as tmp:
            report = self._report(self._journal(Path(tmp), gap_seconds=290))
        self.assertIn("4.83 мин", report)
        self.assertIn("запрос -> System 0", report)
        self.assertIn("ПРИБЫТИЕ", report)
        # The spool-up is reported per jump too.
        self.assertIn("15.00 мин", report)

    def test_a_longer_gap_is_reported_as_is(self) -> None:
        with TemporaryDirectory() as tmp:
            report = self._report(self._journal(Path(tmp), gap_seconds=372))
        self.assertIn("6.20 мин", report)

    def test_a_retarget_during_the_spool_is_not_counted_as_a_cycle(self) -> None:
        """Changing the destination mid-prepare is not a new jump.

        Real journals contain this: two requests 92 seconds apart for the same
        carrier, the second moving the departure by two minutes. Treating that
        as a jump cycle produces a negative gap and, before this was handled,
        made the tool report it as the shortest one.
        """
        base = datetime.now(timezone.utc) - timedelta(hours=6)

        def ts(offset: float) -> str:
            return (base + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")

        events = [
            {"timestamp": ts(0), "event": "Fileheader", "part": 1, "Odyssey": True},
            {"timestamp": ts(600), "event": "CarrierJumpRequest", "CarrierID": 1,
             "SystemName": "First", "DepartureTime": ts(1500)},
            {"timestamp": ts(692), "event": "CarrierJumpRequest", "CarrierID": 1,
             "SystemName": "Second", "DepartureTime": ts(1620)},
            {"timestamp": ts(1682), "event": "CarrierJump", "StarSystem": "Second",
             "SystemAddress": 1},
            {"timestamp": ts(2400), "event": "CarrierJumpRequest", "CarrierID": 1,
             "SystemName": "Third", "DepartureTime": ts(3300)},
        ]
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "Journal.2026-09-16T120000.01.log").write_text(
                "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
            )
            report = self._report(directory)

        self.assertIn("смена цели", report)
        self.assertIn("пропущено как смена цели", report)
        self.assertNotIn("самый короткий промежуток: -", report)

    def test_a_single_jump_says_there_is_nothing_to_compare(self) -> None:
        with TemporaryDirectory() as tmp:
            report = self._report(self._journal(Path(tmp), gap_seconds=290, jumps=1))
        self.assertIn("минимум два запроса", report)

    def test_an_empty_directory_is_handled(self) -> None:
        with TemporaryDirectory() as tmp:
            report = self._report(Path(tmp))
        self.assertIn("не найдено", report)


class EntryPointTests(unittest.TestCase):
    def test_script_entrypoint_runs(self) -> None:
        """PyInstaller's caller: the file is executed directly."""
        result = run([sys.executable, str(ENTRY_SCRIPT), "--version"])
        self.assertEqual(
            result.returncode,
            0,
            f"the frozen entry point fails:\n{result.stdout}\n{result.stderr}",
        )
        self.assertIn("elite-hud", result.stdout)

    def test_script_entrypoint_self_check(self) -> None:
        result = run([sys.executable, str(ENTRY_SCRIPT), "--self-check"])
        self.assertEqual(
            result.returncode,
            0,
            f"--self-check failed:\n{result.stdout}\n{result.stderr}",
        )
        self.assertIn("self-check OK", result.stdout)

    def test_module_entrypoint_runs(self) -> None:
        """The documented caller: ``python -m elite_hud``."""
        result = run([sys.executable, "-m", "elite_hud", "--version"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("elite-hud", result.stdout)

    def test_entry_script_avoids_relative_imports(self) -> None:
        """A relative import here would break the windowed build."""
        source = ENTRY_SCRIPT.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        self.assertNotIn("from .", code, "the PyInstaller entry point uses a relative import")

    def test_package_main_keeps_working_under_dash_m(self) -> None:
        result = run([sys.executable, "-m", "elite_hud", "--self-check"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("self-check OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
