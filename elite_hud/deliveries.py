"""Cargo missions: how much is still to be picked up and handed in.

A commander running deliveries has up to twenty missions open at once, each for
its own commodity and its own station. The journal says how each one is doing, but
only in pieces, and the number that matters -- how much cargo is still owed -- is
not in any single event.

Two events carry it, and between them they cover the whole life of a mission:

* ``MissionAccepted`` states the commodity and the total to deliver, so a mission
  counts from the moment it is taken, before any cargo has moved.
* ``CargoDepot`` states the running totals. Its fields are *state*, not deltas:
  after handing the cargo over, ``ItemsCollected`` is 0 again, so "in the hold"
  and "still owed" are different numbers and both are read rather than derived
  from each other.

``Mission_Mining`` counts too, and that is not a guess: 22 mining missions in
these journals produce ``CargoDepot`` events, because mining a commodity and
delivering it is the same job as far as the bar is concerned. Missions without a
commodity -- donations, passengers -- never enter the book, so nothing has to be
decided from a mission's name.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

#: Events that end a mission, whatever the outcome.
CLOSING_EVENTS = ("MissionCompleted", "MissionAbandoned", "MissionFailed")


@dataclass(slots=True)
class CargoMission:
    """One mission's cargo, as far as the journal has said."""

    mission_id: int
    commodity: str = ""
    #: Total the mission asks for.
    total: int = 0
    #: In the hold right now, per the game's own figure.
    collected: int = 0
    #: Handed over so far.
    delivered: int = 0

    @property
    def outstanding(self) -> int:
        """Still owed to the destination: the total, less what was delivered."""
        return max(0, self.total - self.delivered)

    @property
    def to_collect(self) -> int:
        """Still to be picked up: neither delivered nor in the hold."""
        return max(0, self.total - self.delivered - self.collected)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


@dataclass(slots=True)
class DeliveryBook:
    """Every open mission that involves carrying a commodity somewhere."""

    missions: dict[int, CargoMission] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.missions)

    def observe(self, event: dict) -> bool:
        """Fold in a mission event. Returns True when something changed."""
        name = str(event.get("event") or "")
        mission_id = _as_int(event.get("MissionID"))
        if mission_id is None:
            return False

        if name in CLOSING_EVENTS:
            return self.missions.pop(mission_id, None) is not None
        if name == "MissionAccepted":
            return self._accepted(mission_id, event)
        if name == "CargoDepot":
            return self._depot(mission_id, event)
        return False

    def _accepted(self, mission_id: int, event: dict) -> bool:
        """A mission enters the book only if it names a commodity and an amount.

        That is what makes this work without reading mission names: a donation has
        no commodity, so it is not cargo, and the same rule covers delivery,
        collect and mining missions alike.
        """
        commodity = str(event.get("Commodity_Localised") or "").strip()
        if not commodity:
            commodity = str(event.get("Commodity") or "").strip()
        total = _as_int(event.get("Count"))
        if not commodity or not total or total <= 0:
            return False
        self.missions[mission_id] = CargoMission(
            mission_id=mission_id, commodity=commodity, total=total
        )
        return True

    def _depot(self, mission_id: int, event: dict) -> bool:
        """The running totals, which only exist for missions we already know.

        A ``CargoDepot`` for an unknown mission is not invented into one: it can
        arrive for a mission taken before the replayed history began, and a row
        with a total and no commodity would be a guess.
        """
        mission = self.missions.get(mission_id)
        if mission is None:
            return False
        total = _as_int(event.get("TotalItemsToDeliver"))
        collected = _as_int(event.get("ItemsCollected"))
        delivered = _as_int(event.get("ItemsDelivered"))
        before = (mission.total, mission.collected, mission.delivered)
        if total is not None:
            mission.total = total
        if collected is not None:
            mission.collected = collected
        if delivered is not None:
            mission.delivered = delivered
        return (mission.total, mission.collected, mission.delivered) != before

    def totals(self) -> tuple[int, int]:
        """``(to collect, outstanding)`` across every open cargo mission.

        Both are sums of what the game stated, never of one derived from the
        other: a mission can be part-collected, part-delivered, and the two
        questions have different answers.
        """
        return (
            sum(mission.to_collect for mission in self.missions.values()),
            sum(mission.outstanding for mission in self.missions.values()),
        )

    def carrying(self) -> int:
        """Tonnes in the hold for these missions, as the game reports it."""
        return sum(mission.collected for mission in self.missions.values())
