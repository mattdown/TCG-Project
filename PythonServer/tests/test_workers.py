import copy
import random

import pytest
import torch

from src.agents.heuristic_agent import HeuristicAgent
from src.cards.vanilla import generate_vanilla_set
from src.model.registry import create_model
from src.training.ppo import PPOConfig, collect_games, train
from src.training.workers import SelfPlayPool


def _net(seed: int = 0):
    torch.manual_seed(seed)
    return create_model("gnn", hidden=32, num_layers=1)


def test_a_worker_plays_the_same_games_as_this_process():
    net, cards = _net(), [generate_vanilla_set(seed=1)]
    league = [HeuristicAgent(), copy.deepcopy(net).eval()]
    with SelfPlayPool(1, cards) as pool:
        steps, turns, league_result, _ = pool.collect(net, 4, random.Random(5), league, league_share=0.5)
    seed = random.Random(5).randrange(2**31)  # the seed the pool drew for its one worker
    torch.manual_seed(seed)
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        expected, expected_turns, expected_league, _ = collect_games(net, cards, 4, random.Random(seed), "cpu",
                                                                     league=league, league_share=0.5)
    finally:
        torch.set_num_threads(threads)
    assert [s.action_index for s in steps] == [s.action_index for s in expected]
    assert (turns, league_result) == (expected_turns, expected_league)


def test_workers_follow_the_learner_and_the_league_as_they_change():
    cards = [generate_vanilla_set(seed=1)]
    net, old, new = _net(0), _net(1).eval(), _net(2).eval()
    with SelfPlayPool(2, cards) as pool:
        _, _, (_, games), _ = pool.collect(net, 6, random.Random(0), [old], league_share=1.0)
        assert games == 6 and all(len(sent) == 1 for sent in pool.sent)
        net.load_state_dict(_net(3).state_dict())
        steps, _, (_, games), _ = pool.collect(net, 5, random.Random(1), [new], league_share=1.0)
        assert games == 5 and steps
        assert all(sent == {pool.keys[new]} for sent in pool.sent)  # the old snapshot was dropped


def test_a_failing_worker_raises_here():
    with SelfPlayPool(1, [generate_vanilla_set(seed=1)]) as pool:
        with pytest.raises(RuntimeError, match="worker failed"):
            pool.collect(_net(), 2, random.Random(0), [object()], league_share=1.0)  # not an agent


def test_train_with_workers(tmp_path):
    cfg = PPOConfig(iterations=3, games_per_iteration=4, eval_every=3, eval_games=2, hidden=32, num_layers=1,
                    league_share=0.5, snapshot_every=1, pool_size=1, workers=2)
    lines = []
    train(cfg, [generate_vanilla_set(seed=1)], tmp_path / "net.pt", log=lines.append)
    assert (tmp_path / "net.pt").exists() and sum(line.startswith("it ") for line in lines) == 3
