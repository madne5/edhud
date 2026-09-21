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
from elite_hud.notices import DOCKING_REASONS, DockingNotice, NoticeStyle
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
    )


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

    def test_every_documented_reason_is_translated(self) -> None:
        for reason in DOCKING_REASONS:
            with self.subTest(reason=reason):
                rendered = DockingNotice(station="X", reason=reason).render(self.style)
                self.assertIn(DOCKING_REASONS[reason], rendered.text)

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
