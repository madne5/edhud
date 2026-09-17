"""Tests for the journal tail: rotation, truncation and partial lines."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import builtins
import os
import time
from unittest import mock
from elite_hud.journal.watcher import (
    JOURNAL_RE,
    JournalTailer,
    JournalWatcher,
    journal_sort_key,
    list_journals,
)


def line(event: str, **extra: object) -> str:
    return json.dumps({"timestamp": "2026-03-14T20:00:00Z", "event": event, **extra})


class SortKeyTests(unittest.TestCase):
    def test_ordering_is_chronological(self) -> None:
        names = [
            "Journal.2026-03-14T200000.02.log",
            "Journal.2026-03-13T090000.01.log",
            "Journal.2026-03-14T200000.01.log",
        ]
        paths = [Path(name) for name in names]
        self.assertEqual(
            [p.name for p in sorted(paths, key=journal_sort_key)],
            [
                "Journal.2026-03-13T090000.01.log",
                "Journal.2026-03-14T200000.01.log",
                "Journal.2026-03-14T200000.02.log",
            ],
        )

    def test_regex_rejects_unrelated_files(self) -> None:
        self.assertIsNotNone(JOURNAL_RE.match("Journal.2026-03-14T200000.01.log"))
        self.assertIsNone(JOURNAL_RE.match("Status.json"))
        self.assertIsNone(JOURNAL_RE.match("Journal.log"))

    def test_legacy_filenames_sort_with_modern_ones(self) -> None:
        # 3.x wrote Journal.<YYMMDDHHMMSS>.<nn>.log; both generations can coexist.
        names = [
            "Journal.2022-06-07T181623.01.log",
            "Journal.161114145328.01.log",
            "Journal.2019-01-05T090000.01.log",
        ]
        ordered = [p.name for p in sorted((Path(n) for n in names), key=journal_sort_key)]
        self.assertEqual(
            ordered,
            [
                "Journal.161114145328.01.log",
                "Journal.2019-01-05T090000.01.log",
                "Journal.2022-06-07T181623.01.log",
            ],
        )

    def test_legacy_part_numbers_sort_within_the_same_second(self) -> None:
        names = ["Journal.161114145328.02.log", "Journal.161114145328.01.log"]
        ordered = [p.name for p in sorted((Path(n) for n in names), key=journal_sort_key)]
        self.assertEqual(ordered, ["Journal.161114145328.01.log", "Journal.161114145328.02.log"])


class ListJournalsTests(unittest.TestCase):
    def test_only_journal_files_are_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Journal.2026-03-14T200000.01.log").write_text("", encoding="utf-8")
            (root / "Status.json").write_text("{}", encoding="utf-8")
            (root / "Market.json").write_text("{}", encoding="utf-8")
            self.assertEqual([p.name for p in list_journals(root)],
                             ["Journal.2026-03-14T200000.01.log"])

    def test_missing_directory_is_empty(self) -> None:
        self.assertEqual(list_journals(Path("/nonexistent/path/xyz")), [])


class TailerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_only_new_lines(self) -> None:
        path = self._write("Journal.2026-03-14T200000.01.log", line("Fileheader") + "\n")
        tailer = JournalTailer()
        tailer.switch_to(path, from_start=True)
        self.assertEqual(list(tailer.read_new_lines()), [line("Fileheader")])
        # Nothing new yet.
        self.assertEqual(list(tailer.read_new_lines()), [])

        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line("LoadGame") + "\n")
        self.assertEqual(list(tailer.read_new_lines()), [line("LoadGame")])

    def test_partial_line_is_held_until_complete(self) -> None:
        path = self._write("Journal.2026-03-14T200000.01.log", "")
        tailer = JournalTailer()
        tailer.switch_to(path, from_start=True)

        with open(path, "a", encoding="utf-8") as handle:
            handle.write('{"event": "Load')
        self.assertEqual(list(tailer.read_new_lines()), [])

        with open(path, "a", encoding="utf-8") as handle:
            handle.write('Game"}\n')
        self.assertEqual(list(tailer.read_new_lines()), ['{"event": "LoadGame"}'])

    def test_truncation_restarts_from_zero(self) -> None:
        path = self._write("Journal.2026-03-14T200000.01.log", line("Fileheader") + "\n")
        tailer = JournalTailer()
        tailer.switch_to(path, from_start=True)
        list(tailer.read_new_lines())

        path.write_text(line("LoadGame") + "\n", encoding="utf-8")  # shorter content
        self.assertEqual(list(tailer.read_new_lines()), [line("LoadGame")])

    def test_switch_to_skips_to_end_by_default(self) -> None:
        path = self._write("Journal.2026-03-14T200000.01.log", line("Fileheader") + "\n")
        tailer = JournalTailer()
        tailer.switch_to(path)
        self.assertEqual(list(tailer.read_new_lines()), [])

    def test_blank_lines_are_ignored(self) -> None:
        path = self._write("Journal.2026-03-14T200000.01.log", "\n\n" + line("Fileheader") + "\n\n")
        tailer = JournalTailer()
        tailer.switch_to(path, from_start=True)
        self.assertEqual(list(tailer.read_new_lines()), [line("Fileheader")])

    def test_utf8_survives_a_split_multibyte_character(self) -> None:
        path = self._write("Journal.2026-03-14T200000.01.log", "")
        tailer = JournalTailer()
        tailer.switch_to(path, from_start=True)

        payload = json.dumps({"event": "FSDJump", "StarSystem": "Система"}, ensure_ascii=False)
        raw = (payload + "\n").encode("utf-8")
        # Split in the middle of a two-byte Cyrillic character.
        with open(path, "wb") as handle:
            handle.write(raw[: raw.index("С".encode()) + 1])
        self.assertEqual(list(tailer.read_new_lines()), [])
        with open(path, "ab") as handle:
            handle.write(raw[raw.index("С".encode()) + 1 :])
        self.assertEqual(list(tailer.read_new_lines()), [payload])


# -- replay window and failure handling ------------------------------------

NAME = "Journal.2026-03-14T200000.01.log"


def write_journal(directory: Path, *, age_days: float = 0.0) -> Path:
    path = directory / NAME
    path.write_text(
        "\n".join(
            json.dumps(event)
            for event in (
                {"event": "Fileheader", "language": "Russian"},
                {"event": "LoadGame", "Commander": "Madne5", "Credits": 100},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    if age_days:
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
    return path


def collect(directory: Path, *, days: int, timeout: float = 3.0) -> list[dict]:
    """Watch a directory, collecting whatever the replay delivers."""
    events: list[dict] = []
    watcher = JournalWatcher(directory, events.append, poll_interval=0.02, history_days=days)
    watcher.start()
    deadline = time.time() + timeout
    while time.time() < deadline and not events:
        time.sleep(0.02)
    watcher.stop()
    return events


class HistoryWindowTests(unittest.TestCase):
    def test_a_recent_journal_is_replayed(self) -> None:
        directory = Path(tempfile.mkdtemp())
        write_journal(directory)
        events = collect(directory, days=7)
        self.assertEqual([event.get("event") for event in events],
                         ["Fileheader", "LoadGame"])

    def test_zero_days_means_no_history(self) -> None:
        """The config says 0 disables history; it used to replay everything."""
        directory = Path(tempfile.mkdtemp())
        write_journal(directory)
        # Nothing is delivered from the existing file; the tailer starts at the
        # end of it instead.
        events: list[dict] = []
        watcher = JournalWatcher(directory, events.append, poll_interval=0.02, history_days=0)
        watcher.start()
        time.sleep(0.3)
        watcher.stop()
        self.assertEqual(events, [])

    def test_an_old_journal_is_outside_the_window(self) -> None:
        directory = Path(tempfile.mkdtemp())
        write_journal(directory, age_days=30)
        self.assertEqual(collect(directory, days=7), [])

    def test_an_old_journal_is_inside_a_wider_window(self) -> None:
        directory = Path(tempfile.mkdtemp())
        write_journal(directory, age_days=30)
        self.assertEqual(len(collect(directory, days=60)), 2)


class ReplayFailureTests(unittest.TestCase):
    def test_history_survives_a_failed_replay(self) -> None:
        """Marking the file as seen on failure hid the failure.

        The tailer then started at the end of the file, the poll loop never
        revisited it, and the whole session's history was skipped for the rest
        of the run -- including the LoadGame that supplies rank and the balance.
        """
        directory = Path(tempfile.mkdtemp())
        target = write_journal(directory)
        real_open = builtins.open
        failed = {"count": 0}

        def flaky(file, *args, **kwargs):
            if str(file) == str(target) and failed["count"] == 0:
                failed["count"] += 1
                raise PermissionError(13, "Permission denied")
            return real_open(file, *args, **kwargs)

        events: list[dict] = []
        watcher = JournalWatcher(directory, events.append, poll_interval=0.02, history_days=7)
        with mock.patch.object(builtins, "open", flaky):
            watcher.start()
            deadline = time.time() + 3.0
            while time.time() < deadline and len(events) < 2:
                time.sleep(0.02)
        watcher.stop()

        self.assertEqual(failed["count"], 1, "the failure injection did not fire")
        # The recovery path read the file from the beginning rather than
        # treating it as already processed.
        self.assertEqual([event.get("event") for event in events],
                         ["Fileheader", "LoadGame"])

    def test_a_successful_replay_marks_the_file_seen(self) -> None:
        directory = Path(tempfile.mkdtemp())
        target = write_journal(directory)
        events: list[dict] = []
        watcher = JournalWatcher(directory, events.append, poll_interval=0.02, history_days=7)
        watcher.start()
        time.sleep(0.3)
        watcher.stop()
        self.assertIn(target, watcher._seen_files)


if __name__ == "__main__":
    unittest.main()
