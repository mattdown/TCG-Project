import random

from src.agents.base import Agent
from src.cards.schema import CardSet
from src.game.decks import random_deck
from src.game.engine import Game


def play_game(agents: tuple[Agent, Agent], game: Game) -> Game:
    while not game.is_over:
        game.step(agents[game.state.decision_player].choose(game), validate=False)
    return game


def play_match(agent_a: Agent, agent_b: Agent, card_set: CardSet, num_games: int, seed: int = 0,
               mirror: bool = False) -> dict:
    """agent_a vs agent_b on random decks. Each deck pair is played twice with the seats swapped, so
    who goes first and which deck is stronger cancel out. With `mirror` both players get the same
    deck, so the result says how they play, not what they drew (each still shuffles its own copy)."""
    rng = random.Random(seed)
    wins = [0, 0]
    draws = turns = 0
    for i in range(num_games):
        if i % 2 == 0:
            deck = random_deck(card_set, rng)
            decks = (deck, list(deck)) if mirror else (deck, random_deck(card_set, rng))
            game_seed = rng.randrange(2**31)
        seats = (agent_a, agent_b) if i % 2 == 0 else (agent_b, agent_a)
        game = play_game(seats, Game(*decks, seed=game_seed, first_player=0))
        turns += game.state.turn
        if game.state.winner is None:
            draws += 1
        else:
            wins[(game.state.winner + i) % 2] += 1
    return {"win_rate": (wins[0] + 0.5 * draws) / num_games, "wins": wins, "draws": draws,
            "avg_turns": turns / num_games}
