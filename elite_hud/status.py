"""Reading ``Status.json``.

The journal is a log: it reports things that happened. Some values the HUD wants
are not events at all -- the credit balance is the clearest case, since nothing
in the journal announces it changing. They live in ``Status.json``, which the
game rewrites continuously while running.

Two things make this file awkward, and both are handled here.

It is written **non-atomically and often**, so a read can land mid-write and find
truncated JSON. That is expected rather than exceptional: the next poll a few
hundred milliseconds later succeeds, so a parse failure returns ``None`` instead
of raising.

The game **truncates it on exit**. A copy taken after quitting holds only
``{"Flags": 0}`` and no other field at all, which is exactly what the journals
this project was built against contain -- so a reader that trusts the file to
have a balance would work in play and appear broken on any saved copy. Every
field is therefore optional.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

FILENAME = "Status.json"

#: Status flags. Only the ones this project acts on are named.
FLAG_DOCKED = 1 << 0
FLAG_LANDED = 1 << 1
FLAG_SHIELDS_UP = 1 << 3
FLAG_SUPERCRUISE = 1 << 4
FLAG_JUMPING = 1 << 30


@dataclass(slots=True)
class StatusSnapshot:
    """Whatever the status file happened to say. Every field is optional."""

    #: Credit balance, as the game reports it.
    balance: int | None = None
    #: "Clean", "Illegal", "Wanted", ... Depends on the local jurisdiction.
    legal_state: str = ""
    flags: int = 0
    fuel_main: float | None = None
    cargo: float | None = None
    destination: str = ""
    body: str = ""
    at: datetime | None = None

    @property
    def docked(self) -> bool:
        return bool(self.flags & FLAG_DOCKED)

    @property
    def landed(self) -> bool:
        return bool(self.flags & FLAG_LANDED)

    @property
    def wanted(self) -> bool:
        return self.legal_state.casefold() in ("wanted", "illegal")

    @property
    def empty(self) -> bool:
        """True for the post-exit stub, which carries nothing useful."""
        return (
            self.balance is None
            and not self.legal_state
            and not self.destination
            and not self.body
            and self.flags == 0
        )


def _as_int(value) -> int | None:
    # bool is an int subclass, and the game does not send booleans here.
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _as_float(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def read_status(path: Path) -> StatusSnapshot | None:
    """Parse a status file, or return ``None`` if it is mid-write.

    ``None`` deliberately covers both "not there" and "not readable yet",
    because the caller treats them the same way: keep the previous value and try
    again on the next tick. Returning a snapshot with everything empty instead
    would let a half-written file erase a good balance.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        log.debug("cannot read status file %s: %s", path, exc)
        return None
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.debug("status file mid-write (%s); will retry", exc)
        return None
    if not isinstance(data, dict):
        return None
    return parse_status(data)


def parse_status(data: dict) -> StatusSnapshot:
    """Build a snapshot from an already-parsed status object."""
    snapshot = StatusSnapshot()
    snapshot.balance = _as_int(data.get("Balance"))
    snapshot.legal_state = str(data.get("LegalState") or "")

    flags = _as_int(data.get("Flags"))
    if flags is not None:
        snapshot.flags = flags

    fuel = data.get("Fuel")
    if isinstance(fuel, dict):
        snapshot.fuel_main = _as_float(fuel.get("FuelMain"))
    snapshot.cargo = _as_float(data.get("Cargo"))

    destination = data.get("Destination")
    if isinstance(destination, dict):
        # A route destination may carry only a name, only a system, or both.
        snapshot.destination = str(
            destination.get("Name") or destination.get("System") or ""
        )
    snapshot.body = str(data.get("BodyName") or data.get("Body") or "")

    stamp = data.get("timestamp")
    if isinstance(stamp, str):
        snapshot.at = _parse_timestamp(stamp)
    return snapshot


def _parse_timestamp(text: str) -> datetime | None:
    """The status file uses the same Zulu ISO-8601 stamps as the journal."""
    try:
        cleaned = text.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class StatusReader:
    """Polls the status file and hands over snapshots that actually changed.

    The file is rewritten several times a second, so it is compared by
    modification time before being read: parsing it on every tick would waste
    work inside a running game, which is the one place this project does not
    want to be wasteful.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._mtime: float | None = None
        self._last: StatusSnapshot | None = None

    @classmethod
    def beside(cls, journal_dir: Path) -> "StatusReader":
        return cls(Path(journal_dir) / FILENAME)

    def poll(self) -> StatusSnapshot | None:
        """Return a new snapshot, or ``None`` when nothing has changed.

        A snapshot with nothing in it (the post-exit stub) is handed over too:
        the caller needs to know that the balance stopped being reported rather
        than keep displaying a stale number forever.
        """
        try:
            stamp = self.path.stat().st_mtime
        except OSError:
            return None
        if stamp == self._mtime:
            return None

        snapshot = read_status(self.path)
        if snapshot is None:
            # Leave the mtime alone so the next poll retries this same write.
            return None
        self._mtime = stamp
        self._last = snapshot
        return snapshot

    @property
    def last(self) -> StatusSnapshot | None:
        return self._last
