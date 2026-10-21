import pytest

from src.cards.schema import Card
from src.cards.vanilla import generate_keyword_set, keyword_value, stat_budget, stat_value
from src.game.actions import Action, ActionType
from src.game.state import Zone
from tests.helpers import fixture_set, give_mana, put_in_hand, put_in_play, started_game, unit


def attacks(game):
    return {(a.card, a.target) for a in game.legal_actions() if a.type in (ActionType.ATTACK, ActionType.ATTACK_HERO)}


def test_guard_must_be_attacked_first_and_blocks_the_hero():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=3))
    other = put_in_play(game, 1, unit(name="Other"))
    guard = put_in_play(game, 1, unit(name="Guard", guard=1))
    assert attacks(game) == {(attacker, guard)}
    game.step(Action(ActionType.ATTACK, attacker, guard))
    assert game.card(guard).zone == Zone.DISCARD
    assert attacks(game) == set()  # the attacker has attacked
    assert game.card(other).zone == Zone.PLAY


def test_elusive_attacker_is_revealed_and_can_then_be_chosen():
    game = started_game()
    sneaky = put_in_play(game, 0, unit(power=1, health=3, name="Sneaky", elusive=1))
    assert game.hidden(sneaky)
    game.step(Action(ActionType.ATTACK_HERO, sneaky))
    assert not game.hidden(sneaky) and game.keyword(sneaky, "elusive")


def test_charge_attacks_the_turn_its_played():
    game = started_game()
    rusher = put_in_hand(game, 0, unit(cost=1, name="Rusher", charge=1))
    plain = put_in_hand(game, 0, unit(cost=1, name="Plain"))
    give_mana(game, 0, 2)
    game.step(Action(ActionType.PLAY, rusher))
    game.step(Action(ActionType.PLAY, plain))
    assert (rusher, None) in attacks(game)
    assert not any(a == plain for a, _ in attacks(game))


def test_duelist_adds_power_only_when_attacking():
    game = started_game()
    duelist = put_in_play(game, 0, unit(power=1, health=5, name="Duelist", duelist=2))
    target = put_in_play(game, 1, unit(power=1, health=5, name="Target"))
    assert game.attack_damage(duelist, target) == (1, 3)
    assert game.attack_damage(target, duelist) == (1, 1)
    assert game.attack_damage(duelist, None) == (0, 3)


def test_armor_reduces_damage_but_not_below_zero():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=5))
    armored = put_in_play(game, 1, unit(power=1, health=5, name="Armored", armor=2))
    assert game.attack_damage(attacker, armored) == (1, 1)
    weak = put_in_play(game, 0, unit(power=1, health=5, name="Weak"))
    assert game.attack_damage(weak, armored) == (1, 0)
    result = game.step(Action(ActionType.ATTACK, attacker, armored), record=True)
    assert game.card(armored).damage == 1 and result.damage == {attacker: 1, armored: 1}


def test_keyword_json_round_trip_and_validation():
    card = unit(guard=1, duelist=2)
    assert card.to_dict()["keywords"] == {"duelist": 2, "guard": True}
    assert Card.from_dict(card.to_dict()) == card
    with pytest.raises(ValueError):
        unit(flying=1)
    with pytest.raises(ValueError):
        unit(guard=2)


def test_keyword_set_spends_budget_on_keywords():
    card_set = generate_keyword_set()
    assert len({c.name for c in card_set.cards}) == len(card_set) == 200
    with_keywords = [c for c in card_set.cards if c.keywords]
    assert 60 <= len(with_keywords) <= 130
    for card in card_set.cards:
        value = stat_value(card.power, card.health) + keyword_value(dict(card.keywords))
        assert abs(value - stat_budget(card.cost)) <= 1
        assert card.traits and card.power >= 1 and card.health >= 1


def test_granted_armor_lasts_through_the_opponents_turn():
    game = started_game()
    slippery = put_in_play(game, 0, fixture_set()["SLIPPERY"])
    game.step(Action(ActionType.ATTACK_HERO, slippery))
    assert game.keyword(slippery, "armor") == 1
    game.step(Action(ActionType.END_TURN))  # the opponent's turn: still armored
    assert game.keyword(slippery, "armor") == 1
    game.step(Action(ActionType.END_TURN))  # back to us: it's gone
    assert not game.keyword(slippery, "armor")
