"""Encodes what one player sees at a decision point as plain NumPy arrays.

This is the framework-neutral form of the state graph. Each model converts it to its own
input: builder.py makes PyG HeteroData for the GNN, dense.py makes padded tensors for the
entity transformer. A JAX model could consume the same arrays.

Cards are your hand, your units and the opponent's units. The opponent's hand and both
decks are hidden, so they only appear as counts in the player features. Card features hold
only what a card *is* (no card ID), so the network can handle cards it has never seen.
The graph's edges aren't stored: they follow from card_owner and card_in_play.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from src.cards.schema import Card
from src.game.actions import Action
from src.game.engine import Game
from src.game.state import Phase, Zone
from src.game.terms import ASPECTS

KEYWORD_SCALE = {"guard": 1, "elusive": 1, "charge": 1, "duelist": 3, "armor": 2}
CARD_STATIC_DIM = 3 + len(KEYWORD_SCALE) + len(ASPECTS)
CARD_DYNAMIC_DIM = 10
PLAYER_DIM = 13
GLOBAL_DIM = 4


@dataclass
class EncodedObs:
    card_static: np.ndarray  # [N, CARD_STATIC_DIM] float32: what each card is
    card_dynamic: np.ndarray  # [N, CARD_DYNAMIC_DIM] float32: its current state
    card_owner: np.ndarray  # [N] int64: 0 = the observing player, 1 = the opponent
    card_in_play: np.ndarray  # [N] bool
    player: np.ndarray  # [2, PLAYER_DIM] float32: observing player first
    global_: np.ndarray  # [GLOBAL_DIM] float32
    action_type: np.ndarray  # [A] int64
    action_actor: np.ndarray  # [A] int64: card index, -1 when the action has no actor
    action_target: np.ndarray  # [A] int64: card index, -1 when the action has no target

    @property
    def num_cards(self) -> int:
        return len(self.card_owner)

    @property
    def num_actions(self) -> int:
        return len(self.action_type)


@dataclass
class Observation:
    encoded: EncodedObs
    actions: list[Action]  # in the same order as the encoded actions


@lru_cache(maxsize=None)
def card_static_features(card: Card) -> np.ndarray:
    """What the card is. The card encoder turns these into the card embedding."""
    return np.array([card.cost / 10, card.power / 10, card.health / 10,
                     *(card.keyword(k) / scale for k, scale in KEYWORD_SCALE.items()),
                     *(float(a in card.aspects) for a in ASPECTS)], dtype=np.float32)


def observe(game: Game, player: int) -> Observation:
    s = game.state
    me, opp = s.players[player], s.players[1 - player]

    card_uids = me.hand + me.play + opp.play
    decision = game.pending_decision()
    if decision and decision[0].source not in card_uids:  # e.g. an action card resolving from the discard pile
        card_uids.append(decision[0].source)
    node_of = {uid: i for i, uid in enumerate(card_uids)}
    instances = [game.card(uid) for uid in card_uids]
    marked = set(me.mulligan_marked)
    static = np.array([card_static_features(c.card) for c in instances], dtype=np.float32).reshape(-1, CARD_STATIC_DIM)
    dynamic = np.array([
        (c.zone == Zone.HAND, c.zone == Zone.PLAY, c.owner == player, c.exhausted, c.fresh,
         c.damage / 10, (c.card.health - c.damage) / 10, c.uid in marked,
         c.zone == Zone.PLAY and game.hidden(c.uid), game.frozen(c.uid))
        for c in instances], dtype=np.float32).reshape(-1, CARD_DYNAMIC_DIM)
    owner = np.array([c.owner != player for c in instances], dtype=np.int64)
    in_play = dynamic[:, 1].astype(bool)

    def player_features(p: int) -> list[float]:
        ps = s.players[p]
        cfg = game.config
        return [ps.health / cfg.hero_health, ps.mana / cfg.max_mana, ps.crystals / cfg.max_mana, len(ps.hand) / 10,
                len(ps.deck) / 30, len(ps.discard) / 30, len(ps.play) / cfg.max_board,
                sum(game.can_attack(u) for u in ps.play) / cfg.max_board,
                sum(game.stat(u, "power") for u in ps.play) / 30, ps.spare_spore, s.active_player == p,
                ps.mulligan_done, ps.fatigue / 10]

    actions = game.legal_actions() if s.decision_player == player else []
    encoded = EncodedObs(
        card_static=static,
        card_dynamic=dynamic,
        card_owner=owner,
        card_in_play=in_play,
        player=np.array([player_features(player), player_features(1 - player)], dtype=np.float32),
        global_=np.array([s.turn / 50, s.phase == Phase.MULLIGAN, s.phase == Phase.MAIN, s.decision_player == player],
                         dtype=np.float32),
        action_type=np.array([a.type for a in actions], dtype=np.int64),
        action_actor=np.array([node_of.get(a.card, -1) for a in actions], dtype=np.int64),
        action_target=np.array([node_of.get(a.target, -1) for a in actions], dtype=np.int64),
    )
    return Observation(encoded, actions)
