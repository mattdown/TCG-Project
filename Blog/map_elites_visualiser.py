"""MAP-Elites visualiser: how Quality-Diversity search finds the best deck of each kind, animated for the blog (part 2).

    uv run --project PythonServer python Blog/map_elites_visualiser.py              # Blog/build/map_elites_visualiser.html, opened
    uv run --project PythonServer python Blog/map_elites_visualiser.py --budget 500 # a quicker, smaller run
    uv run --project PythonServer --with playwright python Blog/map_elites_visualiser.py --render   # also the .mp4

Run from the repository root; it uses PythonServer's environment. It takes a minute or two: the page shows a
real run, played here and baked in.

The run is small but real. Decks are 30 cards from cardsets/set_200.json (the cards with painted art), the first
ones drawn like self-play's (src/game/decks.random_deck). Every deck plays GAMES games with the rule-based
heuristic agent in both seats, against OPPONENTS fixed decks, once going first and once second. From those games:

- fitness f(x): the average health difference at the end (your hero's health minus theirs), -30 to 30;
- behaviour b(x): the deck's average card cost (from the list, no games needed) and the share of the damage it
  dealt that went to the enemy hero rather than to units.

map_elites() is the algorithm, short enough to read: a fixed GRID x GRID map over BOUNDS, INITIAL random decks,
then pick a random elite, mutate it (swap k cards, k geometric: 1 half the time), play, and keep it if its cell
is empty or it beats the elite there. optimise() is the contrast on the page's first step: a plain evolutionary
search that keeps only the fittest decks, given the same games.

Sliding boundaries (Fontaine et al., GECCO 2019) are shown on the same decks rather than a run of their own:
every SLIDE_EVERY evaluations the boundaries are put at percentiles of the decks seen so far, and the map grows
from 2x2 to 20x20. The page compares that with an even 20x20 grid over the same points.

Everything is seeded, so the same budget gives the same page.
"""
import argparse
import random
import time
import webbrowser
from pathlib import Path

import numpy as np

from card_generation_visualiser import OUT, SET_SIZE, render  # next to this file; it puts PythonServer on the path
from card_lab import bake, describe
from src.agents.heuristic_agent import HeuristicAgent  # noqa: E402
from src.cards.abilities import render as card_text  # noqa: E402
from src.cards.art import art_key  # noqa: E402
from src.cards.schema import Card, load_card_set  # noqa: E402
from src.game.decks import DECK_SIZE, MAX_COPIES, random_deck  # noqa: E402
from src.game.engine import Game  # noqa: E402
from src.game.terms import TERMS, keyword_text  # noqa: E402

TEMPLATE = Path(__file__).with_name("map_elites_visualiser.html")
SUMMARY = ("How MAP-Elites (Quality-Diversity search) finds the best deck of each kind for an AI-playtested "
           "trading card game, from a real small run: fitness and two behaviour descriptors (average card cost and "
           "the share of damage dealt to the enemy hero), a grid with one elite per cell, the loop of picking an "
           "elite, mutating it, playing games and keeping it if it is better, the illuminated map with its coverage "
           "and QD-score, stepping stones, and sliding boundaries (Fontaine et al., 2019).")
CARD_SET = Path(__file__).parents[1] / "PythonServer" / "cardsets" / f"set_{SET_SIZE}.json"

SEED = 0
OPPONENTS = 4  # fixed opponent decks
GAMES = 2 * OPPONENTS  # each opponent twice: going first, then second
BUDGET, INITIAL = 2000, 100  # evaluations in all; the first INITIAL are random decks
GRID = 10
BOUNDS = ((2.0, 5.0), (0.1, 0.7))  # average cost; share of damage to the enemy hero
SLIDE_EVERY, SLIDE_FROM, SLIDE_TO = 100, 2, 20
POPULATION = 20  # optimise(): the plain search's population, and its budget below
OPTIMISE_BUDGET = 600


# ---------------------------------------------------------------------- the algorithm

def map_elites(budget: int, initial: int, new_deck, mutate, evaluate, cell, rng: random.Random):
    """MAP-Elites. Returns the archive (cell -> index of its elite in history) and every evaluation in order."""
    archive, history = {}, []
    for i in range(budget):
        if i < initial:
            parent, (deck, swaps) = None, (new_deck(), None)
        else:
            parent = archive[rng.choice(sorted(archive))]  # a random elite
            deck, swaps = mutate(history[parent]["deck"])
        fitness, behaviour = evaluate(deck)
        c = cell(behaviour)
        incumbent = archive.get(c)
        if incumbent is None:
            outcome = "new"
        elif fitness > history[incumbent]["fitness"]:
            outcome = "better"
        else:
            outcome = "worse"
        if outcome != "worse":
            archive[c] = i
        history.append({"deck": deck, "parent": parent, "swaps": swaps, "fitness": fitness, "behaviour": behaviour,
                        "cell": c, "outcome": outcome, "replaced": incumbent if outcome == "better" else None})
    return archive, history


def optimise(budget: int, population: list, mutate, evaluate, rng: random.Random) -> list[list[dict]]:
    """A plain evolutionary search for contrast: mutate the fitter half, keep the fittest. Each generation's population."""
    pop = [{"deck": d, **dict(zip(("fitness", "behaviour"), evaluate(d)))} for d in population]
    generations, spent = [pop], len(pop)
    while spent + len(pop) <= budget:
        pop = sorted(pop, key=lambda x: -x["fitness"])
        children = []
        for _ in range(len(pop)):
            deck = mutate(rng.choice(pop[:len(pop) // 2])["deck"])[0]
            children.append({"deck": deck, **dict(zip(("fitness", "behaviour"), evaluate(deck)))})
        spent += len(children)
        pop = sorted(pop + children, key=lambda x: -x["fitness"])[:len(pop)]
        generations.append(pop)
    return generations


# ---------------------------------------------------------------------- decks and games

def geometric_k(rng: random.Random) -> int:
    """How many cards to swap: 1 half the time, 2 a quarter, and so on."""
    k = 1
    while rng.random() < 0.5 and k < DECK_SIZE:
        k += 1
    return k


def mutator(cards: list[Card], rng: random.Random):
    """Swap k cards for k others from the set, keeping at most MAX_COPIES of each. Decks are sorted card indexes."""
    def mutate(deck: tuple[int, ...]) -> tuple[tuple[int, ...], dict]:
        k = geometric_k(rng)
        deck = list(deck)
        out = [deck.pop(rng.randrange(len(deck))) for _ in range(k)]
        added = []
        while len(added) < k:
            c = rng.randrange(len(cards))
            if deck.count(c) < MAX_COPIES and c not in out:
                deck.append(c)
                added.append(c)
        return tuple(sorted(deck)), {"k": k, "out": out, "in": added}
    return mutate


def evaluator(cards: list[Card], opponents: list[list[Card]], seed: int):
    """Plays the deck against each opponent, going first and then second, with the heuristic agent in both seats."""
    agents = (HeuristicAgent(), HeuristicAgent())

    def evaluate(deck: tuple[int, ...]) -> tuple[float, tuple[float, float]]:
        mine = [cards[i] for i in deck]
        health = hero = units = 0
        for n, opponent in enumerate(opponents):
            for seat in (0, 1):
                decks = (mine, opponent) if seat == 0 else (opponent, mine)
                game = Game(*decks, seed=seed + n, first_player=0)
                while not game.is_over:
                    result = game.step(agents[game.state.decision_player].choose(game), validate=False, record=True)
                    hero += result.hero_damage.get(1 - seat, 0)
                    units += sum(d for uid, d in result.damage.items() if game.card(uid).owner != seat)
                players = game.state.players
                health += players[seat].health - players[1 - seat].health
        cost = sum(cards[i].cost for i in deck) / len(deck)
        return round(health / (2 * len(opponents)), 3), (round(cost, 4), round(hero / max(1, hero + units), 4))
    return evaluate


def grid_cell(bounds=BOUNDS, grid: int = GRID):
    """Even cells over fixed bounds; anything outside goes in the edge cell."""
    def cell(b: tuple[float, float]) -> tuple[int, int]:
        return tuple(min(grid - 1, max(0, int((v - lo) / (hi - lo) * grid))) for v, (lo, hi) in zip(b, bounds))
    return cell


def sliding(points: list[tuple[float, float]], every: int = SLIDE_EVERY, start: int = SLIDE_FROM,
            end: int = SLIDE_TO) -> list[dict]:
    """Fontaine et al.'s sliding boundaries: every `every` evaluations, each axis is cut at percentiles of the
    points seen so far, into a grid that grows from start x start to end x end."""
    steps = max(1, len(points) // every)
    out = []
    for s in range(1, steps + 1):
        seen = np.array(points[:s * every])
        size = start + round((end - start) * (s - 1) / max(1, steps - 1))
        cuts = [[round(float(q), 4) for q in np.quantile(seen[:, a], np.arange(1, size) / size)] for a in (0, 1)]
        out.append({"seen": s * every, "size": size, "cuts": cuts})
    return out


def occupied(points: list[tuple[float, float]], cuts: list[list[float]]) -> int:
    """How many cells of the grid with these inner boundaries hold at least one point."""
    return len({tuple(int(np.searchsorted(c, v, side="right")) for v, c in zip(p, cuts)) for p in points})


# ---------------------------------------------------------------------- the page's data

def card_json(card: Card) -> dict:
    """What painted_card.html needs to draw a card."""
    ability = card.abilities[0] if card.abilities else None
    return {"name": card.name, "subtitle": card.subtitle, "type": card.type, "cost": card.cost, "power": card.power,
            "health": card.health, "traits": list(card.traits), "keywords": [keyword_text(k, v) for k, v in card.keywords], "text": card_text(ability, card.type) if ability else "",
            "kind": ability["kind"] if ability else "", "art": art_key(card.name, card.subtitle, card.aspects)}


def showcase(history: list[dict], initial: int) -> list[int]:
    """The loop's worked examples, early in the run so the map still has room: a deck that finds an empty cell,
    one that loses to the elite, one that beats it, and a later swap of two or three cards that beats one."""
    early = range(initial, len(history))
    pick = lambda test: next((i for i in early if test(history[i])), None)
    chosen = [pick(lambda h: h["outcome"] == "new" and h["swaps"]["k"] == 1),
              pick(lambda h: h["outcome"] == "worse"),
              pick(lambda h: h["outcome"] == "better")]
    chosen = sorted(i for i in chosen if i is not None)
    if not chosen:
        return []
    last = next((i for i in early if i > chosen[-1] and history[i]["swaps"]["k"] in (2, 3)
                 and history[i]["outcome"] == "better"), None)
    return chosen + ([last] if last is not None else [])


def stepping_stone(archive: dict, history: list[dict]) -> list[int]:
    """A lineage that ends at one of the best elites and passes through a mediocre elite in another cell: the
    chain from that ancestor to the elite, by history index. Direct parents are preferred."""
    final = sorted(history[i]["fitness"] for i in archive.values())
    median, top = final[len(final) // 2], final[int(len(final) * 0.85)]
    best = None
    for i in archive.values():
        child = history[i]
        if child["fitness"] < top:
            continue
        chain, a = [i], child["parent"]
        while a is not None:
            chain.append(a)
            h = history[a]
            if h["cell"] != child["cell"] and h["fitness"] < median:
                score = (child["fitness"] - h["fitness"]) / len(chain)  # a big jump in few steps
                if best is None or score > best[0]:
                    best = (score, chain[::-1])
            a = h["parent"]
    return best[1] if best else []


def run(budget: int = BUDGET, initial: int = INITIAL, seed: int = SEED, opponents: int = OPPONENTS,
        optimise_budget: int = OPTIMISE_BUDGET) -> dict:
    """The run, its contrast and everything the page draws, as plain data."""
    card_set = load_card_set(CARD_SET)
    cards = card_set.cards
    rng = random.Random(seed)
    rivals = [random_deck(card_set, random.Random(seed * 1000 + n)) for n in range(opponents)]
    evaluate = evaluator(cards, rivals, seed)
    by_id = {c.id: i for i, c in enumerate(cards)}
    new_deck = lambda: tuple(sorted(by_id[c.id] for c in random_deck(card_set, rng)))

    games = time.perf_counter()
    archive, history = map_elites(budget, initial, new_deck, mutator(cards, rng), evaluate, grid_cell(), rng)
    seconds = time.perf_counter() - games
    plain_rng = random.Random(seed + 1)
    start = [h["deck"] for h in history[:POPULATION]]  # the same first decks
    generations = optimise(optimise_budget, start, mutator(cards, plain_rng), evaluate, plain_rng)

    points = [h["behaviour"] for h in history]
    slides = sliding(points)
    even = [[round(BOUNDS[a][0] + (BOUNDS[a][1] - BOUNDS[a][0]) * k / SLIDE_TO, 4) for k in range(1, SLIDE_TO)]
            for a in (0, 1)]
    shown = showcase(history, initial)
    lineage = stepping_stone(archive, history)
    show_cards = sorted({c for i in shown for c in (*history[i]["swaps"]["out"], *history[i]["swaps"]["in"])})
    final = [history[i]["fitness"] for i in archive.values()]
    return {
        "config": {"budget": budget, "initial": initial, "games": 2 * opponents, "opponents": opponents,
                   "grid": GRID, "bounds": BOUNDS, "set": f"set_{SET_SIZE}", "deck_size": DECK_SIZE,
                   "slide_every": SLIDE_EVERY, "slide_from": SLIDE_FROM, "slide_to": SLIDE_TO,
                   "population": POPULATION, "optimise_budget": optimise_budget},
        "stats": {"games": budget * 2 * opponents, "seconds": round(seconds, 1),
                  "games_per_second": round(budget * 2 * opponents / seconds, 1), "elites": len(archive),
                  "coverage": round(len(archive) / GRID ** 2, 3),
                  "qd_score": round(sum(f + 30 for f in final), 1), "best": max(final),
                  "uniform_cells": occupied(points, even), "sliding_cells": occupied(points, slides[-1]["cuts"])},
        "terms": {"hero": TERMS["hero"], "unit": TERMS["unit"]},
        "evals": [{"p": h["parent"], "k": h["swaps"]["k"] if h["swaps"] else 0, "f": h["fitness"],
                   "b": h["behaviour"], "c": h["cell"], "o": h["outcome"]} for h in history],
        "showcase": [{"i": i, "parent": history[i]["parent"], "out": history[i]["swaps"]["out"],
                      "in": history[i]["swaps"]["in"], "parent_deck": history[history[i]["parent"]]["deck"],
                      "replaced": history[i]["replaced"]} for i in shown],
        "first_deck": history[0]["deck"], "costs": [c.cost for c in cards],
        "lineage": lineage,
        "plain": [[{"f": x["fitness"], "b": x["behaviour"]} for x in g] for g in generations],
        "slides": slides, "even": even,
        "cards": {c: card_json(cards[c]) for c in show_cards},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--budget", type=int, default=BUDGET, help="evaluations (each plays GAMES games)")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", type=Path, default=OUT / "map_elites_visualiser.html")
    parser.add_argument("--render", action="store_true", help="also render the video next to the page (needs playwright)")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    data = run(args.budget, seed=args.seed)
    s = data["stats"]
    print(f"{s['games']:,} games in {s['seconds']} s ({s['games_per_second']} a second): {s['elites']} elites, "
          f"coverage {s['coverage']:.0%}, QD-score {s['qd_score']}, best {s['best']}")
    keys = {c["art"] for c in data["cards"].values()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(describe(bake(TEMPLATE, data, keys), "MAP-Elites visualiser", SUMMARY))
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    if args.render:
        render(args.out, args.out.with_suffix(".mp4"), args.fps)
    elif not args.no_browser:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
