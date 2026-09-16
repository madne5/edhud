# Экзобиология Elite Dangerous: Odyssey — базовые выплаты, множители, порог 8000

> Все цифры в этом файле **не выдуманы**: они собраны из трёх независимых наборов данных
> и сверены машинно (см. раздел «Верификация»). Спорные значения помечены ⚠️.

## 0. Краткие выводы (TL;DR)

1. **Видов с базой ниже 8 000 кредитов НЕ существует.** Минимум по всем стандартным видам —
   **1 000 000 кр**; единственное исключение — спец-вид `Radicoida Unicus` (119 037 кр,
   одна система HIP 87621). Фильтр «> 8000 кр» пропускает **100 %** видов.
2. Реальный базовый диапазон: **1 000 000 … 20 000 000 кр**, медиана ~2,64 млн.
3. Бонус «First Logged» — это **+400 % (итого ×5)**, а **не** отдельный ×4 поверх ×5.
   **First Footfall сам кредитов не даёт** — он лишь *гарантирует* бонус First Logged.
4. **Бонуса за расстояние от Пузыря в экзобиологии нет** (это механика картографии).
5. **Род (genus) виден в журнале ДО высадки** — после сканирования планеты DSS
   (`SAASignalsFound → Genuses`). **Вид (species) — только после первого образца**
   (`ScanOrganic`, `ScanType: "Log"`), т.е. уже на поверхности.
6. Соответствия «звук FSS ↔ род биологии» в игре **нет**. Аудио-сигнатуры —
   это SRV Wave Scanner (3 класса сигналов), к родам биологии отношения не имеет.

---

## 1. Таблица базовых выплат: genus → species → base value

Значения — базовые выплаты Vista Genomics в кредитах (без множителей).
Столбец «×5» — выплата при First Logged.

### Aleoida (5 видов; 3 385 200 … 12 934 900)

| Species | Base (CR) | ×5 (First Logged) |
|---|---:|---:|
| Aleoida Gravis | 12,934,900 | 64,674,500 |
| Aleoida Arcus | 7,252,500 | 36,262,500 |
| Aleoida Coronamus | 6,284,600 | 31,423,000 |
| Aleoida Spica | 3,385,200 | 16,926,000 |
| Aleoida Laminiae | 3,385,200 | 16,926,000 |

### Anemone (8; все по 1 499 900)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Luteolum Anemone | 1,499,900 | 7,499,500 |
| Croceum Anemone | 1,499,900 | 7,499,500 |
| Puniceum Anemone | 1,499,900 | 7,499,500 |
| Roseum Anemone | 1,499,900 | 7,499,500 |
| Rubeum Bioluminescent Anemone | 1,499,900 | 7,499,500 |
| Prasinum Bioluminescent Anemone | 1,499,900 | 7,499,500 |
| Roseum Bioluminescent Anemone | 1,499,900 | 7,499,500 |
| Blatteum Bioluminescent Anemone | 1,499,900 | 7,499,500 |

### Bacterium (13; 1 000 000 … 8 418 000)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Bacterium Informem | 8,418,000 | 42,090,000 |
| Bacterium Volu | 7,774,700 | 38,873,500 |
| Bacterium Nebulus | 5,289,900 | 26,449,500 |
| Bacterium Scopulum | 4,934,500 | 24,672,500 |
| Bacterium Omentum | 4,638,900 | 23,194,500 |
| Bacterium Verrata | 3,897,000 | 19,485,000 |
| Bacterium Tela | 1,949,000 | 9,745,000 |
| Bacterium Cerbrus | 1,689,800 | 8,449,000 |
| Bacterium Alcyoneum | 1,658,500 | 8,292,500 |
| Bacterium Bullaris | 1,152,500 | 5,762,500 |
| Bacterium Aurasus | 1,000,000 | 5,000,000 |
| Bacterium Acies | 1,000,000 | 5,000,000 |
| Bacterium Vesicula | 1,000,000 | 5,000,000 |

### Brain Tree (8; все 1 593 700)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Roseum Brain Tree | 1,593,700 | 7,968,500 |
| Gypseeum Brain Tree | 1,593,700 | 7,968,500 |
| Ostrinum Brain Tree | 1,593,700 | 7,968,500 |
| Viride Brain Tree | 1,593,700 | 7,968,500 |
| Aureum Brain Tree | 1,593,700 | 7,968,500 |
| Puniceum Brain Tree | 1,593,700 | 7,968,500 |
| Lindigoticum Brain Tree | 1,593,700 | 7,968,500 |
| Lividum Brain Tree | 1,593,700 | 7,968,500 |

### Cactoida (5; 2 483 600 … 16 202 800)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Cactoida Vermis | 16,202,800 | 81,014,000 |
| Cactoida Cortexum | 3,667,600 | 18,338,000 |
| Cactoida Pullulanta | 3,667,600 | 18,338,000 |
| Cactoida Lapis | 2,483,600 | 12,418,000 |
| Cactoida Peperatis | 2,483,600 | 12,418,000 |

### Clypeus (3; 8 418 000 … 16 202 800)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Clypeus Speculumi | 16,202,800 | 81,014,000 |
| Clypeus Margaritus | 11,873,200 | 59,366,000 |
| Clypeus Lacrimam | 8,418,000 | 42,090,000 |

### Concha (4; 2 352 400 … 19 010 800)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Concha Biconcavis ⚠️ | 19,010,800 | 95,054,000 |
| Concha Aureolas | 7,774,700 | 38,873,500 |
| Concha Renibus | 4,572,400 | 22,862,000 |
| Concha Labiata | 2,352,400 | 11,762,000 |

⚠️ У `Concha Biconcavis` источники расходятся: Canonn (данные продаж) и ArtemisScannerTracker
(«Update 14.01») дают **19 010 800**; EDMC-BioScan и старые (курсивные) таблицы вики —
**16 777 215** = 2²⁴−1 (типичный плейсхолдер до ребаланса Update 14).
Принято 19 010 800. При разработке рекомендуется держать это значение в конфиге.

### Electricae (2; оба 6 284 600)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Electricae Pluma | 6,284,600 | 31,423,000 |
| Electricae Radialem | 6,284,600 | 31,423,000 |

### Fonticulua (6; 1 000 000 … 20 000 000)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Fonticulua Fluctus | 20,000,000 | 100,000,000 |
| Fonticulua Segmentatus | 19,010,800 | 95,054,000 |
| Fonticulua Upupam | 5,727,600 | 28,638,000 |
| Fonticulua Lapida | 3,111,000 | 15,555,000 |
| Fonticulua Digitos | 1,804,100 | 9,020,500 |
| Fonticulua Campestris | 1,000,000 | 5,000,000 |

### Frutexa (7; 1 632 500 … 10 326 000)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Frutexa Flammasis | 10,326,000 | 51,630,000 |
| Frutexa Acus | 7,774,700 | 38,873,500 |
| Frutexa Sponsae | 5,988,000 | 29,940,000 |
| Frutexa Flabellum | 1,808,900 | 9,044,500 |
| Frutexa Collum | 1,639,800 | 8,199,000 |
| Frutexa Metallicum | 1,632,500 | 8,162,500 |
| Frutexa Fera | 1,632,500 | 8,162,500 |

### Fumerola (4; 6 284 600 … 16 202 800)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Fumerola Extremus | 16,202,800 | 81,014,000 |
| Fumerola Nitris | 7,500,900 | 37,504,500 |
| Fumerola Carbosis | 6,284,600 | 31,423,000 |
| Fumerola Aquatis | 6,284,600 | 31,423,000 |

### Fungoida (4; 1 670 100 … 3 703 200)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Fungoida Bullarum | 3,703,200 | 18,516,000 |
| Fungoida Gelata | 3,330,300 | 16,651,500 |
| Fungoida Stabitis | 2,680,300 | 13,401,500 |
| Fungoida Setisis | 1,670,100 | 8,350,500 |

### Osseus (6; 1 483 000 … 12 934 900)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Osseus Discus | 12,934,900 | 64,674,500 |
| Osseus Pellebantus | 9,739,000 | 48,695,000 |
| Osseus Fractus | 4,027,800 | 20,139,000 |
| Osseus Pumice | 3,156,300 | 15,781,500 |
| Osseus Spiralis | 2,404,700 | 12,023,500 |
| Osseus Cornibus | 1,483,000 | 7,415,000 |

### Recepta (3; 12 934 900 … 16 202 800)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Recepta Deltahedronix | 16,202,800 | 81,014,000 |
| Recepta Conditivus | 14,313,700 | 71,568,500 |
| Recepta Umbrux | 12,934,900 | 64,674,500 |

### Stratum (8; 1 362 000 … 19 010 800)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Stratum Tectonicas | 19,010,800 | 95,054,000 |
| Stratum Cucumisis | 16,202,800 | 81,014,000 |
| Stratum Laminamus | 2,788,300 | 13,941,500 |
| Stratum Frigus | 2,637,500 | 13,187,500 |
| Stratum Excutitus | 2,448,900 | 12,244,500 |
| Stratum Araneamus | 2,448,900 | 12,244,500 |
| Stratum Paleas | 1,362,000 | 6,810,000 |
| Stratum Limaxus | 1,362,000 | 6,810,000 |

### Tubus (5; 2 415 500 … 11 873 200)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Tubus Cavas | 11,873,200 | 59,366,000 |
| Tubus Compagibus | 7,774,700 | 38,873,500 |
| Tubus Sororibus | 5,727,600 | 28,638,000 |
| Tubus Rosarium | 2,637,500 | 13,187,500 |
| Tubus Conifer | 2,415,500 | 12,077,500 |

### Tussock (15; 1 000 000 … 19 010 800)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Tussock Stigmasis | 19,010,800 | 95,054,000 |
| Tussock Virgam | 14,313,700 | 71,568,500 |
| Tussock Triticum | 7,774,700 | 38,873,500 |
| Tussock Capillum | 7,025,800 | 35,129,000 |
| Tussock Pennata | 5,853,800 | 29,269,000 |
| Tussock Serrati | 4,447,100 | 22,235,500 |
| Tussock Caputus | 3,472,400 | 17,362,000 |
| Tussock Albata | 3,252,500 | 16,262,500 |
| Tussock Ventusa | 3,227,700 | 16,138,500 |
| Tussock Ignis | 1,849,000 | 9,245,000 |
| Tussock Cultro | 1,766,600 | 8,833,000 |
| Tussock Catena | 1,766,600 | 8,833,000 |
| Tussock Divisa | 1,766,600 | 8,833,000 |
| Tussock Pennatis | 1,000,000 | 5,000,000 |
| Tussock Propagito | 1,000,000 | 5,000,000 |

### Sinuous Tubers (8; все 1 514 500)

| Species | Base (CR) | ×5 |
|---|---:|---:|
| Roseum Sinuous Tubers | 1,514,500 | 7,572,500 |
| Prasinum Sinuous Tubers | 1,514,500 | 7,572,500 |
| Albidum Sinuous Tubers | 1,514,500 | 7,572,500 |
| Caeruleum Sinuous Tubers | 1,514,500 | 7,572,500 |
| Lindigoticum Sinuous Tubers | 1,514,500 | 7,572,500 |
| Violaceum Sinuous Tubers | 1,514,500 | 7,572,500 |
| Viride Sinuous Tubers | 1,514,500 | 7,572,500 |
| Blatteum Sinuous Tubers | 1,514,500 | 7,572,500 |

### Одиночные роды

| Genus | Species | Base (CR) | ×5 |
|---|---|---:|---:|
| Crystalline Shard | Crystalline Shards | 1,628,800 | 8,144,000 |
| Amphora Plant | Amphora Plant | 1,628,800 | 8,144,000 |
| Bark Mound | Bark Mound | 1,471,900 | 7,359,500 |
| Radicoida ⚠️ | Radicoida Unicus | 119,037 | 595,185 |

⚠️ `Radicoida Unicus` — вид из одной системы (HIP 87621). Canonn и BioScan дают **119 037**,
ArtemisScannerTracker — **1 904 592**. Не подтверждено.

### Thargoid (не стандартная экзобиология; для полноты)

| Species | Base (CR) |
|---|---:|
| Thargoid Mega Barnacles | 2,313,500 |
| Thargoid Spires | 2,247,100 |
| Thargoid Coral Root | 1,924,600 |
| Thargoid Coral Tree | 1,896,800 |

**Итого: 22 рода (включая 3 одиночных), 118 стандартных видов (+4 таргоидских).**

---

## 2. Как считается итоговая выплата

### Формула

```
payout = base_value × (1 + 4 × was_not_previously_logged)      # → ×5 при First Logged
```

Точные факты (подтверждены):

* **First Logged («First Scanned») = +400 %**, т.е. **итого ×5** базовой стоимости.
  Формулировки источников дословно:
  * вики «Exobiologist»: «samples that qualify as "First Logged" will reward **quadruple (x4)**
    the sample's base value as a bonus, **on top of the base value**»;
  * вики «First Footfall»: «the **First Scanned 500 % Bonus (base value + 4x base value as a bonus)**»;
  * вики «Vista Genomics»: бонус даётся, если вид «has not previously been logged in the Codex
    for a given **galactic region**».
  * **Эмпирическое подтверждение** — пример из официальной документации журнала, событие
    `SellOrganicData`: `{"Genus":"Tubus","Species":"Tubus Conifer","Value":2415500,"Bonus":9662000}`.
    `9662000 = 4 × 2415500` ровно. ✅
* **First Footfall кредитов сам по себе НЕ даёт.** Он лишь гарантирует, что вид ещё не занесён
  в кодекс региона, т.е. что вы получите ×5. Дословно: «Getting First Footfall **does not grant
  any credits directly**, however … is almost guaranteed that they will receive the First Scanned
  500 % Bonus».
* **Множители НЕ перемножаются.** Неверно модельное представление «×4 за первую запись × ×5 за
  first footfall = ×20». Максимум — **×5**. Отдельного множителя за первую посадку нет.
* **Бонус привязан к галактическому региону** (Codex region), а не к системе и не к галактике.
  Один и тот же вид в другом регионе снова даёт ×5, если там он ещё не занесён.
* **Бонуса за расстояние от Пузыря нет.** Дистанционный бонус существует только в картографии
  (`SellExplorationData` → `BaseValue` + `Bonus`). Влияние расстояния на экзобиологию —
  **только косвенное**: чем дальше от обитаемого космоса, тем меньше шанс, что вид уже
  кто-то занёс → выше шанс на ×5. Подтверждение: утилита BioScan считает множитель как
  `mult = 5 if not body.was_footfalled(cmd) and not system_populated else 1` — т.е. ×5 даётся
  только вне населённых систем и без предыдущего footfall.
* **За 3 образца платят один раз** за вид (нужно 3 образца + `Analyse` — это условие выплаты,
  а не множитель).
* Есть отдельный мелкий ваучер за новую запись в кодексе (`CodexEntry → VoucherAmount`,
  в примере 50 000 кр) — не путать с выплатой Vista Genomics.

### Практические итоговые суммы (×5)

| Вид | Base | ×5 |
|---|---:|---:|
| Fonticulua Fluctus | 20,000,000 | 100,000,000 |
| Stratum Tectonicas | 19,010,800 | 95,054,000 |
| Tussock Stigmasis | 19,010,800 | 95,054,000 |
| Fonticulua Segmentatus | 19,010,800 | 95,054,000 |
| Concha Biconcavis | 19,010,800 | 95,054,000 |
| Bacterium Aurasus (самый дешёвый обычный) | 1,000,000 | 5,000,000 |

---

## 3. Порог 8000 кредитов — прямой ответ

**Видов с базовой выплатой ниже 8 000 кредитов НЕТ.** Вообще ни одного.

| Диапазон базы | Кол-во стандартных видов |
|---|---:|
| 0 … 8 000 | **0** |
| 8 000 … 1 000 000 | 1 (`Radicoida Unicus`, 119 037) |
| 1 000 000 … 2 000 000 | 50 |
| 2 000 000 … 5 000 000 | 28 |
| 5 000 000 … 10 000 000 | 21 |
| 10 000 000 … 20 000 000 | 18 |

Минимум 1 000 000 · медиана 2 637 500 · максимум 20 000 000.

**Следствие для фильтра:** условие `base > 8000` истинно для **всех 118 видов** — такой фильтр
бесполезен. Чтобы фильтр был осмысленным, нужно:

1. **Фильтровать по роду, а не по виду** — род становится известен в журнале **до высадки**
   (см. §4), а вид — нет. Именно это и есть практический критерий отбора систем.
2. Использовать порог по **роду/виду** в миллионах, например:
   * `≥ 5 000 000` базы (→ ≥ 25 млн с ×5): **39 видов** — реально «дорогие»;
   * `≥ 10 000 000` базы: **18 видов** — топ-тир.
3. Комбинировать с вероятностью ×5 (ненаселённая система + отсутствие First Footfall).

### Ранжирование родов по максимальной выплате

| Род | Видов | Мин базы | Макс базы | Макс ×5 |
|---|---:|---:|---:|---:|
| Fonticulua | 6 | 1,000,000 | 20,000,000 | 100,000,000 |
| Concha | 4 | 2,352,400 | 19,010,800 | 95,054,000 |
| Stratum | 8 | 1,362,000 | 19,010,800 | 95,054,000 |
| Tussock | 15 | 1,000,000 | 19,010,800 | 95,054,000 |
| Cactoida | 5 | 2,483,600 | 16,202,800 | 81,014,000 |
| Clypeus | 3 | 8,418,000 | 16,202,800 | 81,014,000 |
| Fumerola | 4 | 6,284,600 | 16,202,800 | 81,014,000 |
| Recepta | 3 | 12,934,900 | 16,202,800 | 81,014,000 |
| Aleoida | 5 | 3,385,200 | 12,934,900 | 64,674,500 |
| Osseus | 6 | 1,483,000 | 12,934,900 | 64,674,500 |
| Tubus | 5 | 2,415,500 | 11,873,200 | 59,366,000 |
| Frutexa | 7 | 1,632,500 | 10,326,000 | 51,630,000 |
| Bacterium | 13 | 1,000,000 | 8,418,000 | 42,090,000 |
| Electricae | 2 | 6,284,600 | 6,284,600 | 31,423,000 |
| Fungoida | 4 | 1,670,100 | 3,703,200 | 18,516,000 |
| Crystalline Shard | 1 | 1,628,800 | 1,628,800 | 8,144,000 |
| Amphora Plant | 1 | 1,628,800 | 1,628,800 | 8,144,000 |
| Brain Tree | 8 | 1,593,700 | 1,593,700 | 7,968,500 |
| Sinuous Tubers | 8 | 1,514,500 | 1,514,500 | 7,572,500 |
| Anemone | 8 | 1,499,900 | 1,499,900 | 7,499,500 |
| Bark Mound | 1 | 1,471,900 | 1,471,900 | 7,359,500 |
| Radicoida ⚠️ | 1 | 119,037 | 119,037 | 595,185 |

**Важный нюанс:** у «выгодных» родов большой разброс. Например, у `Tussock` минимум 1 000 000
(`Tussock Pennatis`), а максимум 19 010 800 (`Tussock Stigmasis`) — разница ×19. Поэтому
для точного прогноза нужно не только род, но и параметры планеты (атмосфера, температура,
гравитация, вулканизм, регион) — именно так работают BioScan и BioInsights: они строят
**список возможных видов** по параметрам планеты, а затем сужают его после DSS.

### Топ-15 самых дешёвых (полный список, не «ниже 8000»)

| Species | Base (CR) |
|---|---:|
| Radicoida Unicus ⚠️ | 119,037 |
| Bacterium Aurasus | 1,000,000 |
| Bacterium Acies | 1,000,000 |
| Bacterium Vesicula | 1,000,000 |
| Fonticulua Campestris | 1,000,000 |
| Tussock Pennatis | 1,000,000 |
| Tussock Propagito | 1,000,000 |
| Bacterium Bullaris | 1,152,500 |
| Stratum Paleas | 1,362,000 |
| Stratum Limaxus | 1,362,000 |
| Bark Mound | 1,471,900 |
| Osseus Cornibus | 1,483,000 |
| Luteolum Anemone | 1,499,900 |
| Croceum Anemone | 1,499,900 |
| Puniceum Anemone | 1,499,900 |

### Топ-15 самых дорогих

| Species | Base (CR) |
|---|---:|
| Fonticulua Fluctus | 20,000,000 |
| Concha Biconcavis ⚠️ | 19,010,800 |
| Fonticulua Segmentatus | 19,010,800 |
| Stratum Tectonicas | 19,010,800 |
| Tussock Stigmasis | 19,010,800 |
| Cactoida Vermis | 16,202,800 |
| Clypeus Speculumi | 16,202,800 |
| Fumerola Extremus | 16,202,800 |
| Recepta Deltahedronix | 16,202,800 |
| Stratum Cucumisis | 16,202,800 |
| Recepta Conditivus | 14,313,700 |
| Tussock Virgam | 14,313,700 |
| Aleoida Gravis | 12,934,900 |
| Osseus Discus | 12,934,900 |
| Recepta Umbrux | 12,934,900 |

---

## 4. Что и когда становится известно в журнале игры

| Этап | Событие журнала | Что узнаём |
|---|---|---|
| 1. «Хонк» в системе | `FSSDiscoveryScan` | `BodyCount`, `NonBodyCount` — только счётчики |
| 2. FSS-сканирование конкретного тела | `FSSBodySignals` | `Signals[]` c `Type: "$SAA_SignalType_Biological;"` и `Count` — **число** биосигналов на планете. **Рода НЕТ** |
| 3. Сканирование поверхности (DSS / зонды) | `SAASignalsFound` | **`Genuses[]`** — `{"Genus":"$Codex_Ent_Bacterial_Genus_Name;","Genus_Localised":"Bacterium"}` → **РОД известен, ещё до высадки** |
| 4. Первый образец на поверхности (Genetic Sampler) | `ScanOrganic` c `ScanType: "Log"` | **`Genus`, `Species`, `Variant`** (+`_Localised`) → **ВИД известен только здесь** |
| 5. Второй/третий образец | `ScanOrganic` `ScanType: "Sample"` | прогресс |
| 6. Третий образец | `ScanOrganic` `ScanType: "Analyse"` | образец готов к продаже |
| 7. Продажа в Vista Genomics | `SellOrganicData` | `BioData[]` c `Value` (= базе) и `Bonus` (= 4×база при First Logged) |

**Прямой ответ на вопрос 4:** ДО высадки можно узнать только **род** (после DSS, шаг 3).
**Вид** (species) в журнале появляется **только после первого взятого образца** (шаг 4), т.е. уже
на поверхности. Предсказать вид заранее из журнала нельзя — только эвристически по параметрам
планеты (это и делают BioScan / BioInsights).

Дополнительно:

* В `ScanOrganic` присутствует недокументированное в основной таблице поле **`WasLogged`**
  (bool). Оно показывает, был ли этот вид/вариант уже занесён в кодекс региона — то есть
  **прямо говорит, получите ли вы ×5**. Подтверждено исходником BioScan:
  `entry.get('WasLogged', None)`. Это самое полезное поле для расчёта выплаты.
* **Отдельного события «First Footfall» в журнале НЕТ.** На форуме Frontier висит
  запрос на его добавление («[Request for Enhancement] - First Footfall Confirmed event in
  journal»). Поэтому утилиты выводят First Footfall косвенно: своя высадка/`Touchdown` +
  населённость системы. Практический признак ×5 — `WasLogged == false` из `ScanOrganic`.
* Полезные для фильтрации поля события `Scan` (планета): `Atmosphere`, `AtmosphereType`,
  `Volcanism`, `SurfaceGravity`, `SurfaceTemperature`, `SurfacePressure`, `PlanetClass`,
  `Landable`, `WasDiscovered`, `WasMapped` — именно они дают прогноз видов.
* `CodexEntry` (при новой записи) содержит `Region` / `Region_Localised` — прямой способ
  определить галактический регион для логики First Logged.

---

## 5. Готовые датасеты и точные URL

### Машинно-читаемые (то, что можно встроить в Python)

| Что | URL |
|---|---|
| **BioScan: реестр родов** | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data/species.py` |
| **BioScan: значения по родам** (19 файлов) | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data/rulesets/<genus>.py` |
| пример: Bacterium | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data/rulesets/bacterium.py` |
| пример: Tussock | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data/rulesets/tussock.py` |
| пример: Stratum | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data/rulesets/stratum.py` |
| **ArtemisScannerTracker: плоский dict species→price** | `https://raw.githubusercontent.com/Balvald/ArtemisScannerTracker/main/organicinfo.py` |
| BioScan: регионы кодекса | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data/regions.py` |
| BioScan: кодекс | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/bio_data/codex.py` |
| BioScan: справочные звёзды туманностей (374 КБ) | `https://raw.githubusercontent.com/Silarn/EDMC-BioScan/master/src/bio_scan/nebula_data/reference_stars.py` |

Доступные имена файлов в `rulesets/`: `aleoida, anemone, bacterium, brain_tree, cactoida, clypeus,
concha, electricae, fonticulua, frutexa, fumerola, fungoida, osseus, recepta, shard, stratum,
tubers, tubus, tussock` (все проверены: HTTP 200).

Структура каждого файла: `catalog = { "$Codex_Ent_..._Genus_Name;": { "$Codex_Ent_..._Species_Name;":
{"name": "Tubus Conifer", "value": 2415500, "rulesets": [...] } } }` — то есть помимо значения там
ещё и **условия встречаемости** (атмосфера, гравитация, температура, давление, вулканизм, регион).
Это идеальная база для фильтра систем.

Особый случай: `Bark Mound`, `Amphora Plant`, `Radicoida Unicus` лежат не в `rulesets/`, а прямо
в `species.py` (dict `_mound_amphora`).

### Человекочитаемые источники данных о ценах

* **Canonn Research, Vista Genomics Price List** (по реальным загруженным данным продаж):
  <https://canonn.science/codex/vista-genomics-price-list/> ·
  Google Sheet: <https://docs.google.com/spreadsheets/d/15lqZtqJk7B2qUV5Jb4tlnst6i1B7pXlAUzQnacX64Kc/>
* **Canonn Biosheet** (условия встречаемости): <https://canonn.fyi/biosheet> ·
  <https://docs.google.com/spreadsheets/d/1nV_UD_0kIxkWAHhAqvf62ILHpbYzdZpJ53CqPHn3qlA/>
* Вики: «Exobiology Sample Values and Details», «Exobiologist», «Vista Genomics», «First Footfall»

---

## 6. Про «аудио-сигнатуру» биологических сигналов в FSS

Короткий ответ: **звук в FSS не кодирует род биологии, и такого соответствия не существует.**
Что есть на самом деле:

1. **FSS (Full Spectrum System Scanner)** работает через полосу Filtered Signal Analysis:
   частота → тип цели. Обратная связь по настройке — **визуальная**: «сломанное кольцо»
   вокруг цели становится сплошным при точной частоте, и появляются симметрично
   сгруппированные стрелки у прицела. Плюс звуковой отклик на попадание в резонанс.
2. **FSS не показывает род.** Максимум, что даёт FSS по биологии — событие `FSSBodySignals`,
   где для тела указано `Type: "$SAA_SignalType_Biological;"` и `Count` — просто **число**
   биосигналов. На этом этапе ни род, ни вид неизвестны.
3. **Род появляется только после DSS** (`SAASignalsFound → Genuses`). Это уже не FSS.
4. То, что обычно называют «аудио-сигнатурой биологических сигналов», — это **SRV Wave Scanner**
   (модуль только у Scarab). Дословно: сканер различает **три класса** сигналов — *natural*
   (низкая частота, низкий тон — фрагменты для добычи), *vessel* (средняя частота — корабли и
   места крушений), *artificial* (высокая частота — data points и поселения). Звук помогает
   **оценить направление/положение** объекта, а не определить биологию.
5. Игровые утилиты (BioScan, Observatory BioInsights) определяют вид **не по звуку**, а по
   **параметрам планеты и положению в Галактике** (атмосфера, температура, гравитация,
   вулканизм, тип тела, класс звезды, регион, близость туманностей).

**Вывод:** если в проекте планируется «определение рода по звуку FSS» — такой механики в игре
нет. Определять род/вид нужно из журнала (`SAASignalsFound` → `ScanOrganic`) либо
эвристически по параметрам планеты, как это делают BioScan/BioInsights.

---

## 7. Верификация данных

Сверены три независимых источника:

1. **EDMC-BioScan** (rulesets, 116 записей) — <https://github.com/Silarn/EDMC-BioScan>
2. **Canonn Research** — цена по фактическим продажам, <https://canonn.science/codex/vista-genomics-price-list/>
3. **ArtemisScannerTracker** («Update 14.01 prices», 118 записей) — <https://github.com/Balvald/ArtemisScannerTracker>

Результат машинной сверки:

* **116 из 122** записей совпали точно во всех источниках, где они присутствуют.
* Расхождений «2 из 3» — **0** (кроме Concha Biconcavis, см. ниже).
* Без полного трёхстороннего подтверждения остались: `Concha Biconcavis` (⚠️ ребаланс Update 14),
  `Bark Mound` (различие только в написании: Canonn пишет «Bark Mounds», значение то же),
  `Radicoida Unicus` (⚠️ конфликт), 4 таргоидских записи (только Canonn + вики).
* `Stratum Aranaemus` — **ошибочная запись** в EDMC-BioScan (дубль-опечатка от
  `Stratum Araneamus`); удалена. Ни Canonn, ни Artemis, ни вики такого вида не знают.
* `Concha Biconcavis`: 16 777 215 (= 2²⁴−1) — устаревший плейсхолдер; актуальное значение
  **19 010 800** (Canonn + Artemis).
* Вики-страницы «Exobiologist» / «Exobiology Sample Values and Details» помечают ряд значений
  курсивом с пометкой «credit values in italic may be outdated». Курсивные значения,
  которые **опровергнуты тремя источниками** (не использовать):
  Amphora Plant (3 626 400), Crystalline Shard (3 626 400), Bacterium Nebulus (9 116 600),
  Bacterium Scopulum (8 633 800), Brain Tree Aureum/Gypseeum/Lindigoticum/Ostrinum/Puniceum
  (3 565 100), Sinuous Tuber Albidum (3 425 600), Anemone Croceum (3 399 800),
  Fonticulua Fluctus (16 777 215).

## 8. Созданные файлы

* `exobiology_base_values.json` — вложенный: genus → species → value
* `exobiology_species_values.json` — плоский: `{"Aleoida Arcus": 7252500, ...}` (запрошенный формат)
* `exobiology_codex_keys.json` — `$Codex_Ent_*_Name;` → value
* `exobiology_report.md` — авто-сгенерированные таблицы и ранжирования
* `merge_values.py` — воспроизводимый скрипт слияния трёх источников
* `extract_bio_values.py` — извлечение значений из rulesets BioScan
