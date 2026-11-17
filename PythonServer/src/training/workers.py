"""Self-play in parallel worker processes.

`collect_games` is pure Python game logic plus small network calls, so one process uses about one
core. The pool splits an iteration's games across worker processes, each running `collect_games`
on its share with its own seed and one torch thread, and merges what they return. The learner's
weights go to every worker each iteration; league snapshots are sent once per worker and kept
there until they leave the league.
"""
import itertools
import multiprocessing as mp
import random
import traceback
import weakref
from multiprocessing.connection import Connection

import torch
from torch import nn

from src.agents.puzzles import Puzzle
from src.cards.schema import CardSet
from src.model.registry import create_model


def _payload(net: nn.Module) -> tuple:
    return net.arch, net.hparams, {k: v.cpu() for k, v in net.state_dict().items()}


def _build(payload: tuple) -> nn.Module:
    arch, hparams, state = payload
    net = create_model(arch, **hparams)
    net.load_state_dict(state)
    return net.eval()


def _worker(conn: Connection, card_sets: list[CardSet], puzzles: list[Puzzle] | None):
    from src.training.ppo import collect_games  # here, not at the top: ppo imports this module

    torch.set_num_threads(1)
    net, snapshots = None, {}
    while (job := conn.recv()) is not None:
        try:
            payload, league_spec, num_games, puzzle_games, seed, options = job
            if net is None:
                net = _build(payload)
            else:
                net.load_state_dict(payload[2])
            league = []
            for kind, key, value in league_spec:
                if kind == "agent":
                    league.append(value)
                    continue
                if value is not None:
                    snapshots[key] = _build(value)
                league.append(snapshots[key])
            keep = {key for kind, key, _ in league_spec if kind == "net"}
            snapshots = {k: v for k, v in snapshots.items() if k in keep}
            torch.manual_seed(seed)
            result = collect_games(net, card_sets, num_games, random.Random(seed), "cpu", league=league,
                                   puzzles=puzzles, puzzle_games=puzzle_games, **options)
            conn.send(("ok", result))
        except Exception:
            conn.send(("error", traceback.format_exc()))


class SelfPlayPool:
    """Worker processes that play an iteration's games between them (see the module docstring)."""

    def __init__(self, workers: int, card_sets: list[CardSet], puzzles: list[Puzzle] | None = None):
        ctx = mp.get_context("spawn")  # fork is unsafe with torch's threads, and the macOS default anyway
        self.conns: list[Connection] = []
        self.procs = []
        for _ in range(workers):
            parent, child = ctx.Pipe()
            proc = ctx.Process(target=_worker, args=(child, card_sets, puzzles), daemon=True)
            proc.start()
            child.close()
            self.conns.append(parent)
            self.procs.append(proc)
        self.keys: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()  # league network -> key
        self.counter = itertools.count()
        self.sent = [set() for _ in range(workers)]  # snapshot keys each worker holds

    def collect(self, net: nn.Module, num_games: int, rng: random.Random, league: list | None = None,
                puzzle_games: int = 0, **options):
        """The same as `collect_games` (same arguments and return value), played across the workers."""
        n = len(self.conns)
        payload = _payload(net)
        busy = []
        for i, conn in enumerate(self.conns):
            games = num_games // n + (i < num_games % n)
            puzzles = puzzle_games // n + (i < puzzle_games % n)
            seed = rng.randrange(2**31)
            if games + puzzles == 0:
                continue
            conn.send((payload, self._league_spec(league or [], i), games, puzzles, seed, options))
            busy.append((conn, games, puzzles))
        steps, turns, league_wins, league_games, solved = [], 0.0, 0, 0, 0.0
        for conn, games, puzzles in busy:
            status, result = conn.recv()
            if status == "error":
                raise RuntimeError(f"self-play worker failed:\n{result}")
            worker_steps, avg_turns, (wins, played), puzzle_rate = result
            steps += worker_steps
            turns += avg_turns * games
            league_wins += wins
            league_games += played
            solved += (puzzle_rate or 0.0) * puzzles
        return (steps, turns / max(num_games, 1), (league_wins, league_games),
                solved / puzzle_games if puzzle_games else None)

    def _league_spec(self, league: list, worker: int) -> list[tuple]:
        spec = []
        for member in league:
            if not isinstance(member, nn.Module):
                spec.append(("agent", None, member))
                continue
            if member not in self.keys:
                self.keys[member] = next(self.counter)
            key = self.keys[member]
            spec.append(("net", key, None if key in self.sent[worker] else _payload(member)))
            self.sent[worker].add(key)
        self.sent[worker] &= {key for kind, key, _ in spec if kind == "net"}
        return spec

    def close(self):
        for conn in self.conns:
            try:
                conn.send(None)
            except (BrokenPipeError, OSError):
                pass
        for proc in self.procs:
            proc.join(timeout=10)
            if proc.is_alive():
                proc.terminate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
