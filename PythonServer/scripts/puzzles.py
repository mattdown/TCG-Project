"""Tactical puzzles: does the agent find lethal? (src/agents/puzzles.py)

Collects puzzles from games between two copies of --model on random decks (written to --out, one
per line; reused if it exists), then scores the heuristic agent, the model and the model with
search on them: how often each wins before its turn ends, for "face" puzzles (attacking the hero
with everything is enough) and "tactical" ones (it takes more)."""
import argparse
import json
import random
from pathlib import Path

from src.agents.heuristic_agent import HeuristicAgent
from src.agents.neural_agent import NeuralAgent
from src.agents.puzzles import Puzzle, record_game, solves
from src.agents.search_agent import SearchAgent
from src.cards.schema import load_card_set
from src.game.decks import random_deck
from src.paths import MODEL_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cards", type=Path, default=Path("cardsets/heldout_200.json"))
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, help="puzzle file (default data/puzzles_<cards>.jsonl)")
    args = parser.parse_args()
    card_set = load_card_set(args.cards)
    out = args.out or Path("data") / f"puzzles_{args.cards.stem}.jsonl"

    if out.exists():
        puzzles = [Puzzle.from_dict(json.loads(line)) for line in out.read_text().splitlines()]
        print(f"{len(puzzles)} puzzles from {out}")
    else:
        rng = random.Random(args.seed)
        player = NeuralAgent.from_checkpoint(args.model)
        puzzles, turns, unfinished = [], 0, 0
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as f:
            for i in range(args.games):
                decks = (random_deck(card_set, rng), random_deck(card_set, rng))
                found, checked, unknown = record_game((player, player), decks, rng.randrange(2**31), i % 2, card_set)
                turns += checked
                unfinished += unknown
                for p in found:
                    f.write(json.dumps(p.to_dict()) + "\n")
                puzzles += found
                if (i + 1) % 20 == 0:
                    print(f"  {i + 1} games, {len(puzzles)} puzzles", flush=True)
        print(f"{len(puzzles)} puzzles from {args.games} games ({turns} turns checked, {unfinished} too big to "
              f"search), written to {out}")

    opponent = HeuristicAgent()
    agents = [HeuristicAgent(), NeuralAgent.from_checkpoint(args.model),
              SearchAgent.from_checkpoint(args.model, card_set)]
    kinds = {"face": [p for p in puzzles if p.face], "tactical": [p for p in puzzles if not p.face]}
    print(f"{'':>22} " + "  ".join(f"{k} ({len(v)})".rjust(16) for k, v in kinds.items()))
    for agent in agents:
        rates = [sum(solves(agent, p, card_set, opponent) for p in v) / max(len(v), 1) for v in kinds.values()]
        print(f"{agent.name:>22} " + "  ".join(f"{r:16.1%}" for r in rates), flush=True)


if __name__ == "__main__":
    main()
