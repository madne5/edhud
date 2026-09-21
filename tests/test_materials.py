"""The material pickup line: "+1 Сера (Редкость: 1)  Всего: 285".

This was deleted along with the notification centre it happened to live in, and
asked for back on its own. So it is now deliberately the whole of the
notification system: one transient line, no sound, no pulsing border, nothing to
dismiss. These tests pin the wording, the running total, and the two ways the
total can be wrong -- announced before the hold is known, and inflated by a
MaterialTrade read with the wrong keys.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from elite_hud.config import Config
from elite_hud.materials import MaterialTable, MaterialNotice
from elite_hud.state import GameState


def make_state(config: Config | None = None, **kwargs) -> GameState:
    config = config or Config()
    return GameState(
        materials_enabled=config.materials.enabled,
        material_notify=config.materials.notify_collected,
        rarity_label=config.overlay.labels.rarity,
        total_label=config.overlay.labels.total,
        **kwargs,
    )


class MaterialTableTests(unittest.TestCase):
    def test_the_bundled_table_loads(self) -> None:
        table = MaterialTable()
        self.assertTrue(table.loaded, "elite_hud/data/materials.json is missing")
        self.assertEqual(len(table), 137)

    def test_rarity_comes_from_the_table(self) -> None:
        """The journal never states rarity, in any event type."""
        table = MaterialTable()
        self.assertEqual(table.rarity("sulphur"), 1)
        self.assertEqual(table.rarity("Sulphur"), 1, "symbols are case-insensitive")
        self.assertEqual(table.rarity("unknownmaterial"), 0)

    def test_an_unknown_material_is_not_an_error(self) -> None:
        """A material added by a future update must not cost us the display."""
        table = MaterialTable()
        self.assertIsNone(table.get("brandnewmaterial"))
        self.assertEqual(table.display_name("brandnewmaterial", "Новьё"), "Новьё")

    def test_a_missing_table_costs_rarity_and_nothing_else(self) -> None:
        with TemporaryDirectory() as tmp:
            table = MaterialTable(Path(tmp) / "absent.json")
        self.assertFalse(table.loaded)
        # The journal's own localised name still carries the display.
        self.assertEqual(table.display_name("sulphur", "Сера"), "Сера")


class PickupNoticeTests(unittest.TestCase):
    def test_the_line_is_the_one_that_was_asked_for(self) -> None:
        state = make_state()
        state.apply({"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 284}]})
        state.apply(
            {"event": "MaterialCollected", "Name": "sulphur",
             "Name_Localised": "Сера", "Count": 1}
        )
        notices = state.drain_notices()
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].text(), "+1 Сера (Редкость: 1)  Всего: 285")

    def test_the_game_s_own_wording_is_used(self) -> None:
        """A Russian client gets Russian without us shipping a translation."""
        state = make_state()
        state.apply(
            {"event": "Materials",
             "Encoded": [{"Name": "shieldpatternanalysis", "Count": 9}]}
        )
        state.apply(
            {"event": "MaterialCollected", "Name": "shieldpatternanalysis",
             "Name_Localised": "Неполный анализ поглощения щита", "Count": 2}
        )
        text = state.drain_notices()[0].text()
        self.assertIn("Неполный анализ поглощения щита", text)
        self.assertIn("Всего: 11", text)

    def test_the_hold_is_unknown_until_a_materials_event_reports_it(self) -> None:
        """A pickup must not announce a total of one for a full hold.

        Materials fires at login and reports everything at once; a HUD started
        without history sees only the pickup. Reporting the total then would be
        a number the journal has not stated.
        """
        state = make_state()
        state.apply(
            {"event": "MaterialCollected", "Name": "sulphur",
             "Name_Localised": "Сера", "Count": 1}
        )
        notice = state.drain_notices()[0]
        self.assertIsNone(notice.total)
        self.assertEqual(notice.text(), "+1 Сера (Редкость: 1)")

    def test_notices_are_taken_once(self) -> None:
        state = make_state()
        state.apply({"event": "Materials", "Raw": []})
        state.apply({"event": "MaterialCollected", "Name": "iron",
                     "Name_Localised": "Железо", "Count": 1})
        self.assertEqual(len(state.drain_notices()), 1)
        self.assertEqual(state.drain_notices(), [])

    def test_a_batch_carries_every_pickup(self) -> None:
        """A mining laser fires several a second; the app shows the last and
        logs the rest, so the state must not drop them here."""
        state = make_state()
        state.apply({"event": "Materials", "Raw": [{"Name": "iron", "Count": 10}]})
        for _ in range(3):
            state.apply({"event": "MaterialCollected", "Name": "iron", "Count": 1})
        self.assertEqual(len(state.drain_notices()), 3)

    def test_display_switches_are_the_overlay_s_decision(self) -> None:
        notice = MaterialNotice(symbol="sulphur", name="Сера", count=1, rarity=1, total=285)
        self.assertEqual(notice.text(show_rarity=False), "+1 Сера  Всего: 285")
        self.assertEqual(notice.text(show_total=False), "+1 Сера (Редкость: 1)")
        self.assertEqual(notice.text(show_rarity=False, show_total=False), "+1 Сера")


class HoldingsTests(unittest.TestCase):
    def test_discarding_lowers_the_hold_without_breaking_the_floor(self) -> None:
        state = make_state()
        state.apply({"event": "Materials", "Raw": [{"Name": "iron", "Count": 5}]})
        state.apply({"event": "MaterialDiscarded", "Name": "iron", "Count": 2})
        self.assertEqual(state.holdings["iron"], 3)
        state.apply({"event": "MaterialDiscarded", "Name": "iron", "Count": 99})
        self.assertEqual(state.holdings["iron"], 0, "a count must never go negative")

    def test_a_trade_reads_the_keys_the_event_actually_uses(self) -> None:
        """Nested MaterialTrade objects use ``Material`` and ``Quantity``.

        Reading ``Name`` and ``Count`` instead made every trade a silent no-op,
        and the holdings stayed wrong for the rest of the session. The test that
        covered it asserted the invented keys on both sides, so it passed.
        """
        state = make_state()
        state.apply({"event": "Materials", "Raw": [{"Name": "iron", "Count": 100}]})
        state.apply(
            {
                "event": "MaterialTrade",
                "Paid": {"Material": "iron", "Quantity": 6},
                "Received": {"Material": "sulphur", "Quantity": 1},
            }
        )
        self.assertEqual(state.holdings["iron"], 94)
        self.assertEqual(state.holdings["sulphur"], 1)

    def test_synthesis_and_engineering_spend_materials(self) -> None:
        state = make_state()
        state.apply({"event": "Materials", "Raw": [{"Name": "iron", "Count": 40}]})
        state.apply({"event": "Synthesis", "Name": "FSD_Basic",
                     "Materials": [{"Name": "iron", "Count": 3}]})
        self.assertEqual(state.holdings["iron"], 37)
        state.apply({"event": "EngineeringCraft", "BlueprintName": "FSD_LongRange",
                     "Ingredients": [{"Name": "iron", "Count": 2}]})
        self.assertEqual(state.holdings["iron"], 35)

    def test_materials_can_be_switched_off_entirely(self) -> None:
        config = Config()
        config.materials.enabled = False
        state = make_state(config)
        state.apply({"event": "Materials", "Raw": [{"Name": "iron", "Count": 5}]})
        state.apply({"event": "MaterialCollected", "Name": "iron", "Count": 1})
        self.assertEqual(state.holdings, {})
        self.assertEqual(state.drain_notices(), [])

    def test_collection_can_be_tracked_without_being_announced(self) -> None:
        config = Config()
        config.materials.notify_collected = False
        state = make_state(config)
        state.apply({"event": "Materials", "Raw": [{"Name": "iron", "Count": 5}]})
        state.apply({"event": "MaterialCollected", "Name": "iron", "Count": 1})
        self.assertEqual(state.holdings["iron"], 6)
        self.assertEqual(state.drain_notices(), [])


class ConfigSectionTests(unittest.TestCase):
    def test_the_section_is_written_and_read_back(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            written = Config()
            written.materials.display_seconds = 7.5
            written.materials.rarity = False
            path.write_text(written.to_toml(), encoding="utf-8")
            loaded = Config.load(path)
        self.assertIn("[materials]", written.to_toml())
        self.assertEqual(loaded.materials.display_seconds, 7.5)
        self.assertFalse(loaded.materials.rarity)

    def test_an_older_file_gains_the_section(self) -> None:
        from elite_hud.config import add_missing_sections

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("[overlay]\nfont_size = 14\n", encoding="utf-8")
            added = add_missing_sections(path, Config())
            text = path.read_text(encoding="utf-8")
        self.assertIn("materials", added)
        self.assertIn("[materials]", text)
        self.assertIn("font_size = 14", text, "existing settings are preserved")

    def test_an_absurd_duration_is_clamped(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("[materials]\ndisplay_seconds = 600\n", encoding="utf-8")
            config = Config.load(path)
        self.assertEqual(config.materials.display_seconds, 30.0)


if __name__ == "__main__":
    unittest.main()
