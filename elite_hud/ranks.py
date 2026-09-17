"""Commander ranks: names, and how far each ladder goes.

The journal reports ranks as bare indexes (``Rank.Combat: 3``) and progress to
the next step as a percentage (``Progress.Combat: 96``). Neither carries a name,
so both tables live here.

Combat, Trade and Explore gained Elite I-V in Odyssey, which took them from
nine steps to fourteen. The other ladders stop where they always did.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Journal field name for each track.
TRACKS = ("Combat", "Trade", "Explore", "Soldier", "Exobiologist", "Empire", "Federation", "CQC")


@dataclass(frozen=True, slots=True)
class Ladder:
    key: str
    #: English names, indexed by the journal's rank number.
    names: tuple[str, ...]
    #: Russian names, from the game's own localisation.
    names_ru: tuple[str, ...]
    #: Single glyph drawn next to the progress.
    glyph: str

    @property
    def max_rank(self) -> int:
        return len(self.names) - 1

    def name(self, rank: int, *, russian: bool = True) -> str:
        names = self.names_ru if russian else self.names
        if 0 <= rank < len(names):
            return names[rank]
        return names[-1] if names else str(rank)

    def is_max(self, rank: int) -> bool:
        return rank >= self.max_rank


_COMBAT = ("Harmless", "Mostly Harmless", "Novice", "Competent", "Expert", "Master",
           "Dangerous", "Deadly", "Elite", "Elite I", "Elite II", "Elite III", "Elite IV", "Elite V")
_COMBAT_RU = ("Безвредный", "Почти безвредный", "Новичок", "Компетентный", "Опытный", "Мастер",
              "Опасный", "Смертельный", "Элита", "Элита I", "Элита II", "Элита III", "Элита IV", "Элита V")

_TRADE = ("Penniless", "Mostly Penniless", "Peddler", "Dealer", "Merchant", "Broker",
          "Entrepreneur", "Tycoon", "Elite", "Elite I", "Elite II", "Elite III", "Elite IV", "Elite V")
_TRADE_RU = ("Без гроша", "Почти без гроша", "Лоточник", "Торговец", "Купец", "Брокер",
             "Предприниматель", "Магнат", "Элита", "Элита I", "Элита II", "Элита III", "Элита IV", "Элита V")

_EXPLORE = ("Aimless", "Mostly Aimless", "Scout", "Surveyor", "Trailblazer", "Pathfinder",
            "Ranger", "Pioneer", "Elite", "Elite I", "Elite II", "Elite III", "Elite IV", "Elite V")
_EXPLORE_RU = ("Бесцельный", "Почти бесцельный", "Разведчик", "Землемер", "Первопроходец", "Следопыт",
               "Рейнджер", "Пионер", "Элита", "Элита I", "Элита II", "Элита III", "Элита IV", "Элита V")

_SOLDIER = ("Defenceless", "Mostly Defenceless", "Rookie", "Soldier", "Gunslinger", "Warrior",
            "Gladiator", "Deadeye", "Elite", "Elite I", "Elite II", "Elite III", "Elite IV", "Elite V")
_SOLDIER_RU = ("Беззащитный", "Почти беззащитный", "Новобранец", "Солдат", "Стрелок", "Воин",
               "Гладиатор", "Снайпер", "Элита", "Элита I", "Элита II", "Элита III", "Элита IV", "Элита V")

_EXOBIOLOGIST = ("Directionless", "Mostly Directionless", "Compiler", "Collector", "Cataloguer",
                 "Taxonomist", "Ecologist", "Geneticist", "Elite", "Elite I", "Elite II", "Elite III",
                 "Elite IV", "Elite V")
_EXOBIOLOGIST_RU = ("Бессистемный", "Почти бессистемный", "Собиратель", "Коллекционер", "Каталогизатор",
                    "Таксономист", "Эколог", "Генетик", "Элита", "Элита I", "Элита II", "Элита III",
                    "Элита IV", "Элита V")

_FEDERATION = ("None", "Recruit", "Cadet", "Midshipman", "Petty Officer", "Chief Petty Officer",
               "Warrant Officer", "Ensign", "Lieutenant", "Lieutenant Commander", "Post Commander",
               "Post Captain", "Rear Admiral", "Vice Admiral", "Admiral")
_FEDERATION_RU = ("Нет", "Новобранец", "Кадет", "Гардемарин", "Мичман", "Главный мичман",
                  "Уорент-офицер", "Прапорщик", "Лейтенант", "Лейтенант-коммандер", "Коммандер",
                  "Капитан", "Контр-адмирал", "Вице-адмирал", "Адмирал")

_EMPIRE = ("None", "Outsider", "Serf", "Master", "Squire", "Knight", "Lord", "Baron", "Viscount",
           "Count", "Earl", "Marquis", "Duke", "Prince", "King")
_EMPIRE_RU = ("Нет", "Чужак", "Крепостной", "Господин", "Оруженосец", "Рыцарь", "Лорд", "Барон", "Виконт",
              "Граф", "Эрл", "Маркиз", "Герцог", "Принц", "Король")

_CQC = ("Helpless", "Mostly Helpless", "Amateur", "Semi Professional", "Professional",
        "Champion", "Hero", "Legend", "Elite")
_CQC_RU = ("Беспомощный", "Почти беспомощный", "Любитель", "Полупрофессионал", "Профессионал",
           "Чемпион", "Герой", "Легенда", "Элита")

LADDERS: dict[str, Ladder] = {
    "Combat": Ladder("Combat", _COMBAT, _COMBAT_RU, "crossed_swords"),
    "Trade": Ladder("Trade", _TRADE, _TRADE_RU, "scales"),
    "Explore": Ladder("Explore", _EXPLORE, _EXPLORE_RU, "compass"),
    "Soldier": Ladder("Soldier", _SOLDIER, _SOLDIER_RU, "rifle"),
    "Exobiologist": Ladder("Exobiologist", _EXOBIOLOGIST, _EXOBIOLOGIST_RU, "leaf"),
    "Empire": Ladder("Empire", _EMPIRE, _EMPIRE_RU, "empire"),
    "Federation": Ladder("Federation", _FEDERATION, _FEDERATION_RU, "federation"),
    "CQC": Ladder("CQC", _CQC, _CQC_RU, "arena"),
}

#: The two superpower ladders are shown all the time, the rest only on change.
SUPERPOWERS = ("Empire", "Federation")

#: Ranks worth announcing when they change.
ANNOUNCED = ("Combat", "Trade", "Explore", "Soldier", "Exobiologist", "CQC")


def ladder(track: str) -> Ladder | None:
    return LADDERS.get(track)
