"""Card generation visualiser: one card's path through the grammar, animated for the blog.

    uv run --project PythonServer python Blog/card_generation_visualiser.py                  # Blog/build/card_generation_visualiser.html, opened
    uv run --project PythonServer python Blog/card_generation_visualiser.py --seed 94        # start on another card (the explorer's seeds)
    uv run --project PythonServer --with playwright python Blog/card_generation_visualiser.py --render   # also the .mp4

Run from the repository root. The card comes from the generator in PythonServer (via card_lab.py),
so this uses PythonServer's environment.

The page plays a timeline (2 s per decision) built from the card's derivation (src/cards/trace.py): every
decision the sampler made, its options and the one it took. It has a scrubber for checking the
timing. It starts on --seed and bakes in a pool of other cards for its "New card" button, so the
page needs no server. The card is drawn like the Unity client's, on its painted frame: web-sized copies of
the client's art (TCGClient/Assets/Art/Sprites) are in Blog/art and baked into the page. --render steps that timeline frame by frame in Chrome and joins the frames with ffmpeg,
so the video is smooth and the same every time.
"""
import argparse
import base64
import json
import random
import shutil
import subprocess
import webbrowser
from pathlib import Path

from card_lab import DEFAULTS, one, page  # next to this file; it puts PythonServer on the path
from src.cards.abilities import Renderer, render as card_text  # noqa: E402

TEMPLATE = Path(__file__).with_name("card_generation_visualiser.html")
OUT = Path(__file__).parent / "build"
ART = Path(__file__).with_name("art")  # card_frame.webp, card_frame_action.webp, card_art.webp
WIDTH, HEIGHT = 1920, 1080


def card_data(seed: int) -> dict:
    params = {k: v for k, v in DEFAULTS.items() if k not in ("seed", "count")}
    data = one(seed, **params)
    return {"seed": seed, "kept": data["kept"], "text_stages": text_stages(data["kept"])}


def pool_data(first: int, size: int) -> dict:
    """The first card, then `size` others at random: what the page's "New card" button picks from."""
    others = [s for s in random.Random(0).sample(range(1, 100_000), size + 1) if s != first][:size]
    return {"cards": [card_data(s) for s in [first, *others]]}


def text_stages(kept: dict) -> list[dict]:
    """The card text as the tree unfolds: each stage is shown once the decisions in its section
    (`after`, a path of trace sections) are made. Rendered from parts of the finished ability, so a
    stage only appears once that part can't change; "…" marks what is still to come."""
    a, card_type = kept["tree"], kept["card_type"]
    if not a:
        return []
    full = card_text(a, card_type)

    def lead(ability: dict) -> str:  # "Whenever …, if …": the text before the steps
        text = card_text(ability, card_type)
        return text[:len(text) - len(Renderer(card_type).steps(ability["steps"])) - 2]

    stages = []
    if a["kind"] == "triggered":
        stages.append({"after": ["ability", "trigger"], "text": lead({**a, "condition": None}) + ", …"})
        if a.get("condition"):
            stages.append({"after": ["ability", "condition"], "text": lead(a) + ", …"})
    steps = a.get("steps", [])
    if len(steps) == 1 and "choose_one" in steps[0]:  # each option as it's decided
        options = steps[0]["choose_one"]
        for k in range(1, len(options)):
            partial = card_text({**a, "steps": [{**steps[0], "choose_one": options[:k]}]}, card_type)
            stages.append({"after": ["ability", "steps", f"option {k}"], "text": partial + " …"})
    stages.append({"after": ["ability"], "text": full})
    return stages


def card_art() -> str:
    """The frame and art as data URIs, so the page stays one file."""
    uris = {f.stem: "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode() for f in sorted(ART.glob("*.webp"))}
    return f"<script>window.CARD_ART = {json.dumps(uris)};</script>"


def render(html: Path, video: Path, fps: int):
    """Steps the page's timeline with window.seek(t) and pipes a screenshot of each frame to ffmpeg."""
    from playwright.sync_api import sync_playwright  # only needed for --render

    if not shutil.which("ffmpeg"):
        raise SystemExit("--render needs ffmpeg on the PATH")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        tab = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        tab.goto(f"{html.resolve().as_uri()}?render=1")
        tab.wait_for_function("window.ready === true")
        duration = tab.evaluate("window.DURATION")
        frames = round(duration * fps)
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(video)], stdin=subprocess.PIPE)
        for i in range(frames + 1):
            tab.evaluate(f"window.seek({i / fps})")
            ffmpeg.stdin.write(tab.screenshot(type="png"))
            if i % fps == 0:
                print(f"\r{i / fps:4.1f} / {duration:.1f} s", end="", flush=True)
        ffmpeg.stdin.close()
        ffmpeg.wait()
        browser.close()
    print(f"\nWrote {video}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=112, help="the first card: the same seeds as the card explorer")
    parser.add_argument("--pool", type=int, default=50, help="other cards baked in for the New card button")
    parser.add_argument("--out", type=Path, default=OUT / "card_generation_visualiser.html")
    parser.add_argument("--render", action="store_true", help="also render the video next to the page (needs playwright)")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page(pool_data(args.seed, args.pool), TEMPLATE).replace("<!--CARD_ART-->", card_art()))
    print(f"Wrote {args.out}")
    if args.render:
        render(args.out, args.out.with_suffix(".mp4"), args.fps)
    elif not args.no_browser:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
