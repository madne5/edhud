"""Fines and notoriety.

The in-game term for a criminal record is notoriety: a level from 0 to 10 that
rises when you destroy clean ships and decays while you stay out of trouble. It
is what makes a commander shoot-on-sight to system security, so knowing the
level is worth a glance.

It turns out the journal reports it outright, in the ``Crime`` section of the
``Statistics`` event, which carries ``Notoriety``, ``Fines``, ``Total_Fines``,
``Bounties_Received``, ``Total_Bounties`` and ``Highest_Bounty``. That is a much
better source than modelling the level from kills and decay, which would have
been a guess dressed up as a number.

The catch is when the event fires: like ``Rank`` and ``Progress``, ``Statistics``
is written once at session start. So the level is a snapshot from login rather
than a live figure, and the live part is the money: ``CommitCrime`` adds a fine,
``PayFines`` clears it, and that is what changes during a session.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Notoriety runs 0-10 in the game.
MAX_NOTORIETY = 10


@dataclass(slots=True)
class CrimeRecord:
    """What the commander owes, and how wanted they are."""

    #: Notoriety level at the last Statistics event, None until one arrives.
    notoriety: int | None = None
    #: Unpaid fines accumulated this session.
    fines: int = 0
    #: Bounties placed on the commander during this session.
    session_bounties: int = 0
    session_bounty_value: int = 0

    # -- lifetime totals, which never describe the present ------------------
    # These come from Statistics and cover the whole career: a commander with
    # 122 bounties received over five years is not wanted right now. Keeping
    # them in the same fields as the live ones made a spotless commander look
    # permanently hunted, because clean() saw the career total.
    lifetime_fines: int = 0
    lifetime_crimes: int = 0
    lifetime_bounties_received: int = 0
    lifetime_bounty_total: int = 0
    highest_bounty: int = 0
    #: Most recent crime type, for the log and the tooltip.
    last_crime: str = ""

    @property
    def notorious(self) -> bool:
        return bool(self.notoriety)

    @property
    def clean(self) -> bool:
        """Nothing owing, no notoriety, no live bounty: the segment stays hidden.

        Lifetime totals are deliberately excluded: they never fall, so using
        them here would hide the segment for nobody.
        """
        return not self.fines and not self.notorious and not self.session_bounties

    def observe_statistics(self, crime: dict) -> None:
        """Fold in the ``Crime`` section of a ``Statistics`` event."""
        value = crime.get("Notoriety")
        if isinstance(value, int) and not isinstance(value, bool):
            self.notoriety = max(0, min(MAX_NOTORIETY, value))
        for key, attr in (
            ("Total_Fines", "lifetime_fines"),
            ("Fines", "lifetime_crimes"),
            ("Bounties_Received", "lifetime_bounties_received"),
            ("Total_Bounties", "lifetime_bounty_total"),
            ("Highest_Bounty", "highest_bounty"),
        ):
            amount = crime.get(key)
            if isinstance(amount, int) and not isinstance(amount, bool):
                setattr(self, attr, amount)

    def add_fine(self, amount: int, *, crime: str = "") -> None:
        if amount > 0:
            self.fines += amount
        if crime:
            self.last_crime = crime

    def pay_fines(self, amount: int = 0, *, all_fines: bool = False) -> None:
        """Clear the debt. ``PayFines`` names the amount, and says if it was all."""
        if all_fines or amount <= 0:
            self.fines = 0
            return
        self.fines = max(0, self.fines - amount)

    def add_bounty(self, amount: int) -> None:
        """A bounty placed on the commander rather than one they earned."""
        self.session_bounties += 1
        if amount > 0:
            self.session_bounty_value += amount

    def describe(self) -> str:
        parts: list[str] = []
        if self.notoriety is not None:
            parts.append(f"notoriety {self.notoriety}")
        if self.fines:
            parts.append(f"fines {self.fines:,}")
        if self.session_bounties:
            parts.append(f"bounties {self.session_bounties}")
        return ", ".join(parts) or "clean"
