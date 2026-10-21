import random

from scripts.card_lab import one, run
from src.cards.abilities import AbilitySampler, card_problems, render
from src.agents.heuristic_agent import HeuristicAgent
from src.agents.match import play_match
from src.agents.random_agent import RandomAgent
from src.cards.generate import CardGenerator, generate_ability_set
from src.cards.quality import (MAX_COMPLEXITY, complexity, disconnected_steps, dominated_options, quality_problems,
                               skeleton)
from src.cards.names import full_name, main_effect, static_kind
from src.cards.theme import ACTION_WORDS, JOBS
from src.cards.trace import Tracer, path_probability

OPPOSING = {"owner": "opponent"}


def on_play(*steps, condition=None):
    return {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": condition, "steps": list(steps)}


def choose(name="it", f=OPPOSING):
    return {"choose": {"count": 1, "filter": f}, "as": name}


def damage(n, target=None):
    return {"effect": "deal_damage", "amount": n, "target": target or {"ref": "it"}}


def gain(n):
    return {"effect": "heal_hero", "amount": n, "target": "you"}


def test_complexity_counts_every_node():
    assert complexity(on_play(gain(1))) == 1
    assert complexity(on_play(choose(), damage(2), {"if": {"defeated": "it"}, "then": [gain(1)]})) == 4
    assert complexity(on_play(gain(1), condition={"behind_on_health": True})) == 2
    activated = {"kind": "activated", "cost": [{"exhaust_this": True}, {"pay": 2}], "steps": [gain(1)]}
    assert complexity(activated) == 2


def test_steps_must_connect():
    follow_up = on_play(choose(), damage(2), {"if": {"defeated": "it"}, "then": [gain(1)]})
    assert disconnected_steps(follow_up["steps"]) == []
    glued = on_play(choose(), damage(2), gain(1))
    assert disconnected_steps(glued["steps"]) == ["'heal_hero' isn't connected to the steps before it"]
    # Player effects don't connect: "draw a card, heal your hero" is two ideas.
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


def _decisions(node):
    for c in node["children"]:
        if "section" in c:
            yield from _decisions(c)
        else:
            yield c


def test_trace_records_every_decision_with_its_options():
    generator = CardGenerator(random.Random(4))
    for _ in range(30):
        a = generator.card()
        steps = list(_decisions(a.trace))
        assert steps[0]["decision"] == "Action card?"
        assert any(d["decision"] == "Ability kind" for d in steps)
        for d in steps:
            chosen = next(o for o in d["options"] if o["name"] == d["chosen"])
            assert chosen["p"] > 0
            assert abs(sum(o["p"] for o in d["options"]) - 1) < 5e-3  # each p is rounded
        assert 0 < path_probability(a.trace) <= 1


def test_tracing_matches_plain_sampling():
    """The tracer draws from the random generator exactly as plain calls would."""
    rng = random.Random(9)
    plain = random.Random(9)
    tracer = Tracer(rng)
    assert tracer.weighted("x", {"a": 1, "b": 0, "c": 3}) == plain.choices(["a", "c"], [1, 3])[0]
    assert tracer.chance("y", 0.3) == (plain.random() < 0.3)
    assert tracer.small("z", 1, 5) == plain.choices([1, 2, 3, 4, 5], [1, 1 / 2, 1 / 3, 1 / 4, 1 / 5])[0]
    assert rng.random() == plain.random()


def test_explorer_data():
    data = one(seed=12, jobs=6, action_share=0.25, variety=1)
    kept = data["kept"]
    assert kept["stopped_at"] is None and kept["card"] is not None
    assert 0 < kept["ability_p"] <= 1 and kept["ability_decisions"] >= 1
    assert all(a["stopped_at"] and "trace" in a for a in data["others"])


def test_names_are_unique_and_actions_get_event_names():
    generator = CardGenerator(random.Random(6), jobs=JOBS[:2])
    cards = [generator.card().card for _ in range(300)]
    assert len({full_name(c) for c in cards}) == len(cards)
    for c in cards:
        if c.type == "unit":
            assert c.subtitle and c.name.split()[-1] in JOBS[:2]
        else:
            assert not c.subtitle and not any(job in c.name for job in JOBS)
            assert c.name.split()[0] in {w for words in ACTION_WORDS.values() for w in words}


def test_main_effect_and_static_kind():
    may = on_play({"may": [{"effect": "damage_hero", "target": "you", "amount": 2}], "if_you_do": [gain(3)]})
    assert main_effect(may) == "heal_hero"
    discount = {"kind": "static", "condition": None, "modifiers": [{"cost_reduction": 1, "filter": {"owner": "you"}}]}
    assert static_kind(discount) == "discount"


def test_ability_set_is_playable():
    card_set = generate_ability_set(60, seed=2)
    assert len(card_set) == 60 and card_set.name == "abilities_60"
    assert [c.id for c in card_set.cards[:2]] == ["A1-001", "A1-002"]
    assert {c.traits[0] for c in card_set.cards if c.type == "unit"} <= set(card_set.notes["jobs"])
    result = play_match(RandomAgent(), HeuristicAgent(), card_set, num_games=4, seed=1)
    assert result
