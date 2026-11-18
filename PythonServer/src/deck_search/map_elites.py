"""MAP-Elites over decks (Fontaine et al. 2019; docs/stage-2-research-plan.md section 4A).

The archive keeps the best deck in each cell of a grid over behaviour descriptors, so the search
maps the space of *different* strong decks instead of converging on one. A deck is a sorted tuple
of card IDs. Its fitness is the average hero-health difference at the end of its games against a
fixed field of random decks, played in both seats; its descriptors are measured from the same
games (`MEASURES`).

The map (Space) is the ring of play styles by default: six measures, one per style, each in
standard deviations from the first (random) decks' mean, summed as vectors 60 degrees apart in
the ring's order (src/cards/classes.py). The angle is the deck's play style and the radius how
strongly it leans to it; cells are 30-degree sectors times radius bands. A grid over chosen
measures is the other option. Boundaries slide: every `slide_every` evaluations the radius bands
(or the grid's cuts) are set at percentiles of every deck evaluated so far, and the archive is
rebuilt from the whole history, because decks bunch up and even cells waste most of the map. Evaluations run in batches across
worker processes; a batch's parents are picked from the archive as it was when the batch started.
"""
import math
import multiprocessing as mp
import random
from collections import Counter
from dataclasses import asdict, dataclass, field

import numpy as np

from src.cards.schema import Card, CardSet
from src.game.decks import MAX_COPIES, class_pool, deck_class, has_classes, random_deck
from src.game.terms import ASPECTS
from src.game.engine import Game
from src.game.state import Zone

Deck = tuple[str, ...]

# What a deck's games measure, each usable as a behaviour axis. STYLE_MEASURES are one per play
# style, in the ring's order (src/cards/classes.py): the "ring" axes project them onto it.
STYLE_MEASURES = ("aggro", "swarm", "growth", "fortress", "control", "spells")
MEASURES = ("cost", "hero_share", "turns", "action_share", *STYLE_MEASURES)


@dataclass
class Config:
    budget: int = 10_000  # evaluations in all
    initial: int = 200  # random decks first
    opponents: int = 16  # field decks, each played in both seats (8 overfit the field more)
    axes: tuple[str, ...] = ("ring",)  # ("ring",): the style measures on the ring (Space); else measures for a grid
    grid: int = 10  # cells per axis (grid axes)
    sectors: int = 12  # ring: 30-degree sectors, one centred on each style and one between each neighbouring pair
    rings: int = 8  # ring: radius bands, sliding like the grid's boundaries
    per_class: bool = False  # class sets: an archive per class instead of one shared map
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
    archive: dict[tuple, int]  # cell (with the deck's class first in a class set) -> index of its elite in history
    history: list[Evaluation] = field(default_factory=list)
    classes: bool = False  # one archive per class: cells are (class, *cell)
    space: "Space | None" = None

    def elites(self) -> list[tuple[tuple[int, ...], Evaluation]]:
        return sorted((cell, self.history[i]) for cell, i in self.archive.items())

    def stats(self) -> dict:
        fit = [e.fitness for _, e in self.elites()]
        groups = len({cell[0] for cell in self.archive}) if self.classes else 1
        return {"evaluations": len(self.history), "elites": len(fit),
                "coverage": round(len(fit) / (groups * self.space.size()), 3) if self.space else None,
                "qd_score": round(sum(f + 30 for f in fit), 1),  # fitness shifted to be positive (hero health 30)
                "best": max(fit), "mean_elite": round(sum(fit) / len(fit), 2)}

    def to_json(self) -> dict:
        ring = self.space is not None and self.space.ring
        return {"config": asdict(self.config), "cuts": self.cuts, "stats": self.stats(),
                "reference": self.space.reference if ring else None,
                "elites": [{"cell": list(cell[1:] if self.classes else cell), "fitness": e.fitness,
                            "measures": e.measures, "deck": list(e.deck),
                            **(dict(zip(("angle", "radius"), self.space.point(e))) if ring else {})}
                           for cell, e in self.elites()]}


# ---------------------------------------------------------------------- decks

def deck_of(cards: list[Card]) -> Deck:
    return tuple(sorted(c.id for c in cards))


def mutate(deck: Deck, ids: list[str], rng: random.Random) -> tuple[Deck, int]:
    """Swaps k cards for k others from `ids`, k geometric (1 half the time), keeping MAX_COPIES."""
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

class Tally:
    """One player's style measures over a game, from the rules' own step records."""

    def __init__(self, seat: int):
        self.seat = seat
        self.hero = self.units = 0  # damage dealt to the enemy hero / enemy units
        self.board = self.bonus = self.ends = 0  # units in play and their stat bonuses, summed over your turns' ends
        self.crystals = self.healed = self.guarded = self.removed = self.drawn = 0

    def step(self, game: Game, result, before_active: int):
        me, them = self.seat, 1 - self.seat
        owner = lambda uid: game.card(uid).owner
        self.hero += result.hero_damage.get(them, 0)
        self.units += sum(d for uid, d in result.damage.items() if owner(uid) == them)
        self.crystals += result.crystals.get(me, 0)
        self.healed += result.hero_healed.get(me, 0) + sum(h for uid, h in result.healed.items() if owner(uid) == me)
        self.guarded += sum(d for uid, d in result.damage.items() if owner(uid) == me and game.keyword(uid, "guard"))
        if not result.attacked:  # outside combat: removed by abilities
            self.removed += sum(owner(uid) == them for uid in result.defeated)
        self.removed += sum(m.owner == them and m.source == Zone.PLAY and m.dest == Zone.HAND for m in result.moves)
        self.removed += sum(e.kind == "freeze" and owner(e.uid) == them for e in result.effects)
        draws = sum(m.owner == me and m.source == Zone.DECK for m in result.moves)
        began = game.state.active_player == me and before_active != me  # the turn's own draw
        if result.abilities:
            self.drawn += max(0, draws - began)
        if before_active == me and game.state.active_player != me:  # the end of your turn
            mine = [c for c in game.state.cards if c.owner == me and c.zone == Zone.PLAY]
            self.board += len(mine)
            self.bonus += sum(max(0, game.stat(c.uid, "power") + game.stat(c.uid, "health") - c.card.power - c.card.health)
                              for c in mine)
            self.ends += 1


def play(deck: list[Card], field_: list[list[Card]], agents: tuple, seed: int) -> tuple[float, dict[str, float]]:
    """Plays the deck against each field deck in both seats; fitness and the measures: one per play
    style (STYLE_MEASURES) and a few plain ones."""
    health = turns = actions = played = 0
    tallies = []
    for n, rival in enumerate(field_):
        for seat in (0, 1):
            decks = (deck, rival) if seat == 0 else (rival, deck)
            game = Game(*decks, seed=seed + n, first_player=0)
            tally = Tally(seat)
            while not game.is_over:
                before = game.state.active_player
                result = game.step(agents[game.state.decision_player].choose(game), validate=False, record=True)
                tally.step(game, result, before)
            tallies.append(tally)
            players = game.state.players
            health += players[seat].health - players[1 - seat].health
            turns += game.state.turn
            mine = [c for c in game.state.cards if c.owner == seat and c.played_turn is not None]
            played += len(mine)
            actions += sum(c.card.type == "action" for c in mine)
    games = 2 * len(field_)
    total = lambda f: sum(f(t) for t in tallies)
    ends = max(1, total(lambda t: t.ends))
    hero, units = total(lambda t: t.hero), total(lambda t: t.units)
    return round(health / games, 3), {
        "cost": round(sum(c.cost for c in deck) / len(deck), 4),
        "hero_share": round(hero / max(1, hero + units), 4),
        "turns": round(turns / games, 2),
        "action_share": round(actions / max(1, played), 4),
        # one per style, on the ring's order (STYLE_MEASURES)
        "aggro": round(hero / max(1, hero + units), 4),
        "swarm": round(total(lambda t: t.board) / ends, 3),
        "growth": round(total(lambda t: t.bonus) / ends + total(lambda t: t.crystals) / games, 3),
        "fortress": round(total(lambda t: t.healed + t.guarded) / games, 3),
        "control": round(total(lambda t: t.removed) / games, 3),
        "spells": round((actions + total(lambda t: t.drawn)) / games, 3)}


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


def ring_point(measures: dict[str, float], reference: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """The six style measures, each in standard deviations from the reference decks' mean, summed as
    vectors 60 degrees apart in the ring's order: (angle in degrees, radius). The angle is the play
    style (0 aggro, 60 swarm, … 300 spells), the radius how strongly the deck leans to it."""
    z = [(measures[m] - reference[m][0]) / reference[m][1] for m in STYLE_MEASURES]
    x = sum(v * math.cos(math.radians(60 * i)) for i, v in enumerate(z))
    y = sum(v * math.sin(math.radians(60 * i)) for i, v in enumerate(z))
    return round(math.degrees(math.atan2(y, x)) % 360, 2), round(math.hypot(x, y), 4)


def sector(angle: float, sectors: int) -> int:
    """Sectors centred on 0 degrees (aggro) and every 360/sectors after it."""
    width = 360 / sectors
    return int(((angle + width / 2) % 360) // width)


class Space:
    """Where a deck goes: a grid over the chosen measures, or ("ring",) the six style measures
    projected onto the ring, cut into fixed angle sectors and sliding radius bands."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ring = tuple(cfg.axes) == ("ring",)
        self.reference: dict[str, tuple[float, float]] = {}
        self.cuts: list[list[float]] = []

    def point(self, e: Evaluation) -> tuple[float, ...]:
        if self.ring:
            return ring_point(e.measures, self.reference)
        return tuple(e.measures[a] for a in self.cfg.axes)

    def calibrate(self, history: list[Evaluation], first: bool = False):
        """Sets the boundaries from the decks seen so far; the first call (the random decks) also
        fixes the ring's reference, so points stay comparable through the run."""
        if self.ring and first:
            for m in STYLE_MEASURES:
                values = np.array([e.measures[m] for e in history])
                self.reference[m] = (float(values.mean()), float(values.std()) or 1.0)
        points = np.array([self.point(e) for e in history])
        if self.ring:
            self.cuts = [[], percentile_cuts(points[:, 1:], self.cfg.rings)[0]]
        else:
            self.cuts = percentile_cuts(points, self.cfg.grid)

    def cell(self, e: Evaluation) -> tuple[int, ...]:
        p = self.point(e)
        if self.ring:
            return sector(p[0], self.cfg.sectors), int(np.searchsorted(self.cuts[1], p[1], side="right"))
        return cell_of(p, self.cuts)

    def size(self) -> int:
        return self.cfg.sectors * self.cfg.rings if self.ring else self.cfg.grid ** len(self.cfg.axes)


def build_archive(history: list[Evaluation], key) -> dict:
    """The best deck for each key (a cell)."""
    archive: dict[tuple, int] = {}
    for i, e in enumerate(history):
        c = key(e)
        if c not in archive or e.fitness > history[archive[c]].fitness:
            archive[c] = i
    return archive


def map_elites(card_set: CardSet, evaluate, cfg: Config, log=print) -> Result:
    """Runs the search; `evaluate` maps a list of decks (and game seeds) to (fitness, measures) for each."""
    rng = random.Random(cfg.seed)
    ids = [c.id for c in card_set.cards]
    pool, group = (lambda deck: ids), None
    if has_classes(card_set):  # a deck keeps to its class: swaps come from its class and the neutrals
        by_id = {c.id: c for c in card_set.cards}
        pools = {a: [c.id for c in class_pool(card_set, a)] for a in (*ASPECTS, None)}
        aspect = lambda deck: deck_class([by_id[i] for i in deck])
        pool = lambda deck: pools[aspect(deck)]
        if cfg.per_class:  # one archive per class: cells are (class, *cell)
            group = lambda deck: aspect(deck) or ""
    space = Space(cfg)
    key = (lambda e: (group(e.deck), *space.cell(e))) if group else space.cell
    history: list[Evaluation] = []

    def add(decks, parents, swaps):
        seeds = None if cfg.fixed_seeds else [rng.randrange(2**31) for _ in decks]
        for d, p, k, (f, m) in zip(decks, parents, swaps, evaluate(decks, seeds)):
            history.append(Evaluation(d, f, m, p, k))

    first = [deck_of(random_deck(card_set, rng)) for _ in range(cfg.initial)]
    for start in range(0, len(first), cfg.batch):
        part = first[start:start + cfg.batch]
        add(part, [None] * len(part), [0] * len(part))
    space.calibrate(history, first=True)
    archive = build_archive(history, key)
    slid = len(history)
    result = lambda: Result(cfg, space.cuts, archive, history, group is not None, space)
    while len(history) < cfg.budget:
        n = min(cfg.batch, cfg.budget - len(history))
        elites = sorted(archive.values())
        parents = [rng.choice(elites) for _ in range(n)]
        children = [mutate(history[p].deck, pool(history[p].deck), rng) for p in parents]
        before = len(history)
        add([d for d, _ in children], parents, [k for _, k in children])
        if len(history) - slid >= cfg.slide_every:
            space.calibrate(history)
            archive = build_archive(history, key)
            slid = len(history)
        else:
            for i in range(before, len(history)):
                c = key(history[i])
                if c not in archive or history[i].fitness > history[archive[c]].fitness:
                    archive[c] = i
        if log and (len(history) // 1000) > (before // 1000):
            s = result().stats()
            log(f"{len(history):6} evaluations | {s['elites']} elites | best {s['best']:+.2f} "
                f"| mean elite {s['mean_elite']:+.2f} | QD {s['qd_score']}")
    return result()
