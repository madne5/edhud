"""Both entry points must work the way their real callers invoke them.

This exists because they differ in a way that is easy to get wrong and hard to
notice: ``python -m elite_hud`` gives the package a ``__package__``, while
PyInstaller executes the entry script directly as ``__main__``. A relative
import works in the first case and fails in the second -- and in a windowed
build that failure appears as a dialog nobody can dismiss, so the release
pipeline hangs instead of reporting an error.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

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
