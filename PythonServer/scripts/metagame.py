"""The metagame between MAP-Elites elites (src/deck_search/metagame.py): their matchup table, its
Nash and smoothed (quantal response) equilibria, and the balance targets.

    uv run python -m scripts.metagame data/elites/heldout_200_c.json
    uv run python -m scripts.metagame data/elites/heldout_200_c.json --agent models/tcgnet_v7c_best.pt
    uv run python -m scripts.metagame --load data/metagame/heldout_200_c.heuristic.json --temperature 0.01

Takes the --top fittest elites of each class, plays every pair --games times (each deal in both
seats) and writes the table to data/metagame/<archive>.<agent>.json; --load re-reports a saved one.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from src.cards.schema import load_card_set
from src.deck_search.metagame import Matchups, balance, class_table, exploitability, nash, qre, top_elites
from src.game.terms import ASPECT_NAMES
from src.paths import ROOT


def name(aspect) -> str:
    return ASPECT_NAMES.get(aspect, "Neutral") if aspect else "Neutral"


def report(saved: dict, temperature: float):
    card_set = load_card_set(ROOT / saved["cards"])
    table = np.array(saved["table"])
    decks = [tuple(d) for d in saved["decks"]]
    classes = saved["classes"]
    print(f"{len(decks)} decks from {saved['archive']}, played by {saved['agent']} ({saved['games']} games a pair; "
          f"one matchup is about ±{0.5 / np.sqrt(saved['games']):.0%})")
    for label, mix in (("Nash", nash(table)), (f"Smoothed (temperature {temperature})", qre(table, temperature))):
        b = balance(table, mix, decks, card_set)
        print(f"\n{label}: exploitability {exploitability(table, mix):+.3f}, {b.decks:.1f} effective decks, "
              f"{b.effective_classes:.1f} effective classes")
        print("  classes: " + ", ".join(f"{name(c)} {s:.0%}" for c, s in b.classes.items() if s >= 0.005))
        print(f"  best deck against the field {b.best_vs_field:.1%}; cards used {b.cards_used:.0%}; "
              f"must-play {b.must_play:.0%}")
        print("  deck slots: " + ", ".join(f"{g} {s:.0%}" for g, s in list(b.groups.items())[:8]))
    names, ct = class_table(table, classes)
    order = np.argsort(-ct.mean(1))
    print("\nClass against class (the row's mean win rate):")
    print(" " * 10 + "".join(f"{name(names[k]):>8}" for k in order))
    for r in order:
        print(f"{name(names[r]):>8}  " + "".join(f"{ct[r, k]:8.1%}" for k in order))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path, nargs="?", help="a MAP-Elites archive (data/elites/...)")
    parser.add_argument("--load", type=Path, help="report a saved table instead of playing one")
    parser.add_argument("--agent", default="heuristic", help='"heuristic" or a checkpoint')
    parser.add_argument("--top", type=int, default=10, help="the fittest N elites of each class")
    parser.add_argument("--games", type=int, default=40, help="games a pair (each deal in both seats)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.02, help="the smoothed equilibrium's")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.load:
        report(json.loads(args.load.read_text()), args.temperature)
        return
    if not args.archive:
        parser.error("give an archive or --load")
    archive = json.loads(args.archive.read_text())
    elites = top_elites(archive, args.top)
    decks = [tuple(e["deck"]) for e in elites]
    card_set = load_card_set(ROOT / archive["cards"])
    start = time.perf_counter()
    with Matchups(card_set, args.agent, args.games, args.workers, args.seed) as matchups:
        table = matchups.table(decks)
    seconds = time.perf_counter() - start
    games = len(decks) * (len(decks) - 1) // 2 * args.games
    print(f"{games:,} games in {seconds:.0f} s ({games / seconds:.0f} a second)")
    saved = {"archive": str(args.archive), "cards": archive["cards"], "agent": args.agent, "games": args.games,
             "seed": args.seed, "decks": [list(d) for d in decks], "classes": [e.get("class") for e in elites],
             "fitness": [e["fitness"] for e in elites], "table": np.round(table, 4).tolist()}
    out = args.out or Path("data/metagame") / f"{args.archive.stem}.{Path(args.agent).stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(saved))
    print(f"Wrote {out}\n")
    report(saved, args.temperature)


if __name__ == "__main__":
    main()
