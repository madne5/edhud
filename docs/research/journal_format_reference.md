# Elite Dangerous Player Journal — точный справочник по формату

Составлено по официальному документу Frontier **"Elite Dangerous Player Journal Manual" v37** (полный текст PDF:
`doc/journal/Journal_Manual_v37.pdf` в репозитории [kayahr/ed-journal](https://github.com/kayahr/ed-journal)),
схемам [EDCD/EDDN](https://github.com/EDCD/EDDN), типизированным моделям
[kayahr/ed-journal](https://github.com/kayahr/ed-journal) (TypeScript), [Observatory Framework](https://git.quartznet.info/quartznet/pulsar),
[EDCD/EDDI](https://github.com/EDCD/EDDI) (реальные примеры строк журнала в `SAMPLE`),
[rster2002/ed-logs](https://github.com/rster2002/ed-logs) (Rust, только live 4.x) и [EDCD/EDMarketConnector](https://github.com/EDCD/EDMarketConnector).
Всё, что не подтверждено минимум одним из этих источников, помечено явно **«не подтверждено»**.

---

## 0. Общие правила формата

| Свойство | Значение |
|---|---|
| Формат файла | Line-delimited JSON (JSON Lines): один JSON-объект на строку, LF, UTF-8 |
| Общие поля каждого события | `timestamp` (string), `event` (string) |
| `timestamp` | ISO 8601, **GMT/UTC**, всегда с суффиксом `Z`, секундная точность, без миллисекунд: `"2022-11-21T15:04:36Z"` (Manual §2.2, §2.3) |
| Локализация | Внутренние символы игры вида `$symbolname;` дублируются ключом с суффиксом `_Localised` (UTF-8). Если локализованная строка совпадает с исходной — ключ `_Localised` **не пишется** (Manual §2.4) |
| ID-поля | `SystemAddress`, `MarketID`, `CarrierID`, `BodyID`, `EntryID`, `ShipID`, `FID` — целые uint64. В JS/JSON.parse числа > `Number.MAX_SAFE_INTEGER` (9007199254740991) теряют точность → читать как BigInt/строку |
| Исключение из формата времени | `CarrierDecommission.ScrapTime` — Unix-epoch в секундах (`1584601200`), а не ISO (Manual §11.5) |
| Один файл = одна игровая сессия | см. §12 |

---

## 1. `Fileheader` — заголовок файла (первое событие каждого файла)

Точные имена ключей (регистр важен). Manual §2.2 называет поле `odyssey` строчными буквами, но **в реальных
журналах ключ пишется с заглавной — `Odyssey`** (подтверждено EDPlayerJournal, kayahr, ed-journals).

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `timestamp` | string ISO | да | Время создания файла |
| `event` | string | да | `"Fileheader"` (в Manual-примере ошибочно `"fileheader"` строчными — в реальных журналах `"Fileheader"`) |
| `part` | int | да | Номер части файла, начинается с 1; растёт при ротации |
| `language` | string | да | Код языка, напр. `"English/UK"` (в старых журналах — `"English\UK"` с обратным слэшем) |
| `Odyssey` | bool | опц. | `true` для 4.x (Odyssey/live). **Отсутствует** в legacy 3.x |
| `gameversion` | string | да | `"4.0.0.1450"` (live) или `"3.5.3.400 EDH"` (legacy Horizons); может содержать признак beta |
| `build` | string | да | Номер сборки, напр. `"r286858/r0 "` — **с завершающим пробелом** (баг Frontier) |

Реальные примеры (тесты [EDPlayerJournal](https://git.aror.org/florian/EDPlayerJournal)):

```json
{ "timestamp":"2022-11-21T15:04:36Z", "event":"Fileheader", "part":1, "language":"English/UK", "Odyssey":true, "gameversion":"4.0.0.1450", "build":"r286858/r0 " }
{ "timestamp":"2020-01-02T23:45:23Z", "event":"Fileheader", "part":1, "language":"English\\UK", "gameversion":"3.5.3.400 EDH", "build":"r213094/r0 " }
```

Практика: `Odyssey`: отсутствует/false → legacy 3.8 (`gameversion` начинается с `"3."`); true → live 4.x. Это
штатный способ определять поколение журнала. `Fileheader` присутствует в **каждом** файле журнала, а не только
в первом за сессию (Manual §2.2).

---

## 2. `LoadGame`, `Location`, `FSDJump`, `CarrierJump`

### 2.1 `LoadGame` — вход в игру из главного меню (Manual §3.8)

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `Commander` | string | да | Имя командира |
| `FID` | string | опц. | Player ID (с декабря 2018) |
| `Horizons` | bool | опц. | Есть Horizons |
| `Odyssey` | bool | опц. | Есть Odyssey |
| `Ship` / `ShipID` | string / uint | опц. | Текущий корабль и его id (нет при полёте в Apex Shuttle) |
| `Ship_Localised` | string | опц. | Не всегда присутствует |
| `ShipName` / `ShipIdent` | string | опц. | Пользовательское имя/бортовой номер |
| `StartLanded` / `StartDead` | bool | опц. | Пишутся только если `true` |
| `GameMode` | string | опц. | `"Open"` \| `"Solo"` \| `"Group"` (иногда отсутствует) |
| `Group` | string | опц. | Только для режима Group |
| `Credits` / `Loan` | long | да | Баланс и ссуда |
| `FuelLevel` / `FuelCapacity` | float | опц. | Топливо и объём бака |
| `language` / `gameversion` / `build` | string | опц. | С Odyssey Update 5 (июль 2021) |

### 2.2 `Location` — при старте или возрождении (Manual §4.12)

| Поле | Тип | Описание |
|---|---|---|
| `StarSystem` | string | Имя системы |
| `SystemAddress` | uint64 | ID системы |
| `StarPos` | `[number,number,number]` | Координаты x,y,z в св. годах |
| `Body` / `Body_Localised` | string | Тело (звезда/планета) |
| `BodyID` | int | ID тела внутри системы |
| `BodyType` | string | `Planet` \| `Star` \| `Station` \| `PlanetaryRing` \| `AsteroidCluster` \| `Null` \| `StellarRing` \| `Ring` |
| `DistFromStarLS` | float | Расстояние до звезды прибытия, св. секунды (нет, если рядом) |
| `Docked` | bool | Пристыкован |
| `Latitude` / `Longitude` | float | Если на поверхности |
| `StationName` / `StationType` / `MarketID` | string / string / uint64 | Если пристыкован |
| `SystemFaction` | object `{Name, FactionState}` | Контролирующая фракция |
| `SystemAllegiance` | string | `Federation` \| `Empire` \| `Alliance` \| `Independent` \| `PilotsFederation` \| `None` |
| `SystemEconomy`, `SystemSecondEconomy`, `SystemGovernment`, `SystemSecurity` | string (+`_Localised`) | Экономика/правительство/безопасность |
| `Population` | long | Население |
| `Wanted` | bool | — |
| `Factions` | array of `{Name, FactionState, Government, Influence, Allegiance, Happiness(_Localised), MyReputation, PendingStates[], RecoveringStates[], ActiveStates[], SquadronFaction}` | Локальные фракции |
| `Conflicts` | array of `{WarType, Status, Faction1{Name,Stake,WonDays}, Faction2{...}}` | Конфликты |
| `Powers` | string[] | Влияющие силы |
| `PowerplayState` | string | `InPrepareRadius` \| `Prepared` \| `Exploited` \| `Contested` \| `Controlled` \| `Turmoil` \| `HomeSystem` |
| `StationFaction`, `StationGovernment(+_L)`, `StationAllegiance`, `StationServices[]`, `StationEconomies[]`, `StationEconomy(+_L)` | — | Только если стартуешь на станции |
| `ThargoidWar` | object `{CurrentState, NextStateSuccess, NextStateFailure, SuccessStateReached, WarProgress, RemainingPorts, EstimatedRemainingTime}` | Если система затронута войной |
| `Taxi`, `Multicrew`, `InSRV`, `OnFoot` | bool | Odyssey |
| `ControllingPower` | string | — |

### 2.3 `FSDJump` — прыжок между системами (Manual §4.8)

Ключи: `StarSystem` (string), `SystemAddress` (uint64), `StarPos` `[x,y,z]` (number[]), `Body` (string, имя звезды),
`BodyID` (int), `BodyType` (string), `JumpDist` (float, св. лет), `FuelUsed` (float), `FuelLevel` (float),
`BoostUsed` (int, 1 если использован буст FSD), `SystemFaction {Name, FactionState}`, `SystemAllegiance`,
`SystemEconomy(+_Localised)`, `SystemSecondEconomy(+_Localised)`, `SystemGovernment(+_Localised)`,
`SystemSecurity(+_Localised)`, `Population` (long), `Wanted` (bool), `Factions[]`, `Conflicts[]`, `Powers[]`,
`PowerplayState` (+ `PowerplayStateControlProgress/Reinforcement/Undermining`, `PowerplayConflictProgress[]`),
`ThargoidWar{}`, `ControllingPower`, `Taxi`, `Multicrew`.

Пример (Manual §4.8, сокращён):

```json
{ "timestamp":"2018-10-29T10:05:21Z", "event":"FSDJump", "StarSystem":"Eranin", "SystemAddress":2832631632594, "StarPos":[-22.84375,36.53125,-1.18750], "SystemAllegiance":"Independent", "SystemEconomy":"$economy_Agri;", "SystemEconomy_Localised":"Agriculture", "SystemGovernment":"$government_Anarchy;", "SystemGovernment_Localised":"Anarchy", "SystemSecurity":"$GAlAXY_MAP_INFO_state_anarchy;", "SystemSecurity_Localised":"Anarchy", "Population":450000, "JumpDist":13.334, "FuelUsed":0.000000, "FuelLevel":25.630281, "SystemFaction":{ "Name":"Mob of Eranin", "FactionState":"CivilLiberty" } }
```

Важно: в `FSDJump` **нет** `Docked`, `Latitude`, `Longitude`, `StationName`, `StationType`.
В старых журналах (до v3.x) ключи были без префикса: `Faction`, `Government`, `Economy`, `Security`, `Allegiance`,
а `SystemFaction` был строкой — библиотеки обязаны конвертировать (kayahr).

### 2.4 `CarrierJump` — прыжок носителя, пока игрок на нём (Manual §11.1)

«Аналогичен FSDJump и Location, но пишется, если игрок онлайн и пристыкован к носителю в момент прыжка.
**Не содержит** расстояния прыжка и потраченного топлива.»

Ключи: `Docked` (bool), `OnFoot` (bool, опц.), `StationName`, `StationType`, `MarketID`, `StationFaction{Name}`,
`StationGovernment(+_Localised)`, `StationServices[]`, `StationEconomy(+_Localised)`, `StationEconomies[]`,
`Conflicts[]`, `Powers[]`, `PowerplayState`+…, `Taxi`, `Multicrew`, `StarSystem`, `SystemAddress`, `StarPos`,
`SystemAllegiance`, `SystemEconomy(+_Localised)`, `SystemSecondEconomy(+_Localised)`, `SystemGovernment(+_Localised)`,
`SystemSecurity(+_Localised)`, `Population`, `Body`, `BodyID`, `BodyType`, `ControllingPower`, `Factions[]`,
`SystemFaction{Name, FactionState}`.

```json
{ "timestamp":"2020-03-25T15:55:56Z", "event":"CarrierJump", "Docked":true, "StationName":"FC L14X1J", "StationType":"FleetCarrier", "MarketID":3700005632, "StarSystem":"Hermitage", "SystemAddress":5363877956440, "StarPos":[-28.75000,25.00000,10.43750], "SystemAllegiance":"", "SystemEconomy":"$economy_None;", "SystemEconomy_Localised":"None", "SystemGovernment":"$government_None;", "SystemGovernment_Localised":"None", "SystemSecurity":"$GAlAXY_MAP_INFO_state_anarchy;", "SystemSecurity_Localised":"Anarchy", "Population":0, "Body":"Hermitage", "BodyID":0, "BodyType":"Star", "SystemFaction":{ "Name":"FleetCarrier" } }
```

---

## 3. `FSSDiscoveryScan` — «хонк» (Manual §6.6)

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `Progress` | number (float, 0..1) | да | Насколько полно просканирована система (в журнале пишется как `0.824540`) |
| `BodyCount` | int | да | Число тел в системе |
| `NonBodyCount` | int | да | Число не-телесных сигналов |
| `SystemName` | string | **опц.** | **Не перечислено в Manual v37**; есть в реальных журналах 4.x. В старых (3.x) событиях может отсутствовать |
| `SystemAddress` | uint64 | **опц.** | То же |

Реальный пример ([EDDI `FSSDiscoveryScanEvent`](https://github.com/EDCD/EDDI/blob/develop/Events/FSSDiscoveryScanEvent.cs)) — **без** SystemName/SystemAddress:

```json
{ "timestamp":"2018-11-04T23:44:36Z", "event":"FSSDiscoveryScan", "Progress":0.824540, "BodyCount":4, "NonBodyCount":8 }
```

По ed-journals (модель для live 4.x) `SystemName`/`SystemAddress` — обязательные; по kayahr — опциональные.
`StarPos` в этом событии **не пишется** — EDDN требует, чтобы отправитель добавлял его сам из последнего
`Location`/`FSDJump`/`CarrierJump`.

---

## 4. `FSSAllBodiesFound` — все тела системы найдены (Manual §6.4)

| Поле | Тип | Обяз. |
|---|---|---|
| `SystemName` | string | да |
| `SystemAddress` | uint64 | да |
| `Count` | int | да (число тел в системе) |

```json
{ "timestamp":"2019-03-10T16:09:36Z", "event":"FSSAllBodiesFound", "SystemName":"Dumbae DN-I d10-6057", "SystemAddress":208127228285531, "Count":19 }
```

---

## 5. `FSSSignalDiscovered` — сигнал, найденный в FSS (Manual §6.7)

Одно событие = **один** сигнал (не массив). Массив `signals` — конструкция EDDN-схемы, в журнале её нет.

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `SignalName` | string | да | Внутреннее имя, напр. `"$USS;"`, `"$USS_PowerConvoy;"`, `"$MULTIPLAYER_SCENARIO42_TITLE;"` |
| `SignalName_Localised` | string | опц. | Локализованное имя сигнала |
| `SignalType` | string | опц. | Тип. **Не перечислен в Manual v37**; есть в kayahr/EDDN. Значения (kayahr): `Outpost`, `StationCoriolis`, `FleetCarrier`, `StationONeilOrbis`, `NavBeacon`, `Megaship`, `Combat`, `Installation`, `StationONeilCylinder`, `Generic`, `ResourceExtraction`, `StationBernalSphere`, `TouristBeacon`, `Titan`, `StationMegaShip`, `USS`, `Codex`, `StationAsteroid`, `SquadronCarrier`, `StationDodec` |
| `SpawningState` | string | опц. | BGS-состояние, вызвавшее сигнал |
| `SpawningState_Localised` | string | опц. | — |
| `SpawningFaction` / `SpawningFaction_Localised` | string | опц. | Фракция |
| `TimeRemaining` | float (сек) | опц. | Сколько сигнал ещё проживёт (в основном для USS), напр. `1519.981689` |
| `SystemAddress` | uint64 | да | ID системы |
| `ThreatLevel` | int | опц. | Уровень угрозы (USS) |
| `USSType` / `USSType_Localised` | string | опц. | Тип USS (`$USS_Type_Salvage;`, `$USS_Type_PowerEmissions;`, …) |
| `SpawningPower` / `OpposingPower` | string | опц. | Силы (новые типы USS) |
| `IsStation` | bool | опц. | `true` для станции |

Реальные примеры ([EDDI `SignalDetectedEvent`](https://github.com/EDCD/EDDI/blob/develop/Events/SignalDetectedEvent.cs)):

```json
{ "timestamp":"2018-11-22T06:21:00Z", "event":"FSSSignalDiscovered", "SystemAddress":58132919110424, "SignalName":"$USS;", "SignalName_Localised":"Unidentified signal source", "USSType":"$USS_Type_Salvage;", "USSType_Localised":"Degraded emissions", "SpawningState":"$FactionState_None;", "SpawningState_Localised":"None", "SpawningFaction":"$faction_none;", "SpawningFaction_Localised":"None", "ThreatLevel":0, "TimeRemaining":1519.981689 }
{ "timestamp":"2024-10-31T19:28:41Z", "event":"FSSSignalDiscovered", "SystemAddress":908620468962, "SignalName":"$USS_PowerEmissions;", "SignalName_Localised":"Unidentified signal source", "SignalType":"USS", "USSType":"$USS_Type_PowerEmissions;", "USSType_Localised":"Power Wreckage Signature", "SpawningPower":"Nakato Kaine", "OpposingPower":"Aisling Duval", "ThreatLevel":3, "TimeRemaining":1278.169189 }
```

Практика (EDDN `fsssignaldiscovered-README.md`): в Horizon 3.8 события идут после `Location`/`FSDJump`/`CarrierJump`,
в Odyssey 4.0 — **до** них, поэтому систему нужно брать из «только что прибыл» события. `TimeRemaining` EDDN
запрещает пересылать (PII/эфемерность), события с `USSType == "$USS_Type_MissionTarget;"` — отбрасывать.

---

## 6. `SAASignalsFound` — поверхностное сканирование (Manual §6.15) ⭐

Точная структура (подтверждено manual v37, kayahr, Observatory, EDDI, EDMC-BioScan):

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `SystemAddress` | uint64 | да | ID системы |
| `BodyName` | string | да | Имя тела (для колец — `"... 4 A Ring"`) |
| `BodyID` | int | да | ID тела |
| `Signals` | array of object | да | Найденные сигналы |
| `Signals[].Type` | string | да | Внутренний тип: `"$SAA_SignalType_Biological;"`, `"$SAA_SignalType_Geological;"`, `"$SAA_SignalType_Human;"`, `"$PlanetaryMiningLocation_Name;"`, либо имя минерала (`"LowTemperatureDiamond"`, `"Alexandrite"`) |
| `Signals[].Type_Localised` | string | опц. | `"Biological"`, `"Geological"`, `"Human"`, `"Low Temperature Diamonds"`, … (может отсутствовать, если совпадает) |
| `Signals[].Count` | int | да | Количество сигналов данного типа |
| `Genuses` | array of object | **опц.** | Роды биологии на теле. Добавлено в **Odyssey Update 13 (июль 2022)** — Manual v35: «Extended the SAASignalsFound event to include the genuses on the scanned planet». Может быть пустым массивом `[]` |
| `Genuses[].Genus` | string | да | Напр. `"$Codex_Ent_Bacterial_Genus_Name;"` |
| `Genuses[].Genus_Localised` | string | да | Напр. `"Bacterium"` |

### Про `Species` / `Species_Localised` в `Genuses` — НЕТ

Поля `Species`/`Species_Localised` внутри `Genuses` **не подтверждены**: их нет ни в Manual v37 (перечислен
только `Genus`), ни в реальных примерах EDDI, ни в моделях kayahr (`Genuses?: Array<{Genus, Genus_Localised}>`),
ни в Observatory (`class GenusType { Genus; Genus_Localised; }`). Вид на момент SAA-скана игре неизвестен —
`Genus`/`Species`/`Variant` появляются только в событии `ScanOrganic` после взятия образца.
Соответствие «сколько сигналов у какого рода» из журнала **не выводится однозначно** — **не подтверждено**.

### Реальные примеры

Manual v37 (три официальных примера, включая кольцо и биологию с `Genuses`):

```json
{ "timestamp":"2019-04-17T13:38:18Z", "event":"SAASignalsFound", "BodyName":"Hermitage 4 A Ring", "SystemAddress":5363877956440, "BodyID":11, "Signals":[ { "Type":"LowTemperatureDiamond", "Type_Localised":"Low Temperature Diamonds", "Count":1 }, { "Type":"Alexandrite", "Count":1 } ] }
{ "timestamp":"2022-07-01T09:14:32Z", "event":"SAASignalsFound", "BodyName":"Asellus 3a", "SystemAddress":1144348739947, "BodyID":10, "Signals":[ { "Type":"$SAA_SignalType_Biological;", "Type_Localised":"Biological", "Count":2 }, { "Type":"$SAA_SignalType_Geological;", "Type_Localised":"Geological", "Count":3 }, { "Type":"$SAA_SignalType_Human;", "Type_Localised":"Human", "Count":8 } ], "Genuses":[ { "Genus":"$Codex_Ent_Bacterial_Genus_Name;", "Genus_Localised":"Bacterium" }, { "Genus":"$Codex_Ent_Stratum_Genus_Name;", "Genus_Localised":"Stratum" } ] }
```

EDDI `SurfaceSignalsEvent` (реальные строки журнала; обратите внимание на пустой `Genuses`, на новый тип
`$PlanetaryMiningLocation_Name;` и на количество биосигналов):

```json
{ "timestamp":"2025-05-26T05:23:29Z", "event":"SAASignalsFound", "BodyName":"Col 69 Sector TP-E c12-4 B 11", "SystemAddress":1184102126066, "BodyID":25, "Signals":[ { "Type":"$SAA_SignalType_Biological;", "Type_Localised":"Biological", "Count":1 } ], "Genuses":[ { "Genus":"$Codex_Ent_Bacterial_Genus_Name;", "Genus_Localised":"Bacterium" } ] }
{ "timestamp":"2022-12-08T04:32:21Z", "event":"SAASignalsFound", "BodyName":"Gurabru 4 a", "SystemAddress":2553098013019, "BodyID":18, "Signals":[ { "Type":"$SAA_SignalType_Biological;", "Type_Localised":"Biological", "Count":8 } ], "Genuses":[ { "Genus":"$Codex_Ent_Bacterial_Genus_Name;", "Genus_Localised":"Bacterium" }, { "Genus":"$Codex_Ent_Cactoid_Genus_Name;", "Genus_Localised":"Cactoida" }, { "Genus":"$Codex_Ent_Clypeus_Genus_Name;", "Genus_Localised":"Clypeus" }, { "Genus":"$Codex_Ent_Conchas_Genus_Name;", "Genus_Localised":"Concha" }, { "Genus":"$Codex_Ent_Fungoids_Genus_Name;", "Genus_Localised":"Fungoida" }, { "Genus":"$Codex_Ent_Osseus_Genus_Name;", "Genus_Localised":"Osseus" }, { "Genus":"$Codex_Ent_Shrubs_Genus_Name;", "Genus_Localised":"Frutexa" }, { "Genus":"$Codex_Ent_Tussocks_Genus_Name;", "Genus_Localised":"Tussock" } ] }
{ "timestamp":"2026-08-30T01:56:01Z", "event":"SAASignalsFound", "BodyName":"Shinrarta Dezhra AB 3 c", "SystemAddress":3932277478106, "BodyID":61, "Signals":[ { "Type":"$SAA_SignalType_Geological;", "Type_Localised":"Geological", "Count":2 }, { "Type":"$PlanetaryMiningLocation_Name;", "Type_Localised":"Planetary Mining Location", "Count":18 }, { "Type":"$SAA_SignalType_Human;", "Type_Localised":"Human", "Count":1 } ], "Genuses":[  ] }
```

### 6.1 `FSSBodySignals` — тот же смысл, но во время FSS-скана (Manual §6.5)

«Пишется при завершении полного сканирования системы, перечисляя число SAA-сигналов в системе (как в верхней
правой панели игры)». Поля: `BodyName` (string), `BodyID` (int), `SystemAddress` (uint64),
`Signals[]` (array of `{Type, Type_Localised, Count}`). `Genuses` в этом событии **нет**.
EDMC-BioScan регистрирует оба события (`'FSSBodySignals' | 'SAASignalsFound'`) как источник данных о
биосигналах тела (см. `research/EDMC-BioScan/src/load.py:1169`).

```json
{ "timestamp":"2022-03-17T18:20:53Z", "event":"FSSBodySignals", "BodyName":"Phroi Blou EW-W d1-1056 2 a", "BodyID":18, "SystemAddress":36293555558035, "Signals":[ { "Type":"$SAA_SignalType_Geological;", "Type_Localised":"Geological", "Count":3 } ] }
```

---

## 7. `Scan` — детальный/базовый скан тела (Manual §6.3)

`Scan` — объединение трёх вариантов: звезда (`StarType`), планета/луна (`PlanetClass`), прочее. Определять по
наличию ключа `StarType` / `PlanetClass`.

### 7.1 Общие поля (`ScanBody`)

| Поле | Тип | Описание |
|---|---|---|
| `ScanType` | string | `AutoScan` \| `Basic` \| `Detailed` \| `NavBeaconDetail` (в старых журналах может отсутствовать) |
| `StarSystem` | string | В старых журналах может отсутствовать — брать из предыдущего `FSDJump` |
| `SystemAddress` | uint64 | Может отсутствовать в старых журналах |
| `BodyName` | string | Имя тела |
| `BodyID` | int | ID тела |
| `DistanceFromArrivalLS` | float | Расстояние до звезды прибытия в св. секундах |
| `WasDiscovered` | bool | Уже открыто кем-то (нет в базовом скане) |
| `WasMapped` | bool | Уже картировано |
| `WasFootfalled` | bool | Есть в kayahr/ed-journal; **в Manual v37 не указано — не подтверждено официально** |
| `Parents` | array of object | Иерархия: `[{"Star":2},{"Planet":11}]` и т.п. (BodyType → BodyID) |
| `SemiMajorAxis`, `Eccentricity`, `OrbitalInclination`, `Periapsis`, `OrbitalPeriod`, `AscendingNode`, `MeanAnomaly` | float | Орбитальные параметры |
| `Rings` | array of `{Name, RingClass, MassMT, InnerRad, OuterRad}` | Кольца |

### 7.2 Звезда (`ScanStar`)

`StarType` (string, enum: `O B A F G K M L T Y TTS AeBe W C S MS N H D DA DAB DAV DAZ DB DBV DC DCV DQ A_BlueWhiteSuperGiant
B_BlueWhiteSuperGiant F_WhiteSuperGiant G_WhiteSuperGiant K_OrangeGiant M_RedGiant M_RedSuperGiant SupermassiveBlackHole` … —
набор по kayahr `StarType.ts`), `Subclass` (int 0..9), `StellarMass` (float, массы Солнца), `Radius` (float, м),
`AbsoluteMagnitude` (float), `RotationPeriod` (float, сек), `SurfaceTemperature` (float, K), `Luminosity` (string),
`Age_MY` (int, млн лет).

### 7.3 Планета/луна (`ScanPlanet`) — ключевое для экзобиологии

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `PlanetClass` | string | да | `Ammonia world`, `Earthlike body`, `Gas giant with ammonia based life`, `Gas giant with water based life`, `Helium rich gas giant`, `High metal content body`, `Icy body`, `Metal rich body`, `Rocky ice body`, `Rocky body`, `Sudarsky class I..V gas giant`, `Water giant`, `Water world` |
| `MassEM` | float | да | Масса в массах Земли |
| `Radius` | float | да | Радиус в метрах |
| `SurfaceGravity` | float | да | Гравитация, м/с² |
| `SurfaceTemperature` | float | опц. | Температура, K (нет при базовом скане) |
| `SurfacePressure` | float | опц. | Давление, кПа (нет при базовом скане) |
| `Landable` | bool | опц. | Можно ли приземлиться (нет при базовом скане) |
| `TerraformState` | string | опц. | `Terraformable` \| `Terraforming` \| `Terraformed` \| отсутствует/null |
| `Atmosphere` | string | опц. | Внутреннее имя, напр. `"thin carbon dioxide"`; пустая строка, если нет |
| `AtmosphereType` | string | опц. | Напр. `"CarbonDioxide"`, `"Ammonia"`, `"None"` |
| `AtmosphereComposition` | array `[{Name, Percent}]` | опц. | Состав атмосферы |
| `Volcanism` | string | опц. | Напр. `"minor nitrogen magma volcanism"`; пустая строка, если нет |
| `Materials` | array `[{Name, Percent}]` | опц. | (В очень старых журналах был объект `{name: percent}` — kayahr конвертирует) |
| `Composition` | object `{Ice, Metal, Rock}` | опц. | Состав (проценты) |
| `ReserveLevel` | string | опц. | `PristineResources` \| `MajorResources` \| `CommonResources` \| `LowResources` \| `DepletedResources` |
| `TidalLock` | bool | опц. | Приливный захват |
| `RotationPeriod`, `AxialTilt` | float | опц. | Если вращается |
| `Rings` | array | опц. | Если есть кольца |

### 7.4 Есть ли в `Scan` количество биосигналов? — **НЕТ**

Поля `BioSignals` (или `SAA`, `BiologicalSignals`, `Genuses`) в `Scan` **не подтверждены нигде**: их нет
в списке параметров Manual v37 (§6.3, включая отдельный перечень для планет), нет в kayahr `ScanPlanet`,
нет в EDDN (`scan-valid.json`), нет в модели ed-journals, нет в `EDMC-BioScan`/EDMC (`bio_signals` в плагине
считается по событиям `SAASignalsFound`/`FSSBodySignals`, а не по `Scan`).

**Откуда брать биосигналы:**

* количество биосигналов на теле → `SAASignalsFound.Signals[]`, элемент с `Type == "$SAA_SignalType_Biological;"`, поле `Count`
  (либо `FSSBodySignals` в той же форме);
* роды на теле → `SAASignalsFound.Genuses[]` (`Genus`, `Genus_Localised`), только 4.x / Update 13+;
* род/вид/вариант конкретного образца → `ScanOrganic` (`Genus`, `Species`, `Variant` + `_Localised`);
* денежная стоимость проданных образцов → `SellOrganicData.BioData[]` (`Value`, `Bonus`);
* кодекс-записи о биологии → `CodexEntry` с `Category == "$Codex_Category_Biology;"`.

Для предсказания доступных видов ed-exobiology использует из `Scan` именно:
`Landable`, `PlanetClass`, `Atmosphere`, `SurfaceGravity`, `SurfaceTemperature`, `SurfacePressure`, `Volcanism`,
`Materials`, `Composition`, `Parents`, `SemiMajorAxis` + признак наличия геологических сигналов
(см. `ed-exobiology/src/modules/exobiology/models/spawn_source/target_planet.rs`).

### 7.5 `ScanOrganic` (Manual §12.22) и `SellOrganicData` (Manual §12.24)

```json
{ "timestamp":"2022-12-07T14:27:55Z", "event":"ScanOrganic", "ScanType":"Analyse", "Genus":"$Codex_Ent_Tubus_Genus_Name;", "Genus_Localised":"Tubus", "Species":"$Codex_Ent_Tubus_01_Name;", "Species_Localised":"Tubus Conifer", "Variant":"$Codex_Ent_Tubus_01_A_Name;", "Variant_Localised":"Tubus Conifer - Indigo", "SystemAddress":316174882163, "Body":44 }
{ "timestamp":"2022-12-07T14:44:28Z", "event":"SellOrganicData", "MarketID":128001536, "BioData":[ { "Genus":"$Codex_Ent_Tubus_Genus_Name;", "Genus_Localised":"Tubus", "Species":"$Codex_Ent_Tubus_01_Name;", "Species_Localised":"Tubus Conifer", "Variant":"$Codex_Ent_Tubus_01_A_Name;", "Variant_Localised":"Tubus Conifer - Indigo", "Value":2415500, "Bonus":9662000 } ] }
```

`ScanOrganic`: `ScanType` (`Log` → `Sample` → `Analyse`, Manual перечисляет как `Log,, Sample, Analyse`),
`Genus`, `Species`, `Variant` (+`_Localised`), `SystemAddress`, `Body` (это **BodyID**, не имя; с Odyssey Update 14
добавлен ещё и `WasLogged` — есть в EDMC-BioScan, в Manual v37 как параметр не указан → не подтверждено официально).
`SellOrganicData`: `MarketID`, `BioData[]` из `{Genus, Species, Variant, Value, Bonus}` (+`_Localised`).

---

## 8. `CodexEntry` — запись в кодексе (Manual §6.1)

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `EntryID` | uint64 | да | ID записи кодекса |
| `Name` | string | да | Внутреннее имя, напр. `"$Codex_Ent_Shrubs_05_F_Name;"`, `"$Codex_Ent_IceFumarole_CarbonDioxideGeysers_Name;"` |
| `Name_Localised` | string | опц. | Напр. `"Frutexa Fera - Green"` |
| `Category` | string | да | `"$Codex_Category_Biology;"` (биология **и** геология/аномалии), `"$Codex_Category_StellarBodies;"`, `"$Codex_Category_Civilisations;"` |
| `Category_Localised` | string | опц. | `"Biological and Geological"` |
| `SubCategory` | string | да | `"$Codex_SubCategory_Organic_Structures;"` (организмы), `"$Codex_SubCategory_Geology_and_Anomalies;"`, `"$Codex_SubCategory_Gas_Giants;"`, `"$Codex_SubCategory_Guardian;"`, `"$Codex_SubCategory_Thargoid;"` |
| `SubCategory_Localised` | string | опц. | `"Organic structures"` |
| `Region` | string | да | `"$Codex_RegionName_18;"` (номер региона) |
| `Region_Localised` | string | опц. | `"Inner Orion Spur"` |
| `System` | string | да | Имя системы (**не** `StarSystem`!) |
| `SystemAddress` | uint64 | да | ID системы |
| `BodyID` | int | опц. | Добавлено в Odyssey Update 12 (Manual v34: «CodexEntry: add BodyID»). **`BodyName` в журнале нет** — EDDN требует восстанавливать имя тела из `ApproachBody` |
| `NearestDestination` | string | опц. | Если в пределах 50 км от объекта из навигационной панели: `"$SAA_Unknown_Signal:#type=$SAA_SignalType_Geological;:#index=9;"`, `"Biological Site"`, `"$Ancient:#index=1;"` |
| `NearestDestination_Localised` | string | опц. | `"Surface signal: Geological (9)"` |
| `Latitude` / `Longitude` | float | опц. | Координаты |
| `IsNewEntry` | bool | опц. | Новая запись (в EDDI трактуется как «новая в текущем регионе») |
| `NewTraitsDiscovered` | bool | опц. | Обнаружены новые traits |
| `Traits` | string[] | опц. | Только для записей с «traits» (напр. `["o_l_turn01_idle"]`) |
| `VoucherAmount` | int | опц. | Вознаграждение-ваучер за запись кодекса, если начислено |

### `Reward` vs `VoucherAmount` для биологических записей

* Поля **`Reward` в `CodexEntry` нет** — оно отсутствует в Manual v37 (§6.1), в EDDN-схеме `codexentry-v1.0`
  (там только `VoucherAmount`), в kayahr `CodexEntry`, в Observatory `CodexEntry` и в EDDI `CodexEntryEvent`
  (там есть только `voucherAmount`, комментарий: «The credit voucher amount awarded for the discovery, if any»).
  Ключевое слово `Reward` в Manual встречается только в других событиях (`Bounty`, `FactionKillBond`,
  `MissionAccepted/Completed`, `DatalinkVoucher`, `RedeemVoucher`) — **`Reward` в `CodexEntry`: не подтверждено**.
* `VoucherAmount` — разовое вознаграждение-ваучер за саму кодекс-запись (обычно `50000`), а **не** стоимость
  образца. Оплата за экзобиологию приходит через `SellOrganicData` (`Value` + `Bonus`).
* Поле опционально и часто отсутствует даже при `IsNewEntry: true` (см. первый пример ниже — Frutexa Fera - Green
  без `VoucherAmount`).

Реальные примеры ([EDDI `CodexEntryEvent.SAMPLES`](https://github.com/EDCD/EDDI/blob/develop/Events/CodexEntryEvent.cs)):

```json
{ "timestamp":"2026-01-17T09:09:12Z", "event":"CodexEntry", "EntryID":2460101, "Name":"$Codex_Ent_Ingensradices_Unicus_Name;", "Name_Localised":"Radicoida Unica", "SubCategory":"$Codex_SubCategory_Organic_Structures;", "SubCategory_Localised":"Organic structures", "Category":"$Codex_Category_Biology;", "Category_Localised":"Biological and Geological", "Region":"$Codex_RegionName_18;", "Region_Localised":"Inner Orion Spur", "System":"HIP 87621", "SystemAddress":147882789259, "BodyID":1, "NearestDestination":"Biological Site", "Latitude":-22.478512, "Longitude":-5.011441, "IsNewEntry":true, "VoucherAmount":50000 }
{ "timestamp":"2023-07-22T04:10:26Z", "event":"CodexEntry", "EntryID":2440503, "Name":"$Codex_Ent_Shrubs_05_F_Name;", "Name_Localised":"Frutexa Fera - Green", "SubCategory":"$Codex_SubCategory_Organic_Structures;", "SubCategory_Localised":"Organic structures", "Category":"$Codex_Category_Biology;", "Category_Localised":"Biological and Geological", "Region":"$Codex_RegionName_5;", "Region_Localised":"Norma Arm", "System":"Greae Phio FO-G d11-1005", "SystemAddress":34542299533283, "BodyID":42, "Latitude":-45.382187, "Longitude":173.182938, "IsNewEntry":true }
{ "timestamp":"2019-07-02T03:02:31Z", "event":"CodexEntry", "EntryID":2301801, "Name":"$Codex_Ent_L_Org_Moll03_V3_Def_Name;", "Name_Localised":"Luteolum Umbrella Mollusc", "SubCategory":"$Codex_SubCategory_Organic_Structures;", "Category":"$Codex_Category_Biology;", "Region":"$Codex_RegionName_9;", "System":"Canonnia", "SystemAddress":13603220441236, "Traits":[ "o_l_turn01_idle" ], "NewTraitsDiscovered":true }
```

Официальный пример Manual v37 (геология/аномалия, но с `VoucherAmount: 50000` и `NearestDestination`):

```json
{ "timestamp":"2019-05-13T13:28:51Z", "event":"CodexEntry", "EntryID":1400159, "Name":"$Codex_Ent_IceFumarole_CarbonDioxideGeysers_Name;", "Name_Localised":"Carbon Dioxide Ice Fumarole", "SubCategory":"$Codex_SubCategory_Geology_and_Anomalies;", "SubCategory_Localised":"Geology and anomalies", "Category":"$Codex_Category_Biology;", "Category_Localised":"Biological and Geological", "Region":"$Codex_RegionName_18;", "Region_Localised":"Inner Orion Spur", "System":"Hermitage", "SystemAddress":5363877956440, "NearestDestination":"$SAA_Unknown_Signal:#type=$SAA_SignalType_Geological;:#index=9;", "NearestDestination_Localised":"Surface signal: Geological (9)", "IsNewEntry":true, "VoucherAmount":50000 }
```

---

## 9. События флот-носителя (Manual §11)

### 9.1 `CarrierJumpRequest` — запрос прыжка (Manual §11.4)

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `CarrierID` | uint64 | да | ID носителя (= MarketID) |
| `CarrierType` | string | опц. | `"FleetCarrier"` \| `"SquadronCarrier"`. **В Manual v37 не указано**; читается EDDI (`JsonParsing.getString(data,"CarrierType")`) и присутствует в kayahr → подтверждено для новых версий |
| `SystemName` | string | да | Система назначения |
| `Body` | string | опц. | Имя тела (добавлено в v3.7 beta 2, Manual v28: «CarrierJumpRequest — added Body (name) and BodyID») |
| `SystemAddress` | uint64 | да | Address системы назначения |
| `BodyID` | int | опц. | ID тела назначения |
| `DepartureTime` | string ISO 8601 UTC | опц. | **Момент, когда носитель совершит прыжок.** Добавлено в Odyssey Update 14 (ноябрь 2022; Manual v36: «Added "DepartureTime" to the "CarrierJumpRequest" event»). До Update 14 поле отсутствовало |

**Формат `DepartureTime`:** строка ISO 8601 UTC, как и `timestamp`, секундная точность, обычно округлена до
минут: `"2020-04-20T09:45:00Z"` при `timestamp` запроса `"2020-04-20T09:30:58Z"`. В kayahr — `string`;
в EDDI парсится как `DateTime`; в Observatory — `DateTimeOffset`; в ed-journals — `DateTime<Utc>`.

**Ловушка в Manual v37:** в списке параметров §11.4 написано `SystemID: systemaddress`, но в официальном примере
и во всех реальных данных ключ называется **`SystemAddress`**. (Observatory для страховки моделирует оба поля:
`SystemAddress` и `SystemID`.) Ориентироваться на `SystemAddress`.

```json
{ "timestamp":"2020-04-20T09:30:58Z", "event":"CarrierJumpRequest", "CarrierID":3700005632, "SystemName":"Paesui Xena", "Body":"Paesui Xena A", "SystemAddress":7269634680241, "BodyID":1, "DepartureTime":"2020-04-20T09:45:00Z" }
{ "timestamp":"2020-05-11T18:56:09Z", "event":"CarrierJumpRequest", "CarrierID":3700357376, "SystemName":"Hemang", "Body":"Hemang A 2 a", "SystemAddress":4756709905082, "BodyID":7 }
```

(второй — реальный пример EDDI: до Update 14, без `DepartureTime`)

### 9.2 `CarrierJumpCancelled` (Manual §11.16) / `CarrierJump` (§11.1)

`CarrierJumpCancelled`: `CarrierID` (uint64), `CarrierType` (string, опц.). Всё. Manual: «This is logged when a
jump is cancelled».
`CarrierJump` — см. §2.4: полный срез системы+станции, пишется при прыжке носителя, если игрок онлайн на нём.
Важно: `CarrierJump` пишется **и при прибытии не на носителе** (Squadron Carrier и т.п. — не подтверждено);
достоверно документировано только «игрок онлайн и пристыкован к носителю».

### 9.3 `CarrierStats` — меню управления носителем (Manual §11.3)

| Поле | Тип | Описание |
|---|---|---|
| `CarrierID` | uint64 | = MarketID |
| `CarrierType` | string | опц. (нет в Manual; есть в kayahr) |
| `Callsign`, `Name` | string | Позывной и имя носителя |
| `DockingAccess` | string | `all` \| `none` \| `friends` \| `squadron` \| `squadronfriends` |
| `AllowNotorious` | bool | — |
| `FuelLevel` | int | Топливо (тонн) |
| `JumpRangeCurr`, `JumpRangeMax` | float | Текущая/максимальная дальность прыжка |
| `PendingDecommission` | bool | — |
| `SpaceUsage` | object | `{TotalCapacity, Crew, Cargo, CargoSpaceReserved, ShipPacks, ModulePacks, FreeSpace}` |
| `Finance` | object | `{CarrierBalance, ReserveBalance, AvailableBalance, ReservePercent, TaxRate}` в Manual v37 и старых журналах; **в новых журналах** единый `TaxRate` разбит на `TaxRate_rearm`, `TaxRate_refuel`, `TaxRate_repair`, `TaxRate_pioneersupplies`, `TaxRate_shipyard`, `TaxRate_outfitting` (kayahr) — разделение **не описано в Manual v37** |
| `Crew` | array | `[{CrewRole, Activated, Enabled, CrewName}]` |
| `ShipPacks`, `ModulePacks` | array | `[{PackTheme, PackTier}]` |

```json
{ "timestamp":"2020-03-27T09:42:04Z", "event":"CarrierStats", "CarrierID":3700005632, "Callsign":"L14-X1J", "Name":"Spirula", "DockingAccess":"all", "AllowNotorious":false, "FuelLevel":63, "JumpRangeCurr":81.079422, "JumpRangeMax":500.000000, "PendingDecommission":false, "SpaceUsage":{ "TotalCapacity":25000, "Crew":5450, "Cargo":440, "CargoSpaceReserved":44, "ShipPacks":774, "ModulePacks":913, "FreeSpace":17379 }, "Finance":{ "CarrierBalance":10000000, "ReserveBalance":1800000, "AvailableBalance":8171946, "ReservePercent":18, "TaxRate":3 }, "Crew":[ { "CrewRole":"Captain", "Activated":true, "Enabled":true, "CrewName":"Herbert Benson" } ], "ShipPacks":[ { "PackTheme":"Zorgon Peterson - Cargo", "PackTier":1 } ], "ModulePacks":[ { "PackTheme":"ExplosiveWeaponry", "PackTier":2 } ] }
```

### 9.4 `CarrierLocation` — новое событие ⚠️

**В Manual v37 отсутствует** (поиск по тексту manual не находит). Подтверждено реализациями:
kayahr `CarrierLocation.ts` (файл от 2025 г.) и EDDI `Events/CarrierLocationEvent.cs` («Triggered at startup and
shortly before a monitored fleet carrier arrives at a new destination»).
Поля: `CarrierID` (uint64), `CarrierType` (string, опц.), `StarSystem` (string), `SystemAddress` (uint64),
`BodyID` (int).

```json
{ "timestamp":"2025-03-19T19:02:10Z", "event":"CarrierLocation", "CarrierID":3705689344, "StarSystem":"HR 3635", "SystemAddress":1694121347427, "BodyID":1 }
```

### 9.5 Как определить, что прыжок запланирован и сколько до него осталось

1. `CarrierJumpRequest` — прыжок **запланирован**. Сохранить `CarrierID`, `SystemName`, `SystemAddress`, `Body`,
   `BodyID`, `DepartureTime`.
2. Осталось времени = `DepartureTime` − текущее UTC (оба — ISO 8601 UTC; в EDDI/kayahr/Observatory парсятся как
   обычные дат-таймы). Если `DepartureTime` отсутствует (журналы до Update 14 / сама игра старой версии) —
   точное время неизвестно, есть только факт запроса. В `CarrierStats` нет поля с cooldown/таймером — **не подтверждено**.
3. Прыжок отменён → `CarrierJumpCancelled` с тем же `CarrierID` (сбросить запланированный прыжок).
4. Прыжок совершён → `CarrierJump` (только если игрок онлайн на носителе) либо `CarrierLocation` (EDDI: пишется
   при старте и незадолго до прибытия носителя) — обновляет фактическое положение носителя.
5. `CarrierJumpRequest` и `CarrierJump` — **разные** события: первое фиксирует намерение (может быть отменено,
   может не состояться), второе — фактическое перемещение носителя вместе с игроком.

---

## 10. `timestamp` — формат во всех событиях

* Ключ `timestamp` есть в **каждом** событии. Значение — строка ISO 8601 в GMT/UTC, всегда с `Z`:
  `"2022-11-21T15:04:36Z"`, `"2018-11-04T23:44:36Z"`. Доли секунды не пишутся (Manual §2.2, §2.3).
* Внутри файла время монотонно возрастает; при ротации файлов (новый part) время продолжается, а не сбрасывается.
* `DepartureTime` — тот же формат ISO 8601 UTC.
* Единственное известное исключение: `CarrierDecommission.ScrapTime` — Unix-epoch секунды (int).
* Ответственность за таймзону на читателе: в файле нет локального времени, только UTC → при сравнении с
  `DepartureTime` приводить «сейчас» к UTC.

---

## 11. Где лежат журналы и как называются файлы

### 11.1 Имена файлов

Manual §2.1: «The filename is of the form `Journal.<datestamp>.<part>.log`». Два варианта датстампа встречаются
в реальных архивах:

* современный (live 4.x): `Journal.2022-06-07T181623.01.log` → `Journal.YYYY-MM-DDTHHMMSS.NN.log`
* старый (3.x): `Journal.161114145328.01.log` → `Journal.YYMMDDHHMMSS.NN.log`

`NN` — номер части (`part`), начинается с `01` и совпадает с `Fileheader.part`. Формально встречались и файлы
вида `Journal.2015-01-02T123456-01.log` (в тестовых данных kayahr) — нестандартный разделитель.

Регулярка из kayahr `Journal.ts` (как есть в исходнике, с учётом приоритета `|`):

```
^Journal\.\d{12}|\d{4}-\d{2}-\d{2}T\d{6}\.\d{2}\.log$
```

Практически: `Journal.` + (`YYMMDDHHMMSS` **или** `YYYY-MM-DDTHHMMSS`) + `.NN.log`.

### 11.2 Пути

| Платформа | Путь |
|---|---|
| Windows | `C:\Users\<User Name>\Saved Games\Frontier Developments\Elite Dangerous\` (Manual §2.1). В Проводнике можно открыть через `shell:SavedGames\Frontier Developments\Elite Dangerous\`. `Saved Games` можно перенести на другой диск, но только через Properties папки |
| Linux + Steam Proton | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous/` (kayahr README, ed-journals, EDMC) — AppID игры `359320` |
| Linux (EDMC docs, вариант `~/.steam`) | `~/.steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Linux + Wine | `~/.wine/drive_c/users/<you>/Saved Games/Frontier Developments/Elite Dangerous` (EDMC Troubleshooting) |
| Linux, прочие Proton-сборки (ed-journals) | `~/.local/share/Steam/compatibilitytools.d/Proton 3.16-8 Beta ED/dist/share/default_pfx/drive_c/users/steamuser/...`; `~/.local/share/Steam/steamapps/common/Elite Dangerous/Products/elite-dangerous-64/Logs/Saved Games/Frontier Developments/Elite Dangerous`; `~/.local/share/Steam/steamapps/common/Proton 4.2/dist/share/default_pfx/drive_c/users/steamuser/...` |
| macOS | Нативной версии игры нет (EDMC: «EDMC only runs via WINE or similar products on Mac»). Игра идёт внутри Wine-префикса, поэтому внутри префикса действует тот же Windows-путь. **Whisky:** бутылки лежат в `~/Library/Containers/com.isaacmarovitz.Whisky/Bottles/` ([docs.getwhisky.app/paths](https://docs.getwhisky.app/paths.html)) → журналы в `<Bottles>/<Bottle>/drive_c/users/<wineuser>/Saved Games/Frontier Developments/Elite Dangerous`. **CrossOver:** бутылки по умолчанию в `~/Library/Application Support/CrossOver/Bottles/` (CodeWeavers KB «Change Where CrossOver Stores Bottles»; страница на момент проверки не открывалась — **точный путь для ED внутри бутылки не подтверждён авторитетным источником**). Точное имя wine-пользователя (`crossover` или имя macOS-пользователя) зависит от версии обёртки → **надёжнее искать по маске `*/Saved Games/Frontier Developments/Elite Dangerous`, либо задавать путь вручную**. Parallels/Boot Camp/Windows-VM — обычный Windows-путь |
| Переменная окружения | `ED_JOURNAL_DIR` — поддерживается библиотекой kayahr (`Journal.findDirectory()` проверяет её первой) — самый надёжный способ для macOS/Wine-обёрток |

### 11.3 Прочие файлы в той же папке (Manual §2.1)

`Market.json`, `Outfitting.json`, `Shipyard.json`, `Status.json` (перезаписываются на месте, не ротируются),
а также (kayahr, Odyssey) `Backpack.json`, `Cargo.json`, `FCMaterials.json`, `ModulesInfo.json`, `NavRoute.json`,
`ShipLocker.json`. Это **не** журнал: перезаписываемые «снимки» состояния, а не поток событий.

---

## 12. Ротация журналов и смысл `Fileheader`

* `Fileheader` — **первое событие в каждом файле журнала** (Manual §2.2: «the heading entry is added at the
  beginning of every file»). Значит, появление `Fileheader` = начало нового файла/новой сессии чтения; после него
  обычно идёт `LoadGame`/`Commander`/`Location`/`Materials`/`Rank`/`Progress` и т.п.
* Новый файл создаётся при каждом запуске игры (одна игровая сессия → один файл). Прямой формулировки
  «новый файл при каждом запуске» в Manual v37 **нет** — это согласованное поведение, на которое опираются
  все инструменты (EDMC/EDDN/EDDI/EDDiscovery): метка времени в имени файла соответствует началу сессии,
  а `Fileheader.gameversion`/`build` описывают версию клиента именно этой сессии. Помечено как
  **не подтверждено прямой цитатой manual**.
* Ротация внутри долгой сессии: если файл вырастает до **500 000 строк**, игра пишет событие `Continued`
  с параметром `Part` (номер следующей части), закрывает файл и открывает новый с `part` + 1 и новым `Fileheader`
  (Manual §2.2 и §13.6). То есть `part` > 1 возможен и без перезапуска игры.
* Автоматическое удаление старых файлов журнала — **не подтверждено** (ни в Manual, ни в документации инструментов
  такого утверждения не найдено); инструменты обязаны сами ограничивать глубину чтения.
* Читателю важно: файлы надо сортировать хронологически. kayahr сортирует имена так: при равной длине —
  лексикографически, при разной — сначала более короткие (старый формат `YYMMDDHHMMSS` короче нового
  `YYYY-MM-DDTHHMMSS`), потому что формат имени менялся между версиями игры.
* Первая строка файла может быть недописанной в момент чтения — надёжнее дочитывать по мере появления новых строк
  (журнал пишется инкрементально, построчно).

---

## 13. Что реально «не подтверждено» (сводка)

| Утверждение | Статус |
|---|---|
| `Scan.BioSignals` (или любое поле с числом биосигналов в `Scan`) | **не подтверждено** — отсутствует в Manual v37, kayahr, EDDN, ed-journals, EDMC-BioScan/EDMC |
| `SAASignalsFound.Genuses[].Species` / `Species_Localised` | **не подтверждено** — только `Genus`/`Genus_Localised` (Manual v37, реальные примеры EDDI, kayahr, Observatory) |
| `CodexEntry.Reward` | **не подтверждено** — есть только `VoucherAmount` (Manual v37, EDDN-схема, kayahr, Observatory, EDDI) |
| `CarrierLocation` в официальном manual | **не подтверждено** (Manual v37 события не содержит); подтверждено EDDI и kayahr |
| `CarrierJumpRequest.CarrierType` | в Manual v37 не указано; подтверждено EDDI (читает ключ) и kayahr |
| `CarrierStats.Finance.TaxRate_*` (разбивка по службам) | в Manual v37 не описано; подтверждено kayahr |
| `Scan.WasFootfalled` | в Manual v37 не указано; подтверждено kayahr |
| `ScanOrganic.WasLogged` | в Manual v37 не указано; используется EDMC-BioScan |
| Cooldown носителя / точный таймер до следующего возможного прыжка в журнале | **не подтверждено** — поля нет |
| Автоудаление старых файлов журнала | **не подтверждено** |
| Новый файл журнала строго при каждом запуске игры | согласованное поведение; прямой цитаты manual нет |
| Путь журналов внутри CrossOver-бутылки на macOS | **не подтверждено авторитетным источником** (для Whisky подтверждён только корень бутылок) |
| `FSSDiscoveryScan.SystemName`/`SystemAddress` | в Manual v37 не перечислены; в реальных 4.x-журналах есть, в примере 3.x (2018) отсутствуют |
| `FSSSignalDiscovered.SignalType` | в Manual v37 не перечислен; подтверждено kayahr/EDDN/реальными примерами |

---

## 14. Источники

* **Elite Dangerous Player Journal Manual v37** (официальный документ Frontier) — полный PDF:
  [kayahr/ed-journal `doc/journal/Journal_Manual_v37.pdf`](https://github.com/kayahr/ed-journal/blob/main/doc/journal/Journal_Manual_v37.pdf)
  (в этом же репозитории лежат версии v1–v37; текст извлечён из PDF v37 локально).
  Обсуждение документации на форуме Frontier:
  [Commanders log manual and data sample](https://forums.frontier.co.uk/threads/commanders-log-manual-and-data-sample.275151/),
  [Journal docs for Odyssey release](https://forums.frontier.co.uk/threads/journal-docs-for-odyssey-release.575010/),
  [Journal Documentation for v3.0](https://forums.frontier.co.uk/threads/journal-documentation-for-v3-0.401661/)
* [kayahr/ed-journal](https://github.com/kayahr/ed-journal) — TypeScript-типы всех событий (README: пути к журналам и Proton)
* [EDCD/EDDN `schemas/`](https://github.com/EDCD/EDDN/tree/master/schemas) — JSON-схемы `codexentry`, `fssdiscoveryscan`,
  `fssallbodiesfound`, `fsssignaldiscovered`, `fssbodysignals`, `journal` + README с правилами по локализации и PII
* [EDCD/EDDI](https://github.com/EDCD/EDDI) — `Events/*.cs` с реальными строками журнала в `SAMPLE(S)`
  (`CodexEntryEvent`, `CarrierLocationEvent`, `CarrierJumpRequestEvent`, `FSSDiscoveryScanEvent`, `SignalDetectedEvent`,
  `SurfaceSignalsEvent`, `SystemScanComplete`, `ScanOrganicEvent`)
* [Observatory Framework (quartznet/pulsar)](https://git.quartznet.info/quartznet/pulsar) — `ObservatoryFramework/Files/Journal/**`
  (`SAASignalsFound.cs`, `CodexEntry.cs`, `CarrierJumpRequest.cs`, `FSSSignalDiscovered.cs`, `ParameterTypes/Genus.cs`)
* [rster2002/ed-logs (`ed-journals`, `ed-exobiology`)](https://github.com/rster2002/ed-logs) — Rust-модели только для
  live 4.x, `auto_detect_journal_path` со списком Linux-путей, модель предсказания видов
* [EDCD/EDMarketConnector](https://github.com/EDCD/EDMarketConnector) — вики
  [Installation & Setup](https://github.com/EDCD/EDMarketConnector/wiki/Installation-&-Setup) и
  [Troubleshooting](https://github.com/EDCD/EDMarketConnector/wiki/Troubleshooting) (пути журналов, оговорка про macOS)
* [Whisky docs — What's Where](https://docs.getwhisky.app/paths.html) — расположение бутылок на macOS
* [EDPlayerJournal (florian)](https://git.aror.org/florian/EDPlayerJournal) — реальные строки `Fileheader` в тестах
* Локально: `research/EDMC-BioScan/src/load.py` — как плагин-экспортёр биологии регистрирует
  `'Scan'`, `'FSSBodySignals'`, `'SAASignalsFound'`, `'ScanOrganic'`, `'CodexEntry'`
