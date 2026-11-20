"""Prices from the metagame: repricing and double-oracle deck building as one loop
(docs/roadmap.md, step 3; docs/stage-2-research-plan.md, F2 and 3B).

Each round:
1. play the matchup table between the population of decks on the current prices (Matchups);
2. find the best response to the population's smoothed equilibrium: a per-class MAP-Elites run
   whose field is drawn from the mix, started from the population's decks (double oracle); add
   each class's best new deck and play only its new pairs;
3. read each deck's value: its win rate against the mix. Across the population, a price group
   whose card count goes with a higher value gives decks an edge, so it's underpriced; one that
   goes with a lower value is overpriced;
4. move each group's log scale by `step` times that correlation (capped per round, with a dead
   band for noise), reprice the set in place (src/cards/reprice.py) and keep the decks the mix
   uses most, with a few of every class.
The loop is balanced when no group's count goes with winning. Groups belong mostly to classes,
so the signal also lifts weak classes and holds back strong ones. (Usage in the mix against the
set's supply was tried first and fails: a group only some classes can play looks unused when
those classes are out of the mix, and a class out of the mix never gets a signal at all.)
The agent stays fixed (the heuristic by default): it's the cheap inner loop, and the agent is
retrained in the outer one. A model can play the table (it sets the prices) while the heuristic
searches the best responses, which a model is too slow for. Groups without an ability (vanilla and keyword units) and small
groups keep their prices.
"""
import json
import math
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from src.cards.reprice import reprice, scales_of
from src.cards.schema import CardSet, save_card_set
from src.deck_search.map_elites import Config, Deck, Evaluator, map_elites
from src.deck_search.metagame import Matchups, balance, card_group, class_table, qre
from src.game.decks import deck_class


@dataclass
class LoopConfig:
    rounds: int = 8
    agent: str = "heuristic"  # plays the table, so it sets the prices
    search_agent: str = ""  # plays the best-response search (default: the agent; the heuristic is ~120x faster)
    games: int = 40  # per pair in the table
    temperature: float = 0.02  # the smoothed equilibrium's
    step: float = 0.5  # a group's log scale moves by step × the correlation of its count with value
    dead_band: float = 0.15  # smaller correlations are noise (about one standard error with 70 decks)
    max_change: float = 0.2  # largest change of a group's log scale in one round (about ×1.22)
    min_cards: int = 10  # smaller groups keep their price
    population: int = 72  # decks kept between rounds
    keep_per_class: int = 3  # every class keeps at least its best this many
    search_budget: int = 3000  # MAP-Elites evaluations for each best response
    opponents: int = 16  # field decks drawn from the mix
    workers: int = 8
    seed: int = 0


def group_counts(card_set: CardSet, decks: list[Deck]) -> dict[str, np.ndarray]:
    """Each price group's card count in each deck."""
    groups = {g: np.zeros(len(decks)) for g in {card_group(c) for c in card_set.cards}}
    for k, deck in enumerate(decks):
        for i in deck:
            groups[card_group(card_set[i])][k] += 1
    return groups


def price_step(counts: dict[str, np.ndarray], value: np.ndarray, scales: dict[str, float], sizes: dict[str, int],
               cfg: LoopConfig) -> tuple[dict[str, float], dict[str, float]]:
    """New scales for the ability groups whose count goes with a deck's value (win rate against the
    mix), and every group's correlation."""
    out, corr = {}, {}
    for g, n in counts.items():
        if n.std() == 0 or value.std() == 0:
            continue
        corr[g] = round(float(np.corrcoef(n, value)[0, 1]), 3)
        if sizes.get(g, 0) < cfg.min_cards or g in ("unit, vanilla", "unit, keywords") or abs(corr[g]) < cfg.dead_band:
            continue
        change = max(-cfg.max_change, min(cfg.max_change, cfg.step * corr[g]))
        out[g] = round(scales.get(g, 1.0) * math.exp(change), 4)
    return out, corr


def mix_field(decks: list[Deck], mix: np.ndarray, n: int, rng: random.Random) -> list[Deck]:
    """`n` field decks drawn from the mix (with replacement)."""
    return rng.choices(decks, weights=list(mix), k=n)


def prune(decks: list[Deck], mix: np.ndarray, classes: list, cap: int, keep: int) -> list[int]:
    """Indexes of the decks to keep: each class's `keep` most used, then the most used overall."""
    order = list(np.argsort(-mix))
    kept = []
    for c in set(classes):
        kept += [k for k in order if classes[k] == c][:keep]
    for k in order:
        if len(kept) >= cap:
            break
        if k not in kept:
            kept.append(k)
    return sorted(kept)


def best_responses(card_set: CardSet, decks: list[Deck], mix: np.ndarray, cfg: LoopConfig, rng: random.Random,
                   log) -> list[Deck]:
    """Each class's best deck against a field drawn from the mix, searched from the population."""
    field_ = mix_field(decks, mix, cfg.opponents, rng)
    search = Config(budget=cfg.search_budget, initial=max(200, len(decks)), opponents=cfg.opponents, per_class=True,
                    rings=4, seed=rng.randrange(2**31))
    with Evaluator(card_set, field_, cfg.search_agent or cfg.agent, cfg.workers) as evaluate:
        result = map_elites(card_set, evaluate, search, log=None, start=list(decks))
    best = {}
    for _, e in result.elites():
        c = deck_class([card_set[i] for i in e.deck])
        if e.deck not in decks and (c not in best or e.fitness > best[c].fitness):
            best[c] = e
    for c, e in sorted(best.items(), key=lambda kv: str(kv[0])):
        log(f"    best response {c}: {e.fitness:+.1f} against the mix")
    return [e.deck for e in best.values()]


def summary(card_set: CardSet, decks: list[Deck], table: np.ndarray, mix: np.ndarray) -> dict:
    b = balance(table, mix, decks, card_set)
    classes = [deck_class([card_set[i] for i in d]) for d in decks]
    names, ct = class_table(table, classes)
    return {"balance": b.to_json(), "class_means": {str(n): round(float(r.mean()), 4) for n, r in zip(names, ct)}}


def run(card_set: CardSet, decks: list[Deck], cfg: LoopConfig, out_dir: Path, log=print) -> CardSet:
    """Runs the loop from `decks` (e.g. the top elites per class); writes each round to `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(cfg.seed)
    decks = list(dict.fromkeys(decks))
    sizes = Counter(card_group(c) for c in card_set.cards)
    for r in range(cfg.rounds):
        with Matchups(card_set, cfg.agent, cfg.games, cfg.workers, cfg.seed) as m:
            table = m.table(decks)
            mix = qre(table, cfg.temperature)
            before = summary(card_set, decks, table, mix)
            new = best_responses(card_set, decks, mix, cfg, rng, log)
            table = m.extend(decks, table, new)
        decks = decks + new
        mix = qre(table, cfg.temperature)
        after = summary(card_set, decks, table, mix)
        scales = scales_of(card_set)
        changed, corr = price_step(group_counts(card_set, decks), table @ mix, scales, sizes, cfg)
        b = after["balance"]
        log(f"round {r + 1}: {b['decks']:.1f} effective decks, {b['effective_classes']:.1f} effective classes, "
            f"top class {b['top_class']:.0%}, best deck {b['best_vs_field']:.1%} against the field, "
            f"cards used {b['cards_used']:.0%}")
        log("  classes in the mix: " + ", ".join(f"{c} {s:.0%}" for c, s in b["classes"].items() if s >= 0.005))
        log("  class means: " + ", ".join(f"{c} {v:.1%}" for c, v in
                                         sorted(after["class_means"].items(), key=lambda kv: -kv[1])))
        log("  prices: " + ", ".join(f"{g} {scales.get(g, 1.0):g}→{s:g}" for g, s in sorted(changed.items())))
        classes = [deck_class([card_set[i] for i in d]) for d in decks]
        record = {"round": r + 1, "config": asdict(cfg), "scales": scales, "changed": changed, "correlation": corr,
                  "before": before,
                  "after": after, "decks": [list(d) for d in decks], "classes": classes,
                  "table": np.round(table, 4).tolist(), "mix": np.round(mix, 5).tolist()}
        (out_dir / f"round_{r + 1:02d}.json").write_text(json.dumps(record))
        keep = prune(decks, mix, classes, cfg.population, cfg.keep_per_class)
        decks = [decks[k] for k in keep]
        card_set, changes = reprice(card_set, changed)
        log(f"  repriced {len(changes)} cards")
    with Matchups(card_set, cfg.agent, cfg.games, cfg.workers, cfg.seed) as m:
        table = m.table(decks)
    mix = qre(table, cfg.temperature)
    final = summary(card_set, decks, table, mix)
    b = final["balance"]
    log(f"final prices: {b['decks']:.1f} effective decks, {b['effective_classes']:.1f} effective classes, "
        f"top class {b['top_class']:.0%}, best deck {b['best_vs_field']:.1%} against the field")
    (out_dir / "final.json").write_text(json.dumps({"cards": card_set.name, "scales": scales_of(card_set),
                                                    "after": final,
                                                    "decks": [list(d) for d in decks],
                                                    "table": np.round(table, 4).tolist(),
                                                    "mix": np.round(mix, 5).tolist()}))
    save_card_set(card_set, out_dir / f"{card_set.name}.json")
    return card_set
