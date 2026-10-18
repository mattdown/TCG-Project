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
class ActiveEffect:
    """A lasting change made by an ability.

    It ends when turn `expires_turn` ends, when its `source` leaves play (for "while this
    card is in play"), or when the affected card leaves play.
    """
    kind: str  # "stat" | "keyword" | "cant_ready" | "barred" (can't score or use ⟳ abilities)
    uid: int
    stat: str | None = None
    keyword: str | None = None
    value: int = 0
    expires_turn: int | None = None
    source: int | None = None


@dataclass
class Frame:
    """A pending ability: being resolved, or waiting for a decision at its current node."""
    source: int  # uid of the card whose ability it is
    controller: int
    ability: int  # index into the card's compiled abilities
    node: int = 0
    bindings: dict[str, list[int]] = field(default_factory=dict)  # name → chosen uids


@dataclass
class Continuation:
    """Engine work that waits for the abilities above it on the stack to resolve first:
    duel damage after "when this attacks" triggers, the end of a turn after "end of turn"
    triggers, the draw after "start of turn" triggers."""
    kind: str  # "duel" | "end_turn" | "draw"
    args: tuple = ()


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
    pending: list[Frame | Continuation] = field(default_factory=list)  # the stack; top is the end
    queue: list[Frame] = field(default_factory=list)  # triggered, waiting to go on the stack
    effects: list[ActiveEffect] = field(default_factory=list)
    duel: tuple[int, int] | None = None  # (attacker, defender) while duel damage is worked out
