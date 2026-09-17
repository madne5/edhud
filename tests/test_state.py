"""Tests for the journal-to-state state machine."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elite_hud.exobiology import Confidence, ExobiologyTable
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


class FixtureReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = GameState(ExobiologyTable(), value_threshold=THRESHOLD)
        cls.alerts = play(load_events(), cls.state)

    def test_commander_and_odyssey_flag(self) -> None:
        self.assertEqual(self.state.commander, "MadNe5")
        self.assertTrue(self.state.odyssey)

    def test_ends_in_the_second_system(self) -> None:
        self.assertEqual(self.state.system.name, "Synuefe GX-K c24-11")
        self.assertEqual(self.state.system.address, 3107710603986)

    def test_fss_reports_complete_for_the_scanned_system(self) -> None:
        self.assertEqual(self.state.system.fss_progress, 1.0)
        self.assertEqual(self.state.system.body_count, 3)
        self.assertEqual(self.state.system.non_body_count, 1)
        self.assertAlmostEqual(self.state.system.progress_percent, 100.0)

    def test_three_alerts_are_raised(self) -> None:
        kinds = sorted((a.confidence.value, a.title) for a in self.alerts)
        self.assertEqual(
            kinds,
            [
                ("confirmed", "Stratum Tectonicas"),
                ("guaranteed", "Clypeus"),
                ("possible", "Stratum"),
            ],
        )

    def test_cheap_genus_raises_nothing(self) -> None:
        # System B only holds Fungoida (max 3.7M), which is below the threshold.
        self.assertFalse(
            any(a.system == "Synuefe GX-K c24-11" for a in self.alerts),
            "Fungoida must not trigger a 7M alert",
        )

    def test_confirmed_alert_carries_the_first_logged_bonus(self) -> None:
        confirmed = next(a for a in self.alerts if a.confidence is Confidence.CONFIRMED)
        self.assertTrue(confirmed.bonus_applies)
        self.assertEqual(confirmed.value, 19_010_800)
        self.assertEqual(confirmed.payout, 95_054_000)
        self.assertEqual(confirmed.body, "Synuefe PK-V b48-0 5")

    def test_carrier_jump_was_cancelled(self) -> None:
        self.assertFalse(self.state.carrier.jump_scheduled)
        self.assertEqual(self.state.carrier.callsign, "K7Q-BQL")
        self.assertEqual(self.state.carrier.carrier_id, 3_700_000_000)


class SystemTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(ExobiologyTable(), value_threshold=THRESHOLD)

    def test_progress_falls_back_to_scanned_bodies(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        self.state.apply({"event": "FSSDiscoveryScan", "SystemAddress": 1,
                          "SystemName": "Eranin", "BodyCount": 4, "NonBodyCount": 0})
        for body_id in (1, 2):
            self.state.apply({"event": "Scan", "ScanType": "Detailed", "SystemAddress": 1,
                              "BodyID": body_id, "BodyName": f"Eranin {body_id}",
                              "PlanetClass": "Icy body"})
        self.assertEqual(self.state.system.scanned_bodies, 2)
        self.assertAlmostEqual(self.state.system.progress_percent, 50.0)

    def test_bodies_are_counted_once_and_rings_excluded(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        for _ in range(3):
            self.state.apply({"event": "Scan", "ScanType": "Detailed", "SystemAddress": 1,
                              "BodyID": 7, "BodyName": "Eranin 7", "PlanetClass": "Rocky body"})
        self.state.apply({"event": "Scan", "ScanType": "Detailed", "SystemAddress": 1,
                          "BodyID": 8, "BodyName": "Eranin 7 Ring", "PlanetClass": "Rocky body"})
        self.assertEqual(self.state.system.scanned_bodies, 1)

    def test_biology_of_another_system_is_ignored(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        self.state.apply({"event": "FSSBodySignals", "SystemAddress": 999, "BodyID": 3,
                          "BodyName": "Elsewhere 3",
                          "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 5}]})
        # FSSBodySignals carries SystemAddress but not the system name; the
        # signals still land on the body, so only the address guard protects us.
        self.assertEqual(self.state.system.bio_signal_total, 0)

    def test_bio_totals_merge_fss_and_dss_counts(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        self.state.apply({"event": "FSSBodySignals", "SystemAddress": 1, "BodyID": 3,
                          "BodyName": "Eranin 3",
                          "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 4}]})
        self.state.apply({"event": "SAASignalsFound", "SystemAddress": 1, "BodyID": 3,
                          "BodyName": "Eranin 3",
                          "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 4}],
                          "Genuses": [{"Genus": "$Codex_Ent_Bacterial_Genus_Name;",
                                       "Genus_Localised": "Bacterium"}]})
        # The DSS restates the same signal count; it must not double it.
        self.assertEqual(self.state.system.bio_signal_total, 4)
        self.assertEqual(self.state.system.bio_body_count, 1)

    def test_geological_signals_are_not_counted_as_biology(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        self.state.apply({"event": "FSSBodySignals", "SystemAddress": 1, "BodyID": 3,
                          "BodyName": "Eranin 3",
                          "Signals": [{"Type": "$SAA_SignalType_Geological;", "Count": 9}]})
        self.assertEqual(self.state.system.bio_signal_total, 0)

    def test_alerts_are_not_repeated_for_the_same_body(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        event = {"event": "SAASignalsFound", "SystemAddress": 1, "BodyID": 3,
                 "BodyName": "Eranin 3",
                 "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 2}],
                 "Genuses": [{"Genus": "$Codex_Ent_Clypeus_Genus_Name;",
                              "Genus_Localised": "Clypeus"}]}
        self.assertEqual(len(self.state.apply(event)), 1)
        self.assertEqual(self.state.apply(event), [])

    def test_genus_then_species_escalates_confidence(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        first = self.state.apply({
            "event": "SAASignalsFound", "SystemAddress": 1, "BodyID": 3, "BodyName": "Eranin 3",
            "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 1}],
            "Genuses": [{"Genus": "$Codex_Ent_Stratum_Genus_Name;", "Genus_Localised": "Stratum"}],
        })
        self.assertEqual([a.confidence for a in first], [Confidence.POSSIBLE])

        second = self.state.apply({
            "event": "ScanOrganic", "ScanType": "Log", "SystemAddress": 1, "Body": 3,
            "Genus": "$Codex_Ent_Stratum_Genus_Name;", "Genus_Localised": "Stratum",
            "Species": "$Codex_Ent_Stratum_07_Name;", "Species_Localised": "Stratum Tectonicas",
            "WasLogged": True,
        })
        self.assertEqual([a.confidence for a in second], [Confidence.CONFIRMED])
        self.assertFalse(second[0].bonus_applies)
        self.assertEqual(second[0].payout, second[0].value)

    def test_non_biology_codex_entries_are_ignored(self) -> None:
        self.state.apply({"event": "FSDJump", "StarSystem": "Eranin", "SystemAddress": 1})
        alerts = self.state.apply({
            "event": "CodexEntry", "SystemAddress": 1, "BodyID": 3,
            "Category": "$Codex_Category_StellarBodies;",
            "Name": "$Codex_Ent_Stratum_07_Name;", "Name_Localised": "Stratum Tectonicas",
        })
        self.assertEqual(alerts, [])
        self.assertEqual(self.state.system.bio_signal_total, 0)


class CarrierTests(unittest.TestCase):
    """Cooldown is derived: the journal never reports one.

    EDDI and the Carrier Manager both measure it from DepartureTime with a
    290-second constant, and this follows them.
    """

    def setUp(self) -> None:
        self.state = GameState(ExobiologyTable(), carrier_spool_seconds=15 * 60)

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
        from_request = GameState(ExobiologyTable())
        from_request.apply({"event": "CarrierJumpRequest", "CarrierID": 1, "SystemName": "Sol",
                            "DepartureTime": "2026-03-14T20:30:00Z"})

        from_arrival = GameState(ExobiologyTable())
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
        self.state = GameState(ExobiologyTable(), value_threshold=THRESHOLD)

    def test_unknown_events_are_ignored(self) -> None:
        self.assertEqual(self.state.apply({"event": "SomethingNew", "value": 1}), [])
        self.assertEqual(self.state.apply({"no_event_key": True}), [])

    def test_handler_exceptions_do_not_propagate(self) -> None:
        # A malformed payload must never take the overlay down.
        self.assertEqual(
            self.state.apply({"event": "SAASignalsFound", "BodyID": "not-an-int", "Signals": "x"}),
            [],
        )
        self.assertEqual(self.state.apply({"event": "FSDJump"}), [])

    def test_last_event_is_tracked(self) -> None:
        self.state.apply({"event": "Shutdown", "timestamp": "2026-03-14T21:00:00Z"})
        self.assertEqual(self.state.last_event, "Shutdown")
        self.assertEqual(self.state.last_event_at,
                         datetime(2026, 3, 14, 21, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()


class CodexVariantTests(unittest.TestCase):
    """A CodexEntry names a species *variant*; the table is keyed by the species.

    Without stripping the variant token every real biology codex entry resolved
    to nothing. That was invisible in these journals only because each codex line
    is paired with a same-second ScanOrganic, which the HUD does handle -- so the
    path existed for the case it never worked for.
    """

    def setUp(self) -> None:
        self.table = ExobiologyTable()

    def test_a_colour_variant_resolves(self) -> None:
        species = self.table.species("$Codex_Ent_Clypeus_02_M_Name;")
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Clypeus Margaritus")

    def test_an_element_variant_resolves(self) -> None:
        species = self.table.species("$Codex_Ent_Bacterial_09_Antimony_Name;")
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Bacterium Volu")

    def test_every_real_biology_codex_symbol_resolves(self) -> None:
        for symbol in (
            "$Codex_Ent_Clypeus_02_M_Name;",
            "$Codex_Ent_Tussocks_14_M_Name;",
            "$Codex_Ent_Cactoid_03_M_Name;",
            "$Codex_Ent_Conchas_01_Niobium_Name;",
            "$Codex_Ent_Fungoids_02_Mercury_Name;",
            "$Codex_Ent_Bacterial_09_Antimony_Name;",
            "$Codex_Ent_Bacterial_01_M_Name;",
        ):
            with self.subTest(symbol=symbol):
                self.assertIsNotNone(self.table.species(symbol), symbol)

    def test_a_plain_species_symbol_still_resolves(self) -> None:
        species = self.table.species("$Codex_Ent_Stratum_07_Name;")
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Stratum Tectonicas")

    def test_an_unknown_variant_is_still_unknown(self) -> None:
        self.assertIsNone(self.table.species("$Codex_Ent_NotAGenus_02_M_Name;"))

    def test_the_stripper_leaves_a_base_symbol_alone(self) -> None:
        from elite_hud.exobiology import _strip_variant

        self.assertEqual(
            _strip_variant("Codex_Ent_Stratum_07_Name"), "Codex_Ent_Stratum_07_Name"
        )
        self.assertEqual(
            _strip_variant("$Codex_Ent_Clypeus_02_M_Name;"), "Codex_Ent_Clypeus_02_Name"
        )
