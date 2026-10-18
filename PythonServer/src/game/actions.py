from dataclasses import dataclass
from enum import IntEnum


class ActionType(IntEnum):
    MULLIGAN = 0  # mark a card in hand to put back
    KEEP_HAND = 1  # finish the mulligan
    ADD_ENERGY = 2
    PLAY = 3
    SCORE = 4
    DUEL = 5
    END_TURN = 6
    ACTIVATE = 7  # use a ⟳ ability: card = the unit, option = which of its abilities
    CHOOSE_TARGET = 8  # while an ability resolves: card = its source, target = the chosen card
    ACCEPT = 9  # "you may …": yes
    DECLINE = 10  # "you may …": no
    CHOOSE_OPTION = 11  # "choose one": option = which


@dataclass(frozen=True)
class Action:
    type: ActionType
    card: int | None = None  # uid of the card acting or being played
    target: int | None = None  # uid of the target, if any
    option: int | None = None  # ability index (ACTIVATE) or option index (CHOOSE_OPTION)

    def to_dict(self) -> dict:
        return {"type": self.type.name.lower(), "card": self.card, "target": self.target, "option": self.option}
