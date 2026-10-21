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

        decision = game.pending_decision()
        if decision:
            return self._decide(game, decision[1], actions)

        if ActionType.KEEP_HAND in by_type:
            # Put back cards costing 6+ when the hand has fewer than three cheap cards.
            hand = [game.card(a.card).card for a in by_type.get(ActionType.MULLIGAN, [])]
            cheap = sum(c.cost <= 3 for c in hand)
            expensive = [a for a in by_type.get(ActionType.MULLIGAN, []) if game.card(a.card).card.cost >= 6]
            return expensive[0] if cheap < 3 and expensive else by_type[ActionType.KEEP_HAND][0]

        # Play the most expensive affordable card, using the Spare Spore if it makes one affordable.
        if ActionType.PLAY in by_type:
            return max(by_type[ActionType.PLAY], key=lambda a: game.card(a.card).card.cost)
        if ActionType.SPARE_SPORE in by_type and self._spore_helps(game):
            return by_type[ActionType.SPARE_SPORE][0]

        # Trade when the attacker defeats the target and survives, preferring expensive targets;
        # otherwise go for the hero.
        good_trades = [a for a in by_type.get(ActionType.ATTACK, []) if self._wins_trade(game, a)]
        if good_trades:
            return max(good_trades, key=lambda a: game.card(a.target).card.cost)
        if ActionType.ATTACK_HERO in by_type:
            return by_type[ActionType.ATTACK_HERO][0]
        if ActionType.ATTACK in by_type:  # Guard is in the way: attack it anyway
            return by_type[ActionType.ATTACK][0]

        return by_type[ActionType.END_TURN][0]

    @staticmethod
    def _decide(game: Game, node, actions: list[Action]) -> Action:
        """Choices inside abilities: always say yes, take the first option, and pick the most
        expensive opposing card or the cheapest of your own (usually a cost being paid)."""
        if node.kind == "may":
            return next(a for a in actions if a.type == ActionType.ACCEPT)
        if node.kind == "choose_one":
            return actions[0]
        mine = node.data["filter"].get("owner") == "you"
        by_cost = sorted(actions, key=lambda a: game.card(a.target).card.cost)
        return by_cost[0] if mine else by_cost[-1]

    @staticmethod
    def _spore_helps(game: Game) -> bool:
        p = game.state.decision_player
        hand = [game.card(u) for u in game.state.players[p].hand]
        return any(game.play_cost(c.uid) == game.mana(p) + 1 for c in hand)

    @staticmethod
    def _wins_trade(game: Game, action: Action) -> bool:
        attacker, defender = game.card(action.card), game.card(action.target)
        to_attacker, to_defender = game.attack_damage(action.card, action.target)
        defeats = to_defender >= defender.card.health - defender.damage
        survives = to_attacker < attacker.card.health - attacker.damage
        return defeats and survives
