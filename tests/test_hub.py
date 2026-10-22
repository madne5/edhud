from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elite_hud.config import Config, HubConfig
from elite_hud.hub import HubClient


class HubConfigTests(unittest.TestCase):
    def test_defaults_are_off(self):
        config = HubConfig()
        self.assertFalse(config.enabled)
        self.assertFalse(config.token)
        self.assertTrue(config.filter_systems)

    def test_loads_hub_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                '[hub]\nenabled = true\nurl = "http://localhost:8000/"\ntoken = "kssn_x"\n',
                encoding="utf-8",
            )
            config = Config.load(path)
            self.assertTrue(config.hub.enabled)
            self.assertEqual(config.hub.url, "http://localhost:8000")
            self.assertEqual(config.hub.token, "kssn_x")

    def test_generated_file_has_hub_but_not_token(self):
        text = Config().to_toml()
        self.assertIn("[hub]", text)
        self.assertIn("filter_systems = true", text)
        self.assertNotIn('token = "', text)


class HubClientTests(unittest.TestCase):
    def _client(self, **overrides):
        values = {
            "enabled": True,
            "url": "http://127.0.0.1:1",
            "token": "kssn_test",
            "filter_systems": False,
            "history_seconds": 0,
        }
        values.update(overrides)
        config = HubConfig(**values)
        tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return HubClient(config, spool_path=Path(tmp.name))

    def test_offer_spools_and_observes(self):
        client = self._client()
        client.offer(
            {
                "event": "Docked",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "SystemAddress": 1,
                "StarSystem": "Sol",
                "Docked": True,
                "StationName": "Abraham Lincoln",
                "Factions": [
                    {"Name": "Sol Workers", "Influence": 0.5, "MyReputation": 100.0}
                ],
            }
        )
        self.assertEqual(client.system_id, 1)
        self.assertEqual(client.station, "Abraham Lincoln")
        events = client._read_spool()
        self.assertEqual(len(events), 1)
        self.assertNotIn("MyReputation", events[0]["Factions"][0])

    def test_system_filter(self):
        client = self._client(filter_systems=True)
        client._systems = {1}
        client._systems_loaded = True
        now = datetime.now(timezone.utc).isoformat()
        client.offer({"event": "FSDJump", "timestamp": now, "SystemAddress": 2, "StarSystem": "X"})
        self.assertEqual(len(client._read_spool()), 0)
        client.offer({"event": "FSDJump", "timestamp": now, "SystemAddress": 1, "StarSystem": "Sol"})
        self.assertEqual(len(client._read_spool()), 1)

    def test_history_filter(self):
        client = self._client(history_seconds=60)
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        client.offer({"event": "FSDJump", "timestamp": old, "SystemAddress": 1, "StarSystem": "Sol"})
        self.assertEqual(len(client._read_spool()), 0)

    def test_refresh_presence_and_status(self):
        client = self._client()
        client._get = lambda path: (
            True,
            200,
            json.dumps({"systems": [{"id64": 1, "name": "Sol"}]}),
        )
        client._refresh_systems()
        self.assertEqual(client._systems, {1})
        self.assertTrue(client._systems_loaded)

        posted = []
        client._post = lambda path, payload: (posted.append((path, payload)) or (True, 200, ""))
        client.system_id = 1
        client.system_name = "Sol"
        client.station = "Abraham Lincoln"
        client._send_presence()
        self.assertEqual(posted[0][0], "/api/v1/presence")
        self.assertEqual(posted[0][1]["station"], "Abraham Lincoln")
        self.assertIn("sent", client.status())


if __name__ == "__main__":
    unittest.main()


class HubMarketTests(unittest.TestCase):
    def test_market_is_sent_once_per_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            market = Path(tmp) / "Market.json"
            market.write_text(
                json.dumps(
                    {
                        "MarketID": 1,
                        "SystemAddress": 2,
                        "timestamp": "2026-10-22T10:00:00Z",
                        "Items": [{"Name": "gold"}],
                    }
                ),
                encoding="utf-8",
            )
            config = HubConfig(
                enabled=True,
                url="http://127.0.0.1:1",
                token="kssn_test",
                filter_systems=False,
                history_seconds=0,
                send_market=True,
            )
            client = HubClient(config, journal_dir=Path(tmp), spool_path=Path(tmp) / "spool.jsonl")
            posted = []
            client._post = lambda path, payload: (posted.append((path, payload)) or (True, 200, ""))
            client._send_market()
            client._send_market()
            self.assertEqual(len(posted), 1)
            self.assertEqual(posted[0][0], "/api/v1/ingest/market")
            self.assertEqual(posted[0][1]["station_id"], 1)
