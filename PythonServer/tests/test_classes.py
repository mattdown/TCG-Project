from collections import Counter

import pytest

from src.cards import classes as cls
from src.cards.generate import generate_card_set


@pytest.fixture(scope="module")
def class_set():
    return generate_card_set(400, seed=3, classes=True, prefix="T")


def test_the_ring_gives_each_style_to_two_neighbouring_classes():
    styles = Counter(s for pair in cls.CLASSES.values() for s in pair)
    assert set(styles) == set(cls.STYLES) and set(styles.values()) == {2}
    for a, b in cls.CLASSES.values():
        assert abs(cls.STYLES.index(a) - cls.STYLES.index(b)) in (1, 5)  # neighbours on the ring
    for aspect, own in cls.CLASSES.items():
        assert not set(own) & set(cls.opposite(aspect)) and not set(own) & set(cls.neighbours(aspect))


def test_a_class_never_makes_its_opposite_styles_signatures():
    for aspect in cls.CLASSES:
        tilt = cls.tilt(cls.CLASSES[aspect], aspect)
        for label, options in cls.zeros(aspect).items():
            assert all(tilt[label][o] == 0 for o in options)
        assert cls.zeros(aspect)  # every class gives something up


def test_class_cards_keep_to_their_class(class_set):
    for card in class_set.cards:
        if card.aspects:
            assert not cls.class_problems(card, card.aspects[0]), card


def test_classes_are_even_and_neutrals_are_units(class_set):
    by_class = Counter(c.aspects[0] if c.aspects else "neutral" for c in class_set.cards)
    counts = [n for a, n in by_class.items() if a != "neutral"]
    assert len(counts) == 6 and max(counts) - min(counts) <= 1
    neutral = [c for c in class_set.cards if not c.aspects]
    assert 0.2 < len(neutral) / len(class_set.cards) < 0.4
    assert all(c.type == "unit" for c in neutral)
    plain = sum(not c.abilities for c in neutral) / len(neutral)
    assert 0.55 < plain < 0.85


def test_neutral_ability_units_pay_a_tax():
    from src.cards.generate import CardGenerator
    import random
    g = CardGenerator(random.Random(0), ("Baker", "Miner"), classes=True)
    taxed = []
    for _ in range(200):
        a = g.card()
        if not a.card.aspects and a.card.abilities:
            taxed.append(a)
    assert taxed
    for a in taxed:
        notes = [n for n in a.trace["children"] if n.get("section") == "card"]
        assert any(d.get("decision") == "Neutral tax" for n in notes for d in n["children"])


def test_classes_lean_towards_their_styles(class_set):
    """Each class's own signature effects are more common in it than in the opposite class."""
    def share(aspect, effect):
        cards = [c for c in class_set.cards if c.aspects == (aspect,) and c.abilities]
        return sum(f'"effect": "{effect}"' in str(c.abilities).replace("'", '"') for c in cards) / len(cards)
    assert share("aspect_5", "summon") > share("aspect_2", "summon")  # Glow (swarm) vs Bog
    assert share("aspect_2", "draw") > share("aspect_3", "draw")  # Bog (spells) vs Moss
