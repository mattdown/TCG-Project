"""Design loop: the series' loop as one animated panel for the blog.

Generate → Playtest → Measure → Tune. New cards from the grammar and tuned cards meet in the set that goes
into the next round's playtest: some rounds tuning fixes the cards in place, others need new cards.

    uv run --project PythonServer python Blog/design_loop.py          # Blog/build/design_loop.html, opened

Run from the repository root. The cards on it are real cards from cardsets/set_200.json (the ones with painted
art), drawn like the Unity client's; the network, the metrics' verdicts and the fixes are illustrations, not results.
The page plays on a loop with no controls, and holds still for readers who prefer reduced motion.
"""
import argparse
import webbrowser
from pathlib import Path

from card_generation_visualiser import OUT, set_cards  # next to this file; it puts PythonServer on the path
from card_lab import _attempt_json, bake

TEMPLATE = Path(__file__).with_name("design_loop.html")
FAN = (4, 2, 9)  # by number in set_200: Morel Scholar, Porcini Baker, Buttercup Colony
TUNED = 16  # Oyster Postman, whose cost changes in the Tune panel


def loop_data() -> dict:
    cards = set_cards(max(*FAN, TUNED))

    def card(number: int) -> dict:
        kept = _attempt_json(cards[number - 1])
        return {"kind": kept["kind"], "art": kept["card"]["art"], "card": kept["card"] | {"text": kept["text"]}}

    return {"fan": [card(n) for n in FAN], "tuned": card(TUNED)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT / "design_loop.html")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    data = loop_data()
    keys = {c["art"] for c in [*data["fan"], data["tuned"]]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(bake(TEMPLATE, data, keys))
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    if not args.no_browser:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
