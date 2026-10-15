"""Generates the vanilla card set (stats only) with simple heuristics."""
import argparse
from collections import Counter
from pathlib import Path

from src.cards.schema import save_card_set
from src.cards.vanilla import generate_vanilla_set
from src.paths import CARDSET_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=CARDSET_PATH)
    args = parser.parse_args()

    card_set = generate_vanilla_set(args.count, args.seed)
    save_card_set(card_set, args.out)
    curve = Counter(c.cost for c in card_set.cards)
    print(f"Wrote {len(card_set)} cards to {args.out}")
    print("Cost curve: " + ", ".join(f"{cost}: {curve[cost]}" for cost in sorted(curve)))
    print(f"Energy sources: {sum(c.energy_source for c in card_set.cards)}")


if __name__ == "__main__":
    main()
