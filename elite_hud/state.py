"""Game state derived from the Elite Dangerous journal.

``GameState.apply(event)`` is the single entry point: it mutates state and
returns the list of :class:`Alert` objects raised by that event.  Nothing here
touches the filesystem or the UI, which keeps it trivially unit-testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import jump_range, ranks
from .exobiology import Confidence, ExobiologyTable, Genus, Species

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
class BodyBio:
    """Exobiology knowledge about a single body of the current system."""

    body_id: int
    name: str
    signals: int = 0
    genus_keys: list[str] = field(default_factory=list)
    species_keys: list[str] = field(default_factory=list)

    def add_genus(self, key: str) -> None:
        if key and key not in self.genus_keys:
            self.genus_keys.append(key)

    def add_species(self, key: str) -> None:
        if key and key not in self.species_keys:
            self.species_keys.append(key)


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
    bodies: dict[int, BodyBio] = field(default_factory=dict)

    #: highest-confidence valuable organic found in this system
    best_confidence: Confidence = Confidence.NONE
    best_value: int = 0
    best_label: str = ""
    best_body: str = ""
    best_genus: str = ""
    best_species: str = ""

    @property
    def progress_percent(self) -> float:
        if self.fss_all_found:
            return 100.0
        if self.fss_progress > 0:
            return max(0.0, min(1.0, self.fss_progress)) * 100.0
        if self.body_count > 0:
            return max(0.0, min(1.0, self.scanned_bodies / self.body_count)) * 100.0
        return 0.0

    @property
    def bio_signal_total(self) -> int:
        return sum(b.signals for b in self.bodies.values())

    @property
    def bio_body_count(self) -> int:
        return sum(1 for b in self.bodies.values() if b.signals > 0)

    def clear(self) -> None:
        self.name = ""
        self.address = 0
        self.body_count = 0
        self.non_body_count = 0
        self.fss_progress = 0.0
        self.fss_all_found = False
        self.scanned_bodies = 0
        self.scanned_ids.clear()
        self.bodies.clear()
        self.best_confidence = Confidence.NONE
        self.best_value = 0
        self.best_label = ""
        self.best_body = ""
        self.best_genus = ""
        self.best_species = ""



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
class Announcement:
    """Something worth telling the commander about, beyond a bio alert."""

    #: "rank" | "footfall" | "docking" | "material"
    kind: str
    title: str
    detail: str = ""
    #: optional numeric payload, e.g. the new rank index
    value: int = 0
    #: optional glyph name for the notification
    glyph: str = ""
    #: override colour role: "accent" | "success" | "danger" | "foreground"
    tone: str = "accent"
    at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class Alert:
    """A user-visible notification raised by a journal event."""

    key: str
    title: str
    detail: str
    value: int
    confidence: Confidence
    system: str
    body: str
    genus: str = ""
    species: str = ""
    body_id: int = 0
    at: datetime = field(default_factory=utcnow)
    #: ``ScanOrganic.WasLogged`` was False, so the base+4x bonus applies
    bonus_applies: bool = False
    #: expected payout once the bonus is taken into account (0 = unknown)
    payout: int = 0


# ---------------------------------------------------------------------------
# main state machine
# ---------------------------------------------------------------------------

#: `CarrierJumpRequest` in current builds carries `DepartureTime`; older builds
#: only carried the request, and the carrier then spools up for this long.

#: Selling a species that was never logged in this galactic region pays
#: base + 4x base, i.e. five times the base value.
FIRST_LOGGED_MULTIPLIER = 5

_JOURNAL_BIOLOGY_CATEGORY = "$Codex_Category_Biology;"

# Events the HUD deliberately ignores: FSSSignalDiscovered (other signal types),
# SAAScanComplete, NavBeaconScan, SellExplorationData, Materials, Rank, ... .
# Any event without a matching ``_on_<Name>`` method is simply skipped.


class GameState:
    def __init__(
        self,
        exobiology: ExobiologyTable,
        *,
        value_threshold: int = 7_000_000,
        carrier_spool_seconds: float = DEFAULT_CARRIER_SPOOL_SECONDS,
        carrier_cooldown_seconds: float = DEFAULT_CARRIER_COOLDOWN_SECONDS,
        carrier_jump_seconds: float = DEFAULT_CARRIER_JUMP_SECONDS,
        carrier_cancel_seconds: float = DEFAULT_CARRIER_CANCEL_SECONDS,
        carrier_ready_display_seconds: float = CARRIER_READY_DISPLAY_SECONDS,
    ) -> None:
        self.exobiology = exobiology
        self.value_threshold = value_threshold
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

        self.last_event: str = ""
        self.last_event_at: datetime | None = None
        self.events_seen = 0

        #: "Open" | "Solo" | "Group", as loaded and as changed in session.
        self.game_mode: str = ""
        #: Private group name, when the mode is Group.
        self.group_name: str = ""

        #: Rank index per track, e.g. {"Combat": 3}.
        self.ranks: dict[str, int] = {}
        #: Percent towards the next step of each track, 0-100.
        self.rank_progress: dict[str, int] = {}

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
        self.announcements: list[Announcement] = []

        #: (system_address, body_id, organic key) -> best confidence alerted so far
        self._alerted: dict[tuple[int, int, str], Confidence] = {}

    # -- public API --------------------------------------------------------

    def apply(self, event: dict) -> list[Alert]:
        """Fold one journal event into the state; return any new alerts."""
        name = event.get("event")
        if not isinstance(name, str):
            return []
        self.events_seen += 1
        self.last_event = name
        self.last_event_at = parse_timestamp(event.get("timestamp")) or utcnow()

        handler = getattr(self, f"_on_{name}", None)
        if handler is None:
            return []
        try:
            alerts = handler(event) or []
        except Exception:
            log.exception("failed to process %s", name)
            return []
        return alerts

    def drain_announcements(self) -> list[Announcement]:
        """Hand over the announcements queued since the last call."""
        pending, self.announcements = self.announcements, []
        return pending

    def reset(self) -> None:
        self.system.clear()
        self.carrier = CarrierState(ready_display_seconds=self.carrier.ready_display_seconds)

    def settle(self, now: datetime | None = None) -> None:
        """Advance state that depends on the clock; call from the UI loop."""
        self.carrier.settle(now)

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

    def _on_Rank(self, event: dict) -> None:
        for track in ranks.TRACKS:
            value = event.get(track)
            if isinstance(value, int):
                self.ranks[track] = value

    def _on_Promotion(self, event: dict) -> None:
        """Fires when a rank is gained; the fields name the tracks that moved."""
        for track in ranks.ANNOUNCED:
            value = event.get(track)
            if not isinstance(value, int):
                continue
            # The field carries the NEW index, so it is also the freshest source
            # for the rank itself -- Rank is only written at startup.
            previous = self.ranks.get(track)
            self.ranks[track] = value
            self.rank_progress[track] = 0
            if previous == value:
                continue
            index = value
            ladder = ranks.ladder(track)
            title = ladder.name(index) if ladder else str(index)
            self.announcements.append(
                Announcement(
                    kind="rank",
                    title=title,
                    detail=track,
                    value=index,
                    glyph="star",
                    tone="success",
                )
            )

    def _on_Progress(self, event: dict) -> None:
        for track in ranks.TRACKS:
            value = event.get(track)
            if isinstance(value, int):
                self.rank_progress[track] = value

    def _on_Commander(self, event: dict) -> None:
        self.commander = str(event.get("Name") or self.commander)

    def _on_Loadout(self, event: dict) -> None:
        ship = event.get("Ship_Localised") or event.get("Ship")
        if ship:
            self.ship = str(ship)
            self.ship_type = str(ship)
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
        count = event.get("Count")
        if isinstance(count, int):
            self.cargo_count = count
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

    def _close_mission(self, event: dict) -> None:
        self.missions_known = True
        mission_id = event.get("MissionID")
        if isinstance(mission_id, int):
            self.active_missions.discard(mission_id)

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
        # Alerts are scoped per system; drop the previous system's history.
        self._alerted = {k: v for k, v in self._alerted.items() if k[0] == address}

    def _on_FSDJump(self, event: dict) -> None:
        self._enter_system(str(event.get("StarSystem") or ""), int(event.get("SystemAddress") or 0))
        level = event.get("FuelLevel")
        if isinstance(level, (int, float)):
            self.fuel_level = float(level)
            self._recompute_jump_range()

    def _on_Location(self, event: dict) -> None:
        self._enter_system(str(event.get("StarSystem") or ""), int(event.get("SystemAddress") or 0))

    def _on_CarrierJump(self, event: dict) -> list[Alert] | None:
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

    # -- body signals ------------------------------------------------------

    @staticmethod
    def _bio_count(signals: object) -> int:
        if not isinstance(signals, list):
            return 0
        total = 0
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            kind = str(signal.get("Type") or "")
            if "Biological" not in kind:
                continue
            count = signal.get("Count")
            total += int(count) if isinstance(count, int) else 1
        return total

    def _body(self, body_id: int, name: str) -> BodyBio:
        entry = self.system.bodies.get(body_id)
        if entry is None:
            entry = BodyBio(body_id=body_id, name=name)
            self.system.bodies[body_id] = entry
        elif name and not entry.name:
            entry.name = name
        return entry

    def _on_FSSBodySignals(self, event: dict) -> list[Alert] | None:
        return self._record_signals(event)

    def _on_SAASignalsFound(self, event: dict) -> list[Alert] | None:
        return self._record_signals(event, with_genuses=True)

    def _record_signals(self, event: dict, *, with_genuses: bool = False) -> list[Alert]:
        # Signal events carry SystemAddress; stale ones from a system we have
        # already left must not pollute the current scan.
        address = int(event.get("SystemAddress") or 0)
        if self.system.address and address and address != self.system.address:
            return None
        body_id = event.get("BodyID")
        if not isinstance(body_id, int):
            return None
        body = self._body(body_id, str(event.get("BodyName") or ""))

        count = self._bio_count(event.get("Signals"))
        if count > body.signals:
            body.signals = count

        alerts: list[Alert] = []
        if not with_genuses:
            return None

        genuses = event.get("Genuses")
        if isinstance(genuses, list):
            for raw in genuses:
                if not isinstance(raw, dict):
                    continue
                key = raw.get("Genus") or raw.get("Genus_Localised") or ""
                genus = self.exobiology.genus(str(key))
                if genus is None:
                    log.debug("unknown genus %r", key)
                    continue
                if not genus.sellable:
                    continue
                body.add_genus(genus.key)
                alerts.extend(self._assess_genus(body, genus))

        self._recompute_best()
        return alerts or None

    # -- scans -------------------------------------------------------------

    def _on_Scan(self, event: dict) -> None:
        address = int(event.get("SystemAddress") or 0)
        if self.system.address and address and address != self.system.address:
            return
        body_id = event.get("BodyID")
        if not isinstance(body_id, int):
            return
        body = self._body(body_id, str(event.get("BodyName") or ""))
        # Rings and belt clusters are not bodies and must not inflate the count.
        name = body.name
        if "Belt Cluster" in name or name.endswith("Ring"):
            return
        if body_id in self.system.scanned_ids:
            return
        self.system.scanned_ids.add(body_id)
        self.system.scanned_bodies += 1

    # -- organics ----------------------------------------------------------

    def _on_ScanOrganic(self, event: dict) -> list[Alert]:
        body_id = event.get("Body")
        species = self.exobiology.species(
            event.get("Species") or event.get("Species_Localised")
        )
        genus = self.exobiology.genus(event.get("Genus") or event.get("Genus_Localised"))
        if genus is None and species is not None:
            genus = self.exobiology.genus(species.name.split(" ")[0])

        body: BodyBio | None = None
        if isinstance(body_id, int):
            body = self._body(body_id, "")
            if genus is not None:
                body.add_genus(genus.key)
            if species is not None:
                body.add_species(species.key)

        if species is None:
            return []

        # `WasLogged` is the only direct signal about the base+4x bonus.
        was_logged = event.get("WasLogged")
        bonus = was_logged is False

        confidence = self.exobiology.assess_species(species, self.value_threshold)
        alerts: list[Alert] = []
        if confidence is not Confidence.NONE and body is not None:
            alerts = self._raise(body, species.key, confidence, species, genus, bonus=bonus)

        self._recompute_best()
        return alerts

    def _on_CodexEntry(self, event: dict) -> list[Alert]:
        category = str(event.get("Category") or "")
        if category and category != _JOURNAL_BIOLOGY_CATEGORY:
            return []
        # Codex entries can arrive for a system we have already left.
        address = int(event.get("SystemAddress") or 0)
        if self.system.address and address and address != self.system.address:
            return []
        species = self.exobiology.species(
            event.get("Name") or event.get("Name_Localised")
        )
        if species is None:
            return []

        body_id = event.get("BodyID")
        body: BodyBio | None = None
        if isinstance(body_id, int):
            body = self._body(body_id, "")
            body.add_species(species.key)
            genus = self.exobiology.genus(species.name.split(" ")[0])
            if genus is not None:
                body.add_genus(genus.key)

        confidence = self.exobiology.assess_species(species, self.value_threshold)
        alerts = self._raise(body, species.key, confidence, species, None) if confidence is not Confidence.NONE else []
        self._recompute_best()
        return alerts

    # -- assessment helpers ------------------------------------------------

    def _assess_genus(self, body: BodyBio, genus: Genus) -> list[Alert]:
        confidence = self.exobiology.assess_genus(genus, self.value_threshold)
        if confidence is Confidence.NONE:
            return []
        return self._raise(body, genus.key, confidence, None, genus)

    def _raise(
        self,
        body: BodyBio,
        organic_key: str,
        confidence: Confidence,
        species: Species | None,
        genus: Genus | None,
        *,
        bonus: bool = False,
    ) -> list[Alert]:
        dedupe = (self.system.address, body.body_id, organic_key)
        previous = self._alerted.get(dedupe, Confidence.NONE)
        if confidence.rank <= previous.rank:
            return []
        self._alerted[dedupe] = confidence

        if species is not None:
            value = species.value
            label = species.name
        else:
            value = genus.max_value if genus else 0
            label = genus.name if genus else organic_key

        return [
            Alert(
                key=f"{self.system.address}:{body.body_id}:{organic_key}",
                title=label,
                detail=confidence.value,
                value=value,
                confidence=confidence,
                system=self.system.name,
                body=body.name,
                genus=genus.name if genus else "",
                species=species.name if species else "",
                body_id=body.body_id,
                bonus_applies=bonus,
                payout=value * FIRST_LOGGED_MULTIPLIER if bonus else value,
            )
        ]

    def _recompute_best(self) -> None:
        best_confidence = Confidence.NONE
        best_value = 0
        best_label = ""
        best_body = ""
        best_genus = ""
        best_species = ""

        for body in self.system.bodies.values():
            for key in body.species_keys:
                species = self.exobiology.species(key)
                if species is None:
                    continue
                confidence = self.exobiology.assess_species(species, self.value_threshold)
                if confidence is Confidence.NONE:
                    continue
                if (confidence.rank, species.value) > (best_confidence.rank, best_value):
                    best_confidence = confidence
                    best_value = species.value
                    best_label = species.name
                    best_body = body.name
                    best_species = species.name
                    best_genus = species.name.split(" ")[0]
            for key in body.genus_keys:
                genus = self.exobiology.genus(key)
                if genus is None:
                    continue
                confidence = self.exobiology.assess_genus(genus, self.value_threshold)
                if confidence is Confidence.NONE:
                    continue
                if (confidence.rank, genus.max_value) > (best_confidence.rank, best_value):
                    best_confidence = confidence
                    best_value = genus.max_value
                    best_label = genus.name
                    best_body = body.name
                    best_genus = genus.name
                    best_species = ""

        self.system.best_confidence = best_confidence
        self.system.best_value = best_value
        self.system.best_label = best_label
        self.system.best_body = best_body
        self.system.best_genus = best_genus
        self.system.best_species = best_species

    # -- fleet carrier -----------------------------------------------------

    def _on_CarrierStats(self, event: dict) -> None:
        self.carrier.carrier_id = int(event.get("CarrierID") or self.carrier.carrier_id or 0)
        self.carrier.callsign = str(event.get("Callsign") or self.carrier.callsign)
        self.carrier.name = str(event.get("Name") or self.carrier.name)

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
