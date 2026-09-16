"""TOML configuration for elite-hud.

A default ``config.toml`` is written next to the executable on first run so the
user has something to edit.  Parsing is done with the stdlib ``tomllib``, which
keeps the runtime dependency list at exactly one package (PySide6).
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CONFIG_FILENAME = "config.toml"


@dataclass
class JournalConfig:
    #: Empty means "auto-detect".
    path: str = ""
    #: Seconds between directory polls.
    poll_interval: float = 0.75
    #: Replay journal files modified within this many days at startup so the
    #: HUD is correct even if it was started mid-session. 0 disables history.
    history_days: int = 7
    #: Replay history at all.
    replay_history: bool = True


@dataclass
class LabelConfig:
    """Text shown by the HUD. Change these to localise or shorten the bar."""

    carrier: str = "ФК"
    bodies: str = "тел"
    fss: str = "FSS"
    bio: str = "БИО"
    bio_body: str = "тел"
    #: marks a value that is a lower bound for a whole genus, e.g. "≥19.0M"
    at_least: str = "≥"
    waiting: str = "ожидание журнала"
    no_system: str = "нет данных"


@dataclass
class OverlayConfig:
    enabled: bool = True
    #: "top-center", "top-left", "top-right", "bottom-center"
    position: str = "top-center"
    #: Distance from the screen edge, in pixels.
    offset_y: int = 4
    offset_x: int = 0
    font_family: str = "Consolas"
    font_size: int = 13
    #: 0.0-1.0, applied to the whole HUD.
    opacity: float = 0.92
    #: Let mouse clicks pass through to the game.
    click_through: bool = True
    #: Re-assert topmost a few times per second (Windows games steal z-order).
    always_on_top: bool = True
    #: Repaint rate; also the countdown tick rate.
    refresh_hz: float = 10.0
    #: Background/foreground colours as #RRGGBB.
    background: str = "#0b0f14"
    background_alpha: int = 165
    foreground: str = "#d8e2ef"
    accent: str = "#ff9d2e"
    danger: str = "#ff5555"
    success: str = "#5ee08a"
    #: Segments shown in the bar, in order. Available: carrier, system, fss, bio.
    segments: list[str] = field(default_factory=lambda: ["carrier", "system", "fss", "bio"])
    #: Draw a subtle rounded plate behind the text.
    show_background: bool = True
    #: Prefix each segment with a small glyph.
    show_glyphs: bool = True
    labels: LabelConfig = field(default_factory=LabelConfig)


@dataclass
class AlertConfig:
    #: Payout that counts as "worth stopping for", in credits.
    min_value: int = 7_000_000
    sound_enabled: bool = True
    #: Custom WAV/MP3 path; empty uses the bundled synthesised tone.
    sound_file: str = ""
    volume: float = 0.8
    #: Lowest confidence that may play a sound: possible|guaranteed|confirmed.
    sound_min_confidence: str = "guaranteed"
    #: How long the HUD stays in the flashed alert state.
    display_seconds: float = 8.0
    #: Windows toast notification in addition to the HUD flash.
    desktop_notification: bool = False


@dataclass
class UpdateConfig:
    """Self-update from GitHub Releases."""

    enabled: bool = True
    #: off      -- never look
    #: notify   -- look, tell the user, do nothing else
    #: download -- look, download, apply on the next start
    #: install  -- look, download and apply straight away
    mode: str = "install"
    #: GitHub repository that publishes the releases, as "owner/name".
    repo: str = "madne5/edhud"
    #: Only needed for a private repository (public releases need no token).
    token: str = ""
    check_on_start: bool = True
    check_interval_hours: float = 6.0
    include_prerelease: bool = False
    #: Which release asset to fetch: any | installer | portable
    asset: str = "any"
    timeout_seconds: float = 15.0
    #: Keep the downloaded package after a failed install, for troubleshooting.
    keep_downloads: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"
    #: Empty writes to stderr only.
    file: str = ""


@dataclass
class Config:
    journal: JournalConfig = field(default_factory=JournalConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    #: species name -> credit value, overrides for the bundled table
    exobiology_overrides: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        config = cls()
        if path is None or not path.is_file():
            return config
        try:
            with open(path, "rb") as handle:
                raw: dict[str, Any] = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            log.error("cannot read %s: %s -- using defaults", path, exc)
            return config

        _merge(config.journal, raw.get("journal"))
        _merge(config.overlay, raw.get("overlay"))
        _merge(config.overlay.labels, raw.get("overlay", {}).get("labels"))
        _merge(config.alerts, raw.get("alerts"))
        _merge(config.update, raw.get("update"))
        _merge(config.logging, raw.get("logging"))

        overrides = raw.get("exobiology", {}).get("values")
        if isinstance(overrides, dict):
            config.exobiology_overrides = {
                str(k): int(v) for k, v in overrides.items() if isinstance(v, (int, float))
            }
        config.validate()
        return config

    def validate(self) -> None:
        overlay = self.overlay
        overlay.opacity = min(1.0, max(0.15, float(overlay.opacity)))
        overlay.refresh_hz = min(60.0, max(1.0, float(overlay.refresh_hz)))
        overlay.font_size = max(7, int(overlay.font_size))
        overlay.background_alpha = min(255, max(0, int(overlay.background_alpha)))
        if overlay.position not in VALID_POSITIONS:
            log.warning("unknown overlay.position %r, using top-center", overlay.position)
            overlay.position = "top-center"
        if not overlay.segments:
            overlay.segments = ["carrier", "system", "fss", "bio"]
        unknown = [s for s in overlay.segments if s not in VALID_SEGMENTS]
        if unknown:
            log.warning("dropping unknown overlay.segments %s", unknown)
            overlay.segments = [s for s in overlay.segments if s in VALID_SEGMENTS] or ["system", "fss"]

        alerts = self.alerts
        alerts.min_value = max(0, int(alerts.min_value))
        alerts.volume = min(1.0, max(0.0, float(alerts.volume)))
        alerts.display_seconds = max(0.0, float(alerts.display_seconds))
        if alerts.sound_min_confidence not in VALID_CONFIDENCES:
            log.warning(
                "unknown alerts.sound_min_confidence %r, using 'guaranteed'",
                alerts.sound_min_confidence,
            )
            alerts.sound_min_confidence = "guaranteed"

        self.journal.poll_interval = min(10.0, max(0.05, float(self.journal.poll_interval)))
        self.journal.history_days = max(0, int(self.journal.history_days))

        update = self.update
        if update.mode not in VALID_UPDATE_MODES:
            log.warning("unknown update.mode %r, using 'notify'", update.mode)
            update.mode = "notify"
        if update.asset not in VALID_UPDATE_ASSETS:
            log.warning("unknown update.asset %r, using 'any'", update.asset)
            update.asset = "any"
        update.check_interval_hours = max(0.25, float(update.check_interval_hours))
        update.timeout_seconds = min(120.0, max(3.0, float(update.timeout_seconds)))
        update.repo = update.repo.strip().strip("/")

    def to_toml(self) -> str:
        lines: list[str] = [
            "# elite-hud configuration",
            "# Every key here is optional; delete a line to fall back to the default.",
            "",
        ]
        for section_name, section in (
            ("journal", self.journal),
            ("overlay", self.overlay),
            ("alerts", self.alerts),
            ("update", self.update),
            ("logging", self.logging),
        ):
            lines.append(f"[{section_name}]")
            nested: list[tuple[str, Any]] = []
            for key, value in asdict(section).items():
                # Nested dataclasses become their own sub-table, not a dict literal.
                if isinstance(value, dict):
                    nested.append((key, value))
                    continue
                lines.append(f"{key} = {_toml_value(value)}")
            for key, value in nested:
                lines.append("")
                lines.append(f"[{section_name}.{key}]")
                for sub_key, sub_value in value.items():
                    lines.append(f"{sub_key} = {_toml_value(sub_value)}")
            lines.append("")
        lines.append("[exobiology.values]")
        lines.append("# Override individual species payouts when Frontier rebalances them.")
        lines.append('# "Stratum Tectonicas" = 19010800')
        lines.append("")
        return "\n".join(lines)


VALID_POSITIONS = {"top-center", "top-left", "top-right", "bottom-center", "bottom-left", "bottom-right"}
VALID_SEGMENTS = {"carrier", "system", "fss", "bio"}
VALID_CONFIDENCES = {"possible", "guaranteed", "confirmed"}
VALID_UPDATE_MODES = {"off", "notify", "download", "install"}
VALID_UPDATE_ASSETS = {"any", "installer", "portable"}


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return str(value)


def _merge(target: Any, raw: Any) -> None:
    """Copy known keys from a parsed TOML section onto a dataclass instance."""
    if not isinstance(raw, dict) or not is_dataclass(target):
        return
    known = {f.name: f for f in fields(target)}
    for key, value in raw.items():
        field_info = known.get(key)
        if field_info is None:
            log.warning("ignoring unknown config key %r", key)
            continue
        current = getattr(target, key)
        try:
            if is_dataclass(current) and isinstance(value, dict):
                # Nested table: recurse so the sub-dataclass keeps its defaults.
                _merge(current, value)
            elif isinstance(current, bool):
                setattr(target, key, bool(value))
            elif isinstance(current, int) and not isinstance(current, bool):
                setattr(target, key, int(value))
            elif isinstance(current, float):
                setattr(target, key, float(value))
            elif isinstance(current, list):
                if not isinstance(value, list):
                    raise TypeError("expected a list")
                setattr(target, key, [str(v) for v in value])
            elif isinstance(current, str):
                setattr(target, key, str(value))
            else:
                setattr(target, key, value)
        except (TypeError, ValueError) as exc:
            log.warning("bad value for %r (%r): %s -- keeping %r", key, value, exc, current)


def set_update_mode(path: Path, mode: str) -> bool:
    """Rewrite ``[update] mode`` in place, preserving comments and layout.

    Returns False when the file is missing or the edit could not be written.
    """
    if mode not in VALID_UPDATE_MODES:
        return False
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    section = ""
    inserted = False
    found_section = False
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            if section == "update":
                found_section = True
            continue
        if section != "update" or stripped.startswith("#"):
            continue
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key == "mode":
            lines[index] = f'mode = "{mode}"'
            inserted = True
            break

    if not inserted:
        if not found_section:
            lines += ["", "[update]"]
        lines.append(f'mode = "{mode}"')

    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("cannot persist the update mode: %s", exc)
        return False
    return True


def ensure_config_file(path: Path) -> bool:
    """Write a commented default config if none exists. Returns True if created."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Config().to_toml(), encoding="utf-8")
    return True
