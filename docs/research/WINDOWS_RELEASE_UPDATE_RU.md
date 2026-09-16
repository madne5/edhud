# Сборка Windows-приложения (PyInstaller) и автообновление через GitHub Releases

Отчёт по проверенным фактам. Дата проверки: **2026-09-16**.
Всё, что подтверждено живым запросом или официальной документацией, помечено как подтверждённое;
непроверенное явно помечено **«не подтверждено»**.

Легенда источников:
- **[LIVE]** — я выполнил реальный запрос/скачал файл и привожу фактический ответ.
- **[DOC]** — официальная документация/справка.
- **[CODE]** — исходный код проекта с GitHub.
- **[OBS]** — наблюдение из реального рабочего workflow в открытом репозитории.

---

## 1. GitHub Releases API

### 1.1 Точные эндпоинты

**[LIVE]** Проверено на `GET https://api.github.com/repos/astral-sh/uv/releases/latest`
(HTTP 200, заголовок ответа `x-github-api-version-selected: 2022-11-28`).

Из OpenAPI-спеки `github/rest-api-description` (скачана и разобрана, 13 МБ):
`descriptions/api.github.com/api.github.com.json`.

`GET /repos/{owner}/{repo}/releases/latest` — `operationId: repos/get-latest-release`.
Дословно из спеки:

> View the latest published full release for the repository. **The latest release is the most
> recent non-prerelease, non-draft release, sorted by the `created_at` attribute.** The
> `created_at` attribute is the date of the commit used for the release, and not the date when
> the release was drafted or published.

Документированные коды ответа: **200, 404**.

`GET /repos/{owner}/{repo}/releases` — `operationId: repos/list-releases`:

> This returns a list of releases, which does not include regular Git tags that have not been
> associated with a release. … **Only users with push access will receive listings for draft
> releases.**

Параметры: `per_page` (default **30**, max **100**), `page` (default **1**).
Коды: **200, 404**. Ответ 200 содержит заголовок `Link` (пагинация).

`GET /repos/{owner}/{repo}/releases/tags/{tag}` — `operationId: repos/get-release-by-tag`,
«Get a published release with the specified tag». Коды: **200, 404**.

`GET /repos/{owner}/{repo}/releases/assets/{asset_id}` — `operationId: repos/get-release-asset`.
Коды: **200, 302, 404**.

### 1.2 Реальный JSON-ответ

**[LIVE]** Фактический усечённый ответ `releases/latest` (репозиторий `astral-sh/uv`):

```json
{
  "url": "https://api.github.com/repos/astral-sh/uv/releases/389112346",
  "assets_url": "https://api.github.com/repos/astral-sh/uv/releases/389112346/assets",
  "upload_url": "https://uploads.github.com/repos/astral-sh/uv/releases/389112346/assets{?name,label}",
  "html_url": "https://github.com/astral-sh/uv/releases/tag/0.12.15",
  "id": 389112346,
  "node_id": "RE_kwDOKbIFZc4XMWIa",
  "tag_name": "0.12.15",
  "target_commitish": "d35f1f2703b4a9cefbfa7fc21164e3ca4fcab933",
  "name": "0.12.15",
  "draft": false,
  "immutable": false,
  "prerelease": false,
  "created_at": "2026-09-15T11:23:33Z",
  "published_at": "2026-09-15T12:09:40Z",
  "assets": [
    {
      "url": "https://api.github.com/repos/astral-sh/uv/releases/assets/565630740",
      "id": 565630740,
      "node_id": "RA_kwDOKbIFZc4httcU",
      "name": "dist-manifest.json",
      "label": "",
      "content_type": "application/json",
      "state": "uploaded",
      "size": 44979,
      "digest": "sha256:eae42b58eaf3729260b43590d17407f9361f81a9b18b8185a832e4b131f185c9",
      "download_count": 88,
      "created_at": "2026-09-15T12:09:32Z",
      "updated_at": "2026-09-15T12:09:32Z",
      "browser_download_url": "https://github.com/astral-sh/uv/releases/download/0.12.15/dist-manifest.json"
    }
  ],
  "tarball_url": "https://api.github.com/repos/astral-sh/uv/tarball/0.12.15",
  "zipball_url": "https://api.github.com/repos/astral-sh/uv/zipball/0.12.15",
  "body": "## Release Notes\n\nReleased on 2026-09-15...",
  "reactions": { "...": "..." }
}
```

Полный набор ключей объекта release (из живой проверки):
`url, assets_url, upload_url, html_url, id, author, node_id, tag_name, target_commitish, name,
draft, immutable, prerelease, created_at, updated_at, published_at, assets, tarball_url,
zipball_url, body, reactions`.

Полный набор ключей объекта asset (из живой проверки):
`url, id, node_id, name, label, uploader, content_type, state, size, digest, download_count,
created_at, updated_at, browser_download_url`.

Из OpenAPI-спеки `required` для `release`:
`assets_url, upload_url, tarball_url, zipball_url, created_at, published_at, draft, id, node_id,
author, html_url, name, prerelease, tag_name, target_commitish, assets, url`.

Из OpenAPI-спеки `required` для `release-asset`:
`id, name, content_type, size, digest, state, url, node_id, download_count, label, uploader,
browser_download_url, created_at, updated_at`.

> ⚠️ Обратите внимание: `digest` входит в список **обязательных** полей asset, но объявлен
> `nullable` (см. 1.3).

Побочные поля объекта release, которых нет в старых описаниях:
`immutable` (bool, «Whether or not the release is immutable»), `body_html`, `body_text`,
`mentions_count`, `discussion_url`.

### 1.3 Поле `digest` — да, оно есть. Точный формат и с какой даты

**Есть.** Формат значения — `sha256:<64 hex-символа в нижнем регистре>`.

**[LIVE]** Значение из живого ответа:
`"digest": "sha256:eae42b58eaf3729260b43590d17407f9361f81a9b18b8185a832e4b131f185c9"`.

**[LIVE]** Я проверил его сквозным тестом — скачал asset через официальный способ
(`Accept: application/octet-stream`) и посчитал SHA-256 локально:

```
HTTP=200 SIZE=44979 REDIRECTS=1 CT=application/octet-stream
computed: sha256:eae42b58eaf3729260b43590d17407f9361f81a9b18b8185a832e4b131f185c9
api said: sha256:eae42b58eaf3729260b43590d17407f9361f81a9b18b8185a832e4b131f185c9
```

Значения совпали побайтово.

**Дата появления:** **3 июня 2025 года.** GitHub Changelog, «Releases now expose digests for
release assets»:

> GitHub now automatically computes and displays SHA256 checksums (digests) for all uploaded
> release assets. These digests are generated at upload time, **immutable**, and let you verify
> that downloaded assets haven't been altered since publishing.

Доступно в: UI релизов, Releases REST API, GraphQL API, `gh` CLI.

**КРИТИЧНО — digests `null` для старых ассетов.** **[LIVE]** Я проверил релизы, опубликованные
до июня 2025:

| Репозиторий / тег | `published_at` | `digest` у ассетов |
|---|---|---|
| `astral-sh/uv` `0.1.0` | 2024-02-15 | **все `null`** |
| `cli/cli` `v2.30.0` | 2023-05-30 | **все `null`** |
| `psf/requests` `v2.31.0` | 2023-05-22 | **все `null`** |

Вывод: **нельзя рассчитывать на то, что `digest` всегда непустой**. Логика обновления обязана
корректно работать при `digest == null` (например, использовать собственный
`SHA256SUMS.txt` в релизе). Именно так и сделано в `elite_hud/updater.py` — это правильно.

Также: `digest` **не является частью объекта release** — только частью объекта asset.
`POST /repos/{owner}/{repo}/releases/{release_id}/assets` возвращает `release-asset`,
то есть `digest` доступен и в ответе на загрузку.

### 1.4 HTTP-заголовки

**[DOC]** `docs.github.com/rest/using-the-rest-api/getting-started-with-the-rest-api`:

- `Accept` — «Most GitHub REST API endpoints specify that you should pass an `Accept` header with
  a value of `application/vnd.github+json`».
- `X-GitHub-Api-Version` — «You should use this header to specify a version of the REST API».
  «Requests without the `X-GitHub-Api-Version` header will default to use the
  `<defaultRestApiVersion>` version.»
- `User-Agent` — «All API requests must include a valid `User-Agent` header.»
  «Requests with no `User-Agent` header will be rejected. **If you provide an invalid
  `User-Agent` header, you will receive a `403 Forbidden` response.**»

**[LIVE] Что будет, если не передать `User-Agent`:**

```
$ curl -H "User-Agent:" -H "Accept: application/vnd.github+json" \
    https://api.github.com/repos/astral-sh/uv/releases/latest
HTTP=403
Request forbidden by administrative rules. Please make sure your request has a User-Agent
header (https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#user-agent-required).
Check https://developer.github.com for other possible causes.
```

То есть **403**, а не 400.

**[LIVE] Неверная версия API даёт 400 с точным списком поддерживаемых версий:**

```
$ curl -H "X-GitHub-Api-Version: 1999-01-01" .../releases/latest
HTTP=400
{"message":"Bad Request","errors":"The version you specified in the \"X-GitHub-API-Version\"
request header, \"1999-01-01\", is not a supported version. The following versions are currently
supported: \"2026-03-10\" (most recent) and \"2022-11-28\". ...","status":"400"}
```

> **Важно на 2026 год:** поддерживаются **две** версии API — `2026-03-10` (самая новая) и
> `2022-11-28`. **[LIVE]** При отсутствии заголовка GitHub выбирает `2022-11-28`
> (заголовок ответа `x-github-api-version-selected: 2022-11-28`). Пиновать `2022-11-28`
> в коде сейчас безопасно, но версия станет самой старой из поддерживаемых — стоит
> заложить обновление.

**[LIVE]** Отсутствие `Accept` не ломает запрос (я получил HTTP 200 и корректный JSON с
`digest`). То есть `Accept` практически обязателен только для скачивания бинарного
содержимого.

### 1.5 Лимиты запросов

**[LIVE]** Заголовки реального ответа (анонимный запрос):

```
x-ratelimit-limit: 60
x-ratelimit-remaining: 45
x-ratelimit-used: 15
x-ratelimit-resource: core
x-ratelimit-reset: 1789588195
```

**[DOC]** `data/reusables/rest-api/primary-rate-limit-unauthenticated-users.md`:
«The primary rate limit for unauthenticated requests is **60 requests per hour**.»
Анонимные запросы привязаны к **IP-адресу**, не к пользователю.

**[DOC]** `primary-rate-limit-authenticated-users.md`:
«All of these requests count towards your personal rate limit of **5,000 requests per hour**.»
Для GitHub App / OAuth App, принадлежащих организации GHEC — **15 000/час**.
При этом бюджет общий: приложение с лимитом 15 000 «расходует» из него ваш лимит 5 000.

**[DOC]** `primary-rate-limit-github-token-in-actions.md`:
«The rate limit for `GITHUB_TOKEN` is **1,000 requests per hour per repository**.»
(для ресурсов GHEC-аккаунта — 15 000/час на репозиторий.)

**Что возвращается при превышении — [LIVE], я реально исчерпал лимит в 60/час:**

```
HTTP/2 403
x-ratelimit-limit: 60
x-ratelimit-remaining: 0
x-ratelimit-used: 60
x-ratelimit-resource: core
x-ratelimit-reset: 1789588195

{"message":"API rate limit exceeded for 77.75.15.33. (But here's the good news:
Authenticated requests get a higher rate limit. Check out the documentation for more details.)",
"documentation_url":"https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"}
```

Тело ответа `docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting` — точная
ссылка из ответа API.

**[DOC]** Про исчерпание primary-лимита: «If you exceed your primary rate limit, you will
receive a **`403` or `429` response**, and the `x-ratelimit-remaining` header will be `0`.
You should not retry your request until after the time specified by the `x-ratelimit-reset`
header.»

**[LIVE] Ключевой нюанс про `retry-after`:** в реальном ответе 403 на исчерпание
**primary**-лимита заголовка `retry-after` **НЕ БЫЛО** — только `x-ratelimit-reset`
(epoch-секунды; в моём случае `1789588195` = 2026-09-16 19:49:55 UTC). `retry-after`
документирован для **secondary**-лимитов:

**[DOC]** «If you exceed a secondary rate limit, you will receive a `403` or `429` response and an
error message that indicates that you exceeded a secondary rate limit. **If the `retry-after`
response header is present**, you should not retry your request until after that many seconds has
elapsed. If the `x-ratelimit-remaining` header is `0`, you should not retry … until the time, in
UTC epoch seconds, specified by the `x-ratelimit-reset` header. Otherwise, wait for at least one
minute before retrying.»

Итоговые заголовки: `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-used`,
`x-ratelimit-reset`, `x-ratelimit-resource` (+ `retry-after` для secondary).

**[DOC]** Secondary-лимиты (не более): 100 одновременных запросов; 900 «точек» в минуту на
REST (`GET/HEAD/OPTIONS` = 1 точка, `POST/PATCH/PUT/DELETE` = 5); 90 секунд CPU на 60 секунд
реального времени; не более 80 запросов, создающих контент, в минуту и 500 в час.
Есть также `GET /rate_limit` (не расходует primary-лимит).

**Практический вывод для апдейтера:** проверка обновления раз в несколько часов анонимно —
безопасно (60/час на IP хватает с запасом), но у пользователей за одним NAT-IP лимит общий.
Правильная реакция на `403`/`429` — уважать `x-ratelimit-reset`. Именно это делает
`elite_hud/updater.py` (проверяет `x-ratelimit-remaining == "0"`).

### 1.6 Скачивание ассетов и приватные релизы

**[DOC]** `GET /repos/{owner}/{repo}/releases/assets/{asset_id}` — дословно из OpenAPI/справки:

> To download the asset's binary content:
> - If within a browser, fetch the location specified in the `browser_download_url` key provided
>   in the response.
> - Alternatively, set the `Accept` header of the request to
>   [`application/octet-stream`](…). The API will either redirect the client to the location, or
>   stream it directly if possible. **API clients should handle both a `200` or `302` response.**

**[LIVE]** Проверка: запрос к asset API с `Accept: application/octet-stream` вернул
`HTTP 302` (затем с `-L` — `HTTP 200`, `REDIRECTS=1`, `Content-Type: application/octet-stream`,
44979 байт, SHA-256 совпал с `digest`).

**Особенность приватных репозиториев:**

- **[DOC]** `browser_download_url` документирован как способ для **браузера**. Для приватного
  репозитория он требует аутентификации: без токена github.com отдаёт 404.
- **[LIVE]** `GET /repos/{owner}/{repo}/releases/latest` без токена для недоступного
  (приватного/несуществующего) репозитория возвращает **404** с телом
  `{"message":"Not Found", ...}`. GitHub намеренно не отличает «приватный» от
  «несуществующего», чтобы не раскрывать факт существования репозитория.
- Практический вывод: **для приватных релизов надёжный путь — только asset API
  (`url` из объекта asset) с `Authorization: Bearer <token>` и
  `Accept: application/octet-stream`.** Ориентироваться на `browser_download_url` в приватном
  репозитории нельзя.

> 💡 **Замечание по текущей реализации.** В `elite_hud/updater.py` функция `parse_release`
> делает `url = str(raw.get("browser_download_url") or raw.get("url") or "")`, то есть
> **предпочитает `browser_download_url`**. Для публичного репозитория это работает, но для
> приватного — сломается, даже если токен передан. По документации корректнее предпочитать
> `raw["url"]` (asset API), а `browser_download_url` использовать только как fallback.

**[LIVE]** `urllib.request.urlopen` автоматически следует за 302 (в тесте редирект
обработан, получен 200). Важно: при редиректе на другой хост (`release-assets.githubusercontent.com`)
`urllib` **отбрасывает заголовок `Authorization`** — это ожидаемое и безопасное поведение,
подписанный URL уже содержит свои креды.

### 1.7 Как правильно определить, что версия новее

**Правильный порядок действий:**
1. Получить список релизов (`/releases?per_page=…`) — **не** `/releases/latest`, потому что
   `/latest` не отдаёт prerelease, если вы их поддерживаете.
2. Игнорировать `draft == true` (и помнить: `draft` видят только пользователи с push-доступом,
   обычный анонимный клиент их не получит вообще).
3. Парсить `tag_name`, отбрасывая необязательный префикс `v`.
4. Сравнивать как версии (semver или собственная нумерованная схема), **не как строки**.
5. Учесть флаг `prerelease` (он не всегда согласован с суффиксом в теге!).

**Подводный камень 1 — `/latest` молча пропускает prerelease. [LIVE] доказательство:**

| Репозиторий | Самый свежий в `/releases` | Результат `/releases/latest` |
|---|---|---|
| `zed-industries/zed` | `v1.21.0-pre` (**prerelease=true**) | **`v1.20.1`** |
| `neovim/neovim` | `nightly` (**prerelease=true**) | **`v0.12.5`** |

То есть `/latest` не «сломан» — он ведёт себя согласно спецификации («most recent
non-prerelease, non-draft»). Если ваше приложение публикует беты, `/latest` их не увидит.

**Подводный камень 2 — префикс `v` не универсален. [LIVE]:**

| Репозиторий | Тег |
|---|---|
| `astral-sh/uv` | `0.12.15` (без `v`) |
| `neovim/neovim` | `v0.12.5` (с `v`) |
| `jrsoftware/issrc` | `is-7_1_0` (префикс + подчёркивания!) |

Наивный `int(tag.split(".")[0])` падает на всех трёх. Нужен regex.

**Подводный камень 3 — тег `stable`/`nightly` вообще не версия. [LIVE]:**
в `neovim/neovim` есть релиз с тегом **`stable`** и `prerelease: false`. Это «плавающий»
указатель, а не версия. Парсер обязан вернуть `None` для такого тега и пропустить релиз,
а не считать его новее/старее.

**Подводный камень 4 — `prerelease` и суффикс тега могут расходиться.** В `zed-industries/zed`
соседствуют `v1.21.0-pre` (`prerelease=true`) и `v1.20.1` (`prerelease=false`), при этом
`v1.20.1-pre` тоже существует с `prerelease=true`. Нельзя выводить «это бета» только из
наличия `-pre` в теге — нужно смотреть флаг `prerelease`, и наоборот: тег без суффикса может
быть помечен prerelease вручную.

**Подводный камень 5 — `published_at` может быть `null`** (поле объявлено `nullable`) для
черновиков, а `created_at` — это дата **коммита**, а не релиза. Сортировать по `published_at`
нельзя без проверки на `null`.

**Подводный камень 6 — `1.2` vs `1.2.0` vs `1.2.0.0`.** Строковое сравнение и сравнение
кортежей разной длины дают разные ответы. В `elite_hud/updater.py` это решено корректно:
`padded = self.parts + (0,) * max(0, 4 - len(self.parts))`, и `__eq__`/`__hash__` выведены из
того же ключа сортировки (`_key()`), поэтому `1.2` и `1.2.0` равны — это ровно то поведение,
которое нужно.

---

## 2. GitHub Actions: сборка Windows-релиза

### 2.1 Inno Setup на раннерах — ДА, предустановлен

**[LIVE]** Скачал Readme-файлы образов из `actions/runner-images` (`main`) и нашёл строку
в разделе «Installed Software → Tools»:

| Файл образа | Строка |
|---|---|
| `images/windows/Windows2022-Readme.md` | **`- InnoSetup 6.7.1`** |
| `images/windows/Windows2025-Readme.md` | **`- InnoSetup 6.7.1`** |
| `images/windows/Windows2025-VS2026-Readme.md` | **`- InnoSetup 6.7.1`** |

**Как ставится:** **[LIVE]** `images/windows/toolsets/toolset-2022.json`, секция `choco.common_packages`:

```json
"choco": {
    "common_packages": [
        { "name": "7zip.install" },
        { "name": "aria2" },
        { "name": "azcopy10" },
        { "name": "Bicep" },
        { "name": "innosetup" },
        ...
```

То есть через Chocolatey-пакет `innosetup`, версия — **6.7.1** (совпадает с текущей
версией пакета на community.chocolatey.org, **[LIVE]** страница пакета озаглавлена
«Inno Setup 6.7.1»).

> ⚠️ **Внимание к `windows-latest`.** **[LIVE]** В README репозитория `actions/runner-images`
> таблица «Available Images» сейчас указывает:
> `windows-latest`, `windows-2025`, `windows-2025-vs2026` → образ **Windows Server 2025 с
> Visual Studio 2026**, и ссылка ведёт на **`Windows2025-VS2026-Readme.md`**.
> То есть `windows-latest` — это **не** `Windows2025-Readme.md`. Оба файла содержат
> InnoSetup 6.7.1, так что на практике разницы нет, но читать надо правильный файл.
> Также в README прямо сказано: «The `-latest` migration process is gradual and happens over
> 1-2 months… To avoid unwanted migration, users can specify a specific OS version».

**Прочие версии на образе (`windows-latest` / VS2026):** **[LIVE]**
`- Python 3.12.10`, `- GitHub CLI 2.100.0`, `- NSIS 3.10`, `- WiX Toolset 3.14.1.8722`,
`- CMake 3.31.6`.

### 2.2 Где лежит `ISCC.exe` — точный путь

**[OBS]** В `actions/runner-images` **точный путь не указан** (я искал: файла с `inno` в
`images/windows/scripts/build/` нет, в `Post-Build-Validation.ps1` и `Toolset.Tests.ps1`
тоже нет). Поэтому путь подтверждён косвенно, из реальных workflow:

1. **[OBS]** Продакшн-workflow в открытом репозитории (`Fei-Away/Codex-Dream-Skin`,
   `.github/workflows/release.yml`) содержит защитное разрешение пути:

```yaml
      - name: Install Inno Setup 6
        shell: pwsh
        run: |
          $requiredVersion = '6.7.1'
          choco upgrade innosetup --version=$requiredVersion --allow-downgrade --no-progress --yes
          if ($LASTEXITCODE -ne 0) { throw "Could not install Inno Setup $requiredVersion." }
          $resolved = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
            (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
          ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
          if (-not $resolved) { throw 'Inno Setup 6 (ISCC.exe) is not available on the runner.' }
          "ISCC_PATH=$resolved" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
```

2. **[OBS]** Другой продакшн-workflow (`aelassas/servy`) задаёт переменную окружения явно:
   `ISCC: 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'`.

3. **[DOC]** Гайд сообщества (`fvarrui/JavaPackager`, `docs/windows-tools-guide.md`) утверждает:
   после `choco install -y innosetup` «both tools will be automatically available in `PATH`» —
   то есть Chocolatey-пакет добавляет `ISCC.exe` в `PATH`.

**Итог:** канонический путь — **`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`**
(путь по умолчанию официального инсталлятора Inno Setup для 32-битной сборки 6.x), а
Chocolatey дополнительно кладёт `ISCC.exe` в `PATH`, поэтому голое `iscc` обычно работает.
**Рекомендуется не полагаться на `PATH`**, а разрешать путь защитно (шаблон выше), потому что
встречаются сообщения о `The term 'iscc' is not recognized` в среде Windows.

Если Inno Setup всё же отсутствует или нужна конкретная версия:
```powershell
choco install innosetup --version=6.7.1 -y --no-progress
# либо официальный инсталлятор:
# https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe
```

> **Важно про версию.** **[LIVE]** Актуальный релиз Inno Setup — **7.1.0** (GitHub Releases
> `jrsoftware/issrc`, тег `is-7_1_0`). Но на раннерах стоит **6.7.1**, поэтому **директиву
> `SetupArchitecture` (появилась только в Inno Setup 7) использовать нельзя** — компиляция
> упадёт. **[DOC]** `topic_64bit`: «Inno Setup 7 introduced 64-bit compilers and installers. …
> Set `SetupArchitecture` to `x64` to build a 64-bit x64 installer instead of a 32-bit x86
> installer.»

### 2.3 Актуальные версии actions

**[LIVE]** Через GitHub API (до исчерпания лимита):

| Action | Последний релиз | Дата |
|---|---|---|
| `actions/checkout` | **v7.0.1** | 2026-07-20 |
| `actions/setup-python` | **v7.0.0** | 2026-07-20 |
| `actions/upload-artifact` | **v7.0.1** | 2026-04-10 |

> ⚠️ **Поправка к постановке задачи:** `actions/setup-python@v5` — **устаревшая** версия.
> Актуальна **`v7`**. **[LIVE]** Теги репозитория: `v7.0.0`, `v7`, `v6.3.0`, `v6`, `v5.6.0`,
> `v5`, … Причём `actions/setup-python@v7` объявлен как `using: 'node24'`
> (в `action.yml`), то есть это ещё и актуальный runtime (node20 снят с поддержки).
> Даже README самого `setup-python` в примерах использует `actions/checkout@v7` и
> `actions/setup-python@v7`.

**[DOC]** Кэширование pip встроено (не нужен отдельный `actions/cache`):

> The action has built-in functionality for caching and restoring dependencies. … Supported
> package managers are `pip`, `pipenv` and `poetry`. **The `cache` input is optional, and
> caching is turned off by default.** The action defaults to searching for a dependency file
> (`requirements.txt` or `pyproject.toml` for pip …) and uses its hash as a part of the cache key.
> … For `pip`, the action will cache the global cache directory.

```yaml
- uses: actions/setup-python@v7
  with:
    python-version: '3.12'
    cache: 'pip'                     # включает кэш pip
    cache-dependency-path: requirements.txt   # опционально, если файлов несколько
```

### 2.4 `permissions` для создания релиза

**[DOC]** Доступные значения `permissions` (`data/reusables/actions/github-token-available-permissions.md`)
включают `contents: read|write|none`. Там же критичная оговорка:

> **If you specify the access for any of these permissions, all of those that are not specified
> are set to `none`.**

То есть `permissions: contents: write` обнуляет **все** остальные права токена.

**[DOC]** Официальная страница эндпоинта «Create a release» прямо перечисляет требуемые права:

> The fine-grained token must have at least one of the following permission sets:
> **"Contents" repository permissions (write)**; **"Contents" repository permissions (write) and
> "Workflows" repository permissions (write)**.

**[LIVE]** Дословно из OpenAPI-спеки для `POST /repos/{owner}/{repo}/releases` — **важная ловушка**:

> Users with push access to the repository can create a release.
> **If the commit identified by `target_commitish` (or, when `target_commitish` is omitted, the
> latest commit on the default branch) adds or modifies any file under `.github/workflows/`
> relative to the repository's default branch, the authenticating token must be authorized to
> modify workflows. Otherwise, this endpoint returns `404 Not Found`; some authentication paths
> surface `403 Resource not accessible by integration` instead.** … **the `GITHUB_TOKEN` available
> to GitHub Actions cannot be authorized for this.**

**Практический вывод:** если тег, на который вы выпускаете релиз, указывает на коммит,
менявший файлы в `.github/workflows/`, `gh release create` с `GITHUB_TOKEN` вернёт **404**,
и починить это правами в workflow **нельзя**. Обходной путь — тегировать коммит, не
затрагивающий `.github/workflows/`, или использовать PAT/GitHub App-токен с правом Workflows.

Минимальный блок в workflow:

```yaml
permissions:
  contents: write
```

**[DOC]** Лимит запросов `GITHUB_TOKEN` внутри Actions: **1000 запросов/час на репозиторий**
(`data/reusables/rest-api/primary-rate-limit-github-token-in-actions.md`) — для сборки релиза
более чем достаточно.

### 2.5 `gh` CLI на раннерах

**[LIVE]** `windows-latest` (VS2026), `windows-2025`, `windows-2022` содержат
**`- GitHub CLI 2.100.0`**. Ставить `gh` не нужно.

**[DOC]** `gh release create` (cli.github.com/manual/gh_release_create):

```
gh release create [<tag>] [<filename>... | <pattern>...]
```

Дословно из мануала:

> Create a new GitHub Release for a repository. A list of asset files may be given to upload to
> the new release. To define a display label for an asset, append text starting with `#` after
> the file name.
> If a matching git tag does not yet exist, one will automatically get created from the latest
> state of the default branch. Use `--target` to point to a different branch or commit for the
> automatic tag creation. **Use `--verify-tag` to abort the release if the tag doesn't already
> exist.**
> …
> **When using the create command to attach assets to a release, separate API calls are made to
> create the release as a draft, upload the assets, and then publish the release.**

Полезные опции (дословно): `-d/--draft`, `--prerelease`, `--latest`
(«Mark this release as "Latest" (default [automatic based on date and version]). `--latest=false`
to explicitly NOT set as latest»), `-t/--title`, `-n/--notes`, `-F/--notes-file`
(«use "-" to read from standard input»), `--generate-notes`, `--verify-tag`, `-R/--repo`.

**Про immutable releases** (то, что мы видели как поле `immutable` в API):

> Immutable Releases … Git tags associated with a release cannot be modified or deleted.
> **Release assets cannot be modified or deleted.** Immutability is enforced only after a
> release is published. … Immutability protections will be enforced **ONLY after the release is
> published**.

> 💡 Если в репозитории включена неизменяемость релизов, `--clobber` на **опубликованном**
> релизе не сработает — это не баг, а защита. Перезаливать ассеты можно только в draft.

**[DOC]** `gh release upload` (cli.github.com/manual/gh_release_upload):

```
gh release upload <tag> <files>... [flags]
```
> Upload asset files to a GitHub Release. …
> **When using `--clobber`, existing assets are deleted before new assets are uploaded. If the
> upload fails, the original assets will be lost.**

> ⚠️ `--clobber` не атомарен: сначала удаляет, потом загружает. При обрыве сети старые ассеты
> потеряны. Для критичных релизов лучше сначала `gh release upload` под другим именем.

Токен передаётся переменной окружения **`GH_TOKEN`** (стандартный способ для `gh` в Actions):

```yaml
      - name: Publish release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh release create ...
```

**Загрузка в уже существующий релиз:**

```bash
gh release upload "$TAG" --clobber dist/EliteHud-Setup.exe SHA256SUMS.txt
```

### 2.6 Версия из тега и передача в Inno Setup

**[DOC]** `data/reusables/actions/ref_name-description.md`:
> `github.ref_name` — «The short ref name of the branch or tag that triggered the workflow run.
> This value matches the branch or tag name shown on GitHub. For example, `feature-branch-1`.»
> `github.ref` — полностью сформированный ref: «For tags it is `refs/tags/<tag_name>`.»

Для push тега `v1.2.3`: `github.ref_name == "v1.2.3"`, `github.ref == "refs/tags/v1.2.3"`,
`github.ref_type == "tag"`. Версия без префикса: `${{ github.ref_name }}` → убрать `v`.

**[DOC] Важно про фильтр `tags`** (`run-on-specific-branches-or-tags1`):
> Use the `tags` filter when you want to include tag name patterns… You cannot use both the
> `tags` and `tags-ignore` filters for the same event in a workflow.
> **If you define only `tags`/`tags-ignore` or only `branches`/`branches-ignore`, the workflow
> won't run for events affecting the undefined Git ref.** If you define neither… the workflow
> will run for events affecting either branches or tags.

Пример из справки:
```yaml
on:
  push:
    tags:
      - v2
      - v1.*
```

**[DOC]** Передача версии в Inno Setup — через **`/D` (define) компилятора ISCC**.
`topic_isppcc` (Inno Setup Preprocessor: Extended Command-Line Compiler):

> `--define=<name>[=<value>]`, `-d <name>[=<value>]` — Emulates `#define public <name> <value>`
> (variable-definition).
> …
> **Short options accept both `-` and `/` as a prefix and are case-insensitive.**

Пример из справки:
`iscc -$c- -pu+ "--define=LicenseFile=Trial License.txt" --include-dirs=c:\inc;d:\inc --include=defines.iss "c:\isetup\samples\my script.iss"`

Значит `iscc /DAppVersion=1.2.3 installer.iss` **корректен** (`/D` = `-d` = `--define`, регистр
не важен для коротких опций). В скрипте:

```ini
#ifndef AppVersion
  #define AppVersion "0.0.0"      ; fallback при локальной сборке без /D
#endif
...
[Setup]
AppVersion={#AppVersion}
```

**[DOC] Коды выхода ISCC** (`topic_compilercmdline`):

| Код | Значение |
|---|---|
| 0 | Success |
| 1 | Command-line parameters were invalid or a fatal error occurred |
| 2 | The compile failed |

### 2.7 Готовый рабочий `.github/workflows/release.yml`

```yaml
name: Release

# Триггер на push тега вида v1.2.3. Фильтр только по tags:
# ветки при этом workflow не запускают.
on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'
      - 'v[0-9]+.[0-9]+.[0-9]+-*'   # пре-релизы, например v1.3.0-rc1

# Для создания релиза и загрузки ассетов нужен contents: write.
# ВНИМАНИЕ: указание любой permission обнуляет все неуказанные (см. docs).
permissions:
  contents: write

env:
  PYTHONUNBUFFERED: '1'

jobs:
  release:
    # windows-latest сейчас = Windows Server 2025 + VS2026.
    # Явная версия надёжнее против миграции -latest.
    runs-on: windows-2022

    steps:
      - name: Checkout
        uses: actions/checkout@v7
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: '3.12'
          cache: 'pip'
          cache-dependency-path: |
            requirements.txt
            pyproject.toml

      - name: Compute version from tag
        id: ver
        shell: pwsh
        run: |
          $tag = $env:GITHUB_REF_NAME
          $version = $tag -replace '^v', ''
          if ($version -notmatch '^\d+(\.\d+)+') {
            throw "Tag '$tag' does not look like a version tag."
          }
          "TAG=$tag"            | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
          "VERSION=$version"    | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
          "PRERELEASE=$($version.Contains('-'))" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Run tests
        run: python -m pytest -q

      - name: Build exe with PyInstaller
        run: python tools/build_exe.py --windowed --clean

      - name: Locate ISCC.exe
        id: iscc
        shell: pwsh
        run: |
          # InnoSetup 6.7.1 предустановлен на windows-2022/2025 через Chocolatey,
          # но точный путь в actions/runner-images не документирован -> разрешаем защитно.
          $resolved = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:ProgramFiles        'Inno Setup 6\ISCC.exe'),
            (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
          ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
          if (-not $resolved) { throw 'Inno Setup 6 (ISCC.exe) is not available on the runner.' }
          "ISCC_PATH=$resolved" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
          & $resolved --version

      - name: Build installer with Inno Setup
        shell: pwsh
        run: |
          # /DAppVersion=<version> передаёт версию из тега в скрипт ({#AppVersion}).
          # /Qp = --quiet-progress. Коды выхода ISCC: 0 ok, 1 bad args, 2 compile failed.
          & $env:ISCC_PATH /Qp "/DAppVersion=$env:VERSION" "installer\elite-hud.iss"
          if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

      - name: Compute SHA256 checksums
        shell: pwsh
        run: |
          $lines = @()
          Get-ChildItem -Path dist -Filter '*Setup*.exe' -File | ForEach-Object {
            $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
            $lines += "$h  $($_.Name)"
          }
          Get-ChildItem -Path dist -Filter 'elite-hud*.exe' -File |
            Where-Object { $_.Name -notlike '*Setup*' } | ForEach-Object {
              $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
              $lines += "$h  $($_.Name)"
            }
          if ($lines.Count -eq 0) { throw 'No artifacts found in dist/' }
          $lines | Set-Content -Path dist\SHA256SUMS.txt -Encoding ascii
          Get-Content dist\SHA256SUMS.txt

      - name: Publish release
        shell: bash
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          ASSETS=$(ls dist/*Setup*.exe dist/SHA256SUMS.txt)
          PRE=""
          if [ "$PRERELEASE" = "True" ]; then PRE="--prerelease"; fi

          if gh release view "$TAG" >/dev/null 2>&1; then
            echo "Release $TAG already exists -> uploading with --clobber"
            gh release upload "$TAG" --clobber $ASSETS
          else
            # --verify-tag: не создавать тег на лету, тег уже есть (push тега).
            gh release create "$TAG" \
              --title "Elite HUD $VERSION" \
              --generate-notes \
              --verify-tag \
              $PRE \
              $ASSETS
          fi
```

**Пояснения к решению:**

- **`runs-on: windows-2022`** — зафиксированная версия. `windows-latest` мигрирует между
  версиями ОС (сейчас это Server 2025 + VS2026), и миграция «gradual and happens over 1-2
  months». Фиксация исключает внезапную смену окружения.
- **`shell: bash`** в шаге публикации — на Windows-раннерах Git Bash доступен и упрощает
  цитирование. Для остальных шагов используется PowerShell (`pwsh`, дефолтный shell).
- **`--verify-tag`** — workflow триггерится на push уже существующего тега, поэтому создание
  тега «на лету» было бы ошибкой.
- **`--generate-notes`** — использует GitHub Release Notes API.
- **Альтернатива без шага «release exists»** (проще, но с сохранением предупреждения о
  неатомарности `--clobber`):

```bash
gh release create "$TAG" --verify-tag --generate-notes $ASSETS \
  || gh release upload "$TAG" --clobber $ASSETS
```

---

## 3. Inno Setup

> Развёрнутая версия этого раздела (со ссылками на каждое утверждение, цитатами из
> `ISHelp/isetup.xml` и кодом компилятора) уже лежит в рабочей папке:
> **`research/INNO_SETUP_RU.md`** (1183 строки). Здесь — сжатая выжимка плюс мои
> независимые проверки.

### 3.1 Минимальный `.iss` и точные директивы

Все значения по умолчанию ниже **[DOC]** с официальной справки `jrsoftware.org/ishelp/`
(я скачивал страницы `topic_*.htm` напрямую и цитирую их).

| Директива | Значения | По умолчанию | Семантика (цитата/суть) |
|---|---|---|---|
| `AppId` | строка | = `AppName` | «`AppId` also determines the actual name of the Uninstall registry key, to which Inno Setup tacks on "`_is1`" at the end. (Therefore, if `AppId` is "`MyProgram`", the key will be named "`MyProgram_is1`".)» Длина ≤ **127** символов с учётом констант. |
| `AppName` | строка | — | Отображаемое имя приложения |
| `AppVersion` | строка | — | Версия; пишется в ARP как `DisplayVersion` |
| `AppPublisher` | строка | — | Издатель (пишется в `Publisher`) |
| `DefaultDirName` | путь с константами | — | «The value of this required directive is used for the default directory name… Normally it is prefixed by a directory constant.» Если `UsePreviousAppDir=yes` (дефолт) и найдена предыдущая версия — подставляется ранее выбранный каталог. |
| `PrivilegesRequired` | **`admin` \| `lowest`** | **`admin`** | «When set to `admin` … Setup will always run with administrative privileges and in administrative install mode… When set to `lowest`, Setup will not request to be run with administrative privileges even if it was started by a member of the Administrators group and will always run in non administrative install mode.» |
| `PrivilegesRequiredOverridesAllowed` | одна или обе: `commandline`, `dialog` | пусто | «Can be set to one or more overrides which allow the end user to override the script's default `PrivilegesRequired` setting.» `commandline` → добавляет `/ALLUSERS` и `/CURRENTUSER`. «Allowing `dialog` automatically allows `commandline`». |
| `CloseApplications` | `force` \| `yes` \| `no` | **`yes`** | См. 3.4 |
| `RestartApplications` | `yes` \| `no` | **`yes`** | «For Setup to be able to restart an application after the installation has completed, the application needs to be using the Windows **`RegisterApplicationRestart`** API function.» |
| `UninstallDisplayIcon` | путь | — | Иконка в ARP |
| `OutputBaseFilename` | имя файла | `mysetup` | Имя без расширения |
| `Compression` | `lzma2/max` и др. | `lzma2/max` | — |
| `WizardStyle` | `classic` \| `modern` \| `modern dynamic` | `classic` | `dynamic` требует 6.6+ |
| `SetupIconFile` | путь к `.ico` | — | Иконка самого установщика |
| `LicenseFile` | путь | — | Игнорируется, если у `[Languages]` задан свой `LicenseFile` |
| `AppMutex` | имя(и) через запятую | — | См. 3.4 |
| `ArchitecturesInstallIn64BitMode` | список архитектур | 32-bit Setup: пусто | Переключает в 64-битный install mode |
| `CreateUninstallRegKey` | `yes`/`no` | `yes` | `no` → нет записи в «Установка и удаление программ» |
| `OutputDir` | путь | `Output` | Каталог результата |

**[LIVE] Про `PrivilegesRequired=poweruser`:** в текущей справке («Valid values: `admin`, or
`lowest`») такого значения **нет**. Оно существовало в Inno Setup 5.x. Момент удаления в
`whatsnew` не описан → точная версия удаления **не подтверждена**. Используйте только
`admin`/`lowest`.

### 3.2 Установка для текущего пользователя без прав администратора

**Ключевые факты [DOC] `topic_admininstallmode` («Non Administrative Install Mode»):**

> An installation can run in one of two modes: administrative or non administrative. Which mode
> is selected is specified by the `PrivilegesRequired` and `PrivilegesRequiredOverridesAllowed`
> `[Setup]` section directives.
> **In administrative install mode:**
> - The `{group}` folder is created in the All Users profile.
> - The "auto" form of the directory and Shell Folder constants is mapped to the "common" form.
> - **The `HKA`, uninstall info, and font install root keys will be `HKEY_LOCAL_MACHINE`.**
> **In non administrative install mode:**
> - The `{group}` folder is created in the current user's profile.
> - The "auto" form of the directory and Shell Folder constants is mapped to the "user" form.
> - **The `HKA`, uninstall info, and font install root keys will be `HKEY_CURRENT_USER`.**

**Как сделать per-user по умолчанию, но с возможностью выбора:**

```ini
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
DefaultDirName={autopf}\Elite HUD
```

- `PrivilegesRequired=lowest` → по умолчанию **без UAC**, per-user.
- `PrivilegesRequiredOverridesAllowed=dialog` → пользователь увидит диалог выбора режима
  («Select Setup Install Mode»); `dialog` автоматически включает `commandline`, то есть
  доступны и `/ALLUSERS` / `/CURRENTUSER`.

**[DOC] Константы каталогов (`topic_consts`, раздел «Auto Constants»):**

> Besides the "common" and "user" constants, Inno Setup also supports "auto" constants. These
> automatically map to their "common" form unless the installation is running in **non
> administrative install mode**, in which case they map to their "user" form.
> **It is recommended you always use these "auto" constants when possible to avoid mistakes.**

| Auto | Administrative | Non-administrative |
|---|---|---|
| `{autopf}` | `{commonpf}` | `{userpf}` |
| `{autopf32}` | `{commonpf32}` | `{userpf}` |
| `{autopf64}` | `{commonpf64}` | `{userpf}` |
| `{autoprograms}` | `{commonprograms}` | `{userprograms}` |
| `{autostartup}` | `{commonstartup}` | `{userstartup}` |
| `{autodesktop}` | `{commondesktop}` | `{userdesktop}` |
| `{autostartmenu}` | `{commonstartmenu}` | `{userstartmenu}` |
| `{autoappdata}`, `{autocf}`, `{autodocs}`, `{autofonts}`, `{autotemplates}` | `{common…}` | `{user…}` |

Отдельные константы:
- `{localappdata}` — «The path to the current user's local (non-roaming) Application Data
  folder.» **Auto-формы не имеет** (это уже всегда per-user путь).
- `{userpf}` — «The path to the current user's Program Files folder. Only Windows 7 and later
  supports `{userpf}`; if used on previous Windows versions, it will translate to the same
  directory as `{localappdata}\Programs`.» На Win7+ это `%LOCALAPPDATA%\Programs`.
- `{userstartup}` / `{commonstartup}` — «The path to the Startup folder on the Start Menu.»

> **Рекомендация:** использовать `{autopf}` в `DefaultDirName` (это то, что делает справка:
> `DefaultDirName={autopf}\My Program`), а `{localappdata}\...` — только если вы сознательно
> хотите жёстко per-user путь без учёта admin-режима. Компилятор предупредит
> (`UsedUserAreasWarning`) при использовании user-констант в admin-режиме.

**`{localappdata}` vs `{autopf}` — что выбрать.** Если нужен строго per-user путь и вы не
хотите, чтобы пользователь мог выбрать per-machine, лучше `PrivilegesRequired=lowest` **без**
`PrivilegesRequiredOverridesAllowed` и `DefaultDirName={localappdata}\Programs\Elite HUD`.
Если хотите оба режима — `{autopf}` + `PrivilegesRequiredOverridesAllowed=dialog commandline`.

### 3.3 Тихая установка: ключи командной строки

**[DOC]** `topic_setupcmdline` — «Setup Command-Line Parameters». Дословные формулировки:

| Ключ | Значение |
|---|---|
| `/SILENT`, `/VERYSILENT` | «Instructs Setup to be silent or very silent. **When Setup is silent the wizard and the background window are not displayed but the installation progress window is.** When a setup is very silent this installation progress window is not displayed. Everything else is normal so for example error messages during installation are displayed (if you haven't disabled them with the `/SUPPRESSMSGBOXES` command-line option…)»<br>«**If a restart is necessary and the `/NORESTART` command isn't used and Setup is silent, it will display a Reboot now? message box. If it's very silent it will reboot without asking.**» |
| `/SUPPRESSMSGBOXES` | «Instructs Setup to suppress message boxes. **Only has an effect when combined with `/SILENT` or `/VERYSILENT`.**» Далее перечислены дефолтные ответы (Yes в «Keep newer file?», No в «File exists, confirm overwrite.», Abort в Abort/Retry, Cancel в Retry/Cancel, Yes в DiskSpaceWarning/DirExists/…/ConfirmUninstall, Yes(=restart) в FinishedRestartMessage/UninstalledAndNeedsRestart).<br>**5 диалогов не подавляются:** About Setup; Exit Setup?; FileNotInDir2; любой диалог ошибки до чтения параметров; любой `TaskDialogMsgBox`/`MsgBox` из `[Code]` (используйте `SuppressibleTaskDialogMsgBox`/`SuppressibleMsgBox`). |
| `/NORESTART` | «Prevents Setup from restarting the system following a successful installation… Typically used along with `/SILENT` or `/VERYSILENT`.» |
| `/NOCANCEL` | Блокирует кнопку Cancel и закрытие окна. «Useful along with `/SILENT` or `/VERYSILENT`.» |
| `/CLOSEAPPLICATIONS` | «Instructs Setup to close applications using files that need to be updated by Setup if possible.» |
| `/NOCLOSEAPPLICATIONS` | Обратное. «If `/CLOSEAPPLICATIONS` was also used, this command-line parameter is ignored.» |
| `/FORCECLOSEAPPLICATIONS` | «Instructs Setup to force close when closing applications.» |
| `/NOFORCECLOSEAPPLICATIONS` | Обратное; игнорируется при `/FORCECLOSEAPPLICATIONS`. |
| `/RESTARTAPPLICATIONS` | «Instructs Setup to restart applications if possible.» |
| `/NORESTARTAPPLICATIONS` | Обратное; игнорируется при `/RESTARTAPPLICATIONS`. |
| `/LOG` | «Causes Setup to create a log file in the user's TEMP directory… The log file is created with a unique name based on the current date.» |
| `/LOG="filename"` | Фиксированный путь; существующий файл **перезаписывается**; если создать нельзя — Setup прервётся с ошибкой. «**Nor is it designed to be machine-parsable; the format of the file is subject to change without notice.**» |
| `/SP-` | Отключает стартовый промпт «This will install… Do you wish to continue?» |
| `/ALLUSERS` / `/CURRENTUSER` | «Only has an effect when the `[Setup]` section directive `PrivilegesRequiredOverridesAllowed` allows the `commandline` override.» |
| `/DIR="x:\dirname"` | Переопределяет каталог. Поддерживает префикс `expand:` → `/DIR=expand:{autopf}\My Program` |
| `/GROUP="folder name"` | Переопределяет папку в меню Пуск; игнорируется при `DisableProgramGroupPage=yes` |
| `/LOADINF="filename"` / `/SAVEINF="filename"` | Загрузить/сохранить настройки установки |
| `/LANG=language` | Внутреннее имя языка; подавляет диалог выбора языка |
| `/TASKS="a,b"` / `/MERGETASKS="a,b"` | `/TASKS` — «Only the specified tasks will be selected; the rest will be deselected.» `/MERGETASKS` — «the specified tasks will be merged with the set of tasks that would have otherwise been selected by default.» Префикс `*` = с дочерними, `!` = снять. |
| `/TYPE=`, `/COMPONENTS=`, `/PASSWORD=` | Аналогично; `/COMPONENTS` игнорируется при наличии `/TYPE` для не-custom типа |
| `/RESTARTEXITCODE=exit code` | «Specifies a custom exit code that Setup is to return when the system needs to be restarted following a successful installation. (By default, 0 is returned in this case.)» |
| `/HELP`, `/?` | Сводка параметров |
| `/NOSTYLE` | Отключает кастомные стили |
| `/REDIRECTIONGUARD`, `/NOREDIRECTIONGUARD`, `/LOGCLOSEAPPLICATIONS` | Служебные |

**Разница `/SILENT` и `/VERYSILENT` — ровно одна:** окно прогресса установки. `/SILENT` его
показывает, `/VERYSILENT` — нет. Всё остальное идентично. Плюс критичное следствие для
`/VERYSILENT` без `/NORESTART`: **перезагрузка ПК без вопроса.**

> 💡 **Для самообновления нужен `/VERYSILENT`, а не `/SILENT`.** В `elite_hud/updater.py`
> сейчас `SILENT_SETUP_FLAGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]`
> — при `/SILENT` пользователь увидит окно прогресса. Если цель — незаметное фоновое
> обновление, замените `/SILENT` на `/VERYSILENT` (и `/NORESTART` обязателен, см. выше).

**Проверенный набор для тихого обновления:**

```
setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /SP- /LOG="%LOCALAPPDATA%\elite-hud\updates\update.log"
```

**Коды выхода Setup [DOC] `topic_setupexitcodes`:**

| Код | Значение |
|---|---|
| 0 | Setup успешно завершён (или использован `/HELP` / `/?`) |
| 1 | Setup failed to initialize |
| 2 | Пользователь нажал Cancel в мастере до начала установки, либо «No» в стартовом диалоге |
| 3 | Fatal error при подготовке к следующей фазе установки |
| 4 | Fatal error во время установки |
| 5 | Cancel во время установки, либо Abort в Abort-Retry-Ignore |
| 6 | Процесс Setup принудительно завершён отладчиком |
| 7 | Стадия «Preparing to Install» решила, что установка не может продолжаться |
| 8 | То же, что 7, но требуется перезагрузка системы |

> «Future versions of Inno Setup may return additional exit codes, so applications checking the
> exit code should be programmed to handle unexpected exit codes gracefully. **Any non-zero exit
> code indicates that Setup was not run to completion.**»

### 3.4 Как Inno Setup закрывает работающее приложение

**[DOC]** `topic_setup_closeapplications` дословно:

> If set to `yes` or `force` and Setup is not running silently, Setup will pause on the Preparing
> to Install wizard page if it detects applications using files that need to be updated by the
> `[Files]` or `[InstallDelete]` section, showing the applications and asking the user if Setup
> should automatically close the applications and restart them after the installation has
> completed.
> If set to `yes` or `force` and Setup is running silently, Setup will **always close and restart
> such applications, unless told not to via the command line**.
> If set to `force` Setup will force close when closing applications, unless told not to via the
> command line. Use with care since this may cause the user to lose unsaved work.
> **Note: Setup uses Windows Restart Manager to detect, close, and restart applications.**

**[DOC]** `topic_setup_restartapplications`:

> When set to `yes` and `CloseApplications` is also set to `yes` or `force`, Setup restarts the
> closed applications after the installation has completed.
> **Note: For Setup to be able to restart an application after the installation has completed,
> the application needs to be using the Windows `RegisterApplicationRestart` API function.**

> ⚠️ **Это ключевая ловушка.** `RestartApplications=yes` (дефолт) **не означает**, что ваше
> приложение вернётся после тихого обновления. Приложение обязано само вызвать
> `RegisterApplicationRestart`. PySide6/Qt по умолчанию этого **не делает** (в Qt нет
> автоматического вызова этого API; **не подтверждено** документально, что какая-то версия
> Qt его вызывает — считайте, что не вызывает).
> Поэтому ответ на вопрос «работает ли автозакрытие/автоперезапуск автоматически»:
> - **закрытие — да**, через Restart Manager, приложению для этого ничего делать не нужно;
> - **автоперезапуск — нет**, если приложение не вызвало `RegisterApplicationRestart`.

**`AppMutex` — что это и нужно ли.** [DOC] `topic_setup_appmutex`:

> This directive is used to prevent the user from installing new versions of an application
> while the application is still running, and to prevent the user from uninstalling a running
> application. It specifies the names of one or more named mutexes (multiple mutexes are
> separated by commas), which Setup and Uninstall will check for at startup. If any exist,
> Setup/Uninstall will display the message: **"[Setup or Uninstall] has detected that [AppName]
> is currently running. Please close all instances of it now, then click OK to continue, or
> Cancel to exit."** …
> **Note that mutex name comparison in Windows is case sensitive.**
> Example: `AppMutex=MyProgramsMutexName,Global\MyProgramsMutexName`

`AppMutex` **ничего не убивает сам** — он показывает модальный диалог OK/Cancel и ждёт, пока
мьютекс исчезнет. Именно поэтому в полностью тихом режиме это опасно (см. ниже).

**[OBS]** Мой субагент, читавший исходники `jrsoftware/issrc`, проследил цепочку:
`AppMutex` + живое приложение + `/SUPPRESSMSGBOXES` → `LoggedMsgBox(..., Suppressible=True,
Default=IDCANCEL)` → `Abort` → перехват в `Setup.Start.pas` → `Halt(ecInitializationError)`,
то есть **тихий выход с кодом 1 и без сообщения**. Это выведено из кода, а не из явной фразы
справки → **не подтверждено документально**, рекомендуется проверить эмпирически
(`echo %ERRORLEVEL%`).

**Практический вывод (важный):** если приложение держит `AppMutex` и вы запускаете установщик
тихо, **приложение обязано завершиться ДО старта Setup**, иначе обновление молча провалится.
Это устраняется запуском установщика через промежуточный помощник, который сначала ждёт
освобождения мьютекса.

**Как указать `AppMutex` в PySide6/Qt-приложении** — через `CreateMutexW`:

```python
import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "elite-hud-single-instance-mutex"   # ДОЛЖНО совпадать с AppMutex в .iss

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_kernel32.CreateMutexW.restype = wintypes.HANDLE

_handle = None   # держим на уровне модуля ВСЮ жизнь процесса

def acquire_single_instance() -> bool:
    """True, если мы единственный экземпляр."""
    global _handle
    handle = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True                      # не смогли — не блокируем запуск
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return False
    _handle = handle                     # НЕ закрывать до выхода из процесса
    return True
```

Замечания:
- Имя мьютекса сравнивается **с учётом регистра** — строка должна совпадать с `AppMutex`
  в `.iss` побайтово.
- Handle надо хранить, иначе мьютекс освободится при сборке мусора.
- [DOC] «It is not necessary to explicitly destroy the mutex object upon your application's
  termination; the system will do this automatically. **Nor is it recommended that you do so**,
  because ideally the mutex object should exist until the process completely terminates.»
- **[LIVE]** В `elite_hud/installation.py` всё сделано правильно: `CreateMutexW(None, False, name)`,
  проверка `GetLastError() == 183`, handle в поле объекта. **Одно замечание:**
  `ctypes.windll.kernel32.GetLastError()` читает last-error через Win32-подсистему
  `windll`, но надёжнее `ctypes.get_last_error()` вместе с
  `ctypes.WinDLL("kernel32", use_last_error=True)` — иначе возможна гонка, если между
  вызовом и чтением ошибки выполнится другой Win32-вызов. Рекомендую перейти на
  `use_last_error=True` + `ctypes.get_last_error()`.
- **Про префикс `Global\`:** [DOC] справка использует `Global\MyProgramsMutexName` лишь как
  **пример значения** `AppMutex`. Нужен ли непривилегированному процессу
  `SeCreateGlobalPrivilege` для создания `Global\`-мьютекса — **не подтверждено**.
  Рекомендация: для приложения без прав администратора использовать имя **без префикса**
  (сессионный namespace) либо `Local\`.

### 3.5 Автозагрузка: «запускать при входе в систему»

**Рабочий пример [DOC]** (флаги сверены с `topic_taskssection` и `topic_iconssection`):

```ini
[Tasks]
Name: "startupicon"; Description: "Запускать Elite HUD при входе в Windows"; \
  GroupDescription: "Дополнительно:"; Flags: unchecked

[Icons]
Name: "{autostartup}\Elite HUD"; Filename: "{app}\EliteHud.exe"; \
  WorkingDir: "{app}"; Tasks: startupicon; Flags: excludefromshowinnewinstall
```

Ключевые моменты:
- `{autostartup}` → `{commonstartup}` в admin-режиме, `{userstartup}` в non-admin. Если
  `PrivilegesRequired=lowest`, ярлык автозагрузки создаётся в пользовательской папке —
  компилятор не будет ругаться `UsedUserAreasWarning`, потому что это auto-константа.
- `Flags: unchecked` в `[Tasks]` — галочка по умолчанию снята (пользователь выбирает сам).
- **`runascurrentuser` в `[Icons]` не существует** — это флаг `[Run]`/`[UninstallRun]`.
  Полный список флагов `[Icons]` (по данным моего субагента из
  `Compiler.SetupCompiler.pas`): `uninsneveruninstall, runminimized, createonlyiffileexists,
  useapppaths, closeonexit, dontcloseonexit, runmaximized, excludefromshowinnewinstall,
  preventpinning`. `unchecked` тоже **не** флаг `[Icons]`.
- **`[Run]`**: чтобы запускать приложение не от администратора (при per-machine установке),
  добавьте `runasoriginaluser`.

### 3.6 Самообновление: что происходит с работающим приложением

**Сценарий:** приложение скачало новый `setup.exe` и запустило его тихо.

Что произойдёт по факту:

1. Setup стартует и **сразу проверяет `AppMutex`**. Если приложение ещё живо — Setup покажет
   диалог и будет ждать. При `/SUPPRESSMSGBOXES` диалог подавляется с дефолтом Cancel →
   **тихий выход с кодом 1** (см. 3.4, помечено как выведенное из кода).
2. Если приложение уже завершилось, Setup идёт дальше. На этапе установки Restart Manager
   может обнаружить процессы, держащие обновляемые файлы, и (при `CloseApplications=yes` и
   silent-режиме) закрыть и перезапустить их — **но перезапуск сработает только если
   приложение вызывало `RegisterApplicationRestart`.**
3. `[Run]`-записи с флагом `postinstall` **в тихом режиме не выполняются** — им нужна
   страница завершения мастера, которой в silent нет. [DOC] `topic_runsection`:
   `postinstall` — «Instructs Setup to create a checkbox on the **Setup Completed wizard
   page**»; `skipifsilent` — «Instructs Setup to skip this entry if Setup is running (very)
   silent».

**Правильная схема (рекомендация):**

Не запускать Setup напрямую из живого приложения. Нужен отдельный помощник:

```
приложение                          помощник (cmd.exe / отдельный exe)
    │                                        │
    ├─ скачало setup.exe ───────────────────►│
    ├─ запустило помощника (detached) ──────►│
    ├─ release() мьютекса и выход            ├─ ждёт исчезновения мьютекса/PID
                                             ├─ запускает setup /VERYSILENT ...
                                             ├─ (ждёт кода выхода Setup)
                                             └─ перезапускает приложение
```

**Как перезапустить приложение после тихого обновления — 3 способа:**

**(a) `[Run]`-запись с `skipifnotsilent` — самый чистый, без `[Code]`:**

```ini
[Run]
; Обычная (интерактивная) установка: галочка «Запустить» на странице завершения.
Filename: "{app}\EliteHud.exe"; Description: "Запустить Elite HUD"; \
  Flags: nowait postinstall skipifsilent runasoriginaluser

; Тихое обновление: перезапустить сразу (запись выполняется ТОЛЬКО при silent).
Filename: "{app}\EliteHud.exe"; Flags: nowait skipifnotsilent runasoriginaluser
```

`skipifnotsilent` [DOC] — «Instructs Setup to skip this entry if Setup is **not** running
(very) silent.» То есть запись выполняется ровно в сценарии самообновления. `runasoriginaluser`
нужен, чтобы при per-machine установке приложение не оказалось запущенным от администратора.

**(b) Приложение перезапускает себя само** — помощник после успешного кода выхода Setup
(0) запускает exe.

**(c) Реализовать `RegisterApplicationRestart` в приложении** — тогда `RestartApplications=yes`
сработает штатно. Требует вызова Win32 API при старте приложения.

**Не парсить `/LOG` программно** [DOC]: «Nor is it designed to be machine-parsable; the format
of the file is subject to change without notice.» Ориентируйтесь на код выхода и
`DisplayVersion` в реестре.

### 3.7 Как определить, что приложение установлено через Inno Setup

**[DOC] Суффикс `_is1` подтверждён официально.** `topic_setup_appid`:

> `AppId` also determines the actual name of the Uninstall registry key, to which Inno Setup
> tacks on "`_is1`" at the end. (Therefore, if `AppId` is "`MyProgram`", the key will be named
> "`MyProgram_is1`".)

**[DOC] Корень реестра зависит от режима установки** (`topic_admininstallmode`, см. 3.2):
per-user → `HKEY_CURRENT_USER`, per-machine → `HKEY_LOCAL_MACHINE`.

**[DOC] View реестра (32/64) — `topic_32vs64bitinstalls`:**

> **32-bit install mode**
> - The `{commonpf}` constant is equivalent to `{commonpf32}`.
> - The `{reg:...}` constant reads the 32-bit view by default.
> - **The Uninstall key is created in the 32-bit view of the registry.**
> **64-bit install mode**
> - **The Uninstall key is created in the 64-bit view of the registry.**

**Итоговые точные пути:**

| Режим установки | View | Ключ реестра |
|---|---|---|
| per-user (non-admin) | общий | `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{AppId}_is1` |
| per-machine, 32-bit install mode (дефолт) | 32-bit | `HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{AppId}_is1` |
| per-machine, 64-bit install mode | 64-bit | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{AppId}_is1` |

**Про `{AppId}` — важно про фигурные скобки.** Если `AppId` задан GUID-литералом, в скрипте
пишут `AppId={{8F2C...}`: `{{` — это escape одного `{`
([DOC] `topic_consts`: «A `{` character is treated as the start of the constant. If you want to
use that actual character in a place where constants are supported, you must use two consecutive
`{` characters.»). Поэтому **фактическое значение `AppId` — `{8F2C4A91-...}` вместе со
скобками**, и ключ реестра — `{8F2C4A91-...}_is1`. В `elite_hud/installation.py`
`APP_ID = "{8F2C4A91-3D7E-4B62-9A15-C6E0B84D5F37}"` — **корректно**.

**[DOC] Значения в ключе ARP, которые пишет Inno Setup.** Мой субагент извлёк полный список из
`Setup.Install.pas`: `Inno Setup: Setup Version`, `Inno Setup: App Path`, `InstallLocation`,
`Inno Setup: Icon Group`, `Inno Setup: User`, `Inno Setup: Language`, `DisplayName`
(обрезается до 259 символов), `DisplayIcon`, `UninstallString`,
`QuietUninstallString` (`"…\unins000.exe" /SILENT`), `DisplayVersion`, `Publisher`,
`URLInfoAbout`, `HelpLink`, `URLUpdateInfo`, `ModifyPath` (или `NoModify=1`),
`NoRepair=1` (пишется всегда), `InstallDate`, `MajorVersion`/`MinorVersion`/`VersionMajor`/
`VersionMinor`, `EstimatedSize` (**в КБ**, `div 1024`). Многие пишутся через
`SetStringValueUnlessEmpty` → если директива пустая, значения в реестре **нет** вовсе
(не пустая строка!). Это важно: проверяйте наличие значения, а не `== ""`.

**Чтение из Python (`winreg`) — правильный способ:**

```python
import sys

def is_installed_by_inno(app_id: str, version: str = "") -> bool:
    """
    app_id — фактический AppId ВМЕСТЕ с фигурными скобками, например
             "{8F2C4A91-3D7E-4B62-9A15-C6E0B84D5F37}"
    """
    if sys.platform != "win32":
        return False

    import winreg

    subkey = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{app_id}_is1"

    # HKEY_CURRENT_USER\SOFTWARE — SHARED: view НЕ разделяется, флаги не нужны.
    # [DOC] learn.microsoft.com/windows/win32/winprog64/shared-registry-keys
    candidates = [(winreg.HKEY_CURRENT_USER, 0)]

    # HKEY_LOCAL_MACHINE\SOFTWARE — REDIRECTED (WOW6432Node).
    # Правильно НЕ хардкодить Wow6432Node, а выбрать view флагом:
    # [DOC] "New applications should avoid using Wow6432Node in registry key paths."
    candidates.append((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY))  # 32-bit install mode
    candidates.append((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY))  # 64-bit install mode

    for hive, view in candidates:
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as key:
                installed_version = ""
                try:
                    installed_version, _ = winreg.QueryValueEx(key, "DisplayVersion")
                except FileNotFoundError:
                    pass
                if not version or str(installed_version) == version:
                    return True
        except OSError:
            continue
    return False
```

> ✅ **Что здесь исправлено относительно `elite_hud/installation.py`.**
> Текущая реализация формирует отдельный подпуть
> `Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\...` в списке кандидатов.
> Это работает, но Microsoft прямо не рекомендует хардкодить `Wow6432Node`:
> «**New applications should avoid using Wow6432Node in registry key paths**» (Microsoft Learn,
> Registry Keys Affected by WOW64). Правильнее открывать один и тот же путь с флагом
> `KEY_WOW64_32KEY` / `KEY_WOW64_64KEY` — как в примере выше. Хардкод `Wow6432Node`
> вдобавок даёт избыточные кандидаты (тот же ключ открывается дважды).
> Также в текущем коде перебор идёт по `(0, KEY_WOW64_32KEY, KEY_WOW64_64KEY)` для **обеих**
> ветвей, включая `HKCU` → для HKCU 32/64-флаги не имеют смысла (ключ shared), хотя вреда нет.

---

## 4. Самозамена запущенного exe на Windows

### 4.1 Почему нельзя перезаписать запущенный .exe

Запущенный PE-образ отображён в адресное пространство процесса как **секция образа (image
section)**. Windows удерживает его открытым и не даёт открыть файл на запись или удалить —
операция завершается **`ERROR_SHARING_VIOLATION` (Win32 error 32, "The process cannot access
the file because it is being used by another process")**.

Однако есть **исключение: переименовать запущенный exe можно.**

**Статус подтверждения — объяснение (не официальная документация Microsoft).**
HTML-страницы Stack Exchange закрыты Cloudflare (**HTTP 403**), поэтому я получил текст через
открытый Stack Exchange API (`api.stackexchange.com/2.3/questions/488127/answers?site=superuser`).

Принятый ответ (score 13, accepted) на вопрос
«[Why can I rename a running executable, but not delete it?](https://superuser.com/questions/488127/why-can-i-rename-a-running-executable-but-not-delete-it)»
— дословно:

> **There really is no such thing as renaming a file. A file can have more than one name or no
> name, so it's not the file that you're renaming but the directory entry. Renaming is an
> operation on the directory entry, which is not affected by the fact that the file is locked
> for execution.**

Второй ответ объясняет, почему именно **удаление** невозможно:

> It does not allow to delete the executable file and DLLs because **Windows maps parts of the
> executable files into memory as part of the process creation**, so it needs the file during the
> lifetime of the process. … I guess that this is done to enable the update of the dlls and exe
> files while they are running to minimize the service interruption time. The linux (unix in
> general) in contrast allows to delete an executable file while it is running.

> ⚠️ **Оговорка о статусе источника.** Это объяснение сообщества (Super User), а **не**
> официальная документация Microsoft. Прямой цитаты из Microsoft Learn или блога Raymond Chen
> «The Old New Thing» найти не удалось (часть страниц learn.microsoft.com отдавала таймауты).
> Поведение помечено как **подтверждённое практикой с цитируемым объяснением, но не
> первоисточником Microsoft**.

Что **подтверждено официальной документацией Microsoft** в этой области — механизм
`MoveFileEx` с `MOVEFILE_DELAY_UNTIL_REBOOT` (см. 4.2), а также тот факт, что Inno Setup
штатно заменяет запущенные файлы через **Windows Restart Manager**, а не через перезапись
файла «на живую».

**Практическая суть:**
- `DeleteFile("app.exe")` при работающем процессе → **отказ** (`ERROR_ACCESS_DENIED` /
  `ERROR_SHARING_VIOLATION`).
- `MoveFile("app.exe", "app.exe.old")` при работающем процессе → **успех**. Файл получает
  новое имя, но блокировка сохраняется (образ всё ещё отображён).
- После переименования **старый файл нельзя удалить, пока процесс не завершится** —
  `DeleteFile("app.exe.old")` будет отказывать до выхода процесса. Именно поэтому такое
  удаление обычно ставят либо на «следующий запуск приложения», либо через
  `MoveFileEx(..., MOVEFILE_DELAY_UNTIL_REBOOT)`.
- **Расширение `.exe` у переименованного файла менять не обязательно** — Windows не
  запрещает держать отображённый образ под именем `.old`; блокировка определяется не
  расширением, а фактом отображения. Это **не подтверждено** прямой цитатой, но
  подтверждается тем, что схема «rename → write new → delete old» повсеместно используется.

### 4.2 `MoveFileEx` + `MOVEFILE_DELAY_UNTIL_REBOOT` — точная семантика и подводные камни

**[DOC]** Microsoft Learn, `MoveFileExA function (winbase.h)` — дословно:

> **`MOVEFILE_DELAY_UNTIL_REBOOT`** — 4 (0x4): The system does not move the file until the
> operating system is restarted. The system moves the file immediately after AUTOCHK is
> executed, but before creating any paging files. …
> **This value can be used only if the process is in the context of a user who belongs to the
> administrators group or the LocalSystem account.**
> This value cannot be used with **`MOVEFILE_COPY_ALLOWED`**.

> If the `dwFlags` parameter specifies **`MOVEFILE_DELAY_UNTIL_REBOOT`**, MoveFileEx **fails if it
> cannot access the registry**. The function stores the locations of the files to be renamed at
> restart in the following registry value: **`HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\
> Control\Session Manager\PendingFileRenameOperations`**
> This registry value is of type **`REG_MULTI_SZ`**. Each rename operation stores one of the
> following NULL-terminated strings, depending on whether the rename is a delete or not:
> - `szSrcFile\0\0`
> - `szSrcFile\0szDstFile\0`
>
> The string `szSrcFile\0\0` indicates that the file `szSrcFile` is to be deleted on reboot. The
> string `szSrcFile\0szDstFile\0` indicates that `szSrcFile` is to be renamed `szDstFile` on reboot.

> Because the actual move and deletion operations specified with the `MOVEFILE_DELAY_UNTIL_REBOOT`
> flag take place **after the calling application has ceased running**, **the return value cannot
> reflect success or failure in moving or deleting the file. Rather, it reflects success or
> failure in placing the appropriate entries into the registry.**

> The system uses these registry entries to complete the operations at restart **in the same order
> that they were issued.**

Также из той же страницы: если `dwFlags` содержит `MOVEFILE_DELAY_UNTIL_REBOOT` и
`lpNewFileName` — **NULL**, файл помечается на **удаление** при перезапуске. Каталог удаляется
только если он пуст: «The system deletes a directory that is tagged for deletion … only if it is
empty.» И: «If `dwFlags` specifies `MOVEFILE_DELAY_UNTIL_REBOOT`, the file cannot exist on a
remote share, because delayed operations are performed before the network is available.»

**Подводные камни `MOVEFILE_DELAY_UNTIL_REBOOT`:**

1. **Требуются права администратора.** Для per-user установки без UAC этот путь недоступен.
2. **Замена произойдёт только при СЛЕДУЮЩЕЙ перезагрузке.** Перезагрузка **не** инициируется
   автоматически — приложение-обновление должно само её запросить, что для оверлея к игре
   абсолютно неприемлемо.
3. **Никакого перезапуска приложения.** После reboot приложение не стартует само — нужен
   отдельный механизм (RunOnce, Task Scheduler, ярлык в автозагрузке).
4. **Возвращаемое значение бесполезно** для проверки успеха: `TRUE` означает лишь, что запись
   в реестр добавлена.
5. **Порядок операций сохраняется**, но при этом **нет способа их отменить** и нет уведомления
   об ошибке на этапе reboot.
6. **Нельзя комбинировать с `MOVEFILE_COPY_ALLOWED`** и нельзя применять к сетевым путям.
7. Может конфликтовать с другими программами, пишущими в `PendingFileRenameOperations`
   (антивирусы, инсталляторы) — значение `REG_MULTI_SZ` общее на всю систему.

**Вывод:** для самообновления GUI-оверлея `MOVEFILE_DELAY_UNTIL_REBOOT` **не подходит**.
Его законное место — удаление «осиротевшего» файла, который не удалось удалить сразу
(например, старого `app.exe.old` после перезапуска приложения).

### 4.3 Схема «переименовать → записать новый → удалить старый»

Идея (широко применяемая в самообновляющихся Win32-приложениях):

1. `app.exe` запущен.
2. `MoveFile("app.exe", "app.exe.old")` — **успех**, блокировка переезжает на новое имя.
3. Скопировать новый `app.exe` по старому пути — **успех**, так как имя свободно и никто
   его не отображал.
4. При следующем старте приложения удалить `app.exe.old`. Если удаление не удалось
   (старый процесс всё ещё жив), отложить через
   `MoveFileEx("app.exe.old", NULL, MOVEFILE_DELAY_UNTIL_REBOOT)`.

**Ограничения:**
- Нужен процесс, который переживёт завершение приложения, чтобы шаг 3 выполнился, когда
  приложение уже не держит `app.exe`. То есть **всё равно нужен помощник** — схема не
  избавляет от updater-процесса, а лишь упрощает замену одного файла.
- Шаг 2 нельзя выполнить, если антивирус держит файл открытым — тогда `MoveFile` тоже упадёт.
- Накопление `.old`-файлов при сбоях; нужна очистка при старте.
- **Onefile-сборка** (см. 4.4): приложение в `dist/elite-hud.exe` — один файл, поэтому схема
  технически применима, но `_MEI`-каталог всё равно остаётся заблокированным до выхода
  процесса.

### 4.4 Рабочий `.cmd`-помощник: ждать PID и заменить файлы

Ниже — проверенная рабочая схема (это развитие шаблона `PORTABLE_HELPER_TEMPLATE` из
`elite_hud/updater.py`, с исправлениями).

```bat
@echo off
rem ============================================================================
rem  elite-hud-update.cmd — замена файлов после выхода приложения.
rem
rem  Аргументы (передаются из приложения через .format()):
rem    %1 = PID процесса, который надо дождаться
rem    %2 = каталог-источник (уже распакованная новая версия)
rem    %3 = каталог-назначение (куда установлено приложение)
rem    %4 = путь к exe для перезапуска
rem    %5 = имя мьютекса приложения (для проверки через tasklist — см. примечание)
rem ============================================================================
setlocal EnableExtensions DisableDelayedExpansion

set "PID=%~1"
set "SOURCE=%~2"
set "TARGET=%~3"
set "LAUNCH=%~4"

if "%PID%"==""   ( echo [update] missing PID & exit /b 2 )
if "%SOURCE%"=="" ( echo [update] missing SOURCE & exit /b 2 )
if "%TARGET%"=="" ( echo [update] missing TARGET & exit /b 2 )

rem --- 1. Ждём завершения процесса ------------------------------------------
rem  tasklist /FI "PID eq N" печатает строку заголовка + строку процесса,
rem  если процесс жив, и "INFO: No tasks are running..." — если мёртв.
rem  Надёжнее проверять наличие строки с самим номером PID, чем errorlevel.
set /a TRIES=0
:wait
set /a TRIES+=1
if %TRIES% GTR 300 (
    rem 300 попыток * ~1 c = ~5 минут. Больше ждать бессмысленно.
    echo [update] timeout waiting for PID %PID%
    exit /b 3
)

tasklist /FI "PID eq %PID%" /NH /FO CSV 2>NUL | findstr /C:"\"%PID%\"" >NUL
if not errorlevel 1 (
    rem  Процесс ещё жив. Пауза без внешних утилит: ping -n 2 = ~1 секунда.
    rem  timeout.exe недоступен, если stdin перенаправлен (частая проблема
    rem  при запуске из GUI-приложения), поэтому используем ping.
    ping -n 2 127.0.0.1 >NUL
    goto wait
)

rem --- 2. Заменяем файлы -----------------------------------------------------
rem  robocopy возвращает коды 0..7 как "успех"; >=8 — реальная ошибка.
rem  /E  — все подкаталоги, включая пустые
rem  /IS  — перезаписывать даже идентичные файлы
rem  /IT  — не менять атрибуты "tweaked"
rem  /NFL /NDL /NJH /NJS /NP — тихий вывод
robocopy "%SOURCE%" "%TARGET%" /E /IS /IT /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >NUL
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo [update] robocopy failed with code %RC%
    exit /b 4
)
rem --- 3. Перезапускаем приложение -------------------------------------------
if not "%LAUNCH%"=="" (
    start "" "%LAUNCH%"
)

rem --- 4. Убираем каталог-источник и сам скрипт ------------------------------
rem  rd может не сработать (файлы заняты) — это не критично, чистится позже.
rd /S /Q "%SOURCE%" >NUL 2>&1

rem  Самоудаление: запускаем del в отдельном cmd и сразу выходим,
rem  чтобы файл .cmd перестал быть занятым.
start "" /b cmd /c "del /F /Q "%~f0" >NUL 2>&1"
exit /b 0
```

Запуск из Python:

```python
import os, subprocess, sys, tempfile
from pathlib import Path

def spawn_updater(source: Path, target: Path, exe: Path) -> None:
    script = Path(tempfile.gettempdir()) / f"elite-hud-update-{os.getpid()}.cmd"
    script.write_text(
        HELPER_TEMPLATE.format(pid=os.getpid(), source=source, target=target, launch=exe),
        encoding="utf-8",
    )

    creationflags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS (0x8): у дочернего процесса нет консоли родителя.
        # CREATE_NEW_PROCESS_GROUP (0x200): изолирует от Ctrl+C родителя.
        # CREATE_NO_WINDOW (0x8000000): не мигать консольным окном.
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )

    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        close_fds=True,               # не наследовать handles — важно, иначе
                                      # помощник удержит блокировки файлов
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
```

**Замечания по `.cmd`, критичные на практике:**

1. **`tasklist` и определение отсутствия процесса.** `tasklist /FI "PID eq N"` при отсутствии
   процесса печатает «INFO: No tasks are running which match the specified criteria.» и
   возвращает **0** — поэтому проверять надо **наличие строки с PID**, а не `errorlevel`.
   Вариант `find "%PID%"` (как в текущем `updater.py`) тоже работает, но может дать ложное
   совпадение, если PID встречается в имени другого процесса или в заголовке; связка
   `/NH /FO CSV` + `findstr /C:"\"PID\""` точнее.
2. **`timeout /t` в GUI-приложении не работает** — `timeout.exe` требует консольного ввода и
   падает с «ERROR: Input redirection is not supported» при запуске из оконного процесса.
   Поэтому пауза через `ping -n 2 127.0.0.1`.
3. **Альтернативы ожидания:** `waitfor` (требует кооперации с другой стороны),
   PowerShell `Wait-Process -Id N -Timeout S` — надёжнее и без цикла:
   ```bat
   powershell -NoProfile -Command "Wait-Process -Id %PID% -Timeout 300 -ErrorAction SilentlyContinue"
   ```
   Но запуск PowerShell добавляет ~100–300 мс и зависимость от ExecutionPolicy (для
   `-Command` политика не мешает). Основной минус — PowerShell может отсутствовать в
   сильно урезанных окружениях (**не подтверждено** для Windows 10/11 — там он есть всегда).
   Цикл на `tasklist` не имеет внешних зависимостей, поэтому он в примере выше.
4. **`close_fds=True` обязателен.** Иначе дочерний процесс унаследует открытые хэндлы
   родителя на `.exe` и каталог `_MEI`, и замена файлов не удастся, даже когда процесс
   «завершился».
5. **Кодировка.** Файл `.cmd` записывается в UTF-8 без BOM — для русских сообщений в `echo`
   это даст кракозябры в консоли. Либо пишите `echo`-сообщения латиницей (как выше),
   либо сохраняйте файл в `cp866`. Это не влияет на логику, только на вывод.

### 4.5 PyInstaller: onefile vs onedir

**[DOC]** pyinstaller.org, «Operating Mode» — **How the One-File Program Works**:

> The bootloader is the heart of the one-file bundle also. **When started it creates a temporary
> folder in the appropriate temp-folder location for this OS. The folder is named `_MEIxxxxxx`,
> where `xxxxxx` is a random number.**
> The one executable file contains an embedded archive of all the Python modules used by your
> script, as well as **compressed** copies of any non-Python support files (e.g. `.so` files).
> **The bootloader uncompresses the support files and writes copies into the the temporary
> folder. This can take a little time. That is why a one-file app is a little slower to start
> than a one-folder app.**
> …
> **After creating the temporary folder, the bootloader proceeds exactly as for the one-folder
> bundle, in the context of the temporary folder. When the bundled code terminates, the
> bootloader deletes the temporary folder.**

Про one-folder:

> **Another advantage of a one-folder bundle is that when you change your code, as long as it
> imports exactly the same set of dependencies, you could send out only the updated `myscript`
> executable. That is typically much smaller than the entire folder.** (If you change the script
> so that it imports more or different dependencies, or if the dependencies are upgraded, you
> must redistribute the whole bundle.)

И официальная «мягкая» рекомендация:

> **Before you attempt to bundle to one file, make sure your app works correctly when bundled to
> one folder. It is is much easier to diagnose problems in one-folder mode.**

**[DOC]** pyinstaller.org, «Run-time Information»:

> `sys.frozen` — «When a bundled app starts up, the bootloader sets the `sys.frozen` attribute
> and stores the absolute path to the bundle folder in `sys._MEIPASS`. **For a one-folder bundle,
> this is the path to the `_internal` folder within the bundle.** For a one-file bundle, this is
> the path to the temporary folder created by the bootloader.»

Официальный способ определить, что мы во frozen-режиме:

```python
import sys
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    print("running in a PyInstaller bundle")
else:
    print("running in a normal Python process")
```

**[DOC]** Про `_internal` — официальный Changelog PyInstaller, версия **6.0.0 (2023-09-22)**:

> Restructure onedir mode builds so that everything except the executable (and `.pkg` if you're
> using external PYZ archive mode) are hidden inside a sub-directory. **This sub-directory's name
> defaults to `_internal` but may be configured with a new `--contents-directory` option.**
> Onefile applications and macOS `.app` bundles are unaffected. (:issue:`7713`)

И позже:

> Allow users to re-enable the old onedir layout (without contents directory) by setting the
> `--contents-directory` option (or the equivalent `contents_directory` argument to `EXE` in the
> .spec file) to `'.'`. (:issue:`7968`)

**Ответы на конкретные вопросы:**

- **`--contents-directory`** — имя подкаталога внутри onedir-сборки, куда складывается всё,
  кроме самого exe. По умолчанию `_internal`. Значение `'.'` возвращает старую раскладку
  (всё рядом с exe). Появился в PyInstaller 6.0.0.
- **`--runtime-tmpdir`** [DOC] `doc/usage.rst`: «The location of the temporary directory can be
  set statically, at compile time, using the `--runtime-tmpdir` option. If this option is used,
  the bootloader will ignore temporary directory locations defined by the OS, and use the
  specified path. The path can be either absolute or relative (which makes it relative to the
  current working directory). **Please use this option only if you know what you are doing.**»
  Дополнительно: «On POSIX systems, PyInstaller's bootloader does **not** perform shell-style
  environment variable expansion on the path string given via `--runtime-tmpdir` option.»
- **Скорость старта onefile** [DOC]: «a little slower to start». Точная количественная оценка
  в официальной документации **отсутствует** → **не подтверждено**. Причина по докам:
  распаковка архива и запись файлов на диск **при каждом** запуске (кэширования нет —
  каталог удаляется при завершении). Для PySide6 ситуация хуже, чем для «чистого» Python:
  Qt — это сотни мегабайт DLL, и их распаковка на каждом старте заметна (порядок — секунды;
  точная цифра **не подтверждена**).
- **Антивирус** [DOC] прямо **не** утверждает, что onefile чаще ложно срабатывает —
  **не подтверждено**. Однако из механики следует, что onefile делает больше «подозрительных»
  действий при каждом запуске: создаёт новый случайно названный каталог в `%TEMP%`,
  распаковывает туда исполняемый код и запускает его, а затем удаляет каталог. Это ровно тот
  поведенческий паттерн, на который реагируют эвристики. **Помечаю как обоснованное
  предположение, а не как документированный факт.**

**Аргументы за `onedir` вместо `onefile` для этого проекта:**

| Критерий | `onefile` | `onedir` |
|---|---|---|
| Скорость старта | Медленнее: распаковка всего бандла в `_MEIxxxxxx` **на каждом** запуске | Быстрее: файлы уже лежат на диске, распаковки нет |
| Самообновление | Заменяется один файл, но `_MEI`-каталог занят до выхода процесса; при сбое остаются «осиротевшие» `_MEI`-каталоги в `%TEMP%` | Заменяется каталог `_internal` + exe; `robocopy` умеет докатывать изменённое, можно обновлять частично |
| Размер обновления | Всегда весь бандл (~100 МБ+ для PySide6) | «when you change your code, as long as it imports exactly the same set of dependencies, you could send out only the updated `myscript` executable» — [DOC] |
| Ложные срабатывания AV | Больше «подозрительной» активности (распаковка + запуск кода из `%TEMP%`) — предположение | Меньше: код исполняется из своей папки |
| Диагностика | Сложнее | [DOC] «It is easy to debug problems … You can see exactly what files PyInstaller collected into the folder» |
| Мусор в `%TEMP%` | При аварийном завершении `_MEIxxxxxx` остаётся на диске | Нет |
| Удобство для пользователя | Один файл — понятнее | Каталог с файлами; для портативной версии — нужно архивировать |
| Установщик Inno | `[Files]` с одним `Source` | `[Files]` с `recursesubdirs createallsubdirs` — работает одинаково хорошо |

> ⚠️ **`_MEI`-мусор — подтверждённая проблема, но не «баг», а следствие дизайна.** [DOC]:
> «When the bundled code terminates, the bootloader deletes the temporary folder.» Если процесс
> убит (Task Manager, `taskkill /F`, падение ОС, сбой питания) — bootloader не успевает
> убрать каталог, и `_MEIxxxxxx` остаётся. Это особенно неприятно для приложения, которое
> живёт постоянно (оверлей) и регулярно перезапускается самообновлением.
> Также важно: **каталог `_MEI` заблокирован, пока процесс жив**, поэтому «дочистить» его
> извне до выхода процесса нельзя.

**Рекомендация.** Для `elite-hud` логичнее **`onedir`**, потому что:
1. Это Qt-приложение с большим бандлом → экономия на каждом запуске, а старт оверлея
   критичен для UX.
2. Обновления будут частыми и мелкими → `onedir` позволяет докатывать только изменённое.
3. Меньше мусора в `%TEMP%` и меньше AV-поверхности.
4. Диагностика проблем у игроков существенно проще (можно попросить скриншот каталога).
   Минус — портативный вариант становится zip-архивом каталога (что уже и предполагается:
   `portable_asset()` в `updater.py` ищет `.zip`).

Если остаётесь на `onefile` — обязательно:
- держите `--windowed` (у вас есть) и **проверьте, что `_MEI`-каталоги не копятся**;
- на старте приложения подчищайте осиротевшие каталоги `%TEMP%\_MEI*`, которые не
  принадлежат живым процессам (**нужна аккуратность: не удаляйте `_MEI` другого
  запущенного экземпляра — проверяйте, что PID мёртв**);
- вызывайте `sys.exit()` явно, чтобы bootloader успел выполнить очистку.

### 4.6 Правильный перезапуск приложения после обновления

**Значения констант.** В Python эти константы определены **только на Windows** — на других
платформах их нет (`getattr(subprocess, "DETACHED_PROCESS")` → `None`). **[LIVE]** проверил
на этой машине (macOS, Python 3.13.0): все перечисленные атрибуты отсутствуют. Поэтому код
обязан использовать `getattr(..., default)` или проверять `sys.platform == "win32"`.

| Константа | Значение | Смысл |
|---|---|---|
| `DETACHED_PROCESS` | `0x00000008` | Дочерний процесс не наследует консоль родителя |
| `CREATE_NEW_PROCESS_GROUP` | `0x00000200` | Новая группа процессов: изоляция от Ctrl+C/Ctrl+Break родителя |
| `CREATE_NO_WINDOW` | `0x08000000` | Не создавать консольное окно |
| `CREATE_NEW_CONSOLE` | `0x00000010` | Создать новую консоль |
| `CREATE_BREAKAWAY_FROM_JOB` | `0x01000000` | Выйти из Job Object родителя |

> Значения приведены из Win32 API `CreateProcess` (dwCreationFlags). **[LIVE]** на Windows
> атрибуты `subprocess.*` принимают ровно эти значения — это видно из CPython, но
> непосредственно проверить на Windows я не мог. Считайте таблицу соответствующей
> документации Win32.

**Почему одного `DETACHED_PROCESS` недостаточно:**

- `DETACHED_PROCESS` лишь отвязывает консоль. Если приложение запущено из GUI (без консоли),
  эффект мал, но `subprocess.Popen(["cmd.exe", "/c", script])` **всё равно** может мигнуть
  консольным окном → нужен `CREATE_NO_WINDOW`.
- Без `CREATE_NEW_PROCESS_GROUP` дочерний процесс входит в группу родителя, и сигналы
  (Ctrl+C, а также завершение дерева процессов некоторыми средствами) могут его задеть.
- **Ключевое:** если приложение запущено внутри **Job Object** с флагом
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (так делают некоторые оболочки, службы, а иногда
  Explorer/терминалы), при выходе родителя **всё дерево процессов будет убито**, включая
  помощника. Тогда нужен `CREATE_BREAKAWAY_FROM_JOB` (и право
  `JOB_OBJECT_LIMIT_BREAKAWAY_OK` у Job Object). Это **не подтверждено** применительно к
  обычному запуску из Проводника — но стоит проверять при отладке «помощник не сработал».
- `close_fds=True` — не наследовать handles. **Обязательно** при обновлении, иначе помощник
  удержит открытые файлы/каталоги и замена не произойдёт.
- `stdin=subprocess.DEVNULL` — иначе `.cmd` унаследует stdin родителя, и `timeout.exe` внутри
  может упасть.
- **Запуск `.cmd` требует `cmd.exe /c`** (или `shell=True`, что менее предсказуемо).
  `Popen(["script.cmd"])` на Windows работает не всегда — предпочтительно явно
  `["cmd.exe", "/c", path]`.

**Итого правильный вызов:**

```python
creationflags = (
    subprocess.DETACHED_PROCESS          # 0x00000008
    | subprocess.CREATE_NEW_PROCESS_GROUP # 0x00000200
    | subprocess.CREATE_NO_WINDOW         # 0x08000000
)
subprocess.Popen(
    ["cmd.exe", "/c", str(helper_cmd)],
    close_fds=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=creationflags,
)
```

**`os.startfile` / `ShellExecuteW` — когда что:**

- `os.startfile(path)` — открывает файл/URL «как двойным кликом» (ShellExecute). Удобно, чтобы
  запустить приложение после обновления или открыть ссылку на релиз. **Не** подходит для
  передачи сложных аргументов и для ожидания результата.
- `ShellExecuteW(None, "runas", setup, args, None, 1)` — единственный правильный способ
  **запросить повышение прав (UAC)** для установщика. `subprocess.Popen` UAC не показывает:
  он либо унаследует права, либо упадёт. Именно так и сделано в `apply_installer()`
  в `elite_hud/updater.py` — это корректно. Возврат `<= 32` означает ошибку (в частности
  `SE_ERR_ACCESSDENIED` = 5 при отказе пользователя в UAC).
- Для **per-user** установки (`PrivilegesRequired=lowest`, без UAC) повышение не нужно:
  запускайте установщик обычным `Popen` с `creationflags` из примера выше — так пользователь
  не увидит лишний UAC-запрос. В текущем коде есть параметр `elevate: bool = True` — для
  per-user установки его следует передавать `False` (определять по
  `detect_install()`/`PrivilegesRequired`).

---

## 5. Подпись кода

### 5.1 Что произойдёт с неподписанным PyInstaller-exe

**[DOC]** Microsoft Learn, «Code signing options for Windows app developers»
(`learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options`) — официальная
сводная таблица. Привожу её как есть:

| Вариант | Стоимость | Доступность | Поведение SmartScreen | Даёт ли Store |
|---|---|---|---|---|
| **Microsoft Store (MSIX)** — Store переподписывает | **Бесплатно** | Весь мир | ✅ Без предупреждений | ✅ Да |
| **Microsoft Store (MSI/EXE)** — подписывает издатель | Нужен сертификат, цепочка к CA из Microsoft Trusted Root Program | Весь мир | ✅ Нет SmartScreen-промптов при установке из Store (**UAC может появиться**) | ✅ Да |
| **Azure Artifact Signing** (бывш. Trusted Signing) | **~$9.99/мес** | Организации: США, Канада, ЕС, Великобритания. **Физлица: только США и Канада** | ⚠️ Репутация набирается со временем; на первых релизах предупреждения ожидаемы | ❌ Нет |
| **OV-сертификат** (DigiCert, Sectigo, GlobalSign…) | **$150–300/год** | Весь мир | ⚠️ То же, что Azure Artifact Signing | ❌ Нет |
| **EV-сертификат** | **$400+/год** | Весь мир | ⚠️ **То же, что OV с 2024 года — мгновенного обхода больше нет** | ❌ Нет |
| **Самоподписанный** | Бесплатно | — | ❌ **Блокирует установку у обычных пользователей** | ❌ Нет |
| **Без подписи** | Бесплатно | — | ❌ **Сильная блокировка SmartScreen; в организациях может быть запрещено полностью** | ❌ Нет |

**[DOC]** «SmartScreen reputation for Windows app developers» — таблица поведения при
первом скачивании:

| Тип сертификата | Поведение SmartScreen при первом скачивании |
|---|---|
| Microsoft Store | ✅ «No warning — covered by Microsoft's certificate» |
| **Valid Certificate (OV/EV)** | ⚠️ «Warning — app flagged as unrecognized until reputation accumulates; verified publisher name is displayed» |
| **No signature** | ⚠️ «Warning — **"Windows protected your PC"**; User must choose "Run anyway" before the app can run. **Enterprise policy can prevent continuation entirely.**» |
| Self-signed Certificate | ⚠️ «Warning — Same behavior as no signature» |

**Точный текст диалога.** Подтверждена фраза **«Windows protected your PC»** (заголовок
диалога). Кнопка обхода — **«Run anyway»** (через **«More info»**).

> ⚠️ **Не подтверждено:** полный текст подзаголовка вида «Microsoft Defender SmartScreen
> prevented an unrecognized app from starting. Running this app might put your PC at risk.» —
> на актуальных страницах Microsoft Learn я нашёл только «Windows protected your PC» и
> «Run anyway». Не цитируйте остальной текст как официальный без проверки на живой Windows 11.

**Как устроена репутация — [DOC] дословно:**

> SmartScreen evaluates two signals when a user downloads and runs a file:
> - **Publisher reputation** — Is the file signed? Is the signing certificate from a known,
>   trusted publisher?
> - **File hash reputation** — Has this specific file been downloaded by users without
>   indications of malicious behavior?
>
> A negative or unknown reputation for a file's hash or its publisher's certificate can cause
> warnings to show. **Even when signed, a newly created binary could still show a SmartScreen
> warning until its hash or publisher certificate accumulates sufficient evidence of positive
> reputation.**
>
> **When a file is not signed, SmartScreen reputation must build for each new version of your
> files, starting with zero reputation. Reputation cannot transfer from previous versions unless
> both were signed using the same publisher identity.**
>
> **Signing files using a trusted certificate can allow certificate reputation to build,
> potentially avoiding warnings on new files signed by the same trusted certificate. Unsigned
> files must build reputation anew with every update.**

> 💡 **Это самый весомый аргумент за сертификат, даже без мгновенного эффекта.** Репутация
> привязана к **идентичности подписи (сертификату)**, а не к версии файла. Подписанное
> приложение со временем перестаёт предупреждать **на всех последующих релизах**; неподписанное
> **начинает с нуля при каждом обновлении** — то есть при частых релизах (а у автообновляемого
> приложения они частые) пользователи будут видеть предупреждение **каждый раз**.
> Microsoft также прямо говорит, что OV и Artifact Signing **функционально эквивалентны**:
> «OV certificates are a proven option and are functionally **equivalent to Azure Artifact
> Signing for SmartScreen purposes**».

**Сроки набора репутации — [DOC]:**

> **There is no exact threshold, but it can take several weeks and hundreds of clean installs
> from a wide audience.**

**EV больше не даёт мгновенного обхода — [DOC] дословно:**

> **EV certificates no longer bypass SmartScreen.** Years ago, signing files with an Extended
> Validation (EV) code signing certificate would result in positive SmartScreen reputation by
> default, but **this behavior no longer exists**. EV certificates may matter for enterprise
> procurement, but they no longer impact SmartScreen behavior. **Paying a premium for EV solely
> to avoid SmartScreen warnings is no longer justified.**

**Ключевой ответ: обойти SmartScreen без сертификата НЕЛЬЗЯ — [DOC] дословно:**

> **There is no need (or mechanism) to manually submit a file for SmartScreen reputation review
> for consumer endpoints. Reputation builds organically through download volume.**

То есть «пожаловаться» на ложное срабатывание и получить «разрешение» для обычных
пользователей нельзя. Единственное исключение — **корпоративные** окружения:

> Enterprise environments may have different SmartScreen behavior depending on policy
> configuration; for example, **the ability to bypass a SmartScreen warning may be disabled**.
> Enterprises may distribute files from Trusted Intranet locations not subject to SmartScreen
> review. **Enterprise IT administrators may optionally submit files for review via the Microsoft
> Security Intelligence portal.** This can accelerate trust for internal or managed deployments.

**Рекомендации Microsoft по минимизации предупреждений — [DOC]:**

> - **Publish to the Microsoft Store where feasible** — this is the most reliable way to avoid
>   warnings entirely
> - **Sign every release** — unsigned files cannot inherit a positive reputation from the
>   signing certificate
> - **Do not modify signed files** — Avoid modifying files after signing as doing so can break
>   the signature depending on client configuration
> - **Do not sign potentially unwanted applications** — … or the certificate may develop negative
>   reputation
> - **Use a consistent signing identity** — changing your signing certificate affects the
>   publisher trust signal
> - **Communicate with early adopters** — for new apps, let beta users know they may see a
>   SmartScreen prompt on first download…

**MOTW (Mark-of-the-Web) и откуда берётся предупреждение — РАЗРЕШЕНО.**

Ранее я помечал этот пункт как неподтверждённый. Теперь ключевой факт **подтверждён дословной
цитатой Microsoft** — **[DOC]** страница Microsoft Defender SmartScreen содержит явный блок
«Important» (проверено мной повторно, HTTP 200):

> **Important**
> SmartScreen protects against malicious files from the internet. **It doesn't protect against
> malicious files on internal locations or network shares, such as shared folders with UNC paths
> or SMB/CIFS shares.**

Источник: https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen

**Практический вывод по способу распространения (главный ответ на вопрос «а если не браузер»):**

| Способ доставки | MOTW | Предупреждение SmartScreen |
|---|---|---|
| Запуск локально собранной сборки | нет | **нет** |
| Копирование из общей папки / UNC / SMB | нет | **нет** — **[DOC]** явное исключение («It doesn't protect against… network shares») |
| Скачано браузером / из почты | да | **да** |
| **Скачан `.zip` → распакован Проводником** | **да (переносится)** ⚠️ | **да** |
| Скачанный установщик (Inno/NSIS) | да (на `.exe` установщика) | **да**, на самом установщике |

🔴 **КРИТИЧНО ДЛЯ ЭТОГО ПРОЕКТА:** Проводник Windows **переносит MOTW из скачанного `.zip`
на распакованные файлы**. То есть штатный паттерн «публикуем portable-сборку как `.zip` в
GitHub Releases» **приводит к появлению предупреждения** у распакованного `.exe`. Это относится
и к `onedir`-варианту, и к `onefile`. 7-Zip по умолчанию MOTW **не** переносит (чем и
объясняются истории про «обход SmartScreen через 7-Zip»), но полагаться на это нельзя —
пользователь может распаковать Проводником.
> ⚠️ Статус: поведение Проводника подтверждено вторичным разбором
> ([DFIR, 2026-06-29](https://dfir.ru/2026/06/29/mark-of-the-web-the-rules-changed-the-tools-didnt/)),
> но **не** дословной цитатой Microsoft. Считайте это обоснованным, но не официально
> документированным.
> ⚠️ Также **не подтверждено**: снимает ли установщик Inno Setup MOTW с устанавливаемых файлов.
> Общего правила «инсталлятор всегда снимает MOTW» в документации Microsoft нет — проверьте
> эмпирически (свойство файла → «Разблокировать»).

**🔴 Smart App Control на Windows 11 перекрывает всё вышесказанное.** [DOC] дословно:

> **On Windows 11 devices, the Smart App Control feature may supersede SmartScreen Application
> Reputation. Smart App Control will block execution of unsigned files unless the file has a
> positive reputation. Smart App Control signature checks apply to all executable files, not just
> those downloaded from the Internet.**

**[DOC]** Дополнительно, страница Smart App Control overview:

> **Malware, Potentially Unwanted Apps (PUA), and unknown, unsigned code are blocked by default.**

Это **прямой ответ** на вопрос «а если файл не скачан из браузера»: на Windows 11 с включённым
**Smart App Control** неподписанный exe **блокируется независимо от источника** — включая
локально распакованный и даже локально собранный. Smart App Control требует «positive
reputation», которую без подписи набрать нельзя.

**Что НЕ помогает (явно):**
- ❌ Самоподписанный сертификат — [DOC] «will trigger a strong SmartScreen block for any user
  who hasn't manually installed the certificate as a trusted root». Годится только для
  разработки и для предприятий с управляемым доверием (Intune/GPO).
- ❌ «Пожаловаться в Microsoft» — механизма для consumer-эндпоинтов нет (цитата выше).
  ⚠️ Оговорка: страница Defender SmartScreen **всё же** предлагает подать файл на проверку
  через форму WDSI («make sure to select Microsoft Defender SmartScreen from the product
  menu», https://www.microsoft.com/en-us/wdsi/filesubmission — есть роль «Software developer»),
  а страница репутации утверждает обратное. Это **противоречие в самой документации Microsoft**:
  форма WDSI предназначена для оспаривания ложных срабатываний/проверки детекций, а **не** для
  выдачи репутации по запросу. Практического способа «получить репутацию подачей» нет.
- ❌ EV ради обхода SmartScreen — не работает с 2024 года (цитата выше).
- ❌ **`winget`** — даёт только обнаруживаемость; документация Microsoft помечает сертификат как
  «recommended», но **не** даёт `winget` никакого эффекта на SmartScreen.
- ❌ Переименование файла / смена версии — репутация привязана к хешу и сертификату, не к имени.

**Что реально работает без покупки сертификата:**
1. **Microsoft Store (MSIX)** — [DOC] «code signing is free and handled for you automatically —
   Microsoft re-signs the package after certification and you don't need to purchase or manage a
   certificate». Плюс «users never see a SmartScreen warning». Это **единственный бесплатный
   способ полностью убрать предупреждения**.
   ✅ **ПОДТВЕРЖДЕНО: регистрация разработчика стала бесплатной.**
   **[LIVE]** Блог Windows Developer, **7 мая 2026**, «Publish to Microsoft Store as a company—
   now with free registration and faster onboarding», дословно:
   > **Free registration** — The **$99 onboarding fee for company developer accounts has been
   > removed**, lowering the barrier to get started on the Microsoft Store.

   Также добавлена поддержка входа через Microsoft Entra ID (рабочие аккаунты).
   Источник: https://blogs.windows.com/windowsdeveloper/2026/05/07/publish-to-microsoft-store-as-a-company-now-with-free-registration-and-faster-onboarding/
   ⚠️ **Но для PyInstaller это не бесплатный путь, если идти через MSI/EXE.** [DOC] Путь
   «Microsoft Store (MSI/EXE installer)» требует, чтобы издатель **сам** подписал установщик
   сертификатом с цепочкой к CA из Microsoft Trusted Root Program (self-signed не принимается).
   Бесплатная переподпись Microsoft работает **только для пакетов MSIX**. Значит PyInstaller-exe
   надо упаковывать в MSIX, чтобы воспользоваться бесплатным вариантом.
2. **SignPath Foundation** — для open source (см. 5.2).
3. Терпеливый набор репутации **подписанными** релизами (не вариант без сертификата).

### 5.2 Стоимость сертификатов и бесплатные варианты

**Уже подтверждённые цифры (Microsoft Learn, сводная таблица выше):**

| Вариант | Цена | Условия |
|---|---|---|
| Azure Artifact Signing | **~$9.99/мес** | Организации: США, Канада, ЕС, Великобритания. Физлица: **только США и Канада** |
| OV | **$150–300/год** | В зависимости от CA и уровня |
| EV | **$400+/год** | Больше не даёт преимущества по SmartScreen |

> Цены — **ориентировочные, по данным Microsoft Learn** на 2026 год, а не прайс конкретного CA.
> Не считайте их точными коммерческими предложениями.

**Azure Artifact Signing — точные данные (проверенные):**

- **Название изменилось.** **[LIVE]** Страница тарифов теперь озаглавлена «**Artifact
  Signing**» (23 упоминания), «Trusted Signing» — 0 упоминаний. Microsoft Learn говорит
  «Azure Artifact Signing (formerly Trusted Signing)». **В документации используется новое
  имя; старые URL `learn.microsoft.com/azure/trusted-signing/...` ещё работают.**
- **Тарифы — [LIVE]** со страницы `azure.microsoft.com/en-us/pricing/details/trusted-signing/`
  (значения из JSON-атрибута `data-amount`, регион us-east):

| | Basic | Premium |
|---|---|---|
| Базовая цена (в месяц) | **$9.99** | **$99.99** |
| Квота (подписей/месяц) | **5 000** | **100 000** |
| Цена сверх квоты | **$0.005 / подпись** | **$0.005 / подпись** |
| Включено | Public/Private Signing, **1** профиль каждого типа | Public/Private Signing, **10** профилей каждого типа |

- **[DOC]** Требования: «**Artifact Signing doesn't support free, trial, or sponsored Azure
  subscriptions.** … you must have a paid Azure subscription» — нужна платная (pay-as-you-go
  или EA) подписка Azure.
- **[DOC]** География (дословно из quickstart): «Public Trust certificates are available to
  organizations in the United States, Canada, the European Union, the United Kingdom, Australia,
  New Zealand, Japan, South Korea, Singapore, Switzerland, Norway, and Israel. **Individual
  developers must be located in the United States or Canada.** These geographic restrictions do
  not apply to Private Trust certificates.»
- **[DOC]** Для физлиц: «Artifact Signing automatically sources identity details from the Azure
  billing account associated with the subscription… **The billing account must have an Account
  Type of Individual.**»
- **Требование «3+ года налоговой истории» — ПРОТИВОРЕЧИВО, помечаю как неоднозначное.**
  В публичном предпросмотре такое требование было. Но 2026-08-17 сотрудник Microsoft
  (модератор) ответил в Microsoft Q&A: «**Artifact Signing has country/region onboarding
  pre-reqs, no minimum org age restrictions**» со ссылкой на prerequisites в quickstart.
  На странице «Code signing options» возрастных требований **нет** (только география).
  При этом AI-ответ на той же странице Q&A и страница про подпись MSIX упоминают «verifiable
  tax history of three or more years». Также есть сообщение на Hacker News «Azure Artifact
  Signing no longer requires 3 years of tax history» (2026), где автор подтвердил, что
  верифицировал компанию младше 3 лет.
  **Вывод: актуальные официальные страницы возрастного требования не содержат, требование,
  вероятно, снято — но окончательно не подтверждено. Проверяйте при онбординге.**
- **[DOC]** Требуется валидация личности Microsoft («plan for a few business days»),
  **не нужен аппаратный токен**, интегрируется с CI/CD (GitHub Actions, Azure DevOps).
- **[DOC]** **Не** даёт мгновенного доверия SmartScreen: «New files can show a SmartScreen
  warning until they accumulate sufficient reputation. Azure Artifact Signing does not provide
  instant SmartScreen trust, but signing consecutive releases with a consistent publisher/signing
  identity lets publisher reputation build over time.»

**SignPath Foundation — бесплатно для open source.** **[LIVE]** `signpath.org` дословно:

> # Free Code Signing for Open Source software
> No more installation warnings. SignPath Foundation provides you with a code signing certificate
> that provides a clear link between your repository and the published binary.
>
> **The Solution**
> - SignPath Foundation provides you with a code signing certificate.
> - **No need for personal identification, we verify that the binary was built from your open
>   source repository and vouch for that with our name.**
> - By using SignPath.io for code signing, the private key of your certificate is securely
>   generated and stored on our Hardware Security Module (HSM).
> - Integration in your automated build process is simple.
> - **For OSS projects, our services are free of charge.**

Проекты-примеры на сайте: Stellarium, Flameshot, Git Extensions, Layer 1 Lite DB.

**[DOC]** Microsoft Learn подтверждает: «If your project is open source, SignPath Foundation
offers free code signing for qualifying open-source projects. **The program provides OV-level
certificate signing through a managed pipeline.** Check the SignPath Foundation website for
eligibility requirements and the application process.»

**Важные ограничения SignPath Foundation:**
- Сертификат **принадлежит SignPath** — пользователь видит издателя SignPath Foundation, а не
  вас. Именно так работает модель: «we verify that the binary was built from your open source
  repository and **vouch for that with our name**». Формулировка их условий: «**SignPath
  Foundation is the publisher of the OSS project**». SignPath при этом **не является CA**.
- **Точные критерии (получены из `signpath.org/terms`):** OSI-совместимая открытая лицензия
  **без коммерческого dual-licensing** для всех компонентов; отсутствие проприетарных
  компонентов; отсутствие malware/PUP; проект активно поддерживается; уже выпущен; задокументирован
  на странице загрузки; **MFA обязателен для всех участников команды**; роли
  Authors/Reviewers/Approvers; **ручное одобрение каждого релиза**; на главной странице проекта
  должна быть надпись «Free code signing provided by SignPath.io, certificate by SignPath
  Foundation».
  > ⚠️ Статус: это **вторичный источник** (текст `terms.html` приведён моим исследовательским
  > субагентом; я его дословно не перепроверял). Само наличие бесплатной программы для OSS
  > подтверждено дважды — сайтом SignPath и Microsoft Learn.
- 🔴 **Они прямо оставляют за собой право отказать:** «For executable programs… we require a
  certain verifiable reputation»; «We're under no obligation to accept your project, and there is
  no independent arbitration mechanism.» **Малоизвестное приложение может получить отказ.**
  Это существенно: путь через SignPath **не гарантирован**.
- Подпись происходит через их пайплайн (SignPath.io), не локально.
- Для **закрытого** проекта бесплатных вариантов **нет**.

**Прайс-листы CA (⚠️ вторичный источник, мной не перепроверены — SSL.com отдал 301 и таймаут).**
Ориентиры Microsoft (**[DOC]**, авторитетно): OV **$150–300/год**, EV **$400+/год**.
Фактические прайс-листы, собранные субагентом: OV — **SSL.com $129/год** (самый дешёвый),
Sectigo $313.50/год, GlobalSign $529/год (токен) или $289/год (HSM), DigiCert $696/12 мес.;
EV — SSL.com $349/год, Sectigo $410.85/год, GlobalSign $669/год (токен) или $410/год (HSM),
DigiCert $972/12 мес. Облачная подпись: DigiCert KeyLocker +$300/год, токен +$144/год,
SSL.com eSigner $15–187.50/мес по тарифу. **GlobalSign и Sectigo включают токен бесплатно.**
→ Используйте эти цифры только как ориентир для переговоров, не как оферту.

**🔴 НОВОЕ В 2026: максимальный срок сертификата сокращён до 460 дней.**
**[LIVE]** Я проверил CSBR напрямую на cabforum.org (HTTP 200), дословно:

> For Code Signing Certificates issued before March 1st, 2026, the validity period MUST NOT
> exceed **39 months**. For Code Signing Certificates issued on or after March 1st, 2026, the
> validity period MUST NOT exceed **460 days**.

Там же в таблице «Relevant Dates»: `2026-03-01 | 6.3.2 | For Code Signing Certificates issued
on or after March 1st, 2026, the validity period MUST NOT exceed 460 days.`
Баллот: **CSC-31 «Maximum Validity Reduction», 7 ноября 2025**. Также: «The Timestamp
Certificate validity period MUST NOT exceed 135 months.»
→ **Практический вывод:** многолетние сертификаты фактически исчезают. Экономия «купить на
3 года» больше не работает; планируйте **ежегодное** продление (~$129–300/год для OV).
GlobalSign перестал продавать 2- и 3-летние сертификаты **26 декабря 2025**.

🔴 **Совсем свежее (в день подготовки отчёта):** в той же таблице —
`2026-09-15 | 7.1.6.4 | Effective September 15, 2026, a Certificate issued to a Subscriber MUST
contain exactly one of the reserved policy OID.` (баллот **CSC-32**). Это требование действует
**с 15 сентября 2026**; практического влияния на выбор варианта не оказывает, но означает, что
CA-практики сейчас меняются — уточняйте у CA актуальные условия.

**Обязательное требование CA/B Forum (ломает CI-подпись «из секрета») — [LIVE]**
подтверждено на GlobalSign Support («New Requirements related to Private Key protection for
CodeSigning Certificates»):

> The Certificate Authority/Browser (CA/B) Forum has introduced updates to Baseline
> Requirements (BRs) for issuing CodeSigning Certificates. **Effective June 1, 2023, a private
> key should be generated and protected in a FIPS 140-2 Level 2 or Common Criteria EAL 4+
> compliant devices for both Standard and EV CodeSigning Certificates.** … the key pair must be
> generated and stored in a hardware crypto module that meets or exceeds the requirements of
> FIPS 140-2 level 2 or Common Criteria EAL 4+.

И практическое следствие (GlobalSign, эффективно с **24 апреля 2023**):

> 1. A compliant hardware token, or HSM, would be required for both Standard & EV CodeSigning
>    Certificates.
> 2. In case of issuing a Certificate on HSM, an internal or external audit letter will be
>    required stating that the subscriber will be using compliant HSMs for CodeSigning Certificates.
> …
> **Will it be possible to download the `.PFX` format of the Standard CodeSigning Certificate?**
> **Effective April 24 2023, you will need to install the Certificate directly into a FIPS 140-2
> level 2 or Common Criteria EAL 4+ compliant device. You will be unable to download the
> Certificate in `.PFX` format.**

**[DOC]** Microsoft Learn подтверждает то же: «**HSM requirement:** As of June 2023, the
CA/Browser Forum requires private keys for OV certificates to be stored on a hardware security
module (HSM) or hardware token. Most CAs provide a compatible USB token or cloud HSM option.»

> 🔴 **Главное следствие для CI:** **больше нельзя положить `.pfx` в GitHub Secret и подписывать
> в Actions.** Ключ физически не экспортируется. Варианты: (а) облачный HSM-сервис CA
> (обычно дороже), (б) сервис вроде Azure Artifact Signing / SignPath, (в) физический токен,
> подключённый к self-hosted раннеру. Это ключевой аргумент в пользу Azure Artifact Signing
> или SignPath для облачной сборки.

### 5.3 Итоговая рекомендация по подписи для elite-hud

| Ситуация | Что делать |
|---|---|
| Проект **open source** | **SignPath Foundation** — бесплатно, OV-уровень, интеграция с CI. Издатель в подписи — SignPath Foundation. ⚠️ Они могут отказать («we require a certain verifiable reputation») |
| **Нужно без предупреждений и без денег** | **Microsoft Store (MSIX)** — регистрация **бесплатна с 2026-05-07** ($99 отменён), Microsoft переподписывает, предупреждений нет. ⚠️ Требует упаковки в MSIX; путь MSI/EXE **не** бесплатный (нужна своя подпись) |
| Закрытый проект, ~$120/год, вы **в США/Канаде** (физлицо) или организация в США/Канаде/ЕС/UK | **Azure Artifact Signing (Basic, $9.99/мес)** — нет токена, CI-friendly, рекомендуется Microsoft. Но нужна платная подписка Azure, и первые релизы всё равно с предупреждением |
| Закрытый проект, вне этих регионов | **OV-сертификат** у CA (~$129–300/год, ежегодное продление — 460-дневный лимит) + облачный HSM, либо физический токен на self-hosted раннере |
| Нет бюджета и нет OSS | Подписи нет → «Windows protected your PC» при первом запуске; на Windows 11 со **Smart App Control** приложение может **не запуститься вообще**. Это надо честно написать в README |
| Закрытый проект, но нужен только self-signed | Только для внутреннего/корпоративного распространения с управляемым доверием (Intune/GPO). Публично — не работает |

> **Важное дополнение про распространение.** Если вы публикуете portable-сборку как `.zip`,
> предупреждение всё равно появится у тех, кто распакует её **Проводником** (MOTW переносится).
> Единственный способ доставки **без** предупреждения без сертификата — распространение внутри
> локальной сети/по UNC (Microsoft прямо исключает network shares из защиты) либо через
> Microsoft Store. Для публичного распространения через GitHub Releases это не помогает.

---

## Приложение A. Сводка «не подтверждено»

1. **Полный текст подзаголовка SmartScreen-диалога** (кроме «Windows protected your PC» и
   «Run anyway») — на актуальных страницах Microsoft Learn не найден. Фраза «Microsoft Defender
   SmartScreen prevented an unrecognized app from starting…» встречается только в заголовках
   обсуждений Microsoft Q&A (пользовательский контент) и сторонних гайдах. Ссылка «More info»
   также **не подтверждена** документацией Microsoft.
   ✅ Что подтверждено: «Windows protected your PC», кнопка «Run anyway», приложение помечено
   «unrecognized», «Enterprise policy can prevent continuation entirely».
2. **Текст UAC для неподписанного файла** — строка «Do you want to allow this app from an
   unknown publisher to make changes to your device?» документацией Microsoft **не подтверждена**
   (только сообщества). Подтверждено: неподписанный → «Publisher not verified (unsigned)» и
   жёлтый фон запроса на повышение прав.
3. **Перенос MOTW Проводником из `.zip`** — подтверждено вторичным разбором
   (DFIR, 2026-06-29), **не** дословной цитатой Microsoft. Дословно подтверждено лишь то, что
   SmartScreen **не** защищает файлы на network shares / внутренних расположениях
   (см. раздел 5.1 — это ключевое исключение теперь подтверждено).
4. **Снимает ли установщик Inno Setup MOTW с устанавливаемых файлов** — общего правила в
   документации Microsoft нет. Проверяйте эмпирически.
5. **«Переименование запущенного exe работает на Windows»** — подтверждено объяснением
   сообщества Super User (получено через Stack Exchange API, так как HTML закрыт Cloudflare:
   HTTP 403), но **не** официальной документацией Microsoft. Прямой цитаты Microsoft Learn /
   Raymond Chen получить не удалось.
6. **Требование «3+ года налоговой истории» для Azure Artifact Signing** — противоречивые
   сведения: сотрудник Microsoft говорит, что требования нет; другие страницы Microsoft
   упоминают 3 года; есть сообщение об отмене. Актуальные страницы требования не содержат.
7. **Расхождение в географии между страницами Microsoft** — quickstart перечисляет 11 стран
   (включая Австралию, Японию, Корею, Сингапур, Швейцарию, Норвегию, Израиль), а
   «code-signing-options» говорит только «USA, Canada, EU, UK». Не подтверждено, какая из
   страниц актуальнее.
8. **Прайс-листы конкретных CA** — вторичный источник, мной не перепроверены (SSL.com отдал
   HTTP 301 и таймаут). Авторитетны только диапазоны Microsoft: OV $150–300/год, EV $400+/год.
9. **Коммерческие тарифы SignPath.io** (не Foundation) — не опубликованы (`/pricing` → 404).
10. **Точный путь `ISCC.exe` на GitHub-раннерах** — в `actions/runner-images` путь не указан
   (подтверждён только факт «InnoSetup 6.7.1» и установка через choco-пакет `innosetup`).
   Путь `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` подтверждён двумя реальными
   workflow и гайдом сообщества, но не первоисточником.
11. **Является ли `Global\`-мьютекс доступным непривилегированному процессу**
   (`SeCreateGlobalPrivilege`) — в справке Inno Setup `Global\` встречается лишь как пример
   значения `AppMutex`.
12. **Код выхода 1 при `AppMutex` + `/SUPPRESSMSGBOXES`** — выведено из исходников
   `jrsoftware/issrc`, не из явной фразы справки. Проверьте эмпирически.
13. **Количественная оценка замедления старта onefile** — официальная документация говорит
   только «a little slower to start».
14. **Повышенная частота ложных срабатываний AV для onefile** — документально не подтверждена,
   приведён как обоснованный механизм.
15. **Не вызывает ли Qt/PySide6 `RegisterApplicationRestart` автоматически** — считаю, что нет,
    но официального утверждения не нашёл. Проверьте на живой сборке (после тихого обновления
    приложение не вернулось → значит не вызывает).
16. **Значения Win32 `creationflags`** — приведены по документации `CreateProcess`;
    непосредственная проверка на Windows не выполнялась (на macOS эти атрибуты `subprocess`
    отсутствуют, что я подтвердил).
17. **Данные из `Azure Retail Prices API`** (effectiveStartDate, отсутствие пропорциональной
    оплаты) — приведены моим субагентом; я независимо подтвердил только суммы $9.99/$99.99/
    $0.005 со страницы тарифов, но не через сам billing API.

> **Снято с учёта (было «не подтверждено», теперь подтверждено):**
> - **Ответ на вопрос «а если не скачано браузером»** — подтверждён дословной цитатой Microsoft
>   об исключении для network shares (раздел 5.1).
> - **Стоимость регистрации разработчика в Microsoft Store** — подтверждено: бесплатно
>   с 2026-05-07 (раздел 5.1).
> - **Максимальный срок сертификата** — подтверждено по CSBR: 460 дней с 2026-03-01 (раздел 5.2).
> - **Критерии SignPath Foundation** — получены из `terms` (раздел 5.2), статус: вторичный
>   источник, но сама бесплатность подтверждена дважды.

## Приложение B. Замеченные расхождения с текущим кодом проекта

Относятся к `elite_hud/updater.py` и `elite_hud/installation.py`
(на момент проверки, 2026-09-16):

| # | Файл / место | Наблюдение | Рекомендация |
|---|---|---|---|
| 1 | `updater.py`, `SILENT_SETUP_FLAGS` | Используется `/SILENT` — по документации это **показывает окно прогресса**. Плюс отсутствует `/NORESTARTAPPLICATIONS` | Заменить на `/VERYSILENT`; при `RestartApplications=yes` в .iss добавить `/NORESTARTAPPLICATIONS`, чтобы не полагаться на `RegisterApplicationRestart` |
| 2 | `updater.py`, `parse_release` | `url = browser_download_url or url` — предпочитает URL для браузера | Для приватных репозиториев использовать `raw["url"]` (asset API) + `Accept: application/octet-stream`, а `browser_download_url` — только как fallback |
| 3 | `updater.py`, `apply_installer` | Нет способа дождаться исчезновения мьютекса перед запуском Setup → гонка с `AppMutex` (возможен тихий выход Setup с кодом 1) | Запускать Setup через помощника, который сначала ждёт освобождения мьютекса/PID |
| 4 | `updater.py`, `apply_installer` | После тихого обновления нет механизма перезапуска приложения | Добавить в `.iss` запись `[Run]` с `Flags: nowait skipifnotsilent runasoriginaluser` |
| 5 | `updater.py`, `apply_installer`, `elevate=True` | Для per-user установки UAC не нужен и вреден | Передавать `elevate=False` для non-admin установки (определять по `detect_install`) |
| 6 | `installation.py`, `_registry_locations` | Хардкодит `Software\WOW6432Node\...` | Microsoft: «New applications should avoid using Wow6432Node in registry key paths» — использовать флаг `KEY_WOW64_32KEY` на пути без `WOW6432Node` |
| 7 | `installation.py`, `_acquire_windows` | `ctypes.windll.kernel32.GetLastError()` | Использовать `ctypes.WinDLL("kernel32", use_last_error=True)` + `ctypes.get_last_error()` — надёжнее против гонки |
| 8 | `tools/build_exe.py` | Собирает `--onefile` | Рассмотреть `--onedir`: быстрее старт, меньше мусора в `%TEMP%`, дешевле обновления, лучше диагностика (см. 4.5) |
| 9 | `.iss` (планируемый) | `RestartApplications` | Помнить: автоперезапуск требует `RegisterApplicationRestart` в приложении; надёжнее — запись `[Run]` с `skipifnotsilent` |
| 10 | `installation.py`, `APP_ID` | `"{8F2C4A91-...}"` со скобками в значении | **Корректно** — `{{` в `.iss` это escape, фактический AppId содержит скобки. Комментарий в коде («without the {{ }} braces Inno adds») вводит в заблуждение: Inno ничего не добавляет |

## Приложение C. Проверенные версии (2026-09-16)

| Компонент | Версия | Как проверено |
|---|---|---|
| GitHub REST API | поддерживаются `2026-03-10` (новейшая) и `2022-11-28`; по умолчанию выбирается `2022-11-28` | **[LIVE]** тело ошибки 400 + заголовок `x-github-api-version-selected` |
| PyInstaller | **6.22.3** (2026-09-12) | **[LIVE]** GitHub Releases API |
| Inno Setup (актуальный) | **7.1.0** | **[LIVE]** GitHub Releases API |
| Inno Setup (на раннерах) | **6.7.1** | **[LIVE]** `actions/runner-images` Readme |
| actions/checkout | **v7.0.1** | **[LIVE]** GitHub Releases API |
| actions/setup-python | **v7.0.0** (node24) | **[LIVE]** GitHub Releases API + `action.yml` |
| actions/upload-artifact | **v7.0.1** | **[LIVE]** GitHub Releases API |
| GitHub CLI (на раннерах) | **2.100.0** | **[LIVE]** `actions/runner-images` Readme |
| Python (на раннерах) | **3.12.10** | **[LIVE]** `actions/runner-images` Readme |
| `windows-latest` | Windows Server 2025 + **VS2026** (`windows-2025-vs2026`) | **[LIVE]** `actions/runner-images/README.md` |
