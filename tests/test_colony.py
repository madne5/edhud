"""Colonisation construction sites, from the events a real session left behind.

Two facts here were measured against the journals rather than assumed, and both of
them decide whether the line can be trusted:

* a ``ColonisationConstructionDepot`` event follows every contribution about a
  second later, with the provided amounts raised by exactly what was handed over
  -- eight contributions, all eight matching to the tonne -- so nothing has to be
  patched up between reports;
* symbols are not case-consistent between events: a contribution says
  ``$Aluminium_name;`` where the site's own list says ``$aluminium_name;``.

A third is a rule rather than a measurement: a site is recognised by its
MarketID, never by its name, because the name is localised and a Russian client
calls the same place something else.
"""

from __future__ import annotations

import unittest

from elite_hud.colony import ColonyBook, normalise
from elite_hud.config import Config
from elite_hud.state import GameState

#: Real: the site after its first delivery, with the head of its 24 commodities.
DEPOT = {
    "event": "ColonisationConstructionDepot", "MarketID": 4388835075,
    "ConstructionProgress": 0.124206, "ConstructionComplete": False,
    "ConstructionFailed": False,
    "ResourcesRequired": [
        {"Name": "$aluminium_name;", "Name_Localised": "Алюминий",
         "RequiredAmount": 2407, "ProvidedAmount": 1232, "Payment": 3239},
        {"Name": "$ceramiccomposites_name;", "Name_Localised": "Керамокомпозиты",
         "RequiredAmount": 249, "ProvidedAmount": 0, "Payment": 724},
        {"Name": "$steel_name;", "Name_Localised": "Сталь",
         "RequiredAmount": 6640, "ProvidedAmount": 3320, "Payment": 1166},
    ],
}
#: Real: the contribution that came a second before it.
CONTRIBUTION = {
    "event": "ColonisationContribution", "MarketID": 4388835075,
    "Contributions": [{"Name": "$Aluminium_name;", "Name_Localised": "Алюминий",
                       "Amount": 1232}],
}
#: Real: docking at the site, which is where its name comes from.
DOCKED_AT_SITE = {
    "event": "Docked", "StationName": "Planetary Construction Site: Shaara Gateway",
    "StationType": "PlanetaryConstructionDepot", "MarketID": 4388835075,
    "StarSystem": "Koli Discii",
}


class SymbolTests(unittest.TestCase):
    def test_symbols_differ_in_case_between_events(self) -> None:
        """The trap that makes a delivered commodity look untouched."""
        self.assertNotEqual("$Aluminium_name;", "$aluminium_name;")
        self.assertEqual(normalise("$Aluminium_name;"), normalise("$aluminium_name;"))


class ColonyBookTests(unittest.TestCase):
    def _book(self) -> ColonyBook:
        book = ColonyBook()
        book.observe(DEPOT)
        return book

    def test_the_site_is_read_whole(self) -> None:
        site = self._book().sites[4388835075]
        self.assertAlmostEqual(site.percent, 12.4206, places=3)
        self.assertEqual(len(site.resources), 3)

    def test_what_is_still_owed_is_summed_from_the_required_amounts(self) -> None:
        site = self._book().sites[4388835075]
        # 2407-1232 = 1175, 249-0 = 249, 6640-3320 = 3320
        self.assertEqual(site.remaining, 1175 + 249 + 3320)
        self.assertEqual(site.outstanding, 3)

    def test_a_delivered_commodity_is_not_still_owed(self) -> None:
        book = ColonyBook()
        book.observe(DEPOT | {"ResourcesRequired": [
            {"Name": "$aluminium_name;", "Name_Localised": "Алюминий",
             "RequiredAmount": 2407, "ProvidedAmount": 2407, "Payment": 3239},
        ]})
        site = book.sites[4388835075]
        self.assertEqual(site.remaining, 0)
        self.assertEqual(site.outstanding, 0)
        self.assertIsNone(site.most_needed())

    def test_a_provided_amount_over_the_requirement_never_goes_negative(self) -> None:
        book = ColonyBook()
        book.observe(DEPOT | {"ResourcesRequired": [
            {"Name": "$steel_name;", "RequiredAmount": 10, "ProvidedAmount": 99},
        ]})
        self.assertEqual(book.sites[4388835075].remaining, 0)

    def test_the_most_needed_commodity_is_the_largest_remainder(self) -> None:
        most = self._book().sites[4388835075].most_needed()
        assert most is not None
        self.assertEqual(most.label, "Сталь")
        self.assertEqual(most.remaining, 3320)

    def test_the_name_is_learned_from_the_station(self) -> None:
        book = self._book()
        self.assertEqual(book.sites[4388835075].name, "")
        self.assertTrue(book.observe(DOCKED_AT_SITE))
        self.assertEqual(
            book.sites[4388835075].name, "Planetary Construction Site: Shaara Gateway"
        )

    def test_a_place_is_a_site_only_if_its_market_id_says_so(self) -> None:
        """Recognising one by name would break on any non-English client.

        A station whose name happens to read like a construction site is still just
        a station until a construction report names its MarketID.
        """
        book = self._book()
        book.observe({"event": "Docked", "MarketID": 999, "StationType": "Coriolis",
                      "StationName": "Planetary Construction Site: Elsewhere"})
        self.assertEqual(book.docked_market_id, 0)
        self.assertNotIn(999, book.sites)

    def test_the_docked_site_is_the_one_shown(self) -> None:
        book = self._book()
        book.observe({"event": "Docked", "MarketID": 777, "StationName": "Other site"})
        book.observe({"event": "ColonisationConstructionDepot", "MarketID": 777,
                      "ConstructionProgress": 0.5, "ResourcesRequired": []})
        self.assertEqual(book.current().market_id, 777)
        book.observe(DOCKED_AT_SITE)
        self.assertEqual(book.current().market_id, 4388835075)

    def test_the_last_site_reports_while_it_is_still_being_built(self) -> None:
        """A finished site is worth a line when standing there, not from afar."""
        book = ColonyBook()
        book.observe(DEPOT)
        book.observe({"event": "ColonisationConstructionDepot", "MarketID": 555,
                      "ConstructionProgress": 0.4, "ResourcesRequired": []})
        self.assertEqual(book.current().market_id, 555)

        book.observe({"event": "ColonisationConstructionDepot", "MarketID": 555,
                      "ConstructionProgress": 1.0, "ConstructionComplete": True,
                      "ResourcesRequired": []})
        self.assertIsNone(book.current(), "finished, and we are not there")

        book.observe({"event": "Docked", "MarketID": 555, "StationName": "Done"})
        self.assertEqual(book.current().market_id, 555, "but it is worth saying here")

    def test_a_failed_site_is_kept_the_same_way(self) -> None:
        book = ColonyBook()
        book.observe({"event": "ColonisationConstructionDepot", "MarketID": 1,
                      "ConstructionProgress": 0.2, "ConstructionFailed": True,
                      "ResourcesRequired": []})
        self.assertIsNone(book.current())

    def test_undocking_from_nowhere_clears_the_site(self) -> None:
        book = self._book()
        book.observe(DOCKED_AT_SITE)
        book.observe({"event": "Location", "Docked": False, "StarSystem": "Koli Discii"})
        self.assertEqual(book.docked_market_id, 0)

    def test_the_real_session_advances_exactly_as_the_journal_did(self) -> None:
        """21:47 -> 21:48 -> 21:56 on 2026-09-20, with the game's own numbers."""
        book = ColonyBook()
        book.observe(DEPOT | {"ConstructionProgress": 0.0, "ResourcesRequired": [
            {"Name": "$steel_name;", "Name_Localised": "Сталь",
             "RequiredAmount": 6640, "ProvidedAmount": 0, "Payment": 1166},
            {"Name": "$aluminium_name;", "Name_Localised": "Алюминий",
             "RequiredAmount": 2407, "ProvidedAmount": 0, "Payment": 3239},
        ]})
        self.assertEqual(book.sites[4388835075].remaining, 9047)

        # The contribution, then the depot report a second later: +1232 aluminium.
        book.observe(CONTRIBUTION)
        book.observe(DEPOT)
        site = book.sites[4388835075]
        self.assertEqual(site.remaining, 1175 + 249 + 3320)
        self.assertAlmostEqual(site.percent, 12.42, places=2)

    def test_an_event_without_a_usable_market_id_changes_nothing(self) -> None:
        for bad in (
            {"event": "ColonisationConstructionDepot"},
            {"event": "ColonisationConstructionDepot", "MarketID": "x"},
            {"event": "ColonisationConstructionDepot", "MarketID": True},
            {"event": "ColonisationContribution", "MarketID": 1},
            {"event": "SomethingElse", "MarketID": 1},
        ):
            with self.subTest(event=bad):
                book = ColonyBook()
                self.assertFalse(book.observe(bad))
                self.assertEqual(len(book), 0)

    def test_a_report_with_no_readable_list_still_records_the_progress(self) -> None:
        """The resources can be unreadable while the progress is not.

        Showing "12% with nothing outstanding" is honest about what the event
        said; discarding the whole report would throw away a fact we do have.
        """
        for resources in ("nonsense", [None, 7, {}], []):
            with self.subTest(resources=resources):
                book = ColonyBook()
                self.assertTrue(book.observe({"event": "ColonisationConstructionDepot",
                                              "MarketID": 1,
                                              "ConstructionProgress": 0.12,
                                              "ResourcesRequired": resources}))
                site = book.sites[1]
                self.assertAlmostEqual(site.percent, 12.0, places=3)
                self.assertEqual(site.remaining, 0)
                self.assertEqual(site.outstanding, 0)


class ColonyStateTests(unittest.TestCase):
    def test_the_state_routes_the_site_events(self) -> None:
        state = GameState()
        state.apply(DEPOT)
        state.apply(DOCKED_AT_SITE)
        site = state.colony.current()
        assert site is not None
        self.assertEqual(site.name, "Planetary Construction Site: Shaara Gateway")
        self.assertEqual(site.remaining, 1175 + 249 + 3320)


class ColonySegmentTests(unittest.TestCase):
    def _hud(self):
        from PySide6.QtWidgets import QApplication

        from tests.test_hud import QT_SKIP_REASON

        if QT_SKIP_REASON:
            self.skipTest(QT_SKIP_REASON)
        QApplication.instance() or QApplication([])
        from elite_hud.overlay.hud import HudWindow

        config = Config()
        state = GameState()
        state.apply({"event": "FSDJump", "StarSystem": "Koli Discii", "SystemAddress": 1})
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0
        hud.rebuild()
        return hud, state

    def test_nothing_is_shown_without_a_site(self) -> None:
        hud, _ = self._hud()
        self.assertNotIn("осталось", hud.bar_text())
        hud.close()

    def test_progress_and_the_shortfall_appear(self) -> None:
        hud, state = self._hud()
        state.apply(DEPOT)
        hud.rebuild()
        text = hud.bar_text()
        self.assertIn("12%", text)
        self.assertIn("осталось", text)
        self.assertIn("4744 т", text, "1175 + 249 + 3320")
        self.assertIn("Сталь", text)
        hud.close()

    def test_the_name_appears_once_it_is_known(self) -> None:
        hud, state = self._hud()
        state.apply(DEPOT)
        self.assertNotIn("Shaara", hud.bar_text())
        state.apply(DOCKED_AT_SITE)
        hud.rebuild()
        self.assertIn("Shaara Gateway", hud.bar_text())
        hud.close()

    def test_a_finished_site_says_so_while_docked(self) -> None:
        hud, state = self._hud()
        state.apply(DEPOT | {"ConstructionProgress": 1.0, "ConstructionComplete": True})
        state.apply(DOCKED_AT_SITE)
        hud.rebuild()
        self.assertIn("достроена", hud.bar_text())
        hud.close()

    def test_it_is_on_by_default_in_the_bottom_row(self) -> None:
        config = Config()
        self.assertIn("colony", config.overlay.status_segments)


if __name__ == "__main__":
    unittest.main()
