"""Prices from the metagame (src/deck_search/price_loop.py): the matchup table, the best response
to its smoothed equilibrium, and a market step on group prices, repeated.

    uv run python -m scripts.price_loop data/elites/set_1000_c_share.json --rounds 8

Starts from the archive's --top elites per class on the archive's set; writes each round, the
final table and the repriced set to data/price_loop/<archive>/.
"""
import argparse
import json
from pathlib import Path

from src.cards.schema import load_card_set
from src.deck_search.metagame import top_elites
from src.deck_search.price_loop import LoopConfig, run
from src.paths import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--out", type=Path)
    for name, value in vars(LoopConfig()).items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=type(value), default=value)
    args = parser.parse_args()
    archive = json.loads(args.archive.read_text())
    card_set = load_card_set(ROOT / archive["cards"])
    decks = [tuple(e["deck"]) for e in top_elites(archive, args.top)]
    cfg = LoopConfig(**{k: getattr(args, k) for k in vars(LoopConfig())})
    run(card_set, decks, cfg, args.out or Path("data/price_loop") / args.archive.stem, log=lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
