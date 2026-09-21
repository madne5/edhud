"""Tests for the update orchestration layer (modes, staging, housekeeping)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from elite_hud.config import UpdateConfig
from elite_hud.installation import INSTALLED, PORTABLE, SOURCE, InstallInfo
from elite_hud.update_service import UpdateService
from elite_hud.updater import (
    Asset,
    GitHubClient,
    GitHubError,
    Release,
    UpdateInfo,
    Version,
)

def _assets(base: str, *, corrupt_digest: bool = False) -> list[dict]:
    """Release assets with absolute URLs, as the real API returns them.

    The digests are the true SHA-256 of what the server actually returns, so a
    passing test means the checksum path really ran.
    """
    setup_digest = hashlib.sha256(PAYLOAD).hexdigest()
    zip_digest = hashlib.sha256(ZIP_PAYLOAD).hexdigest()
    if corrupt_digest:
        setup_digest = zip_digest = "0" * 64
    return [
        {
            "name": "elite-hud-setup-0.3.0.exe",
            "url": f"{base}/api/asset-setup",
            "browser_download_url": f"{base}/setup.exe",
            "size": len(PAYLOAD),
            "digest": f"sha256:{setup_digest}",
        },
        {
            "name": "elite-hud-0.3.0-win64.zip",
            "url": f"{base}/api/asset-zip",
            "browser_download_url": f"{base}/portable.zip",
            "size": len(ZIP_PAYLOAD),
            "digest": f"sha256:{zip_digest}",
        },
    ]


def _releases(base: str, *, corrupt_digest: bool = False) -> list[dict]:
    return [
        {
            "tag_name": "v0.3.0",
            "name": "elite-hud 0.3.0",
            "body": "notes",
            "html_url": "https://example.invalid/r",
            "published_at": "2026-04-01T10:00:00Z",
            "prerelease": False,
            "assets": _assets(base, corrupt_digest=corrupt_digest),
        },
        {
            "tag_name": "v0.1.0",
            "name": "elite-hud 0.1.0",
            "body": "",
            "html_url": "",
            "published_at": "2026-01-01T10:00:00Z",
            "prerelease": False,
            "assets": [],
        },
    ]

def _zip_bytes() -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("elite-hud/elite-hud.exe", b"MZ fake")
    return buffer.getvalue()


PAYLOAD = b"installer-bytes" * 100
ZIP_PAYLOAD = _zip_bytes()


class _Handler(BaseHTTPRequestHandler):
    corrupt_digest = False

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        base = f"http://{self.headers.get('Host', '127.0.0.1')}"
        if self.path.startswith("/repos/"):
            body = json.dumps(_releases(base, corrupt_digest=self.corrupt_digest)).encode()
        elif self.path in ("/setup.exe", "/api/asset-setup"):
            body = PAYLOAD
        elif self.path in ("/portable.zip", "/api/asset-zip"):
            body = ZIP_PAYLOAD
        else:
            body = b""
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        return


#: The most recently entered server, so tests can reach it from inside a
#: ``with`` block without contorting the fixture.
_last_server: "_Server | None" = None


class _Server:
    """A throwaway HTTP server acting as the GitHub API and asset CDN."""

    def __init__(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def tamper(self, enabled: bool) -> None:
        """Make the server advertise digests that do not match its payloads."""
        self.server.RequestHandlerClass = type(
            "Handler", (_Handler,), {"corrupt_digest": enabled}
        )

    def __enter__(self) -> str:
        global _last_server
        _last_server = self
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class ServiceTestCase(unittest.TestCase):
    def make_service(self, base: str, tmp: Path, **config_kwargs) -> UpdateService:
        config = UpdateConfig(repo="madne5/edhud", **config_kwargs)
        return UpdateService(
            config,
            current_version="0.2.0",
            install=InstallInfo(PORTABLE, tmp),
            download_dir=tmp,
            client_factory=lambda repo, token, timeout: GitHubClient(
                repo, api_base=base, timeout=timeout
            ),
        )


class CheckTests(ServiceTestCase):
    def test_reports_an_available_update(self) -> None:
        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp))
            result = service.check_now()
            self.assertEqual(result.status, "update")
            self.assertEqual(result.update.version, "0.3.0")  # type: ignore[union-attr]

    def test_newer_current_version_is_up_to_date(self) -> None:
        with _Server() as base, TemporaryDirectory() as tmp:
            config = UpdateConfig(repo="madne5/edhud")
            service = UpdateService(
                config,
                current_version="0.4.0",
                download_dir=Path(tmp),
                client_factory=lambda repo, token, timeout: GitHubClient(
                    repo, api_base=base, timeout=timeout
                ),
            )
            self.assertEqual(service.check_now().status, "current")

    def test_disabled_when_repo_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            config = UpdateConfig(repo="")
            service = UpdateService(config, current_version="0.2.0", download_dir=Path(tmp))
            self.assertEqual(service.check_now().status, "disabled")

    def test_portable_and_installed_pick_different_assets(self) -> None:
        with _Server() as base, TemporaryDirectory() as tmp:
            portable = self.make_service(base, Path(tmp))
            self.assertTrue(portable.check_now().update.asset.name.endswith(".zip"))  # type: ignore[union-attr]

            installed = self.make_service(base, Path(tmp))
            installed.install = InstallInfo(INSTALLED, Path(tmp))
            self.assertTrue(  # type: ignore[union-attr]
                installed.check_now().update.asset.name.endswith(".exe")
            )

    def test_explicit_asset_preference_overrides_the_install_mode(self) -> None:
        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), asset="portable")
            service.install = InstallInfo(INSTALLED, Path(tmp))
            self.assertTrue(service.check_now().update.asset.name.endswith(".zip"))  # type: ignore[union-attr]


class EnablementTests(ServiceTestCase):
    def test_disabled_when_mode_is_off(self) -> None:
        with TemporaryDirectory() as tmp:
            service = self.make_service("http://127.0.0.1:1", Path(tmp), mode="off")
            self.assertFalse(service.enabled)

    def test_enabled_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            service = self.make_service("http://127.0.0.1:1", Path(tmp))
            self.assertTrue(service.enabled)

    def test_check_interval_gating(self) -> None:
        with TemporaryDirectory() as tmp:
            service = self.make_service("http://127.0.0.1:1", Path(tmp), check_interval_hours=6.0)
            now = 10_000.0
            service.last_check = now
            self.assertFalse(service.due_for_check(now + 60))
            self.assertFalse(service.due_for_check(now + 5 * 3600))
            self.assertTrue(service.due_for_check(now + 6 * 3600))


class PendingUpdateTests(ServiceTestCase):
    def test_pending_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self.make_service("http://127.0.0.1:1", root)
            package = root / "setup.exe"
            package.write_bytes(b"x")

            info = UpdateInfo(
                release=Release("v0.3.0", Version((0, 3, 0)), "", "", "", None, False),
                asset=Asset("setup.exe", str(package), 1),
            )
            service.mark_pending(info, package)
            self.assertTrue(service.pending_path.is_file())

            staged = service.take_pending()
            self.assertIsNotNone(staged)
            version, path = staged  # type: ignore[misc]
            self.assertEqual(version, "0.3.0")
            self.assertEqual(path, package)

    def test_missing_package_clears_the_record(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self.make_service("http://127.0.0.1:1", root)
            service.pending_path.write_text(
                json.dumps({"version": "0.3.0", "path": str(root / "gone.exe")}),
                encoding="utf-8",
            )
            self.assertIsNone(service.take_pending())
            self.assertFalse(service.pending_path.exists())

    def test_corrupt_record_is_ignored(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self.make_service("http://127.0.0.1:1", root)
            service.pending_path.write_text("not json", encoding="utf-8")
            self.assertIsNone(service.take_pending())


class ApplyHookTests(ServiceTestCase):
    def test_the_instance_guard_is_released_before_the_installer_runs(self) -> None:
        """Inno aborts on a live AppMutex, and /SUPPRESSMSGBOXES hides why."""
        calls: list[str] = []

        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_before_apply = lambda: calls.append("released")

            def fake_apply(update, path) -> None:
                calls.append("applied")

            service.apply = fake_apply  # type: ignore[method-assign]
            result = service.check_now()
            assert result.update is not None
            service.download_and_install(result.update)

            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and "applied" not in calls:
                time.sleep(0.05)

        self.assertEqual(calls, ["released", "applied"])

    def test_a_failing_hook_does_not_block_the_update(self) -> None:
        calls: list[str] = []

        def boom() -> None:
            raise RuntimeError("hook exploded")

        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_before_apply = boom
            service.apply = lambda update, path: calls.append("applied")  # type: ignore[method-assign]
            result = service.check_now()
            assert result.update is not None
            service.download_and_install(result.update)

            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and "applied" not in calls:
                time.sleep(0.05)

        self.assertEqual(calls, ["applied"])


class ApplyFailureTests(ServiceTestCase):
    """A guard released for an installer that never ran has to come back.

    Releasing the single-instance mutex is a bet that Setup takes over. A
    dismissed UAC prompt is how that bet is lost: the HUD keeps running, and if
    it keeps running unguarded then a second instance can start beside it and the
    next installer cannot tell that this one is running.
    """

    def _run_failing_apply(self, service) -> list[str]:
        calls: list[str] = []
        service.on_before_apply = lambda: calls.append("released")
        service.on_apply_failed = lambda: calls.append("reacquired")

        def failing_apply(update, path) -> None:
            calls.append("applied")
            raise GitHubError("UAC отклонён")

        service.apply = failing_apply  # type: ignore[method-assign]
        result = service.check_now()
        assert result.update is not None
        service.download_and_install(result.update)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and "reacquired" not in calls:
            time.sleep(0.05)
        return calls

    def test_the_guard_is_taken_back_when_the_installer_did_not_run(self) -> None:
        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            calls = self._run_failing_apply(service)
        self.assertEqual(calls, ["released", "applied", "reacquired"])

    def test_a_successful_apply_leaves_the_guard_released(self) -> None:
        """The installer needs it gone; the process is about to exit anyway."""
        calls: list[str] = []

        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_before_apply = lambda: calls.append("released")
            service.on_apply_failed = lambda: calls.append("reacquired")
            service.apply = lambda update, path: calls.append("applied")  # type: ignore[method-assign]
            result = service.check_now()
            assert result.update is not None
            service.download_and_install(result.update)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and "applied" not in calls:
                time.sleep(0.05)
            time.sleep(0.2)
        self.assertEqual(calls, ["released", "applied"])

    def test_a_failing_apply_failed_hook_does_not_escape(self) -> None:
        def boom() -> None:
            raise RuntimeError("hook exploded")

        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_apply_failed = boom

            def failing_apply(update, path) -> None:
                raise GitHubError("UAC отклонён")

            service.apply = failing_apply  # type: ignore[method-assign]
            result = service.check_now()
            assert result.update is not None
            service.download_and_install(result.update)
            time.sleep(0.5)


class SourceCheckoutTests(ServiceTestCase):
    """A checkout must never download a release it cannot install."""

    def _source_service(self, base: str, tmp: Path, **config_kwargs) -> UpdateService:
        config = UpdateConfig(repo="madne5/edhud", **config_kwargs)
        return UpdateService(
            config,
            current_version="0.2.0",
            install=InstallInfo(SOURCE, tmp),
            download_dir=tmp,
            client_factory=lambda repo, token, timeout: GitHubClient(
                repo, api_base=base, timeout=timeout
            ),
        )

    def test_an_install_mode_checkout_only_reports_the_version(self) -> None:
        events: list[tuple[str, str]] = []

        with _Server() as base, TemporaryDirectory() as tmp:
            service = self._source_service(base, Path(tmp), mode="install")
            service.on_event = lambda event: events.append((event.kind, event.message))
            service.check_async()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not events:
                time.sleep(0.05)
            time.sleep(0.5)
            downloaded = list(Path(tmp).glob("*"))

        kinds = [kind for kind, _ in events]
        self.assertIn("available", kinds)
        self.assertNotIn("applied", kinds, "a checkout cannot install anything")
        self.assertNotIn("downloading", kinds, "and must not download to find out")
        self.assertEqual([p.name for p in downloaded if p.suffix in (".zip", ".exe")], [])
        self.assertEqual(SOURCE, service.install.mode)


class TamperTests(ServiceTestCase):
    def test_a_wrong_sha256_stops_the_update(self) -> None:
        """The checksum is the only thing between the user and a swapped
        installer, so it has to be enforced all the way through the service."""
        events: list = []
        applied: list[str] = []

        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_event = events.append
            service.apply = lambda update, path: applied.append(path.name)  # type: ignore[method-assign]

            server = _last_server
            assert server is not None
            server.tamper(True)
            try:
                result = service.check_now()
                assert result.update is not None
                service.download_and_install(result.update)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and not any(
                    event.kind in ("error", "applied") for event in events
                ):
                    time.sleep(0.05)
            finally:
                server.tamper(False)

        self.assertEqual(applied, [], "a tampered package was installed")
        self.assertTrue(
            any(event.kind == "error" for event in events),
            f"no error reported; events were {[e.kind for e in events]}",
        )
        self.assertIn("контрольная сумма", " ".join(e.message for e in events))


class AutomaticModeTests(ServiceTestCase):
    """Regression: modes "install" and "download" never downloaded anything.

    _check_worker held the busy lock and then called _download_worker, which
    acquires the same lock. threading.Lock is not reentrant, so the worker
    blocked forever while still holding it -- and every later request, including
    a click on the tray's "install" entry, returned silently at the busy check.
    Nothing in the suite exercised these two modes through check_async(), so it
    shipped.
    """

    @staticmethod
    def _wait_for(predicate, timeout: float = 20.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def test_install_mode_downloads_and_applies_by_itself(self) -> None:
        applied: list[str] = []
        events: list = []
        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="install")
            service.on_event = events.append
            service.apply = lambda update, path: applied.append(update.version)  # type: ignore[method-assign]
            service.check_async()
            waited = self._wait_for(lambda: bool(applied))

        self.assertTrue(
            waited, f"nothing was installed; events were {[e.kind for e in events]}"
        )
        self.assertEqual(applied, ["0.3.0"])

    def test_download_mode_stages_instead_of_applying(self) -> None:
        applied: list[str] = []
        events: list = []
        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="download")
            service.on_event = events.append
            service.apply = lambda update, path: applied.append(update.version)  # type: ignore[method-assign]
            service.check_async()
            waited = self._wait_for(lambda: any(e.kind == "staged" for e in events))
            staged = service.take_pending()

        self.assertTrue(waited, f"nothing was staged; events were {[e.kind for e in events]}")
        self.assertEqual(applied, [], "a staged update must not be applied yet")
        self.assertIsNotNone(staged)
        assert staged is not None
        self.assertEqual(staged[0], "0.3.0")

    def test_a_click_while_busy_is_acknowledged_not_swallowed(self) -> None:
        events: list = []
        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_event = events.append
            result = service.check_now()
            assert result.update is not None

            service._busy.acquire()  # type: ignore[attr-defined]
            try:
                service.download_and_install(result.update)
            finally:
                service._busy.release()  # type: ignore[attr-defined]

        self.assertIn(
            "busy",
            [event.kind for event in events],
            "the request was dropped without telling the user anything",
        )

    def test_an_interactive_check_while_busy_is_reported_too(self) -> None:
        events: list = []
        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_event = events.append
            service._busy.acquire()  # type: ignore[attr-defined]
            try:
                service.check_async(interact=True)
            finally:
                service._busy.release()  # type: ignore[attr-defined]
        self.assertIn("busy", [event.kind for event in events])


class PruneTests(ServiceTestCase):
    def test_keeps_the_newest_packages(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self.make_service("http://127.0.0.1:1", root)
            for index in range(5):
                path = root / f"setup-{index}.exe"
                path.write_bytes(b"x")
                # Stagger modification times so "newest" is unambiguous.
                import os

                os.utime(path, (1_000 + index, 1_000 + index))

            removed = service.prune_downloads(keep=2)
            self.assertEqual(removed, 3)
            remaining = sorted(p.name for p in root.iterdir())
            self.assertEqual(remaining, ["setup-3.exe", "setup-4.exe"])

    def test_keep_downloads_disables_pruning(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self.make_service("http://127.0.0.1:1", root, keep_downloads=True)
            for index in range(4):
                (root / f"setup-{index}.exe").write_bytes(b"x")
            self.assertEqual(service.prune_downloads(keep=1), 0)


class EventFlowTests(ServiceTestCase):
    def test_events_are_emitted_on_a_background_thread(self) -> None:
        events: list = []
        lock = threading.Lock()

        def collect(event) -> None:
            with lock:
                events.append(event)

        with _Server() as base, TemporaryDirectory() as tmp:
            service = self.make_service(base, Path(tmp), mode="notify")
            service.on_event = collect
            service.check_async()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with lock:
                    if any(e.kind == "available" for e in events):
                        break
                time.sleep(0.05)

        kinds = [event.kind for event in events]
        self.assertIn("checking", kinds)
        self.assertIn("available", kinds)

    def test_check_async_is_a_no_op_while_busy(self) -> None:
        with TemporaryDirectory() as tmp:
            service = self.make_service("http://127.0.0.1:1", Path(tmp))
            service._busy.acquire()  # type: ignore[attr-defined]
            try:
                service.check_async()
                self.assertIsNone(service._thread)  # type: ignore[attr-defined]
            finally:
                service._busy.release()  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
