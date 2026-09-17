"""Timed notifications for the HUD.

Everything the HUD says beyond its two standing rows -- a rank gained, a first
footfall available, a material picked up, a bio payout -- goes through here, so
they all appear and disappear the same way instead of each growing its own
timer. Three of the remaining features need this, which is why it exists before
any of them.

The centre owns time, not Qt. It is handed a clock (``time.monotonic`` by
default) and answers "what should be on screen right now, at what opacity and
offset". The window does the drawing. That keeps the timing testable without a
display and lets the window decide when it is worth starting a repaint timer:
:meth:`NotificationCenter.animating` is false once everything has settled, and
a HUD that keeps repainting at 60 Hz inside a running game is a real cost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .state import Announcement

#: Colour roles a notification may ask for; resolved to real colours by the
#: window, which owns the palette.
TONES = ("accent", "success", "danger", "foreground")

DEFAULT_HOLD = 6.0
DEFAULT_FADE_IN = 0.18
DEFAULT_FADE_OUT = 0.45
#: Entrance slides down from this many pixels above its resting place.
ENTER_SLIDE = 8.0
#: Exit drifts up by this much. Less than the entrance, so leaving is calmer.
EXIT_SLIDE = 5.0


@dataclass(slots=True)
class Notification:
    """One thing to tell the commander, with its own lifetime."""

    key: str
    title: str
    detail: str = ""
    glyph: str = ""
    tone: str = "accent"
    value: int = 0
    #: Seconds held at full opacity. ``None`` means "use the centre's
    #: default", which is how the config reaches notifications that do not
    #: care; a number here overrides it for one notification.
    hold: float | None = None
    #: How many identical notifications folded into this one, for "x3".
    count: int = 1
    #: Monotonic seconds; set by the centre on push.
    created: float = 0.0
    #: Monotonic seconds at which the fade-out begins.
    expires: float = 0.0

    @property
    def lifetime(self) -> float:
        return max(0.0, self.expires - self.created)

    def text(self) -> str:
        """Title plus detail, with a repeat count when one has accrued."""
        parts = [self.title]
        if self.detail:
            parts.append(self.detail)
        line = "  ".join(part for part in parts if part)
        if self.count > 1:
            line = f"{line}  x{self.count}"
        return line


@dataclass(slots=True)
class Rendered:
    """A notification plus the animation state the painter needs."""

    notification: Notification
    opacity: float
    #: Vertical offset in pixels; negative is above the resting position.
    offset: float

    @property
    def settled(self) -> bool:
        return self.opacity >= 1.0 and self.offset == 0.0


class NotificationCenter:
    """Holds the live notifications and decides what is visible when.

    Repeat pushes with the same key fold into the existing notification rather
    than stacking: picking up four units of the same material should read as
    one line saying "x4", not four lines fighting for the same spot.
    """

    def __init__(
        self,
        *,
        max_visible: int = 3,
        hold_seconds: float = DEFAULT_HOLD,
        fade_in: float = DEFAULT_FADE_IN,
        fade_out: float = DEFAULT_FADE_OUT,
        clock=time.monotonic,
    ) -> None:
        self.max_visible = max(1, int(max_visible))
        self.hold_seconds = max(0.0, float(hold_seconds))
        self.fade_in = max(0.0, float(fade_in))
        self.fade_out = max(0.0, float(fade_out))
        self._clock = clock
        self._items: list[Notification] = []

    # -- input -------------------------------------------------------------

    def push(self, notification: Notification) -> Notification:
        """Add a notification, folding it into a live one with the same key."""
        now = self._clock()
        notification.created = now
        hold = self.hold_seconds if notification.hold is None else float(notification.hold)
        notification.hold = max(0.0, hold)
        notification.expires = now + notification.hold
        if notification.tone not in TONES:
            notification.tone = "accent"
        if notification.count < 1:
            notification.count = 1

        existing = self._find(notification.key)
        if existing is not None:
            # Keep the original position so the line does not jump around, but
            # take the new wording and restart the clock.
            existing.title = notification.title
            existing.detail = notification.detail
            existing.glyph = notification.glyph or existing.glyph
            existing.tone = notification.tone
            existing.value = notification.value
            existing.count += notification.count
            existing.expires = notification.expires
            existing.hold = notification.hold
            self._enforce_limit()
            return existing

        self._items.append(notification)
        self._enforce_limit()
        return notification

    @staticmethod
    def key_for(kind: str, detail: str = "") -> str:
        """Identity used for folding repeats together.

        ``detail`` is part of the key on purpose. Two things of the same kind
        are not necessarily the same thing: an Empire promotion and a
        Federation promotion are both ``kind="rank"`` and must stay separate
        lines, while picking up three units of one material should fold into
        one line. The detail is what tells those cases apart.
        """
        return f"{kind}:{detail}" if detail else kind

    def announce(self, announcement: Announcement, **overrides) -> Notification:
        """Adapt a :class:`~elite_hud.state.Announcement` into a notification.

        The state layer raises announcements with no idea how long anything
        should stay on screen; the timings belong here.
        """
        fields = {
            # An announcement may name its own identity when the detail is
            # display text; otherwise kind plus detail identifies it.
            "key": announcement.key or self.key_for(announcement.kind, announcement.detail),
            "title": announcement.title,
            "detail": announcement.detail,
            "glyph": announcement.glyph,
            "tone": announcement.tone,
            "value": announcement.value,
        }
        fields.update(overrides)
        return self.push(Notification(**fields))

    def drain(self, announcements: list[Announcement]) -> list[Notification]:
        """Announce everything the state layer queued, in order."""
        return [self.announce(item) for item in announcements]

    # -- housekeeping ------------------------------------------------------

    def _find(self, key: str) -> Notification | None:
        return next((item for item in self._items if item.key == key), None)

    def _enforce_limit(self) -> None:
        """Never hold more than ``max_visible``; the soonest to expire gives way.

        Dropping by position rather than by expiry contradicted the fold: a
        repeat push keeps its original list position and restarts its clock, so
        popping index 0 destroyed the line that had just been refreshed while an
        older, already-read line stayed on screen.
        """
        while len(self._items) > self.max_visible:
            soonest = min(range(len(self._items)), key=lambda i: self._items[i].expires)
            self._items.pop(soonest)

    def tick(self) -> None:
        """Drop whatever has finished fading out."""
        now = self._clock()
        self._items = [item for item in self._items if now < item.expires + self.fade_out]

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    @property
    def items(self) -> tuple[Notification, ...]:
        return tuple(self._items)

    # -- output ------------------------------------------------------------

    def rendered(self) -> list[Rendered]:
        """What to draw now, oldest first, each with opacity and offset."""
        now = self._clock()
        out: list[Rendered] = []
        for item in self._items:
            remaining = item.expires - now
            if remaining < 0:
                # Fading out: the fade is measured from the expiry. A fully
                # faded item is skipped rather than emitted at zero opacity,
                # otherwise animating() could never report that things have
                # settled and the repaint timer would run for the whole session.
                if self.fade_out <= 0:
                    continue
                progress = 1.0 - (-remaining) / self.fade_out
                if progress <= 0.0:
                    continue
                progress = min(1.0, progress)
                out.append(
                    Rendered(item, progress, (1.0 - progress) * EXIT_SLIDE)
                )
                continue

            age = now - item.created
            if self.fade_in > 0 and age < self.fade_in:
                progress = max(0.0, age / self.fade_in)
                out.append(
                    Rendered(item, progress, -(1.0 - progress) * ENTER_SLIDE)
                )
            else:
                out.append(Rendered(item, 1.0, 0.0))
        return out

    def animating(self) -> bool:
        """True while a repaint timer is still earning its keep.

        Includes the run-up to expiry, not just the fade-in. Without that the
        timer stopped as soon as a notification had appeared, nothing was left
        to drive the fade-out, and expiring items were never evicted at all --
        ``tick`` is only reached from the animation timer, so a stale
        notification stayed in the centre for the whole session and the next
        push with the same key folded into it.
        """
        now = self._clock()
        if any(not entry.settled for entry in self.rendered()):
            return True
        # An item that has already expired is not a reason to keep repainting:
        # its fade-out is over, and the eviction that follows is a bookkeeping
        # step that rebuild() performs on the ordinary tick.
        return any(
            now < item.expires <= now + self.fade_out for item in self._items
        )

    @property
    def busy(self) -> bool:
        """True while anything is on screen at all."""
        return bool(self._items)

    def snapshot(self) -> list[str]:
        """Plain-text lines, for logs and for the tray tooltip."""
        return [entry.text() for entry in self._items]
