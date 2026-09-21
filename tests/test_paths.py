"""Tests for journal directory discovery."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from elite_hud import paths

from elite_hud.paths import ED_SUBPATH, candidate_journal_dirs, find_journal_dir, looks_like_journal_dir


class LookupTests(unittest.TestCase):
    def test_directory_without_journals_is_not_a_journal_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(looks_like_journal_dir(root))
            (root / "Status.json").write_text("{}", encoding="utf-8")
            self.assertFalse(looks_like_journal_dir(root))

    def test_directory_with_journals_is_recognised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Journal.2026-03-14T200000.01.log").write_text("", encoding="utf-8")
            self.assertTrue(looks_like_journal_dir(root))

    def test_missing_directory_is_not_a_journal_dir(self) -> None:
        self.assertFalse(looks_like_journal_dir(Path("/nonexistent/xyz")))


class FindJournalDirTests(unittest.TestCase):
    def test_explicit_existing_path_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(find_journal_dir(tmp), Path(tmp))

    def test_explicit_path_is_expanded(self) -> None:
        """A path with ``~`` or an environment variable in it is resolved.

        The fixture used to be a plain temporary path with neither, so removing
        the expansion from ``find_journal_dir`` entirely left it green.
        """
        home = Path.home()
        self.assertEqual(find_journal_dir("~"), home, "~ is expanded")
        self.assertEqual(find_journal_dir("$HOME"), home, "an environment variable is expanded")
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            (parent / "journals").mkdir()
            os.environ["ELITE_HUD_TEST_DIR"] = str(parent)
            try:
                self.assertEqual(find_journal_dir("$ELITE_HUD_TEST_DIR/journals"),
                                 parent / "journals")
                self.assertEqual(find_journal_dir(str(parent / "journals")),
                                 parent / "journals", "and a plain path still works")
            finally:
                os.environ.pop("ELITE_HUD_TEST_DIR", None)

    def test_unusable_explicit_path_returns_none(self) -> None:
        self.assertIsNone(find_journal_dir("/nonexistent/definitely/not/here"))

    def test_explicit_path_that_does_not_exist_yet_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pending = Path(tmp) / "not-yet-created"
            self.assertEqual(find_journal_dir(str(pending)), pending)


class EnvOverrideTests(unittest.TestCase):
    def test_ed_journal_dir_is_honoured_first(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("ED_JOURNAL_DIR")
            os.environ["ED_JOURNAL_DIR"] = tmp
            try:
                candidates = candidate_journal_dirs()
                self.assertEqual(candidates[0], Path(tmp))
                self.assertEqual(find_journal_dir(), Path(tmp))
            finally:
                if previous is None:
                    os.environ.pop("ED_JOURNAL_DIR", None)
                else:
                    os.environ["ED_JOURNAL_DIR"] = previous


class CandidateTests(unittest.TestCase):
    def test_candidates_are_deduplicated(self) -> None:
        candidates = candidate_journal_dirs()
        self.assertEqual(len(candidates), len({str(p) for p in candidates}))

    def test_the_windows_layouts_produce_the_paths_the_game_uses(self) -> None:
        """The Windows candidates, built here rather than on Windows.

        The old version looped over the platform's own candidate list and checked
        that each "Saved Games" entry ended with the constant that had been used to
        build it -- a comparison with itself, which on this machine ran zero times
        because none of the candidates match on macOS.
        """
        # Only the environment is faked; faking the platform as well would send the
        # code down a path that builds WindowsPath, which cannot exist on macOS.
        # Expectations are built with Path too, so the separators are whatever the
        # running platform uses -- an f-string with forward slashes passed here and
        # failed on Windows, which is the platform this code is for.
        profile = Path("elite-hud-profile")
        with mock.patch.dict(os.environ, {"USERPROFILE": str(profile)}, clear=False):
            os.environ.pop("OneDrive", None)
            os.environ.pop("OneDriveConsumer", None)
            candidates = [str(p) for p in paths._windows_candidates()]

        for layout in ("Saved Games", "OneDrive/Saved Games", "Documents/Saved Games"):
            expected = str(profile / Path(layout) / ED_SUBPATH)
            with self.subTest(layout=layout):
                self.assertIn(expected, candidates, f"missing: {candidates}")
        self.assertTrue(all(c.endswith(str(ED_SUBPATH)) for c in candidates))


if __name__ == "__main__":
    unittest.main()
