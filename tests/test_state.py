"""Tests for the journal-to-state state machine."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elite_hud.state import GameState, parse_timestamp

FIXTURE = Path(__file__).parent / "fixtures" / "Journal.2026-03-14T200000.01.log"
THRESHOLD = 7_000_000


def load_events(path: Path = FIXTURE) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def play(events: list[dict], state: GameState) -> list:
    alerts = []
    for event in events:
        alerts.extend(state.apply(event))
    return alerts


class TimestampTests(unittest.TestCase):
    def test_parses_zulu(self) -> None:
        parsed = parse_timestamp("2026-03-14T20:30:00Z")
        self.assertEqual(parsed, datetime(2026, 3, 14, 20, 30, tzinfo=timezone.utc))

    def test_parses_offset(self) -> None:
        parsed = parse_timestamp("2026-03-14T22:30:00+02:00")
        self.assertEqual(parsed, datetime(2026, 3, 14, 20, 30, tzinfo=timezone.utc))

    def test_rejects_garbage(self) -> None:
        self.assertIsNone(parse_timestamp("not a date"))
        self.assertIsNone(parse_timestamp(None))


class CarrierTests(unittest.TestCase):
    """Cooldown is derived: the journal never reports one.

    EDDI and the Carrier Manager both measure it from DepartureTime with a
    290-second constant, and this follows them.
    """

    def setUp(self) -> None:
        self.state = GameState(carrier_spool_seconds=15 * 60)

    def _request(self, departure: str, requested_at: str = "2026-03-14T20:15:00Z") -> None:
        self.state.apply({"event": "CarrierJumpRequest", "CarrierID": 1, "SystemName": "Sol",
                          "DepartureTime": departure, "timestamp": requested_at})

    def test_explicit_departure_time_is_used(self) -> None:
        self._request("2026-03-14T20:30:00Z")
        carrier = self.state.carrier
        self.assertTrue(carrier.jump_scheduled)
        self.assertFalse(carrier.departure_inferred)
        self.assertEqual(carrier.target_system, "Sol")
        self.assertAlmostEqual(
            carrier.seconds_until_jump(datetime(2026, 3, 14, 20, 15, tzinfo=timezone.utc)),
            900.0,
        )

    def test_missing_departure_time_falls_back_to_the_spool_window(self) -> None:
        """15 minutes is Frontier's minimum, and only valid for old logs."""
        self.state.apply({"event": "CarrierJumpRequest", "CarrierID": 1, "SystemName": "Sol",
                          "timestamp": "2026-03-14T20:15:00Z"})
        carrier = self.state.carrier
        self.assertTrue(carrier.departure_inferred)
        self.assertEqual(carrier.departure, datetime(2026, 3, 14, 20, 30, tzinfo=timezone.utc))

    def test_the_cooldown_is_five_minutes_from_arrival(self) -> None:
        self._request("2026-03-14T20:30:00Z")
        carrier = self.state.carrier
        # Departs 20:30:00; the cooldown runs from there, so ready at 20:34:50.
        self.assertEqual(carrier.ready_at, datetime(2026, 3, 14, 20, 34, 50, tzinfo=timezone.utc))
        self.assertAlmostEqual(
            carrier.seconds_until_ready(datetime(2026, 3, 14, 20, 31, 2, tzinfo=timezone.utc)),
            228.0,
            msg="right after arrival ~3:48 of the cooldown is left",
        )
        self.assertIsNone(
            carrier.seconds_until_ready(datetime(2026, 3, 14, 20, 37, tzinfo=timezone.utc))
        )

    def test_an_arrival_confirms_the_same_moment(self) -> None:
        """The two sources must not disagree, whichever is seen first."""
        from_request = GameState()
        from_request.apply({"event": "CarrierJumpRequest", "CarrierID": 1, "SystemName": "Sol",
                            "DepartureTime": "2026-03-14T20:30:00Z"})

        from_arrival = GameState()
        from_arrival.apply({"event": "CarrierJump", "StarSystem": "Sol", "SystemAddress": 1,
                            "timestamp": "2026-03-14T20:31:02Z"})  # departure + 62s

        self.assertEqual(from_request.carrier.ready_at, from_arrival.carrier.ready_at)
        self.assertEqual(from_request.carrier.ready_at,
                         datetime(2026, 3, 14, 20, 34, 50, tzinfo=timezone.utc))

    def test_cancelling_imposes_a_one_minute_cooldown(self) -> None:
        self._request("2026-03-14T20:30:00Z")
        self.state.apply({"event": "CarrierJumpCancelled", "CarrierID": 1,
                          "timestamp": "2026-03-14T20:20:00Z"})
        carrier = self.state.carrier
        self.assertFalse(carrier.jump_scheduled)
        self.assertEqual(carrier.ready_at, datetime(2026, 3, 14, 20, 21, tzinfo=timezone.utc))

    def test_a_passed_departure_stops_being_a_countdown(self) -> None:
        self._request("2026-03-14T20:30:00Z")
        carrier = self.state.carrier

        just_before = datetime(2026, 3, 14, 20, 29, tzinfo=timezone.utc)
        self.assertAlmostEqual(carrier.seconds_until_jump(just_before), 60.0)

        self.state.settle(datetime(2026, 3, 14, 20, 30, 30, tzinfo=timezone.utc))
        self.assertFalse(carrier.jump_scheduled)
        self.assertIsNone(carrier.seconds_until_jump())
        # The cooldown keeps running; it is unaffected by the jump starting.
        # The cooldown runs from departure and does not care that the jump is
        # still in progress.
        self.assertAlmostEqual(
            carrier.seconds_until_ready(datetime(2026, 3, 14, 20, 30, 30, tzinfo=timezone.utc)),
            260.0,
        )

    def test_ready_is_flagged_only_briefly(self) -> None:
        self._request("2026-03-14T20:30:00Z")
        carrier = self.state.carrier
        just_ready = datetime(2026, 3, 14, 20, 35, 10, tzinfo=timezone.utc)
        self.assertTrue(carrier.became_ready(just_ready))
        long_ready = datetime(2026, 3, 14, 21, 30, tzinfo=timezone.utc)
        self.assertFalse(carrier.became_ready(long_ready))

    def test_no_cooldown_before_the_carrier_has_moved(self) -> None:
        """Otherwise every startup would invent one out of nothing."""
        carrier = self.state.carrier
        self.assertIsNone(carrier.seconds_until_ready())
        self.assertFalse(carrier.became_ready())

    def test_carrier_location_is_not_mistaken_for_a_jump(self) -> None:
        """It also fires on login, hours after the last jump."""
        self.state.apply({"event": "CarrierLocation", "CarrierID": 1,
                          "StarSystem": "Sol", "SystemAddress": 10477373803,
                          "timestamp": "2026-03-14T21:00:00Z"})
        self.assertIsNone(self.state.carrier.seconds_until_ready())
        self.assertEqual(self.state.carrier.last_system, "Sol")

    def test_a_cooldown_never_shortens(self) -> None:
        self._request("2026-03-14T20:30:00Z")
        carrier = self.state.carrier
        carrier.block_until(datetime(2026, 3, 14, 20, 20, tzinfo=timezone.utc))
        self.assertEqual(carrier.ready_at, datetime(2026, 3, 14, 20, 34, 50, tzinfo=timezone.utc))


class RobustnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState()

    def test_unknown_events_are_ignored(self) -> None:
        # apply() is a fold, not a query: it reports what it changed by mutating
        # state, and it returns nothing.
        self.assertIsNone(self.state.apply({"event": "SomethingNew", "value": 1}))
        self.assertIsNone(self.state.apply({"no_event_key": True}))
        self.assertEqual(self.state.last_event, "SomethingNew")

    def test_handler_exceptions_do_not_propagate(self) -> None:
        # A malformed payload must never take the overlay down.
        self.assertIsNone(
            self.state.apply({"event": "SAASignalsFound", "BodyID": "not-an-int", "Signals": "x"})
        )
        self.assertIsNone(self.state.apply({"event": "FSDJump"}))

    def test_last_event_is_tracked(self) -> None:
        self.state.apply({"event": "Shutdown", "timestamp": "2026-03-14T21:00:00Z"})
        self.assertEqual(self.state.last_event, "Shutdown")
        self.assertEqual(self.state.last_event_at,
                         datetime(2026, 3, 14, 21, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()

