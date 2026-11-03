"""Card lab: generate cards from the ability grammar and see every stage, including what was thrown away.

    uv run --project PythonServer python Blog/card_lab.py                      # web page at http://localhost:8765
    uv run --project PythonServer python Blog/card_lab.py --text --count 50    # the same in the terminal
    uv run --project PythonServer python Blog/card_lab.py --export lab.html    # a self-contained page, no server needed

Run from the repository root: the cards come from the generator in PythonServer, so this uses its environment.

The page has the Lantern look and draws cards like the Unity client (painted_card.html). The default seed, 0,
gives the first cards of cardsets/set_200.json, which have painted art (Blog/art/cards); other cards get a
placeholder mushroom in their aspect's colour.

One card's path through the grammar, animated, is card_generation_visualiser.py.

The pipeline is described in docs/ability-generation.md.
"""
import argparse
import base64
import json
import random
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parents[1] / "PythonServer"))
from src.cards.abilities import validate  # noqa: E402
from src.cards.art import art_key  # noqa: E402
from src.cards.generate import STAGES, Attempt, CardGenerator  # noqa: E402
from src.cards.quality import (ACTION_COMPLEXITY, MAX_COMPLEXITY, MAX_NARROWING, complexity,  # noqa: E402
                                disconnected_steps, dominated_options, narrowing, skeleton)
from src.cards.theme import JOBS  # noqa: E402
from src.cards.trace import decisions, path_probability  # noqa: E402
from src.game.terms import ASPECT_NAMES, keyword_text  # noqa: E402

PAGE = Path(__file__).with_name("card_lab.html")
CARD_KIT = Path(__file__).with_name("card_kit.html")  # card text helpers, shared by every page
PAINTED_CARD = Path(__file__).with_name("painted_card.html")  # the client's card
ART = Path(__file__).with_name("art")  # the frame, its parts and the background; cards/ has each card's art
DEFAULTS = {"seed": 0, "count": 60, "jobs": 6, "action_share": 0.25, "vanilla_share": 0.04, "keyword_share": 0.25,
            "variety": 4}


def _checks(a: Attempt) -> list[dict]:
    """Every test's verdict, so the page can show the whole pipeline for one draw."""
    if a.ability is None:  # vanilla and keyword-only units
        return [{"test": "card", "name": "Fits a card",
                 "problems": a.problems if a.stopped_at == "card" else []},
                {"test": "duplicate", "name": "Not a duplicate",
                 "problems": a.problems if a.stopped_at == "duplicate" else []}] if a.stopped_at != "card" else \
               [{"test": "card", "name": "Fits a card", "problems": a.problems}]
    grammar = validate(a.ability, a.card_type)
    size = complexity(a.ability)
    budget = MAX_COMPLEXITY + (ACTION_COMPLEXITY if a.card_type == "action" else 0)
    narrow = narrowing(a.ability)
    steps = a.ability.get("steps", [])
    checks = [
        {"test": "grammar", "name": "Legal under the grammar", "problems": grammar},
        {"test": "complexity", "name": f"Complexity {size} of {budget}",
         "problems": [f"{size} nodes is over the budget of {budget}"] if size > budget else []},
        {"test": "narrowing", "name": f"Narrowing {narrow} of {MAX_NARROWING}",
         "problems": [f"{narrow} conditions or restrictions is over the budget of {MAX_NARROWING}"]
         if narrow > MAX_NARROWING else []},
        {"test": "connected", "name": "Steps connected", "problems": disconnected_steps(steps)},
        {"test": "dominated", "name": "No dominated options", "problems": dominated_options(a.ability)},
    ]
    if a.card is not None or a.stopped_at == "card":
        checks.append({"test": "card", "name": "Can matter on this card, worth a card",
                       "problems": a.problems if a.stopped_at == "card" else []})
    if a.stopped_at == "variety" or a.card is not None:
        checks.append({"test": "variety", "name": "Adds variety",
                       "problems": a.problems if a.stopped_at == "variety" else []})
    return checks


def _attempt_json(a: Attempt, trace: bool = False) -> dict:
    c = a.card
    card = None if c is None else {
        "name": c.name, "subtitle": c.subtitle, "type": c.type, "cost": c.cost, "power": c.power, "health": c.health,
        "aspect": c.aspects[0] if c.aspects else None,
        "aspect_name": ASPECT_NAMES[c.aspects[0]] if c.aspects else "Neutral",
        "traits": list(c.traits), "keywords": [keyword_text(k, v) for k, v in c.keywords], "archetype": a.archetype,
        "art": art_key(c.name, c.subtitle, c.aspects),
    }
    kind = a.ability["kind"] if a.ability else a.kind  # triggered, static, … or vanilla, keywords
    shape = skeleton(a.ability, abstract_traits=True) if a.ability else json.dumps(a.kind)
    return {"index": a.index, "card_type": a.card_type, "kind": kind, "text": a.text if a.ability else "",
            "complexity": a.complexity, "value": a.value, "stopped_at": a.stopped_at, "problems": a.problems,
            "checks": _checks(a), "tree": a.ability, "card": card, "shape": shape} | \
        (_trace_json(a.trace) if trace else {})


def _trace_json(root: dict) -> dict:
    ability = next((c for c in root["children"] if c.get("section") == "ability"), None)
    if ability is None:  # no ability: the odds are the whole card's
        return {"trace": root, "has_ability": False, "ability_p": path_probability(root),
                "ability_decisions": decisions(root), "decisions": decisions(root)}
    return {"trace": root, "has_ability": True, "ability_p": path_probability(ability),
            "ability_decisions": decisions(ability), "decisions": decisions(root)}


def make_generator(seed: int, jobs: int, action_share: float, vanilla_share: float, keyword_share: float,
                   variety: int) -> tuple[tuple[str, ...], CardGenerator]:
    """Set up exactly as generate_card_set does, so the same seed gives the same cards as a saved set."""
    rng = random.Random(seed)
    job_list = tuple(rng.sample(JOBS, min(jobs, len(JOBS))))
    return job_list, CardGenerator(rng, job_list, action_share=action_share, variety=variety,
                                   vanilla_share=vanilla_share, keyword_share=keyword_share)


def run(seed: int, count: int, jobs: int, action_share: float, vanilla_share: float, keyword_share: float,
        variety: int) -> dict:
    job_list, generator = make_generator(seed, jobs, action_share, vanilla_share, keyword_share, variety)
    kept = [generator.card().index for _ in range(count)]
    return {"params": {"seed": seed, "count": count, "jobs": jobs, "action_share": action_share,
                       "vanilla_share": vanilla_share, "keyword_share": keyword_share, "variety": variety},
            "job_list": list(job_list), "stages": list(STAGES), "max_complexity": MAX_COMPLEXITY,
            "kept": kept, "attempts": [_attempt_json(a) for a in generator.attempts]}


def print_text(data: dict, rejected: bool):
    by_index = {a["index"]: a for a in data["attempts"]}
    for n, i in enumerate(data["kept"], 1):
        a = by_index[i]
        c = a["card"]
        stats = "" if c["type"] == "action" else f" {c["power"]}/{c["health"]},"
        keywords = "".join(f" {k}." for k in c["keywords"])
        name = f"{c['name']} – {c['subtitle']}" if c["subtitle"] else c["name"]
        print(f"{n:3d}. {name} [{c['type']}, cost {c['cost']},{stats} {a['kind']}, {c['aspect_name']}]{keywords} {a['text']}")
    stopped = [a for a in data["attempts"] if a["stopped_at"]]
    print(f"\n{len(data['attempts'])} draws, {len(data['kept'])} kept. Stopped at: "
          + ", ".join(f"{s} {sum(a['stopped_at'] == s for a in stopped)}" for s in data["stages"]))
    if rejected:
        for a in stopped:
            print(f"  ✗ {a['stopped_at']}: {a['text']}\n      {'; '.join(a['problems'])}")


def page(data: dict | None, source: Path = PAGE) -> str:
    html = source.read_text().replace("<!--CARD_KIT-->", CARD_KIT.read_text())
    if data is not None:
        payload = json.dumps(data).replace("</", "<\\/")
        html = html.replace("<!--LAB_DATA-->", f"<script>window.LAB_DATA = {payload};</script>")
    return html


def card_art(keys: set[str] | None, inline: bool = True) -> str:
    """The frame, parts and the cards' art (these keys, or all of it), as data URIs so a page stays one
    file, or as /art/ URLs for the lab's server. A card without art gets no entry."""
    def src(f: Path) -> str:
        if not inline:
            return "/" + f.relative_to(ART.parent).as_posix()
        return "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()
    parts = {f.stem: src(f) for f in sorted(ART.glob("*.webp"))}
    files = sorted((ART / "cards").glob("*.webp")) if keys is None else \
        [f for k in sorted(keys) if (f := ART / "cards" / f"{k}.webp").exists()]
    cards = {f.stem: src(f) for f in files}
    return f"<script>window.CARD_ART = {json.dumps(parts)};\nwindow.CARD_IMAGES = {json.dumps(cards)};</script>"


def bake(template: Path, data: dict | None, keys: set[str] | None, inline: bool = True) -> str:
    """A page with the card kit, the painted card, the images for these art keys and the data."""
    html = page(data, template).replace("<!--PAINTED_CARD-->", PAINTED_CARD.read_text())
    return html.replace("<!--CARD_ART-->", card_art(keys, inline))


def art_keys(data: dict) -> set[str]:
    return {a["card"]["art"] for a in data["attempts"] if a["card"]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, "text/html; charset=utf-8", bake(PAGE, None, None, inline=False))
        elif url.path.startswith("/art/") and ".." not in url.path and (ART.parent / url.path[1:]).is_file():
            self._send(200, "image/webp", (ART.parent / url.path[1:]).read_bytes())
        elif url.path == "/api/generate":
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                params = {k: type(d)(query.get(k, d)) for k, d in DEFAULTS.items()}
                params["count"] = max(1, min(params["count"], 500))
                params["variety"] = max(1, min(params["variety"], 16))
                self._send(200, "application/json", json.dumps(run(**params)))
            except ValueError as e:
                self._send(400, "application/json", json.dumps({"error": str(e)}))
        else:
            self._send(404, "text/plain", "not found")

    def _send(self, status: int, content_type: str, body: str | bytes):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name, default in DEFAULTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=type(default), default=default)
    parser.add_argument("--text", action="store_true", help="print to the terminal instead of serving the page")
    parser.add_argument("--rejected", action="store_true", help="with --text, also list the draws that were stopped")
    parser.add_argument("--export", type=Path, help="write a self-contained page with this batch baked in")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    params = {k: getattr(args, k) for k in DEFAULTS}

    if args.text:
        print_text(run(**params), args.rejected)
    elif args.export:
        data = run(**params)
        args.export.write_text(bake(PAGE, data, art_keys(data)))
        print(f"Wrote {args.export}")
    else:
        url = f"http://localhost:{args.port}/"
        server = ThreadingHTTPServer(("localhost", args.port), Handler)
        print(f"Card lab at {url} (Ctrl+C to stop)")
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
