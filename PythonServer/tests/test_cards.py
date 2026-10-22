import random
from collections import Counter

from src.cards.schema import Card, load_card_set, save_card_set
from src.cards.vanilla import generate_keyword_set, generate_vanilla_set, stat_budget, stat_value
from src.game.decks import DECK_SIZE, MAX_COPIES, random_deck


def test_generator_is_deterministic():
    assert generate_vanilla_set(seed=3).cards == generate_vanilla_set(seed=3).cards
    assert generate_vanilla_set(seed=3).cards != generate_vanilla_set(seed=4).cards


def test_generated_cards_are_within_one_point_of_budget():
    card_set = generate_vanilla_set()
    assert len(card_set) == 200
    assert len({c.name for c in card_set.cards}) == 200
    for card in card_set.cards:
        delta = stat_value(card.power, card.health) - stat_budget(card.cost)
        assert abs(delta) <= 1
        assert card_set.notes["budget_delta"][card.id] == delta


def test_card_set_round_trip(tmp_path):
    card_set = generate_vanilla_set(n=20)
    save_card_set(card_set, tmp_path / "set.json")
    loaded = load_card_set(tmp_path / "set.json")
    assert loaded.cards == card_set.cards and loaded.notes == card_set.notes


def test_unknown_card_fields_are_rejected():
    data = generate_vanilla_set(n=1).cards[0].to_dict() | {"ability": "fly"}
    try:
        Card.from_dict(data)
    except ValueError as e:
        assert "ability" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_random_decks_are_legal():
    card_set = generate_vanilla_set()
    rng = random.Random(0)
    for one_aspect in (False, True):
        for _ in range(50):
            deck = random_deck(card_set, rng, one_aspect=one_aspect)
            assert len(deck) == DECK_SIZE
            assert max(Counter(c.id for c in deck).values()) <= MAX_COPIES
            if one_aspect:
                assert len({a for c in deck for a in c.aspects}) <= 1  # one aspect plus neutral cards


def test_decks_focus_on_two_jobs():
    card_set = generate_keyword_set()  # 20 jobs
    rng = random.Random(0)

    def top_two_share(focus_jobs):
        shares = []
        for _ in range(100):
            jobs = Counter(c.traits[0] for c in random_deck(card_set, rng, focus_jobs=focus_jobs) if c.traits)
            shares.append(sum(n for _, n in jobs.most_common(2)) / sum(jobs.values()))
        return sum(shares) / len(shares)

    assert top_two_share(2) > 0.6 > top_two_share(0)
