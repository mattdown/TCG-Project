import pytest

from src.cards import classes as cls
from src.cards.costing import GROUP_SCALE, price, price_group, round_points
from src.cards.generate import generate_card_set
from src.cards.reprice import MAX_COST, reprice, scales_of
from src.cards.vanilla import MAX_STATS, MIN_STATS_VALUE, keyword_value, stat_budget


@pytest.fixture(scope="module")
def card_set():
    return generate_card_set(300, seed=2, classes=True, prefix="T")


def spend(card, scales, classes=True):
    tax = cls.NEUTRAL_TAX if classes and not card.aspects else 0
    return round_points(price(card.abilities[0], card.type, scales)) + keyword_value(dict(card.keywords)) + tax


def test_a_new_set_records_its_prices_and_the_same_prices_change_nothing(card_set):
    assert scales_of(card_set) == GROUP_SCALE
    same, changes = reprice(card_set, {})
    assert same.cards == card_set.cards and not changes


def test_repriced_cards_are_what_the_generator_would_make_at_the_new_prices(card_set):
    new = {"action, draw": GROUP_SCALE["action, draw"] * 3, "unit, deal_damage": 1.0,
           "unit, static self_situational": 0.9}
    repriced, changes = reprice(card_set, new)
    scales = GROUP_SCALE | new
    assert repriced.notes["group_scale"] == scales and changes
    for before, after in zip(card_set.cards, repriced.cards):
        if not before.abilities or price_group(before.abilities[0], before.type) not in new:
            assert after == before  # other groups don't move
            continue
        assert (after.name, after.abilities, after.keywords, after.aspects) == \
               (before.name, before.abilities, before.keywords, before.aspects)
        if after.type == "action":
            if 1 < after.cost < MAX_COST:
                assert after.cost == round_points(price(after.abilities[0], "action", scales) / 2)
        elif after.cost < MAX_COST and after.power + after.health > MIN_STATS_VALUE:
            assert after.power + after.health == stat_budget(after.cost) - spend(after, scales)


def test_dearer_draw_costs_more_and_cheaper_damage_gives_more_stats(card_set):
    repriced, changes = reprice(card_set, {"action, draw": GROUP_SCALE["action, draw"] * 3, "unit, deal_damage": 1.0})
    by_group = {}
    for c in changes:
        by_group.setdefault(c.group, []).append(c)
    assert all(c.new[0] > c.old[0] for c in by_group["action, draw"])
    assert all(sum(c.new[1:]) >= sum(c.old[1:]) and c.new[0] <= c.old[0] for c in by_group["unit, deal_damage"])


def test_units_keep_their_shape_and_stay_legal(card_set):
    repriced, changes = reprice(card_set, {"unit, deal_damage": 8.0, "unit, draw": 0.1})
    by_id = {c.id: c for c in repriced.cards}
    for ch in changes:
        card = by_id[ch.card]
        assert 1 <= card.power <= MAX_STATS["power"] and 1 <= card.health <= MAX_STATS["health"]
        old_power, old_health = ch.old[1:]
        if min(card.power, card.health) > 1 and min(old_power, old_health) > 1:
            assert (card.power >= card.health) == (old_power >= old_health) or abs(card.power - card.health) <= 1
    assert any(c.new[0] > c.old[0] for c in changes)  # some got too dear for their cost and cost more now


def test_repricing_chains_from_the_prices_a_set_was_given(card_set):
    once, _ = reprice(card_set, {"action, draw": 5.1})
    twice, _ = reprice(once, {"action, draw": 5.1})
    assert twice.cards == once.cards  # already at those prices
