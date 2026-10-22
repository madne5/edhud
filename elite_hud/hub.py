"""Optional upload to the private KSSN Hub.

The journal watcher stays responsible for the overlay.  This module is a second
consumer: it filters events to the systems the hub watches, writes them to a
small durable spool, and posts batches with the device bearer token.  It never
touches the Qt thread and it is disabled unless ``[hub].enabled`` is true.
"""

from __future__ import annotations

import gzip
import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # certifi is a runtime dependency, but keep import failure harmless
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

from .config import HubConfig, user_config_dir

log = logging.getLogger(__name__)

EVENT_TYPES = {"FSDJump", "Location", "Docked", "Undocked", "CarrierJump"}
USER_AGENT = "elite-hud-hub/1.0 (+https://kssn.space)"


SAFE_FIELDS = (
    "event",
    "timestamp",
    "StarSystem",
    "SystemAddress",
    "Body",
    "BodyType",
    "Docked",
    "StationName",
    "StationType",
    "MarketID",
    "StationServices",
    "StationEconomies",
    "DistFromStarLS",
    "StationFaction",
    "StationGovernment",
    "StationAllegiance",
    "SystemFaction",
    "SystemEconomy",
    "SystemSecondEconomy",
    "SystemSecurity",
    "SystemGovernment",
    "SystemAllegiance",
    "Population",
    "Factions",
    "Conflicts",
)
FACTION_FIELDS = (
    "Name",
    "FactionState",
    "Government",
    "Allegiance",
    "Influence",
    "Happiness",
    "Happiness_Localised",
    "ActiveStates",
    "PendingStates",
    "RecoveringStates",
)


def sanitize_event(event: dict) -> dict:
    """Strip personal journal fields before they leave the machine."""
    data = {}
    for key in SAFE_FIELDS:
        if key not in event:
            continue
        value = event[key]
        if key == "Factions" and isinstance(value, list):
            data[key] = [
                {field: faction.get(field) for field in FACTION_FIELDS if field in faction}
                for faction in value
                if isinstance(faction, dict)
            ]
        elif key == "SystemFaction" and isinstance(value, dict):
            data[key] = {"Name": value.get("Name")}
        elif key == "StationFaction" and isinstance(value, dict):
            data[key] = {"Name": value.get("Name")}
        else:
            data[key] = value
    return data


def _parse_timestamp(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class HubClient:
    """Durable, non-blocking uploader for the hub's journal API."""

    def __init__(
        self,
        config: HubConfig,
        *,
        journal_dir: Path | None = None,
        spool_path: Path | None = None,
    ) -> None:
        self.config = config
        self.journal_dir = journal_dir
        self.spool_path = spool_path or self._default_spool()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

        self._systems: set[int] = set()
        self._systems_loaded = False
        self._systems_loaded_at = 0.0
        self.system_id: int | None = None
        self.system_name = ""
        self.station = ""
        self.ship = ""
        self.game_mode = ""
        self.last_status = "off"
        self.last_error = ""
        self.sent = 0
        self._last_presence = 0.0
        self._market_mtime = 0.0
        self._market_path = self._find_market()

    @staticmethod
    def _default_spool() -> Path:
        return Path(user_config_dir()) / "hub-spool.jsonl"

    def _find_market(self) -> Path | None:
        if self.journal_dir is None:
            return None
        path = Path(self.journal_dir) / "Market.json"
        return path if path.is_file() else path

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if not self.config.enabled:
            self.last_status = "disabled"
            return
        if not self.config.token:
            self.last_status = "no token"
            log.warning("hub is enabled but hub.token is empty")
            return
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="kssn-hub", daemon=True)
        self._thread.start()
        self.last_status = "starting"
        log.info("hub upload enabled: %s", self.config.url)

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        self.last_status = "stopped"

    def offer(self, event: dict) -> None:
        """Called from the journal watcher thread: filter, observe, spool."""
        if not self.config.enabled or not self.config.token:
            return
        self._observe(event)
        if event.get("event") not in EVENT_TYPES:
            return
        if not self._allowed(event):
            return
        self._append(sanitize_event(event))
        self._wake.set()

    # -- event filter ------------------------------------------------------

    def _observe(self, event: dict) -> None:
        name = event.get("event")
        if name == "LoadGame":
            self.ship = str(event.get("Ship") or self.ship)
            self.game_mode = str(event.get("GameMode") or self.game_mode)
            return
        if name in {"FSDJump", "Location", "CarrierJump", "Docked"}:
            try:
                self.system_id = int(event.get("SystemAddress"))
            except (TypeError, ValueError):
                pass
            self.system_name = str(event.get("StarSystem") or self.system_name)
        if name in {"Docked", "Location"} and event.get("Docked"):
            self.station = str(event.get("StationName") or "")
        elif name in {"Undocked", "FSDJump", "CarrierJump"}:
            self.station = ""

    def _allowed(self, event: dict) -> bool:
        timestamp = _parse_timestamp(event.get("timestamp"))
        if timestamp is not None and self.config.history_seconds > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(
                seconds=self.config.history_seconds
            )
            if timestamp < cutoff:
                return False
        if not self.config.filter_systems:
            return True
        if not self._systems_loaded:
            # The server checks again. Sending before the first list arrives
            # means a fresh HUD does not lose the Location event that starts
            # the session; nothing outside the watched list is stored.
            return True
        try:
            return int(event.get("SystemAddress")) in self._systems
        except (TypeError, ValueError):
            return False

    # -- spool -------------------------------------------------------------

    def _append(self, event: dict) -> None:
        try:
            self.spool_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with open(self.spool_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError as exc:
            self.last_error = f"spool: {exc}"
            log.warning("cannot write hub spool %s: %s", self.spool_path, exc)

    def _read_spool(self) -> list[dict]:
        with self._lock:
            try:
                lines = self.spool_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
        events = []
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def _drop_first(self, count: int) -> None:
        with self._lock:
            try:
                lines = self.spool_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return
            remaining = lines[count:]
            tmp = self.spool_path.with_suffix(".tmp")
            try:
                tmp.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
                tmp.replace(self.spool_path)
            except OSError as exc:
                self.last_error = f"spool rewrite: {exc}"
                log.warning("cannot rewrite hub spool: %s", exc)

    # -- HTTP --------------------------------------------------------------

    def _context(self):
        if certifi is not None:
            try:
                return ssl.create_default_context(cafile=certifi.where())
            except (OSError, ssl.SSLError):
                pass
        return ssl.create_default_context()

    def _post(self, path: str, payload: dict) -> tuple[bool, int, str]:
        url = self.config.url.rstrip("/") + path
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        request = urllib.request.Request(
            url, data=gzip.compress(body), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds, context=self._context()
            ) as response:
                text = response.read().decode("utf-8", "replace")
                return 200 <= response.status < 300, response.status, text
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            self.last_error = f"HTTP {exc.code}: {text[:200]}"
            return False, exc.code, text
        except (OSError, ValueError) as exc:
            self.last_error = str(exc)
            return False, 0, str(exc)

    def _get(self, path: str) -> tuple[bool, int, str]:
        request = urllib.request.Request(
            self.config.url.rstrip("/") + path,
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds, context=self._context()
            ) as response:
                return True, response.status, response.read().decode("utf-8", "replace")
        except (urllib.error.HTTPError, OSError, ValueError) as exc:
            self.last_error = str(exc)
            return False, 0, str(exc)

    # -- worker ------------------------------------------------------------

    def _run(self) -> None:
        backoff = self.config.poll_interval
        while not self._stop.is_set():
            try:
                if self._should_refresh_systems():
                    self._refresh_systems()
                if self._should_heartbeat():
                    self._send_presence()
                if self.config.send_market:
                    self._send_market()
                events = self._read_spool()
                if events:
                    batch = events[: self.config.batch_size]
                    ok, status, _ = self._post(
                        "/api/v1/ingest/journal", {"events": batch}
                    )
                    if ok:
                        self._drop_first(len(batch))
                        self.sent += len(batch)
                        self.last_status = f"sent {self.sent}"
                        self.last_error = ""
                        backoff = self.config.poll_interval
                    elif status in (401, 403):
                        self.last_status = "auth error"
                        self._stop.wait(300)
                    else:
                        self.last_status = "retrying"
                        self._stop.wait(backoff)
                        backoff = min(60.0, max(self.config.poll_interval, backoff * 2))
            except Exception:  # pragma: no cover - worker must survive
                log.exception("hub worker failed")
                self.last_status = "error"
                self._stop.wait(self.config.poll_interval)
            self._wake.wait(self.config.poll_interval)
            self._wake.clear()

    def _should_refresh_systems(self) -> bool:
        return (
            not self._systems_loaded
            or time.monotonic() - self._systems_loaded_at
            > self.config.systems_refresh_minutes * 60
        )

    def _refresh_systems(self) -> None:
        ok, _, body = self._get("/api/v1/systems")
        if not ok:
            return
        try:
            payload = json.loads(body)
            systems = payload.get("systems") or []
            self._systems = {int(item["id64"]) for item in systems if item.get("id64")}
            self._systems_loaded = True
            self._systems_loaded_at = time.monotonic()
        except (TypeError, ValueError, KeyError):
            return

    def _should_heartbeat(self) -> bool:
        if self.system_id is None:
            return False
        if self.config.filter_systems and self._systems_loaded:
            if self.system_id not in self._systems:
                return False
        return time.monotonic() - self._last_presence >= self.config.heartbeat_seconds

    def _send_presence(self) -> None:
        if self.system_id is None:
            return
        payload = {
            "system_id64": self.system_id,
            "system_name": self.system_name,
            "station": self.station or None,
            "ship": self.ship or None,
            "game_mode": self.game_mode or None,
        }
        ok, _, _ = self._post("/api/v1/presence", payload)
        if ok:
            self._last_presence = time.monotonic()
            self.last_error = ""

    def _send_market(self) -> None:
        path = self._market_path
        if path is None or not path.is_file():
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if mtime <= self._market_mtime:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        station_id = data.get("MarketID")
        try:
            station_id = int(station_id)
        except (TypeError, ValueError):
            return
        system_id = data.get("SystemAddress") or self.system_id
        try:
            system_id = int(system_id)
        except (TypeError, ValueError):
            return
        if self.config.filter_systems and self._systems_loaded and system_id not in self._systems:
            return
        ok, _, _ = self._post(
            "/api/v1/ingest/market",
            {
                "station_id": station_id,
                "system_id64": system_id,
                "captured_at": data.get("timestamp"),
                "data": data,
            },
        )
        if ok:
            self._market_mtime = mtime

    def status(self) -> dict:
        return {
            "status": self.last_status,
            "sent": self.sent,
            "pending": len(self._read_spool()),
            "error": self.last_error,
            "systems": len(self._systems),
        }
