import random

import numpy as np
import pytest
import torch
from torch_geometric.data import Batch

from functools import lru_cache

from src.cards.generate import generate_card_set
from src.game.actions import Action, ActionType
from src.game.decks import random_deck
from src.game.engine import Game
from src.graph.abilities import FEATURES
from src.graph.builder import collate_hetero, to_hetero_data
from src.graph.dense import NUM_FIXED_TOKENS, REL, bucket, collate_dense, relation_matrix
from src.graph.encode import CARD_DYNAMIC_DIM, CARD_STATIC_DIM, OUTCOME_FEATURES, action_outcome, observe
from src.model.common import segment_entropy, segment_log_softmax
from src.model.registry import (ARCHITECTURES, LEGACY_ACTIONS, LEGACY_FEATURES, create_model, load_model,
                                save_model)
from tests.helpers import filler_deck, put_in_hand, put_in_play, started_game, unit

ARCHS = sorted(ARCHITECTURES)


@lru_cache(maxsize=None)
def ability_set():
    return generate_card_set(120, seed=4)


def random_positions(n, seed=0):
    card_set = ability_set()
    rng = random.Random(seed)
    observations = []
    while len(observations) < n:
        game = Game(random_deck(card_set, rng), random_deck(card_set, rng), seed=rng.randrange(2**31))
        for _ in range(rng.randrange(80)):
            if game.is_over:
                break
            game.step(rng.choice(game.legal_actions()))
        if not game.is_over:
            observations.append(observe(game, game.state.decision_player))
    return observations


def small(arch):
    torch.manual_seed(0)
    return create_model(arch, hidden=32, num_layers=2).eval()


# --- encoding


def test_encoding_matches_state():
    game = started_game()
    mine = put_in_play(game, 0, unit(name="Mine"))
    theirs = put_in_play(game, 1, unit(name="Theirs"))
    obs = observe(game, 0)
    enc = obs.encoded
    n_cards = len(game.state.players[0].hand) + 2
    assert enc.card_static.shape == (n_cards, CARD_STATIC_DIM)
    assert enc.card_dynamic.shape == (n_cards, CARD_DYNAMIC_DIM)
    assert list(enc.card_owner[-2:]) == [0, 1] and enc.card_in_play[-2:].all()
    assert enc.num_actions == len(obs.actions) == len(game.legal_actions())
    attack = obs.actions.index(Action(ActionType.ATTACK, mine, theirs))
    assert enc.action_actor[attack] == n_cards - 2 and enc.action_target[attack] == n_cards - 1
    hero = obs.actions.index(Action(ActionType.ATTACK_HERO, mine))
    assert enc.action_actor[hero] == n_cards - 2 and enc.action_target[hero] == -1
    assert enc.player[0][0] == 1.0  # full health
    assert enc.action_actor[obs.actions.index(Action(ActionType.END_TURN))] == -1


def test_opponent_hand_is_hidden():
    game = started_game()
    assert observe(game, 0).encoded.num_cards == len(game.state.players[0].hand)


def _outcome(game, action) -> dict:
    return dict(zip(OUTCOME_FEATURES, action_outcome(game, game.state.decision_player, action)))


def test_attack_outcome_counts_armor():
    """The previewed fight already takes Armor off, so the network doesn't have to learn the sum."""
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=3, health=2))
    plain = put_in_play(game, 1, unit(power=1, health=3))
    armored = put_in_play(game, 1, unit(power=1, health=3, armor=1))
    hit_plain = _outcome(game, Action(ActionType.ATTACK, attacker, plain))
    hit_armored = _outcome(game, Action(ActionType.ATTACK, attacker, armored))
    assert hit_plain["previewed"] == 1 and hit_plain["enemy_defeated"] > 0 and hit_plain["enemy_unit_damage"] == 0.3
    assert hit_armored["enemy_defeated"] == 0 and hit_armored["enemy_unit_damage"] == 0.2
    assert hit_armored["my_unit_damage"] == 0.1 and hit_armored["my_defeated"] == 0
    assert game.state.cards[armored].damage == 0  # tried on a copy


def test_lethal_and_unpreviewed_actions():
    game = started_game()
    attacker = put_in_play(game, 0, unit(power=5, health=1))
    game.state.players[1].health = 5
    lethal = _outcome(game, Action(ActionType.ATTACK_HERO, attacker))
    assert lethal["win"] == 1 and lethal["enemy_hero_damage"] == 0.5 and not game.is_over
    assert not any(_outcome(game, Action(ActionType.END_TURN)).values())


def test_outcomes_never_depend_on_hidden_cards():
    """The same position with the hidden cards dealt differently gives the same outcome features."""
    draw = {"kind": "triggered", "trigger": {"event": "on_play"}, "condition": None,
            "steps": [{"effect": "draw", "amount": 2, "target": "you"}]}
    encodings = []
    for seed in range(4):
        rng = random.Random(seed)
        decks = [filler_deck(), filler_deck()]
        for deck in decks:
            deck[:10] = [unit(cost=1, power=rng.randrange(1, 9), health=rng.randrange(1, 9), name=f"R{i}")
                         for i in range(10)]
            rng.shuffle(deck)
        game = started_game(*decks)
        put_in_hand(game, 0, unit(abilities=(draw,), name="Drawer"))
        encodings.append(observe(game, 0).encoded.action_outcome)
    assert all(np.array_equal(encodings[0], e) for e in encodings[1:])


def test_outcomes_in_random_positions_are_finite_and_only_on_previewed_actions():
    for o in random_positions(20, seed=3):
        e = o.encoded
        assert e.action_outcome.shape == (e.num_actions, len(OUTCOME_FEATURES)) and np.isfinite(e.action_outcome).all()
        for a, row in zip(o.actions, e.action_outcome):
            if a.type in (ActionType.END_TURN, ActionType.MULLIGAN, ActionType.KEEP_HAND, ActionType.SPARE_SPORE):
                assert not row.any()
            else:
                assert row[0] == 1


def test_hetero_data_edges():
    game = started_game()
    put_in_play(game, 0, unit(name="Mine"))
    put_in_play(game, 1, unit(name="Theirs"))
    data = to_hetero_data(observe(game, 0).encoded)
    assert data["card", "faces", "card"].edge_index.shape == (2, 2)
    assert data["card", "belongs_to", "player"].edge_index.shape == (2, data["card"].num_nodes)


def test_relation_matrix():
    owner = np.array([0, 0, 1])
    in_play = np.array([False, True, True])
    rel = relation_matrix(owner, in_play, size=4)
    c = NUM_FIXED_TOKENS
    assert rel.shape == (7, 7)
    assert rel[1, c] == REL["belongs_to"] and rel[c, 1] == REL["has_card"]
    assert rel[2, c + 2] == REL["belongs_to"]
    assert rel[c + 1, c + 2] == rel[c + 2, c + 1] == REL["faces"]
    assert rel[c, c + 2] == REL["none"]  # the card in hand doesn't face anything
    assert rel[c + 3, 1] == REL["none"] and rel[c + 3, c + 3] == REL["self"]  # padding


def test_bucket_sizes():
    assert [bucket(n) for n in (0, 1, 8, 9, 16, 17, 40)] == [8, 8, 8, 16, 16, 32, 64]


def test_dense_batch_padding():
    observations = random_positions(5)
    batch = collate_dense([o.encoded for o in observations])
    assert batch.card_mask.sum(1).tolist() == [o.encoded.num_cards for o in observations]
    assert batch.action_mask.sum(1).tolist() == [o.encoded.num_actions for o in observations]
    assert batch.node_mask.sum(1).tolist() == [o.encoded.num_nodes for o in observations]
    assert batch.relation.shape[1] == NUM_FIXED_TOKENS + batch.card_static.shape[1] + batch.node_features.shape[1]


# --- models


@pytest.mark.parametrize("arch", ARCHS)
def test_forward_gives_one_distribution_per_decision(arch):
    observations = random_positions(16)
    net = small(arch)
    logits, index, values = net(net.collate([o.encoded for o in observations]))
    assert logits.shape == (sum(len(o.actions) for o in observations),)
    assert values.shape == (16,) and values.abs().max() <= 1
    log_probs = segment_log_softmax(logits, index)
    probs = torch.zeros(16).index_add(0, index, log_probs.exp())
    assert torch.allclose(probs, torch.ones(16), atol=1e-5)
    assert (segment_entropy(log_probs, index) >= -1e-6).all()


@pytest.mark.parametrize("arch", ARCHS)
def test_batched_scores_match_single_scores(arch):
    # For the transformer this also checks that padding has no effect.
    observations = random_positions(4, seed=1)
    net = small(arch)
    batched, index, values = net(net.collate([o.encoded for o in observations]))
    for i, obs in enumerate(observations):
        single, _, value = net(net.collate([obs.encoded]))
        assert torch.allclose(batched[index == i], single, atol=1e-5)
        assert torch.allclose(values[i], value[0], atol=1e-5)


@pytest.mark.parametrize("arch", ARCHS)
def test_state_with_no_cards(arch):
    game = started_game()
    game.state.players[0].hand.clear()
    obs = observe(game, 0)
    assert obs.encoded.num_cards == 0
    net = small(arch)
    logits, _, values = net(net.collate([obs.encoded]))
    assert logits.shape == (1,) and values.shape == (1,)  # only END_TURN


@pytest.mark.parametrize("arch", ARCHS)
def test_save_and_load(arch, tmp_path):
    net = small(arch)
    save_model(net, tmp_path / "m.pt")
    loaded = load_model(tmp_path / "m.pt")
    assert type(loaded) is type(net)
    obs = random_positions(1)[0].encoded
    assert torch.allclose(net(net.collate([obs]))[0], loaded(loaded.collate([obs]))[0])


def test_checkpoint_without_arch_loads_as_gnn(tmp_path):
    net = small("gnn")
    torch.save({"hparams": net.hparams, "state_dict": net.state_dict()}, tmp_path / "old.pt")
    assert load_model(tmp_path / "old.pt").arch == "gnn"


def test_fast_hetero_collate_matches_pyg_batching():
    observations = [o.encoded for o in random_positions(6, seed=2)]
    fast = collate_hetero(observations)
    reference = Batch.from_data_list([to_hetero_data(o) for o in observations])
    net = small("gnn")
    for a, b in zip(net(fast), net(reference)):
        assert torch.allclose(a.float(), b.float(), atol=1e-5)


def test_recording_messages_gives_the_same_embeddings():
    net = small("gnn")
    batch = net.collate([o.encoded for o in random_positions(4, seed=3)])
    messages = []
    with torch.no_grad():
        plain, recorded = net.node_states(batch), net.node_states(batch, messages)
    assert len(messages) == len(net.convs)
    for a, b in zip(plain, recorded):
        assert all(torch.allclose(a[t], b[t], atol=1e-6) for t in a)
    for edge_type, (h, edge_index, alpha) in messages[0].items():
        assert alpha.shape == (edge_index.size(1),) and h.size(0) == batch[edge_type[2]].num_nodes


@pytest.mark.parametrize("arch", ARCHS)
def test_older_checkpoints_load_with_zero_weights_for_new_ability_features(arch, tmp_path):
    net = create_model(arch, hidden=32, num_layers=2)
    save_model(net, tmp_path / "model.pt")
    checkpoint = torch.load(tmp_path / "model.pt")
    checkpoint["state_dict"]["ability_in.0.weight"] = checkpoint["state_dict"]["ability_in.0.weight"][:, :-3]
    torch.save(checkpoint, tmp_path / "old.pt")
    weight = load_model(tmp_path / "old.pt").ability_in[0].weight
    assert torch.equal(weight[:, :-3], net.ability_in[0].weight[:, :-3]) and not weight[:, -3:].any()


@pytest.mark.parametrize("arch", ARCHS)
def test_checkpoints_from_before_outcomes_ignore_them(arch, tmp_path):
    """An older checkpoint loads with a zero outcome projection, so its scores don't change."""
    net = small(arch)
    save_model(net, tmp_path / "model.pt")
    checkpoint = torch.load(tmp_path / "model.pt")
    del checkpoint["state_dict"]["outcome_in.weight"], checkpoint["state_dict"]["outcome_in.bias"]
    del checkpoint["outcome_features"]
    torch.save(checkpoint, tmp_path / "old.pt")
    loaded = load_model(tmp_path / "old.pt")
    observations = [o.encoded for o in random_positions(4, seed=5)]
    with torch.no_grad():
        logits, _, _ = loaded(loaded.collate(observations))
        for o in observations:
            o.action_outcome[:] = 0
        blind, _, _ = loaded(loaded.collate(observations))
    assert not loaded.outcome_in.weight.any() and torch.allclose(logits, blind)


@pytest.mark.parametrize("arch", ARCHS)
def test_checkpoints_from_before_names_drop_the_v1_features_and_action(arch, tmp_path):
    """Older checkpoints saved no names and still had columns for activated abilities and the
    exhaust / ready grammar, and an ACTIVATE action."""
    net = create_model(arch, hidden=32, num_layers=2)
    state = net.state_dict()
    weight = state["ability_in.0.weight"]
    state["ability_in.0.weight"] = torch.stack(
        [weight[:, FEATURES.index(n)] if n in FEATURES else torch.ones(32) for n in LEGACY_FEATURES], 1)
    rows = state["action_type_emb.weight"]
    state["action_type_emb.weight"] = torch.stack(
        [rows[ActionType[n]] if n in ActionType.__members__ else torch.ones(32) for n in LEGACY_ACTIONS])
    torch.save({"arch": arch, "hparams": net.hparams, "state_dict": state}, tmp_path / "old.pt")
    loaded = load_model(tmp_path / "old.pt")
    assert torch.equal(loaded.ability_in[0].weight, net.ability_in[0].weight)
    assert torch.equal(loaded.action_type_emb.weight, net.action_type_emb.weight)
