# Подпись кода Windows для неподписанного PyInstaller‑приложения: состояние 2025–2026

**Дата сбора данных:** 16 сентября 2026 г.
**Область:** Windows 10/11; распространение `.exe`/`.msi` вне Microsoft Store.
**Метод:** только фактические источники (Microsoft Learn, blogs.windows.com, cabforum.org, signpath.org, прайс‑листы CA, официальный Azure Retail Prices API). Ничего не додумано.

### Легенда достоверности

| Маркер | Значение |
|---|---|
| ✅ | Подтверждено первичным источником (Microsoft, CA/B Forum, SignPath, официальный API цен Azure) |
| ⚠️ | Подтверждено вторичным/косвенным источником, либо логическое следствие из первичного |
| ❌ **не подтверждено** | Не удалось подтвердить первичным источником; гипотеза, а не факт |

---

## 0. Краткий итог (TL;DR)

| Вариант | Стоимость | Поведение SmartScreen | Источник |
|---|---|---|---|
| Без подписи | 0 | ⚠️ «Windows protected your PC», нужна кнопка «Run anyway» | [MS Learn](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) |
| Самоподписанный сертификат | 0 | ⚠️ «Same behavior as no signature» — **не помогает** | там же |
| OV‑сертификат | $150–300/год (типично по MS); от $129/год (SSL.com) | ⚠️ предупреждение, пока не накопится репутация | [MS Learn](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) |
| EV‑сертификат | $400+/год | ⚠️ **то же, что OV с 2024 года** — мгновенного доверия больше нет | там же |
| Azure Artifact Signing (бывш. Trusted Signing) | $9.99/мес (Basic) | ⚠️ репутация накапливается со временем | [Azure Pricing](https://azure.microsoft.com/en-us/pricing/details/artifact-signing/) |
| Microsoft Store (MSIX) | **бесплатно** (Store сам переподписывает) | ✅ **предупреждений нет** | [MS Learn](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) |
| SignPath Foundation (только OSS) | бесплатно | OV‑уровень, но издатель = SignPath Foundation | [signpath.org](https://signpath.org/) |

**Главные выводы:**
1. **Самоподписанный сертификат не решает проблему SmartScreen вообще** — Microsoft прямо приравнивает его к отсутствию подписи.
2. **EV больше не даёт мгновенного обхода SmartScreen** — поведение убрано в 2024 году. Переплачивать за EV ради SmartScreen бессмысленно.
3. Для закрытого проекта **бесплатного варианта OV не существует**.
4. Самый дешёвый способ вообще не видеть предупреждений — **Microsoft Store (MSIX)**, и с мая 2026 регистрация разработчика там бесплатна.

---

## 1. Что именно происходит при запуске неподписанного PyInstaller `.exe`

### 1.1 Диалог Microsoft Defender SmartScreen

**Подтверждено первичным источником Microsoft** ✅ — страница
[SmartScreen reputation for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) (последнее обновление **2026‑05‑06**).
В таблице поведения при первой загрузке для строки «No signature» указано дословно:

> ⚠️ Warning — **"Windows protected your PC"**; User must choose **"Run anyway"** before the app can run. Enterprise policy can prevent continuation entirely.

То есть первичный источник Microsoft подтверждает:
- заголовок диалога — **«Windows protected your PC»** ✅
- кнопка — **«Run anyway»** ✅
- приложение помечается как **unrecognized** ✅
- в корпоративной среде продолжение может быть **полностью запрещено политикой** ✅

**Что НЕ подтверждено первичной документацией Microsoft** ❌:

- Полная вторая строка диалога — **«Microsoft Defender SmartScreen prevented an unrecognized app from starting. Running this app might put your PC at risk.»** — в доступных мне продуктовых документах Microsoft (learn.microsoft.com, support.microsoft.com) **дословно не найдена**. Формулировка широко воспроизводится:
  - в заголовках веток Microsoft Q&A на learn.microsoft.com, например: [«Microsoft Defender SmartScreen prevented an unrecognized app from starting»](https://learn.microsoft.com/en-ie/answers/questions/3885339/microsoft-defender-smartscreen-prevented-an-unreco) — ⚠️ но это пользовательский контент, а не продуктовая документация;
  - в сторонних инструкциях, например [mnemonic-gui walkthrough](https://github.com/bg002h/mnemonic-gui/blob/master/docs/onboarding/windows-smartscreen-walkthrough.md) — ⚠️ не авторитетный источник.
  → Считайте эту формулировку **вероятной, но «не подтверждено» первичным источником**. Практически важно то, что заголовок и кнопка «Run anyway» подтверждены.

- Ссылка **«More info»**, после нажатия которой появляется «Run anyway» — в документации Microsoft **дословно не найдена** ❌. Microsoft подтверждает только наличие кнопки «Run anyway». Порядок «More info» → «Run anyway» воспроизводится в сторонних источниках и в скриншотах, но **не подтверждён** продуктовой документацией.

- Утверждение «SmartScreen запоминает исключение; последующие запуски открываются напрямую» — встречается в сторонних инструкциях ⚠️; в документации Microsoft **не подтверждено** ❌.

### 1.2 Mark‑of‑the‑Web (MOTW, поток `Zone.Identifier`) — механизм

**Подтверждено Microsoft** ✅. Наиболее точное продуктовое описание MOTW находится в документации Microsoft 365 Apps:
[Macros from the internet are blocked by default in Office](https://learn.microsoft.com/en-us/microsoft-365-apps/security/internet-macros-blocked).

Дословные факты оттуда:
- «**Mark of the Web is added by Windows to files from an untrusted location, such as the internet or Restricted Zone.** For example, browser downloads or email attachments.» ✅
- «**By default, Mark of the Web is added to files only from the Internet or Restricted sites zones.**» ✅
- «**Mark of the Web only applies to files saved on an NTFS file system**, not files saved to FAT32 formatted devices.» ✅
- Посмотреть зону можно так: `notepad {имя файла}:Zone.Identifier` (значение `ZoneId`) ✅
- Снять метку: галочка **Unblock** на вкладке General в свойствах файла, либо командлет `Unblock-File` ✅

**Как MOTW связан с репутацией SmartScreen** ✅ — из [документации SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen):

> Microsoft Defender SmartScreen determines whether a **downloaded** app or app installer is potentially malicious by:
> – Checking **downloaded files** against a list of reported malicious software sites and programs known to be unsafe...
> – Checking **downloaded files** against a list of files that are well known and downloaded frequently. **If the file isn't on that list, Microsoft Defender SmartScreen shows a warning**, advising caution.

Механизм, следовательно: MOTW помечает файл как «загруженный из интернета» → SmartScreen применяет к нему проверку репутации (репутация хеша файла + репутация сертификата) → при отсутствии репутации показывается предупреждение.

**Ключевое практическое следствие для PyInstaller** ✅: файл, собранный **локально**, MOTW не получает → предупреждение SmartScreen **не появляется** (при условии, что он не передан через интернет). Файл, **скачанный браузером**, MOTW получает → предупреждение появляется.

⚠️ **Важный нюанс для распространения PyInstaller‑сборок:** если вы публикуете `.zip` с `onedir`‑сборкой на GitHub Releases, пользователь скачивает архив (MOTW ставится на архив), а затем распаковывает его. Windows Explorer **переносит** MOTW из архива на извлечённые файлы — именно на этом построена логика «7‑Zip по умолчанию позволяет извлечённым файлам обходить SmartScreen» (то есть Explorer так делает, а 7‑Zip по умолчанию нет). Источники: [gbhackers](https://gbhackers.com/7-zip-default-setting/), [ZeroWL](https://blog.zerowl.io/7-zip-mark-of-the-web-bypass-lets-malicious-files-evade-windows-smartscreen), а также технический разбор [DFIR: «Mark‑of‑the‑Web: the rules changed, the tools didn't» (2026‑06‑29)](https://dfir.ru/2026/06/29/mark-of-the-web-the-rules-changed-the-tools-didnt/). ⚠️ Это вторичные источники; отдельной страницы Microsoft, документирующей распространение MOTW из ZIP, я не нашёл → деталь про ZIP помечена как ⚠️.

✅ Из того же разбора DFIR: с **2022 года** Microsoft изменила недокументированное правило — если у файла внутри смонтированного контейнера (VHD/VHDX/ISO) нет `Zone.Identifier`, проверяется сам файл‑контейнер. Сторонние архиваторы (WinRAR, 7‑Zip) этого не делают.

### 1.3 Есть ли предупреждение, если приложение НЕ скачано браузером?

**Точный ответ — подтверждено Microsoft** ✅. В документации SmartScreen есть явный блок «Important»:

> SmartScreen protects against malicious files from the internet. **It doesn't protect against malicious files on internal locations or network shares, such as shared folders with UNC paths or SMB/CIFS shares.**
> — [Microsoft Defender SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen)

Разбор по способам распространения:

| Способ | MOTW | Предупреждение SmartScreen от репутации приложений | UAC |
|---|---|---|---|
| Сборка запускается локально на машине сборки | нет | **нет** ✅ | нет (если не запрашивается админ) |
| Скопировано из общей папки / по UNC / SMB | нет | **нет** ✅ (явное исключение в документации MS) | только если запрашивается админ |
| Скачано браузером | да | **да** ✅ | только если запрашивается админ |
| Скачан `.zip` → распакован Explorer'ом | да (переносится) ⚠️ | **да** ⚠️ | только если запрашивается админ |
| Установщик (Inno Setup/NSIS), скачанный браузером | да (на `.exe` установщика) | **да**, на установщике ⚠️ | зависит от режима установки |

⚠️ Уточнение по установщику: MOTW ставится на **загруженный установщик**. Дальнейшее поведение зависит от того, распространяет ли инсталлятор MOTW на устанавливаемые файлы. Общего правила «установщик всегда снимает MOTW со всех файлов» в документации Microsoft я не нашёл → **не подтверждено**. Для onedir‑сборки, которую просто распаковывают из ZIP, MOTW на `.exe` **сохранится**, и предупреждение будет.

### 1.4 Что такое «репутация» и как она накапливается

**Подтверждено Microsoft** ✅ — [SmartScreen reputation for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

SmartScreen учитывает **два сигнала**:
1. **Репутация издателя (publisher reputation)** — подписан ли файл, известен ли и доверен ли сертификат подписи.
2. **Репутация хеша файла (file hash reputation)** — скачивал ли этот конкретный файл кто‑то ещё без признаков вредоносности.

Дословные цитаты:

> A negative or unknown reputation for a file's hash or its publisher's certificate can cause warnings to show. Even when signed, a newly created binary could still show a SmartScreen warning until its hash or publisher certificate accumulates sufficient evidence of positive reputation.

> **When a file is not signed, SmartScreen reputation must build for each new version of your files, starting with zero reputation. Reputation cannot transfer from previous versions unless both were signed using the same publisher identity.**

> **Signing files using a trusted certificate can allow certificate reputation to build, potentially avoiding warnings on new files signed by the same trusted certificate. Unsigned files must build reputation anew with every update.**

→ **Репутация привязана к идентичности подписи (сертификату), а не к версии файла.** Для неподписанного приложения каждая новая версия начинается с нуля. Это самый весомый аргумент за покупку сертификата даже при отсутствии мгновенного эффекта.

Сроки:
> **There is no exact threshold, but it can take several weeks and hundreds of clean installs from a wide audience.**
— ⚠️ Точного порога Microsoft не называет; это оценка из документации.

**Про OV и EV — текущее состояние** ✅:

| Тип сертификата | Поведение при первой загрузке (дословно из таблицы MS) |
|---|---|
| Microsoft Store | ✅ No warning — covered by Microsoft's certificate |
| Valid Certificate (OV/EV) | ⚠️ Warning — app flagged as unrecognized **until reputation accumulates**; verified publisher name is displayed |
| No signature | ⚠️ Warning — "Windows protected your PC"; User must choose "Run anyway" |
| Self‑signed Certificate | ⚠️ **Warning — Same behavior as no signature** |

**Про EV — принципиальное изменение** ✅, дословно:

> **EV certificates no longer bypass SmartScreen.** Years ago, signing files with an Extended Validation (EV) code signing certificate would result in positive SmartScreen reputation by default, but **this behavior no longer exists**. EV certificates may matter for enterprise procurement, but they **no longer impact SmartScreen behavior**. **Paying a premium for EV solely to avoid SmartScreen warnings is no longer justified.**

Вторая страница Microsoft уточняет дату ✅:
> That behavior was **removed in 2024**. EV‑signed files now go through the same reputation-building process as OV certificates.
> Paying the EV premium (**$400+/year**) solely to avoid SmartScreen warnings is no longer justified.
> — [Code signing options for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) (обновлено **2026‑08‑29**)

**Отвечая прямо на вопрос «накапливает ли OV репутацию со временем»: ДА** ✅. Формулировка Microsoft: OV и Artifact Signing — «⚠️ Same as Azure Artifact Signing — reputation builds over time», и «OV certificates are a proven option and are functionally **equivalent to Azure Artifact Signing for SmartScreen purposes**».

### 1.5 Windows 11: Smart App Control (более жёсткий, чем SmartScreen)

**Подтверждено Microsoft** ✅ — [Smart App Control overview](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/overview):

> **Malware, Potentially Unwanted Apps (PUA), and unknown, unsigned code are blocked by default.**

> Smart App Control will block apps and binary files identified as unsafe by Microsoft's app intelligence services **unless those files are code signed with a certificate issued by a certificate authority (CA) within the Trusted Root Program**.

И прямое предупреждение из документации по репутации SmartScreen ✅:
> **On Windows 11 devices, the Smart App Control feature may supersede SmartScreen Application Reputation. Smart App Control will block execution of unsigned files unless the file has a positive reputation. Smart App Control signature checks apply to all executable files, not just those downloaded from the Internet.**

Это критично: **Smart App Control проверяет все исполняемые файлы, независимо от MOTW**. То есть для пользователей с включённым Smart App Control неподписанное PyInstaller‑приложение будет **заблокировано**, даже если оно скопировано из локальной сети и MOTW отсутствует. Условия работы: только на «чистой» установке Windows 11 (22572+) и только в отдельных регионах ✅.

### 1.6 UAC и «Unknown publisher»

**Механизм — подтверждено Microsoft** ✅ — [How User Account Control works](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/user-account-control/how-it-works):

> When an app attempts to run with an administrator's full access token, Windows first analyzes the executable file to determine its publisher. Apps are first separated into three categories based on the file's publisher: **Windows / Publisher verified (signed) / Publisher not verified (unsigned)**.
> The elevation prompt color-coding is as follows:
> • **Gray background**: The application is a Windows administrative app... or an application signed by a verified publisher
> • **Yellow background**: the application is **unsigned or signed but isn't trusted**

→ Для неподписанного `.exe` в UAC‑запросе: жёлтый фон и пометка **«Unknown publisher»** / «Publisher not verified» ✅.

**Точный текст запроса — ❌ не подтверждено первичной документацией.** Фраза
«*Do you want to allow this app from an unknown publisher to make changes to your device?*»
дословно в продуктовой документации Microsoft **не найдена**; она встречается в пользовательских ветках Microsoft Q&A (например, [заголовок ветки на learn.microsoft.com](https://learn.microsoft.com/en-ca/answers/questions/656593/how-to-stop-do-you-want-to-allow-this-app-from-an)). Считайте формулировку вероятной, но **не подтверждённой**.

**Про обход UAC при per‑user установке** ⚠️:
- ✅ Подтверждено документацией: UAC‑запрос возникает, когда приложению нужен **administrator access token** («each application that requires the administrator access token must prompt the end user for consent»), и «all apps run as a standard user unless a user provides consent or credentials».
- ⚠️ **Следствие (логический вывод, не цитата):** приложение, которое устанавливается per‑user (в `%LOCALAPPDATA%`, настройки в `HKCU`) и не объявляет требование прав администратора, **не вызывает UAC‑запрос вообще** — ни «unknown publisher», ни какого‑либо другого. Для PyInstaller `onedir`, который просто распаковывается в папку пользователя и запускается, повышение прав не требуется, поэтому UAC не появляется.
- ❌ **Не подтверждено:** что PyInstaller по умолчанию встраивает манифест с `requestedExecutionLevel=asInvoker` и что опция `--uac-admin` добавляет `requireAdministrator`. Мне не удалось получить документацию PyInstaller по этому вопросу (установленного PyInstaller в окружении нет, страница usage в текущей версии опцию не документирует). Проверьте на своей сборке вручную через `mt.exe`/`sigcheck`.

### 1.7 Изменения 2023–2026, влияющие на эту задачу

| Дата | Изменение | Статус | Источник |
|---|---|---|---|
| **1 июня 2023** | **CA/B Forum:** закрытые ключи подписчика для code signing сертификатов должны генерироваться/храниться/использоваться в Hardware Crypto Module уровня **FIPS 140‑2 Level 2** или **Common Criteria EAL 4+**. **Дата подтверждена** | ✅ | [CSBR v3.11.0](https://cabforum.org/working-groups/code-signing/requirements/) |
| 2023‑04‑23/24 | GlobalSign начал требовать токен; **скачивание `.pfx` прекращено** | ✅ | [GlobalSign advisory](https://support.globalsign.com/code-signing/advisory/new-requirements-related-private-key-protection-codesigning-certificates) |
| **2024** | **Убрано мгновенное доверие SmartScreen для EV** | ✅ | [MS Learn](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) |
| 15 апреля 2025 | CA/B Forum: новый §6.2.7.2 — ключи Timestamp Authority (Root и Sub CA с validity > 72 мес.) в Hardware Crypto Module, offline/air‑gapped | ✅ | [CSBR v3.11.0](https://cabforum.org/working-groups/code-signing/requirements/) |
| 7 ноября 2025 | Ballot CSC‑31 «Maximum Validity Reduction» | ✅ | там же |
| **26 декабря 2025** | **GlobalSign:** последний день заказа 2‑ и 3‑летних code signing сертификатов | ✅ | [shop.globalsign.com](https://shop.globalsign.com/en/code-signing) |
| **1 марта 2026** | **CSBR §6.3.2:** для сертификатов, выпущенных **до** 2026‑03‑01 — срок ≤ 39 мес.; **с 2026‑03‑01 — ≤ 460 дней**. То есть много­летние сертификаты фактически исчезают | ✅ | [CSBR v3.11.0](https://cabforum.org/working-groups/code-signing/requirements/) |
| **7 мая 2026** | **Microsoft Store: регистрация company‑аккаунта стала бесплатной** (сбор $99 отменён), поддержка входа через Microsoft Entra ID | ✅ | [blogs.windows.com](https://blogs.windows.com/windowsdeveloper/2026/05/07/publish-to-microsoft-store-as-a-company-now-with-free-registration-and-faster-onboarding/) |
| 2026 | Azure Trusted Signing **переименован в Azure Artifact Signing** и вышел в **GA** (общая доступность) | ✅ | [MS Learn Overview](https://learn.microsoft.com/en-us/azure/artifact-signing/overview) (обновлено 2026‑05‑12); старый URL `/azure/trusted-signing/overview` редиректит на `/azure/artifact-signing/overview` |
| 2026‑06‑29 | Публичный разбор несоответствия правил распространения MOTW в сторонних архиваторах | ⚠️ | [DFIR](https://dfir.ru/2026/06/29/mark-of-the-web-the-rules-changed-the-tools-didnt/) |

**Дословный текст требования CA/B Forum (подтверждено)** ✅ — [CSBR v3.11.0 от 16 июня 2026](https://cabforum.org/working-groups/code-signing/requirements/), §6.2.7.4.1:

> **Effective June 1, 2023**, Subscriber Private Keys for Code Signing Certificates SHALL be protected per the following requirements. The CA MUST obtain a contractual representation from the Subscriber that the Subscriber will use one of the following options to generate and protect their Code Signing Certificate Private Keys **in a Hardware Crypto Module with a unit design form factor certified as conforming to at least FIPS 140‑2 Level 2 or Common Criteria EAL 4+**:
> (1) Subscriber uses a Hardware Crypto Module meeting the specified requirement;
> (2) Subscriber uses a **cloud‑base key generation and protection solution** [key creation/storage/usage must remain within the cloud HCM security boundary; subscription must log all access, operations and configuration changes];
> (3) Subscriber uses a **Signing Service** which meets the requirements of Section 6.2.7.3.

Дополнительно ✅: **Signing Services** (облачные сервисы подписи) обязаны быть строже — §6.2.7.3: «For Code Signing Certificates, Signing Services SHALL protect Subscriber Private Keys in a Hardware Crypto Module conforming to at least **FIPS 140‑2 level 3** or Common Criteria EAL 4+».

**Уточнение по дате** ✅: изначально в Ballot CSC‑17 датой был **15 ноября 2021**, и именно CSC‑17 перенёс её на **1 июня 2023**. То есть 1 июня 2023 — это уже перенесённый (окончательный) срок, дальнейших продлений не найдено.
Источник: [Ballot CSC‑17](https://cabforum.org/2022/09/27/ballot-csc-17-subscriber-private-key-extension/).

**Важное уточнение: до 2023‑06‑01 для OV/не‑EV допускался «любой» USB/SD‑токен** ✅:
> ...or another type of hardware storage token with a unit design form factor of SD Card or USB token (**not necessarily certified as conformant with FIPS 140‑2 Level 2 or Common Criteria EAL 4+**).
То есть именно 1 июня 2023 **закрыл разрыв** между EV (строгие требования уже действовали) и OV.

**Влияние на CI/CD — подтверждено производителями** ✅:
- DigiCert: «Effective June 1, 2023, code signing certificate key pairs may only be issued and stored in a Hardware Security Module (HSM) that meets or exceeds FIPS 140‑2 Level 2 or Common Criteria EAL 4+ standards. This ensures the private key is protected and **cannot be exported**.» — [digicert.com](https://www.digicert.com/signing/code-signing-certificates)
- Sectigo: «As of June 1, 2023 Code Signing certificates will be: Installed on a Sectigo token and shipped securely to the customer. Available as a download to be installed on the customer's own HSM.» — [sectigo.com](https://www.sectigo.com/ssl-certificates-tls/code-signing)
- GlobalSign: «Effective April 24 2023, you will need to install the Certificate directly into a FIPS 140‑2 level 2 or Common Criteria EAL 4+ compliant device. **You will be unable to download the Certificate in .PFX format.**»

**Практический вывод:** ✅ **нельзя больше положить `.pfx` в секрет репозитория / GitHub Secrets и подписывать в CI.** Ключ неэкспортируемый. Нужен либо физический HSM/токен на self‑hosted раннере, либо облачный сервис подписи: **Azure Artifact Signing**, **SignPath**, **DigiCert KeyLocker**, **SSL.com eSigner**.

**Прочие изменения политик Defender** ⚠️: отдельных ужесточений политик Microsoft Defender, специально затрагивающих неподписанные приложения в 2025–2026, я **не подтвердил** ❌. Подтверждены только: Smart App Control (блокировка неподписанного кода) ✅ и SmartScreen Application Reputation ✅. Утверждения о неких новых «строгих политиках 2025‑2026» без ссылки — **не подтверждено**.

### 1.8 Как уменьшить предупреждения БЕЗ покупки сертификата

**Что работает** ✅:

1. **Публикация в Microsoft Store (MSIX) — самый надёжный бесплатный путь.** ✅ Дословно:
   > If you publish your app as an MSIX package through the Microsoft Store, code signing is free and handled for you automatically — **Microsoft re-signs the package after certification** and you don't need to purchase or manage a certificate.
   > The simplest way to avoid SmartScreen warnings is to publish through the Microsoft Store. **Store-distributed apps are signed by a Microsoft certificate and are never subject to SmartScreen download warnings.**
   - Регистрация разработчика: **бесплатно** (с 2026‑05‑07, ранее $99 для company) ✅ — [blogs.windows.com](https://blogs.windows.com/windowsdeveloper/2026/05/07/publish-to-microsoft-store-as-a-company-now-with-free-registration-and-faster-onboarding/), [MS Learn](https://learn.microsoft.com/en-us/windows/apps/publish/whats-new-company-developer).
   - ⚠️ **Ограничение для PyInstaller:** MSIX‑путь требует упаковки в MSIX. Путь «MSI/EXE installer submission» **требует** подписи издателем сертификатом, цепочка которого ведёт к CA из Microsoft Trusted Root Program (self‑signed не принимается) ✅ — то есть для PyInstaller это **не** бесплатный путь.

2. **SignPath Foundation — бесплатно, но только для open source.** ✅ См. раздел 2.5.

3. **Накопление репутации подписью** — требует сертификата, то есть денег. ✅

4. **Подача файла в Microsoft на проверку** — ситуация **противоречива, и это важно** ⚠️:
   - Страница [Microsoft Defender SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen) **утверждает, что подача возможна** ✅: «If you believe a warning or block was incorrectly shown for a file or application... submit a file to Microsoft for review... **make sure to select Microsoft Defender SmartScreen from the product menu**». Форма: [microsoft.com/en-us/wdsi/filesubmission](https://www.microsoft.com/en-us/wdsi/filesubmission) (есть роль «**Software developer** — Software providers wanting to validate detection of their products»).
   - Страница репутации **утверждает обратное** ✅: «**There is no need (or mechanism) to manually submit a file for SmartScreen reputation review for consumer endpoints.** Reputation builds organically through download volume.» — и добавляет, что **только корпоративные ИТ‑администраторы** могут опционально подать файл через **Microsoft Security Intelligence portal** для ускорения доверия во внутренних развёртываниях.
   → **Вывод:** единого «report as safe» для потребительского SmartScreen, который выдаёт репутацию по запросу, **не существует**. Форма WDSI предназначена для оспаривания ложных срабатываний / проверки детекций, а не для «выдачи репутации». Практического способа получить репутацию через подачу нет. ⚠️

**Что НЕ работает** ✅ (дословно из таблицы Microsoft):

| Способ | Результат |
|---|---|
| **Самоподписанный сертификат** | ⚠️ **«Same behavior as no signature»** — предупреждение остаётся. Не помогает вообще. |
| Подпись EV | ⚠️ «Same as OV since 2024 — no longer instant bypass» |
| Пересборка / смена имени файла / хеша | Репутация неподписанного файла начинается **с нуля для каждой версии** ✅ |
| **winget** | ✅ Из документации Microsoft: «Regardless of your packaging format, you can submit a manifest to the Windows Package Manager Community Repository... This doesn't replace your existing distribution method — it adds a command-line installation path». В таблице: `winget manifest` → «Cert recommended». **Никакого влияния на SmartScreen в документации нет** ❌ — не подтверждено, что winget помогает. |

Дополнительные рекомендации из документации Microsoft ✅ (для минимизации предупреждений):
- подписывать **каждый** релиз и не менять идентичность подписи;
- не модифицировать файлы после подписи;
- не подписывать потенциально нежелательные приложения (сертификат может получить **негативную** репутацию);
- предупреждать ранних пользователей о возможном предупреждении.

---

## 2. Стоимость сертификатов подписи кода (2025–2026)

**Все цены — ориентировочные прайс‑листовые, в USD, собраны 16 сентября 2026 г.** Итоговые цены зависят от региона, акций и переговоров с CA.

### 2.1 Официальные ориентиры Microsoft (самый авторитетный источник)

✅ [Code signing options for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options), обновлено **2026‑08‑29**:

| Опция | Стоимость (цитата MS) |
|---|---|
| Microsoft Store (MSIX) | **Free** |
| Microsoft Store (MSI/EXE) | «Cert chaining to Trusted Root Program CA required (varies by CA)» |
| Azure Artifact Signing | **~$9.99/month** |
| **OV сертификат** | **$150–300/year** |
| **EV сертификат** | **$400+/year** |
| Самоподписанный | Free |
| Без подписи | Free |

✅ Дублируется на странице [Choose a distribution path](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/choose-distribution-path) (обновлено 2026‑09‑14): «Traditional OV certificates are also accepted (typically **$150–300/year** from a CA)».

### 2.2 Прайс‑листы CA (OV)

| CA | OV, 1 год | OV, 2 года | OV, 3 года | Примечание |
|---|---|---|---|---|
| **SSL.com** | **$129.00** | $116.10/год | $109.65/год | самый дешёвый найденный OV ✅ |
| DigiCert | $696.00 за 12 мес. | — | — | только 12‑мес. подписка |
| Sectigo (Store) | $313.50 (list $379.00) | $265.65/год | $219.45/год | сайт sectigo.com цен в HTML не содержит |
| GlobalSign | $529/год (токен) или **$289/год (HSM)** | **снято с продажи** | **снято с продажи** | 2/3‑летние — последний заказ 26.12.2025 |

### 2.3 Прайс‑листы CA (EV)

| CA | EV, 1 год | EV, 2 года | EV, 3 года |
|---|---|---|---|
| **SSL.com** | **$349.00** | $299.00/год | $249.00/год |
| DigiCert | $972.00 за 12 мес. | — | — |
| Sectigo (Store) | $410.85 (list $498.00) | $349.80/год | $288.20/год |
| GlobalSign | $669/год (токен) или $410/год (HSM) | снято | снято |

⚠️ **Напоминание:** переплата за EV (≈ +$220…+$280/год против OV) **не даёт ничего для SmartScreen** с 2024 года ✅. Microsoft: «EV certificates may matter for enterprise procurement, but they no longer impact SmartScreen behavior».

### 2.4 Почему CA/B Forum заставляет использовать токен / облачный HSM и сколько это стоит

Причина ✅: требование с **1 июня 2023** (раздел 1.7). Ключ **неэкспортируемый**, `.pfx` больше не выдаётся → физический токен нужен на машине сборки, либо нужен облачный сервис подписи.

**Стоимость аппаратных/облачных решений** (16 сентября 2026):

| Решение | Стоимость | Как включено |
|---|---|---|
| **DigiCert KeyLocker** (облачная подпись) | **+$300.00/год** (OV $996 vs $696; EV $1,272 vs $972); OV включает 1 000 подписей/год | **платная надстройка**, не включена ✅ |
| **DigiCert USB‑токен** | +$144.00/год (OV $840 vs $696; EV $1,116 vs $972) | платно |
| **SSL.com eSigner Cloud Code Signing** | Tier 1 **$15.00/мес** (240 подписей, 1 credential); Tier 2 $63.75/мес (1 200); Tier 3 $131.25/мес (3 600); Tier 4 $187.50/мес (12 000). Новым сертификатам — 30 дней бесплатно. Доп. credential $20/мес | **платная подписка**, не включена ✅ |
| **SSL.com USB‑токен / YubiKey** | +$379.00 (страницы OV/EV) либо +$249.00 (страница signing‑service) — страницы противоречат друг другу ⚠️; Express‑доставка +$329.00 | платно |
| **SSL.com аттестация собственного cloud HSM** (разово): AWS CloudHSM $1 500; Google Cloud HSM $500 (на одной странице) / $1 500 (на другой) ⚠️; Azure Dedicated HSM $500 | разово | платно |
| **GlobalSign** | токен **включён** в цену; при этом HSM‑вариант **дешевле**: OV $289/год, EV $410/год | включено ✅ |
| **Sectigo** | «Free FIPS‑Compliant token will be shipped to you each year» — **включён** | включено ✅ |
| **Azure Artifact Signing** | **$9.99/мес** — HSM не нужен вообще (ключи в FIPS 140‑3 Level 3 HSM Microsoft) | сама услуга ✅ |
| **SignPath.io** | HSM SignPath (KMS/HSM), отдельная покупка токена не нужна | сама услуга ✅ |

❌ **Не подтверждено:** цена отдельной доставки/обработки токена у DigiCert; цена Sectigo Certificate Manager / Signing Manager (найденная страница `sectigo.com/enterprise/code-signing` отдавала HTTP 404); цена GlobalSign Atlas Auto Enrollment; стоимость DigiCert Software Trust Manager как отдельного SKU.

### 2.5 Azure Artifact Signing (ранее «Azure Trusted Signing», изначально «Azure Code Signing»)

**Точное текущее название: Azure Artifact Signing** ✅. Переименован из **Azure Trusted Signing**; старый адрес `/azure/trusted-signing/overview` редиректит на `/azure/artifact-signing/overview`. Страница обновлена **2026‑05‑12**.
Источник: [What is Artifact Signing?](https://learn.microsoft.com/en-us/azure/artifact-signing/overview).

**Что это** ✅: полностью управляемый Microsoft сервис подписи; нулевое сопровождение жизненного цикла сертификатов внутри **HSM уровня FIPS 140‑3 Level 3**; интеграция с GitHub Actions, Azure DevOps и др.; поддерживает Public Trust, Private Trust, VBS enclave, CI policy, test signing; «content‑confidential signing» — файл не покидает вашу машину (подписывается дайджест).

**Статус: GA (общая доступность), не public preview** ✅ — в текущей документации нет пометки preview (слово «preview» встречается только как флаг CLI и как «Certificat**e** subject preview»), а сервис имеет опубликованные розничные цены с **2024‑06‑01**. Ребрендинг в Artifact Signing и GA состоялись в 2026 году.
⚠️ Первоначально сервис запускался как public preview (2024) — это исторический факт, в текущем состоянии **GA** ✅.

**Цены — подтверждено официальным Azure Retail Prices API** ✅ (запрос 2026‑09‑16, `serviceName eq 'Trusted Signing'`, `effectiveStartDate 2024-06-01`):

| SKU | Цена | Квота подписей/мес |
|---|---|---|
| **Basic** | **$9.99/мес** | **5 000** |
| **Premium** | **$99.99/мес** | **100 000** |
| Signature Overage | **$0.005 за подпись** | сверх квоты |

**Ответ на вопрос «есть ли тариф $9.99/мес»: ДА, подтверждено** ✅ — и в API, и в документации («Cost — Starts at $9.99/month», «Cost: Approximately $9.99/month»), и на странице цен ([Azure Artifact Signing pricing](https://azure.microsoft.com/en-us/pricing/details/artifact-signing/): Basic $9.99/мес, Premium $99.99/мес).
⚠️ Тарификация **не пропорциональна**: «The pricing is not calculated on a pro rata basis. The invoice is generated with the full amount for the SKU that you selected» ✅.

**Требования к участию (eligibility)** ✅ — [quickstart](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart):

- **Требуется подписка Azure** ✅ и **ID тенанта Microsoft Entra** ✅ (явно в Prerequisites).
- **Public Trust — география организаций** ✅, дословно: «available to organizations in the **United States, Canada, the European Union, the United Kingdom, Australia, New Zealand, Japan, South Korea, Singapore, Switzerland, Norway, and Israel**».
  ⚠️ **Противоречие между страницами Microsoft:** страница [Code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) (2026‑08‑29) даёт более узкий список: «Organizations: **USA, Canada, EU, UK**». Быстро меняющийся список — уточняйте на дату заказа.
- **Индивидуальные разработчики: только США и Канада** ✅, дословно: «**Individual developers must be located in the United States or Canada.**»
- Географические ограничения **не применяются** к Private Trust ✅.
- **Индивидуальный разработчик (ИП / sole proprietor / физлицо) — ДОПУСТИМ** ✅, отдельная процедура «Individual identity validation»: данные берутся из billing account Azure, у которого **Account Type должен быть Individual**, а legal name и sold‑to‑address должны совпадать с государственным удостоверением. ❌ (Обратите внимание: ИП/самозанятый **вне** США/Канады — не подходит.)
- **Организационная валидация**: требуется юридическое лицо, домен, основной и дополнительный e‑mail на домене организации, бизнес‑идентификатор, адрес ✅.
- **Сроки проверки: от 1 до 20 рабочих дней** (иногда дольше, если запросят документы) ✅. На загрузку документов — **три попытки** ✅.
- **Нельзя задать произвольные CN/O**: FAQ прямо указывает, что кастомизация не поддерживается, а CN обязан быть валидированным юридическим именем (требование CA/B Forum CSBR) ✅.
- Проверка личности выполняется **только в портале Azure** (через CLI нельзя) ✅; нужна роль **Artifact Signing Identity Verifier** ✅.

**Про требование «3 года проверяемой истории бизнеса» — ❌ НЕ ПОДТВЕРЖДЕНО (и, вероятно, снято):**
- Это условие было объявлено в блоге Microsoft «Trusted Signing Public Preview Update» от **1 апреля 2025** ⚠️ (первоисточник — блог Tech Community, который мне не удалось прочитать: страница отдаётся через JS).
- В **текущей документации** (quickstart, FAQ, overview) этого требования **НЕТ** — там только географические ограничения ✅. Были вопросы пользователей именно об этом (например, [ветка от 2026‑08‑18](https://learn.microsoft.com/en-in/answers/questions/5979123/artifact-signing-organization-identity-validation) — **без ответа Microsoft**).
- → Считайте требование **не подтверждённым на текущую дату**: возможно, оно снято (как снято ограничение «только США и Канада»), но официального подтверждения нет. ❌

**SmartScreen для Artifact Signing** ✅: «⚠️ Reputation builds over time; initial warnings expected», «Azure Artifact Signing **does not provide instant SmartScreen trust**».

**Плюс:** не требует физического токена ✅ и интегрируется в CI/CD ✅ — то есть решает и проблему CA/B Forum, и проблему SmartScreen (после накопления репутации) за ~$120/год.

### 2.6 SignPath Foundation — бесплатно для open source

**Точное название: SignPath Foundation** ✅. **Бесплатно для OSS** ✅ — дословно:
> Free Code Signing for Open Source software... **For OSS projects, our services are free of charge.**
— [signpath.org](https://signpath.org/)

**Чей это сертификат и что видит пользователь** ✅ — дословно из [условий](https://signpath.org/terms.html):
> **The code signing certificate is issued to SignPath Foundation. This means that SignPath Foundation is the publisher of the OSS project.**

→ **Подпись покажет «SignPath Foundation» как издателя, а не вас и не ваш проект.** ✅ Это подтверждается и Microsoft: «provides OV‑level certificate signing through a managed pipeline» ✅.
SignPath **не является CA** и не может выдавать сертификаты ✅: «Since we are not a Certificate Authority (CA), we cannot issue certificates to you, your project, or anybody else... What we actually do is get certificates issued to "SignPath Foundation" and let OSS projects use them.»

**Критерии участия (дословно)** ✅ — [signpath.org/terms.html](https://signpath.org/terms.html):

*Условия бесплатной OSS‑подписки:*
- «**No malware**: The project must not contain malware or potentially unwanted programs.»
- «**OSS License**: The project must use an **OSI‑approved Open Source license** without commercial dual‑licensing for all components.» ← **именно то, о чём вы спрашивали: лицензия должна быть одобрена OSI, и без коммерческого dual‑licensing**
- «**No proprietary code**: The project may not contain any proprietary, non open‑source component (especially code published by a maintainer or an affiliated person/organization).» (можно включать System Libraries — см. §1 GPLv3)
- «**Maintained**: The project must be actively maintained.»
- «**Released**: The project must already be released in the form that should be signed.» ← **нельзя подписать то, что ещё не выпущено**
- «**Documented**: The project's functionality must be described on its download page or in the app store entry...»

*Дополнительно для сертификата SignPath Foundation:*
- «**No hacking tools**» (инструменты для эксплуатации уязвимостей не подписываются)
- «Sign your own projects only» / «Sign your own binaries only»
- Уважение приватности, предупреждение об изменениях системы, наличие деинсталляции
- «All team members must use **multi‑factor authentication**»
- Роли: **Authors / Reviewers / Approvers**; каждый signing request требует одобрения
- **Публичный репозиторий** явно не требуется как отдельный пункт ⚠️ — требуется владение репозиторием, верифицируемая сборка из исходников и «code signing policy» на главной странице проекта. Требование «public repo» **дословно не найдено** → ❌ не подтверждено (но по смыслу требуется наличие исходников и репозитория).
- На главной/странице загрузок должна быть указана политика подписи с точной формулировкой: **«Free code signing provided by SignPath.io, certificate by SignPath Foundation»**

**Критично — не всякий OSS‑проект примут** ✅, дословно:
> **Any project can get a SignPath certificate** — Since our name is on the certificate, our name and reputation is at stake. We cannot risk signing malware or other unwanted software... For executable programs that may be downloaded and executed based on our signature, **we require a certain verifiable reputation**. (Not for developer libraries/components/packages though.)
> **We're under no obligation to accept your project, and there is no independent arbitration mechanism.**

→ То есть для малоизвестного приложения SignPath **вправе отказать**. ✅

**Итого: это действительно бесплатно, но (а) только для OSI‑OSS, (б) издатель в подписи — SignPath Foundation, (в) приём не гарантирован.** ✅

### 2.7 Другие бесплатные / дешёвые варианты

- **Microsoft Store (MSIX)** — **бесплатно**, и **единственный бесплатный путь, полностью убирающий предупреждения SmartScreen** ✅ (Store переподписывает пакет своим сертификатом). Регистрация разработчика бесплатна с 2026‑05‑07 ✅ (см. 1.8). ⚠️ Для PyInstaller требует упаковки в MSIX.
- **.NET Foundation** ⚠️: Authenticode‑подпись остаётся заявленной льготой проектов фонда — «We provide support services for our projects including **Authenticode code‑signing of binaries and installers**...» ([dotnetfoundation.org/projects/benefits](https://dotnetfoundation.org/projects/benefits)). Отдельная плата не указана. ❌ Активно ли это в 2026 году — **не подтверждено**. Кроме того, это льгота для проектов фонда, а не общая программа для всех OSS.
- **SignPath.io — коммерческие тарифы** ❌ **не подтверждено**: `signpath.io/pricing`, `about.signpath.io/pricing`, `signpath.io/plans` отдают 404; `sitemap.xml` не содержит страницы цен. Прайс непубличен (или доступен только по запросу).
- **Google / Mozilla / прочие программы подписи Windows‑бинарников для OSS** ❌ **не подтверждено** — таких программ обнаружить не удалось (не подтверждено ни в пользу их существования, ни против).
- **Microsoft Store MSI/EXE installer path** ⚠️ — **не** бесплатный: требуется сертификат от CA в Microsoft Trusted Root Program, self‑signed не принимается ✅.
- **winget** ⚠️ — по документации Microsoft не требует подписи (но требование и не отрицается ❌) и **не даёт никакого эффекта для SmartScreen** ❌.

### 2.8 Прямой ответ: для закрытого проекта бесплатного OV нет

✅ **Подтверждено.** OV‑сертификат:
- выдаётся только CA (DigiCert, Sectigo, SSL.com, GlobalSign и др.) и **стоит денег ежегодно**;
- минимальная найденная цена — **$129/год** (SSL.com, 1 год), типичный диапазон по Microsoft — **$150–300/год**, DigiCert — **$696/год**;
- **бесплатных программ OV‑сертификатов для закрытого ПО не существует** ❌ (не найдено ни одной);
- бесплатные варианты (SignPath Foundation, .NET Foundation) требуют **open source** ✅;
- единственный бесплатный путь к отсутствию предупреждений — **Microsoft Store (MSIX)**, что подразумевает публикацию в Store и упаковку MSIX.

⚠️ Отдельно: **самоподписанный сертификат для закрытого проекта — бесполезен** для публичного распространения ✅ («Same behavior as no signature», «Blocks installation for public users»). Он применим только для локальной разработки и для внутреннего корпоративного развёртывания с управляемым доверием (Intune / Group Policy).

---

## 3. Практические выводы для неподписанного PyInstaller‑приложения

| Сценарий | Что увидит пользователь |
|---|---|
| Вы собрали `.exe` и запускаете локально | ничего ✅ |
| Пользователь копирует onedir из сетевой папки / UNC | **ничего** — SmartScreen не проверяет сетевые расположения ✅ |
| Пользователь скачал `.exe` браузером | SmartScreen: «Windows protected your PC» + «Run anyway» ✅ |
| Пользователь скачал `.zip` и распаковал Explorer'ом | то же самое (MOTW переносится на извлечённый `.exe`) ⚠️ |
| Любой из вариантов у пользователя с Smart App Control | **блокировка** неподписанного кода ✅ |
| Любой запуск с запросом прав администратора, без подписи | UAC с жёлтым фоном и «Unknown publisher» ✅ (текст фразы ❌) |
| Установка per‑user без запроса админа | **UAC не появляется** ⚠️ (следствие из механизма UAC) |

**Что реально снижает проблему без сертификата:**
1. Публикация в Microsoft Store как MSIX — бесплатно, предупреждений нет ✅.
2. Для OSS — SignPath Foundation ✅.
3. Предупреждение пользователей + инструкция «More info → Run anyway» ⚠️ (UI‑порядок не подтверждён документацией).
4. Установка per‑user без запроса прав администратора — убирает UAC‑часть проблемы ⚠️.
5. ❌ Подача в Microsoft «на проверку» репутации **не даёт** — механизма для потребительского SmartScreen нет ✅.

**Что не поможет:** самоподписанный сертификат ✅, EV «ради SmartScreen» ✅, winget ❌, переименование/пересборка ✅.

**Минимальный платный путь:** Azure Artifact Signing, **$9.99/мес** — но требуется подписка Azure, юрлицо из списка стран (или физлицо из США/Канады), и мгновенного доверия не будет: репутация накапливается неделями ✅.

---

## 4. Сводный список «не подтверждено»

1. ❌ Дословная вторая строка диалога SmartScreen («Microsoft Defender SmartScreen prevented an unrecognized app from starting. Running this app might put your PC at risk.») — в продуктовой документации Microsoft не найдена.
2. ❌ Наличие ссылки «More info» в диалоге SmartScreen — документацией Microsoft не подтверждено.
3. ❌ «SmartScreen запоминает исключение для последующих запусков» — не подтверждено документацией.
4. ❌ Дословный текст UAC «Do you want to allow this app from an unknown publisher to make changes to your device?» — только пользовательский контент.
5. ❌ Манифест PyInstaller по умолчанию (`asInvoker`) и поведение `--uac-admin` — документацию получить не удалось.
6. ❌ Требование «3 года проверяемой истории бизнеса» для Azure Artifact Signing — в текущей документации отсутствует; первоисточник (блог 2025‑04‑01) недоступен для проверки; официального опровержения нет.
7. ❌ Отдельные «ужесточения политик Microsoft Defender 2025–2026», затрагивающие неподписанные приложения — не найдены.
8. ❌ Любая польза winget для SmartScreen — в документации отсутствует.
9. ❌ Наличие программ Google / Mozilla / иных фондов по подписи Windows‑бинарников для OSS.
10. ❌ Коммерческие тарифы SignPath.io — прайс непубличен (страницы 404).
11. ❌ Активность программы Authenticode‑подписи .NET Foundation в 2026 году.
12. ❌ Стоимость доставки/обработки токена DigiCert; тарифы Sectigo Certificate/Signing Manager; GlobalSign Atlas Auto Enrollment; отдельный SKU DigiCert Software Trust Manager.
13. ❌ Грандфазеринг сертификатов, выпущенных до 2023‑06‑01, — явной формулировки в CSBR нет (в тексте нет ни дедлайна сверх 2023‑06‑01, ни оговорки о «старых» сертификатах).
14. ❌ Требование публичного репозитория у SignPath Foundation — дословно в условиях не найдено.
15. ⚠️ Противоречие между страницами Microsoft по географии Artifact Signing (расширенный список в quickstart против «USA, Canada, EU, UK» в code-signing-options).
16. ⚠️ Противоречие внутри документации Microsoft о подаче файла на проверку (SmartScreen-страница говорит, что можно; страница репутации — что механизма для потребителей нет).
17. ⚠️ Противоречие прайс‑страниц SSL.com по цене USB‑токена ($379 против $249) и аттестации Google Cloud HSM ($500 против $1 500).

---

## 5. Источники

**Microsoft:**
- [SmartScreen reputation for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) (обновлено 2026‑05‑06)
- [Code signing options for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) (обновлено 2026‑08‑29)
- [Choose a distribution path for your Windows app](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/choose-distribution-path) (обновлено 2026‑09‑14)
- [Microsoft Defender SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen)
- [Smart App Control](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/overview)
- [How User Account Control works](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/user-account-control/how-it-works)
- [Macros from the internet are blocked by default in Office](https://learn.microsoft.com/en-us/microsoft-365-apps/security/internet-macros-blocked) (описание MOTW / Zone.Identifier)
- [What is Artifact Signing?](https://learn.microsoft.com/en-us/azure/artifact-signing/overview)
- [Artifact Signing quickstart (identity validation, eligibility)](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)
- [Artifact Signing FAQ](https://learn.microsoft.com/en-us/azure/artifact-signing/faq)
- [Azure Artifact Signing pricing](https://azure.microsoft.com/en-us/pricing/details/artifact-signing/) и [Azure Retail Prices API](https://prices.azure.com/api/retail/prices)
- [Revamped company onboarding experience with zero registration fees](https://learn.microsoft.com/en-us/windows/apps/publish/whats-new-company-developer)
- [Publish to Microsoft Store as a company — now with free registration](https://blogs.windows.com/windowsdeveloper/2026/05/07/publish-to-microsoft-store-as-a-company-now-with-free-registration-and-faster-onboarding/) (2026‑05‑07)
- [Submit a file for malware analysis](https://www.microsoft.com/en-us/wdsi/filesubmission)

**CA/Browser Forum:**
- [Code Signing Baseline Requirements v3.11.0 (16 июня 2026)](https://cabforum.org/working-groups/code-signing/requirements/)
- [Ballot CSC‑17 Subscriber Private Key Extension](https://cabforum.org/2022/09/27/ballot-csc-17-subscriber-private-key-extension/)

**SignPath:**
- [signpath.org](https://signpath.org/)
- [SignPath Foundation — условия участия](https://signpath.org/terms.html)

**CA / прайс‑листы:**
- [DigiCert code signing](https://www.digicert.com/signing/code-signing-certificates), [сравнение](https://www.digicert.com/signing/compare-code-signing-certificates)
- [Sectigo code signing](https://www.sectigo.com/ssl-certificates-tls/code-signing), [Sectigo Store OV](https://sectigostore.com/code-signing/sectigo-code-signing-certificate), [Sectigo Store EV](https://sectigostore.com/code-signing/sectigo-ev-code-signing-certificate)
- [SSL.com OV](https://www.ssl.com/products/software-integrity/code-signing/ov/), [SSL.com EV](https://www.ssl.com/products/software-integrity/code-signing/ev/), [SSL.com signing service](https://www.ssl.com/products/software-integrity/signing-service/)
- [GlobalSign shop](https://shop.globalsign.com/en/code-signing)
- [GlobalSign: New Requirements related to Private Key protection](https://support.globalsign.com/code-signing/advisory/new-requirements-related-private-key-protection-codesigning-certificates)

**Прочее:**
- [DFIR: Mark‑of‑the‑Web: the rules changed, the tools didn't (2026‑06‑29)](https://dfir.ru/2026/06/29/mark-of-the-web-the-rules-changed-the-tools-didnt/)
- [.NET Foundation project benefits](https://dotnetfoundation.org/projects/benefits)
- [7‑Zip MOTW bypass](https://blog.zerowl.io/7-zip-mark-of-the-web-bypass-lets-malicious-files-evade-windows-smartscreen)
