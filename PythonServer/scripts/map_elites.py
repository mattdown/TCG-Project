"""MAP-Elites deck search (src/deck_search/map_elites.py), or re-scoring an archive with another agent.

    uv run python -m scripts.map_elites --cards cardsets/set_1000_g2.json --workers 8
    uv run python -m scripts.map_elites --rescore data/elites/set_1000_g2.json --agent models/tcgnet_v6b.pt --workers 8

The search writes the archive (its elites, cell boundaries and settings) as JSON; --history also
writes every evaluation. --rescore plays an archive's elites against the same field with another
agent and prints how the two agents' fitness compares.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from src.cards.schema import load_card_set
from src.deck_search.map_elites import MEASURES, Config, Evaluator, field_decks, map_elites


def search(args):
    card_set = load_card_set(args.cards)
    cfg = Config(budget=args.budget, initial=args.initial, opponents=args.opponents, axes=tuple(args.axes),
                 grid=args.grid, slide_every=args.slide_every, batch=args.batch, fixed_seeds=args.fixed_seeds, seed=args.seed)
    field = field_decks(card_set, cfg.opponents, cfg.seed)
    start = time.perf_counter()
    with Evaluator(card_set, field, args.agent, args.workers, cfg.seed) as evaluate:
        result = map_elites(card_set, evaluate, cfg)
    seconds = time.perf_counter() - start
    games = len(result.history) * 2 * cfg.opponents
    out = result.to_json()
    out.update(cards=str(args.cards), agent=args.agent, field=[list(d) for d in field],
               seconds=round(seconds, 1), games_per_second=round(games / seconds, 1))
    args.out = args.out or Path("data/elites") / f"{card_set.name}.json"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    if args.history:
        rows = [{"deck": list(e.deck), "fitness": e.fitness, "measures": e.measures, "parent": e.parent,
                 "swaps": e.swaps} for e in result.history]
        args.out.with_suffix(".history.json").write_text(json.dumps(rows))
    s = out["stats"]
    print(f"{games:,} games in {seconds:.0f} s ({games / seconds:.0f} a second): {s['elites']} elites, "
          f"coverage {s['coverage']:.0%}, best {s['best']:+.2f}, mean elite {s['mean_elite']:+.2f}")
    print(f"Wrote {args.out}")


def rescore(args):
    archive = json.loads(args.rescore.read_text())
    card_set = load_card_set(args.cards or Path(archive["cards"]))
    field = [tuple(d) for d in archive["field"]]
    decks = [tuple(e["deck"]) for e in archive["elites"]]
    start = time.perf_counter()
    with Evaluator(card_set, field, args.agent, args.workers, archive["config"]["seed"]) as evaluate:
        scores = evaluate(decks)
    seconds = time.perf_counter() - start
    games = len(decks) * 2 * len(field)
    old = np.array([e["fitness"] for e in archive["elites"]])
    new = np.array([f for f, _ in scores])
    rank = lambda x: np.argsort(np.argsort(x))
    print(f"{games:,} games in {seconds:.0f} s ({games / seconds:.1f} a second)")
    print(f"mean fitness {old.mean():+.2f} ({archive['agent']}) -> {new.mean():+.2f} ({args.agent}); "
          f"correlation {np.corrcoef(old, new)[0, 1]:.2f}, rank correlation {np.corrcoef(rank(old), rank(new))[0, 1]:.2f}")
    for e, (f, m) in zip(archive["elites"], scores):
        e.update(rescored=f, rescored_measures=m)
    archive["rescored_with"] = args.agent
    out = args.out or args.rescore.with_name(f"{args.rescore.stem}.{Path(args.agent).stem}.json")
    out.write_text(json.dumps(archive, indent=1))
    print(f"Wrote {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cards", type=Path, default=None, help="default: set_1000_g2 (or the archive's set)")
    parser.add_argument("--agent", default="heuristic", help='"heuristic" or a checkpoint')
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--budget", type=int, default=Config.budget)
    parser.add_argument("--initial", type=int, default=Config.initial)
    parser.add_argument("--opponents", type=int, default=Config.opponents)
    parser.add_argument("--axes", nargs="+", choices=MEASURES, default=list(Config.axes))
    parser.add_argument("--grid", type=int, default=Config.grid)
    parser.add_argument("--slide-every", type=int, default=Config.slide_every)
    parser.add_argument("--batch", type=int, default=Config.batch)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--fixed-seeds", action="store_true", help="the same game seeds for every deck")
    parser.add_argument("--history", action="store_true", help="also write every evaluation")
    parser.add_argument("--rescore", type=Path, default=None, help="an archive to re-score with --agent")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.rescore:
        rescore(args)
    else:
        args.cards = args.cards or Path("cardsets/set_1000_g2.json")
        search(args)


if __name__ == "__main__":
    main()
