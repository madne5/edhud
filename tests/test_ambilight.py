"""Ambilight: what the lamp shows, and when.

The lamp is a network device driven by an obfuscated third-party library, so the
tests here cover the two things that can actually be checked without hardware:
the pure logic that decides the colour, and the worker that sends it.
"""

from __future__ import annotations

import unittest

from elite_hud.ambilight import (
    FLAG_FSD_CHARGING,
    FLAG_IN_DANGER,
    FLAG_INTERDICTED,
    OFF,
    AmbilightService,
    AmbilightShow,
    FeelinLightDriver,
    LightDriver,
    NullDriver,
    Situation,
    scale,
)
from elite_hud.config import Config
from elite_hud.status import parse_status


class Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingDriver(LightDriver):
    def __init__(self) -> None:
        self.sent: list[tuple[int, int, int]] = []
        self.closed = False

    def apply(self, colour) -> None:
        self.sent.append(tuple(colour))

    def close(self) -> None:
        self.closed = True


class ExplodingDriver(LightDriver):
    def apply(self, colour) -> None:
        raise RuntimeError("lamp on fire")


class SituationTests(unittest.TestCase):
    def test_a_plain_status_is_idle(self) -> None:
        situation = Situation.from_flags(0)
        self.assertTrue(situation.idle)

    def test_each_flag_is_read(self) -> None:
        self.assertTrue(Situation.from_flags(FLAG_FSD_CHARGING).charging)
        self.assertTrue(Situation.from_flags(FLAG_IN_DANGER).in_danger)
        self.assertTrue(Situation.from_flags(FLAG_INTERDICTED).interdicted)

    def test_the_status_file_flags_match_the_light_flags(self) -> None:
        """Two modules decode the same bits; they must agree."""
        snapshot = parse_status({"Flags": FLAG_FSD_CHARGING | FLAG_IN_DANGER | FLAG_INTERDICTED})
        self.assertTrue(snapshot.fsd_charging)
        self.assertTrue(snapshot.in_danger)
        self.assertTrue(snapshot.being_interdicted)
        self.assertFalse(Situation.from_flags(snapshot.flags).idle)


class ScaleTests(unittest.TestCase):
    def test_full_brightness_is_unchanged(self) -> None:
        self.assertEqual(scale((10, 20, 30), 1.0), (10, 20, 30))

    def test_zero_is_off(self) -> None:
        self.assertEqual(scale((255, 255, 255), 0.0), OFF)

    def test_out_of_range_factors_are_clamped(self) -> None:
        self.assertEqual(scale((255, 255, 255), 5.0), (255, 255, 255))
        self.assertEqual(scale((255, 255, 255), -1.0), OFF)


class ChargingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.show = AmbilightShow(charge_period=2.0)

    def test_it_breathes_rather_than_blinking(self) -> None:
        """A bright sample either side of the peak, and a dark one at the ends."""
        dark = self.show.frame(0.0, Situation(charging=True))
        rising = self.show.frame(0.5, Situation(charging=True))
        peak = self.show.frame(1.0, Situation(charging=True))
        self.assertEqual(dark, OFF)
        self.assertGreater(peak[2], rising[2])
        self.assertGreater(rising[2], 0)

    def test_the_colour_is_blue(self) -> None:
        peak = self.show.frame(1.0, Situation(charging=True))
        self.assertEqual(peak[0], 0)
        self.assertEqual(peak[1], 0)
        self.assertGreater(peak[2], 100)

    def test_it_repeats_every_period(self) -> None:
        self.assertEqual(
            self.show.frame(0.4, Situation(charging=True)),
            self.show.frame(2.4, Situation(charging=True)),
        )

    def test_it_stops_when_the_charge_ends(self) -> None:
        self.assertNotEqual(self.show.frame(1.0, Situation(charging=True)), OFF)
        self.assertEqual(self.show.frame(1.0, Situation()), OFF)


class InterdictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.show = AmbilightShow(interdiction_period=1.0, interdiction_duty=0.5)

    def test_it_strobes(self) -> None:
        lit = self.show.frame(0.1, Situation(interdicted=True))
        dark = self.show.frame(0.7, Situation(interdicted=True))
        self.assertEqual(lit, (255, 0, 0))
        self.assertEqual(dark, OFF)

    def test_it_is_red(self) -> None:
        colour = self.show.frame(0.1, Situation(interdicted=True))
        self.assertGreater(colour[0], 200)
        self.assertEqual(colour[1], 0)
        self.assertEqual(colour[2], 0)


class DangerTests(unittest.TestCase):
    def test_it_is_a_steady_red_glow(self) -> None:
        show = AmbilightShow(danger_colour=(255, 0, 0), danger_level=0.5)
        first = show.frame(0.0, Situation(in_danger=True))
        later = show.frame(10.0, Situation(in_danger=True))
        self.assertEqual(first, later, "a glow must not flicker")
        self.assertEqual(first, (128, 0, 0))

    def test_it_goes_out_when_the_danger_passes(self) -> None:
        show = AmbilightShow()
        self.assertNotEqual(show.frame(0.0, Situation(in_danger=True)), OFF)
        self.assertEqual(show.frame(0.1, Situation()), OFF)


class PriorityTests(unittest.TestCase):
    """Being interdicted outranks being shot at, which outranks charging."""

    def setUp(self) -> None:
        self.show = AmbilightShow()

    def test_interdiction_beats_everything(self) -> None:
        everything = Situation(charging=True, interdicted=True, in_danger=True)
        colour = self.show.frame(0.0, everything)
        self.assertEqual(colour, (255, 0, 0))

    def test_danger_beats_charging(self) -> None:
        both = Situation(charging=True, in_danger=True)
        colour = self.show.frame(1.0, both)
        # Charging at its peak is 242 blue; danger is dimmer and red only.
        self.assertEqual(colour[2], 0)

    def test_a_flash_gives_way_to_an_interdiction_and_does_not_return(self) -> None:
        show = AmbilightShow()
        show.flash_balance(0.0)
        self.assertEqual(show.frame(0.05, Situation()), (0, 255, 0))

        # An interdiction cancels it rather than pausing it.
        show.frame(0.1, Situation(interdicted=True))
        self.assertEqual(show.frame(0.2, Situation()), OFF)


class BalanceFlashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.show = AmbilightShow(balance_flashes=2, balance_on=0.2, balance_off=0.2)

    def test_two_green_flashes(self) -> None:
        self.show.flash_balance(0.0)
        seen = [
            self.show.frame(t, Situation())
            for t in (0.05, 0.25, 0.45, 0.65)
        ]
        self.assertEqual(seen, [(0, 255, 0), OFF, (0, 255, 0), OFF])

    def test_it_finishes(self) -> None:
        self.show.flash_balance(0.0)
        self.assertEqual(self.show.frame(1.0, Situation()), OFF)

    def test_a_second_flash_replaces_the_first(self) -> None:
        """Selling a hold in several transactions must not queue a strobe."""
        self.show.flash_balance(0.0)
        self.show.flash_balance(0.1)
        self.assertEqual(self.show.frame(0.15, Situation()), (0, 255, 0))
        # The first flash would still be running at 0.8; the replacement is not.
        self.assertEqual(self.show.frame(0.8, Situation()), OFF)


class BrightnessTests(unittest.TestCase):
    def test_dimming_applies_to_every_effect(self) -> None:
        show = AmbilightShow(brightness=0.5, danger_colour=(200, 100, 0), danger_level=1.0)
        self.assertEqual(show.frame(0.0, Situation(in_danger=True)), (100, 50, 0))

    def test_zero_brightness_is_dark(self) -> None:
        show = AmbilightShow(brightness=0.0)
        self.assertEqual(show.frame(0.0, Situation(in_danger=True)), OFF)


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.driver = RecordingDriver()
        self.service = AmbilightService(
            AmbilightShow(), self.driver, fps=20.0, clock=self.clock
        )

    def test_only_changes_are_sent(self) -> None:
        """A steady glow is one request, not twenty a second."""
        self.service.set_situation(Situation(in_danger=True))
        for _ in range(10):
            self.service._step()
            self.clock.advance(0.05)
        self.assertEqual(len(self.driver.sent), 1)

    def test_a_change_is_sent(self) -> None:
        self.service.set_situation(Situation(in_danger=True))
        self.service._step()
        self.service.set_situation(Situation())
        self.service._step()
        self.assertEqual(self.driver.sent[-1], OFF)

    def test_going_idle_sends_off(self) -> None:
        self.service._step()
        self.assertEqual(self.driver.sent, [OFF])

    def test_the_balance_flash_reaches_the_lamp(self) -> None:
        self.service.flash_balance()
        self.service._step()
        self.assertEqual(self.driver.sent[-1], (0, 255, 0))

    def test_a_failing_driver_does_not_stop_the_worker(self) -> None:
        """A lamp that has been unplugged must not take the thread down."""
        broken = AmbilightService(AmbilightShow(), ExplodingDriver(), clock=self.clock)
        broken.set_situation(Situation(in_danger=True))
        with self.assertLogs("elite_hud.ambilight", level="ERROR"):
            broken._step()
        # It survives and can be stepped again.
        with self.assertLogs("elite_hud.ambilight", level="ERROR"):
            broken._step()

    def test_stopping_closes_the_driver(self) -> None:
        self.service.start()
        self.service.stop()
        self.assertTrue(self.driver.closed)

    def test_starting_twice_is_harmless(self) -> None:
        self.service.start()
        self.service.start()
        self.service.stop()


class DriverTests(unittest.TestCase):
    def test_the_null_driver_accepts_anything(self) -> None:
        NullDriver().apply((10, 20, 30))
        NullDriver().close()

    def test_the_library_is_optional(self) -> None:
        """It is not installed here, and that must be survivable.

        The module is obfuscated and Windows-only, so most machines will not
        have it; the overlay has to start anyway.
        """
        driver = FeelinLightDriver(["192.168.0.68"])
        self.assertFalse(driver.available)
        # And applying to an unavailable driver is a no-op rather than a raise.
        driver.apply((255, 0, 0))
        driver.close()


class ConfigTests(unittest.TestCase):
    def test_it_is_off_by_default(self) -> None:
        """It needs hardware and a third-party library, so it must be opted into."""
        self.assertFalse(Config().ambilight.enabled)

    def test_the_defaults_are_the_requested_colours(self) -> None:
        ambilight = Config().ambilight
        self.assertEqual(ambilight.charge_colour, [0, 0, 255])
        self.assertEqual(ambilight.danger_colour, [255, 0, 0])
        self.assertEqual(ambilight.interdiction_colour, [255, 0, 0])
        self.assertEqual(ambilight.balance_colour, [0, 255, 0])

    def test_validation_clamps_the_numbers(self) -> None:
        config = Config()
        config.ambilight.fps = 500.0
        config.ambilight.brightness = 3.0
        config.ambilight.danger_level = -1.0
        config.ambilight.balance_flashes = 0
        config.ambilight.ips = [" 192.168.0.68 ", ""]
        config.validate()
        self.assertEqual(config.ambilight.fps, 60.0)
        self.assertEqual(config.ambilight.brightness, 1.0)
        self.assertEqual(config.ambilight.danger_level, 0.0)
        self.assertEqual(config.ambilight.balance_flashes, 1)
        self.assertEqual(config.ambilight.ips, ["192.168.0.68"])

    def test_the_rgb_helper_falls_back_on_nonsense(self) -> None:
        from elite_hud.app import _rgb

        self.assertEqual(_rgb([10, 20, 30], (1, 2, 3)), (10, 20, 30))
        self.assertEqual(_rgb([300, -5, 20], (1, 2, 3)), (255, 0, 20))
        self.assertEqual(_rgb("magenta", (1, 2, 3)), (1, 2, 3))
        self.assertEqual(_rgb([1, 2], (1, 2, 3)), (1, 2, 3))
        self.assertEqual(_rgb(None, (1, 2, 3)), (1, 2, 3))


class BalanceChangeTests(unittest.TestCase):
    def test_a_balance_change_is_counted(self) -> None:
        """A counter, not a flag, so a change cannot be missed between reads."""
        from elite_hud.exobiology import ExobiologyTable
        from elite_hud.state import GameState

        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        # The first reading is not a change: there is nothing to compare against.
        state.apply_status(parse_status({"Balance": 1000}))
        self.assertEqual(state.balance_changes, 0)

        state.apply_status(parse_status({"Balance": 1001}))
        self.assertEqual(state.balance_changes, 1)
        state.apply_status(parse_status({"Balance": 500}))
        self.assertEqual(state.balance_changes, 2)

    def test_an_unchanged_balance_is_not_a_change(self) -> None:
        from elite_hud.exobiology import ExobiologyTable
        from elite_hud.state import GameState

        config = Config()
        state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
        state.apply_status(parse_status({"Balance": 1000}))
        state.apply_status(parse_status({"Balance": 1000}))
        self.assertEqual(state.balance_changes, 0)


if __name__ == "__main__":
    unittest.main()
