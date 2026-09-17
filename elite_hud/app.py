"""Entry point: wire the journal watcher, the state machine and the HUD together."""

from __future__ import annotations

import argparse
import json
import logging
import queue
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__
from .alerts import SoundPlayer
from .config import (
    CONFIG_FILENAME,
    SEGMENT_NAMES,
    STATUS_SEGMENT_NAMES,
    Config,
    add_missing_sections,
    ensure_config_file,
    resolve_config_path,
    set_config_list,
    toggle_segment,
    set_config_value,
    set_update_mode,
)
from .exobiology import Confidence, ExobiologyTable
from .footfall import FootfallPolicy
from .installation import SingleInstanceGuard
from .journal.watcher import JournalWatcher
from .notifications import Notification, NotificationCenter
from .paths import expand_user_path, find_journal_dir
from .state import Alert, GameState, parse_timestamp
from .status import StatusReader
from .update_service import UpdateEvent, UpdateService

log = logging.getLogger("elite_hud")

#: Never apply more than this many events in a single UI tick, so a long
#: history replay cannot freeze the overlay.
MAX_EVENTS_PER_TICK = 2000

CONFIDENCE_BY_NAME = {
    "possible": Confidence.POSSIBLE,
    "guaranteed": Confidence.GUARANTEED,
    "confirmed": Confidence.CONFIRMED,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elite-hud",
        description="Elite Dangerous journal HUD overlay.",
    )
    parser.add_argument("--config", type=Path, help="path to config.toml")
    parser.add_argument("--journal-dir", type=Path, help="override the journal directory")
    parser.add_argument(
        "--replay",
        type=Path,
        metavar="JOURNAL.LOG",
        help="replay a journal file instead of watching the live one",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.0,
        help="replay speed multiplier (0 = as fast as possible, default)",
    )
    parser.add_argument(
        "--replay-loop",
        action="store_true",
        help="restart the replay file when it ends",
    )
    parser.add_argument(
        "--replay-live",
        action="store_true",
        help="shift replay timestamps onto the current clock (shows a live carrier countdown)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="parse and log without opening the overlay window",
    )
    parser.add_argument(
        "--print-state",
        action="store_true",
        help="with --headless, print the HUD line after every alert",
    )
    parser.add_argument(
        "--list-genera",
        action="store_true",
        help="print the exobiology value table and exit",
    )
    parser.add_argument(
        "--make-config",
        action="store_true",
        help="write a default config.toml next to the package and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"elite-hud {__version__}",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="check GitHub for a newer release, print the result and exit",
    )
    parser.add_argument(
        "--carrier-report",
        action="store_true",
        help="read the journals and print the observed fleet carrier jump timings",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="verify the bundled data and configuration, then exit (0 = healthy)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="ignore the single-instance guard (for testing)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return parser


def setup_logging(config: Config, verbose: bool) -> None:
    level = logging.DEBUG if verbose else getattr(logging, config.logging.level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if config.logging.file:
        path = expand_user_path(config.logging.file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def default_config_path(explicit: Path | None) -> Path:
    """Kept as a thin alias so callers need not know about the install shape."""
    return resolve_config_path(explicit)


def print_genera(table: ExobiologyTable, threshold: int) -> None:
    print(f"{'genus':<16} {'min':>12} {'max':>12}  species over {threshold:,}")
    print("-" * 60)
    for genus in sorted(table.genera_by_key.values(), key=lambda g: -g.max_value):
        if not genus.sellable:
            continue
        hits = [s for s in genus.species if s.value >= threshold]
        print(
            f"{genus.name:<16} {genus.min_value:>12,} {genus.max_value:>12,}  "
            f"{len(hits)}/{len(genus.species)}"
            + (f"  e.g. {hits[0].name}" if hits else "")
        )


class ReplaySource(threading.Thread):
    """Feed a journal file into the event queue, optionally in real time."""

    def __init__(
        self,
        path: Path,
        sink: queue.Queue,
        *,
        speed: float,
        loop: bool,
        live: bool = False,
    ) -> None:
        super().__init__(name="journal-replay", daemon=True)
        self.path = path
        self.sink = sink
        self.speed = speed
        self.loop = loop
        #: rebase timestamps onto the current wall clock so a recorded session
        #: replays as if it were happening now (live countdowns, no stale data)
        self.live = live
        self._shift: timedelta | None = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _iter_events(self):
        with open(self.path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                import json

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and "event" in event:
                    yield event

    def _rebase(self, event: dict) -> dict:
        """Shift an event's timestamps so the recording appears to be live."""
        if not self.live:
            return event
        stamp = parse_timestamp(event.get("timestamp"))
        if stamp is None:
            return event
        if self._shift is None:
            self._shift = datetime.now(timezone.utc) - stamp
            log.info("replay rebased by %s", self._shift)
        event = dict(event)
        event["timestamp"] = (stamp + self._shift).isoformat().replace("+00:00", "Z")
        departure = parse_timestamp(event.get("DepartureTime"))
        if departure is not None:
            event["DepartureTime"] = (
                (departure + self._shift).isoformat().replace("+00:00", "Z")
            )
        return event

    def run(self) -> None:
        while not self._stop.is_set():
            previous: datetime | None = None
            for raw in self._iter_events():
                event = self._rebase(raw)
                if self._stop.is_set():
                    return
                if self.speed > 0:
                    stamp = parse_timestamp(event.get("timestamp"))
                    if stamp is not None and previous is not None:
                        delay = (stamp - previous).total_seconds() / self.speed
                        if delay > 0:
                            self._stop.wait(min(delay, 30.0))
                    previous = stamp
                # Never let a fast replay balloon memory: throttle the producer
                # instead of dropping events the consumer has not seen yet.
                while not self._stop.is_set() and self.sink.qsize() > 25_000:
                    self._stop.wait(0.05)
                self.sink.put(event)
            if not self.loop:
                return
            log.info("replay finished, looping")


class HudApp:
    def __init__(self, config: Config, options: argparse.Namespace) -> None:
        self.config = config
        self.options = options
        self.events: queue.Queue[dict] = queue.Queue()
        self.alerts_seen = 0

        self.table = ExobiologyTable()
        applied = self.table.apply_overrides(config.exobiology_overrides)
        if applied:
            log.info("applied %d exobiology value override(s)", applied)

        self.state = GameState(
            self.table,
            value_threshold=config.alerts.min_value,
            carrier_spool_seconds=config.carrier.spool_minutes * 60.0,
            carrier_cooldown_seconds=config.carrier.jump_cooldown_seconds,
            carrier_jump_seconds=config.carrier.jump_duration_seconds,
            carrier_cancel_seconds=config.carrier.cancel_cooldown_seconds,
            footfall=FootfallPolicy(
                enabled=config.footfall.enabled,
                require_biology=config.footfall.require_biology,
                require_undiscovered=config.footfall.require_undiscovered,
                min_bio_signals=config.footfall.min_bio_signals,
            ),
            footfall_label=config.overlay.labels.footfall_first,
            faction_name=config.faction.name,
            faction_match=config.faction.match,
            material_rarity=config.materials.rarity,
            material_enabled=config.materials.enabled,
            material_notify=config.materials.notify_collected,
            rarity_label=config.overlay.labels.rarity,
            total_label=config.overlay.labels.total,
        )
        self.sound = SoundPlayer(config.alerts.sound_file, config.alerts.volume)
        self.sound_min_rank = CONFIDENCE_BY_NAME[
            config.alerts.sound_min_confidence
        ].rank

        self.instance: SingleInstanceGuard | None = None
        self._exit_for_update = False
        self.watcher: JournalWatcher | None = None
        self.replay: ReplaySource | None = None
        self.hud = None
        self.tray = None
        self._app = None
        self._last_alert: Alert | None = None
        self.status_reader: StatusReader | None = None
        self._pending_sound = False

        self.update_events: queue.Queue[UpdateEvent] = queue.Queue()
        self.updates = UpdateService(
            config.update,
            current_version=__version__,
            on_event=self.update_events.put,
            on_before_apply=self._release_instance_guard,
        )
        self._update_actions: dict[str, object] = {}
        self._faction_actions: dict[str, object] = {}
        self._monitor_group = None
        self._update_mode_group = None
        self._quit_after_update = False

    # -- event plumbing ----------------------------------------------------

    def _on_journal_event(self, event: dict) -> None:
        self.events.put(event)

    def _poll_status(self) -> None:
        """Read Status.json for the values the journal never reports."""
        reader = getattr(self, "status_reader", None)
        if reader is None:
            return
        snapshot = reader.poll()
        if snapshot is not None:
            self.state.apply_status(snapshot)

    def _start_status_reader(self, journal_dir) -> None:
        """Begin polling the status file beside the journal."""
        if journal_dir is None:
            return
        self.status_reader = StatusReader.beside(Path(journal_dir))
        log.info("reading live status from %s", self.status_reader.path)

    def _drain(self) -> bool:
        """Apply queued events. Returns True when something changed."""
        changed = False
        best: Alert | None = None
        for _ in range(MAX_EVENTS_PER_TICK):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            for alert in self.state.apply(event):
                self.alerts_seen += 1
                self._log_alert(alert)
                if best is None or (alert.value, alert.confidence.rank) > (
                    best.value,
                    best.confidence.rank,
                ):
                    best = alert

        if self.hud is not None:
            self._publish_announcements()

        if best is not None:
            self._last_alert = best
            if self.hud is not None:
                self.hud.push_alert(best)
            if self.options.print_state:
                print(self.render_text_line())
            if best.confidence.rank >= self.sound_min_rank:
                self._pending_sound = True
            if self.config.alerts.desktop_notification and self.tray is not None:
                self.tray.showMessage(
                    f"{best.title} — {best.value:,} cr",
                    f"{best.system} · {best.body}" if best.body else best.system,
                )
        return changed

    def _publish_announcements(self) -> None:
        """Hand the state layer's queued announcements to the HUD.

        These were being raised and quietly dropped before the notification
        system existed, so a rank gained never reached the screen.
        """
        for announcement in self.state.drain_announcements():
            log.info(
                "NOTIFY [%s] %s%s",
                announcement.kind,
                announcement.title,
                f" — {announcement.detail}" if announcement.detail else "",
            )
            self.hud.push_notification(
                Notification(
                    key=NotificationCenter.key_for(
                        announcement.kind, announcement.detail
                    ),
                    title=announcement.title,
                    detail=announcement.detail,
                    glyph=announcement.glyph,
                    tone=announcement.tone,
                    value=announcement.value,
                )
            )

    def _log_alert(self, alert: Alert) -> None:
        payout = f" (payout {alert.payout:,})" if alert.bonus_applies else ""
        log.info(
            "ALERT [%s] %s — %s cr%s%s / %s",
            alert.confidence.value,
            alert.title,
            f"{alert.value:,}",
            payout,
            f" @ {alert.body}" if alert.body else "",
            alert.system or "?",
        )

    def _drain_updates(self) -> None:
        while True:
            try:
                event = self.update_events.get_nowait()
            except queue.Empty:
                return
            self._handle_update_event(event)

    def _handle_update_event(self, event: UpdateEvent) -> None:
        log.info("update: %s", event.message)
        available_action = self._update_actions.get("install")
        status_action = self._update_actions.get("status")

        if event.kind == "available" and available_action is not None:
            available_action.setEnabled(True)
            available_action.setText(f"Установить {event.update.version}")  # type: ignore[attr-defined]
        if status_action is not None and event.kind in {
            "checking",
            "current",
            "available",
            "downloading",
            "staged",
            "applying",
            "applied",
            "error",
            "busy",
        }:
            status_action.setText(event.message)  # type: ignore[attr-defined]

        if event.kind == "downloading" and self.tray is not None:
            self.tray.setToolTip(f"elite-hud — {event.message} {event.progress * 100:.0f}%")

        if event.kind == "applying":
            # Yesterday's mutex would make a silent Setup abort with code 1.
            self._release_instance_guard()

        if self.tray is not None and event.kind in {"available", "staged", "error", "current"}:
            self.tray.showMessage("elite-hud", event.message)

        if event.kind == "applied" and not self._quit_after_update:
            # The installer needs this process gone before it can replace files;
            # a short delay lets the tray balloon appear first.
            self._quit_after_update = True
            self._release_instance_guard()
            if self._app is not None:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(800, self._app.quit)

    def _tick(self) -> None:
        # Advance anything that depends on the clock before drawing.
        self.state.settle()
        self._poll_status()
        self._drain()
        self._drain_updates()
        if self._pending_sound:
            self._pending_sound = False
            if self.config.alerts.sound_enabled:
                self.sound.play()
        if self.hud is not None:
            self.hud.rebuild()

    # -- text rendering (headless) -----------------------------------------

    def render_text_line(self) -> str:
        from .formatting import format_credits, format_countdown

        state = self.state
        parts: list[str] = []
        remaining = state.carrier.seconds_until_jump()
        if remaining is not None:
            target = f" -> {state.carrier.target_system}" if state.carrier.target_system else ""
            parts.append(f"ФК{target} {format_countdown(remaining)}")
        if state.system.name:
            parts.append(f"{state.system.name} {state.system.body_count} тел")
            parts.append(f"FSS {state.system.progress_percent:.0f}%")
            parts.append(
                f"БИО {state.system.bio_signal_total}"
                f" ({state.system.bio_body_count} тел)"
            )
            if state.system.best_confidence is not Confidence.NONE:
                parts.append(
                    f"[{state.system.best_confidence.value}] {state.system.best_label} "
                    f"{format_credits(state.system.best_value)}"
                )
        return "  |  ".join(parts) if parts else "(нет данных)"

    # -- lifecycle ---------------------------------------------------------

    def start_sources(self) -> None:
        if self.options.replay is not None:
            self.replay = ReplaySource(
                self.options.replay,
                self.events,
                speed=self.options.speed,
                loop=self.options.replay_loop,
                live=self.options.replay_live,
            )
            self.replay.start()
            log.info("replaying %s", self.options.replay)
            return

        directory = find_journal_dir(
            str(self.options.journal_dir) if self.options.journal_dir else self.config.journal.path
        )
        if directory is None:
            log.error(
                "no journal directory found; set journal.path in %s", CONFIG_FILENAME
            )
            return
        log.info("watching %s", directory)
        self._start_status_reader(directory)
        self.watcher = JournalWatcher(
            directory,
            self._on_journal_event,
            poll_interval=self.config.journal.poll_interval,
            history_days=self.config.journal.history_days,
            replay_history=self.config.journal.replay_history,
            on_status=lambda message: log.debug("watcher: %s", message),
        )
        self.watcher.start()

    def stop_sources(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
        if self.replay is not None:
            self.replay.stop()

    def shutdown(self) -> None:
        self.stop_sources()
        self.updates.stop()
        if self.hud is not None:
            self.hud.close()
            self.hud = None

    # -- Qt ----------------------------------------------------------------

    def _build_tray(self, app) -> None:
        from PySide6.QtGui import QActionGroup, QColor
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        from .overlay.icons import icon_pixmap

        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.debug("no system tray available")
            return

        tray = QSystemTrayIcon(icon_pixmap(64, "bio", QColor(self.config.overlay.accent)))
        tray.setToolTip(f"elite-hud {__version__}")
        tray.activated.connect(lambda reason: self._toggle_hud())

        menu = QMenu()
        menu.addAction("Показать / скрыть HUD", self._toggle_hud)
        menu.addAction("Открыть config.toml", self._open_config)
        menu.addSeparator()
        self._build_faction_menu(menu)
        self._build_segment_menus(menu)
        menu.addSeparator()
        self._build_monitor_menu(menu)
        menu.addSeparator()
        self._build_update_menu(menu, app)
        menu.addSeparator()
        menu.addAction("Выход", app.quit)

        tray.setContextMenu(menu)
        tray.show()
        self.tray = tray

    def _build_faction_menu(self, menu) -> None:
        """Ask for a faction to follow, rather than making anyone edit a file."""
        submenu = menu.addMenu("Фракция")
        current = self.config.faction.name
        label = current or "не выбрана"
        self._faction_actions["status"] = submenu.addAction(f"Отслеживается: {label}")
        self._faction_actions["status"].setEnabled(False)
        submenu.addAction("Задать фракцию…", self._prompt_faction)
        if current:
            submenu.addAction("Не отслеживать", lambda: self._set_faction(""))

    def _prompt_faction(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, accepted = QInputDialog.getText(
            None,
            "elite-hud",
            "Название фракции (совпадение нестрогое):",
            text=self.config.faction.name,
        )
        if accepted:
            self._set_faction(str(name).strip())

    def _set_faction(self, name: str) -> None:
        self.config.faction.name = name
        self.config.validate()
        path = default_config_path(self.options.config)
        persisted = set_config_value(path, "faction", "name", name)
        action = self._faction_actions.get("status")
        if action is not None:
            action.setText(f"Отслеживается: {name or 'не выбрана'}")
        if self.hud is not None:
            self.hud.rebuild()
        note = "" if persisted else " (не сохранилось в config.toml)"
        log.info("following faction %r%s", name, note)
        if self.tray is not None and name:
            self.tray.showMessage("elite-hud", f"Следим за фракцией: {name}{note}")

    def _build_segment_menus(self, menu) -> None:
        """Tick blocks on and off without editing config.toml by hand.

        Two submenus rather than one, because the two rows are independent: a
        commander who is not working on Empire or Federation standing wants to
        drop those two and keep the rest of the status row.
        """
        top = menu.addMenu("Верхняя строка")
        self._add_segment_actions(top, "segments", SEGMENT_NAMES, self.config.overlay.segments)

        status = menu.addMenu("Строка состояния")
        self._add_segment_actions(
            status, "status_segments", STATUS_SEGMENT_NAMES, self.config.overlay.status_segments
        )

    def _add_segment_actions(self, menu, key: str, names: dict, enabled: list) -> None:
        for value, label in names.items():
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value in enabled)
            action.triggered.connect(
                lambda checked=False, v=value, k=key, a=action: self._toggle_segment(k, v, checked, a)
            )

    def _toggle_segment(self, key: str, value: str, enabled: bool, action) -> None:
        """Add or remove one segment, in the configured order."""
        order = list(SEGMENT_NAMES if key == "segments" else STATUS_SEGMENT_NAMES)
        current = toggle_segment(list(getattr(self.config.overlay, key)), order, value, enabled)
        setattr(self.config.overlay, key, current)
        self.config.validate()
        persisted = set_config_list(
            default_config_path(self.options.config), "overlay", key, list(getattr(self.config.overlay, key))
        )

        # validate() may have dropped something it does not recognise; reflect
        # that back onto the checkbox so the menu cannot lie about the state.
        action.setChecked(value in getattr(self.config.overlay, key))

        if self.hud is not None:
            self.hud.rebuild()
        note = "" if persisted else " (не сохранилось в config.toml)"
        log.info("overlay.%s = %s%s", key, getattr(self.config.overlay, key), note)

    def _build_monitor_menu(self, menu) -> None:
        """Let the user pick a display without editing the config by hand."""
        from PySide6.QtGui import QActionGroup

        from .overlay.hud import HudWindow

        monitors = menu.addMenu("Монитор")
        group = QActionGroup(menu)
        group.setExclusive(True)
        current = self.config.overlay.monitor
        for value, label in HudWindow.screen_choices():
            action = monitors.addAction(label)
            action.setCheckable(True)
            action.setChecked(value == current)
            action.triggered.connect(lambda _checked=False, v=value: self._set_monitor(v))
            group.addAction(action)
        self._monitor_group = group

    def _set_monitor(self, value: str) -> None:
        self.config.overlay.monitor = value
        self.config.validate()
        path = default_config_path(self.options.config)
        persisted = set_config_value(path, "overlay", "monitor", value)
        if self.hud is not None:
            self.hud.reposition(force=True)
        note = "" if persisted else " (не сохранилось в config.toml)"
        where = self.hud.screen_label() if self.hud is not None else value
        log.info("HUD monitor set to %s%s", value, note)
        if self.tray is not None:
            self.tray.showMessage("elite-hud", f"HUD на мониторе: {where}{note}")

    def _build_update_menu(self, menu, app) -> None:
        from PySide6.QtGui import QActionGroup

        status = menu.addAction(
            f"elite-hud {__version__}" if not self.updates.enabled else "обновления включены"
        )
        status.setEnabled(False)
        self._update_actions["status"] = status

        check = menu.addAction("Проверить обновления", self._check_updates_now)
        self._update_actions["check"] = check

        install = menu.addAction("Обновление не найдено")
        install.setEnabled(False)
        install.triggered.connect(lambda: self.updates.download_and_install())
        self._update_actions["install"] = install

        if not self.updates.enabled:
            check.setEnabled(False)

        modes = menu.addMenu("Режим обновлений")
        group = QActionGroup(menu)
        group.setExclusive(True)
        labels = {
            "install": "Скачивать и устанавливать",
            "download": "Ставить при следующем запуске",
            "notify": "Только уведомлять",
            "off": "Выключено",
        }
        for mode, label in labels.items():
            action = modes.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.config.update.mode == mode)
            action.triggered.connect(lambda _checked=False, m=mode: self._set_update_mode(m))
            group.addAction(action)
        self._update_mode_group = group

        menu.addAction("Заметки о выпуске", self._open_release_page)

    def _release_instance_guard(self) -> None:
        """Drop the single-instance mutex before Setup replaces our files.

        The hook runs on the update worker thread, so it must not touch Qt.
        """
        if self.instance is not None:
            log.debug("releasing the instance guard so the installer can proceed")
            self.instance.release()

    def _check_updates_now(self) -> None:
        self.updates.check_async(interact=True)

    def _set_update_mode(self, mode: str) -> None:
        self.config.update.mode = mode
        self.config.validate()
        path = default_config_path(self.options.config)
        persisted = set_update_mode(path, mode)
        self.updates.check_async(interact=True)
        note = "" if persisted else " (не сохранилось в config.toml)"
        log.info("update mode set to %s%s", mode, note)
        if self.tray is not None:
            self.tray.showMessage(
                "elite-hud",
                f"режим обновлений: {mode}{note}",
            )

    def _open_release_page(self) -> None:
        import subprocess
        import webbrowser

        update = self.updates.available
        url = (
            update.release.html_url
            if update is not None and update.release.html_url
            else f"https://github.com/{self.config.update.repo}/releases"
        )
        try:
            webbrowser.open(url)
        except Exception:
            log.exception("cannot open %s", url)

    def _toggle_hud(self) -> None:
        if self.hud is None:
            return
        if self.hud.isVisible():
            self.hud.hide()
        else:
            self.hud.show_overlay()

    def _open_config(self) -> None:
        import subprocess

        path = default_config_path(self.options.config)
        if not path.is_file():
            ensure_config_file(path)
        try:
            if sys.platform == "win32":
                import os

                os.startfile(path)  # noqa: S606 - intentional shell open
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            log.exception("cannot open %s", path)

    def _prepare_updates(self, interactive_ui: bool) -> None:
        """Apply a staged update, then start watching for new ones."""
        from .updater import clear_stale_marker

        if clear_stale_marker():
            log.info("removed a leftover update marker from an interrupted update")
        self.updates.prune_downloads()

        if self.updates.enabled and self.config.update.mode == "download":
            if self.updates.apply_pending():
                # The installer needs this process gone; exit without a UI.
                log.info("exiting so the staged update can be installed")
                self._exit_for_update = True
                return

        if not self.updates.enabled:
            return
        self.updates.start()
        if interactive_ui:
            self._schedule_update_checks()

    def _schedule_update_checks(self) -> None:
        from PySide6.QtCore import QTimer

        interval_ms = int(self.config.update.check_interval_hours * 3600 * 1000)
        timer = QTimer(self._app)
        timer.setInterval(max(60_000, interval_ms))

        def tick() -> None:
            if self.updates.due_for_check():
                self.updates.check_async()

        timer.timeout.connect(tick)
        timer.start()
        self._update_timer = timer

    def run(self) -> int:
        if not self.options.headless:
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication

            from .overlay.hud import HudWindow

            # The QApplication must exist before anything creates a QTimer.
            self._app = QApplication(sys.argv[:1])
            self._app.setApplicationName("elite-hud")
            self._app.setQuitOnLastWindowClosed(False)

            if not self.options.force and self.options.replay is None:
                self.instance = SingleInstanceGuard()
                if not self.instance.acquire():
                    log.error(
                        "elite-hud уже запущен (второй экземпляр не нужен); "
                        "используйте --force, чтобы обойти проверку"
                    )
                    return 3

            # May apply a staged update and ask us to exit without a UI.
            self._prepare_updates(interactive_ui=True)
            if self._exit_for_update:
                return 0

            self.hud = HudWindow(self.config, self.state)
            self.hud.show_overlay()
            self._build_tray(self._app)

            interval = max(16, int(1000 / self.config.overlay.refresh_hz))

            def on_quit(*_args) -> None:
                self.shutdown()
                self._app.quit()

            signal.signal(signal.SIGINT, lambda *_: on_quit())
            # Lets Python-level signal handlers run while Qt owns the loop.
            keepalive = QTimer(self._app)
            keepalive.start(200)
            keepalive.timeout.connect(lambda: None)
            self._app.aboutToQuit.connect(self.shutdown)

            timer = QTimer(self._app)
            timer.timeout.connect(self._tick)
            timer.start(interval)

            self.start_sources()
            log.info("HUD running; exit from the tray icon or press Ctrl+C")
            return self._app.exec()

        # Headless: plain loop, useful on machines without a display.
        self._prepare_updates(interactive_ui=False)
        self.start_sources()
        log.info("headless mode; Ctrl+C to stop")
        try:
            while True:
                self._tick()
                if self.replay is not None and not self._replay_alive():
                    # Producer is done; keep draining until the queue is empty.
                    while not self.events.empty():
                        self._tick()
                    break
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()
        return 0

    def _replay_alive(self) -> bool:
        return self.replay is not None and self.replay.is_alive()


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)

    config_path = default_config_path(options.config)
    # `--list-genera` is a read-only query and must not leave a file behind.
    created = False if options.list_genera else ensure_config_file(config_path)
    config = Config.load(config_path)
    setup_logging(config, options.verbose)
    if created:
        log.info("wrote default config to %s", config_path)
    elif not options.list_genera:
        # A config file is written once and then left alone, so settings added
        # by a newer version would otherwise be invisible: the commander opens
        # the file to set the new option and finds nothing to set.
        added = add_missing_sections(config_path, config)
        if added:
            log.info("config.toml gained sections: %s", ", ".join(added))

    if options.make_config:
        print(f"config: {config_path}")
        return 0

    if options.list_genera:
        table = ExobiologyTable()
        table.apply_overrides(config.exobiology_overrides)
        print_genera(table, config.alerts.min_value)
        return 0

    if options.carrier_report:
        return run_carrier_report(config, options)

    if options.self_check:
        return run_self_check(config)

    if options.check_update:
        return run_update_check(config, options)

    app = HudApp(config, options)
    return app.run()


def run_carrier_report(config: Config, options: argparse.Namespace) -> int:
    """Print what the journals actually say about carrier jumps.

    The cooldown is nowhere in the journal, so the only way to settle how long
    it really is on a given account is to look at the gaps between what the
    commander actually did: departure to departure, and departure to the next
    request. If they asked for the next jump as soon as the game allowed it, the
    shortest such gap is the cooldown.
    """
    from .journal.watcher import list_journals

    directory = find_journal_dir(
        str(options.journal_dir) if options.journal_dir else config.journal.path
    )
    if directory is None:
        print("не найдена папка с журналами; укажите --journal-dir")
        return 1

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=config.journal.history_days)
    ).timestamp()
    records: list[tuple[datetime, str, dict]] = []
    for path in list_journals(directory):
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    name = str(event.get("event") or "")
                    if not name.startswith("Carrier"):
                        continue
                    stamp = parse_timestamp(event.get("timestamp"))
                    if stamp is not None:
                        records.append((stamp, name, event))
        except OSError as exc:
            print(f"не удалось прочитать {path.name}: {exc}", file=sys.stderr)

    if not records:
        print(f"в {directory} не найдено событий флотоносца")
        return 0

    records.sort(key=lambda item: item[0])
    print(f"журналы: {directory}")
    print(f"событий флотоносца: {len(records)}\n")

    requests: list[tuple[datetime, datetime]] = []
    arrivals: list[tuple[datetime, str]] = []
    for stamp, name, event in records:
        if name == "CarrierJumpRequest":
            departure = parse_timestamp(event.get("DepartureTime"))
            target = event.get("SystemName") or "?"
            if departure is None:
                print(f"{stamp:%Y-%m-%d %H:%M:%S}  запрос -> {target}  (без DepartureTime)")
                continue
            spool = (departure - stamp).total_seconds()
            requests.append((stamp, departure))
            print(
                f"{stamp:%Y-%m-%d %H:%M:%S}  запрос -> {target}"
                f"  отправление {departure:%H:%M:%S}  разгон {spool/60:5.2f} мин"
            )
        elif name == "CarrierJump":
            arrivals.append((stamp, "прибытие"))
            print(f"{stamp:%Y-%m-%d %H:%M:%S}  ПРИБЫТИЕ (игрок был на борту)")
        elif name == "CarrierJumpCancelled":
            print(f"{stamp:%Y-%m-%d %H:%M:%S}  отмена запроса")
        elif name == "CarrierLocation":
            print(f"{stamp:%Y-%m-%d %H:%M:%S}  местоположение: {event.get('StarSystem') or '?'}")

    if len(requests) < 2:
        print("\nДля оценки перезарядки нужно минимум два запроса прыжка.")
        return 0

    print("\n=== промежутки между последовательными прыжками ===")
    print("  (от отправления предыдущего до запроса следующего)")

    gaps: list[float] = []
    retargets = 0
    for (previous_request, previous_departure), (next_request, _) in zip(requests, requests[1:]):
        gap = (next_request - previous_departure).total_seconds()
        if gap <= 0 or next_request <= previous_request:
            # Asking again while the current spool-up is still running just
            # changes the destination; it is not a new jump cycle.
            retargets += 1
            print(f"  {previous_departure:%m-%d %H:%M:%S} -> {next_request:%m-%d %H:%M:%S}"
                  f"   {gap/60:6.2f} мин  <- смена цели во время разгона")
            continue
        gaps.append(gap)
        print(f"  {previous_departure:%m-%d %H:%M:%S} -> {next_request:%m-%d %H:%M:%S}"
              f"   {gap/60:6.2f} мин")

    if retargets:
        print(f"\n  ({retargets} запрос(ов) пропущено как смена цели, а не новый прыжок)")

    if not gaps:
        print("\nГодных промежутков нет.")
        return 0

    shortest = min(gaps)
    shortest_three = sorted(gaps)[:3]
    print(f"\nсамый короткий промежуток: {shortest/60:.2f} мин ({shortest:.0f} с)")
    print(f"три самых коротких: {[round(g) for g in shortest_three]} с")
    print(
        f"\nзапрос проходил уже через {shortest:.0f} с после отправления, значит перезарядка"
        f"\nне больше этого — то есть не длиннее {shortest/60:.2f} мин."
    )
    configured = config.carrier.jump_cooldown_seconds
    verdict = "согласуется" if configured <= shortest else "БОЛЬШЕ измеренного — покажет готовность позже, чем игра"
    print(f"\nсейчас в конфиге: carrier.jump_cooldown_seconds = {configured:.0f}  ({verdict})")
    return 0


def run_self_check(config: Config) -> int:
    """Verify that a frozen or source install is actually intact.

    Written for the release workflow: a windowed executable has no console, so
    the only dependable signal it can give a build script is its exit code.
    """
    from .updater import clear_stale_marker

    problems: list[str] = []

    table = ExobiologyTable()
    applied = table.apply_overrides(config.exobiology_overrides)
    genera = len(table.genera_by_key)
    species = len(table.species_by_key)
    print(f"version              {__version__}")
    print(f"exobiology table     {genera} genera, {species} species ({applied} overrides)")
    if genera < 15 or species < 80:
        problems.append("the bundled exobiology table is missing or truncated")
    for name in ("Stratum Tectonicas", "Fonticulua Fluctus"):
        if table.species(name) is None:
            problems.append(f"the exobiology table has no entry for {name}")

    data_path = Path(__file__).resolve().parent / "data" / "exobiology.json"
    print(f"data file            {data_path} ({'present' if data_path.is_file() else 'MISSING'})")
    if not data_path.is_file():
        problems.append(f"{data_path} does not exist")

    sounds = SoundPlayer(config.alerts.sound_file, config.alerts.volume)
    print(f"alert sound          {'ready' if sounds.available else 'unavailable'}")

    journal = find_journal_dir(config.journal.path)
    print(f"journal directory    {journal or 'not found (harmless outside the game)'}")

    if clear_stale_marker():
        print("note                 cleared a leftover update marker")

    if problems:
        for problem in problems:
            print(f"PROBLEM: {problem}", file=sys.stderr)
        return 1
    print("self-check OK")
    return 0


#: Exit codes of --check-update, for scripting.
EXIT_UP_TO_DATE = 0
EXIT_UPDATE_AVAILABLE = 10
EXIT_UPDATE_CHECK_FAILED = 1
EXIT_UPDATES_DISABLED = 11


def run_update_check(config: Config, options: argparse.Namespace) -> int:
    """Print the result of an update check and exit. Used by scripts and CI."""
    from .updater import format_size

    if not config.update.enabled:
        print("проверка обновлений выключена (update.enabled = false)")
        return EXIT_UPDATES_DISABLED

    service = UpdateService(config.update, current_version=__version__)
    result = service.check_now()

    if result.status == "error":
        print(f"ошибка: {result.message}")
        return EXIT_UPDATE_CHECK_FAILED
    if not result.has_update:
        print(f"elite-hud {__version__} — обновлений нет")
        return EXIT_UP_TO_DATE

    update = result.update
    assert update is not None
    print(f"доступна версия {update.version} (у вас {__version__})")
    print(f"  файл:  {update.asset.name} ({format_size(update.asset.size)})")
    print(f"  режим: {config.update.mode}, архив: {service.install.mode}")
    if update.release.published_at:
        print(f"  дата:  {update.release.published_at:%Y-%m-%d}")
    if update.release.html_url:
        print(f"  релиз: {update.release.html_url}")
    if update.notes and options.verbose:
        print()
        print(update.notes.strip())
    return EXIT_UPDATE_AVAILABLE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
