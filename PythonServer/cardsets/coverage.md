# coverage: checklist

Generated from the grammar (seed 0), so every building block appears at least 2 times. Costs are rough (src/cards/costing.py).

## Cards

- [ ] **C1-001 Truffle Scholar** (cost 3, action)
  - Deal 3 damage to chosen damaged opposing unit. If it was defeated, draw a card for each of your Scholar units (up to 5).
- [ ] **C1-002 Truffle Miner** (cost 5, 2 power · 2 health · 1 score, Armor +1)
  - Whenever you play another Baker unit, deal 1 damage to chosen exhausted opposing unit for each Chef unit in play (up to 3). If it was defeated, put the top card of your deck into your energy zone, exhausted.
- [ ] **C1-003 Truffle Baker** (cost 5, 2 power · 4 health · 2 score, Charge)
  - When you play this unit, if you have fewer VP than your opponent, choose one: • Your opponent loses 1 VP. • Your other units get +1 score this turn.
- [ ] **C1-004 Truffle Lamplighter** (cost 3, 2 power · 1 health · 1 score)
  - ⟳, 1 energy: Choose one: • Your opponent discards a card at random. • Your other exhausted units get +1 power this turn.
- [ ] **C1-005 Truffle Chef** (cost 1, action)
  - You may discard a card. If you do, your units with cost 4 or less gain Guard until the start of your next turn.
- [ ] **C1-006 Truffle Postman** (cost 3, 1 power · 1 health · 1 score, Charge)
  - ⟳, exhaust another of your ready units: Choose one: • Put the top card of your deck into your energy zone, exhausted. • Gain 1 VP.
- [ ] **C1-007 Porcini Scholar** (cost 5, 3 power · 4 health · 1 score, Armor +1)
  - When you play this unit, you may lose 1 VP. If you do, your other units with cost 4 or less gain Armor +1 until the start of your next turn.
- [ ] **C1-008 Porcini Miner** (cost 5, 6 power · 1 health · 1 score, Duelist +1)
  - While this unit is attacking, it gets +2 power.
- [ ] **C1-009 Porcini Baker** (cost 2, action)
  - All damaged opposing units can’t ready at the start of their next turn.
- [ ] **C1-010 Porcini Lamplighter** (cost 2, 1 power · 1 health · 1 score, Guard)
  - While this unit is attacking, it gets +1 power.
- [ ] **C1-011 Porcini Chef** (cost 4, 1 power · 2 health · 1 score, Elusive)
  - Whenever this unit scores, remove 3 damage from this unit.
- [ ] **C1-012 Porcini Postman** (cost 4, 1 power · 2 health · 1 score, Charge)
  - Whenever an opposing unit is defeated, choose one: • Gain 1 VP. • Remove all damage from this unit.
- [ ] **C1-013 Portobello Scholar** (cost 2, action)
  - Choose one: • Draw a card. • Chosen opposing unit can’t ready at the start of its next turn.
- [ ] **C1-014 Portobello Miner** (cost 4, 2 power · 2 health · 2 score, Guard)
  - While this unit is defending, it gets +1 health for each Baker unit in play (up to +3).
- [ ] **C1-015 Portobello Baker** (cost 3, 1 power · 2 health · 1 score, Elusive)
  - While this unit is damaged, it has Guard.
- [ ] **C1-016 Portobello Lamplighter** (cost 3, 2 power · 1 health · 1 score, Duelist +2)
  - While this unit is defending, it gets +1 health.
- [ ] **C1-017 Portobello Chef** (cost 1, action)
  - You may exhaust a chosen ready unit of yours. If you do, ready your units. They can’t score or use ⟳ abilities this turn.
- [ ] **C1-018 Portobello Postman** (cost 4, 4 power · 1 health · 1 score)
  - At the start of your turn, if you have fewer VP than your opponent, exhaust chosen opposing unit.
- [ ] **C1-019 Morel Scholar** (cost 5, 1 power · 4 health · 3 score)
  - While this unit is damaged, it has Duelist +1.
- [ ] **C1-020 Morel Miner** (cost 5, 1 power · 2 health · 4 score)
  - Whenever an opposing unit is defeated, if you have 2 or more other Postman units in play, ready your other Chef units. They can’t score or use ⟳ abilities this turn.
- [ ] **C1-021 Morel Baker** (cost 3, action)
  - Return all opposing units to their owners’ hands.
- [ ] **C1-022 Morel Lamplighter** (cost 2, 1 power · 2 health · 1 score)
  - Whenever this unit attacks in a duel, if you have 3 or more other Chef units in play, this unit gets +1 health this turn.
- [ ] **C1-023 Morel Chef** (cost 8, 1 power · 1 health · 1 score)
  - At the start of your turn, return all opposing units to their owners’ hands.
- [ ] **C1-024 Morel Postman** (cost 3, 2 power · 1 health · 1 score)
  - At the end of your turn, this unit gets +2 health until the start of your next turn.
- [ ] **C1-025 Inkcap Scholar** (cost 2, action)
  - Remove all damage from your units.
- [ ] **C1-026 Inkcap Miner** (cost 4, 4 power · 1 health · 2 score)
  - Whenever this unit scores, this unit gets +1 power this turn.
- [ ] **C1-027 Inkcap Baker** (cost 5, 2 power · 2 health · 1 score)
  - Whenever this unit attacks in a duel, defeat chosen exhausted opposing unit.
- [ ] **C1-028 Inkcap Lamplighter** (cost 3, 1 power · 2 health · 1 score)
  - When this unit is defeated, defeat chosen exhausted opposing unit.
- [ ] **C1-029 Inkcap Chef** (cost 1, action)
  - All opposing units get −2 power this turn.
- [ ] **C1-030 Inkcap Postman** (cost 5, 4 power · 6 health · 1 score)
  - When this unit is defeated, chosen opposing unit gets −1 power this turn.
- [ ] **C1-031 Ghost Scholar** (cost 3, 1 power · 1 health · 2 score)
  - All damaged opposing units get −1 power.
- [ ] **C1-032 Ghost Miner** (cost 2, 1 power · 2 health · 1 score)
  - Your other Miner units get +1 health.
- [ ] **C1-033 Ghost Baker** (cost 2, action)
  - Your units get +1 score this turn.
- [ ] **C1-034 Ghost Lamplighter** (cost 5, 4 power · 5 health · 1 score)
  - Postman cards you play cost 1 less.
- [ ] **C1-035 Ghost Chef** (cost 2, 1 power · 1 health · 1 score)
  - Your other Baker units get +1 health.
- [ ] **C1-036 Ghost Postman** (cost 3, 1 power · 1 health · 2 score)
  - Scholar cards you play cost 1 less.
- [ ] **C1-037 Turkey-tail Scholar** (cost 5, 3 power · 2 health · 3 score)
  - Your other Miner units get +1 power.
- [ ] **C1-038 Turkey-tail Miner** (cost 5, 2 power · 3 health · 1 score)
  - At the end of your turn, draw a card.
- [ ] **C1-039 Turkey-tail Baker** (cost 5, 1 power · 2 health · 1 score)
  - ⟳, discard a card: Draw 2 cards.
- [ ] **C1-040 Turkey-tail Lamplighter** (cost 3, 2 power · 1 health · 1 score)
  - ⟳, discard a card: Your opponent loses 1 VP.
- [ ] **C1-041 Turkey-tail Chef** (cost 4, 1 power · 1 health · 1 score)
  - ⟳, 2 energy: Draw 2 cards.
- [ ] **C1-042 Turkey-tail Postman** (cost 4, 2 power · 3 health · 1 score)
  - ⟳, exhaust another of your ready units: Draw a card.
- [ ] **C1-043 Shiitake Scholar** (cost 3, 1 power · 1 health · 2 score)
  - Whenever you play another Postman unit, put the top card of your deck into your energy zone, exhausted.
- [ ] **C1-044 Shiitake Miner** (cost 2, action)
  - Draw 2 cards.
- [ ] **C1-045 Shiitake Baker** (cost 1, action)
  - Gain 1 VP.
- [ ] **C1-046 Shiitake Lamplighter** (cost 1, action)
  - Your opponent discards a card at random.

## Building blocks

| Building block | Cards |
|---|---|
| ability: activated | C1-004, C1-006, C1-039, C1-040, C1-041, C1-042 |
| ability: on_resolve | C1-001, C1-005, C1-009, C1-013, C1-017, C1-021, C1-025, C1-029, C1-033, C1-044, C1-045, C1-046 |
| ability: static | C1-008, C1-010, C1-014, C1-015, C1-016, C1-019, C1-031, C1-032, C1-034, C1-035, C1-036, C1-037 |
| ability: triggered | C1-002, C1-003, C1-007, C1-011, C1-012, C1-018, C1-020, C1-022, C1-023, C1-024, C1-026, C1-027, C1-028, C1-030, C1-038, C1-043 |
| amount: all | C1-012, C1-025 |
| amount: per count, capped | C1-001, C1-002, C1-014 |
| card type: action | C1-001, C1-005, C1-009, C1-013, C1-017, C1-021, C1-025, C1-029, C1-033, C1-044, C1-045, C1-046 |
| card type: unit | C1-002, C1-003, C1-004, C1-006, C1-007, C1-008, C1-010, C1-011, C1-012, C1-014, C1-015, C1-016, C1-018, C1-019, C1-020, C1-022, C1-023, C1-024, C1-026, C1-027, C1-028, C1-030, C1-031, C1-032, C1-034, C1-035, C1-036, C1-037, C1-038, C1-039, C1-040, C1-041, C1-042, C1-043 |
| condition: behind_on_vp | C1-003, C1-018 |
| condition: count | C1-020, C1-022 |
| condition: defeated | C1-001, C1-002 |
| condition: this_is attacking | C1-008, C1-010 |
| condition: this_is damaged | C1-015, C1-019 |
| condition: this_is defending | C1-014, C1-016 |
| cost: discard | C1-039, C1-040 |
| cost: exhaust_another | C1-006, C1-042 |
| cost: exhaust_this | C1-004, C1-006, C1-039, C1-040, C1-041, C1-042 |
| cost: pay | C1-004, C1-041 |
| decision: choose | C1-001, C1-002, C1-013, C1-017, C1-018, C1-027, C1-028, C1-030 |
| decision: choose one | C1-003, C1-004, C1-006, C1-012, C1-013 |
| decision: may | C1-005, C1-007, C1-017 |
| duration: this_turn | C1-003, C1-004, C1-022, C1-026, C1-029, C1-030, C1-033 |
| duration: until_their_next_turn | C1-009, C1-013 |
| duration: until_your_next_turn | C1-005, C1-007, C1-024 |
| effect: add_energy | C1-002, C1-006, C1-043 |
| effect: cant_ready | C1-009, C1-013 |
| effect: deal_damage | C1-001, C1-002 |
| effect: defeat | C1-027, C1-028 |
| effect: discard | C1-004, C1-005, C1-046 |
| effect: draw | C1-001, C1-013, C1-038, C1-039, C1-041, C1-042, C1-044 |
| effect: exhaust | C1-017, C1-018 |
| effect: gain_vp | C1-006, C1-012, C1-045 |
| effect: grant_keyword | C1-005, C1-007 |
| effect: lose_vp | C1-003, C1-007, C1-040 |
| effect: modify_stat | C1-003, C1-004, C1-022, C1-024, C1-026, C1-029, C1-030, C1-033 |
| effect: ready | C1-017, C1-020 |
| effect: remove_damage | C1-011, C1-012, C1-025 |
| effect: return_to_hand | C1-021, C1-023 |
| filter owner: any | C1-002, C1-014 |
| filter owner: opponent | C1-001, C1-002, C1-009, C1-013, C1-018, C1-021, C1-023, C1-027, C1-028, C1-029, C1-030 |
| filter owner: you | C1-001, C1-002, C1-003, C1-004, C1-005, C1-007, C1-017, C1-020, C1-022, C1-025, C1-033, C1-043 |
| filter: cost_max | C1-005, C1-007 |
| filter: damaged | C1-001, C1-009 |
| filter: exhausted | C1-002, C1-004, C1-017, C1-027, C1-028 |
| filter: not_this | C1-002, C1-003, C1-004, C1-007, C1-020, C1-022, C1-043 |
| filter: trait | C1-001, C1-002, C1-014, C1-020, C1-022, C1-043 |
| keyword: armor | C1-002, C1-007 |
| keyword: charge | C1-003, C1-006, C1-012 |
| keyword: duelist | C1-008, C1-016 |
| keyword: elusive | C1-011, C1-015 |
| keyword: guard | C1-010, C1-014 |
| stat change: health + | C1-022, C1-024 |
| stat change: power + | C1-004, C1-026 |
| stat change: power − | C1-029, C1-030 |
| stat change: score + | C1-003, C1-033 |
| static: cost reduction | C1-034, C1-036 |
| static: health for all(…) | C1-032, C1-035 |
| static: health for this card | C1-014, C1-016 |
| static: keyword for this card | C1-015, C1-019 |
| static: power for all(…) | C1-031, C1-037 |
| static: power for this card | C1-008, C1-010 |
| step: if | C1-001, C1-002 |
| target: all(…) | C1-003, C1-004, C1-005, C1-007, C1-009, C1-017, C1-020, C1-021, C1-023, C1-025, C1-029, C1-033 |
| target: an earlier choice | C1-001, C1-002, C1-013, C1-017, C1-018, C1-027, C1-028, C1-030 |
| target: opponent | C1-003, C1-004, C1-040, C1-046 |
| target: this card | C1-011, C1-012, C1-022, C1-024, C1-026 |
| target: you | C1-001, C1-002, C1-005, C1-006, C1-007, C1-012, C1-013, C1-038, C1-039, C1-041, C1-042, C1-043, C1-044, C1-045 |
| trigger: another_played | C1-002, C1-043 |
| trigger: end_of_turn | C1-024, C1-038 |
| trigger: on_attack | C1-022, C1-027 |
| trigger: on_defeated | C1-028, C1-030 |
| trigger: on_play | C1-003, C1-007 |
| trigger: on_score | C1-011, C1-026 |
| trigger: opposing_defeated | C1-012, C1-020 |
| trigger: start_of_turn | C1-018, C1-023 |
