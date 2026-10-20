import random

from scripts.card_lab import run
from src.cards.abilities import AbilitySampler, card_problems, render
from src.cards.generate import CardGenerator
from src.cards.quality import (MAX_COMPLEXITY, complexity, disconnected_steps, dominated_options, quality_problems,
                               skeleton)

OPPOSING = {"owner": "opponent"}


def on_play(*steps, condition=None):
    return {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": condition, "steps": list(steps)}


def choose(name="it", f=OPPOSING):
    return {"choose": {"count": 1, "filter": f}, "as": name}


def damage(n, target=None):
    return {"effect": "deal_damage", "amount": n, "target": target or {"ref": "it"}}


def gain(n):
    return {"effect": "gain_vp", "amount": n, "target": "you"}


def test_complexity_counts_every_node():
    assert complexity(on_play(gain(1))) == 1
    assert complexity(on_play(choose(), damage(2), {"if": {"defeated": "it"}, "then": [gain(1)]})) == 4
    assert complexity(on_play(gain(1), condition={"behind_on_vp": True})) == 2
    activated = {"kind": "activated", "cost": [{"exhaust_this": True}, {"pay": 2}], "steps": [gain(1)]}
    assert complexity(activated) == 2


def test_steps_must_connect():
    follow_up = on_play(choose(), damage(2), {"if": {"defeated": "it"}, "then": [gain(1)]})
    assert disconnected_steps(follow_up["steps"]) == []
    glued = on_play(choose(), damage(2), gain(1))
    assert disconnected_steps(glued["steps"]) == ["'gain_vp' isn't connected to the steps before it"]
    # Player effects don't connect: "draw a card, gain 1 VP" is two ideas.
    assert disconnected_steps([{"effect": "draw", "amount": 1, "target": "you"}, gain(1)])
    # Choose one's options are alternatives, not a sequence.
    assert disconnected_steps([{"choose_one": [[gain(1)], [choose(), damage(1)]]}]) == []


def test_dominated_options():
    assert dominated_options(on_play({"choose_one": [[gain(3)], [gain(1)]]}))
    assert dominated_options(on_play({"choose_one": [[gain(2)], [gain(2)]]}))  # the same option twice
    assert dominated_options(on_play({"choose_one": [[gain(2)], [choose(), damage(1)]]})) == []
    # Same shape, but each option is bigger somewhere: a real choice.
    a = [choose("it", {"owner": "opponent", "cost_max": 2}), damage(3)]
    b = [choose("it", {"owner": "opponent", "cost_max": 4}), damage(1)]
    assert dominated_options(on_play({"choose_one": [a, b]})) == []


def test_skeleton_ignores_numbers_and_optionally_jobs():
    lord = lambda job, n: {"kind": "static", "condition": None, "modifiers": [
        {"subject": {"all": {"owner": "you", "trait": job, "not_this": True}}, "stat": "health", "amount": n}]}
    assert skeleton(lord("Chef", 1)) == skeleton(lord("Chef", 2))
    assert skeleton(lord("Chef", 1)) != skeleton(lord("Fisher", 1))
    assert skeleton(lord("Chef", 1), abstract_traits=True) == skeleton(lord("Fisher", 1), abstract_traits=True)


def test_sampled_abilities_pass_the_quality_tests():
    rng = random.Random(0)
    sampler = AbilitySampler(rng)
    for i in range(1000):
        ability = sampler.ability("action" if i % 4 == 0 else "unit")
        assert quality_problems(ability) == [] and complexity(ability) <= MAX_COMPLEXITY


def test_keyword_the_unit_already_has_cant_matter():
    elusive = {"kind": "static", "condition": {"this_is": "damaged"},
               "modifiers": [{"subject": "this", "keyword": "elusive", "value": 1}]}
    assert card_problems("unit", 3, {"elusive": 1}, [elusive])
    assert card_problems("unit", 3, {}, [elusive]) == []
    armor = {**elusive, "modifiers": [{"subject": "this", "keyword": "armor", "value": 1}]}
    assert card_problems("unit", 3, {"armor": 1}, [armor]) == []  # numbered keywords add up


def test_generator_records_every_attempt_and_keeps_one_ability_per_card():
    generator = CardGenerator(random.Random(1), variety=3)
    kept = [generator.card() for _ in range(40)]
    assert all(a.stopped_at is None and len(a.card.abilities) == 1 for a in kept)
    assert len(generator.attempts) >= 3 * len(kept)
    stopped = [a for a in generator.attempts if a.stopped_at]
    assert all(a.problems for a in stopped)
    assert {a.stopped_at for a in stopped} <= {"grammar", "quality", "card", "variety"}


def test_variety_spreads_shapes():
    def distinct(variety):
        generator = CardGenerator(random.Random(2), variety=variety)
        return len({skeleton(generator.card().ability, abstract_traits=True) for _ in range(60)})
    assert distinct(4) > distinct(1)


def test_card_lab_data():
    data = run(seed=3, count=10, jobs=6, action_share=0.25, variety=2)
    assert len(data["kept"]) == 10
    for a in data["attempts"]:
        assert a["checks"][0]["test"] == "grammar"
        assert (a["card"] is None) == (a["stopped_at"] in ("grammar", "quality", "card"))
    assert all(data["attempts"][i]["card"]["traits"][0] in data["job_list"]
               for i in data["kept"] if data["attempts"][i]["card"]["type"] == "unit")
    assert render(data["attempts"][data["kept"][0]]["tree"], data["attempts"][data["kept"][0]]["card_type"])
