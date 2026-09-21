"""Check the carrier-hold rule against real journals.

    python tools/verify_carrier_cargo.py -journal/Journal.2026-09-16T113843.01.log
    python tools/verify_carrier_cargo.py -journal/*.log

``CarrierStats`` is the only event that states a carrier's hold, and it fires
when the carrier's management screen is opened rather than when cargo moves. So
``CarrierBook`` adjusts the figure from the events that move cargo in between —
and those adjustments can be wrong in a way no unit test can see, because the
unit tests encode the same assumptions as the code.

This does the one check that cannot be faked: it replays a journal through the
real state machine and, at every ``CarrierStats``, compares the figure the code
worked out with the figure the game states. A disagreement is printed with the
events that caused it, and the game's value then replaces it, exactly as it does
in a live session.

Run it on a journal from a session that unloaded or delivered to a carrier: a
clean report means the rule matches what the game actually did.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from elite_hud.carriers import CarrierBook  # noqa: E402

#: Events that move cargo without stating the hold.
TRACKED = {"CargoTransfer", "MarketSell", "MarketBuy", "Docked", "Undocked"}


def replay(path: Path) -> int:
    book = CarrierBook()
    #: Carriers the game has already described. The first CarrierStats for one
    #: is not a check: before it the book knows nothing and would read zero.
    known: set[int] = set()
    disagreements = 0
    adjustments = 0

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or '"event"' not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("event")
        stamp = str(event.get("timestamp") or "")[11:19]

        if name == "CarrierStats":
            carrier_id = event.get("CarrierID")
            usage = event.get("SpaceUsage")
            stated = usage.get("Cargo") if isinstance(usage, dict) else None
            if isinstance(carrier_id, int) and isinstance(stated, int):
                previous = book.carriers.get(carrier_id)
                if carrier_id in known and previous is not None:
                    if previous.cargo == stated:
                        print(f"  сверка     {stamp} {previous.label}: сошлось, {stated} т")
                    else:
                        disagreements += 1
                        print(
                            f"  РАСХОЖДЕНИЕ {stamp} {previous.label}: код насчитал "
                            f"{previous.cargo}, игра говорит {stated} "
                            f"(разница {stated - previous.cargo:+d})"
                        )
                else:
                    print(f"  {stamp} {event.get('Callsign')}: игра говорит {stated} т")
                known.add(carrier_id)
            book.observe(event)
            continue

        if name in TRACKED:
            # The carrier this event concerns, worked out the same way the book
            # does: the one being docked at, or the market that was traded with.
            carrier_id = (
                event.get("MarketID")
                if name in ("MarketSell", "MarketBuy")
                else book.docked_carrier_id
            )
            before = book.carriers.get(carrier_id)
            cargo_before = before.cargo if before is not None else None
            if book.observe(event) and before is not None:
                adjustments += 1
                print(
                    f"  правка     {stamp} {name}: {before.label} "
                    f"{cargo_before} -> {before.cargo} т"
                )
            continue

        book.observe(event)

    print(f"\n{path.name}: правок {adjustments}, расхождений с игрой {disagreements}")
    return disagreements


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    total = 0
    for path in paths:
        if not path.is_file():
            print(f"нет файла: {path}", file=sys.stderr)
            return 2
        print("=" * 84)
        print(path)
        total += replay(path)
    print("=" * 84)
    print("РАСХОЖДЕНИЙ НЕТ" if not total else f"РАСХОЖДЕНИЙ: {total}")
    return 0 if not total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
