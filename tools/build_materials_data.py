"""Build ``elite_hud/data/materials.json``.

The HUD needs two things about a material: its display name and its rarity.
Only one of them has to be bundled.

**Names come from the journal.** Every ``MaterialCollected`` and every entry of a
``Materials`` event carries ``Name_Localised`` in the client's own language --
"Сера", "Щитоизлучатели", "Неполный анализ поглощения щита" on the journals this
project was built against. That is both more correct and more useful than any
table we could ship: a commander running the game in French gets French for
free. The English name is bundled only as a fallback, because an English client
may omit ``Name_Localised`` and leave the bare lowercase symbol to be shown.

**Rarity has to be bundled.** The journal never states it, in any event type.

Rarity is therefore the only external data here, and it is 137 integers. Its
source, ``EDCD/FDevIDs``, carries **no licence file at all** (checked across the
usual filenames on both main and master), which means all rights reserved by
default. That is worth stating plainly rather than burying: the alternative is
that a commander cannot see rarity at all, and rarity is the single most useful
thing to know about a material. The values themselves are facts about the game
rather than creative content, and ``materials.rarity` can be switched off in
config for anyone who would rather not rely on them.

Usage:

    python tools/build_materials_data.py research/data/materials.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "elite_hud" / "data" / "materials.json"

SOURCE_NOTE = (
    "Rarity from EDCD/FDevIDs (github.com/EDCD/FDevIDs, material.csv), which "
    "carries no licence file. English names from the same source; display names "
    "at runtime come from the journal's Name_Localised instead."
)

#: Rarity is 1-5 in the game. Anything else means the source changed shape and
#: should not be published silently.
VALID_RARITIES = (1, 2, 3, 4, 5)
KINDS = ("Raw", "Manufactured", "Encoded")


def build(rows: list[dict]) -> dict:
    rarity: dict[str, int] = {}
    names: dict[str, str] = {}
    kinds: dict[str, str] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().casefold()
        if not symbol:
            raise SystemExit(f"row without a symbol: {row!r}")
        if symbol in rarity:
            raise SystemExit(f"duplicate symbol {symbol!r}")
        value = row.get("rarity")
        if value not in VALID_RARITIES:
            raise SystemExit(f"{symbol}: unexpected rarity {value!r}")
        kind = str(row.get("type") or "")
        if kind not in KINDS:
            raise SystemExit(f"{symbol}: unexpected type {kind!r}")
        rarity[symbol] = int(value)
        names[symbol] = str(row.get("name") or row.get("symbol") or symbol)
        kinds[symbol] = kind
    return {
        "_source": SOURCE_NOTE,
        "rarity": dict(sorted(rarity.items())),
        "names": dict(sorted(names.items())),
        "kinds": dict(sorted(kinds.items())),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    source = Path(argv[1])
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"{source} should contain a list of rows")
    payload = build(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    counts: dict[str, int] = {}
    for kind in payload["kinds"].values():
        counts[kind] = counts.get(kind, 0) + 1
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}: {len(payload['rarity'])} materials {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
