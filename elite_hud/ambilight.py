"""Ambilight: driving an ambient lamp from the game.

The lamp is a "Feelin Light Q1", controlled over the local network by
``kittle1990/Feelin_Light_Q1_Python``. Its licence is CC0, so there is no
obstacle to using it -- but its source is obfuscated with PyArmor and ships a
Windows-only ``pyarmor_runtime.pyd``, so the wire protocol cannot be read out of
it and reimplemented. The one thing that is available is the API the project
documents:

    robot = feelinlight('robot')
    robot.ip_list = ['192.168.0.68']
    robot.whole_lamp_color(r, g, b)

So this module is written against exactly that, treats the library as strictly
optional, and keeps every decision about *what* to show in a pure-Python layer
that can be tested without any hardware. If the library is absent, or the lamp
is unreachable, the HUD carries on as though nothing were configured: the light
is decoration, and decoration must never be able to break the overlay.

What drives it, in priority order:

* being interdicted -- a strobe, because it is the one that needs an immediate
  reaction
* in danger -- a steady glow, which covers being shot at and fighting
* charging the FSD -- a slow blue pulse
* a change in the credit balance -- two green flashes
* otherwise off

The first three come from Status.json flags, which are the only real-time source
for them: the journal reports the *start* of a jump charge and the *end* of an
interdiction, but not the states in between, and the flags cover exactly the
window that matters.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

Colour = tuple[int, int, int]

#: Nothing lit. A lamp given this is switched off, not merely dimmed.
OFF: Colour = (0, 0, 0)

#: Status.json flag bits, verified against the reference flag table rather than
#: recalled: FSD_CHARGING is bit 17, DANGER 22, INTERDICTED 23.
FLAG_HARDPOINTS = 1 << 6
FLAG_SHIELDS_UP = 1 << 3
FLAG_FSD_CHARGING = 1 << 17
FLAG_IN_DANGER = 1 << 22
FLAG_INTERDICTED = 1 << 23
FLAG_FSD_JUMP = 1 << 30


def scale(colour: Colour, factor: float) -> Colour:
    """Dim a colour by a 0..1 factor, keeping it a valid RGB triple."""
    factor = max(0.0, min(1.0, factor))
    return tuple(max(0, min(255, int(round(channel * factor)))) for channel in colour)  # type: ignore[return-value]


@dataclass(slots=True)
class Situation:
    """What the game is doing, as far as the light is concerned."""

    charging: bool = False
    interdicted: bool = False
    in_danger: bool = False
    hardpoints: bool = False

    @classmethod
    def from_flags(cls, flags: int) -> "Situation":
        return cls(
            charging=bool(flags & FLAG_FSD_CHARGING) or bool(flags & FLAG_FSD_JUMP),
            interdicted=bool(flags & FLAG_INTERDICTED),
            in_danger=bool(flags & FLAG_IN_DANGER),
            hardpoints=bool(flags & FLAG_HARDPOINTS),
        )

    @property
    def idle(self) -> bool:
        return not (self.charging or self.interdicted or self.in_danger)


@dataclass(slots=True)
class Flash:
    """A short pattern that plays once and then gives way."""

    colour: Colour
    times: int
    on: float
    off: float
    started: float

    @property
    def duration(self) -> float:
        return self.times * (self.on + self.off)

    def colour_at(self, now: float) -> Colour | None:
        """The colour right now, or None once the pattern has finished."""
        elapsed = now - self.started
        if elapsed < 0 or elapsed >= self.duration:
            return None
        cycle = elapsed % (self.on + self.off)
        return self.colour if cycle < self.on else OFF


@dataclass(slots=True)
class AmbilightShow:
    """Turns the game situation into a colour, with no hardware involved.

    Everything here is a pure function of the time and the situation, which is
    what makes the patterns testable: the timing is expressed in seconds and the
    tests drive a clock by hand.
    """

    #: Slow breathing while the FSD spools up. Pure blue, which is also the
    #: colour the vendor's own example uses for the whole ring.
    charge_colour: Colour = (0, 0, 255)
    charge_period: float = 1.4
    #: Fast on/off while being interdicted.
    interdiction_colour: Colour = (255, 0, 0)
    interdiction_period: float = 0.5
    interdiction_duty: float = 0.5
    #: Steady red under attack.
    danger_colour: Colour = (255, 0, 0)
    danger_level: float = 0.55
    #: Two green flashes when the balance changes.
    balance_colour: Colour = (0, 255, 0)
    balance_flashes: int = 2
    balance_on: float = 0.16
    balance_off: float = 0.16
    #: Overall dimming.
    brightness: float = 1.0

    _flash: Flash | None = field(default=None, init=False, repr=False)

    # -- input -------------------------------------------------------------

    def flash_balance(self, now: float) -> None:
        """Queue the two green flashes.

        Replaced rather than queued when one is already playing: a burst of
        balance changes -- selling a hold in several transactions -- would
        otherwise leave the light strobing green for a long time after the fact.
        """
        self._flash = Flash(
            colour=self.balance_colour,
            times=max(1, self.balance_flashes),
            on=self.balance_on,
            off=self.balance_off,
            started=now,
        )

    # -- output ------------------------------------------------------------

    def frame(self, now: float, situation: Situation) -> Colour:
        """The colour to show at ``now``."""
        if situation.interdicted:
            # The strobe outranks everything, and cancels a pending flash so it
            # cannot reappear once the interdiction is over.
            self._flash = None
            cycle = (now % self.interdiction_period) / self.interdiction_period
            lit = cycle < self.interdiction_duty
            return scale(self.interdiction_colour, self.brightness) if lit else OFF

        if situation.in_danger:
            self._flash = None
            return scale(self.danger_colour, self.brightness * self.danger_level)

        if situation.charging:
            self._flash = None
            # A cosine pulse from off to full and back, which reads as breathing
            # rather than as a blink.
            phase = (now % self.charge_period) / self.charge_period
            level = (1.0 - math.cos(2 * math.pi * phase)) / 2.0
            return scale(self.charge_colour, self.brightness * level)

        if self._flash is not None:
            colour = self._flash.colour_at(now)
            if colour is not None:
                return scale(colour, self.brightness)
            self._flash = None

        return OFF


class LightDriver:
    """Sends colours somewhere. The base class does nothing at all."""

    def apply(self, colour: Colour) -> None:  # pragma: no cover - trivial
        return None

    def close(self) -> None:  # pragma: no cover - trivial
        return None


class NullDriver(LightDriver):
    """Used when the lamp is off, absent, or unreachable."""


class FeelinLightDriver(LightDriver):
    """Drives the lamp through the vendor's own library.

    The library is imported lazily so that a commander without the hardware, or
    without its dependencies installed, pays nothing for this module existing.
    Failures are counted rather than raised: a lamp that has been unplugged
    should cost one log line, not the overlay.
    """

    #: Consecutive failures before giving up entirely.
    FAILURE_LIMIT = 5

    def __init__(self, ips: list[str], *, discover_seconds: float = 0.0) -> None:
        self.ips = [ip for ip in ips if ip]
        self.available = False
        self.failures = 0
        self._robot = None
        self._lock = threading.Lock()
        self._connect(discover_seconds)

    def _connect(self, discover_seconds: float) -> None:
        try:
            from FeelinLight import feelinlight  # type: ignore[import-not-found]
        except Exception as exc:
            log.warning("ambilight: FeelinLight library unavailable (%s)", exc)
            return
        try:
            robot = feelinlight("robot")
            if self.ips:
                robot.ip_list = list(self.ips)
            elif discover_seconds > 0:
                # Discovery prints what it finds; whether it also fills ip_list
                # is not documented, and the source is obfuscated, so the
                # configured addresses remain the reliable route.
                robot.find_devices(discover_seconds)
            self._robot = robot
            self.available = True
            log.info("ambilight: lamp ready (%s)", ", ".join(self.ips) or "discovered")
        except Exception:
            log.exception("ambilight: could not initialise the lamp")

    def apply(self, colour: Colour) -> None:
        if not self.available or self._robot is None:
            return
        with self._lock:
            try:
                self._robot.whole_lamp_color(*colour)
                self.failures = 0
            except Exception as exc:
                self.failures += 1
                if self.failures >= self.FAILURE_LIMIT:
                    self.available = False
                    log.warning(
                        "ambilight: lamp stopped responding after %d tries (%s); "
                        "switching it off for this session",
                        self.failures,
                        exc,
                    )
                else:
                    log.debug("ambilight: send failed (%s)", exc)

    def close(self) -> None:
        self.apply(OFF)


class AmbilightService:
    """Feeds the show to the lamp from a thread of its own.

    On a thread because every frame is a network request, and the HUD's tick
    must not wait for a lamp. Frames are only sent when the colour actually
    changes, which for a steady glow means one request rather than twenty a
    second.
    """

    def __init__(
        self,
        show: AmbilightShow,
        driver: LightDriver,
        *,
        fps: float = 20.0,
        clock=time.monotonic,
    ) -> None:
        self.show = show
        self.driver = driver
        self.interval = 1.0 / max(1.0, fps)
        self._clock = clock
        self._lock = threading.Lock()
        self._situation = Situation()
        self._pending_flashes = 0
        self._last: Colour | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- input from the HUD thread -----------------------------------------

    def set_situation(self, situation: Situation) -> None:
        with self._lock:
            self._situation = situation

    def flash_balance(self) -> None:
        """Ask for the green flashes; the worker stamps them with its own time."""
        with self._lock:
            self._pending_flashes += 1

    # -- worker ------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="ambilight", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        self.driver.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._step()
            self._stop.wait(self.interval)

    def _step(self) -> None:
        now = self._clock()
        with self._lock:
            situation = self._situation
            flashes, self._pending_flashes = self._pending_flashes, 0
        for _ in range(flashes):
            self.show.flash_balance(now)

        try:
            colour = self.show.frame(now, situation)
        except Exception:
            # A bug in the show must not take the worker down with it.
            log.exception("ambilight: frame failed")
            return
        if colour == self._last:
            return
        try:
            self.driver.apply(colour)
        except Exception:
            # The worker must outlive anything the driver does. An exception
            # here would otherwise kill this thread silently and the lamp would
            # stop responding for the rest of the session with nothing in the
            # log to say why.
            log.exception("ambilight: driver failed to apply %s", colour)
            return
        # Recorded only after a successful send, so a colour that failed to
        # reach the lamp is tried again on the next frame rather than being
        # remembered as sent. FeelinLightDriver disables itself after a few
        # failures, so a lamp that has gone away is not retried forever.
        self._last = colour
