"""MAP-Elites over decks (Fontaine et al. 2019; docs/stage-2-research-plan.md section 4A).

The archive keeps the best deck in each cell of a grid over behaviour descriptors, so the search
maps the space of *different* strong decks instead of converging on one. A deck is a sorted tuple
of card IDs. Its fitness is the average hero-health difference at the end of its games against a
fixed field of random decks, played in both seats; its descriptors are measured from the same
games (`MEASURES`).

Cell boundaries slide: every `slide_every` evaluations each axis is cut at percentiles of every
deck evaluated so far, and the archive is rebuilt from the whole history, because decks bunch up
and an even grid over fixed bounds wastes most of its cells. Evaluations run in batches across
worker processes; a batch's parents are picked from the archive as it was when the batch started.
"""
import multiprocessing as mp
import random
from collections import Counter
from dataclasses import asdict, dataclass, field

import numpy as np

from src.cards.schema import Card, CardSet
from src.game.decks import DECK_SIZE, MAX_COPIES, random_deck
from src.game.engine import Game

Deck = tuple[str, ...]

# What a deck's games measure, each usable as a behaviour axis.
MEASURES = ("cost", "hero_share", "turns", "action_share")


@dataclass
class Config:
    budget: int = 10_000  # evaluations in all
    initial: int = 200  # random decks first
    opponents: int = 16  # field decks, each played in both seats (8 overfit the field more)
    axes: tuple[str, ...] = ("cost", "hero_share")
    grid: int = 10  # cells per axis
    slide_every: int = 100
    batch: int = 64  # evaluations per batch (parents come from the archive as it was before it)
    fixed_seeds: bool = False  # the same game seeds for every deck (less noise, but the search can fit the deals)
    seed: int = 0


@dataclass
class Evaluation:
    deck: Deck
    fitness: float
    measures: dict[str, float]
    parent: int | None = None
    swaps: int = 0


@dataclass
class Result:
    config: Config
    cuts: list[list[float]]
    archive: dict[tuple[int, ...], int]  # cell -> index of its elite in history
    history: list[Evaluation] = field(default_factory=list)

    def elites(self) -> list[tuple[tuple[int, ...], Evaluation]]:
        return sorted((cell, self.history[i]) for cell, i in self.archive.items())

    def stats(self) -> dict:
        fit = [e.fitness for _, e in self.elites()]
        return {"evaluations": len(self.history), "elites": len(fit),
                "coverage": round(len(fit) / self.config.grid ** len(self.config.axes), 3),
                "qd_score": round(sum(f + 30 for f in fit), 1),  # fitness shifted to be positive (hero health 30)
                "best": max(fit), "mean_elite": round(sum(fit) / len(fit), 2)}

    def to_json(self) -> dict:
        return {"config": asdict(self.config), "cuts": self.cuts, "stats": self.stats(),
                "elites": [{"cell": list(cell), "fitness": e.fitness, "measures": e.measures, "deck": list(e.deck)}
                           for cell, e in self.elites()]}


# ---------------------------------------------------------------------- decks

def deck_of(cards: list[Card]) -> Deck:
    return tuple(sorted(c.id for c in cards))


def mutate(deck: Deck, ids: list[str], rng: random.Random) -> tuple[Deck, int]:
    """Swaps k cards for k others from the set, k geometric (1 half the time), keeping MAX_COPIES."""
    k = 1
    while rng.random() < 0.5 and k < len(deck):
        k += 1
    cards = list(deck)
    out = {cards.pop(rng.randrange(len(cards))) for _ in range(k)}
    copies = Counter(cards)
    while len(cards) < len(deck):
        c = rng.choice(ids)
        if copies[c] < MAX_COPIES and c not in out:
            cards.append(c)
            copies[c] += 1
    return tuple(sorted(cards)), k


def field_decks(card_set: CardSet, opponents: int, seed: int) -> list[Deck]:
    """The fixed field: random decks drawn as self-play draws them."""
    return [deck_of(random_deck(card_set, random.Random(seed * 1000 + n))) for n in range(opponents)]


# ---------------------------------------------------------------------- evaluation

def play(deck: list[Card], field_: list[list[Card]], agents: tuple, seed: int) -> tuple[float, dict[str, float]]:
    """Plays the deck against each field deck in both seats; fitness and the measures."""
    health = hero = units = turns = 0
    actions = played = 0
    for n, rival in enumerate(field_):
        for seat in (0, 1):
            decks = (deck, rival) if seat == 0 else (rival, deck)
            game = Game(*decks, seed=seed + n, first_player=0)
            while not game.is_over:
                result = game.step(agents[game.state.decision_player].choose(game), validate=False, record=True)
                hero += result.hero_damage.get(1 - seat, 0)
                units += sum(d for uid, d in result.damage.items() if game.card(uid).owner != seat)
            players = game.state.players
            health += players[seat].health - players[1 - seat].health
            turns += game.state.turn
            mine = [c for c in game.state.cards if c.owner == seat and c.played_turn is not None]
            played += len(mine)
            actions += sum(c.card.type == "action" for c in mine)
    games = 2 * len(field_)
    return round(health / games, 3), {
        "cost": round(sum(c.cost for c in deck) / len(deck), 4),
        "hero_share": round(hero / max(1, hero + units), 4),
        "turns": round(turns / games, 2),
        "action_share": round(actions / max(1, played), 4)}


_worker: dict = {}


def make_agent(spec: str):
    """"heuristic" or a checkpoint path (the network plays greedily)."""
    if spec == "heuristic":
        from src.agents.heuristic_agent import HeuristicAgent
        return HeuristicAgent()
    from src.agents.neural_agent import NeuralAgent
    return NeuralAgent.from_checkpoint(spec)


def _init(card_set: CardSet, field_: list[Deck], agent: str):
    import torch
    torch.set_num_threads(1)
    by_id = {c.id: c for c in card_set.cards}
    _worker.update(by_id=by_id, field=[[by_id[i] for i in d] for d in field_],
                   agents=(make_agent(agent), make_agent(agent)))


def _evaluate(job: tuple[Deck, int]) -> tuple[float, dict[str, float]]:
    deck, seed = job
    return play([_worker["by_id"][i] for i in deck], _worker["field"], _worker["agents"], seed)


class Evaluator:
    """Plays decks against the field in worker processes (or here, with workers=0)."""

    def __init__(self, card_set: CardSet, field_: list[Deck], agent: str = "heuristic", workers: int = 0,
                 seed: int = 0):
        self.seed = seed
        self.pool = None
        if workers:
            self.pool = mp.get_context("spawn").Pool(workers, _init, (card_set, field_, agent))
        else:
            _init(card_set, field_, agent)

    def __call__(self, decks: list[Deck], seeds: list[int] | None = None) -> list[tuple[float, dict[str, float]]]:
        jobs = list(zip(decks, seeds or [self.seed] * len(decks)))
        if self.pool:
            return self.pool.map(_evaluate, jobs, chunksize=max(1, len(jobs) // (4 * self.pool._processes)))
        return [_evaluate(j) for j in jobs]

    def close(self):
        if self.pool:
            self.pool.terminate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------- the archive

def percentile_cuts(points: np.ndarray, grid: int) -> list[list[float]]:
    """Inner boundaries per axis at the 1/grid, 2/grid, … percentiles of the points."""
    return [[float(q) for q in np.quantile(points[:, a], np.arange(1, grid) / grid)] for a in range(points.shape[1])]


def cell_of(point, cuts: list[list[float]]) -> tuple[int, ...]:
    return tuple(int(np.searchsorted(c, v, side="right")) for v, c in zip(point, cuts))


def build_archive(history: list[Evaluation], axes: tuple[str, ...], cuts: list[list[float]]) -> dict:
    archive: dict[tuple[int, ...], int] = {}
    for i, e in enumerate(history):
        c = cell_of([e.measures[a] for a in axes], cuts)
        if c not in archive or e.fitness > history[archive[c]].fitness:
            archive[c] = i
    return archive


def map_elites(card_set: CardSet, evaluate, cfg: Config, log=print) -> Result:
    """Runs the search; `evaluate` maps a list of decks to (fitness, measures) for each."""
    rng = random.Random(cfg.seed)
    ids = [c.id for c in card_set.cards]
    history: list[Evaluation] = []

    def add(decks, parents, swaps):
        seeds = None if cfg.fixed_seeds else [rng.randrange(2**31) for _ in decks]
        for d, p, k, (f, m) in zip(decks, parents, swaps, evaluate(decks, seeds)):
            history.append(Evaluation(d, f, m, p, k))

    first = [deck_of(random_deck(card_set, rng)) for _ in range(cfg.initial)]
    for start in range(0, len(first), cfg.batch):
        part = first[start:start + cfg.batch]
        add(part, [None] * len(part), [0] * len(part))
    points = lambda: np.array([[e.measures[a] for a in cfg.axes] for e in history])
    cuts = percentile_cuts(points(), cfg.grid)
    archive = build_archive(history, cfg.axes, cuts)
    slid = len(history)
    while len(history) < cfg.budget:
        n = min(cfg.batch, cfg.budget - len(history))
        elites = sorted(archive.values())
        parents = [rng.choice(elites) for _ in range(n)]
        children = [mutate(history[p].deck, ids, rng) for p in parents]
        before = len(history)
        add([d for d, _ in children], parents, [k for _, k in children])
        if len(history) - slid >= cfg.slide_every:
            cuts = percentile_cuts(points(), cfg.grid)
            archive = build_archive(history, cfg.axes, cuts)
            slid = len(history)
        else:
            for i in range(before, len(history)):
                e = history[i]
                c = cell_of([e.measures[a] for a in cfg.axes], cuts)
                if c not in archive or e.fitness > history[archive[c]].fitness:
                    archive[c] = i
        if log and (len(history) // 1000) > (before // 1000):
            r = Result(cfg, cuts, archive, history)
            s = r.stats()
            log(f"{len(history):6} evaluations | {s['elites']} elites | best {s['best']:+.2f} "
                f"| mean elite {s['mean_elite']:+.2f} | QD {s['qd_score']}")
    return Result(cfg, cuts, archive, history)
