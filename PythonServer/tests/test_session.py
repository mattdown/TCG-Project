import pytest

from src.cards.vanilla import generate_vanilla_set
from src.server.session import GameSession


@pytest.fixture
def session():
    s = GameSession(generate_vanilla_set())
    s.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 1})
    return s


def test_requests_before_new_game_fail():
    assert GameSession(generate_vanilla_set()).handle({"type": "state"})["status"] == "error"


def test_card_set():
    response = GameSession(generate_vanilla_set()).handle({"type": "card_set"})
    assert response["status"] == "ok" and len(response["cards"]) == 200


def test_state_hides_ai_hand(session):
    state = session.handle({"type": "state"})["state"]
    assert state["players"][0]["hand"] is not None and state["players"][1]["hand"] is None
    assert state["players"][1]["hand_count"] == 7


def test_neural_opponent_without_model_is_an_error():
    response = GameSession(generate_vanilla_set()).handle({"type": "new_game", "opponent": "neural"})
    assert response["status"] == "error"


def test_full_game_through_the_session(session):
    for _ in range(2000):
        state = session.handle({"type": "state"})["state"]
        if state["game_over"]:
            break
        if state["decision_player"] == 0:
            response = session.handle({"type": "act", "action_index": len(state["legal_actions"]) - 1})
        else:
            response = session.handle({"type": "ai_turn"})
        assert response["status"] == "ok", response
    assert state["game_over"]


def test_acting_out_of_turn_is_an_error(session):
    state = session.handle({"type": "state"})["state"]
    wrong = "ai_move" if state["decision_player"] == 0 else "act"
    assert session.handle({"type": wrong, "action_index": 0})["status"] == "error"
