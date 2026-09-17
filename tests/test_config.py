"""Tests for configuration loading, defaults and validation."""

from __future__ import annotations

import os
import stat
import sys
from unittest import mock
import tempfile
import tomllib
import unittest
from pathlib import Path

from elite_hud.config import (
    Config,
    ensure_config_file,
    is_writable_dir,
    resolve_config_path,
    set_config_value,
    set_update_mode,
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
            config.overlay.segments, ["carrier", "system", "balance", "fss", "bio"]
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

    Writability is patched rather than simulated with chmod: Windows ignores
    POSIX mode bits on directories, so a permission-based test would pass on
    Linux and macOS while silently testing nothing on the real target.
    """

    def setUp(self) -> None:
        self._had_frozen = hasattr(sys, "frozen")
        self._frozen = getattr(sys, "frozen", None)
        self._executable = sys.executable
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._had_frozen:
            sys.frozen = self._frozen  # type: ignore[attr-defined]
        elif hasattr(sys, "frozen"):
            del sys.frozen  # type: ignore[attr-defined]
        sys.executable = self._executable

    def test_installed_copy_uses_the_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "elite-hud"
            install_dir.mkdir()
            sys.frozen = True  # type: ignore[attr-defined]
            sys.executable = str(install_dir / "elite-hud.exe")
            with mock.patch("elite_hud.config.is_writable_dir", return_value=False):
                resolved = resolve_config_path(None)
            self.assertEqual(resolved, user_config_dir() / "config.toml")

    def test_portable_copy_keeps_the_config_next_to_the_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "elite-hud"
            install_dir.mkdir()
            sys.frozen = True  # type: ignore[attr-defined]
            sys.executable = str(install_dir / "elite-hud.exe")
            with mock.patch("elite_hud.config.is_writable_dir", return_value=True):
                resolved = resolve_config_path(None)
            self.assertEqual(resolved, install_dir.resolve() / "config.toml")

    def test_an_explicit_path_always_wins(self) -> None:
        explicit = Path(tempfile.gettempdir()) / "custom" / "config.toml"
        sys.frozen = True  # type: ignore[attr-defined]
        self.assertEqual(resolve_config_path(explicit), explicit)

    def test_source_checkout_uses_the_repository_root(self) -> None:
        if hasattr(sys, "frozen"):
            del sys.frozen  # type: ignore[attr-defined]
        expected = Path(__file__).resolve().parent.parent / "config.toml"
        self.assertEqual(resolve_config_path(None), expected)


@unittest.skipIf(sys.platform == "win32", "POSIX permission bits only")
class RealPermissionsTests(unittest.TestCase):
    """One genuine end-to-end check that a read-only directory is detected."""

    def setUp(self) -> None:
        geteuid = getattr(os, "geteuid", None)
        if geteuid is not None and geteuid() == 0:  # pragma: no cover
            self.skipTest("running as root; permissions are not enforced")

    def test_is_writable_dir_detects_a_read_only_directory(self) -> None:
        path = Path(tempfile.mkdtemp()) / "elite-hud"
        path.mkdir()
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
        try:
            self.assertFalse(is_writable_dir(path))
            self.assertTrue(is_writable_dir(path.parent))
        finally:
            os.chmod(path, stat.S_IRWXU)

    def test_an_unwritable_directory_is_reported_not_raised(self) -> None:
        path = Path(tempfile.mkdtemp()) / "ro"
        path.mkdir()
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
        try:
            self.assertFalse(ensure_config_file(path / "config.toml"))
        finally:
            os.chmod(path, stat.S_IRWXU)


class MonitorSettingTests(unittest.TestCase):
    def test_default_is_the_primary_display(self) -> None:
        self.assertEqual(Config().overlay.monitor, "primary")

    def test_the_value_survives_a_save_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            text = Config().to_toml().replace('monitor = "primary"', 'monitor = "1"')
            path.write_text(text, encoding="utf-8")
            self.assertEqual(Config.load(path).overlay.monitor, "1")


class ConfigEditorTests(unittest.TestCase):
    """Editing one key must not disturb the rest of the file.

    Rewriting the whole file from the defaults would discard whatever comments
    the user added, so the editor touches a single line.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "config.toml"
        self.addCleanup(self._tmp.cleanup)

    def test_edits_an_existing_key(self) -> None:
        self.path.write_text(
            "# my comment\n[overlay]\nmonitor = \"primary\"\nfont_size = 14\n",
            encoding="utf-8",
        )
        self.assertTrue(set_config_value(self.path, "overlay", "monitor", "2"))
        text = self.path.read_text(encoding="utf-8")
        self.assertIn('monitor = "2"', text)
        self.assertIn("# my comment", text)
        self.assertIn("font_size = 14", text)

    def test_appends_a_missing_key_to_an_existing_section(self) -> None:
        self.path.write_text("[overlay]\nfont_size = 14\n", encoding="utf-8")
        self.assertTrue(set_config_value(self.path, "overlay", "monitor", "1"))
        self.assertEqual(Config.load(self.path).overlay.monitor, "1")
        self.assertEqual(Config.load(self.path).overlay.font_size, 14)

    def test_creates_a_missing_section(self) -> None:
        self.path.write_text("[alerts]\nmin_value = 5\n", encoding="utf-8")
        self.assertTrue(set_config_value(self.path, "overlay", "monitor", "1"))
        loaded = Config.load(self.path)
        self.assertEqual(loaded.overlay.monitor, "1")
        self.assertEqual(loaded.alerts.min_value, 5)

    def test_does_not_touch_the_same_key_in_another_section(self) -> None:
        self.path.write_text(
            '[overlay]\nmonitor = "primary"\n\n[update]\nmode = "install"\n',
            encoding="utf-8",
        )
        self.assertTrue(set_config_value(self.path, "update", "mode", "off"))
        loaded = Config.load(self.path)
        self.assertEqual(loaded.update.mode, "off")
        self.assertEqual(loaded.overlay.monitor, "primary")

    def test_the_result_still_parses_as_toml(self) -> None:
        self.path.write_text(Config().to_toml(), encoding="utf-8")
        self.assertTrue(set_config_value(self.path, "overlay", "monitor", "1"))
        tomllib.loads(self.path.read_text(encoding="utf-8"))  # must not raise

    def test_a_missing_file_is_reported_not_raised(self) -> None:
        self.assertFalse(set_config_value(Path(self._tmp.name) / "absent.toml", "overlay", "monitor", "1"))

    def test_set_update_mode_still_works(self) -> None:
        self.path.write_text(Config().to_toml(), encoding="utf-8")
        self.assertTrue(set_update_mode(self.path, "notify"))
        self.assertEqual(Config.load(self.path).update.mode, "notify")
        self.assertFalse(set_update_mode(self.path, "nonsense"))


class EnsureConfigTests(unittest.TestCase):
    def test_a_broken_location_is_reported_not_raised(self) -> None:
        """A convenience file must never stop the HUD from starting."""
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "not-a-directory"
            blocker.write_text("x", encoding="utf-8")
            # The parent is a file, so creating the config is impossible on any
            # platform -- no permission bits involved.
            self.assertFalse(ensure_config_file(blocker / "config.toml"))

    def test_creates_once_and_then_leaves_it_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            self.assertTrue(ensure_config_file(path))
            path.write_text("[alerts]\nmin_value = 1\n", encoding="utf-8")
            self.assertFalse(ensure_config_file(path))
            self.assertEqual(Config.load(path).alerts.min_value, 1)


if __name__ == "__main__":
    unittest.main()
