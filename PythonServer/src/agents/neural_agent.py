import torch

from src.agents.base import Agent
from src.game.actions import Action
from src.game.engine import Game
from src.graph.builder import build_observation
from src.model.network import TCGNet, collate, load_model


class NeuralAgent(Agent):
    name = "neural"

    def __init__(self, net: TCGNet, device: str = "cpu", greedy: bool = True):
        self.net = net
        self.device = device
        self.greedy = greedy

    @classmethod
    def from_checkpoint(cls, path, device: str = "cpu", greedy: bool = True) -> "NeuralAgent":
        return cls(load_model(path, device), device, greedy)

    def choose(self, game: Game) -> Action:
        obs = build_observation(game, game.state.decision_player)
        self.net.eval()
        with torch.no_grad():
            logits, _, _ = self.net(collate([obs.data]).to(self.device))
        index = int(logits.argmax()) if self.greedy else int(torch.multinomial(logits.softmax(-1), 1))
        return obs.actions[index]

    def value(self, game: Game, player: int) -> float:
        """The network's estimate of player's chance to win, in [-1, 1]."""
        obs = build_observation(game, player)
        with torch.no_grad():
            _, _, value = self.net(collate([obs.data]).to(self.device))
        return float(value[0])
