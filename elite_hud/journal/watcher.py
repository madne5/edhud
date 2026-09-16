"""Tail Elite Dangerous journal files.

The game rotates ``Journal.<timestamp>.<nn>.log`` on every launch, so the
watcher has to cope with new files appearing, files disappearing (EDMC and
similar tools move them) and the last line being only partially flushed.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

JOURNAL_GLOB = "Journal.*.log"
#: Live 4.x naming: Journal.2022-06-07T181623.01.log
JOURNAL_RE = re.compile(r"^Journal\.(\d{4}-\d{2}-\d{2}T\d{6})\.(\d+)\.log$", re.IGNORECASE)
#: Legacy 3.x naming: Journal.161114145328.01.log (YYMMDDHHMMSS)
LEGACY_JOURNAL_RE = re.compile(r"^Journal\.(\d{12})\.(\d+)\.log$", re.IGNORECASE)


def journal_sort_key(path: Path) -> tuple[str, int]:
    """Chronological key; anything unrecognised sorts last by plain name.

    Both filename generations are normalised to the same ``YYYY-MM-DDTHHMMSS``
    shape so a directory holding legacy and current logs still sorts correctly.
    """
    match = JOURNAL_RE.match(path.name)
    if match:
        return (match.group(1), int(match.group(2)))

    match = LEGACY_JOURNAL_RE.match(path.name)
    if match:
        raw = match.group(1)
        # The game shipped in 2014, so a two digit year is always 20xx.
        iso = f"20{raw[0:2]}-{raw[2:4]}-{raw[4:6]}T{raw[6:12]}"
        return (iso, int(match.group(2)))

    return (path.name, 0)


def list_journals(directory: Path) -> list[Path]:
    try:
        files = [p for p in directory.glob(JOURNAL_GLOB) if p.is_file()]
    except OSError:
        return []
    return sorted(files, key=journal_sort_key)


class JournalTailer:
    """Read complete lines out of one journal file, remembering the offset."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self._offset = 0
        self._partial = b""

    def switch_to(self, path: Path, *, from_start: bool = False) -> None:
        if self.path == path and not from_start:
            return
        self.path = path
        self._offset = 0 if from_start else self._safe_size(path)
        self._partial = b""

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def read_new_lines(self) -> Iterator[str]:
        """Yield every newly completed line, tolerating truncation/rotation."""
        path = self.path
        if path is None:
            return

        size = self._safe_size(path)
        if size < self._offset:
            # File was truncated or replaced under us; start over.
            log.debug("journal %s shrank, restarting from 0", path.name)
            self._offset = 0
            self._partial = b""

        if size == self._offset:
            return

        try:
            with open(path, "rb") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
                self._offset = handle.tell()
        except OSError as exc:
            log.warning("cannot read %s: %s", path, exc)
            return

        data = self._partial + chunk
        parts = data.split(b"\n")
        # The trailing element is either b"" (line complete) or a partial line.
        self._partial = parts.pop()

        for raw in parts:
            line = raw.strip()
            if not line:
                continue
            try:
                yield line.decode("utf-8")
            except UnicodeDecodeError:
                yield line.decode("utf-8", "replace")


class JournalWatcher:
    """Poll the journal directory and hand decoded events to a callback.

    ``on_event`` is invoked on the watcher thread; consumers must be
    thread-safe (the HUD pushes into a queue and drains it on the Qt thread).
    """

    def __init__(
        self,
        directory: Path,
        on_event: Callable[[dict], None],
        *,
        poll_interval: float = 0.75,
        history_days: int = 7,
        replay_history: bool = True,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.directory = directory
        self.on_event = on_event
        self.poll_interval = max(0.05, poll_interval)
        self.history_days = history_days
        self.replay_history = replay_history
        self.on_status = on_status

        self._tailer = JournalTailer()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._seen_files: set[Path] = set()
        self.lines_read = 0
        self.events_delivered = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="journal-watcher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    # -- internals ---------------------------------------------------------

    def _cutoff(self) -> float:
        if self.history_days <= 0:
            return float("-inf")
        return (datetime.now(timezone.utc) - timedelta(days=self.history_days)).timestamp()

    def _status(self, message: str) -> None:
        if self.on_status is not None:
            try:
                self.on_status(message)
            except Exception:  # pragma: no cover - defensive
                log.debug("status callback failed", exc_info=True)

    def _emit_line(self, line: str) -> None:
        self.lines_read += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            log.debug("skipping malformed journal line: %.120s", line)
            return
        if not isinstance(event, dict) or "event" not in event:
            return
        self.events_delivered += 1
        try:
            self.on_event(event)
        except Exception:
            log.exception("event handler failed for %s", event.get("event"))

    def _replay_history(self) -> None:
        """Feed every file in the recent window, oldest first, so state is warm."""
        cutoff = self._cutoff()
        files = list_journals(self.directory)
        for path in files:
            try:
                if path.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        line = line.strip()
                        if line:
                            self._emit_line(line)
            except OSError as exc:
                log.warning("cannot replay %s: %s", path, exc)
            self._seen_files.add(path)

        if files:
            # Hand the newest file to the tailer positioned at its current end.
            self._tailer.switch_to(files[-1])
            self._status(f"replayed {len(self._seen_files)} journal file(s)")

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            files = list_journals(self.directory)
            if not files:
                self._status(f"waiting for journals in {self.directory}")
                self._stop.wait(self.poll_interval)
                continue

            newest = files[-1]
            if self._tailer.path != newest:
                log.info("switching to journal %s", newest.name)
                # Only skip to the end for a brand new file if we are already
                # caught up on the previous one; otherwise read it from 0.
                already_seen = newest in self._seen_files
                self._tailer.switch_to(newest, from_start=not already_seen)
                self._status(f"journal {newest.name}")

            for line in self._tailer.read_new_lines():
                self._emit_line(line)
            self._seen_files.add(newest)

            self._stop.wait(self.poll_interval)

    def _run(self) -> None:
        try:
            if self.replay_history:
                self._replay_history()
            else:
                files = list_journals(self.directory)
                if files:
                    self._tailer.switch_to(files[-1])
                    self._seen_files.add(files[-1])
            self._poll_loop()
        except Exception:
            log.exception("journal watcher died")
            self._status("journal watcher stopped unexpectedly")
