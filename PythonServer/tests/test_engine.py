import random

import pytest

from src.cards.vanilla import generate_vanilla_set
from src.game.actions import Action, ActionType
from src.game.decks import random_deck
from src.game.engine import Game, GameConfig
from src.game.state import Phase, Zone
from tests.helpers import filler_deck, give_energy, put_in_hand, put_in_play, started_game, unit

END = Action(ActionType.END_TURN)


def test_new_game_deals_hands_and_starts_with_mulligan():
    game = Game(filler_deck(), filler_deck(), seed=0, first_player=1)
    assert game.state.phase == Phase.MULLIGAN
    assert game.state.decision_player == 1
    assert [len(p.hand) for p in game.state.players] == [7, 7]
    assert [len(p.deck) for p in game.state.players] == [53, 53]


def test_mulligan_replaces_marked_cards_without_redrawing_them():
    game = Game(filler_deck(), filler_deck(), seed=0, first_player=0)
    marked = game.state.players[0].hand[:3]
    for uid in marked:
        game.step(Action(ActionType.MULLIGAN, uid))
    assert Action(ActionType.MULLIGAN, marked[0]) not in game.legal_actions()
    game.step(Action(ActionType.KEEP_HAND))
    hand = game.state.players[0].hand
    assert len(hand) == 7 and not set(marked) & set(hand)
    assert game.state.decision_player == 1  # now the second player's mulligan
    game.step(Action(ActionType.KEEP_HAND))
    assert game.state.phase == Phase.MAIN and game.state.turn == 1 and game.state.active_player == 0


def test_first_player_skips_first_draw_only():
    game = started_game()
    assert len(game.state.players[0].hand) == 7
    game.step(END)
    assert len(game.state.players[1].hand) == 8


def test_add_energy_once_per_turn():
    game = started_game()
    energy_actions = [a for a in game.legal_actions() if a.type == ActionType.ADD_ENERGY]
    game.step(energy_actions[0])
    assert game.ready_energy(0) == 1
    assert not any(a.type == ActionType.ADD_ENERGY for a in game.legal_actions())


def test_non_energy_source_cannot_be_added():
    game = started_game()
    uid = put_in_hand(game, 0, unit(energy_source=False, name="No energy"))
    assert Action(ActionType.ADD_ENERGY, uid) not in game.legal_actions()


def test_play_costs_energy_and_unit_is_fresh():
    game = started_game()
    uid = put_in_hand(game, 0, unit(cost=3, name="Three"))
    give_energy(game, 0, 2)
    assert Action(ActionType.PLAY, uid) not in game.legal_actions()
    give_energy(game, 0, 1)
    game.step(Action(ActionType.PLAY, uid))
    assert game.card(uid).zone == Zone.PLAY and game.card(uid).fresh
    assert game.ready_energy(0) == 0
    assert Action(ActionType.SCORE, uid) not in game.legal_actions()


def test_units_and_energy_ready_at_start_of_owners_turn():
    game = started_game()
    uid = put_in_play(game, 0, unit(), exhausted=True, fresh=True)
    give_energy(game, 0, 2)
    for e in game.state.players[0].energy:
        game.card(e).exhausted = True
    game.step(END)
    assert game.card(uid).exhausted  # still the opponent's turn
    game.step(END)
    assert not game.card(uid).exhausted and not game.card(uid).fresh
    assert game.ready_energy(0) == 2
    assert Action(ActionType.SCORE, uid) in game.legal_actions()


def test_score_exhausts_and_gains_vp():
    game = started_game()
    uid = put_in_play(game, 0, unit(score=3))
    game.step(Action(ActionType.SCORE, uid))
    assert game.state.players[0].vp == 3 and game.card(uid).exhausted
    assert Action(ActionType.SCORE, uid) not in game.legal_actions()


def test_reaching_vp_target_wins_immediately():
    game = started_game(config=GameConfig(vp_to_win=5))
    game.state.players[0].vp = 3
    uid = put_in_play(game, 0, unit(score=2))
    game.step(Action(ActionType.SCORE, uid))
    assert game.is_over and game.state.winner == 0
    assert game.legal_actions() == []


def test_duel_only_targets_exhausted_opposing_units():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=3))
    ready_target = put_in_play(game, 1, unit())
    exhausted_target = put_in_play(game, 1, unit(), exhausted=True)
    duels = [a for a in game.legal_actions() if a.type == ActionType.DUEL]
    assert duels == [Action(ActionType.DUEL, attacker, exhausted_target)]
    assert ready_target not in [a.target for a in duels]


def test_duel_deals_damage_both_ways_and_defeats():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=4))
    defender = put_in_play(game, 1, unit(power=2, health=3), exhausted=True)
    game.step(Action(ActionType.DUEL, attacker, defender))
    assert game.card(attacker).damage == 2 and game.card(attacker).exhausted
    assert game.card(defender).zone == Zone.DISCARD and game.card(defender).damage == 0
    assert defender in game.state.players[1].discard


def test_damage_persists_between_turns():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=1, health=5))
    defender = put_in_play(game, 1, unit(power=1, health=5), exhausted=True)
    game.step(Action(ActionType.DUEL, attacker, defender))
    game.step(END)
    game.step(END)
    assert game.card(attacker).damage == 1 and game.card(defender).damage == 1


def test_drawing_from_empty_deck_loses():
    game = started_game()
    game.state.players[1].deck.clear()
    game.step(END)
    assert game.is_over and game.state.winner == 0


def test_turn_cap_is_a_draw():
    game = started_game(config=GameConfig(max_turns=3))
    for _ in range(3):
        game.step(END)
    assert game.is_over and game.state.winner is None


def test_illegal_action_raises():
    game = started_game()
    with pytest.raises(ValueError):
        game.step(Action(ActionType.SCORE, 0))


def test_clone_is_independent_and_shares_card_definitions():
    game = started_game()
    copy = game.clone()
    copy.step(END)
    assert game.state.turn == 1 and copy.state.turn == 2
    assert copy.state.cards[0].card is game.state.cards[0].card


@pytest.mark.parametrize("seed", range(20))
def test_random_games_finish_and_conserve_cards(seed):
    card_set = generate_vanilla_set()
    rng = random.Random(seed)
    game = Game(random_deck(card_set, rng), random_deck(card_set, rng), seed=seed)
    while not game.is_over:
        actions = game.legal_actions()
        assert actions
        game.step(rng.choice(actions))
        for p, ps in enumerate(game.state.players):
            zones = ps.deck + ps.hand + ps.play + ps.energy + ps.discard
            assert len(zones) == 60 and all(game.card(u).owner == p for u in zones)
            assert all(game.card(u).zone == Zone.PLAY for u in ps.play)
    assert game.state.winner in (0, 1, None)
