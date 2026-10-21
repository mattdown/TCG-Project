"""Rules engine (rules v2, Hearthstone-style: docs/technical-plan.md section 2).

Every decision is a choice from legal_actions(), and step() applies one. Turn structure:
mulligan (each player once) → for each turn: gain a mana crystal and refill them, units can
attack again, start-of-turn abilities, draw, then main-phase actions until END_TURN, then
end-of-turn abilities. A hero at 0 health loses. Drawing from an empty deck deals growing
damage to your hero instead.

Abilities (docs/technical-plan.md section 3) are compiled to decision graphs and resolved on a
stack (state.pending). Triggered abilities wait in state.queue until no ability is part-way
through resolving, then go on the stack. Whenever resolution reaches a choose, may or
choose-one node, the engine stops and that choice becomes the next decision.
"""
import copy
import random
from collections import Counter
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
    hero_health: int = 30
    max_mana: int = 10
    opening_hand: tuple[int, int] = (3, 4)  # first player, second player
    max_board: int = 7
    max_hand: int = 10  # a card drawn into a full hand is discarded
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
    hero_damage: dict[int, int] = field(default_factory=dict)  # player → damage to their hero
    hero_healed: dict[int, int] = field(default_factory=dict)  # player → health their hero got back
    mana_spent: dict[int, int] = field(default_factory=dict)  # player → mana paid
    crystals: dict[int, int] = field(default_factory=dict)  # player → mana crystals gained by abilities
    exhausted: list[int] = field(default_factory=list)  # units that attacked (or were stopped from attacking)
    readied: list[int] = field(default_factory=list)  # units that can attack again at the start of a turn
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
            players.append(PlayerState(deck=uids, health=config.hero_health, aspect=deck_aspect(deck)))
        first = self.rng.randrange(2) if first_player is None else first_player
        self.state = GameState(cards, players, first_player=first, active_player=first, decision_player=first)
        players[1 - first].spare_spore = True
        for p in (first, 1 - first):
            for _ in range(config.opening_hand[p != first]):
                self._draw(p)

    # ------------------------------------------------------------------ queries

    @property
    def is_over(self) -> bool:
        return self.state.phase == Phase.GAME_OVER

    def card(self, uid: int) -> CardInstance:
        return self.state.cards[uid]

    def mana(self, player: int) -> int:
        return self.state.players[player].mana

    def stat(self, uid: int, name: str) -> int:
        """Power or health, including abilities' bonuses (never below 0)."""
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

    def frozen(self, uid: int) -> bool:
        """An ability stops this unit attacking on its owner's next turn."""
        return any(e.uid == uid and e.kind == "freeze" for e in self.state.effects)

    def hidden(self, uid: int) -> bool:
        """Elusive and hasn't attacked yet: enemies can't attack it or choose it."""
        return bool(self.keyword(uid, "elusive")) and not self.card(uid).revealed

    def play_cost(self, uid: int) -> int:
        c = self.card(uid)
        reduction = 0
        for src, ctrl, modifier, condition in self._statics():
            if ("cost_reduction" in modifier and ctrl == c.owner and self._condition(condition, ctrl, src)
                    and self.matches(uid, {**modifier["filter"], "zone": "hand", "type": "any"}, ctrl, src)):
                reduction += modifier["cost_reduction"]
        return max(c.card.cost - reduction, 0)

    def can_attack(self, uid: int) -> bool:
        c = self.card(uid)
        return (c.zone == Zone.PLAY and not c.exhausted and (not c.fresh or bool(self.keyword(uid, "charge")))
                and self.stat(uid, "power") + self.keyword(uid, "duelist") > 0)

    def attack_targets(self, attacker_uid: int) -> tuple[list[int], bool]:
        """(enemy units this unit may attack, whether it may attack the enemy hero).

        Hidden Elusive units can't be attacked. While the enemy has a Guard unit that can be
        attacked, attacks must go to a Guard unit."""
        s = self.state
        units = [uid for uid in s.players[1 - s.cards[attacker_uid].owner].play if not self.hidden(uid)]
        guards = [uid for uid in units if self.keyword(uid, "guard")]
        return (guards, False) if guards else (units, True)

    def attack_damage(self, attacker_uid: int, defender_uid: int | None) -> tuple[int, int]:
        """(damage to the attacker, damage to the defender, or to the hero when defender_uid is
        None). Duelist adds to the attacker's power; Armor reduces the damage each unit takes;
        heroes deal none back. Abilities that apply "while attacking" or "while defending" count."""
        previous, self.state.duel = self.state.duel, (attacker_uid, defender_uid)
        try:
            attack = self.stat(attacker_uid, "power") + self.keyword(attacker_uid, "duelist")
            if defender_uid is None:
                return 0, attack
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
        board_full = len(ps.play) >= self.config.max_board
        for uid in ps.hand:
            if self.play_cost(uid) <= ps.mana and (s.cards[uid].card.type != "unit" or not board_full):
                actions.append(Action(ActionType.PLAY, uid))
        if ps.spare_spore:
            actions.append(Action(ActionType.SPARE_SPORE))
        for uid in ps.play:
            unit = s.cards[uid]
            if not unit.exhausted and not unit.fresh:
                actions.extend(Action(ActionType.ACTIVATE, uid, option=i) for i in self._activatable(uid))
            if self.can_attack(uid):
                units, hero = self.attack_targets(uid)
                actions.extend(Action(ActionType.ATTACK, uid, t) for t in units)
                if hero:
                    actions.append(Action(ActionType.ATTACK_HERO, uid))
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
            case ActionType.PLAY:
                self._play(p, action.card)
            case ActionType.SPARE_SPORE:
                ps.spare_spore = False
                ps.mana += 1
            case ActionType.ATTACK | ActionType.ATTACK_HERO:
                unit = self.card(action.card)
                unit.exhausted = unit.revealed = True
                if self._result:
                    self._result.exhausted.append(unit.uid)
                s.pending.append(Continuation("attack", (action.card, action.target)))
                self._trigger(action.card, "on_attack")
                if action.type == ActionType.ATTACK_HERO:
                    self._trigger(action.card, "on_attack_hero")
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
        ps.crystals = min(ps.crystals + 1, self.config.max_mana)
        ps.mana = ps.crystals
        for uid in ps.play:
            c = self.card(uid)
            c.fresh = False
            held = [e for e in s.effects if e.uid == uid and e.kind == "freeze"]
            if held:  # frozen: can't attack this turn, then it wears off
                s.effects = [e for e in s.effects if e not in held]
                c.exhausted = True
                continue
            if self._result and c.exhausted:
                self._result.readied.append(uid)
            c.exhausted = False
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
            ps.fatigue += 1
            self._damage_hero(p, ps.fatigue)
            return
        uid = ps.deck.pop()
        dest = Zone.HAND if len(ps.hand) < self.config.max_hand else Zone.DISCARD  # a full hand burns the card
        self._zone_lists(p)[dest].append(uid)
        self.card(uid).zone = dest
        if self._result:
            self._result.moves.append(Move(uid, p, Zone.DECK, dest))

    def _pay(self, p: int, cost: int):
        ps = self.state.players[p]
        paid = min(cost, ps.mana)
        ps.mana -= paid
        if self._result:
            self._result.mana_spent[p] = self._result.mana_spent.get(p, 0) + paid

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
                if "pay" in cost and cost["pay"] > self.mana(c.owner):
                    payable = False
                if "exhaust_another" in cost and not any(
                        u != uid and not self.card(u).exhausted for u in self.state.players[c.owner].play):
                    payable = False
                if "discard" in cost and not self.state.players[c.owner].hand:
                    payable = False
            if payable:
                out.append(i)
        return out

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
            case "attack":
                attacker, defender = step.args
                if self.card(attacker).zone != Zone.PLAY:
                    return
                if defender is None:
                    self._damage_hero(1 - self.card(attacker).owner, self.attack_damage(attacker, None)[1])
                elif self.card(defender).zone == Zone.PLAY:
                    to_attacker, to_defender = self.attack_damage(attacker, defender)
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
        """Hidden Elusive units can't be chosen by their owner's opponent."""
        chosen = frame.bindings.get(node.name, [])
        return [u for u in self.candidates(node.data["filter"], frame.controller, frame.source)
                if u not in chosen and not (self.card(u).owner != frame.controller and self.hidden(u))]

    def _payable(self, cost: list, frame: Frame) -> bool:
        """Whether a "you may" cost can be paid in full, so "if you do" can follow."""
        ps = self.state.players[frame.controller]
        for step in cost:
            if "choose" in step and not self.candidates(step["choose"]["filter"], frame.controller, frame.source):
                return False
            if step.get("effect") == "discard" and len(ps.hand) < step.get("amount", 1):
                return False
            if step.get("effect") == "damage_hero" and ps.health <= step.get("amount", 1):
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
        if "behind_on_health" in cond:
            return s.players[controller].health < s.players[1 - controller].health
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
                case "return_to_hand":  # into a full hand, the card is discarded instead
                    full = len(s.players[self.card(t).owner].hand) >= self.config.max_hand
                    self._move(t, Zone.DISCARD if full else Zone.HAND)
                case "exhaust":
                    self.card(t).exhausted = True
                    if self._result:
                        self._result.exhausted.append(t)
                case "freeze":
                    self._add_effect(ActiveEffect("freeze", t))
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
                case "heal_hero":
                    ps = s.players[t]
                    healed = min(amount, self.config.hero_health - ps.health)
                    ps.health += healed
                    if self._result and healed:
                        self._result.hero_healed[t] = self._result.hero_healed.get(t, 0) + healed
                case "damage_hero":
                    self._damage_hero(t, amount)
                case "gain_crystal":
                    ps = s.players[t]
                    if ps.crystals < self.config.max_mana:  # an empty crystal: more mana from next turn
                        ps.crystals += 1
                        if self._result:
                            self._result.crystals[t] = self._result.crystals.get(t, 0) + 1
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

    def _damage_hero(self, p: int, amount: int):
        if amount <= 0:
            return
        self.state.players[p].health -= amount
        if self._result:
            self._result.hero_damage[p] = self._result.hero_damage.get(p, 0) + amount
        if self.state.players[p].health <= 0:
            self._end_game(1 - p)

    def _move(self, uid: int, zone: Zone):
        c = self.card(uid)
        if self._result:
            self._result.moves.append(Move(uid, c.owner, c.zone, zone))
        zones = self._zone_lists(c.owner)
        zones[c.zone].remove(uid)
        zones[zone].append(uid)
        c.zone = zone
        c.exhausted = c.fresh = c.revealed = False
        c.damage = 0
        if zone != Zone.PLAY:  # lasting effects end when a card leaves play
            self.state.effects = [e for e in self.state.effects if e.uid != uid]

    def _zone_lists(self, p: int) -> dict[Zone, list[int]]:
        return self._zone_lists_of(self.state.players[p])

    @staticmethod
    def _zone_lists_of(ps: PlayerState) -> dict[Zone, list[int]]:
        return {Zone.DECK: ps.deck, Zone.HAND: ps.hand, Zone.PLAY: ps.play, Zone.DISCARD: ps.discard}

    def _end_game(self, winner: int | None):
        if self.state.phase == Phase.GAME_OVER:
            return
        self.state.phase = Phase.GAME_OVER
        self.state.winner = winner


def deck_aspect(deck: list[Card]) -> str | None:
    """The hero's aspect: the most common aspect in the deck (one aspect plus neutral cards)."""
    counts = Counter(a for card in deck for a in card.aspects)
    return counts.most_common(1)[0][0] if counts else None


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
        case ActionType.PLAY:
            return f"Play {name}"
        case ActionType.SPARE_SPORE:
            return f"Use the {TERMS['spare_spore']} (+1 {TERMS['mana']} this turn)"
        case ActionType.ATTACK:
            return f"{TERMS['attack'].capitalize()}: {name} → {game.card(action.target).card.name}"
        case ActionType.ATTACK_HERO:
            return f"{TERMS['attack'].capitalize()}: {name} → the enemy {TERMS['hero']}"
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
