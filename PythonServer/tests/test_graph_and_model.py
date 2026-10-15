import random

import torch

from src.cards.vanilla import generate_vanilla_set
from src.game.actions import Action, ActionType
from src.game.decks import random_deck
from src.game.engine import Game
from src.graph.builder import CARD_DYNAMIC_DIM, CARD_STATIC_DIM, build_observation
from src.model.network import TCGNet, collate, segment_entropy, segment_log_softmax
from tests.helpers import put_in_play, started_game, unit


def random_positions(n, seed=0):
    card_set = generate_vanilla_set()
    rng = random.Random(seed)
    observations = []
    while len(observations) < n:
        game = Game(random_deck(card_set, rng), random_deck(card_set, rng), seed=rng.randrange(2**31))
        for _ in range(rng.randrange(80)):
            if game.is_over:
                break
            game.step(rng.choice(game.legal_actions()))
        if not game.is_over:
            observations.append(build_observation(game, game.state.decision_player))
    return observations


def test_observation_matches_state():
    game = started_game()
    mine = put_in_play(game, 0, unit(name="Mine"))
    theirs = put_in_play(game, 1, unit(name="Theirs"), exhausted=True)
    obs = build_observation(game, 0)
    data = obs.data
    n_cards = len(game.state.players[0].hand) + 2
    assert data["card"].x_static.shape == (n_cards, CARD_STATIC_DIM)
    assert data["card"].x_dynamic.shape == (n_cards, CARD_DYNAMIC_DIM)
    assert data["card", "faces", "card"].edge_index.shape == (2, 2)
    assert data["action"].num_nodes == len(obs.actions) == len(game.legal_actions())
    duel = obs.actions.index(Action(ActionType.DUEL, mine, theirs))
    assert data["action"].actor[duel] == n_cards - 2 and data["action"].target[duel] == n_cards - 1
    assert data["action"].actor[obs.actions.index(Action(ActionType.END_TURN))] == -1


def test_opponent_hand_is_hidden():
    game = started_game()
    obs = build_observation(game, 0)
    assert obs.data["card"].num_nodes == len(game.state.players[0].hand)


def test_forward_on_batch_gives_one_distribution_per_decision():
    observations = random_positions(16)
    net = TCGNet(hidden=32, num_layers=2)
    logits, index, values = net(collate([o.data for o in observations]))
    assert logits.shape == (sum(len(o.actions) for o in observations),)
    assert values.shape == (16,) and values.abs().max() <= 1
    probs = torch.zeros(16).index_add(0, index, segment_log_softmax(logits, index).exp())
    assert torch.allclose(probs, torch.ones(16), atol=1e-5)
    assert (segment_entropy(segment_log_softmax(logits, index), index) >= -1e-6).all()


def test_batched_scores_match_single_scores():
    observations = random_positions(4, seed=1)
    net = TCGNet(hidden=32, num_layers=2).eval()
    batched, index, _ = net(collate([o.data for o in observations]))
    for i, obs in enumerate(observations):
        single, _, _ = net(collate([obs.data]))
        assert torch.allclose(batched[index == i], single, atol=1e-5)


def test_graph_with_no_cards_works():
    game = started_game()
    game.state.players[0].hand.clear()
    obs = build_observation(game, 0)
    assert obs.data["card"].num_nodes == 0
    logits, _, values = TCGNet(hidden=32, num_layers=2)(collate([obs.data]))
    assert logits.shape == (1,) and values.shape == (1,)  # only END_TURN
