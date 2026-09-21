"""Two languages, one source of truth each, and the rules that keep them honest.

The tests here are mostly about drift: a label added without an English word, a
table that quietly loses a key, a config file that pins the wording for ever. All
three are silent failures in the product and loud ones here.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

import elite_hud.i18n as i18n
from elite_hud.config import Config, LabelConfig
from elite_hud.i18n import ENGLISH_LABELS, ENGLISH_MESSAGES, Messages


class CoverageTests(unittest.TestCase):
    """English must have a word for everything we can say."""

    def test_every_label_has_an_english_word(self) -> None:
        names = {f.name for f in fields(LabelConfig)}
        self.assertEqual(
            sorted(set(ENGLISH_LABELS) - names), [], "English labels that do not exist"
        )
        self.assertEqual(
            sorted(names - set(ENGLISH_LABELS)), [], "labels with no English word"
        )

    def test_every_message_has_an_english_word(self) -> None:
        names = {f.name for f in fields(Messages)}
        self.assertEqual(sorted(set(ENGLISH_MESSAGES) - names), [])
        self.assertEqual(sorted(names - set(ENGLISH_MESSAGES)), [])

    def test_the_english_labels_differ_from_the_russian_ones(self) -> None:
        """A copy-paste that leaves a Russian word in the English table.

        Three are legitimately the same -- "Raw" is not translated, and the
        language names name themselves -- so the list is explicit rather than
        empty, and adding one is a decision rather than an accident.
        """
        allowed = {"edsm_yes", "edsm_no", "material_raw", "material_manufactured",
                   "material_encoded", "tonnes"}
        same = {
            name
            for name, value in ENGLISH_LABELS.items()
            if value == getattr(LabelConfig(), name) and name not in allowed
        }
        self.assertEqual(sorted(same), [])

    def test_the_language_names_name_themselves(self) -> None:
        self.assertEqual(i18n.LANGUAGE_NAMES["ru"], "Русский")
        self.assertEqual(i18n.LANGUAGE_NAMES["en"], "English")
        self.assertEqual(set(i18n.LANGUAGE_NAMES), set(i18n.LANGUAGES))


class ResolutionTests(unittest.TestCase):
    def test_russian_is_the_default(self) -> None:
        self.assertEqual(i18n.normalise(""), "ru")
        self.assertEqual(i18n.normalise("ru"), "ru")
        self.assertEqual(i18n.labels("ru").balance, "баланс")

    def test_english_is_selected_by_code(self) -> None:
        self.assertEqual(i18n.normalise("EN"), "en")
        self.assertEqual(i18n.labels("en").balance, "balance")
        self.assertEqual(i18n.messages("en").quit, "Quit")

    def test_an_unknown_language_falls_back(self) -> None:
        with self.assertLogs("elite_hud.i18n", level="WARNING"):
            self.assertEqual(i18n.normalise("de"), "ru")
        self.assertEqual(i18n.labels("de").balance, "баланс")

    def test_a_translation_written_by_hand_wins(self) -> None:
        table = i18n.resolve_labels("en", {"balance": "БАЛАНС", "missions": "задания"})
        self.assertEqual(table.balance, "БАЛАНС")
        self.assertEqual(table.missions, "задания")

    def test_a_copy_of_our_own_word_does_not_pin_the_language(self) -> None:
        """The rule that makes a language switch work at all.

        Every config file written by 0.11 and earlier contains a full label table
        -- our own Russian defaults, dumped verbatim. Treating those as
        translations would mean switching to English changed nothing.
        """
        dumped = {f.name: getattr(LabelConfig(), f.name) for f in fields(LabelConfig)}
        table = i18n.resolve_labels("en", dumped)
        self.assertEqual(table.balance, "balance")
        self.assertEqual(table.missions, "missions")

    def test_an_unknown_key_is_ignored_rather_than_raising(self) -> None:
        with self.assertLogs("elite_hud.i18n", level="WARNING"):
            table = i18n.resolve_labels("ru", {"nonsense": "x"})
        self.assertEqual(table.balance, "баланс")


class ConfigLanguageTests(unittest.TestCase):
    def _load(self, text: str) -> Config:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text, encoding="utf-8")
            return Config.load(path)

    def test_the_language_is_read_from_the_file(self) -> None:
        config = self._load('[overlay]\nlanguage = "en"\n')
        self.assertEqual(config.overlay.language, "en")
        self.assertEqual(config.overlay.labels.balance, "balance")
        self.assertEqual(config.messages.quit, "Quit")

    def test_a_hand_written_label_survives_the_language(self) -> None:
        config = self._load(
            '[overlay]\nlanguage = "en"\n[overlay.labels]\nmissions = "TASKS"\n'
        )
        self.assertEqual(config.overlay.labels.missions, "TASKS")
        self.assertEqual(config.overlay.labels.balance, "balance")

    def test_a_dumped_russian_table_does_not_block_english(self) -> None:
        dumped = "\n".join(
            f'{f.name} = "{getattr(LabelConfig(), f.name)}"' for f in fields(LabelConfig)
        )
        config = self._load(f'[overlay]\nlanguage = "en"\n[overlay.labels]\n{dumped}\n')
        self.assertEqual(config.overlay.labels.balance, "balance")

    def test_switching_language_re_resolves_the_labels(self) -> None:
        """What the tray does: set the code, then apply."""
        config = Config()
        self.assertEqual(config.overlay.labels.balance, "баланс")
        config.overlay.language = "en"
        config.apply_language()
        self.assertEqual(config.overlay.labels.balance, "balance")
        self.assertEqual(config.messages.quit, "Quit")
        config.overlay.language = "ru"
        config.apply_language()
        self.assertEqual(config.overlay.labels.balance, "баланс")

    def test_the_language_is_written_out_and_read_back(self) -> None:
        config = Config()
        config.overlay.language = "en"
        config.apply_language()
        text = config.to_toml()
        self.assertIn('language = "en"', text)
        reloaded = self._load(text)
        self.assertEqual(reloaded.overlay.language, "en")
        self.assertEqual(reloaded.overlay.labels.missions, "missions")

    def test_the_internal_label_cache_never_reaches_the_file(self) -> None:
        """It is bookkeeping, not a setting, and must not be written as one."""
        config = self._load('[overlay.labels]\nmission_capacity = "x"\n')
        for line in config.to_toml().splitlines():
            self.assertNotIn("_file_labels", line)

    def test_every_language_renders_every_label(self) -> None:
        """No language may leave a label empty, whatever it is set to."""
        for language in i18n.LANGUAGES:
            config = Config()
            config.overlay.language = language
            config.apply_language()
            for field in fields(LabelConfig):
                with self.subTest(language=language, label=field.name):
                    self.assertTrue(
                        str(getattr(config.overlay.labels, field.name)).strip(),
                        f"{field.name} is empty in {language}",
                    )


class WiredThroughTests(unittest.TestCase):
    """The language reaches the parts that are not the bar."""

    def test_the_update_service_speaks_the_language(self) -> None:
        """What the service emits, not the table it was handed.

        Reading ``service.messages`` back only proves the table was stored: the
        service could emit hardcoded Russian and this would not notice. So a real
        event is triggered -- asking to install with nothing available -- and the
        message it emits is checked.
        """
        from elite_hud.config import UpdateConfig
        from elite_hud.update_service import UpdateService

        config = Config()
        config.overlay.language = "en"
        config.apply_language()

        events: list[tuple[str, str]] = []
        service = UpdateService(
            UpdateConfig(), messages=config.messages,
            on_event=lambda event: events.append((event.kind, event.message)),
        )
        service.download_and_install()  # nothing available: emits an error
        self.assertEqual(events, [("error", "no update is available")])

        russian = UpdateService(UpdateConfig(), messages=i18n.messages("ru"),
                                on_event=lambda event: events.append((event.kind, event.message)))
        russian.download_and_install()
        self.assertEqual(events[-1], ("error", "нет доступного обновления"))

    def test_network_failures_speak_the_language(self) -> None:
        """The text of the error the tray would show, in the chosen language."""
        from elite_hud.updater import GitHubClient, GitHubError

        for language, expected in (
            ("en", "no connection to GitHub"),
            ("ru", "нет связи с GitHub"),
        ):
            with self.subTest(language=language):
                client = GitHubClient(
                    "a/b", timeout=1, api_base="http://127.0.0.1:1",
                    messages=i18n.messages(language),
                )
                with self.assertRaises(GitHubError) as caught:
                    client.releases()
                self.assertIn(expected, str(caught.exception))

    def test_the_display_picker_speaks_the_language(self) -> None:
        from elite_hud.overlay.hud import HudWindow

        english = HudWindow.screen_choices(i18n.messages("en"))
        self.assertEqual(english[0][1], "Primary")
        self.assertEqual(english[-1][1], "The one under the cursor")
        russian = HudWindow.screen_choices(i18n.messages("ru"))
        self.assertEqual(russian[0][1], "Основной")

    def test_the_bar_renders_in_english(self) -> None:
        from PySide6.QtWidgets import QApplication

        from tests.test_hud import QT_SKIP_REASON

        if QT_SKIP_REASON:
            self.skipTest(QT_SKIP_REASON)
        QApplication.instance() or QApplication([])
        from elite_hud.overlay.hud import HudWindow
        from elite_hud.state import GameState

        config = Config()
        config.overlay.language = "en"
        config.apply_language()
        state = GameState()
        state.apply({"event": "FSDJump", "StarSystem": "Sol", "SystemAddress": 1})
        state.apply({"event": "LoadGame", "Credits": 1_000_000})
        hud = HudWindow(config, state)
        hud._available_width = lambda: 2560.0
        hud.rebuild()
        text = hud.bar_text()
        hud.close()
        self.assertIn("balance", text)
        self.assertNotIn("баланс", text)
        self.assertIn("Sol", text, "names are never translated")


if __name__ == "__main__":
    unittest.main()
