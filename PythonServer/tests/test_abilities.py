import random

import pytest

from src.cards.abilities import AbilitySampler, card_problems, render, validate

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
    assert render(ability) == ("When you play this unit, deal 2 damage to chosen opposing unit. "
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
    hurt_yourself = [{"effect": "lose_vp", "amount": 1, "target": "you"}]
    assert validate({"kind": "on_resolve", "steps": hurt_yourself}, "action")
    as_cost = [{"may": hurt_yourself, "if_you_do": [{"effect": "draw", "amount": 2, "target": "you"}]}]
    assert validate({"kind": "on_resolve", "steps": as_cost}, "action") == []


def test_activated_abilities_must_cost_exhaust_this():
    ability = {"kind": "activated", "cost": [{"pay": 2}],
               "steps": [{"effect": "draw", "amount": 1, "target": "you"}]}
    assert any("must cost ⟳" in p for p in validate(ability))
    ability["cost"] = [{"exhaust_this": True}, {"pay": 2}]
    assert validate(ability) == []
    assert render(ability) == "⟳, 2 energy: Draw a card."


def test_activated_abilities_have_no_may():
    may = {"may": [{"effect": "discard", "amount": 1, "target": "you"}],
           "if_you_do": [{"effect": "draw", "amount": 2, "target": "you"}]}
    ability = {"kind": "activated", "cost": [{"exhaust_this": True}], "steps": [may]}
    assert any("before the colon" in p for p in validate(ability))


def test_ready_bars_scoring_and_activating():
    steps = [{"choose": {"count": 1, "filter": {"owner": "you", "not_this": True}}, "as": "it"},
             {"effect": "ready", "target": {"ref": "it"}}]
    ability = {"kind": "activated", "cost": [{"exhaust_this": True}], "steps": steps}
    assert any("barred" in p for p in validate(ability))
    steps[1]["no_score_or_activate"] = True
    assert validate(ability) == []
    assert render(ability) == ("⟳: Ready another chosen unit of yours. "
                               "It can’t score or use ⟳ abilities this turn.")


def test_defensive_keywords_last_until_your_next_turn():
    grant = {"effect": "grant_keyword", "keyword": "elusive", "value": 1, "target": "this"}
    ability = {"kind": "triggered", "trigger": {"event": "on_score"}, "condition": None, "steps": [grant]}
    assert any("until the start of your next turn" in p for p in validate({**ability, "steps": [
        {**grant, "duration": "this_turn"}]}))
    good = {**ability, "steps": [{**grant, "duration": "until_your_next_turn"}]}
    assert validate(good) == []
    assert render(good) == "Whenever this unit scores, this unit gains Elusive until the start of your next turn."


def test_charge_is_never_granted():
    grant = {"effect": "grant_keyword", "keyword": "charge", "value": 1, "duration": "this_turn", "target": "this"}
    ability = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [grant]}
    assert any("Charge" in p for p in validate(ability))


def test_sampler_grants_keywords_for_the_right_time():
    for ability, card_type in sample(3000, seed=9):
        for step in ability.get("steps", []):
            if step.get("effect") == "grant_keyword":
                assert step["keyword"] != "charge"
                assert step["duration"] == ("this_turn" if step["keyword"] == "duelist" else "until_your_next_turn")


def test_card_level_checks():
    damaged = {"kind": "static", "condition": {"this_is": "damaged"}, "modifiers": [
        {"subject": "this", "stat": "power", "amount": 1}]}
    assert card_problems("unit", 1, {}, [damaged])
    assert card_problems("unit", 2, {}, [damaged]) == []
    score_now = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [
        {"effect": "modify_stat", "stat": "score", "delta": 1, "duration": "this_turn", "target": "this"}]}
    assert card_problems("unit", 3, {}, [score_now])
    power_now = {**score_now, "steps": [{**score_now["steps"][0], "stat": "power"}]}
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
