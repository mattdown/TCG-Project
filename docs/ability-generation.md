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
| **Connected steps** | Every step after the first must act on a card that an earlier step acted on, or ask about it ("if it was defeated"). Choices only name a card and aren't counted. "You may … if you do" and choose one connect their parts by construction. | Unrelated effects glued together: "+1 health this turn. Deal 1 damage to the enemy hero." |
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
- **Aspect:** random, or neutral 10% of the time. Aspects have no identity yet (it will come
  from a designed generation vector per aspect, stage-2 research plan 4G), so for now decks
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

## What the generator can say

The grammar in technical-plan.md section 3 is the full design space. The generator covers only
part of it, and the engine runs a little more than the generator makes. Counts are from
`cardsets/set_200.json` (139 of its 200 cards have an ability), or `set_1000_g2` (716 of 1,000,
the grammar since P2's first batch) where marked.

**Generated now:**

- **Kinds:** triggered (12 triggers: when played, when it attacks, when it attacks the enemy hero,
  when it's defeated, start and end of your turn, when you play another unit of a job, when an
  enemy unit is defeated, and since P2: when another of your units (of a job) is defeated, when
  this unit takes damage and survives, when you play an action, when you summon a token; 79 of
  the newer ones in `set_1000_g2`), static, and on-resolve for actions. One ability per card.
- **Effects (14):** deal damage, remove damage, defeat, return to hand, freeze, a "this turn"
  **power** bonus or penalty (never health: health only changes for good, through buffs), a
  **lasting buff** (+power and/or +health until the unit leaves play; 10 in `set_200`), grant a
  keyword (Guard, Armor or Duelist, for a set duration), draw, discard, heal your hero, damage a
  hero, gain a mana crystal, summon tokens (the most common effect, 42).
- **Step patterns:** one effect, two effects, "deal damage; if it was defeated, …", "you may … if
  you do …" (units only) and "choose one".
- **"For each" amounts:** damage, draw, hero healing, power bonuses and lasting buffs can scale
  with a count, up to a cap of 3–5: units of a job (yours or everyone's), damaged units, your
  units with a keyword, cards in your hand, or cards you played this turn. A static "while
  attacking" bonus can scale with units of a job: "+1 power for each other Miner you control".
  Health never scales with damaged units. 16 in `set_200`; in `set_1000_g2`, 22 count damaged
  units, 24 a keyword, 8 your hand and 22 buffs or power bonuses scale.
- **Conditions:** "if you have 2 or 3 other units of a job", "if you've played 2 or 3 other cards
  this turn" (45 abilities mention cards played this turn in `set_1000_g2`), "if your hero has
  less health", "if it was defeated", and for statics "while attacking / defending / damaged".
- **Statics:** a bonus while attacking or defending, +1 to your other units of a job, a keyword
  while damaged or while you have other units of a job, cost −1 for a job, and −1 power for
  damaged enemy units.
- **Targets:** a chosen unit, a **random** unit (94 in `set_1000_g2`), all units matching a filter,
  this unit, you or your opponent, and **damage split at random** among enemy units ("deal 4
  damage split at random among enemy units": a `repeat` of a random choice and 1 damage; 7 in
  `set_1000_g2`, since the variety stage keeps few of one shape). Filters: whose, a job (your
  side only), damaged, cost at most 2–4. Random choices are made by the engine's random numbers,
  never a player; previews stop at them, so neither the network nor the client sees how they'll
  fall.
- **Rules that keep the new triggers sensible:** "when this takes damage and survives" never gives
  this unit health (no buff with health, no "remove damage"), and needs at least 2 health; "when
  you summon a token" never summons.

**The engine runs, but the generator doesn't make:** "else" branches, amounts equal to a
unit's stat (`stat_of`: "deal damage equal to its power"; the graph encoder has no feature
for it yet), "its owner" as a target (`owner_of`), "if it's still in play" and "if it's your
turn" conditions, the "while this is in play" duration, choices the opponent makes
(`chooser`), and zone filters beyond the two uses the generator makes of the hand (a chosen
discard and a cost discount). Each is a small step: a sampler branch, its text,
its price and a test.

**In the grammar, but not built yet:** the `for_each` step (repeat steps for each matching
unit: "for each damaged enemy unit, draw a card"), the durations "until their next turn" and
"permanent", optional choices ("up to one"), and cost comparisons other than "at most". The
keyword filter is built but only used for counts, and `repeat` only for split damage.

**What's missing for a richer set** (part 2's grammar work, roughly in order of value):

1. **Durations that fit the effect.** Done differently in P2's first batch: there are no
   temporary health changes at all (a "this turn" health bonus mostly did nothing).
2. **More things to count.** P2's first batch added damaged units, units with a keyword, cards
   in your hand and cards played this turn, and scaling buffs and power bonuses. Still missing:
   units defeated this turn, the stat of a chosen unit, and scaling summons.
3. **More triggers.** P2's first batch added your own units being defeated, taking damage and
   surviving, playing an action, and summoning a token. Still missing: drawing (it risks loops
   with draw effects) and a unit surviving a fight it started. Triggers are where combos and
   synergy come from, so this matters most for part 2's synergy work.
4. **Other zones.** Abilities only touch the board, the hand (discard) and the deck (draw).
   Missing: bringing a unit back from the discard pile, searching the deck for a job, changing
   the cost of cards in hand, copying or transforming a card.
5. **Memory.** P2's first batch added "cards played this turn" (each card remembers the turn it
   was played), as a condition and a count. Still missing: counters and other history (units
   defeated, damage dealt this turn). A unit that grows is a lasting buff on this unit from a
   repeating trigger.
6. **More card kinds and keywords.** Only units and actions, and five keywords. Items (lasting
   cards that aren't units), hidden traps that trigger on the opponent's turn, and keywords such
   as healing your hero when this deals damage or defeating any unit this damages are the
   obvious candidates, all with placeholder names.
7. **More than one ability per card,** once single abilities are priced well.

Compared with the genre as a whole (mechanics many card games share, described generically,
with placeholder names when built; never copied cards), also missing:

8. **Interacting with abilities.** Removing a unit's text, transforming a unit into another,
   taking control of an enemy unit, setting or swapping stats. Today an ability can only be
   answered by removing the whole unit.
9. **Making cards.** Adding a random card to hand, "pick one of three" generated options,
   shuffling cards into a deck. Card advantage and variety in play, and a good fit for a
   generated set.
10. **Randomness.** P2's first batch added random targets and damage split at random among enemy
    units. Still missing: split damage that can also hit the enemy hero, and random cards (with
    making cards, 9). Coin flips ("50%: …") are left out on purpose: they swing games and are hard
    to price.
11. **Keyword staples.** Heal your hero when this deals damage; defeat any unit this damages;
    ignore the first damage taken; attack twice a turn; can attack units but not the hero the
    turn it's played; extra damage on your actions; a delayed cost (locks mana next turn).
12. **Board position.** Nothing cares about neighbouring units.
13. **Hero-level play.** No repeatable hero power, no hero weapon or hero attacks, no hero armor.
    A hero power is a big structural change and a candidate for part 3.
14. **Card kinds.** Weapons for the hero, besides items and traps (6).
15. **Long-term goals.** Quest-like cards that reward completing a condition over several turns.
16. **Conditions on hand or deck.** "If you're holding a Baker", conditions on what's in your deck.

**Priority:** triggers, counting and memory (2, 3, 5) create synergy, so they give deck search
something to find; P2's first batch (2026-11-17) did the bulk of them, plus randomness (10).
Interaction and making cards (8, 9) add the most depth and are the obvious second batch. Hero-level play and
new card kinds (13, 14) change the game itself and probably belong to part 3. Which items go in
part 2's first batch is decided when that work starts (stage-2 research plan, step P2).

## Where it stands

Card lab, seed 1, 60 cards, 6 jobs, variety 4: 449 draws, 60 kept (P2's first batch,
2026-11-17; 340 just before it).

| Stopped at | Draws | Main reason |
|---|---|---|
| Grammar | 1 | almost always legal by construction (the rare exception: a "this turn" bonus at the end of the turn) |
| Quality | 87 | mostly steps not connected, then too complex (dominated options are rare) |
| Card | 174 | mostly actions too weak to be a card (worth less than 1 mana): random targets are priced at 0.65 of a chosen one, so small random actions fall below it; then keywords a cheap unit can't pay for (89 before the batch) |
| Duplicate | 1 | the same card as one already kept |
| Variety | 126 | expected: most good draws are set aside |

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
  default seed, 0, gives the first cards of `set_200`, which have art (from a snapshot of their
  draws, `Blog/data/set_200_draws.json`, since today's grammar gives other cards for seed 0);
  other cards get a placeholder mushroom in their aspect's colour
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
- **2026-11-05:** New section "What the generator can say": what is generated, what the engine
  runs but isn't generated, what is in the grammar but not built, and what a richer set needs.
  No code change.
- **2026-11-15:** "What's missing" extended with gaps compared with the genre (8–16: interacting
  with abilities, making cards, randomness, keyword staples, board position, hero-level play,
  card kinds, long-term goals, conditions on hand or deck) and a priority note. No code change.
- **2026-11-17:** P2's first grammar batch (stage-2 plan, P2).
  - No temporary health: "this turn" stat changes are power only (health only changes through
    lasting buffs). Old sets with health bonuses still load and run.
  - Four triggers: another of your units (of a job) is defeated, this unit takes damage and
    survives (it never heals itself, and needs 2 health), you play an action, you summon a token
    (it never summons).
  - Counts: damaged units, your units with a keyword, cards in your hand, cards you played this
    turn (`played_this_turn`, a filter over cards in any zone but the deck). Lasting buffs and
    power bonuses can scale; health never scales with damaged units.
  - "If you've played 2 or more other cards this turn" as a condition.
  - Randomness: random targets (a choice whose chooser is `random`) and damage split at random
    (`repeat`, unrolled in the decision graph). Previews (the network's action outcomes and the
    client's) stop at the first random choice.
  - Rough prices: the new triggers' use rates are guesses (1.0, 0.8, 0.6, 0.5), a random target
    is worth 0.65 of a chosen one.
  - New sets `set_1000_g2`, `heldout_200_g2` and `armor_heavy_g2` (same seeds and recipes as the
    old ones); the old sets stay for comparisons. The coverage set was regenerated.
  - The card lab, generation visualiser and design loop keep `set_200`'s cards (the ones with
    painted art) from a snapshot of their draws made with the grammar of the time.
- **2026-11-18, measured use rates.** `experiments.py fire` with tcgnet_v7g2 on `set_1000_g2`
  (results.md): every trigger's use rate in `costing.TRIGGER_USES` is now the measured one. The
  four new guesses were all too high (`damaged` 0.8 → 0.43, `token_summoned` 0.5 → 0.32), and
  so were most of the 2026-10-22 rates (start of turn 1.1 → 0.64, end of turn 2.0 → 1.31); only
  an enemy unit being defeated went up (1.0 → 1.26). The `_g2` and coverage sets were
  regenerated with the same seeds; the new prices change which draws are kept, so most cards
  differ. The fire check's narrowing test no longer mistakes the `damaged` trigger for a filter.
- **2026-11-18, pricing from v6b.** `experiments.py effects` re-measured with v6b: removal was
  priced for a weak agent (`GROUP_SCALE` for unit and action damage up 1.5–2.3×), random targets
  were too cheap (`RANDOM_TARGET` 0.65 → 0.85), and unit groups priced at a floor (draw, summon,
  heal_hero, gain_crystal) take measured scales. `--groups` tests feature groups (random target,
  choose one). Deck search still finds over-used groups each round (results.md, deck search).
- **2026-11-18, classes.** `generate_card_set(classes=True)` (`src/cards/classes.py`): six play
  styles on a ring, each aspect two neighbouring ones; a style is a set of multipliers on the
  sampler's labelled choices, applied by the tracer (`Tracer.tilt`). A class never makes its
  opposite styles' signatures (a class check throws away what a forced path reaches) and damps
  its neighbours'. Class cards take one style or both (bridge, 20%); actions are a per-style
  share. Neutrals: 30%, units only, 70% vanilla (keywords allowed), the rest one style's ability
  with a one-stat-point tax. In class mode the variety stage compares only draws in the first
  draw's price group, since comparing across groups favoured damage (it has the most shapes).
  New sets `set_1000_c`, `heldout_200_c`, `armor_heavy_c` (194 cards: Armor is now Fortress only).
- **2026-11-20, clashing keywords.** A unit's second keyword can't clash with its first
  (`CLASHING_KEYWORDS` in `src/cards/vanilla.py`: Guard and Elusive). A playtest found an Elusive
  Guard that couldn't be attacked or chosen and didn't force attacks. The rules now let Guard
  override Elusive, so the one or two such cards in the saved sets play as plain Guards (their
  Elusive is wasted cost); the saved sets aren't regenerated, since any change to the draws
  reshuffles a whole set.
