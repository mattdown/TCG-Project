from dataclasses import dataclass, field
from enum import IntEnum

from src.cards.schema import Card


class Zone(IntEnum):
    DECK = 0
    HAND = 1
    PLAY = 2
    DISCARD = 3


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
    exhausted: bool = False  # has attacked (or been stopped from attacking) this turn
    fresh: bool = False  # entered play this turn: can't attack yet, unless it has Charge
    damage: int = 0
    revealed: bool = False  # has attacked, so Elusive no longer protects it


@dataclass
class ActiveEffect:
    """A lasting change made by an ability.

    It ends when turn `expires_turn` ends, when its `source` leaves play (for "while this
    card is in play"), or when the affected card leaves play.
    """
    kind: str  # "stat" | "keyword" | "freeze" (can't attack on its owner's next turn)
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
    attack damage after "when this attacks" triggers, the end of a turn after "end of turn"
    triggers, the draw after "start of turn" triggers."""
    kind: str  # "attack" (attacker, defender uid or None for the hero) | "end_turn" | "draw"
    args: tuple = ()


@dataclass
class PlayerState:
    deck: list[int]  # card uids, top of the deck is the end of the list
    hand: list[int] = field(default_factory=list)
    play: list[int] = field(default_factory=list)
    discard: list[int] = field(default_factory=list)
    health: int = 30  # the hero's health left
    crystals: int = 0  # mana crystals: one more each turn, up to GameConfig.max_mana
    mana: int = 0  # unspent mana this turn
    fatigue: int = 0  # damage the next draw from an empty deck deals
    spare_spore: int = 0  # the second player's one-off +1 mana: how many are left
    aspect: str | None = None  # the hero's aspect: the deck's aspect, None if it has only neutral cards
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
    duel: tuple[int, int | None] | None = None  # (attacker, defender; None for the hero) while attack damage is worked out
