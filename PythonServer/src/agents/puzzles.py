"""Tactical puzzles: positions from real games where the player to move can win this turn.

A diagnostic for the agent (does it find lethal?) and, later, a source of training targets.
Positions come from recorded games: each is stored as the decks, the seed and the moves that
reach it, so it replays exactly. At the start of each turn an exact search (`find_lethal`) looks
for a sequence of the player's moves that wins before the turn ends. A line only counts if it
works whatever the player can't see: it's replayed on copies with their deck and the opponent's
cards re-dealt (`Game.determinize`), and lines that need the opponent to choose something are
skipped. So a puzzle never asks the agent to guess.

A puzzle is "face" when attacking the hero with every unit that can is enough, and "tactical"
when it takes more: playing cards first, trading off a Guard, using an ability, ordering.
"""
import random
from dataclasses import asdict, dataclass

from src.agents.base import Agent
from src.cards.schema import Card, CardSet
from src.game.actions import Action, ActionType
from src.game.engine import Game
from src.game.state import Phase

ORDER = {ActionType.ATTACK_HERO: 0, ActionType.PLAY: 1, ActionType.ATTACK: 2, ActionType.SPARE_SPORE: 3}


@dataclass
class Puzzle:
    cards: str  # the card set's name
    decks: tuple[list[str], list[str]]  # card ids, in the order the game was dealt from
    seed: int
    first_player: int
    moves: list[int]  # indexes into legal_actions() that reach the position
    player: int  # who can win this turn
    line: list[dict]  # one winning line (Action.to_dict)
    face: bool  # attacking the hero with everything is enough

    def position(self, card_set: CardSet) -> Game:
        game = Game(*([card_set[i] for i in deck] for deck in self.decks), seed=self.seed,
                    first_player=self.first_player)
        for i in self.moves:
            game.step(game.legal_actions()[i], validate=False)
        return game

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Puzzle":
        return cls(**{**d, "decks": tuple(d["decks"])})


def action_from_dict(d: dict) -> Action:
    return Action(ActionType[d["type"].upper()], d["card"], d["target"], d["option"])


def turn_start(game: Game, last_turn: int) -> bool:
    """The first decision of a player's main phase (after any start-of-turn abilities)."""
    s = game.state
    return s.turn != last_turn and s.phase == Phase.MAIN and s.decision_player == s.active_player and not s.pending


def find_lethal(game: Game, budget: int = 20_000) -> tuple[list[Action] | None, bool]:
    """A sequence of the decision player's moves that wins this turn, searched exactly (depth first,
    remembering positions already ruled out), and whether the search finished within `budget`
    positions. The line is None if there's none, or none found before the budget ran out."""
    me = game.state.decision_player
    failed: set = set()
    nodes = 0

    def search(g: Game) -> list[Action] | None:
        nonlocal nodes
        nodes += 1
        if nodes > budget:
            return None
        if g.is_over:
            return [] if g.state.winner == me else None
        if g.state.active_player != me or g.state.decision_player != me:
            return None  # the turn ended, or the opponent must choose: not a sure line
        key = _key(g) if not g.state.pending else None
        if key is not None and key in failed:
            return None
        actions = sorted(g.legal_actions(), key=lambda a: ORDER.get(a.type, 4 if a.type != ActionType.END_TURN else 5))
        for action in actions:
            child = g.clone()
            child.step(action, validate=False)
            line = search(child)
            if line is not None:
                return [action, *line]
        if key is not None and nodes <= budget:
            failed.add(key)
        return None

    line = search(game.clone())
    return line, line is not None or nodes <= budget


def sure(game: Game, line: list[Action], card_set: CardSet, worlds: int = 4, seed: int = 0) -> bool:
    """Whether `line` wins in every re-deal of what the player can't see (and with new random numbers)."""
    me = game.state.decision_player
    rng = random.Random(seed)
    for _ in range(worlds):
        g = game.clone()
        g.determinize(me, rng, card_set)
        for action in line:
            if g.is_over or g.state.decision_player != me or action not in g.legal_actions():
                return False
            g.step(action, validate=False)
        if g.state.winner != me:
            return False
    return True


def face_line(game: Game) -> list[Action]:
    """Attack the hero with every unit that can, nothing else (first choice for any decision)."""
    g, me, line = game.clone(), game.state.decision_player, []
    while not g.is_over and g.state.decision_player == me and g.state.active_player == me:
        actions = g.legal_actions()
        face = [a for a in actions if a.type == ActionType.ATTACK_HERO]
        if g.state.pending:
            action = actions[0]
        elif face:
            action = face[0]
        else:
            break
        line.append(action)
        g.step(action, validate=False)
    return line if g.state.winner == me else []


def record_game(agents: tuple[Agent, Agent], decks: tuple[list[Card], list[Card]], seed: int, first_player: int,
                card_set: CardSet, budget: int = 20_000) -> tuple[list[Puzzle], int, int]:
    """Plays a game and returns a puzzle for every turn that started with a sure lethal, the number
    of turns checked and the number whose search ran out of budget (lethal unknown)."""
    game = Game(*decks, seed=seed, first_player=first_player)
    moves, puzzles, last_turn, turns, unfinished = [], [], 0, 0, 0
    while not game.is_over:
        if turn_start(game, last_turn):
            last_turn = game.state.turn
            line, finished = find_lethal(game, budget)
            turns += 1
            unfinished += not finished
            if line is not None and sure(game, line, card_set):
                face = bool(face_line(game)) and sure(game, face_line(game), card_set)
                puzzles.append(Puzzle(card_set.name, tuple([c.id for c in d] for d in decks), seed, first_player,
                                      list(moves), game.state.decision_player, [a.to_dict() for a in line], face))
        action = agents[game.state.decision_player].choose(game)
        moves.append(game.legal_actions().index(action))
        game.step(action, validate=False)
    return puzzles, turns, unfinished


def solves(agent: Agent, puzzle: Puzzle, card_set: CardSet, opponent: Agent) -> bool:
    """Whether `agent` wins before its turn ends; `opponent` makes any choices it has in that turn."""
    game = puzzle.position(card_set)
    me = puzzle.player
    while not game.is_over and game.state.active_player == me:
        mover = agent if game.state.decision_player == me else opponent
        game.step(mover.choose(game), validate=False)
    return game.state.winner == me


def _key(g: Game) -> tuple:
    """Everything a move this turn can change, for spotting the same position reached in another order."""
    s = g.state
    return (tuple((c.zone, c.damage, c.attacked, c.fresh, c.revealed) for c in s.cards),
            tuple((tuple(p.hand), tuple(p.deck), tuple(p.play), tuple(p.discard), p.health, p.mana, p.spare_spore,
                   p.fatigue) for p in s.players),
            tuple((e.kind, e.uid, e.stat, e.keyword, e.value, e.expires_turn, e.source) for e in s.effects),
            s.turn_actions, s.turn_abilities)
