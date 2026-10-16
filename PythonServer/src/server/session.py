"""Game session behind the ZeroMQ server: turns JSON requests into engine calls.

Every request is a JSON object with a "type"; every response has "status" ("ok" or
"error") and, where relevant, "state": the game as the human player sees it.

  {"type": "card_set"}                         → all card definitions
  {"type": "new_game", "human_seat": 0,        → starts a game on random decks
   "opponent": "neural"|"heuristic"|"random",
   "seed": 123}
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
from src.cards.schema import CardSet
from src.game.actions import Action, ActionType
from src.game.decks import random_deck
from src.game.engine import Game, Move, StepResult, describe_action
from src.game.state import Phase, Zone

# Zones whose cards both players see. Energy counts: adding a card as energy names it.
PUBLIC_ZONES = (Zone.PLAY, Zone.DISCARD, Zone.ENERGY)


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
        return {"status": "ok", "name": self.card_set.name, "cards": [c.to_dict() for c in self.card_set.cards]}

    def _new_game(self, request):
        seed = request.get("seed")
        rng = random.Random(seed)
        self.human_seat = int(request.get("human_seat", 0))
        self.ai = self._make_agent(request.get("opponent", "neural"))
        self.game = Game(random_deck(self.card_set, rng), random_deck(self.card_set, rng), seed=rng.randrange(2**31))
        return {"status": "ok", "opponent": self.ai.name, "state": self.view()}

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
            return {"uid": uid, "card_id": c.card.id, "exhausted": c.exhausted, "fresh": c.fresh, "damage": c.damage}

        players = []
        for p, ps in enumerate(s.players):
            players.append({
                "vp": ps.vp,
                "energy_ready": g.ready_energy(p),
                "energy_total": len(ps.energy),
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
            "vp_to_win": g.config.vp_to_win,
            "legal_actions": [{"index": i, **a.to_dict(), "text": describe_action(g, a), "preview": self._preview(a)}
                              for i, a in enumerate(legal)],
        }

    def _preview(self, action: Action) -> dict | None:
        """What a play, score or duel would do: the action tried on a copy of the game.

        The client shows these while dragging ("+2 VP", "Defeated") without knowing any rules.
        Only actions that draw nothing are previewed, so no hidden card is revealed.
        """
        if action.type not in (ActionType.PLAY, ActionType.SCORE, ActionType.DUEL):
            return None
        return self._result_view(self.game.clone().step(action, validate=False, record=True))

    def _result_view(self, r: StepResult) -> dict:
        """A step result as the human may see it: hidden moves keep only who and where."""
        return {
            "damage": [{"uid": uid, "amount": n} for uid, n in r.damage.items()],
            "defeated": r.defeated,
            "vp": [{"player": p, "amount": n} for p, n in r.vp.items()],
            "energy_spent": [{"player": p, "amount": n} for p, n in r.energy_spent.items()],
            "exhausted": r.exhausted,
            "readied": r.readied,
            "moves": [self._move_view(m) for m in r.moves],
        }

    def _move_view(self, m: Move) -> dict:
        public = m.owner == self.human_seat or m.dest in PUBLIC_ZONES or m.source in PUBLIC_ZONES
        return {"uid": m.uid if public else None,
                "card_id": self.game.card(m.uid).card.id if public else None,
                "player": m.owner, "from": m.source.name.lower(), "to": m.dest.name.lower()}
