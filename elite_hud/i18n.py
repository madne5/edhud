"""Everything the program says to a commander, in one of the shipped languages.

Two tables, both with the same shape as the dataclasses they translate:
:class:`LabelConfig` for the bar and :class:`Messages` for the windows around it
(the tray menu, the balloons, the reasons a docking request was refused, the
update status lines, and the network failures those can produce).

**One source of truth per language.** Russian *is* the dataclass default, so it
needs no table of its own; English is an override table, and a test asserts that
table covers every field. A label added without an English word then fails the
suite instead of silently appearing in Russian to an English user.

**The language does not override a deliberate edit.** A key present in
``[overlay.labels]`` whose value is not one of the shipped words is a translation
someone wrote on purpose, and it wins over the chosen language. A key whose value
*is* a shipped word is a copy of our own default -- what an older version wrote
into every config file it created -- and is ignored, so that switching language
actually switches something. Without that rule, every config made by 0.11 and
earlier would pin the wording to Russian for ever.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields

from .config import LabelConfig

log = logging.getLogger(__name__)

#: Shipped languages, in the order the tray lists them.
LANGUAGES = ("ru", "en")

#: How each language names itself, which is not translated: a commander looking
#: for English is looking for the word "English".
LANGUAGE_NAMES = {"ru": "Русский", "en": "English"}

DEFAULT_LANGUAGE = "ru"


@dataclass
class Messages:
    """The strings around the bar. Russian is the default, as everywhere else."""

    # -- tray menu ---------------------------------------------------------
    show_hide: str = "Показать / скрыть HUD"
    open_config: str = "Открыть config.toml"
    top_row: str = "Верхняя строка"
    bottom_row: str = "Нижняя строка"
    monitor: str = "Монитор"
    language: str = "Язык"
    quit: str = "Выход"

    # -- tray entries and balloons ----------------------------------------
    config_writable: str = "config: {path}"
    config_read_only: str = "config: НЕ ЗАПИСЫВАЕТСЯ — {path}"
    not_saved: str = "{what}: не сохранилось в {path}; после перезапуска вернётся как было"
    hud_on_monitor: str = "HUD на мониторе: {where}"
    already_running: str = (
        "elite-hud уже запущен (второй экземпляр не нужен); "
        "используйте --force, чтобы обойти проверку"
    )

    # -- display picker ----------------------------------------------------
    #: A display the bar can be put on. "нет данных" is also the answer when no
    #: display can be enumerated at all.
    screen_none: str = "нет данных"
    screen_primary: str = "Основной"
    screen_primary_mark: str = " — основной"
    screen_under_cursor: str = "Тот, где курсор мыши"

    # -- notices -----------------------------------------------------------
    docking_denied: str = "{where}: стыковка запрещена — {why}"
    docking_nowhere: str = "станция"
    docking_reason_unknown: str = "причина не указана"
    #: The game's own reasons, translated where the meaning is unambiguous. A
    #: reason not in this table is quoted as it stands rather than guessed at.
    docking_reasons: dict[str, str] = field(
        default_factory=lambda: {
            "Distance": "слишком далеко от станции",
            "NoSpace": "все площадки заняты",
            "TooLarge": "корабль слишком большой для площадки",
            "Hostile": "станция враждебна",
            "Offline": "стыковка отключена",
            "ActiveFighter": "сначала верните истребитель на борт",
        }
    )

    # -- update checks -----------------------------------------------------
    update_checking: str = "проверка обновлений…"
    update_already_checking: str = "проверка обновлений уже идёт…"
    update_check_failed: str = "ошибка проверки обновлений: {error}"
    update_current: str = "установлена последняя версия ({version})"
    update_available: str = "доступна версия {version}"
    update_available_source: str = (
        "доступна версия {version}; запущено из исходников — обновление вручную"
    )
    update_nothing: str = "нет доступного обновления"
    update_busy: str = "обновление уже загружается, подождите…"
    update_busy_start: str = "не удалось начать загрузку: другая задача не завершилась"
    update_downloading: str = "загрузка обновления {version}…"
    update_download_failed: str = "не удалось скачать обновление: {error}"
    update_staged: str = (
        "обновление {version} загружено и будет установлено при следующем запуске"
    )
    update_check_now: str = "Проверить обновления"
    update_none_found: str = "Обновление не найдено"
    update_install_action: str = "Установить {version}"
    update_mode: str = "Режим обновлений"
    update_mode_install: str = "Скачивать и устанавливать"
    update_mode_download: str = "Ставить при следующем запуске"
    update_mode_notify: str = "Только уведомлять"
    update_mode_off: str = "Выключено"
    release_notes: str = "Заметки о выпуске"
    update_installing: str = "установка версии {version}…"
    update_installed: str = "обновление установлено, перезапуск…"
    update_install_failed: str = "не удалось установить обновление: {error}"

    # -- network failures, as the tray has to show them --------------------
    net_repo_missing: str = "репозиторий {repo} не найден или релизов ещё нет"
    net_rate_limited: str = "исчерпан лимит запросов к GitHub API, попробуйте позже"
    net_token_rejected: str = "GitHub отклонил запрос ({code}); проверьте токен доступа"
    net_http_error: str = "GitHub ответил ошибкой {code}"
    net_tls_failed: str = "не удалось проверить сертификат GitHub (системное время и сертификаты)"
    net_no_connection: str = "нет связи с GitHub: {error}"
    net_timeout: str = "GitHub не ответил вовремя"
    net_not_json: str = "GitHub вернул не JSON — возможно, запрос перехвачен прокси"
    net_unexpected: str = "неожиданный ответ GitHub API"
    net_download_http: str = "не удалось скачать {name} (HTTP {code})"
    net_bad_url: str = "GitHub вернул некорректный адрес файла: {url}"
    net_download_failed: str = "не удалось скачать обновление (HTTP {code})"
    net_unsafe_archive: str = "архив содержит небезопасный путь: {name}"
    net_windows_only: str = "установка обновления поддерживается только в Windows"
    net_installer_failed: str = "не удалось запустить установщик (отклонён запрос прав?)"
    net_source_checkout: str = (
        "обновление на месте недоступно при запуске из исходников: "
        "sys.executable — это интерпретатор, а не HUD"
    )
    net_already_staged: str = "новая версия уже распакована в целевую папку"
    net_repo_unset: str = "не задан репозиторий обновлений (update.repo)"
    net_no_releases: str = "обновлений нет"
    net_no_asset: str = (
        "в релизе {tag} нет подходящего файла для этого способа установки"
    )
    net_checksum_mismatch: str = (
        "контрольная сумма скачанного файла не совпала — загрузка отменена"
    )


#: English wording for every label in :class:`LabelConfig`. Russian is the
#: dataclass default, so it is deliberately absent here.
ENGLISH_LABELS: dict[str, str] = {
    "carrier": "FC",
    "carrier_cooldown": "ready in",
    "carrier_ready": "ready",
    "mode_open": "OPEN PLAY",
    "mode_solo": "SOLO",
    "mode_group": "PRIVATE GROUP",
    "missions": "missions",
    "jump_max": "max",
    "jump_current": "cur",
    "bodies": "bodies",
    "waiting": "waiting for the journal",
    "balance": "balance",
    "notoriety": "notoriety",
    "fines": "fine",
    "tonnes": "t",
    "carrier_cargo": "cargo",
    "carrier_reserved": "reserved",
    "jump_next": "next",
    "rarity": "rarity",
    "total": "total",
    "material_raw": "Raw",
    "material_manufactured": "Manufactured",
    "material_encoded": "Encoded",
    "jumps": "jumps",
    "deliveries_collect": "collect",
    "deliveries_deliver": "deliver",
    "edsm_discovered": "discovered",
    "edsm_fuel": "fuel",
    "edsm_yes": "yes",
    "edsm_no": "no",
    "edsm_traffic": "traffic",
    "edsm_traffic_none": "none",
    "edsm_day": "day",
    "edsm_week": "week",
    "edsm_total": "total",
    "edsm_unknown": "no data in EDSM — possibly unvisited",
}

#: English wording for everything in :class:`Messages`.
ENGLISH_MESSAGES: dict[str, object] = {
    "show_hide": "Show / hide HUD",
    "open_config": "Open config.toml",
    "top_row": "Top row",
    "bottom_row": "Bottom row",
    "monitor": "Monitor",
    "language": "Language",
    "quit": "Quit",
    "config_writable": "config: {path}",
    "config_read_only": "config: NOT WRITABLE — {path}",
    "not_saved": "{what}: not saved to {path}; it will revert after a restart",
    "hud_on_monitor": "HUD on monitor: {where}",
    "already_running": (
        "elite-hud is already running (a second instance is pointless); "
        "use --force to skip the check"
    ),
    "screen_none": "no data",
    "screen_primary": "Primary",
    "screen_primary_mark": " — primary",
    "screen_under_cursor": "The one under the cursor",
    "docking_denied": "{where}: docking refused — {why}",
    "docking_nowhere": "station",
    "docking_reason_unknown": "reason not given",
    "docking_reasons": {
        "Distance": "too far from the station",
        "NoSpace": "every landing pad is taken",
        "TooLarge": "the ship is too large for the pad",
        "Hostile": "the station is hostile",
        "Offline": "docking is offline",
        "ActiveFighter": "recall your fighter first",
    },
    "update_check_now": "Check for updates",
    "update_none_found": "No update found",
    "update_install_action": "Install {version}",
    "update_mode": "Update mode",
    "update_mode_install": "Download and install",
    "update_mode_download": "Install on the next start",
    "update_mode_notify": "Notify only",
    "update_mode_off": "Off",
    "release_notes": "Release notes",
    "update_checking": "checking for updates…",
    "update_already_checking": "an update check is already running…",
    "update_check_failed": "update check failed: {error}",
    "update_current": "the latest version is installed ({version})",
    "update_available": "version {version} is available",
    "update_available_source": (
        "version {version} is available; running from a checkout — update by hand"
    ),
    "update_nothing": "no update is available",
    "update_busy": "an update is already downloading, please wait…",
    "update_busy_start": "could not start the download: another job has not finished",
    "update_downloading": "downloading {version}…",
    "update_download_failed": "could not download the update: {error}",
    "update_staged": "{version} has been downloaded and will install on the next start",
    "update_installing": "installing {version}…",
    "update_installed": "update installed, restarting…",
    "update_install_failed": "could not install the update: {error}",
    "net_repo_missing": "repository {repo} was not found, or has no releases yet",
    "net_rate_limited": "the GitHub API rate limit is exhausted, try again later",
    "net_token_rejected": "GitHub rejected the request ({code}); check the access token",
    "net_http_error": "GitHub answered with error {code}",
    "net_tls_failed": "the GitHub certificate could not be verified (clock and trust store)",
    "net_no_connection": "no connection to GitHub: {error}",
    "net_timeout": "GitHub did not answer in time",
    "net_not_json": "GitHub returned something that is not JSON — a proxy, perhaps",
    "net_unexpected": "unexpected answer from the GitHub API",
    "net_download_http": "could not download {name} (HTTP {code})",
    "net_bad_url": "GitHub returned an unusable file address: {url}",
    "net_download_failed": "could not download the update (HTTP {code})",
    "net_unsafe_archive": "the archive contains an unsafe path: {name}",
    "net_windows_only": "installing an update is supported on Windows only",
    "net_installer_failed": "the installer could not be started (was elevation refused?)",
    "net_source_checkout": (
        "an in-place update is not possible from a source checkout: "
        "sys.executable is an interpreter, not the HUD"
    ),
    "net_already_staged": "the new version is already unpacked into the target folder",
    "net_repo_unset": "no update repository is configured (update.repo)",
    "net_no_releases": "no updates",
    "net_no_asset": "release {tag} has no file suitable for this install",
    "net_checksum_mismatch": "the downloaded file's checksum did not match — cancelled",
}


def normalise(language: str) -> str:
    """A shipped language, falling back to Russian with a word about it."""
    key = (language or "").strip().casefold()
    if key in LANGUAGES:
        return key
    if key:
        log.warning("unknown overlay.language %r, using %s", language, DEFAULT_LANGUAGE)
    return DEFAULT_LANGUAGE


def labels(language: str) -> LabelConfig:
    """The label table for a language, before any hand-written overrides."""
    if normalise(language) == "en":
        return LabelConfig(**ENGLISH_LABELS)
    return LabelConfig()


def messages(language: str) -> Messages:
    """The window strings for a language."""
    if normalise(language) == "en":
        return Messages(**ENGLISH_MESSAGES)  # type: ignore[arg-type]
    return Messages()


def all_label_values() -> set[str]:
    """Every word we ship for any label, in any language.

    Used to tell a translation someone wrote from a copy of our own default: a
    value in this set is ours, not theirs.
    """
    values = {getattr(LabelConfig(), f.name) for f in fields(LabelConfig)}
    values.update(ENGLISH_LABELS.values())
    return values


def resolve_labels(language: str, overrides: dict | None = None) -> LabelConfig:
    """The labels to use: the language's, then anything written on purpose.

    An override is honoured when it is not one of our own words, so a commander
    who translated a label keeps it while everybody else gets their language.
    """
    table = labels(language)
    shipped = all_label_values()
    for key, value in (overrides or {}).items():
        text = str(value).strip() if isinstance(value, str) else ""
        if not text or text in shipped:
            continue
        if hasattr(table, key):
            setattr(table, key, text)
        else:
            log.warning("ignoring unknown overlay.labels key %r", key)
    return table
