"""TOML configuration for elite-hud.

A default ``config.toml`` is written next to the executable on first run so the
user has something to edit.  Parsing is done with the stdlib ``tomllib``, which
keeps the runtime dependency list at exactly one package (PySide6).
"""

from __future__ import annotations

import logging
import os
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
    #: shown while the carrier is recharging: "ФК готов через 04:12"
    carrier_cooldown: str = "готов через"
    #: shown briefly once it may jump again
    carrier_ready: str = "готов"
    #: game modes
    mode_open: str = "ОТКРЫТАЯ ИГРА"
    mode_solo: str = "СОЛО"
    mode_group: str = "ЧАСТНАЯ СЕССИЯ"
    #: second-row labels
    missions: str = "миссии"
    jump_max: str = "макс"
    jump_current: str = "тек"
    bodies: str = "тел"
    #: marks a value that is a lower bound for a whole genus, e.g. "≥19.0M"
    waiting: str = "ожидание журнала"
    #: notification title when landing on a body would be a first footfall
    #: unredeemed value: "К зачислению 343.3M"
    #: suffix naming how many samples back the figure: "5 проб"
    #: credit balance in the top row
    balance: str = "баланс"
    #: faction influence in the current system: "Traders & Explorers Inc. 30%"
    #: notoriety level: "Плохая репутация 3"
    notoriety: str = "Плохая репутация"
    #: unpaid fines
    fines: str = "штраф"
    #: unsold exploration data, counted rather than valued
    #: tonnes, for the cargo hold
    tonnes: str = "т"
    #: what a carrier actually holds: "KSS0 груз 6313/60000 т"
    carrier_cargo: str = "груз"
    #: space held back by an outstanding buy order, shown only when there is
    #: one: "V3G-N1H груз 7001/25000 т · бронь 12857"
    carrier_reserved: str = "бронь"
    #: units for the cartography counts
    #: jump target: "след. Blu Theia CB-K c23-0 (K, 3)"
    jump_next: str = "след."
    #: material pickup line: "+3 Вольфрам (Сырьевой, Редкость: 3)  Всего: 79"
    rarity: str = "Редкость"
    total: str = "Всего"
    #: the three material categories, as the journal spells them
    material_raw: str = "Сырьевой"
    material_manufactured: str = "Промышленный"
    material_encoded: str = "Данные"
    #: plural noun for remaining jumps
    jumps: str = "прыжка"
    #: cargo missions: "взять 196 т · сдать 4320 т"
    deliveries_collect: str = "взять"
    deliveries_deliver: str = "сдать"
    #: colonisation site: "Shaara Gateway 12% · осталось 3120 т"
    colony: str = "стройка"
    colony_left: str = "осталось"
    colony_needed: str = "нужно"
    colony_done: str = "достроена"
    colony_failed: str = "стройка провалена"
    #: EDSM line for the system being jumped to
    edsm_discovered: str = "открыта"
    edsm_fuel: str = "заправка"
    edsm_yes: str = "да"
    edsm_no: str = "нет"
    edsm_traffic: str = "трафик"
    edsm_traffic_none: str = "нет"
    edsm_day: str = "сутки"
    edsm_week: str = "неделя"
    edsm_total: str = "всего"
    #: Shown when EDSM has never heard of the system. Deliberately not "nobody
    #: has been here": EDSM only holds what commanders uploaded, so an absence
    #: there is not proof of anything.
    edsm_unknown: str = "в EDSM нет данных — возможно, не посещалась"


@dataclass
class OverlayConfig:
    enabled: bool = True
    #: "top-center", "top-left", "top-right", "bottom-center"
    position: str = "top-center"
    #: Which display to appear on:
    #:   primary -- the primary display (default)
    #:   cursor  -- the display the mouse pointer is on
    #:   0, 1, … -- a display by zero-based index
    #:   anything else -- matched against the display name
    monitor: str = "primary"
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
    #: Restricted, but not an error: a carrier whose docking is limited.
    #: Separate from accent so the meaning can be changed on its own.
    warning: str = "#ff9d2e"
    #: Segments shown in the bar, in order. Available: carrier, system, fss, bio.
    segments: list[str] = field(
        default_factory=lambda: [
            "carrier",
            "system",
            "balance",
            "ship",
            "cargo",
            "missions",
            "deliveries",
        ]
    )
    #: Segments in the always-visible second row. Available: next, carriers,
    #: mode, crime.
    #:
    #: Everything is on by default. A segment that has nothing to say stays
    #: hidden anyway -- the crime readout vanishes for a clean commander, and the
    #: jump target for one with no route -- so shipping them off bought nothing
    #: and cost a commander a trip into the tray menu to discover a feature
    #: existed at all.
    status_segments: list[str] = field(
        default_factory=lambda: ["next", "carriers", "colony", "mode", "crime"]
    )
    #: Show the line that explains a refused docking request, with its reason.
    show_docking_denied: bool = True
    #: Draw a subtle rounded plate behind the text.
    show_background: bool = True
    #: Prefix each segment with a small glyph.
    show_glyphs: bool = True
    labels: LabelConfig = field(default_factory=LabelConfig)



@dataclass
class CarrierConfig:
    """Fleet carrier jump timings.

    The journal never reports a cooldown directly, so the HUD derives it from
    the events that do exist. These numbers are Frontier's, not ours, and are
    here so a rebalance is a config edit rather than a new release.
    """

    #: Spool-up between requesting a jump and the carrier departing. Frontier's
    #: figure is "at least 15 minutes"; only used when a CarrierJumpRequest
    #: carries no DepartureTime (journals older than Update 14).
    spool_minutes: float = 15.0
    #: Cooldown after a jump, counted from DepartureTime. Measured from real
    #: journals at "no more than 296 seconds"; 290 is the tools' value and fits.
    jump_cooldown_seconds: float = 290.0
    #: How long the jump itself takes, from DepartureTime to arrival. Measured
    #: at 59-64 seconds across seventeen jumps. Only used to interpret a
    #: CarrierJump event, whose timestamp is the arrival.
    jump_duration_seconds: float = 62.0
    #: Cooldown after cancelling a scheduled jump.
    cancel_cooldown_seconds: float = 60.0
    #: Draw the cooldown segment at all.
    show_cooldown: bool = True


@dataclass
class CommanderConfig:
    """Game constants about the commander, not display choices."""

    #: How many missions the game lets a commander hold at once.
    mission_capacity: int = 20


@dataclass
class EdsmConfig:
    """What to look up about the system we are jumping to.

    EDSM is a player-run database of what commanders chose to upload, and these
    are the questions it can answer before the journal can: whether the system is
    known at all, who first reported it, whether the primary star can be scooped
    for fuel, and how much traffic it sees.
    """

    enabled: bool = True
    #: Requests are background; this bounds one of them.
    timeout_seconds: float = 15.0
    #: Who discovered the system, and when.
    show_discovery: bool = True
    #: Day, week and total visits. EDSM has no month or year to show.
    show_traffic: bool = True
    #: Whether the primary star can be scooped, which decides a fuel stop.
    show_fuel_star: bool = True
    #: Re-check an unknown system after arriving in it, so "no data" is
    #: confirmed or corrected rather than left standing.
    verify_on_arrival: bool = True
    #: How long the line stays after arriving in the system it describes. The
    #: line about the system being jumped *to* is useful for the whole flight;
    #: the same line about the system just arrived in has said everything it has
    #: to say, and leaving it up makes the bar look stuck. 0 keeps it until the
    #: next jump, which is what it did before.
    arrival_display_seconds: float = 15.0


@dataclass
class MaterialsConfig:
    """The engineering-material pickup line.

    One line of text, shown for a few seconds when something is collected:
    "+1 Сера (Редкость: 1)  Всего: 285". Rarity is the only part the journal
    never states, so it can be switched off here for anyone who would rather
    not rely on the bundled table.
    """

    #: Track holdings and show pickups at all.
    enabled: bool = True
    #: Show the pickup line as materials are collected.
    notify_collected: bool = True
    #: Append "(Редкость: N)".
    rarity: bool = True
    #: Append "Всего: N" once a Materials event has reported the whole hold.
    show_total: bool = True
    #: How long a line stays on screen.
    display_seconds: float = 4.0
    #: One colour per category, so a pickup says what kind of material it was
    #: before the word is read: minerals, parts, data.
    raw_color: str = "#e0a458"
    manufactured_color: str = "#5ec8e0"
    encoded_color: str = "#b98ce0"


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
    carrier: CarrierConfig = field(default_factory=CarrierConfig)
    commander: CommanderConfig = field(default_factory=CommanderConfig)
    materials: MaterialsConfig = field(default_factory=MaterialsConfig)
    edsm: EdsmConfig = field(default_factory=EdsmConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @staticmethod
    def _table(raw: dict, name: str) -> dict:
        """A section, or an empty one when the file put something else there.

        Every other kind of malformed config degrades with a log line. Writing
        ``overlay = false``, which is valid TOML, used to raise AttributeError
        out of ``load`` and stop the HUD from starting at all -- before logging
        was even configured, so nothing recorded why.
        """
        value = raw.get(name)
        if value is None:
            return {}
        if not isinstance(value, dict):
            log.warning("config section [%s] is %s, not a table; ignoring it",
                        name, type(value).__name__)
            return {}
        return value

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
        if not isinstance(raw, dict):  # pragma: no cover - tomllib always gives one
            return config

        overlay = cls._table(raw, "overlay")
        _merge(config.journal, cls._table(raw, "journal"))
        _merge(config.overlay, overlay)
        _merge(config.overlay.labels, cls._table(overlay, "labels"))
        _merge(config.carrier, cls._table(raw, "carrier"))
        _merge(config.commander, cls._table(raw, "commander"))
        _merge(config.materials, cls._table(raw, "materials"))
        _merge(config.edsm, cls._table(raw, "edsm"))
        _merge(config.update, cls._table(raw, "update"))
        _merge(config.logging, cls._table(raw, "logging"))


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
        # An empty list is honoured rather than replaced. Unticking every block
        # in the top row used to substitute a hardcoded list, so four blocks the
        # commander had switched off kept drawing, and the config file recorded
        # a state the menu had never shown.
        unknown = [s for s in overlay.segments if s not in VALID_SEGMENTS]
        if unknown:
            log.warning("dropping unknown overlay.segments %s", unknown)
            overlay.segments = [s for s in overlay.segments if s in VALID_SEGMENTS]

        unknown_status = [s for s in overlay.status_segments if s not in VALID_STATUS_SEGMENTS]
        if unknown_status:
            log.warning("dropping unknown overlay.status_segments %s", unknown_status)
            overlay.status_segments = [s for s in overlay.status_segments if s in VALID_STATUS_SEGMENTS]


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

        carrier = self.carrier
        carrier.spool_minutes = min(120.0, max(0.0, float(carrier.spool_minutes)))
        carrier.jump_cooldown_seconds = min(3600.0, max(0.0, float(carrier.jump_cooldown_seconds)))
        carrier.jump_duration_seconds = min(600.0, max(0.0, float(carrier.jump_duration_seconds)))
        carrier.cancel_cooldown_seconds = min(3600.0, max(0.0, float(carrier.cancel_cooldown_seconds)))

        self.commander.mission_capacity = max(1, int(self.commander.mission_capacity))

        self.materials.display_seconds = min(
            30.0, max(0.5, float(self.materials.display_seconds))
        )

        self.edsm.timeout_seconds = min(60.0, max(3.0, float(self.edsm.timeout_seconds)))
        self.edsm.arrival_display_seconds = min(
            600.0, max(0.0, float(self.edsm.arrival_display_seconds))
        )

        self.overlay.monitor = str(self.overlay.monitor).strip()

    def to_toml(self) -> str:
        lines: list[str] = [
            "# elite-hud configuration",
            "# Every key here is optional; delete a line to fall back to the default.",
            "",
        ]
        for section_name, section in (
            ("journal", self.journal),
            ("overlay", self.overlay),
            ("carrier", self.carrier),
            ("commander", self.commander),
            ("materials", self.materials),
            ("edsm", self.edsm),
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

        lines.append("# Override individual species payouts when Frontier rebalances them.")
        lines.append('# "Stratum Tectonicas" = 19010800')
        lines.append("")
        return "\n".join(lines)


VALID_POSITIONS = {"top-center", "top-left", "top-right", "bottom-center", "bottom-left", "bottom-right"}
VALID_SEGMENTS = {
    "carrier", "system", "balance", "cargo", "ship", "missions", "deliveries", "colony",
}

#: Human names for the segments, in the order they appear in a row. Used by the
#: tray menu so blocks can be hidden without editing the config by hand.
SEGMENT_NAMES: dict[str, str] = {
    "carrier": "Флотоносец",
    "system": "Система",
    "balance": "Баланс",
    "ship": "Корабль",
    "cargo": "Трюм",
    "missions": "Миссии",
    "deliveries": "Груз по миссиям",
    "colony": "Стройка колонии",
}
STATUS_SEGMENT_NAMES: dict[str, str] = {
    "next": "Цель прыжка",
    "carriers": "Флотоносцы",
    "mode": "Режим игры",
    "crime": "Розыск",
    "deliveries": "Груз по миссиям",
    "colony": "Стройка колонии",
}

#: Segments accepted in the bottom row. Ship and missions now default to the top
#: row but are still accepted here: each builder works in either row, and
#: refusing them would silently drop the segments of an existing config for no
#: good reason.
VALID_STATUS_SEGMENTS = {"next", "carriers", "mode", "crime", "deliveries", "colony"}
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
    """Rewrite ``[update] mode`` in place, preserving comments and layout."""
    if mode not in VALID_UPDATE_MODES:
        return False
    return set_config_value(path, "update", "mode", mode)


def _section_span(lines: list[str], section: str) -> tuple[str, int | None]:
    """Where a section lives in a config file.

    Returns ``(form, index)`` where form is ``"header"`` (declared as
    ``[section]``), ``"dotted"`` (declared only through ``section.key = value``
    lines) or ``"absent"``. ``index`` is the last line that belongs to the
    section, or None when it has no lines of its own.

    Both forms have to be told apart, because inserting a bare ``key = value``
    into a dotted-declared table would put it at the top level instead.
    """
    header = f"[{section}]"
    prefix = f"{section}."
    header_index: int | None = None
    dotted_index: int | None = None
    body_index: int | None = None
    inside = False
    for index, raw in enumerate(lines):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            inside = stripped[1:-1].strip() == section
            if inside and header_index is None:
                header_index = index
            continue
        if inside:
            body_index = index
        elif stripped.split("=", 1)[0].strip().startswith(prefix):
            dotted_index = index
    if header_index is not None:
        return "header", body_index if body_index is not None else header_index
    if dotted_index is not None:
        return "dotted", dotted_index
    return "absent", None


def _place_in_section(lines: list[str], section: str, key: str, value: Any) -> None:
    """Put a key into its own section, creating or extending it as needed.

    Appending to the end of the file instead put the key inside whichever table
    happened to be last -- here that is ``[exobiology.values]`` -- so the value
    was silently dropped while the caller was told the write had succeeded.
    Declaring the section again when it already had a header is worse still:
    TOML rejects a duplicate table, so from the next start onwards the whole
    file failed to parse and every setting silently reverted to its default.
    """
    form, index = _section_span(lines, section)
    if form == "header" and index is not None:
        lines.insert(index + 1, f"{key} = {_toml_value(value)}")
    elif form == "dotted" and index is not None:
        # The table lives as dotted keys, so the new key has to be dotted too.
        lines.insert(index + 1, f"{section}.{key} = {_toml_value(value)}")
    else:
        lines += ["", f"[{section}]", f"{key} = {_toml_value(value)}"]


def set_config_value(path: Path, section: str, key: str, value: str) -> bool:
    """Set one key in one section, in place, keeping comments and layout.

    Rewriting the whole file from ``to_toml`` would discard the comments a user
    added, so this edits the single line instead. Returns False when the file is
    missing or the edit could not be written.

    The value is rendered through :func:`_toml_value` rather than wrapped in
    quotes by hand. Doing it by hand meant a value containing a quotation mark or
    a backslash produced invalid TOML, and an unreadable config is not a
    cosmetic problem: ``Config.load`` falls back to *every* default, so one
    awkward character in one setting silently discards the whole file.
    """
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    rendered = f"{key} = {_toml_value(str(value))}"
    current_section = ""
    inserted = False
    for index, raw in enumerate(lines):
        stripped = raw.split("#", 1)[0].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            continue
        if current_section != section or not stripped:
            continue
        existing = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if existing == key:
            lines[index] = rendered
            inserted = True
            break

    if not inserted:
        _place_in_section(lines, section, key, str(value))

    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("cannot persist %s.%s: %s", section, key, exc)
        return False
    return True


def toggle_segment(
    current: list[str], order: list[str], value: str, enabled: bool
) -> list[str]:
    """Add or remove one segment, keeping the row in menu order.

    Append would put a re-enabled block at the end of the row, which reads as a
    different bar than the menu describes, so the result is always ordered by the
    menu's own vocabulary. Names the vocabulary does not know about are kept --
    a config written by a newer version should not lose its blocks to an older
    one -- and they go first, ahead of the ordered ones.
    """
    names = [name for name in current if name != value]
    if enabled:
        names.append(value)
    allowed = set(order)
    ordered = [name for name in order if name in set(names)]
    return [name for name in names if name not in allowed] + ordered


def set_config_list(path: Path, section: str, key: str, values: list[str]) -> bool:
    """Set one list-valued key in one section, in place.

    Kept separate from :func:`set_config_value` because that one quotes whatever
    it is given, which would turn a list into the string ``"[a, b]"``. Lists are
    written on a single line by ``to_toml``, so replacing the line is enough.
    Returns False when the file is missing or the edit could not be written.
    """
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    current_section = ""
    inserted = False
    for index, raw in enumerate(lines):
        stripped = raw.split("#", 1)[0].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            continue
        if current_section != section or not stripped:
            continue
        existing = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if existing == key:
            lines[index] = f"{key} = {_toml_value(list(values))}"
            inserted = True
            break

    if not inserted:
        _place_in_section(lines, section, key, list(values))

    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("cannot persist %s.%s: %s", section, key, exc)
        return False
    return True


def user_config_dir() -> Path:
    """The per-user configuration directory for this platform."""
    import sys  # noqa: PLC0415

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "elite-hud"


def is_writable_dir(path: Path) -> bool:
    """Whether a file can actually be created in ``path``.

    Probes by writing, rather than trusting ``os.access``: on Windows that call
    is unreliable for directories, and an install under ``Program Files`` looks
    writable to it while every real write is denied.
    """
    probe = path / ".elite-hud-write-test"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def resolve_config_path(explicit: "Path | None" = None) -> Path:
    """Where the configuration lives. The same answer on every launch.

    Two rules, in this order, and nothing else:

    1. An existing file always wins over a computed one. Wherever the settings
       are, they keep being used.
    2. A new file is created in the per-user directory -- ``%APPDATA%`` on
       Windows -- never beside the program.

    The second rule is what makes the settings survive an update. A file beside
    the program sits in the install directory, and an installer owns that
    directory: replacing it, or installing somewhere else next time, takes the
    settings with it. The per-user directory is not the installer's to touch, so
    updating cannot lose anything.

    What this replaced decided by whether the program's own directory was
    writable *at that moment*, which is not a stable property -- an installed
    copy normally runs unelevated and cannot write to ``Program Files``, but an
    elevated run can. The two runs then read and wrote two different files, and a
    panel switched on in one was gone in the next. An existing ``config.toml``
    beside the program is still honoured, because that is someone's deliberate
    portable setup, but being unable to *write* it no longer sends the program
    looking somewhere else: it reads the file it found and says it cannot save.
    """
    import sys  # noqa: PLC0415

    if explicit is not None:
        return explicit
    if not getattr(sys, "frozen", False):
        # Running from a source checkout.
        return Path(__file__).resolve().parent.parent / CONFIG_FILENAME

    executable_dir = Path(sys.executable).resolve().parent
    beside = executable_dir / CONFIG_FILENAME
    per_user = user_config_dir() / CONFIG_FILENAME

    if per_user.is_file():
        return per_user
    if beside.is_file():
        return beside
    return per_user


def config_is_writable(path: Path) -> bool:
    """Whether settings can actually be saved to ``path``.

    Checked before telling the commander a switch has been remembered: a
    read-only file means the panel reverts on the next launch, and saying
    nothing about that is how it goes unnoticed for days.
    """
    if not path.is_file():
        return is_writable_dir(path.parent)
    try:
        with open(path, "a", encoding="utf-8"):
            pass
    except OSError:
        return False
    return True


def _section_names(lines: list[str], text: str = "") -> set[str]:
    """Names of the tables a config file already declares.

    Parsing is preferred over scanning for ``[header]`` lines, because a table
    may also be declared with dotted keys (``overlay.monitor = "1"``) and a
    header may carry a trailing comment. Both fooled the line scanner, which
    then added a second declaration of a table the file already had: TOML
    rejects that outright, so from the next start onwards ``Config.load`` was
    returning every default and never recovered, because the repair path cannot
    run on a file that will not parse.
    """
    if text:
        try:
            parsed = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            found: set[str] = set()

            def walk(node: dict, prefix: str = "") -> None:
                for name, value in node.items():
                    path = f"{prefix}{name}"
                    if isinstance(value, dict):
                        found.add(path)
                        walk(value, path + ".")

            walk(parsed)
            return found

    # Fall back to scanning when the file does not parse, so a broken file can
    # still be reported on rather than silently treated as empty.
    found = set()
    for raw in lines:
        stripped = raw.split("#", 1)[0].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            found.add(stripped[1:-1].strip())
    return found


def add_missing_sections(path: Path, config: "Config | None" = None) -> list[str]:
    """Append sections the running version has but the file predates.

    A config file is written once and then left alone, so a version that adds a
    section leaves every existing file without it -- a commander opening the
    file to set the new option finds nothing to set. Only whole *sections* are
    added here, never individual keys: the file's own header promises that
    deleting a line falls back to the default, and re-adding keys would make
    that a lie.

    Comments and existing values are preserved. Returns the section names added.
    """
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    existing = _section_names(lines, "\n".join(lines))
    canonical = (config or Config()).to_toml().splitlines()

    # Group the canonical output by section, keeping order.
    order: list[str] = []
    bodies: dict[str, list[str]] = {}
    current = ""
    for line in canonical:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip()
            if current not in bodies:
                bodies[current] = []
                order.append(current)
            continue
        if current:
            bodies[current].append(line)

    # The label table is deliberately never written out. Labels are how
    # localisation will work, and a file holding a full set of one language's
    # wording would override the chosen language forever after.
    skip = {"overlay.labels"}

    added: list[str] = []
    for name in order:
        if name in existing or name in skip:
            continue
        lines.append("")
        lines.append(f"# added by a newer version of elite-hud")
        lines.append(f"[{name}]")
        lines.extend(bodies[name])
        added.append(name)

    if not added:
        return []
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("cannot add sections to %s: %s", path, exc)
        return []
    log.info("added config sections: %s", ", ".join(added))
    return added


def ensure_config_file(path: Path) -> bool:
    """Write a commented default config if none exists.

    Returns True when a file was created. Never raises: being unable to write a
    convenience file must not stop the HUD from starting.
    """
    try:
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(Config().to_toml(), encoding="utf-8")
    except OSError as exc:
        log.warning("cannot write a default config to %s: %s", path, exc)
        return False
    return True
