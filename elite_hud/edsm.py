"""What EDSM knows about the system we are jumping to.

The journal says nothing about a system until we arrive, and the questions that
matter before a jump are exactly the ones it cannot answer: has anyone been here,
is there a star to scoop, is this place busy. EDSM has those, so the target is
looked up as soon as it is selected.

Two calls, both measured against the live API:

* ``GET /api-v1/system?systemName=…&showId=1&showCoordinates=1&showPrimaryStar=1``
  answers with the system, its ``primaryStar.isScoopable`` and its coordinates --
  or with an empty list, which is how EDSM says it has never heard of it.
* ``GET /api-system-v1/traffic?systemName=…`` answers with
  ``discovery: {commander, date}`` and ``traffic: {total, week, day}``.

Three honesty rules, because a wrong answer here is worse than no answer:

* **A failure is not an absence.** A timeout means we do not know, and that is
  reported as nothing rather than as "nobody has been here".
* **Absence is not proof.** EDSM holds what commanders chose to upload, so a
  system it has never heard of is reported as "no data in EDSM", not as
  "unvisited". The claim is re-checked on arrival.
* **EDSM reports no month or year of traffic** -- only day, week and total. The
  month and year the request asked for do not exist in the API, so they are not
  shown and not faked from the total.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .updater import ssl_context

log = logging.getLogger(__name__)

#: The API lives on the web host; ``api.edsm.net`` does not resolve at all.
EDSM_BASE = "https://www.edsm.net"

SYSTEM_PATH = "/api-v1/system"
TRAFFIC_PATH = "/api-system-v1/traffic"


@dataclass(frozen=True, slots=True)
class SystemFacts:
    """Everything EDSM said about one system, or nothing at all."""

    name: str
    #: False only when EDSM answered and did not know the system. A failed
    #: request never produces a SystemFacts at all.
    known: bool = False
    discoverer: str = ""
    discovered_at: str = ""
    #: None when unknown, which is not the same as False.
    scoopable: bool | None = None
    primary_star: str = ""
    traffic_day: int | None = None
    traffic_week: int | None = None
    traffic_total: int | None = None

    @property
    def has_traffic(self) -> bool:
        return any(
            value is not None
            for value in (self.traffic_day, self.traffic_week, self.traffic_total)
        )


def describe(facts: SystemFacts | None, labels, config) -> str:
    """The one line the bar shows about a system, or "" for nothing.

    Deliberately free of Qt, so it can be tested anywhere rather than only where
    a window can be created -- and the wording is worth testing: an absence in
    EDSM is not proof that nobody has been there, and the line must not say it
    is.
    """
    if facts is None or not config.enabled:
        return ""
    parts = [facts.name or "?"]
    if not facts.known:
        parts.append(labels.edsm_unknown)
        return "  ·  ".join(parts)

    if config.show_discovery:
        who = facts.discoverer or "?"
        when = f" {facts.discovered_at}" if facts.discovered_at else ""
        parts.append(f"{labels.edsm_discovered}: {who}{when}")
    if config.show_fuel_star and facts.scoopable is not None:
        answer = labels.edsm_yes if facts.scoopable else labels.edsm_no
        parts.append(f"{labels.edsm_fuel}: {answer}")
    if config.show_traffic and facts.has_traffic:
        if not facts.traffic_total:
            parts.append(f"{labels.edsm_traffic}: {labels.edsm_traffic_none}")
        else:
            parts.append(
                f"{labels.edsm_traffic}: "
                f"{labels.edsm_day} {facts.traffic_day or 0}, "
                f"{labels.edsm_week} {facts.traffic_week or 0}, "
                f"{labels.edsm_total} {facts.traffic_total or 0}"
            )
    return "  ·  ".join(parts)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _short_date(value: str) -> str:
    """EDSM's "2026-09-14 19:40:56" as "14.09.2026", or as it came."""
    parts = value.split(" ")[0].split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return value.strip()
    year, month, day = parts
    return f"{day}.{month}.{year}"


class EdsmClient:
    """The two requests, with no policy attached to them."""

    def __init__(self, *, base: str = EDSM_BASE, timeout: float = 15.0) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, name: str, **extra: str) -> object | None:
        query = urllib.parse.urlencode({"systemName": name, **extra})
        url = f"{self.base}{path}?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": "elite-hud"})
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=ssl_context()
            ) as response:
                body = response.read()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            log.info("EDSM %s lookup for %r failed: %s", path, name, exc)
            return None
        try:
            return json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            log.info("EDSM %s lookup for %r returned something that is not JSON", path, name)
            return None

    def system(self, name: str) -> dict | None:
        """The system record, or None when the request itself failed.

        An empty list is a successful answer meaning "never heard of it", which
        is why it is told apart from a failure rather than folded into it.

        ``showPrimaryStar`` is not a nicety: without it EDSM omits ``primaryStar``
        entirely, so the fuel-star answer is silently missing rather than absent.
        The other two flags cost nothing and are what makes the record complete.
        """
        payload = self._get(
            SYSTEM_PATH,
            name,
            showId="1",
            showCoordinates="1",
            showPrimaryStar="1",
        )
        if payload is None:
            return None
        if isinstance(payload, list):
            return {}
        return payload if isinstance(payload, dict) else None

    def traffic(self, name: str) -> dict | None:
        payload = self._get(TRAFFIC_PATH, name)
        return payload if isinstance(payload, dict) else None

    def lookup(self, name: str) -> SystemFacts | None:
        """Both calls, folded into one answer. None means we do not know."""
        system = self.system(name)
        if system is None:
            return None
        if not system:
            # EDSM answered, and has never heard of this system. No traffic
            # request: there is nothing to ask about.
            return SystemFacts(name=name, known=False)

        facts = SystemFacts(name=str(system.get("name") or name), known=True)
        star = system.get("primaryStar")
        if isinstance(star, dict):
            scoopable = star.get("isScoopable")
            facts = SystemFacts(
                name=facts.name,
                known=True,
                scoopable=scoopable if isinstance(scoopable, bool) else None,
                primary_star=str(star.get("type") or star.get("name") or ""),
            )

        traffic = self.traffic(name)
        if traffic is None:
            # The system is known; the traffic numbers simply did not arrive.
            return facts

        discovery = traffic.get("discovery")
        if isinstance(discovery, dict):
            facts = SystemFacts(
                name=facts.name,
                known=True,
                scoopable=facts.scoopable,
                primary_star=facts.primary_star,
                discoverer=str(discovery.get("commander") or ""),
                discovered_at=_short_date(str(discovery.get("date") or "")),
            )
        numbers = traffic.get("traffic")
        if isinstance(numbers, dict):
            facts = SystemFacts(
                name=facts.name,
                known=True,
                scoopable=facts.scoopable,
                primary_star=facts.primary_star,
                discoverer=facts.discoverer,
                discovered_at=facts.discovered_at,
                traffic_total=_as_int(numbers.get("total")),
                traffic_week=_as_int(numbers.get("week")),
                traffic_day=_as_int(numbers.get("day")),
            )
        return facts


class EdsmService:
    """Looks systems up off the UI thread, once each, and reports back.

    Deliberately the same shape as the update service: a queue in, a queue out,
    a daemon thread in between. A jump is a moment when the bar must not stall,
    and a lookup that hangs is a lookup that must not be waited for.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout: float = 15.0,
        on_event=None,
        client: EdsmClient | None = None,
    ) -> None:
        self.enabled = enabled
        self.client = client or EdsmClient(timeout=timeout)
        self.on_event = on_event
        self._pending: queue.Queue[str | None] = queue.Queue()
        #: Answers already given this session, so a route of twenty jumps asks
        #: about each system once.
        self._cache: dict[str, SystemFacts] = {}
        self._asked: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="edsm-lookup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._pending.put(None)

    def request(self, name: str, *, force: bool = False) -> None:
        """Ask about a system, unless it is already known or already asked.

        ``force`` is for the arrival check: the whole point there is to find out
        whether the answer has changed.
        """
        if not self.enabled:
            return
        name = name.strip()
        if not name:
            return
        if not force:
            if name in self._asked or name in self._cache:
                return
        self._asked.add(name)
        self._pending.put(name)

    def cached(self, name: str) -> SystemFacts | None:
        return self._cache.get(name.strip())

    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                name = self._pending.get(timeout=0.5)
            except queue.Empty:
                continue
            if name is None:
                return
            try:
                facts = self.client.lookup(name)
            except Exception:  # pragma: no cover - the client catches its own
                log.exception("EDSM lookup for %r raised", name)
                continue
            if facts is None:
                # A failure. Forgotten, not cached: the next jump may retry.
                self._asked.discard(name)
                continue
            self._cache[name] = facts
            log.info(
                "EDSM %s: %s",
                name,
                "no data" if not facts.known else (
                    f"discovered by {facts.discoverer or '?'} {facts.discovered_at}"
                ),
            )
            if self.on_event is not None:
                self.on_event(facts)
