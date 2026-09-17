"""Commander ranks: names, and how far each ladder goes.

The journal reports ranks as bare indexes (``Rank.Combat: 3``) and progress to
the next step as a percentage (``Progress.Combat: 96``). Neither carries a name,
so both tables live here.

Odyssey added Elite I-V to all six pilot ladders, taking them from nine steps
to fourteen; CQC included, despite the widespread belief that it stops at Elite.
Empire and Federation were always fifteen steps, ending at King and Admiral.

``Progress`` is NOT a way to detect a topped-out ladder: a commander can sit at
100 percent on rank 0 of a superpower while waiting for a promotion mission. The
index has to be compared against :data:`MAX_RANKS`.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Journal field name for each track.
TRACKS = ("Combat", "Trade", "Explore", "Soldier", "Exobiologist", "Empire", "Federation", "CQC")

#: Where each ladder ends. Verified against the journal indexes and the rank
#: tables EDDI and FDevIDs carry: the six pilot ladders run to Elite V (13) and
#: the two superpower ones to King and Admiral (14).
MAX_RANKS = {track: 13 for track in TRACKS}
MAX_RANKS["Empire"] = 14
MAX_RANKS["Federation"] = 14


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
        return MAX_RANKS.get(self.key, len(self.names) - 1)

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
        "Champion", "Hero", "Legend", "Elite", "Elite I", "Elite II", "Elite III", "Elite IV", "Elite V")
_CQC_RU = ("Беспомощный", "Почти беспомощный", "Любитель", "Полупрофессионал", "Профессионал",
           "Чемпион", "Герой", "Легенда", "Элита", "Элита I", "Элита II", "Элита III", "Элита IV", "Элита V")

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
#:
#: This is every ladder, superpowers included. It previously left the two
#: superpowers out on the grounds that their ranks are always on screen anyway
#: -- but ``Promotion`` is the only event that reports a rank changing mid
#: session, so skipping them there meant a promotion to Count or Admiral was
#: neither announced nor stored, and the HUD kept showing the old rank until
#: the game was restarted. Two of the three promotions in the journals we test
#: against are Imperial, so this was not a rare corner.
ANNOUNCED = TRACKS


def ladder(track: str) -> Ladder | None:
    return LADDERS.get(track)
