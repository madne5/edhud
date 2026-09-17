"""Current jump range, computed from what the journal gives us.

The journal reports ``Loadout.MaxJumpRange``, which the Player Journal Manual
v38 defines as "based on zero cargo, and just enough fuel for 1 jump". It never
reports the range with the ship as it is actually loaded, so that has to be
derived.

The game's formula, as used by EDDI and EDSY and verified here against the
``MaxJumpRange`` the game itself writes for four different ships (agreement to
1e-6 ly):

    range = optimalMass / mass * (fuel * 1000 / linearConstant) ** (1 / powerConstant)

with ``mass = unladen + fuel + cargo`` and ``fuel`` capped at one jump's worth.
``linearConstant`` and ``powerConstant`` are not in the journal -- they are
properties of the drive, so they come from the tables below.

Because ``MaxJumpRange`` already folds in optimalMass, linearConstant, the
engineering and the booster, the same answer is reached by scaling it:

    base   = MaxJumpRange - booster
    fuel_t = min(fuel, maxFuelPerJump)
    range  = base * (unladen + maxFuelPerJump) / (unladen + fuel + cargo)
             * (fuel_t / maxFuelPerJump) ** (1 / powerConstant) + booster

which needs only the power constant and the booster bonus. When the tank holds
more than one jump's worth -- the usual case -- the power term is exactly 1 and
only the masses matter.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: Power constant by drive size, and the linear constant by rating. Neither is
#: in the journal; these are the values EDDI carries in DataDefinitions/Module.cs.
FSD_POWER_CONSTANT = {2: 2.00, 3: 2.15, 4: 2.30, 5: 2.45, 6: 2.60, 7: 2.75, 8: 2.90}
#: Supercruise-overcharge drives are not on the same curve. The MkII size 8 was
#: measured from a real loadout; the rest follow their size.
SCO_POWER_CONSTANT = {2: 2.15, 3: 2.30, 4: 2.45, 5: 2.45, 6: 2.60, 7: 2.75, 8: 2.5025}

FSD_LINEAR_CONSTANT = {"E": 11.0, "D": 10.0, "C": 8.0, "B": 10.0, "A": 12.0}
SCO_LINEAR_CONSTANT = {"E": 8.0, "D": 12.0, "C": 12.0, "B": 12.0, "A": 13.0}
#: The MkII size 8 again.
MkII_LINEAR_CONSTANT = 11.0

#: One jump's worth of fuel, by size and rating: how much the drive can burn at
#: once. Engineered values arrive in the journal as a MaxFuelPerJump modifier
#: and take precedence over this table.
FSD_MAX_FUEL = {
    (2, "E"): 0.40, (3, "E"): 0.80, (4, "E"): 1.30, (5, "E"): 2.00, (6, "E"): 3.30,
    (7, "E"): 5.30, (8, "E"): 8.40,
    (2, "D"): 0.50, (3, "D"): 1.00, (4, "D"): 1.70, (5, "D"): 2.60, (6, "D"): 4.30,
    (7, "D"): 6.90, (8, "D"): 10.90,
    (2, "C"): 0.60, (3, "C"): 1.20, (4, "C"): 2.00, (5, "C"): 3.10, (6, "C"): 5.10,
    (7, "C"): 8.10, (8, "C"): 12.80,
    (2, "B"): 0.80, (3, "B"): 1.60, (4, "B"): 2.60, (5, "B"): 4.10, (6, "B"): 6.70,
    (7, "B"): 10.60, (8, "B"): 16.60,
    (2, "A"): 0.60, (3, "A"): 1.20, (4, "A"): 2.00, (5, "A"): 3.00, (6, "A"): 5.00,
    (7, "A"): 8.00, (8, "A"): 12.80,
}
SCO_MAX_FUEL = {
    (2, "A"): 0.70, (3, "A"): 1.30, (4, "A"): 2.10, (5, "A"): 5.20, (6, "A"): 8.20,
    (7, "A"): 13.10, (8, "A"): 6.80,
    (5, "D"): 2.60, (6, "D"): 4.30, (7, "D"): 6.90, (8, "D"): 10.90,
    (5, "E"): 2.00, (6, "E"): 3.30, (7, "E"): 5.30, (8, "E"): 8.40,
}

#: Base optimal mass by size and rating, in tonnes. Only a fallback: an
#: engineered drive reports FSDOptimalMass with its base in OriginalValue.
FSD_OPTIMAL_MASS = {
    (2, "A"): 90.0, (3, "A"): 150.0, (4, "A"): 525.0, (5, "A"): 1050.0,
    (6, "A"): 1800.0, (7, "A"): 2700.0, (8, "A"): 4670.0,
}
SCO_OPTIMAL_MASS = {
    (2, "A"): 105.0, (3, "A"): 175.0, (4, "A"): 600.0, (5, "A"): 1175.0,
    (6, "A"): 2000.0, (7, "A"): 3000.0, (8, "A"): 4670.0,
}

#: Guardian FSD booster: a flat addition to the range, by module size.
GUARDIAN_BOOSTER_BONUS = {1: 4.00, 2: 6.00, 3: 7.75, 4: 9.25, 5: 10.50}

_SIZE_RE = re.compile(r"_size(\d)")
_CLASS_RE = re.compile(r"_class(\d)")
#: The journal names the top rating "class 5"; the letters run the other way.
CLASS_TO_RATING = {1: "E", 2: "D", 3: "C", 4: "B", 5: "A"}


@dataclass(frozen=True, slots=True)
class DriveSpec:
    """What we can work out about the installed frame shift drive."""

    size: int = 0
    rating: str = ""
    power_constant: float = 0.0
    linear_constant: float = 0.0
    max_fuel_per_jump: float = 0.0
    optimal_mass: float = 0.0
    is_sco: bool = False
    is_mkii: bool = False


def parse_drive(item: str | None, engineering: dict | None = None) -> DriveSpec | None:
    """Read a frame shift drive module's symbol and its engineering."""
    if not item or "hyperdrive" not in item.lower():
        return None

    size_match = _SIZE_RE.search(item)
    class_match = _CLASS_RE.search(item)
    size = int(size_match.group(1)) if size_match else 0
    rating = CLASS_TO_RATING.get(int(class_match.group(1)), "") if class_match else ""

    is_sco = "overcharge" in item.lower()
    is_mkii = "mkii" in item.lower()

    power_table = SCO_POWER_CONSTANT if is_sco else FSD_POWER_CONSTANT
    power = power_table.get(size, FSD_POWER_CONSTANT.get(size, 0.0))
    linear = (
        MkII_LINEAR_CONSTANT
        if is_mkii
        else (SCO_LINEAR_CONSTANT if is_sco else FSD_LINEAR_CONSTANT).get(rating, 0.0)
    )

    fuel_table = SCO_MAX_FUEL if is_sco else FSD_MAX_FUEL
    fuel = fuel_table.get((size, rating), FSD_MAX_FUEL.get((size, rating), 0.0))
    engineered_fuel = modifier_value(engineering, "MaxFuelPerJump")
    if engineered_fuel:
        fuel = engineered_fuel

    mass_table = SCO_OPTIMAL_MASS if is_sco else FSD_OPTIMAL_MASS
    optimal = mass_table.get((size, rating), FSD_OPTIMAL_MASS.get((size, rating), 0.0))
    engineered_mass = modifier_value(engineering, "FSDOptimalMass")
    if engineered_mass:
        optimal = engineered_mass

    return DriveSpec(
        size=size,
        rating=rating,
        power_constant=power,
        linear_constant=linear,
        max_fuel_per_jump=fuel,
        optimal_mass=optimal,
        is_sco=is_sco,
        is_mkii=is_mkii,
    )


def booster_bonus(size: int) -> float:
    return GUARDIAN_BOOSTER_BONUS.get(size, 0.0)


def parse_booster(item: str | None) -> float:
    """Guardian FSD booster contribution, or 0 if none is fitted."""
    if not item or "guardianfsdbooster" not in item.replace("_", "").lower():
        return 0.0
    match = _SIZE_RE.search(item)
    return booster_bonus(int(match.group(1))) if match else 0.0


def modifier_value(engineering: dict | None, label: str) -> float | None:
    """Pull one engineering modifier out of a module's Engineering block."""
    if not isinstance(engineering, dict):
        return None
    for modifier in engineering.get("Modifiers") or []:
        if not isinstance(modifier, dict) or modifier.get("Label") != label:
            continue
        value = modifier.get("Value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def max_range(spec: DriveSpec, unladen_mass: float, booster: float = 0.0) -> float:
    """The ship's maximum range: no cargo, one jump's worth of fuel."""
    return current_range(
        unladen_mass=unladen_mass,
        fuel=spec.max_fuel_per_jump,
        cargo=0.0,
        spec=spec,
        booster=booster,
    )


def current_range(
    *,
    unladen_mass: float,
    fuel: float,
    cargo: float,
    spec: DriveSpec | None,
    booster: float = 0.0,
    max_jump_range: float = 0.0,
) -> float:
    """The range the ship has right now, given its fuel and cargo.

        range = optimalMass / mass * (fuel * 1000 / linearConstant) ** (1 / powerConstant)

    with ``mass = unladen + fuel + cargo`` and ``fuel`` capped at one jump's
    worth. When the drive's constants are unknown the journal's own
    ``MaxJumpRange`` is scaled by mass instead, which is exact whenever the tank
    holds more than a single jump.
    """
    if unladen_mass <= 0:
        return max_jump_range

    if spec is None or spec.optimal_mass <= 0 or spec.linear_constant <= 0 or spec.power_constant <= 0:
        return _scaled_range(unladen_mass, fuel, cargo, spec, booster, max_jump_range)

    max_fuel = spec.max_fuel_per_jump or fuel
    fuel_used = min(max(fuel, 0.0), max_fuel) if max_fuel > 0 else 0.0
    if fuel_used <= 0:
        return 0.0
    mass = unladen_mass + max(fuel, 0.0) + max(cargo, 0.0)

    try:
        result = (
            spec.optimal_mass / mass
            * (fuel_used * 1000.0 / spec.linear_constant) ** (1.0 / spec.power_constant)
            + booster
        )
    except (OverflowError, ZeroDivisionError):  # pragma: no cover - defensive
        log.debug("jump range fell over for %r", spec)
        return max_jump_range
    return max(0.0, result)


def _scaled_range(
    unladen_mass: float,
    fuel: float,
    cargo: float,
    spec: DriveSpec | None,
    booster: float,
    max_jump_range: float,
) -> float:
    """Fallback: scale the journal's maximum by the change in mass."""
    if max_jump_range <= 0:
        return 0.0
    max_fuel = (spec.max_fuel_per_jump if spec else 0.0) or max(fuel, 0.0)
    if max_fuel <= 0:
        return max_jump_range
    base = max(0.0, max_jump_range - booster)
    power = spec.power_constant if spec and spec.power_constant > 0 else 1.0
    fuel_used = min(max(fuel, 0.0), max_fuel)
    if fuel_used <= 0:
        return 0.0
    mass_now = unladen_mass + max(fuel, 0.0) + max(cargo, 0.0)
    mass_reference = unladen_mass + max_fuel
    try:
        return max(
            0.0,
            base * mass_reference / mass_now * ((fuel_used / max_fuel) ** (1.0 / power)) + booster,
        )
    except (OverflowError, ZeroDivisionError):  # pragma: no cover - defensive
        return max_jump_range


def build_spec(loadout: dict) -> tuple[DriveSpec | None, float]:
    """Drive spec and booster bonus from a ``Loadout`` event."""
    spec: DriveSpec | None = None
    booster = 0.0
    for module in loadout.get("Modules") or []:
        if not isinstance(module, dict):
            continue
        item = module.get("Item")
        if not isinstance(item, str):
            continue
        if "hyperdrive" in item.lower():
            spec = parse_drive(item, module.get("Engineering"))
        elif "guardianfsdbooster" in item.replace("_", "").lower():
            booster = parse_booster(item)
    return spec, booster
