import random

import pytest

from src.cards.abilities import AbilitySampler, _effects_in, card_problems, render, validate

OPPOSING = {"owner": "opponent"}


def sample(n, seed=0):
    rng = random.Random(seed)
    sampler = AbilitySampler(rng)
    for _ in range(n):
        card_type = "action" if rng.random() < 0.25 else "unit"
        yield sampler.ability(card_type), card_type


def test_sampled_abilities_are_valid_and_render():
    for ability, card_type in sample(2000):
        assert validate(ability, card_type) == [], ability
        text = render(ability, card_type)
        assert text and "{" not in text and "None" not in text


def test_plan_example_renders():
    ability = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [
        {"choose": {"count": 1, "filter": OPPOSING}, "as": "it"},
        {"effect": "deal_damage", "amount": 2, "target": {"ref": "it"}},
        {"if": {"defeated": "it"}, "then": [{"effect": "draw", "amount": 1, "target": "you"}]}]}
    assert validate(ability) == []
    assert render(ability) == ("When you play this unit, deal 2 damage to chosen enemy unit. "
                               "If it was defeated, draw a card.")


def test_scaling_static_renders():
    ability = {"kind": "static", "condition": {"this_is": "attacking"}, "modifiers": [
        {"subject": "this", "stat": "power", "amount": {"per": {"owner": "any", "trait": "Elf"}, "k": 1, "cap": 4}}]}
    assert validate(ability) == []
    assert render(ability) == "While this unit is attacking, it gets +1 power for each Elf unit in play (up to +4)."


@pytest.mark.parametrize("steps, problem", [
    ([{"effect": "deal_damage", "amount": 2, "target": {"ref": "it"}}], "before it is chosen"),
    ([{"effect": "deal_damage", "amount": 2, "target": "you"}], "needs a unit target"),
    ([{"effect": "draw", "amount": 1, "target": "opponent"}], "helps its target but targets opponent"),
    ([{"effect": "deal_damage", "amount": 9, "target": {"all": OPPOSING}}], "outside"),
    ([{"effect": "deal_damage", "amount": {"per": OPPOSING, "k": 1}, "target": {"all": OPPOSING}}], "without a cap"),
    ([{"effect": "defeat", "target": {"all": OPPOSING}}], "can't target all"),
    ([{"choose": {"count": 1, "filter": OPPOSING}, "as": "it"}, {"effect": "defeat", "target": {"ref": "it"}}],
     "restricted target"),
])
def test_validation_catches_problems(steps, problem):
    problems = validate({"kind": "on_resolve", "steps": steps}, "action")
    assert any(problem in p for p in problems), problems


def test_self_harm_is_allowed_only_as_a_may_cost():
    hurt_yourself = [{"effect": "damage_hero", "amount": 2, "target": "you"}]
    assert validate({"kind": "on_resolve", "steps": hurt_yourself}, "action")
    as_cost = [{"may": hurt_yourself, "if_you_do": [{"effect": "draw", "amount": 2, "target": "you"}]}]
    assert validate({"kind": "on_resolve", "steps": as_cost}, "action") == []


def test_defensive_keywords_last_until_your_next_turn():
    grant = {"effect": "grant_keyword", "keyword": "guard", "value": 1, "target": "this"}
    ability = {"kind": "triggered", "trigger": {"event": "on_attack_hero"}, "condition": None, "steps": [grant]}
    assert any("until the start of your next turn" in p for p in validate({**ability, "steps": [
        {**grant, "duration": "this_turn"}]}))
    good = {**ability, "steps": [{**grant, "duration": "until_your_next_turn"}]}
    assert validate(good) == []
    assert render(good) == ("Whenever this unit attacks the enemy hero, this unit gains Guard until the start of "
                            "your next turn.")


@pytest.mark.parametrize("keyword", ["charge", "elusive"])
def test_charge_and_elusive_are_never_granted(keyword):
    grant = {"effect": "grant_keyword", "keyword": keyword, "value": 1, "duration": "this_turn", "target": "this"}
    ability = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [grant]}
    assert any("can't be granted" in p for p in validate(ability))


def test_sampler_grants_keywords_for_the_right_time():
    for ability, card_type in sample(3000, seed=9):
        for step in ability.get("steps", []):
            if step.get("effect") == "grant_keyword":
                assert step["keyword"] not in ("charge", "elusive")
                assert step["duration"] == ("this_turn" if step["keyword"] == "duelist" else "until_your_next_turn")


def test_card_level_checks():
    damaged = {"kind": "static", "condition": {"this_is": "damaged"}, "modifiers": [
        {"subject": "this", "stat": "power", "amount": 1}]}
    assert card_problems("unit", 1, {}, [damaged])
    assert card_problems("unit", 2, {}, [damaged]) == []
    power_now = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [
        {"effect": "modify_stat", "stat": "power", "delta": 1, "duration": "this_turn", "target": "this"}]}
    assert card_problems("unit", 3, {}, [power_now])
    assert card_problems("unit", 3, {"charge": 1}, [power_now]) == []


def test_end_of_turn_bonuses_last_through_the_opponents_turn():
    buff = {"effect": "modify_stat", "stat": "power", "delta": 2, "target": {"all": {"owner": "you"}}}
    ability = {"kind": "triggered", "trigger": {"event": "end_of_turn"}, "condition": None, "steps": [buff]}
    assert any("ends as soon as it starts" in p for p in validate({**ability, "steps": [
        {**buff, "duration": "this_turn"}]}))
    good = {**ability, "steps": [{**buff, "duration": "until_your_next_turn"}]}
    assert validate(good) == []
    assert render(good) == "At the end of your turn, your units get +2 power until the start of your next turn."
    for sampled, _ in sample(3000, seed=11):
        if sampled["kind"] == "triggered" and sampled["trigger"]["event"] == "end_of_turn":
            assert validate(sampled) == []


def test_on_play_self_healing_is_rejected():
    heal = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [
        {"effect": "remove_damage", "amount": 2, "target": "this"}]}
    assert any("just played" in p for p in card_problems("unit", 3, {}, [heal]))


def test_sampler_follows_rules_v2():
    """Nothing refers to the v1 rules."""
    for ability, _ in sample(3000, seed=12):
        assert ability["kind"] in ("triggered", "static", "on_resolve")
        effects = {e["effect"] for e in _effects_in(ability.get("steps", []))}
        assert not effects & {"ready", "exhaust", "gain_vp", "lose_vp", "add_energy", "cant_ready"}


def _random_pick(filter_):
    return {"choose": {"count": 1, "filter": filter_, "chooser": "random"}, "as": "it"}


def test_sampled_abilities_keep_the_health_rules():
    """No temporary health; a unit never heals itself whenever it's damaged; damaged units never buy health."""
    for ability, _ in sample(3000, seed=5):
        event = ability.get("trigger", {}).get("event")
        for e in _effects_in(ability.get("steps", [])):
            assert not (e["effect"] == "modify_stat" and e["stat"] == "health")
            if event == "damaged" and e["target"] == "this":
                assert e["effect"] != "remove_damage" and not (e["effect"] == "buff" and e["health"])
            if isinstance(e.get("amount"), dict) and e["amount"]["per"].get("damaged"):
                assert not e.get("health")
            if event == "token_summoned":
                assert e["effect"] != "summon"


def test_the_sampler_makes_each_new_construct():
    seen = set()
    for ability, _ in sample(3000, seed=6):
        seen.add(ability.get("trigger", {}).get("event"))
        text = render(ability)
        seen |= {k for k in ("split at random", "a random", "played this turn", "in your hand", "units with")
                 if k in text}
    assert {"ally_defeated", "damaged", "action_played", "token_summoned", "split at random", "a random",
            "played this turn", "in your hand", "units with"} <= seen


def test_random_and_split_targets_render():
    hit = {"kind": "on_resolve", "steps": [_random_pick({"owner": "opponent", "damaged": True}),
                                           {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 2}]}
    assert validate(hit, "action") == []
    assert render(hit, "action") == "Deal 2 damage to a random damaged enemy unit."
    split = {"kind": "on_resolve", "steps": [{"repeat": 3, "steps": [
        _random_pick(OPPOSING), {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 1}]}]}
    assert validate(split, "action") == []
    assert render(split, "action") == "Deal 3 damage split at random among enemy units."


def test_repeat_must_be_a_random_choice_and_one_effect():
    chosen = {"choose": {"count": 1, "filter": OPPOSING}, "as": "it"}
    bad = {"kind": "on_resolve", "steps": [{"repeat": 3, "steps": [
        chosen, {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 1}]}]}
    assert any("repeat" in p for p in validate(bad, "action"))
    too_many = {"kind": "on_resolve", "steps": [{"repeat": 9, "steps": [
        _random_pick(OPPOSING), {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 1}]}]}
    assert any("outside" in p for p in validate(too_many, "action"))


def test_new_triggers_and_counts_render():
    def on(event, *steps, condition=None, **trigger):
        return {"kind": "triggered", "trigger": {"event": event, **trigger}, "condition": condition, "steps": list(steps)}
    draw = {"effect": "draw", "target": "you", "amount": 1}
    played = {"owner": "you", "played_this_turn": True, "zone": "any", "type": "any", "not_this": True}
    assert render(on("ally_defeated", draw, filter={"owner": "you", "zone": "discard", "trait": "Miner"})) == \
        "Whenever another of your Miner units is defeated, draw a card."
    assert render(on("damaged", draw)) == "Whenever this unit takes damage and survives, draw a card."
    assert render(on("action_played", draw)) == "Whenever you play an action, draw a card."
    assert render(on("token_summoned", draw, condition={"count": played, "at_least": 2})) == \
        "Whenever you summon a token, if you've played 2 or more other cards this turn, draw a card."
    per_hand = {"effect": "damage_hero", "target": "opponent", "amount": {"per": {
        "owner": "you", "zone": "hand", "type": "any"}, "k": 1, "cap": 3}}
    assert render({"kind": "on_resolve", "steps": [{**per_hand, "effect": "draw", "target": "you"}]}, "action") == \
        "Draw a card for each card in your hand (up to 3)."


def test_validation_of_the_new_trigger_rules():
    heal_self = {"kind": "triggered", "trigger": {"event": "damaged"}, "condition": None,
                 "steps": [{"effect": "remove_damage", "target": "this", "amount": 1}]}
    assert any("heals" in p for p in validate(heal_self))
    token = {"name": "Sprout", "power": 1, "health": 1}
    loop = {"kind": "triggered", "trigger": {"event": "token_summoned"}, "condition": None,
            "steps": [{"effect": "summon", "target": "you", "amount": 1, "token": token}]}
    assert any("token" in p for p in validate(loop))
    damaged_health = {"kind": "on_resolve", "steps": [{"effect": "buff", "target": {"all": {"owner": "you"}},
                                                       "power": 0, "health": 1, "amount": {
                                                           "per": {"owner": "any", "damaged": True}, "k": 1, "cap": 3}}]}
    assert any("damaged" in p for p in validate(damaged_health, "action"))
