"""Fleet carriers: callsigns, locations and hold space."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from elite_hud.carriers import CarrierBook, CarrierInfo
from elite_hud.config import Config
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
        self.assertEqual(info.hold(), (7001, 25000))
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
        self.assertEqual(reopened.info(3713063168).hold(), (6089, 60000))

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
        state = GameState()
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
        state = GameState(carrier_cache=cache,
        )
        self.assertTrue(state.carriers.persist)
        state.apply(PERSONAL)
        self.assertTrue(cache.is_file())

    def test_a_ship_cache_passed_by_path_is_not_discarded(self) -> None:
        cache = Path(tempfile.mkdtemp()) / "ships.json"
        config = Config()
        state = GameState(ship_cache=cache
        )
        self.assertTrue(state.ship_names.persist)
        state.apply({"event": "ShipyardSwap", "ShipType": "explorer_nx",
                     "ShipType_Localised": "Caspian Explorer"})
        self.assertTrue(cache.is_file())

    def test_the_hold_figures_are_the_games_own(self) -> None:
        """Every figure is read, never derived by subtraction.

        FreeSpace is not TotalCapacity - Cargo, because crew quarters, ship
        packs and outstanding buy orders all take space too. SpaceUsage does
        close exactly, but only when every term is included, so a display that
        wants "how much is aboard" has to read Cargo.
        """
        config = Config()
        state = GameState()
        state.apply(PERSONAL)
        info = state.carriers.info(3714982656)
        self.assertNotEqual(info.free_space, info.total_capacity - info.cargo)
        self.assertEqual(info.hold(), (7001, 25000))
        self.assertEqual(info.cargo, 7001)
        self.assertEqual(info.free_space, 5142)

    def test_the_reservation_is_read(self) -> None:
        """12857 t of the hold is held by a buy order, and it is in the event.

        It is what makes 25000, 7001 and 5142 add up, and reading it is what
        stops a purchase contract from being shown as delivered cargo.
        """
        state = GameState()
        state.apply(
            {
                "event": "CarrierStats",
                "CarrierID": 3714982656,
                "Callsign": "V3G-N1H",
                "SpaceUsage": {"TotalCapacity": 25000, "Crew": 0, "Cargo": 7001,
                               "CargoSpaceReserved": 12857, "ShipPacks": 0,
                               "ModulePacks": 0, "FreeSpace": 5142},
            }
        )
        info = state.carriers.info(3714982656)
        self.assertEqual(info.cargo_space_reserved, 12857)
        self.assertEqual(info.reserved_note(), "12857")
        # The whole event closes, which is why nothing needs to be inferred.
        self.assertEqual(
            info.cargo + info.cargo_space_reserved + info.free_space
            + info.crew,
            info.total_capacity,
        )

    def test_no_reservation_reports_nothing(self) -> None:
        info = CarrierInfo(carrier_id=1, cargo_space_reserved=0)
        self.assertEqual(info.reserved_note(), "")


class CarrierCargoTrackingTests(unittest.TestCase):
    """The hold has to move when cargo moves, not only when the panel opens.

    ``CarrierStats`` states the hold, but it fires when the carrier's management
    screen is opened. On 2026-09-16 1232 t of tritium left KSS0 at 08:43:23 and
    the new figure -- exactly 1232 less, 5081 -- did not arrive until 09:00:12.
    Seventeen minutes of the bar showing a number that was wrong, which is the
    reported symptom.

    Every event below is copied from those journals, and both directions are
    confirmed by the arithmetic: 6089 + 224 = 6313 after a transfer to KSS0, and
    6313 - 1232 = 5081 after one from it. The next CarrierStats overwrites
    whatever this works out, so a mistake cannot survive long.
    """

    KSS0 = 3713063168

    #: Real CarrierStats for KSS0, in order: before, after +224, after -1232.
    STATS_6089 = {
        "event": "CarrierStats", "CarrierID": 3713063168,
        "CarrierType": "SquadronCarrier", "Callsign": "KSS0",
        "Name": "Sergey Korolev - mHQ", "FuelLevel": 686, "DockingAccess": "all",
        "SpaceUsage": {"TotalCapacity": 60000, "Crew": 6270, "Cargo": 6089,
                       "CargoSpaceReserved": 0, "ShipPacks": 0, "ModulePacks": 0,
                       "FreeSpace": 42951},
    }
    STATS_6313 = dict(STATS_6089, SpaceUsage=dict(STATS_6089["SpaceUsage"], Cargo=6313,
                                                  FreeSpace=42727))
    STATS_5081 = dict(STATS_6089, SpaceUsage=dict(STATS_6089["SpaceUsage"], Cargo=5081,
                                                  FreeSpace=43959))
    #: Real: V3G-N1H at 21:23:03 on 2026-09-20, with a buy order outstanding.
    STATS_RESERVED_537 = dict(
        STATS_6089,
        Callsign="V3G-N1H",
        SpaceUsage={"TotalCapacity": 25000, "Crew": 0, "Cargo": 19321,
                    "CargoSpaceReserved": 537, "ShipPacks": 0, "ModulePacks": 0,
                    "FreeSpace": 5142},
    )
    #: Real: the same carrier seven seconds after 537 t had been delivered.
    STATS_19858_AFTER_DELIVERY = dict(
        STATS_RESERVED_537,
        SpaceUsage=dict(STATS_RESERVED_537["SpaceUsage"], Cargo=19858,
                        CargoSpaceReserved=0),
    )

    DOCKED_AT_KSS0 = {
        "event": "Docked", "StationName": "KSS0", "StationType": "FleetCarrier",
        "MarketID": 3713063168, "StarSystem": "Blu Theia AV-F d11-1",
        "SystemAddress": 940002216571,
    }
    #: Real: 224 t of sapphire moved from the ship into KSS0 at 21:57:07.
    TRANSFER_IN = {
        "event": "CargoTransfer",
        "Transfers": [{"Type": "sapphire", "Type_Localised": "Сапфир",
                       "Count": 224, "Direction": "tocarrier"}],
    }
    #: Real: 1232 t of tritium came off KSS0 into the ship at 08:43:23.
    TRANSFER_OUT = {
        "event": "CargoTransfer",
        "Transfers": [{"Type": "tritium", "Type_Localised": "Тритий",
                       "Count": 1232, "Direction": "toship"}],
    }
    #: Real: 34 t of sapphire moved from the SRV into the ship at 20:46:28,
    #: while the commander was on a planet surface and not docked anywhere.
    SRV_TRANSFER = {
        "event": "CargoTransfer",
        "Transfers": [{"Type": "sapphire", "Type_Localised": "Сапфир",
                       "Count": 34, "Direction": "toship"}],
    }

    def _book(self) -> CarrierBook:
        book = CarrierBook()
        book.observe(self.STATS_6089)
        return book

    def test_a_login_docked_at_a_carrier_counts_as_docked(self) -> None:
        """The docking is often in an earlier journal file than the transfer.

        On 2026-09-16 the commander logged in already standing on KSS0: the
        ``Docked`` event was in the previous file, and the transfer that emptied
        1232 t out of the carrier was at 08:43:23 in the next one. ``Location``
        is written at every login and carries ``Docked: true`` with the station
        and its MarketID, so it is the event that closes this gap. Relying on
        ``Docked`` alone dropped that transfer and left the bar 1232 t too high.
        """
        book = CarrierBook()
        book.observe(self.STATS_6313)
        book.observe(
            {"event": "Location", "Docked": True, "StationName": "KSS0",
             "StationType": "FleetCarrier", "MarketID": self.KSS0,
             "StarSystem": "Blu Theia AV-F d11-1", "SystemAddress": 940002216571}
        )
        self.assertTrue(book.observe(self.TRANSFER_OUT))
        self.assertEqual(book.info(self.KSS0).cargo, 5081)

    def test_logging_in_in_space_is_not_docked_anywhere(self) -> None:
        book = self._book()
        book.observe(self.DOCKED_AT_KSS0)
        book.observe({"event": "Location", "Docked": False,
                      "StarSystem": "Blu Theia AV-F d11-1"})
        self.assertFalse(book.observe(self.SRV_TRANSFER))
        self.assertEqual(book.info(self.KSS0).cargo, 6089)

    def test_the_whole_real_sequence_matches_the_game(self) -> None:
        """The 2026-09-16 session, event for event, as the journal recorded it.

        Location at 08:40:34 says we are docked at KSS0; CarrierStats at
        08:41:50 states 6313 t; CargoTransfer at 08:43:23 takes 1232 t off; and
        the game's own next CarrierStats, at 09:00:12, says 5081. The point of
        the rule is that the bar can show 5081 from 08:43:23 instead of waiting
        seventeen minutes for the game to say so -- and that the figure it shows
        in the meantime is the one the game will confirm.
        """
        state = GameState()
        state.apply({"event": "LoadGame", "Commander": "Madne5",
                     "Ship": "Explorer_NX", "Credits": 3_000_000_000})
        state.apply({"event": "Location", "Docked": True, "StationName": "KSS0",
                     "StationType": "FleetCarrier", "MarketID": self.KSS0})
        state.apply(self.STATS_6313)
        self.assertEqual(state.carriers.info(self.KSS0).cargo, 6313)

        state.apply(self.TRANSFER_OUT)
        derived = state.carriers.info(self.KSS0).cargo
        self.assertEqual(derived, 5081)

        # The game agrees, when it finally says so.
        state.apply(self.STATS_5081)
        self.assertEqual(state.carriers.info(self.KSS0).cargo, derived)

    def test_a_transfer_to_the_carrier_adds_to_the_hold(self) -> None:
        book = self._book()
        book.observe(self.DOCKED_AT_KSS0)
        self.assertTrue(book.observe(self.TRANSFER_IN))
        self.assertEqual(book.info(self.KSS0).cargo, 6313)
        self.assertEqual(book.info(self.KSS0).cargo, self.STATS_6313["SpaceUsage"]["Cargo"])

    def test_a_transfer_from_the_carrier_takes_from_the_hold(self) -> None:
        book = self._book()
        book.observe(self.STATS_6313)
        book.observe(self.DOCKED_AT_KSS0)
        self.assertTrue(book.observe(self.TRANSFER_OUT))
        self.assertEqual(book.info(self.KSS0).cargo, 5081)
        self.assertEqual(book.info(self.KSS0).cargo, self.STATS_5081["SpaceUsage"]["Cargo"])

    def test_an_srv_transfer_is_not_the_carrier(self) -> None:
        """Six of the eight transfers in these journals were the SRV, not cargo.

        All six were ``toship`` and all six happened after a mining run with the
        commander on a surface, so applying them to the carrier's hold would
        have moved a number the game never moved. Docking is what tells them
        apart.
        """
        book = self._book()
        for _ in range(6):
            self.assertFalse(book.observe(self.SRV_TRANSFER))
        self.assertEqual(book.info(self.KSS0).cargo, 6089)

    def test_docking_elsewhere_ends_the_attribution(self) -> None:
        """A stale carrier would collect a later SRV transfer as its own."""
        book = self._book()
        book.observe(self.DOCKED_AT_KSS0)
        book.observe({"event": "Docked", "StationName": "Metz Enterprise",
                      "StationType": "Coriolis", "MarketID": 3230679808})
        self.assertFalse(book.observe(self.SRV_TRANSFER))
        self.assertEqual(book.info(self.KSS0).cargo, 6089)

    def test_undocking_ends_the_attribution(self) -> None:
        book = self._book()
        book.observe(self.DOCKED_AT_KSS0)
        book.observe({"event": "Undocked", "StationName": "KSS0",
                      "StationType": "FleetCarrier", "MarketID": self.KSS0})
        self.assertFalse(book.observe(self.TRANSFER_OUT))
        self.assertEqual(book.info(self.KSS0).cargo, 6089)

    def test_a_transfer_never_drives_the_hold_below_zero(self) -> None:
        book = self._book()
        book.observe(self.DOCKED_AT_KSS0)
        book.observe({"event": "CargoTransfer",
                      "Transfers": [{"Type": "gold", "Count": 999999,
                                     "Direction": "toship"}]})
        self.assertEqual(book.info(self.KSS0).cargo, 0)

    def test_an_unreadable_transfer_is_ignored(self) -> None:
        """The journal is the game's file; a shape we do not know must be inert."""
        book = self._book()
        book.observe(self.DOCKED_AT_KSS0)
        for bad in (
            {"event": "CargoTransfer"},
            {"event": "CargoTransfer", "Transfers": "nonsense"},
            {"event": "CargoTransfer", "Transfers": [None, 7]},
            {"event": "CargoTransfer", "Transfers": [{"Count": "many",
                                                     "Direction": "toship"}]},
            {"event": "CargoTransfer", "Transfers": [{"Count": 5, "Direction": None}]},
        ):
            with self.subTest(event=bad):
                self.assertFalse(book.observe(bad))
        self.assertEqual(book.info(self.KSS0).cargo, 6089)

    def test_the_next_carrier_stats_wins(self) -> None:
        """Whatever the deltas worked out, the game's own figure replaces it."""
        book = self._book()
        book.observe(self.DOCKED_AT_KSS0)
        book.observe(self.TRANSFER_IN)
        self.assertEqual(book.info(self.KSS0).cargo, 6313)
        # The journal's next real CarrierStats, two minutes later.
        book.observe(self.STATS_6313)
        self.assertEqual(book.info(self.KSS0).cargo, 6313)
        # And a figure the deltas could not have known about.
        book.observe(dict(self.STATS_6089, SpaceUsage=dict(
            self.STATS_6089["SpaceUsage"], Cargo=12345)))
        self.assertEqual(book.info(self.KSS0).cargo, 12345)

    def test_a_trade_at_a_carrier_s_market_moves_its_hold(self) -> None:
        """Selling to a carrier puts goods in it; buying takes them out.

        Confirmed on 2026-09-20: V3G-N1H reported 19321 t with 537 t reserved,
        three sales of 112, 9 and 416 t followed, and the game's next
        CarrierStats said 19858 t with 0 reserved. 112 + 9 + 416 = 537, and
        19321 + 537 = 19858, so both the hold and the reservation moved by
        exactly what the trades said.
        """
        book = self._book()
        self.assertTrue(book.observe({"event": "MarketSell", "MarketID": self.KSS0,
                                      "Type": "gold", "Count": 100}))
        self.assertEqual(book.info(self.KSS0).cargo, 6189)
        self.assertTrue(book.observe({"event": "MarketBuy", "MarketID": self.KSS0,
                                      "Type": "gold", "Count": 40}))
        self.assertEqual(book.info(self.KSS0).cargo, 6149)

    def test_a_sale_at_a_carrier_spends_the_reservation(self) -> None:
        """The row must show the buy order shrinking as the goods arrive.

        This is the other half of the original complaint: a 20000 t purchase
        contract looked like 20000 t already loaded. The reservation is what the
        deliveries consume, and on 2026-09-20 it went 537 -> 0 over three sales
        that totalled exactly 537 t.
        """
        book = CarrierBook()
        book.observe(self.STATS_RESERVED_537)
        self.assertEqual(book.info(self.KSS0).cargo_space_reserved, 537)

        for count in (112, 9, 416):
            book.observe({"event": "MarketSell", "MarketID": self.KSS0,
                          "Type": "steel", "Count": count})
        info = book.info(self.KSS0)
        self.assertEqual(info.cargo_space_reserved, 0)
        self.assertEqual(info.cargo, 19321 + 537)
        self.assertEqual(info.reserved_note(), "", "nothing left to show")
        # And the game agrees, seven seconds later in the journal.
        book.observe(self.STATS_19858_AFTER_DELIVERY)
        self.assertEqual(info.cargo, 19858)
        self.assertEqual(info.cargo_space_reserved, 0)

    def test_a_sale_never_overspends_the_reservation(self) -> None:
        book = CarrierBook()
        book.observe(self.STATS_RESERVED_537)
        book.observe({"event": "MarketSell", "MarketID": self.KSS0,
                      "Type": "steel", "Count": 5000})
        self.assertEqual(book.info(self.KSS0).cargo_space_reserved, 0)

    def test_a_purchase_from_a_carrier_leaves_the_reservation_alone(self) -> None:
        """Sale orders hold stock that is already counted in the hold."""
        book = CarrierBook()
        book.observe(self.STATS_RESERVED_537)
        book.observe({"event": "MarketBuy", "MarketID": self.KSS0,
                      "Type": "steel", "Count": 100})
        info = book.info(self.KSS0)
        self.assertEqual(info.cargo, 19321 - 100)
        self.assertEqual(info.cargo_space_reserved, 537)

    def test_the_hold_is_never_adjusted_from_nothing(self) -> None:
        """A delivery cannot invent a total for a carrier nobody has reported.

        At the start of a session the book may know nothing about a carrier, and
        adding a 1232 t delivery to that would present the amount delivered as
        the whole hold.
        """
        book = CarrierBook()  # no CarrierStats at all
        self.assertFalse(
            book.observe({"event": "MarketSell", "MarketID": self.KSS0,
                          "Type": "steel", "Count": 1232})
        )
        # Nothing to adjust, so nothing is remembered either: a carrier known
        # only from a trade would be a nameless row the cache keeps forever.
        self.assertIsNone(book.info(self.KSS0))
        self.assertEqual(len(book), 0)

    def test_the_hold_is_known_again_after_a_restart(self) -> None:
        cache = Path(tempfile.mkdtemp()) / "carriers.json"
        book = CarrierBook(cache_path=cache)
        book.observe(self.STATS_6089)
        reopened = CarrierBook(cache_path=cache)
        self.assertTrue(reopened.info(self.KSS0).cargo_known)
        self.assertTrue(
            reopened.observe({"event": "MarketSell", "MarketID": self.KSS0,
                              "Type": "steel", "Count": 11})
        )
        self.assertEqual(reopened.info(self.KSS0).cargo, 6100)

    def test_a_trade_at_a_station_is_ignored(self) -> None:
        """All four market trades in the journals were at stations."""
        book = self._book()
        self.assertFalse(book.observe({"event": "MarketSell", "MarketID": 3230679808,
                                       "Type": "gold", "Count": 1232}))
        self.assertEqual(book.info(self.KSS0).cargo, 6089)

    def test_an_unknown_carrier_is_not_invented(self) -> None:
        """A carrier never seen in CarrierStats must not appear from a trade.

        It would show up as a blank row that could not be named, and the cache
        would keep it there.
        """
        book = CarrierBook()
        self.assertFalse(book.observe({"event": "MarketSell", "MarketID": 999,
                                       "Type": "gold", "Count": 10}))
        book.observe({"event": "Docked", "StationName": "ZZZ-000",
                      "StationType": "FleetCarrier", "MarketID": 999})
        self.assertFalse(book.observe(self.TRANSFER_IN))
        self.assertEqual(len(book), 0)

    def test_the_move_survives_a_restart(self) -> None:
        cache = Path(tempfile.mkdtemp()) / "carriers.json"
        book = CarrierBook(cache_path=cache)
        book.observe(self.STATS_6089)
        book.observe(self.DOCKED_AT_KSS0)
        book.observe(self.TRANSFER_IN)
        reopened = CarrierBook(cache_path=cache)
        self.assertEqual(reopened.info(self.KSS0).cargo, 6313)

    def test_the_events_reach_the_carrier_through_apply(self) -> None:
        """state must route them: the book is only reachable through apply()."""
        state = GameState()
        state.apply(self.STATS_6089)
        state.apply(self.DOCKED_AT_KSS0)
        state.apply(self.TRANSFER_IN)
        self.assertEqual(state.carriers.info(self.KSS0).cargo, 6313)
        state.apply({"event": "Undocked", "StationName": "KSS0",
                     "StationType": "FleetCarrier", "MarketID": self.KSS0})
        state.apply(self.SRV_TRANSFER)
        self.assertEqual(state.carriers.info(self.KSS0).cargo, 6313)


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
