"""PPO self-play with a league.

Each iteration plays a batch of games in lockstep, on fresh random decks from one or more card
sets. Most games are self-play: the current network in both seats. A `league_share` of them
put it against an opponent from the league instead: frozen snapshots of earlier versions
(added every `snapshot_every` iterations, the newest `pool_size` kept) and the heuristic
agent. Playing only against its current self, an agent can learn to beat itself and forget
how to beat anything else; the league keeps old strategies in the mix.

Every decision the learner makes becomes one training step. The reward is +1 / -1 for a win
/ loss (0 for a draw) at the player's last decision, and advantages come from GAE over that
player's own decisions.

Puzzle episodes (`puzzle_games` a iteration, from `puzzles`) start at a position with a sure lethal
(src/agents/puzzles.py) and cover only that player's turn: +1 if it wins before the turn ends,
otherwise the value of where the turn left it (minus the opponent's value at their first decision),
so the value head keeps meaning "chance of winning". They give a direct signal for taking lethal,
which a whole game only gives through the final result.
"""
import contextlib
import copy
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
from torch import nn

from src.agents.heuristic_agent import HeuristicAgent
from src.agents.match import play_match
from src.agents.neural_agent import NeuralAgent
from src.agents.puzzles import Puzzle
from src.agents.random_agent import RandomAgent
from src.cards.schema import CardSet
from src.game.decks import random_deck
from src.game.engine import Game
from src.graph.encode import EncodedObs, observe
from src.model.common import segment_entropy, segment_log_softmax, segment_ptr
from src.model.registry import create_model, load_model, save_model
from src.training.workers import SelfPlayPool


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
    eval_seed: int = 1000  # the same deck pairs at every eval, so checkpoints differ by play, not by the deal
    arch: str = "gnn"  # "gnn" or "transformer"
    hidden: int = 128
    num_layers: int = 4
    seed: int = 0
    device: str = "cpu"  # faster than MPS here: the graphs are small, so GPU overhead outweighs the compute (2026-11-15)
    league_share: float = 0.3  # share of games against a league opponent (0: pure self-play)
    snapshot_every: int = 10  # add a frozen copy of the network to the league this often
    pool_size: int = 8  # snapshots kept (the heuristic agent is always in the league)
    init: str = ""  # checkpoint to start from (its arch and size win over the fields above)
    mirror_share: float = 0.0  # share of games with the same deck on both sides: the result is down to play, not deck luck
    outcomes: bool = True  # False hides the action-outcome features in self-play (an ablation)
    puzzles: str = ""  # puzzle file (scripts/puzzles.py) on the training cards, for puzzle episodes
    puzzle_games: int = 0  # puzzle episodes a iteration, on top of the games
    workers: int = 0  # self-play worker processes (0: play in this process); see src/training/workers.py
    wandb: str = ""  # Weights & Biases project to log to ("" = off; `wandb login` once, or WANDB_MODE=offline)


@dataclass
class Step:
    obs: EncodedObs
    action_index: int
    log_prob: float
    value: float
    advantage: float = 0.0
    ret: float = 0.0


@dataclass
class LeagueGame:
    """A game against a league opponent: who sits where, and who it is."""
    seat: int  # the opponent's seat
    opponent: int  # index into the league list


def _sample(net: nn.Module, observations: list, device: str):
    """One stochastic move per observation: (choices, log probs, values)."""
    batch = net.collate([o.encoded for o in observations]).to(device)
    with torch.no_grad():
        logits, index, values = net(batch)
        log_probs = segment_log_softmax(logits, index).cpu()
    ptr = segment_ptr(index, len(observations)).cpu()
    out = []
    for i in range(len(observations)):
        lp = log_probs[ptr[i]:ptr[i + 1]]
        choice = int(torch.multinomial(lp.exp(), 1))
        out.append((choice, float(lp[choice]), float(values[i])))
    return out


def collect_games(net: nn.Module, card_sets: CardSet | list[CardSet], num_games: int, rng: random.Random,
                  device: str, gamma: float = 1.0, gae_lambda: float = 0.95, league: list | None = None,
                  league_share: float = 0.0, outcomes: bool = True, mirror_share: float = 0.0,
                  puzzles: list[Puzzle] | None = None, puzzle_games: int = 0):
    """Plays num_games games, a league_share of them against league opponents (frozen networks or
    agents) and a mirror_share with the same deck on both sides, plus puzzle_games puzzle episodes
    (one turn each, from puzzles on these card sets). Returns the training steps, the average game
    length in turns, the learner's results against the league as (wins, games), and the share of
    puzzle episodes it won (None without any). outcomes=False zeroes the action-outcome features."""
    def look(game: Game):
        obs = observe(game, game.state.decision_player)
        if not outcomes:
            obs.encoded.action_outcome[:] = 0
        return obs

    card_sets = card_sets if isinstance(card_sets, list) else [card_sets]
    games, matchups = [], []
    for _ in range(num_games):
        cs = rng.choice(card_sets)
        deck = random_deck(cs, rng)
        other = list(deck) if rng.random() < mirror_share else random_deck(cs, rng)
        games.append(Game(deck, other, seed=rng.randrange(2**31)))
        matchups.append(LeagueGame(rng.randrange(2), rng.randrange(len(league)))
                        if league and rng.random() < league_share else None)
    focus: list[int | None] = [None] * num_games  # a puzzle episode's player: only their turn is played
    if puzzles and puzzle_games:
        by_name = {cs.name: cs for cs in card_sets}
        for puzzle in rng.choices(puzzles, k=puzzle_games):
            games.append(puzzle.position(by_name[puzzle.cards]))
            matchups.append(None)
            focus.append(puzzle.player)
    trajectories = [([], []) for _ in games]  # per game, per player: the learner's decisions only
    active = list(range(len(games)))
    net.eval()
    while active:
        learner, by_opponent = [], {}
        for g in active:
            m = matchups[g]
            if m is not None and games[g].state.decision_player == m.seat:
                by_opponent.setdefault(m.opponent, []).append(g)
            else:
                learner.append(g)
        if learner:
            observations = [look(games[g]) for g in learner]
            for g, obs, (choice, log_prob, value) in zip(learner, observations, _sample(net, observations, device)):
                game = games[g]
                if focus[g] is None or game.state.decision_player == focus[g]:
                    trajectories[g][game.state.decision_player].append(Step(obs.encoded, choice, log_prob, value))
                game.step(obs.actions[choice], validate=False)
        for k, group in by_opponent.items():
            opponent = league[k]
            if isinstance(opponent, nn.Module):
                observations = [look(games[g]) for g in group]
                for g, obs, (choice, _, _) in zip(group, observations, _sample(opponent, observations, device)):
                    games[g].step(obs.actions[choice], validate=False)
            else:
                for g in group:
                    games[g].step(opponent.choose(games[g]), validate=False)
        active = [g for g in active if not games[g].is_over
                  and (focus[g] is None or games[g].state.active_player == focus[g])]

    unfinished = [g for g in range(len(games)) if focus[g] is not None and not games[g].is_over]
    bootstrap = dict(zip(unfinished, _values(net, [games[g] for g in unfinished], device)))
    steps, league_wins, league_games, solved = [], 0, 0, 0
    for g, (game, per_player, m) in enumerate(zip(games, trajectories, matchups)):
        winner = game.state.winner
        for player, trajectory in enumerate(per_player):
            if g in bootstrap:  # a puzzle whose turn ended: the position's value for the player
                outcome = bootstrap[g] if game.state.decision_player == player else -bootstrap[g]
            else:
                outcome = 0.0 if winner is None else (1.0 if winner == player else -1.0)
            steps.extend(_gae(trajectory, outcome, gamma, gae_lambda))
        if m is not None:
            league_games += 1
            league_wins += winner == 1 - m.seat
        if focus[g] is not None:
            solved += winner == focus[g]
    puzzle_rate = solved / (len(games) - num_games) if len(games) > num_games else None
    return steps, sum(g.state.turn for g in games[:num_games]) / max(num_games, 1), (league_wins, league_games), puzzle_rate


def _values(net: nn.Module, games: list[Game], device: str) -> list[float]:
    """The value of each game for its decision player."""
    if not games:
        return []
    batch = net.collate([observe(g, g.state.decision_player).encoded for g in games]).to(device)
    with torch.no_grad():
        _, _, values = net(batch)
    return values.cpu().tolist()


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


def train(cfg: PPOConfig, card_sets: CardSet | list[CardSet], out_path, log=print,
          eval_sets: dict[str, CardSet] | None = None) -> nn.Module:
    """Trains on games from the card sets (each game picks one); evaluates on the first, and vs the
    heuristic on each of eval_sets (cards it doesn't train on). The best checkpoint is picked on the
    eval sets' average when there are any: the training cards flatter the agent."""
    card_sets = card_sets if isinstance(card_sets, list) else [card_sets]
    eval_sets = eval_sets or {}
    run = None
    if cfg.wandb:
        import wandb
        run = wandb.init(project=cfg.wandb, name=Path(out_path).stem, config=asdict(cfg))
    torch.manual_seed(cfg.seed)
    rng = random.Random(cfg.seed)
    net = (load_model(cfg.init, cfg.device) if cfg.init
           else create_model(cfg.arch, hidden=cfg.hidden, num_layers=cfg.num_layers).to(cfg.device))
    net.train()
    optimizer = torch.optim.Adam(net.parameters(), lr=cfg.lr)
    snapshots: list[nn.Module] = []
    puzzles = _load_puzzles(cfg.puzzles, card_sets) if cfg.puzzle_games else None
    best = -1.0
    with SelfPlayPool(cfg.workers, card_sets, puzzles) if cfg.workers else contextlib.nullcontext() as pool:
        for it in range(1, cfg.iterations + 1):
            t0 = time.time()
            league = [HeuristicAgent(), *snapshots]
            options = dict(gamma=cfg.gamma, gae_lambda=cfg.gae_lambda, league_share=cfg.league_share,
                           outcomes=cfg.outcomes, mirror_share=cfg.mirror_share)
            if pool:
                collected = pool.collect(net, cfg.games_per_iteration, rng, league, cfg.puzzle_games, **options)
            else:
                collected = collect_games(net, card_sets, cfg.games_per_iteration, rng, cfg.device, league=league,
                                          puzzles=puzzles, puzzle_games=cfg.puzzle_games, **options)
            steps, avg_turns, (league_wins, league_games), puzzle_rate = collected
            t1 = time.time()
            metrics = ppo_update(net, optimizer, steps, cfg)
            t2 = time.time()
            league_text = f" | league {league_wins}/{league_games}" if league_games else ""
            if puzzle_rate is not None:
                league_text += f" | puzzles {puzzle_rate:.0%}"
            if run:
                run.log({"steps": len(steps), "turns_per_game": avg_turns, **metrics, "play_s": t1 - t0, "learn_s": t2 - t1,
                         **({"league_win_rate": league_wins / league_games} if league_games else {}),
                         **({"puzzle_win_rate": puzzle_rate} if puzzle_rate is not None else {})}, step=it)
            log(f"it {it:4d} | {len(steps):6d} steps | {avg_turns:5.1f} turns/game | "
                f"pi {metrics['policy_loss']:+.3f} v {metrics['value_loss']:.3f} ent {metrics['entropy']:.3f} "
                f"kl {metrics['approx_kl']:+.4f} clip {metrics['clip_frac']:.2f} ep {metrics['epochs']} | "
                f"play {t1 - t0:4.1f}s learn {t2 - t1:4.1f}s{league_text}")
            if cfg.league_share > 0 and it % cfg.snapshot_every == 0:
                snapshot = copy.deepcopy(net).eval()
                for p in snapshot.parameters():
                    p.requires_grad_(False)
                snapshots = (snapshots + [snapshot])[-cfg.pool_size:]
            if it % cfg.eval_every == 0 or it == cfg.iterations:
                result = evaluate(net, card_sets[0], cfg.eval_games, seed=cfg.eval_seed, device=cfg.device)
                agent = NeuralAgent(net, device=cfg.device, greedy=True)
                for name, cs in eval_sets.items():
                    result[f"{name}_vs_heuristic"] = play_match(agent, HeuristicAgent(), cs, cfg.eval_games, cfg.eval_seed)["win_rate"]
                held_out = [result[f"{name}_vs_heuristic"] for name in eval_sets]
                score = sum(held_out) / len(held_out) if held_out else result["vs_heuristic"]
                log(f"     eval: {result['vs_random']:.1%} vs random, {result['vs_heuristic']:.1%} vs heuristic"
                    + "".join(f", {name} {result[f'{name}_vs_heuristic']:.1%}" for name in eval_sets))
                if run:
                    run.log({f"eval/{k}": v for k, v in result.items()} | {"eval/score": score}, step=it)
                save_model(net, out_path, {"config": asdict(cfg), "iteration": it, "eval": result})
                if score > best:
                    best = score
                    save_model(net, str(out_path).replace(".pt", "_best.pt"),
                               {"config": asdict(cfg), "iteration": it, "eval": result})
    if run:
        run.finish()
    return net


def _load_puzzles(path: str, card_sets: list[CardSet]) -> list[Puzzle]:
    """The puzzles from `path` on the training card sets (puzzles on other cards would be evaluation data)."""
    names = {cs.name for cs in card_sets}
    puzzles = [Puzzle.from_dict(json.loads(line)) for line in Path(path).read_text().splitlines()]
    puzzles = [p for p in puzzles if p.cards in names]
    if not puzzles:
        raise ValueError(f"no puzzles in {path} on the training cards ({', '.join(sorted(names))})")
    return puzzles
