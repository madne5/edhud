"""Tests for the exobiology value table and its confidence model."""

from __future__ import annotations

import unittest

from elite_hud.exobiology import Confidence, ExobiologyTable

THRESHOLD = 7_000_000


class ExobiologyLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = ExobiologyTable()

    def test_species_by_codex_key(self) -> None:
        species = self.table.species("$Codex_Ent_Stratum_07_Name;")
        self.assertIsNotNone(species)
        assert species is not None
        self.assertEqual(species.name, "Stratum Tectonicas")
        self.assertEqual(species.value, 19_010_800)

    def test_species_by_localised_name(self) -> None:
        species = self.table.species("Bacterium Informem")
        self.assertIsNotNone(species)
        assert species is not None
        self.assertEqual(species.value, 8_418_000)

    def test_variant_suffix_is_stripped(self) -> None:
        species = self.table.species("Stratum Tectonicas - Lime")
        self.assertIsNotNone(species)
        assert species is not None
        self.assertEqual(species.name, "Stratum Tectonicas")

    def test_genus_by_codex_key_and_name(self) -> None:
        by_key = self.table.genus("$Codex_Ent_Clypeus_Genus_Name;")
        by_name = self.table.genus("Clypeus")
        self.assertIsNotNone(by_key)
        self.assertIs(by_key, by_name)

    def test_unknown_organic_is_none(self) -> None:
        self.assertIsNone(self.table.species("Unobtainium Weed"))
        self.assertIsNone(self.table.genus("$Codex_Ent_Nonsense_Genus_Name;"))

    def test_corrected_concha_value(self) -> None:
        # EDMC-BioScan still ships the 2**24-1 placeholder here.
        species = self.table.species("Concha Biconcavis")
        assert species is not None
        self.assertEqual(species.value, 19_010_800)

    def test_non_sellable_organics_never_resolve(self) -> None:
        # Brain Trees / Anemones / Sinuous Tubers have no Vista Genomics payout.
        for name in ("Roseum Brain Tree", "Luteolum Anemone", "Viride Sinuous Tubers"):
            self.assertIsNone(self.table.species(name), name)


class GenusAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = ExobiologyTable()

    def _assess(self, genus_name: str) -> Confidence:
        genus = self.table.genus(genus_name)
        return self.table.assess_genus(genus, THRESHOLD)

    def test_every_clypeus_species_clears_the_threshold(self) -> None:
        self.assertIs(self._assess("Clypeus"), Confidence.GUARANTEED)

    def test_every_recepta_species_clears_the_threshold(self) -> None:
        self.assertIs(self._assess("Recepta"), Confidence.GUARANTEED)

    def test_stratum_is_only_possible(self) -> None:
        # Stratum spans 1.36M .. 19.0M, so a genus sighting cannot promise 7M.
        self.assertIs(self._assess("Stratum"), Confidence.POSSIBLE)

    def test_cheap_genera_never_alert(self) -> None:
        self.assertIs(self._assess("Fungoida"), Confidence.NONE)
        self.assertIs(self._assess("Electricae"), Confidence.NONE)

    def test_species_assessment_is_confirmed(self) -> None:
        genus = self.table.genus("Stratum")
        assert genus is not None
        best = genus.best()
        assert best is not None
        self.assertIs(self.table.assess_species(best, THRESHOLD), Confidence.CONFIRMED)

    def test_threshold_ordering(self) -> None:
        self.assertGreater(Confidence.CONFIRMED.rank, Confidence.GUARANTEED.rank)
        self.assertGreater(Confidence.GUARANTEED.rank, Confidence.POSSIBLE.rank)
        self.assertGreater(Confidence.POSSIBLE.rank, Confidence.NONE.rank)


class OverrideTests(unittest.TestCase):
    def test_override_recomputes_genus_envelope(self) -> None:
        table = ExobiologyTable()
        self.assertIs(table.assess_genus(table.genus("Fungoida"), THRESHOLD), Confidence.NONE)
        applied = table.apply_overrides({"Fungoida Bullarum": 9_000_000})
        self.assertEqual(applied, 1)
        genus = table.genus("Fungoida")
        assert genus is not None
        self.assertIs(table.assess_genus(genus, THRESHOLD), Confidence.POSSIBLE)
        self.assertEqual(genus.max_value, 9_000_000)

    def test_unknown_override_is_ignored(self) -> None:
        table = ExobiologyTable()
        self.assertEqual(table.apply_overrides({"Not A Real Species": 5}), 0)


if __name__ == "__main__":
    unittest.main()
