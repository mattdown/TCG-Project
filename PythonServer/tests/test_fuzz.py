"""Random games with randomly generated abilities: the engine must never crash, get stuck or
break an invariant, whatever combination of abilities meets.

Set FUZZ_GAMES to play more games than the default, e.g. FUZZ_GAMES=2000 uv run pytest tests/test_fuzz.py
"""
import os
import random

import pytest

from src.cards.abilities import AbilitySampler
from src.cards.schema import Card
from src.game.engine import Game
from src.game.state import Continuation, Frame, Zone
from src.game.terms import ASPECTS

GAMES = int(os.environ.get("FUZZ_GAMES", 60))
MAX_STEPS = 5000


def ability_pool(rng: random.Random, n: int = 120) -> list[Card]:
    sampler = AbilitySampler(rng)
    cards = []
    for i in range(n):
        aspects = (ASPECTS[i % len(ASPECTS)],)
        if rng.random() < 0.3:
            cards.append(Card(f"A{i}", f"Action {i}", "action", aspects, rng.random() < 0.8, rng.randint(0, 5),
                              0, 0, 0, abilities=(sampler.ability("action"),)))
        else:
            abilities = tuple(sampler.ability("unit") for _ in range(rng.choice((0, 1, 1, 2))))
            cards.append(Card(f"U{i}", f"Unit {i}", "unit", aspects, rng.random() < 0.8, rng.randint(1, 6),
                              rng.randint(0, 5), rng.randint(1, 6), rng.randint(0, 3),
                              traits=(rng.choice(("Fisher", "Baker", "Knight", "Chef")),), abilities=abilities))
    return cards


def check_invariants(game: Game):
    s = game.state
    for p, ps in enumerate(s.players):
        zones = {Zone.DECK: ps.deck, Zone.HAND: ps.hand, Zone.PLAY: ps.play, Zone.ENERGY: ps.energy,
                 Zone.DISCARD: ps.discard}
        assert sum(len(z) for z in zones.values()) == 60
        for zone, uids in zones.items():
            assert all(game.card(u).zone == zone and game.card(u).owner == p for u in uids)
        for u in ps.play:
            assert game.card(u).card.type == "unit"
            assert 0 <= game.card(u).damage < game.stat(u, "health") or game.is_over
    assert all(e.uid in s.players[game.card(e.uid).owner].play for e in s.effects)
    assert all(isinstance(x, (Frame, Continuation)) for x in s.pending)
    if not game.is_over:
        assert game.legal_actions(), "a decision with no options"


@pytest.mark.parametrize("seed", range(GAMES))
def test_random_games_with_random_abilities(seed):
    rng = random.Random(seed)
    pool = ability_pool(rng)
    game = Game([rng.choice(pool) for _ in range(60)], [rng.choice(pool) for _ in range(60)], seed=seed)
    for step in range(MAX_STEPS):
        if game.is_over:
            break
        action = rng.choice(game.legal_actions())
        if step % 50 == 0:  # a clone must behave exactly like the original
            copy = game.clone()
            copy.step(action)
            game.step(action)
            assert copy.state == game.state
        else:
            game.step(action)
        check_invariants(game)
    assert game.is_over, f"game {seed} still running after {MAX_STEPS} steps"
