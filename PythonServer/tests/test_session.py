import pytest

from src.cards.vanilla import generate_vanilla_set
from src.server.session import GameSession
from tests.helpers import give_energy, put_in_hand, put_in_play, started_game, unit


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


def session_at(game):
    s = GameSession(generate_vanilla_set())
    s.game, s.human_seat = game, 0
    return s


def legal(state, type_):
    return [a for a in state["legal_actions"] if a["type"] == type_]


def test_state_has_vp_to_win(session):
    assert session.handle({"type": "state"})["state"]["vp_to_win"] == 20


def amounts(entries, key="uid"):
    return {e[key]: e["amount"] for e in entries}


def test_duel_preview_matches_the_result():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=4))
    weak = put_in_play(game, 1, unit(power=2, health=2), exhausted=True)
    tough = put_in_play(game, 1, unit(power=1, health=9), exhausted=True)
    s = session_at(game)
    duels = {a["target"]: a for a in legal(s.view(), "duel")}
    preview = duels[weak]["preview"]
    assert amounts(preview["damage"]) == {attacker: 2, weak: 3} and preview["defeated"] == [weak]
    assert amounts(duels[tough]["preview"]["damage"]) == {attacker: 1, tough: 3}
    assert duels[tough]["preview"]["defeated"] == []
    response = s.handle({"type": "act", "action_index": duels[weak]["index"]})
    assert response["action"]["result"] == preview
    assert response["state"]["players"][0]["play"][0]["damage"] == 2


def test_previewing_does_not_change_the_game():
    game = started_game()
    put_in_play(game, 0, unit(power=5, health=5))
    put_in_play(game, 1, unit(power=5, health=5), exhausted=True)
    s = session_at(game)
    before = s.view()
    assert s.view() == before


def test_score_and_play_previews():
    game = started_game()
    scorer = put_in_play(game, 0, unit(score=3))
    card = put_in_hand(game, 0, unit(cost=2))
    give_energy(game, 0, 3)
    state = session_at(game).view()
    score = next(a for a in legal(state, "score") if a["card"] == scorer)
    play = next(a for a in legal(state, "play") if a["card"] == card)
    assert amounts(score["preview"]["vp"], "player") == {0: 3}
    assert amounts(play["preview"]["energy_spent"], "player") == {0: 2}
    assert play["preview"]["moves"] == [{"uid": card, "card_id": "Unit 2/1/1/1", "player": 0,
                                         "from": "hand", "to": "play"}]
    assert all(a["preview"] is None for a in legal(state, "end_turn") + legal(state, "add_energy"))


def test_every_action_record_has_a_result(session):
    for _ in range(300):
        state = session.handle({"type": "state"})["state"]
        if state["game_over"]:
            break
        if state["decision_player"] == 0:
            response = session.handle({"type": "act", "action_index": 0})
            records = [response["action"]]
        else:
            records = session.handle({"type": "ai_turn"})["actions"]
        for record in records:
            assert set(record["result"]) == {"damage", "defeated", "vp", "energy_spent", "exhausted", "readied", "moves"}


def test_ai_draws_and_put_backs_stay_hidden():
    s = GameSession(generate_vanilla_set())
    s.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 2})
    hidden = []
    for _ in range(200):
        state = s.handle({"type": "state"})["state"]
        if state["game_over"]:
            break
        if state["decision_player"] == 0:
            records = [s.handle({"type": "act", "action_index": len(state["legal_actions"]) - 1})["action"]]
        else:
            records = s.handle({"type": "ai_turn"})["actions"]
        for record in records:
            for m in record["result"]["moves"]:
                if m["player"] == 1 and {m["from"], m["to"]} <= {"deck", "hand"}:
                    hidden.append(m)
    assert hidden and all(m["uid"] is None and m["card_id"] is None for m in hidden)
