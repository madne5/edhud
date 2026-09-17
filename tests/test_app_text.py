"""Qt mangles a literal ampersand in widget text, which is not obvious."""

from __future__ import annotations

import unittest

from elite_hud.app import qt_text


class QtTextTests(unittest.TestCase):
    def test_an_ampersand_is_doubled(self) -> None:
        """Qt reads a single & as a mnemonic and does not draw it, so the
        faction "Traders & Explorers" was shown as "Traders  Explorers"."""
        self.assertEqual(qt_text("Traders & Explorers"), "Traders && Explorers")

    def test_text_without_one_is_untouched(self) -> None:
        self.assertEqual(qt_text("Граф"), "Граф")
        self.assertEqual(qt_text(""), "")

    def test_every_ampersand_is_doubled(self) -> None:
        self.assertEqual(qt_text("A&B&C"), "A&&B&&C")

    def test_a_label_containing_a_name_is_safe(self) -> None:
        self.assertEqual(
            qt_text("Отслеживается: Traders & Explorers Inc."),
            "Отслеживается: Traders && Explorers Inc.",
        )


if __name__ == "__main__":
    unittest.main()
