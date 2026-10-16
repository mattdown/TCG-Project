import random

import pytest
import torch

from src.cards.vanilla import generate_vanilla_set
from src.model.registry import create_model
from src.training.ppo import PPOConfig, Step, _gae, collect_games, ppo_update


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
    steps, avg_turns = collect_games(net, generate_vanilla_set(), 2, random.Random(0), "cpu")
    assert steps and avg_turns > 0
    metrics = ppo_update(net, torch.optim.Adam(net.parameters(), lr=1e-3), steps, cfg)
    assert all(v == v for v in metrics.values())  # no NaNs


def test_update_handles_a_step_count_one_above_the_minibatch_size():
    # Regression: a leftover minibatch of one step made the advantage std NaN.
    torch.manual_seed(0)
    cfg = PPOConfig(epochs=1, minibatch_size=8, hidden=32, num_layers=2)
    net = create_model("gnn", hidden=32, num_layers=2)
    steps, _ = collect_games(net, generate_vanilla_set(), 1, random.Random(0), "cpu")
    metrics = ppo_update(net, torch.optim.Adam(net.parameters(), lr=1e-3), steps[:17], cfg)
    assert all(v == v for v in metrics.values())
    assert all(torch.isfinite(p).all() for p in net.parameters())
