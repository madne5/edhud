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
    add_missing_sections,
    ensure_config_file,
    is_writable_dir,
    resolve_config_path,
    set_config_value,
    set_update_mode,
    user_config_dir,
    SEGMENT_NAMES,
    STATUS_SEGMENT_NAMES,
    VALID_SEGMENTS,
    VALID_STATUS_SEGMENTS,
    set_config_list,
    toggle_segment,
)


class DefaultsTests(unittest.TestCase):
    def test_defaults_are_sane(self) -> None:
        config = Config()
        self.assertEqual(config.overlay.position, "top-center")
        self.assertTrue(config.overlay.click_through)
        self.assertTrue(config.overlay.always_on_top)
        self.assertEqual(
            config.overlay.segments,
        ["carrier", "system", "balance", "ship", "cargo", "missions"]
        )

    def test_generated_toml_round_trips(self) -> None:
        text = Config().to_toml()
        parsed = tomllib.loads(text)  # must not raise
        self.assertIn("overlay", parsed)
        self.assertIn("labels", parsed["overlay"])
        self.assertEqual(parsed["overlay"]["labels"]["missions"], "миссии")

    def test_generated_toml_loads_back_to_the_same_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(Config().to_toml(), encoding="utf-8")
            loaded = Config.load(path)
        self.assertEqual(loaded.overlay.font_family, "Consolas")
        self.assertEqual(loaded.overlay.labels.carrier, "ФК")


class LoadingTests(unittest.TestCase):
    def _load(self, text: str) -> Config:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text, encoding="utf-8")
            return Config.load(path)

    def test_unknown_keys_are_ignored(self) -> None:
        config = self._load("[overlay]\nnot_a_real_key = 5\nfont_size = 16\n")
        self.assertEqual(config.overlay.font_size, 16)

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
        config = self._load("[overlay]\nopacity = 4.0\n")
        self.assertEqual(config.overlay.opacity, 1.0)

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
        self.path.write_text("[carrier]\nspool_minutes = 5\n", encoding="utf-8")
        self.assertTrue(set_config_value(self.path, "overlay", "monitor", "1"))
        loaded = Config.load(self.path)
        self.assertEqual(loaded.overlay.monitor, "1")
        self.assertEqual(loaded.carrier.spool_minutes, 5)

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
            path.write_text("[carrier]\nspool_minutes = 1\n", encoding="utf-8")
            self.assertFalse(ensure_config_file(path))
            self.assertEqual(Config.load(path).carrier.spool_minutes, 1)


if __name__ == "__main__":
    unittest.main()


class SegmentTests(unittest.TestCase):
    """Hiding blocks: the vocabulary, and the order they come back in."""

    def test_every_segment_has_a_human_name(self) -> None:
        """A new segment with no entry would be invisible in the tray menu."""
        self.assertEqual(VALID_SEGMENTS - set(SEGMENT_NAMES), set())
        self.assertEqual(VALID_STATUS_SEGMENTS - set(STATUS_SEGMENT_NAMES), set())

    def test_the_name_tables_have_no_stale_entries(self) -> None:
        self.assertEqual(set(SEGMENT_NAMES) - VALID_SEGMENTS, set())
        self.assertEqual(set(STATUS_SEGMENT_NAMES) - VALID_STATUS_SEGMENTS, set())

    def test_turning_one_off_removes_it(self) -> None:
        order = list(SEGMENT_NAMES)
        self.assertEqual(
            toggle_segment(["carrier", "system", "cargo"], order, "system", False),
            ["carrier", "cargo"],
        )

    def test_turning_one_back_on_restores_the_menu_order(self) -> None:
        """Appending would silently rearrange the bar when a block returns."""
        order = list(SEGMENT_NAMES)
        # cargo sits between ship and missions in the menu, so it must come
        # back there rather than at the end.
        self.assertEqual(
            toggle_segment(["carrier", "missions"], order, "cargo", True),
            ["carrier", "cargo", "missions"],
        )

    def test_turning_on_something_already_on_does_not_duplicate_it(self) -> None:
        order = list(SEGMENT_NAMES)
        self.assertEqual(
            toggle_segment(["carrier", "cargo"], order, "cargo", True), ["carrier", "cargo"]
        )

    def test_turning_off_something_absent_is_harmless(self) -> None:
        order = list(SEGMENT_NAMES)
        self.assertEqual(toggle_segment(["carrier"], order, "cargo", False), ["carrier"])

    def test_an_unknown_segment_is_kept(self) -> None:
        """A config from a newer version must not lose its blocks to an older one."""
        order = list(SEGMENT_NAMES)
        result = toggle_segment(["carrier", "somethingNew"], order, "cargo", True)
        self.assertIn("somethingNew", result)
        self.assertIn("carrier", result)
        self.assertIn("cargo", result)

    def test_turning_everything_off_leaves_nothing(self) -> None:
        order = list(STATUS_SEGMENT_NAMES)
        current = list(order)
        for name in order:
            current = toggle_segment(current, order, name, False)
        self.assertEqual(current, [])


class ConfigListTests(unittest.TestCase):
    """Persisting a list without destroying the file's comments."""

    def _config(self, text: str) -> Path:
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_replaces_an_existing_list(self) -> None:
        path = self._config('[overlay]\nsegments = ["carrier", "system"]\n')
        self.assertTrue(
            set_config_list(path, "overlay", "segments", ["carrier", "system"])
        )
        reloaded = Config.load(path)
        self.assertEqual(reloaded.overlay.segments, ["carrier", "system"])

    def test_keeps_comments_and_other_keys(self) -> None:
        path = self._config(
            "# my notes\n[overlay]\n# which blocks\nsegments = [\"carrier\"]\nfont_size = 15\n"
        )
        set_config_list(path, "overlay", "segments", ["system"])
        text = path.read_text(encoding="utf-8")
        self.assertIn("# my notes", text)
        self.assertIn("# which blocks", text)
        self.assertIn("font_size = 15", text)
        self.assertEqual(Config.load(path).overlay.segments, ["system"])

    def test_adds_the_key_when_missing(self) -> None:
        path = self._config("[overlay]\nfont_size = 15\n")
        set_config_list(path, "overlay", "status_segments", ["mode"])
        reloaded = Config.load(path)
        self.assertEqual(reloaded.overlay.status_segments, ["mode"])
        self.assertEqual(reloaded.overlay.font_size, 15)

    def test_adds_the_section_when_missing(self) -> None:
        path = self._config("[journal]\n")
        set_config_list(path, "overlay", "segments", ["system"])
        self.assertEqual(Config.load(path).overlay.segments, ["system"])

    def test_writes_a_real_list_not_a_quoted_string(self) -> None:
        """The bug this function exists to avoid."""
        path = self._config("[overlay]\n")
        set_config_list(path, "overlay", "segments", ["system", "cargo"])
        self.assertIn('segments = ["system", "cargo"]', path.read_text(encoding="utf-8"))
        self.assertEqual(Config.load(path).overlay.segments, ["system", "cargo"])

    def test_a_missing_file_is_reported_not_created(self) -> None:
        self.assertFalse(
            set_config_list(Path("/nonexistent/config.toml"), "overlay", "segments", ["system"])
        )


class MissingSectionTests(unittest.TestCase):
    """A config written once never gains settings from later versions."""

    def _file(self, text: str) -> Path:
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_new_section_is_added(self) -> None:
        """Otherwise the commander looks for the setting and finds nothing."""
        path = self._file("[journal]\npath = ''\n")
        self.assertIn("carrier", add_missing_sections(path))
        self.assertEqual(Config.load(path).carrier.spool_minutes, 15.0)

    def test_existing_values_and_comments_survive(self) -> None:
        path = self._file('# keep me\n[journal]\npath = "D:/ED"\n')
        add_missing_sections(path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("# keep me", text)
        self.assertIn('path = "D:/ED"', text)
        self.assertEqual(Config.load(path).journal.path, "D:/ED")

    def test_the_label_table_is_never_written_out(self) -> None:
        """A file holding one language's wording would freeze that language,
        which is exactly what the localisation setting must be free to change."""
        path = self._file("[journal]\n")
        added = add_missing_sections(path)
        self.assertNotIn("overlay.labels", added)
        self.assertNotIn("[overlay.labels]", path.read_text(encoding="utf-8"))

    def test_it_is_idempotent(self) -> None:
        path = self._file("[journal]\n")
        add_missing_sections(path)
        self.assertEqual(add_missing_sections(path), [])

    def test_a_second_run_does_not_duplicate_a_section(self) -> None:
        path = self._file("[journal]\n")
        add_missing_sections(path)
        add_missing_sections(path)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("[carrier]"), 1)

    def test_a_missing_file_is_left_alone(self) -> None:
        self.assertEqual(add_missing_sections(Path("/nonexistent/config.toml")), [])

    def test_deleted_keys_inside_an_existing_section_are_not_restored(self) -> None:
        """The file promises that deleting a line falls back to the default."""
        path = self._file("[overlay]\nfont_size = 15\n")
        add_missing_sections(path)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("superpower_progress", text)
        self.assertEqual(Config.load(path).overlay.font_size, 15)

    def test_the_result_still_loads(self) -> None:
        path = self._file("[overlay]\nsegments = [\"system\"]\n")
        add_missing_sections(path)
        reloaded = Config.load(path)
        self.assertEqual(reloaded.overlay.segments, ["system"])
        self.assertEqual(reloaded.carrier.spool_minutes, 15.0)


class ConfigEscapingTests(unittest.TestCase):
    """A value that breaks the TOML takes the whole config with it."""

    def _path(self) -> Path:
        path = Path(tempfile.mkdtemp()) / "config.toml"
        ensure_config_file(path)
        return path

    def test_an_ampersand_round_trips(self) -> None:
        """The faction this was written for is "Traders & Explorers"."""
        path = self._path()
        set_config_value(path, "journal", "path", "Traders & Explorers")
        self.assertEqual(Config.load(path).journal.path, "Traders & Explorers")

    def test_a_quote_round_trips(self) -> None:
        path = self._path()
        set_config_value(path, "journal", "path", 'The "Best" Faction')
        self.assertEqual(Config.load(path).journal.path, 'The "Best" Faction')

    def test_a_backslash_round_trips(self) -> None:
        path = self._path()
        set_config_value(path, "journal", "path", "Back\\slash")
        self.assertEqual(Config.load(path).journal.path, "Back\\slash")

    def test_a_broken_value_does_not_discard_the_rest_of_the_file(self) -> None:
        """Config.load silently falls back to every default on a parse error,
        so one awkward character used to lose unrelated settings too."""
        path = self._path()
        set_config_value(path, "overlay", "font_size", "15")
        set_config_value(path, "journal", "path", 'Quote " here')
        reloaded = Config.load(path)
        self.assertEqual(reloaded.overlay.font_size, 15)
        self.assertEqual(reloaded.journal.path, 'Quote " here')


class SectionPlacementTests(unittest.TestCase):
    """Where a written key lands, and never declaring a table twice.

    Both failures here were silent: the caller was told the write succeeded, and
    the damage only showed up on the next start as a setting that would not
    stick, or as the entire file silently reverting to defaults.
    """

    def _file(self, text: str) -> Path:
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_key_goes_into_its_own_section_not_the_last_one(self) -> None:
        path = self._file('[journal]\npoll_interval = 1.0\n\n[carrier]\nspool_minutes = 5\n')
        set_config_value(path, "journal", "path", "Sol")
        reloaded = Config.load(path)
        self.assertEqual(reloaded.journal.path, "Sol")
        # The other section must be untouched: the key went into its own table,
        # not appended to whichever one happened to be last.
        self.assertEqual(reloaded.carrier.spool_minutes, 5.0)

    def test_a_deleted_key_is_restored_into_its_section(self) -> None:
        """The file promises deleting a line falls back to the default."""
        path = Path(tempfile.mkdtemp()) / "config.toml"
        ensure_config_file(path)
        text = path.read_text(encoding="utf-8").replace('name = ""\n', "", 1)
        path.write_text(text, encoding="utf-8")
        set_config_value(path, "journal", "path", "X")
        self.assertEqual(Config.load(path).journal.path, "X")

    def test_an_empty_section_gets_a_key_without_a_second_header(self) -> None:
        """A duplicate [table] makes the whole file unparseable in TOML."""
        path = self._file("[faction]\n")
        set_config_value(path, "journal", "path", "X")
        self.assertEqual(path.read_text(encoding="utf-8").count("[faction]"), 1)
        self.assertEqual(Config.load(path).journal.path, "X")

    def test_a_dotted_declaration_is_extended_with_a_dotted_key(self) -> None:
        """A bare key inserted after `faction.match = ...` would land at the
        top level, not in the table."""
        path = self._file('faction.match = "contains"\n')
        set_config_value(path, "journal", "path", "X")
        self.assertNotIn("[faction]", path.read_text(encoding="utf-8"))
        self.assertEqual(Config.load(path).journal.path, "X")

    def test_a_missing_section_is_created(self) -> None:
        path = self._file('[journal]\npath = ""\n')
        set_config_value(path, "carrier", "spool_minutes", "5")
        reloaded = Config.load(path)
        self.assertEqual(reloaded.carrier.spool_minutes, 5.0)
        self.assertEqual(reloaded.journal.path, "")

    def test_compound_values_are_not_split_or_dropped(self) -> None:
        path = Path(tempfile.mkdtemp()) / "config.toml"
        ensure_config_file(path)
        set_config_value(path, "journal", "path", 'A "B" \\ C & D')
        self.assertEqual(Config.load(path).journal.path, 'A "B" \\ C & D')


class SectionDetectionTests(unittest.TestCase):
    """A table declared twice breaks the file permanently, so detection must
    see every way TOML can declare one."""

    def _file(self, text: str) -> Path:
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_dotted_key_records_the_table_as_present(self) -> None:
        path = self._file('overlay.monitor = "1"\n')
        add_missing_sections(path)
        reloaded = Config.load(path)
        self.assertEqual(reloaded.overlay.monitor, "1")
        self.assertNotIn("[overlay]", path.read_text(encoding="utf-8"))

    def test_a_header_with_a_trailing_comment_counts_as_present(self) -> None:
        path = self._file("[journal] # journal folder\npath = \"\"\n")
        add_missing_sections(path)
        self.assertEqual(Config.load(path).journal.path, "")
        self.assertEqual(path.read_text(encoding="utf-8").count("[journal]"), 1)

    def test_a_one_line_dotted_config_survives_migration(self) -> None:
        """This shape used to become permanently unparseable."""
        path = self._file("overlay.enabled = false\n")
        add_missing_sections(path)
        self.assertFalse(Config.load(path).overlay.enabled)
        add_missing_sections(path)
        self.assertFalse(Config.load(path).overlay.enabled)


class MalformedSectionTests(unittest.TestCase):
    """A scalar where a table belongs is valid TOML and used to be fatal."""

    def _load(self, text: str) -> Config:
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text(text, encoding="utf-8")
        return Config.load(path)

    def test_a_boolean_section_does_not_stop_startup(self) -> None:
        self.assertEqual(self._load("overlay = false").overlay.font_size, 13)

    def test_a_number_section_does_not_stop_startup(self) -> None:
        self.assertEqual(self._load("overlay = 3").overlay.font_size, 13)

    def test_a_string_section_does_not_stop_startup(self) -> None:
        self.assertEqual(self._load('overlay = "top-center"').overlay.monitor, "primary")

    def test_other_settings_still_load_alongside_it(self) -> None:
        # Within validate()'s range, so the point is the surviving setting
        # rather than the clamp.
        config = self._load('overlay = false\n[carrier]\nspool_minutes = 45\n')
        self.assertEqual(config.carrier.spool_minutes, 45.0)
