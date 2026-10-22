"""Abilities in the state graph: ability nodes, their edges and the decision context."""
import numpy as np

from src.game.actions import Action, ActionType
from src.graph.abilities import FEATURES, INDEX, card_ability_graph
from src.graph.encode import observe
from tests.helpers import action, give_mana, put_in_hand, put_in_play, started_game, unit

OPP = {"owner": "opponent"}


def triggered(event, *steps):
    return {"kind": "triggered", "trigger": {"event": event}, "condition": None, "steps": list(steps)}


SNIPER = unit(cost=2, name="Sniper", abilities=[triggered(
    "on_play", {"choose": {"count": 1, "filter": OPP}, "as": "it"},
    {"effect": "deal_damage", "amount": 2, "target": {"ref": "it"}},
    {"if": {"defeated": "it"}, "then": [{"effect": "draw", "amount": 1, "target": "you"}]})])


def names(row):
    return {FEATURES[i] for i in np.flatnonzero(row)}


def test_card_ability_graph_follows_the_decision_graph():
    g = card_ability_graph(SNIPER)
    kinds = [next(f for f in names(r) if f.startswith("kind:")) for r in g.features]
    assert sorted(kinds) == sorted(["kind:entry", "kind:end", "kind:choose", "kind:effect", "kind:if", "kind:effect"])
    entry = kinds.index("kind:entry")
    assert {"ability:triggered", "event:on_play"} <= names(g.features[entry])
    damage = next(i for i, r in enumerate(g.features) if r[INDEX["op:deal_damage"]])
    assert g.features[damage, INDEX["amount"]] == 2 / 5 and g.features[damage, INDEX["target:ref"]] == 1
    choose = kinds.index("kind:choose")
    # The choice binds "it": the damage and the "if it was defeated" both use it.
    assert {(int(a), int(b)) for a, b in g.uses.T} == {(choose, damage), (choose, kinds.index("kind:if"))}
    assert len(g.next[0]) == 6  # entry → choose → damage → if → (draw | end), draw → end


def test_vanilla_cards_have_no_ability_nodes():
    game = started_game()
    put_in_play(game, 0, unit(name="Plain"))
    assert observe(game, 0).encoded.num_nodes == 0


def test_matches_follow_the_rules_and_only_visible_cards():
    game = started_game()
    a = put_in_play(game, 1, unit(health=5, name="A"))
    b = put_in_play(game, 1, unit(health=5, name="B"))
    hidden = put_in_play(game, 1, unit(health=5, name="Sneaky", elusive=1))
    put_in_hand(game, 0, SNIPER)
    enc = observe(game, 0).encoded
    uids = game.state.players[0].hand + game.state.players[0].play + game.state.players[1].play
    choose = next(i for i in range(enc.num_nodes) if enc.node_features[i, INDEX["kind:choose"]])
    matched = {uids[c] for n, c in enc.node_matches.T if n == choose}
    # The filter matches every enemy unit (the engine's candidates); Elusive only stops the choice.
    assert matched == {a, b, hidden}
    assert all(enc.node_card[n] == uids.index(next(u for u in game.state.players[0].hand
                                                  if game.card(u).card is SNIPER)) for n in range(enc.num_nodes))


def test_decision_context_and_bound_choices():
    game = started_game()
    a = put_in_play(game, 1, unit(health=5, name="A"))
    put_in_play(game, 1, unit(health=5, name="B"))
    uid = put_in_hand(game, 0, SNIPER)
    give_mana(game, 0, 2)
    game.step(Action(ActionType.PLAY, uid))
    obs = observe(game, 0)
    enc = obs.encoded
    assert all(a.type == ActionType.CHOOSE_TARGET for a in obs.actions)
    context = enc.action_context[0]
    assert context >= 0 and (enc.action_context == context).all()
    assert enc.node_features[context, INDEX["kind:choose"]] == 1
    assert enc.node_features[context, INDEX["resolving"]] == 1
    assert (enc.action_option == -1).all()
    assert enc.node_bound.shape[1] == 0  # nothing chosen yet
    # Choosing A binds it to the choose node until the ability finishes.
    frame = game.state.pending[-1]
    frame.bindings["it"] = [a]
    enc = observe(game, 0).encoded
    uids = game.state.players[0].hand + game.state.players[0].play + game.state.players[1].play
    assert [(int(n), uids[c]) for n, c in enc.node_bound.T] == [(context, a)]


def test_choose_one_options_point_at_their_first_step():
    charm = action({"choose_one": [[{"effect": "draw", "amount": 1, "target": "you"}],
                                   [{"effect": "damage_hero", "amount": 2, "target": "opponent"}]]}, name="Charm")
    game = started_game()
    uid = put_in_hand(game, 0, charm)
    give_mana(game, 0, 1)
    game.step(Action(ActionType.PLAY, uid))
    obs = observe(game, 0)
    enc = obs.encoded
    assert [a.type for a in obs.actions] == [ActionType.CHOOSE_OPTION] * 2
    first, second = enc.action_option
    assert enc.node_features[first, INDEX["op:draw"]] == 1
    assert enc.node_features[second, INDEX["op:damage_hero"]] == 1
    assert enc.node_features[enc.action_context[0], INDEX["kind:choose_one"]] == 1


def test_static_modifiers_get_nodes_and_matches():
    lord = unit(name="Lord", abilities=[{"kind": "static", "condition": None, "modifiers": [
        {"subject": {"all": {"owner": "you", "trait": "Chef", "not_this": True}}, "stat": "power", "amount": 1}]}])
    game = started_game()
    put_in_play(game, 0, lord)
    chef = put_in_play(game, 0, unit(name="Chef", traits=("Chef",)))
    put_in_play(game, 0, unit(name="Baker", traits=("Baker",)))
    enc = observe(game, 0).encoded
    uids = game.state.players[0].hand + game.state.players[0].play + game.state.players[1].play
    modifier = next(i for i in range(enc.num_nodes) if enc.node_features[i, INDEX["kind:modifier"]])
    assert {uids[c] for n, c in enc.node_matches.T if n == modifier} == {chef}
    assert enc.node_features[modifier, INDEX["subject:all"]] == 1


def test_buff_nodes_carry_both_amounts():
    feast = action({"effect": "buff", "power": 2, "health": 1, "target": {"all": {"owner": "you"}}}, name="Feast")
    g = card_ability_graph(feast)
    node = next(r for r in g.features if r[INDEX["op:buff"]])
    assert node[INDEX["buff_power"]] == 2 / 3 and node[INDEX["buff_health"]] == 1 / 3
    assert node[INDEX["duration:permanent"]] == 1
