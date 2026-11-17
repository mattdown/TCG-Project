# Roadmap

Open work only. When something lands, delete its item (git history keeps it), put any numbers in
[results.md](results.md), and record a decision where it constrains future work: in CLAUDE.md, or the
design doc it belongs to. The design is [technical-plan.md](technical-plan.md); part 2's plan is
[stage-2-research-plan.md](stage-2-research-plan.md).

Where things stand (2026-11-17): the engine runs rules v2 with generated ability cards, priced from
measurements on random decks (stage 1). The agent (`tcgnet_v6b`) beats the heuristic player 79% on
cards it has never seen, 89% with search within a turn, which the server's AI now uses. Part 2 has
started with a stronger agent and the cost model. The Unity client plays all of it, with painted
art and a GNN overlay. Blog part 1 is published.

## Now: a stronger agent (part 2, plan section 6, P1–P4)

- [ ] **Tune search:** beam and top-k (4 and 4 now; wider or deeper isn't measured).
- [ ] **Tactical puzzles:** positions from real games where a short search finds lethal or a much
  better line; does the policy find it? A diagnostic first (and the way to check "does it value
  draw 2, removal, may-costs sensibly?"), training targets later if it keeps missing them.
- [ ] **Free hero attacks:** re-check on v6b (results.md); if it still passes them up, add
  potential-based reward shaping on the hero-health difference.
- [ ] **Faster self-play:** parallel self-play workers (the play half of an iteration, ~3–5×),
  then larger batches per iteration. `torch.compile` or a CUDA GPU only if learning dominates
  after that. No TPU / JAX work until the model is the bottleneck.
- [ ] **P2, first grammar batch:** pick items from [ability-generation.md](ability-generation.md),
  "What's missing" 1–16, when it starts.
- [ ] **P3, the joint loop:** train on about half random and half elite decks → price with the
  frozen agent (the cost model) → MAP-Elites deck search (move `map_elites()` from `Blog/` into
  PythonServer) → a fixed benchmark. The cost model work below is part of it.
- [ ] **P4, search in training** (expert iteration), once P3 runs.
- [ ] **Merge `part2-agent` into `main`** once the Unity client is checked against it (v6b needs
  this branch's code). Optionally restore the Unity 6000.3.28 upgrade on `main` first.

### The learned cost model (part of P3)

- [ ] Each card's effect on win rate from self-play (win rate when played, adjusted for turn).
- [ ] Cost model: card embedding → fair cost.
- [ ] Does it find the deliberately mis-costed cards (`notes.budget_delta`, ±1 on ~30% of cards)?
- [ ] Is it self-consistent (a stable value for +1 power or health)? Does it rediscover "a fair
  vanilla unit has about 2 × mana + 1 stats"?
- [ ] Re-cost, retrain, repeat until stable; then it replaces the rough value table.
- [ ] Actions are still a little weak (37% against vanilla swaps before v4; v4 50%): re-check
  once the cost model prices them.

## Next: stage 2, deck search and classes

- [ ] **M0:** planted-synergy benchmark, and section 2's balance targets as code.
- [ ] Measure games a second for the GNN (batched and not) and the heuristic agent.
- [ ] **M1:** adapt Fontaine et al. 2019 (MAP-Elites over decks, sliding boundaries,
  health-difference fitness): heuristic agent first, then a play-measured descriptor (share of
  damage to the hero), then re-score the archive with the GNN.
- [ ] **Class generation vectors** (plan 4G): a shared base plus sparse per-class offsets on the
  sampler's weights, hard zeros, themes as bundles, one cost model for all; quotas and enabler
  checks per class. Then turn on `ONE_ASPECT` and put the class on the hero only.
- [ ] MAP-Elites over a class-weighted set: do classes land in different regions of the map?
- [ ] Play-style space (plan 4H): generation → card statistics → play style; a synergy graph
  and community detection for emergent archetypes.
- [ ] A proper literature search before claiming play-style-conditioned generation is new.

## Card generation

Rule: general tests on the tree's shape, never rules about particular cards.

- [ ] Keyword equivalence: write keywords in the DSL; an ability that compiles to a keyword becomes
  the keyword ("+1 power while attacking" = Duelist +1).
- [ ] Fits the cost curve: reject cards worth more than the top cost can pay for.
- [ ] Job reachability: keep job conditions that a deck from the set can meet.
- [ ] More varied "you may" costs (only 4 kinds, so they repeat).
- [ ] Health buffs that last through the opponent's turn (a "this turn" health buff at the start
  of your turn does nothing).
- [ ] Later: automate the group-price loop (measure → partial update → regenerate → fine-tune).

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
  not from a learned cost model, and only for average random decks.
- Dominated "choose one" options are only caught when both options have the same shape; abilities
  equal to a keyword aren't caught.
- Self-play is a single process on the CPU.
- The opponent's hand and deck are counts only, with no belief model. Search (`SearchAgent`)
  covers only the agent's own turn and guesses the opponent's cards from the set (a prior).
- The heuristic agent is deliberately simple (plays its most expensive card, makes favourable
  trades, otherwise attacks the hero; always says yes to "you may").
- A turn is capped at 50 plays and attacks and 100 abilities (`GameConfig`), so a runaway loop
  ends the turn instead of hanging.
- Unity: `NetMQConfig.Cleanup` can hang, so the network thread is abandoned on exit.
