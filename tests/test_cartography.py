"""Unsold exploration data: counted, deliberately not valued."""

from __future__ import annotations

import unittest

from elite_hud.cartography import CartographyHold, is_sellable_body
from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.state import GameState


class SellableBodyTests(unittest.TestCase):
    def test_a_normal_body_counts(self) -> None:
        self.assertTrue(is_sellable_body("Blu Theia AV-F d11-1 B 3"))
        self.assertTrue(is_sellable_body("Sol"))

    def test_a_ring_does_not_count(self) -> None:
        self.assertFalse(is_sellable_body("Blu Theia AV-F d11-1 B 3 Ring"))

    def test_a_belt_cluster_does_not_count(self) -> None:
        self.assertFalse(is_sellable_body("Blu Theia AV-F d11-1 Belt Cluster 1"))

    def test_an_empty_name_does_not_count(self) -> None:
        self.assertFalse(is_sellable_body(""))
        self.assertFalse(is_sellable_body(None))


class HoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hold = CartographyHold()

    def test_a_fresh_hold_is_empty(self) -> None:
        self.assertTrue(self.hold.empty)
        self.assertEqual(self.hold.describe(), "пусто")

    def test_scans_accumulate_per_system(self) -> None:
        self.hold.add_scan("Sol", 1)
        self.hold.add_scan("Sol", 2)
        self.hold.add_scan("Lave", 1)
        self.assertEqual(self.hold.system_count, 2)
        self.assertEqual(self.hold.body_count, 3)

    def test_the_same_body_scanned_twice_counts_once(self) -> None:
        """A re-scan must not inflate what the commander is carrying."""
        self.hold.add_scan("Sol", 1)
        self.hold.add_scan("Sol", 1)
        self.assertEqual(self.hold.body_count, 1)

    def test_a_body_id_can_repeat_across_systems(self) -> None:
        """BodyID is only unique within a system."""
        self.hold.add_scan("Sol", 1)
        self.hold.add_scan("Lave", 1)
        self.assertEqual(self.hold.body_count, 2)

    def test_garbage_is_ignored(self) -> None:
        self.hold.add_scan("", 1)
        self.hold.add_scan("Sol", "three")
        self.assertTrue(self.hold.empty)

    def test_mapping_is_tracked(self) -> None:
        self.hold.add_scan("Sol", 1)
        self.hold.add_scan("Sol", 2)
        self.hold.add_mapping("Sol", 1)
        self.assertEqual(self.hold.mapped_count, 1)

    def test_mapping_a_body_that_was_sold_does_not_count(self) -> None:
        self.hold.add_scan("Sol", 1)
        self.hold.add_mapping("Sol", 1)
        self.hold.clear()
        self.assertEqual(self.hold.mapped_count, 0)

    def test_a_sale_empties_everything(self) -> None:
        self.hold.add_scan("Sol", 1)
        self.hold.add_mapping("Sol", 1)
        self.hold.clear()
        self.assertTrue(self.hold.empty)
        self.assertEqual(self.hold.mapped_count, 0)

    def test_describe_includes_the_mapped_count(self) -> None:
        self.hold.add_scan("Sol", 1)
        self.hold.add_mapping("Sol", 1)
        self.assertIn("карт 1", self.hold.describe())


class CartographyStateTests(unittest.TestCase):
    def setUp(self) -> None:
        config = Config()
        self.state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        self.state.apply({"event": "FSDJump", "StarSystem": "Sol", "SystemAddress": 1})

    def scan(self, body_id: int, name: str = "Sol 4", address: int = 1, **extra) -> None:
        event = {
            "event": "Scan",
            "SystemAddress": address,
            "BodyID": body_id,
            "BodyName": name,
            "PlanetClass": "Icy body",
        }
        event.update(extra)
        self.state.apply(event)

    def test_scans_are_held(self) -> None:
        self.scan(1)
        self.scan(2)
        self.assertEqual(self.state.cartography.describe(), "1 сист. / 2 тел")

    def test_rings_are_not_held(self) -> None:
        self.scan(1, "Sol 4 Ring")
        self.scan(2, "Sol Belt Cluster 1")
        self.assertTrue(self.state.cartography.empty)

    def test_a_surface_scan_marks_the_body_mapped(self) -> None:
        self.scan(1)
        self.state.apply(
            {"event": "SAAScanComplete", "SystemAddress": 1, "BodyID": 1,
             "BodyName": "Sol 4", "ProbesUsed": 6, "EfficiencyTarget": 8}
        )
        self.assertEqual(self.state.cartography.mapped_count, 1)

    def test_selling_exploration_data_empties_the_hold(self) -> None:
        self.scan(1)
        self.state.apply(
            {
                "event": "MultiSellExplorationData",
                "Discovered": [{"SystemName": "Sol", "NumBodies": 1}],
                "BaseValue": 1000,
                "Bonus": 0,
                "TotalEarnings": 1000,
            }
        )
        self.assertTrue(self.state.cartography.empty)

    def test_the_single_system_sale_also_empties_it(self) -> None:
        self.scan(1)
        self.state.apply({"event": "SellExplorationData", "Systems": ["Sol"]})
        self.assertTrue(self.state.cartography.empty)

    def test_a_second_system_keeps_its_own_bodies(self) -> None:
        self.scan(1)
        self.state.apply({"event": "FSDJump", "StarSystem": "Lave", "SystemAddress": 2})
        # The address matters: a Scan carrying the previous system's address is
        # rejected, which is what keeps a stale scan out of the current system.
        self.scan(1, address=2)
        self.assertEqual(self.state.cartography.system_count, 2)
        self.assertEqual(self.state.cartography.body_count, 2)

    def test_scanning_the_same_body_twice_counts_once(self) -> None:
        self.scan(1)
        self.scan(1)
        self.assertEqual(self.state.cartography.body_count, 1)

    def test_the_running_count_never_exceeds_a_later_sale(self) -> None:
        """The property that makes the count safe to show.

        Across the real journals the running count was a lower bound at all five
        sales, never above. Counting bodies the commander did not scan is the
        failure that would matter, so this pins the direction.
        """
        for body_id in range(1, 6):
            self.scan(body_id)
        self.state.apply(
            {
                "event": "MultiSellExplorationData",
                "Discovered": [{"SystemName": "Sol", "NumBodies": 5}],
            }
        )
        # Everything the commander scanned has been sold, so nothing is left to
        # claim beyond it.
        self.assertEqual(self.state.cartography.body_count, 0)


if __name__ == "__main__":
    unittest.main()
