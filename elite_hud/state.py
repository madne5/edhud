"""Game state derived from the Elite Dangerous journal.

``GameState.apply(event)`` is the single entry point: it mutates state and
returns the list of :class:`Alert` objects raised by that event.  Nothing here
touches the filesystem or the UI, which keeps it trivially unit-testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import jump_range
from .carriers import CarrierBook
from .crime import CrimeRecord
from .deliveries import DeliveryBook
from .materials import MaterialNotice, MaterialTable
from .notices import DockingNotice
from .ships import ShipNames

log = logging.getLogger(__name__)


def parse_timestamp(value: object) -> datetime | None:
    """Parse a journal ISO-8601 timestamp (``...Z`` or with offset)."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        log.debug("unparseable timestamp %r", value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# state containers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SystemState:
    """Everything the HUD shows about the system the commander is in."""

    name: str = ""
    address: int = 0
    body_count: int = 0
    non_body_count: int = 0
    fss_progress: float = 0.0
    fss_all_found: bool = False
    scanned_bodies: int = 0
    #: BodyIDs already counted towards ``scanned_bodies`` in this system
    scanned_ids: set[int] = field(default_factory=set)
    @property
    def progress_percent(self) -> float:
        if self.fss_all_found:
            return 100.0
        if self.fss_progress > 0:
            return max(0.0, min(1.0, self.fss_progress)) * 100.0
        if self.body_count > 0:
            return max(0.0, min(1.0, self.scanned_bodies / self.body_count)) * 100.0
        return 0.0

    def clear(self) -> None:
        self.name = ""
        self.address = 0
        self.body_count = 0
        self.non_body_count = 0
        self.fss_progress = 0.0
        self.fss_all_found = False
        self.scanned_bodies = 0
        self.scanned_ids.clear()



#: Frontier's numbers, overridden by the [carrier] config section. The journal
#: never reports a cooldown anywhere -- not in CarrierStats, not in any event --
#: so the HUD has to derive it.
#:
#: The cooldown is about five minutes, and it runs from DepartureTime -- the
#: moment the carrier jumps -- not from arrival. Measured from a commander's own
#: journals: requests went through 296, 299 and 303 seconds after departure, so
#: the game allows one from 296 seconds at the latest. 290 is EDDI's and the
#: Carrier Manager's constant and fits comfortably under that floor.
#:
#: The wiki's "5-minute cooldown after the jump completes" reads as though it
#: started at arrival, which would be 62 seconds later than it does. The wiki's
#: own summary of the cycle -- "you can jump every 20 minutes" -- only adds up
#: with a 15-minute spool and a 5-minute cooldown both counted from the request.
#:
#: `elite-hud --carrier-report` re-measures this from whatever journals are on
#: hand, so the number can be rechecked rather than trusted.
DEFAULT_CARRIER_SPOOL_SECONDS = 15 * 60.0
DEFAULT_CARRIER_COOLDOWN_SECONDS = 290.0

#: How long the jump itself takes, from DepartureTime to arrival. Measured at
#: 59-64 seconds over seventeen jumps, median 62.
DEFAULT_CARRIER_JUMP_SECONDS = 62.0

#: Cancelling a scheduled jump imposes its own, much shorter, cooldown.
DEFAULT_CARRIER_CANCEL_SECONDS = 60.0

#: How long "ready to jump" is worth showing once the cooldown has elapsed.
CARRIER_READY_DISPLAY_SECONDS = 60.0


@dataclass(slots=True)
class CarrierState:
    """Fleet carrier identity plus any scheduled jump."""

    carrier_id: int = 0
    callsign: str = ""
    name: str = ""
    target_system: str = ""
    departure: datetime | None = None
    requested_at: datetime | None = None
    #: set when a CarrierJumpRequest carried no DepartureTime and we inferred one
    departure_inferred: bool = False
    #: Last system the carrier was reported in.
    last_system: str = ""
    #: Absolute moment the carrier may be sent somewhere again. An absolute
    #: time rather than "last jump plus a duration", because the events that
    #: establish it (a request, an arrival, a cancellation) each name a different
    #: starting point, and taking the latest is what keeps them consistent.
    ready_at: datetime | None = None
    #: How long "ready" stays on screen once the cooldown has elapsed.
    ready_display_seconds: float = CARRIER_READY_DISPLAY_SECONDS

    @property
    def jump_scheduled(self) -> bool:
        """True while a `CarrierJumpRequest` is on record (even if overdue)."""
        return self.departure is not None

    def seconds_until_jump(self, now: datetime | None = None) -> float | None:
        """Seconds left, or ``None`` when there is no live countdown.

        An overdue departure returns ``None``: :meth:`settle` will have turned
        it into a jump, and a countdown frozen at ``00:00`` helps nobody.
        """
        if self.departure is None:
            return None
        now = now or utcnow()
        remaining = (self.departure - now).total_seconds()
        if remaining <= 0:
            return None
        return remaining

    def seconds_until_ready(self, now: datetime | None = None) -> float | None:
        """Seconds left of the cooldown, or ``None`` when it may jump now.

        ``None`` also covers "we have never seen this carrier move", because
        there is nothing meaningful to show in that case.
        """
        if self.ready_at is None:
            return None
        now = now or utcnow()
        remaining = (self.ready_at - now).total_seconds()
        if remaining <= 0:
            return None
        return remaining

    def became_ready(self, now: datetime | None = None) -> bool:
        """True briefly after the cooldown ends, so the bar can say "ready"."""
        if self.ready_at is None:
            return False
        now = now or utcnow()
        elapsed = (now - self.ready_at).total_seconds()
        return 0 <= elapsed < self.ready_display_seconds

    def block_until(self, when: datetime, *, replace: bool = False) -> None:
        """Record the earliest moment a jump may be requested.

        The latest of the known sources normally wins: a request and the matching
        arrival derive the moment differently but agree to the second, so taking
        the maximum keeps them consistent whichever is seen first.

        ``replace`` is for a cancellation, which *revokes* the cooldown the
        request had booked -- the jump never happens, so only the short
        cancellation cooldown applies. It is safe because the game refuses a new
        request while a cooldown is running, so the two cannot overlap.
        """
        if replace or self.ready_at is None or when > self.ready_at:
            self.ready_at = when

    def settle(self, now: datetime | None = None) -> bool:
        """Advance state that depends on the passage of time.

        Once a scheduled departure time has passed the carrier has jumped --
        whether or not this commander was aboard to see the ``CarrierJump``
        event. Turning that into the arrival (and so starting the cooldown)
        keeps the bar moving instead of expiring into silence.
        """
        if self.departure is None:
            return False
        now = now or utcnow()
        if now < self.departure:
            return False
        # The jump is under way, so it is no longer "scheduled". The cooldown
        # itself was already established when the jump was requested.
        self.cancel()
        return True

    def cancel(self) -> None:
        self.target_system = ""
        self.departure = None
        self.requested_at = None
        self.departure_inferred = False


@dataclass(slots=True)
class JumpPlan:
    """Where the commander is going next.

    ``FSDTarget`` is the only routine source for this, and it is written when a
    target is chosen in the galaxy map: it carries the system name, the star
    class and how many jumps remain. A plotted ``NavRoute`` would be better --
    it carries every leg with coordinates -- but the journals this was built
    against contain 83 NavRoute events and not one of them has a single leg,
    so that path is written and left untested against real data.
    """

    #: Target system name, empty when nothing is selected.
    target: str = ""
    star_class: str = ""
    #: Jumps remaining when the target was set, counted down on arrival.
    remaining: int = 0
    #: Legs of a plotted route, outermost last; usually empty in practice.
    route: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.target)

    def arrive(self, system: str) -> None:
        """Clear the plan when the commander reaches the system it named.

        The name in ``FSDTarget`` is the *next waypoint*, not the final
        destination: across the journals this was built against the name changes
        on every hop while ``RemainingJumpsInRoute`` counts down 8, 7, 6, 5. The
        game re-issues the event with the following waypoint as soon as the
        route advances -- often while still in the previous system -- so
        arriving at the named system means that leg is finished.

        Clearing is therefore right, and decrementing would be wrong: it would
        read "7 jumps" while the commander is sitting in the target. If there is
        more route left, the next FSDTarget arrives immediately and restores the
        plan with the game's own number.
        """
        if not self.target or system != self.target:
            return
        self.clear()

    def clear(self) -> None:
        self.target = ""
        self.star_class = ""
        self.remaining = 0
        self.route.clear()


# ---------------------------------------------------------------------------
# main state machine
# ---------------------------------------------------------------------------

#: `CarrierJumpRequest` in current builds carries `DepartureTime`; older builds
#: only carried the request, and the carrier then spools up for this long.

# Events the HUD deliberately ignores: FSSSignalDiscovered (other signal types),
# SAAScanComplete, NavBeaconScan, SellExplorationData, Materials, Rank, ... .
# Any event without a matching ``_on_<Name>`` method is simply skipped.


class GameState:
    def __init__(
        self,
        *,
        carrier_spool_seconds: float = DEFAULT_CARRIER_SPOOL_SECONDS,
        carrier_cooldown_seconds: float = DEFAULT_CARRIER_COOLDOWN_SECONDS,
        carrier_jump_seconds: float = DEFAULT_CARRIER_JUMP_SECONDS,
        carrier_cancel_seconds: float = DEFAULT_CARRIER_CANCEL_SECONDS,
        carrier_ready_display_seconds: float = CARRIER_READY_DISPLAY_SECONDS,
        ship_names: ShipNames | None = None,
        ship_cache: Path | None = None,
        carrier_book: CarrierBook | None = None,
        carrier_cache: Path | None = None,
        material_table: MaterialTable | None = None,
        materials_enabled: bool = True,
        material_notify: bool = True,
        rarity_label: str = "Редкость",
        total_label: str = "Всего",
        show_docking_denied: bool = True,
    ) -> None:
        #: Where the commander is heading next.
        self.jump_plan = JumpPlan()
        #: Fines owed and notoriety.
        self.crime = CrimeRecord()
        #: Open missions that involve carrying a commodity somewhere.
        self.deliveries = DeliveryBook()
        #: Ship model names, learned from the journal (see elite_hud/ships.py).
        # `is not None`, not `or`: these objects define __len__, so an empty one
        # is falsy and would be silently replaced.
        self.ship_names = (
            ship_names if ship_names is not None else ShipNames(ship_cache)
        )
        #: Fleet carriers, learned and cached (see elite_hud/carriers.py).
        self.carriers = (
            carrier_book
            if carrier_book is not None
            else CarrierBook(cache_path=carrier_cache)
        )
        #: The model as the game names it, e.g. "Caspian Explorer".
        self.ship_model = ""
        #: Cargo rack total, from Loadout.
        self.cargo_capacity = 0
        #: Tonnes currently in the hold.
        self.cargo_count = 0
        #: Live values that only Status.json reports.
        self.legal_state = ""
        #: True while the status file is the source of the balance.
        self.status_live = False
        self.carrier_spool_seconds = carrier_spool_seconds
        self.carrier_cooldown_seconds = carrier_cooldown_seconds
        self.carrier_jump_seconds = carrier_jump_seconds
        self.carrier_cancel_seconds = carrier_cancel_seconds

        self.commander = ""
        self.ship = ""
        self.odyssey = False
        self.game_mode = ""
        self.credits: int | None = None
        self.system = SystemState()
        self.carrier = CarrierState(ready_display_seconds=carrier_ready_display_seconds)

        # -- engineering materials ---------------------------------------
        #: Rarity and canonical names; rarity is the one thing the journal never
        #: states, so it comes from the bundled table.
        self.material_table = (
            material_table if material_table is not None else MaterialTable()
        )
        #: What the commander holds, by journal symbol.
        self.holdings: dict[str, int] = {}
        #: A Materials event reports the whole hold at once and fires at login.
        #: Until one has been seen the hold is unknown, not empty -- see
        #: MaterialNotice.total.
        self.materials_known = False
        self.materials_enabled = materials_enabled
        self.material_notify = material_notify
        #: Labels, so the wording lives in config rather than in this module.
        self.rarity_label = rarity_label
        self.total_label = total_label
        #: Facts worth showing for a few seconds, oldest first: material
        #: pickups and refused docking requests. The overlay turns them into
        #: text, because how they read is a matter of configuration.
        self.notices: list[MaterialNotice | DockingNotice] = []
        self.show_docking_denied = show_docking_denied

        self.last_event: str = ""
        self.last_event_at: datetime | None = None
        self.events_seen = 0

        #: "Open" | "Solo" | "Group", as loaded and as changed in session.
        self.game_mode: str = ""
        #: Private group name, when the mode is Group.
        self.group_name: str = ""

        #: Rank index per track, e.g. {"Combat": 3}.
        #: Percent towards the next step of each track, 0-100.

        self.ship_ident: str = ""
        self.ship_name: str = ""
        self.ship_type: str = ""
        self.max_jump_range: float = 0.0
        self.current_jump_range: float = 0.0
        #: Fuel in the main tank, and how much cargo is aboard: both feed the
        #: laden jump range.
        self.fuel_level: float = 0.0
        self.fuel_capacity: float = 0.0
        self.cargo_count: int = 0
        self.unladen_mass: float = 0.0
        self._drive: jump_range.DriveSpec | None = None
        self._booster: float = 0.0

        #: MissionIDs the commander currently holds.
        self.active_missions: set[int] = set()
        #: False until the journal has actually told us about missions, so the
        #: HUD does not claim "0/20" before anything has been read.
        self.missions_known = False

        #: Announcements raised by the events folded in so far.

        #: (system_address, body_id, organic key) -> best confidence alerted so far

    # -- public API --------------------------------------------------------

    def apply(self, event: dict) -> None:
        """Fold one journal event into the state."""
        name = event.get("event")
        if not isinstance(name, str):
            return
        self.events_seen += 1
        self.last_event = name
        self.last_event_at = parse_timestamp(event.get("timestamp")) or utcnow()

        handler = getattr(self, f"_on_{name}", None)
        if handler is None:
            return
        try:
            handler(event)
        except Exception:
            # One malformed event must not stop the HUD: the journal is written
            # by the game, but a replay of an older format or a hand-edited file
            # can still carry something unexpected.
            log.exception("failed to process %s", name)

    def reset(self) -> None:
        self.system.clear()
        self.carrier = CarrierState(ready_display_seconds=self.carrier.ready_display_seconds)

    def settle(self, now: datetime | None = None) -> None:
        """Advance state that depends on the clock; call from the UI loop."""
        self.carrier.settle(now)

    # -- ships -------------------------------------------------------------

    def _on_ShipyardSwap(self, event: dict) -> None:
        if self.ship_names.observe(event):
            log.debug("learned ship name: %s", self.ship_names.names)
        # A swap changes the current ship without a Loadout in some cases.
        symbol = str(event.get("ShipType") or "")
        if symbol:
            self.ship_type = symbol
            self.ship_model = self.ship_names.display(symbol)
            self.ship = self.ship_model

    def _on_StoredShips(self, event: dict) -> None:
        self.ship_names.observe(event)

    def _on_ShipyardTransfer(self, event: dict) -> None:
        self.ship_names.observe(event)

    # -- crime -------------------------------------------------------------

    def _on_Statistics(self, event: dict) -> None:
        """The only place notoriety is reported, once per session start."""
        crime = event.get("Crime")
        if isinstance(crime, dict):
            self.crime.observe_statistics(crime)

    def _on_CommitCrime(self, event: dict) -> None:
        fine = event.get("Fine")
        amount = int(fine) if isinstance(fine, int) and not isinstance(fine, bool) else 0
        self.crime.add_fine(amount, crime=str(event.get("CrimeType") or ""))

    def _on_PayFines(self, event: dict) -> None:
        amount = event.get("Amount")
        self.crime.pay_fines(
            int(amount) if isinstance(amount, int) and not isinstance(amount, bool) else 0,
            all_fines=bool(event.get("AllFines")),
        )

    def apply_status(self, snapshot) -> None:
        """Fold in a Status.json snapshot.

        Only fields the snapshot actually carries are applied. The game empties
        this file on exit, and a stub must not wipe a balance the journal
        already gave us from the last LoadGame.
        """
        if snapshot.balance is not None:
            self.credits = snapshot.balance
            self.status_live = True
        elif snapshot.empty and self.status_live:
            # The file went back to its post-exit stub: stop claiming to be live
            # rather than keep showing a number nothing is updating.
            self.status_live = False
        if snapshot.legal_state:
            self.legal_state = snapshot.legal_state
        if snapshot.cargo is not None:
            # Status.json is the live figure; the Cargo event only fires on a
            # change the game chooses to report.
            self.cargo_count = max(0, int(snapshot.cargo))

    # -- session / location ------------------------------------------------

    def _on_Fileheader(self, event: dict) -> None:
        self.odyssey = bool(event.get("Odyssey", False))
        log.info(
            "journal gameversion %s (build %s, language %s, Odyssey=%s)",
            event.get("gameversion") or event.get("version"),
            (event.get("build") or "").strip(),
            event.get("language"),
            self.odyssey,
        )

    def _on_LoadGame(self, event: dict) -> None:
        self.ship_names.observe(event)
        self.commander = str(event.get("Commander") or self.commander)
        mode = str(event.get("GameMode") or "")
        if mode:
            self.game_mode = mode
        self.group_name = str(event.get("Group") or "")
        self.credits = event.get("Credits", self.credits)

    def _on_GameModeChange(self, event: dict) -> None:
        """Only Open, Solo and Group are modes we display.

        The game also reports "MainGame" here, which is about the launcher
        versus CQC rather than about who else is in the instance, so it is
        ignored.
        """
        mode = str(event.get("GameMode") or "")
        if mode in ("Open", "Solo", "Group"):
            self.game_mode = mode
            if mode == "Group":
                self.group_name = str(event.get("Group") or self.group_name)

    def _on_Commander(self, event: dict) -> None:
        self.commander = str(event.get("Name") or self.commander)

    def _on_Loadout(self, event: dict) -> None:
        self.ship_names.observe(event)
        symbol = str(event.get("Ship") or "")
        # The model name, not the commander's own name for the ship and not the
        # ident: the journal only sometimes carries it, so the learned table
        # fills the gap.
        self.ship_type = symbol
        self.ship = str(event.get("Ship_Localised") or "") or self.ship_names.display(symbol)
        self.ship_model = self.ship
        capacity = event.get("CargoCapacity")
        if isinstance(capacity, int) and not isinstance(capacity, bool):
            self.cargo_capacity = max(0, capacity)
        self.ship_ident = str(event.get("ShipIdent") or self.ship_ident)
        self.ship_name = str(event.get("ShipName") or self.ship_name)
        mass = event.get("UnladenMass")
        if isinstance(mass, (int, float)) and mass > 0:
            self.unladen_mass = float(mass)
        capacity = event.get("FuelCapacity")
        if isinstance(capacity, dict) and isinstance(capacity.get("Main"), (int, float)):
            self.fuel_capacity = float(capacity["Main"])
            if not self.fuel_level:
                self.fuel_level = self.fuel_capacity
        self._drive, self._booster = jump_range.build_spec(event)

        maximum = event.get("MaxJumpRange")
        if isinstance(maximum, (int, float)) and maximum > 0:
            self.max_jump_range = float(maximum)
        self._recompute_jump_range()

    def _recompute_jump_range(self) -> None:
        """Refresh the laden range after anything that changes the ship's mass."""
        if self.max_jump_range <= 0:
            return
        self.current_jump_range = jump_range.current_range(
            max_jump_range=self.max_jump_range,
            unladen_mass=self.unladen_mass,
            fuel=self.fuel_level,
            cargo=float(self.cargo_count),
            spec=self._drive,
            booster=self._booster,
        )

    def _on_Cargo(self, event: dict) -> None:
        # Only the ship's own hold counts; an SRV has its own. A missing Vessel is
        # not assumed to mean the ship: every one of the 575 Cargo events in this
        # project's journals states it (544 Ship, 31 SRV), so an event without it
        # is a shape we have never seen, and counting it could put an SRV's hold
        # on the bar as the ship's. The live status file supplies the count anyway.
        vessel = str(event.get("Vessel") or "")
        if vessel != "Ship":
            if not vessel:
                log.debug("Cargo event without a Vessel; ignoring it")
            return
        count = event.get("Count")
        if isinstance(count, int) and not isinstance(count, bool):
            self.cargo_count = max(0, count)
            self._recompute_jump_range()

    def _on_FuelScoop(self, event: dict) -> None:
        total = event.get("Total")
        if isinstance(total, (int, float)):
            self.fuel_level = float(total)
            self._recompute_jump_range()

    def _on_RefuelAll(self, event: dict) -> None:
        if self.fuel_capacity:
            self.fuel_level = self.fuel_capacity
            self._recompute_jump_range()

    # -- missions ----------------------------------------------------------

    def _on_CargoDepot(self, event: dict) -> None:
        """How much of a mission's commodity has moved, and how much is left."""
        self.deliveries.observe(event)

    def _on_Missions(self, event: dict) -> None:
        """Written at startup with whatever missions are still open."""
        self.missions_known = True
        active = event.get("Active")
        if isinstance(active, list):
            self.active_missions = {
                int(m["MissionID"]) for m in active
                if isinstance(m, dict) and isinstance(m.get("MissionID"), int)
            }

    def _on_MissionAccepted(self, event: dict) -> None:
        self.missions_known = True
        mission_id = event.get("MissionID")
        if isinstance(mission_id, int):
            self.active_missions.add(mission_id)
        # A mission that names a commodity and an amount is one that involves
        # moving cargo, so it joins the delivery book from the moment it is taken.
        self.deliveries.observe(event)

    def _close_mission(self, event: dict) -> None:
        self.missions_known = True
        mission_id = event.get("MissionID")
        if isinstance(mission_id, int):
            self.active_missions.discard(mission_id)
        self.deliveries.observe(event)

    _on_MissionCompleted = _close_mission
    _on_MissionAbandoned = _close_mission
    _on_MissionFailed = _close_mission

    # -- systems -----------------------------------------------------------

    def _enter_system(self, name: str, address: int) -> None:
        if self.system.address == address and self.system.name == name:
            return
        log.info("entering system %s (%s)", name, address)
        self.system.clear()
        self.system.name = name
        self.system.address = address
        # Arriving at the target consumes a leg of the plan.
        self.jump_plan.arrive(name)

    def _on_FSDTarget(self, event: dict) -> None:
        name = str(event.get("Name") or "")
        if not name:
            return
        remaining = event.get("RemainingJumpsInRoute")
        self.jump_plan.target = name
        self.jump_plan.star_class = str(event.get("StarClass") or "")
        self.jump_plan.remaining = int(remaining) if isinstance(remaining, int) else 1

    def _on_NavRoute(self, event: dict) -> None:
        route = event.get("Route")
        legs: list[str] = []
        if isinstance(route, list):
            for leg in route:
                if isinstance(leg, dict) and leg.get("StarSystem"):
                    legs.append(str(leg["StarSystem"]))
        self.jump_plan.route = legs
        if legs:
            # A plotted route names its own destination and length, which beats
            # FSDTarget's count, and it arrives after the target is set.
            self.jump_plan.target = legs[-1]

    def _on_NavRouteClear(self, event: dict) -> None:
        self.jump_plan.route.clear()

    def _on_FSDJump(self, event: dict) -> None:
        self._enter_system(str(event.get("StarSystem") or ""), int(event.get("SystemAddress") or 0))
        level = event.get("FuelLevel")
        if isinstance(level, (int, float)):
            self.fuel_level = float(level)
            self._recompute_jump_range()

    def _on_Location(self, event: dict) -> None:
        # Location is written at every login and says whether the commander is
        # docked and where, including when they are standing on a carrier. The
        # carrier book needs it: a cargo transfer often arrives in a later
        # journal file than the Docked event that began the visit.
        self.carriers.observe(event)
        self._enter_system(str(event.get("StarSystem") or ""), int(event.get("SystemAddress") or 0))

    def _on_CarrierJump(self, event: dict) -> None:
        # This event only exists when the commander was docked at the time, and
        # its timestamp is the arrival -- which is the jump's duration later than
        # the departure the cooldown is really measured from.
        arrived = parse_timestamp(event.get("timestamp"))
        if arrived is not None:
            self.carrier.block_until(
                arrived
                + timedelta(seconds=self.carrier_cooldown_seconds - self.carrier_jump_seconds)
            )
        self.carrier.cancel()
        if event.get("StarSystem"):
            self._enter_system(str(event["StarSystem"]), int(event.get("SystemAddress") or 0))
        return None

    def _on_CarrierLocation(self, event: dict) -> None:
        self.carriers.observe(event)
        """Reports where the carrier is: at startup, and near an arrival.

        Deliberately NOT treated as a jump. It also fires on login, where the
        last jump may have been hours earlier, so using it would show a bogus
        cooldown every time the game starts.
        """
        if event.get("StarSystem"):
            self.carrier.last_system = str(event["StarSystem"])

    # -- FSS ---------------------------------------------------------------

    def _on_FSSDiscoveryScan(self, event: dict) -> None:
        address = int(event.get("SystemAddress") or 0)
        if self.system.address and address and address != self.system.address:
            return
        if not self.system.name:
            self.system.name = str(event.get("SystemName") or "")
            self.system.address = address
        progress = event.get("Progress")
        if isinstance(progress, (int, float)):
            self.system.fss_progress = float(progress)
        if isinstance(event.get("BodyCount"), int):
            self.system.body_count = int(event["BodyCount"])
        if isinstance(event.get("NonBodyCount"), int):
            self.system.non_body_count = int(event["NonBodyCount"])

    def _on_FSSAllBodiesFound(self, event: dict) -> None:
        address = int(event.get("SystemAddress") or 0)
        if self.system.address and address and address != self.system.address:
            return
        self.system.fss_all_found = True
        self.system.fss_progress = 1.0
        if isinstance(event.get("Count"), int) and not self.system.body_count:
            self.system.body_count = int(event["Count"])

    # -- body scanning -----------------------------------------------------

    def _on_Scan(self, event: dict) -> None:
        """Count a scanned body once, for the system's scan progress.

        Rings and belt clusters arrive through the same event but are not
        bodies, so counting them would let the HUD claim a system is further
        along than it is.
        """
        address = int(event.get("SystemAddress") or 0)
        if self.system.address and address and address != self.system.address:
            return
        body_id = event.get("BodyID")
        if not isinstance(body_id, int):
            return
        name = str(event.get("BodyName") or "")
        if "Belt Cluster" in name or name.endswith("Ring"):
            return

        if body_id in self.system.scanned_ids:
            return
        self.system.scanned_ids.add(body_id)
        self.system.scanned_bodies += 1

    def _on_CargoTransfer(self, event: dict) -> None:
        # Moving cargo to or from a carrier moves its hold, and no other event
        # reports that until the management screen is opened.
        self.carriers.observe(event)

    def _on_MarketSell(self, event: dict) -> None:
        self.carriers.observe(event)

    def _on_MarketBuy(self, event: dict) -> None:
        self.carriers.observe(event)

    def _on_Docked(self, event: dict) -> None:
        # Which station we are at decides whether a later CargoTransfer belongs
        # to a carrier or to the SRV. The system is not taken from here --
        # Location and FSDJump set it, and entering a system consumes a leg of
        # the jump plan.
        self.carriers.observe(event)

    def _on_Undocked(self, event: dict) -> None:
        self.carriers.observe(event)

    def _on_DockingDenied(self, event: dict) -> None:
        """A refused docking request, with the game's own reason.

        Worth a line because the reason is not always obvious from the cockpit:
        a carrier whose pads are all taken looks exactly like one that is simply
        too far away, and the difference decides whether to wait or to fly.
        """
        if self.show_docking_denied:
            self.notices.append(
                DockingNotice(
                    station=str(event.get("StationName") or ""),
                    reason=str(event.get("Reason") or ""),
                )
            )

    def _on_CarrierStats(self, event: dict) -> None:
        self.carriers.observe(event)
        self.carrier.carrier_id = int(event.get("CarrierID") or self.carrier.carrier_id or 0)
        self.carrier.callsign = str(event.get("Callsign") or self.carrier.callsign)
        self.carrier.name = str(event.get("Name") or self.carrier.name)

    def _on_CarrierFinance(self, event: dict) -> None:
        self.carriers.observe(event)

    def _on_CarrierJumpRequest(self, event: dict) -> None:
        self.carrier.carrier_id = int(event.get("CarrierID") or self.carrier.carrier_id or 0)
        target = event.get("SystemName") or event.get("Body") or ""
        self.carrier.target_system = str(target)

        departure = parse_timestamp(event.get("DepartureTime"))
        requested_at = parse_timestamp(event.get("timestamp")) or utcnow()
        self.carrier.requested_at = requested_at
        if departure is None:
            departure = requested_at + timedelta(seconds=self.carrier_spool_seconds)
            self.carrier.departure_inferred = True
        else:
            self.carrier.departure_inferred = False
        self.carrier.departure = departure
        # The cooldown runs from departure, which is the moment the carrier
        # jumps. A CarrierJump event, when the commander was aboard, reports the
        # arrival that many seconds later and is converted back to the same
        # instant.
        self.carrier.block_until(
            departure + timedelta(seconds=self.carrier_cooldown_seconds)
        )
        log.info(
            "carrier jump scheduled to %s, departure %s%s",
            target,
            departure.isoformat(),
            " (inferred)" if self.carrier.departure_inferred else "",
        )

    def _on_CarrierJumpCancelled(self, event: dict) -> None:
        # A cancellation only concerns the carrier we are actually tracking.
        cancelled_id = int(event.get("CarrierID") or 0)
        if cancelled_id and self.carrier.carrier_id and cancelled_id != self.carrier.carrier_id:
            return
        if not self.carrier.jump_scheduled:
            return
        cancelled_at = parse_timestamp(event.get("timestamp"))
        if cancelled_at is not None:
            # Cancelling imposes its own, much shorter, cooldown.
            self.carrier.block_until(
                cancelled_at + timedelta(seconds=self.carrier_cancel_seconds),
                replace=True,
            )
        log.info("carrier jump cancelled")
        self.carrier.cancel()

    def _on_CarrierJumpRequestCancelled(self, event: dict) -> None:
        self._on_CarrierJumpCancelled(event)

    # -- engineering materials ---------------------------------------------

    def drain_notices(self) -> list[MaterialNotice | DockingNotice]:
        """Take the notices queued since the last call."""
        notices, self.notices = self.notices, []
        return notices

    def _on_Materials(self, event: dict) -> None:
        """Seed the whole hold; this event reports everything at once."""
        if not self.materials_enabled:
            return
        for kind in ("Raw", "Manufactured", "Encoded"):
            items = event.get(kind)
            if not isinstance(items, list):
                continue
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                symbol = self.material_table.normalise(str(raw.get("Name") or ""))
                if not symbol:
                    continue
                count = raw.get("Count")
                self.holdings[symbol] = int(count) if isinstance(count, int) else 0
        self.materials_known = True

    def _on_MaterialCollected(self, event: dict) -> None:
        if not self.materials_enabled:
            return
        symbol = self.material_table.normalise(str(event.get("Name") or ""))
        if not symbol:
            return
        count = event.get("Count")
        count = int(count) if isinstance(count, int) else 1
        self.holdings[symbol] = self.holdings.get(symbol, 0) + count
        if self.material_notify:
            self._announce_material(symbol, count, str(event.get("Name_Localised") or ""))

    def _on_MaterialDiscarded(self, event: dict) -> None:
        if not self.materials_enabled:
            return
        symbol = self.material_table.normalise(str(event.get("Name") or ""))
        if not symbol:
            return
        count = event.get("Count")
        count = int(count) if isinstance(count, int) else 0
        self.holdings[symbol] = max(0, self.holdings.get(symbol, 0) - count)

    def _on_MaterialTrade(self, event: dict) -> None:
        """A trader swaps one material for another, at a rate.

        The nested objects use ``Material`` and ``Quantity``, not ``Name`` and
        ``Count``: reading the latter made every trade a silent no-op, and the
        holdings then stayed wrong for the rest of the session. A test asserted
        the invented keys on both sides, so it passed against the bug.
        """
        paid = event.get("Paid")
        if isinstance(paid, dict):
            self._consume_material(paid)
        received = event.get("Received")
        if isinstance(received, dict):
            symbol = self._material_symbol(received)
            amount = self._material_amount(received)
            if symbol and amount:
                symbol = self.material_table.normalise(symbol)
                self.holdings[symbol] = self.holdings.get(symbol, 0) + amount

    @staticmethod
    def _material_symbol(entry: dict) -> str:
        """The name field differs by event: Material, Name, or a localised one."""
        return str(entry.get("Material") or entry.get("Name") or "")

    @staticmethod
    def _material_amount(entry: dict) -> int:
        for key in ("Quantity", "Count", "Amount"):
            value = entry.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return 0

    def _on_Synthesis(self, event: dict) -> None:
        materials = event.get("Materials")
        if isinstance(materials, list):
            for raw in materials:
                if isinstance(raw, dict):
                    self._consume_material(raw)

    def _on_EngineeringCraft(self, event: dict) -> None:
        # The event names ingredients only in some versions; both spellings are
        # handled because getting this wrong would silently inflate the hold.
        for key in ("Ingredients", "Materials"):
            items = event.get(key)
            if isinstance(items, list):
                for raw in items:
                    if isinstance(raw, dict):
                        self._consume_material(raw)

    def _consume_material(self, entry: dict) -> None:
        symbol = self.material_table.normalise(self._material_symbol(entry))
        if not symbol:
            return
        amount = self._material_amount(entry)
        self.holdings[symbol] = max(0, self.holdings.get(symbol, 0) - amount)

    def _announce_material(self, symbol: str, count: int, localised: str) -> None:
        """Queue the pickup line, e.g. "+1 Сера (Редкость: 1)  Всего: 285"."""
        material = self.material_table.get(symbol)
        self.notices.append(
            MaterialNotice(
                symbol=symbol,
                name=self.material_table.display_name(symbol, localised),
                count=count,
                rarity=material.rarity if material else 0,
                category=material.kind if material else "",
                # Unknown is not zero: without a Materials event the hold has
                # never been reported, and announcing "Всего: 1" for a hold of
                # hundreds is worse than saying nothing about the total.
                total=self.holdings.get(symbol, 0) if self.materials_known else None,
            )
        )
