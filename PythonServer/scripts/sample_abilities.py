"""Samples abilities from the grammar and prints them as card text."""
import argparse
import json
import random

from src.cards.abilities import AbilitySampler, render, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--action-share", type=float, default=0.25, help="share of action cards (the rest are units)")
    parser.add_argument("--trees", action="store_true", help="also print each ability's authoring tree")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    sampler = AbilitySampler(rng)
    for i in range(1, args.count + 1):
        card_type = "action" if rng.random() < args.action_share else "unit"
        ability = sampler.ability(card_type)
        problems = validate(ability, card_type)
        print(f"{i:3d}. [{card_type}, {ability['kind']}] {render(ability, card_type)}")
        if problems:
            print(f"     invalid: {'; '.join(problems)}")
        if args.trees:
            print("     " + json.dumps(ability))


if __name__ == "__main__":
    main()
