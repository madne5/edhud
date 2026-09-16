"""Background update orchestration.

All network work happens on a worker thread and is reported back as
:class:`UpdateEvent` objects on a queue, which the Qt timer drains.  That keeps
the overlay's paint loop free of blocking calls, exactly like the journal
watcher.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .config import UpdateConfig
from .installation import InstallInfo, detect_install, needs_elevation
from .updater import (
    CheckResult,
    GitHubClient,
    GitHubError,
    UpdateChecker,
    UpdateDownloader,
    UpdateInfo,
    apply_installer,
    apply_portable,
    default_download_dir,
    stage_portable,
)

log = logging.getLogger(__name__)

#: ``update.mode`` values that fetch the package by themselves.
AUTO_DOWNLOAD_MODES = {"download", "install"}

#: How long a download waits for the check to finish before giving up loudly.
BUSY_ACQUIRE_TIMEOUT = 90.0

PENDING_FILENAME = "pending-update.json"


@dataclass
class UpdateEvent:
    """One step of the update lifecycle, for the UI to display."""

    kind: str  #: checking | current | available | downloading | staged | applying | error
    message: str
    update: UpdateInfo | None = None
    progress: float = 0.0


class UpdateService:
    """Checks for, downloads and applies new releases."""

    def __init__(
        self,
        config: UpdateConfig,
        *,
        current_version: str = __version__,
        on_event=None,
        install: InstallInfo | None = None,
        download_dir: Path | None = None,
        client_factory=None,
        on_before_apply=None,
    ) -> None:
        self.config = config
        self.current_version = current_version
        self.on_event = on_event
        self.install = install or detect_install()
        self.download_dir = download_dir or default_download_dir()
        #: seam for tests: (repo, token, timeout) -> GitHubClient
        self._client_factory = client_factory
        #: called right before the installer runs, while we still hold locks
        self.on_before_apply = on_before_apply

        self.available: UpdateInfo | None = None
        self.last_check: float = 0.0
        self.last_error: str = ""
        self._busy = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- helpers -----------------------------------------------------------

    def _emit(self, event: UpdateEvent) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception:  # pragma: no cover - defensive
            log.debug("update event handler failed", exc_info=True)

    def _client(self) -> GitHubClient:
        if self._client_factory is not None:
            return self._client_factory(
                self.config.repo, self.config.token, self.config.timeout_seconds
            )
        return GitHubClient(
            self.config.repo,
            token=self.config.token,
            timeout=self.config.timeout_seconds,
        )

    def check_now(self) -> "CheckResult":
        """Synchronous check; used by ``--check-update`` and the workers."""
        return self._checker(self._client()).check()

    def _checker(self, client: GitHubClient) -> UpdateChecker:
        preference = self.config.asset
        if preference == "any":
            preference = self.install.update_preference
        return UpdateChecker(
            self.config.repo,
            self.current_version,
            token=self.config.token,
            allow_prerelease=self.config.include_prerelease,
            prefer=preference,
            client=client,
        )

    @property
    def enabled(self) -> bool:
        return self.config.enabled and self.config.mode != "off"

    def due_for_check(self, now: float | None = None) -> bool:
        if not self.enabled:
            return False
        now = now if now is not None else time.monotonic()
        interval = self.config.check_interval_hours * 3600.0
        return (now - self.last_check) >= interval

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Kick off the first check if the config asks for one."""
        if self.config.check_on_start:
            self.check_async()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    def check_async(self, *, interact: bool = False) -> None:
        if self._busy.locked():
            log.debug("update check already running")
            if interact:
                self._emit(UpdateEvent("busy", "проверка обновлений уже идёт…"))
            return
        self._thread = threading.Thread(
            target=self._check_worker,
            args=(interact,),
            name="update-check",
            daemon=True,
        )
        self._thread.start()

    # -- workers -----------------------------------------------------------

    def _check_worker(self, interact: bool) -> None:
        pending: UpdateInfo | None = None
        install_now = False

        with self._busy:
            self._emit(UpdateEvent("checking", "проверка обновлений…"))
            try:
                result = self.check_now()
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("update check crashed")
                self.last_error = str(exc)
                self._emit(UpdateEvent("error", f"ошибка проверки обновлений: {exc}"))
                return

            self.last_check = time.monotonic()
            if result.status == "error":
                self.last_error = result.message
                self._emit(UpdateEvent("error", result.message))
                return
            if not result.has_update:
                self.last_error = ""
                if interact:
                    self._emit(UpdateEvent("current", f"установлена последняя версия ({self.current_version})"))
                return

            self.available = result.update
            assert self.available is not None
            self._emit(
                UpdateEvent(
                    "available",
                    f"доступна версия {self.available.version}",
                    self.available,
                )
            )
            if self.config.mode in AUTO_DOWNLOAD_MODES:
                pending = self.available
                install_now = self.config.mode == "install"

        # Deliberately outside the `with`: _download_worker acquires the same
        # lock, so calling it inline deadlocked the worker thread and left the
        # lock held for the life of the process -- which made the tray's
        # "install" entry do nothing at all.
        if pending is not None:
            self._start_download(pending, install_now=install_now)

    def _start_download(self, update: UpdateInfo, *, install_now: bool) -> None:
        threading.Thread(
            target=self._download_worker,
            args=(update,),
            kwargs={"install_now": install_now},
            name="update-download",
            daemon=True,
        ).start()

    def download_and_install(self, update: UpdateInfo | None = None) -> None:
        """User-triggered download + apply, used by the tray menu."""
        target = update or self.available
        if target is None:
            self._emit(UpdateEvent("error", "нет доступного обновления"))
            return
        if self._busy.locked():
            log.info("install requested while update work is already running")
            self._emit(UpdateEvent("busy", "обновление уже загружается, подождите…"))
            return
        self._start_download(target, install_now=True)

    def _download_worker(self, update: UpdateInfo, *, install_now: bool) -> None:
        # Bounded rather than `with`: if this lock is ever held for the life of
        # the process again, the user should see an error instead of an install
        # button that quietly does nothing.
        if not self._busy.acquire(timeout=BUSY_ACQUIRE_TIMEOUT):
            log.error("the update lock is still held after %.0fs", BUSY_ACQUIRE_TIMEOUT)
            self._emit(
                UpdateEvent("error", "не удалось начать загрузку: другая задача не завершилась")
            )
            return
        try:
            try:
                client = self._client()
                downloader = UpdateDownloader(client, self.download_dir)
                last_report = 0.0

                def progress(received: int, total: int) -> None:
                    nonlocal last_report
                    now = time.monotonic()
                    if now - last_report < 0.25:
                        return
                    last_report = now
                    fraction = (received / total) if total else 0.0
                    self._emit(
                        UpdateEvent(
                            "downloading",
                            f"загрузка обновления {update.version}…",
                            update,
                            fraction,
                        )
                    )

                path = downloader.fetch(update, progress=progress)
                log.info("downloaded %s to %s", update.asset.name, path)
            except GitHubError as exc:
                self.last_error = str(exc)
                self._emit(UpdateEvent("error", str(exc)))
                return
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("update download crashed")
                self.last_error = str(exc)
                self._emit(UpdateEvent("error", f"не удалось скачать обновление: {exc}"))
                return

            if not install_now:
                self.mark_pending(update, path)
                self._emit(
                    UpdateEvent(
                        "staged",
                        f"обновление {update.version} загружено и будет установлено при следующем запуске",
                        update,
                    )
                )
                return

            self.clear_pending()
            self._emit(UpdateEvent("applying", f"установка версии {update.version}…", update))
            self._before_apply()
            try:
                self.apply(update, path)
            except GitHubError as exc:
                self.last_error = str(exc)
                self._emit(UpdateEvent("error", str(exc)))
                return
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("applying the update crashed")
                self.last_error = str(exc)
                self._emit(UpdateEvent("error", f"не удалось установить обновление: {exc}"))
                return
            self._emit(UpdateEvent("applied", "обновление установлено, перезапуск…", update))
        finally:
            self._busy.release()

    def apply(self, update: UpdateInfo, path: Path) -> None:
        """Hand the downloaded package to the platform-specific installer."""
        if path.suffix.lower() == ".zip":
            staging = stage_portable(path, self.download_dir / "staged")
            apply_portable(staging)
        else:
            # Only ask for administrator rights when the install directory
            # actually needs them; a per-user install updates silently.
            apply_installer(path, elevate=needs_elevation(self.install.location))

    # -- pending update (download mode) ------------------------------------

    @property
    def pending_path(self) -> Path:
        return self.download_dir / PENDING_FILENAME

    def mark_pending(self, update: UpdateInfo, path: Path) -> None:
        try:
            self.pending_path.parent.mkdir(parents=True, exist_ok=True)
            self.pending_path.write_text(
                json.dumps(
                    {
                        "version": update.version,
                        "asset": update.asset.name,
                        "path": str(path),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("cannot record the pending update: %s", exc)

    def clear_pending(self) -> None:
        self.pending_path.unlink(missing_ok=True)

    def take_pending(self) -> tuple[str, Path] | None:
        """Pop a staged update recorded by ``update.mode = "download"``."""
        try:
            payload = json.loads(self.pending_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        path = Path(str(payload.get("path", "")))
        version = str(payload.get("version", ""))
        if not path.is_file():
            self.clear_pending()
            return None
        return version, path

    def apply_pending(self) -> bool:
        """Apply a staged update. Returns True when the caller should exit."""
        staged = self.take_pending()
        if staged is None:
            return False
        version, path = staged
        log.info("applying the update staged earlier (%s)", version)
        self._emit(UpdateEvent("applying", f"установка версии {version}…"))
        self._before_apply()
        try:
            install_update = UpdateInfo(
                release=self._placeholder_release(version), asset=_placeholder_asset(path)
            )
            self.apply(install_update, path)
        except Exception as exc:
            log.exception("staged update failed")
            self._emit(UpdateEvent("error", f"не удалось установить обновление: {exc}"))
            return False
        self.clear_pending()
        self._emit(UpdateEvent("applied", "обновление установлено, перезапуск…"))
        return True

    @staticmethod
    def _placeholder_release(version: str):
        from .updater import Release

        return Release(
            tag=version,
            version=None,
            name=version,
            notes="",
            html_url="",
            published_at=None,
            prerelease=False,
        )

    # -- housekeeping ------------------------------------------------------

    def _before_apply(self) -> None:
        """Give the UI a chance to drop locks before Setup takes over.

        Inno Setup aborts when the ``AppMutex`` is still held: with
        ``/SUPPRESSMSGBOXES`` it cannot even show the "close the application"
        prompt, so it exits without installing. Releasing our single-instance
        guard first removes that race entirely.
        """
        if self.on_before_apply is None:
            return
        try:
            self.on_before_apply()
        except Exception:  # pragma: no cover - defensive
            log.debug("before-apply hook failed", exc_info=True)

    def prune_downloads(self, keep: int = 2) -> int:
        """Delete old packages so the cache directory cannot grow forever."""
        if self.config.keep_downloads:
            return 0
        try:
            files = sorted(
                (p for p in self.download_dir.iterdir() if p.is_file() and p.name != PENDING_FILENAME),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return 0
        removed = 0
        for path in files[keep:]:
            try:
                path.unlink()
                removed += 1
            except OSError:
                log.debug("cannot remove %s", path)
        return removed


def _placeholder_asset(path: Path):
    from .updater import Asset

    return Asset(name=path.name, url=str(path), size=0)

