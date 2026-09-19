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
from .config import (
    CONFIG_FILENAME,
    SEGMENT_NAMES,
    STATUS_SEGMENT_NAMES,
    Config,
    add_missing_sections,
    config_is_writable,
    ensure_config_file,
    resolve_config_path,
    set_config_list,
    user_config_dir,
    toggle_segment,
    set_config_value,
    set_update_mode,
)
from .installation import SingleInstanceGuard
from .journal.watcher import JournalWatcher
from .paths import expand_user_path, find_journal_dir
from .state import GameState, parse_timestamp
from .status import StatusReader
from .update_service import UpdateEvent, UpdateService

log = logging.getLogger("elite_hud")


def _rgb(values, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    """A configured colour as an RGB triple, falling back when it is unusable."""
    try:
        parts = [max(0, min(255, int(v))) for v in values]
    except (TypeError, ValueError):
        return fallback
    if len(parts) != 3:
        return fallback
    return parts[0], parts[1], parts[2]


def _monotonic() -> float:
    import time  # noqa: PLC0415

    return time.monotonic()


def qt_text(text: str) -> str:
    """Make a string safe to show in a Qt widget.

    Qt reads a single ``&`` in a menu or action label as the mnemonic marker and
    does not draw it, so a faction called "Traders & Explorers" appeared as
    "Traders  Explorers" and looked like the ampersand had been rejected. The
    doubled form is how Qt spells a literal one.
    """
    return str(text).replace("&", "&&")

#: Never apply more than this many events in a single UI tick, so a long
#: history replay cannot freeze the overlay.
MAX_EVENTS_PER_TICK = 2000



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


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)

    config_path = default_config_path(options.config)
    created = ensure_config_file(config_path)
    config = Config.load(config_path)
    setup_logging(config, options.verbose)
    if created:
        log.info("wrote default config to %s", config_path)
    else:
        # A config file is written once and then left alone, so settings added
        # by a newer version would otherwise be invisible: the commander opens
        # the file to set the new option and finds nothing to set.
        added = add_missing_sections(config_path, config)
        if added:
            log.info("config.toml gained sections: %s", ", ".join(added))

    if options.make_config:
        print(f"config: {config_path}")
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

    print(f"version              {__version__}")
    print(f"config               {default_config_path(None)}"
          f" ({'writable' if config_is_writable(default_config_path(None)) else 'NOT WRITABLE'})")
    if not config_is_writable(default_config_path(None)):
        problems.append("settings cannot be saved: the config file is not writable")

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
