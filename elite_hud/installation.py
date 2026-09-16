"""How this copy of the HUD was installed, and keeping one instance running.

Two deployment shapes are supported:

* **installed** -- placed by the Inno Setup package. There is an uninstall
  registry entry, updates arrive as a new ``setup.exe``, and the HUD lives in
  ``Program Files`` or ``%LOCALAPPDATA%`` depending on the chosen scope.
* **portable** -- an unpacked zip. Updates arrive as another zip.

The distinction decides which release asset the updater downloads.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: Must match ``AppMutex`` in installer/elite-hud.iss so the installer can tell
#: that the HUD is running and close it before replacing files.
APP_MUTEX_NAME = "elite-hud-single-instance-mutex"

#: Must match ``AppId`` in installer/elite-hud.iss (without the {{ }} braces
#: Inno adds around it in the registry key name).
APP_ID = "{8F2C4A91-3D7E-4B62-9A15-C6E0B84D5F37}"

INSTALLED = "installed"
PORTABLE = "portable"


@dataclass(frozen=True)
class InstallInfo:
    mode: str
    location: Path | None = None
    version: str = ""

    @property
    def is_installed(self) -> bool:
        return self.mode == INSTALLED

    @property
    def update_preference(self) -> str:
        """Which release asset this copy should download."""
        return "installer" if self.is_installed else "portable"


def _registry_locations() -> list[tuple[int, str]]:
    """Every uninstall key hive/view an Inno install could have written.

    The 32-bit view is selected with ``KEY_WOW64_32KEY`` rather than by writing
    ``WOW6432Node`` into the path: Microsoft explicitly asks new applications
    not to hardcode that node, and the flag keeps working under registry
    redirection on every Windows version.
    """
    import winreg  # noqa: PLC0415 - Windows only

    subkey = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
    views = (
        0,
        getattr(winreg, "KEY_WOW64_32KEY", 0),
        getattr(winreg, "KEY_WOW64_64KEY", 0),
    )

    locations: list[tuple[int, str]] = []
    seen: set[int] = set()
    # A per-user install writes to HKCU, a per-machine one to HKLM; an
    # "admin" install of a 32-bit app lands in the 32-bit view of HKLM.
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in views:
            handle = hive | view
            if handle in seen:
                continue
            seen.add(handle)
            locations.append((handle, subkey))
    return locations


def detect_install() -> InstallInfo:
    """Best-effort description of how this copy is deployed."""
    if sys.platform != "win32":
        return InstallInfo(PORTABLE, Path(sys.executable).resolve().parent)

    try:
        import winreg  # noqa: PLC0415 - Windows only
    except ImportError:  # pragma: no cover - defensive
        return InstallInfo(PORTABLE, Path(sys.executable).resolve().parent)

    for hive, subkey in _registry_locations():
        try:
            with winreg.OpenKey(hive, subkey) as key:
                version = _query(key, "DisplayVersion")
                location = _query(key, "InstallLocation")
        except OSError:
            continue
        folder = Path(location) if location else Path(sys.executable).resolve().parent
        log.debug("found Inno Setup install entry (%s, version %s)", folder, version)
        return InstallInfo(INSTALLED, folder, version)

    return InstallInfo(PORTABLE, Path(sys.executable).resolve().parent)


def _query(key, name: str) -> str:
    import winreg  # noqa: PLC0415 - Windows only

    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value)


def is_elevated() -> bool:
    """True when this process already runs with administrator rights."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes  # noqa: PLC0415 - Windows only

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return False


def needs_elevation(location: Path | None = None) -> bool:
    """Whether replacing files in ``location`` requires a UAC prompt.

    A per-user install lives somewhere the user owns, so it never needs
    elevation -- and prompting for it anyway would be the difference between a
    silent update and an intrusive one.
    """
    if sys.platform != "win32":
        return False
    if is_elevated():
        return False
    target = location or Path(sys.executable).resolve().parent
    try:
        return not os.access(str(target), os.W_OK)
    except OSError:
        return True


@dataclass
class SingleInstanceGuard:
    """Hold a named mutex so a second HUD refuses to start.

    The same mutex is what Inno Setup looks for, so keeping it alive for the
    whole process lifetime is what lets a silent update close and restart us.
    """

    name: str = APP_MUTEX_NAME
    _handle: object | None = None
    _lock_path: Path | None = None
    _lock_fd: int | None = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            return self._acquire_windows()
        return self._acquire_lockfile()

    def _acquire_windows(self) -> bool:
        import ctypes  # noqa: PLC0415 - Windows only

        ERROR_ALREADY_EXISTS = 183

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # HANDLE is pointer sized: without explicit types ctypes truncates it
        # to int and CloseHandle then gets a bogus value.
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool

        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            log.warning("CreateMutexW failed; allowing startup")
            return True
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def _acquire_lockfile(self) -> bool:
        """POSIX fallback: an advisory lock the kernel drops on process exit.

        A lock file without locking would need liveness probing to detect a
        crashed run; ``flock`` makes that unnecessary, because the lock dies
        with the process holding it.
        """
        import fcntl  # noqa: PLC0415 - POSIX only
        import tempfile  # noqa: PLC0415

        path = Path(tempfile.gettempdir()) / f"{self.name}.lock"
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            log.debug("cannot open the lock file %s: %s", path, exc)
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        os.truncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("ascii"))
        self._lock_fd = fd
        self._lock_path = path
        return True

    def release(self) -> None:
        if self._handle is not None:
            try:
                import ctypes  # noqa: PLC0415

                ctypes.windll.kernel32.CloseHandle(self._handle)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                log.debug("closing the mutex failed", exc_info=True)
            self._handle = None
        if self._lock_fd is not None:
            # Closing the descriptor releases the advisory lock.
            try:
                os.close(self._lock_fd)
            except OSError:  # pragma: no cover - defensive
                pass
            self._lock_fd = None
        if self._lock_path is not None:
            self._lock_path.unlink(missing_ok=True)
            self._lock_path = None
