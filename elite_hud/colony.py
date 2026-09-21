"""Colonisation construction sites: how far along, and what is still needed.

``ColonisationConstructionDepot`` states the whole site: its progress, and for
every commodity how much is required, how much has been provided and what is
paid per unit. Two things about it were measured rather than assumed.

**It is refreshed on every delivery.** In these journals each
``ColonisationContribution`` is followed a second later by a depot event, and the
provided amounts rise by exactly what was contributed -- eight contributions, all
eight matching to the tonne. So the figures can be shown as the game states them,
with nothing derived and nothing needing to be patched up in between.

**Symbols are not case-consistent between events.** A contribution names
``$Aluminium_name;`` while the site's own list names ``$aluminium_name;``. Any
matching by symbol has to normalise, or the very commodity that was just
delivered looks untouched.

The site's *name* is not in this event at all -- only its MarketID. It is learned
from ``Docked`` and ``Location``, which carry the station name, and shown only
when it is known rather than as a number.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


def normalise(symbol: str) -> str:
    """Journal symbols differ in case between events; compare them folded."""
    return (symbol or "").strip().casefold()


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


@dataclass(slots=True)
class Resource:
    """One commodity the site wants."""

    symbol: str
    name: str = ""
    required: int = 0
    provided: int = 0
    #: Credits paid per unit, as the event states it.
    payment: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.required - self.provided)

    @property
    def label(self) -> str:
        return self.name or self.symbol


@dataclass(slots=True)
class ConstructionSite:
    """One site, as the last depot event described it."""

    market_id: int
    name: str = ""
    #: 0.0 - 1.0, as the game reports it.
    progress: float = 0.0
    complete: bool = False
    failed: bool = False
    resources: dict[str, Resource] = field(default_factory=dict)

    @property
    def remaining(self) -> int:
        """Tonnes still to be delivered, summed from the game's own figures."""
        return sum(resource.remaining for resource in self.resources.values())

    @property
    def outstanding(self) -> int:
        """How many commodities still have something owing."""
        return sum(1 for resource in self.resources.values() if resource.remaining > 0)

    @property
    def percent(self) -> float:
        return max(0.0, min(100.0, self.progress * 100.0))

    def most_needed(self) -> Resource | None:
        """The commodity with the most still to deliver, for a short line."""
        pending = [r for r in self.resources.values() if r.remaining > 0]
        if not pending:
            return None
        return max(pending, key=lambda r: r.remaining)


@dataclass(slots=True)
class ColonyBook:
    """Every construction site the journal has described."""

    sites: dict[int, ConstructionSite] = field(default_factory=dict)
    #: The last site to report, which is the one last delivered to.
    last_market_id: int = 0
    #: The site the commander is docked at, if any.
    docked_market_id: int = 0

    def __len__(self) -> int:
        return len(self.sites)

    def observe(self, event: dict) -> bool:
        name = str(event.get("event") or "")
        if name in ("Docked", "Location"):
            return self._observe_location(event)
        if name == "ColonisationConstructionDepot":
            return self._observe_depot(event)
        return False

    def _observe_location(self, event: dict) -> bool:
        """Learn a site's name, and note which one we are docked at.

        Recognising a site by its name would be wrong -- the name is localised,
        and a Russian client calls it something else -- so the only test is
        whether this MarketID is one a depot event has already described. A place
        we have not seen a construction report for is simply a place.
        """
        # Leaving comes first: a Location with Docked false carries no MarketID,
        # and checking for one first left the previous site standing while the
        # commander flew away from it.
        if str(event.get("event")) == "Location" and not event.get("Docked"):
            self.docked_market_id = 0
            return False
        market = _as_int(event.get("MarketID"))
        if market is None:
            return False
        if market not in self.sites:
            self.docked_market_id = 0
            return False

        self.docked_market_id = market
        site = self.sites[market]
        station = str(event.get("StationName") or "")
        if station and site.name != station:
            site.name = station
            return True
        return False

    def _observe_depot(self, event: dict) -> bool:
        market = _as_int(event.get("MarketID"))
        if market is None:
            return False
        site = self.sites.get(market)
        if site is None:
            site = ConstructionSite(market_id=market)
            self.sites[market] = site

        progress = event.get("ConstructionProgress")
        if isinstance(progress, (int, float)) and not isinstance(progress, bool):
            site.progress = float(progress)
        site.complete = bool(event.get("ConstructionComplete"))
        site.failed = bool(event.get("ConstructionFailed"))

        resources = event.get("ResourcesRequired")
        if isinstance(resources, list):
            for raw in resources:
                if not isinstance(raw, dict):
                    continue
                symbol = normalise(str(raw.get("Name") or ""))
                if not symbol:
                    continue
                resource = Resource(symbol=symbol)
                name = str(raw.get("Name_Localised") or "").strip()
                resource.name = name or str(raw.get("Name") or "").strip()
                resource.required = _as_int(raw.get("RequiredAmount")) or 0
                resource.provided = _as_int(raw.get("ProvidedAmount")) or 0
                resource.payment = _as_int(raw.get("Payment")) or 0
                site.resources[symbol] = resource

        self.last_market_id = market
        log.info(
            "colony %s: %.2f%%, %d т still to deliver over %d commodities",
            site.name or market,
            site.percent,
            site.remaining,
            site.outstanding,
        )
        return True

    def current(self) -> ConstructionSite | None:
        """The site worth showing, or None.

        The one being stood on wins, whatever state it is in -- that is where a
        commander is looking at it. Otherwise the last site to report, but only
        while it is still being built: a finished or failed site is worth a line
        when you are there and worth nothing from three systems away.
        """
        if self.docked_market_id and self.docked_market_id in self.sites:
            return self.sites[self.docked_market_id]
        site = self.sites.get(self.last_market_id)
        if site is None or site.complete or site.failed:
            return None
        return site
