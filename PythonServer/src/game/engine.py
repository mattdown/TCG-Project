"""Rules engine.

Every decision is a choice from legal_actions(), and step() applies one. Turn structure:
mulligan (each player once) → for each turn: ready, start-of-turn abilities, draw, then
main-phase actions until END_TURN, then end-of-turn abilities. The first player to
GameConfig.vp_to_win VP wins; a player who has to draw from an empty deck loses.

Abilities (docs/technical-plan.md section 3) are compiled to decision graphs and resolved on a
stack (state.pending). Triggered abilities wait in state.queue until no ability is part-way
through resolving, then go on the stack. Whenever resolution reaches a choose, may or
choose-one node, the engine stops and that choice becomes the next decision.
"""
import copy
import random
from dataclasses import dataclass, field

from src.cards.abilities import Renderer, render
from src.cards.schema import Card
from src.game.actions import Action, ActionType
from src.game.decision_graph import CompiledAbility, Node, compiled
from src.game.state import ActiveEffect, CardInstance, Continuation, Frame, GameState, Phase, PlayerState, Zone
from src.game.terms import KEYWORDS, TERMS

ZONES = {"play": Zone.PLAY, "hand": Zone.HAND, "discard": Zone.DISCARD}


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
    vp: dict[int, int] = field(default_factory=dict)  # player → VP gained (negative if lost)
    energy_spent: dict[int, int] = field(default_factory=dict)  # player → energy exhausted to pay
    exhausted: list[int] = field(default_factory=list)  # units exhausted by acting
    readied: list[int] = field(default_factory=list)  # cards readied at the start of a turn or by an ability
    moves: list[Move] = field(default_factory=list)
    abilities: list[int] = field(default_factory=list)  # sources of abilities that started resolving
    healed: dict[int, int] = field(default_factory=dict)  # uid → damage removed
    effects: list[ActiveEffect] = field(default_factory=list)  # lasting changes abilities made


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

    # ------------------------------------------------------------------ queries

    @property
    def is_over(self) -> bool:
        return self.state.phase == Phase.GAME_OVER

    def card(self, uid: int) -> CardInstance:
        return self.state.cards[uid]

    def ready_energy(self, player: int) -> int:
        return sum(not self.state.cards[u].exhausted for u in self.state.players[player].energy)

    def stat(self, uid: int, name: str) -> int:
        """Power, health or score, including abilities' bonuses (never below 0)."""
        c = self.card(uid)
        value = getattr(c.card, name)
        if c.zone == Zone.PLAY:
            value += sum(e.value for e in self._effects_on(uid) if e.kind == "stat" and e.stat == name)
            value += sum(self._modifier_amount(m, src, ctrl) for src, ctrl, m in self._statics_on(uid)
                         if m.get("stat") == name)
        return max(value, 0)

    def keyword(self, uid: int, name: str) -> int:
        """The keyword's value including ones granted by abilities; 0 if the card doesn't have it."""
        c = self.card(uid)
        value = c.card.keyword(name)
        if c.zone == Zone.PLAY:
            value += sum(e.value for e in self._effects_on(uid) if e.kind == "keyword" and e.keyword == name)
            value += sum(m.get("value", 1) for _, _, m in self._statics_on(uid) if m.get("keyword") == name)
        return value if KEYWORDS[name] else min(value, 1)

    def cant_ready(self, uid: int) -> bool:
        """An ability stops this card readying at the start of its owner's next turn."""
        return any(e.uid == uid and e.kind == "cant_ready" for e in self.state.effects)

    def barred(self, uid: int) -> bool:
        """An ability stops this unit scoring or using ⟳ abilities this turn."""
        return self._barred(uid)

    def play_cost(self, uid: int) -> int:
        c = self.card(uid)
        reduction = 0
        for src, ctrl, modifier, condition in self._statics():
            if ("cost_reduction" in modifier and ctrl == c.owner and self._condition(condition, ctrl, src)
                    and self.matches(uid, {**modifier["filter"], "zone": "hand", "type": "any"}, ctrl, src)):
                reduction += modifier["cost_reduction"]
        return max(c.card.cost - reduction, 0)

    def duel_targets(self, attacker_uid: int) -> list[int]:
        """Opposing units this unit may duel.

        Normally only exhausted units. Guard units can be dueled even while ready, and must be
        dueled first if any can be. Only Elusive units can duel Elusive units.
        """
        s = self.state
        elusive = self.keyword(attacker_uid, "elusive")
        candidates = [uid for uid in s.players[1 - s.cards[attacker_uid].owner].play
                      if (s.cards[uid].exhausted or self.keyword(uid, "guard"))
                      and (not self.keyword(uid, "elusive") or elusive)]
        guards = [uid for uid in candidates if self.keyword(uid, "guard")]
        return guards or candidates

    def duel_damage(self, attacker_uid: int, defender_uid: int) -> tuple[int, int]:
        """(damage to the attacker, damage to the defender). Duelist adds to the attacker's power;
        Armor reduces the damage each unit takes. Abilities that apply "while attacking" or
        "while defending" count."""
        previous, self.state.duel = self.state.duel, (attacker_uid, defender_uid)
        try:
            attack = self.stat(attacker_uid, "power") + self.keyword(attacker_uid, "duelist")
            to_defender = max(0, attack - self.keyword(defender_uid, "armor"))
            to_attacker = max(0, self.stat(defender_uid, "power") - self.keyword(attacker_uid, "armor"))
        finally:
            self.state.duel = previous
        return to_attacker, to_defender

    def matches(self, uid: int, f: dict, controller: int, source: int | None) -> bool:
        """Whether a card matches an ability's filter. "you" means the ability's controller."""
        c = self.card(uid)
        owner = f.get("owner", "any")
        return (c.zone == ZONES[f.get("zone", "play")]
                and (f.get("type", "unit") == "any" or c.card.type == f.get("type", "unit"))
                and (owner == "any" or (c.owner == controller) == (owner == "you"))
                and ("trait" not in f or f["trait"] in c.card.traits)
                and (not f.get("damaged") or c.damage > 0)
                and ("exhausted" not in f or c.exhausted == f["exhausted"])
                and ("cost_max" not in f or c.card.cost <= f["cost_max"])
                and ("keyword" not in f or self.keyword(uid, f["keyword"]) > 0)
                and (not f.get("not_this") or uid != source))

    def candidates(self, f: dict, controller: int, source: int | None) -> list[int]:
        zone = ZONES[f.get("zone", "play")]
        uids = [u for ps in self.state.players for u in self._zone_lists_of(ps)[zone]]
        return [u for u in uids if self.matches(u, f, controller, source)]

    def pending_decision(self) -> tuple[Frame, Node] | None:
        """The ability and node waiting for a decision, if any."""
        if not self.state.pending or not isinstance(self.state.pending[-1], Frame):
            return None
        frame = self.state.pending[-1]
        return frame, self._ability(frame).nodes[frame.node]

    def legal_actions(self) -> list[Action]:
        s = self.state
        if s.phase == Phase.GAME_OVER:
            return []
        p = s.decision_player
        ps = s.players[p]
        if s.phase == Phase.MULLIGAN:
            return ([Action(ActionType.MULLIGAN, uid) for uid in ps.hand if uid not in ps.mulligan_marked]
                    + [Action(ActionType.KEEP_HAND)])
        if s.pending:
            return self._decision_actions()

        actions = []
        ready_energy = self.ready_energy(p)
        for uid in ps.hand:
            card = s.cards[uid].card
            if card.energy_source and not ps.added_energy_this_turn:
                actions.append(Action(ActionType.ADD_ENERGY, uid))
            if self.play_cost(uid) <= ready_energy:
                actions.append(Action(ActionType.PLAY, uid))
        for uid in ps.play:
            unit = s.cards[uid]
            if unit.exhausted:
                continue
            if not unit.fresh and not self._barred(uid):
                actions.append(Action(ActionType.SCORE, uid))
                actions.extend(Action(ActionType.ACTIVATE, uid, option=i) for i in self._activatable(uid))
            if not unit.fresh or self.keyword(uid, "charge"):
                actions.extend(Action(ActionType.DUEL, uid, t) for t in self.duel_targets(uid))
        actions.append(Action(ActionType.END_TURN))
        return actions

    # ------------------------------------------------------------------ actions

    def step(self, action: Action, validate: bool = True, record: bool = False) -> StepResult | None:
        """Applies an action; with record=True, returns what it changed."""
        if validate and action not in self.legal_actions():
            raise ValueError(f"illegal action {action}")
        self._result = StepResult() if record else None
        try:
            self._apply(action)
            self._resolve()
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
                self._play(p, action.card)
            case ActionType.SCORE:
                unit = self.card(action.card)
                unit.exhausted = True
                if self._result:
                    self._result.exhausted.append(unit.uid)
                self._gain_vp(p, self.stat(unit.uid, "score"))
                self._trigger(action.card, "on_score")
            case ActionType.DUEL:
                self.card(action.card).exhausted = True
                if self._result:
                    self._result.exhausted.append(action.card)
                s.pending.append(Continuation("duel", (action.card, action.target)))
                self._trigger(action.card, "on_attack")
            case ActionType.ACTIVATE:
                self._activate(p, action.card, action.option)
            case ActionType.END_TURN:
                s.pending.append(Continuation("end_turn", (p,)))
                for uid in ps.play:
                    self._trigger(uid, "end_of_turn")
            case ActionType.CHOOSE_TARGET | ActionType.ACCEPT | ActionType.DECLINE | ActionType.CHOOSE_OPTION:
                self._decide(action)

    def add_card(self, owner: int, card: Card, zone: Zone, exhausted: bool = False) -> int:
        """Puts a new copy of a card straight into a zone, outside the rules: for scenarios and tests."""
        uid = len(self.state.cards)
        self.state.cards.append(CardInstance(uid, card, owner, zone, exhausted=exhausted))
        self._zone_lists(owner)[zone].append(uid)
        return uid

    def clone(self) -> "Game":
        # Card definitions are immutable, so share them instead of copying.
        memo = {id(c.card): c.card for c in self.state.cards}
        return copy.deepcopy(self, memo)

    # ------------------------------------------------------------------ turn structure

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
            c = self.card(uid)
            c.fresh = False
            held = [e for e in s.effects if e.uid == uid and e.kind == "cant_ready"]
            if held:  # "can't ready at the start of its next turn": used up now
                s.effects = [e for e in s.effects if e not in held]
                continue
            if self._result and c.exhausted:
                self._result.readied.append(uid)
            c.exhausted = False
        if s.turn > 1:  # the first player skips their first draw
            s.pending.append(Continuation("draw", (p,)))
        for uid in ps.play:
            self._trigger(uid, "start_of_turn")

    def _end_turn(self, p: int):
        s = self.state
        s.effects = [e for e in s.effects if e.expires_turn is None or e.expires_turn > s.turn]
        self._check_defeats()  # a health bonus may just have ended
        if s.phase != Phase.GAME_OVER:
            self._begin_turn(1 - p)

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
            self._result.energy_spent[p] = self._result.energy_spent.get(p, 0) + min(cost, len(ready))

    def _play(self, p: int, uid: int):
        card = self.card(uid).card
        self._pay(p, self.play_cost(uid))
        if card.type == "action":
            self._move(uid, Zone.DISCARD)
            for i, ability in enumerate(compiled(card)):
                if ability.kind == "on_resolve":
                    self.state.queue.append(Frame(uid, p, i))
            return
        self._move(uid, Zone.PLAY)
        self.card(uid).fresh = True
        self._trigger(uid, "on_play")
        for other in self.state.players[p].play:
            if other != uid:
                self._trigger(other, "another_played", played=uid)

    def _activate(self, p: int, uid: int, index: int):
        self.card(uid).exhausted = True
        if self._result:
            self._result.exhausted.append(uid)
        for cost in self._ability_of(uid, index).tree["cost"]:
            if "pay" in cost:
                self._pay(p, cost["pay"])
        self.state.queue.append(Frame(uid, p, index))

    def _activatable(self, uid: int) -> list[int]:
        """Indexes of this unit's ⟳ abilities whose other costs can be paid now."""
        c = self.card(uid)
        out = []
        for i, ability in enumerate(compiled(c.card)):
            if ability.kind != "activated":
                continue
            payable = True
            for cost in ability.tree["cost"]:
                if "pay" in cost and cost["pay"] > self.ready_energy(c.owner):
                    payable = False
                if "exhaust_another" in cost and not any(
                        u != uid and not self.card(u).exhausted for u in self.state.players[c.owner].play):
                    payable = False
                if "discard" in cost and not self.state.players[c.owner].hand:
                    payable = False
            if payable:
                out.append(i)
        return out

    def _barred(self, uid: int) -> bool:
        return any(e.kind == "barred" for e in self._effects_on(uid))

    # ------------------------------------------------------------------ abilities

    def _ability(self, frame: Frame) -> CompiledAbility:
        return self._ability_of(frame.source, frame.ability)

    def _ability_of(self, uid: int, index: int) -> CompiledAbility:
        return compiled(self.card(uid).card)[index]

    def _trigger(self, uid: int, event: str, played: int | None = None):
        """Queues the card's abilities triggered by this event."""
        c = self.card(uid)
        for i, ability in enumerate(compiled(c.card)):
            if ability.kind != "triggered" or ability.tree["trigger"]["event"] != event:
                continue
            trigger_filter = ability.tree["trigger"].get("filter")
            if played is not None and trigger_filter and not self.matches(played, trigger_filter, c.owner, uid):
                continue
            self.state.queue.append(Frame(uid, c.owner, i))

    def _resolve(self):
        """Resolves the stack until a decision is needed or it's empty."""
        s = self.state
        while s.phase != Phase.GAME_OVER:
            top = s.pending[-1] if s.pending else None
            if s.queue and not (isinstance(top, Frame) and top.node != 0):
                # Nothing is part-way through resolving: triggered abilities go on the stack,
                # the first triggered on top so it resolves first.
                s.pending.extend(reversed(s.queue))
                s.queue.clear()
                continue
            if top is None:
                break
            if isinstance(top, Continuation):
                s.pending.pop()
                self._continue(top)
                continue
            ability = self._ability(top)
            node = ability.nodes[top.node]
            match node.kind:
                case "entry":
                    if not self._condition(ability.tree.get("condition"), top.controller, top.source, top.bindings):
                        s.pending.pop()
                        continue
                    if self._result:
                        self._result.abilities.append(top.source)
                    top.node = node.next
                case "end":
                    s.pending.pop()
                case "effect":
                    self._effect(node.data, top)
                    top.node = node.next
                    self._check_defeats()
                case "if":
                    held = self._condition(node.data, top.controller, top.source, top.bindings)
                    top.node = node.branches[0 if held else 1]
                case "choose":
                    options = self._choose_options(top, node)
                    bound = top.bindings.setdefault(node.name, [])
                    needed = node.data.get("count", 1) - len(bound)
                    if needed <= 0 or not options:
                        top.node = node.next
                    elif len(options) <= needed:  # no real choice
                        bound.extend(options)
                        top.node = node.next
                    else:
                        mine = node.data.get("chooser", "you") == "you"
                        s.decision_player = top.controller if mine else 1 - top.controller
                        return
                case "may":
                    if not self._payable(node.data["cost"], top):
                        top.node = node.branches[1]
                    else:
                        s.decision_player = top.controller
                        return
                case "choose_one":
                    s.decision_player = top.controller
                    return
        if s.phase == Phase.GAME_OVER:
            s.pending.clear()
            s.queue.clear()
        elif s.phase == Phase.MAIN:
            s.decision_player = s.active_player

    def _continue(self, step: Continuation):
        match step.kind:
            case "duel":
                attacker, defender = step.args
                if self.card(attacker).zone == Zone.PLAY and self.card(defender).zone == Zone.PLAY:
                    to_attacker, to_defender = self.duel_damage(attacker, defender)
                    self._damage(attacker, to_attacker)
                    self._damage(defender, to_defender)
                    self._check_defeats()
            case "end_turn":
                self._end_turn(*step.args)
            case "draw":
                self._draw(*step.args)

    def _decision_actions(self) -> list[Action]:
        frame, node = self.pending_decision()
        if node.kind == "choose":
            return [Action(ActionType.CHOOSE_TARGET, frame.source, uid) for uid in self._choose_options(frame, node)]
        if node.kind == "may":
            return [Action(ActionType.ACCEPT, frame.source), Action(ActionType.DECLINE, frame.source)]
        return [Action(ActionType.CHOOSE_OPTION, frame.source, option=i) for i in range(len(node.branches))]

    def _decide(self, action: Action):
        frame, node = self.pending_decision()
        match action.type:
            case ActionType.CHOOSE_TARGET:
                bound = frame.bindings.setdefault(node.name, [])
                bound.append(action.target)
                if len(bound) >= node.data.get("count", 1):
                    frame.node = node.next
            case ActionType.ACCEPT:
                frame.node = node.branches[0]
            case ActionType.DECLINE:
                frame.node = node.branches[1]
            case ActionType.CHOOSE_OPTION:
                frame.node = node.branches[action.option]

    def _choose_options(self, frame: Frame, node: Node) -> list[int]:
        chosen = frame.bindings.get(node.name, [])
        return [u for u in self.candidates(node.data["filter"], frame.controller, frame.source) if u not in chosen]

    def _payable(self, cost: list, frame: Frame) -> bool:
        """Whether a "you may" cost can be paid in full, so "if you do" can follow."""
        ps = self.state.players[frame.controller]
        for step in cost:
            if "choose" in step and not self.candidates(step["choose"]["filter"], frame.controller, frame.source):
                return False
            if step.get("effect") == "discard" and len(ps.hand) < step.get("amount", 1):
                return False
            if step.get("effect") == "lose_vp" and ps.vp < step.get("amount", 1):
                return False
        return True

    def _targets(self, target, frame: Frame, zone: Zone = Zone.PLAY) -> list[int]:
        """Cards (or players, for player effects) an effect applies to."""
        if target == "this":
            return [frame.source] if self.card(frame.source).zone == zone else []
        if target == "you":
            return [frame.controller]
        if target == "opponent":
            return [1 - frame.controller]
        if "ref" in target:
            return [u for u in frame.bindings.get(target["ref"], []) if self.card(u).zone == zone]
        if "all" in target:
            return self.candidates(target["all"], frame.controller, frame.source)
        if "owner_of" in target:
            return sorted({self.card(u).owner for u in frame.bindings.get(target["owner_of"], [])})
        raise ValueError(f"unknown target {target}")

    def _amount(self, amount, controller: int, source: int, bindings: dict | None = None):
        if amount is None:
            return 1
        if isinstance(amount, (int, str)):
            return amount
        if "per" in amount:
            return min(amount["cap"], amount.get("k", 1) * len(self.candidates(amount["per"], controller, source)))
        bound = [u for u in (bindings or {}).get(amount["stat_of"], []) if self.card(u).zone == Zone.PLAY]
        return self.stat(bound[0], amount["stat"]) if bound else 0

    def _condition(self, cond: dict | None, controller: int, source: int, bindings: dict | None = None) -> bool:
        if not cond:
            return True
        s = self.state
        bindings = bindings or {}
        if "defeated" in cond:
            return any(self.card(u).zone == Zone.DISCARD for u in bindings.get(cond["defeated"], []))
        if "in_play" in cond:
            return any(self.card(u).zone == Zone.PLAY for u in bindings.get(cond["in_play"], []))
        if "count" in cond:
            return len(self.candidates(cond["count"], controller, source)) >= cond["at_least"]
        if "behind_on_vp" in cond:
            return s.players[controller].vp < s.players[1 - controller].vp
        if "turn" in cond:
            return (s.active_player == controller) == (cond["turn"] == "yours")
        if "this_is" in cond:
            c = self.card(source)
            return {"attacking": s.duel is not None and s.duel[0] == source,
                    "defending": s.duel is not None and s.duel[1] == source,
                    "exhausted": c.exhausted, "damaged": c.damage > 0}[cond["this_is"]]
        raise ValueError(f"unknown condition {cond}")

    def _effect(self, step: dict, frame: Frame):
        s = self.state
        op = step["effect"]
        amount = self._amount(step.get("amount"), frame.controller, frame.source, frame.bindings)
        targets = self._targets(step["target"], frame, Zone.HAND if op == "discard_card" else Zone.PLAY)
        duration = step.get("duration", "this_turn")

        def lasting(uid: int, **fields) -> ActiveEffect:
            # "Until the start of your next turn": through the opponent's next turn, if it's your turn now.
            expires = {"this_turn": s.turn,
                       "until_your_next_turn": s.turn + (s.active_player == frame.controller)}.get(duration)
            return ActiveEffect(uid=uid, expires_turn=expires,
                                source=frame.source if duration == "while_this_in_play" else None, **fields)

        for t in targets:
            match op:
                case "deal_damage":
                    self._damage(t, amount)
                case "remove_damage":
                    before = self.card(t).damage
                    self.card(t).damage = 0 if amount == "all" else max(0, before - amount)
                    if self._result and before > self.card(t).damage:
                        self._result.healed[t] = self._result.healed.get(t, 0) + before - self.card(t).damage
                case "defeat":
                    self._defeat(t)
                case "return_to_hand":
                    self._move(t, Zone.HAND)
                case "exhaust":
                    self.card(t).exhausted = True
                    if self._result:
                        self._result.exhausted.append(t)
                case "ready":
                    self.card(t).exhausted = False
                    if self._result:
                        self._result.readied.append(t)
                    self._add_effect(ActiveEffect("barred", t, expires_turn=s.turn))
                case "cant_ready":
                    self._add_effect(ActiveEffect("cant_ready", t))
                case "modify_stat":
                    self._add_effect(lasting(t, kind="stat", stat=step["stat"], value=step["delta"]))
                case "grant_keyword":
                    self._add_effect(lasting(t, kind="keyword", keyword=step["keyword"], value=step.get("value", 1)))
                case "draw":
                    for _ in range(amount):
                        self._draw(t)
                case "discard":
                    for _ in range(amount):
                        if s.players[t].hand:
                            self._move(self.rng.choice(s.players[t].hand), Zone.DISCARD)
                case "discard_card":
                    self._move(t, Zone.DISCARD)
                case "gain_vp":
                    self._gain_vp(t, amount)
                case "lose_vp":
                    lost = min(amount, s.players[t].vp)
                    s.players[t].vp -= lost
                    if self._result:
                        self._result.vp[t] = self._result.vp.get(t, 0) - lost
                case "add_energy":
                    if s.players[t].deck:
                        uid = s.players[t].deck[-1]
                        self._move(uid, Zone.ENERGY)
                        self.card(uid).exhausted = True
                case _:
                    raise ValueError(f"unknown effect {op}")

    # ------------------------------------------------------------------ statics and lasting effects

    def _add_effect(self, effect: ActiveEffect):
        self.state.effects.append(effect)
        if self._result:
            self._result.effects.append(effect)

    def _effects_on(self, uid: int) -> list[ActiveEffect]:
        return [e for e in self.state.effects
                if e.uid == uid and (e.source is None or self.card(e.source).zone == Zone.PLAY)]

    def _statics(self):
        """(source, controller, modifier, condition) for every static ability in play."""
        for p, ps in enumerate(self.state.players):
            for uid in ps.play:
                for ability in compiled(self.card(uid).card):
                    if ability.kind == "static":
                        for modifier in ability.tree["modifiers"]:
                            yield uid, p, modifier, ability.tree.get("condition")

    def _statics_on(self, uid: int):
        """(source, controller, modifier) for static modifiers that currently apply to this card."""
        for src, ctrl, modifier, condition in self._statics():
            subject = modifier.get("subject")
            if subject is None:
                continue
            applies = uid == src if subject == "this" else self.matches(uid, subject["all"], ctrl, src)
            if applies and self._condition(condition, ctrl, src):
                yield src, ctrl, modifier

    def _modifier_amount(self, modifier: dict, source: int, controller: int) -> int:
        amount = modifier["amount"]
        if isinstance(amount, int):
            return amount
        return self._amount(amount, controller, source)

    # ------------------------------------------------------------------ changing cards

    def _damage(self, uid: int, amount: int):
        if amount <= 0:
            return
        self.card(uid).damage += amount
        if self._result:
            self._result.damage[uid] = self._result.damage.get(uid, 0) + amount

    def _check_defeats(self):
        """Defeats every unit whose damage has reached its health."""
        while self.state.phase != Phase.GAME_OVER:
            doomed = [u for ps in self.state.players for u in ps.play
                      if self.card(u).damage >= self.stat(u, "health")]
            if not doomed:
                return
            for uid in doomed:
                self._defeat(uid)

    def _defeat(self, uid: int):
        if self.card(uid).zone != Zone.PLAY:
            return
        owner = self.card(uid).owner
        if self._result:
            self._result.defeated.append(uid)
        self._move(uid, Zone.DISCARD)
        self._trigger(uid, "on_defeated")
        for other in self.state.players[1 - owner].play:
            self._trigger(other, "opposing_defeated")

    def _gain_vp(self, p: int, amount: int):
        self.state.players[p].vp += amount
        if self._result:
            self._result.vp[p] = self._result.vp.get(p, 0) + amount
        if self.state.players[p].vp >= self.config.vp_to_win:
            self._end_game(p)

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
        if zone != Zone.PLAY:  # lasting effects end when a card leaves play
            self.state.effects = [e for e in self.state.effects if e.uid != uid]

    def _zone_lists(self, p: int) -> dict[Zone, list[int]]:
        return self._zone_lists_of(self.state.players[p])

    @staticmethod
    def _zone_lists_of(ps: PlayerState) -> dict[Zone, list[int]]:
        return {Zone.DECK: ps.deck, Zone.HAND: ps.hand, Zone.PLAY: ps.play, Zone.ENERGY: ps.energy,
                Zone.DISCARD: ps.discard}

    def _end_game(self, winner: int | None):
        if self.state.phase == Phase.GAME_OVER:
            return
        self.state.phase = Phase.GAME_OVER
        self.state.winner = winner


def ability_text(card: Card, index: int) -> str:
    return render(card.abilities[index], card.type)


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
        case ActionType.ACTIVATE:
            return f"{name}: {ability_text(game.card(action.card).card, action.option)}"
        case ActionType.CHOOSE_TARGET:
            return f"Choose {game.card(action.target).card.name}"
        case ActionType.ACCEPT:
            return "Yes"
        case ActionType.DECLINE:
            return "No"
        case ActionType.CHOOSE_OPTION:
            _, node = game.pending_decision()
            option = node.data["options"][action.option]
            return Renderer(game.card(action.card).card.type).steps(option)
