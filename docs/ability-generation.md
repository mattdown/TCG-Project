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

- **No rules about particular cards.** A test never says "don't pair VP loss with healing".
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

`AbilitySampler.raw()` walks the grammar: ability kind (triggered / activated / static for
units, on-resolve for actions), then trigger, condition, step pattern, effects, targets and
numbers. The weights are hand-set placeholders (`EFFECT_WEIGHTS`, `TRIGGERS`, the step
patterns in `_steps`).

**One ability per card for now.** One idea per card keeps cards readable and makes each
ability's effect on a card measurable on its own. The engine and the card schema support more;
only the generator is limited.

### 2. Grammar (legality)

`validate()` checks the hard constraints from the technical plan: scope, types, polarity,
size limits, no runaway abilities, grant durations. The sampler builds legal trees by
construction, so this stage rarely rejects anything. It exists so that trees written by hand
or by another generator are checked in the same way.

### 3. Quality tests (`src/cards/quality.py`)

Legal isn't the same as worth generating. Three tests, each a general property of the tree:

| Test | Rule | Catches |
|---|---|---|
| **Complexity budget** | At most `MAX_COMPLEXITY` = 4 nodes. A node is each step (choice, effect, if, may, choose one), the condition, each activated cost beyond ⟳ and each static modifier. | Long abilities that stack a condition, a "you may", a choice and a follow-up |
| **Connected steps** | Every step after the first must act on a card that an earlier step acted on, or ask about it ("if it was defeated"). Choices only name a card and aren't counted. "You may … if you do" and choose one connect their parts by construction. | Unrelated effects glued together: "+1 health this turn. Your opponent loses 1 VP." |
| **No dominated options** | In a choose one, an option with the same shape as another (the same tree apart from its numbers) that is no bigger in any number is never worth picking. Every number in the grammar is better bigger for whoever chooses it, so no knowledge of particular effects is needed. | "Choose one: gain 3 VP, or gain 1 VP." Also the same option twice. |

The complexity budget is the main lever on how wild the set is. 4 rejects about 6% of raw
draws. Raising it later (by rarity, for example) is a one-line change.

Trade-offs worth knowing:

- **Players don't connect steps.** "Draw a card. Gain 1 VP." fails, even though both effects
  are on you. Counting the player as a link would let almost any pair of player effects
  through. Two-part player effects can still be written as "you may … if you do".
- **Dominance only compares options of the same shape.** "Gain 3 VP or your opponent loses
  1 VP" still gets through. Comparing different effects needs a value model, so it waits for
  the learned cost model or for the agent's choice statistics (below).

### 4. Build and cost the card

`CardGenerator._build` turns the ability into a card:
- **Names:** mushroom species + job.
- **Aspect:** random.
- **Energy source:** 80% of cards.
- **Cost and stats:** from the rough ability value in `src/cards/costing.py`. Units also get an
  archetype (how stats are spread) and sometimes a keyword. Every unit scores at least 1 VP.

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

Card lab, seed 1, 60 cards, 6 jobs, variety 4: 329 draws, 60 kept.

| Stopped at | Draws | Main reason |
|---|---|---|
| Grammar | 0 | (legal by construction) |
| Quality | 85 | steps not connected 50, too complex 31, dominated option 4 |
| Card | 4 | couldn't matter on the card |
| Variety | 180 | expected: 3 of every 4 good draws are set aside |

Problems still visible in the output, and what will deal with each:

| Problem | Example | Fix |
|---|---|---|
| Options of different shapes where one is clearly better | "Gain 1 VP for each Archer (up to 5), or gain 1 VP" | Value model (learned cost model, or agent choice spread) |
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

The card lab (`PythonServer/scripts/card_lab.py`) runs the whole pipeline and shows every
stage, including what was thrown away and why. Run these from `PythonServer/`.

The web page, at <http://localhost:8765>. Change the seed, set size, jobs, action share and variety there:

```bash
uv run python -m scripts.card_lab
```

The same output in the terminal (`--rejected` adds the thrown-away draws):

```bash
uv run python -m scripts.card_lab --text --count 50 --rejected
```

A self-contained page with one batch baked in, which needs no Python to view (for sharing or a blog post):

```bash
uv run python -m scripts.card_lab --export lab.html --seed 7 --count 80
```

The page shows:
- each kept card in the client's card style
- the funnel of draws through each stage, with counts per reason
- for each card, the checks it passed, its costing, its ability tree and its shape

`scripts.generate_cards --kind coverage` builds the coverage set for checking the engine and
client. It uses the same pipeline.

## Log

- **2026-10-20:** First version.
  - New quality tests: complexity budget 4, connected steps, dominated options.
  - New variety stage and card lab.
  - One ability per card.
  - New card check: a keyword the unit already has.
  - Card text now says "chosen opposing Chef unit", not "chosen Chef opposing unit".
