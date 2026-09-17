"""Exobiology value model: genus/species codex keys -> Vista Genomics payout.

The journal identifies organics by codex symbol (``$Codex_Ent_Bacterial_01_Name;``)
and, in ``ScanOrganic``, by a localised name.  Both are indexed here so the
overlay can turn whatever it receives into a credit value and a confidence
level.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent / "data" / "exobiology.json"


class Confidence(str, Enum):
    """How sure we are that a body's exobiology clears the value threshold."""

    #: Exact species resolved (ScanOrganic / CodexEntry / sample analysed).
    CONFIRMED = "confirmed"
    #: Genus resolved and *every* species of that genus clears the threshold.
    GUARANTEED = "guaranteed"
    #: Genus resolved and *some* species of that genus clears the threshold.
    POSSIBLE = "possible"
    #: Nothing here can clear the threshold.
    NONE = "none"

    @property
    def rank(self) -> int:
        return {"none": 0, "possible": 1, "guaranteed": 2, "confirmed": 3}[self.value]


@dataclass(frozen=True, slots=True)
class Species:
    key: str
    name: str
    value: int


@dataclass(frozen=True, slots=True)
class Genus:
    key: str
    name: str
    sellable: bool
    min_value: int
    max_value: int
    species: tuple[Species, ...]

    def best(self) -> Species | None:
        candidates = [s for s in self.species if s.value > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.value)


#: ``Codex_Ent_<Genus>_<NN>_<Variant>_Name`` -> ``Codex_Ent_<Genus>_<NN>_Name``.
#: Tolerant of the surrounding ``$`` and ``;`` because the lookup runs after
#: they have already been stripped, and working on either form avoids having to
#: remember which.
_VARIANT_RE = re.compile(r"^\$?(?P<base>Codex_Ent_.+_\d+)_[^_]+_Name;?$")


def _strip_variant(symbol: str) -> str:
    """Drop the colour or element token from a codex species symbol."""
    match = _VARIANT_RE.match(symbol)
    if match is None:
        return symbol
    return match.group("base") + "_Name"


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _strip_symbol(text: str) -> str:
    """``$Codex_Ent_Bacterial_01_Name;`` -> ``Codex_Ent_Bacterial_01_Name``."""
    out = text.strip()
    if out.startswith("$"):
        out = out[1:]
    if out.endswith(";"):
        out = out[:-1]
    return out


class ExobiologyTable:
    """Lookup table for organic values, built from ``data/exobiology.json``."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_PATH
        self.genera_by_key: dict[str, Genus] = {}
        self.genera_by_name: dict[str, Genus] = {}
        self.species_by_key: dict[str, Species] = {}
        self.species_by_name: dict[str, Species] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("cannot load exobiology table %s: %s", self.path, exc)
            return

        for genus_key, genus_data in (raw.get("genera") or {}).items():
            species = tuple(
                Species(key=key, name=info.get("name", key), value=int(info.get("value", 0)))
                for key, info in (genus_data.get("species") or {}).items()
            )
            genus = Genus(
                key=genus_key,
                name=genus_data.get("name", genus_key),
                sellable=bool(genus_data.get("sellable", True)),
                min_value=int(genus_data.get("min_value", 0)),
                max_value=int(genus_data.get("max_value", 0)),
                species=species,
            )
            self.genera_by_key[genus_key] = genus
            self.genera_by_name.setdefault(_normalize(genus.name), genus)
            if not genus.sellable:
                # Horizons-era curiosities (Brain Trees, Anemones, ...) have no
                # Vista Genomics payout, so they must never resolve to a value.
                continue
            for entry in species:
                self.species_by_key[entry.key] = entry
                self.species_by_name.setdefault(_normalize(entry.name), entry)

        log.debug(
            "exobiology table: %d genera, %d species",
            len(self.genera_by_key),
            len(self.species_by_key),
        )

    # -- lookups -----------------------------------------------------------

    def genus(self, key_or_name: str | None) -> Genus | None:
        if not key_or_name:
            return None
        text = key_or_name.strip()
        if text in self.genera_by_key:
            return self.genera_by_key[text]
        stripped = _strip_symbol(text)
        if stripped in self.genera_by_key:
            return self.genera_by_key[stripped]
        # Localised genus names arrive as "Bacterium" and, occasionally, the
        # full "$Codex_Ent_Bacterial_Genus_Name;" symbol.
        by_name = self.genera_by_name.get(_normalize(text))
        if by_name is not None:
            return by_name
        for genus in self.genera_by_key.values():
            if _normalize(genus.name) == _normalize(stripped):
                return genus
        return None

    def species(self, key_or_name: str | None) -> Species | None:
        """Resolve a species from a codex symbol or a localised name.

        ``ScanOrganic`` variants arrive as ``"Bacterium Cerbrus - Yellow"``;
        the colour suffix is stripped before matching.
        """
        if not key_or_name:
            return None
        text = key_or_name.strip()

        if text in self.species_by_key:
            return self.species_by_key[text]
        stripped = _strip_symbol(text)
        if stripped in self.species_by_key:
            return self.species_by_key[stripped]
        # CodexEntry names a species *variant*, e.g.
        # "$Codex_Ent_Clypeus_02_M_Name;" or
        # "$Codex_Ent_Bacterial_09_Antimony_Name;". The table is keyed by the
        # base species, so without this every real biology codex entry resolved
        # to nothing while a codex entry with no accompanying ScanOrganic --
        # which is the case this path exists for -- was lost entirely.
        base = _strip_variant(stripped)
        if base != stripped:
            # The table is keyed by the full symbol, "$..._Name;", so both the
            # bare and the wrapped form are worth trying.
            for candidate in (base, f"${base};"):
                hit = self.species_by_key.get(candidate)
                if hit is not None:
                    return hit

        normalized = _normalize(text)
        hit = self.species_by_name.get(normalized)
        if hit is not None:
            return hit

        if " - " in normalized:
            head = normalized.split(" - ", 1)[0].strip()
            hit = self.species_by_name.get(head)
            if hit is not None:
                return hit

        # "Bacterium Cerbrus" may be reported with extra variant words.
        for name, entry in self.species_by_name.items():
            if normalized.startswith(name):
                return entry
        return None

    def value(self, key_or_name: str | None) -> int | None:
        species = self.species(key_or_name)
        if species is not None:
            return species.value
        genus = self.genus(key_or_name)
        if genus is not None and genus.max_value:
            return genus.max_value
        return None

    # -- assessment --------------------------------------------------------

    @staticmethod
    def assess_genus(genus: Genus | None, threshold: int) -> Confidence:
        if genus is None or not genus.sellable or threshold <= 0:
            return Confidence.NONE
        if genus.min_value >= threshold:
            return Confidence.GUARANTEED
        if genus.max_value >= threshold:
            return Confidence.POSSIBLE
        return Confidence.NONE

    @staticmethod
    def assess_species(species: Species | None, threshold: int) -> Confidence:
        if species is None or threshold <= 0:
            return Confidence.NONE
        return Confidence.CONFIRMED if species.value >= threshold else Confidence.NONE

    def apply_overrides(self, overrides: dict[str, int]) -> int:
        """Apply user-supplied ``species name -> value`` corrections."""
        applied = 0
        for name, value in overrides.items():
            try:
                value = int(value)
            except (TypeError, ValueError):
                log.warning("ignoring non-numeric exobiology override %r=%r", name, value)
                continue
            species = self.species(name)
            if species is None:
                log.warning("exobiology override for unknown species %r ignored", name)
                continue
            replaced = Species(key=species.key, name=species.name, value=value)
            self.species_by_key[species.key] = replaced
            self.species_by_name[_normalize(species.name)] = replaced
            self._reindex_genus(species.key, replaced)
            applied += 1
        return applied

    def _reindex_genus(self, species_key: str, replacement: Species) -> None:
        for genus_key, genus in list(self.genera_by_key.items()):
            if not any(s.key == species_key for s in genus.species):
                continue
            species = tuple(
                replacement if s.key == species_key else s for s in genus.species
            )
            values = [s.value for s in species if s.value > 0]
            updated = Genus(
                key=genus.key,
                name=genus.name,
                sellable=genus.sellable,
                min_value=min(values) if values else 0,
                max_value=max(values) if values else 0,
                species=species,
            )
            self.genera_by_key[genus_key] = updated
            self.genera_by_name[_normalize(updated.name)] = updated
