"""The jump plan: where the commander is heading next."""

from __future__ import annotations

import unittest

from elite_hud.config import Config
from elite_hud.state import GameState, JumpPlan


class JumpPlanUnitTests(unittest.TestCase):
    def test_a_fresh_plan_is_inactive(self) -> None:
        plan = JumpPlan()
        self.assertFalse(plan.active)

    def test_active_once_it_names_a_system(self) -> None:
        self.assertTrue(JumpPlan(target="Sol").active)

    def test_clearing_empties_everything(self) -> None:
        plan = JumpPlan(target="Sol", star_class="G", remaining=3, route=["A", "Sol"])
        plan.clear()
        self.assertFalse(plan.active)
        self.assertEqual(plan.route, [])
        self.assertEqual(plan.remaining, 0)

    def test_arriving_at_the_named_system_clears_the_plan(self) -> None:
        plan = JumpPlan(target="Sol", star_class="G", remaining=8)
        plan.arrive("Sol")
        self.assertFalse(plan.active)

    def test_arriving_elsewhere_leaves_the_plan_alone(self) -> None:
        plan = JumpPlan(target="Sol", remaining=8)
        plan.arrive("Lave")
        self.assertEqual(plan.target, "Sol")
        self.assertEqual(plan.remaining, 8)

    def test_arriving_with_no_plan_is_harmless(self) -> None:
        plan = JumpPlan()
        plan.arrive("Sol")
        self.assertFalse(plan.active)

    def test_arriving_does_not_count_down(self) -> None:
        """The name is the next waypoint, not the destination.

        Decrementing would leave the HUD reading "7 jumps" while the commander
        sits in the system it names. The game re-issues FSDTarget with the
        following waypoint anyway, so its own number always wins.
        """
        plan = JumpPlan(target="Sol", remaining=8)
        plan.arrive("Sol")
        self.assertEqual(plan.remaining, 0)


class JumpPlanStateTests(unittest.TestCase):
    def setUp(self) -> None:
        config = Config()
        self.state = GameState()
        self.state.apply({"event": "FSDJump", "StarSystem": "Start", "SystemAddress": 1})

    def target(self, **kwargs) -> None:
        event = {
            "event": "FSDTarget",
            "Name": "Goal",
            "StarClass": "G",
            "RemainingJumpsInRoute": 5,
            "SystemAddress": 2,
        }
        event.update(kwargs)
        self.state.apply(event)

    def test_a_target_sets_the_plan(self) -> None:
        self.target()
        plan = self.state.jump_plan
        self.assertEqual(plan.target, "Goal")
        self.assertEqual(plan.star_class, "G")
        self.assertEqual(plan.remaining, 5)

    def test_a_target_without_a_remaining_count_counts_as_one(self) -> None:
        self.state.apply({"event": "FSDTarget", "Name": "Goal"})
        self.assertEqual(self.state.jump_plan.remaining, 1)

    def test_a_target_without_a_name_is_ignored(self) -> None:
        self.target(Name="")
        self.assertFalse(self.state.jump_plan.active)

    def test_a_nameless_target_leaves_an_earlier_plan_alone(self) -> None:
        self.target()
        self.target(Name=None)
        self.assertEqual(self.state.jump_plan.target, "Goal")

    def test_jumping_to_the_target_ends_the_plan(self) -> None:
        self.target(Name="Goal")
        self.state.apply({"event": "FSDJump", "StarSystem": "Goal", "SystemAddress": 2})
        self.assertFalse(self.state.jump_plan.active)

    def test_reaching_the_target_by_location_also_ends_the_plan(self) -> None:
        """Logged in at the destination, e.g. after a carrier ride."""
        self.target(Name="Goal")
        self.state.apply({"event": "Location", "StarSystem": "Goal", "SystemAddress": 2})
        self.assertFalse(self.state.jump_plan.active)

    def test_re_targeting_mid_route_replaces_the_plan(self) -> None:
        self.target(Name="Waypoint", RemainingJumpsInRoute=8)
        self.target(Name="NextOne", RemainingJumpsInRoute=7, StarClass="K")
        plan = self.state.jump_plan
        self.assertEqual(plan.target, "NextOne")
        self.assertEqual(plan.remaining, 7)
        self.assertEqual(plan.star_class, "K")

    # -- routes -------------------------------------------------------------

    def test_a_plotted_route_names_its_own_destination(self) -> None:
        self.state.apply(
            {
                "event": "NavRoute",
                "Route": [
                    {"StarSystem": "One", "StarClass": "K", "StarPos": [1.0, 2.0, 3.0]},
                    {"StarSystem": "Two", "StarClass": "M"},
                    {"StarSystem": "Three", "StarClass": "G"},
                ],
            }
        )
        plan = self.state.jump_plan
        self.assertEqual(plan.route, ["One", "Two", "Three"])
        # The last leg is the destination, and beats FSDTarget's count.
        self.assertEqual(plan.target, "Three")

    def test_an_empty_route_clears_the_legs_but_not_the_target(self) -> None:
        """The journals contain 83 NavRoute events and not one has a leg."""
        self.target(Name="Goal")
        self.state.apply({"event": "NavRoute", "Route": []})
        self.assertEqual(self.state.jump_plan.route, [])
        self.assertEqual(self.state.jump_plan.target, "Goal")

    def test_nav_route_clear_keeps_the_target(self) -> None:
        """The clear arrives just before the jump, when the plan still matters."""
        self.target(Name="Goal")
        self.state.apply({"event": "NavRouteClear"})
        self.assertEqual(self.state.jump_plan.target, "Goal")

    def test_a_route_without_usable_legs_is_ignored(self) -> None:
        self.target(Name="Goal")
        self.state.apply(
            {"event": "NavRoute", "Route": [None, "x", {"StarClass": "K"}]}
        )
        self.assertEqual(self.state.jump_plan.route, [])
        self.assertEqual(self.state.jump_plan.target, "Goal")

    def test_a_route_overrides_an_earlier_target_name(self) -> None:
        self.target(Name="Waypoint", RemainingJumpsInRoute=3)
        self.state.apply(
            {"event": "NavRoute", "Route": [{"StarSystem": "A"}, {"StarSystem": "Z"}]}
        )
        self.assertEqual(self.state.jump_plan.target, "Z")


if __name__ == "__main__":
    unittest.main()
