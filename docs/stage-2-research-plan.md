# Stage 2 research plan: balancing against the best decks

Stage 1 showed the system works: an agent that reads cards it has never seen, a generator
whose prices can be measured in play, and a loop where better prices made skill matter more
(the trained agent went from 62% to 75% against the heuristic agent on unseen cards once actions
and abilities were priced from measurements, `ability-generation.md` log, 2026-10-23).

Stage 2 is the research problem: pricing cards so that **no deck is broken**, not just so that
the average card is fair.

## 1. Why stage 1's method isn't enough

Every measurement so far prices a card by its **average value across random decks**: the
deck tests, the price scales and the per-effect calibration (`scripts/experiments.py`).

Real balance is about the **best decks a card can be in**. Players find them, and the
metagame forms around them. A card that is fair in 99% of decks and twice as strong in one
combination defines the format. The current method misses it twice over:

- **Random decks almost never assemble a synergy.** A specific two-card combination in a
  1,000-card pool shows up in a tiny share of games.
- **Averaging hides it when it does.** A 1% tail barely moves a mean.
- **A synergy only shows if the agent can play it.** Combos need setup and sequencing, so a
  weaker agent undervalues exactly the cards that are dangerous in skilled hands. Prices are
  already skill-dependent: v4 got more out of unit abilities than v3 did on the same cards.

So the question changes from "what is this card worth on average?" to "what is the most this
card can be worth, in the decks a strong player would build?"

## 2. What "balanced" means: targets we can measure

Stage 2 needs targets that are numbers, so methods can be compared:

| Target | Measure |
|---|---|
| **No dominant deck** | The best deck found wins at most X% (e.g. 60%) against the field of strong decks |
| **A diverse metagame** | Many decks in the equilibrium mixture (below), from different jobs and card types |
| **Most cards playable** | Share of cards that appear in at least one strong deck |
| **No must-play card** | No card appears in more than Y% of strong decks |
| **Fair on average** | Stage 1's tests stay near 50% (a regression check, not the goal) |
| **Skill matters** | A stronger agent beats a weaker one by a clear margin on balanced sets |

## 3. Building blocks we already have

- **Engine:** fast, deterministic, hidden information handled, fuzz-tested.
- **Agent:** reads ability trees as graphs, so it handles any generated card;
  `tcgnet_v4` beats the heuristic agent 75% on unseen cards.
- **Generator:** controls where synergy can come from (jobs, triggers such as "whenever you
  play another Baker", summons, buffs, "for each" counts), with derivation traces.
- **Measurement harness:** `scripts/experiments.py` with paired seats, parallel workers, and
  re-priced copies of cards. Throughput on this Mac is roughly 5–10 games a second with the
  neural agent across 10 processes; the heuristic agent is much faster.

The main constraint is compute: every method below spends games, and search over decks spends
a lot of them.

## 4. Approaches

### A. Deck search

Search deck space for the strongest decks, with the agent playing them. Candidates:
- **Evolutionary search:** mutate decks (swap cards), keep the winners against a field.
- **Quality-diversity (MAP-Elites):** keep the best deck in each niche (e.g. by main job,
  curve, share of actions), so the search maps the space of *different* strong decks instead
  of converging on one.

A card's value is then measured in the decks that are good. Cost: thousands of games per
generation, so it needs a cheap evaluator (D).

### B. The metagame as a game

Treat deck choice as a game between players and solve it:
- **Double oracle / PSRO:** keep a population of decks, compute the equilibrium mixture of
  the matchup table, add the best response to that mixture (found with A), repeat.
- The equilibrium gives the balance targets directly: how many decks it uses, whether one
  dominates, which cards appear in it.

### C. Worst-case pricing per card (red-team decks)

For each card, search for the deck that gets the most out of it, then raise its price until
even that deck isn't dominant. This is minimax pricing instead of averaging, and it is the
direct answer to the "1% of decks" problem. Doing it for every card is expensive, so it
should run on cards flagged by D or E.

### D. Deck-level surrogate model (synergy-aware cost)

Predict a deck's strength from its cards: card embeddings (the agent's card encoder) combined
with attention, trained on game results and matchups from A–C.
- **Synergy becomes measurable:** the deck's predicted value minus the sum of its cards' values.
- **It's the cheap evaluator** deck search needs, with real games only to check the best candidates.
- **It generalises the cost model:** a card's price is no longer one number but a function of
  the deck around it, and the price that matters is its value in the best decks.

### E. Targeted exploration from the generator

The generator knows which cards reference each other: a job trigger and that job's units,
"for each unit" and summons, buffs and wide boards. A graph of these references can point A
and C at likely combinations, instead of waiting to find them by chance.

### F. A stronger player

Synergies only matter if the agent can play them. Candidates:
- **Search at play time:** determinized MCTS or IS-MCTS (guess the hidden cards, search each
  guess) with the value head at the leaves. A turn's order of plays and attacks is the main
  planning problem, and the engine is deterministic within a turn, so even shallow search
  should help.
- **Longer training on more varied decks**, including decks from A, so the agent learns to play
  strong archetypes, not just random piles. Probably on a cloud GPU.

## 5. A first experiment with ground truth: planted synergies

Before trusting any method, test it on synergies we put there on purpose:
1. Take a balanced-on-average set and **plant** a few deliberately broken combinations: two
   fair-looking cards that together are far too strong (e.g. "your Bakers get +2/+2" plus
   cheap Baker summons), and a few deliberately overpriced cards as controls.
2. Ask each method to find them. Can random-deck averaging see them (expected: no)? Does
   deck search find the combination? Does the surrogate flag it as synergy? Does red-teaming
   price it correctly?
3. Measure how many games each method needs to find each planted combination.

This gives stage 2 what the ±1 mis-costed vanilla cards gave stage 1: a known answer to check
methods against. It's also a clear story for the blog.

## 6. Proposed order

| Milestone | Work | Done when |
|---|---|---|
| **M0** | Planted-synergy benchmark (section 5); metrics from section 2 as code | Random-deck averaging is shown to miss the planted combos |
| **M1** | Deck search (A): evolutionary first, MAP-Elites second | It finds the planted combos within a known budget of games |
| **M2** | Deck-level surrogate (D), trained on M1's games | It predicts held-out matchups well and flags planted synergies |
| **M3** | Metagame loop (B) using M1 for best responses and M2 to screen | An equilibrium over decks with diversity numbers |
| **M4** | Worst-case pricing (C) on flagged cards, then re-generate | The section 2 targets hold on a fresh set |
| **M5** | Stronger player (F) and scale to 3,000 cards | Targets still hold with a stronger agent; cloud runs |

F can start alongside any milestone: a stronger player makes every other measurement more
trustworthy.

## 7. Open questions

- **Where does the price live?** One cost per card, or a base cost plus learned deck-dependent
  corrections? Printed cards have one cost, so worst-case pricing has to collapse to one number.
- **Which field?** Balance against what: the equilibrium mixture, a fixed set of archetypes, or
  every deck found so far?
- **Skill dependence:** prices measured with agent N can be wrong for agent N+1. Re-measure
  after every agent improvement, or price for a fixed reference agent?
- **Aspects as classes:** turning on one aspect per deck (`ONE_ASPECT`) shrinks deck space a lot
  and is how real games contain synergy. When should it come in: before deck search, or as one
  of its results (clustering)?
- **Compute:** how much of this fits on the Mac, and what goes to a cloud GPU (training) or many
  CPUs (games)?
- **Changing the generator vs re-pricing:** when a combination is broken, raise a price, change
  the card, or stop the generator making that pattern (a new general test)?

## 8. Related work to check

From memory, to verify before relying on it:
- Deck building by evolutionary search for Hearthstone (several papers around 2016–2019).
- MAP-Elites applied to Hearthstone deck spaces (around 2019).
- "Evolving the Hearthstone meta": balancing by simulating a metagame (around 2019).
- PSRO (policy-space response oracles, 2017) and double-oracle methods for population-based
  game solving.
- Legends of Code and Magic: a research card game with competitions on drafting and playing.

Read in full:
- **AI Playtesting** (<https://aiplaytesting.github.io/>), a 14-week project: an AI playtester for
  Slay the Spire, with 32 reimplemented cards and fixed 12–13 card decks against one scripted
  boss. The rules run in Python with Unity as a front end (the same split as ours), plus a
  designer app to build decks, train the agent with one click and chart playtest statistics.
  The agent is Deep Q-learning on a hand-made state vector with one output per card, so new
  cards mean retraining; action masking took it from a few percent to about 60%, and to 87–90%
  on two test decks a human always wins. Balancing is a designer reading the statistics.
  Useful for us:
  - **Decks with a known answer** to judge the agent: the same idea as our planted synergies.
  - **The agent missed the designers' combo** (playing Flex before attacks): a concrete case of
    section 4F, where an agent that can't execute a synergy undervalues its cards.
  - **The differences** are the point of this project: an agent that reads cards it has never
    seen (generated cards), two-player self-play instead of a scripted boss, and a closed loop
    that re-prices and regenerates cards instead of handing a designer a chart.

## 9. Blog part 2

The frame: **average-case balance versus worst-case balance.** Stage 1 is the average case,
and it worked (the hand-written cost table was off by about 2×, and self-play proved it).
Then the planted-synergy experiment shows why that isn't enough, and the rest of the post is
the search for the decks that break a set.
