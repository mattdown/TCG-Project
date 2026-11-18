import random
from collections import Counter

import numpy as np

from src.cards.vanilla import generate_vanilla_set
from src.deck_search.map_elites import (STYLE_MEASURES, Config, Evaluation, Evaluator, build_archive, cell_of,
                                        deck_of, field_decks, map_elites, mutate, percentile_cuts, ring_point,
                                        sector)
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
    archive = build_archive(history, lambda e: cell_of([e.measures["x"]], [[0.5]]))
    assert archive == {(0,): 1, (1,): 2}


def test_a_small_search_runs_and_improves_on_random_decks():
    cards = generate_vanilla_set(seed=1)
    cfg = Config(budget=120, initial=40, opponents=2, axes=("cost", "hero_share"), grid=3, slide_every=40, batch=20)
    field = field_decks(cards, cfg.opponents, cfg.seed)
    with Evaluator(cards, field) as evaluate:
        result = map_elites(cards, evaluate, cfg, log=None)
    assert len(result.history) == 120
    stats = result.stats()
    assert 1 <= stats["elites"] <= 9
    first = max(e.fitness for e in result.history[:cfg.initial])
    assert stats["best"] >= first
    assert set(result.history[0].measures) == {"cost", "hero_share", "turns", "action_share", *STYLE_MEASURES}
    assert all(e.parent is not None for e in result.history[cfg.initial:])
    assert result.to_json()["elites"][0]["deck"]


def test_workers_give_the_same_scores():
    cards = generate_vanilla_set(seed=1)
    field = field_decks(cards, 2, 0)
    decks = [deck_of(random_deck(cards, random.Random(s))) for s in range(4)]
    with Evaluator(cards, field) as here, Evaluator(cards, field, workers=2) as there:
        assert here(decks) == there(decks)


def test_a_class_deck_keeps_to_its_class():
    from src.cards.generate import generate_card_set
    from src.game.decks import deck_class
    cards = generate_card_set(300, seed=1, classes=True, prefix="T")
    cfg = Config(budget=60, initial=20, opponents=1, rings=2, slide_every=20, batch=20, per_class=True)
    with Evaluator(cards, field_decks(cards, 1, 0)) as evaluate:
        result = map_elites(cards, evaluate, cfg, log=None)
    by_id = {c.id: c for c in cards.cards}
    for e in result.history:
        deck = [by_id[i] for i in e.deck]
        aspect = deck_class(deck)
        assert all(c.aspects in ((), (aspect,)) for c in deck)
    assert len({cell[0] for cell in result.archive}) > 1  # each class keeps its own archive


def test_the_ring_points_each_style_its_own_way():
    reference = {m: (0.0, 1.0) for m in STYLE_MEASURES}
    for i, m in enumerate(STYLE_MEASURES):
        angle, radius = ring_point({**{k: 0.0 for k in STYLE_MEASURES}, m: 2.0}, reference)
        assert round(angle) % 360 == 60 * i and round(radius, 6) == 2
        assert sector(angle, 12) == 2 * i
    bridge = ring_point({**{k: 0.0 for k in STYLE_MEASURES}, "aggro": 1.0, "swarm": 1.0}, reference)
    assert sector(bridge[0], 12) == 1  # between aggro and swarm


def test_a_ring_search_fills_sectors_and_rings():
    from src.cards.generate import generate_card_set
    cards = generate_card_set(300, seed=1, classes=True, prefix="T")
    cfg = Config(budget=100, initial=40, opponents=1, rings=3, slide_every=40, batch=20)
    with Evaluator(cards, field_decks(cards, 1, 0)) as evaluate:
        result = map_elites(cards, evaluate, cfg, log=None)
    out = result.to_json()
    assert len({tuple(e["cell"]) for e in out["elites"]}) == len(out["elites"]) > 3
    assert all(0 <= e["cell"][0] < 12 and 0 <= e["cell"][1] < 3 for e in out["elites"])
    assert set(out["reference"]) == set(STYLE_MEASURES) and "angle" in out["elites"][0]
