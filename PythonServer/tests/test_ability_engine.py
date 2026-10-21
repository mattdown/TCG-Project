"""Abilities in the engine: hand-written cards for each trigger, decision, effect, duration and static."""
from src.game.actions import Action, ActionType
from src.game.state import Zone
from tests.helpers import action, give_mana, put_in_hand, put_in_play, started_game, unit

OPP = {"owner": "opponent"}
END = Action(ActionType.END_TURN)


def triggered(event, *steps, condition=None, trigger_filter=None):
    trigger = {"event": event}
    if trigger_filter:
        trigger["filter"] = trigger_filter
    return {"kind": "triggered", "trigger": trigger, "condition": condition, "steps": list(steps)}


def choose(filter_, name="it"):
    return {"choose": {"count": 1, "filter": filter_}, "as": name}


def effect(op, target, **params):
    return {"effect": op, "target": target, **params}


def it():
    return {"ref": "it"}


def play(game, card, player=0):
    """Puts the card in hand with enough mana and plays it."""
    uid = put_in_hand(game, player, card)
    give_mana(game, player, card.cost)
    game.step(Action(ActionType.PLAY, uid))
    return uid


SNIPER = unit(cost=2, name="Sniper", abilities=[triggered(
    "on_play", choose(OPP), effect("deal_damage", it(), amount=2),
    {"if": {"defeated": "it"}, "then": [effect("draw", "you", amount=1)]})])


# ------------------------------------------------------------------ choices


def test_single_target_is_chosen_automatically():
    game = started_game()
    target = put_in_play(game, 1, unit(health=2, name="Target"))
    hand = len(game.state.players[0].hand)
    play(game, SNIPER)  # play() puts the card in hand first, so playing it leaves the hand size as it was
    assert game.card(target).zone == Zone.DISCARD  # 2 damage defeated it
    assert len(game.state.players[0].hand) == hand + 1  # drew one
    assert not game.state.pending and game.state.decision_player == 0


def test_choose_is_a_decision_when_there_are_options():
    game = started_game()
    tough = put_in_play(game, 1, unit(health=5, name="Tough"))
    weak = put_in_play(game, 1, unit(health=2, name="Weak"))
    play(game, SNIPER)
    assert {a.type for a in game.legal_actions()} == {ActionType.CHOOSE_TARGET}
    assert {a.target for a in game.legal_actions()} == {tough, weak}
    hand = len(game.state.players[0].hand)
    game.step(Action(ActionType.CHOOSE_TARGET, game.state.pending[-1].source, tough))
    assert game.card(tough).damage == 2 and len(game.state.players[0].hand) == hand  # not defeated: no draw
    assert ActionType.END_TURN in {a.type for a in game.legal_actions()}


def test_no_target_means_the_effect_does_nothing():
    game = started_game()
    hand = len(game.state.players[0].hand)
    play(game, SNIPER)
    assert len(game.state.players[0].hand) == hand
    assert not game.state.pending


def test_may_with_a_chosen_discard():
    looter = action({"may": [effect("discard", "you", amount=1, chosen=True)],
                     "if_you_do": [effect("draw", "you", amount=2)]}, name="Looter")
    game = started_game()
    hand_before = len(game.state.players[0].hand)
    play(game, looter)
    assert {a.type for a in game.legal_actions()} == {ActionType.ACCEPT, ActionType.DECLINE}
    game.step(Action(ActionType.ACCEPT, game.state.pending[-1].source))
    discard = game.legal_actions()[0]
    assert discard.type == ActionType.CHOOSE_TARGET and game.card(discard.target).zone == Zone.HAND
    game.step(discard)
    assert game.card(discard.target).zone == Zone.DISCARD
    assert len(game.state.players[0].hand) == hand_before - 1 + 2


def test_may_declined_does_nothing():
    looter = action({"may": [effect("discard", "you", amount=1, chosen=True)],
                     "if_you_do": [effect("draw", "you", amount=2)]}, name="Looter")
    game = started_game()
    hand_before = len(game.state.players[0].hand)
    play(game, looter)
    game.step(Action(ActionType.DECLINE, game.state.pending[-1].source))
    assert len(game.state.players[0].hand) == hand_before


def test_may_isnt_offered_when_the_cost_cant_be_paid():
    sacrifice = action({"may": [effect("damage_hero", "you", amount=2)],
                        "if_you_do": [effect("draw", "you", amount=2)]}, name="Sacrifice")
    game = started_game()
    game.state.players[0].health = 2
    play(game, sacrifice)  # paying 2 health would end the game
    assert not game.state.pending


def test_choose_one():
    charm = action({"choose_one": [[effect("damage_hero", "opponent", amount=2)], [effect("draw", "you", amount=1)]]},
                   name="Charm")
    game = started_game()
    play(game, charm)
    options = game.legal_actions()
    assert [a.option for a in options] == [0, 1] and options[0].type == ActionType.CHOOSE_OPTION
    game.step(options[0])
    assert game.state.players[1].health == 28


# ------------------------------------------------------------------ action cards and activated abilities


def test_action_card_affects_all_matching_units_and_goes_to_discard():
    heal = action(effect("remove_damage", {"all": {"owner": "you", "trait": "Baker"}}, amount="all"), name="Heal")
    game = started_game()
    baker = put_in_play(game, 0, unit(health=5, name="Baker", traits=("Baker",)))
    knight = put_in_play(game, 0, unit(health=5, name="Knight", traits=("Knight",)))
    game.card(baker).damage = game.card(knight).damage = 3
    uid = play(game, heal)
    assert game.card(baker).damage == 0 and game.card(knight).damage == 3
    assert game.card(uid).zone == Zone.DISCARD


def test_activated_ability_costs_the_attack_and_mana():
    """Not generated in rules v2, but the engine keeps them for a later mechanic."""
    wizard = unit(name="Wizard", abilities=[{"kind": "activated", "cost": [{"exhaust_this": True}, {"pay": 2}],
                                             "steps": [effect("draw", "you", amount=1)]}])
    game = started_game()
    uid = put_in_play(game, 0, wizard)
    activate = Action(ActionType.ACTIVATE, uid, option=0)
    give_mana(game, 0, 1)
    assert activate not in game.legal_actions()  # not enough mana
    give_mana(game, 0, 2)
    hand = len(game.state.players[0].hand)
    game.step(activate)
    assert game.card(uid).exhausted and game.mana(0) == 0
    assert len(game.state.players[0].hand) == hand + 1
    assert activate not in game.legal_actions()


def test_fresh_units_cant_activate():
    wizard = unit(name="Wizard", abilities=[{"kind": "activated", "cost": [{"exhaust_this": True}],
                                             "steps": [effect("draw", "you", amount=1)]}])
    game = started_game()
    uid = put_in_play(game, 0, wizard, fresh=True)
    assert ActionType.ACTIVATE not in {a.type for a in game.legal_actions()}


def test_exhaust_another_cost_is_a_choice():
    general = unit(name="General", abilities=[{"kind": "activated",
                                               "cost": [{"exhaust_this": True}, {"exhaust_another": 1}],
                                               "steps": [effect("damage_hero", "opponent", amount=2)]}])
    game = started_game()
    uid = put_in_play(game, 0, general)
    a = put_in_play(game, 0, unit(name="A"))
    b = put_in_play(game, 0, unit(name="B"))
    game.step(Action(ActionType.ACTIVATE, uid, option=0))
    assert {x.target for x in game.legal_actions()} == {a, b}
    game.step(Action(ActionType.CHOOSE_TARGET, uid, a))
    assert game.card(a).exhausted and not game.card(b).exhausted and game.state.players[1].health == 28


# ------------------------------------------------------------------ triggers


def test_on_attack_hero_and_on_defeated_triggers():
    raider = unit(name="Raider", abilities=[triggered("on_attack_hero", effect("draw", "you", amount=1))])
    martyr = unit(name="Martyr", abilities=[triggered("on_defeated", effect("damage_hero", "opponent", amount=3))])
    game = started_game()
    r = put_in_play(game, 0, raider)
    hand = len(game.state.players[0].hand)
    game.step(Action(ActionType.ATTACK_HERO, r))
    assert len(game.state.players[0].hand) == hand + 1 and game.state.players[1].health == 29
    m = put_in_play(game, 1, martyr)
    attacker = put_in_play(game, 0, unit(power=3, health=3, name="Attacker"))
    game.step(Action(ActionType.ATTACK, attacker, m))
    assert game.card(m).zone == Zone.DISCARD and game.state.players[0].health == 27


def test_on_attack_hero_doesnt_trigger_on_unit_attacks():
    raider = unit(name="Raider", health=5, abilities=[triggered("on_attack_hero", effect("draw", "you", amount=1))])
    game = started_game()
    r = put_in_play(game, 0, raider)
    target = put_in_play(game, 1, unit(health=5, name="Target"))
    hand = len(game.state.players[0].hand)
    game.step(Action(ActionType.ATTACK, r, target))
    assert len(game.state.players[0].hand) == hand


def test_on_attack_resolves_before_damage():
    brute = unit(power=1, health=5, name="Brute", abilities=[triggered(
        "on_attack", effect("modify_stat", "this", stat="power", delta=2, duration="this_turn"))])
    game = started_game()
    b = put_in_play(game, 0, brute)
    target = put_in_play(game, 1, unit(health=5, name="Target"))
    game.step(Action(ActionType.ATTACK, b, target))
    assert game.card(target).damage == 3


def test_start_and_end_of_turn_triggers():
    farmer = unit(name="Farmer", abilities=[triggered("start_of_turn", effect("damage_hero", "opponent", amount=1)),
                                            triggered("end_of_turn", effect("damage_hero", "opponent", amount=2))])
    game = started_game()
    put_in_play(game, 0, farmer)
    game.step(END)
    assert game.state.players[1].health == 28
    game.step(END)
    assert game.state.players[1].health == 27


def test_another_played_trigger_checks_its_filter():
    captain = unit(name="Captain", abilities=[triggered(
        "another_played", effect("damage_hero", "opponent", amount=1),
        trigger_filter={"owner": "you", "trait": "Sailor", "not_this": True})])
    game = started_game()
    put_in_play(game, 0, captain)
    play(game, unit(name="Sailor", traits=("Sailor",)))
    play(game, unit(name="Baker", traits=("Baker",)))
    assert game.state.players[1].health == 29


def test_opposing_defeated_trigger():
    hunter = unit(name="Hunter", abilities=[triggered("opposing_defeated", effect("draw", "you", amount=1))])
    game = started_game()
    put_in_play(game, 0, hunter)
    victim = put_in_play(game, 1, unit(name="Victim"))
    attacker = put_in_play(game, 0, unit(power=2, health=3, name="Attacker"))
    hand = len(game.state.players[0].hand)
    game.step(Action(ActionType.ATTACK, attacker, victim))
    assert len(game.state.players[0].hand) == hand + 1


def test_trigger_condition():
    comeback = unit(name="Comeback", abilities=[triggered(
        "on_play", effect("heal_hero", "you", amount=2), condition={"behind_on_health": True})])
    game = started_game()
    game.state.players[0].health = 25
    game.state.players[1].health = 20
    play(game, comeback)
    assert game.state.players[0].health == 25
    game.state.players[1].health = 28
    play(game, unit(name="Comeback 2", abilities=comeback.abilities))
    assert game.state.players[0].health == 27


def test_heal_hero_stops_at_full_health():
    tea = action(effect("heal_hero", "you", amount=5), name="Tea")
    game = started_game()
    game.state.players[0].health = 28
    play(game, tea)
    assert game.state.players[0].health == 30


def test_gain_crystal_adds_an_empty_crystal():
    sprout = action(effect("gain_crystal", "you"), name="Sprout")
    game = started_game()
    give_mana(game, 0, 3)
    game.step(Action(ActionType.PLAY, put_in_hand(game, 0, sprout)))  # costs 1
    assert game.state.players[0].crystals == 4 and game.mana(0) == 2


# ------------------------------------------------------------------ durations


def test_this_turn_bonus_expires():
    pump = action(choose({"owner": "you"}), effect("modify_stat", it(), stat="power", delta=2, duration="this_turn"),
                  name="Pump")
    game = started_game()
    u = put_in_play(game, 0, unit(power=1, name="U"))
    play(game, pump)
    assert game.stat(u, "power") == 3
    game.step(END)
    assert game.stat(u, "power") == 1


def test_freeze_stops_one_turn_of_attacks():
    freeze = action(choose(OPP), effect("freeze", it()), name="Freeze")
    game = started_game()
    target = put_in_play(game, 1, unit(name="Target"))
    play(game, freeze)
    game.step(END)
    assert game.card(target).exhausted  # its turn started: it can't attack
    assert not any(a.card == target for a in game.legal_actions())
    game.step(END)
    game.step(END)
    assert not game.card(target).exhausted


def test_health_bonus_ending_can_defeat():
    shield = action(choose({"owner": "you"}), effect("modify_stat", it(), stat="health", delta=2,
                                                     duration="this_turn"), name="Shield")
    game = started_game()
    u = put_in_play(game, 0, unit(health=2, name="U"))
    play(game, shield)
    game.card(u).damage = 3
    game.step(END)
    assert game.card(u).zone == Zone.DISCARD


# ------------------------------------------------------------------ statics and amounts


def test_scaling_static_applies_only_while_attacking():
    champion = unit(power=1, health=9, name="Champion", abilities=[{
        "kind": "static", "condition": {"this_is": "attacking"},
        "modifiers": [{"subject": "this", "stat": "power",
                       "amount": {"per": {"owner": "any", "trait": "Fisher"}, "k": 1, "cap": 3}}]}])
    game = started_game()
    c = put_in_play(game, 0, champion)
    for i in range(4):
        put_in_play(game, i % 2, unit(name=f"Fisher {i}", traits=("Fisher",)))
    target = put_in_play(game, 1, unit(power=1, health=9, name="Target"))
    assert game.stat(c, "power") == 1
    assert game.attack_damage(c, target) == (1, 4)  # 1 + 3 (4 Fishers, capped at 3)
    assert game.attack_damage(target, c) == (1, 1)  # defending: no bonus
    assert game.attack_damage(c, None) == (0, 4)  # attacking the hero counts too


def test_lord_bonus_ends_when_the_lord_leaves():
    lord = unit(power=1, health=1, name="Lord", abilities=[{
        "kind": "static", "condition": None,
        "modifiers": [{"subject": {"all": {"owner": "you", "trait": "Knight", "not_this": True}},
                       "stat": "health", "amount": 1}]}])
    game = started_game()
    lord_uid = put_in_play(game, 1, lord)
    knight = put_in_play(game, 1, unit(health=1, name="Knight", traits=("Knight",)))
    game.card(knight).damage = 1
    assert game.stat(knight, "health") == 2
    attacker = put_in_play(game, 0, unit(power=1, health=3, name="Attacker"))
    game.step(Action(ActionType.ATTACK, attacker, lord_uid))
    assert game.card(lord_uid).zone == Zone.DISCARD and game.card(knight).zone == Zone.DISCARD


def test_static_keyword_while_damaged():
    wall = unit(health=5, name="Wall", abilities=[{"kind": "static", "condition": {"this_is": "damaged"},
                                                    "modifiers": [{"subject": "this", "keyword": "guard"}]}])
    game = started_game()
    attacker = put_in_play(game, 0, unit(name="Attacker"))
    w = put_in_play(game, 1, wall)
    other = put_in_play(game, 1, unit(name="Other"))
    assert game.attack_targets(attacker) == ([w, other], True)
    game.card(w).damage = 1
    assert game.attack_targets(attacker) == ([w], False)


def test_hidden_elusive_units_cant_be_chosen_by_enemy_abilities():
    game = started_game()
    sneaky = put_in_play(game, 1, unit(health=5, name="Sneaky", elusive=1))
    plain = put_in_play(game, 1, unit(health=5, name="Plain"))
    play(game, SNIPER)  # only one legal target left, so it's chosen automatically
    assert game.card(plain).damage == 2 and game.card(sneaky).damage == 0


def test_cost_reduction_static():
    guild = unit(name="Guild", abilities=[{"kind": "static", "condition": None,
                                           "modifiers": [{"cost_reduction": 1, "filter": {"owner": "you", "trait": "Chef"}}]}])
    game = started_game()
    put_in_play(game, 0, guild)
    chef = put_in_hand(game, 0, unit(cost=3, name="Chef", traits=("Chef",)))
    baker = put_in_hand(game, 0, unit(cost=3, name="Baker", traits=("Baker",)))
    assert game.play_cost(chef) == 2 and game.play_cost(baker) == 3


def test_scaling_damage():
    storm = action(choose(OPP), effect("deal_damage", it(), amount={"per": {"owner": "you"}, "k": 1, "cap": 4}),
                   name="Storm")
    game = started_game()
    for i in range(3):
        put_in_play(game, 0, unit(name=f"Ally {i}"))
    target = put_in_play(game, 1, unit(health=9, name="Target"))
    play(game, storm)
    assert game.card(target).damage == 3


# ------------------------------------------------------------------ cloning mid-ability


def test_clone_in_the_middle_of_a_decision():
    game = started_game()
    a = put_in_play(game, 1, unit(health=5, name="A"))
    b = put_in_play(game, 1, unit(health=5, name="B"))
    play(game, SNIPER)
    copy = game.clone()
    copy.step(Action(ActionType.CHOOSE_TARGET, copy.state.pending[-1].source, a))
    assert copy.card(a).damage == 2 and game.card(a).damage == 0
    game.step(Action(ActionType.CHOOSE_TARGET, game.state.pending[-1].source, b))
    assert game.card(b).damage == 2 and copy.card(b).damage == 0


def test_returning_to_a_full_hand_discards_the_card():
    bounce = action(choose(OPP), effect("return_to_hand", it()), name="Bounce")
    game = started_game()
    target = put_in_play(game, 1, unit(name="Target"))
    while len(game.state.players[1].hand) < 10:
        put_in_hand(game, 1, unit())
    play(game, bounce)
    assert game.card(target).zone == Zone.DISCARD and len(game.state.players[1].hand) == 10
