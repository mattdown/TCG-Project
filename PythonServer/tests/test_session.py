from dataclasses import replace

import pytest

from src.cards.art import art_key
from src.cards.coverage import generate_coverage_set
from src.cards.schema import Card, CardSet
from src.cards.vanilla import generate_vanilla_set
from src.model.registry import create_model
from src.server.session import GameSession
from tests.helpers import fixture_set, give_mana, put_in_hand, put_in_play, started_game, unit


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
    assert state["players"][1]["hand_count"] in (3, 5)


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


def test_state_has_heroes_and_mana(session):
    state = session.handle({"type": "state"})["state"]
    assert state["hero_health"] == 30 and state["max_mana"] == 10
    assert all(set(p) >= {"health", "mana", "crystals", "spare_spore", "fatigue"} for p in state["players"])


def amounts(entries, key="uid"):
    return {e[key]: e["amount"] for e in entries}


def test_attack_preview_matches_the_result():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=4))
    weak = put_in_play(game, 1, unit(power=2, health=2))
    tough = put_in_play(game, 1, unit(power=1, health=9))
    s = session_at(game)
    attacks = {a["target"]: a for a in legal(s.view(), "attack")}
    preview = attacks[weak]["preview"]
    assert amounts(preview["damage"]) == {attacker: 2, weak: 3} and preview["defeated"] == [weak]
    assert amounts(attacks[tough]["preview"]["damage"]) == {attacker: 1, tough: 3}
    assert attacks[tough]["preview"]["defeated"] == []
    response = s.handle({"type": "act", "action_index": attacks[weak]["index"]})
    assert response["action"]["result"] == preview
    assert response["state"]["players"][0]["play"][0]["damage"] == 2


def test_previewing_does_not_change_the_game():
    game = started_game()
    put_in_play(game, 0, unit(power=5, health=5))
    put_in_play(game, 1, unit(power=5, health=5))
    s = session_at(game)
    before = s.view()
    assert s.view() == before


def test_hero_attack_and_play_previews():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3))
    card = put_in_hand(game, 0, unit(cost=2))
    give_mana(game, 0, 3)
    state = session_at(game).view()
    hit = next(a for a in legal(state, "attack_hero") if a["card"] == attacker)
    play = next(a for a in legal(state, "play") if a["card"] == card)
    assert amounts(hit["preview"]["hero_damage"], "player") == {1: 3}
    assert amounts(play["preview"]["mana_spent"], "player") == {0: 2}
    assert play["preview"]["moves"] == [{"uid": card, "card_id": "Unit 2/1/1", "player": 0,
                                         "from": "hand", "to": "play"}]
    assert all(a["preview"] is None for a in legal(state, "end_turn"))


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
            assert set(record["result"]) == {"damage", "defeated", "hero_damage", "hero_healed", "mana_spent", "crystals",
                                             "attacked", "moves", "abilities", "healed", "effects", "summoned"}


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
    """A session whose cards all have the same on-play ability: draw a card, then deal 1 damage to a chosen enemy unit."""
    ability = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None, "steps": [
        {"effect": "draw", "target": "you", "amount": 1},
        {"choose": {"count": 1, "filter": {"owner": "opponent"}}, "as": "it"},
        {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 1}]}
    cards = [Card(f"C{i}", f"Card {i}", "unit", (f"aspect_{1 + i % 6}",), 1, 1, 3, abilities=(ability,))
             for i in range(30)]
    session = GameSession(CardSet("abilities", cards))
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 4})
    return session


def test_card_set_includes_ability_text():
    cards = ability_session().handle({"type": "card_set"})["cards"]
    assert cards[0]["ability_text"] == ["When you play this unit, draw a card. Deal 1 damage to chosen enemy unit."]
    assert cards[0]["abilities"][0]["kind"] == "triggered"


def test_card_set_names_each_cards_art():
    """Art is keyed by how the card looks (name, subtitle, habitat), so regenerated sets reuse it."""
    assert art_key("Porcini Baker", "Up Before Dawn", ("aspect_4",)) == "porcini-baker--up-before-dawn--meadow"
    assert art_key("Lion's-mane Chef", "Retired (Mostly)", ()) == "lion-s-mane-chef--retired-mostly--neutral"
    assert art_key("Ember Volley", "", ("aspect_1",)) == "ember-volley--ember"
    cards = ability_session().handle({"type": "card_set"})["cards"]
    assert all(c["art"] == art_key(c["name"], c["subtitle"], c["aspects"]) for c in cards)


def test_pending_decision_and_previews_dont_reveal_draws():
    session = ability_session()
    game = session.game
    while game.state.phase.name == "MULLIGAN":
        session.handle({"type": "act" if game.state.decision_player == 0 else "ai_move", "action_index": 0})
    put_in_play(game, 1, unit(health=5, name="A"))
    put_in_play(game, 1, unit(health=5, name="B"))
    give_mana(game, game.state.active_player, 1)
    if game.state.active_player != 0:
        session.handle({"type": "ai_turn"})
        give_mana(game, 0, 1)
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
        "mana": action_card.cost, "health": 24, "opponent_health": 12}})["state"]
    me, them = state["players"]
    assert state["phase"] == "main" and state["decision_player"] == 0 and state["turn"] == 1
    assert action_card.id in [c["card_id"] for c in me["hand"]]
    assert [c["card_id"] for c in me["play"]] == [unit_card.id] and me["play"][0]["damage"] == 1
    assert [c["card_id"] for c in them["play"]] == [unit_card.id]
    assert me["mana"] == me["crystals"] == action_card.cost
    assert me["health"] == 24 and them["health"] == 12
    assert any(a["type"] == "play" and a["card"] == me["hand"][-1]["uid"] for a in state["legal_actions"])


def test_scenario_rejects_unknown_cards():
    session = GameSession(generate_vanilla_set())
    response = session.handle({"type": "new_game", "opponent": "random", "scenario": {"hand": ["NOPE"]}})
    assert response["status"] == "error" and "NOPE" in response["msg"]


def coverage_scenario(scenario, seed=1):
    session = GameSession(fixture_set())
    state = session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": seed,
                            "scenario": scenario})["state"]
    return session, state


def test_card_set_has_keyword_rules():
    response = GameSession(generate_vanilla_set()).handle({"type": "card_set"})
    assert response["keywords"]["duelist"] == {"name": "Duelist", "numbered": True, "rule": "+N power while attacking."}
    assert set(response["keywords"]) == {"guard", "elusive", "charge", "duelist", "armor"}


def test_card_set_has_aspect_names_and_descriptions():
    response = GameSession(generate_vanilla_set()).handle({"type": "card_set"})
    aspects = response["aspects"]
    assert set(aspects) == {"aspect_1", "aspect_2", "aspect_3", "aspect_4", "aspect_5", "aspect_6", "neutral"}
    assert aspects["aspect_1"]["name"] == "Ember" and aspects["neutral"]["name"] == "Neutral"
    assert all(a["description"] for a in aspects.values())


def test_card_instances_show_current_stats_and_keywords():
    # WEAKENER: "When you play this unit, choose one: • Deal 1 damage to the enemy hero. • All enemy units get −1 power this turn."
    session, state = coverage_scenario({"hand": ["WEAKENER"], "opponent_play": ["BRUISER"], "mana": 5})
    them = state["players"][1]["play"][0]
    assert them["power"] == 6 and them["health"] == 2 and them["keywords"] == {}
    weakener = next(c["uid"] for c in state["players"][0]["hand"] if c["card_id"] == "WEAKENER")
    play = next(a for a in legal(state, "play") if a["card"] == weakener)
    state = session.handle({"type": "act", "action_index": play["index"]})["state"]
    weaken = next(a for a in legal(state, "choose_option") if "power" in a["text"])
    state = session.handle({"type": "act", "action_index": weaken["index"]})["state"]
    assert state["players"][1]["play"][0]["power"] == 5
    mine = state["players"][0]["play"][0]
    assert mine["fresh"] and not mine["can_attack"] and not mine["frozen"] and not mine["hidden"]
    assert set(mine) >= {"power", "health", "keywords", "cost", "can_attack"}


def test_granted_keywords_and_freeze_are_shown():
    # SLIPPERY: "Whenever this unit attacks the enemy hero, it gains Armor +1 until the start of your next turn."
    # FREEZER: "Whenever this unit attacks the enemy hero, freeze all enemy units."
    session, state = coverage_scenario({"play": ["SLIPPERY", "FREEZER"], "opponent_play": [{"id": "POSTMAN", "attacked": True}]})
    by_card = {c["card_id"]: c for c in state["players"][0]["play"]}
    for card_id in ("SLIPPERY", "FREEZER"):
        hit = next(a for a in legal(state, "attack_hero") if a["card"] == by_card[card_id]["uid"])
        state = session.handle({"type": "act", "action_index": hit["index"]})["state"]
    attacker = next(c for c in state["players"][0]["play"] if c["card_id"] == "SLIPPERY")
    assert attacker["keywords"] == {"armor": 1}
    assert state["players"][1]["play"][0]["frozen"]


def test_action_cards_have_no_stats_in_the_state():
    _, state = coverage_scenario({"hand": ["HEAL"], "mana": 1})
    card = next(c for c in state["players"][0]["hand"] if c["card_id"] == "HEAL")
    assert card["cost"] == 1 and "power" not in card


def test_results_include_healing_and_lasting_effects():
    # HEAL (action): "You may deal 2 damage to your hero. If you do, remove all damage from your units with cost 2 or less."
    session, state = coverage_scenario({"hand": ["HEAL"], "mana": 1, "play": [{"id": "POSTMAN", "damage": 1}]})
    hurt = state["players"][0]["play"][0]["uid"]
    action_card = next(c["uid"] for c in state["players"][0]["hand"] if c["card_id"] == "HEAL")
    play = next(a for a in legal(state, "play") if a["card"] == action_card)
    state = session.handle({"type": "act", "action_index": play["index"]})["state"]
    result = session.handle({"type": "act", "action_index": legal(state, "accept")[0]["index"]})["action"]["result"]
    assert result["healed"] == [{"uid": hurt, "amount": 1}] and result["hero_damage"] == [{"player": 0, "amount": 2}]
    # WEAKENER: "… • All enemy units get −1 power this turn."
    session, state = coverage_scenario({"hand": ["WEAKENER"], "opponent_play": ["BRUISER"], "mana": 5})
    weakener = next(c["uid"] for c in state["players"][0]["hand"] if c["card_id"] == "WEAKENER")
    play = next(a for a in legal(state, "play") if a["card"] == weakener)
    state = session.handle({"type": "act", "action_index": play["index"]})["state"]
    weaken = next(a for a in legal(state, "choose_option") if "power" in a["text"])
    result = session.handle({"type": "act", "action_index": weaken["index"]})["action"]["result"]
    them = state["players"][1]["play"][0]["uid"]
    assert result["effects"] == [{"uid": them, "kind": "stat", "stat": "power", "keyword": None, "value": -1,
                                  "this_turn": True, "lasts": "this_turn"}]


def test_summons_send_their_tokens_and_report_them():
    sprouts = Card("sprouts", "Sprouts", "action", (), 1, 0, 0, abilities=({"kind": "on_resolve", "steps": [
        {"effect": "summon", "amount": 2, "target": "you", "token": {"name": "Sprout", "power": 1, "health": 1}}]},))
    session = GameSession(CardSet("s", [sprouts] + [replace(unit(name=f"Filler {i}"), id=f"f{i}") for i in range(15)]))
    cards = session.handle({"type": "card_set"})["cards"]
    token = next(c for c in cards if c.get("token"))
    assert (token["name"], token["power"], token["health"]) == ("Sprout", 1, 1)
    state = session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 1,
                            "scenario": {"hand": ["sprouts"], "mana": 1}})["state"]
    uid = next(c["uid"] for c in state["players"][0]["hand"] if c["card_id"] == "sprouts")
    play = next(a for a in state["legal_actions"] if a["type"] == "play" and a["card"] == uid)
    assert [s["card_id"] for s in play["preview"]["summoned"]] == [token["id"]] * 2
    response = session.handle({"type": "act", "action_index": play["index"]})
    assert [s["card_id"] for s in response["action"]["result"]["summoned"]] == [token["id"]] * 2
    assert [c["card_id"] for c in response["state"]["players"][0]["play"]][-2:] == [token["id"]] * 2


def test_graph_has_the_gnn_nodes_and_edges_from_the_humans_side():
    card_set = generate_coverage_set(per_feature=1, candidates=500)
    unit_card = next(c for c in card_set.cards if c.type == "unit" and c.abilities)
    session = GameSession(card_set)
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 2, "scenario": {
        "hand": [unit_card.id], "play": [unit_card.id], "opponent_play": [unit_card.id],
        "opponent_hand": [unit_card.id], "mana": 10}})
    graph = session.handle({"type": "graph"})["graph"]
    nodes = graph["nodes"]
    assert [n["id"] for n in nodes] == list(range(len(nodes)))
    assert graph["embedding"] == "features" and graph["layers"] == 1
    assert all(len(v) == graph["dim"] for n in nodes for v in n["vectors"])
    cards = [n for n in nodes if n["type"] == "card"]
    me, them = session.game.state.players
    assert [c["uid"] for c in cards] == me.hand + me.play + them.play  # never the AI's hand
    assert sum(n["type"] == "player" for n in nodes) == 2 and sum(n["type"] == "global" for n in nodes) == 1
    abilities = [n for n in nodes if n["type"] == "ability"]
    assert abilities and {n["card"] for n in abilities} == {c["id"] for c in cards}
    assert any(n["label"].startswith("entry") for n in abilities)
    types = {n["id"]: n["type"] for n in nodes}
    for e in graph["edges"]:
        if e["type"] in ("next", "uses"):
            assert types[e["src"]] == types[e["dst"]] == "ability"
        elif e["type"] in ("part_of", "matches", "bound_to"):
            assert (types[e["src"]], types[e["dst"]]) == ("ability", "card")
    assert {"belongs_to", "faces", "part_of", "next"} <= {e["type"] for e in graph["edges"]}
    legal = session.handle({"type": "state"})["state"]["legal_actions"]
    assert [a["index"] for a in graph["actions"]] == [a["index"] for a in legal]
    for a in graph["actions"]:
        assert a["probability"] is None and types[a["global"]] == "global"
        assert all(a[slot] is None or types[a[slot]] == "card" for slot in ("actor", "target"))
        assert all(a[slot] is None or types[a[slot]] == "ability" for slot in ("context", "option"))
    assert any(a["type"] == "play" and a["actor"] is not None for a in graph["actions"])
    assert graph["value"]["estimate"] is None
    assert [types[n] for n in graph["value"]["nodes"]] == ["global", "player", "player"]


def test_graph_returns_every_gnn_layer():
    session = GameSession(fixture_set())
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 1, "scenario": {"mana": 3}})
    session._net = create_model("gnn", hidden=32, num_layers=2)
    graph = session.handle({"type": "graph"})["graph"]
    assert graph["embedding"] == "gnn" and graph["layers"] == 3
    assert all(len(n["vectors"]) == 3 and len(n["vectors"][0]) == graph["dim"] for n in graph["nodes"])
    probabilities = [a["probability"] for a in graph["actions"]]
    assert probabilities and abs(sum(probabilities) - 1) < 1e-2
    assert -1 <= graph["value"]["estimate"] <= 1


def test_graph_node_names_the_input_features_without_a_model():
    session = GameSession(fixture_set())
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 1, "scenario": {"mana": 3}})
    graph = session.handle({"type": "graph"})["graph"]
    for n in graph["nodes"]:
        node = session.handle({"type": "graph_node", "node": n["id"]})["node"]
        assert node["id"] == n["id"] and node["type"] == n["type"] and node["embedding"] == "features"
        assert node["input"] and node["stages"] == [] and node["layers"] == [] and node["read_by"]
        assert all(f["value"] != 0 and isinstance(f["name"], str) for group in node["input"] for f in group["features"])
    card = next(n for n in graph["nodes"] if n["type"] == "card")
    node = session.handle({"type": "graph_node", "node": card["id"]})["node"]
    assert [g["name"] for g in node["input"]] == ["static", "dynamic"]
    assert {"name": "in_hand", "value": 1.0} in node["input"][1]["features"]
    assert session.handle({"type": "graph_node", "node": len(graph["nodes"])})["status"] == "error"


def test_graph_node_has_each_layers_messages_and_attention():
    session = GameSession(fixture_set())
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 1, "scenario": {"mana": 3}})
    session._net = create_model("gnn", hidden=32, num_layers=2)
    graph = session.handle({"type": "graph"})["graph"]
    linked = {(e["src"], e["dst"]) for e in graph["edges"]} | {(e["dst"], e["src"]) for e in graph["edges"]}
    forward = {e["type"] for e in graph["edges"]} | {"belongs_to", "faces", "opposes", "in", "part_of", "next",
                                                     "uses", "matches", "bound_to"}
    for n in graph["nodes"]:
        node = session.handle({"type": "graph_node", "node": n["id"]})["node"]
        assert node["embedding"] == "gnn" and node["hidden"] == 32 and len(node["layers"]) == 2
        assert node["stages"][-1]["dim"] == 32 and len(node["stages"][-1]["vector"]) == 16
        for layer in node["layers"]:
            assert layer["dim"] == 32 and len(layer["vector"]) == 16 and layer["incoming"]
            for message in layer["incoming"]:
                assert message["shown_as"] in forward and message["message"] >= 0
                assert abs(sum(m["attention"] for m in message["neighbours"]) - 1) < 1e-2
                assert all((m["node"], n["id"]) in linked for m in message["neighbours"])
    glob = next(n for n in graph["nodes"] if n["type"] == "global")
    layer = session.handle({"type": "graph_node", "node": glob["id"]})["node"]["layers"][0]
    assert [(m["type"], len(m["neighbours"])) for m in layer["incoming"]] == [("in", 2)]


def test_graph_layer_steps_match_the_networks_forward_pass():
    session = GameSession(fixture_set())
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 1, "scenario": {"mana": 3}})
    assert session.handle({"type": "graph_layer", "node": 0, "layer": 1})["status"] == "error"  # no model
    session._net = create_model("gnn", hidden=32, num_layers=2)
    graph = session.handle({"type": "graph"})["graph"]
    for n in graph["nodes"]:
        node = session.handle({"type": "graph_node", "node": n["id"]})["node"]
        for depth, summary in enumerate(node["layers"], start=1):
            layer = session.handle({"type": "graph_layer", "node": n["id"], "layer": depth})["layer"]
            assert layer["layer"] == depth and layer["heads"] * layer["head_dim"] == layer["hidden"] == 32
            assert layer["output"]["vector"] == pytest.approx(summary["vector"], abs=2e-3)
            assert [t["type"] for t in layer["edge_types"]] == [m["type"] for m in summary["incoming"]]
            for steps, message in zip(layer["edge_types"], summary["incoming"]):
                assert steps["message_size"] == pytest.approx(message["message"], abs=2e-3)
                averaged = {nb["node"]: sum(nb["attention"]) / layer["heads"] for nb in steps["neighbours"]}
                for nb in message["neighbours"]:
                    assert averaged[nb["node"]] == pytest.approx(nb["attention"], abs=2e-3)
                for head in range(layer["heads"]):
                    assert sum(nb["attention"][head] for nb in steps["neighbours"]) == pytest.approx(1, abs=1e-2)
    assert session.handle({"type": "graph_layer", "node": 0, "layer": 3})["status"] == "error"


def test_graph_has_no_actions_on_the_ais_decision():
    session = GameSession(fixture_set())
    session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 1})
    while session.game.state.decision_player == 0:
        session.handle({"type": "act", "action_index": 0})
    assert session.handle({"type": "graph"})["graph"]["actions"] == []


def test_unusable_actions_and_options_say_so():
    enemy = {"choose": {"count": 1, "filter": {"owner": "opponent"}}, "as": "it"}
    hit = {"effect": "deal_damage", "target": {"ref": "it"}, "amount": 2}
    draw = {"effect": "draw", "target": "you", "amount": 1}
    bolt = Card("BOLT", "Bolt", "action", ("aspect_1",), 1, 0, 0, abilities=({"kind": "on_resolve", "steps": [enemy, hit]},))
    charm = Card("CHARM", "Charm", "action", ("aspect_1",), 1, 0, 0,
                 abilities=({"kind": "on_resolve", "steps": [{"choose_one": [[enemy, hit], [draw]]}]},))
    session = GameSession(CardSet("unusable", [bolt, charm] + generate_vanilla_set().cards[:30]))
    state = session.handle({"type": "new_game", "opponent": "heuristic", "human_seat": 0, "seed": 2, "scenario": {
        "hand": ["BOLT", "CHARM"], "mana": 1}})["state"]
    hand = {c["card_id"]: c for c in state["players"][0]["hand"]}
    assert hand["BOLT"]["unusable"] == "Bolt has nothing to target." and "unusable" not in hand["CHARM"]
    assert not any(a["type"] == "play" and a["card"] == hand["BOLT"]["uid"] for a in state["legal_actions"])

    play = next(a for a in state["legal_actions"] if a["type"] == "play" and a["card"] == hand["CHARM"]["uid"])
    pending = session.handle({"type": "act", "action_index": play["index"]})["state"]["pending"]
    assert [o["usable"] for o in pending["options"]] == [False, True]
