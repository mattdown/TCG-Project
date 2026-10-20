"""Card lab: generate cards from the ability grammar and see every stage, including what was thrown away.

    uv run python -m scripts.card_lab                      # web page at http://localhost:8765
    uv run python -m scripts.card_lab --text --count 50    # the same in the terminal
    uv run python -m scripts.card_lab --export lab.html    # a self-contained page, no server needed

The pipeline is described in docs/ability-generation.md.
"""
import argparse
import json
import random
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.cards.abilities import validate
from src.cards.generate import STAGES, Attempt, CardGenerator
from src.cards.quality import MAX_COMPLEXITY, complexity, disconnected_steps, dominated_options, skeleton
from src.cards.theme import JOBS
from src.game.terms import ASPECT_NAMES, keyword_text

PAGE = Path(__file__).with_name("card_lab.html")
DEFAULTS = {"seed": 1, "count": 60, "jobs": 6, "action_share": 0.25, "variety": 4}


def _checks(a: Attempt) -> list[dict]:
    """Every test's verdict, so the page can show the whole pipeline for one draw."""
    grammar = validate(a.ability, a.card_type)
    size = complexity(a.ability)
    steps = a.ability.get("steps", [])
    checks = [
        {"test": "grammar", "name": "Legal under the grammar", "problems": grammar},
        {"test": "complexity", "name": f"Complexity {size} of {MAX_COMPLEXITY}",
         "problems": [f"{size} nodes is over the budget of {MAX_COMPLEXITY}"] if size > MAX_COMPLEXITY else []},
        {"test": "connected", "name": "Steps connected", "problems": disconnected_steps(steps)},
        {"test": "dominated", "name": "No dominated options", "problems": dominated_options(a.ability)},
    ]
    if a.card is not None or a.stopped_at == "card":
        checks.append({"test": "card", "name": "Can matter on this card",
                       "problems": a.problems if a.stopped_at == "card" else []})
    if a.stopped_at == "variety" or a.card is not None:
        checks.append({"test": "variety", "name": "Adds variety",
                       "problems": a.problems if a.stopped_at == "variety" else []})
    return checks


def _attempt_json(a: Attempt) -> dict:
    c = a.card
    card = None if c is None else {
        "name": c.name, "type": c.type, "cost": c.cost, "power": c.power, "health": c.health, "score": c.score,
        "aspect": c.aspects[0], "aspect_name": ASPECT_NAMES[c.aspects[0]], "energy_source": c.energy_source,
        "traits": list(c.traits), "keywords": [keyword_text(k, v) for k, v in c.keywords], "archetype": a.archetype,
    }
    return {"index": a.index, "card_type": a.card_type, "kind": a.ability["kind"], "text": a.text,
            "complexity": a.complexity, "value": a.value, "stopped_at": a.stopped_at, "problems": a.problems,
            "checks": _checks(a), "tree": a.ability, "card": card,
            "shape": skeleton(a.ability, abstract_traits=True)}


def run(seed: int, count: int, jobs: int, action_share: float, variety: int) -> dict:
    rng = random.Random(seed)
    job_list = tuple(rng.sample(JOBS, min(jobs, len(JOBS))))
    generator = CardGenerator(rng, job_list, action_share=action_share, variety=variety)
    kept = [generator.card().index for _ in range(count)]
    return {"params": {"seed": seed, "count": count, "jobs": jobs, "action_share": action_share, "variety": variety},
            "job_list": list(job_list), "stages": list(STAGES), "max_complexity": MAX_COMPLEXITY,
            "kept": kept, "attempts": [_attempt_json(a) for a in generator.attempts]}


def print_text(data: dict, rejected: bool):
    by_index = {a["index"]: a for a in data["attempts"]}
    for n, i in enumerate(data["kept"], 1):
        a = by_index[i]
        c = a["card"]
        stats = "" if c["type"] == "action" else f" {c['power']}/{c['health']}, {c['score']} VP,"
        keywords = "".join(f" {k}." for k in c["keywords"])
        print(f"{n:3d}. {c['name']} [{c['type']}, cost {c['cost']},{stats} {a['kind']}]{keywords} {a['text']}")
    stopped = [a for a in data["attempts"] if a["stopped_at"]]
    print(f"\n{len(data['attempts'])} draws, {len(data['kept'])} kept. Stopped at: "
          + ", ".join(f"{s} {sum(a['stopped_at'] == s for a in stopped)}" for s in data["stages"]))
    if rejected:
        for a in stopped:
            print(f"  ✗ {a['stopped_at']}: {a['text']}\n      {'; '.join(a['problems'])}")


def page(data: dict | None) -> str:
    html = PAGE.read_text()
    if data is not None:
        payload = json.dumps(data).replace("</", "<\\/")
        html = html.replace("<!--LAB_DATA-->", f"<script>window.LAB_DATA = {payload};</script>")
    return html


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, "text/html; charset=utf-8", page(None))
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

    def _send(self, status: int, content_type: str, body: str):
        data = body.encode()
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
        args.export.write_text(page(run(**params)))
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
