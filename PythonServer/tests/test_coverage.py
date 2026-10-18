import random

from src.cards.abilities import AbilitySampler
from src.cards.costing import ability_value
from src.cards.coverage import card_features, coverage_report, generate_coverage_set
from src.cards.theme import JOBS


def test_coverage_set_uses_every_building_block_twice():
    card_set = generate_coverage_set(seed=3)
    features = card_set.notes["features"]
    assert len(features) > 50
    assert all(len(cards) >= 2 for cards in features.values())
    assert {f for c in card_set.cards for f in card_features(c)} == set(features)
    assert len({c.name for c in card_set.cards}) == len(card_set)


def test_coverage_set_only_refers_to_its_own_jobs():
    card_set = generate_coverage_set(seed=4)
    jobs = set(card_set.notes["jobs"])
    assert {c.traits[0] for c in card_set.cards if c.type == "unit"} <= jobs
    text = coverage_report(card_set)
    assert not any(f" {job} unit" in text for job in set(JOBS) - jobs)


def test_units_can_afford_their_abilities():
    for card in generate_coverage_set(seed=5).cards:
        if card.type == "unit":
            assert card.power >= 1 and card.health >= 1


def test_ability_values_are_positive_and_scale():
    sampler = AbilitySampler(random.Random(0))
    assert all(ability_value(sampler.ability("unit")) > 0 for _ in range(500))

    def draw(n):
        return {"kind": "on_resolve", "steps": [{"effect": "draw", "target": "you", "amount": n}]}

    assert ability_value(draw(2)) == 2 * ability_value(draw(1))
    repeatable = {"kind": "triggered", "trigger": {"event": "start_of_turn"}, "condition": None,
                  "steps": draw(1)["steps"]}
    assert ability_value(repeatable) > ability_value(draw(1))
