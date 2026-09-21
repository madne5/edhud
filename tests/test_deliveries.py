"""Cargo missions: what is still to be picked up, and what is still owed.

The event shapes here are copied from real journals, including the one fact that
makes this tricky: ``CargoDepot`` reports *state*, not deltas, so after handing
cargo over ``ItemsCollected`` is 0 again. "In the hold" and "still owed" are
therefore different numbers, and a segment that derived one from the other would
be wrong the moment a mission is part-delivered.

``Mission_Mining`` is included deliberately: 22 of them in these journals produce
``CargoDepot`` events, because mining a commodity and carrying it to a station is
the same job. Nothing is decided from a mission's name.
"""

from __future__ import annotations

import unittest

from elite_hud.config import Config
from elite_hud.deliveries import DeliveryBook
from elite_hud.state import GameState

#: Real: 196 t of insulating membrane, accepted in Sol.
ACCEPTED_MEMBRANE = {
    "event": "MissionAccepted", "MissionID": 1066382954,
    "Faction": "Sol Workers' Party", "Name": "Mission_Delivery_Democracy",
    "Commodity": "$InsulatingMembrane_Name;",
    "Commodity_Localised": "Изолирующая мембрана", "Count": 196,
    "DestinationSystem": "Sol", "DestinationStation": "M.Gorbachev",
}
#: Real: the same mission, collected.
COLLECTED_MEMBRANE = {
    "event": "CargoDepot", "MissionID": 1066382954, "UpdateType": "Collect",
    "CargoType": "InsulatingMembrane", "Count": 196,
    "StartMarketID": 128016384, "EndMarketID": 128017152,
    "ItemsCollected": 196, "ItemsDelivered": 0, "TotalItemsToDeliver": 196,
    "Progress": 0.0,
}
#: Real: 416 t of silver delivered in one go.
DELIVERED_SILVER = {
    "event": "CargoDepot", "MissionID": 1066259986, "UpdateType": "Deliver",
    "CargoType": "Silver", "Count": 416, "ItemsCollected": 0,
    "ItemsDelivered": 416, "TotalItemsToDeliver": 416, "Progress": 0.0,
}
#: Real: a donation, which is not cargo.
DONATION = {
    "event": "MissionAccepted", "MissionID": 1066259188,
    "Name": "Mission_AltruismCredits_name", "Donation": "1000000",
    "Donated": 1000000,
}


class DeliveryBookTests(unittest.TestCase):
    def test_a_mission_with_a_commodity_enters_the_book(self) -> None:
        book = DeliveryBook()
        self.assertTrue(book.observe(ACCEPTED_MEMBRANE))
        self.assertEqual(len(book), 1)
        self.assertEqual(book.totals(), (196, 196), "nothing collected yet")

    def test_a_donation_does_not(self) -> None:
        """No commodity means no cargo, decided from fields rather than names."""
        book = DeliveryBook()
        self.assertFalse(book.observe(DONATION))
        self.assertEqual(len(book), 0)

    def test_collecting_moves_the_cargo_into_the_hold(self) -> None:
        book = DeliveryBook()
        book.observe(ACCEPTED_MEMBRANE)
        self.assertTrue(book.observe(COLLECTED_MEMBRANE))
        self.assertEqual(book.carrying(), 196)
        self.assertEqual(book.totals(), (0, 196), "picked up, not handed in")

    def test_delivering_settles_the_mission(self) -> None:
        book = DeliveryBook()
        book.observe(ACCEPTED_MEMBRANE)
        book.observe(COLLECTED_MEMBRANE)
        book.observe(DELIVERED_SILVER | {"MissionID": 1066382954})
        self.assertEqual(book.totals(), (0, 0))

    def test_a_part_delivered_mission_keeps_both_numbers_apart(self) -> None:
        """The reason ``ItemsCollected`` is read rather than derived.

        The game reports the hold as empty once the cargo has been handed over,
        so 400 delivered of 1000 leaves 600 to collect and 600 outstanding -- not
        1000, which is what subtracting the held cargo would give.
        """
        book = DeliveryBook()
        book.observe(ACCEPTED_MEMBRANE | {"MissionID": 7, "Count": 1000})
        book.observe({"event": "CargoDepot", "MissionID": 7, "UpdateType": "Collect",
                      "ItemsCollected": 400, "ItemsDelivered": 0,
                      "TotalItemsToDeliver": 1000})
        self.assertEqual(book.totals(), (600, 1000))
        book.observe({"event": "CargoDepot", "MissionID": 7, "UpdateType": "Deliver",
                      "ItemsCollected": 0, "ItemsDelivered": 400,
                      "TotalItemsToDeliver": 1000})
        self.assertEqual(book.carrying(), 0, "the game says the hold is empty")
        self.assertEqual(book.totals(), (600, 600))

    def test_totals_add_up_across_missions(self) -> None:
        book = DeliveryBook()
        book.observe(ACCEPTED_MEMBRANE | {"MissionID": 1, "Count": 196})
        book.observe(ACCEPTED_MEMBRANE | {"MissionID": 2, "Count": 416,
                                          "Commodity_Localised": "Серебро"})
        self.assertEqual(book.totals(), (612, 612))
        book.observe({"event": "CargoDepot", "MissionID": 1, "UpdateType": "Collect",
                      "ItemsCollected": 196, "ItemsDelivered": 0,
                      "TotalItemsToDeliver": 196})
        self.assertEqual(book.totals(), (416, 612))
        self.assertEqual(book.carrying(), 196)

    def test_a_depot_event_for_an_unknown_mission_is_ignored(self) -> None:
        """It can arrive for a mission taken before the replayed history began.

        Inventing a mission from it would put a total on the bar with no
        commodity and no idea whether it is still open.
        """
        book = DeliveryBook()
        self.assertFalse(book.observe(DELIVERED_SILVER))
        self.assertEqual(len(book), 0)

    def test_every_way_a_mission_can_end_closes_it(self) -> None:
        for event in ("MissionCompleted", "MissionAbandoned", "MissionFailed"):
            with self.subTest(event=event):
                book = DeliveryBook()
                book.observe(ACCEPTED_MEMBRANE)
                self.assertTrue(book.observe({"event": event, "MissionID": 1066382954}))
                self.assertEqual(len(book), 0)

    def test_closing_a_mission_we_never_had_reports_nothing(self) -> None:
        book = DeliveryBook()
        self.assertFalse(book.observe({"event": "MissionCompleted", "MissionID": 999}))

    def test_unreadable_fields_do_not_enter_the_book(self) -> None:
        for bad in (
            {"event": "MissionAccepted", "MissionID": 5},
            {"event": "MissionAccepted", "MissionID": 5, "Commodity": "$x_Name;", "Count": 0},
            {"event": "MissionAccepted", "MissionID": 5, "Commodity": "$x_Name;", "Count": "many"},
            {"event": "MissionAccepted", "Commodity": "$x_Name;", "Count": 10},
            {"event": "CargoDepot", "MissionID": 5},
            {"event": "SomethingElse", "MissionID": 5},
        ):
            with self.subTest(event=bad):
                self.assertFalse(DeliveryBook().observe(bad))

    def test_a_commodity_without_a_localised_name_still_reads(self) -> None:
        """English clients may omit ``Commodity_Localised``."""
        book = DeliveryBook()
        book.observe({"event": "MissionAccepted", "MissionID": 3,
                      "Commodity": "$Silver_Name;", "Count": 10})
        self.assertEqual(len(book), 1)
        self.assertEqual(book.missions[3].commodity, "$Silver_Name;")


class DeliveryStateTests(unittest.TestCase):
    def test_the_state_routes_every_mission_event(self) -> None:
        state = GameState()
        state.apply(ACCEPTED_MEMBRANE)
        self.assertEqual(state.deliveries.totals(), (196, 196))
        state.apply(COLLECTED_MEMBRANE)
        self.assertEqual(state.deliveries.totals(), (0, 196))
        state.apply({"event": "MissionCompleted", "MissionID": 1066382954})
        self.assertEqual(len(state.deliveries), 0)

    def test_missions_still_count_towards_the_mission_limit(self) -> None:
        """The delivery book is separate from the count of open missions."""
        state = GameState()
        state.apply(ACCEPTED_MEMBRANE)
        state.apply(DONATION)
        self.assertEqual(len(state.active_missions), 2)
        self.assertEqual(len(state.deliveries), 1)


class DeliverySegmentTests(unittest.TestCase):
    """The segment, as the bar builds it."""

    def _hud(self):
        # ``QApplication.instance()`` is None in a fresh process even where Qt
        # works, so the probe -- which actually starts one, in a subprocess that
        # can die without taking the run with it -- is what decides.
        from PySide6.QtWidgets import QApplication

        from tests.test_hud import QT_SKIP_REASON

        if QT_SKIP_REASON:
            self.skipTest(QT_SKIP_REASON)
        QApplication.instance() or QApplication([])
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        state = GameState()
        state.apply({"event": "FSDJump", "StarSystem": "Sol", "SystemAddress": 1})
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0
        hud.rebuild()
        return hud, state, config

    def test_nothing_is_shown_without_cargo_missions(self) -> None:
        hud, _, _ = self._hud()
        self.assertNotIn("сдать", hud.bar_text())
        hud.close()

    def test_both_numbers_appear(self) -> None:
        hud, state, _ = self._hud()
        state.apply(ACCEPTED_MEMBRANE | {"MissionID": 1, "Count": 196})
        state.apply(ACCEPTED_MEMBRANE | {"MissionID": 2, "Count": 416})
        state.apply({"event": "CargoDepot", "MissionID": 1, "UpdateType": "Collect",
                     "ItemsCollected": 196, "ItemsDelivered": 0,
                     "TotalItemsToDeliver": 196})
        hud.rebuild()
        text = hud.bar_text()
        self.assertIn("взять", text)
        self.assertIn("сдать", text)
        self.assertIn("416 т", text, "not yet picked up")
        self.assertIn("612 т", text, "still owed in total")
        hud.close()

    def test_the_segment_is_off_by_default_in_the_bottom_row(self) -> None:
        config = Config()
        self.assertIn("deliveries", config.overlay.segments)
        self.assertNotIn("deliveries", config.overlay.status_segments)

    def test_the_row_can_be_emptied_of_it(self) -> None:
        """It is a segment like any other, so the tray can switch it off."""
        config = Config()
        config.overlay.segments = [s for s in config.overlay.segments if s != "deliveries"]
        config.validate()
        self.assertNotIn("deliveries", config.overlay.segments)


if __name__ == "__main__":
    unittest.main()
