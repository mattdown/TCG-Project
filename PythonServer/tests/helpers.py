from src.cards.schema import Card
from src.game.actions import Action, ActionType
from src.game.engine import Game, GameConfig
from src.game.state import CardInstance, Zone


def unit(cost=1, power=1, health=1, score=1, energy_source=True, name=None, traits=(), abilities=(),
         **keywords) -> Card:
    """A unit card; keywords as flags or values, e.g. unit(guard=1, duelist=2)."""
    name = name or f"Unit {cost}/{power}/{health}/{score}"
    return Card(id=name, name=name, type="unit", aspects=("aspect_1",), energy_source=energy_source,
                cost=cost, power=power, health=health, score=score, traits=tuple(traits),
                keywords=tuple(sorted(keywords.items())), abilities=tuple(abilities))


def action(*steps, cost=1, name=None) -> Card:
    """An action card whose on-resolve ability is these steps."""
    name = name or f"Action {len(steps)}"
    return Card(id=name, name=name, type="action", aspects=("aspect_1",), energy_source=True, cost=cost,
                power=0, health=0, score=0, abilities=({"kind": "on_resolve", "steps": list(steps)},))


def filler_deck(size=60) -> list[Card]:
    return [unit(name=f"Filler {i}") for i in range(size)]


def started_game(deck_a=None, deck_b=None, config=GameConfig()) -> Game:
    """A game past the mulligan: player 0 to act on turn 1."""
    game = Game(deck_a or filler_deck(), deck_b or filler_deck(), seed=0, first_player=0, config=config)
    game.step(Action(ActionType.KEEP_HAND))
    game.step(Action(ActionType.KEEP_HAND))
    return game


def put_in_play(game: Game, player: int, card: Card, exhausted=False, fresh=False) -> int:
    """Adds a new card instance straight into play and returns its uid."""
    uid = len(game.state.cards)
    game.state.cards.append(CardInstance(uid, card, player, Zone.PLAY, exhausted=exhausted, fresh=fresh))
    game.state.players[player].play.append(uid)
    return uid


def put_in_hand(game: Game, player: int, card: Card) -> int:
    uid = len(game.state.cards)
    game.state.cards.append(CardInstance(uid, card, player, Zone.HAND))
    game.state.players[player].hand.append(uid)
    return uid


def give_energy(game: Game, player: int, amount: int):
    for _ in range(amount):
        uid = len(game.state.cards)
        game.state.cards.append(CardInstance(uid, unit(name="Energy"), player, Zone.ENERGY))
        game.state.players[player].energy.append(uid)
