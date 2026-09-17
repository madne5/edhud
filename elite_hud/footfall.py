"""First-footfall eligibility.

Landing on a body nobody has walked on before earns the first-footfall bonus,
which multiplies every organic sold from that body by five. The journal tells us
in advance: ``Scan`` carries ``WasFootfalled``, false meaning no one has set foot
there yet.

Whether that is worth interrupting a commander about is the whole question here,
because the raw signal is far too common to announce. Across the six journals
this project tests against: 987 bodies are scanned, 371 are landable, 347 are
landable and unfootfalled -- and only 35 of those have biological signals at
all. Announcing 347 of them would be noise; announcing the 35 is the difference
between a tip and a nuisance.

One ordering detail drives the whole design. ``FSSBodySignals`` -- the event that
says a body has biology -- arrives *before* ``Scan`` in 344 of 346 cases, because
scanning a body's signals comes before resolving the body itself. So at the
moment biology becomes known, nothing is yet known about landing; and at the
moment landing becomes known, the biology is remembered from earlier. The
decision therefore has to be taken on ``Scan``, recalling what the signal events
already said. Checking at signal time would never fire.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Journal signal types that mean "there is biology down there".
BIOLOGICAL_SIGNAL = "$SAA_SignalType_Biological;"
#: The readable form Spansh uses in search results, where signals are reported
#: as ``{"count": 1, "name": "Biological"}`` rather than by symbol.
BIOLOGICAL_ALIASES = ("Biological",)


def is_biological(signal_type: str) -> bool:
    """True for the journal's biological signal symbol or a readable alias.

    Matching on the symbol matters: the journal carries both, and a commander
    running a Russian client sees a localised string that no search for
    "Biological" would ever find.
    """
    text = (signal_type or "").strip()
    if not text:
        return False
    if text.casefold() == BIOLOGICAL_SIGNAL.casefold():
        return True
    return text in BIOLOGICAL_ALIASES


@dataclass(slots=True)
class FootfallPolicy:
    """What counts as worth telling the commander about."""

    #: Report nothing at all.
    enabled: bool = True
    #: Only bodies that actually have biology. This is the filter that turns
    #: 347 candidates into 35; without it the HUD would be unusable.
    require_biology: bool = True
    #: Only bodies nobody has scanned before either. Stricter, and excludes
    #: bodies other commanders have already mapped.
    require_undiscovered: bool = False
    #: Minimum biological signal count on the body. Only consulted when
    #: ``require_biology`` is set; on its own it means nothing.
    min_bio_signals: int = 1

    def admits(self, body: "BodySurvey") -> bool:
        """Whether this body should be announced, given what is known now."""
        if not self.enabled:
            return False
        if body.footfalled is not False:
            # Unknown counts as "not eligible": announcing a body someone else
            # has already walked on would be wrong, and there is no second
            # chance to un-say it.
            return False
        if not body.landable:
            return False
        if body.announced:
            return False
        if self.require_undiscovered and body.discovered is not False:
            return False
        if self.require_biology and body.bio_signals < max(1, self.min_bio_signals):
            return False
        return True


@dataclass(slots=True)
class BodySurvey:
    """What is known about one body, accumulated as its events arrive."""

    body_id: int
    name: str = ""
    system: str = ""
    #: ``None`` means the journal has not said yet.
    landable: bool | None = None
    footfalled: bool | None = None
    discovered: bool | None = None
    planet_class: str = ""
    #: Highest biological signal count reported for this body.
    bio_signals: int = 0
    #: Genuses, as symbols, from the DSS.
    genuses: tuple[str, ...] = ()
    #: Set once the commander has been told, so it is said exactly once.
    announced: bool = False

    def describe(self) -> str:
        """Short suffix for the notification, e.g. "био: 6"."""
        parts: list[str] = []
        if self.planet_class:
            parts.append(self.planet_class)
        if self.bio_signals:
            parts.append(f"bio: {self.bio_signals}")
        return " · ".join(parts)

    def observe_scan(self, event: dict) -> None:
        """Fold in a ``Scan`` event."""
        landable = event.get("Landable")
        if isinstance(landable, bool):
            self.landable = landable
        footfalled = event.get("WasFootfalled")
        if isinstance(footfalled, bool):
            self.footfalled = footfalled
        discovered = event.get("WasDiscovered")
        if isinstance(discovered, bool):
            self.discovered = discovered
        planet_class = event.get("PlanetClass_Localised") or event.get("PlanetClass")
        if planet_class:
            self.planet_class = str(planet_class)

    def observe_signals(self, signals, *, genuses=()) -> None:
        """Fold in the biological part of an ``FSSBodySignals``/``SAASignalsFound``."""
        if isinstance(signals, list):
            for raw in signals:
                if not isinstance(raw, dict):
                    continue
                if not is_biological(str(raw.get("Type") or "")):
                    continue
                count = raw.get("Count")
                self.bio_signals = max(self.bio_signals, int(count or 0))
        keys = tuple(
            str(raw.get("Genus") or "")
            for raw in genuses
            if isinstance(raw, dict) and raw.get("Genus")
        )
        if keys:
            merged = list(self.genuses)
            for key in keys:
                if key not in merged:
                    merged.append(key)
            self.genuses = tuple(merged)
