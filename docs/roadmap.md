# Roadmap

Open work only. When something lands, delete its item (git history keeps it), put any numbers in
[results.md](results.md), and record a decision where it constrains future work: in CLAUDE.md, or the
design doc it belongs to. The design is [technical-plan.md](technical-plan.md); part 2's plan is
[stage-2-research-plan.md](stage-2-research-plan.md).

Where things stand (2026-11-19): the engine runs rules v2 with generated ability cards. The
agent (`tcgnet_v6b`, fine-tuned for classes as `v7c_best`) beats the heuristic player 79% on cards
it has never seen, 89% with search within a turn, which the server's AI now uses. P2's first
grammar batch is in, and the class set `set_1000_c` has six classes on a ring of play styles.
MAP-Elites finds the best decks of each class, and the first metagame (a matchup table and its
Nash equilibrium) shows the prices are the problem: Bog and Ember win on underpriced draw and
removal (results.md, 2026-11-19). The Unity client plays all of it, with painted art and a GNN
overlay. Blog part 1 is published.

**The order (decided 2026-11-19):** the agent, the prices and the metagame depend on each other,
so they're iterated together, with the cheap parts inside and the expensive part outside. Prices
and the metagame (minutes a round with the heuristic) loop many times with a fixed agent; the
agent (hours a round) is retrained rarely, and since it sees card features, not IDs, a fine-tune
adapts it to repriced cards. Pricing comes from the equilibrium, not from average decks, and
repricing and double-oracle deck building are one loop. Steps 2–5 below, in order (step 1, the
metagame module `src/deck_search/metagame.py`, is done).

## Now: prices from the metagame (plan F2 and 3B)

- [ ] **2. Reprice a set in place:** the same abilities and cards, new costs and stats from new
  group scales (today a new price means regenerating the set). Each card keeps its
  `budget_delta`.
- [ ] **3. The combined loop, with the heuristic:** solve the smoothed mix (`metagame.qre`; the
  plain Nash mix jumps with noise) → update the group scales by each
  group's over- or under-use in the mix against a target (prices as a market: raise what the mix
  over-buys) → reprice → re-play the table → add the best response (MAP-Elites with the mix as
  its field: double oracle; `Matchups.extend` plays only its new pairs) → repeat. About 15–20 minutes a round. Start from the worst groups
  (action draw, removal that draws, self-situational units), then see whether the growth groups
  (action summon and buff, lords) need cheaper prices. Every few rounds, re-play the table with
  v7c_best: a price the heuristic likes but the model doesn't is the heuristic's bias.
- [ ] **4. The learned cost model** (card features → the price the loop settled on), so new
  generated sets start near balance. Checks: does it find the deliberately mis-costed cards
  (`notes.budget_delta`, ±1 on ~30% of cards)? Is it self-consistent (a stable value for +1 power
  or health)? Does it rediscover "a fair vanilla unit has about 2 × mana + 1 stats"? Then it
  replaces the hand-written value table.
- [ ] **5. Per-card fixes** (worst-case pricing, plan 3C / M4) for the outliers the group scales
  leave, then P3's agent training on the settled set: about half random and half elite decks,
  judged with `scripts.benchmark --decks` on `heldout_200_c`'s elites (v7c2, fine-tuned on
  random decks only, lost its lead there; results.md, 2026-11-19). Re-search or re-score that
  archive with the model (`--agent`), since heuristic-found elites suit the heuristic.
- [ ] Literature check before the blog claims the combined loop is new: "Metagame Autobalancing
  for Competitive Multiplayer Games" (Hernandez et al., about 2020) tunes game parameters to a
  target metagame, and "Evolving the Hearthstone meta" changes card stats by simulation. Ours adds
  generated cards, prices that carry to the generator, and double-oracle deck search in the loop.
  The same search covers play-style-conditioned generation.

## Later: a stronger and faster agent (part 2, plan section 6)

- [ ] **P4, search in training** (expert iteration), once step 5 has trained on elite decks.
- [ ] **Faster learning:** the PPO update is now about 85% of an iteration (results.md, speed), and
  it's compute: more threads, MPS and bigger minibatches don't help. Options: a CUDA GPU, a
  smaller or cheaper model (fewer edge types or layers), or fewer epochs. No TPU / JAX work until
  the model is the bottleneck.
- [ ] **Search with the GNN** (M2): the GNN plays about 0.9 games a second per process (6.9 with
  8 workers), about 120× slower than the heuristic, so today it can only re-score archives and
  tables. Batch its inference across games, and follow Deep Surrogate Assisted MAP-Elites (Zhang
  et al., GECCO 2022, arXiv 2112.03534): a surrogate trained on the decks played so far predicts
  fitness and the measures, MAP-Elites runs on the surrogate, and only its elites are played for
  real. The paper's input is a bag of cards (one count per card), which works within one set;
  card features pooled over the deck would also carry to unseen sets. The same surrogate can
  screen matchups for the table.
- [ ] Actions are still a little weak (37% against vanilla swaps before v4; v4 50%): re-check
  once the loop prices them.
- [ ] **Merge `part2-agent` into `main`** once the Unity client is checked against it (v6b needs
  this branch's code). Optionally restore the Unity 6000.3.28 upgrade on `main` first.

## Deck search and classes, alongside

- [ ] **Classes, what's left** (the ring is built, plan 4G): enabler checks per class (every payoff
  has enough enablers, e.g. token payoffs and summoners, action_played and actions); put the
  class on the hero only (cards keep their aspect as data, not a network feature); the client
  (class on the hero, neutral grey).
- [ ] **Check the ring map's measures** (built 2026-11-18: six style measures projected onto the
  ring, `--axes ring`, the default): with 65% class decks every class's best decks land in or
  next to its own sectors (results.md, 2026-11-19). The fortress measure is still noisy (neutral
  Guard units take hits in every class) and the spells sectors fill least; refine them if classes
  overlap. A CVT archive over all six measures is the fallback if different decks share
  cells.
- [ ] **M0 / M1, planted synergies:** a planted-synergy benchmark, and does the search find the
  planted combos within a known budget? Re-evaluate elites on fresh games (their search scores
  are a maximum over noisy evaluations).
- [ ] Play-style space (plan 4H): generation → card statistics → play style; a synergy graph
  and community detection for emergent archetypes.

## Card generation

Rule: general tests on the tree's shape, never rules about particular cards.

- [ ] **Second grammar batch:** interacting with abilities and making cards (ability-generation.md,
  "What's missing" 8 and 9), and what's left of 2, 3, 5 and 10 (split damage that can hit the
  hero, a draw trigger).
- [ ] Split damage is rare (7 in `set_1000_g2`): the variety stage keeps few of one shape. Raise
  its weight if deck search needs more of it.

- [ ] Keyword equivalence: write keywords in the DSL; an ability that compiles to a keyword becomes
  the keyword ("+1 power while attacking" = Duelist +1).
- [ ] Fits the cost curve: reject cards worth more than the top cost can pay for.
- [ ] Job reachability: keep job conditions that a deck from the set can meet.
- [ ] More varied "you may" costs (only 4 kinds, so they repeat).

## Engine and graph

- [ ] The `for_each` step: repeat steps once per matching card ("for each damaged enemy unit,
  draw a card"). In the grammar, not sampled or run. "For each" *amounts* ("deal 1 damage for
  each Miner you control, up to 4") are already built and generated.
- [ ] Items (a card type).
- [ ] Active effects as graph nodes (`active_effect`, `affects`, `source_of` edges).
- [ ] Search past the end of the turn (IS-MCTS with the value head), on `Game.determinize`;
  a belief over the opponent's deck (their focus jobs from what they've played) instead of a prior.
- [ ] Check new cards in Unity against the coverage checklist after each grammar addition.

## Unity client

- [ ] Milestone 5 (small): neutral cards in grey, the hero's aspect on the portrait, vanilla
  cards' text box.
- [ ] Animate `summoned` (new units already appear from the state).
- [ ] GNN overlay step 2: animate message passing layer by layer (the `graph` reply has every
  layer).
- [ ] Design the mulligan, game-over and AI-turn screens properly.
- [ ] Later: a standalone mode (C# engine + ONNX model, as in PyTenTen).

## Blog

- [ ] **Batched updates** (do together, not piecemeal):
  - Part 1 and the README say v4 won 69% "on unseen cards"; that was `set_200`, which v4 trained
    on. On held-out cards it was 61.8%; v6b now gets 79%.
  - The README's agent section: 18 card features (8 static, 10 state; it says 24), one
    self-play process (it says 10), an iteration's time, and v6b's numbers.
  - Rebuild the demos (GNN visualiser: the card now has 8 static features, not 14) and re-copy
    them to the blog.
- [ ] **Part 2:** self-play and balancing. P1a and v6b; the learned cost model (does it
  rediscover the vanilla formula?); the MAP-Elites explainer (done); close on how classes could
  emerge later.
- [ ] **Part 3:** a game of our own, built by extending the grammar and regenerating the set.

## Research questions (later)

- [ ] **Missed lethal** (parked 2026-11-17: better decks in P3 may teach this anyway): v6b misses
  about 1 in 10 face lethals by trading instead of going face (results.md, tactical puzzles).
  Puzzle episodes in PPO (`--puzzles`) made it worse; plain extra self-play helped (94–97%). Next:
  reward a puzzle win more than a merely winning position (e.g. score a miss as 0, or a small
  bonus for winning sooner), or potential-based reward shaping, and re-score with
  `scripts.puzzles`. Re-check free hero attacks on v6b at the same time.
- [ ] **More puzzles:** "a much better line" beyond lethal (needs a judge other than the value head),
  and the checks "does it value draw 2, removal, may-costs sensibly?".
- [ ] Ablations: GATv2 vs SAGE / R-GCN; with and without `faces` edges; the flat per-ability
  baseline instead of ability subgraphs.
- [ ] Auxiliary value targets (final health difference, turns remaining).
- [ ] Does the agent use keywords well now (Armor-heavy 74% vs 79% held-out)? Per-keyword
  scenario tests if not.

## Open decisions

- **Part 3 twist:** what makes the game its own (Assist: drag a unit onto your own unit? a
  mycelium link between units? something from the dropped v1 mechanics?).
- **Game name.**
- **LLM naming pass?** Subtitles and action names come from phrase banks (~290 subtitles, 1,800
  action names); an LLM reading the card text could name cards better.
- **Jobs:** do jobs lean towards certain abilities? The final job and species lists, and how many
  jobs a set has.
- **Power budget while sampling?** Cap a rough power score while sampling, or let auto-costing
  reject anything above the top cost.
- **Sampling weights:** tune by hand, or fit them (keep / reject feedback, self-play measures)?
- **Complexity budget by rarity?** It's 4 nodes for every card.
- **Publish trained models?** Checkpoints are gitignored; the README points to the releases page
  for `tcgnet.pt`. Put v6b there?
- **When to move the engine off pure Python** (Rust / C# / numba), based on profiling.
- **DSL granularity:** template-sized building blocks or finer ones (a larger space, harder
  search)?
- **Set skeleton:** how much to fix by hand (cost curve, rarity, cards per class)?
- **Unity:** port the engine to C# for a standalone build later?
- Stage 2's own open questions are in its plan, section 7.

## Known limitations

- The network sees active effects ("frozen until…", "+1 power this turn") only through their
  results on stats and flags, not as nodes.
- The `for_each` step and items aren't in the engine ("for each" amounts are).
- Ability prices come from a hand-written value table scaled by measured factors per effect group,
  measured on average random decks, not from the metagame or a learned cost model.
- Dominated "choose one" options are only caught when both options have the same shape; abilities
  equal to a keyword aren't caught.
- Training runs on the CPU of one machine (self-play in up to 4 worker processes).
- The opponent's hand and deck are counts only, with no belief model. Search (`SearchAgent`)
  covers only the agent's own turn and guesses the opponent's cards from the set (a prior).
- The heuristic agent is deliberately simple (plays its most expensive card, makes favourable
  trades, otherwise attacks the hero; always says yes to "you may").
- A turn is capped at 50 plays and attacks and 100 abilities (`GameConfig`), so a runaway loop
  ends the turn instead of hanging.
- Unity: `NetMQConfig.Cleanup` can hang, so the network thread is abandoned on exit.
