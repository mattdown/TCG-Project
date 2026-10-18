import pytest

from src.cards.coverage import generate_coverage_set
from src.cards.schema import Card, CardSet, load_card_set
from src.paths import ROOT
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
            assert set(record["result"]) == {"damage", "defeated", "vp", "energy_spent", "exhausted", "readied", "moves",
                                             "abilities", "healed", "effects"}


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


def ability_session():
    """A session whose cards all have the same on-play ability: draw a card, then deal 1 damage to a chosen opposing unit."""
    ability = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [
        {"effect": "draw", "target": "you", "amount": 1},
        {"choose": {"count": 1, "filter": {"owner": "opponent"}}, "as": "it"},
        {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 1}]}
    cards = [Card(f"C{i}", f"Card {i}", "unit", (f"aspect_{1 + i % 6}",), True, 1, 1, 3, 1, abilities=(ability,))
             for i in range(60)]
    session = GameSession(CardSet("abilities", cards))
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 4})
    return session


def test_card_set_includes_ability_text():
    cards = ability_session().handle({"type": "card_set"})["cards"]
    assert cards[0]["ability_text"] == ["When you play this unit, draw a card. Deal 1 damage to chosen opposing unit."]
    assert cards[0]["abilities"][0]["kind"] == "triggered"


def test_pending_decision_and_previews_dont_reveal_draws():
    session = ability_session()
    game = session.game
    while game.state.phase.name == "MULLIGAN":
        session.handle({"type": "act" if game.state.decision_player == 0 else "ai_move", "action_index": 0})
    put_in_play(game, 1, unit(health=5, name="A"))
    put_in_play(game, 1, unit(health=5, name="B"))
    give_energy(game, game.state.active_player, 1)
    if game.state.active_player != 0:
        session.handle({"type": "ai_turn"})
        give_energy(game, 0, 1)
    state = session.handle({"type": "state"})["state"]
    play = next(a for a in state["legal_actions"] if a["type"] == "play")
    assert not any(m["from"] == "deck" for m in play["preview"]["moves"])  # the draw isn't previewed
    state = session.handle({"type": "act", "action_index": play["index"]})["state"]
    assert state["pending"]["kind"] == "choose" and state["pending"]["chooser"] == 0
    assert {a["type"] for a in state["legal_actions"]} == {"choose_target"}


def test_scenario_sets_up_chosen_cards():
    card_set = generate_coverage_set(per_feature=1, candidates=500)
    action_card = next(c for c in card_set.cards if c.type == "action")
    unit_card = next(c for c in card_set.cards if c.type == "unit")
    session = GameSession(card_set)
    state = session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 2, "scenario": {
        "hand": [action_card.id], "play": [{"id": unit_card.id, "damage": 1}], "opponent_play": [unit_card.id],
        "energy": action_card.cost, "vp": 4, "opponent_vp": 2}})["state"]
    me, them = state["players"]
    assert state["phase"] == "main" and state["decision_player"] == 0 and state["turn"] == 1
    assert action_card.id in [c["card_id"] for c in me["hand"]]
    assert [c["card_id"] for c in me["play"]] == [unit_card.id] and me["play"][0]["damage"] == 1
    assert [c["card_id"] for c in them["play"]] == [unit_card.id]
    assert me["energy_ready"] == action_card.cost
    assert me["vp"] == 4 and them["vp"] == 2
    assert any(a["type"] == "play" and a["card"] == me["hand"][-1]["uid"] for a in state["legal_actions"])


def test_scenario_rejects_unknown_cards():
    session = GameSession(generate_vanilla_set())
    response = session.handle({"type": "new_game", "opponent": "random", "scenario": {"hand": ["NOPE"]}})
    assert response["status"] == "error" and "NOPE" in response["msg"]


def coverage_scenario(scenario, seed=1):
    session = GameSession(load_card_set(ROOT / "cardsets" / "coverage_37.json"))
    state = session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": seed,
                            "scenario": scenario})["state"]
    return session, state


def test_card_set_has_keyword_rules():
    response = GameSession(generate_vanilla_set()).handle({"type": "card_set"})
    assert response["keywords"]["duelist"] == {"name": "Duelist", "numbered": True, "rule": "+N power when it starts a duel."}
    assert set(response["keywords"]) == {"guard", "elusive", "charge", "duelist", "armor"}


def test_card_instances_show_current_stats_and_keywords():
    # C1-003: "⟳, 3 energy: Choose one: • Your opponent loses 1 VP. • All opposing units get −1 power this turn."
    session, state = coverage_scenario({"play": ["C1-003"], "opponent_play": ["C1-017"], "energy": 3})
    them = state["players"][1]["play"][0]
    assert them["power"] == 6 and them["health"] == 2 and them["keywords"] == {}
    activate = legal(state, "activate")[0]
    state = session.handle({"type": "act", "action_index": activate["index"]})["state"]
    weaken = next(a for a in legal(state, "choose_option") if "power" in a["text"])
    state = session.handle({"type": "act", "action_index": weaken["index"]})["state"]
    assert state["players"][1]["play"][0]["power"] == 5
    mine = state["players"][0]["play"][0]
    assert mine["exhausted"] and not mine["cant_ready"] and not mine["barred"]
    assert set(mine) >= {"power", "health", "score", "keywords", "cost"}


def test_granted_keywords_and_cant_ready_are_shown():
    # C1-020: "Whenever this unit scores, this unit gains Elusive this turn."
    # C1-014: "Whenever this unit scores, all opposing units can't ready at the start of their next turn."
    session, state = coverage_scenario({"play": ["C1-020", "C1-014"], "opponent_play": [{"id": "C1-018", "exhausted": True}]})
    by_card = {c["card_id"]: c for c in state["players"][0]["play"]}
    for card_id in ("C1-020", "C1-014"):
        score = next(a for a in legal(state, "score") if a["card"] == by_card[card_id]["uid"])
        state = session.handle({"type": "act", "action_index": score["index"]})["state"]
    scorer = next(c for c in state["players"][0]["play"] if c["card_id"] == "C1-020")
    assert scorer["keywords"] == {"elusive": True}
    assert state["players"][1]["play"][0]["cant_ready"]


def test_action_cards_have_no_stats_in_the_state():
    _, state = coverage_scenario({"hand": ["C1-004"], "energy": 1})
    card = next(c for c in state["players"][0]["hand"] if c["card_id"] == "C1-004")
    assert card["cost"] == 1 and "power" not in card


def test_results_include_healing_and_lasting_effects():
    # C1-004 (action): "You may lose 1 VP. If you do, remove all damage from your units with cost 2 or less."
    session, state = coverage_scenario({"hand": ["C1-004"], "energy": 1, "vp": 3,
                                        "play": [{"id": "C1-018", "damage": 1}]})
    hurt = state["players"][0]["play"][0]["uid"]
    action_card = next(c["uid"] for c in state["players"][0]["hand"] if c["card_id"] == "C1-004")
    play = next(a for a in legal(state, "play") if a["card"] == action_card)
    state = session.handle({"type": "act", "action_index": play["index"]})["state"]
    result = session.handle({"type": "act", "action_index": legal(state, "accept")[0]["index"]})["action"]["result"]
    assert result["healed"] == [{"uid": hurt, "amount": 1}] and result["vp"] == [{"player": 0, "amount": -1}]
    # C1-003: "… • All opposing units get −1 power this turn."
    session, state = coverage_scenario({"play": ["C1-003"], "opponent_play": ["C1-017"], "energy": 3})
    state = session.handle({"type": "act", "action_index": legal(state, "activate")[0]["index"]})["state"]
    weaken = next(a for a in legal(state, "choose_option") if "power" in a["text"])
    result = session.handle({"type": "act", "action_index": weaken["index"]})["action"]["result"]
    them = state["players"][1]["play"][0]["uid"]
    assert result["effects"] == [{"uid": them, "kind": "stat", "stat": "power", "keyword": None, "value": -1,
                                  "this_turn": True}]
