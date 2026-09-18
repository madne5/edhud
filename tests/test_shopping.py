"""The shopping list, and the market lookup behind it.

The Spansh endpoint publishes no documentation, so the request shape here was
established by probing it. These tests pin what was learned, because every one of
those details fails silently if it is got wrong: a wrong reference system leaves
distances measured from Sol, a missing sort leaves the nearest station a thousand
light years away, and a wrong filter wrapper returns the whole catalogue as
though no filter had been applied at all.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.market import (
    Offer,
    SpanshMarket,
    _spansh_name,
    normalise_commodity,
    parse_offers,
)
from elite_hud.shopping import Need, ShoppingList
from elite_hud.state import GameState

#: The two commodities that matter here, as the journal spells them and as
#: Spansh spells them. They differ, and the whole catalogue was checked for
#: collisions after normalising -- 411 names, no clashes.
JOURNAL_WINE = "$Wine_Name;"
SPANSH_WINE = "Wine"
JOURNAL_MEAT = "$SyntheticMeat_Name;"
SPANSH_MEAT = "Synthetic Meat"


class NormaliseTests(unittest.TestCase):
    def test_a_journal_symbol_and_a_spansh_name_agree(self) -> None:
        self.assertEqual(normalise_commodity(JOURNAL_WINE), normalise_commodity(SPANSH_WINE))
        self.assertEqual(normalise_commodity(JOURNAL_MEAT), normalise_commodity(SPANSH_MEAT))

    def test_case_and_separators_are_ignored(self) -> None:
        for text in ("$LowTemperatureDiamonds_Name;", "Low Temperature Diamonds",
                     "low temperature diamonds"):
            self.assertEqual(normalise_commodity(text), "lowtemperaturediamonds")

    def test_acronyms_survive(self) -> None:
        """The catalogue has "AI Relics", "CMM Composite", "H.E. Suits"."""
        self.assertEqual(normalise_commodity("AI Relics"), "airelics")
        self.assertEqual(normalise_commodity("$CMMComposite_Name;"), "cmmcomposite")
        self.assertEqual(normalise_commodity("H.E. Suits"), "hesuits")

    def test_nothing_normalises_to_nothing_useful_by_accident(self) -> None:
        self.assertEqual(normalise_commodity(""), "")
        self.assertEqual(normalise_commodity(None), "")


class SpanshNameTests(unittest.TestCase):
    """The fallback used when the catalogue cannot be fetched."""

    def test_camel_case_is_split(self) -> None:
        self.assertEqual(_spansh_name(JOURNAL_MEAT), SPANSH_MEAT)
        self.assertEqual(_spansh_name("$InsulatingMembrane_Name;"), "Insulating Membrane")

    def test_an_acronym_run_is_split_once(self) -> None:
        """CMMComposite is CMM Composite, not one long word."""
        self.assertEqual(_spansh_name("$CMMComposite_Name;"), "CMM Composite")
        self.assertEqual(_spansh_name("$AIRelics_Name;"), "AI Relics")

    def test_a_plain_name_is_passed_through(self) -> None:
        self.assertEqual(_spansh_name(SPANSH_WINE), SPANSH_WINE)

    def test_the_catalogue_wins_over_the_fallback(self) -> None:
        """The fallback gets "HE Suits" where the catalogue says "H.E. Suits",
        so the catalogue must be preferred when it is available."""

        class Stub(SpanshMarket):
            def catalogue(self):  # noqa: D102 - test double
                return {"hesuits": "H.E. Suits"}

        self.assertEqual(Stub().spansh_name("$HESuits_Name;"), "H.E. Suits")


class ParseTests(unittest.TestCase):
    def payload(self) -> dict:
        return {
            "count": 2,
            "reference": {"name": "Achenar"},
            "results": [
                {"system_name": "Liabeze", "name": "W3H-71N", "distance": 6.1,
                 "distance_to_arrival": 120.0, "large_pads": 1, "medium_pads": 0,
                 "small_pads": 0, "market_updated_at": "2026-08-07T20:08:33Z",
                 "market": [{"commodity": "Low Temperature Diamonds", "supply": 40,
                             "buy_price": 1234}]},
                {"system_name": "ICZ HR-V b2-1", "name": "T9X-4KZ", "distance": 7.4,
                 "large_pads": 0, "medium_pads": 2, "small_pads": 1,
                 "market": [{"commodity": "Wine", "supply": 5, "buy_price": 99}]},
            ],
        }

    def test_it_reads_the_fields_the_popup_shows(self) -> None:
        offers = parse_offers("$LowTemperatureDiamonds_Name;", self.payload())
        self.assertEqual(len(offers), 2)
        first = offers[0]
        self.assertEqual(first.system, "Liabeze")
        self.assertEqual(first.station, "W3H-71N")
        self.assertAlmostEqual(first.distance, 6.1)
        self.assertEqual(first.largest_pad, "L")
        self.assertEqual(first.supply, 40)

    def test_the_supply_of_the_wanted_commodity_is_the_one_read(self) -> None:
        """A station selling many things must not report some other supply."""
        offers = parse_offers(JOURNAL_WINE, self.payload())
        self.assertEqual(offers[0].supply, 0, "Liabeze does not sell wine")
        self.assertEqual(offers[1].supply, 5)

    def test_a_malformed_response_yields_nothing(self) -> None:
        for bad in ({}, {"results": "nope"}, {"results": [None, "x", {"name": "no system"}]}):
            with self.subTest(payload=bad):
                self.assertEqual(parse_offers(JOURNAL_WINE, bad), [])


class PadTests(unittest.TestCase):
    def offer(self, large: int, medium: int, small: int) -> Offer:
        return Offer(commodity="Wine", system="S", station="T",
                     large_pads=large, medium_pads=medium, small_pads=small)

    def test_a_large_pad_meets_every_requirement(self) -> None:
        offer = self.offer(1, 0, 0)
        self.assertTrue(offer.fits("L"))
        self.assertTrue(offer.fits("M"))
        self.assertTrue(offer.fits("S"))

    def test_a_medium_pad_does_not_meet_a_large_requirement(self) -> None:
        offer = self.offer(0, 3, 2)
        self.assertFalse(offer.fits("L"))
        self.assertTrue(offer.fits("M"))
        self.assertTrue(offer.fits("S"))

    def test_a_small_pad_only_meets_a_small_requirement(self) -> None:
        offer = self.offer(0, 0, 1)
        self.assertFalse(offer.fits("L"))
        self.assertFalse(offer.fits("M"))
        self.assertTrue(offer.fits("S"))

    def test_no_pads_meets_nothing(self) -> None:
        offer = self.offer(0, 0, 0)
        self.assertFalse(offer.fits("S"))

    def test_an_empty_requirement_accepts_anything(self) -> None:
        self.assertTrue(self.offer(0, 0, 0).fits(""))

    def test_the_requirement_is_case_insensitive(self) -> None:
        self.assertTrue(self.offer(1, 0, 0).fits("l"))


class RequestShapeTests(unittest.TestCase):
    """The details that fail silently when they are wrong."""

    class Recorder(SpanshMarket):
        def __init__(self) -> None:
            super().__init__()
            self.sent: list[dict] = []

        def catalogue(self):  # noqa: D102 - test double
            return {}

        def _post(self, body):  # noqa: D102 - test double
            self.sent.append(body)
            return {"count": 0, "results": []}

    def test_the_reference_system_is_named_as_the_api_expects(self) -> None:
        """`reference` is accepted and ignored, which leaves distances measured
        from Sol -- plausible and wrong."""
        market = self.Recorder()
        market.find_sellers(JOURNAL_WINE, reference_system="Achenar", minimum_pad="L")
        self.assertEqual(market.sent[0]["reference_system"], "Achenar")
        self.assertNotIn("reference", market.sent[0])

    def test_distance_sorting_is_requested(self) -> None:
        market = self.Recorder()
        market.find_sellers(JOURNAL_WINE, reference_system="Achenar", minimum_pad="L")
        self.assertEqual(market.sent[0]["sort"], [{"distance": {"direction": "asc"}}])

    def test_each_filter_uses_the_shape_it_insists_on(self) -> None:
        """has_large_pad wants the wrapper and rejects the bare form;
        export_commodities is the other way round and ignores the wrapper."""
        market = self.Recorder()
        market.find_sellers(JOURNAL_WINE, reference_system="Achenar", minimum_pad="L")
        filters = market.sent[0]["filters"]
        self.assertEqual(filters["has_market"], {"value": True})
        self.assertEqual(filters["export_commodities"], [{"name": SPANSH_WINE}])

    def test_the_request_asks_for_more_than_it_will_show(self) -> None:
        """The pad filter runs locally, so some of the page is discarded."""
        market = self.Recorder()
        market.find_sellers(JOURNAL_WINE, reference_system="Achenar",
                            minimum_pad="L", limit=3)
        self.assertGreater(market.sent[0]["size"], 3)

    def test_a_repeated_lookup_is_cached(self) -> None:
        market = self.Recorder()
        for _ in range(3):
            market.find_sellers(JOURNAL_WINE, reference_system="Achenar", minimum_pad="L")
        self.assertEqual(len(market.sent), 1)

    def test_a_different_pad_requirement_is_not_cached(self) -> None:
        market = self.Recorder()
        market.find_sellers(JOURNAL_WINE, reference_system="Achenar", minimum_pad="L")
        market.find_sellers(JOURNAL_WINE, reference_system="Achenar", minimum_pad="M")
        self.assertEqual(len(market.sent), 2)

    def test_offers_that_are_too_small_are_filtered_out(self) -> None:
        class SmallOnly(SpanshMarket):
            def catalogue(self):  # noqa: D102 - test double
                return {}

            def _post(self, body):  # noqa: D102 - test double
                return {"count": 1, "results": [
                    {"system_name": "Sol", "name": "Tiny Outpost",
                     "large_pads": 0, "medium_pads": 0, "small_pads": 2}]}

        self.assertEqual(
            SmallOnly().find_sellers(JOURNAL_WINE, reference_system="Sol",
                                     minimum_pad="L"),
            [],
        )

    def test_a_missing_commodity_or_reference_is_not_asked_for(self) -> None:
        market = self.Recorder()
        self.assertEqual(market.find_sellers("", reference_system="Sol"), [])
        self.assertEqual(market.find_sellers(JOURNAL_WINE, reference_system=""), [])
        self.assertEqual(market.sent, [])

    def test_a_failed_request_yields_no_offers_rather_than_raising(self) -> None:
        class Broken(SpanshMarket):
            def catalogue(self):  # noqa: D102 - test double
                return {}

            def _post(self, body):  # noqa: D102 - test double
                return None

        self.assertEqual(
            Broken().find_sellers(JOURNAL_WINE, reference_system="Sol"), []
        )


class ShoppingListTests(unittest.TestCase):
    def test_needs_are_summed_per_commodity(self) -> None:
        shopping = ShoppingList()
        shopping.add(1, JOURNAL_WINE, "Вино", 18, "Ngalinn")
        shopping.add(2, JOURNAL_WINE, "Вино", 20, "HIP 8060")
        items = shopping.items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].count, 38)
        self.assertEqual(items[0].missions, 2)
        self.assertEqual(items[0].destinations, ("Ngalinn", "HIP 8060"))

    def test_different_commodities_are_separate(self) -> None:
        shopping = ShoppingList()
        shopping.add(1, JOURNAL_WINE, "Вино", 1)
        shopping.add(2, JOURNAL_MEAT, "Синтетическое мясо", 1)
        self.assertEqual(len(shopping.items), 2)

    def test_removing_a_mission_takes_its_cargo_with_it(self) -> None:
        """Totals cannot be decremented on their own: missions finish in any
        order, and a running total would drift."""
        shopping = ShoppingList()
        shopping.add(1, JOURNAL_WINE, "Вино", 18)
        shopping.add(2, JOURNAL_WINE, "Вино", 20)
        shopping.remove(1)
        self.assertEqual(shopping.items[0].count, 20)
        self.assertEqual(shopping.items[0].missions, 1)

    def test_the_list_empties_when_the_missions_do(self) -> None:
        shopping = ShoppingList()
        shopping.add(1, JOURNAL_WINE, "Вино", 1)
        shopping.remove(1)
        self.assertTrue(shopping.empty)
        self.assertEqual(shopping.items, [])

    def test_the_heaviest_need_comes_first(self) -> None:
        shopping = ShoppingList()
        shopping.add(1, JOURNAL_WINE, "Вино", 5)
        shopping.add(2, JOURNAL_MEAT, "Мясо", 60)
        self.assertEqual([need.display for need in shopping.items], ["Мясо", "Вино"])

    def test_the_order_is_stable_for_equal_counts(self) -> None:
        """An order that shuffles between redraws makes the popup jump."""
        shopping = ShoppingList()
        shopping.add(1, JOURNAL_WINE, "Вино", 5)
        shopping.add(2, JOURNAL_MEAT, "Мясо", 5)
        self.assertEqual(shopping.items, shopping.items)

    def test_an_empty_commodity_is_ignored(self) -> None:
        shopping = ShoppingList()
        shopping.add(1, "", "?", 5)
        self.assertTrue(shopping.empty)

    def test_a_need_describes_itself(self) -> None:
        shopping = ShoppingList()
        shopping.add(1, JOURNAL_WINE, "Вино", 18)
        shopping.add(2, JOURNAL_WINE, "Вино", 18)
        self.assertIn("Вино", shopping.items[0].describe())
        self.assertIn("2 missions", shopping.items[0].describe())


class StateShoppingTests(unittest.TestCase):
    def setUp(self) -> None:
        config = Config()
        self.state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)

    def accepted(self, mission_id: int, commodity: str | None, count: int = 1,
                 destination: str = "Ngalinn") -> None:
        event = {"event": "MissionAccepted", "MissionID": mission_id,
                 "Name": "Mission_Collect_RankEmp", "DestinationSystem": destination}
        if commodity:
            event.update({"Commodity": commodity, "Commodity_Localised": "Вино",
                          "Count": count})
        self.state.apply(event)

    def test_a_delivery_mission_becomes_a_need(self) -> None:
        self.accepted(1, JOURNAL_WINE, 18)
        needs = self.state.shopping.items
        self.assertEqual(len(needs), 1)
        self.assertEqual(needs[0].count, 18)
        self.assertEqual(needs[0].destinations, ("Ngalinn",))

    def test_a_mission_without_cargo_is_ignored(self) -> None:
        """Couriers are most of the traffic and have nothing to buy."""
        self.accepted(1, None)
        self.assertTrue(self.state.shopping.empty)

    def test_completing_a_mission_removes_its_need(self) -> None:
        self.accepted(1, JOURNAL_WINE, 18)
        self.state.apply({"event": "MissionCompleted", "MissionID": 1})
        self.assertTrue(self.state.shopping.empty)

    def test_abandoning_a_mission_removes_its_need(self) -> None:
        self.accepted(1, JOURNAL_WINE, 18)
        self.state.apply({"event": "MissionAbandoned", "MissionID": 1})
        self.assertTrue(self.state.shopping.empty)

    def test_the_startup_mission_list_seeds_the_needs(self) -> None:
        """Otherwise a HUD started mid-session would show an empty list until
        the commander happened to accept something new."""
        self.state.apply({"event": "Missions", "Active": [
            {"MissionID": 5, "Commodity": JOURNAL_MEAT,
             "Commodity_Localised": "Синтетическое мясо", "Count": 63,
             "DestinationSystem": "Zhangana"},
        ]})
        needs = self.state.shopping.items
        self.assertEqual(len(needs), 1)
        self.assertEqual(needs[0].count, 63)

    def test_a_mission_list_without_commodities_seeds_nothing(self) -> None:
        self.state.apply({"event": "Missions", "Active": [{"MissionID": 5}]})
        self.assertTrue(self.state.shopping.empty)


class ShoppingConfigTests(unittest.TestCase):
    def test_it_is_off_by_default(self) -> None:
        """It makes network requests on the commander's behalf."""
        self.assertFalse(Config().shopping.enabled)

    def test_the_pad_requirement_defaults_to_large(self) -> None:
        self.assertEqual(Config().shopping.min_pad, "L")

    def test_an_unknown_pad_falls_back_to_large(self) -> None:
        config = Config()
        config.shopping.min_pad = "XXL"
        config.validate()
        self.assertEqual(config.shopping.min_pad, "L")

    def test_the_pad_is_normalised_to_upper_case(self) -> None:
        config = Config()
        config.shopping.min_pad = " m "
        config.validate()
        self.assertEqual(config.shopping.min_pad, "M")

    def test_the_limits_are_clamped(self) -> None:
        config = Config()
        config.shopping.systems_per_commodity = 99
        config.shopping.refresh_seconds = 1.0
        config.validate()
        self.assertEqual(config.shopping.systems_per_commodity, 10)
        self.assertEqual(config.shopping.refresh_seconds, 30.0)


class GalaxyMapTests(unittest.TestCase):
    """The popup is driven by GuiFocus, the only signal for the map opening."""

    def test_the_galaxy_map_is_recognised(self) -> None:
        from elite_hud.status import parse_status

        self.assertTrue(parse_status({"GuiFocus": 6}).galaxy_map_open)

    def test_other_panels_are_not_the_galaxy_map(self) -> None:
        from elite_hud.status import parse_status

        for focus in (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11):
            with self.subTest(gui_focus=focus):
                self.assertFalse(parse_status({"GuiFocus": focus}).galaxy_map_open)

    def test_a_status_without_gui_focus_is_not_the_map(self) -> None:
        from elite_hud.status import parse_status

        self.assertFalse(parse_status({"Flags": 0}).galaxy_map_open)


if __name__ == "__main__":
    unittest.main()
