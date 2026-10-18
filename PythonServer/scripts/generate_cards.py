"""Generates a card set: units with keywords (default), stats only, or a coverage set that uses every
building block of the ability grammar (plus a Markdown checklist next to it)."""
import argparse
from collections import Counter
from pathlib import Path

from src.cards.schema import save_card_set
from src.cards.coverage import coverage_report, generate_coverage_set
from src.cards.vanilla import generate_keyword_set, generate_vanilla_set
from src.paths import CARDSET_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("keywords", "vanilla", "coverage"), default="keywords")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None, help="defaults to cardsets/<kind>_<count>.json")
    args = parser.parse_args()

    if args.kind == "coverage":
        card_set = generate_coverage_set(args.seed)
    else:
        generate = generate_keyword_set if args.kind == "keywords" else generate_vanilla_set
        card_set = generate(args.count, args.seed)
    out = args.out or CARDSET_PATH.parent / f"{card_set.name}.json"
    save_card_set(card_set, out)
    if args.kind == "coverage":
        out.with_suffix(".md").write_text(coverage_report(card_set))
        print(f"Checklist: {out.with_suffix('.md')}")
    curve = Counter(c.cost for c in card_set.cards)
    print(f"Wrote {len(card_set)} cards to {out}")
    print("Cost curve: " + ", ".join(f"{cost}: {curve[cost]}" for cost in sorted(curve)))
    print(f"Energy sources: {sum(c.energy_source for c in card_set.cards)}")
    print(f"With keywords: {sum(bool(c.keywords) for c in card_set.cards)}")


if __name__ == "__main__":
    main()
