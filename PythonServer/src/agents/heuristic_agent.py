"""A simple rule-based player: a fixed baseline for evaluating trained agents."""
from src.agents.base import Agent
from src.game.actions import Action, ActionType
from src.game.engine import Game


class HeuristicAgent(Agent):
    name = "heuristic"

    def choose(self, game: Game) -> Action:
        actions = game.legal_actions()
        by_type = {}
        for a in actions:
            by_type.setdefault(a.type, []).append(a)

        if ActionType.KEEP_HAND in by_type:
            # Put back cards costing 6+ when the hand has fewer than three cheap cards.
            hand = [game.card(a.card).card for a in by_type.get(ActionType.MULLIGAN, [])]
            cheap = sum(c.cost <= 3 for c in hand)
            expensive = [a for a in by_type.get(ActionType.MULLIGAN, []) if game.card(a.card).card.cost >= 6]
            return expensive[0] if cheap < 3 and expensive else by_type[ActionType.KEEP_HAND][0]

        # Add an energy source every turn, keeping the cheaper cards to play.
        if ActionType.ADD_ENERGY in by_type:
            return max(by_type[ActionType.ADD_ENERGY], key=lambda a: game.card(a.card).card.cost)

        # Play the most expensive affordable unit.
        if ActionType.PLAY in by_type:
            return max(by_type[ActionType.PLAY], key=lambda a: game.card(a.card).card.cost)

        # Duel when the attacker defeats the target and survives, preferring high-score targets.
        good_duels = [a for a in by_type.get(ActionType.DUEL, []) if self._wins_duel(game, a)]
        if good_duels:
            return max(good_duels, key=lambda a: game.card(a.target).card.score)

        if ActionType.SCORE in by_type:
            return max(by_type[ActionType.SCORE], key=lambda a: game.card(a.card).card.score)

        return by_type[ActionType.END_TURN][0]

    @staticmethod
    def _wins_duel(game: Game, action: Action) -> bool:
        attacker, defender = game.card(action.card), game.card(action.target)
        to_attacker, to_defender = game.duel_damage(action.card, action.target)
        defeats = to_defender >= defender.card.health - defender.damage
        survives = to_attacker < attacker.card.health - attacker.damage
        return defeats and survives
