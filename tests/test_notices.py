"""The short-lived lines: a material pickup, and a refused docking request.

Both are the same mechanism and the same shape -- the state records the facts,
the overlay renders them from the configuration -- so they are tested together
here. What matters is that a reason is never invented, that a category is named
and coloured, and that switching a line off actually switches it off.
"""

from __future__ import annotations

import unittest

from elite_hud.config import Config
from elite_hud.materials import CATEGORY_GLYPHS, MaterialNotice
from elite_hud.i18n import ENGLISH_MESSAGES, Messages
from elite_hud.notices import DockingNotice, NoticeStyle
from elite_hud.state import GameState


def style_from(config: Config) -> NoticeStyle:
    """The style the overlay builds, without needing a QApplication."""
    overlay = config.overlay
    materials = config.materials
    labels = overlay.labels
    return NoticeStyle(
        category_labels={
            "raw": labels.material_raw,
            "manufactured": labels.material_manufactured,
            "encoded": labels.material_encoded,
        },
        category_colours={
            "raw": materials.raw_color,
            "manufactured": materials.manufactured_color,
            "encoded": materials.encoded_color,
        },
        rarity_label=labels.rarity,
        total_label=labels.total,
        show_rarity=materials.rarity,
        show_total=materials.show_total,
        warning=overlay.warning,
        success=overlay.success,
        messages=config.messages,
    )


def style_from_en() -> NoticeStyle:
    """The same style, in English."""
    config = Config()
    config.overlay.language = "en"
    config.apply_language()
    return style_from(config)


class OverlayWiringTests(unittest.TestCase):
    """The style a notice is rendered with must be the one the overlay builds.

    ``style_from`` here re-implements ``HudWindow.notice_style`` by hand, so none
    of the tests above can see the overlay's own wiring: dropping
    ``messages=self.config.messages`` from that method made an English config render
    the docking line in Russian and left all of these green.
    """

    def _hud(self, language: str):
        from PySide6.QtWidgets import QApplication

        from tests.test_hud import QT_SKIP_REASON

        if QT_SKIP_REASON:
            self.skipTest(QT_SKIP_REASON)
        QApplication.instance() or QApplication([])
        from elite_hud.overlay.hud import HudWindow
        from elite_hud.state import GameState

        config = Config()
        config.overlay.language = language
        config.apply_language()
        hud = HudWindow(config, GameState())
        hud._available_width = lambda: 2560.0
        self.addCleanup(hud.close)
        return hud

    def test_a_docking_refusal_reads_in_the_chosen_language(self) -> None:
        hud = self._hud("en")
        hud.push_notice(DockingNotice(station="Bainbridge Market", reason="Distance"))
        self.assertEqual(
            hud.notice_text(),
            "Bainbridge Market: docking refused — too far from the station",
        )

    def test_and_in_russian_too(self) -> None:
        hud = self._hud("ru")
        hud.push_notice(DockingNotice(station="Bainbridge Market", reason="Distance"))
        self.assertIn("стыковка запрещена", hud.notice_text())

    def test_the_real_reason_table_reaches_the_bar(self) -> None:
        """A reason added to the table must not be shown as a raw symbol."""
        hud = self._hud("ru")
        hud.push_notice(DockingNotice(station="X", reason="JumpImminent"))
        self.assertEqual(hud.notice_text(), "X: стыковка запрещена — носитель вот-вот прыгнет")


class DockingNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.style = style_from(Config())

    def test_the_reason_is_shown_in_russian(self) -> None:
        notice = DockingNotice(station="Bainbridge Market", reason="Distance")
        rendered = notice.render(self.style)
        self.assertEqual(
            rendered.text,
            "Bainbridge Market: стыковка запрещена — слишком далеко от станции",
        )
        self.assertEqual(rendered.glyph, "warning")
        self.assertEqual(rendered.colour, Config().overlay.warning)

    #: Every reason the game sends, from a journal parser that enumerates them:
    #: ed-journals 0.9.0, ``DockingDeniedReason``. This project's own journals
    #: contain only Distance, so the list cannot be measured from them, and the
    #: test that read the expectations out of the same table the code reads could
    #: not notice a missing or invented reason either -- deleting Hostile from both
    #: languages kept it green, and the shipped table had "Offline", which the game
    #: never sends, while four real reasons were absent.
    GAME_REASONS = {
        "NoSpace": "все площадки заняты",
        "TooLarge": "корабль слишком большой для площадки",
        "Hostile": "станция враждебна",
        "Offences": "есть неоплаченные штрафы",
        "Distance": "слишком далеко от станции",
        "ActiveFighter": "сначала верните истребитель на борт",
        "RestrictedAccess": "нет разрешения на стыковку с этим носителем",
        "JumpImminent": "носитель вот-вот прыгнет",
        "NoReason": "причина не указана",
    }

    def test_the_reason_table_matches_the_reasons_the_game_sends(self) -> None:
        self.assertEqual(Messages().docking_reasons, self.GAME_REASONS)

    def test_every_documented_reason_is_translated(self) -> None:
        for reason, expected in self.GAME_REASONS.items():
            with self.subTest(reason=reason):
                rendered = DockingNotice(station="X", reason=reason).render(self.style)
                self.assertEqual(
                    rendered.text, f"X: стыковка запрещена — {expected}"
                )

    def test_the_reasons_follow_the_language(self) -> None:
        english = Messages(**ENGLISH_MESSAGES).docking_reasons
        self.assertEqual(set(english), set(self.GAME_REASONS), "the same reasons")
        self.assertEqual(english["JumpImminent"], "the carrier is about to jump")
        rendered = DockingNotice(station="X", reason="Distance").render(style_from_en())
        self.assertEqual(rendered.text, "X: docking refused — too far from the station")

    def test_an_unknown_reason_is_quoted_rather_than_guessed(self) -> None:
        """A reason we do not know must not be turned into a plausible one."""
        rendered = DockingNotice(station="X", reason="SomethingNew").render(self.style)
        self.assertIn("SomethingNew", rendered.text)

    def test_a_missing_reason_says_so(self) -> None:
        rendered = DockingNotice(station="X").render(self.style)
        self.assertIn("причина не указана", rendered.text)

    def test_a_missing_station_still_reads(self) -> None:
        rendered = DockingNotice(reason="NoSpace").render(self.style)
        self.assertTrue(rendered.text.startswith("станция:"))

    def test_the_state_queues_it(self) -> None:
        state = GameState()
        state.apply(
            {"event": "DockingDenied", "Reason": "Distance", "MarketID": 1,
             "StationName": "V3G-N1H", "StationType": "FleetCarrier"}
        )
        notices = state.drain_notices()
        self.assertEqual(len(notices), 1)
        self.assertIsInstance(notices[0], DockingNotice)
        self.assertEqual(notices[0].station, "V3G-N1H")

    def test_it_can_be_switched_off(self) -> None:
        state = GameState(show_docking_denied=False)
        state.apply({"event": "DockingDenied", "Reason": "Distance", "StationName": "X"})
        self.assertEqual(state.drain_notices(), [])

    def test_docking_that_succeeds_says_nothing(self) -> None:
        state = GameState()
        state.apply({"event": "DockingGranted", "MarketID": 1, "StationName": "X",
                     "LandingPad": 7})
        state.apply({"event": "Docked", "StationName": "X", "StationType": "Coriolis"})
        self.assertEqual(state.drain_notices(), [])


class MaterialCategoryTests(unittest.TestCase):
    """Each category gets its own word, colour and glyph."""

    def setUp(self) -> None:
        self.config = Config()
        self.style = style_from(self.config)

    def test_the_three_categories_are_named_differently(self) -> None:
        labels = (
            self.style.category_labels["raw"],
            self.style.category_labels["manufactured"],
            self.style.category_labels["encoded"],
        )
        self.assertEqual(labels, ("Сырьевой", "Промышленный", "Данные"))

    def test_each_category_has_its_own_colour_and_glyph(self) -> None:
        colours = {self.style.category_colours[k] for k in CATEGORY_GLYPHS}
        glyphs = set(CATEGORY_GLYPHS.values())
        self.assertEqual(len(colours), 3, "three categories need three colours")
        self.assertEqual(len(glyphs), 3, "three categories need three glyphs")
        self.assertEqual(CATEGORY_GLYPHS["manufactured"], "gear")
        self.assertEqual(CATEGORY_GLYPHS["encoded"], "signal")
        self.assertEqual(CATEGORY_GLYPHS["raw"], "gem")

    def test_a_pickup_names_its_category(self) -> None:
        notice = MaterialNotice(symbol="tungsten", name="Вольфрам", count=3,
                                rarity=3, total=79, category="Raw")
        rendered = notice.render(self.style)
        self.assertEqual(rendered.text, "+3 Вольфрам (Сырьевой, Редкость: 3)  Всего: 79")
        self.assertEqual(rendered.glyph, "gem")
        self.assertEqual(rendered.colour, self.config.materials.raw_color)

    def test_the_category_is_read_from_the_table_not_the_event(self) -> None:
        """MaterialCollected states a category, but the table is what we trust.

        The two agree for every material in the journals; using the table means
        an event that omits the field still produces a labelled line.
        """
        state = GameState(material_notify=True)
        state.apply({"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 284}]})
        state.apply({"event": "MaterialCollected", "Name": "sulphur",
                     "Name_Localised": "Сера", "Count": 1})
        notice = state.drain_notices()[0]
        self.assertEqual(notice.category, "Raw")
        # The event's own Category is not needed, and is not read.
        state.apply({"event": "MaterialCollected", "Name": "sulphur",
                     "Name_Localised": "Сера", "Count": 1, "Category": "Encoded"})
        self.assertEqual(state.drain_notices()[0].category, "Raw")

    def test_an_unknown_category_still_renders(self) -> None:
        notice = MaterialNotice(symbol="x", name="Нечто", count=1, rarity=0,
                                category="Thargoid")
        rendered = notice.render(self.style)
        self.assertEqual(rendered.text, "+1 Нечто")
        self.assertEqual(rendered.glyph, "leaf", "a shape we do know")

    def test_the_category_switch_replaces_the_word(self) -> None:
        notice = MaterialNotice(symbol="tungsten", name="Вольфрам", count=1,
                                rarity=3, total=5, category="Raw")
        self.assertEqual(notice.text(), "+1 Вольфрам (Редкость: 3)  Всего: 5")
        self.assertEqual(notice.text(category_label="Сырьевой"),
                         "+1 Вольфрам (Сырьевой, Редкость: 3)  Всего: 5")
        self.assertEqual(notice.text(category_label="Сырьевой", show_rarity=False,
                                     show_total=False), "+1 Вольфрам (Сырьевой)")

    def test_the_newest_journal_reaches_every_category(self) -> None:
        """All three exist in a real session, so all three must be reachable."""
        state = GameState(material_notify=True)
        state.apply({"event": "Materials",
                     "Raw": [{"Name": "tellurium", "Count": 1}],
                     "Manufactured": [{"Name": "galvanisingalloys", "Count": 1}],
                     "Encoded": [{"Name": "encryptedfiles", "Count": 1}]})
        for symbol in ("tellurium", "galvanisingalloys", "encryptedfiles"):
            state.apply({"event": "MaterialCollected", "Name": symbol, "Count": 1})
        categories = [n.category for n in state.drain_notices()]
        self.assertEqual(categories, ["Raw", "Manufactured", "Encoded"])
        for notice in (
            MaterialNotice(symbol="s", name="n", category=c)
            for c in categories
        ):
            with self.subTest(category=notice.category):
                self.assertIn(notice.category.capitalize(), notice.render(self.style).text[:200]
                              .replace("Сырьевой", "Raw").replace("Промышленный", "Manufactured")
                              .replace("Данные", "Encoded"))


if __name__ == "__main__":
    unittest.main()
