from dataclasses import dataclass, field
from enum import IntEnum

from src.cards.schema import Card


class Zone(IntEnum):
    DECK = 0
    HAND = 1
    PLAY = 2
    ENERGY = 3
    DISCARD = 4


class Phase(IntEnum):
    MULLIGAN = 0
    MAIN = 1
    GAME_OVER = 2


@dataclass
class CardInstance:
    uid: int
    card: Card
    owner: int
    zone: Zone
    exhausted: bool = False
    fresh: bool = False  # entered play this turn: can't score or duel
    damage: int = 0


@dataclass
class PlayerState:
    deck: list[int]  # card uids, top of the deck is the end of the list
    hand: list[int] = field(default_factory=list)
    play: list[int] = field(default_factory=list)
    energy: list[int] = field(default_factory=list)
    discard: list[int] = field(default_factory=list)
    vp: int = 0
    added_energy_this_turn: bool = False
    mulligan_done: bool = False
    mulligan_marked: list[int] = field(default_factory=list)


@dataclass
class GameState:
    cards: list[CardInstance]  # indexed by uid
    players: list[PlayerState]
    first_player: int
    active_player: int  # whose turn it is
    decision_player: int  # who must choose next (differs from active_player during the mulligan)
    turn: int = 0  # counts every player's turn; turn 1 is the first player's first turn
    phase: Phase = Phase.MULLIGAN
    winner: int | None = None  # None with phase GAME_OVER means a draw
