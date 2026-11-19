import json
import random

import numpy as np
import pytest

from src.cards.generate import generate_card_set
from src.deck_search.map_elites import deck_of
from src.deck_search.price_loop import LoopConfig, group_counts, mix_field, price_step, prune, run
from src.game.decks import random_deck


def test_groups_that_go_with_winning_get_dearer_and_losing_ones_cheaper():
    cfg = LoopConfig(step=0.5, max_change=0.2, min_cards=10, dead_band=0.15)
    value = np.array([0.4, 0.45, 0.5, 0.55, 0.6, 0.65])
    counts = {"action, draw": np.array([0, 1, 2, 3, 4, 5.0]),  # more of it, more wins
              "action, summon": np.array([5, 4, 3, 2, 1, 0.0]),
              "unit, buff": np.array([1, 0, 0, 1, 1, 0.0]),  # unrelated
              "unit, vanilla": np.array([0, 1, 2, 3, 4, 5.0]), "tiny": np.array([0, 1, 2, 3, 4, 5.0])}
    sizes = {"action, draw": 50, "action, summon": 50, "unit, buff": 50, "unit, vanilla": 200, "tiny": 5}
    new, corr = price_step(counts, value, {"action, draw": 1.7, "action, summon": 0.77}, sizes, cfg)
    assert new["action, draw"] == pytest.approx(1.7 * np.exp(0.2), rel=1e-3)  # capped
    assert new["action, summon"] == pytest.approx(0.77 * np.exp(-0.2), rel=1e-3)
    assert set(new) == {"action, draw", "action, summon"}  # noise, priceless and tiny groups stay
    assert corr["unit, buff"] == pytest.approx(0, abs=0.3)


def test_the_field_follows_the_mix_and_pruning_keeps_every_class():
    decks = [("a",), ("b",), ("c",), ("d",)]
    field_ = mix_field(decks, np.array([0.7, 0.3, 0, 0]), 200, random.Random(0))
    assert set(field_) == {("a",), ("b",)} and field_.count(("a",)) > field_.count(("b",))
    keep = prune(decks, np.array([0.6, 0.3, 0.1, 0.0]), ["x", "x", "x", "y"], cap=2, keep=1)
    assert keep == [0, 3]  # y's only deck stays though the mix doesn't use it


def test_group_counts_count_each_decks_cards():
    cards = generate_card_set(200, seed=4, classes=True, prefix="T")
    decks = [deck_of(random_deck(cards, random.Random(s))) for s in range(3)]
    counts = group_counts(cards, decks)
    assert all(sum(n[k] for n in counts.values()) == len(decks[k]) for k in range(3))


def test_a_small_loop_runs_reprices_and_writes_its_rounds(tmp_path):
    cards = generate_card_set(300, seed=1, classes=True, prefix="T")
    rng = random.Random(0)
    decks = list({deck_of(random_deck(cards, rng)) for _ in range(6)})
    cfg = LoopConfig(rounds=2, games=2, search_budget=30, opponents=1, workers=0, population=8, min_cards=3,
                     step=2.0, dead_band=0.0)
    out = run(cards, decks, cfg, tmp_path, log=lambda s: None)
    rounds = [json.loads((tmp_path / f"round_{r:02d}.json").read_text()) for r in (1, 2)]
    assert rounds[0]["changed"] and rounds[1]["scales"] == rounds[0]["scales"] | rounds[0]["changed"]
    assert len(rounds[0]["decks"]) > len(decks)  # best responses were added
    assert out.notes["group_scale"] == rounds[1]["scales"] | rounds[1]["changed"]
    assert [c.id for c in out.cards] == [c.id for c in cards.cards] and out.cards != cards.cards
    assert (tmp_path / "final.json").exists() and (tmp_path / f"{cards.name}.json").exists()
