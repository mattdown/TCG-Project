"""Game session behind the ZeroMQ server: turns JSON requests into engine calls.

Every request is a JSON object with a "type"; every response has "status" ("ok" or
"error") and, where relevant, "state": the game as the human player sees it.

  {"type": "card_set"}                         → all card definitions
  {"type": "new_game", "human_seat": 0,        → starts a game on random decks
   "opponent": "neural"|"heuristic"|"random",
   "seed": 123,
   "scenario": {...}}                          → optional: skip the mulligan and set up chosen cards (see _set_up)
  {"type": "state"}                            → current state
  {"type": "act", "action_index": 3}           → applies the human's choice from state.legal_actions
  {"type": "ai_move"}                          → the AI makes one decision (call in a loop to animate)
  {"type": "ai_turn"}                          → the AI decides until it's the human's turn or the game ends

The state never includes the AI's hand or either deck's contents.
"""
import random

from src.agents.base import Agent
from src.agents.heuristic_agent import HeuristicAgent
from src.agents.neural_agent import NeuralAgent
from src.agents.random_agent import RandomAgent
from src.cards.abilities import render
from src.cards.schema import CardSet
from src.game.actions import Action, ActionType
from src.game.decks import random_deck
from src.game.engine import Game, Move, StepResult, describe_action
from src.game.state import Phase, Zone
from src.game.terms import KEYWORD_NAMES, KEYWORD_RULES, KEYWORDS

# Zones whose cards both players see. A card burned from a full hand goes to the discard pile face up.
PUBLIC_ZONES = (Zone.PLAY, Zone.DISCARD)


class GameSession:
    def __init__(self, card_set: CardSet, model_path=None):
        self.card_set = card_set
        self.model_path = model_path
        self.game: Game | None = None
        self.human_seat = 0
        self.ai: Agent | None = None

    def handle(self, request: dict) -> dict:
        handler = {
            "card_set": self._card_set,
            "new_game": self._new_game,
            "state": self._state,
            "act": self._act,
            "ai_move": self._ai_move,
            "ai_turn": self._ai_turn,
        }.get(request.get("type"))
        if handler is None:
            return {"status": "error", "msg": f"unknown request type {request.get('type')!r}"}
        if handler not in (self._card_set, self._new_game) and self.game is None:
            return {"status": "error", "msg": "no game in progress: send new_game first"}
        try:
            return handler(request)
        except ValueError as e:
            return {"status": "error", "msg": str(e)}

    # --- handlers

    def _card_set(self, _):
        cards = [{**c.to_dict(), "ability_text": [render(a, c.type) for a in c.abilities]} for c in self.card_set.cards]
        keywords = {k: {"name": KEYWORD_NAMES[k], "numbered": KEYWORDS[k], "rule": KEYWORD_RULES[k]} for k in KEYWORDS}
        return {"status": "ok", "name": self.card_set.name, "cards": cards, "keywords": keywords}

    def _new_game(self, request):
        seed = request.get("seed")
        rng = random.Random(seed)
        self.human_seat = int(request.get("human_seat", 0))
        self.ai = self._make_agent(request.get("opponent", "neural"))
        scenario = request.get("scenario")
        self.game = Game(random_deck(self.card_set, rng), random_deck(self.card_set, rng), seed=rng.randrange(2**31),
                         first_player=self.human_seat if scenario else None)
        if scenario:
            self._set_up(scenario)
        return {"status": "ok", "opponent": self.ai.name, "state": self.view()}

    def _set_up(self, scenario: dict):
        """Starts the human's first turn with chosen cards, for checking single cards by hand.

            {"hand": ["C1-004"], "play": ["C1-007", {"id": "C1-010", "exhausted": true, "damage": 1}],
             "opponent_play": ["C1-002"], "opponent_hand": [], "mana": 5, "opponent_mana": 0,
             "health": 30, "opponent_health": 12}

        Both mulligans are skipped. Units placed in play can attack straight away. `mana` sets
        the mana crystals, all full.
        """
        g = self.game
        while g.state.phase == Phase.MULLIGAN:
            g.step(Action(ActionType.KEEP_HAND))
        for key, zone, player in (("hand", Zone.HAND, self.human_seat), ("play", Zone.PLAY, self.human_seat),
                                  ("opponent_hand", Zone.HAND, 1 - self.human_seat),
                                  ("opponent_play", Zone.PLAY, 1 - self.human_seat)):
            for entry in scenario.get(key, []):
                entry = {"id": entry} if isinstance(entry, str) else entry
                try:
                    card = self.card_set[entry["id"]]
                except KeyError:
                    raise ValueError(f"unknown card id {entry['id']!r} in scenario")
                uid = g.add_card(player, card, zone, exhausted=entry.get("exhausted", False))
                g.card(uid).damage = entry.get("damage", 0)
        for prefix, player in (("", self.human_seat), ("opponent_", 1 - self.human_seat)):
            ps = g.state.players[player]
            if prefix + "mana" in scenario:
                ps.crystals = ps.mana = min(int(scenario[prefix + "mana"]), g.config.max_mana)
            ps.health = int(scenario.get(prefix + "health", ps.health))

    def _state(self, _):
        return {"status": "ok", "state": self.view()}

    def _act(self, request):
        if self.game.state.decision_player != self.human_seat or self.game.is_over:
            raise ValueError("it is not the human player's decision")
        actions = self.game.legal_actions()
        index = int(request["action_index"])
        if not 0 <= index < len(actions):
            raise ValueError(f"action_index {index} out of range (0..{len(actions) - 1})")
        record = self._apply(actions[index])
        return {"status": "ok", "action": record, "state": self.view()}

    def _ai_move(self, _):
        if self.game.state.decision_player == self.human_seat or self.game.is_over:
            raise ValueError("it is not the AI's decision")
        record = self._apply(self.ai.choose(self.game))
        return {"status": "ok", "action": record, "state": self.view()}

    def _ai_turn(self, _):
        records = []
        while not self.game.is_over and self.game.state.decision_player != self.human_seat:
            records.append(self._apply(self.ai.choose(self.game)))
        return {"status": "ok", "actions": records, "state": self.view()}

    # --- helpers

    def _make_agent(self, name: str) -> Agent:
        if name == "neural":
            if self.model_path is None or not self.model_path.exists():
                raise ValueError("no trained model found: train one or choose another opponent")
            return NeuralAgent.from_checkpoint(self.model_path)
        if name == "heuristic":
            return HeuristicAgent()
        if name == "random":
            return RandomAgent()
        raise ValueError(f"unknown opponent {name!r}")

    def _apply(self, action: Action) -> dict:
        record = {**action.to_dict(), "player": self.game.state.decision_player,
                  "text": describe_action(self.game, action)}
        record["result"] = self._result_view(self.game.step(action, record=True))
        return record

    def view(self) -> dict:
        """The game as the human player sees it."""
        g, s = self.game, self.game.state

        def card_view(uid):
            c = g.card(uid)
            view = {"uid": uid, "card_id": c.card.id, "exhausted": c.exhausted, "fresh": c.fresh, "damage": c.damage,
                    "cost": g.play_cost(uid) if c.zone == Zone.HAND else c.card.cost}
            if c.card.type == "unit":
                # Current values, with abilities' changes: the client shows them against the card's own.
                view.update({"power": g.stat(uid, "power"), "health": g.stat(uid, "health"),
                             "keywords": {k: (g.keyword(uid, k) if KEYWORDS[k] else True)
                                          for k in KEYWORDS if g.keyword(uid, k)},
                             "can_attack": g.can_attack(uid) and c.owner == s.active_player,
                             "frozen": g.frozen(uid), "hidden": c.zone == Zone.PLAY and g.hidden(uid)})
            return view

        players = []
        for p, ps in enumerate(s.players):
            players.append({
                "aspect": ps.aspect,
                "health": ps.health,
                "mana": ps.mana,
                "crystals": ps.crystals,
                "spare_spore": ps.spare_spore > 0,
                "fatigue": ps.fatigue,
                "deck_count": len(ps.deck),
                "hand_count": len(ps.hand),
                "hand": [card_view(u) for u in ps.hand] if p == self.human_seat else None,
                "play": [card_view(u) for u in ps.play],
                "discard": [card_view(u) for u in ps.discard],
                "mulligan_marked": ps.mulligan_marked if p == self.human_seat else None,
            })
        human_decides = s.decision_player == self.human_seat and not g.is_over
        legal = g.legal_actions() if human_decides else []
        return {
            "turn": s.turn,
            "phase": s.phase.name.lower(),
            "active_player": s.active_player,
            "decision_player": s.decision_player,
            "human_seat": self.human_seat,
            "game_over": s.phase == Phase.GAME_OVER,
            "winner": s.winner,
            "players": players,
            "hero_health": g.config.hero_health,
            "max_mana": g.config.max_mana,
            "pending": self._pending_view(),
            "legal_actions": [{"index": i, **a.to_dict(), "text": describe_action(g, a), "preview": self._preview(a)}
                              for i, a in enumerate(legal)],
        }

    def _pending_view(self) -> dict | None:
        """The ability waiting for a decision, if any: whose it is, what kind of choice, its text."""
        decision = self.game.pending_decision()
        if decision is None:
            return None
        frame, node = decision
        card = self.game.card(frame.source).card
        return {"source": frame.source, "card_id": card.id, "kind": node.kind,
                "chooser": self.game.state.decision_player, "ability_text": render(card.abilities[frame.ability], card.type)}

    def _preview(self, action: Action) -> dict | None:
        """What a play or an attack would do: the action tried on a copy of the game, up to the
        first choice an ability asks for.

        The client shows these while dragging ("−3 to the hero", "Defeated") without knowing any rules.
        Only moves of cards that were in play are kept, so a preview never reveals a card an
        ability would draw or discard at random.
        """
        if action.type not in (ActionType.PLAY, ActionType.ATTACK, ActionType.ATTACK_HERO):
            return None
        result = self.game.clone().step(action, validate=False, record=True)
        result.moves = [m for m in result.moves if m.source == Zone.PLAY or m.uid == action.card]
        return self._result_view(result)

    def _result_view(self, r: StepResult) -> dict:
        """A step result as the human may see it: hidden moves keep only who and where."""
        return {
            "damage": [{"uid": uid, "amount": n} for uid, n in r.damage.items()],
            "defeated": r.defeated,
            "hero_damage": [{"player": p, "amount": n} for p, n in r.hero_damage.items()],
            "hero_healed": [{"player": p, "amount": n} for p, n in r.hero_healed.items()],
            "mana_spent": [{"player": p, "amount": n} for p, n in r.mana_spent.items()],
            "crystals": [{"player": p, "amount": n} for p, n in r.crystals.items()],
            "exhausted": r.exhausted,
            "readied": r.readied,
            "moves": [self._move_view(m) for m in r.moves],
            "abilities": r.abilities,
            "healed": [{"uid": uid, "amount": n} for uid, n in r.healed.items()],
            "effects": [{"uid": e.uid, "kind": e.kind, "stat": e.stat, "keyword": e.keyword, "value": e.value,
                         "this_turn": e.expires_turn == self.game.state.turn,
                         "lasts": self._lasts(e)} for e in r.effects],
        }

    def _lasts(self, e) -> str:
        """How long a lasting effect lasts, for the client's label."""
        if e.kind == "freeze":
            return "until_its_next_turn"
        if e.expires_turn is None:
            return "while_in_play" if e.source is not None else "permanent"
        return "this_turn" if e.expires_turn == self.game.state.turn else "until_your_next_turn"

    def _move_view(self, m: Move) -> dict:
        public = m.owner == self.human_seat or m.dest in PUBLIC_ZONES or m.source in PUBLIC_ZONES
        return {"uid": m.uid if public else None,
                "card_id": self.game.card(m.uid).card.id if public else None,
                "player": m.owner, "from": m.source.name.lower(), "to": m.dest.name.lower()}
