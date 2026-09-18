"""What the open missions still need bought, and where to get it.

The rank grind this was written for works by taking twenty delivery missions at
once, which means twenty different commodities from twenty different systems.
The journal says what each mission wants -- ``MissionAccepted`` carries
``Commodity``, ``Count``, ``DestinationSystem`` and ``DestinationStation`` for
the collection and donation missions -- but never where to buy any of it, so the
two halves are kept apart: this module only knows the needs, and
:mod:`elite_hud.market` answers where to satisfy them.

Missions without a commodity are ignored rather than tracked with a blank entry.
Couriers and the like make up most of the traffic and have nothing to buy, and
listing them would bury the ones that matter.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .market import normalise_commodity


@dataclass(slots=True)
class Need:
    """One commodity, and how much of it the open missions want."""

    commodity: str
    localised: str = ""
    count: int = 0
    missions: int = 0
    #: Systems the missions want it delivered to, for context.
    destinations: tuple[str, ...] = ()

    @property
    def display(self) -> str:
        return self.localised or self.commodity

    def describe(self) -> str:
        text = f"{self.display}: {self.count}"
        if self.missions > 1:
            text += f" ({self.missions} missions)"
        return text


class ShoppingList:
    """The commodities wanted by the missions that are currently open.

    Held per mission rather than as a running total, because missions finish in
    whatever order they finish: a total could not be decremented correctly when
    a mission is abandoned, and would drift upwards for the rest of the session.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._missions: dict[int, Need] = {}
        #: Commodity (normalised) -> the name to display for it.
        self._names: dict[str, str] = {}

    def add(
        self,
        mission_id: int,
        commodity: str,
        localised: str = "",
        count: int = 1,
        destination: str = "",
    ) -> None:
        if not commodity:
            return
        with self._lock:
            key = normalise_commodity(commodity)
            if localised:
                self._names.setdefault(key, localised)
            previous = self._missions.get(mission_id)
            destinations = previous.destinations if previous else ()
            if destination and destination not in destinations:
                destinations = (*destinations, destination)
            self._missions[mission_id] = Need(
                commodity=commodity,
                localised=localised or self._names.get(key, ""),
                count=max(0, int(count)),
                missions=1,
                destinations=destinations,
            )

    def remove(self, mission_id: int) -> None:
        with self._lock:
            self._missions.pop(mission_id, None)

    def clear(self) -> None:
        with self._lock:
            self._missions.clear()

    @property
    def items(self) -> list[Need]:
        """One entry per commodity, heaviest first.

        Ties break on the name so the order does not shuffle between redraws,
        which would make the popup jump around while it is being read.
        """
        with self._lock:
            merged: dict[str, Need] = {}
            for need in self._missions.values():
                key = normalise_commodity(need.commodity)
                current = merged.get(key)
                if current is None:
                    merged[key] = Need(
                        commodity=need.commodity,
                        localised=need.localised,
                        count=need.count,
                        missions=1,
                        destinations=need.destinations,
                    )
                    continue
                destinations = current.destinations
                for system in need.destinations:
                    if system not in destinations:
                        destinations = (*destinations, system)
                merged[key] = Need(
                    commodity=current.commodity,
                    localised=current.localised or need.localised,
                    count=current.count + need.count,
                    missions=current.missions + 1,
                    destinations=destinations,
                )
            return sorted(merged.values(), key=lambda n: (-n.count, n.display.casefold()))

    @property
    def total_items(self) -> int:
        return sum(need.count for need in self.items)

    @property
    def empty(self) -> bool:
        with self._lock:
            return not self._missions

    def __len__(self) -> int:
        with self._lock:
            return len(self._missions)
