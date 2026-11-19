import random

import numpy as np
import pytest

from src.cards.vanilla import generate_vanilla_set
from src.deck_search.map_elites import deck_of
from src.deck_search.metagame import (Matchups, balance, class_table, effective_number, exploitability, nash, qre,
                                      top_elites)
from src.game.decks import random_deck

RPS = np.array([[0.5, 1.0, 0.0], [0.0, 0.5, 1.0], [1.0, 0.0, 0.5]])  # rock, paper... as win rates


def test_nash_finds_the_mix_nobody_beats():
    assert np.allclose(nash(RPS), 1 / 3, atol=0.01)
    # a fourth option that loses to everything gets no weight
    table = np.full((4, 4), 0.5)
    table[:3, :3] = RPS
    table[3, :3], table[:3, 3] = 0.3, 0.7
    mix = nash(table)
    assert mix[3] < 0.01 and exploitability(table, mix) < 0.01


def test_a_dominant_deck_takes_the_whole_mix():
    table = np.array([[0.5, 0.6, 0.7], [0.4, 0.5, 0.55], [0.3, 0.45, 0.5]])
    assert nash(table)[0] > 0.99


def test_the_smoothed_equilibrium_tends_to_nash_and_to_even():
    table = np.array([[0.5, 0.6, 0.7], [0.4, 0.5, 0.55], [0.3, 0.45, 0.5]])
    assert qre(table, 0.002)[0] > 0.95
    assert np.allclose(qre(table, 100.0), 1 / 3, atol=0.01)
    soft = qre(table, 0.05)
    assert soft[0] > soft[1] > soft[2] > 0.01  # better decks get more, but nobody is cut out
    assert np.allclose(qre(RPS, 0.05), 1 / 3, atol=1e-3)


def test_the_smoothed_mix_moves_smoothly_with_the_table():
    table = np.array([[0.5, 0.52], [0.48, 0.5]])
    nudged = np.array([[0.5, 0.48], [0.52, 0.5]])
    assert abs(nash(table)[0] - nash(nudged)[0]) > 0.9  # 4 points of noise flips the Nash mix
    assert abs(qre(table, 0.05)[0] - qre(nudged, 0.05)[0]) < 0.5


@pytest.fixture(scope="module")
def small():
    cards = generate_vanilla_set(seed=1)
    decks = [deck_of(random_deck(cards, random.Random(s))) for s in range(4)]
    with Matchups(cards, games=4) as m:
        table = m.table(decks)
    return cards, decks, table


def test_tables_are_consistent_and_repeatable(small):
    cards, decks, table = small
    assert np.allclose(table + table.T, 1.0) and np.allclose(np.diag(table), 0.5)
    with Matchups(cards, games=4) as m:
        assert np.array_equal(m.table(decks[::-1]), table[::-1, ::-1])  # order doesn't change a pair's deals


def test_extending_a_table_plays_only_the_new_pairs(small):
    cards, decks, table = small
    with Matchups(cards, games=4) as m:
        played = []
        real = m._play
        m._play = lambda pairs: played.extend(pairs) or real(pairs)
        bigger = m.extend(decks[:3], table[:3, :3], decks[3:])
    assert np.array_equal(bigger, table)
    assert len(played) == 3 and all(decks[3] in pair for pair in played)


def test_workers_give_the_same_table(small):
    cards, decks, table = small
    with Matchups(cards, games=4, workers=2) as m:
        assert np.array_equal(m.table(decks), table)


def test_balance_reads_the_targets_from_a_mix(small):
    cards, decks, table = small
    b = balance(table, np.array([1.0, 0, 0, 0]), decks, cards)
    assert b.decks == pytest.approx(1) and b.must_play == pytest.approx(1)
    assert b.cards_used == pytest.approx(len(set(decks[0])) / len(cards.cards))
    assert sum(b.groups.values()) == pytest.approx(1) and set(b.groups) <= {"unit, vanilla", "unit, keywords"}
    even = balance(table, np.full(4, 0.25), decks, cards)
    assert even.decks == pytest.approx(4) and even.best_vs_field == pytest.approx(table.mean(1).max())
    assert effective_number([0.5, 0.5]) == pytest.approx(2)


def test_class_tables_and_top_elites():
    table = np.array([[0.5, 0.8, 0.6], [0.2, 0.5, 0.4], [0.4, 0.6, 0.5]])
    names, ct = class_table(table, ["a", "b", "a"])
    assert names == ["a", "b"] and ct[0, 1] == pytest.approx(0.7) and ct[0, 0] == pytest.approx(0.5)
    archive = {"elites": [{"class": c, "fitness": f, "deck": [str(f)]}
                          for c, f in [("a", 1), ("a", 3), ("b", 2), ("a", 2)]]}
    assert [e["fitness"] for e in top_elites(archive, 2)] == [3, 2, 2]
