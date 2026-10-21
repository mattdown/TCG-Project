from src.cards.schema import Card, CardSet
from src.game.actions import Action, ActionType
from src.game.engine import Game, GameConfig
from src.game.state import CardInstance, Zone


def unit(cost=1, power=1, health=1, name=None, traits=(), abilities=(), **keywords) -> Card:
    """A unit card; keywords as flags or values, e.g. unit(guard=1, duelist=2)."""
    name = name or f"Unit {cost}/{power}/{health}"
    return Card(id=name, name=name, type="unit", aspects=("aspect_1",), cost=cost, power=power, health=health,
                traits=tuple(traits), keywords=tuple(sorted(keywords.items())), abilities=tuple(abilities))


def action(*steps, cost=1, name=None) -> Card:
    """An action card whose on-resolve ability is these steps."""
    name = name or f"Action {len(steps)}"
    return Card(id=name, name=name, type="action", aspects=("aspect_1",), cost=cost, power=0, health=0,
                abilities=({"kind": "on_resolve", "steps": list(steps)},))


def filler_deck(size=30) -> list[Card]:
    return [unit(name=f"Filler {i}") for i in range(size)]


def started_game(deck_a=None, deck_b=None, config=GameConfig()) -> Game:
    """A game past the mulligan: player 0 to act on turn 1, with 1 mana crystal."""
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


def give_mana(game: Game, player: int, amount: int):
    """Sets the player's mana crystals, all full."""
    ps = game.state.players[player]
    ps.crystals = ps.mana = amount


def fixture_set() -> CardSet:
    """A few cards with known abilities, for session and engine tests that need card IDs
    (generated sets get new IDs every time they're regenerated)."""
    def static(condition, **modifier):
        return {"kind": "static", "condition": condition, "modifiers": [{"subject": "this", **modifier}]}

    def on(event, *steps):
        return {"kind": "triggered", "trigger": {"event": event}, "condition": None, "steps": list(steps)}

    opponents = {"all": {"owner": "opponent"}}
    weaken = on("on_play", {"choose_one": [
        [{"effect": "damage_hero", "amount": 1, "target": "opponent"}],
        [{"effect": "modify_stat", "stat": "power", "delta": -1, "duration": "this_turn", "target": opponents}]]})
    heal = {"kind": "on_resolve", "steps": [{"may": [{"effect": "damage_hero", "target": "you", "amount": 2}],
                                             "if_you_do": [{"effect": "remove_damage", "amount": "all",
                                                            "target": {"all": {"owner": "you", "cost_max": 2}}}]}]}
    cards = [
        # "When you play this unit, choose one: • Deal 1 damage to the enemy hero. • All enemy units get −1 power this turn."
        Card("WEAKENER", "Weakener", "unit", ("aspect_1",), 5, 5, 3, traits=("Baker",), abilities=(weaken,)),
        # "You may deal 2 damage to your hero. If you do, remove all damage from your units with cost 2 or less."
        Card("HEAL", "Heal", "action", ("aspect_2",), 1, 0, 0, abilities=(heal,)),
        # "Whenever this unit attacks the enemy hero, freeze all enemy units."
        Card("FREEZER", "Freezer", "unit", ("aspect_3",), 3, 1, 2, traits=("Miner",), abilities=(on(
            "on_attack_hero", {"effect": "freeze", "target": opponents}),)),
        # "While this unit is defending, it gets +2 health."
        Card("BRUISER", "Bruiser", "unit", ("aspect_4",), 5, 6, 2, traits=("Chef",),
             abilities=(static({"this_is": "defending"}, stat="health", amount=2),)),
        # "While this unit is defending, it gets +1 health."
        Card("POSTMAN", "Postman", "unit", ("aspect_5",), 2, 1, 2, traits=("Postman",),
             abilities=(static({"this_is": "defending"}, stat="health", amount=1),)),
        # "Whenever this unit attacks the enemy hero, it gains Armor +1 until the start of your next turn."
        Card("SLIPPERY", "Slippery", "unit", ("aspect_6",), 4, 2, 4, traits=("Miner",), abilities=(on(
            "on_attack_hero", {"effect": "grant_keyword", "keyword": "armor", "value": 1,
                               "duration": "until_your_next_turn", "target": "this"}),)),
        # "At the start of your turn, this unit gets +1 power this turn."
        Card("WARMUP", "Warm-up", "unit", ("aspect_1",), 4, 4, 2, traits=("Chef",), abilities=(on(
            "start_of_turn", {"effect": "modify_stat", "stat": "power", "delta": 1, "duration": "this_turn",
                              "target": "this"}),)),
    ]
    fillers = [Card(f"FILLER-{i}", f"Filler {i}", "unit", (f"aspect_{1 + i % 6}",), 2, 2, 2) for i in range(12)]
    return CardSet("fixtures", cards + fillers)  # fillers so 30-card decks can be built
