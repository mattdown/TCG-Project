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
    buff = {"effect": "modify_stat", "stat": "health", "delta": 2, "target": {"all": {"owner": "you"}}}
    ability = {"kind": "triggered", "trigger": {"event": "end_of_turn"}, "condition": None, "steps": [buff]}
    assert any("ends as soon as it starts" in p for p in validate({**ability, "steps": [
        {**buff, "duration": "this_turn"}]}))
    good = {**ability, "steps": [{**buff, "duration": "until_your_next_turn"}]}
    assert validate(good) == []
    assert render(good) == "At the end of your turn, your units get +2 health until the start of your next turn."
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
