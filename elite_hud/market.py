"""Where to buy a commodity: asking Spansh.

The journal says what a mission wants, never where to buy it, so this is the
second half of the overlay that needs the network. The endpoint was worked out
by probing rather than from documentation, because Spansh publishes none, and
three things about it are not obvious:

* The reference system is given as ``reference_system``, not ``reference``.
  ``reference`` is accepted and echoed back but has no effect: distances stay
  measured from Sol, silently. The response's own ``reference`` object is the
  way to tell which one was actually used.
* Sort must be asked for: ``[{"distance": {"direction": "asc"}}]``. Without it
  the results are not ordered by distance, and the nearest station in the first
  page is a thousand light years away.
* **Filter shape is not consistent between fields.** ``has_large_pad`` needs the
  wrapper ``{"value": true}`` and rejects the bare form outright, while
  ``export_commodities`` needs the bare list ``[{"name": "Wine"}]`` and ignores
  the wrapped form silently -- returning the full catalogue as though no filter
  had been given. Verified by the count: a commodity nothing exports returns 0
  with the bare form and the capped 10000 with the wrapper. Getting this wrong
  produces plausible, wrong answers rather than errors, so both shapes are
  spelled out in one place here.

Commodity names differ in presentation between the journal and Spansh: a mission
carries ``$SyntheticMeat_Name;`` and Spansh calls it ``Synthetic Meat``. They
agree once case and separators are removed, and that was checked against the
whole catalogue of 411 commodities -- 411 distinct keys, no collisions, acronyms
included ("AI Relics", "CMM Composite", "H.E. Suits").
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

SEARCH_URL = "https://spansh.co.uk/api/stations/search"
#: Spansh's own commodity catalogue, keyed by the names it uses. Asking it is
#: more reliable than deriving a name from a journal symbol: "CMMComposite" does
#: not spell "CMM Composite", and the filter matches on the exact string.
CATALOGUE_URL = "https://spansh.co.uk/api/stations/field_values/market"

#: Pads, smallest first, so a requirement can be compared by index.
PAD_SIZES = ("S", "M", "L")

#: Spansh caps a search at this many records whatever is asked for.
RESULT_CAP = 10_000

USER_AGENT = "elite-hud (github.com/madne5/edhud)"


def normalise_commodity(text: str) -> str:
    """A commodity's identity, ignoring how it happens to be written.

    ``$SyntheticMeat_Name;`` and ``Synthetic Meat`` both become
    ``syntheticmeat``. Checked against Spansh's whole catalogue: no two
    commodities collide, so this is safe as a lookup key.
    """
    cleaned = str(text or "").strip()
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]
    if cleaned.endswith("_Name"):
        cleaned = cleaned[: -len("_Name")]
    return re.sub(r"[^a-z0-9]", "", cleaned.casefold())


def ssl_context() -> ssl.SSLContext:
    """A verifying context that works from a frozen build.

    PyInstaller does not ship the system certificate store, so the same helper
    the updater uses is reused here rather than repeating the failure.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # pragma: no cover - certifi is a dependency
        return ssl.create_default_context()


@dataclass(slots=True)
class Offer:
    """One station that sells what is wanted."""

    commodity: str
    system: str
    station: str
    distance: float = 0.0
    distance_to_arrival: float = 0.0
    large_pads: int = 0
    medium_pads: int = 0
    small_pads: int = 0
    supply: int = 0
    buy_price: int = 0
    updated: str = ""

    @property
    def largest_pad(self) -> str:
        if self.large_pads:
            return "L"
        if self.medium_pads:
            return "M"
        return "S" if self.small_pads else ""

    def fits(self, minimum: str) -> bool:
        """Whether this station's largest pad meets a minimum size.

        Judged from the pad counts rather than a boolean, because the API
        exposes only ``has_large_pad``: there is no equivalent for medium, and
        a medium-pad requirement has to accept large pads too.
        """
        wanted = minimum.strip().upper() if minimum else ""
        if wanted not in PAD_SIZES:
            return True
        return bool(self.largest_pad) and PAD_SIZES.index(self.largest_pad) >= PAD_SIZES.index(wanted)

    def describe(self) -> str:
        return f"{self.system} / {self.station} ({self.distance:.0f} ly)"


def parse_offers(commodity: str, payload: dict) -> list[Offer]:
    """Turn a search response into offers, ignoring anything malformed."""
    out: list[Offer] = []
    results = payload.get("results")
    if not isinstance(results, list):
        return out
    for raw in results:
        if not isinstance(raw, dict):
            continue
        system = str(raw.get("system_name") or "")
        station = str(raw.get("name") or "")
        if not system or not station:
            continue
        offer = Offer(
            commodity=commodity,
            system=system,
            station=station,
            distance=float(raw.get("distance") or 0.0),
            distance_to_arrival=float(raw.get("distance_to_arrival") or 0.0),
            large_pads=int(raw.get("large_pads") or 0),
            medium_pads=int(raw.get("medium_pads") or 0),
            small_pads=int(raw.get("small_pads") or 0),
            updated=str(raw.get("market_updated_at") or ""),
        )
        for entry in raw.get("market") or []:
            if not isinstance(entry, dict):
                continue
            if normalise_commodity(entry.get("commodity")) != normalise_commodity(commodity):
                continue
            offer.supply = int(entry.get("supply") or 0)
            offer.buy_price = int(entry.get("buy_price") or 0)
            break
        out.append(offer)
    return out


class SpanshMarket:
    """Finds stations selling a commodity, nearest first, with a short cache.

    Synchronous by design: the caller runs it off the HUD's thread. The cache
    matters because a shopping list of ten commodities would otherwise be ten
    requests every time the galaxy map opens.
    """

    #: Cache lifetime. Market data moves slowly, and the popup is opened often.
    CACHE_SECONDS = 900.0

    #: The catalogue changes only when Frontier adds a commodity.
    CATALOGUE_SECONDS = 86400.0

    def __init__(self, *, timeout: float = 20.0, clock=None) -> None:
        import time

        self.timeout = timeout
        self._clock = clock or time.monotonic
        self._cache: dict[tuple, tuple[float, list[Offer]]] = {}
        self._catalogue: dict[str, str] = {}
        self._catalogue_at = 0.0

    # -- commodity names ---------------------------------------------------

    def catalogue(self) -> dict[str, str]:
        """Normalised key -> the exact name Spansh uses, fetched once a day."""
        if self._catalogue and self._clock() - self._catalogue_at < self.CATALOGUE_SECONDS:
            return self._catalogue
        payload = self._get(CATALOGUE_URL)
        names: dict[str, str] = {}
        if isinstance(payload, dict):
            entries = payload.get("min_max")
            if isinstance(entries, dict):
                for name in entries:
                    names[normalise_commodity(name)] = str(name)
        if names:
            self._catalogue = names
            self._catalogue_at = self._clock()
            log.debug("market: catalogue of %d commodities loaded", len(names))
        return self._catalogue

    def spansh_name(self, commodity: str) -> str:
        """The exact catalogue spelling, or a best guess if it is unavailable.

        The guess is only a fallback: it gets "Synthetic Meat" right and "CMM
        Composite" wrong, which is why the catalogue is consulted first.
        """
        key = normalise_commodity(commodity)
        exact = self.catalogue().get(key)
        if exact:
            return exact
        return _spansh_name(commodity)

    def _cache_key(self, commodity: str, reference: str, minimum_pad: str, limit: int) -> tuple:
        return (normalise_commodity(commodity), reference.casefold(), minimum_pad.upper(), limit)

    def find_sellers(
        self,
        commodity: str,
        *,
        reference_system: str,
        minimum_pad: str = "L",
        limit: int = 3,
    ) -> list[Offer]:
        """The nearest stations selling ``commodity`` with a big enough pad."""
        if not commodity or not reference_system:
            return []
        key = self._cache_key(commodity, reference_system, minimum_pad, limit)
        cached = self._cache.get(key)
        if cached is not None and self._clock() - cached[0] < self.CACHE_SECONDS:
            return cached[1]

        offers = self._search(commodity, reference_system, minimum_pad, limit)
        self._cache[key] = (self._clock(), offers)
        return offers

    def _search(
        self, commodity: str, reference_system: str, minimum_pad: str, limit: int
    ) -> list[Offer]:
        # Ask for more than needed: the pad filter is applied here rather than
        # by the server, so some of what comes back will be discarded.
        request_size = max(limit * 4, 20)
        body = {
            "filters": {
                # The wrapped shape this field insists on.
                "has_market": {"value": True},
                # The bare shape this one insists on. The wrapper is ignored.
                "export_commodities": [{"name": self.spansh_name(commodity)}],
            },
            "size": request_size,
            "page": 0,
            "sort": [{"distance": {"direction": "asc"}}],
            "reference_system": reference_system,
        }
        payload = self._post(body)
        if payload is None:
            return []
        offers = [offer for offer in parse_offers(commodity, payload) if offer.fits(minimum_pad)]
        if not offers and payload.get("count"):
            log.debug(
                "market: %s has %s seller(s) but none with a %s pad near %s",
                commodity,
                payload.get("count"),
                minimum_pad,
                reference_system,
            )
        return offers[:limit]

    def _get(self, url: str) -> dict | None:
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=ssl_context()
            ) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
            log.warning("market: could not read %s (%s)", url, exc)
            return None
        return payload if isinstance(payload, dict) else None

    def _post(self, body: dict) -> dict | None:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            SEARCH_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=ssl_context()
            ) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
            # The popup is a convenience; a network problem must degrade to "no
            # data" rather than to a stack trace over the game.
            log.warning("market: search failed (%s)", exc)
            return None
        if not isinstance(payload, dict) or "results" not in payload:
            log.warning("market: unexpected response %s", str(payload)[:120])
            return None
        return payload


def _spansh_name(commodity: str) -> str:
    """The spelling Spansh expects.

    A journal symbol is turned into words so that the request is readable and
    the server's own matching works; a name already in that form is passed
    through untouched.
    """
    text = str(commodity or "").strip()
    if not text.startswith("$"):
        return text
    cleaned = text[1:]
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]
    if cleaned.endswith("_Name"):
        cleaned = cleaned[: -len("_Name")]
    # Split camel case: SyntheticMeat -> Synthetic Meat, and CMMComposite ->
    # CMM Composite. A run of capitals followed by a lower-case letter is an
    # acronym ending, not one long word.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", cleaned)
    return spaced.replace("_", " ").strip()
