"""Tests for the jump range calculation.

The fixtures are four real ``Loadout`` events from a commander's journals, with
the ``MaxJumpRange`` the game itself wrote for each. That makes this a genuine
check rather than a restatement of the formula: the calculation starts from the
drive's own constants and engineering, and has to land on the game's number.
"""

from __future__ import annotations

import unittest

from elite_hud.jump_range import (
    DriveSpec,
    booster_bonus,
    build_spec,
    current_range,
    max_range,
    modifier_value,
    parse_booster,
    parse_drive,
)


def loadout(ship: str, item: str, unladen: float, game_range: float, *,
            modifiers: list[dict] | None = None, booster: str = "") -> dict:
    modules = [{"Slot": "FrameShiftDrive", "Item": item}]
    if modifiers:
        modules[0]["Engineering"] = {"BlueprintName": "FSD_LongRange", "Modifiers": modifiers}
    if booster:
        modules.append({"Slot": "FuelTank", "Item": booster})
    return {
        "event": "Loadout",
        "Ship": ship,
        "UnladenMass": unladen,
        "MaxJumpRange": game_range,
        "CargoCapacity": 0,
        "FuelCapacity": {"Main": 32.0, "Reserve": 0.5},
        "Modules": modules,
    }


#: Each of these reproduces the number the game wrote, to within 1e-5 ly.
REAL_LOADOUTS = (
    loadout(
        "explorer_nx",
        "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii",
        1333.78,
        83.735268,
        modifiers=[{"Label": "FSDOptimalMass", "Value": 7528.039551, "OriginalValue": 4670.0}],
        booster="int_guardianfsdbooster_size5",
    ),
    loadout(
        "lakonminer",
        "int_hyperdrive_overcharge_size5_class5",
        614.80,
        30.660276,
        modifiers=[
            {"Label": "FSDOptimalMass", "Value": 1586.25, "OriginalValue": 1175.0},
            {"Label": "MaxFuelPerJump", "Value": 5.72, "OriginalValue": 5.2},
        ],
    ),
    loadout(
        "panthermkii",
        "int_hyperdrive_overcharge_size7_class5",
        1603.80,
        40.554554,
        modifiers=[{"Label": "FSDOptimalMass", "Value": 5304.0, "OriginalValue": 3000.0}],
    ),
    loadout(
        "mandalay",
        "int_hyperdrive_overcharge_size5_class5",
        325.00,
        72.879395,
        modifiers=[{"Label": "FSDOptimalMass", "Value": 1821.25, "OriginalValue": 1175.0}],
        booster="int_guardianfsdbooster_size4",
    ),
)


class DriveParsingTests(unittest.TestCase):
    def test_class_five_is_the_top_rating(self) -> None:
        """The journal counts classes up while the letters run down."""
        spec = parse_drive("int_hyperdrive_size5_class5")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual((spec.size, spec.rating), (5, "A"))

    def test_engineered_values_win_over_the_table(self) -> None:
        spec = parse_drive(
            "int_hyperdrive_overcharge_size5_class5",
            {"Modifiers": [
                {"Label": "FSDOptimalMass", "Value": 1586.25},
                {"Label": "MaxFuelPerJump", "Value": 5.72},
            ]},
        )
        assert spec is not None
        self.assertEqual(spec.optimal_mass, 1586.25)
        self.assertEqual(spec.max_fuel_per_jump, 5.72)

    def test_sco_drives_have_their_own_constants(self) -> None:
        plain = parse_drive("int_hyperdrive_size5_class5")
        sco = parse_drive("int_hyperdrive_overcharge_size5_class5")
        mkii = parse_drive("int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii")
        assert plain is not None and sco is not None and mkii is not None
        self.assertFalse(plain.is_sco)
        self.assertTrue(sco.is_sco)
        self.assertTrue(mkii.is_mkii)
        self.assertEqual(mkii.power_constant, 2.5025)
        self.assertEqual(mkii.linear_constant, 11.0)

    def test_a_non_drive_is_rejected(self) -> None:
        self.assertIsNone(parse_drive("int_engine_size5_class5"))
        self.assertIsNone(parse_drive(None))

    def test_booster_sizes_map_to_their_bonus(self) -> None:
        self.assertEqual(parse_booster("int_guardianfsdbooster_size5"), 10.50)
        self.assertEqual(parse_booster("int_guardianfsdbooster_size1"), 4.00)
        self.assertEqual(parse_booster("int_engine_size5_class5"), 0.0)
        self.assertEqual(booster_bonus(99), 0.0)

    def test_modifier_lookup_survives_junk(self) -> None:
        self.assertIsNone(modifier_value(None, "FSDOptimalMass"))
        self.assertIsNone(modifier_value({"Modifiers": "nonsense"}, "FSDOptimalMass"))
        self.assertIsNone(modifier_value({"Modifiers": [{"Label": "Other"}]}, "FSDOptimalMass"))


class RealShipTests(unittest.TestCase):
    def test_the_formula_reproduces_what_the_game_wrote(self) -> None:
        for fixture in REAL_LOADOUTS:
            with self.subTest(ship=fixture["Ship"]):
                spec, booster = build_spec(fixture)
                self.assertIsNotNone(spec)
                computed = max_range(spec, fixture["UnladenMass"], booster)  # type: ignore[arg-type]
                self.assertAlmostEqual(
                    computed,
                    fixture["MaxJumpRange"],
                    delta=1e-5,
                    msg=f"{fixture['Ship']}: computed {computed} vs game {fixture['MaxJumpRange']}",
                )


class CurrentRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = DriveSpec(
            size=5, rating="A", power_constant=2.45, linear_constant=13.0,
            max_fuel_per_jump=5.2, optimal_mass=1821.25,
        )

    def _range(self, fuel: float, cargo: float, unladen: float = 325.0) -> float:
        return current_range(
            unladen_mass=unladen, fuel=fuel, cargo=cargo, spec=self.spec, booster=9.25
        )

    def test_the_maximum_is_one_jump_of_fuel_not_a_full_tank(self) -> None:
        """The game defines MaxJumpRange with "just enough fuel for 1 jump".

        Carrying a full 48 t tank makes the ship heavier than carrying the 5.2 t
        a single jump burns, so the range with a full tank is lower.
        """
        self.assertAlmostEqual(
            self._range(self.spec.max_fuel_per_jump, 0.0),
            max_range(self.spec, 325.0, 9.25),
            places=6,
        )
        self.assertLess(self._range(48.0, 0.0), self._range(self.spec.max_fuel_per_jump, 0.0))

    def test_cargo_shortens_the_jump(self) -> None:
        self.assertLess(self._range(48.0, 64.0), self._range(48.0, 0.0))

    def test_burning_fuel_below_one_jump_shortens_it(self) -> None:
        """Above one jump's worth the fuel is dead weight and is burnt off."""
        full = self._range(48.0, 0.0)
        near_empty = self._range(5.2, 0.0)
        self.assertGreater(near_empty, full, "a lighter ship jumps further")

        below = self._range(2.6, 0.0)
        self.assertLess(below, near_empty, "less fuel than a jump needs cannot go as far")

    def test_an_empty_tank_has_no_range(self) -> None:
        self.assertEqual(self._range(0.0, 0.0), 0.0)

    def test_unknown_drive_falls_back_to_scaling_the_maximum(self) -> None:
        """Better a slightly stale number than a crash or a wild guess."""
        scaled = current_range(
            unladen_mass=325.0, fuel=24.0, cargo=0.0, spec=None, max_jump_range=72.9
        )
        self.assertGreater(scaled, 0.0)
        self.assertLess(scaled, 72.9 * 2)

    def test_no_mass_returns_the_given_maximum(self) -> None:
        self.assertEqual(
            current_range(unladen_mass=0.0, fuel=10.0, cargo=0.0, spec=self.spec,
                          max_jump_range=50.0),
            50.0,
        )


if __name__ == "__main__":
    unittest.main()
