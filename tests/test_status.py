"""Reading Status.json: the values the journal never reports."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from elite_hud.config import Config
from elite_hud.state import GameState
from elite_hud.status import StatusReader, parse_status, read_status


def play_state() -> GameState:
    config = Config()
    return GameState()


class ParseTests(unittest.TestCase):
    def test_reads_the_fields_we_want(self) -> None:
        snapshot = parse_status(
            {
                "timestamp": "2026-09-16T23:59:49Z",
                "event": "Status",
                "Flags": 16777228,
                "Balance": 3_323_127_984,
                "LegalState": "Clean",
                "Fuel": {"FuelMain": 31.86, "FuelReservoir": 0.57},
                "Cargo": 64.0,
                "Destination": {"System": 123, "Body": 4, "Name": "Achenar"},
                "BodyName": "Achenar 4",
            }
        )
        self.assertEqual(snapshot.balance, 3_323_127_984)
        self.assertEqual(snapshot.legal_state, "Clean")
        self.assertAlmostEqual(snapshot.fuel_main, 31.86)
        self.assertAlmostEqual(snapshot.cargo, 64.0)
        self.assertEqual(snapshot.destination, "Achenar")
        self.assertEqual(snapshot.body, "Achenar 4")

    def test_the_post_exit_stub_parses(self) -> None:
        """A saved copy holds only this, and it must not look like a balance."""
        snapshot = parse_status({"timestamp": "2026-09-16T23:59:49Z", "event": "Status", "Flags": 0})
        self.assertIsNone(snapshot.balance)
        self.assertTrue(snapshot.empty)

    def test_an_empty_object_is_empty(self) -> None:
        self.assertTrue(parse_status({}).empty)

    def test_destination_falls_back_to_the_system(self) -> None:
        self.assertEqual(parse_status({"Destination": {"System": "Sol"}}).destination, "Sol")

    def test_a_boolean_is_not_a_balance(self) -> None:
        """bool is an int subclass; True is not 1 credit."""
        self.assertIsNone(parse_status({"Balance": True}).balance)

    def test_docked_and_landed_read_the_flags(self) -> None:
        self.assertTrue(parse_status({"Flags": 1}).docked)
        self.assertTrue(parse_status({"Flags": 2}).landed)
        self.assertFalse(parse_status({"Flags": 0}).docked)

    def test_wanted_follows_the_legal_state(self) -> None:
        for text in ("Wanted", "wanted", "Illegal"):
            self.assertTrue(parse_status({"LegalState": text}).wanted, text)
        self.assertFalse(parse_status({"LegalState": "Clean"}).wanted)

    def test_a_bad_timestamp_is_ignored(self) -> None:
        self.assertIsNone(parse_status({"timestamp": "not a date"}).at)

    def test_garbage_types_do_not_raise(self) -> None:
        snapshot = parse_status(
            {"Balance": "lots", "Fuel": "full", "Destination": 7, "Flags": "x"}
        )
        self.assertIsNone(snapshot.balance)
        self.assertIsNone(snapshot.fuel_main)
        self.assertEqual(snapshot.destination, "")


class ReadTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return Path(handle.name)

    def test_reads_a_file(self) -> None:
        path = self._write(json.dumps({"Balance": 500}))
        snapshot = read_status(path)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.balance, 500)

    def test_a_missing_file_is_not_an_error(self) -> None:
        self.assertIsNone(read_status(Path("/nonexistent/Status.json")))

    def test_a_truncated_write_returns_none(self) -> None:
        """The game rewrites this file constantly and not atomically."""
        path = self._write('{"Balance": 3, "Flags":')
        self.assertIsNone(read_status(path))

    def test_an_empty_file_returns_none(self) -> None:
        self.assertIsNone(read_status(self._write("")))


class ReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp()) / "Status.json"

    def test_polls_nothing_before_the_file_exists(self) -> None:
        self.assertIsNone(StatusReader(self.path).poll())

    def test_reports_a_change_once(self) -> None:
        reader = StatusReader(self.path)
        self.path.write_text(json.dumps({"Balance": 1}), encoding="utf-8")
        first = reader.poll()
        self.assertEqual(first.balance, 1)
        # Unchanged mtime: nothing to hand over again.
        self.assertIsNone(reader.poll())
        self.assertEqual(reader.last.balance, 1)

    def test_a_rewrite_is_reported(self) -> None:
        import os

        reader = StatusReader(self.path)
        self.path.write_text(json.dumps({"Balance": 1}), encoding="utf-8")
        reader.poll()
        self.path.write_text(json.dumps({"Balance": 2}), encoding="utf-8")
        os.utime(self.path, (10_000, 10_000))
        self.assertEqual(reader.poll().balance, 2)

    def test_a_bad_write_is_retried_rather_than_swallowed(self) -> None:
        reader = StatusReader(self.path)
        self.path.write_text("{broken", encoding="utf-8")
        self.assertIsNone(reader.poll())
        # The same path must still be read next time, not skipped as unchanged.
        self.path.write_text(json.dumps({"Balance": 9}), encoding="utf-8")
        self.assertEqual(reader.poll().balance, 9)

    def test_beside_points_into_the_journal_directory(self) -> None:
        reader = StatusReader.beside(Path("/journals"))
        self.assertEqual(reader.path, Path("/journals") / "Status.json")


class StateTests(unittest.TestCase):
    def test_a_journal_load_game_gives_an_initial_balance(self) -> None:
        state = play_state()
        state.apply({"event": "LoadGame", "Commander": "Madne5", "Credits": 100})
        self.assertEqual(state.credits, 100)
        # Not live: nothing is updating it yet.
        self.assertFalse(state.status_live)

    def test_a_status_snapshot_supplies_the_live_balance(self) -> None:
        state = play_state()
        state.apply({"event": "LoadGame", "Credits": 100})
        state.apply_status(parse_status({"Balance": 250}))
        self.assertEqual(state.credits, 250)
        self.assertTrue(state.status_live)

    def test_an_empty_snapshot_does_not_wipe_the_balance(self) -> None:
        """The game empties the file on exit; the last known value should stay."""
        state = play_state()
        state.apply({"event": "LoadGame", "Credits": 100})
        state.apply_status(parse_status({"Flags": 0}))
        self.assertEqual(state.credits, 100)
        self.assertFalse(state.status_live)

    def test_live_status_stops_being_claimed_once_the_file_is_stubbed(self) -> None:
        state = play_state()
        state.apply_status(parse_status({"Balance": 250}))
        self.assertTrue(state.status_live)
        state.apply_status(parse_status({"Flags": 0}))
        self.assertFalse(state.status_live)
        # The number stays, but it is no longer presented as live.
        self.assertEqual(state.credits, 250)

    def test_the_legal_state_is_recorded(self) -> None:
        state = play_state()
        state.apply_status(parse_status({"LegalState": "Wanted"}))
        self.assertEqual(state.legal_state, "Wanted")


if __name__ == "__main__":
    unittest.main()
