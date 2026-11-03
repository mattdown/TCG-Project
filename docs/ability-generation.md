# Ability generation

How the project makes abilities and cards from nothing, and how it decides which ones to keep.
This is a living document: update it whenever a stage, a test or a number below changes, and
add a line to the [log](#log) at the end.

The grammar itself (the building blocks and the hard constraints) is in
[technical-plan.md](technical-plan.md) section 3. This document is about the generator built
on top of it.

## The principle: generate and test, with general tests

There are no example cards to learn from or copy, so the generator samples many candidates
and throws most of them away. What matters is *how* it decides what to throw away:

- **No rules about particular cards.** A test never says "don't pair hero damage with healing".
  Each test looks at the *shape* of the ability tree (how many nodes, how the steps refer
  to each other, which numbers differ), so it keeps working as the grammar grows.
- **Hand-written numbers are placeholders.** Sampling weights, the complexity budget and
  the rough costing table are first guesses. Each one is meant to be replaced by something
  measured in self-play.
- **Structural tests are a cheap first filter.** The real judge is the trained agent and
  the learned cost model. Each structural test below has a measured counterpart in
  [Later: measured by the agent](#later-measured-by-the-agent) that eventually confirms or
  replaces it.

## The pipeline

```
sample a tree ─→ grammar ─→ quality tests ─→ build & cost the card ─→ variety ─→ kept
  (abilities.py)  validate()   quality.py        generate.py               generate.py
                    │              │                  │                         │
                    ✗ illegal      ✗ too complex      ✗ couldn't matter         ✗ shape already
                                   ✗ not connected      on this card              common
                                   ✗ fake choice
```

Every draw is recorded with the stage that stopped it and why (`Attempt` in
`src/cards/generate.py`), so the [card lab](#tools) can show what was thrown away as well as
what was kept.

### 1. Sample a tree

`AbilitySampler.raw()` walks the grammar: ability kind (triggered or static for units,
on-resolve for actions), then trigger, condition, step pattern, effects, targets and
numbers. The weights are hand-set placeholders (`EFFECT_WEIGHTS`, `TRIGGERS`, the step
patterns in `_steps`). Actions never get the "you may … if you do" pattern: you play an action
to use it, so an optional ability on one makes no sense.

**One ability per card for now.** One idea per card keeps cards readable and makes each
ability's effect on a card measurable on its own. The engine and the card schema support more;
only the generator is limited.

### 2. Grammar (legality)

`validate()` checks the hard constraints from the technical plan: scope, types, polarity,
size limits, no runaway abilities, grant durations. The sampler builds legal trees by
construction, so this stage rarely rejects anything. It exists so that trees written by hand
or by another generator are checked in the same way.

### 3. Quality tests (`src/cards/quality.py`)

Legal isn't the same as worth generating. Four tests, each a general property of the tree:

| Test | Rule | Catches |
|---|---|---|
| **Complexity budget** | At most `MAX_COMPLEXITY` = 4 nodes. A node is each step (choice, effect, if, may, choose one), the condition and each static modifier. | Long abilities that stack a condition, a "you may", a choice and a follow-up |
| **Narrowing budget** | At most `MAX_NARROWING` = 1 condition or restriction (damaged, cost ≤ n, job) on a filter that picks cards. Filters inside a condition or a "for each" count aren't counted again. In self-play each one roughly halved how often an ability hit; with two or more, abilities almost never fired (`experiments.py fire`). | "When this unit is defeated, if you have 2 or more other Chef units, chosen damaged enemy unit gets −2 power" (fired 0 times in 122 plays) |
| **Connected steps** | Every step after the first must act on a card that an earlier step acted on, or ask about it ("if it was defeated"). Choices only name a card and aren't counted. "You may … if you do" and choose one connect their parts by construction. | Unrelated effects glued together: "+1 health this turn. Your opponent loses 1 VP." |
| **No dominated options** | In a choose one, an option with the same shape as another (the same tree apart from its numbers) that is no bigger in any number is never worth picking. Every number in the grammar is better bigger for whoever chooses it, so no knowledge of particular effects is needed. | "Choose one: draw 2 cards, or draw a card." Also the same option twice. |

The complexity budget is the main lever on how wild the set is. 4 rejects about 6% of raw
draws. Actions get 2 more nodes (`ACTION_COMPLEXITY`): an action is only its ability. Raising it later (by rarity, for example) is a one-line change.

Trade-offs worth knowing:

- **Players don't connect steps.** "Draw a card. Heal your hero for 2." fails, even though both effects
  are on you. Counting the player as a link would let almost any pair of player effects
  through. Two-part player effects can still be written as "you may … if you do".
- **Dominance only compares options of the same shape.** "Heal your hero for 5 or deal 1
  damage to the enemy hero" still gets through. Comparing different effects needs a value model, so it waits for
  the learned cost model or for the agent's choice statistics (below).

### 4. Build and cost the card

**Card kinds.** The first decision is the kind of card, from shares of the whole set. It is one
draw, traced as two decisions: "Card type" (unit or action), then for a unit "Unit kind"
(vanilla, keywords only or ability), whose odds multiply back to these shares:
- vanilla units (stats only, about 4%)
- keyword-only units (about 25%)
- action cards (25%)
- units with one ability (the rest)

Vanilla and keyword-only units skip the ability stages. They are neutral, and a **duplicate**
stage stops any with the same cost, stats and keywords as a card already in the set.

Only about 44–70 fair vanilla stat lines exist up to 10 mana, and about 1,200 keyword-only
ones with balanced stats (5 at 1 mana, 32 at 2). So after 100 duplicates in a row the generator
makes a unit with an ability instead. These counts come from the budget rule, with every stat
at least 1 and at most 12.

`CardGenerator._build` turns the ability into a card:
- **Names:** units are a species + job with a subtitle picked from the ability ("Porcini
  Baker – Up Before Dawn"). Actions get an event name: an aspect word plus a noun for the main
  effect ("Ember Volley"). See [theme.md](theme.md#card-names). Names are only reserved by kept
  cards, and every full name in a set is unique.
- **Aspect:** random, or neutral 10% of the time. Aspects have no identity yet (it should
  later come from clustering generated cards, technical plan section 2), so for now decks
  ignore them.
- **Cost and stats:** from the ability's price in `src/cards/costing.py`: its rough value times
  a measured share (`PRICE_SCALE`: 0.4 for units, 0.2 for actions), the share at which a deck
  tied with a copy whose abilities were swapped for stats. Units also get an archetype (how
  stats are spread) and sometimes a keyword. The stat budget is 2 × cost + 1 (Hearthstone
  players' rule of thumb), minus the ability's price rounded to the nearest point. An action
  costs half its price in mana, to the nearest, and **an action worth less than 1 mana is
  rejected** (`MIN_ACTION_PRICE`): it isn't worth a card. That uses the measured prices now and
  the cost network once it's reliable.

Then the card-level checks run (`card_problems`). They reject abilities that could never
matter *on this card*:
- abilities that need the unit damaged, on a 1-health unit
- "this turn" bonuses for a unit that was just played
- healing a unit that was just played
- giving the unit a keyword without a number (Guard, Elusive, Charge) that it already has

### 5. Variety

Choosing a grammar branch uniformly over-produces small branches. For example, "Your other X
units get +1 health" is a large share of statics, because the static menu is short. With
`variety` = k, the generator draws k good cards for each one it keeps. It keeps the one whose
*shape* has been used least so far. The shape is the tree with numbers and jobs blanked out.
That approximates sampling evenly over distinct abilities rather than over branches, with no
per-branch weights. The default is 4 in the card lab and 1 elsewhere. The coverage generator
has its own diversity: it picks for building-block coverage and never takes the same
ability twice.

## Where it stands

Card lab, seed 1, 60 cards, 6 jobs, variety 4: 293 draws, 60 kept (rules v2).

| Stopped at | Draws | Main reason |
|---|---|---|
| Grammar | 0 | almost always legal by construction (the rare exception: a "this turn" bonus at the end of the turn) |
| Quality | 51 | steps not connected 36, too complex 15 (dominated options are rarer: about 1 in 100 draws) |
| Card | 2 | couldn't matter on the card |
| Variety | 180 | expected: 3 of every 4 good draws are set aside |

Problems still visible in the output, and what will deal with each:

| Problem | Example | Fix |
|---|---|---|
| Options of different shapes where one is clearly better | "Heal your hero for 1 for each Archer (up to 5), or heal your hero for 2" | Value model (learned cost model, or agent choice spread) |
| Ability that does what a keyword does | "Duelist +1. While attacking, +2 power"; "While attacking, +1 power" is Duelist +1 | Keyword equivalence (planned, below) |
| Expensive units with weak stats; very strong repeating effects | cost 8, 2 power, 1 health; "at the start of your turn, defeat …" | Power budget decision, then the cost model |
| Conditions on jobs that rarely come up | "if you have 3 or more other Explorer units" | Job reachability (planned), then trigger rate |
| Sampling weights are guesses | — | Measured later, see below |

## Planned structural tests

- **Keyword equivalence.** Write keywords in the DSL too. When an ability compiles to the
  same thing as a keyword, replace it with the keyword (and then the card-level check above
  catches duplicates).
- **Fits the cost curve.** Reject cards whose estimated value is more than the most expensive
  card can pay for. It uses the rough table now and the cost model later, with no change
  to the rule. Waits on the power budget decision.
- **Job reachability.** Pass the set's job distribution in, and keep a job condition only if
  a deck built from the set can plausibly meet it. Waits on the jobs-per-set decision.

## Later: measured by the agent

Once the agent is trained on cards with abilities, these come from self-play logs, per
ability. Together they are the working definition of "card quality" for the curriculum stage.

| Measure | How | Replaces or confirms |
|---|---|---|
| **Fire rate** | Share of games where the card is in play and the ability resolves | Job reachability; finds dead triggers and conditions |
| **Choice spread** | How evenly the trained agent splits between a choose one's options, or accepts and declines a "you may" | Dominated options, including different shapes; may-costs that are always or never worth paying |
| **Impact** | The cost model's value of the card with the ability minus without it (or win rate with and without) | Card-level "can it matter" checks; finds abilities that never matter and ones that are too strong |
| **Card strength** | Win rate of decks with the card against the same decks with a vanilla card of the same cost | The rough costing table, via the learned cost model |

The complexity budget doesn't need replacing; it is a design choice about how readable the
cards are, not a guess about value.

## Tools

The card lab (`Blog/card_lab.py`) runs the whole pipeline and shows every stage, including
what was thrown away and why. Run these from the repository root: they use PythonServer's
environment.

The web page, at <http://localhost:8765>. Change the seed, set size, jobs, the vanilla, keyword-only and action shares, and variety there:

```bash
uv run --project PythonServer python Blog/card_lab.py
```

The same output in the terminal (`--rejected` adds the thrown-away draws):

```bash
uv run --project PythonServer python Blog/card_lab.py --text --count 50 --rejected
```

A self-contained page with one batch baked in, which needs no Python to view (for sharing or a blog post):

```bash
uv run --project PythonServer python Blog/card_lab.py --export lab.html --seed 7 --count 80
```

The page has the client's Lantern look, like the visualisers, and shows:
- each kept card as the client draws it (`Blog/painted_card.html`), with its painted art. The
  default seed, 0, gives the first cards of `set_200`, which have art; other cards get a
  placeholder mushroom in their aspect's colour
- the funnel of draws through each stage, with counts per reason
- for each card, the checks it passed, its costing, its ability tree and its shape

One card's path through the grammar, animated, is the card generation visualiser
(`Blog/card_generation_visualiser.py`). It reads the sampler's derivation from
`src/cards/trace.py`, which makes exactly the same calls on the random generator as plain
sampling, so tracing never changes what is generated.

`scripts.generate_cards --kind set --count N` writes a playable set of N cards straight from
this pipeline (`cardsets/set_N.json`, plus a checklist `.md`), with `--vanilla-share`,
`--keyword-share` and `--action-share`. It uses 6 jobs, like the coverage set, so job conditions
can be met. Run the server on it with `scripts.server --cards cardsets/set_200.json`. `--kind coverage` builds the coverage set
for checking the engine and client. It uses the same pipeline.

## Log

- **2026-10-20:** First version.
  - New quality tests: complexity budget 4, connected steps, dominated options.
  - New variety stage and card lab.
  - One ability per card.
  - New card check: a keyword the unit already has.
  - Card text now says "chosen opposing Chef unit", not "chosen Chef opposing unit".
- **2026-10-20:** Derivation traces (`src/cards/trace.py`) and the card explorer, which shows
  the path through the grammar for one card at a time.
- **2026-10-20:** `generate_cards --kind abilities --count N`: playable sets straight from the pipeline.
- **2026-10-20:** Subtitles for units and event names for actions (`src/cards/names.py`),
  shown in the card lab and explorer.
- **2026-10-21:** Rules v2 (Hearthstone-style). The grammar's VP effects became hero effects
  (heal your hero, damage a hero), "can't ready" became freeze, energy became "gain an empty
  mana crystal", and the scoring trigger became "whenever this unit attacks the enemy hero".
  Activated abilities, `ready`, `exhaust` and the "exhausted" filter are no longer generated;
  Elusive is no longer granted. Stat budget 2 × cost + 1 from power and health only.
- **2026-10-21:** Card kinds: vanilla (4%) and keyword-only (25%) neutral units alongside ability
  cards, with a duplicate stage for them; keyword subtitles; aspects random or neutral (decks are
  one aspect plus neutral cards, behind `ONE_ASPECT`, off for now). `--kind abilities` became
  `--kind set` (`set_200`).
- **2026-10-22:** Measured with `scripts/experiments.py`: abilities were worth less than one stat
  point on average, and actions lost to a vanilla unit even at cost 0. A big reason: 54 of 133
  ability cards in `set_200` named a job, so with 6 jobs a filter like "enemy Baker unit" often
  had no target. Decks now focus on two jobs (70% of their units), and target restrictions on
  enemy units no longer use jobs (damaged or cost only). Next: price filters by how often they
  match, bigger amounts, a higher complexity limit for actions, lasting buffs and summons.
- **2026-10-22:** Step 2, from the fire check (`experiments.py fire`: how often a played ability
  card's ability hits a target). Only 53% of played ability cards ever did anything; each
  narrowing about halved the hits; triggers fired far less often than the value table assumed
  (start of turn 2.5 uses assumed, about 0.8 measured). Changes:
  - **Own job:** a unit's job is chosen before its ability, and job references are its own job
    75% of the time (`OWN_JOB`), so tribes reward their own members and focused decks meet them.
  - **Narrowing budget** quality test (at most 1).
  - **Costing:** `TRIGGER_USES` from the measurements; `NARROW_FACTOR` 0.5 per narrowing replaces
    the condition factor and also covers restricted filters, which were free before.
  - **Actions:** amounts start one higher and may go one higher, and actions get 2 more nodes of
    complexity.
  - **Prices** (`costing.price`): the rough value times a measured share, 0.4 for units and 0.2
    for actions (`experiments.py scale` on a set built with the changes above). Before these
    changes a deck lost 70–81% to a copy with its abilities swapped for stats; after them,
    the even point moved from about 0.1 to 0.3–0.5 of the value table.
- **2026-10-22:** Step 3a: lasting buffs. New effect `buff` (+power and/or +health on your
  units until they leave play: "A chosen unit of yours gets +2 power and +2 health", "Your
  units get +2 power"), weight 6. A buff on this unit when it's played is rejected (it's just
  more stats). Costing: a lasting point is worth one budget point, like a unit's own stats,
  and pays the full value: `PRICE_SCALE` now applies per effect, except to lasting stats
  (`STAT_RATE`), since it corrects the table's overvalued one-shot effects. Network: `op:buff`,
  `buff_power`, `buff_health` features, appended so older models still load (with zero weights
  for them) until the next retrain.
- **2026-10-22:** Step 3b: summons. New effect `summon` (weight 6): 1 or 2 tokens (2 only when
  a token has 3 stats or fewer), each 2–5 stats (6 on actions), sometimes a keyword (Guard,
  Charge, Armor +1, Duelist +1) and, on units, sometimes the unit's own job. Tokens are
  described inside the ability, so cards stay data; `src/cards/tokens.py` turns a description
  into a card with an id derived from it. Priced at the stat rate, like buffs: a token is a body
  in play. Network: `op:summon`, `token_power`, `token_health` (a token keyword uses the keyword
  features); the summoned unit is an ordinary card node.
- **2026-10-23:** Step 4: per-effect prices. `experiments.py effects` re-prices one group of cards
  (card type + main effect) at 0.5, 1 and 1.5 times its price, with 10 of each deck's 30 cards
  from the group, and fits where the deck ties with the same deck refunded (`costing.GROUP_SCALE`,
  measured with `tcgnet_v3`, retrained on summons and buffs). Damage, discard, bounce and freeze
  were underpriced (×1.2–2.3); unit draw (×0.35) and unit summons (×0.15) overpriced. Several
  groups lost even at the lowest price: buffs, heals, mana crystals, "this turn" stat and keyword
  grants, damage removal and statics. On units they now get ×0.1, and unit prices round to the
  nearest point (they rounded up), so these are mostly free extras. As actions they lose to a
  vanilla 1-mana unit at any price: open decision (stronger effects, or fewer of them as actions).
  Result on a fresh `set_200` (tcgnet_v3 / heuristic): real vs refunded 41% / 44% → 55% / 59%;
  real vs no actions 48% / 34% → 37% / 37%.
- **2026-10-23:** Stronger actions. Action amounts run from one above the effect's range to
  `ACTION_EXTRA` = 2 above it (the validator allowed only the base range, so since step 2 about
  10% of action draws had been rejected for "amount outside range"); stat bonuses and buffs on
  actions go to +4; summon actions get 3–7 stat tokens and pairs more often. Actions priced
  under 1 mana are rejected, and action costs round to the nearest mana. With today's prices
  that removes almost all heal, "this turn" grant, remove-damage, mana-crystal and hero-damage
  actions (each was worth less than a 1-mana vanilla unit in `experiments.py effects`); kept
  actions are mostly damage, summon, draw and buff. Weak unit groups go from 0.1 to 0.3
  (`GROUP_SCALE`): 0.1 overshot.
- **2026-10-28:** Activated (⟳) abilities removed from the code, not just closed off: the
  sampler, validator, card text, costing, complexity, coverage, engine (`ACTIVATE`), graph
  feature and client. Generated sets are unchanged (the option had weight 0). Checkpoints now
  save their feature and action names, and older ones load without the dropped column and row,
  with identical outputs.
- **2026-10-28:** The rest of the v1 exhaust / ready grammar removed: the `exhaust` and `ready`
  effects, the "exhausted" / "ready" filter and the "this unit is exhausted" condition (none
  were generated). The engine's `exhausted` flag is now `attacked`, and freeze is its own
  check, lasting through the frozen unit's owner's next turn. Generated sets are unchanged.
- **2026-10-29:** The trace's "Card kind" decision is now two: "Card type" (unit or action),
  then for units "Unit kind" (vanilla, keywords only or ability). It is still one draw, so
  generated sets are unchanged; only the derivation the explorer and visualiser show differs.
- **2026-10-29:** No "you may … if you do" on action cards: the sampler closes that step
  pattern for on-resolve abilities (a sampler test checks it). Units keep it. Generated sets
  change from here on; the committed card sets still have some may-actions until they are
  regenerated, and they still load (the engine and validator allow them).
