"""Tests for journal directory discovery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b"
            nested.mkdir(parents=True)
            self.assertEqual(find_journal_dir(str(nested)), nested)

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

    def test_candidates_end_with_the_frontier_subpath_on_windows_layouts(self) -> None:
        for path in candidate_journal_dirs():
            if "Saved Games" in str(path):
                self.assertTrue(str(path).endswith(str(ED_SUBPATH)))


if __name__ == "__main__":
    unittest.main()
