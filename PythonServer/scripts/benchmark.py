"""Round-robin matches between agents on random decks."""
import argparse
import itertools
from pathlib import Path

from src.agents.heuristic_agent import HeuristicAgent
from src.agents.match import play_match
from src.agents.neural_agent import NeuralAgent
from src.agents.random_agent import RandomAgent
from src.cards.schema import load_card_set
from src.paths import CARDSET_PATH, MODEL_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--cards", type=Path, default=CARDSET_PATH)
    parser.add_argument("--models", type=Path, nargs="*", default=[MODEL_PATH],
                        help="checkpoints to include as neural agents (named after the file)")
    args = parser.parse_args()

    card_set = load_card_set(args.cards)
    agents = [RandomAgent(seed=0), HeuristicAgent()]
    for path in args.models:
        if path.exists():
            agents.append(NeuralAgent.from_checkpoint(path))
        else:
            print(f"No model at {path}: skipping it")

    for a, b in itertools.combinations(agents, 2):
        r = play_match(a, b, card_set, args.games)
        print(f"{a.name:>16} vs {b.name:<16}  {r['win_rate']:6.1%}  (wins {r['wins'][0]}-{r['wins'][1]}, "
              f"draws {r['draws']}, {r['avg_turns']:.1f} turns/game)")


if __name__ == "__main__":
    main()
