"""Ship model names, learned from the journal rather than bundled.

``Loadout`` does not carry the current ship's model name. It carries the internal
symbol (``explorer_nx``), the commander's own name for the ship ("KSS Deep
Explorer Ship") and its ident ("KSS-99") -- and the manual marks
``Ship_Localised`` as optional, absent from every Loadout in the journals this was
built against.

The model name does appear elsewhere in the journal: ``ShipyardSwap``,
``StoredShips`` and ``ShipyardTransfer`` all carry ``ShipType_Localised``, so a
commander's own journals already contain the mapping for every ship they have
swapped into. That is the source used here.

A bundled table was considered and rejected. The two candidate sources both have
a problem: EDMarketConnector's is GPL-2, which cannot be copied into this project,
and EDCD/FDevIDs ships no licence file at all, which is the same objection that
stopped the rank icons from being bundled. Learning from the game's own output
sidesteps the question entirely, and is more correct besides: it follows the
game's naming rather than a snapshot of it.

Learned pairs are cached to a small file next to the configuration, because
otherwise a commander who flies one ship for a month would never see its name:
the swap that taught it would have fallen outside the replay window.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_FILENAME = "ships.json"

#: Words that should not be capitalised when prettifying a bare symbol.
_SMALL_WORDS = {"mk", "mkii", "mkiii", "mkiv"}


def prettify(symbol: str) -> str:
    """A readable fallback for a symbol no event has named yet.

    Only ever a fallback: it cannot know that ``explorer_nx`` is a Caspian
    Explorer, so it does not pretend to. It just avoids showing an underscore
    soup when the real name has not been seen.
    """
    text = (symbol or "").strip()
    if not text:
        return ""
    words = [word for word in text.split("_") if word]
    if not words:
        return text
    parts = [words[0][:1].upper() + words[0][1:]]
    for word in words[1:]:
        # Short tokens are manufacturer suffixes: "explorer_nx" is an NX.
        parts.append(word.upper() if len(word) <= 3 else word[:1].upper() + word[1:])
    return " ".join(parts)


class ShipNames:
    """Internal ship symbols mapped to the names the game reports for them."""

    def __init__(self, cache_path: Path | None = None, *, persist: bool = True) -> None:
        self.cache_path = Path(cache_path) if cache_path is not None else None
        self.persist = persist and self.cache_path is not None
        self._names: dict[str, str] = {}
        self._load()

    # -- storage -----------------------------------------------------------

    def _load(self) -> None:
        if self.cache_path is None:
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(raw, dict):
            for key, value in raw.items():
                cleaned = self.clean_name(str(value)) if isinstance(value, str) else ""
                if cleaned:
                    self._names[str(key).strip().casefold()] = cleaned

    def _save(self) -> None:
        if not self.persist or self.cache_path is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._names, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            # A cache that cannot be written costs a name after the next
            # restart, nothing more.
            log.debug("cannot write ship name cache %s: %s", self.cache_path, exc)

    # -- learning ----------------------------------------------------------

    @staticmethod
    def normalise(symbol: str) -> str:
        return (symbol or "").strip().casefold()

    @staticmethod
    def clean_name(text: str) -> str:
        """Tidy a name for display, or return "" when it is not usable.

        Two things turn up in real journals. The game pads some names with a
        non-breaking space -- "Caspian\xa0Explorer" -- which measures oddly and
        looks wrong. And some localised fields carry an *unresolved* symbol
        token instead of a name: ``explorationsuit_class3`` came through as
        "$ExplorationSuit_Class1_Name;", which is not a name at all and would
        have been shown to the commander verbatim.
        """
        name = " ".join((text or "").replace("\u00a0", " ").split())
        if not name:
            return ""
        if name.startswith("$") or name.endswith(";"):
            return ""
        return name

    def learn(self, symbol: str, localised: str) -> bool:
        """Record a symbol's display name. Returns True when something changed.

        A blank localised name is common -- ``mandalay`` came through with none
        in these journals -- and must not overwrite a name learned earlier.
        """
        key = self.normalise(symbol)
        name = self.clean_name(localised)
        if not key or not name:
            return False
        if self._names.get(key) == name:
            return False
        self._names[key] = name
        self._save()
        return True

    def observe(self, event: dict) -> bool:
        """Learn from any event that names a ship type.

        Several events carry it: ShipyardSwap (``ShipType``), StoredShips and
        ShipyardTransfer, plus Loadout and LoadGame when the optional
        ``Ship_Localised`` happens to be present.
        """
        changed = False
        for symbol_key, name_key in (
            ("ShipType", "ShipType_Localised"),
            ("Ship", "Ship_Localised"),
            ("StoreOldShip", "StoreOldShip_Localised"),
        ):
            if self.learn(str(event.get(symbol_key) or ""), str(event.get(name_key) or "")):
                changed = True
        for key in ("ShipsHere", "ShipsRemote"):
            entries = event.get(key)
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and self.learn(
                        str(entry.get("ShipType") or ""),
                        str(entry.get("ShipType_Localised") or ""),
                    ):
                        changed = True
        return changed

    # -- lookup ------------------------------------------------------------

    def display(self, symbol: str) -> str:
        """Best available name: what the game called it, else a tidied symbol."""
        key = self.normalise(symbol)
        if not key:
            return ""
        return self._names.get(key) or prettify(key)

    def known(self, symbol: str) -> bool:
        return self.normalise(symbol) in self._names

    def __len__(self) -> int:
        return len(self._names)

    @property
    def names(self) -> dict[str, str]:
        return dict(self._names)
