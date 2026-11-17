import random

from src.agents.heuristic_agent import HeuristicAgent
from src.agents.puzzles import Puzzle, action_from_dict, face_line, find_lethal, record_game, sure
from src.cards.generate import generate_card_set
from src.game.actions import ActionType
from src.game.decks import random_deck
from tests.helpers import put_in_play, started_game, unit


def _board(opponent_health: int, guard: bool):
    game = started_game()
    game.state.players[1].health = opponent_health
    for _ in range(2):
        put_in_play(game, 0, unit(cost=3, power=3, health=3))
    if guard:
        put_in_play(game, 1, unit(power=1, health=1, guard=1))
    return game


def test_lethal_by_attacking_the_hero():
    game = _board(5, guard=False)
    line, finished = find_lethal(game)
    assert finished and [a.type for a in line] == [ActionType.ATTACK_HERO] * 2
    assert face_line(game)


def test_lethal_through_a_guard_needs_a_trade_first():
    game = _board(3, guard=True)
    line, finished = find_lethal(game)
    types = [a.type for a in line]
    assert finished and ActionType.ATTACK in types and types[-1] == ActionType.ATTACK_HERO
    assert not face_line(game)


def test_no_lethal_and_a_search_cut_short():
    assert find_lethal(_board(7, guard=False)) == (None, True)
    assert find_lethal(_board(5, guard=False), budget=1) == (None, False)


def test_sure_rejects_a_line_that_stops_short():
    game = _board(5, guard=False)
    line, _ = find_lethal(game)
    cards = generate_card_set(60, seed=1)
    assert sure(game, line, cards) and not sure(game, line[:1], cards)


def test_recorded_puzzles_replay_to_their_position_and_line():
    cards = generate_card_set(120, seed=4)
    rng = random.Random(0)
    agents = (HeuristicAgent(), HeuristicAgent())
    puzzles = []
    for i in range(4):
        found, turns, _ = record_game(agents, (random_deck(cards, rng), random_deck(cards, rng)), i, i % 2, cards)
        assert turns > 0
        puzzles += found
    assert puzzles
    for p in puzzles:
        assert Puzzle.from_dict(p.to_dict()) == p
        game = p.position(cards)
        assert game.state.decision_player == game.state.active_player == p.player
        if p.face:  # attacking the hero with everything wins (the heuristic agent may still trade first)
            assert face_line(game)
        for d in p.line:
            game.step(action_from_dict(d))
        assert game.state.winner == p.player
