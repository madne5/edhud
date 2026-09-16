"""Tests for the GitHub Releases updater.

These never touch the real network: a local :mod:`http.server` serves canned
GitHub API responses and release assets, so the HTTP client, checksum
verification and download path are all exercised for real.
"""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from elite_hud.updater import (
    Asset,
    GitHubClient,
    GitHubError,
    Release,
    UpdateChecker,
    UpdateDownloader,
    Version,
    apply_installer,
    apply_portable,
    format_size,
    is_newer,
    parse_checksums,
    parse_release,
    sha256_file,
    stage_portable,
)


# ---------------------------------------------------------------------------
# version handling
# ---------------------------------------------------------------------------


class VersionTests(unittest.TestCase):
    def test_parses_common_shapes(self) -> None:
        self.assertEqual(Version.parse("1.2.3").parts, (1, 2, 3))  # type: ignore[union-attr]
        self.assertEqual(Version.parse("v1.2.3").parts, (1, 2, 3))  # type: ignore[union-attr]
        self.assertEqual(Version.parse("0.2").parts, (0, 2))  # type: ignore[union-attr]
        self.assertIsNone(Version.parse("not-a-version"))
        self.assertIsNone(Version.parse(""))

    def test_missing_components_are_equal(self) -> None:
        self.assertEqual(Version.parse("1.2"), Version.parse("1.2.0"))

    def test_release_outranks_its_own_prerelease(self) -> None:
        self.assertGreater(Version.parse("1.0.0"), Version.parse("1.0.0-rc1"))  # type: ignore[arg-type]
        self.assertGreater(Version.parse("1.0.0-rc2"), Version.parse("1.0.0-rc1"))  # type: ignore[arg-type]

    def test_ordering(self) -> None:
        ordered = ["0.9.9", "0.10.0", "1.0.0-beta1", "1.0.0", "1.0.1", "2.0.0"]
        parsed = [Version.parse(v) for v in ordered]
        self.assertEqual(parsed, sorted(parsed))  # type: ignore[type-var]

    def test_is_newer(self) -> None:
        self.assertTrue(is_newer("0.3.0", "0.2.0"))
        self.assertTrue(is_newer("v1.0.0", "0.9.9"))
        self.assertFalse(is_newer("0.2.0", "0.2.0"))
        self.assertFalse(is_newer("0.1.9", "0.2.0"))
        self.assertFalse(is_newer("garbage", "0.2.0"))


# ---------------------------------------------------------------------------
# GitHub payload parsing
# ---------------------------------------------------------------------------

RELEASE_JSON = {
    "tag_name": "v0.3.0",
    "name": "elite-hud 0.3.0",
    "body": "## Что нового\n- предсказание видов",
    "html_url": "https://github.com/madne5/edhud/releases/tag/v0.3.0",
    "published_at": "2026-04-01T10:00:00Z",
    "prerelease": False,
    "draft": False,
    "assets": [
        {
            "name": "elite-hud-setup-0.3.0.exe",
            "url": "https://api.github.invalid/assets/1",
            "browser_download_url": "https://example.invalid/setup.exe",
            "size": 42_000_000,
            "content_type": "application/octet-stream",
            "digest": "sha256:" + "a" * 64,
        },
        {
            "name": "elite-hud-0.3.0-win64.zip",
            "url": "https://api.github.invalid/assets/2",
            "browser_download_url": "https://example.invalid/portable.zip",
            "size": 38_000_000,
            "content_type": "application/zip",
            # GitHub leaves digest null for every release published before
            # June 2025, so the updater must cope with it.
            "digest": None,
        },
        {
            "name": "SHA256SUMS.txt",
            "url": "https://api.github.invalid/assets/3",
            "browser_download_url": "https://example.invalid/SHA256SUMS.txt",
            "size": 250,
        },
    ],
}


class ParseReleaseTests(unittest.TestCase):
    def test_parses_a_realistic_release(self) -> None:
        release = parse_release(RELEASE_JSON)
        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.tag, "v0.3.0")
        self.assertEqual(release.version, Version((0, 3, 0)))
        self.assertEqual(len(release.assets), 3)
        self.assertFalse(release.prerelease)
        self.assertEqual(release.published_at.year, 2026)

    def test_selects_the_right_assets(self) -> None:
        release = parse_release(RELEASE_JSON)
        assert release is not None
        self.assertEqual(release.installer_asset().name, "elite-hud-setup-0.3.0.exe")  # type: ignore[union-attr]
        self.assertEqual(release.portable_asset().name, "elite-hud-0.3.0-win64.zip")  # type: ignore[union-attr]
        self.assertEqual(release.checksum_asset.name, "SHA256SUMS.txt")  # type: ignore[union-attr]

    def test_api_digest_is_exposed_as_sha256(self) -> None:
        release = parse_release(RELEASE_JSON)
        assert release is not None
        self.assertEqual(release.installer_asset().sha256, "a" * 64)  # type: ignore[union-attr]
        self.assertEqual(release.portable_asset().sha256, "")  # type: ignore[union-attr]

    def test_rejects_payloads_without_a_tag(self) -> None:
        self.assertIsNone(parse_release({"name": "no tag"}))
        self.assertIsNone(parse_release("not a dict"))

    def test_notes_survive(self) -> None:
        release = parse_release(RELEASE_JSON)
        assert release is not None
        self.assertIn("предсказание видов", release.notes)

    def test_both_download_urls_are_kept(self) -> None:
        release = parse_release(RELEASE_JSON)
        assert release is not None
        setup = release.installer_asset()
        assert setup is not None
        self.assertEqual(setup.url, "https://api.github.invalid/assets/1")
        self.assertEqual(setup.browser_url, "https://example.invalid/setup.exe")

    def test_download_url_prefers_the_api_only_when_authenticated(self) -> None:
        """browser_download_url does not work anonymously for private repos."""
        release = parse_release(RELEASE_JSON)
        assert release is not None
        setup = release.installer_asset()
        assert setup is not None
        self.assertEqual(setup.download_url(authenticated=False), setup.browser_url)
        self.assertEqual(setup.download_url(authenticated=True), setup.url)

    def test_asset_without_a_browser_url_still_downloads(self) -> None:
        release = parse_release(
            {"tag_name": "v1.0.0", "assets": [{"name": "a.exe", "url": "https://api.invalid/a"}]}
        )
        assert release is not None
        asset = release.assets[0]
        self.assertEqual(asset.download_url(authenticated=False), "https://api.invalid/a")

    def test_asset_lookup_is_case_insensitive(self) -> None:
        release = parse_release(RELEASE_JSON)
        assert release is not None
        self.assertIsNotNone(release.asset("sha256sums.txt"))


class ChecksumTests(unittest.TestCase):
    def test_parses_sha256sum_output(self) -> None:
        text = (
            "d0e1f2" + "0" * 58 + "  elite-hud-setup-0.3.0.exe\n"
            "# a comment\n"
            "\n"
            + "b" * 64 + " *elite-hud-0.3.0-win64.zip\n"
        )
        sums = parse_checksums(text)
        self.assertEqual(len(sums), 2)
        self.assertIn("elite-hud-setup-0.3.0.exe", sums)
        self.assertIn("elite-hud-0.3.0-win64.zip", sums)

    def test_ignores_malformed_lines(self) -> None:
        self.assertEqual(parse_checksums("nonsense\nabc file\n"), {})

    def test_sha256_file_matches_hashlib(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "blob.bin"
            payload = b"elite-hud" * 1000
            path.write_bytes(payload)
            self.assertEqual(sha256_file(path), hashlib.sha256(payload).hexdigest())


# ---------------------------------------------------------------------------
# release selection
# ---------------------------------------------------------------------------


def release(tag: str, *, prerelease: bool = False, assets: tuple[Asset, ...] = ()) -> Release:
    return Release(
        tag=tag,
        version=Version.parse(tag),
        name=tag,
        notes="",
        html_url="",
        published_at=None,
        prerelease=prerelease,
        assets=assets,
    )


SETUP = Asset("elite-hud-setup-0.3.0.exe", "https://example.invalid/s.exe", 100)
PORTABLE = Asset("elite-hud-0.3.0-win64.zip", "https://example.invalid/p.zip", 90)


class SelectReleaseTests(unittest.TestCase):
    def _checker(self, current: str = "0.2.0", **kwargs) -> UpdateChecker:
        return UpdateChecker("madne5/edhud", current, **kwargs)

    def test_picks_the_highest_newer_release(self) -> None:
        releases = [
            release("v0.1.0", assets=(SETUP,)),
            release("v0.3.0", assets=(SETUP,)),
            release("v0.2.1", assets=(SETUP,)),
        ]
        chosen = self._checker().select_release(releases)
        self.assertEqual(chosen.tag, "v0.3.0")  # type: ignore[union-attr]

    def test_ignores_older_and_equal_releases(self) -> None:
        releases = [release("v0.1.0"), release("v0.2.0")]
        self.assertIsNone(self._checker().select_release(releases))

    def test_prereleases_are_skipped_by_default(self) -> None:
        releases = [release("v0.3.0", prerelease=True, assets=(SETUP,))]
        self.assertIsNone(self._checker().select_release(releases))
        chosen = self._checker(allow_prerelease=True).select_release(releases)
        self.assertEqual(chosen.tag, "v0.3.0")  # type: ignore[union-attr]

    def test_stable_beats_prerelease_when_both_are_allowed(self) -> None:
        # Same version number published twice: the stable one must win.
        releases = [
            release("v0.3.0", prerelease=True, assets=(SETUP,)),
            release("v0.3.0", assets=(SETUP,)),
        ]
        chosen = self._checker(allow_prerelease=True).select_release(releases)
        self.assertFalse(chosen.prerelease)  # type: ignore[union-attr]

    def test_unparseable_tags_are_ignored(self) -> None:
        # Real-world examples: neovim publishes a "stable" tag, and Inno Setup
        # uses "is-7_1_0". Neither is a version we may compare.
        for tag in ("nightly", "stable", "is-7_1_0", "latest"):
            with self.subTest(tag=tag):
                self.assertIsNone(self._checker().select_release([release(tag)]))


class PickAssetTests(unittest.TestCase):
    def test_installer_preference(self) -> None:
        r = release("v0.3.0", assets=(SETUP, PORTABLE))
        self.assertEqual(self._pick(r, "installer"), SETUP)

    def test_portable_preference(self) -> None:
        r = release("v0.3.0", assets=(SETUP, PORTABLE))
        self.assertEqual(self._pick(r, "portable"), PORTABLE)

    def test_falls_back_when_the_preferred_kind_is_missing(self) -> None:
        only_zip = release("v0.3.0", assets=(PORTABLE,))
        self.assertEqual(self._pick(only_zip, "installer"), PORTABLE)

    def test_returns_none_when_there_is_nothing_usable(self) -> None:
        self.assertIsNone(self._pick(release("v0.3.0"), "any"))

    @staticmethod
    def _pick(release_obj: Release, preference: str) -> Asset | None:
        checker = UpdateChecker("a/b", "0.1.0", prefer=preference)
        return checker.pick_asset(release_obj)


# ---------------------------------------------------------------------------
# live HTTP against a local server
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, bytes] = {}
    status: dict[str, int] = {}

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        code = self.status.get(self.path, 200)
        body = self.routes.get(self.path, b"")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if code == 403:
            self.send_header("x-ratelimit-remaining", "0")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep the test output quiet
        return


class LocalServerTestCase(unittest.TestCase):
    routes: dict[str, bytes] = {}
    status: dict[str, int] = {}

    @classmethod
    def setUpClass(cls) -> None:
        handler = type("Handler", (_Handler,), {"routes": cls.routes, "status": cls.status})
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def client(self, **kwargs) -> GitHubClient:
        return GitHubClient("madne5/edhud", api_base=self.base, timeout=10, **kwargs)


class ClientTests(LocalServerTestCase):
    routes = {
        "/repos/madne5/edhud/releases?per_page=30": json.dumps([RELEASE_JSON]).encode(),
        "/repos/madne5/edhud/releases?per_page=5": json.dumps([RELEASE_JSON]).encode(),
        "/missing/repos/madne5/edhud/releases?per_page=30": b"",
    }
    status = {"/missing/repos/madne5/edhud/releases?per_page=30": 404}

    def test_fetches_and_parses_the_release_list(self) -> None:
        releases = self.client().releases()
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "v0.3.0")

    def test_missing_repo_reports_clearly(self) -> None:
        broken = GitHubClient("madne5/edhud", api_base=self.base + "/missing", timeout=10)
        with self.assertRaises(GitHubError) as ctx:
            broken.releases()
        self.assertIn("не найден", str(ctx.exception))

    def test_non_json_response_is_reported_clearly(self) -> None:
        """A captive portal or proxy must not surface as a JSON traceback."""
        handler = type(
            "H",
            (_Handler,),
            {"routes": {"/proxy/repos/a/b/releases?per_page=30": b"<html>hello</html>"}, "status": {}},
        )
        original = self.server.RequestHandlerClass
        self.server.RequestHandlerClass = handler  # type: ignore[assignment]
        try:
            client = GitHubClient("a/b", api_base=self.base + "/proxy", timeout=10)
            with self.assertRaises(GitHubError) as ctx:
                client.releases()
            self.assertIn("не JSON", str(ctx.exception))
        finally:
            self.server.RequestHandlerClass = original  # type: ignore[assignment]

    def test_full_check_reports_an_update(self) -> None:
        checker = UpdateChecker("madne5/edhud", "0.2.0", client=self.client())
        result = checker.check()
        self.assertEqual(result.status, "update")
        self.assertEqual(result.update.version, "0.3.0")  # type: ignore[union-attr]

    def test_check_reports_up_to_date(self) -> None:
        checker = UpdateChecker("madne5/edhud", "0.3.0", client=self.client())
        self.assertEqual(checker.check().status, "current")

    def test_downloads_an_asset(self) -> None:
        payload = b"PK\x03\x04 fake installer"
        handler = type("H", (_Handler,), {"routes": {"/asset": payload}, "status": {}})
        self.server.RequestHandlerClass = handler  # type: ignore[assignment]
        try:
            with TemporaryDirectory() as tmp:
                target = Path(tmp) / "setup.exe"
                seen: list[tuple[int, int]] = []
                self.client().download(
                    Asset("asset", self.base + "/asset", 0),
                    target,
                    progress=lambda a, b: seen.append((a, b)),
                )
                self.assertEqual(target.read_bytes(), payload)
                self.assertTrue(seen, "progress callback was never called")
        finally:
            self.server.RequestHandlerClass = type(  # type: ignore[assignment]
                "Handler", (_Handler,), {"routes": self.routes, "status": self.status}
            )


class RateLimitTests(LocalServerTestCase):
    routes = {"/repos/madne5/edhud/releases?per_page=30": b"{}"}
    status = {"/repos/madne5/edhud/releases?per_page=30": 403}

    def test_rate_limit_is_explained(self) -> None:
        checker = UpdateChecker("madne5/edhud", "0.2.0", client=self.client())
        result = checker.check()
        self.assertEqual(result.status, "error")
        self.assertIn("лимит", result.message)


class DownloaderTests(LocalServerTestCase):
    routes = {
        "/repos/madne5/edhud/releases?per_page=30": json.dumps([RELEASE_JSON]).encode(),
    }
    status: dict[str, int] = {}

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.payload = b"elite-hud installer payload"
        cls.digest = hashlib.sha256(cls.payload).hexdigest()
        cls.routes["/setup"] = cls.payload
        cls.routes["/SHA256SUMS.txt"] = (
            f"{cls.digest}  elite-hud-setup-0.3.0.exe\n"
            f"{'f' * 64}  elite-hud-0.3.0-win64.zip\n"
        ).encode()

    def _update(self, *, digest_in_api: bool, sums_url: str = "/SHA256SUMS.txt"):
        from elite_hud.updater import UpdateInfo

        asset = Asset(
            "elite-hud-setup-0.3.0.exe",
            self.base + "/setup",
            100,
            f"sha256:{self.digest}" if digest_in_api else "",
        )
        checksum = Asset("SHA256SUMS.txt", self.base + sums_url, 100) if sums_url else None
        return UpdateInfo(release=release("v0.3.0"), asset=asset, checksum_asset=checksum)

    def test_verifies_using_the_api_digest(self) -> None:
        with TemporaryDirectory() as tmp:
            downloader = UpdateDownloader(self.client(), Path(tmp))
            path = downloader.fetch(self._update(digest_in_api=True, sums_url=""))
            self.assertEqual(path.read_bytes(), self.payload)

    def test_verifies_using_the_checksum_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            downloader = UpdateDownloader(self.client(), Path(tmp))
            path = downloader.fetch(self._update(digest_in_api=False))
            self.assertTrue(path.is_file())

    def test_rejects_a_mismatched_checksum(self) -> None:
        self.routes["/bad-sums.txt"] = b"0" * 64 + b"  elite-hud-setup-0.3.0.exe\n"
        with TemporaryDirectory() as tmp:
            downloader = UpdateDownloader(self.client(), Path(tmp))
            with self.assertRaises(GitHubError) as ctx:
                downloader.fetch(self._update(digest_in_api=False, sums_url="/bad-sums.txt"))
            self.assertIn("контрольная сумма", str(ctx.exception))
            # A rejected download must not be left behind as a usable package.
            self.assertEqual(list(Path(tmp).iterdir()), [])


# ---------------------------------------------------------------------------
# portable staging and platform guards
# ---------------------------------------------------------------------------


class StagePortableTests(unittest.TestCase):
    def _zip(self, tmp: Path, *, wrap: bool, evil: bool = False) -> Path:
        archive = tmp / "update.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            prefix = "elite-hud/" if wrap else ""
            bundle.writestr(prefix + "elite-hud.exe", b"MZ fake")
            bundle.writestr(prefix + "README.md", b"hello")
            if evil:
                bundle.writestr("../../escaped.txt", b"nope")
        return archive

    def test_unwraps_a_single_top_level_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            result = stage_portable(self._zip(root, wrap=True), staging)
            self.assertEqual(result.name, "elite-hud")
            self.assertTrue((result / "elite-hud.exe").is_file())

    def test_handles_a_flat_archive(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            result = stage_portable(self._zip(root, wrap=False), staging)
            self.assertTrue((result / "elite-hud.exe").is_file())

    def test_refuses_zip_slip(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(GitHubError):
                stage_portable(self._zip(root, wrap=False, evil=True), root / "staging")


class PlatformGuardTests(unittest.TestCase):
    def test_applying_requires_windows(self) -> None:
        import sys

        if sys.platform == "win32":  # pragma: no cover - Windows only
            self.skipTest("the platform guards do not apply on Windows")
        with self.assertRaises(GitHubError):
            apply_installer(Path("/tmp/setup.exe"))
        with self.assertRaises(GitHubError):
            apply_portable(Path("/tmp/staged"))


class SetupFlagTests(unittest.TestCase):
    def test_flags_are_fully_silent(self) -> None:
        """/SILENT still shows a progress window, which would steal focus."""
        from elite_hud.updater import SILENT_SETUP_FLAGS

        self.assertIn("/VERYSILENT", SILENT_SETUP_FLAGS)
        self.assertNotIn("/SILENT", SILENT_SETUP_FLAGS)

    def test_flags_let_us_own_the_restart(self) -> None:
        from elite_hud.updater import SILENT_SETUP_FLAGS

        # Inno restarts things itself only via RegisterApplicationRestart, which
        # a Qt app never calls; our installer's [Run] entry does the relaunch.
        self.assertIn("/NORESTARTAPPLICATIONS", SILENT_SETUP_FLAGS)
        self.assertIn("/SUPPRESSMSGBOXES", SILENT_SETUP_FLAGS)
        self.assertIn("/CLOSEAPPLICATIONS", SILENT_SETUP_FLAGS)


class InstallationTests(unittest.TestCase):
    def test_detect_install_never_raises(self) -> None:
        from elite_hud.installation import detect_install

        info = detect_install()
        self.assertIn(info.mode, ("installed", "portable"))
        self.assertIn(info.update_preference, ("installer", "portable"))

    def test_portable_prefers_a_zip(self) -> None:
        from elite_hud.installation import PORTABLE, InstallInfo

        self.assertEqual(InstallInfo(PORTABLE).update_preference, "portable")

    def test_installed_prefers_a_setup_exe(self) -> None:
        from elite_hud.installation import INSTALLED, InstallInfo

        self.assertEqual(InstallInfo(INSTALLED).update_preference, "installer")

    def test_elevation_is_not_requested_off_windows(self) -> None:
        import sys

        from elite_hud.installation import needs_elevation

        if sys.platform != "win32":
            self.assertFalse(needs_elevation(Path("/tmp")))

    def test_single_instance_guard_round_trip(self) -> None:
        from elite_hud.installation import SingleInstanceGuard

        first = SingleInstanceGuard(name="elite-hud-test-guard")
        second = SingleInstanceGuard(name="elite-hud-test-guard")
        self.assertTrue(first.acquire())
        try:
            self.assertFalse(second.acquire(), "a second instance was allowed")
        finally:
            first.release()
        # Released, so a fresh guard can take it again.
        third = SingleInstanceGuard(name="elite-hud-test-guard")
        self.assertTrue(third.acquire())
        third.release()


class FormatSizeTests(unittest.TestCase):
    def test_human_readable(self) -> None:
        self.assertEqual(format_size(512), "512 Б")
        self.assertEqual(format_size(2048), "2 КБ")
        self.assertEqual(format_size(42 * 1024 * 1024), "42.0 МБ")


if __name__ == "__main__":
    unittest.main()
