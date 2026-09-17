"""Unsold value: exobiology samples and vouchers not yet banked."""

from __future__ import annotations

import unittest

from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.state import GameState
from elite_hud.unsold import UnsoldData, normalise_voucher

STRATUM = "$Codex_Ent_Stratum_Genus_Name;"
#: Stratum Tectonicas, the species the journals sell most of.
STRATUM_TECTONICAS = "$Codex_Ent_Stratum_07_Name;"


class VoucherKindTests(unittest.TestCase):
    def test_known_kinds_pass_through(self) -> None:
        for kind in ("bounty", "bond", "codex", "combat"):
            self.assertEqual(normalise_voucher(kind), kind)

    def test_case_is_folded(self) -> None:
        self.assertEqual(normalise_voucher("Bounty"), "bounty")

    def test_bond_spellings_collapse(self) -> None:
        # The journal has used both "CombatBond" and "bond" over the years.
        self.assertEqual(normalise_voucher("CombatBond"), "bond")
        self.assertEqual(normalise_voucher("factionBond"), "bond")

    def test_unknown_kinds_are_kept_not_dropped(self) -> None:
        """Losing an unrecognised voucher would understate the total."""
        self.assertEqual(normalise_voucher("somethingNew"), "somethingnew")

    def test_empty_kind_is_labelled(self) -> None:
        self.assertEqual(normalise_voucher(""), "other")
        self.assertEqual(normalise_voucher(None), "other")


class UnsoldDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = UnsoldData()

    def test_a_first_logged_sample_pays_five_times(self) -> None:
        sample = self.data.add_sample("Stratum Tectonicas", 19_010_800, first_logged=True)
        self.assertEqual(sample.value, 95_054_000)

    def test_an_already_logged_sample_pays_the_base_value(self) -> None:
        sample = self.data.add_sample("Stratum Tectonicas", 19_010_800, first_logged=False)
        self.assertEqual(sample.value, 19_010_800)

    def test_samples_accumulate(self) -> None:
        self.data.add_sample("A", 1_000_000, first_logged=True)
        self.data.add_sample("B", 2_000_000, first_logged=False)
        self.assertEqual(self.data.bio_count, 2)
        self.assertEqual(self.data.bio_credits, 7_000_000)

    def test_a_negative_value_is_not_credit(self) -> None:
        self.data.add_sample("A", -5, first_logged=False)
        self.assertEqual(self.data.bio_credits, 0)

    def test_selling_empties_the_hold(self) -> None:
        self.data.add_sample("A", 1_000_000, first_logged=True)
        self.data.clear_bio(credits=5_000_000, samples=1)
        self.assertEqual(self.data.bio_credits, 0)
        self.assertEqual(self.data.bio_count, 0)
        self.assertEqual(self.data.last_sale_credits, 5_000_000)

    def test_vouchers_accumulate_by_kind(self) -> None:
        self.data.add_voucher("bounty", 100)
        self.data.add_voucher("bounty", 250)
        self.data.add_voucher("bond", 400)
        self.assertEqual(self.data.vouchers, {"bounty": 350, "bond": 400})
        self.assertEqual(self.data.voucher_total, 750)

    def test_redeeming_clears_the_named_kind_only(self) -> None:
        self.data.add_voucher("bounty", 350)
        self.data.add_voucher("bond", 400)
        self.data.redeem("bounty")
        self.assertEqual(self.data.vouchers, {"bond": 400})

    def test_a_partial_redemption_subtracts(self) -> None:
        self.data.add_voucher("bounty", 350)
        self.data.redeem("bounty", 100)
        self.assertEqual(self.data.vouchers["bounty"], 250)

    def test_redeeming_an_unknown_kind_is_harmless(self) -> None:
        self.data.add_voucher("bounty", 350)
        self.data.redeem("codex")
        self.assertEqual(self.data.voucher_total, 350)

    def test_the_total_is_both_halves(self) -> None:
        self.data.add_sample("A", 1_000_000, first_logged=True)
        self.data.add_voucher("bounty", 500)
        self.assertEqual(self.data.total, 5_000_500)

    def test_describe_is_readable(self) -> None:
        self.assertEqual(UnsoldData().describe(), "пусто")
        self.data.add_sample("A", 1_000_000, first_logged=True)
        self.data.add_voucher("bounty", 500)
        described = self.data.describe()
        self.assertIn("bio 1", described)
        self.assertIn("bounty", described)


class UnsoldStateTests(unittest.TestCase):
    """The journal side: what is accumulated, and what empties the hold."""

    def setUp(self) -> None:
        config = Config()
        self.table = ExobiologyTable()
        self.state = GameState(self.table, value_threshold=config.alerts.min_value)
        self.state.apply({"event": "FSDJump", "StarSystem": "Test", "SystemAddress": 1})

    def scan_organic(self, scan_type: str, *, was_logged: bool | None = False) -> None:
        self.state.apply(
            {
                "event": "ScanOrganic",
                "SystemAddress": 1,
                "Body": 6,
                "ScanType": scan_type,
                "Genus": STRATUM,
                "Species": STRATUM_TECTONICAS,
                "WasLogged": was_logged,
            }
        )

    def test_only_the_analyse_pass_adds_a_sample(self) -> None:
        """Log and Sample are earlier steps of the same sampling."""
        self.scan_organic("Log")
        self.scan_organic("Sample")
        self.assertEqual(self.state.unsold.bio_count, 0)
        self.scan_organic("Analyse")
        self.assertEqual(self.state.unsold.bio_count, 1)

    def test_the_sample_is_worth_five_times_when_nobody_logged_it(self) -> None:
        species = self.table.species(STRATUM_TECTONICAS)
        self.assertIsNotNone(species)
        self.scan_organic("Analyse", was_logged=False)
        self.assertEqual(self.state.unsold.bio_credits, species.value * 5)

    def test_an_already_logged_species_pays_the_base_value(self) -> None:
        species = self.table.species(STRATUM_TECTONICAS)
        self.scan_organic("Analyse", was_logged=True)
        self.assertEqual(self.state.unsold.bio_credits, species.value)

    def test_an_unknown_species_is_not_credited(self) -> None:
        self.state.apply(
            {
                "event": "ScanOrganic",
                "SystemAddress": 1,
                "Body": 6,
                "ScanType": "Analyse",
                "Species": "$Codex_Ent_NotARealSpecies_Name;",
                "WasLogged": False,
            }
        )
        self.assertEqual(self.state.unsold.bio_credits, 0)

    def test_selling_empties_the_hold(self) -> None:
        self.scan_organic("Analyse")
        self.assertGreater(self.state.unsold.bio_credits, 0)
        self.state.apply(
            {
                "event": "SellOrganicData",
                "MarketID": 1,
                "BioData": [{"Value": 100, "Bonus": 400}],
            }
        )
        self.assertEqual(self.state.unsold.bio_credits, 0)
        self.assertEqual(self.state.unsold.last_sale_credits, 500)

    def test_dying_loses_the_hold(self) -> None:
        """The whole reason the total is worth showing."""
        self.scan_organic("Analyse")
        self.state.apply({"event": "Bounty", "Reward": 1_000, "VictimFaction": "X"})
        self.assertGreater(self.state.unsold.total, 1_000)
        self.state.apply({"event": "Died", "KillerName": "X"})
        self.assertEqual(self.state.unsold.total, 0)

    def test_bounties_and_bonds_accumulate(self) -> None:
        self.state.apply({"event": "Bounty", "Reward": 1_000})
        self.state.apply({"event": "FactionKillBond", "Reward": 2_000})
        self.assertEqual(self.state.unsold.vouchers, {"bounty": 1_000, "bond": 2_000})

    def test_a_redeem_clears_the_type_it_names(self) -> None:
        self.state.apply({"event": "Bounty", "Reward": 1_000})
        self.state.apply({"event": "RedeemVoucher", "Type": "bounty", "Amount": 1_000})
        self.assertEqual(self.state.unsold.voucher_total, 0)

    def test_a_codex_redeem_does_not_clear_bounties(self) -> None:
        """RedeemVoucher names the type; codex is exobiology, not combat."""
        self.state.apply({"event": "Bounty", "Reward": 1_000})
        self.state.apply({"event": "RedeemVoucher", "Type": "codex", "Amount": 737_500})
        self.assertEqual(self.state.unsold.voucher_total, 1_000)

    def test_garbage_amounts_are_ignored(self) -> None:
        self.state.apply({"event": "Bounty", "Reward": "1000"})
        self.state.apply({"event": "FactionKillBond"})
        self.state.apply({"event": "SellOrganicData", "BioData": "nonsense"})
        self.assertEqual(self.state.unsold.total, 0)

    def test_a_missing_was_logged_pays_only_the_base_value(self) -> None:
        """The bonus is claimed only when the journal says so outright.

        WasLogged is present on every ScanOrganic in the journals this was built
        against (33 of them, all false), so this case does not arise in practice.
        Should it ever, claiming the x5 on an absent field would overstate what
        the commander is carrying, and the alert payout path reads the same flag
        the same way.
        """
        species = self.table.species(STRATUM_TECTONICAS)
        self.scan_organic("Analyse", was_logged=None)
        self.assertEqual(self.state.unsold.bio_credits, species.value)


if __name__ == "__main__":
    unittest.main()
