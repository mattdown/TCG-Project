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


@dataclass(frozen=True)
class Action:
    type: ActionType
    card: int | None = None  # uid of the card acting or being played
    target: int | None = None  # uid of the target, if any

    def to_dict(self) -> dict:
        return {"type": self.type.name.lower(), "card": self.card, "target": self.target}
