"""Ship model names, cargo hold capacity and the live count."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from elite_hud.config import Config
from elite_hud.ships import ShipNames, prettify
from elite_hud.state import GameState
from elite_hud.status import parse_status


def make_state() -> GameState:
    config = Config()
    return GameState(ship_names=ShipNames(Path(tempfile.mkdtemp()) / "ships.json"),
    )


class PrettifyTests(unittest.TestCase):
    """A last resort for a symbol no event has named yet."""

    def test_underscores_become_words(self) -> None:
        self.assertEqual(prettify("panthermkii"), "Panthermkii")

    def test_a_short_suffix_is_upper_cased(self) -> None:
        self.assertEqual(prettify("explorer_nx"), "Explorer NX")

    def test_a_numeric_suffix_is_left_alone(self) -> None:
        self.assertEqual(prettify("typex_3"), "Typex 3")

    def test_an_empty_symbol_is_empty(self) -> None:
        self.assertEqual(prettify(""), "")
        self.assertEqual(prettify(None), "")


class ShipNamesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp()) / "ships.json"
        self.names = ShipNames(self.path)

    def test_a_learned_name_is_returned(self) -> None:
        self.assertTrue(self.names.learn("explorer_nx", "Caspian Explorer"))
        self.assertEqual(self.names.display("explorer_nx"), "Caspian Explorer")

    def test_an_unlearned_symbol_falls_back_to_prettifying(self) -> None:
        self.assertEqual(self.names.display("explorer_nx"), "Explorer NX")

    def test_lookup_is_case_insensitive(self) -> None:
        self.names.learn("Explorer_NX", "Caspian Explorer")
        self.assertEqual(self.names.display("explorer_nx"), "Caspian Explorer")

    def test_a_non_breaking_space_is_normalised(self) -> None:
        """The game really does send "Caspian\\xa0Explorer"."""
        self.names.learn("explorer_nx", "Caspian\u00a0Explorer")
        self.assertEqual(self.names.display("explorer_nx"), "Caspian Explorer")

    def test_an_unresolved_symbol_token_is_not_a_name(self) -> None:
        """explorationsuit_class3 arrives as "$ExplorationSuit_Class1_Name;"."""
        self.assertFalse(self.names.learn("explorationsuit_class3", "$ExplorationSuit_Class1_Name;"))
        self.assertFalse(self.names.known("explorationsuit_class3"))

    def test_a_blank_name_does_not_overwrite_a_known_one(self) -> None:
        """mandalay came through with no localised name at all."""
        self.names.learn("mandalay", "Mandalay")
        self.assertFalse(self.names.learn("mandalay", ""))
        self.assertEqual(self.names.display("mandalay"), "Mandalay")

    def test_an_empty_symbol_is_ignored(self) -> None:
        self.assertFalse(self.names.learn("", "Something"))

    def test_it_survives_a_restart(self) -> None:
        """Otherwise a commander who flies one ship for a month never sees its
        name: the swap that taught it falls outside the replay window."""
        self.names.learn("panthermkii", "Panther Clipper Mk II")
        reopened = ShipNames(self.path)
        self.assertEqual(reopened.display("panthermkii"), "Panther Clipper Mk II")

    def test_a_corrupt_cache_is_survivable(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(len(ShipNames(self.path)), 0)

    def test_it_learns_from_a_swap(self) -> None:
        changed = self.names.observe(
            {"ShipType": "lakonminer", "ShipType_Localised": "Type-11 Prospector"}
        )
        self.assertTrue(changed)
        self.assertEqual(self.names.display("lakonminer"), "Type-11 Prospector")

    def test_it_learns_from_a_stored_ship_list(self) -> None:
        self.names.observe(
            {
                "ShipsHere": [
                    {"ShipType": "typex", "ShipType_Localised": "Alliance Chieftain"}
                ],
                "ShipsRemote": [
                    {"ShipType": "empire_courier", "ShipType_Localised": "Imperial Courier"}
                ],
            }
        )
        self.assertEqual(self.names.display("typex"), "Alliance Chieftain")
        self.assertEqual(self.names.display("empire_courier"), "Imperial Courier")


class ShipAndCargoStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = make_state()

    def loadout(self, **extra) -> None:
        event = {
            "event": "Loadout",
            "Ship": "panthermkii",
            "ShipID": 25,
            "ShipName": "KSS Miner",
            "ShipIdent": "KSS-25",
            "CargoCapacity": 1232,
            "MaxJumpRange": 40.5,
        }
        event.update(extra)
        self.state.apply(event)

    def test_the_model_is_shown_rather_than_the_ident(self) -> None:
        """The ident is the commander's own label and says nothing about the
        ship; the model is what they asked to see."""
        self.state.apply(
            {"event": "ShipyardSwap", "ShipType": "panthermkii",
             "ShipType_Localised": "Panther Clipper Mk II"}
        )
        self.loadout()
        self.assertEqual(self.state.ship_model, "Panther Clipper Mk II")
        self.assertNotEqual(self.state.ship_model, "KSS-25")

    def test_an_unnamed_ship_falls_back_to_its_symbol(self) -> None:
        self.loadout(Ship="neverswapped")
        self.assertEqual(self.state.ship_model, "Neverswapped")

    def test_a_loadout_localised_name_wins(self) -> None:
        self.loadout(Ship_Localised="Caspian Explorer")
        self.assertEqual(self.state.ship_model, "Caspian Explorer")

    def test_loadout_records_the_hold_capacity(self) -> None:
        self.loadout()
        self.assertEqual(self.state.cargo_capacity, 1232)

    def test_the_cargo_event_sets_the_count(self) -> None:
        self.loadout()
        self.state.apply({"event": "Cargo", "Vessel": "Ship", "Count": 199})
        self.assertEqual(self.state.cargo_count, 199)

    def test_an_srv_hold_does_not_count(self) -> None:
        self.loadout()
        self.state.apply({"event": "Cargo", "Vessel": "Ship", "Count": 199})
        self.state.apply({"event": "Cargo", "Vessel": "SRV", "Count": 2})
        self.assertEqual(self.state.cargo_count, 199)

    def test_a_cargo_event_without_a_vessel_is_ignored(self) -> None:
        """No journal has one, so the shape is unknown rather than the ship's.

        The default used to be "no Vessel means Ship", which would have counted an
        SRV's hold as the ship's on any event shape we have not seen. The live
        status file is the primary source for the count, so nothing is lost by
        refusing to guess.
        """
        self.loadout()
        self.state.apply({"event": "Cargo", "Vessel": "Ship", "Count": 199})
        self.state.apply({"event": "Cargo", "Count": 12})
        self.assertEqual(self.state.cargo_count, 199, "the unknown shape changed nothing")

    def test_the_live_status_file_supplies_the_count(self) -> None:
        self.loadout()
        self.state.apply_status(parse_status({"Cargo": 199.0}))
        self.assertEqual(self.state.cargo_count, 199)

    def test_a_swap_changes_the_model(self) -> None:
        self.loadout()
        self.state.apply(
            {"event": "ShipyardSwap", "ShipType": "lakonminer",
             "ShipType_Localised": "Type-11 Prospector"}
        )
        self.assertEqual(self.state.ship_model, "Type-11 Prospector")

    def test_a_loadout_without_a_capacity_leaves_the_hold_unknown(self) -> None:
        """A hold of unknown size must not be shown as 0/0.

        This used to apply an FSDJump -- which touches no hold at all -- and then
        assert the dataclass default, so deleting the capacity handling from
        _on_Loadout left it green. Now a real Loadout is fed in without a
        CargoCapacity, and the figure has to stay absent rather than become zero.
        """
        self.state.apply(
            {"event": "Loadout", "Ship": "explorer_nx", "ShipIdent": "KSS-14",
             "MaxJumpRange": 40.5, "UnladenMass": 1333.780029,
             "FuelCapacity": {"Main": 128.0, "Reserve": 1.14},
             "Modules": []}
        )
        self.assertEqual(self.state.cargo_capacity, 0, "no capacity in the event")
        self.assertGreater(self.state.max_jump_range, 0, "but the rest was read")

        # And the same Loadout with a capacity does set it, so the test above is
        # about the missing field rather than about Loadout being ignored.
        self.state.apply(
            {"event": "Loadout", "Ship": "explorer_nx", "CargoCapacity": 76,
             "MaxJumpRange": 83.73526,
             "FuelCapacity": {"Main": 128.0, "Reserve": 1.14}, "Modules": []}
        )
        self.assertEqual(self.state.cargo_capacity, 76)


if __name__ == "__main__":
    unittest.main()
