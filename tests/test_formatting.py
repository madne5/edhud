"""Tests for the pure formatting helpers."""

from __future__ import annotations

import unittest

from elite_hud.formatting import format_countdown, format_credits


class FormatCreditsTests(unittest.TestCase):
    def test_millions(self) -> None:
        self.assertEqual(format_credits(19_010_800), "19.0M")
        self.assertEqual(format_credits(7_254_600), "7.3M")

    def test_billions(self) -> None:
        self.assertEqual(format_credits(95_054_000), "95.1M")
        self.assertEqual(format_credits(1_500_000_000), "1.5B")

    def test_thousands_and_small(self) -> None:
        self.assertEqual(format_credits(1_500), "2K")
        self.assertEqual(format_credits(999), "999")
        self.assertEqual(format_credits(0), "0")


class FormatCountdownTests(unittest.TestCase):
    def test_minutes(self) -> None:
        self.assertEqual(format_countdown(754), "12:34")

    def test_hours(self) -> None:
        self.assertEqual(format_countdown(3725), "1:02:05")

    def test_rounds_up_so_a_pending_jump_never_reads_zero(self) -> None:
        self.assertEqual(format_countdown(0.4), "00:01")
        self.assertEqual(format_countdown(0), "00:00")

    def test_negative_is_clamped(self) -> None:
        self.assertEqual(format_countdown(-90), "00:00")


if __name__ == "__main__":
    unittest.main()
