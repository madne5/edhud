"""Tests for configuration loading, defaults and validation."""

from __future__ import annotations

import tempfile
import tomllib
import unittest
from pathlib import Path

from elite_hud.config import Config, ensure_config_file


class DefaultsTests(unittest.TestCase):
    def test_defaults_are_sane(self) -> None:
        config = Config()
        self.assertEqual(config.overlay.position, "top-center")
        self.assertEqual(config.alerts.min_value, 7_000_000)
        self.assertTrue(config.overlay.click_through)
        self.assertTrue(config.overlay.always_on_top)
        self.assertEqual(
            config.overlay.segments, ["carrier", "system", "fss", "bio"]
        )

    def test_generated_toml_round_trips(self) -> None:
        text = Config().to_toml()
        parsed = tomllib.loads(text)  # must not raise
        self.assertIn("overlay", parsed)
        self.assertIn("labels", parsed["overlay"])
        self.assertEqual(parsed["overlay"]["labels"]["fss"], "FSS")

    def test_generated_toml_loads_back_to_the_same_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(Config().to_toml(), encoding="utf-8")
            loaded = Config.load(path)
        self.assertEqual(loaded.alerts.min_value, 7_000_000)
        self.assertEqual(loaded.overlay.font_family, "Consolas")
        self.assertEqual(loaded.overlay.labels.carrier, "ФК")


class LoadingTests(unittest.TestCase):
    def _load(self, text: str) -> Config:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text, encoding="utf-8")
            return Config.load(path)

    def test_partial_config_keeps_other_defaults(self) -> None:
        config = self._load("[alerts]\nmin_value = 2_500_000\nsound_enabled = false\n")
        self.assertEqual(config.alerts.min_value, 2_500_000)
        self.assertFalse(config.alerts.sound_enabled)
        self.assertEqual(config.overlay.position, "top-center")

    def test_nested_labels_are_merged(self) -> None:
        config = self._load("[overlay.labels]\nbio = \"EXO\"\n")
        self.assertEqual(config.overlay.labels.bio, "EXO")
        self.assertEqual(config.overlay.labels.fss, "FSS")

    def test_exobiology_overrides(self) -> None:
        config = self._load('[exobiology.values]\n"Stratum Tectonicas" = 21000000\n')
        self.assertEqual(config.exobiology_overrides, {"Stratum Tectonicas": 21_000_000})

    def test_unknown_keys_are_ignored(self) -> None:
        config = self._load("[overlay]\nnot_a_real_key = 5\nfont_size = 16\n")
        self.assertEqual(config.overlay.font_size, 16)

    def test_malformed_toml_falls_back_to_defaults(self) -> None:
        config = self._load("this is not toml at all =")
        self.assertEqual(config.alerts.min_value, 7_000_000)

    def test_missing_file_yields_defaults(self) -> None:
        config = Config.load(Path("/nonexistent/config.toml"))
        self.assertEqual(config.overlay.font_size, 13)


class ValidationTests(unittest.TestCase):
    def test_unknown_position_falls_back(self) -> None:
        config = self._load("[overlay]\nposition = \"middle-of-nowhere\"\n")
        self.assertEqual(config.overlay.position, "top-center")

    def test_unknown_segments_are_dropped(self) -> None:
        config = self._load('[overlay]\nsegments = ["system", "bogus"]\n')
        self.assertEqual(config.overlay.segments, ["system"])

    def test_opacity_and_volume_are_clamped(self) -> None:
        config = self._load("[overlay]\nopacity = 4.0\n[alerts]\nvolume = -1.0\n")
        self.assertEqual(config.overlay.opacity, 1.0)
        self.assertEqual(config.alerts.volume, 0.0)

    def test_unknown_sound_confidence_falls_back(self) -> None:
        config = self._load('[alerts]\nsound_min_confidence = "whenever"\n')
        self.assertEqual(config.alerts.sound_min_confidence, "guaranteed")

    def _load(self, text: str) -> Config:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text, encoding="utf-8")
            return Config.load(path)


class EnsureConfigTests(unittest.TestCase):
    def test_creates_once_and_then_leaves_it_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            self.assertTrue(ensure_config_file(path))
            path.write_text("[alerts]\nmin_value = 1\n", encoding="utf-8")
            self.assertFalse(ensure_config_file(path))
            self.assertEqual(Config.load(path).alerts.min_value, 1)


if __name__ == "__main__":
    unittest.main()
