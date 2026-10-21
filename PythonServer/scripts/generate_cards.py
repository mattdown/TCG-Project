"""Generates a card set: units with keywords (default), stats only, a full set (vanilla, keyword-only
and ability cards in set shares), or a coverage set that uses every building block of the ability
grammar. The set and coverage kinds also write a Markdown checklist next to the JSON."""
import argparse
from collections import Counter
from pathlib import Path

from src.cards.schema import save_card_set
from src.cards.coverage import card_set_report, coverage_report, generate_coverage_set
from src.cards.generate import generate_card_set
from src.cards.vanilla import generate_keyword_set, generate_vanilla_set
from src.paths import CARDSET_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("keywords", "vanilla", "set", "coverage"), default="keywords")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--vanilla-share", type=float, default=0.04, help="--kind set: share of stats-only units")
    parser.add_argument("--keyword-share", type=float, default=0.25, help="--kind set: share of keyword-only units")
    parser.add_argument("--action-share", type=float, default=0.25, help="--kind set: share of action cards")
    parser.add_argument("--out", type=Path, default=None, help="defaults to cardsets/<kind>_<count>.json")
    args = parser.parse_args()

    if args.kind == "coverage":
        card_set = generate_coverage_set(args.seed)
    elif args.kind == "set":
        card_set = generate_card_set(args.count, args.seed, vanilla_share=args.vanilla_share,
                                     keyword_share=args.keyword_share, action_share=args.action_share)
    else:
        generate = generate_keyword_set if args.kind == "keywords" else generate_vanilla_set
        card_set = generate(args.count, args.seed)
    out = args.out or CARDSET_PATH.parent / f"{card_set.name}.json"
    save_card_set(card_set, out)
    if args.kind in ("coverage", "set"):
        report = coverage_report if args.kind == "coverage" else card_set_report
        out.with_suffix(".md").write_text(report(card_set))
        print(f"Checklist: {out.with_suffix('.md')}")
    curve = Counter(c.cost for c in card_set.cards)
    print(f"Wrote {len(card_set)} cards to {out}")
    print("Cost curve: " + ", ".join(f"{cost}: {curve[cost]}" for cost in sorted(curve)))
    print(f"With keywords: {sum(bool(c.keywords) for c in card_set.cards)}")


if __name__ == "__main__":
    main()
