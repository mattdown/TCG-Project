import random

from src.agents.base import Agent
from src.game.actions import Action
from src.game.engine import Game


class RandomAgent(Agent):
    name = "random"

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def choose(self, game: Game) -> Action:
        return self.rng.choice(game.legal_actions())
