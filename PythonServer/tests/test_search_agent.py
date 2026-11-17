import random

import pytest

from src.agents.neural_agent import NeuralAgent
from src.agents.search_agent import SearchAgent
from src.cards.generate import generate_card_set
from src.game.decks import random_deck
from src.game.engine import Game
from src.model.registry import create_model


@pytest.fixture(scope="module")
def cards():
    return generate_card_set(120, seed=4)


def small_net():
    return create_model("gnn", hidden=16, num_layers=1)


def test_search_plays_whole_games_with_legal_moves(cards):
    rng = random.Random(0)
    net = small_net()
    search = SearchAgent(net, cards, beam=2, top_k=2, max_depth=4)
    for seed in range(2):
        game = Game(random_deck(cards, rng), random_deck(cards, rng), seed=seed)
        while not game.is_over:
            agent = search if game.state.decision_player == 0 else NeuralAgent(net)
            move = agent.choose(game)
            assert move in game.legal_actions()
            game.step(move)
    assert search.positions > 0


def test_search_cant_see_hidden_cards(cards):
    """The same public position with different hidden cards (another hand and deck list for the
    opponent, another order for its own deck) gets the same move."""
    rng = random.Random(1)
    net = small_net()
    game = Game(random_deck(cards, rng), random_deck(cards, rng), seed=3)
    agents = (NeuralAgent(net), NeuralAgent(net))
    checked = 0
    while not game.is_over and checked < 10:
        me = game.state.decision_player
        if game.state.active_player == me and len(game.legal_actions()) > 1 and game.state.phase.name == "MAIN":
            other = game.clone()
            _swap_hidden_cards(other, 1 - me, cards, random.Random(checked))
            moves = [SearchAgent(net, cards, beam=2, top_k=3, max_depth=4, seed=7).choose(g) for g in (game, other)]
            assert moves[0] == moves[1]
            checked += 1
        game.step(agents[me].choose(game))
    assert checked > 0


def _swap_hidden_cards(game: Game, opponent: int, cards, rng: random.Random):
    """Gives the opponent other hidden cards and reorders the other player's deck: what search can't see."""
    theirs = game.state.players[opponent]
    for uid in theirs.hand + theirs.deck:
        game.card(uid).card = rng.choice(cards.cards)
    rng.shuffle(game.state.players[1 - opponent].deck)
