"""Exploration data waiting to be sold.

What is carried to Universal Cartographics is the one unsold total this project
will not put a credit figure on. The journal reports what was sold
(``MultiSellExplorationData``, with a body count per system) but never what is
currently held, so a figure would have to be computed from each body's type,
mass, and whether it was first discovered or first mapped. The formula for that
is not in the game's documentation and the community sources for it could not be
confirmed against real sales, so no number is shown. A wrong credit figure is
worse than no credit figure -- which is the whole reason this module counts
instead.

What it does count is verifiable. Replaying the journals this project was built
against, the running count is a *lower bound* on what each sale actually
contained, at every one of the five sales:

    sale                bodies sold   counted
    2026-09-14T21:20Z           461       261
    2026-09-16T16:28Z           540       455
    2026-09-16T16:28Z            78         0
    2026-09-16T23:46Z            72        51
    2026-09-16T23:59Z             5         1

Never once above the sold figure. The shortfall is data scanned before the
journal window began, which the HUD cannot see and does not claim. The dangerous
direction would be counting bodies that were never scanned, and that does not
happen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Names that are not bodies: belt clusters and rings are scanned but never sold.
NOT_A_BODY = ("Belt Cluster",)


def is_sellable_body(name: str) -> bool:
    """Whether a scan of this name counts towards a cartographics sale."""
    text = (name or "").strip()
    if not text:
        return False
    if any(marker in text for marker in NOT_A_BODY):
        return False
    return not text.endswith("Ring")


@dataclass(slots=True)
class CartographyHold:
    """Scanned but unsold systems, and how much of each was mapped."""

    #: System name -> the BodyIDs scanned there and not yet sold.
    systems: dict[str, set[int]] = field(default_factory=dict)
    #: (system, body) pairs that have been surface-mapped.
    mapped: set[tuple[str, int]] = field(default_factory=set)

    def add_scan(self, system: str, body_id: int) -> None:
        if not system or not isinstance(body_id, int):
            return
        self.systems.setdefault(system, set()).add(body_id)

    def add_mapping(self, system: str, body_id: int) -> None:
        if not system or not isinstance(body_id, int):
            return
        self.mapped.add((system, body_id))

    def clear(self) -> None:
        """A sale empties the hold, whatever was in it."""
        self.systems.clear()
        self.mapped.clear()

    @property
    def system_count(self) -> int:
        return len(self.systems)

    @property
    def body_count(self) -> int:
        return sum(len(bodies) for bodies in self.systems.values())

    @property
    def mapped_count(self) -> int:
        """Mapped bodies still held; a map of a body already sold is not held."""
        return sum(
            1
            for system, body_id in self.mapped
            if body_id in self.systems.get(system, ())
        )

    @property
    def empty(self) -> bool:
        return not self.systems

    def describe(self) -> str:
        if self.empty:
            return "пусто"
        text = f"{self.system_count} сист. / {self.body_count} тел"
        if self.mapped_count:
            text += f" (карт {self.mapped_count})"
        return text
