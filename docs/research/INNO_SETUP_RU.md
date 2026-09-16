# Inno Setup для Windows-инсталлятора Python/PySide6-приложения

Отчёт по официальным источникам. Все утверждения подкреплены ссылкой; всё, что не удалось
подтвердить в разрешённых источниках, помечено **«не подтверждено»**.

## 0. Источники, версии, методика

| Что | Где |
|---|---|
| Официальная справка Inno Setup | https://jrsoftware.org/ishelp/ — страницы вида `topic_<topic>.htm` |
| Исходники справки + код | https://github.com/jrsoftware/issrc |
| История версий | https://github.com/jrsoftware/issrc/blob/main/whatsnew.htm |
| Образы GitHub Actions | https://github.com/actions/runner-images |

Текст справки я брал не из HTML-обёртки (сайт отдаёт фреймсет), а из первоисточника, из
которого генерируется https://jrsoftware.org/ishelp/ — `ISHelp/isetup.xml` в репозитории.
Цитаты семантики и значения по умолчанию сверены с тегом релиза `is-7_1_0` и `is-6_7_3`.

**Версии (важно для совместимости):**

* Актуальный стабильный релиз — **Inno Setup 7.1.0** (GitHub Releases, 2026-08-12):
  https://github.com/jrsoftware/issrc/releases
* **GitHub-hosted Windows runners содержат InnoSetup 6.7.1**
  (`actions/runner-images`, `images/windows/Windows2025-Readme.md` и `Windows2022-Readme.md`,
  строка «InnoSetup 6.7.1»), ставится через Chocolatey-пакет `innosetup`
  (`images/windows/toolsets/toolset-2025.json`, `choco.common_packages`).
  Точный путь установки на раннере в этих источниках не указан → **не подтверждено**
  (не полагайтесь на `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` без проверки).
* Следствие: **не используйте `SetupArchitecture`** (директива появилась только в Inno Setup 7,
  см. whatsnew) если сборка идёт на GitHub-раннере с 6.7.1.

---

## 1. Минимальный рабочий `.iss` и семантика директив `[Setup]`

### 1.1 Минимальный (но компилируемый) скрипт

Файлы, которые должны лежать рядом со скриптом: `dist\EliteHud.exe` (сборка PyInstaller),
`app.ico`, `license.txt`.

```ini
[Setup]
AppId={{8F1C2A54-7B3E-4C19-9E2D-4A6B0C7D5E31}
AppName=Elite HUD
AppVersion=1.2.0
AppPublisher=Elite HUD
DefaultDirName={autopf}\Elite HUD
DefaultGroupName=Elite HUD
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex=EliteHud.SingleInstance.v1
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\EliteHud.exe
OutputDir=dist
OutputBaseFilename=EliteHud-Setup-1.2.0
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app.ico
LicenseFile=license.txt
CreateUninstallRegKey=yes

[Tasks]
Name: "startupicon"; Description: "Автозапуск при входе в Windows"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "dist\EliteHud.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Elite HUD"; Filename: "{app}\EliteHud.exe"; WorkingDir: "{app}"
Name: "{group}\Удалить Elite HUD"; Filename: "{uninstallexe}"
Name: "{autostartup}\Elite HUD"; Filename: "{app}\EliteHud.exe"; WorkingDir: "{app}"; Tasks: startupicon

[Run]
Filename: "{app}\EliteHud.exe"; Description: "Запустить Elite HUD"; Flags: nowait postinstall skipifsilent runasoriginaluser
Filename: "{app}\EliteHud.exe"; Flags: nowait skipifnotsilent runasoriginaluser
```

Полная версия — в §8.

### 1.2 Разбор директив

Ссылки — на соответствующие страницы https://jrsoftware.org/ishelp/.

| Директива | Допустимые значения | По умолчанию | Семантика (цитата/пересказ справки) |
|---|---|---|---|
| `AppId` | любая строка, до 127 символов после раскрытия констант; может содержать константы | `AppName` | «The value of `AppId` is stored inside uninstall log files (unins???.dat), and is checked by subsequent installations to determine whether it may append to a particular existing uninstall log.» Также: «`AppId` also determines the actual name of the Uninstall registry key, to which Inno Setup tacks on "`_is1`" at the end.» Не отображается пользователю. ([topic_setup_appid](https://jrsoftware.org/ishelp/topic_setup_appid.htm)) |
| `AppName` | строка, может содержать константы | — (обязательна) | «This **required** directive specifies the name of the application being installed. Do not include the version number». Отображается в заголовках Setup/деинсталлятора. Также значение по умолчанию для `AppId`, `VersionInfoDescription`, `VersionInfoProductName`. ([topic_setup_appname](https://jrsoftware.org/ishelp/topic_setup_appname.htm)) |
| `AppVersion` | строка, может содержать константы | — (обязательна, если не задан `AppVerName`) | «This directive specifies the version number… is displayed in the Version field of the application's *Add/Remove Programs* entry. It is also used to set the `MajorVersion` and `MinorVersion` values in the Uninstall registry key when possible.» ([topic_setup_appversion](https://jrsoftware.org/ishelp/topic_setup_appversion.htm)) |
| `AppPublisher` | строка, может содержать константы | пусто | «This string is displayed on the "Support" dialog of the *Add/Remove Programs* Control Panel applet.» Также значение по умолчанию для `VersionInfoCompany`. ([topic_setup_apppublisher](https://jrsoftware.org/ishelp/topic_setup_apppublisher.htm)) |
| `DefaultDirName` | путь, обычно с константой-каталогом | — (обязательна) | «The value of this **required** directive is used for the default directory name, which is used in the *Select Destination Location* page». Пример из справки: `DefaultDirName={autopf}\My Program` → обычно `C:\Program Files\My Program`. «If `UsePreviousAppDir` is `yes` (the default) and Setup finds a previous version of the same application is already installed, it will substitute the default directory name with the directory selected previously.» ([topic_setup_defaultdirname](https://jrsoftware.org/ishelp/topic_setup_defaultdirname.htm)) |
| `PrivilegesRequired` | `admin` или `lowest` | `admin` | См. §2. ([topic_setup_privilegesrequired](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)) |
| `PrivilegesRequiredOverridesAllowed` | одно или оба, через пробел: `commandline`, `dialog` | пусто | См. §2. ([topic_setup_privilegesrequiredoverridesallowed](https://jrsoftware.org/ishelp/topic_setup_privilegesrequiredoverridesallowed.htm)) |
| `CloseApplications` | `force`, `yes`, `no` | `yes` | «If set to `yes` or `force` and Setup is not running silently, Setup will pause on the *Preparing to Install* wizard page if it detects applications using files that need to be updated… If set to `yes` or `force` and Setup is running silently, Setup will always close and restart such applications, unless told not to via the command line.» «**Note:** Setup uses Windows Restart Manager to detect, close, and restart applications.» ([topic_setup_closeapplications](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm)) |
| `RestartApplications` | `yes`, `no` | `yes` | «When set to `yes` and `CloseApplications` is also set to `yes` or `force`, Setup restarts the closed applications after the installation has completed.» «**Note:** … the application needs to be using the Windows `RegisterApplicationRestart` API function.» ([topic_setup_restartapplications](https://jrsoftware.org/ishelp/topic_setup_restartapplications.htm)) |
| `UninstallDisplayIcon` | путь к `.exe`/`.ico`, опционально `,индекс` (0-based) | пусто | «This lets you specify a particular icon file… to display for the Uninstall entry in the *Add/Remove Programs* Control Panel applet.» Пример: `UninstallDisplayIcon={app}\MyProg.exe,1`. ([topic_setup_uninstalldisplayicon](https://jrsoftware.org/ishelp/topic_setup_uninstalldisplayicon.htm)) |
| `OutputBaseFilename` | имя файла без пути и расширения | `mysetup` | «allows you to assign a different name for the resulting Setup file(s)». «Setting this to `setup` is not recommended: all executables named `setup.exe` are shimmed by Windows application compatibility to load additional DLLs, such as `version.dll`. These DLLs are loaded unsafely by Windows and can be hijacked.» ([topic_setup_outputbasefilename](https://jrsoftware.org/ishelp/topic_setup_outputbasefilename.htm)) |
| `Compression` | `zip`, `zip/1`…`zip/9`, `bzip`, `bzip/1`…`bzip/9`, `lzma`, `lzma/fast\|normal\|max\|ultra\|ultra64`, `lzma2` (+ те же уровни), `none` | **`lzma2/max`** | «This specifies the method of compression to use on the files, and optionally the level of compression.» Для `lzma`/`lzma2`: «If a compression level isn't specified, it defaults to `max`.» Требования к памяти для `max` — словарь 8 МБ при распаковке, ≈98 МБ при сжатии. ([topic_setup_compression](https://jrsoftware.org/ishelp/topic_setup_compression.htm)) |
| `WizardStyle` | одно или более через пробел: базовые `classic`, `modern`; режимы `light`, `dark`, `dynamic`; стили `polar`, `slate`, `stellar`, `windows11`, `zircon`; модификаторы `excludelightbuttons`, `excludelightcontrols`, `hidebevels`, `includetitlebar` | `classic` | «This directive controls the visual style and appearance of Setup and Uninstall.» `dark`/`dynamic` требуют Inno Setup 6.6+ ([isdl.php](https://jrsoftware.org/isdl.php): «6.6: Added support for dark mode and custom styles to Setup and Uninstall»). ([topic_setup_wizardstyle](https://jrsoftware.org/ishelp/topic_setup_wizardstyle.htm)) |
| `SetupIconFile` | путь к `.ico` (или `compiler:...`) | пусто | «Specifies a custom program icon to use for Setup/Uninstall.» «It is recommended to include at least the following sizes in your icon: 16x16, 32x32, 48x48, 64x64, and 256x256.» ([topic_setup_setupiconfile](https://jrsoftware.org/ishelp/topic_setup_setupiconfile.htm)) |
| `LicenseFile` | путь к `.txt` (UTF-8/UTF-16LE) или `.rtf` | пусто | «Specifies the name of an optional license agreement file… which is displayed before the user selects the destination directory for the program.» ([topic_setup_licensefile](https://jrsoftware.org/ishelp/topic_setup_licensefile.htm)) |
| `AppMutex` | одно или более имён мьютексов через запятую; может содержать константы | пусто | См. §4. ([topic_setup_appmutex](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm)) |
| `ArchitecturesInstallIn64BitMode` | список идентификаторов архитектур или булево выражение | 32-битный Setup: пусто; 64-битный Setup: `x64compatible` | «Specifies the architectures on which Setup should enable 64-bit install mode. If this directive is set to a blank value, Setup will always use 32-bit install mode.» «If the expression does indeed match a system running 32-bit Windows, Setup will display an error message and exit.» Пример справки — задавать вместе с `ArchitecturesAllowed`. ([topic_setup_architecturesinstallin64bitmode](https://jrsoftware.org/ishelp/topic_setup_architecturesinstallin64bitmode.htm)) |
| `OutputDir` | путь (относительный — от `SourceDir`, либо `userdocs:...`) | `Output` | «Specifies the "output" directory for the script, which is where the compiler will place the resulting `Setup.*` files.» `OutputDir=.` кладёт файлы в каталог исходников. ([topic_setup_outputdir](https://jrsoftware.org/ishelp/topic_setup_outputdir.htm)) |
| `CreateUninstallRegKey` | `yes`, `no` или скриптовое булево выражение | `yes` | «If this is set to `no`…, Setup won't create an entry in the *Add/Remove Programs* Control Panel applet.» ([topic_setup_createuninstallregkey](https://jrsoftware.org/ishelp/topic_setup_createuninstallregkey.htm)) |

Дополнительно использованы (кратко): `DefaultGroupName`, `AllowNoIcons`, `DisableProgramGroupPage`
(default `auto`), `SolidCompression`, `UsePreviousAppDir` (`yes`), `UsePreviousTasks` (`yes`),
`RestartIfNeededByRun` (см. §4).

**Пояснение к `AppId={{...}`:** в справке по константам — «A `{` character is treated as the start
of the constant. If you want to use that actual character in a place where constants are
supported, you must use two consecutive `{` characters.» Поэтому `{{GUID}` даёт буквальный
`{GUID}`. ([topic_consts](https://jrsoftware.org/ishelp/topic_consts.htm))

**Про `[Icons]`:** у `[Icons]` нет флагов `unchecked` и `runascurrentuser` — см. §5.

---

## 2. Per-user установка без прав администратора

### 2.1 `PrivilegesRequired`

| Значение | Смысл |
|---|---|
| `admin` (**по умолчанию**) | «Setup will always run with administrative privileges and in administrative install mode. If Setup was started by an unprivileged user, Windows will ask for the password to an account that has administrative privileges, and Setup will then run under that account.» |
| `lowest` | «Setup will not request to be run with administrative privileges even if it was started by a member of the Administrators group and will always run in non administrative install mode. Do not use this setting unless you are sure your installation will run successfully on unprivileged accounts.» |

Источник: [topic_setup_privilegesrequired](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)

**Про `poweruser`:** значения `poweruser` в Inno Setup 6/7 **больше нет** — в справке версии 7.1.0
и 6.7.3 указано только `admin` или `lowest`. В справке Inno Setup 5.5.9
(`is-5_5_9/ISHelp/isetup.xml`) было: «Valid values: `poweruser`, `admin`, or `lowest`».
Момент удаления `poweruser` в `whatsnew.htm` явно не описан → **не подтверждено** (факт наличия
в 5.5.9 и отсутствия в 6.7.3/7.1.0 подтверждён).

### 2.2 `PrivilegesRequiredOverridesAllowed`

* Допустимые значения: `commandline` и/или `dialog`, «separated by spaces». По умолчанию — пусто.
* `commandline`: «then Setup will support two additional command-line parameters to override the
  script's default `PrivilegesRequired` setting: `/ALLUSERS` and `/CURRENTUSER`.»
* `dialog`: «then Setup will ask the user to choose the install mode based on the script's default
  `PrivilegesRequired` setting using a suppressible dialog. **Allowing `dialog` automatically allows
  `commandline`** and when one of the command-line parameters is used then Setup will not ask the user.»

Источник: [topic_setup_privilegesrequiredoverridesallowed](https://jrsoftware.org/ishelp/topic_setup_privilegesrequiredoverridesallowed.htm)

**Версия:** `PrivilegesRequiredOverridesAllowed` появилась в **Inno Setup 6.0.0-beta (2019-02-11)**.
Цитата из `whatsnew.htm` (тег `is-6_0_0`, раздел «Overridable install mode»): «Added new [Setup]
section directive: `PrivilegesRequiredOverridesAllowed`, which can be set to one or more overrides
which allow the end user to override the script's default `PrivilegesRequired` setting.»
Также там же: «Added new [Setup] section directive: `UsePreviousPrivileges`.»
https://github.com/jrsoftware/issrc/blob/main/whatsnew.htm

**Диалог «Select Setup Install Mode»** — точные строки из `Files/Default.isl`
(https://github.com/jrsoftware/issrc/blob/main/Files/Default.isl, строки 95–102):

```
PrivilegesRequiredOverrideTitle=Select Setup Install Mode
PrivilegesRequiredOverrideInstruction=Select install mode
PrivilegesRequiredOverrideText1=%1 can be installed for all users (requires administrative privileges), or for you only.
PrivilegesRequiredOverrideText2=%1 can be installed for you only, or for all users (requires administrative privileges).
PrivilegesRequiredOverrideAllUsers=Install for &all users
PrivilegesRequiredOverrideAllUsersRecommended=Install for &all users (recommended)
PrivilegesRequiredOverrideCurrentUser=Install for &me only
PrivilegesRequiredOverrideCurrentUserRecommended=Install for &me only (recommended)
```

`UsePreviousPrivileges` (по умолчанию `yes`): «at startup Setup will look in the registry to see if
the same application is already installed in one of the two install modes, and if so, it will use
that install mode and not ask the user. … `UsePreviousPrivileges` must be set to `no` when `AppId`
includes constants and `PrivilegesRequiredOverridesAllowed` allows `dialog`.»
([topic_setup_usepreviousprivileges](https://jrsoftware.org/ishelp/topic_setup_usepreviousprivileges.htm))

**Что именно считается «AppId includes constants».** Проверка в компиляторе —
`Compiler.SetupCompiler.pas:8415`: `AppIdHasConsts := CheckConst(SetupHeader.AppId, ...)`,
а `CheckConst` (там же, ~1826) трактует **двойную** скобку как escape, а не как константу:

```pascal
if S[I] = '{' then begin
  if (I < Length(S)) and (S[I+1] = '{') then
    Inc(I)            { "{{" — это escape одного "{", НЕ константа }
  else begin
    Result := True;   { настоящая константа }
```

Нарушение — **ошибка компиляции**, а не предупреждение
(`Compiler.SetupCompiler.pas:8421–8425`: `AbortCompile(SCompilerMustNotUsePreviousPrivileges)`;
текст — `Compiler.Messages.pas:107`).

Практический вывод:

| `AppId` | `AppIdHasConsts` | При `PrivilegesRequiredOverridesAllowed=dialog` |
|---|---|---|
| `AppId={{8F1C2A54-...}` (литеральный `{GUID}` через `{{`) | `False` | `UsePreviousPrivileges` можно оставить `yes` (**рекомендуется**) |
| `AppId={#MyAppId}` / `AppId={code:GetAppId}` / `AppId={%ENV}` — реальная константа | `True` | `UsePreviousPrivileges=no` **обязателен** |
| `AppId=EliteHud` | `False` | `UsePreviousPrivileges` можно оставить `yes` |

Поэтому в примерах этого отчёта (`AppId={{GUID}`) `UsePreviousPrivileges=no` **не нужен** —
наоборот, полезно сохранить значение по умолчанию `yes`, чтобы обновление автоматически
использовало тот же режим установки, что и раньше.

### 2.3 Константы каталогов: `{autopf}`, `{userpf}`, `{commonpf}`, `{localappdata}`, `{autoprograms}`

Таблица «auto-констант» из справки ([topic_consts](https://jrsoftware.org/ishelp/topic_consts.htm)):

| Auto | Administrative install mode | Non administrative install mode |
|---|---|---|
| `{autopf}` | `{commonpf}` | `{userpf}` |
| `{autopf32}` | `{commonpf32}` | `{userpf}` |
| `{autopf64}` | `{commonpf64}` | `{userpf}` |
| `{autoprograms}` | `{commonprograms}` | `{userprograms}` |
| `{autostartup}` | `{commonstartup}` | `{userstartup}` |
| `{autodesktop}` | `{commondesktop}` | `{userdesktop}` |
| `{autoappdata}` | `{commonappdata}` | `{userappdata}` |

Цитата: «Besides the "common" and "user" constants, Inno Setup also supports "auto" constants.
These automatically map to their "common" form unless the installation is running in non
administrative install mode, in which case they map to their "user" form. It is recommended you
always use these "auto" constants when possible to avoid mistakes.»

Прочие нужные константы (там же):

* `{localappdata}` — «The path to the current user's local (non-roaming) Application Data folder.»
  Это «shell folder constant», **без** auto-формы.
* `{userpf}` — «The path to the current user's Program Files folder. Only Windows 7 and later
  supports `{userpf}`; if used on previous Windows versions, it will translate to the same directory
  as `{localappdata}\Programs`.»
* `{commonpf}` — Program Files (раньше называлась `{pf}`; переименование в Inno Setup 6).

**Версия:** auto-константы появились в **Inno Setup 6.0.0-beta**. Цитата из `whatsnew.htm`
(тег `is-6_0_0`): «Added new "auto" constants which automatically map to their "common" form unless
the installation is running in non administrative install mode… The list of added "auto" constants
is: {autoappdata}, {autocf}, {autocf32}, {autocf64}, {autodesktop}, {autodocs}, {autopf},
{autopf32}, {autopf64}, {autoprograms}, {autostartmenu}, {autostartup}, and {autotemplates}.»
Там же: «The `{pf}` and `{cf}` constants have been renamed to `{commonpf}` and `{commoncf}`.»

### 2.4 Как `DefaultDirName` взаимодействует с константами

* `DefaultDirName={autopf}\Elite HUD` — правильный «универсальный» вариант: при per-machine
  установке получится `C:\Program Files\Elite HUD`, при per-user — `%LOCALAPPDATA%\Programs\Elite HUD`
  (через `{userpf}`).
* `DefaultDirName={localappdata}\Elite HUD` — всегда per-user, независимо от режима. Компилятор
  выдаст предупреждение `UsedUserAreasWarning` (см. ниже).
* `DefaultDirName={userpf}\Elite HUD` — то же самое, тоже предупреждение.
* Если задан `UsePreviousAppDir=yes` (по умолчанию) и приложение уже установлено с тем же `AppId`,
  выбранный ранее каталог подставляется вместо `DefaultDirName`.

### 2.5 Предупреждение `UsedUserAreasWarning` — точный список констант

Из исходников компилятора, `Projects/Src/Compiler.SetupCompiler.pas` (строки 1798–1816):

```pascal
UserConsts: array[0..0] of String = ('username');
UserShellFolderConsts: array[0..13] of String = (
  'userdesktop', 'userstartmenu', 'userprograms', 'userstartup',
  'userappdata', 'userdocs', 'usertemplates', 'userfavorites', 'usersendto', 'userfonts',
  'localappdata', 'userpf', 'usercf', 'usersavedgames');
ShellFolderConsts: array[0..16] of String = (
  'group', 'commondesktop', 'commonstartmenu', 'commonprograms', 'commonstartup',
  'commonappdata', 'commondocs', 'commontemplates',
  'autodesktop', 'autostartmenu', 'autoprograms', 'autostartup',
  'autoappdata', 'autodocs', 'autotemplates', 'autofavorites', 'autofonts');
```

Что это значит на практике:

* `{localappdata}`, `{userpf}`, `{userstartup}`, `{userprograms}`, `{userdesktop}` и т. п.
  **попадают в список «per-user areas»** и вызывают предупреждение компилятора при
  `PrivilegesRequired=admin`.
* `{autopf}`, `{autoprograms}`, `{autostartup}`, `{autodesktop}` и все `common*` — **не попадают**,
  предупреждения нет.
* Также в список добавляются `HKCU` (в `[Registry]`) и `AlwaysUsePersonalGroup`
  (`Compiler.SetupCompiler.pas:4701`, `:8579`).
* Текст предупреждения (`Compiler.Messages.pas:175`): «The [%s] section directive "%s" is set to
  "%s" but per-user areas (%s) are used by the script. Regardless of the version of Windows, if the
  installation is running in administrative install mode then you should be careful about making any
  per-user area changes: such changes may not achieve what you are intending.»
* Отключается директивой `UsedUserAreasWarning=no`.

Источник: [topic_admininstallmode](https://jrsoftware.org/ishelp/topic_admininstallmode.htm),
[topic_setup_useduserareaswarning](https://jrsoftware.org/ishelp/topic_setup_useduserareaswarning.htm).

### 2.6 Корень реестра: HKCU vs HKLM

Цитата из [topic_admininstallmode](https://jrsoftware.org/ishelp/topic_admininstallmode.htm):

> In administrative install mode: … The `HKA`, uninstall info, and font install root keys will be
> `HKEY_LOCAL_MACHINE`.
> In non administrative install mode: … The `HKA`, uninstall info, and font install root keys will be
> `HKEY_CURRENT_USER`.

Подтверждено кодом, `Projects/Src/Setup.MainFunc.pas:2715–2723`:

```pascal
const
  RootKeys: array[Boolean] of HKEY = (HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE);
begin
  IsAdminInstallMode := AAdminInstallMode;
  InstallModeRootKey := RootKeys[AAdminInstallMode];
```

и `Setup.MainFunc.pas:3569`: `InitializeAdminInstallMode(IsAdmin and (SetupHeader.PrivilegesRequired <> prLowest));`

**Итог:** per-user установка → ключ деинсталляции в `HKCU`; per-machine → в `HKLM`.
Соответственно `UninstallString`/`QuietUninstallString` ведут на `unins000.exe` внутри `{app}`.

**Побочный эффект (из whatsnew 6.0):** «Two separate installation runs that do not share the same
administrative or non administrative install mode no longer count as the same application… you can
now install these modes side-by-side even if the installers share the same `AppId`». И: «To avoid
entries with identical names in the Add/Remove Programs Control Panel applet Setup will now
automatically mark the new entry with a text like "Current user" or "64-bit"». Точные строки из
`Files/Default.isl` (строки 384–390): `UninstallDisplayNameMark=%1 (%2)`, `UninstallDisplayNameMarkAllUsers=All users`,
`UninstallDisplayNameMarkCurrentUser=Current user`, `UninstallDisplayNameMark64Bit=64-bit`.

---

## 3. Тихие ключи командной строки

Источник: [topic_setupcmdline](https://jrsoftware.org/ishelp/topic_setupcmdline.htm).
Для деинсталлятора — [topic_uninstcmdline](https://jrsoftware.org/ishelp/topic_uninstcmdline.htm).

| Ключ | Точная семантика |
|---|---|
| `/SILENT` | «When Setup is silent the wizard and the background window are not displayed **but the installation progress window is**.» |
| `/VERYSILENT` | «When a setup is very silent this installation progress window is not displayed. Everything else is normal so for example error messages during installation are displayed (if you haven't disabled them with the `/SUPPRESSMSGBOXES` command-line option…)» |
| `/SUPPRESSMSGBOXES` | «Instructs Setup to suppress message boxes. **Only has an effect when combined with `/SILENT` or `/VERYSILENT`.**» Значения по умолчанию перечислены в справке; ключевые: `Yes` в «Keep newer file?», `No` в «File exists, confirm overwrite.», `Abort` в Abort/Retry, `Cancel` в Retry/Cancel, `Yes` (=continue) в `DiskSpaceWarning`/`DirExists`/`NoUninstallWarning`/`ExitSetupMessage`/`ConfirmUninstall`, `Yes` (=restart) в `FinishedRestartMessage`. 5 message box'ов не подавляются (About Setup, «Exit Setup?», `FileNotInDir2`, любые ошибки до чтения ключей, а также `TaskDialogMsgBox`/`MsgBox` из `[Code]`). |
| `/NORESTART` | «Prevents Setup from restarting the system following a successful installation, or after a *Preparing to Install* failure that requests a restart.» |
| `/CLOSEAPPLICATIONS` | «Instructs Setup to close applications using files that need to be updated by Setup if possible.» |
| `/RESTARTAPPLICATIONS` | «Instructs Setup to restart applications if possible.» |
| `/LOG` | «Causes Setup to create a log file in the user's `TEMP` directory… The log file is created with a unique name based on the current date.» Важно: «Nor is it designed to be machine-parsable; the format of the file is subject to change without notice.» |
| `/LOG="filename"` | То же, но с фиксированным путём; «If a file with the specified name already exists it will be overwritten.» |
| `/DIR="x:\dirname"` | «Overrides the default directory name displayed on the *Select Destination Location* wizard page. A fully qualified pathname must be specified. May include an `expand:` prefix… For example: `/DIR=expand:{autopf}\My Program`.» |
| `/GROUP="folder name"` | «Overrides the default folder name displayed on the *Select Start Menu Folder* wizard page… **If the [Setup] section directive `DisableProgramGroupPage` was set to `yes`, this command-line parameter is ignored.**» |
| `/ALLUSERS` | «Instructs Setup to install in administrative install mode. **Only has an effect when the [Setup] section directive `PrivilegesRequiredOverridesAllowed` allows the `commandline` override.**» |
| `/CURRENTUSER` | «Instructs Setup to install in non administrative install mode. Only has an effect when… allows the `commandline` override.» |
| `/SP-` | «Disables the *This will install… Do you wish to continue?* prompt at the beginning of Setup. Of course, this will have no effect if the `DisableStartupPrompt` [Setup] section directive was set to `yes`.» |
| `/NOCANCEL` | «Prevents the user from cancelling during the installation process, by disabling the Cancel button and ignoring clicks on the close button. Useful along with `/SILENT` or `/VERYSILENT`.» |
| `/LOADINF="filename"` | «Instructs Setup to load the settings from the specified file after having checked the command line. This file can be prepared using the `/SAVEINF=` command…» |
| `/SAVEINF="filename"` | «Instructs Setup to save installation settings to the specified file.» |

Дополнительно (полезно для self-update): `/NOCLOSEAPPLICATIONS`, `/FORCECLOSEAPPLICATIONS`,
`/NOFORCECLOSEAPPLICATIONS`, `/LOGCLOSEAPPLICATIONS`, `/NORESTARTAPPLICATIONS`,
`/RESTARTEXITCODE=<код>`, `/LANG=<язык>`, `/NOICONS`, `/NOSTYLE`, `/TYPE=`, `/COMPONENTS=`,
`/TASKS=`, `/MERGETASKS=`, `/PASSWORD=`.

### 3.1 Точная разница `/SILENT` и `/VERYSILENT`

Разница **ровно одна**: окно прогресса установки.
`/SILENT` → мастер скрыт, окно прогресса показывается. `/VERYSILENT` → не показывается и оно.
Всё остальное одинаково: сообщения об ошибках всё равно выводятся (если не `/SUPPRESSMSGBOXES`),
стартовый запрос «This will install…» всё равно выводится (если не `/SP-` и не
`DisableStartupPrompt=yes`).

Дополнительное различие в поведении при перезагрузке: «If a restart is necessary and the `/NORESTART`
command isn't used (see below) and Setup is silent, it will display a *Reboot now?* message box.
If it's very silent it will reboot without asking.» То есть **`/VERYSILENT` без `/NORESTART` может
перезагрузить компьютер без вопроса** — для self-update `/NORESTART` обязателен.

### 3.2 Что с чем комбинируется и что игнорируется

| Ключ | Условие |
|---|---|
| `/SUPPRESSMSGBOXES` | работает **только** вместе с `/SILENT` или `/VERYSILENT` |
| `/NOCLOSEAPPLICATIONS` | игнорируется, если также указан `/CLOSEAPPLICATIONS` |
| `/NOFORCECLOSEAPPLICATIONS` | игнорируется, если также указан `/FORCECLOSEAPPLICATIONS` |
| `/NORESTARTAPPLICATIONS` | игнорируется, если также указан `/RESTARTAPPLICATIONS` |
| `/NOREDIRECTIONGUARD` | игнорируется, если также указан `/REDIRECTIONGUARD` |
| `/ALLUSERS`, `/CURRENTUSER` | игнорируются без `PrivilegesRequiredOverridesAllowed=commandline` (или `dialog`, который включает `commandline`) |
| `/GROUP` | игнорируется при `DisableProgramGroupPage=yes` |
| `/SP-` | без эффекта при `DisableStartupPrompt=yes` |
| `/HELP`, `/?` | игнорируется при `UseSetupLdr=no` |
| `/NOCANCEL` | «Useful along with `/SILENT` or `/VERYSILENT`» (не запрещён и без них) |
| `/DIR`, `/LOG`, `/LOADINF`, `/NORESTART` | полностью совместимы с `/VERYSILENT` |

---

## 4. Как Inno Setup закрывает работающее приложение

### 4.1 Механизм Windows Restart Manager

Цитата справки (`CloseApplications`): «**Note:** Setup uses Windows Restart Manager to detect,
close, and restart applications.»
([topic_setup_closeapplications](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm))

Фактическая последовательность из исходников:

1. Сессия создаётся один раз на старте, если `CloseApplications` включён:
   `Projects/Src/Setup.MainFunc.pas:3656–3668` — `RmStartSession(...)`, затем читаются
   `CloseApplicationsFilter` и `CloseApplicationsFilterExcludes`.
2. Регистрация подлежащих замене файлов: `RmRegisterResources(...)` —
   `Setup.MainFunc.pas:2174`.
3. Закрытие: `Projects/Src/Setup.Install.HelperFunc.pas:534–567`, процедура
   `ShutdownApplications` — `RmShutdown(RmSessionHandle, ForcedActionFlag[Forced], nil)`,
   где `ForcedActionFlag[False] = 0`, `ForcedActionFlag[True] = RmForceShutdown`.
   Флаг `Forced` берётся из `CloseApplications=force` **или** из ключа `/FORCECLOSEAPPLICATIONS`:
   ```pascal
   Forced := InitForceCloseApplications or
             ((shForceCloseApplications in SetupHeader.Options) and not InitNoForceCloseApplications);
   ```
   При `ERROR_FAIL_SHUTDOWN` (351) показывается Abort-Retry-Ignore и попытка повторяется.
4. Перезапуск: `RmRestart` вызывается позже (флаг `RmDoRestart`), и — как прямо сказано в
   справке `RestartApplications` — «For Setup to be able to restart an application after the
   installation has completed, the application needs to be using the Windows
   `RegisterApplicationRestart` API function.»

**Важно:** для *обнаружения и закрытия* процесса с открытым файлом участия приложения не
требуется — Restart Manager сам находит держателей файлов. `RegisterApplicationRestart` нужен
**только** для автоматического *перезапуска* после установки.

### 4.2 Директивы

| Директива | Значения | По умолчанию | Семантика |
|---|---|---|---|
| `CloseApplications` | `force`, `yes`, `no` | `yes` | Не-тихий режим: пауза на *Preparing to Install* и вопрос пользователю. Тихий режим: «Setup will always close and restart such applications, unless told not to via the command line.» `force` → «Setup will force close when closing applications… Use with care since this may cause the user to lose unsaved work.» |
| `CloseApplicationsFilter` | список шаблонов имён файлов через запятую | `*.exe,*.dll,*.chm` | «Limits which [Files] and [InstallDelete] entries Setup will check for being in use. Only files matching one of the wildcards will be checked. Setting this to `*.*` can provide better checking at the expense of speed.» |
| `CloseApplicationsFilterExcludes` | список шаблонов через запятую | пусто | «Files matching one of the wildcards will not be checked even if they match `CloseApplicationsFilter`.» **Появилась в 6.4.2** (`whatsnew.htm`: «6.4.2 (2025-03-12) Added [Setup] section directive `CloseApplicationsFilterExcludes`.») |
| `RestartApplications` | `yes`, `no` | `yes` | «When set to `yes` and `CloseApplications` is also set to `yes` or `force`, Setup restarts the closed applications after the installation has completed.» |

Ссылки: [CloseApplications](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm),
[CloseApplicationsFilter](https://jrsoftware.org/ishelp/topic_setup_closeapplicationsfilter.htm),
[RestartApplications](https://jrsoftware.org/ishelp/topic_setup_restartapplications.htm).

### 4.3 `AppMutex` — как работает точно

Цитата справки ([topic_setup_appmutex](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm)):

> This directive is used to prevent the user from installing new versions of an application while
> the application is still running, and to prevent the user from uninstalling a running application.
> It specifies the names of one or more named mutexes (multiple mutexes are separated by commas),
> which Setup and Uninstall will check for at startup. If any exist, Setup/Uninstall will display the
> message: "…has detected that… is currently running. Please close all instances of it now, then
> click OK to continue, or Cancel to exit."
> … It is not necessary to explicitly destroy the mutex object upon your application's termination;
> the system will do this automatically. Nor is it recommended that you do so, because ideally the
> mutex object should exist until the process completely terminates.
> Note that mutex name comparison in Windows is **case sensitive.**

**Ключевое: `AppMutex` ничего не убивает — Setup ждёт.** Исходники,
`Projects/Src/Setup.MainFunc.pas:3740–3743` (внутри `InitializeSetup`):

```pascal
{ Check if app is running }
while CheckForMutexes(ExpandedAppMutex) do
  if LoggedMsgBox(FmtSetupMessage1(msgSetupAppRunningError, ExpandedAppName),
     SetupMessages[msgSetupAppTitle], mbError, MB_OKCANCEL, True, IDCANCEL) <> IDOK then
    Abort;
```

Текст сообщения (`Files/Default.isl:91`):
`SetupAppRunningError=Setup has detected that %1 is currently running.%n%nPlease close all instances of it now, then click OK to continue, or Cancel to exit.`

Деинсталлятор тоже проверяет мьютекс: `Setup.Install.pas:2797–2798` добавляет в uninstall-лог
запись `utMutexCheck` с `ExpandedAppMutex`.

**Нужен ли `AppMutex`?** Формально нет — закрытие файлов обеспечивает Restart Manager. Но:
`AppMutex` — единственный механизм, который даёт *осмысленное сообщение* пользователю при
интерактивной установке поверх работающей программы вместо «файл занят». Для PySide6/Qt-оверлея
он полезен ещё и как «single instance» guard. Если приложение уже использует single-instance
мьютекс — просто укажите его имя в `AppMutex`.

⚠️ **Критично для self-update:** `LoggedMsgBox` вызывается с `Suppressible=True, Default=IDCANCEL`
(`Setup.MainFunc.pas:2599–2613`: `if InitSuppressMsgBoxes and Suppressible then … Result := Default`),
а `InitSuppressMsgBoxes := True` ставится ключом `/SUPPRESSMSGBOXES` (`Setup.MainFunc.pas:3286`).
Значит: **при `AppMutex` + работающем приложении + `/SUPPRESSMSGBOXES` Setup получит ответ
`Cancel` и вызовет `Abort`.** `Abort` внутри `InitializeSetup` перехватывается в
`Setup.Start.pas:223–236` и приводит к `Halt(ecInitializationError)`, то есть **код выхода 1
(«Setup failed to initialize»)**, без какого-либо сообщения (`ShowExceptionMsg` для `EAbort`
только пишет в лог: `Setup.MainFunc.pas:2642–2656`).
Подробности и как это обойти — в §6.

### 4.4 `SetupMutex`

Цитата ([topic_setup_setupmutex](https://jrsoftware.org/ishelp/topic_setup_setupmutex.htm)):

> This directive is used to prevent Setup from running while Setup is already running. It specifies
> the names of one or more named mutexes (multiple mutexes are separated by commas), which Setup will
> check for at startup. If any exist, Setup will display the message: "Setup has detected that Setup
> is currently running. Please close all instances of it now, then click OK to continue, or Cancel to
> exit." If none exist, Setup will create the mutex(es) and continue normally.

Код: `Setup.MainFunc.pas:3746–3750` — цикл `while CheckForMutexes(ExpandedSetupMutex)` и затем
`CreateMutexes(ExpandedSetupMutex)`. То есть при `SetupMutex` **та же ловушка с
`/SUPPRESSMSGBOXES`** (Default = `IDCANCEL` → `Abort` → код 1), если в момент старта уже идёт
другой Setup с тем же именем. Для самоперезапуска обновления это реальный риск (см. §6).

### 4.5 `RestartIfNeededByRun`

Цитата ([topic_setup_restartifneededbyrun](https://jrsoftware.org/ishelp/topic_setup_restartifneededbyrun.htm)):
«When set to `yes`, and a program executed in the `[Run]` section queues files to be replaced on the
next reboot (by calling `MoveFileEx` or by modifying `wininit.ini`), Setup will detect this and prompt
the user to restart the computer at the end of installation.» По умолчанию `yes`.
Для тихого обновления с `/NORESTART` практического вреда нет, но при `[Run]`, который ставит файлы
в очередь на замену, лучше задать `RestartIfNeededByRun=no`, чтобы Setup не инициировал
перезагрузку.

### 4.6 Как PySide6/Qt-приложению создать именованный мьютекс

Справка Inno Setup даёт примеры на Delphi/C/VB (`CreateMutex(nil, False, 'MyProgramsMutexName')` и
т. д.), но не на Python. Эквивалент через `ctypes`:

```python
# elite_hud/single_instance.py
import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183

# Имя ДОЛЖНО совпадать с AppMutex в .iss (сравнение имён в Windows регистрозависимое).
MUTEX_NAME = "EliteHud.SingleInstance.v1"

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_kernel32.CreateMutexW.restype = wintypes.HANDLE

# handle хранится в модуле НА ВСЁ ВРЕМЯ жизни процесса:
# справка Inno Setup прямо не рекомендует закрывать мьютекс вручную.
_handle = None


def acquire_single_instance() -> bool:
    """True — мы первые; False — приложение уже запущено."""
    global _handle
    ctypes.set_last_error(0)
    h = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(h)
        return False
    _handle = h          # держим ссылку, НЕ вызываем CloseHandle до выхода из процесса
    return True
```

Вызывать **до** создания `QApplication`, на самом старте `main()`.

Про префикс `Global\`:

* Справка Inno Setup в примере для `AppMutex` использует
  `AppMutex=MyProgramsMutexName,Global\MyProgramsMutexName`, то есть имя с префиксом `Global\`
  синтаксически допустимо в `AppMutex`.
  ([topic_setup_appmutex](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm))
* Допустимо ли **создание** мьютекса в пространстве имён `Global\` непривилегированным процессом
  (в частности, нужно ли `SeCreateGlobalPrivilege`), в разрешённых источниках
  (jrsoftware.org, issrc, actions/runner-images) **не подтверждено** → **не подтверждено**.
  Если приложение должно работать без прав администратора, безопаснее использовать имя **без
  префикса** (оно будет в сессии пользователя) или `Local\`, и такое же имя указать в `AppMutex`.
  Практический эффект: `AppMutex` и мьютекс приложения должны совпадать посимвольно; если
  приложение создаёт `Local\X`, а в скрипте указано `Global\X` — Setup мьютекс не увидит.

---

## 5. Автозапуск

### 5.1 Где какие флаги действительно допустимы

Это важно, потому что интуиция здесь обманывает:

* `unchecked` — флаг **`[Tasks]`** (и `[Run]` с `postinstall`). В `[Icons]` его **нет**.
  Справка `[Tasks]`: «`unchecked` — Instructs Setup that this task should be unchecked initially.»
* `runascurrentuser` — флаг **только `[Run]`/`[UninstallRun]`**. Справка `[Run]`:
  «`runascurrentuser` — If this flag is specified, the spawned process will inherit Setup/Uninstall's
  user credentials (typically, full administrative privileges). This is the default behavior when the
  `postinstall` flag is not used.»
  В `[Icons]` его нет.

Полный список флагов `[Icons]` — ровно 9, из компилятора
(`Projects/Src/Compiler.SetupCompiler.pas:4324–4327`):

```
uninsneveruninstall, runminimized, createonlyiffileexists, useapppaths,
closeonexit, dontcloseonexit, runmaximized, excludefromshowinnewinstall, preventpinning
```

Справка `[Icons]` подтверждает тот же набор
([topic_iconssection](https://jrsoftware.org/ishelp/topic_iconssection.htm)).

Правильный способ связать ярлык автозапуска с задачей — параметр `Tasks:`:

> `Tasks` — A space separated list of task names, telling Setup to which task the entry belongs. If
> the end user selects a task from this list, the entry is processed… Note that the *Don't create a
> Start Menu folder* checkbox on the *Select Start Menu Folder* wizard page doesn't affect `[Icons]`
> entries that have `Tasks` parameters since they have their own checkboxes.

Источник: [topic_componentstasksparams](https://jrsoftware.org/ishelp/topic_componentstasksparams.htm)

### 5.2 Константы папки автозагрузки

| Константа | Что даёт |
|---|---|
| `{userstartup}` | «The path to the Startup folder on the Start Menu» — профиль текущего пользователя. В списке per-user-констант → **вызывает `UsedUserAreasWarning`** при `PrivilegesRequired=admin`. |
| `{commonstartup}` | Тот же Startup, но «All Users». Предупреждения не вызывает. |
| `{autostartup}` | `{commonstartup}` в admin-режиме, `{userstartup}` в non-admin. **Рекомендуемый вариант** — предупреждения не вызывает и совпадает с выбранным режимом установки. |

Источник: [topic_consts](https://jrsoftware.org/ishelp/topic_consts.htm) + списки констант в
`Compiler.SetupCompiler.pas:1808–1816`.

### 5.3 Полный рабочий пример

```ini
[Setup]
AppId={{8F1C2A54-7B3E-4C19-9E2D-4A6B0C7D5E31}
AppName=Elite HUD
AppVersion=1.2.0
DefaultDirName={autopf}\Elite HUD
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
; UsePreviousPrivileges оставлен по умолчанию (yes): AppId задан как {{GUID},
; то есть "{{" — это escape, а не константа, поэтому компилятор не требует
; "no" (см. §2.2). Со значением yes обновление само повторит ранее выбранный
; режим установки и не будет показывать диалог.
UsePreviousTasks=yes
AppMutex=EliteHud.SingleInstance.v1

[Tasks]
; Флаг unchecked — здесь, в [Tasks]; в [Icons] такого флага нет.
; ВАЖНО: каждая запись обязана быть на ОДНОЙ строке — переноса строк
; обратным слэшем в Inno Setup НЕТ (см. примечание ниже).
Name: "startupicon"; Description: "Автозапуск при входе в Windows"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "dist\EliteHud.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Elite HUD"; Filename: "{app}\EliteHud.exe"; WorkingDir: "{app}"
Name: "{group}\Удалить Elite HUD"; Filename: "{uninstallexe}"

; Автозапуск «для текущего пользователя» — только для non-admin установки.
; {userstartup} вызовет предупреждение при PrivilegesRequired=admin.
Name: "{userstartup}\Elite HUD"; Filename: "{app}\EliteHud.exe"; WorkingDir: "{app}"; Tasks: startupicon; Flags: excludefromshowinnewinstall

; Вариант «для всех пользователей» (нужны права администратора):
; Name: "{commonstartup}\Elite HUD"; Filename: "{app}\EliteHud.exe"; WorkingDir: "{app}"; Tasks: startupicon

; Рекомендуемый универсальный вариант — подставляется common или user
; в зависимости от выбранного режима установки:
; Name: "{autostartup}\Elite HUD"; Filename: "{app}\EliteHud.exe"; WorkingDir: "{app}"; Tasks: startupicon
```

> **Переноса строк в записях `[Section]` нет.** Компилятор читает файл построчно и передаёт
> каждую строку парсеру записи целиком (`Projects/Src/Compiler.SetupCompiler.pas:1345`:
> `EnumProc(PChar(Line.LineText), Ext)`), а `ExtractParameters` останавливается на конце строки
> (`if S^ = #0 then Break;`). Поэтому «`\`» в конце строки — обычный символ, а следующая строка
> будет разобрана как отдельная (ошибочная) запись. В справке механизм продолжения строк не
> описан. Единственное место, где `\` в конце строки работает, — директивы ISPP (например
> `#include`; см. комментарий в `Projects/Bin/Script.ISPP.Test.iss:1418–1423`), и к записям
> секций это не относится.

Замечания:

* `Flags: excludefromshowinnewinstall` — «Prevents the Start menu entry for the new shortcut from
  receiving a highlight on Windows 7 and additionally prevents the new shortcut from being
  automatically pinned the Start screen on Windows 8 (or later).» Для записи в Startup это уместно.
* Если хочется, чтобы автозапуск запускался **не от администратора**, когда установка шла
  per-machine (`PrivilegesRequired=admin`), ярлык в Startup сам по себе даёт запуск от имени
  вошедшего пользователя (Startup обрабатывает Explorer, не Setup). Флаг `runascurrentuser` тут
  неприменим, потому что это флаг `[Run]`, а не `[Icons]`.

---

## 6. Self-update: приложение скачивает новый `setup.exe` и запускает его тихо

### 6.1 Что происходит с работающим приложением

| Механизм | Убивает ли приложение |
|---|---|
| `AppMutex` | **Нет.** Setup крутится в цикле `while CheckForMutexes(...)` и показывает модальный `MB_OKCANCEL`. При `Cancel` — `Abort`. (`Setup.MainFunc.pas:3740–3743`) |
| Restart Manager (`CloseApplications=yes`/`force`) | **Да, закрывает.** `RmShutdown` с флагом `RmForceShutdown` при `force` или `/FORCECLOSEAPPLICATIONS`. Это то, что реально закрывает процесс, держащий файл. (`Setup.Install.HelperFunc.pas:534–567`) |
| `RestartApplications=yes` | После установки Setup может **перезапустить** закрытое приложение — но только если само приложение вызывало `RegisterApplicationRestart`. |

### 6.2 Главная ловушка тихого обновления

Типичная проблема — Setup завершается с кодом **1** и ничего не делает. Причина: комбинация

```
AppMutex=<имя>  +  приложение ещё живо  +  /SUPPRESSMSGBOXES
```

→ `LoggedMsgBox(..., Suppressible=True, Default=IDCANCEL)` возвращает `IDCANCEL` →
`Abort` в `InitializeSetup` → перехват в `Setup.Start.pas:223–236`, где `SetupExitCode` ещё равен 0
→ `Halt(ecInitializationError)` → **код выхода 1**, «Setup failed to initialize», без сообщения.
(Код 1 в документации описан именно как «Setup failed to initialize» — см. §6.5.)

Вторая ловушка: если `/SUPPRESSMSGBOXES` **не** указан, то в `/VERYSILENT`-режиме сообщения об
ошибках всё равно показываются, и появится **модальное окно** «Setup has detected that Elite HUD
is currently running…» — тихое обновление повиснет до клика пользователя.

Третья: одинаковое имя `SetupMutex` у старого и нового Setup — тот же сценарий
(`Setup.MainFunc.pas:3746–3750`).

### 6.3 Рекомендуемые схемы

**Схема A (рекомендуемая) — приложение выходит само, обновление доводит помощник.**

1. Приложение скачивает `EliteHud-Setup-<ver>.exe` в `%LOCALAPPDATA%\EliteHud\updates\` и
   кладёт рядом маркер `update.pending` с версией.
2. Приложение запускает **отдельный процесс-помощник** (не себя) с `DETACHED_PROCESS |
   CREATE_NEW_PROCESS_GROUP` — например `EliteHudUpdater.exe`, либо `cmd.exe /c start "" ...` —
   и **немедленно завершается**, освобождая мьютекс.
3. Помощник ждёт, пока мьютекс `EliteHud.SingleInstance.v1` исчезнет (проще всего — циклически
   `OpenMutexW(SYNCHRONIZE, False, name)`; `ERROR_FILE_NOT_FOUND` = приложение ушло; либо
   `WaitForSingleObject` на handle процесса, который помощник получил при запуске).
4. Помощник запускает установщик:

   ```
   "EliteHud-Setup-1.2.1.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
       /CLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /SP-
       /LOG="%LOCALAPPDATA%\EliteHud\updates\update.log"
   ```
5. Помощник ждёт код выхода Setup. `0` → успех, перезапускает приложение. Иначе — оставляет лог
   и не перезапускает (или показывает ошибку при следующем старте).

Именно «шаг 3» (дождаться освобождения мьютекса) устраняет гонку: Setup проверяет `AppMutex`
в `InitializeSetup`, то есть практически сразу после старта процесса.

**Схема B (проще, но грубее) — без `AppMutex` на время обновления.**

Убрать `AppMutex` из скрипта и положиться на Restart Manager:

```
EliteHud-Setup-1.2.1.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /NORESTARTAPPLICATIONS
```

Setup сам найдёт и принудительно закроет `EliteHud.exe`, держащий файл. Приложение должно быть
готово к тому, что его убьют без предупреждения (потеря несохранённого состояния). Для оверлея
это обычно приемлемо, если состояние пишется в `config.toml` инкрементально.

**Схема C — оставить `AppMutex`, но добавлять `/SUPPRESSMSGBOXES` только после подтверждённого
выхода.** То есть помощник сначала дожидается смерти процесса, и лишь потом стартует Setup с
`/SUPPRESSMSGBOXES`. Фактически это схема A без отдельного «шага 2» — приложение запускает Setup
и выходит, но тогда остаётся гонка, поэтому лучше всё же помощник.

### 6.4 Как приложение возвращается после тихого обновления

**Ключевой факт:** `postinstall`-записи `[Run]` в тихом режиме **не выполняются**. Это видно из
исходников: не-`postinstall` записи обрабатываются в шаге установки —
`Setup.MainForm.pas:107`: `if not(roPostInstall in RunEntry.Options) and ShouldProcessRunEntry(...)`,
тогда как `postinstall`-записи обрабатываются только со страницы завершения через список
флажков — `Setup.WizardForm.pas:1415`: `if (roPostInstall in RunEntry.Options) and ShouldProcessRunEntry(...)`
(наполняет `RunList`, который в silent-режиме не существует).

Решение без `[Code]` — вторая запись `[Run]` с флагом `skipifnotsilent`:

> `skipifnotsilent` — Valid only in a `[Run]` section. Instructs Setup to skip this entry if Setup is
> not running (very) silent.

```ini
[Run]
; 1) Интерактивная установка: галочка «Запустить Elite HUD» на странице завершения.
Filename: "{app}\EliteHud.exe"; Description: "Запустить Elite HUD"; Flags: nowait postinstall skipifsilent runasoriginaluser

; 2) Тихое обновление: сразу перезапустить приложение.
;    postinstall здесь НЕ используется — иначе запись не выполнится в silent-режиме.
Filename: "{app}\EliteHud.exe"; Flags: nowait skipifnotsilent runasoriginaluser
```

`runasoriginaluser` указан явно: без `postinstall` по умолчанию действует `runascurrentuser`
(`Compiler.SetupCompiler.pas:6174`: `(not RunAsCurrentUser and (roPostInstall in Options))`),
то есть при per-machine установке приложение унаследовало бы права администратора.
Справка `[Run]`: «`runasoriginaluser` … the spawned process will execute with the (normally
non-elevated) credentials of the user that started Setup initially».
([topic_runsection](https://jrsoftware.org/ishelp/topic_runsection.htm))

### 6.5 Коды выхода Setup

Документированы на [topic_setupexitcodes](https://jrsoftware.org/ishelp/topic_setupexitcodes.htm)
(«Setup Exit Codes»); те же числа в исходниках — `Setup.MainFunc.pas:47–62`.

| Код | Значение (цитата) |
|---|---|
| 0 | «Setup was successfully run to completion or the `/HELP` or `/?` command-line parameter was used.» |
| 1 | «Setup failed to initialize.» |
| 2 | «The user clicked Cancel in the wizard before the actual installation started, or chose "No" on the opening "This will install..." message box.» |
| 3 | «A fatal error occurred while preparing to move to the next installation phase…» |
| 4 | «A fatal error occurred during the actual installation process.» (Abort-Retry-Ignore сам по себе не фатален; `Abort` там даёт 5.) |
| 5 | «The user clicked Cancel during the actual installation process, or chose *Abort* at an Abort-Retry-Ignore box.» |
| 6 | «The Setup process was forcefully terminated by the debugger…» |
| 7 | «The *Preparing to Install* stage determined that Setup cannot proceed with installation.» |
| 8 | «…and that the system needs to be restarted in order to correct the problem.» |

Важные оговорки из той же страницы:

* «Before returning an exit code of 1, 3, 4, 7, or 8, an error message explaining the problem will
  normally be displayed.» — **кроме** случая `EAbort` (§6.2), где сообщения нет.
* «Future versions of Inno Setup may return additional exit codes, so applications checking the exit
  code should be programmed to handle unexpected exit codes gracefully. Any non-zero exit code
  indicates that Setup was not run to completion.»
* `/RESTARTEXITCODE=<код>` — «Specifies a custom exit code that Setup is to return when the system
  needs to be restarted following a successful installation. (By default, 0 is returned in this case.)»

Деинсталлятор: [topic_uninstexitcodes](https://jrsoftware.org/ishelp/topic_uninstexitcodes.htm) —
«Programs checking the exit code to detect failure should not check for a specific non-zero value; any
non-zero exit code indicates that the uninstaller was not run to completion.» Плюс важная деталь:
«Note that at the moment you get an exit code back from the uninstaller, some code related to
uninstallation might still be running» (uninstaller перезапускает свою копию из `TEMP`).

### 6.6 Сводка подводных камней self-update

| # | Камень | Что делать |
|---|---|---|
| 1 | `AppMutex` + живое приложение + `/SUPPRESSMSGBOXES` → код 1, тихо | Дождаться освобождения мьютекса до старта Setup (схема A), либо убрать `AppMutex` и опереться на Restart Manager (схема B) |
| 2 | `AppMutex` без `/SUPPRESSMSGBOXES` в `/VERYSILENT` → модальное окно, повисание | никогда не запускать самообновление без помощника, который гарантирует выход приложения |
| 3 | `SetupMutex` совпадает у старого и нового Setup → та же проблема, что и (1) | либо не задавать `SetupMutex`, либо убедиться, что старый Setup не запущен |
| 4 | `postinstall` `[Run]` не работает в silent → приложение не вернулось | отдельная запись с `skipifnotsilent`, без `postinstall` |
| 5 | `/VERYSILENT` без `/NORESTART` может перезагрузить ПК без вопроса | всегда `/NORESTART` (и `RestartIfNeededByRun=no`) |
| 6 | Обновление запущено из каталога `{app}` — файлы заняты и Setup не может обновиться штатно | качать и запускать установщик из `%LOCALAPPDATA%\EliteHud\updates\`, а не из `{app}` |
| 7 | `/LOG` предназначен для отладки: «Not is it designed to be machine-parsable» | не парсить лог программно; использовать код выхода и `DisplayVersion` из реестра (§7) |
| 8 | Приложение, запущенное после обновления, унаследует права администратора | явный `Flags: runasoriginaluser` |
| 9 | Антивирус/`SmartScreen` на свежескачанном неподписанном setup.exe | подписывать установщик и приложение; `SignTool` в `[Setup]` (вне рамок этого отчёта) |
| 10 | Если приложение — PyInstaller `--onefile`, оно распаковывается в `%TEMP%\_MEIxxxxx`; содержимое `{app}` — только один `.exe` | Restart Manager корректно найдёт именно `EliteHud.exe`; `CloseApplicationsFilter` по умолчанию (`*.exe,*.dll,*.chm`) это покрывает |

### 6.7 Что ожидать при обновлении поверх per-user установки

Если приложение было установлено `PrivilegesRequired=lowest` (per-user, ключ в `HKCU`), то и
самообновление надо запускать **без** ключей `/ALLUSERS` и `/CURRENTUSER`: при
`UsePreviousPrivileges=yes` (значение по умолчанию; в примерах `AppId={{GUID}` — это escape, а не
константа, поэтому `yes` допустим, см. §2.2) Setup сам найдёт в реестре ранее установленный режим
и повторит его, не показывая диалог. Именно это и нужно при самообновлении, поэтому
`UsePreviousPrivileges=no` здесь вреден.

Практично: **не** передавать ни `/ALLUSERS`, ни `/CURRENTUSER`, а задать в скрипте
`PrivilegesRequired=lowest` и `PrivilegesRequiredOverridesAllowed=commandline` (без `dialog`):
тогда при самообновлении диалог режима не появится (он и так появляется только при `dialog`), а
Setup пойдёт в тот режим, который уже записан в реестре.
Внимание: если пользователь изначально выбрал per-machine, а приложение потом обновит себя
per-user, получится side-by-side из двух установок. Надёжнее хранить выбранный режим и передавать
`/ALLUSERS` или `/CURRENTUSER` явно.

---

## 7. Как Python-приложение определяет, что оно установлено через Inno Setup

### 7.1 Путь ключа и суффикс `_is1`

Суффикс подтверждён и кодом, и справкой.

* Справка: «`AppId` also determines the actual name of the Uninstall registry key, to which Inno
  Setup tacks on "`_is1`" at the end. (Therefore, if `AppId` is "`MyProgram`", the key will be named
  "`MyProgram_is1`".)» ([topic_setup_appid](https://jrsoftware.org/ishelp/topic_setup_appid.htm))
* Код, `Projects/Src/Setup.MainFunc.pas:366–369`:
  ```pascal
  function GetUninstallRegSubkeyName(const UninstallRegKeyBaseName: String): String;
  begin
    Result := Format('%s\%s_is1', [REGSTR_PATH_UNINSTALL, UninstallRegKeyBaseName]);
  end;
  ```
  где `REGSTR_PATH_UNINSTALL` — константа из Delphi-модуля `RegStr` (в `uses` файла
  `Setup.MainFunc.pas:257`); её значение — стандартный путь ARP
  `Software\Microsoft\Windows\CurrentVersion\Uninstall`.
  **Значение макроса `REGSTR_PATH_UNINSTALL` в разрешённых источниках отсутствует** (ни в issrc, ни
  на jrsoftware.org он не определён — только используется) → буквальное значение помечаю как
  **не подтверждено**; сам путь `...\CurrentVersion\Uninstall\<AppId>_is1` подтверждён справкой и
  логикой кода.

Корень (`HKCU` или `HKLM`) определяется режимом установки — см. §2.6
(`Setup.MainFunc.pas:2715–2723`).

Итоговые точные пути:

| Режим | 32-битный install mode | 64-битный install mode |
|---|---|---|
| per-user (non administrative) | `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\<AppId>_is1` | то же самое (HKCU не разделяется по view) |
| per-machine (administrative) | `HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\<AppId>_is1` | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\<AppId>_is1` |

Обоснование 32/64: справка `[topic_32vs64bitinstalls](https://jrsoftware.org/ishelp/topic_32vs64bitinstalls.htm)`:
«32-bit install mode … The `Uninstall` key is created in the 32-bit view of the registry.»
«64-bit install mode … The `Uninstall` key is created in the 64-bit view of the registry.»
Код: `Setup.MainFunc.pas:2726–2736` — `InstallDefaultRegView := rv64Bit` при 64-битном install mode,
иначе `rv32Bit`; и `Setup.Install.pas:230` — `RegView := InstallDefaultRegView`.

Важная деталь из комментариев исходников: **HKCU не разделяется между 32- и 64-битным view**, а HKLM
разделяется. `Setup.Install.pas:200–208`: «HKLM is not shared for 32-bit and 64-bit so check it for
opposite 32-bit or 64-bit install mode. Not checking HKCU since HKCU is shared for 32-bit and 64-bit
mode…». Поэтому для per-user установки WOW64-флаги не важны, а для per-machine — важны.

### 7.2 Имена значений, которые пишет Inno Setup

Точный список из исходников, `Projects/Src/Setup.Install.pas:270–360`
(комментарий в коде: «do not localize or change any of the following strings»):

| Имя значения | Тип | Условие записи / смысл |
|---|---|---|
| `Inno Setup: Setup Version` | REG_SZ | всегда; версия Inno Setup, которой собран установщик |
| `Inno Setup: App Path` | REG_SZ | каталог установки (`WizardDirValue`), либо пусто если `CreateAppDir=no` |
| `InstallLocation` | REG_SZ | каталог с завершающим `\`; пишется только если непустой (`SetStringValueUnlessEmpty`) |
| `Inno Setup: Icon Group` | REG_SZ | имя группы в меню «Пуск» |
| `Inno Setup: No Icons` | REG_DWORD = 1 | только если пользователь выбрал «не создавать папку в меню Пуск» |
| `Inno Setup: User` | REG_SZ | имя пользователя, выполнившего установку |
| `Inno Setup: Setup Type` | REG_SZ | если в скрипте есть `[Types]` |
| `Inno Setup: Selected Components` | REG_SZ | список через запятую |
| `Inno Setup: Deselected Components` | REG_SZ | список через запятую |
| `Inno Setup: Selected Tasks` | REG_SZ | если в скрипте есть `[Tasks]` |
| `Inno Setup: Deselected Tasks` | REG_SZ | если в скрипте есть `[Tasks]` |
| `Inno Setup: User Info: Name` / `: Organization` / `: Serial` | REG_SZ | если включена страница User Info |
| `Inno Setup: Language` | REG_SZ | внутреннее имя языка |
| `DisplayName` | REG_SZ | обрезается до 259 символов: «For the entry to appear in ARP, DisplayName cannot exceed 259 characters» |
| `DisplayIcon` | REG_SZ | из `UninstallDisplayIcon`; только если непусто |
| `UninstallString` | REG_SZ | `"<path>\unins000.exe"` (+ ` /LOG`, если `UninstallLogging=yes`) |
| `QuietUninstallString` | REG_SZ | `"<path>\unins000.exe" /SILENT` (+ ` /LOG`) |
| `DisplayVersion` | REG_SZ | из `AppVersion`; только если непусто |
| `Publisher` | REG_SZ | из `AppPublisher`; только если непусто |
| `URLInfoAbout` | REG_SZ | из `AppPublisherURL` |
| `HelpTelephone` | REG_SZ | из `AppSupportPhone` |
| `HelpLink` | REG_SZ | из `AppSupportURL` |
| `URLUpdateInfo` | REG_SZ | из `AppUpdatesURL` |
| `Readme` | REG_SZ | из `AppReadmeFile` |
| `Contact` | REG_SZ | из `AppContact` |
| `Comments` | REG_SZ | из `AppComments` |
| `ModifyPath` | REG_SZ | если задан `AppModifyPath` |
| `NoModify` | REG_DWORD = 1 | если `AppModifyPath` **не** задан |
| `NoRepair` | REG_DWORD = 1 | **всегда** |
| `InstallDate` | REG_SZ | дата установки (формат `GetInstallDateString`) |
| `MajorVersion`, `MinorVersion`, `VersionMajor`, `VersionMinor` | REG_DWORD | только если из `AppVersion` удалось извлечь major/minor. Комментарий в коде: «Originally MSDN said to write to Major/MinorVersion, now it says to write to VersionMajor/Minor. So write to both.» |
| `EstimatedSize` | REG_DWORD | размер в **КБ** (`EstimatedSize div 1024`), из `UninstallDisplaySize` или посчитанный. Комментарий: «Note: Windows 7 (and later?) doesn't automatically calculate sizes so set EstimatedSize ourselves.» |

Значения, записанные через `SetStringValueUnlessEmpty`, **отсутствуют в реестре**, если
соответствующая директива пуста. То есть нельзя рассчитывать, что `Publisher`, `URLInfoAbout`,
`DisplayVersion` и т. п. есть всегда.

### 7.3 Чтение из Python (`winreg`)

```python
"""Определение установки Elite HUD, сделанной Inno Setup."""
from __future__ import annotations

import winreg

APP_ID = "{8F1C2A54-7B3E-4C19-9E2D-4A6B0C7D5E31}"   # ровно как в AppId (без _is1)
UNINSTALL_SUBKEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_ID + "_is1"
)

# Просмотры реестра. HKCU НЕ разделяется между 32- и 64-битным view
# (см. комментарий в Setup.Install.pas:200–208), поэтому для HKCU достаточно
# одного чтения. Для HKLM view важен — перебираем оба явно.
_VIEWS = (
    ("64bit", winreg.KEY_WOW64_64KEY),
    ("32bit", winreg.KEY_WOW64_32KEY),
)


def _read_values(root, subkey: str, access: int) -> dict | None:
    """Значения ключа или None, если ключа нет."""
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | access) as key:
            count = winreg.QueryInfoKey(key)[1]
            return {
                name: value
                for name, value, _type in (
                    winreg.EnumValue(key, i) for i in range(count)
                )
            }
    except FileNotFoundError:
        return None


def find_inno_install() -> list[dict]:
    """Все записи Inno Setup для нашего AppId (per-user и per-machine)."""
    found: list[dict] = []

    # 1) per-user: HKCU. Читаем в 64-битном view; для HKCU это тот же ключ,
    #    что и в 32-битном (HKCU не разделяется по view).
    for view, access in _VIEWS:
        values = _read_values(winreg.HKEY_CURRENT_USER, UNINSTALL_SUBKEY, access)
        if values is not None:
            found.append({"scope": "user", "view": view, "values": values})
            break

    # 2) per-machine: HKLM. Здесь view ВАЖЕН: 32-битный install mode пишет
    #    в WOW6432Node (KEY_WOW64_32KEY), 64-битный — в 64-битный view.
    for view, access in _VIEWS:
        values = _read_values(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_SUBKEY, access)
        if values is not None:
            found.append({"scope": "machine", "view": view, "values": values})

    return found


def is_inno_installed() -> bool:
    """Признак «установлено через Inno Setup» — наличие значений 'Inno Setup: ...'."""
    return any(
        any(name.startswith("Inno Setup:") for name in entry["values"])
        for entry in find_inno_install()
    )


def installed_version() -> str | None:
    for entry in find_inno_install():
        version = entry["values"].get("DisplayVersion")
        if version:
            return str(version)
    return None
```

Пояснения:

* Для обычного 64-битного Python `winreg.KEY_READ` по умолчанию обращается к **64-битному** view
  (для 32-битного Python — к 32-битному). Поэтому перебор с `KEY_WOW64_32KEY` и
  `KEY_WOW64_64KEY` обязателен, если вы не знаете, какой битности был установщик.
* Если в скрипте включён `ArchitecturesInstallIn64BitMode` (как в примере), per-machine запись
  окажется в **64-битном** view, а `UninstallString` будет вести на 64-битный `unins000.exe`.
* Если `ArchitecturesInstallIn64BitMode` не задан, per-machine запись окажется в **32-битном**
  view (на 64-битной Windows это `WOW6432Node`), и её можно прочитать только с
  `KEY_WOW64_32KEY`.
* Полезные для self-update значения: `DisplayVersion` (сравнить с текущей версией),
  `UninstallString` / `QuietUninstallString` (тихое удаление), `InstallLocation` (где лежит
  `EliteHud.exe`), `Inno Setup: App Path`.
* Наиболее простой и надёжный признак «установлено через Inno Setup» — наличие значений с
  префиксом `Inno Setup: ` (`Inno Setup: Setup Version`, `Inno Setup: App Path`). Комментарий в
  исходниках прямо говорит, что эти строки не локализуются и не меняются.

---

## 8. Полный готовый `.iss`

Требуемые файлы рядом со скриптом: `dist\EliteHud.exe`, `app.ico`, `license.txt`.

```ini
; ============================================================================
;  Elite HUD — скрипт Inno Setup
;
;  Совместимость: Inno Setup 6.0+ (проверено по справке релизов 6.7.3 и 7.1.0).
;  Директив 7.x (SetupArchitecture) намеренно НЕ используется — на GitHub-hosted
;  Windows-раннерах стоит Inno Setup 6.7.1.
;
;  Файлы, которые должны лежать рядом со скриптом:
;    dist\EliteHud.exe   — сборка PyInstaller (--onefile --windowed)
;    app.ico             — иконка приложения (16/32/48/64/256)
;    license.txt         — лицензия, UTF-8
; ============================================================================

#define MyAppName       "Elite HUD"
#define MyAppVersion    "1.2.0"
#define MyAppPublisher  "Elite HUD"
#define MyAppExeName    "EliteHud.exe"
; Имя мьютекса. ДОЛЖНО совпадать с мьютексом, который создаёт приложение
; (Windows сравнивает имена мьютексов с учётом регистра).
#define MyAppMutex      "EliteHud.SingleInstance.v1"

[Setup]
; --- идентификация -----------------------------------------------------------
; AppId задан литералом: "{{" — это escape одного символа "{"
; (см. topic_consts). Итоговый AppId = {8F1C2A54-...}, а ключ деинсталляции —
; {8F1C2A54-...}_is1.
AppId={{8F1C2A54-7B3E-4C19-9E2D-4A6B0C7D5E31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://example.com/elite-hud
AppSupportURL=https://example.com/elite-hud/support
AppUpdatesURL=https://example.com/elite-hud/releases

; --- каталоги ----------------------------------------------------------------
; {autopf} -> {commonpf} в admin-режиме, {userpf} в non-admin.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; DisableDirPage по умолчанию auto: страница выбора каталога не показывается,
; если приложение уже установлено с тем же AppId.

; --- режим установки: per-user по умолчанию, с выбором режима -----------------
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
; UsePreviousPrivileges намеренно оставлен по умолчанию (yes).
; AppId задан как {{GUID}, где "{{" — escape одного "{", а НЕ константа
; (проверка CheckConst в Compiler.SetupCompiler.pas:8415/1826), поэтому
; компилятор не требует здесь "no". С yes обновление автоматически
; переиспользует ранее выбранный режим установки. Если бы AppId содержал
; настоящую константу (например {code:GetAppId}), требовалось бы "no".
UsePreviousAppDir=yes
UsePreviousTasks=yes

; --- работающее приложение ---------------------------------------------------
AppMutex={#MyAppMutex}
; SetupMutex намеренно НЕ задан: при самообновлении старый и новый Setup
; не должны блокировать друг друга в silent-режиме (см. отчёт, §6.2).
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd,*.chm
RestartApplications=no
; [Run] не ставит файлы в очередь на перезагрузку, но фиксируем явно.
RestartIfNeededByRun=no

; --- разрядность -------------------------------------------------------------
; Приложение собрано 64-битным PyInstaller'ом. Оба параметра задаются вместе:
; иначе Setup откажется работать на 32-битной Windows с сообщением об ошибке.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; --- внешний вид и ресурсы ---------------------------------------------------
WizardStyle=modern
; WizardStyle=modern dynamic  ; требует Inno Setup 6.6+ (тёмная тема по системе)
SetupIconFile=app.ico
LicenseFile=license.txt
; LicenseFile игнорируется, если у [Languages] задан параметр LicenseFile.

; --- деинсталляция -----------------------------------------------------------
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
CreateUninstallRegKey=yes
Uninstallable=yes

; --- выход компилятора -------------------------------------------------------
OutputDir=dist
OutputBaseFilename=EliteHud-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes

[Tasks]
; ВНИМАНИЕ: флаг unchecked принадлежит [Tasks] (и [Run] с postinstall),
; в [Icons] такого флага нет.
; ВНИМАНИЕ: запись = одна строка; переноса строк через "\" в Inno Setup нет.
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked
Name: "startupicon"; Description: "Запускать при входе в Windows"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Данные, которые пользователь не должен терять при обновлении:
Source: "config.example.toml"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall
; Если PyInstaller собирается --onedir, добавьте каталог целиком:
; Source: "dist\EliteHud\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; Автозапуск. {autostartup} -> {commonstartup} в admin-режиме и
; {userstartup} в non-admin; предупреждения UsedUserAreasWarning не даёт.
Name: "{autostartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startupicon; Flags: excludefromshowinnewinstall

[Run]
; 1) Обычная (интерактивная) установка: галочка «запустить» на странице завершения.
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

; 2) Тихое обновление: перезапустить приложение сразу.
;    postinstall здесь НЕ используется — записи с postinstall в silent-режиме
;    не выполняются (обрабатываются только со страницы завершения).
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifnotsilent runasoriginaluser
```

Команда компиляции (путь к `ISCC.exe` зависит от версии — на GitHub-раннерах проверяйте фактический):

```bat
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\EliteHud.iss
```

Команда тихого самообновления (запускается помощником после выхода приложения):

```bat
"EliteHud-Setup-1.2.1.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART ^
    /CLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /SP- ^
    /LOG="%LOCALAPPDATA%\EliteHud\updates\update.log"
```

---

## 9. Сводка «не подтверждено»

1. **Создание мьютекса с префиксом `Global\` непривилегированным процессом** (нужен ли
   `SeCreateGlobalPrivilege`) — в разрешённых источниках не найдено. В справке Inno Setup
   `Global\`-имя встречается только как пример значения `AppMutex`. Используйте имя без префикса
   или `Local\`, если приложение работает без прав администратора.
2. **Буквальное значение макроса `REGSTR_PATH_UNINSTALL`** — в issrc он только используется
   (`Setup.MainFunc.pas:368`), но не определён; определён в Delphi-модуле `RegStr`. Сам путь
   `...\Microsoft\Windows\CurrentVersion\Uninstall\<AppId>_is1` подтверждён справкой и кодом.
3. **Точная версия, в которой удалено значение `poweruser` у `PrivilegesRequired`** — факт наличия
   в 5.5.9 и отсутствия в 6.7.3/7.1.0 подтверждён, явной записи в `whatsnew.htm` нет.
4. **Точный путь установки Inno Setup на GitHub-hosted Windows-раннерах** — в
   `actions/runner-images` подтверждён только факт «InnoSetup 6.7.1» и установка через
   Chocolatey-пакет `innosetup`; путь в этих файлах не указан.
5. **Поведение `postinstall`-записей `[Run]` в silent-режиме** — выведено из исходников
   (`Setup.MainForm.pas:107` vs `Setup.WizardForm.pas:1415`), а не из явной фразы в справке.
   Направление вывода надёжное (в silent-режиме нет страницы завершения и нет `RunList`), но
   формальной цитаты справки нет.
6. **Код выхода 1 при `AppMutex` + `/SUPPRESSMSGBOXES`** — выведено из цепочки
   `LoggedMsgBox(Default=IDCANCEL)` → `Abort` → `except` в `Setup.Start.pas` → `Halt(ecInitializationError)`.
   В справке такого сценария нет. Рекомендую проверить эмпирически
   (`echo %ERRORLEVEL%` после запуска).
