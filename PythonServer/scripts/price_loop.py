"""Prices from the metagame (src/deck_search/price_loop.py): the matchup table, the best response
to its smoothed equilibrium, and a market step on group prices, repeated.

    uv run python -m scripts.price_loop data/elites/set_1000_c_share.json --rounds 8

Starts from the archive's --top elites per class on the archive's set; writes each round, the
final table and the repriced set to data/price_loop/<archive>/. --resume DIR starts instead from a
finished loop's repriced set and decks (the --population its final mix uses most), e.g. to go on
with a model playing the table:

    uv run python -m scripts.price_loop --resume data/price_loop/set_1000_c_share \
        --agent models/tcgnet_v7c_best.pt --search-agent heuristic --population 36 --games 20 \
        --out data/price_loop/set_1000_c_v7c_best
"""
import argparse
import json
from pathlib import Path

import numpy as np

from src.cards.schema import load_card_set
from src.deck_search.metagame import top_elites
from src.deck_search.price_loop import LoopConfig, prune, run
from src.game.decks import deck_class
from src.paths import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--out", type=Path)
    for name, value in vars(LoopConfig()).items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=type(value), default=value)
    args = parser.parse_args()
    cfg = LoopConfig(**{k: getattr(args, k) for k in vars(LoopConfig())})
    if args.resume:
        final = json.loads((args.resume / "final.json").read_text())
        name = final.get("cards") or next(p.stem for p in args.resume.glob("*.json")
                                          if p.name != "final.json" and not p.name.startswith("round_"))
        card_set = load_card_set(args.resume / f"{name}.json")
        decks = [tuple(d) for d in final["decks"]]
        classes = [deck_class([card_set[i] for i in d]) for d in decks]
        decks = [decks[k] for k in prune(decks, np.array(final["mix"]), classes, cfg.population, cfg.keep_per_class)]
        out = args.out or args.resume.with_name(args.resume.name + "_resumed")
    else:
        archive = json.loads(args.archive.read_text())
        card_set = load_card_set(ROOT / archive["cards"])
        decks = [tuple(e["deck"]) for e in top_elites(archive, args.top)]
        out = args.out or Path("data/price_loop") / args.archive.stem
    run(card_set, decks, cfg, out, log=lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
