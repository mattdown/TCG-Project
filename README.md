# TCG-Project

Using graph neural networks and self-play to design a novel, balanced set of cards for a
trading card game. The rules engine and ML training live in Python; Unity handles the
playable client and rendering.

See [docs/technical-plan.md](docs/technical-plan.md) for the design of the rules engine,
state graph and model. All game terms (VP, energy, units, duels…) are placeholders.

## Repository layout

```
PythonServer/          Game engine, agents and training (Python, managed with uv)
  src/cards/           card schema, card generators, ability sampler / validator / text
  src/game/            rules engine, random deck builder, placeholder terms
  src/graph/           state → NumPy arrays (encode.py), then PyG graphs (builder.py)
                       or padded dense tensors (dense.py)
  src/model/           policy-value networks: heterogeneous GNN and entity transformer
  src/agents/          random, heuristic and neural agents; match runner
  src/training/        PPO self-play
  src/server/          game session behind the Unity server
  scripts/             entry points (below)
  cardsets/            generated card sets (JSON, one card per line)
  models/              trained checkpoints (gitignored)
  tests/               pytest suite
docs/                  technical plan, client protocol, draw.io diagrams
TCGClient/             Unity 6 client (6000.3.10f1)
Blog/                  tools and pages for the blog: card lab and explorer, ability tree animation
```

## Python setup

Requires [uv](https://docs.astral.sh/uv/). Run every command from `PythonServer/`:

```
cd PythonServer
uv sync
```

| Command | What it does |
|---|---|
| `uv run python -m scripts.generate_cards` | Writes a 200-card set: units with keywords to `cardsets/keywords_200.json` (the default set), or `--kind vanilla` for stats only (`--count`, `--seed`). `--kind set --count N` writes `cardsets/set_N.json`: a full set from the generation pipeline (about 4% vanilla and 25% keyword-only neutral units, a quarter action cards, the rest units with one ability; `--vanilla-share`, `--keyword-share`, `--action-share`), plus a Markdown checklist. `--kind coverage` writes `cardsets/coverage.json`: a small set that uses every ability building block at least twice (about a quarter action cards), plus a Markdown checklist |
| `uv run --project PythonServer python Blog/card_lab.py` (from the repository root) | Card lab: generates cards with abilities and shows every stage of the pipeline, including what was thrown away and why ([docs/ability-generation.md](docs/ability-generation.md)). Opens a web page; `/explorer` generates one card at a time and shows the path it took through the grammar. `--text` prints to the terminal; `--export lab.html` / `--export-explorer explorer.html` write self-contained pages |
| `uv run python -m scripts.train` | PPO self-play on random decks; writes `models/tcgnet.pt` and `models/tcgnet_best.pt`. Every `PPOConfig` field is a flag, e.g. `--arch transformer --iterations 200 --device mps` |
| `uv run python -m scripts.benchmark` | Round-robin win rates: random, heuristic and neural agents (`--models a.pt b.pt` to compare checkpoints) |
| `uv run python -m scripts.server` | ZeroMQ server for the Unity client on `tcp://*:5555`. `--cards cardsets/coverage.json` to check abilities in Unity (`new_game` takes a `scenario`) |
| `uv run pytest` | Runs the tests |

## Current rules

Rules v2, Hearthstone-style ([docs/technical-plan.md](docs/technical-plan.md) section 2).
Two players, each with a hero on 30 health and a 30-card deck (up to 2 copies of a card).
Aspects are only colours for now; later a deck will be one aspect's cards plus neutral cards,
like a Hearthstone class. The first player starts with 3 cards, the second with 5 and the **Spare
Spore** (once per game: +1 mana that turn); both may mulligan once. Each turn: gain a mana
crystal (up to 10) and refill them all, your units can attack again, draw a card, then any
number of actions:

- **Play** a card by paying its cost in mana. A unit is *fresh* until your next turn and
  can't attack yet. At most 7 units in play.
- **Attack** with each unit once per turn: an enemy unit (both deal their power as damage) or
  the enemy hero (who takes the unit's power as damage). Damage on units stays between turns;
  a unit is defeated when its damage reaches its health.

A hero at 0 health loses. Drawing from an empty deck deals 1 damage, then 2, then 3…; a card
drawn into a full hand (10) is discarded. Turn 100 is a draw.

Keywords:

- **Guard:** enemy units must attack a Guard unit if they can.
- **Elusive:** can't be attacked or chosen by enemy abilities until it attacks.
- **Charge:** can attack the turn it's played.
- **Duelist +N:** +N power while attacking.
- **Armor +N:** takes N less damage from attacks.

**Abilities** follow the grammar in [docs/technical-plan.md](docs/technical-plan.md)
section 3: triggered (when played, attacks, attacks the enemy hero, is defeated, start or end
of turn, …), on-resolve (action cards) and static. The engine compiles each ability to a decision graph and resolves it on a
stack; choices inside abilities (choose a target, "you may", "choose one") are ordinary
decisions. The default card set has no abilities yet; `set_200`, the coverage set, the
tests and the fuzz test (`FUZZ_GAMES=2000 uv run pytest tests/test_fuzz.py`) use generated ones.

## Unity client protocol

The server speaks JSON over a ZeroMQ REQ/REP socket. Request types: `card_set`,
`new_game`, `state`, `act`, `ai_move`, `ai_turn`. See
[docs/client-protocol.md](docs/client-protocol.md) for example responses, the state fields
and the client flow. The state is always from the human player's point of view: the AI's
hand and both decks are hidden.
