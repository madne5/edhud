"""Fleet carriers: their callsigns, where they are, and how full their holds are.

A commander may have two -- a personal carrier and a squadron one -- and this
project's own journals contain exactly that: ``KSS0`` flying as a
SquadronCarrier and ``V3G-N1H`` as a FleetCarrier, which are the two callsign
shapes the game uses.

Only one event carries the callsign and the hold: ``CarrierStats``. It fires when
the carrier's management is opened rather than at every login, so on its own the
bar would be blank until the commander happened to look at a carrier. The events
that *do* fire at every login -- ``CarrierLocation``, one per carrier -- carry the
identifier, the type and the system but no callsign. So what is learned from
CarrierStats is cached beside the configuration and re-shown from there, and the
location is refreshed from the login events in between.

On the numbers for the hold: ``SpaceUsage`` reports ``TotalCapacity``, ``Cargo``,
``CargoSpaceReserved``, ``ShipPacks``, ``ModulePacks``, ``Crew`` and ``FreeSpace``,
and they close exactly. In these journals ``V3G-N1H`` reports 25000 total with
7001 cargo, 12857 reserved and 5142 free: the reservation is a buy order holding
the space before anything has been delivered, and it is the term that makes the
figures add up. Every value is read from the event rather than derived from
another, and the load is always ``Cargo`` -- showing ``FreeSpace`` as though it
were the load is what made a purchase contract look like delivered goods.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_FILENAME = "carriers.json"

#: Personal carriers sort before squadron ones, because the first is the
#: commander's own.
KIND_ORDER = {"FleetCarrier": 0, "SquadronCarrier": 1}


@dataclass(slots=True)
class CarrierInfo:
    """Everything known about one carrier."""

    carrier_id: int
    callsign: str = ""
    name: str = ""
    kind: str = ""
    system: str = ""
    cargo: int = 0
    total_capacity: int = 0
    free_space: int = 0
    #: Tonnes held back by outstanding buy orders. Counted in ``free_space``
    #: before anything has been delivered, which is why free space is not a
    #: measure of what is on board: a 20000 t order on a 25000 t carrier drops
    #: free space to about 5000 while the hold still holds almost nothing.
    cargo_space_reserved: int = 0
    crew: int = 0
    fuel: int = 0
    #: "all" | "friends" | "squadron" | "squadronfriends" | "none", as the game
    #: spells it, or "" when CarrierStats has not been seen.
    docking_access: str = ""
    balance: int | None = None
    reserve: int | None = None

    @property
    def known(self) -> bool:
        """Whether it can be named. A carrier seen only in CarrierLocation has
        an identifier but no callsign, and showing the number would be noise."""
        return bool(self.callsign)

    @property
    def label(self) -> str:
        return self.callsign or str(self.carrier_id)

    @property
    def squadron(self) -> bool:
        return self.kind == "SquadronCarrier"

    def hold(self) -> tuple[int, int]:
        """(cargo, total) -- what is actually in the hold, of what fits.

        Cargo, not free space. The two differ by more than the load: free space
        also excludes crew quarters, ship packs and module packs, and it falls
        the moment a buy order is placed, before a single tonne has arrived.
        Showing free space as though it were the load made a 20000 t purchase
        contract read as 20000 t already delivered.
        """
        return (self.cargo, self.total_capacity)

    def reserved_note(self) -> str:
        """The buy-order reservation as a short suffix, or "" when there is none."""
        return str(self.cargo_space_reserved) if self.cargo_space_reserved > 0 else ""

    def access_role(self) -> str:
        """Which palette role the carrier's icon should use.

        Green where anyone may dock, orange where docking is limited to friends,
        the squadron, or both. ``none`` -- nobody may dock -- is grouped with the
        restricted values rather than given a colour of its own, because it is
        still "not open to all"; it can be split out if that reads wrong.

        An empty string means CarrierStats has not been seen, so the icon keeps
        whatever colour the row would otherwise give it rather than claiming an
        access level that is not known.
        """
        if not self.docking_access:
            return ""
        return "success" if self.docking_access == "all" else "warning"


@dataclass(slots=True)
class CarrierBook:
    """Every carrier this commander has, learned and remembered."""

    cache_path: Path | None = None
    persist: bool = True
    carriers: dict[int, CarrierInfo] = field(default_factory=dict)
    #: The carrier the commander is docked at, by CarrierID, or 0.
    #:
    #: Needed because ``CargoTransfer`` does not say what it moved cargo
    #: between: the same event covers the SRV emptying into the ship after a
    #: mining run, and in these journals six of the eight transfers were exactly
    #: that. Docking is the only thing that tells them apart, because cargo can
    #: only move to or from a carrier while docked at one.
    docked_carrier_id: int = 0

    def __post_init__(self) -> None:
        self.persist = self.persist and self.cache_path is not None
        self._load()

    # -- storage -----------------------------------------------------------

    def _load(self) -> None:
        if self.cache_path is None:
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            try:
                carrier_id = int(key)
            except (TypeError, ValueError):
                continue
            info = CarrierInfo(carrier_id=carrier_id)
            for name in (
                "callsign", "name", "kind", "system", "docking_access",
            ):
                text = value.get(name)
                if isinstance(text, str):
                    setattr(info, name, text)
            for name in (
                "cargo", "total_capacity", "free_space", "cargo_space_reserved",
                "crew", "fuel",
            ):
                number = value.get(name)
                if isinstance(number, int) and not isinstance(number, bool):
                    setattr(info, name, number)
            for name in ("balance", "reserve"):
                number = value.get(name)
                if isinstance(number, int) and not isinstance(number, bool):
                    setattr(info, name, number)
            self.carriers[carrier_id] = info
        log.debug("loaded %d carrier(s) from %s", len(self.carriers), self.cache_path)

    def _save(self) -> None:
        if not self.persist or self.cache_path is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {str(k): asdict(v) for k, v in self.carriers.items()}
            self.cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            # Losing the cache costs the callsign until the next CarrierStats.
            log.debug("cannot write carrier cache %s: %s", self.cache_path, exc)

    # -- learning ----------------------------------------------------------

    def info(self, carrier_id: int) -> CarrierInfo | None:
        if not isinstance(carrier_id, int) or isinstance(carrier_id, bool):
            return None
        return self.carriers.get(carrier_id)

    def ensure(self, carrier_id: int) -> CarrierInfo | None:
        if not isinstance(carrier_id, int) or isinstance(carrier_id, bool):
            return None
        info = self.carriers.get(carrier_id)
        if info is None:
            info = CarrierInfo(carrier_id=carrier_id)
            self.carriers[carrier_id] = info
        return info

    @staticmethod
    def _int_or(value, fallback: int) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return fallback

    def observe(self, event: dict) -> bool:
        """Fold in any carrier event. Returns True when something was learned."""
        name = str(event.get("event") or "")

        # These carry no CarrierID, so they are handled before the check that
        # every other carrier event has to pass.
        if name in ("Docked", "Undocked") or name == "Location":
            return self._observe_docking(event)
        if name == "CargoTransfer":
            return self._observe_transfer(event)
        if name in ("MarketSell", "MarketBuy"):
            return self._observe_market_trade(name, event)

        carrier_id = event.get("CarrierID")
        if not isinstance(carrier_id, int) or isinstance(carrier_id, bool):
            return False
        info = self.ensure(carrier_id)
        if info is None:  # pragma: no cover - ensure only fails on a bad id
            return False
        before = asdict(info)

        if name == "CarrierStats":
            info.callsign = str(event.get("Callsign") or info.callsign)
            info.name = str(event.get("Name") or info.name)
            info.kind = str(event.get("CarrierType") or info.kind)
            info.fuel = self._int_or(event.get("FuelLevel"), info.fuel)
            access = event.get("DockingAccess")
            if isinstance(access, str) and access:
                info.docking_access = access.casefold()
            usage = event.get("SpaceUsage")
            if isinstance(usage, dict):
                info.cargo = self._int_or(usage.get("Cargo"), info.cargo)
                info.total_capacity = self._int_or(
                    usage.get("TotalCapacity"), info.total_capacity
                )
                info.free_space = self._int_or(usage.get("FreeSpace"), info.free_space)
                # Read, not derived. SpaceUsage closes exactly -- Cargo +
                # CargoSpaceReserved + FreeSpace + Crew + packs = TotalCapacity
                # -- so subtracting one field from another invents a number
                # instead of reporting one.
                info.cargo_space_reserved = self._int_or(
                    usage.get("CargoSpaceReserved"), info.cargo_space_reserved
                )
                info.crew = self._int_or(usage.get("Crew"), info.crew)
            finance = event.get("Finance")
            if isinstance(finance, dict):
                balance = finance.get("CarrierBalance")
                if isinstance(balance, int) and not isinstance(balance, bool):
                    info.balance = balance
                reserve = finance.get("ReserveBalance")
                if isinstance(reserve, int) and not isinstance(reserve, bool):
                    info.reserve = reserve
        elif name in ("CarrierLocation", "CarrierJump"):
            info.kind = str(event.get("CarrierType") or info.kind)
            info.system = str(event.get("StarSystem") or info.system)
        elif name == "CarrierFinance":
            balance = event.get("CarrierBalance")
            if isinstance(balance, int) and not isinstance(balance, bool):
                info.balance = balance
            reserve = event.get("ReserveBalance")
            if isinstance(reserve, int) and not isinstance(reserve, bool):
                info.reserve = reserve
            info.kind = str(event.get("CarrierType") or info.kind)
        else:
            return False

        if asdict(info) == before:
            return False
        self._save()
        return True

    # -- cargo moving, between the reports ---------------------------------
    #
    # CarrierStats is the only event that states the hold, and it fires when the
    # carrier's management is opened -- not when cargo moves. In the journals
    # this project was built against, 1232 t of tritium left KSS0 at 08:43 and
    # the new figure (5081, exactly 1232 less) did not arrive until 09:00, when
    # the commander next opened that screen. Seventeen minutes of showing a
    # number that was wrong, which is what "the hold does not update" was.
    #
    # So the events that move cargo adjust the figure in between. Both
    # directions are confirmed against those journals: 6089 + 224 = 6313 after a
    # 224 t transfer to KSS0, and 6313 - 1232 = 5081 after a 1232 t transfer
    # from it. The next CarrierStats overwrites whatever this worked out, so a
    # mistake here cannot survive long.

    def _observe_docking(self, event: dict) -> bool:
        """Remember which carrier the commander is docked at.

        A ``CargoTransfer`` does not say what the cargo moved between, and the
        same event covers the SRV emptying into the ship after a mining run:
        six of the eight transfers in these journals were that, and none of them
        touched a carrier's hold. Docking separates them exactly, because cargo
        only reaches or leaves a carrier while docked at one.

        Two events say where the commander is, and both are needed. ``Docked``
        fires when they dock, but a transfer often happens in a *later* journal
        file than the docking did -- on 2026-09-16 the docking was in the
        previous file and the transfer that emptied 1232 t out of KSS0 was at
        08:43:23 in the next one. ``Location`` is written at every login and
        carries ``Docked: true`` with the station and its MarketID, which is what
        closes that gap: relying on ``Docked`` alone silently dropped that
        transfer, and the bar then showed a figure 1232 t too high until the
        commander next opened the carrier screen.
        """
        name = event.get("event")
        if name == "Undocked":
            self.docked_carrier_id = 0
            return False
        if name == "Location" and not event.get("Docked"):
            # In space, or docked nowhere: whatever we were at, we have left.
            self.docked_carrier_id = 0
            return False

        # Docking anywhere that is not a carrier means any earlier carrier is
        # behind us; a stale value here would attribute a later SRV transfer to
        # it.
        if str(event.get("StationType") or "") != "FleetCarrier":
            self.docked_carrier_id = 0
            return False

        # A carrier's MarketID is its CarrierID. Verified on both carriers in
        # the journals: Docked at "KSS0" reports 3713063168, which is KSS0's
        # CarrierID, and "V3G-N1H" reports 3714982656, which is V3G-N1H's.
        market = event.get("MarketID")
        self.docked_carrier_id = (
            market if isinstance(market, int) and not isinstance(market, bool) else 0
        )
        return False

    def _observe_transfer(self, event: dict) -> bool:
        """Apply a ship-to-carrier or carrier-to-ship cargo move."""
        carrier_id = self.docked_carrier_id
        if not carrier_id:
            return False
        transfers = event.get("Transfers")
        if not isinstance(transfers, list):
            return False

        delta = 0
        for item in transfers:
            if not isinstance(item, dict):
                continue
            count = item.get("Count")
            if not isinstance(count, int) or isinstance(count, bool):
                continue
            direction = str(item.get("Direction") or "").casefold()
            if direction == "tocarrier":
                delta += count
            elif direction == "toship":
                delta -= count
        return self._apply_cargo_delta(carrier_id, delta, "CargoTransfer")

    def _observe_market_trade(self, name: str, event: dict) -> bool:
        """Apply a trade at a carrier's own market.

        Selling to a carrier puts the goods in its hold; buying from it takes
        them out. Every market trade in these journals happened at a station, so
        this direction is read from what the events mean rather than measured --
        the identity that makes it safe is not: MarketID matches a known
        CarrierID, which no station can satisfy.
        """
        market = event.get("MarketID")
        if not isinstance(market, int) or isinstance(market, bool):
            return False
        if market not in self.carriers:
            return False
        count = event.get("Count")
        if not isinstance(count, int) or isinstance(count, bool):
            return False
        return self._apply_cargo_delta(
            market, count if name == "MarketSell" else -count, name
        )

    def _apply_cargo_delta(self, carrier_id: int, delta: int, source: str) -> bool:
        """Move the known hold, never below zero, and say so in the log."""
        info = self.carriers.get(carrier_id)
        if info is None or not delta:
            return False
        updated = max(0, info.cargo + delta)
        if updated == info.cargo:
            return False
        log.info(
            "carrier %s hold %d -> %d т (%s, awaiting the next CarrierStats)",
            info.label,
            info.cargo,
            updated,
            source,
        )
        info.cargo = updated
        self._save()
        return True

    # -- display -----------------------------------------------------------

    def known(self) -> list[CarrierInfo]:
        """Carriers that can be named, personal first, then by callsign."""
        return sorted(
            (info for info in self.carriers.values() if info.known),
            key=lambda info: (KIND_ORDER.get(info.kind, 9), info.callsign),
        )

    def __len__(self) -> int:
        return len(self.carriers)
