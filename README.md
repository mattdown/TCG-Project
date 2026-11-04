# TCG-Project

AI playtesting for trading card game design. Cards are generated from a hand-written grammar, and an
agent trained by self-play, a graph neural network that reads what each card does, plays them so designers
can see which cards are too strong or too weak.

This repository goes with a blog series:
[part 1, generating cards and a GNN agent](https://mattdown.ai/posts/tcg-part-1/). The blog is the short,
visual version. This README has the details.

- **Part 1:** a card generator, an agent that can play cards it has never seen, and a basic balance pass.
- **Part 2:** balancing the set against the best decks rather than the average one
  ([docs/stage-2-research-plan.md](docs/stage-2-research-plan.md)).
- **Part 3:** using the tools to make an original game of its own.

Everything is synthetic: no real cards, names or text from any existing game. All game terms are
placeholders, so the game can be renamed in one place (`PythonServer/src/game/terms.py`).

## How it works

### The loop

1. **Generate** cards from the grammar.
2. **Playtest:** the agent plays thousands of games with them.
3. **Measure** the set against design metrics: is each card worth its cost, do cards work together, are there
   infinite combos, are any two cards too alike? Part 1 covers only the first.
4. **Tune** the cards (re-cost them, change numbers, replace them) and go round again.

Designers choose the metrics. The agent can say how strong a card is, not whether it's fun or easy to read, so
this is a tool for designers, not a replacement for them.

### Card generation

Every ability is a tree ([docs/technical-plan.md](docs/technical-plan.md), section 3). The root is a
trigger ("when you play this unit", "at the start of your turn", "whenever an enemy unit is defeated") or a
static rule. Below it are steps: choose a target, deal damage, draw cards, "if it was defeated, …",
"you may …, if you do …", "choose one: …". The grammar is closed, so every tree is an ability the engine can
run and that turns into card text.

Most random trees are bad, so each draw goes through tests that look only at the tree's shape, never at
particular cards ([docs/ability-generation.md](docs/ability-generation.md)):

1. **Grammar:** is it legal?
2. **Quality:** is it small enough to read, are its steps connected, is any "choose one" option strictly
   worse than another, does it narrow its targets so far it would almost never fire?
3. **Card:** with stats and a cost, does it fit on a card?
4. **Variety:** does the set already have too many abilities of this shape?

The 200-card set in `PythonServer/cardsets/set_200.json` took 1,201 draws.

### Why not an LLM?

An LLM has read every Magic and Hearthstone card, so without strong constraints its cards drift towards ones
that exist. It also can't tell you if a card is balanced: it can guess, but it can't play 10,000 games. Here
the cards are original by construction, and the judging is done by an agent that has played them. An LLM
may still be useful later for naming cards.

### The agent

The game state is a heterogeneous graph ([`src/graph/`](PythonServer/src/graph)): nodes for the game,
each player, each card, and each step of each card's ability tree. Edges say how they relate: a card belongs
to a player, a unit faces an enemy unit, an ability step is part of a card, "it" refers to an earlier
choice. A card is described only by what it is (24 features: cost, stats, keywords, state, plus its ability
graph), never by an ID, so a new card is a new graph built from familiar parts.

The network ([`src/model/gnn.py`](PythonServer/src/model/gnn.py)):

- an encoder per node type, to 128 numbers;
- 4 message-passing layers, each a `HeteroConv` of [GATv2](https://arxiv.org/abs/2105.14491) attention
  (4 heads) with its own weights per edge type, then ReLU, a residual connection and LayerNorm;
- a **policy** head that scores each legal action from the nodes it involves, so it handles any number of
  actions and any card;
- a **value** head that reads the game and player nodes.

Training is PPO self-play ([`src/training/`](PythonServer/src/training)). The reward is +1 for a win and
−1 for a loss. Some games are against frozen earlier versions and a hand-written player, so the agent doesn't
just learn to beat its current self. The hand-written player plays its most expensive affordable card, attacks
a unit when it can kill it and survive, and otherwise attacks the hero.

It runs on a laptop. Self-play gives roughly 5–10 games a second on an M-series Mac across 10 processes. An
iteration is 64 games and takes about 20 seconds on MPS, and the agent in the blog had a few hours of
training.

| Benchmark, `set_200` (never trained on), 400 games | Win rate |
|---|---|
| GNN agent vs hand-written player | 69% (275–125) |
| hand-written player vs random | 97% |
| GNN agent vs random | 99.5% |

The test cards come from the same grammar as the training cards. A new kind of effect needs the grammar
extending and the network training on it.

The agent is not superhuman, and doesn't need to be: to measure a design it should play roughly as people
do. It has no belief model of the opponent's hand. For pricing single cards that's probably fine, and part 2
needs a stronger player to find the strongest decks.

### Balance pass (part 1)

Each card starts with a cost from a rough value table: points for power, health, each keyword and each
effect. [`scripts/experiments.py`](PythonServer/scripts/experiments.py) then tests the table by playing
decks against altered copies of themselves, 800 games per comparison:

- `abilities`: abilities removed; abilities' points put back into stats ("refunded"); actions swapped for
  vanilla units of the same cost.
- `scale` and `effects`: the price scale, overall or per kind of effect, at which the real deck wins half its
  games.
- `fire`: how often an ability does anything when played.

The first table charged far too much for abilities: a deck lost three games in four to its own copy with the
abilities traded for stats, and only about half the abilities did anything when played. After re-pricing from
the measured values, regenerating and fine-tuning for a few rounds, a deck with abilities wins 55–59% against
the refunded copy, and actions are roughly worth their cost.

Known problems in the current set:

- Card draw and healing are too cheap (Mire Gossip: 1 mana, draw 4 or deal 2). Each effect is priced by its
  worth in an average random deck, but players build the best deck, where extra cards are worth much more.
  Part 2 balances against the strongest decks.
- A "this turn" health buff at the start of your turn does nothing useful: it expires at the end of your
  turn, and units attack only once a turn. Health buffs should be able to last through the opponent's turn.
- Actions that summon a single unit are just unit cards with an extra step.

### Related work

- **Chimera** (Google Stadia, 2021): ML agents playtested and balanced a card game prototype.
  [Google Research blog](https://research.google/blog/leveraging-machine-learning-for-game-development/).
- **Hearthstone deck spaces:** Fontaine et al., *Mapping Hearthstone Deck Spaces through MAP-Elites with
  Sliding Boundaries*, GECCO 2019. [arXiv:1904.10656](https://arxiv.org/abs/1904.10656).
- **Hearthstone rebalancing:** de Mesentier Silva et al., *Evolving the Hearthstone Meta*, IEEE CoG 2019.
  [arXiv:1907.01623](https://arxiv.org/abs/1907.01623).
- **Generated Magic cards:** neural networks trained on Magic's card text have written new cards for years.

What's different here: the cards come from a grammar rather than an existing game; the agent reads each
card's ability tree, so it plays unseen cards without retraining from scratch; the whole set (aiming for about
3,000 cards) is in the loop; and the goal is a new game.

## The game

Rules v2, Hearthstone-style ([docs/technical-plan.md](docs/technical-plan.md), section 2). Two players, each
with a hero on 30 health and a 30-card deck (up to 2 copies of a card). The first player starts with 3 cards,
the second with 5 and the **Spare Spore** (once per game: +1 mana that turn); both may mulligan once. Each
turn: gain a mana crystal (up to 10) and refill them all, draw a card, then any number of actions:

- **Play** a card by paying its cost. A unit can't attack the turn it's played. At most 7 units in play.
- **Attack** with each unit once per turn: an enemy unit (both deal their power as damage) or the enemy hero.
  Damage on units stays between turns.

A hero at 0 health loses. Drawing from an empty deck deals 1 damage, then 2, then 3…; a card drawn into a full
hand (10) is discarded. Turn 100 is a draw.

Keywords: **Guard** (must be attacked first), **Elusive** (can't be attacked or chosen by enemy abilities
until it attacks), **Charge** (can attack at once), **Duelist +N** (+N power while attacking), **Armor +N**
(takes N less damage from attacks).

The theme is mushrooms with jobs ([docs/theme.md](docs/theme.md)): jobs work like tribes, and the six
aspects (Ember, Bog, Moss, Meadow, Glow, Frost) are habitats. For now aspects are only colours.

## Repository layout

```
PythonServer/     game engine, agents and training (Python 3.12, uv)
  src/cards/      card schema, generators, ability sampler / validator / card text, costing
  src/game/       rules engine, decks, terms.py (every player-facing name)
  src/graph/      state → arrays (encode.py) → PyG graphs (builder.py) or dense tensors (dense.py)
  src/model/      the GNN (default) and an entity transformer
  src/agents/     random, heuristic and neural agents; match runner
  src/training/   PPO self-play
  src/server/     JSON game session for the Unity client
  scripts/        generate_cards, train, benchmark, experiments, server
  cardsets/       generated card sets (JSON, one card per line, with Markdown checklists)
  tests/          pytest
TCGClient/        Unity 6 client (6000.3.10f1): a thin view, the server owns every rule
Blog/             the blog's interactive pages and their tests
docs/             technical plan, ability generation log, client protocol and design, theme, diagrams
```

## Running it

Needs [uv](https://docs.astral.sh/uv/). From `PythonServer/`:

```
uv sync
uv run pytest
uv run python -m scripts.generate_cards --kind set --count 200   # cardsets/set_200.json
uv run python -m scripts.train --iterations 100 --device mps      # models/tcgnet.pt
uv run python -m scripts.benchmark                                # round-robin win rates
uv run python -m scripts.experiments abilities                    # the balance tests above
uv run python -m scripts.server                                   # tcp://*:5555 for the Unity client
```

Trained checkpoints aren't in git (`models/` is ignored), so train one first, or download `tcgnet.pt` from
the [releases page](https://github.com/mattdown/TCG-Project/releases) into `PythonServer/models/`.

### The blog's demos

From the repository root. Each writes a self-contained page to `Blog/build/`:

```
uv run --project PythonServer python Blog/design_loop.py                 # the design loop
uv run --project PythonServer python Blog/card_generation_visualiser.py  # one card's path through the grammar
uv run --project PythonServer python Blog/gnn_visualiser.py              # the GNN, in three parts (needs a model)
uv run --project PythonServer python Blog/card_lab.py                    # the card lab (--export for a page)
uv run --project PythonServer pytest Blog/tests
```

### Playing in Unity

Start the server, open `TCGClient/` in Unity 6000.3.10f1 and press Play in `Scenes/Main.unity`. The client
talks JSON over ZeroMQ ([docs/client-protocol.md](docs/client-protocol.md)); its drop zones, previews and
animations all come from the server. The GNN button overlays the state graph on the board.

## Licence and credits

The code is under the [MIT licence](LICENSE). Fonts and third-party packages keep their own licences.

- Fonts: Outfit, Marcellus SC, Nunito, Lilita One (SIL Open Font License), DejaVu Sans; licences in
  `TCGClient/Assets/Fonts/`.
- Unity packages: NetMQ (via NuGetForUnity), DOTween (free), TextMesh Pro.
- Card art was generated with Gemini, from a written scene per card (`TCGClient/Tools/card_art/`).
- AI was used to help build this project, write its docs and generate the game's assets.
