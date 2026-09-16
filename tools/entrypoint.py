"""Entry point for the PyInstaller build.

PyInstaller runs the entry *script* directly, as ``__main__``. The package's own
``elite_hud/__main__.py`` uses a relative import, which is correct under
``python -m elite_hud`` but raises ``ImportError: attempted relative import with
no known parent package`` when the file is executed as a script.

That failure is invisible in a windowed build: with no console, PyInstaller
reports the traceback through a message box, and a CI runner waits for someone
to click it forever. This entry point uses absolute imports only.

    python tools/entrypoint.py --version

``tests/test_entrypoints.py`` runs both entry points exactly the way their real
callers do, so this cannot regress unnoticed.
"""

from __future__ import annotations

import sys

from elite_hud.app import main

if __name__ == "__main__":
    sys.exit(main())
