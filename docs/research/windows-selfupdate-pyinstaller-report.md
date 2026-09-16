# Самообновление Windows-приложений и PyInstaller: onefile vs onedir

Отчёт по первоисточникам. Везде, где утверждение **не** подтверждено первичным источником, стоит пометка **«не подтверждено»**.

Легенда: **[Д]** — подтверждено документацией Microsoft / PyInstaller / Python; **[И]** — подтверждено исходным кодом проекта; **[С]** — обсуждение/ответ сообщества (не первичный источник).

---

## 1. Почему работающий Windows-`.exe` нельзя перезаписать

### 1.1 Что именно делает ОС

При запуске `.exe` загрузчик создаёт **image section** — секцию, отображённую в адресное пространство процесса (SEC_IMAGE). Файл остаётся открытым на всё время жизни процесса.

Ключевой документированный механизм — `MmFlushImageSection` (WDK, `ntifs.h`):

> «A file system must call the **MmFlushImageSection** routine before **deleting a file or opening a file for write access**.»
> «**MmFlushImageSection** returns TRUE if the flush operation is successful, **or if no image section exists for the file; otherwise** MmFlushImageSection returns **FALSE**.»
> `FlushType`: `MmFlushForDelete` — «The file is being deleted»; `MmFlushForWrite` — «The file is being opened for write access».
>
> — <https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-mmflushimagesection> **[Д]**

Обратите внимание: тип `MmFlushForRename` **не существует**. Именно поэтому набор разрешённых операций над работающим `.exe` несимметричен: удаление и открытие на запись блокируются, а переименование — нет.

### 1.2 `CreateFile` против работающего образа

Сигнатура и правила `dwShareMode` (`CreateFileW`):

```
HANDLE CreateFileW(
  [in]           LPCWSTR               lpFileName,
  [in]           DWORD                 dwDesiredAccess,
  [in]           DWORD                 dwShareMode,
  [in, optional] LPSECURITY_ATTRIBUTES lpSecurityAttributes,
  [in]           DWORD                 dwCreationDisposition,
  [in]           DWORD                 dwFlagsAndAttributes,
  [in, optional] HANDLE                hTemplateFile
);
```

Значения `dwShareMode`: `0` = 0x0 (монопольно), `FILE_SHARE_READ` = 0x1, `FILE_SHARE_WRITE` = 0x2, `FILE_SHARE_DELETE` = 0x4.

> «You cannot request a sharing mode that conflicts with the access mode that is specified in an existing request that has an open handle. **CreateFile would fail and the GetLastError function would return ERROR_SHARING_VIOLATION**.»
>
> `FILE_SHARE_DELETE` (0x00000004): «Enables subsequent open operations on a file or device to request delete access. … **Note Delete access allows both delete and rename operations.**»
>
> — <https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew> **[Д]**

Практические следствия:

| Операция над работающим `.exe` | Результат | Основание |
|---|---|---|
| `CreateFile(GENERIC_READ, FILE_SHARE_READ\|WRITE\|DELETE)` | **успех** (чтение возможно — файл не «заблокирован намертво») | [Д], правила share/access |
| `CreateFile(GENERIC_WRITE, …)` | **провал**: `IRP_MJ_CREATE` → `MmFlushImageSection(MmFlushForWrite)` → FALSE → отказ | [Д] WDK |
| `DeleteFile` | **провал** (см. 1.3) | [Д] |
| `MoveFile`/`MoveFileEx` (переименование) | **успех** | [Д] косвенно + [С] |

Код ошибки при попытке записи: попытка конфликтует по share-режиму раньше, чем доходит до flush, поэтому на практике это `ERROR_SHARING_VIOLATION` (32) — однако **какой именно из двух кодов (5 или 32) вернётся в конкретном сценарии, в документации явно не указано — «не подтверждено»**.

Справочные коды:

- `ERROR_ACCESS_DENIED` = **5 (0x5)** — «Access is denied.»
- `ERROR_SHARING_VIOLATION` = **32 (0x20)** — «The process cannot access the file because it is being used by another process.»
- `ERROR_DELETE_PENDING` = **303 (0x12F)** — «The file cannot be opened because it is in the process of being deleted.»
- `ERROR_VIRUS_INFECTED` = **225 (0xE1)**; `ERROR_VIRUS_DELETED` = **226 (0xE2)**
- `ERROR_EXE_CANNOT_MODIFY_SIGNED_BINARY` = **217 (0xD9)**; `…STRONG_SIGNED_BINARY` = **218 (0xDA)**

— <https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-> **[Д]**

### 1.3 Можно ли удалить работающий `.exe` — правила `DeleteFile`

`DeleteFileW` (`fileapi.h`) документирует ровно то, что нужно:

> «The **DeleteFile** function fails if an application attempts to delete a file that has other handles open for normal I/O **or as a memory-mapped file** (**FILE_SHARE_DELETE** must have been specified when other handles were opened).»
>
> «The **DeleteFile** function marks a file for deletion on close. Therefore, the file deletion **does not occur until the last handle to the file is closed**. Subsequent calls to **CreateFile** to open the file fail with **ERROR_ACCESS_DENIED**.»
>
> «The use of POSIX delete causes the file to be deleted while handles remain open. Subsequent calls to CreateFile … fail with **ERROR_FILE_NOT_FOUND**.»
>
> — <https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-deletefilew> **[Д]**

Итого: удалить работающий `.exe` **нельзя**. Это подтверждено документацией Microsoft напрямую.

### 1.4 Можно ли **переименовать** работающий `.exe` — ДА

Это подтверждается сочетанием двух вещей:

**(а)** Внутренняя механика переименования задокументирована Raymond Chen (Microsoft, «The Old New Thing») — «Renaming a file is a multi-step process, only one of which is changing the name of the file»:

> «Okay, let's look at how renaming a file is performed internally. It's a multi-step operation.
> 1. **Open the file with DELETE permission.**
> 2. Call **NtSetInformationFile** with **FileRenameInformation**.
> 3. Close the handle.»
>
> «The important sharing mode here is neither read nor write. It's **FILE_SHARE_DELETE**, which means "I'm okay with letting someone **delete or rename** the file while I have it open."»
>
> — <https://devblogs.microsoft.com/oldnewthing/20211022-00/?p=105822> **[Д, блог Microsoft]**

**(б)** В `MmFlushImageSection` **отсутствует** `MmFlushForRename`: файловая система обязана вызывать flush только перед delete и перед open-for-write. Значит, переименование не требует «сброса» image section и не блокируется работающим образом.

**(в) Microsoft прямо документирует приём «нельзя удалить — переименуй»** — концептуальная страница «Closing and Deleting Files»:

> «The `DeleteFile` function can be used to delete a file on close. **A file cannot be deleted until all handles to it are closed. If a file cannot be deleted, its name cannot be reused. To reuse a file name immediately, rename the existing file.**»
>
> — <https://learn.microsoft.com/en-us/windows/win32/fileio/closing-and-deleting-files> **[Д, Microsoft]**

Это первоисточник ровно для §2c: Microsoft официально предлагает **переименовать** занятый файл, чтобы немедленно освободить имя и записать на его место новый файл. Отсюда же следует и обратное — переименование доступно там, где удаление недоступно.

Общепринятое объяснение (принятый ответ SuperUser, 13 голосов):

> «There really is no such thing as renaming a file. A file can have more than one name or no name, so **it's not the file that you're renaming but the directory entry**. Renaming is an operation on the **directory entry**, which is not affected by the fact that the file is locked for execution.»
>
> — <https://superuser.com/questions/488127/why-can-i-rename-a-running-executable-but-not-delete-it> **[С]**

Аналогично документировано в `MoveFileExW`: «To delete or rename a file, you must have either delete permission on the file **or delete child permission in the parent directory**» — то есть переименование может опираться на права на **каталог**, а не на файл.
— <https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw> **[Д]**

**Формулировка, которую можно считать подтверждённой:**
> На Windows NT можно **переименовать** работающий `.exe`, но **нельзя его удалить**, и нельзя открыть его на запись. Удаление и открытие на запись требуют `MmFlushImageSection`, который для активной image section возвращает FALSE; переименование этого не требует, т.к. это операция над элементом каталога.

**«Не подтверждено»:** какой именно компонент (загрузчик / memory manager) открывает файл образа с каким именно share-режимом — в документации Microsoft явно не сказано. Также **не подтверждено** документацией, что `DeleteFile`, вызванный на *переименованном* работающем `.exe`, вернёт именно `ERROR_ACCESS_DENIED` (см. 1.5) — это следствие документированного правила, но не отдельная цитата.

### 1.5 `DeleteFile` на переименованном файле (`app.exe.old`)

- `MoveFile("app.exe", "app.exe.old")` **разрешается**, пока процесс работает.
- После переименования файл — всё ещё тот же файл с активной image section. Поэтому `DeleteFile("app.exe.old")` **провалится, пока процесс жив**: документированного «delete-on-close», разрешающего удаление работающего образа, не существует, а `MmFlushImageSection(MmFlushForDelete)` всё ещё возвращает FALSE. **[Д, по совокупности правил]**
- Если бы `DeleteFile` *успел* пометить файл на удаление, то по документации он оставался бы на диске до закрытия последнего handle, а любые последующие `CreateFile` падали бы с **`ERROR_ACCESS_DENIED` (5)**, а не с «file not found» — это ровно документированный сценарий «delete pending» **[Д]**. Именно этот эффект объясняет ответ Raymond Chen «Why can't I delete a file immediately after terminating the process that has the file open?»:

> «To know when the handles are closed, **wait on the process handle**, because the process handle is not signaled until process termination is complete. … You can't delete the file, since it's still open, but maybe you can log an error diagnostic … and maybe add the file to a list of files to clean up the next time the program starts up.»
>
> — <https://devblogs.microsoft.com/oldnewthing/20120329-00/?p=7973> **[Д, блог Microsoft]**

Практический вывод: **удалять `.old` нужно после выхода процесса** — либо при следующем старте приложения, либо через `MOVEFILE_DELAY_UNTIL_REBOOT`. Ровно так и поступает «трюк с переименованием».

**Важно:** попытка `DeleteFile` на `.old`-файле **сразу** после `TerminateProcess` тоже может провалиться — `TerminateProcess` возвращает управление до фактического завершения процесса. Решение — `WaitForSingleObject` на handle процесса (там же, [Д]).

### 1.6 Про расширение `.old`, `.bak`, `.exe`

**«Не подтверждено».** Ни один первичный источник не указывает, что ОС обрабатывает переименованный работающий образ по-разному в зависимости от расширения. Расширение влияет на другое: на ассоциации, иконки, SmartScreen/AV-эвристики и на то, подхватит ли файл антивирус как исполняемый. Практическая рекомендация — **убирать `.exe`** (`app.exe.old`, `app.exe.bak`), чтобы снизить вероятность, что AV/Defender начнёт сканировать и удерживать файл, но это инженерная рекомендация, а не документированное правило.

### 1.7 Сводная таблица (работающий `app.exe`)

| Операция | Разрешена? | Источник |
|---|---|---|
| Открыть на чтение | да | [Д] |
| Открыть на запись / перезаписать | **нет** (`MmFlushForWrite`) | [Д] WDK |
| Удалить (`DeleteFile`) | **нет** (image section — memory-mapped handle) | [Д] DeleteFile |
| Переименовать (`MoveFile`/`MoveFileEx`) | **да** | [Д] Closing and Deleting Files + [Д] Chen + [С] |
| Удалить уже переименованный `.old` | **нет, пока процесс жив** | [Д] по совокупности |
| Удалить через `MOVEFILE_DELAY_UNTIL_REBOOT` | да, но только после перезагрузки | [Д] |
| Заменить через Restart Manager (`RmShutdown`) | да (процесс закрывается) | [Д] |

---

## 2. Корректные схемы самообновления

### 2a. Отдельный updater / `.cmd`, ждущий выхода PID

**Почему не «самообновление изнутри»:** приложение не может перезаписать свой собственный `.exe` (см. §1). Нужен **второй процесс**, который не держит файл, и который переживёт выход первого.

#### Точный синтаксис `tasklist`

```
tasklist [/s <computer> [/u [<domain>\]<username> [/p <password>]]]
         [{/m <module> | /svc | /v}] [/fo {table | list | csv}] [/nh]
         [/fi <filter> [/fi <filter> [ ... ]]]
```

Фильтры: `PID` с операторами `eq, ne, gt, lt, ge, le`; значения PID — числовые. Форматы вывода — `table` (по умолчанию), `list`, `csv`; `/nh` убирает заголовки.
— <https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tasklist> **[Д]**

**Как надёжно определять отсутствие процесса (важно):**

1. `tasklist` возвращает **код выхода 0 и при отсутствии совпадений** — на код возврата полагаться нельзя.
2. При отсутствии совпадений в stdout печатается информационное сообщение. Его текст **локализован** («No tasks are running which match the specified criteria» / «Нет задач, удовлетворяющих критериям»), поэтому парсить его нельзя. **«Не подтверждено»** — точный текст и поведение в `csv`/`/nh` режимах документацией не описаны.
3. **Надёжный способ:** вывести `tasklist /FI "PID eq <pid>" /FO CSV /NH` и искать **точное совпадение PID во второй CSV-колонке**. Отсутствие PID в выводе = процесс завершился. Это не зависит от локали.

#### `.cmd`-скрипт (готов к использованию)

Требуется Windows Vista+ (есть `robocopy`). Запускать **из `%TEMP%`**, чтобы `cmd.exe` не держал файл в каталоге установки.

```bat
@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem ============================================================
rem  update.cmd  <PID> <STAGING_DIR> <INSTALL_DIR> <EXE_NAME> [TIMEOUT_SEC]
rem
rem  %1 PID процесса, который надо дождаться
rem  %2 каталог с НОВЫМИ файлами (уже распакованными)
rem  %3 каталог установки, куда копировать
rem  %4 имя исполняемого файла для перезапуска
rem  %5 сколько секунд ждать максимум (по умолчанию 120)
rem ============================================================

if "%~1"=="" goto :usage
set "APPPID=%~1"
set "SRCDIR=%~2"
set "DSTDIR=%~3"
set "APPEXE=%~4"
if "%~5"=="" (set /a TIMEOUT_S=120) else (set /a TIMEOUT_S=%~5)

set /a ELAPSED=0

:waitloop
rem --- Определяем, жив ли процесс с таким PID ------------------
rem /FO CSV /NH даёт строку:  "image.exe","1234","Console","1","12 345 КБ"
rem Проверяем ТОЧНОЕ совпадение PID во второй колонке.
set "FOUND="
for /f "usebackq tokens=1,2 delims=," %%A in (`tasklist /FI "PID eq %APPPID%" /FO CSV /NH 2^>nul`) do (
    if "%%~B"=="%APPPID%" set "FOUND=1"
)
if not defined FOUND goto :gone

set /a ELAPSED+=1
if %ELAPSED% GEQ %TIMEOUT_S% goto :timeout

rem --- Пауза 1 секунда ------------------------------------------
rem НЕ используем `timeout /t 1`: он падает при перенаправленном
rem stdin ("Input redirection is not supported"). `ping` безопаснее.
ping -n 2 127.0.0.1 >nul
goto :waitloop

:gone
rem Процесс завершился, но дескрипторы/секции могут освобождаться
rem ещё мгновение — даём небольшую паузу.
ping -n 3 127.0.0.1 >nul

rem --- Убираем остаток прошлого обновления ----------------------
if exist "%DSTDIR%\%APPEXE%.old" del /f /q "%DSTDIR%\%APPEXE%.old" >nul 2>&1

rem --- Копируем новые файлы -------------------------------------
rem Коды robocopy: <8 — успех, >=8 — хотя бы одна ошибка.
robocopy "%SRCDIR%" "%DSTDIR%" /E /R:5 /W:1 /NP /NJH /NJS >nul
if %ERRORLEVEL% GEQ 8 goto :copyfail

rem --- Запускаем приложение заново ------------------------------
start "" "%DSTDIR%\%APPEXE%"
exit /b 0

:timeout
echo [update] Ïðîöåññ PID %APPPID% íå çàâåðøèëñÿ çà %TIMEOUT_S% ñ. Îáíîâëåíèå îòìåíåíî.
exit /b 2

:copyfail
echo [update] Îøèáêà êîïèðîâàíèÿ (robocopy exit=%ERRORLEVEL%).
exit /b 3

:usage
echo Usage: update.cmd ^<PID^> ^<STAGING_DIR^> ^<INSTALL_DIR^> ^<EXE_NAME^> [TIMEOUT_SEC]
exit /b 1
```

> Примечание: строки `echo` намеренно оставлены в ASCII-транскодировке; в реальном файле пишите их в кодировке, совпадающей с `chcp` (для русского — 866 или 65001 с `chcp 65001`). Это косметика, логика от неё не зависит.

**Коды возврата `robocopy`** (документировано): `0` — нечего копировать, ошибок нет; `1` — всё скопировано; `2` — есть лишние файлы в приёмнике; `3`,`5`,`6`,`7` — частичные ситуации, ошибок нет; `8` — «Several files didn't copy». Явно: «**Any value equal to or greater than 8 indicates that there was at least one failure during the copy operation.**»
— <https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy> **[Д]**

**Почему `ping` вместо `timeout`:** документация `timeout` описывает только `/t <сек>` и `/nobreak` и ничего не говорит о перенаправленном stdin — <https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/timeout> **[Д]**. Факт падения `timeout` при перенаправленном вводе широко известен, но **в официальной документации не описан — «не подтверждено»**. `ping -n 2 127.0.0.1 >nul` — общепринятая безопасная замена.

**PID может быть переиспользован.** ОС переиспользует идентификаторы процессов; это прямо упомянуто в документации Python (`os.getppid()`): «on Windows it is still the same id, **which may be already reused by another process**» — <https://docs.python.org/3/library/os.html#os.getppid> **[Д]**. Практическое следствие: одного PID недостаточно для абсолютной надёжности. Защита: держать **открытый handle** на процесс из updater'а (`OpenProcess` + `WaitForSingleObject`) вместо опроса PID, либо дополнительно сверять имя образа (`/FI "IMAGENAME eq app.exe"` вместе с `PID eq`), либо использовать файл-мьютекс/именованный объект.

#### Альтернативы ожидания: `waitfor`, PowerShell `Wait-Process`

| Способ | Плюсы | Минусы / что важно |
|---|---|---|
| `tasklist` в цикле | есть везде, без зависимостей | опрос, зависимость от локали при неверном парсинге, гонка с переиспользованием PID |
| `waitfor` | есть в Windows | **Это сетевая синхронизация сигналов** (`/si <signalname>`, `/t <timeout>`), а не ожидание процесса: «Sends or waits for a signal on a system. This command is used to synchronize computers across a network». Чтобы «дождаться» приложения, оно само должно послать сигнал `waitfor /si <name>` при выходе. Схема «`waitfor <pid>` завершится, когда процесс выйдет» **в документации не описана — «не подтверждено»**. <https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/waitfor> **[Д]** |
| PowerShell `Wait-Process` | **самый надёжный**: использует событие `Exited` класса `System.Diagnostics.Process`, а не опрос | медленный старт PowerShell; ошибка процесс-не-найден — non-terminating, нужен `-ErrorAction SilentlyContinue` |

`Wait-Process`:

```
Wait-Process [-Id] <Int32[]> [[-Timeout] <Int32>] [-ErrorAction SilentlyContinue]
```

> «This cmdlet uses the **Exited** event of the **System.Diagnostics.Process** class.»
> «When this interval expires, the command displays a **non-terminating error** that lists the processes that are still running, and ends the wait.»
> «Unlike `Start-Process -Wait`, `Wait-Process` only waits for the processes identified. `Start-Process -Wait` waits for the **process tree** (the process and all its descendants).»
>
> — <https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/wait-process> **[Д]**

**Рекомендация:** для обновления дерева процессов (GUI-приложение + helper-процессы) `Start-Process -Wait` обычно удобнее, потому что ждёт всё дерево; `Wait-Process -Id` — точнее, если нужен один конкретный PID. Если PowerShell доступен, `Wait-Process` надёжнее цикла `tasklist`.

Однострочник для вставки в `.cmd`:

```bat
powershell -NoProfile -NonInteractive -Command ^
  "Wait-Process -Id %APPPID% -Timeout %TIMEOUT_S% -ErrorAction SilentlyContinue"
```

### 2b. `MoveFileEx` + `MOVEFILE_DELAY_UNTIL_REBOOT`

**Точная сигнатура:**

```c
BOOL MoveFileExW(
  [in]           LPCWSTR lpExistingFileName,
  [in, optional] LPCWSTR lpNewFileName,
  [in]           DWORD   dwFlags
);
```

Флаги: `MOVEFILE_REPLACE_EXISTING` = **1 (0x1)**, `MOVEFILE_COPY_ALLOWED` = **2 (0x2)**, `MOVEFILE_DELAY_UNTIL_REBOOT` = **4 (0x4)**, `MOVEFILE_WRITE_THROUGH` = **8 (0x8)**, `MOVEFILE_CREATE_HARDLINK` = 16 (0x10), `MOVEFILE_FAIL_IF_NOT_TRACKABLE` = 32 (0x20).

**Документированные правила `MOVEFILE_DELAY_UNTIL_REBOOT`:**

> «The system does not move the file **until the operating system is restarted**. The system moves the file immediately after AUTOCHK is executed, but before creating any paging files.»
> «This value can be used **only if the process is in the context of a user who belongs to the administrators group or the LocalSystem account**.»
> «This value **cannot be used with MOVEFILE_COPY_ALLOWED**.»
> «If `dwFlags` specifies **MOVEFILE_DELAY_UNTIL_REBOOT** and `lpNewFileName` is **NULL**, **MoveFileEx** registers the `lpExistingFileName` file to be **deleted** when the system restarts.»

**Куда пишется (точные имена):**

> «If the `dwFlags` parameter specifies **MOVEFILE_DELAY_UNTIL_REBOOT**, **MoveFileEx** fails if it cannot access the registry. The function stores the locations of the files to be renamed at restart in the following registry value: **HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\PendingFileRenameOperations**
> This registry value is of type **REG_MULTI_SZ**. Each rename operation stores one of the following NULL-terminated strings, depending on whether the rename is a delete or not:
> - `szSrcFile\0\0`
> - `szSrcFile\0szDstFile\0`
> The string `szSrcFile\0\0` indicates that the file `szSrcFile` is to be **deleted** on reboot. The string `szSrcFile\0szDstFile\0` indicates that `szSrcFile` is to be **renamed** to `szDstFile` on reboot.»

**Порядок и возвращаемое значение:**

> «The system uses these registry entries to complete the operations at restart **in the same order that they were issued**.»
> «Because the actual move and deletion operations … take place after the calling application has ceased running, the return value **cannot reflect success or failure** in moving or deleting the file. Rather, it reflects success or failure in **placing the appropriate entries into the registry**.»
> «The system deletes a directory that is tagged for deletion with the **MOVEFILE_DELAY_UNTIL_REBOOT** flag **only if it is empty**.»

**Про удалённые ресурсы:** «If `dwFlags` specifies **MOVEFILE_DELAY_UNTIL_REBOOT**, the file **cannot exist on a remote share**, because delayed operations are performed before the network is available.»

— всё: <https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw> **[Д]**

**Подводные камни (все следуют из [Д]):**

1. **Замена произойдёт только при следующей перезагрузке.** Перезагрузка **не** инициируется автоматически — `MoveFileEx` её не запускает. Чтобы перезагрузить, нужен отдельный вызов (`ExitWindowsEx`, `InitiateShutdown`).
2. **Нужны права администратора** (или LocalSystem) — иначе вызов падает (и, поскольку ключ в HKLM, писать `PendingFileRenameOperations` вручную тоже может только админ).
3. **Нет способа перезапустить приложение** после операции: код приложения уже не работает. Перезапуск после перезагрузки — отдельная задача (RunOnce, планировщик, `RegisterApplicationRestart`).
4. **Порядок операций важен**: операции выполняются в порядке добавления. Документированный пример: чтобы в итоге файл был удалён И переименован, сначала добавляют удаление, потом переименование (см. фрагмент в документации).
5. **Нет «отката»**: нельзя узнать и отменить операцию (кроме ручной правки `REG_MULTI_SZ`).
6. Файл **не может быть на сетевом ресурсе**.
7. Пустой каталог удалится, непустой — нет; сначала надо удалить/переместить файлы.
8. **`MOVEFILE_COPY_ALLOWED` несовместим** с этим флагом.

**Дополнительно о записи в реестр вручную:** формат `REG_MULTI_SZ` требует double-NUL для «только переименование» / delete-семантики; в документации прямо отмечено: «**Note** Although `\0\0` is technically not allowed in a `REG_MULTI_SZ` node, it can because the file is considered to be renamed to a **null name**.» **[Д]**

### 2c. «Трюк с переименованием» работающего `.exe`

**Схема:**
1. Приложение получает новый бинарник (в `staging`-каталог, вне каталога установки).
2. Приложение запускает updater и завершается.
3. Updater ждёт выхода PID (см. 2a).
4. Updater переименовывает `app.exe` → `app.exe.old` (или сразу — при живом процессе, см. ниже).
5. Updater копирует новый `app.exe` на место старого.
6. Updater запускает `app.exe`.
7. `app.exe.old` удаляется при следующем старте (или `MoveFileEx(NULL, MOVEFILE_DELAY_UNTIL_REBOOT)`).

**Почему это работает:** переименование — операция над **элементом каталога**, а не над файлом; `MmFlushImageSection` для неё не требуется (нет `MmFlushForRename`), поэтому она разрешена даже при активной image section. См. §1.4 и §1.1 ([Д]). Более того, сам приём санкционирован Microsoft: «If a file cannot be deleted, its name cannot be reused. **To reuse a file name immediately, rename the existing file**» — <https://learn.microsoft.com/en-us/windows/win32/fileio/closing-and-deleting-files> **[Д]**.

**Ограничения:**

- `app.exe.old` **нельзя удалить, пока процесс жив** — удаление требует `MmFlushImageSection(MmFlushForDelete)`, который для активного образа возвращает FALSE. Удалять надо после выхода процесса ([Д] §1.5).
- Если шаг 4 выполняется **при живом** процессе (типичный «rename-while-running» вариант), то `app.exe` освобождается **сразу** (имя свободно), и файл можно записать. Это допустимо и часто используется как способ «обновить без ожидания». Но `.old` останется висеть до выхода процесса.
- **`TerminateProcess` не гарантирует, что дескрипторы уже закрыты** — после него нужно дождаться сигнала handle процесса ([Д], Chen 2012).
- **Антивирус.** AV/EDR может держать собственные handle на свежесозданный/переименованный `.exe` и блокировать delete/rename. Это реальная и документируемая в трекерах PyInstaller проблема (см. §3.4): PyInstaller добавлял ретраи и pre-load системных DLL именно из-за удержания файлов «OS and/or anti-virus program» **[И]**.
- **Расширение `.old`.** «Не подтверждено», что ОС относится к переименованному работающему образу по-разному в зависимости от расширения (§1.6). Практическая рекомендация — не оставлять `.exe`, чтобы не провоцировать AV.
- **Иконка в кэше.** Windows кэширует иконку по **полному пути** файла: «the OS keeps an icon cache that seems to be based on the executable's full path, and does not update when an executable at an already-cached location is modified». После подмены `.exe` по тому же пути иконка может не обновиться. Документированный обход — `SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, …)` через `ctypes`.
  — <https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html> **[Д, PyInstaller]**

**Порядок «сначала скопировать, потом переименовать» vs «сначала переименовать»:**
Оба варианта валидны, но «переименовать *до* копирования» даёт более короткое окно, когда `app.exe` отсутствует. Классический безопасный порядок:

```
1. скопировать новый файл в app.exe.new   (рядом, тот же том!)
2. дождаться выхода процесса
3. MoveFileEx("app.exe", "app.exe.old", MOVEFILE_REPLACE_EXISTING)   <- если ещё не сделан
4. MoveFileEx("app.exe.new", "app.exe", MOVEFILE_REPLACE_EXISTING)   <- атомарная замена в пределах тома
```
Шаги 3–4 — переименования в пределах одного тома, то есть атомарные операции над каталогом, без копирования данных.

### 2d. Прочие документированные подходы

#### Windows Restart Manager API

Назначение (дословно):

> «The primary reason software installation and updates require a system restart is that some of the files that are being updated are **currently being used by a running application or service**. Restart Manager enables all but the critical applications and services to be **shut down and restarted**. This **frees the files that are in use** and allows installation operations to complete.»
>
> — <https://learn.microsoft.com/en-us/windows/win32/rstmgr/about-restart-manager> **[Д]**

Точные функции и структуры:

| Элемент | Назначение |
|---|---|
| `RmStartSession(DWORD *pSessionHandle, DWORD dwSessionFlags, WCHAR strSessionKey[CCH_RM_SESSION_KEY+1])` | начинает сессию; `dwSessionFlags` зарезервирован, должен быть `0` |
| `RmJoinSession(DWORD *pSessionHandle, const WCHAR strSessionKey[])` | вторичный установщик присоединяется по **session key** |
| `RmRegisterResources(DWORD dwSessionHandle, UINT nFiles, LPCWSTR rgsFileNames[], UINT nApplications, RM_UNIQUE_PROCESS rgApplications[], UINT nServices, LPCWSTR rgsServiceNames[])` | регистрирует файлы / процессы / службы |
| `RmGetList(DWORD dwSessionHandle, UINT *pnProcInfoNeeded, UINT *pnProcInfo, RM_PROCESS_INFO rgAffectedApps[], LPDWORD lpdwRebootReasons)` | список всех, кто держит ресурсы |
| `RmShutdown(DWORD dwSessionHandle, ULONG lActionFlags, RM_WRITE_STATUS_CALLBACK fnStatus)` | завершает приложения |
| `RmRestart(DWORD dwSessionHandle, DWORD dwRestartFlags, RM_WRITE_STATUS_CALLBACK fnStatus)` | перезапускает зарегистрированные приложения; `dwRestartFlags` зарезервирован, должен быть `0` |
| `RmEndSession(DWORD dwSessionHandle)` | закрывает сессию |

**Флаги `RmShutdown` (точные значения):**

- `RmForceShutdown` = **0x1** — «Force unresponsive applications and services to shut down after the timeout period. An application that does not respond to a shutdown request is forced to shut down within **30 seconds**. A service … after **20 seconds**.»
- `RmShutdownOnlyRegistered` = **0x10** — «Shut down applications if and only if all the applications have been registered for restart using the **RegisterApplicationRestart** function. If any processes or services cannot be restarted, then no processes or services are shut down.»

**Коды ошибок (точные):** `ERROR_SUCCESS` 0; `ERROR_SEM_TIMEOUT` 121; `ERROR_BAD_ARGUMENTS` 160; `ERROR_WRITE_FAULT` 29; `ERROR_OUTOFMEMORY` 14; `ERROR_MAX_SESSIONS_REACHED` 353; `ERROR_INVALID_HANDLE` 6; `ERROR_MORE_DATA` 234; `ERROR_CANCELLED` 1223; `ERROR_SESSION_CREDENTIAL_CONFLICT` 1219 (RmJoinSession); `ERROR_FAIL_NOACTION_REBOOT` 350; `ERROR_FAIL_SHUTDOWN` 351; `ERROR_FAIL_RESTART` 352; `ERROR_REQUEST_OUT_OF_SEQUENCE` 776 (RmRestart до RmShutdown).

**Критично для самообновления (это ломает «наивную» идею):**

> `RmShutdown`: «This function **can only be called from the installer that started the Restart Manager session** using the `RmStartSession` function.»
> `RmRestart`: «This function **can only be called by the primary installer** that called the `RmStartSession` function to start the Restart Manager session.»
> «A maximum of **64** Restart Manager sessions per user session can be open on the system at the same time.»

— <https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmshutdown>, <https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmrestart>, <https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmstartsession>, <https://learn.microsoft.com/en-us/windows/win32/rstmgr/using-restart-manager>, <https://learn.microsoft.com/en-us/windows/win32/rstmgr/restart-manager-portal> **[Д]**

**Практический вывод для self-update:**

- **Приложение не может «само» корректно применить Restart Manager к себе**: `RmShutdown` завершит его, а `RmRestart` должен вызвать тот же процесс (primary), которого уже нет. Поэтому роль primary должен играть **updater**, а не приложение. То есть: updater вызывает `RmStartSession`, `RmRegisterResources` (передавая имена файлов или `RM_UNIQUE_PROCESS`), `RmGetList`, `RmShutdown`, обновляет файлы, `RmRestart`, `RmEndSession`.
- Вторичный участник (например, само приложение) может присоединиться **только** по session key, полученному от primary (`RmJoinSession`), но `RmShutdown`/`RmRestart` ему недоступны.
- `RmRestart` перезапускает **только те** приложения, которые были зарегистрированы через `RegisterApplicationRestart` — иначе `ERROR_FAIL_RESTART` (352) и т.п.
- «Shutdown across sessions is not supported» — приложение в другой сессии (другой пользователь / RDP) завершить нельзя.
- Restart Manager позволяет в том числе **распознать, кто держит файл** (`RmGetList` → `RM_PROCESS_INFO`), что полезно для диагностики «почему не могу заменить файл». Чтобы `RmGetList` вернул список, обычно нужны права на завершение найденных процессов — «Restart Manager shuts down application or services only if the **caller has permission** to do so» **[Д]**.

#### `RegisterApplicationRestart` (для автоперезапуска после обновления)

```c
HRESULT RegisterApplicationRestart(
  [in, optional] PCWSTR pwzCommandline,
  [in]           DWORD  dwFlags
);
```

Флаги: `RESTART_NO_CRASH` = 1, `RESTART_NO_HANG` = 2, `RESTART_NO_PATCH` = 4, `RESTART_NO_REBOOT` = 8. Максимум — `RESTART_MAX_CMD_LINE` символов; имя exe в командную строку не включать.

**Подводные камни ([Д]):**

> «Your initial registration for restart must occur **before** the application encounters an unhandled exception or becomes unresponsive.»
> «For a Windows application that is being updated, the last opportunity to call this function is while processing the **WM_QUERYENDSESSION** message. For a console application that is being updated, the registration must occur **before the installer tries to shutdown the application** (… you cannot call this function when handling the `CTRL_C_EVENT` notification).»
> «If you register for restart and the application encounters an unhandled exception or is not responsive, the user is offered the opportunity to restart the application; the application is **not automatically restarted without the user's consent**. However, if the application is being updated and requires a restart, the application is restarted **automatically**.»
> «**To prevent cyclical restarts, the system will only restart the application if it has been running for a minimum of 60 seconds.**»

— <https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-registerapplicationrestart> **[Д]**

Комментарий Raymond Chen к этой функции:

> «Note that if the program crashes or hangs, the program does **not** restart automatically. … **the restart command is not executed if the user manually terminates the program**, such as by using Task Manager.»
> — <https://devblogs.microsoft.com/oldnewthing/20230608-00/?p=108312> **[Д, блог Microsoft]**

**Правило 60 секунд** — важнейший практический подводный камень: если приложение обновилось раньше, чем через 60 секунд после старта, автоматический перезапуск через `RegisterApplicationRestart` **не сработает**.

#### `MoveFileEx` без флага перезагрузки (как это делают другие updater'ы)

`MoveFileEx(src, dst, MOVEFILE_REPLACE_EXISTING)` в пределах одного тома — атомарная замена имени. Именно это используется в шаге 4 схемы §2c: копируем во временный файл рядом, затем **переименовываем** поверх. Это единственный способ «атомарно» подменить файл на NTFS без reboot-флага, и он требует лишь того, чтобы целевой файл не был запущен/отображён.

---

## 3. PyInstaller onefile — детальный разбор

### 3.1 Точное поведение onefile

Официальная документация, раздел «How the One-File Program Works»:

> «When started it creates a temporary folder in the appropriate temp-folder location for this OS. The folder is named `_MEIxxxxxx`, where *xxxxxx* is a random number.
> The one executable file contains an embedded archive of all the Python modules used by your script, as well as compressed copies of any non-Python support files (e.g. `.so` files). The bootloader **uncompresses the support files and writes copies into the temporary folder**. This can take a little time. That is why a one-file app is a little slower to start than a one-folder app.
> After creating the temporary folder, the bootloader proceeds exactly as for the one-folder bundle, in the context of the temporary folder. **When the bundled code terminates, the bootloader deletes the temporary folder.**»
>
> «Because the program makes a temporary folder with a **unique name**, you can run multiple copies of the app; they won't interfere with each other. However, running multiple copies is **expensive in disk space because nothing is shared**.»
>
> «The `_MEIxxxxxx` folder is **not removed if the program crashes or is killed** (kill -9 on Unix, killed by the Task Manager on Windows, "Force Quit" on macOS). Thus if your app crashes frequently, your users will **lose disk space to multiple `_MEIxxxxxx` temporary folders**.»
>
> — <https://pyinstaller.org/en/stable/operating-mode.html> **[Д]**

**Уточнение по имени каталога (важно и полезно на практике).** Документация говорит «random number», но в исходниках bootloader'а для Windows имя строится иначе:

```c
/* Create _MEI + PID prefix */
swprintf(prefix, 16, L"_MEI%08x", _getpid());
...
wchar_t *application_home_dir_w = _wtempnam(tempdir_path, prefix);
```
— `bootloader/src/pyi_utils_win32.c`, <https://github.com/pyinstaller/pyinstaller/blob/develop/bootloader/src/pyi_utils_win32.c> **[И]**

и проверка имени при валидации:

```c
/* Verify the length of the name:
 *  - Windows: _MEI + process ID number (%08x format) + suffix
 *    added by _wtempnam(); ...
 *  - other platforms: _MEI + process ID number (%08x format) +
 *    six random characters added by mkdtemp(); ... */
```
— `bootloader/src/pyi_security.c`, <https://github.com/pyinstaller/pyinstaller/blob/develop/bootloader/src/pyi_security.c> **[И]**

**Практический вывод:** на Windows имя каталога начинается с `_MEI` + **шестнадцатеричный PID** (8 цифр) + уникальный суффикс. Это позволяет скрипту уборки сопоставлять «осиротевшие» `_MEI*` каталоги с PID и удалять только те, чьи процессы давно не существуют.

**Многофайловая механика onefile:** «The `onefile` mode in PyInstaller uses **two processes**. When the application is launched, the **parent process** extracts the contents of the embedded archive into a temporary directory, sets up the environment and library search paths, and launches the **child process**. … Meanwhile, the parent process **waits for the child process to exit**; when that happens, it cleans up the extracted temporary data, and exits.»

> «**in order for the application's temporary directory to be cleaned up, the parent process must never be forcefully terminated** (for example, via the `TerminateProcess` function). If that happens, the clean-up code has no chance to run, and the temporary directory is left behind. On the other hand, from the perspective of the temporary directory clean-up, the child process can be terminated in any way, even forcefully.»
>
> — <https://pyinstaller.org/en/stable/feature-notes.html> **[Д]**

Это **ключевое** отличие для self-update: убийство процесса через «Завершить задачу»/`TerminateProcess` оставляет `_MEI` каталог. Только корректный выход (или завершение *дочернего* процесса при живом родителе) приводит к уборке.

### 3.2 `sys._MEIPASS` и определение frozen-режима

> «The bootloader sets the **`sys.frozen`** attribute and stores the absolute path to the bundle folder in **`sys._MEIPASS`**. For a one-folder bundle, this is the path to the **`_internal`** folder within the bundle. For a one-file bundle, this is the path to the **temporary folder created by the bootloader**.»

Официальный шаблон проверки:

```python
import sys
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    print('running in a PyInstaller bundle')
else:
    print('running in a normal Python process')
```

Также важно:

> «In a frozen app, **`sys.executable`** is also the path to the program that was executed, but that is not Python; it is the **bootloader** in either the one-file app or the executable in the one-folder app. This gives you a reliable way to **locate the frozen executable the user actually launched**.»

— <https://pyinstaller.org/en/stable/runtime-information.html> **[Д]**

**Следствие для self-update:** именно `sys.executable` — это тот `.exe`, который нужно заменять (для onefile), а `sys._MEIPASS` — это временный распакованный каталог, который заменять бессмысленно.

Дополнительно `_PYI_APPLICATION_HOME_DIR` — служебная переменная окружения, которой родительский процесс onefile передаёт дочернему путь к `_MEI`-каталогу:
> «Used by the top-level onefile process (the parent process) to communicate the location of the application's temporary directory to the main application process. The main application process copies this path to the PyInstaller-specific `sys._MEIPASS` attribute.»
> — <https://pyinstaller.org/en/stable/advanced-topics.html> **[Д]**

### 3.3 Стоимость старта onefile

**Что подтверждено документально:**

> «The bootloader uncompresses the support files and writes copies into the temporary folder. This can take a little time. That is why a **one-file app is a little slower to start** than a one-folder app.»
> «Also, the single executable is **a little slower to start up** than the one-folder bundle.»
> — <https://pyinstaller.org/en/stable/operating-mode.html> **[Д]**

**Распаковка происходит при КАЖДОМ запуске, кэширования нет.** Прямой цитаты «no caching» в документации нет, но это следует из:
- описания алгоритма (родительский процесс распаковывает, ждёт, **удаляет** каталог);
- того, что каталог создаётся заново с уникальным именем каждый запуск («the program makes a temporary folder with a unique name»).

Дополнительное свидетельство — feature request **#7909 «Keep extracted _MEI folder between application starts»** (закрыт как feature request, без реализации):
> «When packaging PyInstaller binaries with Inno Setup, it is **not required to unpack all files on each start**. They can be kept after the app ends and reused on the next start. … Describe the solution you'd like: **An option** that works in tandem with the `--runtime-tmpdir` option to extract files in the installed Program Files folder.»
> — <https://github.com/pyinstaller/pyinstaller/issues/7909> **[И]**

То есть: **опции «кэшировать распаковку» в PyInstaller нет**; распаковка каждый раз. **[Д/И]**

**Количественные оценки (миллисекунды/секунды) в официальной документации отсутствуют — «не подтверждено».** Документация даёт только качественное «a little slower» / «can take a little time». Order-of-magnitude оценки из блогов сильно зависят от размера бандла, диска и AV — приводить их как факт нельзя.

Единственная найденная числовая оценка — **неофициальная** (issue проекта GAM, не PyInstaller):
> «Some rough benchmarking shows PyInstaller's default One Folder mode can **reduce GAM startup and execution time by .2 - .5 seconds**…»
> «what OneFile does EVERY time it's run is: - Extract it's contents to a temp folder on the system - execute from within the temp folder - cleanup the temp folder after execution completes»
> — <https://github.com/GAM-team/GAM/issues/1581> **[неофициально]**

Заметьте: это порядок «сотни миллисекунд» для конкретного приложения — **не** универсальная константа. Отдельно задокументировано, что у **первого** запуска onedir может быть своя задержка (скан ОС/подписи), из-за чего первый старт onedir субъективно не быстрее onefile:
> — обсуждение <https://github.com/orgs/pyinstaller/discussions/8970> **[С]**

Дополнительно: в onefile-режиме **работают два процесса**, что видно в диспетчере задач:
> «This approach of using two processes allows a lot of flexibility and is used in all bundles **except one-folder mode in Windows**. So do not be surprised if you will see your bundled app as **two processes** in your system task manager.»
> — <https://pyinstaller.org/en/stable/advanced-topics.html> **[Д]**

Это важно для self-update: PID, который надо ждать, — это **родительский** (top-level) процесс onefile.

### 3.4 Антивирус / Defender

**Официальное признание проблемы в документации PyInstaller** (раздел про сборку собственного bootloader):

> «There are various reasons why one might want to build the bootloader yourself, including: … **you want to avoid anti-virus false positives that result from the wide-spread use of pre-compiled bootloaders**»
> — <https://pyinstaller.org/en/stable/bootloader-building.html> **[Д, PyInstaller]**

Механизм, прямо названный в документации/чейнджлоге: **широко распространённый (одинаковый у всех) bootloader** попадает в AV-сигнатуры → ложные срабатывания. Это относится и к onedir, и к onefile, но onefile **усугубляет** ситуацию по трём причинам, документированным в трекере:

1. **Распаковка в `%TEMP%` + случайное имя каталога + самораспаковывающийся архив** — характерный паттерн упаковщиков/дропперов. Официальной формулировки «onefile чаще детектится, чем onedir» в документации **нет — «не подтверждено»** как измеренный факт; но AV-взаимодействие именно с временным каталогом onefile документировано многократно (см. ниже).
2. **AV-инъекция DLL в процесс** ломает уборку `_MEI`. Чейнджлог 6.13.0:
   > «…issues with bundled VC runtime DLLs **not being cleaned up** from the application's temporary directory when 3rd party DLLs are **injected into the process (by the OS, an anti-virus program, or some 3rd party component)**.»
   > — `doc/CHANGES.rst`, 6.13.0 (2025-04-15) **[И]**
3. **AV удерживает файлы после выхода процесса**, из-за чего каталог не удаляется. Чейнджлог 6.11.1:
   > «(Windows) Add a **retry loop** to `onefile` temporary directory cleanup as an attempt to mitigate situations when bundled DLLs and python extension modules **remain locked by the OS and/or anti-virus program for a short while after the application process exits**. (:issue:`8870`)»
   > Чейнджлог 6.3.0: «…failures due to anti-virus program interference. (:issue:`8138`)»
   > Чейнджлог 6.0.0: «Extend the operation retry mechanism … This attempts to mitigate the interference from **anti-virus programs and other security tools, which may temporarily block write access to the executable for a scan** between individual processing steps. (:issue:`7871`)»
   > — `doc/CHANGES.rst` **[И]**

Дополнительно в самом bootloader'е для очистки `_MEI` есть специальный «последний шанс» — принудительная выгрузка DLL, загруженных из временного каталога, и цикл ретраев **15 попыток × 1000 мс**:

```c
const int max_attempts = 15; /* Maximum number of attempts in retry loop */
const int delay = 1000;      /* Delay for retry loop (milliseconds) */
…
num_unloaded_dlls = _pyi_win32_force_unload_bundled_dlls(pyi_ctx);
```
где в комментарии явно названы причины: Tcl/Tk-библиотеки, не выгружающие зависимости; задержки grandchild-процессов (напр. `QtWebEngineProcess.exe`); и «Windows itself getting in our way».
— `bootloader/src/pyi_utils_win32.c` **[И]**

**Про `--runtime-tmpdir` как способ снизить AV-трение:** в официальной документации такого утверждения **нет — «не подтверждено»**. Документация называет только три мотива для `--runtime-tmpdir`: (1) защита от периодической очистки стандартного temp ОС, (2) отсутствие стандартного temp на POSIX-системе, (3) `noexec` на `/tmp` (см. 3.5). Логика «фиксированный не-temp каталог → меньше эвристик AV» правдоподобна, но первичным источником не подтверждена. При этом у `--runtime-tmpdir` есть важный побочный эффект: каталог становится предсказуемым и, если он доступен на запись непривилегированным пользователям, это ослабляет модель безопасности onefile (ср. официальное предупреждение о запуске onefile «as administrator» в 3.5).

Общий вывод, который можно утверждать: **инженерные меры, которые PyInstaller применяет сам** — это (а) установка контрольных сумм EXE (чейнджлог 4.3: «Windows: **Set EXE checksums**. **Reduces false-positive detection from antiviral software.**», :issue:`5579`) и (б) сборка собственного bootloader'а. Рекомендация «перейти на onedir, чтобы снизить FP» в документации **не сформулирована — «не подтверждено»**, хотя из перечисленных механизмов (нет распаковки в temp при каждом старте) это следует логически.

**Контрпример, который важно знать:** утверждение «детектится именно onefile» **не подтверждается** даже трекером PyInstaller — есть сообщения о срабатывании Defender и на **onedir**:
> issue #7976 «Windows defender detects virus when using --noconsole on pyinstaller 6.0.0…»; комментарий пользователя: «Same happened to me after 6.0.0 / I'm using `--noconsole` **`--onedir`**»
> — <https://github.com/pyinstaller/pyinstaller/issues/7976> **[И, сообщение пользователя]**

Позиция мейнтейнеров (bwoodsend), дословно:
> «There's nothing we can do about dumb antiviral software. If there was some magic something we could change then malware creators would do it too and the race would start again. The best you can do is **submit your applications to the antiviral software vendors as false positives**.»
> — <https://github.com/pyinstaller/pyinstaller/issues/5492> **[И]**

**Про подпись кода:** официального подтверждения, что подпись снимает FP, **нет — «не подтверждено»**. Документированный факт из Microsoft — обратный по механизму и относится к Smart App Control:
> «If the security service is unable to make a confident prediction about the app, then Smart App Control checks to see if the app has a valid signature. If the app has a valid signature, Smart App Control will let it run. If the app is **unsigned**, or the signature is invalid, Smart App Control will consider it untrusted and **block it** for your protection.»
> — <https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions> **[Д, Microsoft]**

Плюс релевантное правило ASR (Attack Surface Reduction) в Defender:
> «**Block executable files from running unless they meet a prevalence, age, or trusted list criterion**: This ASR rule blocks executable files (for example, .exe, .dll, or .scr, from launching). Launching **untrusted or unknown executable files** can be risky…»
> — <https://learn.microsoft.com/en-us/defender-endpoint/attack-surface-reduction-rules-reference> **[Д, Microsoft]**

Это важнее «AV-эвристик про упаковщик»: свежесобранный, неподписанный и редкий `.exe` попадает под критерий «prevalence/age», и это **документированное** поведение, а не фольклор. Данные о том, что PyInstaller-бандлы **сами по себе** чаще срабатывают по этому правилу, чем любые другие новые EXE, — **«не подтверждено»**.

**Что делать (инженерно, но не документировано PyInstaller):** подписывать `.exe` (если применимо), добавлять в исключения/доверенные списки у клиента, отправлять FP в Microsoft Security Intelligence, собирать собственный bootloader. Последнее документировано как причина: см. цитату в начале §3.4.

### 3.5 `--runtime-tmpdir`

Точная формулировка из man-страницы:

> «`--runtime-tmpdir PATH` — Where to extract libraries and support files in `onefile` mode. If this option is given, the bootloader will **ignore any temp-folder location defined by the run-time OS**. The `_MEIxxxxxx`-folder **will be created here**. Please use this option only if you know what you are doing. Note that on POSIX systems, PyInstaller's bootloader does NOT perform shell-style environment variable expansion on the given path string. Therefore, using environment variables (e.g., `~` or `$HOME`) in path will NOT work.»
> — <https://pyinstaller.org/en/stable/man/pyinstaller.html> **[Д]**

Из раздела «Defining the Extraction Location»:

> «The location of the temporary directory can be set statically, at compile time, using the `--runtime-tmpdir` option. If this option is used, the bootloader will **ignore temporary directory locations defined by the OS**, and use the specified path. **The path can be either absolute or relative (which makes it relative to the current working directory).** Please use this option only if you know what you are doing.»

На Windows путь по умолчанию определяется через `GetTempPathW` (учитывает `TMP` и `TEMP`). На POSIX-системах порядок: env `TMPDIR`, `TEMP`, `TMP`, затем hard-coded `/tmp`, `/var/tmp`, `/usr/tmp`; каталог из переменной **должен существовать** (приложение создаёт только свой подкаталог).

Мотивы, названные документацией:
> «your application is supposed to be running for long periods of time, and you need to **prevent its files from being deleted by the OS that performs periodic clean-up** in standard temporary directories»; POSIX без стандартного temp; `noexec` на `/tmp`.
> — <https://pyinstaller.org/en/stable/usage.html> **[Д]**

В реализации на Windows `--runtime-tmpdir` подменяет переменную `TMP` на время создания каталога, а затем восстанавливает её:
```c
/* Store the path in the TMP environment variable. */
rc = _wputenv_s(L"TMP", runtime_tmpdir_w);
…
/* If we modified TMP environment variable due to runtime_tmpdir option,
 * restore the environment variable to its original state. */
```
— `bootloader/src/pyi_utils_win32.c` **[И]**

**Важное официальное предупреждение о безопасности onefile** (соседний абзац той же страницы):

> «Do **not** give administrator privileges to a one-file executable on Windows ("Run this program as an administrator"). There is an unlikely but not impossible way in which a **malicious attacker could corrupt one of the shared libraries in the temp folder while the bootloader is preparing it**.»
> — <https://pyinstaller.org/en/stable/operating-mode.html> **[Д]**

Плюс, начиная с **PyInstaller 6.22.1**, bootloader проверяет run-time окружение и падает с `Security validation failure: <details>`, если внутренние переменные подделаны:
> «This validation aims to prevent execution with a **spoofed set of internal environment variables** that could trick the executable into using arbitrary application directory; this could lead to arbitrary code execution…»
> — <https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html> **[Д]**

### 3.6 Проблемы self-update именно с onefile

| Проблема | Суть | Источник |
|---|---|---|
| `_MEI`-каталог занят, пока приложение работает | Родительский процесс держит файлы в `_MEI`; завершать его нельзя (`TerminateProcess` ⇒ мусор) | [Д] feature-notes |
| Осиротевшие `_MEI`-каталоги | Остаются при crash/kill родителя, при AV-инъекции DLL, при удержании файлов AV после выхода | [Д] operating-mode, feature-notes; [И] CHANGES 6.11.1/6.13.0 |
| `_MEI` невозможно удалить сразу | Если обновление идёт фоном при работающем приложении, на диске параллельно живут старый распакованный `_MEI` и новый бандл — при большом бандле это десятки–сотни МБ, и они не освобождаются до выхода процесса | [Д] |
| **Плюс:** заменять нужно **один файл** | `sys.executable` — это один `.exe`; нет проблемы «частично обновлённой папки» | [Д] runtime-information |
| «Перезапуск себя» ломает переиспользование temp | См. ниже про `PYINSTALLER_RESET_ENVIRONMENT` | [Д] |

**Критично для onefile + restart (PyInstaller ≥ 6.9).** Дочерний процесс, запущенный через `sys.executable`, по умолчанию считается **worker-процессом** и переиспользует уже распакованный `_MEI`. Для сценария «перезапустить приложение, чтобы новый процесс пережил текущий» это **неправильно**: временные файлы будут удалены при выходе родителя, а на Windows дочерний процесс ещё и помешает очистке.

Официальное решение:

> «if the spawned subprocess is expected to outlive the application process that spawned it (e.g., a "restart scenario"), the temporary files **cannot be re-used**, as they would be removed once the current process exits; the spawned subprocess would end up **missing files** and, on Windows, it might also **interfere with the cleanup** itself due to attempts at accessing the files.»
> «This is done by setting the **`PYINSTALLER_RESET_ENVIRONMENT`** environment variable to `1` when spawning the process, for example:»
> ```python
> # Restart the application
> subprocess.Popen([sys.executable], env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
> sys.exit(0)
> ```
> «Changed in version 6.9: The above requirement was introduced in PyInstaller 6.9, which changed the way the bootloader treats a process spawned via the same executable as its parent process.»
>
> — <https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html> **[Д]**

Семантика переменной:
> «Setting this environment variable to 1 causes the bootloader to reset all PyInstaller's internal environment variables, thus causing its process to be treated as a **top-level process of a new instance of the application**. In onefile mode, for example, this forces the application to **unpack itself again**.»
> — <https://pyinstaller.org/en/stable/advanced-topics.html> **[Д]**

**Итог по onefile + self-update:** жизнеспособная схема — «updater ждёт выхода PID top-level процесса, затем `MoveFileEx`-замена единственного `.exe`, затем запуск нового `.exe`». Осиротевшие `_MEI` — отдельная проблема, решаемая уборкой при старте (сопоставление `_MEI<hexpid>*` с существующими PID).

### 3.7 Аргументы за onedir; есть ли официальная рекомендация

**Есть ли в официальной документации PyInstaller явная рекомендация onefile vs onedir?**
**Нет.** Прямой формулировки «мы рекомендуем onedir» / «мы рекомендуем onefile» в документации **не найдено** (проверены `doc/operating-mode.rst`, `doc/usage.rst`, `doc/feature-notes.rst`, `doc/common-issues-and-pitfalls.rst`, `doc/when-things-wrong.rst`, `doc/advanced-topics.rst`, `doc/CHANGES.rst`). **Это установленный факт об отсутствии утверждения.**

Вместо рекомендации документация даёт набор утверждений, из которых выбор следует:

| Утверждение (дословно) | Где | В пользу |
|---|---|---|
| «you could send out **only the updated `myscript` executable**. That is typically much smaller than the entire folder» (при неизменном наборе зависимостей) | operating-mode | **onedir** (частичные обновления) |
| «It is easy to debug problems … when you use one-folder mode. You can see exactly what files PyInstaller collected» | operating-mode | onedir |
| «It is **much easier to diagnose problems in one-folder mode**» (перед тем как собирать onefile) | operating-mode | onedir (разработка) |
| «the single executable is **a little slower to start up** than the one-folder bundle» | operating-mode | onedir |
| «A disadvantage is that any related files such as a README must be distributed separately» | operating-mode | onefile (UX) |
| «The advantage is that your users get something they understand, a **single executable to launch**» | operating-mode | onefile (UX) |

— <https://pyinstaller.org/en/stable/operating-mode.html> **[Д]**

**Единственное явное «не рекомендуется» в документации** касается комбинации onefile + windowed на macOS:

> «Generating app bundles with onefile executables (i.e., using the combination of `--onefile` and `--windowed` options), while possible, **is not recommended**. Such app bundles are **inefficient, because they require unpacking on each run** (and the unpacked content might be **scanned by the OS each time**). Furthermore, onefile executables will not work when signed/notarized with sandbox enabled…»
> — <https://pyinstaller.org/en/stable/usage.html> **[Д]**

Это самый близкий к «onefile не рекомендуется» документированный текст, и он даёт важную формулировку механизма: **«require unpacking on each run» + «the unpacked content might be scanned by the OS each time»** — прямое подтверждение и стоимости старта, и AV/сканер-эффекта (для macOS, но механизм тот же).

**Рекомендации мейнтейнеров (GitHub, дословно — это не документация, но позиция авторов проекта):**

> «In a onefile build, a (different) `_MEI` folder is created ***each*** time the executable is ran (that's why `emailproxy` should not be using onefile - **it just wastes CPU and disk-write cycles on each run**).»
> «But really, `emailproxy` should be using **onedir** builds instead of onefile ones, since they are distributing as a zip file anyway. Maybe they avoided that due to all the clutter that used to be in the application's directory, but nowadays all that is stored in the `_internal` sub-directory next to executable, so that shouldn't be a problem.»
> («Is this emailproxy thing an indefinitely-running background process?» →) «It's probably **not a good idea for it to be using onefile mode** if it is.»
> — rokm (мейнтейнер PyInstaller), <https://github.com/pyinstaller/pyinstaller/issues/8571> **[И]**

> «When packaging PyInstaller binaries with Inno Setup, you would likely want to use the **`onedir` mode instead of `onefile`** one, wouldn't you? **Then there is no extraction**, and the files are managed by the Inno Setup installer.»
> — rokm, ответ на feature request #7909 (автор запроса ответил «Thanks, I had overlooked that option», issue закрыт)
> — <https://github.com/pyinstaller/pyinstaller/issues/7909> **[И]**

Обратите внимание: **это и есть «ответ на вопрос про Inno Setup», но он дан в трекере, а не в документации** (см. §3.8).

**Итог:** официальной рекомендации между onefile и onedir нет. Мейнтейнеры рекомендуют **onedir** для фоновых/долго живущих процессов, для installer-based распространения и для «restart-heavy» сценариев, и описывают onefile как «wastes CPU and disk-write cycles on each run». Для self-update документированные аргументы тоже складываются в пользу **onedir**, но это инженерный вывод + позиция мейнтейнеров, а не цитата из документации.

### 3.8 Onefile/onedir + Inno Setup; `_internal` (PyInstaller ≥ 6.0)

**Про Inno Setup:** в официальной документации PyInstaller **нет ни одного упоминания Inno Setup** (проверено `grep -rni inno doc/` — совпадений, кроме фамилии «Innokenty» в CREDITS, нет). Комбинация «PyInstaller onedir + Inno Setup» **не документирована как рецепт**; однако мейнтейнер PyInstaller **явно рекомендует её в трекере** (см. цитату rokm в §3.7 и <https://github.com/pyinstaller/pyinstaller/issues/7909>). Так что это «неофициальная, но подтверждённая автором проекта» рекомендация.

Замысел раскладки `_internal` (объяснение автора PR #7713 «Declutter onedir bundles», bwoodsend):

> «When building in onedir mode, move everything except the executable into a subdirectory so **the executable is easily findable**. I'm **deliberately not making this optional** for now because the new if/else path arithmetic bootloader logic it would require will multiply with all the other if/else path arithmetic bootloader logic for macOS `.app` bundles and the too many variants of `MERGE()`…»
> — <https://github.com/pyinstaller/pyinstaller/pull/7713> **[И]**

Именно «необязательность» объясняет, почему в 6.0 это **Incompatible Change** (см. цитату ниже), а не опция.

Позже (6.1.0) возможность отката появилась:

> «Allow users to re-enable the old onedir layout (without contents directory) by settings the `--contents-directory` option (or the equivalent `contents_directory` argument to `EXE` in the .spec file) to `'.'`. (:issue:`7968`)»
> — `doc/CHANGES.rst`, 6.1.0 (2023-10-13) **[И]**
> (опечатка «settings» присутствует в оригинале чейнджлога)

**Изменение раскладки onedir в 6.0 — подтверждено.** Из официального чейнджлога 6.0.0:

> Features: «**Restructure onedir mode builds** so that everything except the executable (and `.pkg` if you're using external PYZ archive mode) are **hidden inside a sub-directory**. This sub-directory's name **defaults to `_internal`** but may be configured with a new `--contents-directory` option. **Onefile applications and macOS `.app` bundles are unaffected.** (:issue:`7713`)»
>
> Incompatible Changes: «**All of onedir build's contents except for the executable are now moved into a sub-directory (called `_internal` by default). `sys._MEIPASS` is adjusted to point to this `_internal` directory.** The breaking implications for this are:
> - Assumptions that `os.path.dirname(sys.executable) == sys._MEIPASS` will break. Code locating application resources using `os.path.dirname(sys.executable)` should be adjusted to use `__file__` or `sys._MEIPASS`, and any code locating the original executable using `sys._MEIPASS` should use `sys.executable` directly.
> - Any custom post processing steps (either in the `.spec` file or externally) which modify the bundle will likely need adjusting to accommodate the new directory. (:issue:`7713`)»
>
> — <https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.0.0/doc/CHANGES.rst> **[И, официальный чейнджлог]**

**Да, `sys._MEIPASS` для onedir указывает на `_internal`:**
> «For a one-folder bundle, this is the path to the **`_internal`** folder within the bundle.»
> — <https://pyinstaller.org/en/stable/runtime-information.html> **[Д]**

**Следствие для updater'а на onedir:** обновлять нужно и `.exe`, и весь `_internal` (кроме случая, когда изменился только код — тогда достаточно `.exe`, см. §3.7). При этом **`.exe` и `_internal` не взаимозаменяемы по версиям**: смешивание «новый `.exe` + старый `_internal`» даёт непредсказуемое поведение, если менялся набор зависимостей.

### 3.9 `--contents-directory` — точная семантика

Man-страница:

> «`--contents-directory CONTENTS_DIRECTORY` — For **onedir builds only**, specify the name of the directory in which **all supporting files (i.e. everything except the executable itself)** will be placed in. **Use "." to re-enable old onedir layout without contents directory.**»
> — <https://pyinstaller.org/en/stable/man/pyinstaller.html> **[Д]**

В `.spec`-файле это аргумент `contents_directory` у `EXE(...)`, по умолчанию `"_internal"`. Валидация в исходниках:

```python
self.contents_directory = kwargs.get("contents_directory", "_internal")
...
if self.contents_directory in ("", "."):
    self.contents_directory = None  # Re-enable old onedir layout without contents directory.
elif self.contents_directory == ".." or "/" in self.contents_directory or "\\" in self.contents_directory:
    raise SystemExit(
        f'ERROR: Invalid value "{self.contents_directory}" passed to `--contents-directory` or '
        '`contents_directory`. Exactly one directory level is required (or just "." to disable the '
        'contents directory).'
    )
```
— `PyInstaller/building/api.py` (ветка `develop`), <https://github.com/pyinstaller/pyinstaller/blob/develop/PyInstaller/building/api.py> **[И]**

Итого:
- допускается **ровно один уровень** имени каталога; `..` и любые `/` или `\` запрещены (ошибка `SystemExit` с текстом выше);
- `""` или `"."` ⇒ `None` ⇒ **старая** раскладка onedir (всё рядом с `.exe`);
- на **onefile не влияет** («Onefile applications and macOS `.app` bundles are unaffected»);
- для updater'а это значит, что при `contents_directory="."` защищать/обновлять нужно «всё в одной папке», а при `_internal` — два объекта: `.exe` и подкаталог.

---

## 4. Корректный перезапуск приложения после обновления из Python

### 4.1 `subprocess.Popen` — базовый рецепт

```python
import os, sys, subprocess

CREATE_NEW_PROCESS_GROUP = 0x00000200   # 512
DETACHED_PROCESS         = 0x00000008   # 8
CREATE_NO_WINDOW         = 0x08000000   # 134217728
CREATE_NEW_CONSOLE       = 0x00000010   # 16
CREATE_BREAKAWAY_FROM_JOB= 0x01000000   # 16777216
CREATE_DEFAULT_ERROR_MODE= 0x04000000   # 67108864

def spawn_detached_gui(exe_path: str, *args: str) -> subprocess.Popen:
    """Запустить GUI-приложение так, чтобы оно пережило текущий процесс."""
    return subprocess.Popen(
        [exe_path, *args],
        cwd=os.path.dirname(exe_path) or None,
        close_fds=True,                              # не наследовать handles (умолчание с 3.7)
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
```

`subprocess.Popen` (полная сигнатура Windows-значимых частей):

```python
class subprocess.Popen(
    args, bufsize=-1, executable=None, stdin=None, stdout=None, stderr=None,
    preexec_fn=None, close_fds=True, shell=False, cwd=None, env=None,
    universal_newlines=None, startupinfo=None, creationflags=0,
    restore_signals=True, start_new_session=False, pass_fds=(), *, ...)
```
> «On Windows, the class uses the Windows **`CreateProcess()`** function.»
> — <https://docs.python.org/3/library/subprocess.html#subprocess.Popen> **[Д]**

`creationflags` в Python — это документированный список флагов Windows: `CREATE_NEW_CONSOLE`, `CREATE_NEW_PROCESS_GROUP`, `ABOVE_NORMAL_PRIORITY_CLASS`, `BELOW_NORMAL_PRIORITY_CLASS`, `HIGH_PRIORITY_CLASS`, `IDLE_PRIORITY_CLASS`, `NORMAL_PRIORITY_CLASS`, `REALTIME_PRIORITY_CLASS`, `CREATE_NO_WINDOW`, `DETACHED_PROCESS`, `CREATE_DEFAULT_ERROR_MODE`, `CREATE_BREAKAWAY_FROM_JOB`.
— <https://docs.python.org/3/library/subprocess.html#windows-constants> **[Д]**

**Точные числовые значения (WinBase.h, документированы Microsoft):**

| Константа | Значение |
|---|---|
| `DEBUG_PROCESS` | 0x00000001 |
| `DEBUG_ONLY_THIS_PROCESS` | 0x00000002 |
| `CREATE_SUSPENDED` | 0x00000004 |
| **`DETACHED_PROCESS`** | **0x00000008** |
| `CREATE_NEW_CONSOLE` | 0x00000010 |
| `CREATE_NEW_PROCESS_GROUP` | 0x00000200 |
| `CREATE_UNICODE_ENVIRONMENT` | 0x00000400 |
| `CREATE_SEPARATE_WOW_VDM` | 0x00000800 |
| `CREATE_DEFAULT_ERROR_MODE` | 0x04000000 |
| `CREATE_NO_WINDOW` | 0x08000000 |
| `CREATE_BREAKAWAY_FROM_JOB` | 0x01000000 |
| `CREATE_PROTECTED_PROCESS` | 0x00040000 |
| `INHERIT_PARENT_AFFINITY` | 0x00010000 |

— <https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags> **[Д]**

### 4.2 Почему `DETACHED_PROCESS` «в одиночку» часто недостаточно — и документированные ограничения комбинаций

Это самая важная часть, и она **документирована явно**:

> **`DETACHED_PROCESS`** (0x00000008): «For console processes, the new process does **not inherit its parent's console** (the default). The new process can call the `AllocConsole` function at a later time to create a console. … **This value cannot be used with `CREATE_NEW_CONSOLE`.**»
>
> **`CREATE_NEW_CONSOLE`** (0x00000010): «The new process has a **new console**, instead of inheriting its parent's console (the default). … **This flag cannot be used with `DETACHED_PROCESS`.**»
>
> **`CREATE_NEW_PROCESS_GROUP`** (0x00000200): «The new process is the root process of a new process group. The process group includes all processes that are descendants of this root process. … **If this flag is specified, CTRL+C signals will be disabled for all processes within the new process group.** … **This flag is ignored if specified with `CREATE_NEW_CONSOLE`.**»
>
> **`CREATE_NO_WINDOW`** (0x08000000): «The process is a console application that is being run without a console window. … **This flag is ignored if the application is not a console application, or if it is used with either `CREATE_NEW_CONSOLE` or `DETACHED_PROCESS`.**»
>
> **`CREATE_BREAKAWAY_FROM_JOB`** (0x01000000): «The child processes of a process associated with a job are **not associated with the job**. If the calling process is **not** associated with a job, this constant has **no effect**. If the calling process **is** associated with a job, **the job must set the `JOB_OBJECT_LIMIT_BREAKAWAY_OK` limit.**»
>
> — <https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags> **[Д]**

**Разбор для практики:**

1. **`CREATE_NO_WINDOW` + `DETACHED_PROCESS` = бессмысленно.** Документация прямо говорит, что `CREATE_NO_WINDOW` **игнорируется** при использовании с `DETACHED_PROCESS` (или `CREATE_NEW_CONSOLE`), а также для не-консольных приложений. Распространённый шаблон `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` содержит избыточный и игнорируемый флаг. Для GUI-приложения (собранного `--windowed`) `CREATE_NO_WINDOW` не нужен вообще.
2. **`DETACHED_PROCESS` + `CREATE_NEW_PROCESS_GROUP` — осмысленная комбинация** и **не** конфликтует (запрещена только пара `DETACHED_PROCESS` + `CREATE_NEW_CONSOLE`). `CREATE_NEW_PROCESS_GROUP` даёт две вещи: (а) `CTRL+C` **отключается** для всего нового дерева процессов — важно, чтобы Ctrl+C, убивающий updater'а/приложение, не убил и вновь запущенный экземпляр; (б) позволяет адресно послать `CTRL_BREAK` в группу через `GenerateConsoleCtrlEvent`.
3. **Для консольного приложения** `DETACHED_PROCESS` означает «нет консоли вообще» — если приложение печатает в stdout, использовать `CREATE_NEW_CONSOLE` (0x10), а **не** `DETACHED_PROCESS`. Помните, что при `CREATE_NEW_CONSOLE` флаг `CREATE_NEW_PROCESS_GROUP` **игнорируется**.
4. **Job Object — главная причина, почему ребёнок может умереть.** Если процесс запущен внутри Job'а с `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (типично для Task Scheduler, некоторых лаунчеров, отладчиков, CI), все процессы в Job'е убиваются при закрытии Job'а. Тогда нужен `CREATE_BREAKAWAY_FROM_JOB` **и** разрешение `JOB_OBJECT_LIMIT_BREAKAWAY_OK` в самом Job'е **[Д]**. Если breakaway не разрешён, `CreateProcess` завершится ошибкой; **какой именно код ошибки — «не подтверждено» документацией** (широко сообщается `ERROR_ACCESS_DENIED` 5).
5. **`DETACHED_PROCESS` сам по себе не «отвязывает» от Job'а, не спасает от завершения по Ctrl+C родителя и не отменяет наследование handles.** Именно поэтому «одного `DETACHED_PROCESS` недостаточно» — это верное практическое утверждение, и его причины документированы по пунктам выше (Job, Ctrl+C/process group, наследование дескрипторов).

### 4.3 Умирает ли дочерний процесс при выходе родителя?

**Нет** — в общем случае Windows не убивает потомков при завершении родителя. Документированная (косвенно) основа: процесс — независимый объект; `CreateProcess` не создаёт связи «родитель жив ⇒ ребёнок жив».

**Исключения, при которых ребёнок всё-таки умирает:**

- **Job Object** с `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` — при закрытии последнего handle на Job (в т.ч. при выходе родителя, если он был единственным держателем) все процессы Job'а завершаются. Обход — `CREATE_BREAKAWAY_FROM_JOB` + `JOB_OBJECT_LIMIT_BREAKAWAY_OK` **[Д]**.
- **Console control events:** при `CTRL_CLOSE_EVENT` (закрытие окна консоли) ОС завершает **все** процессы, привязанные к этой консоли. `CREATE_NEW_PROCESS_GROUP` и/или `CREATE_NEW_CONSOLE`/`DETACHED_PROCESS` изолируют от этого — и это как раз документированные эффекты этих флагов **[Д]**.
- **Явное убийство дерева** (`taskkill /T`, `TerminateJobObject`), а также AV/EDR-политики.

**Практическая рекомендация:** чтобы гарантированно «отвязать» процесс — `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`; если возможен Job — добавить `CREATE_BREAKAWAY_FROM_JOB`; если критично — запускать через Планировщик заданий (`schtasks`) — **[инженерная рекомендация, не документированное правило]**.

### 4.4 `close_fds` и наследование handles

> «If `close_fds` is true, all file descriptors except `0`, `1` and `2` will be closed before the child process is executed. … **On Windows, if `close_fds` is true then no handles will be inherited by the child process unless explicitly passed in the `handle_list` element of `STARTUPINFO.lpAttributeList`, or by standard handle redirection.**»
> «Changed in version 3.7: On Windows the default for `close_fds` was changed from `False` to `True` when redirecting the standard handles. It's now possible to set `close_fds` to `True` when redirecting the standard handles.»
> — <https://docs.python.org/3/library/subprocess.html#subprocess.Popen> **[Д]**

**Практический вывод (это и есть «риск наследования хендлов/локов»):**

- На современном Python `close_fds=True` — значение по умолчанию, и это **правильно** для updater'а: он не должен наследовать дескрипторы родителя, в т.ч. открытые на заменяемые файлы, файлы логов, сокеты.
- **Но:** `close_fds=True` не мешает наследованию **стандартных** дескрипторов (`0`,`1`,`2`) — при редиректе (`stdin/stdout/stderr=…`) они передаются. Если GUI-приложение запускается из родителя, у которого stdout открыт на **файл внутри каталога обновления**, этот файл останется занятым. Поэтому в updater'е всегда явно указывайте `stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL` (или лог вне каталога установки).
- **Родительские** дескрипторы на заменяемые файлы нужно закрыть **до** запуска updater'а: например, закрыть все логи/конфиги/кэши, а сам `staging`-каталог держать вне каталога установки.
- В самом PyInstaller-приложении дополнительно действует `SetDllDirectoryW`, который bootloader ставит в top-level каталог и который **наследуется дочерними процессами**:
  > «On Windows, the PyInstaller's bootloader sets the library search path to the top-level application directory (i.e., the path that is also available in `sys._MEIPASS`) using the `SetDllDirectoryW` … As noted in the API documentation, calling this function also affects the children processes started from the frozen application. To undo the effect of this call and restore standard search paths, `SetDllDirectory` function should be called with `NULL` argument.»
  > ```python
  > import sys
  > if sys.platform == "win32":
  >     import ctypes
  >     ctypes.windll.kernel32.SetDllDirectoryW(None)
  > ```
  > — <https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html> **[Д]**
  Это важно, если из frozen-приложения запускается **внешний** (системный) updater: он унаследует подменённый порядок поиска DLL.

### 4.5 Запуск `.cmd`: `shell=True` или полный путь?

Здесь документации **противоречат**, и это нужно знать:

- **Документация Python:**
  > «On Windows with `shell=True`, the `COMSPEC` environment variable specifies the default shell. **The only time you need to specify `shell=True` on Windows is when the command you wish to execute is built into the shell (e.g. `dir` or `copy`). You do not need `shell=True` to run a batch file or console-based executable.**»
  > — <https://docs.python.org/3/library/subprocess.html#frequently-used-arguments> **[Д, Python]**
- **Документация Windows (`CreateProcessW`):**
  > «**To run a batch file, you must start the command interpreter**; set `lpApplicationName` to `cmd.exe` and set `lpCommandLine` to the following arguments: `/c` plus the name of the batch file.»
  > — <https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw> **[Д, Microsoft]**

Расхождение **«не подтверждено»** в пользу одной из сторон. **Безопасный рецепт, работающий независимо от трактовки** — явная форма без `shell=True`:

```python
import os, subprocess, sys, tempfile, shutil

def run_updater_cmd(cmd_path: str, pid: int, staging: str, install: str,
                    exe_name: str, timeout_s: int = 120) -> subprocess.Popen:
    # 1) Копируем сам .cmd в %TEMP%, чтобы cmd.exe не держал файл
    #    в каталоге установки (иначе его тоже нельзя заменить).
    tmp_cmd = os.path.join(tempfile.gettempdir(), "app_update.cmd")
    shutil.copy2(cmd_path, tmp_cmd)

    # 2) Запускаем через cmd.exe /c с ПОЛНЫМИ путями.
    comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [comspec, "/c", tmp_cmd,
         str(pid), os.path.abspath(staging), os.path.abspath(install),
         exe_name, str(timeout_s)],
        creationflags=creationflags,
        close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
```

Эквивалент через `shell=True` (документированное поведение Windows-шелла: `%COMSPEC% /c …`, причём с Python 3.12 порядок поиска `cmd.exe` изменён — «current directory and `%PATH%` are replaced with `%COMSPEC%` and `%SystemRoot%\System32\cmd.exe`» **[Д]**):

```python
subprocess.Popen(f'"{tmp_cmd}" {pid} "{staging}" "{install}" "{exe_name}"', shell=True)
```

Альтернатива: `pythonw.exe`/`python.exe`-скрипт updater'а вместо `.cmd` — тогда нет проблем с `cmd.exe`, кавычками и локалями, и есть нормальная обработка ошибок. Для frozen-приложения отдельный маленький onedir-«updater.exe» (или `sys.executable` самого приложения с флагом `--apply-update`, запущенный с `PYINSTALLER_RESET_ENVIRONMENT=1`) — часто более надёжно, чем `.cmd`.

### 4.6 `os.startfile` и `ShellExecuteW`

**`os.startfile`** (Windows only):

```
os.startfile(path, [operation], [arguments], [cwd], [show_cmd])
```

Документация (дословно):

> «Start a file with its associated application.
> When *operation* is not specified, this acts like double-clicking the file in Windows Explorer, or giving the file name as an argument to the `start` command from the interactive command shell: the file is opened with whatever application (if any) its extension is associated.
> When another *operation* is given, it must be a "command verb" that specifies what should be done with the file. Common verbs documented by Microsoft are `'open'`, `'print'` and `'edit'` (to be used on files) as well as `'explore'` and `'find'` (to be used on directories).
> When launching an application, specify *arguments* to be passed as a single string. …
> The default working directory is inherited, but may be overridden by the *cwd* argument. This should be an **absolute path**. A relative *path* will be resolved against this argument.
> Use *show_cmd* to override the default window style. … Values are integers as supported by the Win32 `ShellExecute` function.
> **`startfile` returns as soon as the associated application is launched. There is no option to wait for the application to close, and no way to retrieve the application's exit status.** The *path* parameter is relative to the current directory or *cwd*. If you want to use an absolute path, make sure the first character is not a slash (`'/'`). Use `pathlib` or `os.path.normpath`…
> To reduce interpreter startup overhead, the Win32 `ShellExecute` function is not resolved until this function is first called. **If the function cannot be resolved, `NotImplementedError` will be raised.**
> Availability: Windows.
> Changed in version 3.10: Added the *arguments*, *cwd* and *show_cmd* arguments, and the `os.startfile/2` audit event.»

— <https://docs.python.org/3/library/os.html#os.startfile> **[Д]**

**`ShellExecuteW`** (Win32):

```c
HINSTANCE ShellExecuteW(
  [in, optional] HWND    hwnd,
  [in, optional] LPCWSTR lpOperation,
  [in]           LPCWSTR lpFile,
  [in, optional] LPCWSTR lpParameters,
  [in, optional] LPCWSTR lpDirectory,
  [in]           INT     nShowCmd
);
```
> «If the function succeeds, it returns a value **greater than 32**. If the function fails, it returns an error value…»; коды: `0` (out of memory), `ERROR_FILE_NOT_FOUND`, `ERROR_PATH_NOT_FOUND`, `ERROR_BAD_FORMAT`, `SE_ERR_ACCESSDENIED`, `SE_ERR_FNF`, `SE_ERR_PNF`, `SE_ERR_NOASSOC`, `SE_ERR_SHARE` («A sharing violation occurred»), `SE_ERR_OOM` и др.
> «`runas`: Launches an application as Administrator. User Account Control (UAC) will prompt the user for consent…»
> «Because `ShellExecute` can delegate execution to Shell extensions … that are activated using COM, **COM should be initialized before `ShellExecute` is called**.»
> — <https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecutew> **[Д]**

**Когда что уместно:**

| Ситуация | Что использовать | Почему |
|---|---|---|
| Нужно, чтобы обновлённое приложение пережило updater, и нужен контроль над флагами (Job, console, handles) | **`subprocess.Popen` + `creationflags`** | только `CreateProcess` даёт `creationflags`, `cwd`, `env`, `close_fds` [Д] |
| Нужно запустить «как пользователь, через оболочку», с ассоциациями/verb'ами (`open`, `runas`, `print`), либо запустить документ/URL | **`os.startfile` / `ShellExecuteW`** | делегирование оболочке [Д] |
| Нужен запуск с повышением прав (UAC) | `ShellExecuteW("runas", …)` (или `ShellExecuteEx` + `SEE_MASK_NOCLOSEPROCESS`, если нужен handle) | `runas` документирован [Д] |
| Нужно **дождаться** завершения и/или узнать код возврата запущенного процесса | **`Popen` / `ShellExecuteEx`** — `os.startfile` **не умеет ни того, ни другого** | прямая цитата документации [Д] |
| Нужно ждать всё дерево процессов | `Start-Process -Wait` (PowerShell) или Job Object | `Wait-Process` ждёт только указанные PID [Д] |

### 4.7 Риск наследования хендлов/локов — сводка

1. **Закрывайте свои дескрипторы** на заменяемые файлы до запуска updater'а. Открытый родителем handle на `app.exe` **не мешает** переименованию/замене (image section — мешает, обычный handle на запись — мешает), но handle на **файл данных**, который надо заменить, заблокирует `MoveFileEx`/`DeleteFile` (share-mode conflict → `ERROR_SHARING_VIOLATION`).
2. **`close_fds=True`** — оставляйте (это умолчание); но помните, что `0/1/2` передаются при редиректе → явно ставьте `DEVNULL`.
3. **Не наследуйте `SetDllDirectoryW`-искажение** в внешний updater — вызовите `SetDllDirectoryW(None)` перед запуском ([Д], PyInstaller).
4. **`.cmd` держит файл.** `cmd.exe` читает batch-файл по мере выполнения; замена самого `.cmd` внутри обновляемого каталога может «сломать» выполняющийся скрипт. Копируйте `.cmd` в `%TEMP%`.
5. **AV/EDR** может держать handle на только что созданный/распакованный файл — отсюда ретраи в `robocopy` (`/R:5 /W:1`) и паузы после выхода процесса.

---

## 5. Готовые фрагменты

### 5.1 Python: запуск обновления (onefile и onedir)

```python
# app_updater_launch.py  — запускается ИЗ ОБНОВЛЯЕМОГО ПРИЛОЖЕНИЯ, затем приложение выходит.
import os, sys, shutil, tempfile, subprocess

DETACHED_PROCESS          = 0x00000008
CREATE_NEW_PROCESS_GROUP  = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NEW_CONSOLE        = 0x00000010

def is_frozen() -> bool:
    """Официальный шаблон PyInstaller."""
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))

def installed_exe() -> str:
    """Путь к .exe, который надо заменить. sys.executable — bootloader-исполняемый файл."""
    return os.path.abspath(sys.executable)

def installed_dir() -> str:
    """Каталог установки.
    onefile : каталог рядом с .exe
    onedir  : каталог, содержащий .exe и подкаталог _internal (PyInstaller >= 6.0)
    """
    return os.path.dirname(installed_exe())

def launch_update(staging_dir: str, exe_name: str,
                  updater_cmd: str, timeout_s: int = 120) -> None:
    # 1. Копируем .cmd в %TEMP%, чтобы cmd.exe не держал файл в каталоге установки.
    tmp_cmd = os.path.join(tempfile.gettempdir(), "app_update.cmd")
    shutil.copy2(updater_cmd, tmp_cmd)

    # 2. Сбрасываем искажение поиска DLL, внесённое bootloader'ом PyInstaller,
    #    чтобы внешний cmd.exe/robocopy искали системные DLL нормально.
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)

    comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")

    # 3. Запускаем updater отдельным процессом. DETACHED_PROCESS — чтобы он не был
    #    привязан к консоли родителя; CREATE_NEW_PROCESS_GROUP — чтобы Ctrl+C,
    #    убивающий нас, не убил и updater.
    #    CREATE_BREAKAWAY_FROM_JOB нужен ТОЛЬКО если мы внутри Job Object
    #    (иначе CreateProcess может упасть, если Job не разрешает breakaway).
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [comspec, "/c", tmp_cmd,
         str(os.getpid()), os.path.abspath(staging_dir),
         installed_dir(), exe_name, str(timeout_s)],
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def restart_frozen_app_self() -> None:
    """Самоперезапуск frozen-приложения КОРРЕКТНО, с точки зрения PyInstaller >= 6.9.

    Для onefile: без PYINSTALLER_RESET_ENVIRONMENT новый процесс будет считаться
    worker-процессом и переиспользует _MEI-каталог, который родитель удалит при выходе.
    """
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen([sys.executable], env=env,
                     close_fds=True,
                     stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    sys.exit(0)
```

Порядок вызова в приложении:

```python
launch_update(staging_dir=r"C:\ProgramData\MyApp\staging",   # ВНЕ каталога установки!
              exe_name="MyApp.exe",
              updater_cmd=r"C:\ProgramData\MyApp\update.cmd")
# ... закрыть логи/БД/файлы ...
sys.exit(0)      # корректный выход = bootloader onefile уберёт _MEI
```

### 5.2 `.cmd`-updater

См. полный текст в §2a. Ключевые моменты, которые нельзя опускать:
- копировать скрипт в `%TEMP%` перед запуском;
- ждать PID через `tasklist /FO CSV /NH` + сравнение PID, а не через локализованное сообщение;
- `ping -n 2 127.0.0.1 >nul` вместо `timeout`;
- `robocopy … /R:5 /W:1`, ошибка при `ERRORLEVEL GEQ 8`;
- `start "" "%DSTDIR%\%APPEXE%"` для перезапуска (пустой первый аргумент = заголовок окна).

### 5.3 Python: `MoveFileEx` для отложенного удаления `.old`

```python
import ctypes
from ctypes import wintypes

MOVEFILE_REPLACE_EXISTING     = 0x1
MOVEFILE_DELAY_UNTIL_REBOOT   = 0x4

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_MoveFileExW = _k32.MoveFileExW
_MoveFileExW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
_MoveFileExW.restype  = wintypes.BOOL

def delete_on_reboot(path: str) -> None:
    """Зарегистрировать удаление файла при следующей перезагрузке.

    ВНИМАНИЕ: пишет в
      HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\PendingFileRenameOperations
    (REG_MULTI_SZ, запись вида  szSrcFile\\0\\0).
    Требует прав администратора/LocalSystem. Перезагрузка НЕ инициируется.
    """
    if not _MoveFileExW(path, None, MOVEFILE_DELAY_UNTIL_REBOOT):
        raise ctypes.WinError(ctypes.get_last_error())

def replace_without_reboot(src: str, dst: str) -> None:
    """Атомарная (в пределах тома) замена dst файлом src."""
    if not _MoveFileExW(src, dst, MOVEFILE_REPLACE_EXISTING):
        raise ctypes.WinError(ctypes.get_last_error())
```

### 5.4 Python: уборка осиротевших `_MEI`-каталогов (Windows)

```python
import os, re, glob, tempfile, ctypes
from ctypes import wintypes

# На Windows имя каталога onefile — "_MEI" + %08x PID + суффикс от _wtempnam().
_MEI_RE = re.compile(r"^_MEI([0-9a-fA-F]{8})")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

def _pid_alive(pid: int) -> bool:
    h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return True          # не смогли узнать — считаем живым (безопаснее)
        return code.value == STILL_ACTIVE
    finally:
        _k32.CloseHandle(h)

def cleanup_orphan_mei(base: str | None = None) -> list[str]:
    """Удалить _MEI*-каталоги, чьи процессы (по PID в имени) уже не существуют.

    Безопаснее, чем «удалить всё, что старше N часов»: PID берётся из имени.
    Ограничение: PID может быть переиспользован -> каталог живого, но ДРУГОГО
    процесса будет считаться «живым» и не будет удалён. Это безопасная ошибка.
    """
    base = base or tempfile.gettempdir()
    removed = []
    for path in glob.glob(os.path.join(base, "_MEI*")):
        if not os.path.isdir(path):
            continue
        m = _MEI_RE.match(os.path.basename(path))
        if not m:
            continue
        if _pid_alive(int(m.group(1), 16)):
            continue
        try:
            import shutil
            shutil.rmtree(path, ignore_errors=False)
            removed.append(path)
        except OSError:
            pass    # каталог занят (AV, чужие DLL) — попробуем в следующий запуск
    return removed
```

### 5.5 PowerShell-one-liner вместо цикла `tasklist`

```powershell
Wait-Process -Id $PID_TO_WAIT -Timeout 120 -ErrorAction SilentlyContinue
```

---

## 6. Что осталось «не подтверждено»

1. **Точный код ошибки** (`ERROR_SHARING_VIOLATION` 32 против `ERROR_ACCESS_DENIED` 5) при `CreateFile(GENERIC_WRITE)` и при `DeleteFile` на **работающем** `.exe`: документация называет правила, но не коды для этого сценария.
2. **Какой компонент ОС** (загрузчик / Csrss / memory manager) и **с каким share-режимом** держит handle на образ — в документации Microsoft явно не сказано; утверждения вида «image section (SEC_IMAGE) блокирует `DeleteFile`» первичным источником не подтверждены. **Что подтверждено:** (а) flush image section (`MmFlushImageSection`) требуется для delete и open-for-write, но **не** для rename (WDK); (б) удаление невозможно, пока открыты handle'ы, и Microsoft предлагает **переименовать** файл, чтобы немедленно освободить имя (`Closing and Deleting Files`); (в) переименование требует DELETE-доступа, а `FILE_SHARE_DELETE` разрешает «delete or rename» (`CreateFile` + Chen).
3. **Влияние расширения** переименованного файла (`.old` vs `.old.exe`) на возможность удаления/поведение AV — первичным источником не подтверждено.
4. **Текст и поведение сообщения `tasklist`** при отсутствии совпадений в режимах `csv`/`/nh` (локализация) — не документировано.
5. **Завершение `waitfor <pid>` при выходе процесса** — в документации `waitfor` описан как сетевой механизм сигналов; эта схема не документирована.
6. **Падение `timeout` при перенаправленном stdin** — широко известно, но в документации не описано.
7. **Количественные оценки** замедления старта onefile (мс/сек) — в официальной документации отсутствуют; есть только «a little slower» / «can take a little time».
8. **Утверждение «onefile чаще детектится AV, чем onedir»** как измеренный факт — первичным источником не подтверждено. Подтверждено другое: (а) FP из-за распространённости pre-compiled bootloader'ов [Д, PyInstaller]; (б) AV/OS инжектируют DLL и удерживают файлы в `_MEI`, ломая уборку [И, CHANGES 6.10–6.13]; (в) PyInstaller ставит контрольные суммы EXE для снижения FP [И, CHANGES 4.3].
9. **Снижение AV-трения через `--runtime-tmpdir`** — не подтверждено; документация называет другие мотивы для этой опции.
10. **Официальная рекомендация PyInstaller между onefile и onedir** — **отсутствует**; есть только набор утверждений (§3.7) и явное «is not recommended» для **macOS onefile + windowed**.
11. **Inno Setup** в документации PyInstaller **не упоминается вообще**; связка «onedir + Inno Setup» — практика сообщества.
12. **Код ошибки `CreateProcess` при `CREATE_BREAKAWAY_FROM_JOB` в Job'е без `JOB_OBJECT_LIMIT_BREAKAWAY_OK`** — документацией не назван.
13. **`shell=True` для `.cmd`**: документация Python и документация Windows `CreateProcess` противоречат друг другу; использовать явную форму `[comspec, "/c", path]`.
