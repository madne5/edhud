"""Material rarity lookup, holdings tracking and pickup notifications."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.materials import MaterialTable
from elite_hud.state import GameState


class MaterialTableTests(unittest.TestCase):
    def test_loads_the_bundled_table(self) -> None:
        table = MaterialTable()
        self.assertTrue(table.loaded)
        self.assertGreaterEqual(len(table), 130)

    def test_knows_a_raw_material(self) -> None:
        material = MaterialTable().get("sulphur")
        self.assertIsNotNone(material)
        self.assertEqual(material.name, "Sulphur")
        self.assertEqual(material.rarity, 1)
        self.assertEqual(material.kind, "Raw")

    def test_vanadium_is_rarity_two(self) -> None:
        """Worth pinning: an early draft of the panel format claimed five."""
        self.assertEqual(MaterialTable().rarity("vanadium"), 2)

    def test_symbols_are_case_insensitive(self) -> None:
        table = MaterialTable()
        self.assertEqual(table.rarity("Sulphur"), table.rarity("sulphur"))
        self.assertEqual(table.normalise(" Sulphur "), "sulphur")

    def test_an_unknown_symbol_is_none(self) -> None:
        self.assertIsNone(MaterialTable().get("notarealmaterial"))
        self.assertIsNone(MaterialTable().get(""))

    def test_thargoid_materials_are_absent_from_the_table(self) -> None:
        """The bundled snapshot has no Thargoid rows; the code must cope."""
        table = MaterialTable()
        self.assertIsNone(table.get("tg_causticcrystal"))
        self.assertEqual(table.rarity("tg_causticcrystal"), 0)

    def test_display_name_prefers_the_games_own_wording(self) -> None:
        table = MaterialTable()
        self.assertEqual(table.display_name("sulphur", "Сера"), "Сера")

    def test_display_name_falls_back_to_english(self) -> None:
        """An English client may omit Name_Localised entirely."""
        self.assertEqual(MaterialTable().display_name("sulphur", ""), "Sulphur")

    def test_display_name_for_an_unknown_material_uses_the_localised_name(self) -> None:
        self.assertEqual(
            MaterialTable().display_name("tg_causticcrystal", "Каустический кристалл"),
            "Каустический кристалл",
        )

    def test_display_name_for_an_unknown_material_without_one(self) -> None:
        self.assertEqual(MaterialTable().display_name("tg_causticcrystal"), "tg_causticcrystal")

    def test_a_missing_file_leaves_an_empty_table_rather_than_raising(self) -> None:
        """Losing rarity must not cost the whole feature."""
        table = MaterialTable(Path("/nonexistent/materials.json"))
        self.assertFalse(table.loaded)
        self.assertEqual(len(table), 0)
        self.assertIsNone(table.get("sulphur"))

    def test_rows_with_a_bad_rarity_are_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(
                json.dumps(
                    {
                        "rarity": {"good": 3, "high": 9, "low": 0, "text": "2"},
                        "names": {"good": "Good"},
                    }
                ),
                encoding="utf-8",
            )
            table = MaterialTable(path)
            self.assertEqual(table.rarity("good"), 3)
            self.assertEqual(table.rarity("high"), 0)
            self.assertEqual(table.rarity("low"), 0)
            self.assertEqual(table.rarity("text"), 0)

    def test_a_corrupt_file_is_survivable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text("{not json", encoding="utf-8")
            table = MaterialTable(path)
            self.assertFalse(table.loaded)


class MaterialStateTests(unittest.TestCase):
    def setUp(self) -> None:
        config = Config()
        self.state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            rarity_label="Редкость",
            total_label="Всего",
        )

    def collected(self, name: str, count: int = 1, localised: str = "") -> None:
        self.state.apply(
            {
                "event": "MaterialCollected",
                "Category": "Raw",
                "Name": name,
                "Name_Localised": localised,
                "Count": count,
            }
        )

    def notes(self):
        return [a for a in self.state.drain_announcements() if a.kind == "material"]

    # -- seeding ------------------------------------------------------------

    def test_a_materials_event_seeds_the_hold(self) -> None:
        self.state.apply(
            {
                "event": "Materials",
                "Raw": [{"Name": "sulphur", "Name_Localised": "Сера", "Count": 270}],
                "Manufactured": [{"Name": "shieldemitters", "Count": 51}],
                "Encoded": [{"Name": "scanarchives", "Count": 103}],
            }
        )
        self.assertTrue(self.state.materials_known)
        self.assertEqual(self.state.holdings["sulphur"], 270)
        self.assertEqual(self.state.holdings["shieldemitters"], 51)
        self.assertEqual(self.state.holdings["scanarchives"], 103)

    def test_seeding_does_not_announce_anything(self) -> None:
        """A hold is reported at startup; it is not a pickup."""
        self.state.apply(
            {"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 270}]}
        )
        self.assertEqual(self.notes(), [])

    def test_a_later_seed_replaces_rather_than_accumulates(self) -> None:
        self.state.apply({"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 270}]})
        self.state.apply({"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 285}]})
        self.assertEqual(self.state.holdings["sulphur"], 285)

    def test_seeding_tolerates_garbage(self) -> None:
        self.state.apply({"event": "Materials", "Raw": "nonsense", "Encoded": [None, "x"]})
        self.assertTrue(self.state.materials_known)

    # -- collection ---------------------------------------------------------

    def test_collecting_increments_the_hold(self) -> None:
        self.collected("sulphur", 3)
        self.assertEqual(self.state.holdings["sulphur"], 3)
        self.collected("sulphur", 1)
        self.assertEqual(self.state.holdings["sulphur"], 4)

    def test_the_notification_matches_the_requested_shape(self) -> None:
        self.collected("sulphur", 1, localised="Сера")
        note = self.notes()[0]
        self.assertEqual(note.title, "+1 Сера (Редкость: 1)")
        self.assertEqual(note.detail, "Всего: 1")
        self.assertEqual(note.glyph, "gem")

    def test_the_notification_reports_the_running_total(self) -> None:
        self.state.apply({"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 270}]})
        self.collected("sulphur", 1, localised="Сера")
        self.assertEqual(self.notes()[0].detail, "Всего: 271")

    def test_a_missing_count_counts_as_one(self) -> None:
        self.state.apply({"event": "MaterialCollected", "Name": "sulphur"})
        self.assertEqual(self.state.holdings["sulphur"], 1)

    def test_an_unknown_material_is_still_tracked_without_rarity(self) -> None:
        """Thargoid materials are missing from the bundled table."""
        self.collected("tg_causticcrystal", 1, localised="Каустический кристалл")
        self.assertEqual(self.state.holdings["tg_causticcrystal"], 1)
        note = self.notes()[0]
        self.assertEqual(note.title, "+1 Каустический кристалл")
        self.assertNotIn("Редкость", note.title)

    def test_rarity_can_be_switched_off(self) -> None:
        config = Config()
        state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            material_rarity=False,
        )
        state.apply(
            {"event": "MaterialCollected", "Name": "sulphur", "Name_Localised": "Сера",
             "Count": 1}
        )
        note = state.drain_announcements()[0]
        self.assertEqual(note.title, "+1 Сера")

    def test_notifications_can_be_switched_off_while_still_tracking(self) -> None:
        config = Config()
        state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            material_notify=False,
        )
        state.apply({"event": "MaterialCollected", "Name": "sulphur", "Count": 2})
        self.assertEqual(state.holdings["sulphur"], 2)
        self.assertEqual(state.drain_announcements(), [])

    def test_tracking_can_be_switched_off_entirely(self) -> None:
        config = Config()
        state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            material_enabled=False,
        )
        state.apply({"event": "Materials", "Raw": [{"Name": "sulphur", "Count": 270}]})
        state.apply({"event": "MaterialCollected", "Name": "sulphur", "Count": 2})
        self.assertFalse(state.materials_known)
        self.assertEqual(state.holdings, {})
        self.assertEqual(state.drain_announcements(), [])

    # -- removal ------------------------------------------------------------

    def test_discarding_reduces_the_hold(self) -> None:
        self.collected("sulphur", 5)
        self.state.apply({"event": "MaterialDiscarded", "Name": "sulphur", "Count": 2})
        self.assertEqual(self.state.holdings["sulphur"], 3)

    def test_the_hold_never_goes_negative(self) -> None:
        """The journal can disagree with our seed; believing it is not an option."""
        self.collected("sulphur", 1)
        self.state.apply({"event": "MaterialDiscarded", "Name": "sulphur", "Count": 9})
        self.assertEqual(self.state.holdings["sulphur"], 0)

    def test_synthesis_consumes_its_materials(self) -> None:
        self.collected("sulphur", 5)
        self.state.apply(
            {
                "event": "Synthesis",
                "Name": "FSD Basic",
                "Materials": [{"Name": "sulphur", "Count": 3}],
            }
        )
        self.assertEqual(self.state.holdings["sulphur"], 2)

    def test_engineering_consumes_its_ingredients(self) -> None:
        self.collected("sulphur", 5)
        self.state.apply(
            {"event": "EngineeringCraft", "Ingredients": [{"Name": "sulphur", "Count": 4}]}
        )
        self.assertEqual(self.state.holdings["sulphur"], 1)

    def test_a_trade_swaps_both_sides(self) -> None:
        self.collected("iron", 6)
        self.state.apply(
            {
                "event": "MaterialTrade",
                "Paid": {"Name": "iron", "Count": 6},
                "Received": {"Name": "vanadium", "Amount": 2},
            }
        )
        self.assertEqual(self.state.holdings["iron"], 0)
        self.assertEqual(self.state.holdings["vanadium"], 2)

    def test_missing_amounts_are_ignored(self) -> None:
        self.collected("iron", 6)
        self.state.apply({"event": "MaterialTrade", "Paid": {"Name": "iron"}})
        self.assertEqual(self.state.holdings["iron"], 6)


if __name__ == "__main__":
    unittest.main()


class DataPackagingTests(unittest.TestCase):
    """A data file that never reaches the exe fails silently in the field.

    It works in development, where the table is read straight from the source
    tree, and only the installed build is missing it -- the feature just quietly
    loses its data. The exe builder named a single file until this was added.
    """

    def setUp(self) -> None:
        self.repo = Path(__file__).resolve().parent.parent
        self.data_dir = self.repo / "elite_hud" / "data"
        self.build_script = (self.repo / "tools" / "build_exe.py").read_text(encoding="utf-8")

    def test_every_bundled_table_is_listed_by_the_exe_builder(self) -> None:
        names = sorted(path.name for path in self.data_dir.glob("*.json"))
        self.assertIn("exobiology.json", names)
        self.assertIn("materials.json", names)
        unlisted = [name for name in names if f'"{name}"' not in self.build_script]
        self.assertEqual(unlisted, [], "add these to the builder's required list")

    def test_the_builder_copies_the_whole_data_directory(self) -> None:
        """Listing files one by one is what let a new table go missing."""
        self.assertIn('data_dir', self.build_script)
        self.assertIn("elite_hud/data", self.build_script)

    def test_the_tables_load_from_where_the_package_puts_them(self) -> None:
        from elite_hud.materials import DATA_PATH as MATERIALS

        self.assertTrue(MATERIALS.is_file(), MATERIALS)
        self.assertEqual(MATERIALS.parent.name, "data")
        self.assertIsNotNone(MaterialTable(MATERIALS).get("iron"))
