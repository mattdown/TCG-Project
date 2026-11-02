"""Card generation visualiser: one card's path through the grammar, animated for the blog.

    uv run --project PythonServer python Blog/card_generation_visualiser.py                  # Blog/build/card_generation_visualiser.html, opened
    uv run --project PythonServer python Blog/card_generation_visualiser.py --card 94        # start on another card of the set
    uv run --project PythonServer --with playwright python Blog/card_generation_visualiser.py --render   # also the .mp4
    uv run --project PythonServer --with pillow python Blog/card_generation_visualiser.py --refresh-art  # re-shrink the art first

Run from the repository root. The cards come from the generator in PythonServer (via card_lab.py),
so this uses PythonServer's environment.

The cards are the first --count (200) of cardsets/set_200.json, generated again here with the same
seed and settings so each comes with its derivation (src/cards/trace.py): every decision the sampler
made, its options and the one it took. Those are the cards with painted art. The page plays a
timeline (2 s per decision) with a scrubber for checking the timing; it starts on --card and its
"New card" button picks from the rest, so the page needs no server.

The card is drawn like the Unity client's (ClientAssetBuilder.BuildCardPrefab): the plain painted frame,
the sword and shield badges, the job banner and the card's own art. Web-sized copies of the client's
images are kept in Blog/art (frame and parts) and Blog/art/cards (one per art key, 320x400) and baked
into the page; --refresh-art makes them again from TCGClient. --render steps the timeline frame by
frame in Chrome and joins the frames with ffmpeg, so the video is smooth and the same every time.
"""
import argparse
import base64
import json
import shutil
import subprocess
import webbrowser
from pathlib import Path

from card_lab import DEFAULTS, _attempt_json, make_generator, page  # next to this file; it puts PythonServer on the path
from src.cards.abilities import Renderer, render as card_text  # noqa: E402
from src.cards.art import art_key  # noqa: E402
from src.cards.generate import Attempt  # noqa: E402

TEMPLATE = Path(__file__).with_name("card_generation_visualiser.html")
PAINTED_CARD = Path(__file__).with_name("painted_card.html")  # the client's card, shared with gnn_visualiser
OUT = Path(__file__).parent / "build"
ART = Path(__file__).with_name("art")  # the frame, its parts and the background; cards/ has each card's art
CLIENT = Path(__file__).parents[1] / "TCGClient"
SET_SEED, SET_SIZE = 0, 200  # cardsets/set_200.json, the set the card art was painted for
WIDTH, HEIGHT = 1920, 1080

# Blog/art name → (client image, width on the web): about twice the size they are shown at.
PARTS = {"card_frame": ("Assets/Art/Sprites/card_frame_action.png", 840),
         "card_attack": ("Assets/Art/Sprites/card_attack.png", 240),
         "card_defence": ("Assets/Art/Sprites/card_defence.png", 180),
         "card_job_banner": ("Assets/Art/Sprites/card_job_banner.png", 540),
         "background": ("Assets/Art/Sprites/game_background.jpeg", 1920),
         "hero_you": ("Assets/Art/Sprites/hero_you.png", 460),
         "hero_opponent": ("Assets/Art/Sprites/hero_opponent.png", 460)}
CARD_ART_SIZE = (320, 400)  # the client's CardArt is 640x800; the art window is about 270 px wide on the page


def set_cards(count: int) -> list[Attempt]:
    """The first `count` cards of the set, each with its trace (the same cards as generate_card_set)."""
    params = {k: v for k, v in DEFAULTS.items() if k not in ("seed", "count")}
    _, generator = make_generator(SET_SEED, **params)
    return [generator.card() for _ in range(count)]


def card_data(number: int, a: Attempt) -> dict:
    kept = _attempt_json(a, trace=True)
    return {"number": number, "art": art_key(a.card.name, a.card.subtitle, a.card.aspects), "kept": kept,
            "text_stages": text_stages(kept)}


def pool_data(count: int = SET_SIZE) -> dict:
    """Every card the page can show, numbered as in the set (S1-001 is 1)."""
    return {"cards": [card_data(n, a) for n, a in enumerate(set_cards(count), 1)]}


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


def refresh_art(keys: set[str]):
    """Shrink the client's frame, parts and each card's art into Blog/art (needs Pillow)."""
    from PIL import Image

    (ART / "cards").mkdir(parents=True, exist_ok=True)
    for name, (source, width) in PARTS.items():
        image = Image.open(CLIENT / source)
        image.thumbnail((width, width * 4), Image.LANCZOS)
        image.save(ART / f"{name}.webp", quality=82 if image.mode == "RGBA" else 70, method=6)
    missing = []
    for key in sorted(keys):
        source = CLIENT / "Assets" / "Resources" / "CardArt" / f"{key}.jpg"
        if not source.exists():
            missing.append(key)
            continue
        image = Image.open(source).convert("RGB")
        image.thumbnail(CARD_ART_SIZE, Image.LANCZOS)
        image.save(ART / "cards" / f"{key}.webp", quality=72, method=6)
    print(f"Wrote {len(PARTS)} parts and {len(keys) - len(missing)} card images to {ART}"
          + (f"; no art yet for {len(missing)}: {', '.join(missing)}" if missing else ""))


def card_art(keys: set[str]) -> str:
    """The frame, parts and the cards' art as data URIs, so the page stays one file. A card without
    art shows an empty window."""
    uri = lambda f: "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()
    parts = {f.stem: uri(f) for f in sorted(ART.glob("*.webp"))}
    cards = {k: uri(ART / "cards" / f"{k}.webp") for k in sorted(keys) if (ART / "cards" / f"{k}.webp").exists()}
    return f"<script>window.CARD_ART = {json.dumps(parts)};\nwindow.CARD_IMAGES = {json.dumps(cards)};</script>"


def bake(template: Path, data: dict, keys: set[str]) -> str:
    """A page as one file: the card kit, the painted card, the images for these art keys and the data."""
    html = page(data, template).replace("<!--PAINTED_CARD-->", PAINTED_CARD.read_text())
    return html.replace("<!--CARD_ART-->", card_art(keys))


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
    parser.add_argument("--card", type=int, default=2, help="the first card, by its number in the set (1 is S1-001)")
    parser.add_argument("--count", type=int, default=SET_SIZE, help="cards the New card button picks from: the set's first N")
    parser.add_argument("--out", type=Path, default=OUT / "card_generation_visualiser.html")
    parser.add_argument("--refresh-art", action="store_true", help="shrink the client's art into Blog/art first (needs pillow)")
    parser.add_argument("--render", action="store_true", help="also render the video next to the page (needs playwright)")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    data = pool_data(args.count)
    data["first"] = max(1, min(args.card, args.count))
    keys = {c["art"] for c in data["cards"]}
    if args.refresh_art:
        refresh_art(keys)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(bake(TEMPLATE, data, keys))
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB, {len(data['cards'])} cards)")
    if args.render:
        render(args.out, args.out.with_suffix(".mp4"), args.fps)
    elif not args.no_browser:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
