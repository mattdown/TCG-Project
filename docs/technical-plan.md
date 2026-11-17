# Technical plan

The design of the game, the engine, the state graph, the model and training, as they are now.
Open work is in [roadmap.md](roadmap.md), measurements in [results.md](results.md), and part 2's
plan (balancing against the best decks) in [stage-2-research-plan.md](stage-2-research-plan.md).

The project has three parts:

- **a.** Define a trading card game's rules and represent its state as a graph a GNN can
  learn from.
- **b.** Train an agent to play it through self-play.
- **c.** Generate a balanced, interesting set of ~3000 cards.

The card pool is **entirely synthetic**. No cards from any existing game are used. The
rules follow the broad structure of **Hearthstone** (rules v2, section 2): mana that grows
each turn, units that attack each other or the enemy hero, and a hero whose health is the win
condition. More people know it than any other card game, which matters for the players and for
the blog series that documents the project. The terms are our own placeholders. The aim is to
show that a whole card set can be generated from scratch once the rules are defined. This also
keeps the project free of card licensing issues.

![System overview](architecture_overview.png)

The diagram source is [architecture.drawio](architecture.drawio). Page 1 is the system
overview above; page 2 shows the state graph in detail (section 5); page 3 is the ability
grammar: every ability the generator can produce (section 3).

## Placeholder glossary

All names are placeholders until the game has a name and theme. They live in one constants
module (`src/game/terms.py`), so a rename is a single change.

| Placeholder | Meaning |
|---|---|
| **Hero** | Each player's character, with 30 health. A hero at 0 health loses. (The theme may call it something like a Grand Mushroom.) |
| **Mana** | Paid to play cards. Each turn you gain an empty mana crystal (up to 10), then all of them refill |
| **Unit** | A card that stays in play: cost, power, health, traits (jobs) |
| **Action** | A one-shot card: its ability resolves, then it goes to the discard pile |
| **Attack** | A unit fights an enemy unit or the enemy hero, once per turn. Both sides deal their power as damage (heroes deal none back) |
| **Fresh** | Played this turn: can't attack yet |
| **Defeated** | Damage ≥ health: the unit goes to the discard pile |
| **Aspects** (6) | Habitats. Planned: Hearthstone-style classes (a deck is one aspect's cards plus neutral cards; the hero takes the deck's aspect). For now only colours: decks draw from the whole set |
| **Traits** | Unit tags that abilities can refer to: jobs (docs/theme.md). Decks focus on two jobs |
| **Keywords** | Guard, Charge, Duelist +N, Armor +N, Elusive |

## 1. Design principles

1. **A symbolic engine runs the rules; the GNN reads them.** The engine decides what is
   legal and what happens. The graph exposes the rules' *structure* to the network: what each
   ability does, which cards it can target, which effects are active. Generated cards need
   exact, trusted behaviour that a learned model can't guarantee.
2. **One card schema, two consumers.** Each card is pure data: stats, keywords and ability
   trees in a typed DSL. The engine *interprets* the DSL to play the card; the graph builder
   *compiles* the same tree into a subgraph for the network. A new card needs no new code.
3. **No per-card identity.** The network never sees a card ID or a learned per-card
   embedding, only what the card *is*. This lets it handle cards it has never seen, which
   part c depends on.
4. **Train on a randomized pool.** The agent always trains on a wide, randomized pool of
   synthetic cards and decks, so it learns the card space rather than particular cards.
5. **The generator proposes and the cost model prices.** The generator's job is
   *interesting* effects. A cost model learned from the agent's games sets cost and stats,
   which is where most of the balancing happens.

## 2. Rules scope (v2)

- **Players and decks.** Two players, 30-card decks (up to 2 copies of a card). Planned: one
  aspect's cards plus neutral cards, the hero taking the deck's aspect. For now aspects are only
  colours and decks draw from the whole set (`ONE_ASPECT` in `src/game/decks.py`). Each deck
  focuses on two jobs: 70% of its units have one of them (`FOCUS_JOBS`, `FOCUS_SHARE`), so job
  synergies come up; actions are drawn as often as without the focus.
  Each player has a hero with 30 health. A hero at 0 health loses; if both reach 0 at once,
  it's a draw.
- **Start.** The first player draws 3 cards, the second 5. Each player may replace any of
  their opening cards once (mulligan). The second player also gets the **Spare Spore**: once per
  game, gain 1 mana for that turn. This is Hearthstone's answer to the first player's tempo.
  With Hearthstone's 4 cards, the first player won 58–59% of mirror games; with 5, 49% for the
  league model and 54% for the heuristic agent (`scripts/experiments.py first`, 2026-10-22).
  Re-measure once card costs are learned.
- **Turn.** Start of turn: gain an empty mana crystal (up to 10), refill all crystals, units
  can attack again, "start of turn" effects trigger, draw a card. Then the main phase, then
  "end of turn" effects.
- **Main phase actions:**
  - play a card by paying its cost in mana. An action card whose ability opens by choosing a
    card can't be played when there's nothing to choose (in every option, for "choose one"); a
    "choose one" only offers the options that have something to choose (all of them, if none do)
  - attack with a unit
  - end the turn
- **Attacks.**
  - A unit can attack once per turn, but not on the turn it is played (Charge allows it).
  - It attacks an enemy unit or the enemy hero.
  - If the enemy has a Guard unit, an attack must target a Guard unit.
  - Both deal their power as damage to each other; a hero deals none back.
  - Damage on units stays between turns.
- **Limits.**
  - At most 7 units in play each.
  - At most 10 cards in hand: a card drawn into a full hand is discarded.
  - Drawing from an empty deck deals 1 damage to your hero, then 2, then 3, and so on.
- **Card types.** Unit and Action now; Item later.
- **Keywords** (the keyword list is data, so adding one is an engine change plus a feature
  column):

  | Keyword | Effect |
  |---|---|
  | Guard | Enemy attacks must target a Guard unit while there is one |
  | Charge | Can attack the turn it's played |
  | Duelist +N | +N power while attacking |
  | Armor +N | Takes N less damage from attacks |
  | Elusive | Can't be attacked or chosen by enemy abilities until it attacks |

**Aspects and jobs.** Aspects are classes (deckbuilding and, later, a strategic identity);
jobs are tribes that cross aspects (the synergies abilities refer to). Vanilla and keyword-only
units are neutral. Aspect identity is designed (decided 2026-11-15): each aspect gets a
generation vector, a shared base grammar plus sparse per-aspect weight offsets, so the
generator makes different kinds of cards for each (stage-2 research plan, 4G). Clustering the
cards by what they do, so identities emerge instead, is left for later. Until then ability cards
get a random aspect and the deck rule is off, so aspects are only colours.

**Layered rollout.** Each layer adds DSL building blocks and engine support, and is
followed by a bootstrapping round (section 10). Done: vanilla units, keywords, triggered and
static abilities, actions. Still to come: items, then part 3's mechanic of our own.

**Rules v1.** Until 2026-10-21 the rules followed Disney Lorcana: ink and energy sources,
questing for lore (VP), challenging only exhausted characters, activated (⟳) abilities, sites,
chants and Evolve, and the keywords Berserk, Inspire, Veiled, Fragile, Chanter and Choir. v2
switched to Hearthstone's structure because more players and readers know it. VP effects became
hero damage and healing, "can't ready" became freeze, and the scoring trigger became "whenever this
unit attacks the enemy hero". Some dropped mechanics may come back as part 3's twist.

## 3. Card schema and ability DSL

```jsonc
{
  "id": "gen-000123",           // for bookkeeping only, never shown to the network
  "name": "…",                  // with the subtitle and habitat, also keys the card's art
  "subtitle": "…",              // tells apart versions of the same character
  "type": "unit",               // unit | action (item later)
  "aspects": ["aspect_1"],
  "cost": 4, "power": 3, "health": 4,
  "traits": ["trait_a"],
  "keywords": {"charge": true, "duelist": 2},
  "abilities": [ /* DSL trees, below; the generator makes one per card */ ]
}
```

**Abilities are written as trees and run as decision graphs.** Each ability exists in two
forms:

1. **Authoring form: a nested tree, stored in the card JSON.** This is what gets written by
   hand, generated, validated and rendered as card text. Trees are easy for all four.
2. **Decision graph, compiled once per card from the tree.** The engine executes it and the
   GNN reads it. Each step becomes a node. Control edges say what happens next. Data edges
   connect a choice to every later step that refers to it ("it", "that unit", "if you do").

Static abilities and keywords aren't sequences of steps. They are rules applied whenever
stats or legality are calculated, so they stay declarative and are never compiled into a
flow.

![Ability grammar](architecture_ability_grammar.png)

**Grammar (authoring form).** It is small, typed and closed. Page 3 of the diagram lists
every alternative and value range: it is the full space of abilities the generator can
produce.

```
Ability    := triggered(Trigger, [Condition], Steps)
            | on_resolve(Steps)                              // action cards
            | static([Condition], Modifier+)                 // declarative, not compiled to a flow
Steps      := Step+                                          // 1–4 steps, run in order
Step       := choose(count, chooser, Filter, optional?) as Name    // decision point
            | Effect
            | if(Condition) then Steps [else Steps]
            | may(Steps) [if_you_do Steps]                   // yes / no decision point
            | choose_one(Steps, Steps)                       // decision point
            | for_each(Target) Steps
Effect     := op(Amount?, Target, [Duration])
            | buff(power +n, health +n, Target)              // lasting, until the unit leaves play
            | summon(n, Token)                               // tokens enter play for you, fresh
Token      := {name, power, health, keyword?, trait?}       // a unit defined inside the ability (src/cards/tokens.py)
Target     := Name | this | all(Filter) | you | opponent | owner_of(Name)
Trigger    := event + source (this | Filter)
Condition  := defeated(Name) | in_play(Name) | count(Filter) ≥ n | behind_on_health | your_turn
            | this_is(attacking | defending | damaged)
Modifier   := Subject gets stat ±Amount [while Condition]
            | Subject gains Keyword [while Condition]
            | cost(−1) for Filter
Subject    := this | all(Filter)
Amount     := n | k per count(Filter), up to cap | stat_of(Name)
Filter     := {type?, owner?, zone?, trait?, cost_cmp?, damaged?, keyword?, not_this?}
Duration   := this_turn | until_your_next_turn | until_their_next_turn | while_this_in_play | permanent
```

This is the design space, not what is generated today. The generator covers part of it, the
engine runs a little more, and `for_each`, `until_their_next_turn`, `permanent`, optional
choices, `cost_cmp` and the keyword filter aren't built yet: see "What the generator
can say" in [ability-generation.md](ability-generation.md).

A `Name` can only refer to a choice made earlier in the same ability. That keeps every tree
valid and every reference renderable as text.

**Scaling amounts.** Wherever an effect or modifier takes a number, it can take an `Amount`
instead. That covers "deal 1 damage for each Elf in play" and "deal damage equal to its
power". A static ability can scale too: "While this unit is attacking, it gets +1 power for
each Elf in play (up to +4)" is `static(this_is(attacking), this gets power +(1 per
count(Elf in play), up to 4))`. Statics are recalculated live, so the count is taken when the
bonus is needed. A triggered version ("when this unit attacks, it gets +1 power this turn for
each Elf") takes a snapshot instead. In the state graph, a scaling amount is its own small
node with `matches` edges to the cards it is counting.

**Generation constraints.** These are applied while sampling, then checked again before a
card is accepted:

- **Scope.** References only point to earlier choices in the same ability.
- **Types.** An effect's target has the right type: unit effects target units, player
  effects target players.
- **Polarity.** Every effect either helps or hurts its target. Helpful effects target your
  side, harmful ones the opponent's. The reverse is allowed only inside `may … if_you_do`,
  as a cost ("You may deal 2 damage to one of your units. If you do, draw 2 cards.").
  Only units are generated with these: an action is played to be used, so it never says "you may".
- **No runaway abilities.** Abilities are static or triggered (on-resolve for actions); units
  only attack. There is no `ready` effect, so no unit attacks twice.
  Attack loops end by themselves, because units take damage.
- **Abilities must be able to matter.** These checks look at the whole card, not just the
  ability, and also run whenever a card is created:
  - Abilities that only work once the unit is damaged ("while this unit is damaged…", "remove
    damage from this unit") need at least 2 health, because 1 damage defeats a 1-health unit.
  - A unit is fresh the turn it's played, so "when you play this unit, it gets +power this
    turn" only helps with Charge. It has no damage yet, so "remove damage from this unit" when
    played never helps either.
  - A "this turn" bonus from an end-of-turn ability would end at once, so those bonuses last
    until the start of your next turn instead.
  - Granted Guard and Armor protect against the opponent, so they last until the start of
    your next turn. Granted Duelist lasts this turn. Charge and Elusive are never granted:
    they only matter before a unit first acts.
  - Giving a unit a keyword without a number that it already has does nothing.
  - A lasting buff on this unit when it's played is just more stats, so it isn't generated.
  - Summoned tokens stop at a full board. A token that leaves play is gone: returned to hand,
    it goes to the discard pile instead.
- **Size.** At most 2 abilities per card, 4 steps per sequence, nesting depth 2, and 2
  choices per ability. The generator currently makes one ability per card and applies a
  stricter complexity budget, plus quality tests that look at the tree's shape: see
  [ability-generation.md](ability-generation.md).
- **Ranges.** Every number comes from its range (e.g. `deal_damage` 1–5). A scaling amount
  must have a cap, so the card's strength is bounded and the cost model can price it.
- **Validation pipeline:**
  1. Render the card text.
  2. Compile the decision graph.
  3. Simulate in self-play. The ability must change the game state and never loop.
  4. The cost model sets the card's cost and stats (auto-costing).

**Granularity.** The building blocks set the design space, so generated abilities are new
combinations, not new mechanics. Fine-grained, independent building blocks (events, zones,
counters, conditions) widen that space but make generation harder; template-sized blocks do
the opposite. Start template-sized and break blocks apart as the generator improves.

**Two examples in authoring form:**

```jsonc
// "When you play this unit, choose an opposing unit and deal 2 damage to it. If it's defeated, draw a card."
{"kind": "triggered", "trigger": {"event": "on_play", "source": "this"},
 "steps": [
   {"choose": {"count": 1, "chooser": "you", "filter": {"type": "unit", "owner": "opponent"}}, "as": "it"},
   {"effect": "deal_damage", "amount": 2, "target": "it"},
   {"if": {"defeated": "it"}, "then": [{"effect": "draw", "amount": 1, "target": "you"}]}]}

// "Remove all damage from your trait A units."
{"kind": "on_resolve",
 "steps": [{"effect": "remove_damage", "amount": "all",
            "target": {"all": {"type": "unit", "owner": "you", "trait": "trait_a"}}}]}
```

**The decision graph.** The first example compiles to:

```
ENTRY(on_play) → CHOOSE(1 opposing unit, as "it") → EFFECT(deal 2 damage) → IF(defeated?) ─yes→ EFFECT(draw 1)
                        ║                                   ▲                    ▲          └─no──→ END
                        ╚══════════ uses "it" ══════════════╩════════════════════╝
```

- **Node types:**
  - `entry`
  - `choose`, `may`, `choose_one`: the decision points
  - `if`, `effect`, and `for_each` (not built yet)
  - `end`
- **Edges:**
  - control: `next`, `then`, `else`, `option`, `if_you_do`
  - data: `uses`, from a `choose` (or, once built, a `for_each`) to every step that refers to its name
- **Filters** are features of the node that uses them: a `choose`, an `effect` targeting
  `all(…)`, or an `if` testing `count(…)`.

Why this form works for both consumers:

- **References are edges.** "It" is a data edge, so no variable scoping is needed at run time.
- **Resolution state is plain data.** A pending ability is (source card, ability, current
  node, chosen values). The engine keeps a stack of them. The game can be cloned, saved or
  sent to the Unity client in the middle of resolving an ability, and porting to C# is
  straightforward. A recursive interpreter built on Python generators couldn't be
  deep-copied, and search needs `clone()`.
- **Decision nodes are the engine's decision points.** At a `choose`, `may` or `choose_one`
  node the engine pauses and offers the legal options. The policy head gets that node as its
  *context*, so the network knows exactly which step of which ability it is deciding.
- **The GNN reads the graph directly** as the card's ability subgraph.

**Card sources.** Every card is generated, even for tests (`scripts.generate_cards`):

- **Coverage set** (`cardsets/coverage.json` + a checklist): every building block of the grammar
  at least twice, for checking the engine and the client.
- **Training and evaluation sets:** `set_1000` to train on; `heldout_200` and `armor_heavy` for
  cards the agent has never seen (results.md).
- **Generated sets:** the output of part c.

## 4. Rules engine (`src/game/`, `src/cards/`)

- **State:** players (hero health, mana crystals and mana, deck, hand, discard, fatigue,
  Spare Spore), cards in play (attacked this turn, damage, fresh, revealed for
  Elusive), and active effects (op, target, source, expiry).
- **Decision points.** The engine pauses whenever a player must choose: main-phase action,
  target selection, optional "may" effects, ordering of simultaneous triggers, mulligan.
  Every decision is "choose one of these N options", and each option refers to graph nodes.
- **Events and triggers:** an event bus feeds a trigger queue, resolved in rules order.
  Durations are stored as active effects and expired by the turn structure.
- **Ability resolution:** a stack of pending abilities, each (source card, ability, current
  node, chosen values). The engine walks each decision graph and pauses at `choose`, `may`
  and `choose_one` nodes, which become ordinary decision points. Static abilities are
  applied whenever stats or legality are calculated.
- **Determinism:** all randomness comes from a seeded RNG. `clone()` (a hand-written copy,
  about 6× faster than `deepcopy`) supports previews and search. `determinize(player, rng)`
  re-deals what the player can't see on a copy: their own deck order, the opponent's hand and deck
  (pooled and dealt back in the same sizes) and the random numbers, so search never sees a draw
  or the opponent's hand. The pool is the opponent's real remaining cards, so their deck list
  leaks; a belief over unseen deck lists is later.
- **Safety caps:** a turn allows at most 50 plays and attacks; after that only ending the turn is
  legal. Abilities past 100 in a turn fizzle. Two copies of "at the end of each turn, summon…"
  can't loop forever (`GameConfig.max_turn_actions`, `max_turn_abilities`).
- **Performance:** start in pure Python for correctness, profile once self-play runs, then
  move hot paths to a faster implementation. Because the DSL is data, a C# interpreter for
  the Unity client can later load the same card files.

## 5. State graph (`src/graph/`)

![State graph](architecture_state_graph.png)

One heterogeneous graph per player per decision point (`torch_geometric.data.HeteroData`):

| Node type | Features |
|---|---|
| `card` (each card instance that is visible) | card embedding from the card encoder (cost, power, health, keywords; no aspect, since aspects are only colours for now) + zone, attacked, damage, fresh, hidden (Elusive), frozen, owner (relative: you / opponent) |
| `ability` (`src/graph/abilities.py`): one per step of each visible card's abilities: `entry`, `choose`, `may`, `choose_one`, `if`, `effect`, `end`, and one `modifier` per static modifier | node kind + ability kind + trigger event + condition + parameters (op, amount, scaling, stat and delta, buff power and health, token power and health, keyword, duration, target kind, count, chooser) + the fields of the node's Filter, numbers normalised; a flag on the node currently being resolved. 90 features; new ones are appended, so older checkpoints load with zero weights for them |
| `player` (you, opponent): the heroes | health, mana, crystals, hand size, deck size, units and how many can attack, Spare Spore, fatigue, aspect (the class, once aspects are classes) |
| `global` | turn number, phase, whose turn |
| actions (scored by the policy head, not graph nodes) | action type, actor, target, context and option nodes, plus **action outcomes**: the action tried on a copy of the game, keeping only what's visible on the board (damage dealt and taken, units defeated and summoned, stat changes, hero damage and healing, win or loss). Ending the turn, the mulligan and Spare Spore aren't tried |
| `active_effect` (not yet built) | effect type + parameters + turns until it expires |

| Edge type | Kind | Meaning |
|---|---|---|
| `part_of` | static | every ability node → its card |
| `next` | static | control flow inside a decision graph (next step, branches, static modifiers) |
| `uses` | static | data flow: a `choose` → every later step that refers to its name ("it") |
| `belongs_to` | dynamic | card → its owner's player node (zones are card features) |
| `faces` | dynamic | between every unit in play and every opposing unit, so units can weigh up direct threats |
| `matches` | dynamic | a node with a Filter (`choose`, `effect` on `all(…)`, `if` on `count(…)`, `static`, a scaling `amount`) → every card the Filter currently matches, computed by the engine (respects Elusive) |
| `bound_to` | dynamic | while an ability resolves: a `choose` node → the card(s) already chosen for it |
| `affects`, `source_of` (not yet built) | dynamic | active effect → affected card; card → effect it created |

Every edge type also gets its reverse, so information flows both ways.

**Hidden information.** The opponent's hand and deck are counts on their player node. Your
own deck is a count too, plus optionally a deck-composition summary.

**Size.** About 10–30 visible cards plus 4–7 ability nodes per card with an ability: about
20 ability nodes per state on `set_200`. Encoding takes about 85 µs per state; a GNN forward
and backward pass about 2.4× as long as without abilities.

## 6. Model (`src/model/`)

- **Card encoder:** an MLP over stats and keywords. The card's ability isn't pooled into it:
  its ability nodes take part in message passing with the rest of the state (`part_of`
  edges), so the card's embedding and its abilities' meaning can depend on the board.
- **State encoder:** a heterogeneous GNN, the default: 4 layers, each a `HeteroConv` of GATv2
  attention (4 heads, 128 wide) with its own weights per edge type, then ReLU, a residual and
  LayerNorm. An **entity transformer** with edges as attention biases (the AlphaStar / OpenAI
  Five pattern) is kept as the alternative: it played as well after 100 iterations, but the GNN
  is about 3× faster on the CPU. Both (`src/model/gnn.py`, `src/model/transformer.py`) sit on
  one framework-neutral encoder (`src/graph/encode.py`, NumPy arrays). The transformer's input is
  padded to a few fixed sizes, so it suits accelerators and a JAX port.
- **Policy head:** each legal option (attacking the hero is an action type with no target
  card) is encoded as `MLP([action-type embedding,
  emb(actor node), emb(target node), emb(context node), emb(option node), emb(global)])` and
  scored, with a softmax over the legal options only (a pointer-network style head). While an
  ability resolves, the context is the decision node being resolved. For a `choose`, the target
  is the card. For a `choose_one`, the option is the first node of the option's branch.
  Each action's outcome features are projected and added to its action-type embedding.
- **Value head:** win probability from the global and both player nodes. Auxiliary targets
  (final health difference, turns remaining) are an idea for later.
- **Cost model (planned):** predicts a card's fair cost from its embedding, trained on the
  agent's games (section 10). It is used for auto-costing in part c.
- **Baseline (planned):** a flat vector per ability (effect one-hot plus parameters) instead of
  the ability subgraph, to check the subgraphs earn their keep.
- **Checkpoints** store the names of their card, ability and outcome features and action types,
  so an older checkpoint still loads when features change: removed columns are dropped and new
  ones get zero weights (`src/model/registry.py`).

## 7. Training (`src/training/ppo.py`)

- **PPO self-play.** Each iteration plays 64 games (in lockstep, so the network scores many
  positions at once) and makes a PPO update. The reward is +1 for a win and −1 for a loss, with
  GAE (γ = 1, λ = 0.95), and an update stops early once the KL divergence passes a target.
- **League.** 30% of games are against an opponent from the league: frozen snapshots of the
  network (one every 10 iterations, the newest 8 kept) and the heuristic agent, so the agent
  doesn't just learn to beat its current self.
- **Card sets.** Each game draws two random decks from a training set (`set_1000`). Decks focus
  on two jobs. The agent never sees a card ID, so it plays unseen cards.
- **Evaluation.** Every 25 iterations against the random and heuristic agents, on the training
  set and on held-out sets (`--eval-cards`), always on the same deck pairs (`eval_seed`). These
  100-game evals are noisy, so compare models with `scripts.benchmark` (400 games, paired).
- **Running it.** On the CPU (faster than MPS for these small graphs), under `caffeinate`, logged
  to Weights & Biases (`--wandb`). A from-scratch run of 3,000 iterations takes about a day.

## 8. Search within a turn (`src/agents/search_agent.py`)

At play time the agent can search its own turn. At each of its decisions it copies the game,
re-deals the hidden cards (`determinize`), and runs a beam search over its moves: each step keeps
the policy's `top_k` moves (always including ending the turn) and the value head's best `beam`
positions. A line ends when the turn does, scored as minus the opponent's value at their first
decision (the value head is trained only on positions where it's the observer's move). The agent
plays the first move of the best line and searches again at its next decision. The opponent's
choices inside the agent's turn are made greedily by the network. Defaults: beam 4, top 4, 12
moves deep, about 90 ms a decision. Training doesn't use it yet (expert iteration is P4).

## 9. How part a sets up b and c

| Part a decision | Payoff in b | Payoff in c |
|---|---|---|
| Uniform decision points, scoring options by node | One policy head handles every choice | — |
| `clone` / `determinize` | AlphaZero-style search over hidden information later | Cheaper, stronger agents for tournaments |
| No card IDs, cards described by content | Trains on randomized pools and generalises | Evaluates generated cards with no retraining |
| Typed, closed DSL with a text renderer | — | The generator samples valid trees; the engine runs them unchanged; every card is readable |
| Abilities compiled to decision graphs | Choices inside abilities are ordinary decision points, scored with the decision node as context | Generated trees run in the engine with no new code |
| Card embedding + cost model | — | Auto-costing and fast screening of candidates |

## 10. Bootstrapping from nothing

There are no real cards to train on or compare against, which creates a chicken-and-egg
problem: judging cards needs a trained agent, and training an agent needs cards. Iterate:

1. **Round 0, vanilla units.** Sample units with random stats, costed by a rough
   hand-written formula. Train the agent on random decks from this pool.
2. **Fit the cost model.** Measure each card's effect on win rate in the agent's games
   (e.g. win rate when played, adjusted for when it was played). Regress that against the
   card embedding to get a learned fair cost. Check it is self-consistent: does it give each
   stat a stable value in mana (e.g. +1 health ≈ X power at a given cost)? Does it find
   Hearthstone players' rule of thumb that a fair vanilla unit has about 2 × mana + 1 stats?
   This is the first real experiment of the project.
3. **Re-cost the pool and retrain.** Repeat until the cost model stops moving.
4. **Add the next layer of mechanics** (section 2) and repeat from step 1 with the extended
   pool.

So far the rounds used a rough value table scaled by measured factors (results.md, "Card
pricing"). The learned cost model is step P3 of the stage-2 plan.

**Main risk: balance relative to a flawed agent.** If the system only ever measures itself,
it can settle on a "balance" that only its own agent believes in. Mitigations:

- several agent strengths and styles, including hand-written heuristic agents;
- exploit-seeking agents trained only to break the current set;
- human playtesting through the Unity client.

## 11. Open questions

The open decisions are in [roadmap.md](roadmap.md), and stage 2's in its plan (section 7). One
standing check: if an LLM ever generates or names cards, make sure they don't copy cards from
existing games.
