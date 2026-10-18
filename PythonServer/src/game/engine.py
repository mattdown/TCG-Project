"""Rules engine for vanilla units.

Every decision is a choice from legal_actions(), and step() applies one. Turn structure:
mulligan (each player once) → for each turn: ready, draw, then main-phase actions until
END_TURN. The first player to GameConfig.vp_to_win VP wins; a player who has to draw from
an empty deck loses.
"""
import copy
import random
from dataclasses import dataclass, field

from src.cards.schema import Card
from src.game.actions import Action, ActionType
from src.game.state import CardInstance, GameState, Phase, PlayerState, Zone
from src.game.terms import TERMS


@dataclass(frozen=True)
class GameConfig:
    hand_size: int = 7
    vp_to_win: int = 20
    max_turns: int = 100  # safety cap: the game is a draw after this many turns


@dataclass
class Move:
    uid: int
    owner: int
    source: Zone
    dest: Zone


@dataclass
class StepResult:
    """What one step changed, recorded by the rules as they apply it.

    The Unity client animates these and shows them as previews, so it never works out a result
    itself; recording them here keeps them from drifting from the rules.
    """
    damage: dict[int, int] = field(default_factory=dict)  # uid → damage dealt
    defeated: list[int] = field(default_factory=list)
    vp: dict[int, int] = field(default_factory=dict)  # player → VP gained
    energy_spent: dict[int, int] = field(default_factory=dict)  # player → energy exhausted to pay
    exhausted: list[int] = field(default_factory=list)  # units exhausted by acting
    readied: list[int] = field(default_factory=list)  # cards readied at the start of a turn
    moves: list[Move] = field(default_factory=list)


class Game:
    def __init__(self, deck_a: list[Card], deck_b: list[Card], seed: int | None = None,
                 first_player: int | None = None, config: GameConfig = GameConfig()):
        self.config = config
        self.rng = random.Random(seed)
        self._result: StepResult | None = None
        cards, players = [], []
        for owner, deck in enumerate((deck_a, deck_b)):
            uids = []
            for card in deck:
                uids.append(len(cards))
                cards.append(CardInstance(len(cards), card, owner, Zone.DECK))
            self.rng.shuffle(uids)
            players.append(PlayerState(deck=uids))
        first = self.rng.randrange(2) if first_player is None else first_player
        self.state = GameState(cards, players, first_player=first, active_player=first, decision_player=first)
        for p in range(2):
            for _ in range(config.hand_size):
                self._draw(p)

    # --- queries

    @property
    def is_over(self) -> bool:
        return self.state.phase == Phase.GAME_OVER

    def card(self, uid: int) -> CardInstance:
        return self.state.cards[uid]

    def ready_energy(self, player: int) -> int:
        return sum(not self.state.cards[u].exhausted for u in self.state.players[player].energy)

    def duel_targets(self, attacker_uid: int) -> list[int]:
        """Opposing units this unit may duel.

        Normally only exhausted units. Guard units can be dueled even while ready, and must be
        dueled first if any can be. Only Elusive units can duel Elusive units.
        """
        s = self.state
        attacker = s.cards[attacker_uid].card
        candidates = [uid for uid in s.players[1 - s.cards[attacker_uid].owner].play
                      if (s.cards[uid].exhausted or s.cards[uid].card.keyword("guard"))
                      and (not s.cards[uid].card.keyword("elusive") or attacker.keyword("elusive"))]
        guards = [uid for uid in candidates if s.cards[uid].card.keyword("guard")]
        return guards or candidates

    def duel_damage(self, attacker_uid: int, defender_uid: int) -> tuple[int, int]:
        """(damage to the attacker, damage to the defender). Duelist adds to the attacker's power;
        Armor reduces the damage each unit takes."""
        attacker, defender = self.card(attacker_uid).card, self.card(defender_uid).card
        to_defender = max(0, attacker.power + attacker.keyword("duelist") - defender.keyword("armor"))
        to_attacker = max(0, defender.power - attacker.keyword("armor"))
        return to_attacker, to_defender

    def legal_actions(self) -> list[Action]:
        s = self.state
        if s.phase == Phase.GAME_OVER:
            return []
        p = s.decision_player
        ps = s.players[p]
        if s.phase == Phase.MULLIGAN:
            return ([Action(ActionType.MULLIGAN, uid) for uid in ps.hand if uid not in ps.mulligan_marked]
                    + [Action(ActionType.KEEP_HAND)])

        actions = []
        ready_energy = self.ready_energy(p)
        for uid in ps.hand:
            card = s.cards[uid].card
            if card.energy_source and not ps.added_energy_this_turn:
                actions.append(Action(ActionType.ADD_ENERGY, uid))
            if card.cost <= ready_energy:
                actions.append(Action(ActionType.PLAY, uid))
        for uid in ps.play:
            unit = s.cards[uid]
            if unit.exhausted:
                continue
            if not unit.fresh:
                actions.append(Action(ActionType.SCORE, uid))
            if not unit.fresh or unit.card.keyword("charge"):
                actions.extend(Action(ActionType.DUEL, uid, t) for t in self.duel_targets(uid))
        actions.append(Action(ActionType.END_TURN))
        return actions

    # --- actions

    def step(self, action: Action, validate: bool = True, record: bool = False) -> StepResult | None:
        """Applies an action; with record=True, returns what it changed."""
        if validate and action not in self.legal_actions():
            raise ValueError(f"illegal action {action}")
        self._result = StepResult() if record else None
        try:
            self._apply(action)
        finally:
            result, self._result = self._result, None
        return result

    def _apply(self, action: Action):
        s = self.state
        p = s.decision_player
        ps = s.players[p]
        match action.type:
            case ActionType.MULLIGAN:
                ps.mulligan_marked.append(action.card)
            case ActionType.KEEP_HAND:
                self._keep_hand(p)
            case ActionType.ADD_ENERGY:
                self._move(action.card, Zone.ENERGY)
                ps.added_energy_this_turn = True
            case ActionType.PLAY:
                self._pay(p, self.card(action.card).card.cost)
                self._move(action.card, Zone.PLAY)
                self.card(action.card).fresh = True
            case ActionType.SCORE:
                unit = self.card(action.card)
                unit.exhausted = True
                ps.vp += unit.card.score
                if self._result:
                    self._result.exhausted.append(unit.uid)
                    self._result.vp[p] = unit.card.score
                if ps.vp >= self.config.vp_to_win:
                    self._end_game(p)
            case ActionType.DUEL:
                self._duel(action.card, action.target)
            case ActionType.END_TURN:
                self._begin_turn(1 - p)

    def clone(self) -> "Game":
        # Card definitions are immutable, so share them instead of copying.
        memo = {id(c.card): c.card for c in self.state.cards}
        return copy.deepcopy(self, memo)

    # --- rules

    def _keep_hand(self, p: int):
        ps = self.state.players[p]
        marked = ps.mulligan_marked
        for uid in marked:
            ps.hand.remove(uid)
            ps.deck.insert(0, uid)
            self.card(uid).zone = Zone.DECK
            if self._result:
                self._result.moves.append(Move(uid, p, Zone.HAND, Zone.DECK))
        for _ in marked:
            self._draw(p)
        self.rng.shuffle(ps.deck)
        ps.mulligan_marked = []
        ps.mulligan_done = True
        if not self.state.players[1 - p].mulligan_done:
            self.state.decision_player = 1 - p
        else:
            self._begin_turn(self.state.first_player)

    def _begin_turn(self, p: int):
        s = self.state
        s.active_player = s.decision_player = p
        s.phase = Phase.MAIN
        s.turn += 1
        if s.turn > self.config.max_turns:
            self._end_game(None)
            return
        ps = s.players[p]
        ps.added_energy_this_turn = False
        for uid in ps.play + ps.energy:
            if self._result and self.card(uid).exhausted:
                self._result.readied.append(uid)
            self.card(uid).exhausted = False
            self.card(uid).fresh = False
        if s.turn > 1:  # the first player skips their first draw
            self._draw(p)

    def _draw(self, p: int):
        ps = self.state.players[p]
        if not ps.deck:
            self._end_game(1 - p)
            return
        uid = ps.deck.pop()
        ps.hand.append(uid)
        self.card(uid).zone = Zone.HAND
        if self._result:
            self._result.moves.append(Move(uid, p, Zone.DECK, Zone.HAND))

    def _pay(self, p: int, cost: int):
        ready = [u for u in self.state.players[p].energy if not self.card(u).exhausted]
        for uid in ready[:cost]:
            self.card(uid).exhausted = True
        if self._result:
            self._result.energy_spent[p] = min(cost, len(ready))

    def _duel(self, attacker_uid: int, defender_uid: int):
        attacker, defender = self.card(attacker_uid), self.card(defender_uid)
        to_attacker, to_defender = self.duel_damage(attacker_uid, defender_uid)
        attacker.exhausted = True
        attacker.damage += to_attacker
        defender.damage += to_defender
        if self._result:
            self._result.exhausted.append(attacker_uid)
            self._result.damage[attacker_uid] = to_attacker
            self._result.damage[defender_uid] = to_defender
        for unit in (attacker, defender):
            if unit.damage >= unit.card.health:
                if self._result:
                    self._result.defeated.append(unit.uid)
                self._move(unit.uid, Zone.DISCARD)

    def _move(self, uid: int, zone: Zone):
        c = self.card(uid)
        if self._result:
            self._result.moves.append(Move(uid, c.owner, c.zone, zone))
        zones = self._zone_lists(c.owner)
        zones[c.zone].remove(uid)
        zones[zone].append(uid)
        c.zone = zone
        c.exhausted = c.fresh = False
        c.damage = 0

    def _zone_lists(self, p: int) -> dict[Zone, list[int]]:
        ps = self.state.players[p]
        return {Zone.DECK: ps.deck, Zone.HAND: ps.hand, Zone.PLAY: ps.play, Zone.ENERGY: ps.energy, Zone.DISCARD: ps.discard}

    def _end_game(self, winner: int | None):
        self.state.phase = Phase.GAME_OVER
        self.state.winner = winner


def describe_action(game: Game, action: Action) -> str:
    """Short player-facing description, e.g. for the Unity client or logs."""
    name = game.card(action.card).card.name if action.card is not None else None
    match action.type:
        case ActionType.MULLIGAN:
            return f"Put back {name}"
        case ActionType.KEEP_HAND:
            return "Keep hand"
        case ActionType.ADD_ENERGY:
            return f"Add {name} as {TERMS['energy']}"
        case ActionType.PLAY:
            return f"Play {name}"
        case ActionType.SCORE:
            return f"{TERMS['score'].capitalize()} with {name}"
        case ActionType.DUEL:
            return f"{TERMS['duel'].capitalize()}: {name} → {game.card(action.target).card.name}"
        case ActionType.END_TURN:
            return "End turn"
