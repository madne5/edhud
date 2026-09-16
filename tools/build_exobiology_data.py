"""Build elite_hud/data/exobiology.json from the EDMC-BioScan ruleset catalogs.

The ruleset catalogs are plain-data Python modules of the shape:

    {genus_codex_key: {species_codex_key: {"name": str, "value": int, "rulesets": [...]}}}

This tool flattens them into a single JSON blob that the HUD can load without
importing any third-party code.  Run it only when you want to refresh the table:

    python tools/build_exobiology_data.py <path-to-EDMC-BioScan/src/bio_scan/bio_data/rulesets>
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "elite_hud" / "data" / "exobiology.json"

# Genera that are not sellable exobiology: no genetic sampler sample, no
# Vista Genomics payout.  They are Horizons-era codex curiosities and must
# never trigger a payout alert.
NON_SELLABLE_GENERA = {
    "$Codex_Ent_Cone_Name;",  # Bark Mound
    "$Codex_Ent_Vents_Name;",  # Amphora Plant
    "$Codex_Ent_Ground_Struct_Ice_Name;",  # Crystalline Shards
    "$Codex_Ent_Tube_Name;",  # Sinuous Tubers
    "$Codex_Ent_Brancae_Name;",  # Brain Tree
    "$Codex_Ent_Sphere_Name;",  # Anemone
}

# Authoritative in-game ``Genus_Localised`` values keyed by codex symbol.
# The journal reports the localised string in SAASignalsFound.Genuses[].Genus_Localised;
# we keep our own copy so lookups work even when the client language is not English.
GENUS_NAMES = {
    "$Codex_Ent_Aleoids_Genus_Name;": "Aleoida",
    "$Codex_Ent_Bacterial_Genus_Name;": "Bacterium",
    "$Codex_Ent_Brancae_Name;": "Brain Tree",
    "$Codex_Ent_Cactoid_Genus_Name;": "Cactoida",
    "$Codex_Ent_Clypeus_Genus_Name;": "Clypeus",
    "$Codex_Ent_Conchas_Genus_Name;": "Concha",
    "$Codex_Ent_Cone_Name;": "Bark Mound",
    "$Codex_Ent_Electricae_Genus_Name;": "Electricae",
    "$Codex_Ent_Fonticulus_Genus_Name;": "Fonticulua",
    "$Codex_Ent_Fumerolas_Genus_Name;": "Fumerola",
    "$Codex_Ent_Fungoids_Genus_Name;": "Fungoida",
    "$Codex_Ent_Ground_Struct_Ice_Name;": "Crystalline Shards",
    "$Codex_Ent_Ingensradices_Genus_Name;": "Radicoida",
    "$Codex_Ent_Osseus_Genus_Name;": "Osseus",
    "$Codex_Ent_Recepta_Genus_Name;": "Recepta",
    "$Codex_Ent_Shrubs_Genus_Name;": "Frutexa",
    "$Codex_Ent_Sphere_Name;": "Anemone",
    "$Codex_Ent_Stratum_Genus_Name;": "Stratum",
    "$Codex_Ent_Tube_Name;": "Sinuous Tubers",
    "$Codex_Ent_Tubus_Genus_Name;": "Tubus",
    "$Codex_Ent_Tussocks_Genus_Name;": "Tussock",
    "$Codex_Ent_Vents_Name;": "Amphora Plant",
}

# BioScan keeps a handful of species under a genus key equal to their own
# species key.  Fold those into the real genus so the genus lookup is complete.
GENUS_ALIASES = {
    "$Codex_Ent_Stratum_04_Name;": "$Codex_Ent_Stratum_Genus_Name;",
}


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_rs_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# EDMC-BioScan still carries the pre-Update-14 placeholder 2**24-1 for a few
# species.  These values are cross-checked against Canonn's Vista Genomics
# sales data and ArtemisScannerTracker's "Update 14.01" table.
VALUE_CORRECTIONS = {
    "Concha Biconcavis": 19_010_800,  # BioScan: 16_777_215 (2**24-1 placeholder)
}

# Species that appear in BioScan's catalogs under a misspelled name.
NAME_CORRECTIONS = {
    "Stratum Aranaemus": "Stratum Araneamus",
}


def genus_display_name(genus_key: str, species_names: list[str]) -> str:
    """Best-effort human readable genus name.

    In-game ``SAASignalsFound`` reports ``Genus_Localised`` (e.g. "Bacterium"),
    which for the common genera is simply the first word of every species name.
    """
    if not species_names:
        return genus_key
    first_words = {name.split(" ")[0] for name in species_names}
    if len(first_words) == 1:
        return first_words.pop()
    # Mixed first words -> fall back to the longest common prefix word.
    return sorted(species_names, key=len)[0].split(" ")[0]


def main() -> int:
    if len(sys.argv) > 1:
        rulesets_dir = Path(sys.argv[1])
    else:
        # EDMC-BioScan is not vendored here, so clone it next to the repo:
        #   git clone --depth 1 https://github.com/Silarn/EDMC-BioScan research/EDMC-BioScan
        rulesets_dir = (
            REPO_ROOT / "research" / "EDMC-BioScan" / "src" / "bio_scan" / "bio_data" / "rulesets"
        )
    if not rulesets_dir.is_dir():
        print(
            f"rulesets directory not found: {rulesets_dir}\n"
            "Clone the source data first, or pass the path as an argument:\n"
            "  git clone --depth 1 https://github.com/Silarn/EDMC-BioScan "
            "research/EDMC-BioScan\n"
            "  python tools/build_exobiology_data.py <path-to-rulesets>",
            file=sys.stderr,
        )
        return 2

    genera: dict[str, dict] = {}
    by_key: dict[str, int] = {}
    by_name: dict[str, int] = {}
    species_names: dict[str, str] = {}

    for path in sorted(rulesets_dir.glob("*.py")):
        module = load_module(path)
        catalog = getattr(module, "catalog", None)
        if not isinstance(catalog, dict):
            print(f"skipping {path.name}: no catalog dict", file=sys.stderr)
            continue

        for raw_genus_key, species_map in catalog.items():
            if not isinstance(species_map, dict):
                continue
            genus_key = GENUS_ALIASES.get(raw_genus_key, raw_genus_key)

            species_out: dict[str, dict] = {}
            for species_key, info in species_map.items():
                if not isinstance(info, dict) or "value" not in info:
                    continue
                name = NAME_CORRECTIONS.get(info.get("name") or species_key, info.get("name") or species_key)
                value = VALUE_CORRECTIONS.get(name, int(info["value"]))
                species_out[species_key] = {"name": name, "value": value}
                by_key[species_key] = value
                by_name[name] = value
                species_names[species_key] = name

            if not species_out:
                continue

            entry = genera.setdefault(
                genus_key,
                {"name": GENUS_NAMES.get(genus_key, ""), "sellable": genus_key not in NON_SELLABLE_GENERA, "species": {}},
            )
            entry["species"].update(species_out)
            entry["sellable"] = entry["sellable"] and genus_key not in NON_SELLABLE_GENERA

    # Value envelopes and display names are only meaningful once every species
    # of a genus has been folded in.
    for genus_key, entry in genera.items():
        if not entry["name"]:
            entry["name"] = genus_display_name(genus_key, [s["name"] for s in entry["species"].values()])
        values = [s["value"] for s in entry["species"].values() if s["value"] > 0]
        entry["min_value"] = min(values) if values else 0
        entry["max_value"] = max(values) if values else 0
        entry["species"] = dict(sorted(entry["species"].items(), key=lambda kv: -kv[1]["value"]))

    # Non-sellable organics must never be resolvable to a payout.
    for genus_key, entry in genera.items():
        if entry["sellable"]:
            continue
        for species_key, species in entry["species"].items():
            by_key.pop(species_key, None)
            by_name.pop(species["name"], None)

    payload = {
        "_source": "EDMC-BioScan ruleset catalogs (Update 14.01 prices)",
        "genera": dict(sorted(genera.items())),
        "by_key": dict(sorted(by_key.items())),
        "by_name": dict(sorted(by_name.items())),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    sellable = [g for g in genera.values() if g["sellable"]]
    print(f"wrote {OUT_PATH}")
    print(f"  genera: {len(genera)} ({len(sellable)} sellable)")
    print(f"  species keys: {len(by_key)}")
    top = sorted(by_key.items(), key=lambda kv: -kv[1])[:5]
    print("  top species:", ", ".join(f"{species_names.get(k, k)}={v:,}" for k, v in top))
    guaranteed = [g["name"] for g in sellable if g["min_value"] >= 7_000_000]
    print(f"  genera always >= 7,000,000: {guaranteed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
