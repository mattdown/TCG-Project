"""Search within a turn (P1b): a beam search over the agent's own turn, on a copy of the game.

At each of its decisions in its own turn, the agent copies the game, replaces what it can't see with
a guess (`Game.determinize`: its own deck shuffled, the opponent's hand and deck drawn from the card
set the way decks are built, so it never learns their deck list), and searches sequences of its moves: plays, attacks and the choices inside
abilities. Each step keeps the `top_k` moves the policy likes best (always including ending the
turn), and the `beam` positions the value head likes best go on to the next step. A line ends when
the turn ends: it's scored as minus the opponent's value at their first decision, the kind of
position the value head was trained on. The agent plays the first move of the best line, then
searches again at its next decision, since a draw may change the plan.

It fixes ordering mistakes the raw policy makes (attacking before a buff, trading in the wrong
order) without retraining. The opponent's choices inside the agent's turn (an ability they choose
for) are made by the network, greedily.
"""
import random
from pathlib import Path

import torch
from torch import nn

from src.agents.base import Agent
from src.cards.schema import CardSet
from src.game.actions import Action, ActionType
from src.game.engine import Game
from src.game.state import Phase
from src.graph.encode import Observation, observe
from src.model.common import segment_log_softmax, segment_ptr
from src.model.registry import load_model


class SearchAgent(Agent):
    name = "search"

    def __init__(self, net: nn.Module, card_set: CardSet, device: str = "cpu", beam: int = 4, top_k: int = 4,
                 max_depth: int = 12, seed: int = 0, name: str | None = None):
        """`card_set` is the set decks are built from: public knowledge, used to guess hidden cards."""
        self.net = net
        self.card_set = card_set
        self.device = device
        self.beam = beam
        self.top_k = top_k
        self.max_depth = max_depth
        self.rng = random.Random(seed)
        self.positions = 0  # positions the value head scored, for measuring cost
        if name:
            self.name = name

    @classmethod
    def from_checkpoint(cls, path, card_set: CardSet, device: str = "cpu", **kwargs) -> "SearchAgent":
        return cls(load_model(path, device), card_set, device, name=Path(path).stem + "+search", **kwargs)

    def choose(self, game: Game) -> Action:
        me = game.state.decision_player
        if game.state.phase != Phase.MAIN or game.state.active_player != me:
            return self._greedy(game)
        actions = game.legal_actions()
        if len(actions) == 1:
            return actions[0]
        root = game.clone()
        root.determinize(me, self.rng, self.card_set)
        move = self._search(root, me)
        return move if move in actions else self._greedy(game)

    def _search(self, root: Game, me: int) -> Action | None:
        best_score, best_move = -float("inf"), None
        frontier = [(root, None, *scored) for scored in self._evaluate([root])]
        for depth in range(self.max_depth):
            last = depth == self.max_depth - 1
            leaves, children = [], []
            for game, first, obs, log_probs, _ in frontier:
                for i in self._moves(obs, log_probs, last):
                    child = game.clone()
                    child.step(obs.actions[i], validate=False)
                    self._settle(child, me)
                    move = first or obs.actions[i]
                    if child.is_over:
                        score = 0.0 if child.state.winner is None else (1.0 if child.state.winner == me else -1.0)
                        if score > best_score:
                            best_score, best_move = score, move
                    elif child.state.active_player != me:
                        leaves.append((child, move))
                    else:
                        children.append((child, move))
            for (game, move), (obs, _, value) in zip(leaves, self._evaluate([g for g, _ in leaves])):
                score = value if game.state.decision_player == me else -value
                if score > best_score:
                    best_score, best_move = score, move
            if not children:
                break
            scored = [(g, m, *s) for (g, m), s in zip(children, self._evaluate([g for g, _ in children]))]
            frontier = sorted(scored, key=lambda x: x[4], reverse=True)[:self.beam]
        return best_move

    def _moves(self, obs: Observation, log_probs: torch.Tensor, last: bool) -> list[int]:
        """The top_k moves by the policy, plus ending the turn; only ending it at the depth limit."""
        end = [i for i, a in enumerate(obs.actions) if a.type == ActionType.END_TURN]
        if last and end:
            return end
        top = log_probs.topk(min(self.top_k, len(obs.actions))).indices.tolist()
        return top + [i for i in end if i not in top]

    def _settle(self, game: Game, me: int):
        """Lets the opponent make any choices inside the agent's turn, greedily."""
        while not game.is_over and game.state.active_player == me and game.state.decision_player != me:
            game.step(self._greedy(game), validate=False)

    def _evaluate(self, games: list[Game]) -> list[tuple[Observation, torch.Tensor, float]]:
        """Each game seen by its decision player: (observation, move log probs, value for that player)."""
        if not games:
            return []
        observations = [observe(g, g.state.decision_player) for g in games]
        self.positions += len(games)
        batch = self.net.collate([o.encoded for o in observations]).to(self.device)
        self.net.eval()
        with torch.no_grad():
            logits, index, values = self.net(batch)
            log_probs = segment_log_softmax(logits, index).cpu()
        ptr = segment_ptr(index, len(games)).cpu()
        return [(o, log_probs[ptr[i]:ptr[i + 1]], float(values[i])) for i, o in enumerate(observations)]

    def _greedy(self, game: Game) -> Action:
        obs, log_probs, _ = self._evaluate([game])[0]
        return obs.actions[int(log_probs.argmax())]
