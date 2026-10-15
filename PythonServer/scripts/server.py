"""ZeroMQ game server for the Unity client: JSON requests in, JSON responses out.

See src/server/session.py for the request types.
"""
import argparse
import json
from pathlib import Path

import zmq

from src.cards.schema import load_card_set
from src.paths import CARDSET_PATH, MODEL_PATH
from src.server.session import GameSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--cards", type=Path, default=CARDSET_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    args = parser.parse_args()

    session = GameSession(load_card_set(args.cards), model_path=args.model)
    socket = zmq.Context().socket(zmq.REP)
    socket.bind(f"tcp://*:{args.port}")
    print(f"Server ready on tcp://*:{args.port} ({len(session.card_set)} cards"
          f"{', model ' + str(args.model) if args.model.exists() else ', no trained model'})", flush=True)

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
