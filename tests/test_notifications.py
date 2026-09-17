"""Timed notification behaviour, tested against a clock we control."""

from __future__ import annotations

import unittest

from elite_hud.notifications import (
    ENTER_SLIDE,
    Notification,
    NotificationCenter,
)
from elite_hud.state import Announcement


class Clock:
    """A monotonic clock that only moves when a test tells it to."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class NotificationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.centre = NotificationCenter(
            hold_seconds=5.0, fade_in=0.2, fade_out=0.5, clock=self.clock
        )

    def pushed(self, **kwargs) -> Notification:
        fields = {"key": "k", "title": "Заголовок"}
        fields.update(kwargs)
        return self.centre.push(Notification(**fields))

    # -- lifetime -----------------------------------------------------------

    def test_a_new_notification_starts_transparent(self) -> None:
        self.pushed()
        entry = self.centre.rendered()[0]
        self.assertAlmostEqual(entry.opacity, 0.0)
        # It slides down into place from above.
        self.assertAlmostEqual(entry.offset, -ENTER_SLIDE)

    def test_opacity_reaches_full_at_the_end_of_the_fade_in(self) -> None:
        self.pushed()
        self.clock.advance(0.2)
        entry = self.centre.rendered()[0]
        self.assertAlmostEqual(entry.opacity, 1.0)
        self.assertAlmostEqual(entry.offset, 0.0)
        self.assertTrue(entry.settled)

    def test_it_holds_at_full_opacity(self) -> None:
        self.pushed()
        self.clock.advance(2.5)
        entry = self.centre.rendered()[0]
        self.assertAlmostEqual(entry.opacity, 1.0)
        self.assertTrue(entry.settled)

    def test_it_fades_out_after_the_hold(self) -> None:
        self.pushed(hold=5.0)
        self.clock.advance(5.25)
        entry = self.centre.rendered()[0]
        self.assertTrue(0.0 < entry.opacity < 1.0)
        # Leaving drifts up by less than the entrance slide.
        self.assertTrue(0.0 < entry.offset < ENTER_SLIDE)

    def test_a_fully_faded_notification_is_dropped_by_tick(self) -> None:
        self.pushed(hold=5.0)
        self.clock.advance(5.5)
        self.assertEqual(self.centre.rendered(), [])
        self.centre.tick()
        self.assertEqual(len(self.centre), 0)

    def test_animating_stops_once_everything_has_settled(self) -> None:
        """A HUD that never stops repainting burns frames inside a running game."""
        self.pushed()
        self.assertTrue(self.centre.animating())
        self.clock.advance(0.2)
        self.assertFalse(self.centre.animating())

        # It must go quiet again after the fade-out, without waiting for the
        # caller to tick the item away. Default hold is 5 s, fade-out 0.5 s.
        self.clock.advance(5.4)
        self.assertEqual(self.centre.rendered(), [])
        self.assertFalse(self.centre.animating())

    def test_the_centre_default_hold_applies_when_none_is_given(self) -> None:
        item = self.pushed()
        self.assertAlmostEqual(item.hold, 5.0)
        self.clock.advance(4.9)
        self.assertTrue(self.centre.rendered()[0].settled)
        self.clock.advance(0.2)
        self.assertFalse(self.centre.rendered()[0].settled)

    def test_a_zero_hold_still_animates_its_fade_out(self) -> None:
        self.pushed(hold=0.0)
        self.clock.advance(0.25)
        entry = self.centre.rendered()[0]
        self.assertTrue(0.0 < entry.opacity < 1.0)

    def test_hold_is_overridable_per_notification(self) -> None:
        self.pushed(hold=20.0)
        self.clock.advance(10.0)
        self.assertTrue(self.centre.rendered()[0].settled)

    # -- folding repeats ----------------------------------------------------

    def test_repeating_a_key_folds_into_one_notification(self) -> None:
        for _ in range(3):
            self.pushed(key="material", title="Ванадий")
            self.clock.advance(0.1)
        self.assertEqual(len(self.centre), 1)
        self.assertEqual(self.centre.items[0].count, 3)
        self.assertTrue(self.centre.items[0].text().endswith("x3"))

    def test_folding_restarts_the_clock(self) -> None:
        self.pushed(key="material", hold=5.0)
        self.clock.advance(4.5)
        self.pushed(key="material", hold=5.0)
        self.clock.advance(4.5)
        # Would have expired twice over without the refresh.
        self.assertTrue(self.centre.rendered()[0].settled)

    def test_folding_keeps_the_original_position(self) -> None:
        first = self.pushed(key="a", title="Первое")
        self.clock.advance(0.1)
        self.pushed(key="b", title="Второе")
        self.clock.advance(0.1)
        self.pushed(key="a", title="Первое")
        self.assertIs(self.centre.items[0], first)

    def test_folding_accepts_new_wording(self) -> None:
        self.pushed(key="k", title="Старое", detail="")
        self.clock.advance(0.1)
        self.pushed(key="k", title="Новое", detail="подробность")
        self.assertEqual(self.centre.items[0].title, "Новое")
        self.assertEqual(self.centre.items[0].detail, "подробность")

    def test_different_details_stay_separate_lines(self) -> None:
        """Empire and Federation promotions are both kind="rank"."""
        self.centre.announce(Announcement(kind="rank", title="Граф", detail="Empire"))
        self.clock.advance(0.1)
        self.centre.announce(
            Announcement(kind="rank", title="Уорент-офицер", detail="Federation")
        )
        self.assertEqual(len(self.centre), 2)

    def test_key_for_separates_kinds(self) -> None:
        self.assertEqual(NotificationCenter.key_for("rank", "Empire"), "rank:Empire")
        self.assertEqual(NotificationCenter.key_for("carrier"), "carrier")

    # -- limits -------------------------------------------------------------

    def test_no_more_than_max_visible_are_kept(self) -> None:
        centre = NotificationCenter(max_visible=2, clock=self.clock)
        for key in ("a", "b", "c"):
            centre.push(Notification(key=key, title=key.upper()))
        self.assertEqual([item.key for item in centre.items], ["b", "c"])

    def test_max_visible_is_at_least_one(self) -> None:
        centre = NotificationCenter(max_visible=0, clock=self.clock)
        centre.push(Notification(key="a", title="A"))
        self.assertEqual(len(centre), 1)

    # -- announcements ------------------------------------------------------

    def test_announce_carries_the_announcement_fields(self) -> None:
        self.centre.announce(
            Announcement(
                kind="footfall",
                title="Первый след",
                detail="Blu Theia AV-F d11-1 B 3",
                glyph="star",
                tone="success",
                value=5,
            )
        )
        item = self.centre.items[0]
        self.assertEqual(item.key, "footfall:Blu Theia AV-F d11-1 B 3")
        self.assertEqual(item.title, "Первый след")
        self.assertEqual(item.detail, "Blu Theia AV-F d11-1 B 3")
        self.assertEqual(item.glyph, "star")
        self.assertEqual(item.tone, "success")
        self.assertEqual(item.value, 5)

    def test_drain_announces_everything_in_order(self) -> None:
        items = self.centre.drain(
            [
                Announcement(kind="rank", title="Граф", detail="Empire"),
                Announcement(
                    kind="rank", title="Уорент-офицер", detail="Federation"
                ),
            ]
        )
        self.assertEqual([item.title for item in items], ["Граф", "Уорент-офицер"])

    def test_overrides_win_over_the_announcement(self) -> None:
        self.centre.announce(
            Announcement(kind="rank", title="Граф", detail="Empire", tone="accent"),
            tone="danger",
            hold=30.0,
        )
        self.assertEqual(self.centre.items[0].tone, "danger")
        self.assertAlmostEqual(self.centre.items[0].hold, 30.0)

    def test_an_unknown_tone_falls_back_to_accent(self) -> None:
        self.centre.announce(Announcement(kind="rank", title="X", tone="chartreuse"))
        self.assertEqual(self.centre.items[0].tone, "accent")

    # -- bits and pieces ----------------------------------------------------

    def test_clear_empties_everything(self) -> None:
        self.pushed()
        self.centre.clear()
        self.assertEqual(len(self.centre), 0)

    def test_snapshot_is_plain_text(self) -> None:
        self.pushed(key="m", title="Ванадий", detail="Редкость: 5")
        self.assertEqual(self.centre.snapshot(), ["Ванадий  Редкость: 5"])

    def test_text_omits_an_empty_detail(self) -> None:
        self.pushed(title="Только заголовок")
        self.assertEqual(self.centre.items[0].text(), "Только заголовок")


if __name__ == "__main__":
    unittest.main()


class AnnouncementPipelineTests(unittest.TestCase):
    """State -> app -> HUD handoff, without Qt in the way.

    The state layer was raising these and nothing read them, so a rank gained
    never reached the screen. This pins the whole path.
    """

    def _state(self):
        from elite_hud.config import Config
        from elite_hud.exobiology import ExobiologyTable
        from elite_hud.state import GameState

        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        state.apply({"event": "Fileheader", "Odyssey": True})
        return state

    def _publisher(self, state):
        """A stand-in app exposing the real method and nothing else."""
        from elite_hud.app import HudApp

        class FakeHud:
            def __init__(self) -> None:
                self.pushed = []

            def push_notification(self, notification) -> None:
                self.pushed.append(notification)

        class Publisher:
            _publish_announcements = HudApp._publish_announcements

            def __init__(self) -> None:
                self.state = state
                self.hud = FakeHud()

        return Publisher()

    def test_a_promotion_reaches_the_hud(self) -> None:
        state = self._state()
        state.apply({"event": "Rank", "Empire": 8, "Federation": 6, "Combat": 3})
        # Promotion carries the NEW index and is the only event that reports a
        # rank changing mid-session.
        state.apply({"event": "Promotion", "Empire": 9})

        publisher = self._publisher(state)
        publisher._publish_announcements()

        self.assertEqual(len(publisher.hud.pushed), 1)
        note = publisher.hud.pushed[0]
        self.assertEqual(note.title, "Граф")
        self.assertEqual(note.key, "rank:Empire")
        self.assertEqual(note.tone, "success")
        self.assertEqual(note.glyph, "star")
        self.assertEqual(note.value, 9)
        # The stored rank must move too, or the status row keeps showing the
        # old title until the game restarts.
        self.assertEqual(state.ranks["Empire"], 9)

    def test_two_simultaneous_promotions_stay_separate(self) -> None:
        state = self._state()
        state.apply({"event": "Rank", "Empire": 8, "Federation": 5})
        state.apply({"event": "Promotion", "Empire": 9, "Federation": 6})

        publisher = self._publisher(state)
        publisher._publish_announcements()

        keys = [note.key for note in publisher.hud.pushed]
        self.assertEqual(sorted(keys), ["rank:Empire", "rank:Federation"])

    def test_announcements_are_drained_not_replayed(self) -> None:
        """A second tick must not re-announce the same promotion."""
        state = self._state()
        state.apply({"event": "Rank", "Empire": 8})
        state.apply({"event": "Promotion", "Empire": 9})

        publisher = self._publisher(state)
        publisher._publish_announcements()
        publisher._publish_announcements()
        self.assertEqual(len(publisher.hud.pushed), 1)

    def test_nothing_is_raised_without_a_promotion(self) -> None:
        state = self._state()
        state.apply({"event": "Rank", "Empire": 8})
        publisher = self._publisher(state)
        publisher._publish_announcements()
        self.assertEqual(publisher.hud.pushed, [])


class EvictionAndTimerTests(unittest.TestCase):
    """Two failures that only appear once time is involved."""

    def setUp(self) -> None:
        self.clock = Clock()
        self.centre = NotificationCenter(
            max_visible=2, hold_seconds=5.0, fade_in=0.2, fade_out=0.5, clock=self.clock
        )

    def _push(self, key: str, title: str = "T"):
        self.centre.push(Notification(key=key, title=title))

    def test_the_line_that_expires_first_gives_way(self) -> None:
        """Evicting by position killed the line a fold had just refreshed."""
        self._push("a")
        self.clock.advance(4.0)
        self._push("b")
        self.clock.advance(0.1)
        # Refreshing "a" extends its life past "b"'s, but leaves it first in
        # the list.
        self._push("a")
        self.clock.advance(0.1)
        self._push("c")
        self.assertIn("a", [item.key for item in self.centre.items])
        self.assertNotIn("b", [item.key for item in self.centre.items])

    def test_the_timer_stays_on_through_the_fade_out(self) -> None:
        """Otherwise nothing drives the fade, and the item is never evicted."""
        self._push("a")
        self.clock.advance(0.2)
        self.assertFalse(self.centre.animating())
        self.clock.advance(4.4)  # 4.6: inside the last fade_out before expiry
        self.assertTrue(self.centre.animating())

    def test_the_timer_stops_once_the_fade_is_over(self) -> None:
        self._push("a")
        self.clock.advance(5.6)
        self.assertEqual(self.centre.rendered(), [])
        self.assertFalse(self.centre.animating())

    def test_an_expired_notification_is_not_folded_into(self) -> None:
        """The symptom: a stale line absorbing a fresh event as 'x2'."""
        self._push("a", "First")
        self.clock.advance(60.0)
        self.centre.tick()
        self.assertEqual(len(self.centre), 0)
        self._push("a", "Second")
        self.assertEqual(self.centre.items[0].count, 1)
        self.assertEqual(self.centre.items[0].title, "Second")
