"""ZeroMQ game server for the Unity client: JSON requests in, JSON responses out.

See src/server/session.py for the request types.

    uv run python -m scripts.server --cards cardsets/set_1000_c.json --model models/tcgnet_v7c_best.pt \
        --elites data/elites/set_1000_c_share.json

--elites offers each class's best deck: the one the smoothed equilibrium of the archive's metagame
table (--metagame; by default data/metagame/<archive>.<model>.json or <archive>.heuristic.json, if
there is one) plays most, or else the class's fittest elite.
"""
import argparse
import json
from pathlib import Path

import zmq

from src.cards.schema import load_card_set
from src.paths import CARDSET_PATH, MODEL_PATH, ROOT
from src.server.session import GameSession


def find_metagame(elites: Path, model: Path) -> Path | None:
    """The archive's metagame table played by the server's model, else by the heuristic agent."""
    for agent in (model.stem, "heuristic"):
        path = ROOT / "data" / "metagame" / f"{elites.stem}.{agent}.json"
        if path.exists():
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--cards", type=Path, default=CARDSET_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--no-search", action="store_true", help="the neural opponent plays the raw policy, without search")
    parser.add_argument("--elites", type=Path, help="a MAP-Elites archive of the set: offers each class's best deck")
    parser.add_argument("--metagame", type=Path, help="the archive's metagame table (default: found next to it)")
    args = parser.parse_args()

    metagame = args.metagame or (find_metagame(args.elites, args.model) if args.elites else None)
    try:
        session = GameSession(load_card_set(args.cards), model_path=args.model, search=not args.no_search,
                              elites=args.elites, metagame=metagame)
    except ValueError as e:
        parser.error(str(e))
    if args.elites:
        print(f"Best decks for {len(session.best)} classes from {args.elites}"
              f"{', by the smoothed equilibrium of ' + str(metagame) if metagame else ', by fitness'}", flush=True)
    socket = zmq.Context().socket(zmq.REP)
    socket.bind(f"tcp://*:{args.port}")
    print(f"Server ready on tcp://*:{args.port} ({len(session.card_set)} cards"
          f"{', model ' + str(args.model) + ('' if args.no_search else ' with search') if args.model.exists() else ', no trained model'})", flush=True)

    while True:
        message = socket.recv_string()
        try:
            response = session.handle(json.loads(message))
        except Exception as e:  # keep serving: a bad request must not kill the server
            print(f"Error handling {message[:200]!r}: {e!r}", flush=True)
            response = {"status": "error", "msg": str(e)}
        socket.send_string(json.dumps(response))


if __name__ == "__main__":
    main()
