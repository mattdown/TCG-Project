from dataclasses import dataclass
from enum import IntEnum


class ActionType(IntEnum):
    MULLIGAN = 0  # mark a card in hand to put back
    KEEP_HAND = 1  # finish the mulligan
    PLAY = 2
    ATTACK = 3  # card = the attacker, target = the enemy unit
    ATTACK_HERO = 4  # card = the attacker
    END_TURN = 5
    SPARE_SPORE = 6  # the second player's one-off +1 mana
    ACTIVATE = 7  # use a ⟳ ability instead of attacking (not generated in rules v2; kept for later)
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
