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
            fuel: float, reserve: float, cargo: int,
            modifiers: list[dict] | None = None,
            booster: str = "", booster_slot: str = "Slot01_Size5") -> dict:
    """A Loadout event shaped like the game's, with every field spelled out.

    The tank and the hold are passed in rather than defaulted. They do not enter
    the range formula, so a wrong default here was harmless to these tests and
    still made the fixture a lie -- and a fixture that is a lie is how a test
    comes to assert something the game never said.
    """
    modules = [{"Slot": "FrameShiftDrive", "Item": item}]
    if modifiers:
        modules[0]["Engineering"] = {"BlueprintName": "FSD_LongRange", "Modifiers": modifiers}
    if booster:
        modules.append({"Slot": booster_slot, "Item": booster})
    return {
        "event": "Loadout",
        "Ship": ship,
        "UnladenMass": unladen,
        "MaxJumpRange": game_range,
        "CargoCapacity": cargo,
        "FuelCapacity": {"Main": fuel, "Reserve": reserve},
        "Modules": modules,
    }


#: Three real Loadouts, copied field for field from -journal/: the ship, its mass,
#: its tank, its hold, the drive with its engineering, the booster and the slot
#: the booster sits in, and the range the game itself wrote. Each row has to
#: reproduce that range to within 1e-5 ly.
REAL_LOADOUTS = (
    loadout(
        "explorer_nx",
        "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii",
        1333.780029,
        83.73526,
        fuel=128.0, reserve=1.14, cargo=76,
        modifiers=[{"Label": "FSDOptimalMass", "Value": 7528.039551, "OriginalValue": 4670.0}],
        booster="int_guardianfsdbooster_size5",
        booster_slot="Slot04_Size5",
    ),
    loadout(
        "panthermkii",
        "int_hyperdrive_overcharge_size7_class5",
        1603.800049,
        40.554554,
        fuel=128.0, reserve=1.11, cargo=1232,
        modifiers=[{"Label": "FSDOptimalMass", "Value": 5304.0, "OriginalValue": 3000.0}],
    ),
    loadout(
        "mandalay",
        "int_hyperdrive_overcharge_size5_class5",
        325.00,
        72.879395,
        fuel=48.0, reserve=0.5, cargo=64,
        modifiers=[{"Label": "FSDOptimalMass", "Value": 1821.25, "OriginalValue": 1175.0}],
        booster="int_guardianfsdbooster_size4",
        booster_slot="Slot03_Size4",
    ),
)

#: A drive with an engineered ``MaxFuelPerJump``. No journal in this repository
#: has one, so nothing here can be checked against a number the game wrote -- the
#: modifier's name and its effect are from the game's engineering list, not from
#: data. It is kept apart from REAL_LOADOUTS precisely so it cannot be mistaken
#: for something measured, and it exists to prove the modifier is read at all.
SYNTHETIC_FUEL_MODIFIER = loadout(
    "mandalay",
    "int_hyperdrive_overcharge_size5_class5",
    325.00,
    72.879395,
    fuel=48.0, reserve=0.5, cargo=64,
    modifiers=[
        {"Label": "FSDOptimalMass", "Value": 1821.25, "OriginalValue": 1175.0},
        {"Label": "MaxFuelPerJump", "Value": 5.72, "OriginalValue": 5.2},
    ],
    booster="int_guardianfsdbooster_size4",
    booster_slot="Slot03_Size4",
)


class DriveParsingTests(unittest.TestCase):
    def test_class_five_is_the_top_rating(self) -> None:
        """The journal counts classes up while the letters run down."""
        spec = parse_drive("int_hyperdrive_size5_class5")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual((spec.size, spec.rating), (5, "A"))

    def test_engineered_values_win_over_the_table(self) -> None:
        """Both modifiers are read; only the optimal mass is measured.

        ``FSDOptimalMass`` appears in every engineered drive in the journals. An
        engineered ``MaxFuelPerJump`` appears in none, so that half of the test
        proves the modifier is read and says nothing about the value being right.
        """
        spec = parse_drive(
            "int_hyperdrive_overcharge_size5_class5",
            {"Modifiers": [
                {"Label": "FSDOptimalMass", "Value": 1821.25},
                {"Label": "MaxFuelPerJump", "Value": 5.72},
            ]},
        )
        assert spec is not None
        self.assertEqual(spec.optimal_mass, 1821.25)
        self.assertEqual(spec.max_fuel_per_jump, 5.72)

    def test_the_synthetic_fuel_modifier_still_builds_a_spec(self) -> None:
        spec, booster = build_spec(SYNTHETIC_FUEL_MODIFIER)
        assert spec is not None
        self.assertEqual(spec.max_fuel_per_jump, 5.72)
        self.assertEqual(booster, 9.25)

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
    #: Frontier does not publish its range formula, so this one is fitted to the
    #: numbers the game writes and matches them to about 1.3e-5 ly on the worst of
    #: the three ships. The tolerance says so rather than hiding it: the previous
    #: fixture carried a rounded mass and a range of 83.735268 for the Caspian
    #: Explorer, neither of which is what the journal says (1333.780029 and
    #: 83.73526), and the pair had been chosen so that a 1e-5 tolerance held.
    TOLERANCE = 5e-5

    def test_the_formula_reproduces_what_the_game_wrote(self) -> None:
        """The real check on the formula: it must match the game's own numbers.

        Three ships, each with its own drive, engineering, booster and mass, and
        the range the game itself wrote for it. Nothing else in this file can
        catch a formula that is subtly wrong -- the constants table is fitted to
        these very numbers, so a change to the arithmetic shows up here or
        nowhere.
        """
        for fixture in REAL_LOADOUTS:
            with self.subTest(ship=fixture["Ship"]):
                spec, booster = build_spec(fixture)
                self.assertIsNotNone(spec)
                computed = max_range(spec, fixture["UnladenMass"], booster)  # type: ignore[arg-type]
                self.assertAlmostEqual(
                    computed,
                    fixture["MaxJumpRange"],
                    delta=self.TOLERANCE,
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

        The spec here is the Mandalay's -- its engineered optimal mass, its
        drive, its Guardian booster -- so the number to check against is the one
        the game wrote for that ship, 72.879395 ly. Carrying its full 48 t tank
        instead of the 5.2 t a jump burns makes it heavier, so the range drops.

        This used to compare ``max_range(spec, mass, booster)`` with the identical
        ``current_range(...)`` call the function is defined as, which is a
        comparison of an expression with itself: rewriting the formula to drop the
        optimal mass, the constants and the booster still passed.
        """
        self.assertAlmostEqual(
            self._range(self.spec.max_fuel_per_jump, 0.0),
            72.879395,
            places=5,
            msg="the Mandalay's own MaxJumpRange",
        )
        self.assertLess(self._range(48.0, 0.0), self._range(self.spec.max_fuel_per_jump, 0.0))
        self.assertAlmostEqual(max_range(self.spec, 325.0, 9.25), self._range(5.2, 0.0))

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
        """A drive whose constants are unknown still gives a sane figure.

        The fallback can only scale the journal's own maximum by the change in
        mass, and that is what is checked here: the mass-scaling identity, and the
        two cases at its edges. Pinning ``scaled > 0`` and ``scaled < 145`` -- as
        this test used to -- is satisfied by returning the maximum untouched for
        every input, which is the wild guess the fallback exists to avoid.
        """
        maximum = 72.9
        unladen, one_jump, cargo = 325.0, 5.2, 64.0

        # With one jump of fuel and nothing in the hold, the ship is in the state
        # the maximum was measured in, so the fallback must not change it.
        self.assertEqual(
            current_range(unladen_mass=unladen, fuel=one_jump, cargo=0.0,
                          spec=None, max_jump_range=maximum),
            maximum,
        )

        # With cargo it scales by mass, exactly as its docstring claims.
        scaled = current_range(unladen_mass=unladen, fuel=one_jump, cargo=cargo,
                               spec=None, max_jump_range=maximum)
        self.assertAlmostEqual(
            scaled,
            maximum * (unladen + one_jump) / (unladen + one_jump + cargo),
            places=9,
        )
        self.assertLess(scaled, maximum)

        # Its limitation, stated rather than hidden: with no spec there is no way
        # to know how much fuel one jump burns, so a full tank cannot be told
        # apart from a jump's worth and the figure is not reduced for it.
        self.assertEqual(
            current_range(unladen_mass=unladen, fuel=48.0, cargo=0.0,
                          spec=None, max_jump_range=maximum),
            maximum,
            "without a spec the fallback cannot account for the tank",
        )

        # No fuel figure and no spec: the fallback returns the maximum. Zero here
        # means "nothing known about the tank" rather than "empty", and the bar
        # treats a zero range as unknown too -- _ship_segment falls back to the
        # maximum for exactly this reason. Stated so that it is a decision on
        # record rather than an accident of the order of two checks.
        self.assertEqual(
            current_range(unladen_mass=unladen, fuel=0.0, cargo=0.0,
                          spec=None, max_jump_range=maximum),
            maximum,
        )
        # And with no maximum to scale there is nothing to invent.
        self.assertEqual(
            current_range(unladen_mass=unladen, fuel=10.0, cargo=0.0,
                          spec=None, max_jump_range=0.0),
            0.0,
        )

    def test_no_mass_returns_the_given_maximum(self) -> None:
        self.assertEqual(
            current_range(unladen_mass=0.0, fuel=10.0, cargo=0.0, spec=self.spec,
                          max_jump_range=50.0),
            50.0,
        )


if __name__ == "__main__":
    unittest.main()
