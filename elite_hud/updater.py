"""Self-update through GitHub Releases.

The flow is deliberately boring and auditable:

1. ask the GitHub API for the release list of ``update.repo``;
2. pick the highest version that is newer than ours;
3. choose the asset that matches how this copy was installed (setup ``.exe``
   for an Inno Setup install, ``.zip`` for a portable copy);
4. download it next to the download cache and verify its SHA-256 against the
   ``SHA256SUMS.txt`` asset when the release provides one;
5. hand it to the platform: run the setup silently, or swap the portable files
   through a helper script once this process has exited.

Nothing here imports Qt, so the whole thing is unit-testable headlessly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
USER_AGENT = "elite-hud-updater"

#: Names a release may use for its checksum manifest.
CHECKSUM_ASSET_NAMES = ("sha256sums.txt", "sha256sums", "checksums.txt", "checksums.sha256")

#: Where the updater keeps downloads between runs.
DOWNLOAD_DIRNAME = "updates"


def ssl_context() -> ssl.SSLContext:
    """A TLS context that works both frozen and on a bare interpreter.

    Windows and macOS system Python builds sometimes ship without a usable
    trust store; ``certifi`` (a tiny, ubiquitous dependency) fixes that, and is
    the same bundle PyInstaller ships inside the frozen executable.
    """
    try:
        import certifi  # noqa: PLC0415 - optional dependency by design

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ---------------------------------------------------------------------------
# versions
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(
    r"^v?(?P<nums>\d+(?:\.\d+)*)(?:[-_.]?(?P<pre>alpha|beta|rc|pre|dev)[-_.]?(?P<prenum>\d*))?",
    re.IGNORECASE,
)


@dataclass(frozen=True, eq=False)
class Version:
    """A comparable ``major.minor.patch`` version with an optional pre-release.

    Equality is derived from the same key used for ordering, so ``1.2`` and
    ``1.2.0`` compare equal as one would expect.
    """

    parts: tuple[int, ...]
    prerelease: str = ""

    @classmethod
    def parse(cls, text: str) -> "Version | None":
        if not text:
            return None
        match = _VERSION_RE.match(text.strip())
        if match is None:
            return None
        numbers = tuple(int(part) for part in match.group("nums").split("."))
        pre = ""
        if match.group("pre"):
            pre = f"{match.group('pre').lower()}{int(match.group('prenum') or 0):03d}"
        return cls(numbers, pre)

    @property
    def text(self) -> str:
        base = ".".join(str(part) for part in self.parts)
        return f"{base}-{self.prerelease}" if self.prerelease else base

    def _key(self) -> tuple[tuple[int, ...], int, str]:
        # Pad so 1.2 and 1.2.0 compare equal, and a pre-release sorts below the
        # final release of the same number.
        padded = self.parts + (0,) * max(0, 4 - len(self.parts))
        return (padded, 0 if self.prerelease else 1, self.prerelease)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __lt__(self, other: "Version") -> bool:
        return self._key() < other._key()

    def __le__(self, other: "Version") -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: "Version") -> bool:
        return self._key() > other._key()

    def __ge__(self, other: "Version") -> bool:
        return self._key() >= other._key()

    def __str__(self) -> str:
        return self.text


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a strictly newer version than ``current``."""
    left = Version.parse(candidate)
    right = Version.parse(current)
    if left is None or right is None:
        log.debug("cannot compare versions %r and %r", candidate, current)
        return False
    return left > right


# ---------------------------------------------------------------------------
# release model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Asset:
    """A release asset, with both of GitHub's download URLs.

    ``url`` is the REST asset endpoint. It needs ``Accept:
    application/octet-stream`` and, for a private repository, an
    ``Authorization`` header -- ``browser_url`` does not work anonymously there.
    ``browser_url`` is the direct CDN link, which is nicer for public releases
    because it needs no headers and no redirect.
    """

    name: str
    url: str
    size: int = 0
    digest: str = ""
    browser_url: str = ""

    @property
    def sha256(self) -> str:
        """SHA-256 from the API ``digest`` field, when GitHub supplies it.

        GitHub only started populating ``digest`` in June 2025, and the field is
        nullable, so every release published before that reports ``null``.
        """
        prefix = "sha256:"
        if self.digest.startswith(prefix):
            return self.digest[len(prefix) :].strip().lower()
        return ""

    def download_url(self, *, authenticated: bool) -> str:
        """The best URL for this client: the API one when a token is set."""
        if authenticated and self.url:
            return self.url
        return self.browser_url or self.url


@dataclass(frozen=True)
class Release:
    tag: str
    version: Version | None
    name: str
    notes: str
    html_url: str
    published_at: datetime | None
    prerelease: bool
    assets: tuple[Asset, ...] = ()

    def asset(self, name: str) -> Asset | None:
        lowered = name.lower()
        return next((a for a in self.assets if a.name.lower() == lowered), None)

    @property
    def checksum_asset(self) -> Asset | None:
        for candidate in self.assets:
            if candidate.name.lower() in CHECKSUM_ASSET_NAMES:
                return candidate
        return None

    def installer_asset(self) -> Asset | None:
        candidates = [
            a
            for a in self.assets
            if a.name.lower().endswith(".exe") and "setup" in a.name.lower()
        ]
        return candidates[0] if candidates else None

    def portable_asset(self) -> Asset | None:
        candidates = [a for a in self.assets if a.name.lower().endswith(".zip")]
        return candidates[0] if candidates else None


@dataclass
class UpdateInfo:
    """A release that is newer than the running build, plus the asset to fetch."""

    release: Release
    asset: Asset
    checksum_asset: Asset | None = None

    @property
    def version(self) -> str:
        return self.release.version.text if self.release.version else self.release.tag

    @property
    def notes(self) -> str:
        return self.release.notes


@dataclass
class CheckResult:
    """Outcome of an update check, shaped for direct display."""

    status: str  #: "update" | "current" | "error" | "disabled"
    message: str
    update: UpdateInfo | None = None

    @property
    def has_update(self) -> bool:
        return self.update is not None


# ---------------------------------------------------------------------------
# GitHub client
# ---------------------------------------------------------------------------


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    """Minimal read-only GitHub Releases client built on ``urllib``."""

    def __init__(
        self,
        repo: str,
        *,
        token: str = "",
        timeout: float = 15.0,
        api_base: str = GITHUB_API,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.repo = repo.strip().strip("/")
        self.token = token.strip()
        self.timeout = timeout
        self.api_base = api_base.rstrip("/")
        self.user_agent = user_agent

    def _headers(self, *, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            # GitHub rejects requests without a User-Agent.
            "User-Agent": self.user_agent,
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str, *, accept: str = "application/vnd.github+json") -> bytes:
        request = urllib.request.Request(url, headers=self._headers(accept=accept))
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=ssl_context()
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise GitHubError(
                    f"репозиторий {self.repo} не найден или релизов ещё нет"
                ) from exc
            if exc.code in (401, 403):
                remaining = exc.headers.get("x-ratelimit-remaining") if exc.headers else None
                if remaining == "0":
                    raise GitHubError(
                        "исчерпан лимит запросов к GitHub API, попробуйте позже"
                    ) from exc
                raise GitHubError(
                    f"GitHub отклонил запрос ({exc.code}); проверьте токен доступа"
                ) from exc
            raise GitHubError(f"GitHub ответил ошибкой {exc.code}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLError):
                raise GitHubError(
                    "не удалось проверить сертификат GitHub (проверьте системное время и сертификаты)"
                ) from exc
            raise GitHubError(f"нет связи с GitHub: {exc.reason}") from exc
        except TimeoutError as exc:
            raise GitHubError("GitHub не ответил вовремя") from exc

    def releases(self, *, per_page: int = 30) -> list[Release]:
        url = f"{self.api_base}/repos/{self.repo}/releases?per_page={int(per_page)}"
        body = self._get(url).decode("utf-8", "replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GitHubError(
                "GitHub вернул не JSON — возможно, запрос перехвачен прокси или сетью"
            ) from exc
        if not isinstance(payload, list):
            raise GitHubError("неожиданный ответ GitHub API")
        return [release for release in (parse_release(item) for item in payload) if release]

    def asset_bytes(self, asset: Asset) -> bytes:
        """Fetch an asset into memory (used for small files like checksums)."""
        url = asset.download_url(authenticated=bool(self.token))
        self._check_scheme(url)
        request = urllib.request.Request(
            url, headers=self._headers(accept="application/octet-stream")
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=ssl_context()
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise GitHubError(f"не удалось скачать {asset.name} (HTTP {exc.code})") from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"нет связи с GitHub: {exc.reason}") from exc

    @staticmethod
    def _check_scheme(url: str) -> None:
        # urllib raises a bare ValueError for a relative URL, which would
        # surface as an unexplained failure; say what is actually wrong.
        if not url.lower().startswith(("http://", "https://")):
            raise GitHubError(f"GitHub вернул некорректный адрес файла: {url!r}")

    def download(self, asset: Asset, destination: Path, *, progress=None) -> Path:
        """Stream a release asset to ``destination``, reporting progress."""
        url = asset.download_url(authenticated=bool(self.token))
        self._check_scheme(url)
        request = urllib.request.Request(url, headers=self._headers(accept="application/octet-stream"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=ssl_context()
            ) as response:
                total = int(response.headers.get("Content-Length") or 0)
                received = 0
                with open(temporary, "wb") as handle:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        received += len(chunk)
                        if progress is not None:
                            progress(received, total)
        except urllib.error.HTTPError as exc:
            temporary.unlink(missing_ok=True)
            raise GitHubError(f"не удалось скачать обновление (HTTP {exc.code})") from exc
        except urllib.error.URLError as exc:
            temporary.unlink(missing_ok=True)
            raise GitHubError(f"нет связи с GitHub: {exc.reason}") from exc

        temporary.replace(destination)
        return destination


def parse_release(payload: object) -> Release | None:
    if not isinstance(payload, dict):
        return None
    tag = str(payload.get("tag_name") or "")
    if not tag:
        return None

    assets: list[Asset] = []
    for raw in payload.get("assets") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "")
        api_url = str(raw.get("url") or "")
        browser_url = str(raw.get("browser_download_url") or "")
        if not name or not (api_url or browser_url):
            continue
        assets.append(
            Asset(
                name=name,
                url=api_url or browser_url,
                size=int(raw.get("size") or 0),
                digest=str(raw.get("digest") or ""),
                browser_url=browser_url,
            )
        )

    return Release(
        tag=tag,
        version=Version.parse(tag),
        name=str(payload.get("name") or tag),
        notes=str(payload.get("body") or ""),
        html_url=str(payload.get("html_url") or ""),
        published_at=parse_datetime(payload.get("published_at")),
        prerelease=bool(payload.get("prerelease")),
        assets=tuple(assets),
    )


def parse_datetime(value: object) -> datetime | None:
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


def parse_checksums(text: str) -> dict[str, str]:
    """Parse a ``sha256sum``-style manifest into ``{filename: hexdigest}``."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0].strip().lower(), parts[1].strip()
        if name.startswith("*"):
            name = name[1:]
        name = os.path.basename(name)
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            sums[name.lower()] = digest
    return sums


def sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# high level services
# ---------------------------------------------------------------------------


class UpdateChecker:
    """Turns ``repo`` + the running version into a :class:`CheckResult`."""

    def __init__(
        self,
        repo: str,
        current_version: str,
        *,
        token: str = "",
        allow_prerelease: bool = False,
        prefer: str = "any",
        client: GitHubClient | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.current_version = current_version
        self.allow_prerelease = allow_prerelease
        self.prefer = prefer
        self.client = client or GitHubClient(repo, token=token, timeout=timeout)

    def check(self) -> CheckResult:
        if not self.client.repo or "/" not in self.client.repo:
            return CheckResult(
                "disabled", "не задан репозиторий обновлений (update.repo)"
            )
        try:
            releases = self.client.releases()
        except GitHubError as exc:
            log.info("update check failed: %s", exc)
            return CheckResult("error", str(exc))

        candidate = self.select_release(releases)
        if candidate is None:
            return CheckResult("current", "обновлений нет")

        update = self.build_update(candidate)
        if update is None:
            return CheckResult(
                "error",
                f"в релизе {candidate.tag} нет подходящего файла для этого способа установки",
            )
        return CheckResult(
            "update",
            f"доступна версия {update.version}",
            update,
        )

    def select_release(self, releases: list[Release]) -> Release | None:
        """Highest non-draft release newer than the running version."""
        usable = [
            release
            for release in releases
            if release.version is not None
            and (self.allow_prerelease or not release.prerelease)
        ]
        current = Version.parse(self.current_version)
        newer = [
            release
            for release in usable
            if current is None or release.version > current  # type: ignore[operator]
        ]
        if not newer:
            return None
        # Ties between an equally-numbered stable and pre-release favour stable.
        return max(
            newer,
            key=lambda release: (release.version, not release.prerelease),  # type: ignore[arg-type,return-value]
        )

    def build_update(self, release: Release) -> UpdateInfo | None:
        asset = self.pick_asset(release)
        if asset is None:
            return None
        return UpdateInfo(release=release, asset=asset, checksum_asset=release.checksum_asset)

    def pick_asset(self, release: Release) -> Asset | None:
        prefer_installer = self.prefer in ("any", "installer")
        prefer_portable = self.prefer in ("any", "portable")

        if prefer_installer:
            installer = release.installer_asset()
            if installer is not None:
                return installer
        if prefer_portable:
            portable = release.portable_asset()
            if portable is not None:
                return portable
        # Fall back to whatever is there rather than reporting "no file".
        if prefer_installer:
            portable = release.portable_asset()
            if portable is not None:
                return portable
        else:
            installer = release.installer_asset()
            if installer is not None:
                return installer
        return None


class UpdateDownloader:
    """Downloads an :class:`UpdateInfo` into a cache directory and verifies it."""

    def __init__(self, client: GitHubClient, directory: Path) -> None:
        self.client = client
        self.directory = directory

    def fetch(self, update: UpdateInfo, *, progress=None) -> Path:
        target = self.directory / update.asset.name
        log.info(
            "downloading %s from %s",
            update.asset.name,
            update.asset.download_url(authenticated=bool(self.client.token)),
        )
        self.client.download(update.asset, target, progress=progress)

        expected = self.expected_digest(update)
        if expected:
            actual = sha256_file(target)
            if actual != expected:
                target.unlink(missing_ok=True)
                raise GitHubError(
                    "контрольная сумма скачанного файла не совпала — загрузка отменена"
                )
            log.info("sha256 verified for %s", update.asset.name)
        else:
            log.warning(
                "release %s has no SHA-256 for %s; installing unverified",
                update.release.tag,
                update.asset.name,
            )
        return target

    def expected_digest(self, update: UpdateInfo) -> str:
        """Checksum from the API digest field, else from the manifest asset."""
        if update.asset.sha256:
            return update.asset.sha256
        if update.checksum_asset is None:
            return ""
        try:
            payload = self.client.asset_bytes(update.checksum_asset)
        except GitHubError as exc:
            log.warning("cannot fetch checksum manifest: %s", exc)
            return ""
        sums = parse_checksums(payload.decode("utf-8", "replace"))
        expected = sums.get(update.asset.name.lower(), "")
        if not expected:
            log.warning("checksum manifest does not mention %s", update.asset.name)
        return expected


# ---------------------------------------------------------------------------
# applying the update
# ---------------------------------------------------------------------------

#: /VERYSILENT rather than /SILENT: the latter still shows a progress window,
#: which would steal focus from a fullscreen game. /NORESTARTAPPLICATIONS keeps
#: Setup from reviving us itself -- our own [Run] entry relaunches the HUD as
#: the original user, which is what we want.
SILENT_SETUP_FLAGS = [
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
    "/NORESTARTAPPLICATIONS",
]

#: Written by the helper script so a crash mid-update is recoverable.
UPDATE_MARKER = ".update-in-progress"


def apply_installer(path: Path, *, elevate: bool = True) -> None:
    """Run a downloaded Inno Setup package, silently replacing this install."""
    if sys.platform != "win32":
        raise GitHubError("установка обновления поддерживается только в Windows")

    arguments = " ".join(SILENT_SETUP_FLAGS)
    if elevate:
        # Program Files needs administrator rights; ask for them explicitly so
        # the user sees a normal UAC prompt rather than a silent failure.
        import ctypes

        result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "runas", str(path), arguments, None, 1
        )
        if result <= 32:
            raise GitHubError("не удалось запустить установщик (отклонён запрос прав?)")
        return

    subprocess.Popen([str(path), *SILENT_SETUP_FLAGS], close_fds=True)


PORTABLE_HELPER_TEMPLATE = """@echo off
setlocal
set "TARGET={target}"
set "SOURCE={source}"
set "LAUNCH={launch}"
set "PID={pid}"

rem Wait for the running HUD to exit: a locked exe cannot be replaced.
set /a TRIES=0
:wait
set /a TRIES+=1
if %TRIES% GTR 120 goto giveup
tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >NUL
    goto wait
)

robocopy "%SOURCE%" "%TARGET%" /E /IS /IT /NFL /NDL /NJH /NJS /NP >NUL
del /F /Q "{marker}" >NUL 2>&1
start "" "%LAUNCH%"
rd /S /Q "%SOURCE%" >NUL 2>&1
(goto) 2>NUL & del "%~f0"

:giveup
del /F /Q "{marker}" >NUL 2>&1
"""


def stage_portable(archive: Path, staging: Path) -> Path:
    """Extract a portable update zip into ``staging``."""
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.namelist():
            # Guard against zip-slip: refuse absolute or parent-relative paths.
            resolved = (staging / member).resolve()
            if not str(resolved).startswith(str(staging.resolve())):
                raise GitHubError(f"архив содержит небезопасный путь: {member}")
        bundle.extractall(staging)

    # Archives usually wrap everything in a single top-level folder.
    entries = [entry for entry in staging.iterdir() if entry.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return staging


def apply_portable(root: Path, marker_name: str = UPDATE_MARKER) -> None:
    """Swap a portable install in place once this process exits."""
    if not getattr(sys, "frozen", False):
        # Nothing to swap: sys.executable is the interpreter this checkout runs
        # on, and replacing it would take the virtual environment with it. The
        # guard belongs here as well as in detect_install, because this function
        # is what does the damage.
        raise GitHubError(
            "обновление на месте недоступно при запуске из исходников: "
            "sys.executable — это интерпретатор, а не HUD"
        )
    if sys.platform != "win32":
        raise GitHubError("установка обновления поддерживается только в Windows")

    executable = Path(sys.executable).resolve()
    target = executable.parent
    if root.resolve() == target.resolve():
        raise GitHubError("новая версия уже распакована в целевую папку")

    marker = target / marker_name
    try:
        marker.write_text("updating", encoding="utf-8")
    except OSError:
        log.debug("cannot write the update marker, continuing", exc_info=True)

    script = Path(tempfile.gettempdir()) / f"elite-hud-update-{os.getpid()}.cmd"
    script.write_text(
        PORTABLE_HELPER_TEMPLATE.format(
            target=target,
            source=root,
            launch=executable,
            pid=os.getpid(),
            marker=marker,
        ),
        encoding="utf-8",
    )

    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        close_fds=True,
        creationflags=creationflags,
    )
    log.info("update helper started; the HUD will restart on the new version")


def clear_stale_marker() -> bool:
    """Remove the update marker if a previous swap never finished.

    Only portable copies ever write one, and an installed copy's directory is
    read-only for the user, so this must never be fatal.
    """
    try:
        marker = Path(sys.executable).resolve().parent / UPDATE_MARKER
        if marker.exists():
            marker.unlink(missing_ok=True)
            return True
    except OSError as exc:
        log.debug("cannot remove the update marker: %s", exc)
    return False


def default_download_dir() -> Path:
    """Somewhere writable for update downloads, independent of install scope."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "elite-hud" / DOWNLOAD_DIRNAME


def format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} МБ"
    if size >= 1024:
        return f"{size / 1024:.0f} КБ"
    return f"{size} Б"


@dataclass
class UpdatePlan:
    """Everything the UI needs to describe and perform an update."""

    info: UpdateInfo
    download_dir: Path = field(default_factory=default_download_dir)

    @property
    def asset_name(self) -> str:
        return self.info.asset.name

    @property
    def size_text(self) -> str:
        return format_size(self.info.asset.size)
