"""The metagame between decks (docs/stage-2-research-plan.md, section 3B).

A matchup table holds every pair of decks' win rates, each pair played over the same deals with
the decks in both seats. Its Nash equilibrium is the mix of decks a rational field would play: no
deck does better than even against it. The plain equilibrium jumps with noise in the table (a
lucky deck can take the whole mix), so prices are steered by a smoothed one, the logit quantal
response equilibrium: each deck is played in proportion to exp(win rate against the mix /
temperature), which moves smoothly as the table changes and tends to the Nash mix as the
temperature goes to zero. `balance` turns a mix into section 2's targets.

Tables grow: double oracle adds the best response to the mix and plays only its new pairs
(`Matchups.extend`). A pair's deals depend only on the two decks and the seed, so a table played
in any order, or extended, gives the same numbers.
"""
import math
import multiprocessing as mp
import random
import zlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

import numpy as np

from src.agents.match import play_game
from src.cards.costing import price_group
from src.cards.schema import Card, CardSet
from src.deck_search.map_elites import Deck, make_agent
from src.game.decks import deck_class
from src.game.engine import Game

# ---------------------------------------------------------------------- playing the table

_worker: dict = {}


def _init(card_set: CardSet, agent: str):
    import torch
    torch.set_num_threads(1)
    _worker.update(by_id={c.id: c for c in card_set.cards}, agents=(make_agent(agent), make_agent(agent)))


def pair_seed(a: Deck, b: Deck, seed: int) -> int:
    return zlib.crc32(f"{seed}|{'.'.join(a)}|{'.'.join(b)}".encode())


def _pair(job: tuple[Deck, Deck, int, int]) -> float:
    """Deck a's win rate against deck b: `games` games, each deal played with the decks in both seats."""
    a, b, games, seed = job
    by_id, agents = _worker["by_id"], _worker["agents"]
    rng = random.Random(pair_seed(a, b, seed))
    wins = 0.0
    for _ in range(games // 2):
        deal = rng.randrange(2**31)
        for first, second, a_seat in ((a, b, 0), (b, a, 1)):
            game = play_game(agents, Game([by_id[i] for i in first], [by_id[i] for i in second], seed=deal,
                                          first_player=0))
            winner = game.state.winner
            wins += 0.5 if winner is None else float(winner == a_seat)
    return wins / (games // 2 * 2)


class Matchups:
    """Plays matchup tables in worker processes (or here, with workers=0)."""

    def __init__(self, card_set: CardSet, agent: str = "heuristic", games: int = 40, workers: int = 0,
                 seed: int = 0):
        self.games, self.seed, self.pool = games, seed, None
        if workers:
            self.pool = mp.get_context("spawn").Pool(workers, _init, (card_set, agent))
        else:
            _init(card_set, agent)

    def _play(self, pairs: list[tuple[Deck, Deck]]) -> list[float]:
        # each pair is played in a fixed order (the smaller deck first), so its result doesn't
        # depend on where it sits in the table
        jobs = [(min(a, b), max(a, b), self.games, self.seed) for a, b in pairs]
        if self.pool:
            results = self.pool.map(_pair, jobs, chunksize=max(1, len(jobs) // (8 * self.pool._processes)))
        else:
            results = [_pair(j) for j in jobs]
        return [r if a <= b else 1 - r for (a, b), r in zip(pairs, results)]

    def table(self, decks: list[Deck]) -> np.ndarray:
        """table[i, j]: deck i's win rate against deck j (0.5 on the diagonal and for equal decks)."""
        return self.extend(decks[:0], np.zeros((0, 0)), decks)

    def extend(self, decks: list[Deck], table: np.ndarray, new: list[Deck]) -> np.ndarray:
        """The table for decks + new, playing only the pairs that involve a new deck."""
        everyone = list(decks) + list(new)
        n, m = len(decks), len(everyone)
        out = np.full((m, m), 0.5)
        out[:n, :n] = table
        pairs = [(i, j) for j in range(n, m) for i in range(j) if everyone[i] != everyone[j]]
        for (i, j), r in zip(pairs, self._play([(everyone[i], everyone[j]) for i, j in pairs])):
            out[i, j], out[j, i] = r, 1 - r
        return out

    def close(self):
        if self.pool:
            self.pool.close()
            self.pool.join()
            self.pool = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------- equilibria

def nash(table: np.ndarray, iters: int = 20_000) -> np.ndarray:
    """The symmetric Nash mix of a win-rate table, by regret matching+ with linearly weighted
    averaging (it converges for two-player zero-sum games)."""
    payoff = table - 0.5
    n = len(payoff)
    regret, total = np.zeros(n), np.zeros(n)
    for t in range(1, iters + 1):
        positive = regret.sum()
        x = regret / positive if positive > 0 else np.full(n, 1 / n)
        u = payoff @ x
        regret = np.maximum(regret + u - x @ u, 0)
        total += t * x
    return total / total.sum()


def qre(table: np.ndarray, temperature: float = 0.02, iters: int = 5_000, step: float = 0.2) -> np.ndarray:
    """The logit quantal response equilibrium: x = softmax(table @ x / temperature), found by
    damped fixed-point iteration (unique in zero-sum games). Win rates are 0-1, so a temperature
    of 0.02 means a deck 2 points better against the mix is played e times as much."""
    n = len(table)
    x = np.full(n, 1 / n)
    for _ in range(iters):
        u = table @ x / temperature
        response = np.exp(u - u.max())
        response /= response.sum()
        if np.abs(response - x).max() < 1e-10:
            break
        x = (1 - step) * x + step * response
    return x


def exploitability(table: np.ndarray, mix: np.ndarray) -> float:
    """How much better than even the best deck in the table does against the mix (0 at Nash)."""
    return float((table @ mix).max() - 0.5)


# ---------------------------------------------------------------------- balance targets

def card_group(card: Card) -> str:
    """The price group (src/cards/costing.py), or the unit kind for cards with no ability."""
    if card.abilities:
        return price_group(card.abilities[0], card.type)
    return "unit, keywords" if card.keywords else "unit, vanilla"


@dataclass
class Balance:
    """Section 2's targets for one mix over a table."""
    decks: float  # effective number of decks in the mix (exp of its entropy)
    classes: dict[str, float]  # each class's share of the mix
    effective_classes: float
    top_class: float  # the biggest class's share
    best_vs_field: float  # the best deck's mean win rate against every deck in the table
    cards_used: float  # share of the set's cards in a deck with at least 1% of the mix
    must_play: float  # the biggest share of the mix held by decks containing one card
    groups: dict[str, float]  # each price group's share of the mix's deck slots

    def to_json(self) -> dict:
        return asdict(self)


def effective_number(shares) -> float:
    p = np.array([s for s in shares if s > 0])
    return float(math.exp(-(p * np.log(p)).sum()))


def balance(table: np.ndarray, mix: np.ndarray, decks: list[Deck], card_set: CardSet) -> Balance:
    by_id = {c.id: c for c in card_set.cards}
    classes = defaultdict(float)
    holding = defaultdict(float)
    slots = Counter()
    for weight, deck in zip(mix, decks):
        cards = [by_id[i] for i in deck]
        classes[deck_class(cards) or "neutral"] += weight
        for i in set(deck):
            holding[i] += weight
        for c in cards:
            slots[card_group(c)] += weight / len(deck)
    used = {i for weight, deck in zip(mix, decks) if weight >= 0.01 for i in deck}
    classes = dict(sorted(classes.items(), key=lambda kv: -kv[1]))
    return Balance(
        decks=effective_number(mix), classes=classes, effective_classes=effective_number(classes.values()),
        top_class=max(classes.values()), best_vs_field=float(table.mean(1).max()),
        cards_used=len(used) / len(card_set.cards), must_play=max(holding.values()),
        groups=dict(sorted(slots.items(), key=lambda kv: -kv[1])))


def class_table(table: np.ndarray, classes: list[str | None]) -> tuple[list, np.ndarray]:
    """Mean win rate of each class's decks against each class's, over their deck pairs."""
    names = sorted({c for c in classes if c}, key=str) + ([None] if None in classes else [])
    idx = [[k for k, c in enumerate(classes) if c == name] for name in names]
    return names, np.array([[table[np.ix_(a, b)].mean() for b in idx] for a in idx])


def top_elites(archive: dict, top: int) -> list[dict]:
    """The `top` fittest elites of each class (or of the whole archive) in a MAP-Elites archive."""
    groups = defaultdict(list)
    for e in archive["elites"]:
        groups[e.get("class")].append(e)
    return [e for c in sorted(groups, key=str) for e in sorted(groups[c], key=lambda e: -e["fitness"])[:top]]


def best_decks(archive: dict, saved: dict | None = None, temperature: float = 0.02) -> dict[str, list[str]]:
    """The best deck of each class: with a saved metagame table of this archive (scripts.metagame),
    the class's deck the smoothed equilibrium plays most; otherwise its fittest elite. The table
    covers only the top elites, but those are the ones worth offering."""
    if saved is not None:
        mix = qre(np.array(saved["table"]), temperature)
        best: dict[str, tuple[float, list[str]]] = {}
        for weight, deck, aspect in zip(mix, saved["decks"], saved["classes"]):
            if aspect and (aspect not in best or weight > best[aspect][0]):
                best[aspect] = (float(weight), list(deck))
        return {a: deck for a, (_, deck) in sorted(best.items())}
    return {e["class"]: list(e["deck"]) for e in top_elites(archive, 1) if e.get("class")}
