"""Card explorer: every card of a generated set, drawn like the client's, with filters by class.

    uv run --project PythonServer python Blog/card_explorer.py                  # set_1000_c → Blog/build/card_explorer.html
    uv run --project PythonServer python Blog/card_explorer.py --cards PythonServer/data/price_loop/set_1000_c_v7c_best/set_1000_c.json \
        --before PythonServer/cardsets/set_1000_c.json                          # a repriced set, with what changed

Run from the repository root. The page is one self-contained file (cards and any painted art baked in). Filters:
class (each with its two play styles on the ring), card type, cost, ability kind, price group, job and keyword,
and a text search; tap a card for its details and ability tree. With --before, each card also shows its cost and
stats in that set, and a filter keeps only the cards that changed.

The card lab (card_lab.py) shows how cards are generated; this shows what a finished set holds.
"""
import argparse
import webbrowser
from collections import Counter
from pathlib import Path

from card_lab import bake, describe  # card_lab puts PythonServer on sys.path
from src.cards.abilities import render  # noqa: E402
from src.cards.art import art_key  # noqa: E402
from src.cards.classes import CLASSES  # noqa: E402
from src.cards.costing import price_group  # noqa: E402
from src.cards.schema import Card, CardSet, load_card_set  # noqa: E402
from src.game.terms import ASPECT_NAMES, ASPECTS, keyword_text  # noqa: E402

ROOT = Path(__file__).parents[1]
PAGE = Path(__file__).with_name("card_explorer.html")
DEFAULT_CARDS = ROOT / "PythonServer" / "cardsets" / "set_1000_c.json"
OUT = Path(__file__).parent / "build" / "card_explorer.html"


def kind_of(card: Card) -> str:
    if card.abilities:
        return card.abilities[0]["kind"]
    return "keywords" if card.keywords else "vanilla"


def card_json(card: Card, before: Card | None = None) -> dict:
    ability = card.abilities[0] if card.abilities else None
    aspect = card.aspects[0] if card.aspects else None
    out = {"id": card.id, "name": card.name, "subtitle": card.subtitle, "type": card.type, "cost": card.cost,
           "power": card.power, "health": card.health, "aspect": aspect,
           "traits": list(card.traits), "keywords": [keyword_text(k, v) for k, v in card.keywords],
           "keyword_names": [k for k, _ in card.keywords], "kind": kind_of(card),
           "text": render(ability, card.type) if ability else "",
           "group": price_group(ability, card.type) if ability else f"{card.type}, {kind_of(card)}",
           "tree": ability, "art": art_key(card.name, card.subtitle, card.aspects)}
    if before is not None and (before.cost, before.power, before.health) != (card.cost, card.power, card.health):
        out["before"] = {"cost": before.cost, "power": before.power, "health": before.health}
    return out


def label(path: Path) -> str:
    path = path.resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name


def explorer_data(card_set: CardSet, before: CardSet | None = None, source: str | None = None,
                  before_source: str | None = None) -> dict:
    old = {c.id: c for c in before.cards} if before else {}
    cards = [card_json(c, old.get(c.id)) for c in card_set.cards]
    classes = [{"aspect": a, "name": ASPECT_NAMES[a], "styles": list(CLASSES.get(a, ()))} for a in ASPECTS]
    return {"name": card_set.name, "source": source or card_set.name,
            "before": (before_source or before.name) if before else None, "cards": cards, "classes": classes,
            "jobs": sorted({t for c in cards for t in c["traits"]}),
            "groups": [g for g, _ in Counter(c["group"] for c in cards).most_common()]}


def summary(data: dict) -> tuple[str, str]:
    n = len(data["cards"])
    return f"Card Explorer: {data['name']}", (
        f"All {n} cards of {data['name']}, a generated set for an original trading card game: mushrooms with jobs, "
        "in six classes (habitats) and neutral cards. Filter by class, type, cost, ability kind, job and keyword.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cards", type=Path, default=DEFAULT_CARDS)
    parser.add_argument("--before", type=Path, help="the same set at other prices, to show what changed")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    card_set = load_card_set(args.cards)
    data = explorer_data(card_set, load_card_set(args.before) if args.before else None, label(args.cards),
                         label(args.before) if args.before else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(describe(bake(PAGE, data, {c["art"] for c in data["cards"]}), *summary(data)))
    print(f"Wrote {args.out} ({len(data['cards'])} cards)")
    if not args.no_browser:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
