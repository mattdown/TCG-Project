import pytest

from src.cards.schema import Card
from src.cards.vanilla import generate_keyword_set, keyword_value, stat_budget, stat_value
from src.game.actions import Action, ActionType
from src.game.state import Zone
from tests.helpers import put_in_hand, give_energy, put_in_play, started_game, unit


def duels(game):
    return {(a.card, a.target) for a in game.legal_actions() if a.type == ActionType.DUEL}


def test_guard_can_be_dueled_while_ready_and_must_be_dueled_first():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=3))
    exhausted = put_in_play(game, 1, unit(name="Tired"), exhausted=True)
    guard = put_in_play(game, 1, unit(name="Guard", guard=1))
    assert duels(game) == {(attacker, guard)}
    game.step(Action(ActionType.DUEL, attacker, guard))
    assert game.card(guard).zone == Zone.DISCARD
    assert duels(game) == set()  # the attacker is exhausted now
    assert game.card(exhausted).zone == Zone.PLAY


def test_without_a_guard_only_exhausted_units_are_targets():
    game = started_game()
    attacker = put_in_play(game, 0, unit())
    put_in_play(game, 1, unit(name="Ready"))
    tired = put_in_play(game, 1, unit(name="Tired"), exhausted=True)
    assert duels(game) == {(attacker, tired)}


def test_elusive_can_only_be_dueled_by_elusive():
    game = started_game()
    plain = put_in_play(game, 0, unit(name="Plain"))
    flier = put_in_play(game, 0, unit(name="Flier", elusive=1))
    target = put_in_play(game, 1, unit(name="Target", elusive=1), exhausted=True)
    assert duels(game) == {(flier, target)}
    assert plain not in {a for a, _ in duels(game)}


def test_elusive_guard_doesnt_force_non_elusive_attackers():
    game = started_game()
    attacker = put_in_play(game, 0, unit())
    put_in_play(game, 1, unit(name="Elusive guard", guard=1, elusive=1))
    tired = put_in_play(game, 1, unit(name="Tired"), exhausted=True)
    assert duels(game) == {(attacker, tired)}


def test_charge_can_duel_but_not_score_while_fresh():
    game = started_game()
    rusher = put_in_hand(game, 0, unit(cost=1, name="Rusher", charge=1))
    target = put_in_play(game, 1, unit(name="Tired"), exhausted=True)
    give_energy(game, 0, 1)
    game.step(Action(ActionType.PLAY, rusher))
    assert (rusher, target) in duels(game)
    assert Action(ActionType.SCORE, rusher) not in game.legal_actions()


def test_duelist_adds_power_only_when_attacking():
    game = started_game()
    duelist = put_in_play(game, 0, unit(power=1, health=5, name="Duelist", duelist=2))
    target = put_in_play(game, 1, unit(power=1, health=5, name="Target"), exhausted=True)
    assert game.duel_damage(duelist, target) == (1, 3)
    assert game.duel_damage(target, duelist) == (1, 1)


def test_armor_reduces_damage_but_not_below_zero():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=5))
    armored = put_in_play(game, 1, unit(power=1, health=5, name="Armored", armor=2), exhausted=True)
    assert game.duel_damage(attacker, armored) == (1, 1)
    weak = put_in_play(game, 0, unit(power=1, health=5, name="Weak"))
    assert game.duel_damage(weak, armored) == (1, 0)
    result = game.step(Action(ActionType.DUEL, attacker, armored), record=True)
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
        value = stat_value(card.power, card.health, card.score) + keyword_value(dict(card.keywords))
        assert abs(value - stat_budget(card.cost, card.energy_source)) <= 1
        assert card.traits and card.power >= 1 and card.health >= 1
