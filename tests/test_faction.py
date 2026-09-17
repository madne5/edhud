"""Following one faction from system to system."""

from __future__ import annotations

import unittest

from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.state import FactionStatus, GameState

#: The name as the journals really spell it, which is not what a commander
#: would type: the answer to "Traders & Explorers" is "Traders & Explorers Inc.".
FULL_NAME = "Traders & Explorers Inc."


def system_event(factions, controller="", **extra) -> dict:
    event = {
        "event": "FSDJump",
        "StarSystem": "Wregoe DG-H b51-5",
        "SystemAddress": 1,
        "Population": 1000,
        "Factions": factions,
    }
    if controller:
        event["SystemFaction"] = {"Name": controller}
    event.update(extra)
    return event


def faction_entry(name, influence=0.5, **extra) -> dict:
    entry = {"Name": name, "Influence": influence, "FactionState": "None"}
    entry.update(extra)
    return entry


class MatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.status = FactionStatus(wanted="Traders & Explorers")

    def test_contains_is_the_default_and_finds_the_longer_name(self) -> None:
        self.assertTrue(self.status.matches(FULL_NAME, "contains"))

    def test_exact_needs_the_whole_name(self) -> None:
        """The reason the default is loose: this is what a commander types."""
        self.assertFalse(self.status.matches(FULL_NAME, "exact"))
        exact = FactionStatus(wanted=FULL_NAME)
        self.assertTrue(exact.matches(FULL_NAME, "exact"))

    def test_matching_ignores_case_and_padding(self) -> None:
        self.assertTrue(self.status.matches("  traders & EXPLORERS inc.  ", "contains"))
        self.assertTrue(
            FactionStatus(wanted="traders & explorers inc.").matches(FULL_NAME, "exact")
        )

    def test_an_empty_setting_matches_nothing(self) -> None:
        self.assertFalse(FactionStatus(wanted="").matches(FULL_NAME, "contains"))

    def test_an_empty_candidate_matches_nothing(self) -> None:
        self.assertFalse(self.status.matches("", "contains"))

    def test_percent_rounds(self) -> None:
        status = FactionStatus(influence=0.80981)
        self.assertEqual(status.percent, 81)
        self.assertEqual(FactionStatus(influence=0.303).percent, 30)
        self.assertEqual(FactionStatus(influence=0.0).percent, 0)

    def test_clear_resets_everything(self) -> None:
        status = FactionStatus(wanted="X", matched="X", found=True, controlling=True,
                               influence=0.5, reputation=10.0, state="Boom",
                               system="Sol", inhabited=True)
        status.clear()
        self.assertFalse(status.found)
        self.assertFalse(status.controlling)
        self.assertEqual(status.matched, "")
        self.assertEqual(status.influence, 0.0)
        self.assertIsNone(status.reputation)
        self.assertFalse(status.inhabited)
        # The setting itself survives, or following would switch itself off.
        self.assertEqual(status.wanted, "X")


class FactionStateTests(unittest.TestCase):
    def _state(self, name: str = "Traders & Explorers", match: str = "contains") -> GameState:
        config = Config()
        return GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            faction_name=name,
            faction_match=match,
        )

    def test_finds_the_faction_and_its_influence(self) -> None:
        state = self._state()
        state.apply(
            system_event(
                [faction_entry(FULL_NAME, 0.303)],
                controller="Someone Else",
            )
        )
        status = state.faction
        self.assertTrue(status.found)
        self.assertTrue(status.inhabited)
        self.assertEqual(status.matched, FULL_NAME)
        self.assertEqual(status.percent, 30)
        # Found but not in charge: the red case.
        self.assertFalse(status.controlling)
        self.assertEqual(status.system, "Wregoe DG-H b51-5")

    def test_controlling_when_it_is_the_system_faction(self) -> None:
        state = self._state()
        state.apply(system_event([faction_entry(FULL_NAME, 0.80981)], controller=FULL_NAME))
        self.assertTrue(state.faction.found)
        self.assertTrue(state.faction.controlling)
        self.assertEqual(state.faction.percent, 81)

    def test_reputation_and_state_are_captured(self) -> None:
        state = self._state()
        state.apply(
            system_event(
                [faction_entry(FULL_NAME, 0.5, MyReputation=100.0, FactionState="Expansion")]
            )
        )
        self.assertAlmostEqual(state.faction.reputation, 100.0)
        self.assertEqual(state.faction.state, "Expansion")

    def test_an_uninhabited_system_is_not_a_zero_influence_system(self) -> None:
        """92 of 133 jump events in the journals have an empty faction list,
        and every one of them is a system with no population."""
        state = self._state()
        state.apply(system_event([faction_entry(FULL_NAME, 0.8)], controller=FULL_NAME))
        self.assertTrue(state.faction.found)

        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "Blu Theia AV-F d11-1",
                "SystemAddress": 2,
                "Population": 0,
                "Factions": [],
            }
        )
        status = state.faction
        self.assertFalse(status.inhabited)
        # The previous system's figure must not linger on screen.
        self.assertFalse(status.found)
        self.assertEqual(status.percent, 0)

    def test_no_configured_faction_means_nothing_is_tracked(self) -> None:
        state = self._state(name="")
        state.apply(system_event([faction_entry(FULL_NAME, 0.8)], controller=FULL_NAME))
        self.assertFalse(state.faction.found)
        self.assertFalse(state.faction.inhabited)

    def test_the_location_event_is_read_too(self) -> None:
        """A commander who logs in on a station never sends FSDJump."""
        state = self._state()
        state.apply(
            {
                "event": "Location",
                "StarSystem": "Wregoe DG-H b51-4",
                "SystemAddress": 3,
                "Population": 500,
                "SystemFaction": {"Name": FULL_NAME},
                "Factions": [faction_entry(FULL_NAME, 0.633703)],
            }
        )
        self.assertTrue(state.faction.found)
        self.assertTrue(state.faction.controlling)
        self.assertEqual(state.faction.percent, 63)

    def test_exact_mode_ignores_the_longer_name(self) -> None:
        state = self._state(match="exact")
        state.apply(system_event([faction_entry(FULL_NAME, 0.8)], controller=FULL_NAME))
        self.assertFalse(state.faction.found)

    def test_the_matching_faction_is_chosen_among_many(self) -> None:
        state = self._state()
        state.apply(
            system_event(
                [
                    faction_entry("Someone Else", 0.6),
                    faction_entry(FULL_NAME, 0.25),
                    faction_entry("Traders & Explorers PLC", 0.15),
                ],
                controller="Someone Else",
            )
        )
        # First match wins, and both candidates contain the wanted text.
        self.assertEqual(state.faction.matched, FULL_NAME)
        self.assertEqual(state.faction.percent, 25)

    def test_no_controller_reported_means_not_controlling(self) -> None:
        state = self._state()
        state.apply(system_event([faction_entry(FULL_NAME, 0.5)]))
        self.assertTrue(state.faction.found)
        self.assertFalse(state.faction.controlling)

    def test_garbage_influence_is_zero_rather_than_a_crash(self) -> None:
        state = self._state()
        state.apply(
            system_event([{"Name": FULL_NAME, "Influence": "lots", "MyReputation": True}])
        )
        self.assertEqual(state.faction.influence, 0.0)
        self.assertIsNone(state.faction.reputation)

    def test_garbage_faction_entries_are_skipped(self) -> None:
        state = self._state()
        state.apply(system_event([None, "x", {"Influence": 0.5}]))
        self.assertFalse(state.faction.found)
        self.assertTrue(state.faction.inhabited)

    def test_a_faction_list_that_is_not_a_list_is_ignored(self) -> None:
        state = self._state()
        state.apply(system_event("nonsense"))
        self.assertFalse(state.faction.inhabited)


if __name__ == "__main__":
    unittest.main()
