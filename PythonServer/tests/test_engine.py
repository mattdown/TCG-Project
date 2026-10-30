import random
from dataclasses import replace

import pytest

from src.cards.vanilla import generate_vanilla_set
from src.game.actions import Action, ActionType
from src.game.decks import random_deck
from src.game.engine import Game, GameConfig, Move, deck_aspect
from src.game.state import Phase, Zone
from tests.helpers import action, fixture_set, give_mana, put_in_hand, put_in_play, started_game, unit, filler_deck

END = Action(ActionType.END_TURN)


def test_new_game_deals_three_and_five_and_starts_with_mulligan():
    game = Game(filler_deck(), filler_deck(), seed=0, first_player=1)
    assert game.state.phase == Phase.MULLIGAN
    assert game.state.decision_player == 1
    assert [len(p.hand) for p in game.state.players] == [5, 3]
    assert [len(p.deck) for p in game.state.players] == [25, 27]
    assert [p.spare_spore for p in game.state.players] == [1, 0]
    assert [p.health for p in game.state.players] == [30, 30]


def test_mulligan_replaces_marked_cards_without_redrawing_them():
    game = Game(filler_deck(), filler_deck(), seed=0, first_player=0)
    marked = game.state.players[0].hand[:2]
    for uid in marked:
        game.step(Action(ActionType.MULLIGAN, uid))
    assert Action(ActionType.MULLIGAN, marked[0]) not in game.legal_actions()
    game.step(Action(ActionType.KEEP_HAND))
    hand = game.state.players[0].hand
    assert len(hand) == 3 and not set(marked) & set(hand)
    assert game.state.decision_player == 1  # now the second player's mulligan
    game.step(Action(ActionType.KEEP_HAND))
    assert game.state.phase == Phase.MAIN and game.state.turn == 1 and game.state.active_player == 0


def test_every_turn_draws_and_adds_a_mana_crystal():
    game = started_game()
    assert len(game.state.players[0].hand) == 4  # 3 + the first turn's draw
    assert (game.state.players[0].crystals, game.mana(0)) == (1, 1)
    game.step(END)
    assert len(game.state.players[1].hand) == 6  # 5 + the draw
    assert (game.state.players[1].crystals, game.mana(1)) == (1, 1)
    game.step(END)
    assert (game.state.players[0].crystals, game.mana(0)) == (2, 2)


def test_mana_caps_at_ten_and_refills():
    game = started_game()
    give_mana(game, 0, 10)
    game.state.players[0].mana = 3
    game.step(END)
    game.step(END)
    assert (game.state.players[0].crystals, game.mana(0)) == (10, 10)


def test_play_costs_mana_and_unit_is_fresh():
    game = started_game()
    uid = put_in_hand(game, 0, unit(cost=3, name="Three"))
    give_mana(game, 0, 2)
    assert Action(ActionType.PLAY, uid) not in game.legal_actions()
    give_mana(game, 0, 3)
    game.step(Action(ActionType.PLAY, uid))
    assert game.card(uid).zone == Zone.PLAY and game.card(uid).fresh
    assert game.mana(0) == 0
    assert not any(a.card == uid and a.type in (ActionType.ATTACK, ActionType.ATTACK_HERO)
                   for a in game.legal_actions())


def test_board_holds_seven_units():
    game = started_game()
    for _ in range(7):
        put_in_play(game, 0, unit())
    uid = put_in_hand(game, 0, unit(cost=0, name="Zero"))
    assert Action(ActionType.PLAY, uid) not in game.legal_actions()


def test_spare_spore_gives_one_mana_once():
    game = started_game()
    game.step(END)
    assert Action(ActionType.SPARE_SPORE) in game.legal_actions()
    game.step(Action(ActionType.SPARE_SPORE))
    assert game.mana(1) == 2 and not game.state.players[1].spare_spore
    assert Action(ActionType.SPARE_SPORE) not in game.legal_actions()


def test_units_can_attack_again_at_start_of_owners_turn():
    game = started_game()
    uid = put_in_play(game, 0, unit(), attacked=True, fresh=True)
    game.step(END)
    assert game.card(uid).attacked  # still the opponent's turn
    game.step(END)
    assert not game.card(uid).attacked and not game.card(uid).fresh
    assert Action(ActionType.ATTACK_HERO, uid) in game.legal_actions()


def test_attack_any_enemy_unit_or_the_hero():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=3))
    ready = put_in_play(game, 1, unit())
    attacked = put_in_play(game, 1, unit(), attacked=True)
    attacks = {(a.type, a.target) for a in game.legal_actions() if a.card == attacker}
    assert attacks == {(ActionType.ATTACK, ready), (ActionType.ATTACK, attacked), (ActionType.ATTACK_HERO, None)}


def test_guard_must_be_attacked_first():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=3))
    put_in_play(game, 1, unit())
    guard = put_in_play(game, 1, unit(guard=1))
    attacks = [(a.type, a.target) for a in game.legal_actions() if a.card == attacker]
    assert attacks == [(ActionType.ATTACK, guard)]


def test_elusive_hides_until_it_attacks():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=3))
    sneaky = put_in_play(game, 1, unit(power=1, health=3, elusive=1))
    assert not any(a.target == sneaky for a in game.legal_actions())
    game.step(END)
    game.step(Action(ActionType.ATTACK, sneaky, attacker))
    game.step(END)
    assert Action(ActionType.ATTACK, attacker, sneaky) in game.legal_actions()


def test_hidden_guard_doesnt_force_attacks():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=3))
    put_in_play(game, 1, unit(guard=1, elusive=1))
    assert Action(ActionType.ATTACK_HERO, attacker) in game.legal_actions()


def test_attack_deals_damage_both_ways_and_defeats():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=4))
    defender = put_in_play(game, 1, unit(power=2, health=3))
    game.step(Action(ActionType.ATTACK, attacker, defender))
    assert game.card(attacker).damage == 2 and game.card(attacker).attacked
    assert game.card(defender).zone == Zone.DISCARD and game.card(defender).damage == 0
    assert defender in game.state.players[1].discard


def test_attacking_the_hero_and_winning():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=4, health=1, duelist=1))
    game.step(Action(ActionType.ATTACK_HERO, attacker))
    assert game.state.players[1].health == 25 and game.card(attacker).damage == 0
    game.state.players[1].health = 3
    game.card(attacker).attacked = False
    game.step(Action(ActionType.ATTACK_HERO, attacker))
    assert game.is_over and game.state.winner == 0 and game.legal_actions() == []
    assert game.state.players[1].health == 0  # overkill doesn't take it below 0


def test_charge_attacks_the_turn_its_played_and_zero_power_cant_attack():
    game = started_game()
    rusher = put_in_play(game, 0, unit(power=2, charge=1), fresh=True)
    wall = put_in_play(game, 0, unit(power=0, health=5))
    assert Action(ActionType.ATTACK_HERO, rusher) in game.legal_actions()
    assert not any(a.card == wall for a in game.legal_actions())


def test_damage_persists_between_turns():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=1, health=5))
    defender = put_in_play(game, 1, unit(power=1, health=5))
    game.step(Action(ActionType.ATTACK, attacker, defender))
    game.step(END)
    game.step(END)
    assert game.card(attacker).damage == 1 and game.card(defender).damage == 1


def test_empty_deck_deals_growing_damage():
    game = started_game()
    game.state.players[1].deck.clear()
    game.step(END)
    assert game.state.players[1].health == 29
    game.step(END)
    game.step(END)
    assert game.state.players[1].health == 27


def test_full_hand_burns_the_drawn_card():
    game = started_game()
    while len(game.state.players[1].hand) < 10:
        put_in_hand(game, 1, unit())
    top = game.state.players[1].deck[-1]
    game.step(END)
    assert game.card(top).zone == Zone.DISCARD and len(game.state.players[1].hand) == 10


def test_turn_cap_is_a_draw():
    game = started_game(config=GameConfig(max_turns=3))
    for _ in range(3):
        game.step(END)
    assert game.is_over and game.state.winner is None


def test_illegal_action_raises():
    game = started_game()
    with pytest.raises(ValueError):
        game.step(Action(ActionType.ATTACK_HERO, 0))


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
            zones = ps.deck + ps.hand + ps.play + ps.discard
            assert len(zones) == 30 and all(game.card(u).owner == p for u in zones)
            assert all(game.card(u).zone == Zone.PLAY for u in ps.play)
            assert len(ps.play) <= 7 and len(ps.hand) <= 10
    assert game.state.winner in (0, 1, None)


# --- step results (what the client animates and previews)

def test_step_records_nothing_unless_asked():
    game = started_game()
    assert game.step(END) is None


def test_attack_result_has_damage_defeat_and_moves():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=4))
    defender = put_in_play(game, 1, unit(power=2, health=3))
    result = game.step(Action(ActionType.ATTACK, attacker, defender), record=True)
    assert result.damage == {attacker: 2, defender: 3}
    assert result.defeated == [defender] and result.attacked == [attacker]
    assert result.moves == [Move(defender, 1, Zone.PLAY, Zone.DISCARD)]


def test_play_and_hero_attack_results():
    game = started_game()
    card = put_in_hand(game, 0, unit(cost=2))
    attacker = put_in_play(game, 0, unit(power=3))
    give_mana(game, 0, 3)
    played = game.step(Action(ActionType.PLAY, card), record=True)
    assert played.mana_spent == {0: 2} and played.moves == [Move(card, 0, Zone.HAND, Zone.PLAY)]
    hit = game.step(Action(ActionType.ATTACK_HERO, attacker), record=True)
    assert hit.hero_damage == {1: 3} and hit.attacked == [attacker]


def test_end_turn_result_has_the_draw():
    game = started_game()
    top = game.state.players[1].deck[-1]
    result = game.step(END, record=True)
    assert result.moves == [Move(top, 1, Zone.DECK, Zone.HAND)]


def test_keep_hand_result_has_mulligan_moves():
    game = Game(filler_deck(), filler_deck(), seed=0, first_player=0)
    marked = game.state.players[0].hand[0]
    game.step(Action(ActionType.MULLIGAN, marked))
    result = game.step(Action(ActionType.KEEP_HAND), record=True)
    assert result.moves[0] == Move(marked, 0, Zone.HAND, Zone.DECK)
    assert result.moves[1].source == Zone.DECK and result.moves[1].dest == Zone.HAND


def test_recorded_step_matches_unrecorded_step():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=2, health=2))
    defender = put_in_play(game, 1, unit(power=2, health=2))
    plain = game.clone()
    game.step(Action(ActionType.ATTACK, attacker, defender), record=True)
    plain.step(Action(ActionType.ATTACK, attacker, defender))
    assert game.state == plain.state


def test_results_record_lasting_effects():
    cards = {c.id: c for c in fixture_set().cards}
    game = started_game()
    chef = put_in_play(game, 0, cards["WARMUP"])  # "At the start of your turn, this unit gets +1 power this turn."
    game.step(END)
    result = game.step(END, record=True)
    assert [(e.uid, e.kind, e.stat, e.value) for e in result.effects] == [(chef, "stat", "power", 1)]
    assert game.stat(chef, "power") == cards["WARMUP"].power + 1


def test_hero_takes_the_decks_aspect():
    glow = replace(unit(name="Glow"), aspects=("aspect_5",))
    neutral = replace(unit(name="Neutral"), aspects=())
    assert deck_aspect([glow] * 10 + [neutral] * 20) == "aspect_5"
    assert deck_aspect([neutral] * 30) is None
    game = Game([glow] * 10 + [neutral] * 20, filler_deck(), seed=0, first_player=0)
    assert [p.aspect for p in game.state.players] == ["aspect_5", "aspect_1"]


def test_buff_lasts_until_the_unit_leaves_play():
    game = started_game()
    a = put_in_play(game, 0, unit(power=1, health=1, name="A"))
    b = put_in_play(game, 0, unit(power=2, health=2, name="B"))
    feast = action({"effect": "buff", "power": 2, "health": 1, "target": {"all": {"owner": "you"}}}, name="Feast")
    uid = put_in_hand(game, 0, feast)
    give_mana(game, 0, 1)
    game.step(Action(ActionType.PLAY, uid))
    assert [(game.stat(u, "power"), game.stat(u, "health")) for u in (a, b)] == [(3, 2), (4, 3)]
    for _ in range(4):  # it doesn't wear off
        game.step(END)
    assert (game.stat(a, "power"), game.stat(a, "health")) == (3, 2)
    game._move(a, Zone.HAND)
    assert (game.stat(a, "power"), game.stat(a, "health")) == (1, 1)



SPROUT = {"name": "Sprout", "power": 1, "health": 2, "keywords": {"guard": 1}, "trait": "Baker"}


def test_summon_puts_fresh_tokens_into_play_up_to_a_full_board():
    game = started_game()
    for i in range(5):
        put_in_play(game, 0, unit(name=f"U{i}"))
    sprouts = action({"effect": "summon", "amount": 3, "target": "you", "token": SPROUT}, name="Sprouts")
    uid = put_in_hand(game, 0, sprouts)
    give_mana(game, 0, 1)
    result = game.step(Action(ActionType.PLAY, uid), record=True)
    tokens = game.state.players[0].play[5:]
    assert len(tokens) == 2 and result.summoned == tokens  # 7 units is a full board
    token = game.card(tokens[0])
    assert token.fresh and token.card.traits == ("Baker",) and game.keyword(tokens[0], "guard")
    assert (game.stat(tokens[0], "power"), game.stat(tokens[0], "health")) == (1, 2)


def test_a_token_returned_to_hand_is_gone():
    game = started_game()
    sprouts = action({"effect": "summon", "amount": 1, "target": "you", "token": SPROUT}, name="Sprouts")
    uid = put_in_hand(game, 0, sprouts)
    give_mana(game, 0, 1)
    game.step(Action(ActionType.PLAY, uid))
    token = game.state.players[0].play[-1]
    gust = action({"effect": "return_to_hand", "target": {"all": {"owner": "opponent"}}}, name="Gust")
    gust_uid = put_in_hand(game, 1, gust)
    game.step(END)
    give_mana(game, 1, 1)
    game.step(Action(ActionType.PLAY, gust_uid))
    assert game.card(token).zone == Zone.DISCARD and token not in game.state.players[0].hand


ENEMY_UNIT = {"choose": {"count": 1, "filter": {"owner": "opponent"}}, "as": "it"}
HIT_IT = {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 2}


def test_an_action_with_nothing_to_choose_cant_be_played():
    game = started_game()
    bolt = put_in_hand(game, 0, action(ENEMY_UNIT, HIT_IT, name="Bolt"))
    give_mana(game, 0, 1)
    assert game.unusable(bolt) and Action(ActionType.PLAY, bolt) not in game.legal_actions()
    put_in_play(game, 1, unit(health=3))
    assert not game.unusable(bolt) and Action(ActionType.PLAY, bolt) in game.legal_actions()


def test_choose_one_offers_only_options_with_something_to_choose():
    draw = {"effect": "draw", "amount": 1, "target": "you"}
    charm = action({"choose_one": [[ENEMY_UNIT, HIT_IT], [draw]]}, name="Charm")
    game = started_game()
    uid = put_in_hand(game, 0, charm)
    give_mana(game, 0, 1)
    assert not game.unusable(uid)  # the draw option still does something
    game.step(Action(ActionType.PLAY, uid))
    assert [a.option for a in game.legal_actions()] == [1]

    only_targets = action({"choose_one": [[ENEMY_UNIT, HIT_IT], [ENEMY_UNIT, HIT_IT]]}, name="Twin")
    assert game.unusable(put_in_hand(game, 0, only_targets))
