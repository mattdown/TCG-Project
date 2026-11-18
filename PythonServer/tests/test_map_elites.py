import random
from collections import Counter

import numpy as np

from src.cards.vanilla import generate_vanilla_set
from src.deck_search.map_elites import (Config, Evaluator, build_archive, cell_of, deck_of, field_decks,
                                        map_elites, mutate, percentile_cuts, Evaluation)
from src.game.decks import DECK_SIZE, MAX_COPIES, random_deck


def test_mutation_swaps_cards_and_keeps_the_deck_legal():
    cards = generate_vanilla_set(seed=1)
    ids = [c.id for c in cards.cards]
    rng = random.Random(0)
    deck = deck_of(random_deck(cards, rng))
    for _ in range(200):
        child, k = mutate(deck, ids, rng)
        assert len(child) == DECK_SIZE and child == tuple(sorted(child))
        assert max(Counter(child).values()) <= MAX_COPIES
        assert 1 <= k and sum((Counter(deck) - Counter(child)).values()) <= k
        deck = child


def test_sliding_cuts_spread_points_over_the_grid():
    points = np.random.default_rng(0).exponential(size=(1000, 2))  # bunched up, as decks are
    cuts = percentile_cuts(points, 4)
    cells = Counter(cell_of(p, cuts) for p in points)
    assert len(cells) >= 14  # an even grid over the range would leave most of 16 empty
    assert all(len(c) == 3 for c in cuts)


def test_the_archive_keeps_the_best_deck_per_cell():
    history = [Evaluation(("a",), 1.0, {"x": 0.1}), Evaluation(("b",), 3.0, {"x": 0.2}),
               Evaluation(("c",), 2.0, {"x": 0.9})]
    archive = build_archive(history, ("x",), [[0.5]])
    assert archive == {(0,): 1, (1,): 2}


def test_a_small_search_runs_and_improves_on_random_decks():
    cards = generate_vanilla_set(seed=1)
    cfg = Config(budget=120, initial=40, opponents=2, grid=3, slide_every=40, batch=20)
    field = field_decks(cards, cfg.opponents, cfg.seed)
    with Evaluator(cards, field) as evaluate:
        result = map_elites(cards, evaluate, cfg, log=None)
    assert len(result.history) == 120
    stats = result.stats()
    assert 1 <= stats["elites"] <= 9
    first = max(e.fitness for e in result.history[:cfg.initial])
    assert stats["best"] >= first
    assert set(result.history[0].measures) == {"cost", "hero_share", "turns", "action_share"}
    assert all(e.parent is not None for e in result.history[cfg.initial:])
    assert result.to_json()["elites"][0]["deck"]


def test_workers_give_the_same_scores():
    cards = generate_vanilla_set(seed=1)
    field = field_decks(cards, 2, 0)
    decks = [deck_of(random_deck(cards, random.Random(s))) for s in range(4)]
    with Evaluator(cards, field) as here, Evaluator(cards, field, workers=2) as there:
        assert here(decks) == there(decks)
