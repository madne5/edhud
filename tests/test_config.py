"""Tests for configuration loading, defaults and validation."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from elite_hud.config import (
    Config,
    ensure_config_file,
    is_writable_dir,
    resolve_config_path,
    user_config_dir,
)


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


class ConfigLocationTests(unittest.TestCase):
    """Where the config goes depends on how the program was installed.

    The installer runs elevated and places files under Program Files, but the
    program itself runs as the ordinary user on purpose -- so the install
    directory is read-only for it. Writing there unconditionally made a fresh
    install crash on first launch with PermissionError.
    """

    def setUp(self) -> None:
        self._frozen = getattr(sys, "frozen", None)
        self._executable = sys.executable
        self._had_frozen = hasattr(sys, "frozen")
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._had_frozen:
            sys.frozen = self._frozen  # type: ignore[attr-defined]
        elif hasattr(sys, "frozen"):
            del sys.frozen  # type: ignore[attr-defined]
        sys.executable = self._executable

    @staticmethod
    def _read_only_dir() -> Path:
        path = Path(tempfile.mkdtemp()) / "elite-hud"
        path.mkdir()
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
        return path

    def test_is_writable_dir_detects_a_read_only_directory(self) -> None:
        if os.geteuid() == 0:  # pragma: no cover - root ignores permissions
            self.skipTest("running as root; permissions are not enforced")
        path = self._read_only_dir()
        try:
            self.assertFalse(is_writable_dir(path))
            self.assertTrue(is_writable_dir(path.parent))
        finally:
            os.chmod(path, stat.S_IRWXU)

    def test_installed_copy_in_a_read_only_directory_uses_the_user_profile(self) -> None:
        if os.geteuid() == 0:  # pragma: no cover
            self.skipTest("running as root; permissions are not enforced")
        install_dir = self._read_only_dir()
        try:
            sys.frozen = True  # type: ignore[attr-defined]
            sys.executable = str(install_dir / "elite-hud.exe")
            resolved = resolve_config_path(None)
            self.assertNotEqual(resolved.parent, install_dir)
            self.assertEqual(resolved.parent, user_config_dir())
            self.assertEqual(resolved.name, "config.toml")
        finally:
            os.chmod(install_dir, stat.S_IRWXU)

    def test_portable_copy_keeps_the_config_next_to_the_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sys.frozen = True  # type: ignore[attr-defined]
            sys.executable = str(Path(tmp) / "elite-hud.exe")
            # resolve() on both sides: on macOS /var is a symlink to /private/var
            # and the implementation resolves the executable path.
            self.assertEqual(resolve_config_path(None), (Path(tmp) / "config.toml").resolve())

    def test_an_explicit_path_always_wins(self) -> None:
        explicit = Path("/tmp/somewhere/config.toml")
        sys.frozen = True  # type: ignore[attr-defined]
        self.assertEqual(resolve_config_path(explicit), explicit)

    def test_source_checkout_uses_the_repository_root(self) -> None:
        if hasattr(sys, "frozen"):
            del sys.frozen  # type: ignore[attr-defined]
        expected = Path(__file__).resolve().parent.parent / "config.toml"
        self.assertEqual(resolve_config_path(None), expected)


class EnsureConfigTests(unittest.TestCase):
    def test_an_unwritable_location_is_reported_not_raised(self) -> None:
        """A convenience file must never stop the HUD from starting."""
        if os.geteuid() == 0:  # pragma: no cover
            self.skipTest("running as root; permissions are not enforced")
        path = Path(tempfile.mkdtemp()) / "ro"
        path.mkdir()
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
        try:
            self.assertFalse(ensure_config_file(path / "config.toml"))
        finally:
            os.chmod(path, stat.S_IRWXU)

    def test_creates_once_and_then_leaves_it_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            self.assertTrue(ensure_config_file(path))
            path.write_text("[alerts]\nmin_value = 1\n", encoding="utf-8")
            self.assertFalse(ensure_config_file(path))
            self.assertEqual(Config.load(path).alerts.min_value, 1)


if __name__ == "__main__":
    unittest.main()
