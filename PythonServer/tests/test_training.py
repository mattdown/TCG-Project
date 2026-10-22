import copy
import random

import pytest
import torch

from src.cards.schema import CardSet
from src.cards.vanilla import generate_vanilla_set
from src.model.registry import create_model
from src.training.ppo import PPOConfig, Step, _gae, collect_games, ppo_update, train
from tests.test_fuzz import ability_pool


def test_gae_with_terminal_reward():
    steps = [Step(None, 0, 0.0, 0.5), Step(None, 0, 0.0, 0.5)]
    _gae(steps, outcome=1.0, gamma=1.0, lam=1.0)
    assert [s.ret for s in steps] == [1.0, 1.0]
    assert [s.advantage for s in steps] == [0.5, 0.5]


@pytest.mark.parametrize("arch", ["gnn", "transformer"])
def test_one_training_iteration_runs(arch):
    torch.manual_seed(0)
    cfg = PPOConfig(games_per_iteration=2, epochs=1, minibatch_size=64, hidden=32, num_layers=2)
    net = create_model(arch, hidden=32, num_layers=2)
    steps, avg_turns, _ = collect_games(net, generate_vanilla_set(), 2, random.Random(0), "cpu")
    assert steps and avg_turns > 0
    metrics = ppo_update(net, torch.optim.Adam(net.parameters(), lr=1e-3), steps, cfg)
    assert all(v == v for v in metrics.values())  # no NaNs


def test_update_handles_a_step_count_one_above_the_minibatch_size():
    # Regression: a leftover minibatch of one step made the advantage std NaN.
    torch.manual_seed(0)
    cfg = PPOConfig(epochs=1, minibatch_size=8, hidden=32, num_layers=2)
    net = create_model("gnn", hidden=32, num_layers=2)
    steps, _, _ = collect_games(net, generate_vanilla_set(), 1, random.Random(0), "cpu")
    metrics = ppo_update(net, torch.optim.Adam(net.parameters(), lr=1e-3), steps[:17], cfg)
    assert all(v == v for v in metrics.values())
    assert all(torch.isfinite(p).all() for p in net.parameters())


@pytest.mark.parametrize("arch", ["gnn", "transformer"])
def test_training_runs_on_cards_with_abilities(arch):
    """Smoke test: self-play and a PPO update work when abilities create new kinds of decisions."""
    torch.manual_seed(0)
    pool = ability_pool(random.Random(1))
    cfg = PPOConfig(games_per_iteration=2, epochs=1, minibatch_size=64, hidden=32, num_layers=2)
    net = create_model(arch, hidden=32, num_layers=2)
    steps, _, _ = collect_games(net, CardSet("pool", pool), 2, random.Random(0), "cpu")
    metrics = ppo_update(net, torch.optim.Adam(net.parameters(), lr=1e-3), steps, cfg)
    assert all(v == v for v in metrics.values())


def test_league_games_train_only_the_learner():
    from src.agents.heuristic_agent import HeuristicAgent
    torch.manual_seed(0)
    net = create_model("gnn", hidden=32, num_layers=1)
    frozen = copy.deepcopy(net).eval()
    card_sets = [generate_vanilla_set(seed=1), generate_vanilla_set(seed=2)]
    steps, _, (wins, games) = collect_games(net, card_sets, 6, random.Random(3), "cpu",
                                            league=[HeuristicAgent(), frozen], league_share=1.0)
    assert games == 6 and 0 <= wins <= 6
    # Only the learner's decisions are training steps: about half of a self-play game's.
    self_play, _, _ = collect_games(net, card_sets, 6, random.Random(3), "cpu")
    assert 0 < len(steps) < 0.8 * len(self_play)


def test_train_runs_with_a_league(tmp_path):
    cfg = PPOConfig(iterations=2, games_per_iteration=4, eval_every=2, eval_games=2, hidden=32, num_layers=1,
                    league_share=0.5, snapshot_every=1)
    train(cfg, [generate_vanilla_set(seed=1)], tmp_path / "net.pt", log=lambda _: None)
    assert (tmp_path / "net.pt").exists() and (tmp_path / "net_best.pt").exists()
