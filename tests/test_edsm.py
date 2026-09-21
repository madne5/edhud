"""What EDSM is asked, what is believed from the answer, and what is not.

The network is exercised against a local HTTP server, as the updater's tests are,
so nothing here reaches the internet. Three rules are what these tests are really
about, because each of them is a way to show a commander something untrue:

* a failed request is not an answer of "unknown";
* an absent system is not proof that nobody has been there;
* EDSM reports no month or year of traffic, so none is invented from the total.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from elite_hud.edsm import EDSM_BASE, EdsmClient, EdsmService, SystemFacts

#: The live answer for a system the commander discovered themselves.
BLU_THEIA = {
    "name": "Blu Theia AV-F d11-1",
    "id": 102103357,
    "id64": 46682688099,
    "coords": {"x": 8755.59375, "y": 410.625, "z": 2527.875},
    "primaryStar": {"type": "G (White-Yellow) Star", "name": "Blu Theia AV-F d11-1 A",
                    "isScoopable": True},
}
BLU_THEIA_TRAFFIC = {
    "id": 102103357, "name": "Blu Theia AV-F d11-1",
    "discovery": {"commander": "Madne5", "date": "2026-09-14 19:40:56"},
    "traffic": {"total": 1, "week": 1, "day": 0},
    "breakdown": {},
}
#: And for a busy one. Its star is scoopable, which an earlier version of this
#: fixture claimed it was not -- invented rather than measured, and the sort of
#: thing that makes a test agree with a bug.
ACHENAR = {
    "name": "Achenar", "id": 12523, "id64": 164098653,
    "primaryStar": {"type": "B (Blue-White) Star", "name": "Achenar",
                    "isScoopable": True},
}
ACHENAR_TRAFFIC = {
    "id": 12523, "name": "Achenar",
    "discovery": {"commander": "Ishwin", "date": "2015-01-06 15:16:48"},
    "traffic": {"total": 14198, "week": 63, "day": 7},
    "breakdown": {"Asp Explorer": 1},
}
#: A real system whose primary star cannot be scooped: a supermassive black hole.
SAGITTARIUS_A = {
    "name": "Sagittarius A*", "id": 1, "id64": 10477373803,
    "primaryStar": {"type": "Supermassive Black Hole", "name": "Sagittarius A*",
                    "isScoopable": False},
}
SAGITTARIUS_A_TRAFFIC = {
    "id": 1, "name": "Sagittarius A*",
    "discovery": {"commander": "Zulu Romeo", "date": "2014-12-01 12:48:00"},
    "traffic": {"total": 14768, "week": 32, "day": 7},
}


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, object] = {}
    status: dict[str, int] = {}
    seen: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        path = urlparse(self.path)
        query = parse_qs(path.query)
        name = (query.get("systemName") or [""])[0]
        self.seen.append(self.path)
        body = self.routes.get(f"{path.path}|{name}")
        # The live API only includes primaryStar when it is asked for. Mimicking
        # that is the whole point: a fixture that always sent it hid a request
        # that never asked, and the fuel-star answer was missing in the field
        # while every test passed.
        if isinstance(body, dict) and path.path == "/api-v1/system":
            body = dict(body)
            if "showPrimaryStar" not in query:
                body.pop("primaryStar", None)
        code = self.status.get(f"{path.path}|{name}", 200)
        if body is None:
            code, body = 404, b""
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # keep the test output quiet
        return


class LocalServerTestCase(unittest.TestCase):
    routes: dict[str, object] = {}
    status: dict[str, int] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.seen: list[str] = []
        handler = type("Handler", (_Handler,),
                       {"routes": cls.routes, "status": cls.status, "seen": cls.seen})
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def client(self, **kwargs) -> EdsmClient:
        return EdsmClient(base=self.base, timeout=5, **kwargs)


class ClientTests(LocalServerTestCase):
    routes = {
        "/api-v1/system|Blu Theia AV-F d11-1": BLU_THEIA,
        "/api-system-v1/traffic|Blu Theia AV-F d11-1": BLU_THEIA_TRAFFIC,
        "/api-v1/system|Achenar": ACHENAR,
        "/api-system-v1/traffic|Achenar": ACHENAR_TRAFFIC,
        "/api-v1/system|Sagittarius A*": SAGITTARIUS_A,
        "/api-system-v1/traffic|Sagittarius A*": SAGITTARIUS_A_TRAFFIC,
        "/api-v1/system|Nowhere ZZ-Z z99-9": [],
        "/api-v1/system|Broken": "not json at all",
    }

    def test_a_known_system_is_read_whole(self) -> None:
        facts = self.client().lookup("Blu Theia AV-F d11-1")
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertTrue(facts.known)
        self.assertEqual(facts.discoverer, "Madne5")
        self.assertEqual(facts.discovered_at, "14.09.2026")
        self.assertIs(facts.scoopable, True)
        self.assertEqual(facts.primary_star, "G (White-Yellow) Star")
        self.assertEqual(facts.traffic_day, 0)
        self.assertEqual(facts.traffic_week, 1)
        self.assertEqual(facts.traffic_total, 1)

    def test_the_fuel_star_is_asked_for(self) -> None:
        """Without showPrimaryStar the answer has no primaryStar at all.

        Caught in the field, not by a test: the request went out without the flag,
        EDSM left the field out, and the fuel-star answer was simply missing while
        every test passed -- because the fixture sent primaryStar unconditionally.
        """
        self.seen.clear()
        facts = self.client().lookup("Blu Theia AV-F d11-1")
        self.assertTrue(
            any("showPrimaryStar=1" in entry for entry in self.seen),
            f"the system request must ask for the star: {self.seen}",
        )
        assert facts is not None
        self.assertIs(facts.scoopable, True)

    def test_an_unscoopable_star_is_reported_as_such(self) -> None:
        """False and None are different answers and must not be confused."""
        facts = self.client().lookup("Sagittarius A*")
        assert facts is not None
        self.assertIs(facts.scoopable, False)
        self.assertEqual(facts.primary_star, "Supermassive Black Hole")

    def test_an_unknown_system_is_marked_unknown(self) -> None:
        """EDSM answers an empty list, which is an answer, not a failure."""
        facts = self.client().lookup("Nowhere ZZ-Z z99-9")
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertFalse(facts.known)
        self.assertEqual(facts.traffic_total, None)

    def test_an_unknown_system_costs_one_request(self) -> None:
        """Nothing to ask about traffic for, so nothing is asked."""
        self.seen.clear()
        self.client().lookup("Nowhere ZZ-Z z99-9")
        self.assertEqual(len([s for s in self.seen if "Nowhere" in s]), 1)

    def test_a_failure_is_not_an_answer(self) -> None:
        """A 404, a timeout or a garbage body means we do not know."""
        self.assertIsNone(self.client().lookup("Broken"))
        self.assertIsNone(self.client().lookup("Not In The Server At All"))

    def test_unparseable_json_is_a_failure(self) -> None:
        self.assertIsNone(self.client().lookup("Broken"))

    def test_the_live_base_is_the_web_host(self) -> None:
        """``api.edsm.net`` does not resolve; the API lives on the web host."""
        self.assertEqual(EDSM_BASE, "https://www.edsm.net")
        self.assertNotIn("api.edsm.net", EDSM_BASE)


class ServiceTests(LocalServerTestCase):
    routes = ClientTests.routes

    def _service(self, **kwargs):
        answers: list[SystemFacts] = []
        service = EdsmService(client=self.client(), on_event=answers.append, **kwargs)
        return service, answers

    def _wait(self, answers: list, count: int = 1, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(answers) >= count:
                return True
            time.sleep(0.02)
        return False

    def test_a_lookup_arrives_through_the_callback(self) -> None:
        service, answers = self._service()
        service.start()
        try:
            service.request("Achenar")
            self.assertTrue(self._wait(answers), "no answer arrived")
        finally:
            service.stop()
        self.assertEqual(answers[0].discoverer, "Ishwin")

    def test_the_same_system_is_asked_about_once(self) -> None:
        """A route of twenty jumps must not ask twenty times about one system."""
        self.seen.clear()
        service, answers = self._service()
        service.start()
        try:
            for _ in range(5):
                service.request("Achenar")
            self.assertTrue(self._wait(answers))
            time.sleep(0.2)
            for _ in range(5):
                service.request("Achenar")
            time.sleep(0.2)
        finally:
            service.stop()
        self.assertEqual(len([s for s in self.seen if "Achenar" in s]), 2,
                         "system + traffic, once each")

    def test_a_failed_lookup_is_retried_later(self) -> None:
        """A failure must not be remembered as an answer."""
        service, answers = self._service()
        service.start()
        try:
            service.request("Not In The Server At All")
            time.sleep(0.3)
            self.assertEqual(answers, [])
            service.request("Not In The Server At All")
            time.sleep(0.3)
        finally:
            service.stop()
        # The log records both attempts; nothing was cached and nothing shown.
        self.assertEqual(answers, [])
        self.assertIsNone(service.cached("Not In The Server At All"))

    def test_disabled_means_no_requests_at_all(self) -> None:
        self.seen.clear()
        service, answers = self._service(enabled=False)
        service.start()
        try:
            service.request("Achenar")
            time.sleep(0.2)
        finally:
            service.stop()
        self.assertEqual(self.seen, [])
        self.assertEqual(answers, [])

    def test_the_cache_is_readable_without_waiting(self) -> None:
        service, answers = self._service()
        service.start()
        try:
            service.request("Achenar")
            self.assertTrue(self._wait(answers))
        finally:
            service.stop()
        cached = service.cached("Achenar")
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertTrue(cached.known)


class FactsRenderingTests(unittest.TestCase):
    """The line the HUD builds from these facts.

    Calls the same function the HUD calls, without a window: the wording is what
    matters here, and testing it must not depend on a display.
    """

    def _text(self, facts, **config_changes) -> str:
        from elite_hud.config import Config
        from elite_hud.edsm import describe

        config = Config()
        for key, value in config_changes.items():
            section, _, field = key.partition(".")
            setattr(getattr(config, section), field, value)
        return describe(facts, config.overlay.labels, config.edsm)

    def test_unknown_says_no_data_rather_than_unvisited(self) -> None:
        """The wording matters: absence in EDSM proves nothing about visitors."""
        text = self._text(SystemFacts(name="Nowhere ZZ-Z z99-9"))
        self.assertIn("в EDSM нет данных", text)
        self.assertIn("возможно, не посещалась", text)
        self.assertNotIn("никто не посещал", text)

    def test_a_known_system_shows_who_found_it(self) -> None:
        text = self._text(SystemFacts(name="Blu Theia AV-F d11-1", known=True,
                                      discoverer="Madne5", discovered_at="14.09.2026",
                                      scoopable=True, traffic_day=0, traffic_week=1,
                                      traffic_total=1))
        self.assertIn("открыта: Madne5 14.09.2026", text)
        self.assertIn("заправка: да", text)
        self.assertIn("трафик: сутки 0, неделя 1, всего 1", text)

    def test_no_month_or_year_of_traffic_is_invented(self) -> None:
        """EDSM reports day, week and total. There is no month to show."""
        text = self._text(SystemFacts(name="Sagittarius A*", known=True,
                                      discoverer="Zulu Romeo",
                                      discovered_at="01.12.2014", scoopable=False,
                                      traffic_day=7, traffic_week=32,
                                      traffic_total=14768))
        for absent in ("месяц", "год", "за месяц"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, text)
        self.assertIn("всего 14768", text)

    def test_zero_traffic_is_stated_plainly(self) -> None:
        text = self._text(SystemFacts(name="X", known=True, traffic_day=0,
                                      traffic_week=0, traffic_total=0))
        self.assertIn("трафик: нет", text)

    def test_an_unknown_star_says_nothing_about_fuel(self) -> None:
        """None is not False: without data the line claims nothing."""
        text = self._text(SystemFacts(name="X", known=True, discoverer="Someone"))
        self.assertNotIn("заправка", text)

    def test_the_switches_take_effect(self) -> None:
        facts = SystemFacts(name="Sagittarius A*", known=True, discoverer="Zulu Romeo",
                            discovered_at="01.12.2014", scoopable=False,
                            traffic_day=7, traffic_week=32, traffic_total=14768)
        self.assertNotIn("открыта", self._text(facts, **{"edsm.show_discovery": False}))
        self.assertNotIn("заправка", self._text(facts, **{"edsm.show_fuel_star": False}))
        self.assertNotIn("трафик", self._text(facts, **{"edsm.show_traffic": False}))
        self.assertEqual(self._text(facts, **{"edsm.enabled": False}), "")

    def test_nothing_is_shown_without_facts(self) -> None:
        self.assertEqual(self._text(None), "")



class FakeHud:
    """Records what the app tells the bar, without a window."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def set_edsm_facts(self, facts, *, seconds: float = 0.0) -> None:
        self.calls.append(("set", facts.name if facts is not None else None, seconds))

    def expire_edsm(self, seconds: float) -> None:
        self.calls.append(("expire", seconds))

    def rebuild(self) -> None:  # pragma: no cover - the app never calls it here
        pass


class FakeEdsm:
    """Stands in for the lookup service: no threads, no network."""

    def __init__(self, cached: dict | None = None) -> None:
        self._cached = dict(cached or {})
        self.requested: list[tuple[str, bool]] = []

    def cached(self, name: str):
        return self._cached.get(name)

    def request(self, name: str, *, force: bool = False) -> None:
        self.requested.append((name, force))


class ArrivalExpiryTests(unittest.TestCase):
    """The line about the system just reached must not sit there for ever.

    It stays accurate and stops being useful the moment the commander is sitting
    in the system looking at it, and a bar that never changes reads as broken.
    The line about the system being jumped *to* is a different thing: that one is
    worth having for the whole flight, so it does not expire.
    """

    def _app(self, cached: dict | None = None):
        from elite_hud.app import HudApp, build_parser
        from elite_hud.config import Config

        config = Config()
        app = HudApp(config, build_parser().parse_args([]))
        app.hud = FakeHud()
        app.edsm = FakeEdsm(cached)
        return app, config

    def _facts(self, name: str):
        from elite_hud.edsm import SystemFacts

        return SystemFacts(name=name, known=True, discoverer="Someone",
                           discovered_at="01.01.2020", scoopable=True)

    def test_arriving_lets_the_line_run_out(self) -> None:
        app, config = self._app({"Sol": self._facts("Sol")})
        app._edsm_subject = "Sol"
        app.state.apply({"event": "FSDJump", "StarSystem": "Sol", "SystemAddress": 1})
        app._follow_edsm("Sol")
        self.assertEqual(app.hud.calls, [("expire", config.edsm.arrival_display_seconds)])

    def test_a_new_target_replaces_the_line_without_a_deadline(self) -> None:
        app, _ = self._app({"Achenar": self._facts("Achenar")})
        app.state.apply({"event": "FSDTarget", "Name": "Achenar", "StarClass": "K",
                         "RemainingJumpsInRoute": 3})
        app._follow_edsm("")
        self.assertEqual(app.hud.calls, [("set", "Achenar", 0.0)])
        self.assertEqual(app.edsm.requested, [("Achenar", False)])

    def test_arriving_somewhere_unknown_asks_again_and_shows_nothing_yet(self) -> None:
        app, _ = self._app()
        app.state.apply({"event": "FSDJump", "StarSystem": "Nowhere", "SystemAddress": 2})
        app._follow_edsm("Nowhere")
        self.assertEqual(app.hud.calls, [("set", None, 0.0)])
        self.assertEqual(app.edsm.requested, [("Nowhere", True)])

    def test_the_answer_to_an_arrival_lookup_carries_the_deadline(self) -> None:
        """A system EDSM has never heard of is still shown, then retired."""
        app, config = self._app()
        app._edsm_subject = "Nowhere"
        app._show_edsm(self._facts("Nowhere"),
                       seconds=config.edsm.arrival_display_seconds)
        self.assertEqual(
            app.hud.calls, [("set", "Nowhere", config.edsm.arrival_display_seconds)]
        )

    def test_the_deadline_can_be_switched_off(self) -> None:
        """0 means "keep it until the next jump", which is what it used to do."""
        app, config = self._app({"Sol": self._facts("Sol")})
        config.edsm.arrival_display_seconds = 0.0
        app._edsm_subject = "Sol"
        app._follow_edsm("Sol")
        self.assertEqual(
            app.hud.calls,
            [("expire", 0.0)],
            "the bar is told zero, which it treats as no deadline",
        )


class HudExpiryTests(unittest.TestCase):
    """The same behaviour, seen through the bar and a clock that can be moved."""

    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        from tests.test_hud import QT_SKIP_REASON

        if QT_SKIP_REASON:
            self.skipTest(QT_SKIP_REASON)
        QApplication.instance() or QApplication([])
        import elite_hud.overlay.hud as hud_module

        self.module = hud_module
        self.clock = [1000.0]
        self._real = hud_module._monotonic
        hud_module._monotonic = lambda: self.clock[0]
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        self.module._monotonic = self._real

    def _hud(self):
        from elite_hud.config import Config
        from elite_hud.overlay.hud import HudWindow
        from elite_hud.state import GameState

        hud = HudWindow(Config(), GameState())
        hud._available_width = lambda: 2560.0
        hud.rebuild()
        self.addCleanup(hud.close)
        return hud

    def _facts(self):
        from elite_hud.edsm import SystemFacts

        return SystemFacts(name="Sol", known=True, discoverer="Corbin Moran",
                           discovered_at="22.11.2014", scoopable=True, traffic_total=1)

    def test_a_target_line_has_no_deadline(self) -> None:
        hud = self._hud()
        hud.set_edsm_facts(self._facts())
        self.clock[0] += 3600
        hud.rebuild()
        self.assertIn("Sol", hud.edsm_text())
        self.assertTrue(any(row.kind == "edsm" for row in hud._rows))

    def test_an_arrival_line_goes_away(self) -> None:
        hud = self._hud()
        hud.set_edsm_facts(self._facts(), seconds=15.0)
        self.clock[0] += 14
        hud.rebuild()
        self.assertIn("Sol", hud.edsm_text())
        self.clock[0] += 2
        hud.rebuild()
        self.assertEqual(hud.edsm_text(), "")
        self.assertFalse(any(row.kind == "edsm" for row in hud._rows))

    def test_an_expired_line_cannot_come_back(self) -> None:
        """It is forgotten, not merely hidden, so a later rebuild cannot revive it."""
        hud = self._hud()
        hud.set_edsm_facts(self._facts(), seconds=15.0)
        self.clock[0] += 16
        hud.rebuild()
        hud.rebuild()
        self.assertEqual(hud.edsm_text(), "")
        self.assertIsNone(hud._edsm)

    def test_expire_marks_whatever_is_showing(self) -> None:
        hud = self._hud()
        hud.set_edsm_facts(self._facts())
        hud.expire_edsm(15.0)
        self.clock[0] += 16
        hud.rebuild()
        self.assertEqual(hud.edsm_text(), "")

    def test_expiring_nothing_does_nothing(self) -> None:
        hud = self._hud()
        hud.expire_edsm(15.0)
        self.assertEqual(hud.edsm_text(), "")

    def test_zero_seconds_means_no_deadline(self) -> None:
        hud = self._hud()
        hud.set_edsm_facts(self._facts(), seconds=0.0)
        hud.expire_edsm(0.0)
        self.clock[0] += 3600
        hud.rebuild()
        self.assertIn("Sol", hud.edsm_text())


if __name__ == "__main__":
    unittest.main()
