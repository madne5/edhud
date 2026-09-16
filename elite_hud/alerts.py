"""Audible alerts.

The project ships no binary assets: when no custom sound file is configured we
synthesise a short three-note chime into a cached WAV at first use and hand it
to the platform's native player (``winsound`` on Windows, which is stdlib).
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

log = logging.getLogger(__name__)

SAMPLE_RATE = 44_100
#: Two-tone rising chime: root, fifth, octave.
NOTES = ((784.0, 0.10), (1174.7, 0.10), (1568.0, 0.26))
AMPLITUDE = 0.42


def synthesize_chime(path: Path) -> Path:
    """Write a pleasant rising arpeggio as a 16-bit mono WAV."""
    frames = bytearray()
    for frequency, duration in NOTES:
        count = int(SAMPLE_RATE * duration)
        attack = max(1, int(count * 0.06))
        release = max(1, int(count * 0.45))
        for index in range(count):
            envelope = 1.0
            if index < attack:
                envelope = index / attack
            elif index > count - release:
                envelope = max(0.0, (count - index) / release)
            # A little second harmonic makes it read as a chime, not a beep.
            sample = math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
            sample += 0.30 * math.sin(4 * math.pi * frequency * index / SAMPLE_RATE)
            value = int(max(-1.0, min(1.0, sample * envelope * AMPLITUDE)) * 32767)
            frames += struct.pack("<h", value)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(bytes(frames))
    return path


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "elite-hud"


class SoundPlayer:
    """Play the alert sound without blocking the UI thread."""

    def __init__(self, custom_file: str = "", volume: float = 0.8) -> None:
        self.volume = min(1.0, max(0.0, float(volume)))
        self._lock = threading.Lock()
        self._file: Path | None = None

        if custom_file:
            candidate = Path(os.path.expandvars(custom_file)).expanduser()
            if candidate.is_file():
                self._file = candidate
            else:
                log.warning("configured alert sound %s not found, using built-in", candidate)

        if self._file is None:
            self._file = self._builtin_chime()

    def _builtin_chime(self) -> Path | None:
        """Create (and cache) the synthesised chime, falling back to tempdir."""
        for directory in (cache_dir(), Path(tempfile.gettempdir()) / "elite-hud"):
            target = directory / "alert-chime.wav"
            try:
                if not target.is_file():
                    synthesize_chime(target)
                return target
            except OSError as exc:
                log.debug("cannot write alert sound to %s: %s", directory, exc)
        log.warning("could not create the built-in alert sound anywhere")
        return None

    @property
    def available(self) -> bool:
        return self._file is not None

    def play(self) -> None:
        if self._file is None:
            return
        thread = threading.Thread(target=self._play_blocking, name="alert-sound", daemon=True)
        thread.start()

    def _play_blocking(self) -> None:
        path = str(self._file)
        try:
            if sys.platform == "win32":
                import winsound

                with self._lock:
                    winsound.PlaySound(
                        path,
                        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                    )
                return

            command: list[str] | None = None
            if sys.platform == "darwin":
                if shutil.which("afplay"):
                    command = ["afplay", "-v", f"{self.volume:.2f}", path]
            else:
                for player, args in (
                    ("paplay", []),
                    ("aplay", ["-q"]),
                    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
                ):
                    if shutil.which(player):
                        command = [player, *args, path]
                        break

            if command is None:
                log.debug("no audio player available for alert sound")
                return
            with self._lock:
                subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            log.exception("failed to play alert sound")
