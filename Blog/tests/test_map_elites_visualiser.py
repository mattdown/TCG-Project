"""The MAP-Elites visualiser: the algorithm, a small real run, and the page it bakes."""
import random

import pytest

from map_elites_visualiser import TEMPLATE, SUMMARY, geometric_k, map_elites, occupied, run, sliding
from card_lab import bake, describe


def toy(budget: int, seed: int):
    """map_elites on numbers instead of decks: quick, and every rule is visible."""
    rng = random.Random(seed)
    new = lambda: rng.random()
    mutate = lambda x: (min(1.0, max(0.0, x + rng.uniform(-0.2, 0.2))), {"k": 1, "out": [], "in": []})
    evaluate = lambda x: (round(-abs(x - 0.7) + rng.uniform(-0.05, 0.05), 4), (x, x))
    cell = lambda b: (min(4, int(b[0] * 5)), 0)
    return map_elites(budget, 10, new, mutate, evaluate, cell, rng)


def test_map_elites_keeps_only_improvements():
    """Each cell's elite is the fittest deck that ever landed there (the first of any tie), and a deck is kept
    only if its cell was empty or it beat the elite."""
    archive, history = toy(300, seed=1)
    best = {}
    for i, h in enumerate(history):
        old = best.get(h["cell"])
        assert h["outcome"] == ("new" if old is None else "better" if h["fitness"] > history[old]["fitness"] else "worse")
        assert (h["parent"] is None) == (i < 10)
        if h["parent"] is not None:
            assert h["parent"] in best.values()  # parents are elites at the time
        if h["outcome"] != "worse":
            best[h["cell"]] = i
    assert archive == best
    assert all(history[i]["fitness"] == max(h["fitness"] for h in history if h["cell"] == c) for c, i in archive.items())


def test_map_elites_is_deterministic():
    assert toy(200, seed=4) == toy(200, seed=4)
    assert toy(200, seed=4) != toy(200, seed=5)


def test_mutation_size_is_geometric():
    """k is 1 about half the time, 2 about a quarter."""
    rng = random.Random(0)
    ks = [geometric_k(rng) for _ in range(4000)]
    assert abs(ks.count(1) / 4000 - 0.5) < 0.03 and abs(ks.count(2) / 4000 - 0.25) < 0.03


def test_sliding_boundaries_grow_and_spread():
    """The grid grows from 2x2 to 20x20 every 100 points, cut at percentiles, so bunched points fill more cells
    than an even grid over the same range."""
    rng = random.Random(0)
    points = [(rng.gauss(3, 0.3), rng.gauss(0.4, 0.05)) for _ in range(1000)]
    slides = sliding(points)
    assert [s["size"] for s in (slides[0], slides[-1])] == [2, 20] and slides[-1]["seen"] == 1000
    assert all(len(s["cuts"][0]) == s["size"] - 1 and s["cuts"][0] == sorted(s["cuts"][0]) for s in slides)
    even = [[2 + 3 * k / 20 for k in range(1, 20)], [0.1 + 0.6 * k / 20 for k in range(1, 20)]]
    assert occupied(points, slides[-1]["cuts"]) > 2 * occupied(points, even)


@pytest.fixture(scope="module")
def small_run():
    return run(budget=24, initial=8, opponents=1, optimise_budget=40)


def test_small_real_run_is_deterministic(small_run):
    """The run plays real games, so the same seed must give the same page."""
    again = run(budget=24, initial=8, opponents=1, optimise_budget=40)
    assert again["evals"] == small_run["evals"] and again["plain"] == small_run["plain"]
    evals = small_run["evals"]
    assert len(evals) == 24 and all(-30 <= e["f"] <= 30 and 0 <= e["b"][1] <= 1 for e in evals)
    assert all(e["p"] is None for e in evals[:8]) and all(e["p"] is not None for e in evals[8:])
    assert small_run["stats"]["elites"] == len({tuple(e["c"]) for e in evals})


def test_page_bakes(small_run):
    keys = {c["art"] for c in small_run["cards"].values()}
    html = describe(bake(TEMPLATE, small_run, keys), "MAP-Elites visualiser", SUMMARY)
    assert "<!--LAB_DATA-->" not in html and "<!--CARD_ART-->" not in html and "<!--PAINTED_CARD-->" not in html
    assert "<title>MAP-Elites visualiser</title>" in html and "<noscript>" in html
    assert "window.LAB_DATA = " in html
