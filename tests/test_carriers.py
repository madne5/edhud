"""Fleet carriers: callsigns, locations and hold space."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from elite_hud.carriers import CarrierBook, CarrierInfo
from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.state import GameState
from elite_hud.status import parse_status

#: The two carriers in the journals, in the shapes the game really sends.
PERSONAL = {
    "event": "CarrierStats",
    "CarrierID": 3714982656,
    "CarrierType": "FleetCarrier",
    "Callsign": "V3G-N1H",
    "Name": "[KSS0] Yuri Gagarin",
    "FuelLevel": 500,
    "SpaceUsage": {"TotalCapacity": 25000, "Crew": 0, "Cargo": 7001,
                   "CargoSpaceReserved": 0, "ShipPacks": 0, "ModulePacks": 0,
                   "FreeSpace": 5142},
    "Finance": {"CarrierBalance": 1_557_898_804, "ReserveBalance": 0},
}
SQUADRON = {
    "event": "CarrierStats",
    "CarrierID": 3713063168,
    "CarrierType": "SquadronCarrier",
    "Callsign": "KSS0",
    "Name": "Sergey Korolev - mHQ",
    "FuelLevel": 686,
    "SpaceUsage": {"TotalCapacity": 60000, "Crew": 6270, "Cargo": 6089,
                   "CargoSpaceReserved": 0, "ShipPacks": 0, "ModulePacks": 0,
                   "FreeSpace": 42951},
    "Finance": {"CarrierBalance": 10_574_181_836, "ReserveBalance": 1_000_000},
}


class CarrierBookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp()) / "carriers.json"
        self.book = CarrierBook(cache_path=self.path)

    def test_stats_teach_the_callsign_and_the_hold(self) -> None:
        self.assertTrue(self.book.observe(PERSONAL))
        info = self.book.info(3714982656)
        self.assertEqual(info.callsign, "V3G-N1H")
        self.assertEqual(info.name, "[KSS0] Yuri Gagarin")
        self.assertEqual(info.kind, "FleetCarrier")
        self.assertEqual(info.hold(), (5142, 25000))
        self.assertEqual(info.balance, 1_557_898_804)

    def test_a_location_gives_the_system_but_not_the_callsign(self) -> None:
        """CarrierLocation fires at every login and carries no callsign."""
        self.book.observe(PERSONAL)
        self.book.observe(
            {"event": "CarrierLocation", "CarrierID": 3714982656,
             "CarrierType": "FleetCarrier", "StarSystem": "Wregoe DG-H b51-4"}
        )
        info = self.book.info(3714982656)
        self.assertEqual(info.system, "Wregoe DG-H b51-4")
        # The cached callsign survives a location update that lacks it.
        self.assertEqual(info.callsign, "V3G-N1H")

    def test_a_carrier_seen_only_in_a_location_cannot_be_named(self) -> None:
        """Showing the raw identifier would be noise."""
        self.book.observe(
            {"event": "CarrierLocation", "CarrierID": 999, "CarrierType": "FleetCarrier"}
        )
        self.assertFalse(self.book.info(999).known)
        self.assertEqual(self.book.known(), [])

    def test_the_personal_carrier_comes_first(self) -> None:
        self.book.observe(SQUADRON)
        self.book.observe(PERSONAL)
        self.assertEqual([i.callsign for i in self.book.known()], ["V3G-N1H", "KSS0"])

    def test_finance_updates_the_balance(self) -> None:
        self.book.observe(PERSONAL)
        self.book.observe(
            {"event": "CarrierFinance", "CarrierID": 3714982656,
             "CarrierBalance": 999, "ReserveBalance": 5}
        )
        self.assertEqual(self.book.info(3714982656).balance, 999)
        self.assertEqual(self.book.info(3714982656).reserve, 5)

    def test_an_unchanged_event_reports_no_change(self) -> None:
        self.book.observe(PERSONAL)
        self.assertFalse(self.book.observe(PERSONAL))

    def test_garbage_is_ignored(self) -> None:
        for event in (
            {"event": "CarrierStats"},
            {"event": "CarrierStats", "CarrierID": "not a number"},
            {"event": "CarrierStats", "CarrierID": True},
            {"event": "SomethingElse", "CarrierID": 1},
        ):
            with self.subTest(event=event):
                self.assertFalse(self.book.observe(event))

    def test_unexpected_types_do_not_raise(self) -> None:
        self.book.observe({"event": "CarrierStats", "CarrierID": 5,
                           "SpaceUsage": "nonsense", "Finance": 7,
                           "Callsign": None, "FuelLevel": "full"})
        info = self.book.info(5)
        self.assertEqual(info.callsign, "")
        self.assertEqual(info.cargo, 0)
        self.assertIsNone(info.balance)

    def test_it_survives_a_restart(self) -> None:
        """CarrierStats fires when carrier management is opened, not at login,
        so without the cache the bar would be blank until then."""
        self.book.observe(PERSONAL)
        self.book.observe(SQUADRON)
        reopened = CarrierBook(cache_path=self.path)
        self.assertEqual([i.callsign for i in reopened.known()], ["V3G-N1H", "KSS0"])
        self.assertEqual(reopened.info(3713063168).hold(), (42951, 60000))

    def test_a_corrupt_cache_is_survivable(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(len(CarrierBook(cache_path=self.path)), 0)

    def test_no_cache_path_means_memory_only(self) -> None:
        book = CarrierBook()
        self.assertFalse(book.persist)
        book.observe(PERSONAL)
        self.assertEqual(book.info(3714982656).callsign, "V3G-N1H")


class CarrierStateTests(unittest.TestCase):
    def test_both_carriers_are_tracked(self) -> None:
        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        state.apply(PERSONAL)
        state.apply(SQUADRON)
        self.assertEqual(len(state.carriers.known()), 2)

    def test_a_carrier_cache_passed_by_path_is_not_discarded(self) -> None:
        """CarrierBook defines __len__, so an empty one is falsy.

        `carrier_book or CarrierBook(...)` therefore threw away a book built with
        a cache path in favour of one without, and nothing was ever written.
        """
        cache = Path(tempfile.mkdtemp()) / "carriers.json"
        config = Config()
        state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            carrier_cache=cache,
        )
        self.assertTrue(state.carriers.persist)
        state.apply(PERSONAL)
        self.assertTrue(cache.is_file())

    def test_a_ship_cache_passed_by_path_is_not_discarded(self) -> None:
        cache = Path(tempfile.mkdtemp()) / "ships.json"
        config = Config()
        state = GameState(
            ExobiologyTable(), value_threshold=config.alerts.min_value, ship_cache=cache
        )
        self.assertTrue(state.ship_names.persist)
        state.apply({"event": "ShipyardSwap", "ShipType": "explorer_nx",
                     "ShipType_Localised": "Caspian Explorer"})
        self.assertTrue(cache.is_file())

    def test_the_hold_figures_are_the_games_own(self) -> None:
        """They do not add up, so nothing may be derived from them.

        V3G-N1H reports 25000 total, 7001 cargo and 5142 free: 12857 is
        accounted for by nothing in the event.
        """
        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        state.apply(PERSONAL)
        info = state.carriers.info(3714982656)
        self.assertNotEqual(info.free_space, info.total_capacity - info.cargo)
        self.assertEqual(info.hold(), (5142, 25000))


class DockingAccessTests(unittest.TestCase):
    """The icon colour encodes who may dock, so the mapping must be explicit.

    The documented values are all | none | friends | squadron | squadronfriends.
    Both of the journals' carriers are covered by them: KSS0 is "all" and
    V3G-N1H is "squadronfriends".
    """

    def _role(self, access: str) -> str:
        return CarrierInfo(carrier_id=1, docking_access=access).access_role()

    def test_open_to_everyone_is_green(self) -> None:
        self.assertEqual(self._role("all"), "success")

    def test_friends_is_orange(self) -> None:
        self.assertEqual(self._role("friends"), "warning")

    def test_squadron_only_is_orange(self) -> None:
        self.assertEqual(self._role("squadron"), "warning")

    def test_friends_and_squadron_is_orange(self) -> None:
        self.assertEqual(self._role("squadronfriends"), "warning")

    def test_closed_to_everyone_counts_as_restricted(self) -> None:
        """Grouped with the restricted values rather than given its own colour:
        it is still not open to all."""
        self.assertEqual(self._role("none"), "warning")

    def test_an_unknown_value_is_treated_as_restricted(self) -> None:
        """Failing safe: claiming "open to all" for a value we do not know
        would be the one wrong answer that matters."""
        self.assertEqual(self._role("somethingnew"), "warning")

    def test_an_unseen_carrier_claims_nothing(self) -> None:
        self.assertEqual(self._role(""), "")

    def test_the_access_is_read_from_carrier_stats(self) -> None:
        book = CarrierBook()
        book.observe(dict(PERSONAL, DockingAccess="squadronfriends"))
        self.assertEqual(book.info(3714982656).docking_access, "squadronfriends")
        self.assertEqual(book.info(3714982656).access_role(), "warning")

    def test_the_access_is_case_folded(self) -> None:
        book = CarrierBook()
        book.observe(dict(SQUADRON, DockingAccess="ALL"))
        self.assertEqual(book.info(3713063168).access_role(), "success")

    def test_the_access_survives_a_restart(self) -> None:
        path = Path(tempfile.mkdtemp()) / "carriers.json"
        book = CarrierBook(cache_path=path)
        book.observe(dict(SQUADRON, DockingAccess="all"))
        reopened = CarrierBook(cache_path=path)
        self.assertEqual(reopened.info(3713063168).docking_access, "all")
        self.assertEqual(reopened.info(3713063168).access_role(), "success")

    def test_a_location_does_not_clear_the_access(self) -> None:
        """CarrierLocation carries no DockingAccess, and must not erase it."""
        book = CarrierBook()
        book.observe(dict(SQUADRON, DockingAccess="all"))
        book.observe({"event": "CarrierLocation", "CarrierID": 3713063168,
                      "CarrierType": "SquadronCarrier", "StarSystem": "Sol"})
        self.assertEqual(book.info(3713063168).access_role(), "success")


class CarrierInfoTests(unittest.TestCase):
    def test_label_falls_back_to_the_identifier(self) -> None:
        self.assertEqual(CarrierInfo(carrier_id=7).label, "7")
        self.assertEqual(CarrierInfo(carrier_id=7, callsign="ABC-123").label, "ABC-123")

    def test_the_squadron_flag_follows_the_type(self) -> None:
        self.assertTrue(CarrierInfo(carrier_id=1, kind="SquadronCarrier").squadron)
        self.assertFalse(CarrierInfo(carrier_id=1, kind="FleetCarrier").squadron)


if __name__ == "__main__":
    unittest.main()
