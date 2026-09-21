"""Fix the macOS file flags that stop Qt from finding its platform plugin.

    python tools/fix_macos_qt.py                 # the .venv beside this repo
    python tools/fix_macos_qt.py path/to/venv    # or any directory

Symptom, which is confusing because nothing is actually missing
--------------------------------------------------------------

    $ python -c "from PySide6.QtWidgets import QApplication; QApplication([])"
    qt.qpa.plugin: Could not find the Qt platform plugin "offscreen" in ""
    This application failed to start because no Qt platform plugin could be
    initialized.

The plugin files are all there. ``ls`` lists them, ``file`` reads them as Mach-O
bundles, and ``ctypes.CDLL`` loads them happily -- yet Qt insists it cannot find
them, and ``QT_DEBUG_PLUGINS=1`` does not even print a rejection, because the
loader never considers a candidate at all.

Cause
-----

Qt enumerates the plugin directory with ``QDir::entryList(QDir::Files)``, and
that filter excludes hidden files. On macOS a file is "hidden" if it carries the
BSD flag ``UF_HIDDEN`` (0x8000) as well as if its name begins with a dot, and
``QFileInfo::isHidden()`` honours that flag.

Some wheels unpack with those flags set. In this project's venv 3581 of the 4447
files under ``PySide6`` had ``UF_HIDDEN``, including all three platform plugins
(``libqcocoa``, ``libqminimal``, ``libqoffscreen``). So the directory looked
empty to Qt while looking perfectly normal to everything else, and the failure
had nothing to do with Qt, PySide6 or the code that used it.

Check it in one line
--------------------

    python -c "import os,glob;print({p: hex(os.stat(p).st_flags) for p in glob.glob('.venv/lib/python3.13/site-packages/PySide6/Qt/plugins/platforms/*')})"

Any value with 0x8000 in it is a plugin Qt cannot see.

The fix
-------

``chflags -R nohidden`` on the venv, which is what this script does. It is
harmless and idempotent, and worth re-running after any ``pip install`` that
touches PySide6: the flags come with the installation, not with this repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

#: UF_HIDDEN, the flag that makes QDir::Files skip a file.
UF_HIDDEN = 0x8000


def hidden_entries(root: Path) -> list[Path]:
    """Every entry under ``root`` carrying UF_HIDDEN, symlinks included.

    ``os.lstat``, not ``os.stat``: the flag is checked on the link itself, and
    ``chflags -R`` fixes both, but a walk that followed links would report the
    same target many times and miss nothing useful.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + filenames:
            path = Path(dirpath) / name
            try:
                flags = os.lstat(path).st_flags
            except (OSError, AttributeError):
                continue
            if flags & UF_HIDDEN:
                found.append(path)
    return found


def platform_plugins(root: Path) -> list[Path]:
    """The Qt platform plugins inside a venv, if it has any."""
    matches = list(root.glob("lib/python*/site-packages/PySide6/Qt/plugins/platforms/*"))
    if matches:
        return matches
    return list(root.glob("**/PySide6/Qt/plugins/platforms/*"))


def default_root() -> Path:
    """The venv beside this repository, which is what the README uses."""
    return Path(__file__).resolve().parent.parent / ".venv"


def main(argv: list[str]) -> int:
    if os.uname().sysname != "Darwin":
        print("this only applies to macOS; nothing to do", file=sys.stderr)
        return 0

    root = Path(argv[1]).expanduser().resolve() if len(argv) > 1 else default_root()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    plugins = platform_plugins(root)
    before = hidden_entries(root)
    print(f"{root}")
    print(f"  platform plugins found: {len(plugins)}")
    print(f"  entries with UF_HIDDEN: {len(before)}")
    if not before:
        print("  nothing to fix")
        return 0

    result = subprocess.run(["chflags", "-R", "nohidden", str(root)], check=False)
    if result.returncode != 0:
        print("chflags failed; re-run with the same path by hand", file=sys.stderr)
        return result.returncode

    after = hidden_entries(root)
    print(f"  cleared: {len(before) - len(after)}")
    if after:
        print(f"  still hidden: {len(after)} (first: {after[0]})", file=sys.stderr)
        return 1
    print("\nQt should start now. Verify with:")
    print('  python -c "from PySide6.QtWidgets import QApplication; QApplication([]); print(\'ok\')"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
