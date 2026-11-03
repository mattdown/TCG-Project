"""Thumbnail for blog part 1: three of set_200's cards with a graph over them, as a 1200x630 JPEG.

    uv run --project PythonServer --with playwright python Blog/thumbnail.py     # Blog/build/tcg_part1_thumbnail.jpg

Run from the repository root. The page (thumbnail.html) is baked like the other Blog pages, then Chrome takes a
screenshot of it. 1200x630 is the usual size for a shared link's image; the site's posts list crops it to 4:3,
so the cards and the graph sit in the middle of it.
"""
import argparse
from pathlib import Path

from card_generation_visualiser import OUT  # next to this file; it puts PythonServer on the path
from card_lab import bake
from design_loop import loop_data

TEMPLATE = Path(__file__).with_name("thumbnail.html")
WIDTH, HEIGHT = 1200, 630


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT / "tcg_part1_thumbnail.jpg")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # only needed here

    data = {"fan": loop_data()["fan"]}
    page = args.out.with_suffix(".html")
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(bake(TEMPLATE, data, {c["art"] for c in data["fan"]}))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        tab = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        tab.goto(page.resolve().as_uri())
        tab.wait_for_function("window.ready === true")
        tab.screenshot(path=str(args.out), type="jpeg", quality=88)
        browser.close()
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
