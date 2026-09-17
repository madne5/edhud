"""Value carried but not yet banked.

Two things a commander is holding that are lost on death: unsold exobiology
samples, and vouchers that have not been cashed in. Knowing the total is the
difference between taking one more risk and turning back.

What this can and cannot know was established by replaying the journals this
project tests against, and the two halves behave very differently.

**Exobiology is exact.** Accumulating species base values from ``ScanOrganic``
and multiplying by five when ``WasLogged`` is false -- the first-logged bonus --
reproduced a real ``SellOrganicData`` payment to the credit: 133,927,500 cr
predicted against 133,927,500 cr paid. Only ``ScanType == "Analyse"`` counts; a
sample fires the event three times as it is logged, sampled and finally
analysed, and only the last of those puts anything in the hold.

**Exploration is not.** The journal states what was sold (``Discovered``, with a
body count per system) but never what is currently held. Counting scans since
the last sale was tried and rejected: sales consistently exceeded the count,
because bodies scanned before the journal window are still sold inside it, and
one sale of 78 bodies followed another by 14 seconds with no scans between. A
number that wrong is worse than no number, so no exploration total is shown.
Vouchers are accumulated but were not exercised by those journals at all, so
they are the least proven part of this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Voucher kinds, matching RedeemVoucher's own Type values.
VOUCHER_TYPES = (
    "bounty",
    "bond",
    "combat",
    "trade",
    "settlement",
    "scannable",
    "codex",
    "exploration",
)


def normalise_voucher(kind: str) -> str:
    """Map a journal voucher type onto our own vocabulary."""
    text = (kind or "").strip().casefold()
    if text in VOUCHER_TYPES:
        return text
    # The journal has used both "CombatBond" and "bond" for faction bonds.
    if "bond" in text:
        return "bond"
    if "bounty" in text:
        return "bounty"
    return text or "other"


@dataclass(slots=True)
class Sample:
    """One completed exobiology sample sitting in the hold."""

    species: str
    value: int
    first_logged: bool


@dataclass(slots=True)
class UnsoldData:
    """Everything sampled or earned but not yet redeemed."""

    samples: list[Sample] = field(default_factory=list)
    #: Voucher value by kind.
    vouchers: dict[str, int] = field(default_factory=dict)
    #: Samples handed over in the last sale, for logging and tests.
    last_sale_credits: int = 0
    last_sale_samples: int = 0

    # -- exobiology --------------------------------------------------------

    def add_sample(self, species: str, value: int, *, first_logged: bool) -> Sample:
        """Record a completed sample; the x5 applies when no one logged it first."""
        sample = Sample(
            species=species,
            value=max(0, int(value)) * (5 if first_logged else 1),
            first_logged=first_logged,
        )
        self.samples.append(sample)
        return sample

    @property
    def bio_credits(self) -> int:
        return sum(sample.value for sample in self.samples)

    @property
    def bio_count(self) -> int:
        return len(self.samples)

    def clear_bio(self, *, credits: int = 0, samples: int = 0) -> None:
        """Empty the hold after a sale, or after dying and losing it all."""
        self.last_sale_credits = credits
        self.last_sale_samples = samples
        self.samples.clear()

    # -- vouchers ----------------------------------------------------------

    def add_voucher(self, kind: str, amount: int) -> None:
        key = normalise_voucher(kind)
        self.vouchers[key] = self.vouchers.get(key, 0) + max(0, int(amount))

    def redeem(self, kind: str, amount: int = 0) -> None:
        """Cash in vouchers. A journal redeem names the type it cleared."""
        key = normalise_voucher(kind)
        if amount > 0 and self.vouchers.get(key, 0) > amount:
            # Partial redemption: the journal reports what was paid.
            self.vouchers[key] -= amount
            return
        self.vouchers.pop(key, None)

    @property
    def voucher_total(self) -> int:
        return sum(self.vouchers.values())

    @property
    def total(self) -> int:
        return self.bio_credits + self.voucher_total

    # -- presentation ------------------------------------------------------

    def describe(self) -> str:
        """Short summary for logs, e.g. "bio 2 (343.3M) + ваучеры 0"."""
        parts = []
        if self.samples:
            parts.append(f"bio {self.bio_count} ({self.bio_credits:,})")
        for kind, amount in sorted(self.vouchers.items()):
            if amount:
                parts.append(f"{kind} {amount:,}")
        return " + ".join(parts) or "пусто"
