# Technical plan, part a: rules engine and graph representation

The project has three parts:

- **a.** Define a trading card game's rules and represent its state as a graph a GNN can
  learn from.
- **b.** Train an agent to play it through self-play.
- **c.** Generate a balanced, interesting set of ~3000 cards.

The card pool is **entirely synthetic**. No cards from any existing game are used. The
rules follow the broad structure of Disney Lorcana, but use original terms and are tweaked
where useful. The aim is to show that a whole card set can be generated from scratch once
the rules are defined. This also keeps the project free of card licensing issues.

![System overview](architecture_overview.png)

The diagram source is [architecture.drawio](architecture.drawio). Page 1 is the system
overview above; page 2 shows the state graph in detail (see section 5).

## Placeholder glossary

All names are placeholders until the game has a name and theme. Keep them in one constants
module so a rename is a single change.

| Placeholder | Meaning |
|---|---|
| **Victory points (VP)** | First player to 20 wins |
| **Energy**, energy zone | Resource paid to play cards. A card flagged *energy source* can be put into the energy zone, once per turn |
| **Ready / exhausted** | A card is exhausted to score, duel, sing, pay energy or pay a ⟳ cost |
| **Fresh** | Entered play this turn: can't score, duel or pay ⟳ costs |
| **Unit** | Creature-type card: power, health, score (VP gained when scoring), traits |
| **Action**, **Chant** | One-shot card. A Chant can be paid by exhausting a unit with cost ≥ the chant's cost |
| **Item** | Permanent, non-unit card |
| **Site** | Permanent location units can move to; gives VP at the start of its owner's turn |
| **Score** | Exhaust a unit to gain its score in VP |
| **Duel** | Exhaust a unit to fight an exhausted opposing unit or a site; damage is dealt both ways |
| **Defeated** | Damage ≥ health; the card goes to the discard pile |
| **Aspects** (6) | Card colours; decks use 1–2 aspects |
| **Traits** | Unit tags that abilities can refer to (generated with the set) |
| **Keywords** | Guard, Duelist +N, Elusive, Berserk, Armor +N, Charge, Evolve N, Chanter N, Choir N, Inspire, Veiled, Fragile |

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

## 2. Rules scope

- Two players with 60-card decks (up to 4 copies, 1–2 aspects). The first player to 20 VP
  wins; a player who has to draw from an empty deck loses.
- **Turn:** Beginning phase (ready, set — sites give VP and "start of turn" effects trigger —
  then draw; the first player skips their first draw) → Main phase → End of turn. There is
  one mulligan at the start of the game.
- **Main phase actions:** add one energy-source card to the energy zone; play a card by
  exhausting energy; Evolve onto a unit with the same name; chant by exhausting a unit;
  score; duel; move a unit to a site; activate ⟳ abilities.
- **Card types:** Unit, Action (including Chant), Item, Site.
- **Keywords** (the keyword list is data, so adding one is an engine change plus a feature
  column):

  | Keyword | Effect |
  |---|---|
  | Guard | Opponents must duel this unit first |
  | Duelist +N | +N power while dueling |
  | Elusive | Only Elusive units can duel it |
  | Berserk | Can't score; must duel if able |
  | Armor +N | Takes N less damage |
  | Charge | Can duel while fresh |
  | Evolve N | Play onto a unit with the same name for N |
  | Chanter N / Choir N | Counts as cost N for chanting / several units chant together |
  | Inspire | Adds power to another unit when scoring |
  | Veiled | Opponents can't choose it except to duel |
  | Fragile | Defeated when an opponent chooses it |

**Layered rollout.** Each layer adds DSL building blocks and engine support, and is
followed by a bootstrapping round (section 8):

1. Vanilla units (stats only).
2. Keywords.
3. Simple triggered and activated abilities.
4. Actions and items.
5. Sites, chants and Evolve.

## 3. Card schema and ability DSL

```jsonc
{
  "id": "gen-000123",           // for bookkeeping only, never shown to the network
  "name": "…",                  // used for Evolve and "named X" checks, via same_name edges
  "type": "unit",               // unit | action | item | site
  "aspects": ["aspect_1"], "energy_source": true,
  "cost": 4, "power": 3, "health": 4, "score": 1,
  "traits": ["trait_a"],
  "keywords": {"charge": true, "duelist": 2, "evolve": null, "chanter": null},
  "move_cost": null, "site_vp": null,
  "abilities": [ /* DSL trees, below */ ]
}
```

**Ability grammar.** It is small, typed and closed, so every tree can be executed,
rendered as text and generated:

```
Ability   := triggered(Trigger, [Condition], [Cost], Effect+)
           | activated(Cost+, [Condition], Effect+)
           | static(Condition?, Modifier+)
Trigger   := on_play | on_score | on_duel | on_defeated | on_start_of_turn | on_end_of_turn | …  (+ source Filter)
Effect    := deal_damage(n, Selector) | remove_damage(n|all, Selector) | defeat(Selector)
           | return_to_hand(Selector) | draw(n, Player) | gain_vp(n, Player) | lose_vp(n, Player)
           | exhaust(Selector) | ready(Selector) | cant_ready(Selector, Duration)
           | modify_stat(stat, Δ, Selector, Duration) | grant_keyword(kw, Selector, Duration)
           | put_into_energy(Selector) | look_and_choose(n, …) | …
Selector  := choose(count, chooser, Filter, optional?) | all(Filter) | this | random(count, Filter)
Filter    := {type?, owner?, zone?, trait?, cost_cmp?, damaged?, exhausted?, name?, …}
Duration  := this_turn | until_their_next_turn | while(Condition) | permanent
```

**Requirements so the DSL can be generated:**

- **Types and ranges.** Every parameter has a type and a valid range (e.g. `deal_damage.n ∈
  1..5`). Every effect has a *polarity* (does it help or hurt the target?) so that, say,
  "remove damage" can't target opposing units unless a rule explicitly allows it.
- **Text renderer.** A DSL → card text renderer is needed for the Unity client and for
  human review. It is also the easy direction: nothing has to parse free text.
- **"Does something" check.** The engine checks that an ability actually changes game state
  across simulated games, and that it never loops.
- **Granularity.** The building blocks set the design space, so generated abilities are new
  combinations, not new mechanics. Fine-grained, independent building blocks (events, zones,
  counters, conditions) widen that space but make generation harder; template-sized blocks
  do the opposite. Start template-sized and break blocks apart as the generator improves.

**The two example abilities as trees:**

```jsonc
// "When you play this unit, choose an opposing unit. It can't ready at the start of its next turn."
{"kind": "triggered", "trigger": {"event": "on_play", "source": "this"},
 "effects": [{"op": "cant_ready", "duration": "until_their_next_turn",
              "target": {"select": "choose", "count": 1, "chooser": "you",
                         "filter": {"type": "unit", "owner": "opponent"}}}]}

// "Remove all damage from your trait A units."
{"kind": "on_resolve",
 "effects": [{"op": "remove_damage", "amount": "all",
              "target": {"select": "all",
                         "filter": {"type": "unit", "owner": "you", "trait": "trait_a"}}}]}
```

**Card sources:**

- **Starter set.** About 30–60 cards written by hand. They are the engine's test fixtures,
  cover every building block at least once, and are a sanity anchor while nothing else is
  trusted.
- **Random pools.** Sampled from the grammar with a rough cost formula; used to train the
  agent.
- **Generated sets.** The output of part c.

## 4. Rules engine (`src/game/`, `src/cards/`)

- **State:** players (VP, energy, deck, hand, energy zone, discard), cards in play
  (exhausted, damage, fresh, site, evolve stack), and active effects (op, target, source,
  expiry).
- **Decision points.** The engine pauses whenever a player must choose: main-phase action,
  target selection, optional "may" effects, ordering of simultaneous triggers, mulligan.
  Every decision is "choose one of these N options", and each option refers to graph nodes.
- **Events and triggers:** an event bus feeds a trigger queue, resolved in rules order.
  Durations are stored as active effects and expired by the turn structure.
- **Determinism:** all randomness comes from a seeded RNG. `clone()` and
  `determinize(player)` (re-deal the hidden cards consistently with what the player has
  seen) support search in part b.
- **Performance:** start in pure Python for correctness, profile once self-play runs, then
  move hot paths to a faster implementation. Because the DSL is data, a C# interpreter for
  the Unity client can later load the same card files.

## 5. State graph (`src/graph/`)

![State graph](architecture_state_graph.png)

One heterogeneous graph per player per decision point (`torch_geometric.data.HeteroData`):

| Node type | Features |
|---|---|
| `card` (each card instance that is visible) | card embedding from the card encoder + zone, exhausted, damage, fresh, site, owner (relative: you / opponent) |
| `ability`, `trigger`, `cost`, `condition`, `effect`, `selector`, `filter` | node type + its parameters (amount, count, stat, keyword, duration, chooser), numbers normalised |
| `player` (you, opponent) | VP, energy ready / total, hand size, deck size, added energy this turn |
| `global` | turn number, phase, whose turn |
| `active_effect` | effect type + parameters + turns until it expires |

| Edge type | Kind | Meaning |
|---|---|---|
| `has_ability`, `ability → trigger/cost/condition/effect`, `effect → selector → filter` | static | ability tree structure |
| `same_name` | static | links cards that share a name (Evolve, "named X" checks) without a name embedding |
| `owns`, `in_zone` | dynamic | player → card, card → zone |
| `at_site`, `evolved_from` | dynamic | board structure |
| `faces` | dynamic | between every unit in play and every opposing unit, so units can weigh up direct threats |
| `matches` | dynamic | filter → every card it currently matches, computed by the engine (respects Veiled, Elusive, etc.) |
| `affects`, `source_of` | dynamic | active effect → affected card; card → effect it created |

Every edge type also gets its reverse, so information flows both ways.

**Hidden information.** The opponent's hand and deck are counts on their player node. Your
own deck is a count too, plus optionally a deck-composition summary. Face-down
energy-zone cards only matter as energy count.

**Size.** About 20–60 card nodes plus about 5–10 ability nodes per card with abilities,
so a few hundred nodes. That batches easily on a GPU.

## 6. Model (`src/model/`)

- **Card encoder:** an MLP over stats and keywords, plus a small GNN over the card's own
  ability subgraph, pooled into one card embedding. It depends only on the card definition,
  so embeddings can be cached per card during self-play and invalidated when weights change.
- **State encoder:** a heterogeneous GNN (e.g. `HeteroConv` with GATv2 / Transformer
  convolutions) with 4–6 layers. An **entity transformer** with edges as attention biases
  (the AlphaStar / OpenAI Five pattern) is the main alternative. Game states are small enough
  for full attention, and it avoids the limited reach of message passing over a few hops. The
  graph builder is the same for both, so this choice can wait until there's data to compare
  them on.
- **Policy head:** each legal option is encoded as `MLP([action-type embedding,
  emb(actor node), emb(target node), emb(global)])` and scored, with a softmax over the legal
  options only (a pointer-network style head).
- **Value head:** win probability from the pooled player and global nodes. Auxiliary targets
  (final VP difference, turns remaining) help early training.
- **Cost model:** predicts a card's fair cost from its embedding, trained on the agent's games
  (section 8). It is used for auto-costing in part c.
- **Baseline:** a flat vector per ability (effect one-hot plus parameters) instead of the
  ability subgraph. If the subgraphs don't beat it, that's worth knowing early.

## 7. How part a sets up b and c

| Part a decision | Payoff in b | Payoff in c |
|---|---|---|
| Uniform decision points, scoring options by node | One policy head handles every choice | — |
| `clone` / `determinize` | AlphaZero-style search over hidden information later | Cheaper, stronger agents for tournaments |
| No card IDs, cards described by content | Trains on randomized pools and generalises | Evaluates generated cards with no retraining |
| Typed, closed DSL with a text renderer | — | The generator samples valid trees; the engine runs them unchanged; every card is readable |
| Card embedding + cost model | — | Auto-costing and fast screening of candidates |

## 8. Bootstrapping from nothing

There are no real cards to train on or compare against, which creates a chicken-and-egg
problem: judging cards needs a trained agent, and training an agent needs cards. Iterate:

1. **Round 0, vanilla units.** Sample units with random stats, costed by a rough
   hand-written formula. Train the agent on random decks from this pool.
2. **Fit the cost model.** Measure each card's effect on win rate in the agent's games
   (e.g. win rate when played, adjusted for when it was played). Regress that against the
   card embedding to get a learned fair cost. Check it is self-consistent: does it give each
   stat a stable value in energy (e.g. +1 score ≈ X power at a given cost)? This is the
   first real experiment of the project.
3. **Re-cost the pool and retrain.** Repeat until the cost model stops moving.
4. **Add the next layer of mechanics** (section 2) and repeat from step 1 with the extended
   pool.

**Main risk: balance relative to a flawed agent.** If the system only ever measures itself,
it can settle on a "balance" that only its own agent believes in. Mitigations:

- several agent strengths and styles, including hand-written heuristic agents;
- exploit-seeking agents trained only to break the current set;
- human playtesting through the Unity client.

## 9. Milestones for part a

1. Placeholder constants module, card schema and loader; a starter set of vanilla units and
   keywords; DSL → text renderer.
2. Engine core: turn structure, energy, play, score, duel, defeat, win/lose, decision
   points. Random agent vs random agent runs to completion; rules unit tests.
3. Random card pool sampler (vanilla + keywords) with a rough cost formula.
4. Graph builder producing `HeteroData`, with tests that node and edge counts match the
   state.
5. Model forward pass on batched graphs, plus a smoke-test training loop (value regression on
   random-play outcomes). **This is the first end-to-end slice, and it covers round 0 of
   section 8.**
6. DSL interpreter: triggers, selectors, filters, durations, active effects. Add
   abilities to the starter set and the sampler.
7. Then: actions and items, sites, chants and Evolve.

## 10. Open questions

- The game's name, theme and final terms.
- A patent check on mechanics before a public release (rare and narrow, but they exist in
  this genre).
- If an LLM is used as the generator, check that its cards don't copy existing cards from
  other games.
- How much set structure to specify by hand (aspect identities, cost curve, rarity, number
  of cards per aspect) versus letting it emerge. Starting with a light, hand-specified set
  skeleton and treating emergent aspect identity as a stretch goal is the safer path.
- How much hidden information to model: plain PPO from the observation graph first, or invest
  early in determinized search?
- Whether the engine eventually needs a faster implementation (Rust or C#) for self-play
  throughput.
