"""First-footfall policy and its wiring into the state machine."""

from __future__ import annotations

import unittest

from elite_hud.config import Config
from elite_hud.exobiology import ExobiologyTable
from elite_hud.footfall import BodySurvey, FootfallPolicy, is_biological
from elite_hud.notifications import NotificationCenter
from elite_hud.state import GameState

SYMBOL = "$SAA_SignalType_Biological;"
GEOLOGICAL = "$SAA_SignalType_Geological;"


def survey(**kwargs) -> BodySurvey:
    """A landable, un-walked body that qualifies unless a test says otherwise."""
    fields = {"body_id": 6, "name": "Test 4", "landable": True, "footfalled": False}
    fields.update(kwargs)
    return BodySurvey(**fields)


def signals(count: int = 1, kind: str = SYMBOL) -> list[dict]:
    return [{"Type": kind, "Count": count}]


class SignalTypeTests(unittest.TestCase):
    def test_matches_the_journal_symbol(self) -> None:
        self.assertTrue(is_biological(SYMBOL))

    def test_matches_the_readable_alias(self) -> None:
        # Spansh and some tools spell it out.
        self.assertTrue(is_biological("Biological"))

    def test_rejects_other_signal_types(self) -> None:
        self.assertFalse(is_biological(GEOLOGICAL))
        self.assertFalse(is_biological("$PlanetaryMiningLocation_Name;"))

    def test_rejects_a_localised_string(self) -> None:
        """Localised text must never drive logic -- the game may run in any language."""
        self.assertFalse(is_biological("Биологический"))
        self.assertFalse(is_biological("Биологический сигнал"))

    def test_only_the_sourced_alias_is_accepted(self) -> None:
        """The one readable form Spansh really returns, and nothing invented."""
        self.assertFalse(is_biological("Biological signal"))
        self.assertFalse(is_biological("bio"))

    def test_rejects_empty(self) -> None:
        self.assertFalse(is_biological(""))
        self.assertFalse(is_biological(None))


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = FootfallPolicy(require_biology=False)

    def test_accepts_a_landable_unwalked_body(self) -> None:
        self.assertTrue(self.policy.admits(survey()))

    def test_rejects_a_body_someone_has_walked_on(self) -> None:
        self.assertFalse(self.policy.admits(survey(footfalled=True)))

    def test_rejects_a_body_whose_footfall_state_is_unknown(self) -> None:
        """Unknown must fail closed: the claim cannot be taken back."""
        self.assertFalse(self.policy.admits(survey(footfalled=None)))

    def test_rejects_a_body_that_cannot_be_landed_on(self) -> None:
        self.assertFalse(self.policy.admits(survey(landable=False)))
        self.assertFalse(self.policy.admits(survey(landable=None)))

    def test_rejects_a_body_already_announced(self) -> None:
        body = survey(announced=True)
        self.assertFalse(self.policy.admits(body))

    def test_disabled_accepts_nothing(self) -> None:
        policy = FootfallPolicy(enabled=False, require_biology=False)
        self.assertFalse(policy.admits(survey()))

    def test_require_biology_needs_a_biological_signal(self) -> None:
        policy = FootfallPolicy(require_biology=True)
        self.assertFalse(policy.admits(survey(bio_signals=0)))
        self.assertTrue(policy.admits(survey(bio_signals=1)))

    def test_min_bio_signals_is_a_floor(self) -> None:
        policy = FootfallPolicy(require_biology=True, min_bio_signals=4)
        self.assertFalse(policy.admits(survey(bio_signals=3)))
        self.assertTrue(policy.admits(survey(bio_signals=4)))

    def test_min_bio_signals_is_ignored_without_require_biology(self) -> None:
        policy = FootfallPolicy(require_biology=False, min_bio_signals=4)
        self.assertTrue(policy.admits(survey(bio_signals=0)))

    def test_min_bio_signals_of_zero_still_needs_one_signal(self) -> None:
        """Asking for biology but accepting zero of them is a contradiction."""
        policy = FootfallPolicy(require_biology=True, min_bio_signals=0)
        self.assertFalse(policy.admits(survey(bio_signals=0)))
        self.assertTrue(policy.admits(survey(bio_signals=1)))

    def test_require_undiscovered_is_stricter(self) -> None:
        policy = FootfallPolicy(require_biology=False, require_undiscovered=True)
        self.assertFalse(policy.admits(survey(discovered=True)))
        self.assertFalse(policy.admits(survey(discovered=None)))
        self.assertTrue(policy.admits(survey(discovered=False)))


class BodySurveyTests(unittest.TestCase):
    def test_observe_scan_records_landing_data(self) -> None:
        body = BodySurvey(body_id=7)
        body.observe_scan(
            {
                "Landable": True,
                "WasFootfalled": False,
                "WasDiscovered": False,
                "PlanetClass": "Icy body",
            }
        )
        self.assertTrue(body.landable)
        self.assertIs(body.footfalled, False)
        self.assertIs(body.discovered, False)
        self.assertEqual(body.planet_class, "Icy body")

    def test_observe_scan_prefers_the_localised_class_for_display(self) -> None:
        body = BodySurvey(body_id=7)
        body.observe_scan({"PlanetClass": "Icy body", "PlanetClass_Localised": "Ледяное тело"})
        self.assertEqual(body.planet_class, "Ледяное тело")

    def test_observe_scan_ignores_wrong_types(self) -> None:
        body = BodySurvey(body_id=7)
        body.observe_scan({"Landable": "yes", "WasFootfalled": 1})
        self.assertIsNone(body.landable)
        self.assertIsNone(body.footfalled)

    def test_observe_signals_counts_only_biological(self) -> None:
        body = BodySurvey(body_id=7)
        body.observe_signals(signals(6) + [{"Type": GEOLOGICAL, "Count": 22}])
        self.assertEqual(body.bio_signals, 6)

    def test_observe_signals_keeps_the_highest_count(self) -> None:
        body = BodySurvey(body_id=7)
        body.observe_signals(signals(1))
        body.observe_signals(signals(4))
        body.observe_signals(signals(2))
        self.assertEqual(body.bio_signals, 4)

    def test_observe_signals_merges_genuses_without_duplicates(self) -> None:
        body = BodySurvey(body_id=7)
        body.observe_signals([], genuses=[{"Genus": "$a;"}])
        body.observe_signals([], genuses=[{"Genus": "$a;"}, {"Genus": "$b;"}])
        self.assertEqual(body.genuses, ("$a;", "$b;"))

    def test_observe_signals_tolerates_garbage(self) -> None:
        body = BodySurvey(body_id=7)
        body.observe_signals(None)
        body.observe_signals([None, "x", {"Count": 3}])
        self.assertEqual(body.bio_signals, 0)

    def test_describe_lists_what_is_known(self) -> None:
        body = survey(planet_class="Icy body", bio_signals=3)
        self.assertEqual(body.describe(), "Icy body · bio: 3")

    def test_describe_can_be_empty(self) -> None:
        self.assertEqual(BodySurvey(body_id=1).describe(), "")


class FootfallStateTests(unittest.TestCase):
    """The event ordering here is the one the real journals use."""

    def setUp(self) -> None:
        config = Config()
        self.state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            footfall=FootfallPolicy(),
            footfall_label="Первый след",
        )
        self.state.apply({"event": "FSDJump", "StarSystem": "Test", "SystemAddress": 123})

    def scan(self, **kwargs) -> None:
        event = {
            "event": "Scan",
            "SystemAddress": 123,
            "BodyID": 6,
            "BodyName": "Test 4",
            "Landable": True,
            "WasFootfalled": False,
            "WasDiscovered": False,
            "PlanetClass": "Icy body",
        }
        event.update(kwargs)
        self.state.apply(event)

    def body_signals(self, count: int = 3, **kwargs) -> None:
        event = {
            "event": "FSSBodySignals",
            "SystemAddress": 123,
            "BodyID": 6,
            "BodyName": "Test 4",
            "Signals": signals(count),
        }
        event.update(kwargs)
        self.state.apply(event)

    def announcements(self):
        return self.state.drain_announcements()

    def test_signals_before_scan_announces(self) -> None:
        """344 of 346 bodies in the test journals arrive in this order."""
        self.body_signals(6)
        self.assertEqual(self.announcements(), [])
        self.scan()
        notes = self.announcements()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].kind, "footfall")
        self.assertEqual(notes[0].title, "Первый след")
        self.assertIn("Test 4", notes[0].detail)
        self.assertIn("bio: 6", notes[0].detail)
        self.assertEqual(notes[0].tone, "success")

    def test_scan_before_signals_announces_on_the_dss_pass(self) -> None:
        """A DSS pass reports biology after the body was already resolved."""
        self.scan()
        self.assertEqual(self.announcements(), [])
        self.body_signals(2)
        self.assertEqual(len(self.announcements()), 1)

    def test_it_is_announced_only_once(self) -> None:
        self.body_signals(1)
        self.scan()
        self.assertEqual(len(self.announcements()), 1)
        self.scan()
        self.body_signals(1)
        self.assertEqual(self.announcements(), [])

    def test_a_walked_on_body_is_never_announced(self) -> None:
        self.body_signals(4)
        self.scan(WasFootfalled=True)
        self.assertEqual(self.announcements(), [])

    def test_a_body_without_biology_is_not_announced(self) -> None:
        self.state.apply(
            {
                "event": "FSSBodySignals",
                "SystemAddress": 123,
                "BodyID": 6,
                "BodyName": "Test 4",
                "Signals": [{"Type": GEOLOGICAL, "Count": 22}],
            }
        )
        self.scan()
        self.assertEqual(self.announcements(), [])

    def test_a_gas_giant_is_not_announced(self) -> None:
        self.body_signals(5)
        self.scan(Landable=False, PlanetClass="Gas giant")
        self.assertEqual(self.announcements(), [])

    def test_a_stale_system_signal_is_ignored(self) -> None:
        self.state.apply(
            {
                "event": "FSSBodySignals",
                "SystemAddress": 999,
                "BodyID": 6,
                "BodyName": "Elsewhere 4",
                "Signals": signals(3),
            }
        )
        self.scan()
        self.assertEqual(self.announcements(), [])

    def test_a_new_system_clears_the_records(self) -> None:
        self.body_signals(1)
        self.scan()
        self.assertEqual(len(self.announcements()), 1)
        self.state.apply({"event": "FSDJump", "StarSystem": "Other", "SystemAddress": 456})
        self.assertEqual(self.state.system.surveys, {})

    def test_the_notification_key_is_unique_per_body(self) -> None:
        """Two bodies in one system must not fold into one line."""
        self.body_signals(1)
        self.scan()
        self.body_signals(1, BodyID=7, BodyName="Test 5")
        self.scan(BodyID=7, BodyName="Test 5")

        centre = NotificationCenter(hold_seconds=5.0)
        centre.drain(self.announcements())
        self.assertEqual(len(centre), 2)
        self.assertEqual(
            sorted(item.key for item in centre.items),
            ["footfall:Test 4 · Icy body · bio: 1", "footfall:Test 5 · Icy body · bio: 1"],
        )

    def test_require_undiscovered_filters_known_bodies(self) -> None:
        config = Config()
        state = GameState(
            ExobiologyTable(),
            value_threshold=config.alerts.min_value,
            footfall=FootfallPolicy(require_undiscovered=True),
        )
        state.apply({"event": "FSDJump", "StarSystem": "Test", "SystemAddress": 123})
        state.apply(
            {
                "event": "FSSBodySignals",
                "SystemAddress": 123,
                "BodyID": 6,
                "BodyName": "Test 4",
                "Signals": signals(3),
            }
        )
        state.apply(
            {
                "event": "Scan",
                "SystemAddress": 123,
                "BodyID": 6,
                "BodyName": "Test 4",
                "Landable": True,
                "WasFootfalled": False,
                "WasDiscovered": True,
                "PlanetClass": "Icy body",
            }
        )
        self.assertEqual(state.drain_announcements(), [])


if __name__ == "__main__":
    unittest.main()
