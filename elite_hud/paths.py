"""Locate the Elite Dangerous journal directory on any platform we care about.

The overlay targets Windows, but the project is developed on macOS, so the
resolver also understands CrossOver/Whisky bottles and Proton prefixes.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Frontier's sub-path below the "Saved Games" known folder.
ED_SUBPATH = Path("Frontier Developments") / "Elite Dangerous"

# Steam app id of Elite Dangerous, used for Proton prefix discovery.
ED_STEAM_APPID = "359320"

_INVALID_CHARS = '<>:"/\\|?*'


def _saved_games_known_folder() -> Path | None:
    """Ask Windows for the real Saved Games folder (handles OneDrive redirection)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        # FOLDERID_SavedGames {4C5C32FF-BB9D-43b0-B5B4-2D72E54EAAA4}
        guid = ctypes.create_string_buffer(bytes.fromhex("ff325c4c9dbbb043b5b42d72e54eaaa4"))

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        folder_id = GUID.from_buffer_copy(guid.raw)
        path_ptr = ctypes.c_wchar_p()
        res = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr)
        )
        if res != 0 or not path_ptr.value:
            return None
        value = Path(path_ptr.value)
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)
        return value
    except Exception as exc:  # pragma: no cover - platform specific
        log.debug("SHGetKnownFolderPath failed: %s", exc)
        return None


def _windows_candidates() -> list[Path]:
    out: list[Path] = []
    known = _saved_games_known_folder()
    if known:
        out.append(known / ED_SUBPATH)

    home = Path(os.environ.get("USERPROFILE", Path.home()))
    for base in (
        home / "Saved Games",
        home / "OneDrive" / "Saved Games",
        home / "Documents" / "Saved Games",
    ):
        out.append(base / ED_SUBPATH)

    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if onedrive:
        out.append(Path(onedrive) / "Saved Games" / ED_SUBPATH)
    return out


def _bottle_candidates() -> list[Path]:
    """CrossOver / Whisky / Proton bottles (dev machines and Linux Steam)."""
    out: list[Path] = []
    home = Path.home()

    roots = [
        home / "Library" / "Application Support" / "CrossOver" / "Bottles",
        home / "Library" / "Containers" / "com.codeweavers.CrossOver" / "Data"
        / "Library" / "Application Support" / "CrossOver" / "Bottles",
        home / ".local" / "share" / "bottles" / "bottles",
        home / "Library" / "Application Support" / "Whisky" / "Bottles",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        try:
            bottles = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError:
            continue
        for bottle in bottles:
            for users in (bottle / "drive_c" / "users", bottle / "drive_c" / "Users"):
                if not users.is_dir():
                    continue
                for userdir in users.iterdir():
                    if not userdir.is_dir() or userdir.name in {"Public", "Default", "All Users"}:
                        continue
                    out.append(userdir / "Saved Games" / ED_SUBPATH)

    steam_roots = [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / "Library" / "Application Support" / "Steam",
    ]
    for steam in steam_roots:
        prefix = (
            steam / "steamapps" / "compatdata" / ED_STEAM_APPID / "pfx"
            / "drive_c" / "users" / "steamuser" / "Saved Games" / ED_SUBPATH
        )
        out.append(prefix)
    return out


def candidate_journal_dirs() -> list[Path]:
    """Every plausible journal directory, most likely first, de-duplicated."""
    raw: list[Path] = []

    # An explicit environment override always wins; other ED tools use the
    # same variable, so honouring it keeps multi-tool setups consistent.
    override = os.environ.get("ED_JOURNAL_DIR") or os.environ.get("ED_JOURNALDIR")
    if override:
        raw.append(expand_user_path(override))

    if sys.platform == "win32":
        raw.extend(_windows_candidates())
    else:
        raw.extend(_bottle_candidates())
        raw.extend(
            [
                Path.home() / ".local" / "share" / "elite-dangerous" / "journals",
                Path("/opt/elite-dangerous/journals"),
            ]
        )

    seen: set[str] = set()
    out: list[Path] = []
    for path in raw:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def looks_like_journal_dir(path: Path) -> bool:
    """A journal dir is any directory that already holds Journal*.log files."""
    try:
        return path.is_dir() and any(path.glob("Journal.*.log"))
    except OSError:
        return False


def find_journal_dir(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """Resolve the journal directory.

    An explicit path wins if it exists; otherwise we prefer a candidate that
    already contains journals, and fall back to the first candidate whose parent
    exists (the game may not have been launched yet).
    """
    if explicit:
        path = Path(os.path.expandvars(str(explicit))).expanduser()
        if path.is_dir():
            return path
        if path.parent.is_dir():
            log.warning("journal dir %s does not exist yet, will wait for it", path)
            return path
        log.warning("configured journal dir %s is unusable", path)
        return None

    candidates = candidate_journal_dirs()
    for path in candidates:
        if looks_like_journal_dir(path):
            return path
    for path in candidates:
        if path.parent.is_dir():
            return path
    return None


def expand_user_path(value: str) -> Path:
    """Expand %VAR% (Windows) and $VAR/~ (POSIX) in a config-supplied path."""
    expanded = value
    if sys.platform == "win32":
        expanded = os.path.expandvars(expanded)
        while "%%" in expanded:
            expanded = expanded.replace("%%", "%")
    else:
        # Also expand %VAR% so a Windows-authored config still resolves on macOS.
        import re

        def _sub(match: "re.Match[str]") -> str:
            return os.environ.get(match.group(1), match.group(0))

        expanded = re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", _sub, expanded)
        expanded = os.path.expandvars(expanded)
    return Path(expanded).expanduser()


def sanitize_filename(name: str) -> str:
    return "".join("_" if ch in _INVALID_CHARS else ch for ch in name)
