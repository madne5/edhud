"""Short-lived lines in the bar: facts in, rendered text out.

The state layer records what happened -- a material was picked up, docking was
refused -- and the overlay decides how it looks, because every switch that shapes
the wording (show the rarity, show the running total, name the material's
category) lives in the configuration and the state layer has no business reading
it.

So a notice is a value carrying facts, and it renders itself only when handed a
:class:`NoticeStyle`: the labels, colours and switches from the configuration.
Rendering in one direction keeps the two sides from growing into each other,
which is how the old notification centre became impossible to remove.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The game's own reasons, as the journal spells them. Shown to a commander in
#: Russian where the meaning is unambiguous, and left in the game's spelling
#: where it is not -- guessing at a reason would be worse than quoting one.
DOCKING_REASONS = {
    "Distance": "слишком далеко от станции",
    "NoSpace": "все площадки заняты",
    "TooLarge": "корабль слишком большой для площадки",
    "Hostile": "станция враждебна",
    "Offline": "стыковка отключена",
    "ActiveFighter": "сначала верните истребитель на борт",
}


@dataclass(frozen=True, slots=True)
class Rendered:
    """One notice, ready to draw: the text, its glyph and its colour."""

    text: str
    glyph: str = "signal"
    colour: str = ""


@dataclass(frozen=True, slots=True)
class NoticeStyle:
    """The slice of the configuration a notice needs to render itself."""

    #: Material category symbol -> the word to show: "Сырьевой" and so on.
    category_labels: dict[str, str] = field(default_factory=dict)
    #: Material category symbol -> colour.
    category_colours: dict[str, str] = field(default_factory=dict)
    rarity_label: str = "Редкость"
    total_label: str = "Всего"
    show_rarity: bool = True
    show_total: bool = True
    #: Palette roles, for notices that are not about materials.
    foreground: str = ""
    accent: str = ""
    danger: str = ""
    warning: str = ""
    success: str = ""


@dataclass(frozen=True, slots=True)
class DockingNotice:
    """Docking was refused, and why."""

    station: str = ""
    reason: str = ""

    def render(self, style: NoticeStyle) -> Rendered:
        where = self.station or "станция"
        why = DOCKING_REASONS.get(self.reason, self.reason or "причина не указана")
        return Rendered(
            text=f"{where}: стыковка запрещена — {why}",
            glyph="warning",
            colour=style.warning or style.danger,
        )
