"""Start the overlay for real and check that it stays up.

The test suite exercises pieces of the program; this runs the thing a commander
actually launches, window and tray included, against a synthetic journal. It
exists because a release very nearly shipped where ``main`` called a class that
had been deleted: every unit test passed, ``--version`` and ``--self-check`` both
return before the window is created, and the only symptom would have been an
installer that closes instantly.

Two outcomes count as failure:

* the process exits before the deadline, whatever the exit code -- the overlay is
  supposed to keep running;
* it writes a traceback, or logs an error, while starting.

Used by CI (offscreen) and runnable locally on a machine with a display.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: How long the overlay must survive. Long enough for Qt, the tray and the
#: first journal replay to all have happened.
RUN_SECONDS = 12.0

EVENTS = [
    {"event": "Fileheader", "part": 1, "language": "Russian/EN", "Odyssey": True},
    {"event": "Commander", "Name": "Smoke", "FID": "F000000"},
    {"event": "LoadGame", "Commander": "Smoke", "Credits": 1_000_000,
     "Ship": "panthermkii", "ShipName": "Smoke Test"},
    {"event": "ShipyardSwap", "ShipType": "panthermkii",
     "ShipType_Localised": "Panther Clipper Mk II"},
    {"event": "Loadout", "Ship": "panthermkii", "ShipIdent": "SMK-01",
     "CargoCapacity": 1232, "MaxJumpRange": 40.5,
     "FuelCapacity": {"Main": 32.0, "Reserve": 0.63}},
    {"event": "FSDJump", "StarSystem": "Achenar", "SystemAddress": 1,
     "StarPos": [0.0, 0.0, 0.0], "Population": 1000},
    {"event": "FSSDiscoveryScan", "SystemAddress": 1, "SystemName": "Achenar",
     "Progress": 0.45, "BodyCount": 15, "NonBodyCount": 2},
    {"event": "Scan", "SystemAddress": 1, "BodyID": 1, "BodyName": "Achenar 1"},
    {"event": "Cargo", "Vessel": "Ship", "Count": 199,
     "Inventory": [{"Name": "gold", "Count": 199, "Stolen": 0}]},
    {"event": "Missions", "Active": [{"MissionID": 1, "Name": "Mission_Delivery",
                                      "Expiry": "2026-12-31T00:00:00Z"}]},
    {"event": "CarrierStats", "CarrierID": 1, "Callsign": "V3G-N1H",
     "Name": "[SMOKE] Test Carrier", "CarrierType": "FleetCarrier",
     "DockingAccess": "all", "FuelLevel": 500,
     "SpaceUsage": {"TotalCapacity": 25000, "Cargo": 7001, "FreeSpace": 5142}},
]


def write_journal(directory: Path) -> Path:
    """One journal file and a status file, as the game would leave them."""
    stamp = datetime.now(timezone.utc)
    lines = []
    for index, event in enumerate(EVENTS):
        moment = stamp + timedelta(seconds=index)
        lines.append(
            json.dumps({**event, "timestamp": moment.isoformat().replace("+00:00", "Z")})
        )
    path = directory / "Journal.2026-01-01T000000.01.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (directory / "Status.json").write_text(
        json.dumps(
            {
                "timestamp": stamp.isoformat().replace("+00:00", "Z"),
                "event": "Status",
                "Flags": 0,
                "Balance": 1_000_000,
                "Cargo": 199,
            }
        ),
        encoding="utf-8",
    )
    return directory


BAD_LINE = re.compile(r"Traceback \(most recent call last\)|^\d\d:\d\d:\d\d ERROR", re.M)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal = root / "journal"
        journal.mkdir(parents=True, exist_ok=True)
        write_journal(journal)
        config = root / "config.toml"

        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

        command = [
            sys.executable,
            "-m",
            "elite_hud",
            "--journal-dir",
            str(journal),
            "--config",
            str(config),
            "--force",
            "--verbose",
        ]
        print(f"starting: {' '.join(command)}", flush=True)
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            output, _ = process.communicate(timeout=RUN_SECONDS)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
            print(f"the overlay stayed up for {RUN_SECONDS:.0f}s", flush=True)
        else:
            print(output or "", flush=True)
            print(
                f"FAIL: the overlay exited after {RUN_SECONDS:.0f}s or less "
                f"(exit code {process.returncode}); it is supposed to keep running",
                flush=True,
            )
            return 1

    problems = BAD_LINE.findall(output or "")
    if problems:
        print(output or "", flush=True)
        print(f"FAIL: the overlay reported {len(problems)} error(s) while running", flush=True)
        return 1
    print("no tracebacks and no errors in the log", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
