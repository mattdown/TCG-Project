from pathlib import Path

import torch
from torch import nn

from src.agents.base import Agent
from src.game.actions import Action
from src.game.engine import Game
from src.graph.encode import observe
from src.model.registry import load_model


class NeuralAgent(Agent):
    name = "neural"

    def __init__(self, net: nn.Module, device: str = "cpu", greedy: bool = True, name: str | None = None):
        self.net = net
        self.device = device
        self.greedy = greedy
        if name:
            self.name = name

    @classmethod
    def from_checkpoint(cls, path, device: str = "cpu", greedy: bool = True) -> "NeuralAgent":
        return cls(load_model(path, device), device, greedy, name=Path(path).stem)

    def choose(self, game: Game) -> Action:
        obs = observe(game, game.state.decision_player)
        self.net.eval()
        with torch.no_grad():
            logits, _, _ = self.net(self.net.collate([obs.encoded]).to(self.device))
        index = int(logits.argmax()) if self.greedy else int(torch.multinomial(logits.softmax(-1), 1))
        return obs.actions[index]

    def value(self, game: Game, player: int) -> float:
        """The network's estimate of player's chance to win, in [-1, 1]."""
        obs = observe(game, player)
        self.net.eval()
        with torch.no_grad():
            _, _, value = self.net(self.net.collate([obs.encoded]).to(self.device))
        return float(value[0])
