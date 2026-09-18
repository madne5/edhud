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

from . import jump_range, ranks
from .exobiology import Confidence, ExobiologyTable, Genus, Species
from .carriers import CarrierBook
from .cartography import CartographyHold, is_sellable_body
from .crime import CrimeRecord
from .ships import ShipNames
from .footfall import BodySurvey, FootfallPolicy
from .materials import MaterialTable
from .unsold import UnsoldData

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
    #: Landing and biology knowledge per BodyID, for first-footfall calls.
    surveys: dict[int, "BodySurvey"] = field(default_factory=dict)

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
        self.surveys.clear()
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
    #: optional folding identity, when ``detail`` is display text rather than
    #: something that identifies the notification
    key: str = ""
    #: override colour role: "accent" | "success" | "danger" | "foreground"
    tone: str = "accent"
    at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class FactionStatus:
    """What the current system says about a faction we are following.

    The journal only carries a faction list for systems that have a population:
    across the journals this was built against, all 92 jump events without a
    faction list were systems with no population at all. So an empty list is not
    "no data yet", it is "nobody lives here", and the HUD hides the segment
    rather than showing a stale one from the previous system.
    """

    #: The name we were asked to follow, as configured.
    wanted: str = ""
    #: The system's own name for it, once matched.
    matched: str = ""
    found: bool = False
    controlling: bool = False
    #: 0.0-1.0 as the journal reports it.
    influence: float = 0.0
    #: Standing with that faction, if the journal carries it.
    reputation: float | None = None
    #: FactionState, e.g. "None", "Boom".
    state: str = ""
    system: str = ""
    #: The current system has factions at all.
    inhabited: bool = False

    @property
    def percent(self) -> int:
        return int(round(self.influence * 100))

    def matches(self, name: str, mode: str = "contains") -> bool:
        """Whether a journal faction name is the one we are following."""
        wanted = (self.wanted or "").strip().casefold()
        if not wanted:
            return False
        candidate = (name or "").strip().casefold()
        if not candidate:
            return False
        if mode == "exact":
            return candidate == wanted
        return wanted in candidate

    def clear(self) -> None:
        self.matched = ""
        self.found = False
        self.controlling = False
        self.influence = 0.0
        self.reputation = None
        self.state = ""
        self.system = ""
        self.inhabited = False


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
        footfall: FootfallPolicy | None = None,
        footfall_label: str = "Первый след",
        material_table: MaterialTable | None = None,
        material_rarity: bool = True,
        faction_name: str = "",
        faction_match: str = "contains",
        ship_names: ShipNames | None = None,
        ship_cache: Path | None = None,
        carrier_book: CarrierBook | None = None,
        carrier_cache: Path | None = None,
        material_enabled: bool = True,
        material_notify: bool = True,
        rarity_label: str = "Редкость",
        total_label: str = "Всего",
    ) -> None:
        self.exobiology = exobiology
        self.value_threshold = value_threshold
        self.footfall = footfall or FootfallPolicy()
        #: Sampled or earned but not yet banked.
        self.unsold = UnsoldData()
        #: Where the commander is heading next.
        self.jump_plan = JumpPlan()
        #: Fines owed and notoriety.
        self.crime = CrimeRecord()
        #: Exploration data carried but not yet sold.
        self.cartography = CartographyHold()
        #: Ship model names, learned from the journal (see elite_hud/ships.py).
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
        #: The faction we are following, in the current system.
        self.faction = FactionStatus(wanted=faction_name)
        self.faction_match = faction_match
        #: Live values that only Status.json reports.
        self.legal_state = ""
        #: True while the status file is the source of the balance.
        self.status_live = False
        #: Rarity and canonical names; the journal supplies localised names.
        # `is not None`, not `or`: these objects define __len__, so an empty one
        # is falsy and would be silently replaced -- which is how a CarrierBook
        # built with a cache path was discarded in favour of one without, and
        # nothing was ever written.
        self.material_table = (
            material_table if material_table is not None else MaterialTable()
        )
        #: Journal symbol (lowercase) -> how many are held.
        self.holdings: dict[str, int] = {}
        #: A Materials event has been seen, so the hold is known rather than assumed.
        self.materials_known = False
        #: Whether to mention rarity in notifications.
        self.material_rarity = material_rarity
        self.material_enabled = material_enabled
        self.material_notify = material_notify
        #: Text of the first-footfall notification; config supplies the real one.
        self.footfall_label = footfall_label
        #: Labels for the material notification; config supplies the real ones.
        self.rarity_label = rarity_label
        self.total_label = total_label
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

    # -- factions ----------------------------------------------------------

    def _apply_factions(self, event: dict) -> None:
        """Record the followed faction's standing in the system just entered."""
        status = self.faction
        status.clear()
        status.wanted = self.faction.wanted
        status.system = str(event.get("StarSystem") or "")
        if not status.wanted:
            return

        factions = event.get("Factions")
        if not isinstance(factions, list) or not factions:
            # No list means an uninhabited system, not missing data.
            return
        status.inhabited = True

        controller = ""
        system_faction = event.get("SystemFaction")
        if isinstance(system_faction, dict):
            controller = str(system_faction.get("Name") or "")

        for raw in factions:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("Name") or "")
            if not status.matches(name, self.faction_match):
                continue
            status.matched = name
            status.found = True
            status.controlling = bool(controller) and name == controller
            influence = raw.get("Influence")
            if isinstance(influence, (int, float)) and not isinstance(influence, bool):
                status.influence = float(influence)
            reputation = raw.get("MyReputation")
            if isinstance(reputation, (int, float)) and not isinstance(reputation, bool):
                status.reputation = float(reputation)
            status.state = str(raw.get("FactionState") or "")
            break

    # -- status file -------------------------------------------------------

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

    # -- materials ---------------------------------------------------------

    def _on_Materials(self, event: dict) -> None:
        """Seed the whole hold; this event reports everything at once."""
        if not self.material_enabled:
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
        if not self.material_enabled:
            return
        symbol = self.material_table.normalise(str(event.get("Name") or ""))
        if not symbol:
            return
        count = event.get("Count")
        count = int(count) if isinstance(count, int) else 1
        self.holdings[symbol] = self.holdings.get(symbol, 0) + count
        if self.material_notify:
            self._announce_material(
                symbol, count, str(event.get("Name_Localised") or "")
            )

    def _on_MaterialDiscarded(self, event: dict) -> None:
        if not self.material_enabled:
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
        holdings then stayed wrong for the rest of the session. An early test
        asserted the invented keys on both sides, so it passed against the bug.
        """
        paid = event.get("Paid")
        if isinstance(paid, dict):
            self._consume_material(paid)
        received = event.get("Received")
        if isinstance(received, dict):
            symbol = self._material_symbol(received)
            amount = self._material_amount(received)
            if symbol and amount:
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
        """Queue the pickup notification, e.g. "+1 Сера (Редкость: 1)"."""
        material = self.material_table.get(symbol)
        name = self.material_table.display_name(symbol, localised)
        rarity = material.rarity if material else 0
        title = f"+{count} {name}"
        if self.material_rarity and rarity:
            title = f"{title} ({self.rarity_label}: {rarity})"
        # Without a Materials event the hold is unknown, not empty: the journal
        # only reports the whole hold at session start, so a pickup seen after a
        # history-less start would otherwise announce "Всего: 1" for a hold of
        # hundreds. The guard existed but nothing consulted it.
        detail = ""
        if self.materials_known:
            detail = f"{self.total_label}: {self.holdings.get(symbol, 0)}"
        self.announcements.append(
            Announcement(
                kind="material",
                title=title,
                detail=detail,
                # Folded by material, not by the running total: keying on the
                # total meant two different materials with the same count
                # merged into one line claiming "x2", while repeated pickups of
                # one material never folded at all.
                key=symbol,
                value=self.holdings.get(symbol, 0),
                glyph="gem",
                tone="accent",
            )
        )

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
        # Only the ship's own hold counts; an SRV has its own.
        vessel = str(event.get("Vessel") or "Ship")
        if vessel != "Ship":
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
        self._apply_factions(event)
        level = event.get("FuelLevel")
        if isinstance(level, (int, float)):
            self.fuel_level = float(level)
            self._recompute_jump_range()

    def _on_Location(self, event: dict) -> None:
        self._enter_system(str(event.get("StarSystem") or ""), int(event.get("SystemAddress") or 0))
        self._apply_factions(event)

    def _on_CarrierJump(self, event: dict) -> list[Alert] | None:
        # A carrier ride lands the commander in a new system, so the faction
        # standing has to be re-read here too. Without this the HUD kept showing
        # the previous system's faction, influence and controlling colour until
        # something else happened to refresh it.
        self._apply_factions(event)
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

        # Biology is reported before the body itself is resolved, so this is
        # remembered rather than acted on: the landing data arrives with Scan,
        # and the call needs both.
        survey = self._survey(body_id, body.name)
        survey.observe_signals(event.get("Signals"), genuses=event.get("Genuses") or ())
        self._maybe_announce_footfall(survey)

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

        self._maybe_announce_footfall(self._survey(body_id, name), event)

        # Counted for the cartographics hold as well as for the system total:
        # this is what is carried, and only a sale empties it.
        if is_sellable_body(name):
            self.cartography.add_scan(self.system.name, body_id)

        if body_id in self.system.scanned_ids:
            return
        self.system.scanned_ids.add(body_id)
        self.system.scanned_bodies += 1

    # -- first footfall ----------------------------------------------------

    def _survey(self, body_id: int, name: str = "") -> BodySurvey:
        """The footfall record for a body of the current system."""
        survey = self.system.surveys.get(body_id)
        if survey is None:
            survey = BodySurvey(body_id=body_id, name=name, system=self.system.name)
            self.system.surveys[body_id] = survey
        elif name and not survey.name:
            survey.name = name
        return survey

    def _maybe_announce_footfall(
        self, survey: BodySurvey, scan_event: dict | None = None
    ) -> None:
        """Announce an un-walked, landable, worthwhile body -- exactly once.

        Called from both the scan and the signal paths because the two arrive in
        either order: ``FSSBodySignals`` precedes ``Scan`` for 344 of the 346
        bodies in the journals this was built against, but a DSS pass on an
        already-scanned body reports its biology afterwards.

        Queues on ``self.announcements`` rather than returning, because the
        dispatcher treats a handler's return value as bio alerts.
        """
        if scan_event is not None:
            survey.observe_scan(scan_event)
        if not self.footfall.admits(survey):
            return
        survey.announced = True
        detail = survey.name or f"#{survey.body_id}"
        suffix = survey.describe()
        if suffix:
            detail = f"{detail} · {suffix}"
        self.announcements.append(
            Announcement(
                kind="footfall",
                title=self.footfall_label,
                detail=detail,
                value=survey.bio_signals,
                glyph="leaf",
                tone="success",
            )
        )

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

        # Only the final Analyse pass puts a sample in the hold; the Log and
        # Sample passes are the earlier steps of the same sampling.
        if event.get("ScanType") == "Analyse":
            self.unsold.add_sample(
                species.name, species.value, first_logged=bonus
            )

        confidence = self.exobiology.assess_species(species, self.value_threshold)
        alerts: list[Alert] = []
        if confidence is not Confidence.NONE and body is not None:
            alerts = self._raise(body, species.key, confidence, species, genus, bonus=bonus)

        self._recompute_best()
        return alerts

    # -- unsold value ------------------------------------------------------

    def _on_SAAScanComplete(self, event: dict) -> None:
        """A surface scan; mapped bodies are worth more, so they are tracked."""
        body_id = event.get("BodyID")
        if isinstance(body_id, int):
            self.cartography.add_mapping(self.system.name, body_id)

    def _on_MultiSellExplorationData(self, event: dict) -> None:
        """Selling at Universal Cartographics empties the whole hold."""
        self.cartography.clear()

    def _on_SellExplorationData(self, event: dict) -> None:
        # The single-system form of the same sale.
        self.cartography.clear()

    def _on_SellOrganicData(self, event: dict) -> None:
        """A sale empties the biological hold."""
        data = event.get("BioData")
        credits = 0
        count = 0
        if isinstance(data, list):
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                credits += int(raw.get("Value") or 0) + int(raw.get("Bonus") or 0)
                count += 1
        self.unsold.clear_bio(credits=credits, samples=count)
        log.info("sold %d organic samples for %s cr", count, f"{credits:,}")

    def _on_Bounty(self, event: dict) -> None:
        # Read Reward directly rather than with `or`: a zero reward is
        # meaningful here, and `or` would discard it as falsy.
        reward = event.get("Reward")
        if reward is None:
            reward = event.get("TotalReward")
        if not isinstance(reward, int) or isinstance(reward, bool):
            return
        if reward <= 0:
            # A zero reward is not a payout: it is a bounty issued against the
            # commander, which the journal reports through the same event.
            self.crime.add_bounty(0)
            return
        self.unsold.add_voucher("bounty", reward)

    def _on_FactionKillBond(self, event: dict) -> None:
        reward = event.get("Reward")
        if isinstance(reward, int):
            self.unsold.add_voucher("bond", reward)

    def _on_RedeemVoucher(self, event: dict) -> None:
        amount = event.get("Amount")
        self.unsold.redeem(
            str(event.get("Type") or ""), amount if isinstance(amount, int) else 0
        )

    def _on_Died(self, event: dict) -> None:
        """Dying loses unsold samples and vouchers; say so rather than hide it."""
        lost = self.unsold.bio_credits + self.unsold.voucher_total
        if lost:
            log.info("died holding %s cr of unsold data", f"{lost:,}")
        self.unsold.clear_bio()
        self.unsold.vouchers.clear()

    def _on_CodexEntry(self, event: dict) -> list[Alert]:
        category = str(event.get("Category") or "")
        if category and category != _JOURNAL_BIOLOGY_CATEGORY:
            return []
        # Codex entries can arrive for a system we have already left.
        address = int(event.get("SystemAddress") or 0)
        if self.system.address and address and address != self.system.address:
            return []
        # Both spellings are tried in turn rather than with `or`: the localised
        # name is a usable fallback when the symbol is one this table cannot
        # resolve, and `or` never reached it while Name was present.
        species = self.exobiology.species(event.get("Name"))
        if species is None:
            species = self.exobiology.species(event.get("Name_Localised"))
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
