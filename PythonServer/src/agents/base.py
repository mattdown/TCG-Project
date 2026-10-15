from src.game.actions import Action
from src.game.engine import Game


class Agent:
    name = "agent"

    def choose(self, game: Game) -> Action:
        """Pick one of game.legal_actions() for game.state.decision_player."""
        raise NotImplementedError
