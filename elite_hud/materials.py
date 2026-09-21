"""Ship engineering materials: names, rarity and holdings.

The journal supplies the name in the client's own language -- ``Name_Localised``
is present on every ``MaterialCollected`` and on every entry of a ``Materials``
event, so a Russian client gets "Сера" and a French one gets its own word without
us shipping a single translation. Only the English canonical name is bundled, as
a fallback for clients that omit ``Name_Localised``.

Rarity is the one thing the journal never states, so it comes from a bundled
table. Where that table comes from, and the licensing wrinkle attached to it, is
documented in ``tools/build_materials_data.py``.

Holdings are seeded from a ``Materials`` event, which reports the whole hold at
once, and then moved by the events that change it. Seeding matters: a HUD started
mid-session would otherwise believe in an empty hold and report impossible totals
after the first pickup.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent / "data" / "materials.json"

#: Journal categories, in the order the HUD should mention them.
KINDS = ("Raw", "Manufactured", "Encoded")

#: Largest rarity in the game; used to sanity-check the bundled table.
MAX_RARITY = 5


@dataclass(frozen=True, slots=True)
class Material:
    """One material, as far as we know it."""

    symbol: str
    name: str
    rarity: int = 0
    kind: str = ""

    def display_name(self, localised: str = "") -> str:
        """The best name available: the game's own wording, else our fallback."""
        text = (localised or "").strip()
        if text:
            return text
        return self.name or self.symbol


@dataclass(frozen=True, slots=True)
class MaterialNotice:
    """One pickup, ready to be shown: "+1 Сера (Редкость: 1)  Всего: 285".

    Assembled in the state layer because that is where the label wording and the
    running total live; the overlay only draws it. ``total`` is None until a
    ``Materials`` event has reported the whole hold -- the journal states the
    hold once at login, so a pickup seen before that would otherwise announce a
    total of one for a hold of hundreds.
    """

    symbol: str
    name: str
    count: int = 1
    rarity: int = 0
    total: int | None = None

    def text(
        self,
        *,
        rarity_label: str = "Редкость",
        total_label: str = "Всего",
        show_rarity: bool = True,
        show_total: bool = True,
    ) -> str:
        """The single line shown in the bar.

        What to include is the caller's decision -- the state records what
        happened, the overlay decides what is worth drawing from config -- so
        both switches are applied here rather than at collection time.
        """
        line = f"+{self.count} {self.name}"
        if self.rarity and show_rarity:
            line = f"{line} ({rarity_label}: {self.rarity})"
        if self.total is not None and show_total:
            line = f"{line}  {total_label}: {self.total}"
        return line


class MaterialTable:
    """Rarity and canonical names, loaded once from the bundled table."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else DATA_PATH
        self._rarity: dict[str, int] = {}
        self._names: dict[str, str] = {}
        self._kinds: dict[str, str] = {}
        self.loaded = False
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # A missing table costs rarity, not the feature: names still come
            # from the journal.
            log.warning("cannot read material table %s: %s", self.path, exc)
            return
        if not isinstance(raw, dict):
            log.warning("material table %s is not an object", self.path)
            return

        rarity = raw.get("rarity")
        if isinstance(rarity, dict):
            for symbol, value in rarity.items():
                if isinstance(value, int) and 1 <= value <= MAX_RARITY:
                    self._rarity[str(symbol).casefold()] = value
                else:
                    log.warning("ignoring rarity %r for %r", value, symbol)
        names = raw.get("names")
        if isinstance(names, dict):
            self._names = {str(k).casefold(): str(v) for k, v in names.items()}
        kinds = raw.get("kinds")
        if isinstance(kinds, dict):
            self._kinds = {str(k).casefold(): str(v) for k, v in kinds.items()}

        self.loaded = bool(self._rarity or self._names)
        log.debug("loaded %d materials from %s", len(self._rarity), self.path)

    def normalise(self, symbol: str) -> str:
        """Journal symbols are lowercase; the table is keyed the same way."""
        return (symbol or "").strip().casefold()

    def get(self, symbol: str) -> Material | None:
        """The material for a journal symbol, or None when it is unknown."""
        key = self.normalise(symbol)
        if not key:
            return None
        rarity = self._rarity.get(key, 0)
        name = self._names.get(key, "")
        kind = self._kinds.get(key, "")
        if not rarity and not name:
            return None
        return Material(symbol=key, name=name, rarity=rarity, kind=kind)

    def rarity(self, symbol: str) -> int:
        return self._rarity.get(self.normalise(symbol), 0)

    def kind(self, symbol: str) -> str:
        return self._kinds.get(self.normalise(symbol), "")

    def display_name(self, symbol: str, localised: str = "") -> str:
        """Name for display, preferring the game's own localised wording."""
        material = self.get(symbol)
        if material is not None:
            return material.display_name(localised)
        text = (localised or "").strip()
        return text or self.normalise(symbol)

    def __len__(self) -> int:
        return len(self._rarity)
