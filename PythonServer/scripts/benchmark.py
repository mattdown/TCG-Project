"""Round-robin matches between agents on random decks.

Every match is paired: each deck pair is played twice with the seats swapped, and the same --seed
gives every match the same deck pairs, so agents are compared on the same deals. --mirror gives
both players the same deck, which takes deck luck out entirely: the gap between a normal and a
mirror run says how much of a result is the deal. --hide-aspects adds a copy of each model with
the players' aspect features zeroed, to see whether it leans on them. --search adds each model with
search within a turn (SearchAgent)."""
import argparse
import itertools
from pathlib import Path

from src.agents.heuristic_agent import HeuristicAgent
from src.agents.match import play_match
from src.agents.neural_agent import NeuralAgent
from src.agents.random_agent import RandomAgent
from src.agents.search_agent import SearchAgent
from src.cards.schema import load_card_set
from src.paths import CARDSET_PATH, MODEL_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--cards", type=Path, nargs="+", default=[CARDSET_PATH])
    parser.add_argument("--models", type=Path, nargs="*", default=[MODEL_PATH],
                        help="checkpoints to include as neural agents (named after the file)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mirror", action="store_true", help="the same deck for both players")
    parser.add_argument("--hide-aspects", action="store_true", help="also play each model with aspects hidden")
    parser.add_argument("--no-random", action="store_true", help="leave out the random agent")
    parser.add_argument("--search", action="store_true", help="also play each model with search within a turn")
    parser.add_argument("--beam", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()

    agents = ([] if args.no_random else [RandomAgent(seed=0)]) + [HeuristicAgent()]
    for path in args.models:
        if not path.exists():
            print(f"No model at {path}: skipping it")
            continue
        agents.append(NeuralAgent.from_checkpoint(path))
        if args.hide_aspects:
            agents.append(NeuralAgent.from_checkpoint(path, aspects=False))

    for cards in args.cards:
        card_set = load_card_set(cards)
        players = list(agents)
        if args.search:  # search guesses hidden cards from the set, so it's built per set
            players += [SearchAgent.from_checkpoint(path, card_set, beam=args.beam, top_k=args.top_k)
                        for path in args.models if path.exists()]
        print(f"{cards.stem}{' (mirror decks)' if args.mirror else ''}:")
        for a, b in itertools.combinations(players, 2):
            r = play_match(a, b, card_set, args.games, args.seed, mirror=args.mirror)
            print(f"  {a.name:>26} vs {b.name:<26}  {r['win_rate']:6.1%}  (wins {r['wins'][0]}-{r['wins'][1]}, "
                  f"draws {r['draws']}, {r['avg_turns']:.1f} turns/game)", flush=True)


if __name__ == "__main__":
    main()
