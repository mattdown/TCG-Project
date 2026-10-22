"""Experiments on what decides games.

abilities: the same deck lists played against altered copies of themselves, by one agent on
    both sides. "stripped" removes unit abilities (stats unchanged: the ability's cost stays
    paid), "refunded" also puts the ability's points back into stats, and "no actions" swaps
    actions for vanilla units of the same cost. If abilities matter, the real deck wins.
luck: each deck pair is played four times (both agents on both decks, each going first),
    so a result can be put down to the player, the deck or going first.
first: mirror matches under different compensations for the second player, each deck pair
    played twice so both decks go first once.
"""
import argparse
import dataclasses
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import torch

from src.agents.heuristic_agent import HeuristicAgent
from src.agents.match import play_game
from src.agents.neural_agent import NeuralAgent
from src.agents.random_agent import RandomAgent
from src.cards.schema import Card, load_card_set
from src.cards.vanilla import MAX_STATS, keyword_value, stat_budget
from src.game.decks import random_deck
from src.game.engine import Game, GameConfig


def stripped(card: Card) -> Card:
    return dataclasses.replace(card, abilities=()) if card.type == "unit" else card


def refunded(card: Card) -> Card:
    """A unit without its ability and with the ability's points back in its stats."""
    if card.type != "unit" or not card.abilities:
        return card
    budget = stat_budget(card.cost) - keyword_value(dict(card.keywords))
    power, health = card.power, card.health
    while power + health < budget and (power < MAX_STATS["power"] or health < MAX_STATS["health"]):
        if health < MAX_STATS["health"] and (health <= power or power >= MAX_STATS["power"]):
            health += 1
        else:
            power += 1
    return dataclasses.replace(card, power=power, health=health, abilities=())


def no_actions(card: Card) -> Card:
    """An action becomes a vanilla unit of the same cost with full stats."""
    if card.type != "action":
        return card
    cost = max(card.cost, 1)
    budget = stat_budget(cost)
    return dataclasses.replace(card, type="unit", cost=cost, power=budget // 2, health=budget - budget // 2,
                               abilities=())


VARIANTS = {"stripped": stripped, "refunded": refunded, "no actions": no_actions}

# Compensation for going second: opening hands (first, second) and Spare Spores.
FIRST_PLAYER_RULES = {
    "now: 3/4 cards, 1 spore": GameConfig(),
    "3/5 cards, 1 spore": GameConfig(opening_hand=(3, 5)),
    "3/4 cards, 2 spores": GameConfig(spare_spores=2),
    "3/5 cards, 2 spores": GameConfig(opening_hand=(3, 5), spare_spores=2),
    "3/4 cards, 3 spores": GameConfig(spare_spores=3),
}


def make_agent(spec: str):
    if spec == "heuristic":
        return HeuristicAgent()
    if spec == "random":
        return RandomAgent(seed=0)
    return NeuralAgent.from_checkpoint(spec)


def name(spec: str) -> str:
    return Path(spec).stem if spec.endswith(".pt") else spec


def ability_job(cards: Path, agent_spec: str, variant: str, pairs: int, seed: int) -> dict:
    """The real deck against its altered copy, with seats swapped. Returns the real deck's results."""
    torch.set_num_threads(1)
    card_set = load_card_set(cards)
    agent = make_agent(agent_spec)
    alter = VARIANTS[variant]
    rng = random.Random(seed)
    wins = games = 0
    for _ in range(pairs):
        deck = random_deck(card_set, rng)
        altered = [alter(c) for c in deck]
        game_seed = rng.randrange(2**31)
        for real_seat in (0, 1):
            decks = (deck, altered) if real_seat == 0 else (altered, deck)
            game = play_game((agent, agent), Game(*decks, seed=game_seed, first_player=0))
            games += 1
            wins += game.state.winner == real_seat if game.state.winner is not None else 0.5
    changed = sum(alter(c) != c for c in card_set.cards)
    return {"agent": name(agent_spec), "variant": variant, "win_rate": wins / games, "games": games,
            "changed": changed / len(card_set.cards)}


def first_job(cards: Path, agent_spec: str, rules: str, pairs: int, seed: int) -> dict:
    """One agent in both seats; each deck pair is played with either deck going first."""
    torch.set_num_threads(1)
    card_set = load_card_set(cards)
    agent = make_agent(agent_spec)
    config = FIRST_PLAYER_RULES[rules]
    rng = random.Random(seed)
    first_wins = games = turns = 0
    for _ in range(pairs):
        decks = (random_deck(card_set, rng), random_deck(card_set, rng))
        game_seed = rng.randrange(2**31)
        for first in (0, 1):
            game = play_game((agent, agent), Game(*decks, seed=game_seed, first_player=first, config=config))
            games += 1
            turns += game.state.turn
            first_wins += 0.5 if game.state.winner is None else game.state.winner == first
    return {"agent": name(agent_spec), "rules": rules, "first_player": first_wins / games, "games": games,
            "avg_turns": turns / games}


def luck_job(cards: Path, spec_a: str, spec_b: str, pairs: int, seed: int) -> dict:
    """Four games per deck pair: A and B each play both decks, each going first once."""
    torch.set_num_threads(1)
    card_set = load_card_set(cards)
    a = make_agent(spec_a)
    b = make_agent(spec_b) if spec_b != spec_a else a
    rng = random.Random(seed)
    a_wins = first_wins = games = 0
    by_pair = Counter()  # how many of its four games A won
    deck_decided = 0  # one deck won all four games, whoever played it and whoever went first
    for _ in range(pairs):
        decks = (random_deck(card_set, rng), random_deck(card_set, rng))
        game_seed = rng.randrange(2**31)
        won_by_deck = [0, 0]
        pair_a = 0
        for a_deck in (0, 1):
            for first in (0, 1):
                seats = (a, b) if a_deck == 0 else (b, a)  # seat i plays deck i
                game = play_game(seats, Game(*decks, seed=game_seed, first_player=first))
                games += 1
                winner = game.state.winner
                if winner is None:
                    continue
                won_by_deck[winner] += 1
                first_wins += winner == first
                if winner == a_deck:
                    pair_a += 1
        a_wins += pair_a
        by_pair[pair_a] += 1
        deck_decided += 4 in won_by_deck
    return {"a": name(spec_a), "b": name(spec_b), "win_rate": a_wins / games, "games": games,
            "first_player": first_wins / games, "deck_decided": deck_decided / pairs,
            "by_pair": [by_pair[k] / pairs for k in range(5)]}


def run_parallel(fn, jobs: list[tuple], workers: int) -> list[dict]:
    with ProcessPoolExecutor(workers) as pool:
        return list(pool.map(fn, *zip(*jobs)))


def split(pairs: int, chunks: int) -> list[int]:
    return [pairs // chunks + (i < pairs % chunks) for i in range(chunks)]


def merge(results: list[dict], keys: tuple[str, ...]) -> dict:
    """Combines chunks of one experiment, weighting rates by games."""
    total = sum(r["games"] for r in results)
    merged = dict(results[0], games=total)
    for key in keys:
        if isinstance(results[0][key], list):
            merged[key] = [sum(r[key][i] * r["games"] for r in results) / total for i in range(len(results[0][key]))]
        else:
            merged[key] = sum(r[key] * r["games"] for r in results) / total
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment", choices=["abilities", "luck", "first"])
    parser.add_argument("--cards", type=Path, default=Path("cardsets/set_200.json"))
    parser.add_argument("--agents", nargs="+", default=["heuristic", "models/tcgnet_league.pt"],
                        help="abilities: agents to test; luck: pairs of agents as a,b")
    parser.add_argument("--pairs", type=int, default=200, help="deck pairs per experiment")
    parser.add_argument("--chunks", type=int, default=4, help="parallel chunks per experiment")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    if args.experiment == "abilities":
        groups = [(agent, variant) for agent in args.agents for variant in VARIANTS]
        jobs = [(args.cards, agent, variant, n, 1000 * i)
                for agent, variant in groups for i, n in enumerate(split(args.pairs, args.chunks))]
        results = run_parallel(ability_job, jobs, args.workers)
        print(f"{'agent':>16}  {'real deck vs':<12} {'cards changed':>13}  {'real deck wins':>14}")
        for g in range(len(groups)):
            r = merge(results[g * args.chunks:(g + 1) * args.chunks], ("win_rate",))
            print(f"{r['agent']:>16}  {r['variant']:<12} {r['changed']:13.0%}  {r['win_rate']:14.1%}  ({r['games']} games)")
    elif args.experiment == "first":
        groups = [(agent, rules) for agent in args.agents for rules in FIRST_PLAYER_RULES]
        jobs = [(args.cards, agent, rules, n, 1000 * i)
                for agent, rules in groups for i, n in enumerate(split(args.pairs, args.chunks))]
        results = run_parallel(first_job, jobs, args.workers)
        print(f"{'agent':>16}  {'second player gets':<24} {'first player wins':>17} {'turns':>6}")
        for g in range(len(groups)):
            r = merge(results[g * args.chunks:(g + 1) * args.chunks], ("first_player", "avg_turns"))
            print(f"{r['agent']:>16}  {r['rules']:<24} {r['first_player']:17.1%} {r['avg_turns']:6.1f}  ({r['games']} games)")
    else:
        groups = [tuple(spec.split(",")) for spec in args.agents]
        jobs = [(args.cards, a, b, n, 1000 * i)
                for a, b in groups for i, n in enumerate(split(args.pairs, args.chunks))]
        results = run_parallel(luck_job, jobs, args.workers)
        print("A wins k of 4 games on a deck pair; 'deck decided' = one deck won all four.")
        print(f"{'A':>16} vs {'B':<16} {'A wins':>7} {'1st wins':>9} {'deck decided':>13}   k=0   k=1   k=2   k=3   k=4")
        for g in range(len(groups)):
            r = merge(results[g * args.chunks:(g + 1) * args.chunks],
                      ("win_rate", "first_player", "deck_decided", "by_pair"))
            dist = " ".join(f"{p:5.0%}" for p in r["by_pair"])
            print(f"{r['a']:>16} vs {r['b']:<16} {r['win_rate']:7.1%} {r['first_player']:9.1%} "
                  f"{r['deck_decided']:13.0%}   {dist}  ({r['games']} games)")


if __name__ == "__main__":
    main()
