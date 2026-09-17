"""Fines and notoriety."""

from __future__ import annotations

import unittest

from elite_hud.config import Config
from elite_hud.crime import MAX_NOTORIETY, CrimeRecord
from elite_hud.exobiology import ExobiologyTable
from elite_hud.state import GameState

#: The Crime section as the journals really carry it.
REAL_CRIME = {
    "Notoriety": 0,
    "Fines": 369,
    "Total_Fines": 2_288_015,
    "Bounties_Received": 122,
    "Total_Bounties": 439_400,
    "Highest_Bounty": 104_900,
}


class CrimeRecordTests(unittest.TestCase):
    def test_a_fresh_record_is_clean(self) -> None:
        record = CrimeRecord()
        self.assertTrue(record.clean)
        self.assertFalse(record.notorious)
        self.assertEqual(record.describe(), "clean")

    def test_statistics_fills_the_lifetime_totals(self) -> None:
        record = CrimeRecord()
        record.observe_statistics(REAL_CRIME)
        self.assertEqual(record.notoriety, 0)
        self.assertEqual(record.lifetime_fines, 2_288_015)
        self.assertEqual(record.lifetime_crimes, 369)
        self.assertEqual(record.lifetime_bounties_received, 122)
        self.assertEqual(record.lifetime_bounty_total, 439_400)
        self.assertEqual(record.highest_bounty, 104_900)

    def test_a_notorious_commander_is_not_clean(self) -> None:
        record = CrimeRecord()
        record.observe_statistics({"Notoriety": 3})
        self.assertTrue(record.notorious)
        self.assertFalse(record.clean)

    def test_notoriety_is_clamped_to_the_game_range(self) -> None:
        record = CrimeRecord()
        record.observe_statistics({"Notoriety": 99})
        self.assertEqual(record.notoriety, MAX_NOTORIETY)
        record.observe_statistics({"Notoriety": -4})
        self.assertEqual(record.notoriety, 0)

    def test_garbage_statistics_are_ignored(self) -> None:
        record = CrimeRecord()
        record.observe_statistics({"Notoriety": "high", "Total_Fines": None, "Fines": True})
        self.assertIsNone(record.notoriety)
        self.assertEqual(record.lifetime_fines, 0)
        self.assertEqual(record.lifetime_crimes, 0)

    def test_a_fine_accumulates(self) -> None:
        record = CrimeRecord()
        record.add_fine(200, crime="dockingMinorTresspass")
        record.add_fine(50)
        self.assertEqual(record.fines, 250)
        self.assertEqual(record.last_crime, "dockingMinorTresspass")
        self.assertFalse(record.clean)

    def test_a_zero_or_negative_fine_is_not_a_debt(self) -> None:
        record = CrimeRecord()
        record.add_fine(0)
        record.add_fine(-100)
        self.assertEqual(record.fines, 0)
        self.assertTrue(record.clean)

    def test_paying_all_fines_clears_them(self) -> None:
        record = CrimeRecord()
        record.add_fine(200)
        record.pay_fines(200, all_fines=True)
        self.assertEqual(record.fines, 0)

    def test_a_partial_payment_subtracts(self) -> None:
        record = CrimeRecord()
        record.add_fine(500)
        record.pay_fines(200)
        self.assertEqual(record.fines, 300)

    def test_the_debt_never_goes_negative(self) -> None:
        record = CrimeRecord()
        record.add_fine(100)
        record.pay_fines(9999)
        self.assertEqual(record.fines, 0)

    def test_paying_with_no_amount_clears_everything(self) -> None:
        """PayFines without a figure can only mean the lot."""
        record = CrimeRecord()
        record.add_fine(300)
        record.pay_fines()
        self.assertEqual(record.fines, 0)

    def test_a_bounty_against_the_commander_counts(self) -> None:
        record = CrimeRecord()
        record.add_bounty(104_900)
        record.add_bounty(0)
        self.assertEqual(record.session_bounties, 2)
        self.assertEqual(record.session_bounty_value, 104_900)
        self.assertFalse(record.clean)

    def test_describe_lists_what_is_owed(self) -> None:
        record = CrimeRecord()
        record.observe_statistics({"Notoriety": 3})
        record.add_fine(200)
        described = record.describe()
        self.assertIn("notoriety 3", described)
        self.assertIn("200", described)


class CrimeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        config = Config()
        self.state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)

    def test_statistics_are_read_from_the_journal(self) -> None:
        self.state.apply({"event": "Statistics", "Crime": REAL_CRIME})
        self.assertEqual(self.state.crime.lifetime_fines, 2_288_015)
        self.assertEqual(self.state.crime.notoriety, 0)
        # The real commander is clean, so nothing is shown.
        self.assertTrue(self.state.crime.clean)

    def test_statistics_without_a_crime_section_is_harmless(self) -> None:
        self.state.apply({"event": "Statistics", "Bank_Account": {}})
        self.assertIsNone(self.state.crime.notoriety)

    def test_the_real_docking_fine(self) -> None:
        """The one CommitCrime in the journals."""
        self.state.apply(
            {
                "event": "CommitCrime",
                "CrimeType": "dockingMinorTresspass",
                "Faction": "United German Commanders",
                "Fine": 200,
            }
        )
        self.assertEqual(self.state.crime.fines, 200)
        self.assertEqual(self.state.crime.last_crime, "dockingMinorTresspass")

    def test_the_real_fine_payment(self) -> None:
        self.state.apply({"event": "CommitCrime", "Fine": 200})
        self.state.apply({"event": "PayFines", "Amount": 200, "AllFines": True, "ShipID": 19})
        self.assertEqual(self.state.crime.fines, 0)

    def test_a_commit_crime_without_a_fine_is_harmless(self) -> None:
        self.state.apply({"event": "CommitCrime", "CrimeType": "murder"})
        self.assertEqual(self.state.crime.fines, 0)

    def test_a_zero_reward_bounty_is_a_bounty_against_the_commander(self) -> None:
        """The same event reports both payouts and prices on your head."""
        self.state.apply({"event": "Bounty", "Reward": 0, "VictimFaction": "Someone"})
        self.assertEqual(self.state.crime.session_bounties, 1)
        self.assertEqual(self.state.crime.session_bounty_value, 0)
        # And it must not be mistaken for money earned.
        self.assertEqual(self.state.unsold.voucher_total, 0)

    def test_a_real_reward_is_still_a_voucher(self) -> None:
        self.state.apply({"event": "Bounty", "Reward": 1000, "VictimFaction": "Pirate"})
        self.assertEqual(self.state.unsold.voucher_total, 1000)
        self.assertEqual(self.state.crime.session_bounties, 0)

    def test_a_missing_reward_is_ignored(self) -> None:
        self.state.apply({"event": "Bounty", "VictimFaction": "Pirate"})
        self.assertEqual(self.state.unsold.voucher_total, 0)
        self.assertEqual(self.state.crime.session_bounties, 0)


if __name__ == "__main__":
    unittest.main()
