"""Card art: prompts from a card set, images from Gemini, then small copies for the client.

Each card's prompt is a scene written for it (scenes.json: one concrete moment, like "sitting on
a lily pad ... looks proudly at a minnow it just caught") plus the style every card shares
(art_direction.STYLE). Art is named after what the card looks like, not its ID: the name,
subtitle and habitat ("porcini-baker--up-before-dawn--meadow"). A regenerated set reuses every
scene and image whose card it still has; only new cards need writing. Run from TCGClient/:

    uv run --project ../PythonServer --with google-genai --with pillow python Tools/card_art/card_art.py <command>

    prompts ../PythonServer/cardsets/set_200.json   → Tools/card_art/prompts/set_200.jsonl, and
                                                      set_200_briefs.json for cards with no scene yet
    models                                          → image models your key can use
    generate Tools/card_art/prompts/set_200.jsonl   → ArtSource/cards/<key>.png, skipping images that exist
    shrink                                          → Assets/Resources/CardArt/<key>.jpg for the build

`models` and `generate` need a Gemini API key of the art's own, in TCG_ART_GEMINI_KEY or
~/.config/tcg-art.key. They never use GEMINI_API_KEY, which may belong to another account.
"""
import argparse
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from art_direction import HABITATS, JOBS, SPECIES, STYLE

TOOL = Path(__file__).resolve().parent
CLIENT = TOOL.parents[1]
sys.path.insert(0, str(CLIENT.parent / "PythonServer"))
from src.cards.abilities import render  # noqa: E402
from src.cards.art import art_key as _art_key  # noqa: E402

SCENES = TOOL / "scenes.json"  # art key → scene, kept across card sets
RAW = CLIENT / "ArtSource" / "cards"  # outside Assets, so Unity doesn't import the full-size images
BUILD = CLIENT / "Assets" / "Resources" / "CardArt"  # loaded by name: CardView
DEFAULT_MODEL = "gemini-3.1-flash-image"  # Nano Banana 2; gemini-3-pro-image is the pricier Pro
KEY_VAR = "TCG_ART_GEMINI_KEY"
KEY_FILE = Path.home() / ".config" / "tcg-art.key"


def art_key(card: dict) -> str:
    """The image a card uses (src/cards/art.py): the server sends the same key in card_set."""
    return _art_key(card["name"], card.get("subtitle", ""), card["aspects"])


def _aspect(card: dict) -> str:
    return card["aspects"][0] if card["aspects"] else ""


def prompt_for(card: dict, scene: str) -> str:
    return f"{scene} {STYLE.format(glow=HABITATS[_aspect(card)][1])}"


def brief_for(card: dict) -> dict:
    """What a scene writer needs: the look, the job, the setting and what the card does."""
    brief = {"key": art_key(card), "type": card["type"], "name": card["name"], "subtitle": card.get("subtitle", ""),
             "habitat": HABITATS[_aspect(card)][0], "text": " ".join(render(a, card["type"]) for a in card["abilities"]),
             "keywords": card["keywords"]}
    if card["type"] == "unit" and card["traits"]:
        job = card["traits"][0]
        brief |= {"species_look": SPECIES.get(card["name"].removesuffix(f" {job}"), ""), "job_props": JOBS.get(job, "")}
    return brief


def cmd_prompts(args):
    card_set = json.loads(Path(args.cardset).read_text())
    scenes = json.loads(SCENES.read_text()) if SCENES.exists() else {}
    entries, briefs = {}, {}
    for card in card_set["cards"]:
        key = art_key(card)
        if key in scenes:
            entries.setdefault(key, {"key": key, "cards": [], "prompt": prompt_for(card, scenes[key])})["cards"].append(card["id"])
        else:
            briefs.setdefault(key, brief_for(card))
    out = Path(args.out) if args.out else TOOL / "prompts" / f"{card_set['name']}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(e) + "\n" for e in entries.values()))
    have = sum((RAW / f"{k}.png").exists() for k in entries)
    print(f"{len(entries)} prompts → {out} ({have} already have art)")
    brief_path = out.with_name(f"{card_set['name']}_briefs.json")
    if briefs:
        brief_path.write_text(json.dumps(list(briefs.values()), indent=1))
        print(f"{len(briefs)} cards have no scene yet: briefs in {brief_path}; add their scenes to {SCENES.name}")
    else:
        brief_path.unlink(missing_ok=True)


def _client():
    """A client on the art key only, never GEMINI_API_KEY: that one may be a work key set for everything."""
    from google import genai
    key = os.environ.get(KEY_VAR, "").strip() or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not key:
        sys.exit(f"No art key: set {KEY_VAR} or put the key in {KEY_FILE}.")
    if key == os.environ.get("GEMINI_API_KEY", "").strip():
        sys.exit("The art key is the same as GEMINI_API_KEY; use a separate key for card art.")
    return genai.Client(api_key=key)


def cmd_models(args):
    client = _client()  # held, so it isn't closed while the pager is still fetching
    for m in client.models.list():
        if "image" in m.name:
            print(m.name, "-", m.display_name)


def cmd_generate(args):
    from google.genai import types
    from PIL import Image

    entries = [json.loads(line) for line in Path(args.prompts).read_text().splitlines() if line.strip()]
    if args.only:
        entries = [e for e in entries if e["key"] in args.only]
    todo = [e for e in entries if args.force or not (RAW / f"{e['key']}.png").exists()]
    done = len(entries) - len(todo)
    todo = todo[:args.limit] if args.limit else todo
    print(f"{done} of {len(entries)} done, generating {len(todo)} with {args.model}")
    if not todo:
        return
    client = _client()
    RAW.mkdir(parents=True, exist_ok=True)
    config = types.GenerateContentConfig(response_modalities=["IMAGE"],
                                         image_config=types.ImageConfig(aspect_ratio="4:5"))

    def one(entry):
        response = client.models.generate_content(model=args.model, contents=entry["prompt"], config=config)
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                Image.open(io.BytesIO(part.inline_data.data)).save(RAW / f"{entry['key']}.png")
                return
        raise RuntimeError(f"no image returned ({response.candidates[0].finish_reason})")

    failed = []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(one, e): e["key"] for e in todo}
        for i, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try:
                future.result()
                print(f"[{i}/{len(todo)}] {key}", flush=True)
            except Exception as e:  # keep going: a refused prompt shouldn't stop the batch
                failed.append(key)
                code = getattr(e, "code", None)
                print(f"[{i}/{len(todo)}] {key} FAILED: {code or ''} {getattr(e, 'status', '') or str(e)[:200]}", flush=True)
                if code in (401, 403, 429):  # the key or its quota, not this prompt: the rest would fail too
                    pool.shutdown(cancel_futures=True)
                    hint = ("Wait a few minutes or use fewer --workers: new billing accounts have a low spend rate."
                            if code == 429 else "Check the key and that its project has billing on (aistudio.google.com/apikey).")
                    sys.exit(f"Stopped: {str(e)[:300]}\n{hint}")
    if failed:
        print(f"{len(failed)} failed; run again to retry them: {' '.join(failed)}")


def cmd_shrink(args):
    from PIL import Image, ImageOps

    BUILD.mkdir(parents=True, exist_ok=True)
    size = (args.width, args.width * 5 // 4)
    made = 0
    for src in sorted(RAW.glob("*.png")):
        dst = BUILD / f"{src.stem}.jpg"
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            continue
        image = ImageOps.fit(Image.open(src).convert("RGB"), size, Image.LANCZOS)  # crops if the model ignored 4:5
        image.save(dst, quality=88, optimize=True)
        made += 1
    print(f"{made} images written to {BUILD} at {size[0]}x{size[1]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(required=True)
    p = commands.add_parser("prompts", help="write one prompt per card art, and briefs for cards with no scene")
    p.add_argument("cardset")
    p.add_argument("--out")
    p.set_defaults(run=cmd_prompts)
    p = commands.add_parser("models", help="list image models")
    p.set_defaults(run=cmd_models)
    p = commands.add_parser("generate", help="generate missing art")
    p.add_argument("prompts")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--limit", type=int, help="at most this many images, to check a few first")
    p.add_argument("--only", nargs="+", help="just these keys")
    p.add_argument("--force", action="store_true", help="redo images that exist")
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(run=cmd_generate)
    p = commands.add_parser("shrink", help="downsize art for the build")
    p.add_argument("--width", type=int, default=640)
    p.set_defaults(run=cmd_shrink)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
