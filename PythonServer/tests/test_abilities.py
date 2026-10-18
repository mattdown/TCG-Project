import random

import pytest

from src.cards.abilities import AbilitySampler, render, validate

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
