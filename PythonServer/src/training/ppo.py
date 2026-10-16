"""PPO self-play.

Each iteration plays a batch of games in lockstep with the current network in both seats,
on fresh random decks. Every decision becomes one training step for the player who made
it. The reward is +1 / -1 for a win / loss (0 for a draw) at the player's last decision,
and advantages come from GAE over that player's own decisions.
"""
import random
import time
from dataclasses import asdict, dataclass

import torch
from torch import nn

from src.agents.heuristic_agent import HeuristicAgent
from src.agents.match import play_match
from src.agents.neural_agent import NeuralAgent
from src.agents.random_agent import RandomAgent
from src.cards.schema import CardSet
from src.game.decks import random_deck
from src.game.engine import Game
from src.graph.encode import EncodedObs, observe
from src.model.common import segment_entropy, segment_log_softmax, segment_ptr
from src.model.registry import create_model, save_model


@dataclass
class PPOConfig:
    iterations: int = 500
    games_per_iteration: int = 64
    epochs: int = 4
    minibatch_size: int = 512
    lr: float = 3e-4
    gamma: float = 1.0
    gae_lambda: float = 0.95
    clip: float = 0.2
    value_coef: float = 0.5
    entropy_coef: float = 0.01
    max_grad_norm: float = 0.5
    target_kl: float = 0.03
    eval_every: int = 10
    eval_games: int = 100
    arch: str = "gnn"  # "gnn" or "transformer"
    hidden: int = 128
    num_layers: int = 4
    seed: int = 0
    device: str = "cpu"


@dataclass
class Step:
    obs: EncodedObs
    action_index: int
    log_prob: float
    value: float
    advantage: float = 0.0
    ret: float = 0.0


def collect_games(net: nn.Module, card_set: CardSet, num_games: int, rng: random.Random, device: str,
                  gamma: float = 1.0, gae_lambda: float = 0.95):
    """Plays num_games self-play games. Returns the training steps and the average game length in turns."""
    games = [Game(random_deck(card_set, rng), random_deck(card_set, rng), seed=rng.randrange(2**31))
             for _ in range(num_games)]
    trajectories = [([], []) for _ in games]  # per game, per player
    active = list(range(num_games))
    net.eval()
    while active:
        observations = [observe(games[g], games[g].state.decision_player) for g in active]
        batch = net.collate([o.encoded for o in observations]).to(device)
        with torch.no_grad():
            logits, index, values = net(batch)
            log_probs = segment_log_softmax(logits, index).cpu()
        ptr = segment_ptr(index, len(active)).cpu()
        for i, g in enumerate(active):
            lp = log_probs[ptr[i]:ptr[i + 1]]
            choice = int(torch.multinomial(lp.exp(), 1))
            game = games[g]
            trajectories[g][game.state.decision_player].append(
                Step(observations[i].encoded, choice, float(lp[choice]), float(values[i])))
            game.step(observations[i].actions[choice], validate=False)
        active = [g for g in active if not games[g].is_over]

    steps = []
    for game, per_player in zip(games, trajectories):
        for player, trajectory in enumerate(per_player):
            winner = game.state.winner
            outcome = 0.0 if winner is None else (1.0 if winner == player else -1.0)
            steps.extend(_gae(trajectory, outcome, gamma, gae_lambda))
    return steps, sum(g.state.turn for g in games) / num_games


def _gae(trajectory: list[Step], outcome: float, gamma: float, lam: float) -> list[Step]:
    advantage, next_value = 0.0, 0.0
    for t in reversed(range(len(trajectory))):
        step = trajectory[t]
        reward = outcome if t == len(trajectory) - 1 else 0.0
        delta = reward + gamma * next_value - step.value
        advantage = delta + gamma * lam * advantage
        step.advantage, step.ret = advantage, advantage + step.value
        next_value = step.value
    return trajectory


def ppo_update(net: nn.Module, optimizer: torch.optim.Optimizer, steps: list[Step], cfg: PPOConfig) -> dict:
    net.train()
    # Normalise advantages over the whole iteration: a tiny minibatch has no meaningful std.
    all_advantages = torch.tensor([s.advantage for s in steps])
    all_advantages = (all_advantages - all_advantages.mean()) / (all_advantages.std() + 1e-8)
    num_minibatches = max(1, round(len(steps) / cfg.minibatch_size))
    totals = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "approx_kl": 0.0, "clip_frac": 0.0}
    updates = epochs_run = 0
    for _ in range(cfg.epochs):
        epoch_kl = []
        # Equal-sized minibatches, so there's never a leftover of one or two steps.
        for mb_idx in torch.tensor_split(torch.randperm(len(steps)), num_minibatches):
            mb = [steps[i] for i in mb_idx.tolist()]
            batch = net.collate([s.obs for s in mb]).to(cfg.device)
            old_log_prob = torch.tensor([s.log_prob for s in mb], device=cfg.device)
            advantage = all_advantages[mb_idx].to(cfg.device)
            returns = torch.tensor([s.ret for s in mb], device=cfg.device)

            logits, index, values = net(batch)
            log_probs = segment_log_softmax(logits, index)
            chosen = segment_ptr(index, len(mb))[:-1] + torch.tensor([s.action_index for s in mb], device=cfg.device)
            new_log_prob = log_probs[chosen]
            ratio = (new_log_prob - old_log_prob).exp()
            clipped = ratio.clamp(1 - cfg.clip, 1 + cfg.clip)
            policy_loss = -torch.min(ratio * advantage, clipped * advantage).mean()
            value_loss = (values - returns).pow(2).mean()
            entropy = segment_entropy(log_probs, index).mean()
            loss = policy_loss + cfg.value_coef * value_loss - cfg.entropy_coef * entropy
            if not torch.isfinite(loss):
                raise RuntimeError("non-finite PPO loss: stopping before the weights are corrupted")

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), cfg.max_grad_norm)
            optimizer.step()

            with torch.no_grad():
                kl = (old_log_prob - new_log_prob).mean().item()
                epoch_kl.append(kl)
                totals["policy_loss"] += policy_loss.item()
                totals["value_loss"] += value_loss.item()
                totals["entropy"] += entropy.item()
                totals["approx_kl"] += kl
                totals["clip_frac"] += ((ratio - 1).abs() > cfg.clip).float().mean().item()
            updates += 1
        epochs_run += 1
        # Stop early if the policy has already moved far from the one that played the games.
        if sum(epoch_kl) / len(epoch_kl) > cfg.target_kl:
            break
    return {**{k: v / max(updates, 1) for k, v in totals.items()}, "epochs": epochs_run}


def evaluate(net: nn.Module, card_set: CardSet, num_games: int, seed: int, device: str) -> dict:
    agent = NeuralAgent(net, device=device, greedy=True)
    return {
        "vs_random": play_match(agent, RandomAgent(seed), card_set, num_games, seed)["win_rate"],
        "vs_heuristic": play_match(agent, HeuristicAgent(), card_set, num_games, seed)["win_rate"],
    }


def train(cfg: PPOConfig, card_set: CardSet, out_path, log=print) -> nn.Module:
    torch.manual_seed(cfg.seed)
    rng = random.Random(cfg.seed)
    net = create_model(cfg.arch, hidden=cfg.hidden, num_layers=cfg.num_layers).to(cfg.device)
    optimizer = torch.optim.Adam(net.parameters(), lr=cfg.lr)
    best = -1.0
    for it in range(1, cfg.iterations + 1):
        t0 = time.time()
        steps, avg_turns = collect_games(net, card_set, cfg.games_per_iteration, rng, cfg.device,
                                        cfg.gamma, cfg.gae_lambda)
        t1 = time.time()
        metrics = ppo_update(net, optimizer, steps, cfg)
        t2 = time.time()
        log(f"it {it:4d} | {len(steps):6d} steps | {avg_turns:5.1f} turns/game | "
            f"pi {metrics['policy_loss']:+.3f} v {metrics['value_loss']:.3f} ent {metrics['entropy']:.3f} "
            f"kl {metrics['approx_kl']:+.4f} clip {metrics['clip_frac']:.2f} ep {metrics['epochs']} | "
            f"play {t1 - t0:4.1f}s learn {t2 - t1:4.1f}s")
        if it % cfg.eval_every == 0 or it == cfg.iterations:
            result = evaluate(net, card_set, cfg.eval_games, seed=it, device=cfg.device)
            log(f"     eval: {result['vs_random']:.1%} vs random, {result['vs_heuristic']:.1%} vs heuristic")
            save_model(net, out_path, {"config": asdict(cfg), "iteration": it, "eval": result})
            if result["vs_heuristic"] > best:
                best = result["vs_heuristic"]
                save_model(net, str(out_path).replace(".pt", "_best.pt"),
                           {"config": asdict(cfg), "iteration": it, "eval": result})
    return net
