"""Generating one card at a time, with a record of every stage it went through.

    sample a tree → grammar (validate) → quality tests → build and cost the card → variety

Every attempt is kept with the stage that stopped it and why, so the card lab
(scripts/card_lab.py) can show what the generator throws away as well as what it keeps. The
coverage generator uses the same pipeline. docs/ability-generation.md describes each stage.
"""
import math
import random
from collections import Counter
from dataclasses import dataclass, field

from src.cards.abilities import AbilitySampler, render, validate
from src.cards.costing import ability_value
from src.cards.quality import MAX_COMPLEXITY, complexity, quality_problems, skeleton
from src.cards.schema import Card
from src.cards.theme import JOBS, SPECIES
from src.cards.vanilla import (ARCHETYPES, ARCHETYPE_KEYWORDS, KEYWORD_RANGE, MIN_STATS_VALUE, _allocate,
                               keyword_value, stat_budget)
from src.game.terms import ASPECTS

STAGES = ("grammar", "quality", "card", "variety")  # where an attempt can be stopped


@dataclass
class Attempt:
    index: int
    card_type: str
    ability: dict
    text: str
    complexity: int
    value: float  # rough ability value in budget points (costing.py)
    stopped_at: str | None = None  # None: the card was kept
    problems: list[str] = field(default_factory=list)
    card: Card | None = None
    archetype: str | None = None


class CardGenerator:
    """Samples cards with one ability each: one idea per card while the generator is young. The
    engine and the card schema allow more.

    `variety` > 1 draws that many good cards for each one it keeps and keeps the one whose
    shape (skeleton, ignoring numbers and jobs) has been used least so far. Choosing a grammar
    branch uniformly over-produces branches with few possible outputs; this evens it out
    without per-branch weights."""

    def __init__(self, rng: random.Random, jobs: tuple[str, ...] = JOBS, action_share: float = 0.25,
                 variety: int = 1, max_complexity: int = MAX_COMPLEXITY):
        self.rng = rng
        self.jobs = jobs
        self.action_share = action_share
        self.variety = variety
        self.max_complexity = max_complexity
        self.sampler = AbilitySampler(rng, traits=jobs)
        self.shapes = Counter()
        self.attempts: list[Attempt] = []
        self._next = 0

    def attempt(self, card_type: str | None = None) -> Attempt:
        """One draw from the grammar taken as far through the pipeline as it gets."""
        rng = self.rng
        card_type = card_type or ("action" if rng.random() < self.action_share else "unit")
        ability = self.sampler.raw(card_type)
        a = Attempt(self._next, card_type, ability, render(ability, card_type), complexity(ability),
                    round(ability_value(ability), 2))
        self._next += 1
        self.attempts.append(a)
        if problems := validate(ability, card_type):
            a.stopped_at, a.problems = "grammar", problems
        elif problems := quality_problems(ability, self.max_complexity):
            a.stopped_at, a.problems = "quality", problems
        else:
            try:
                a.card, a.archetype = self._build(a.index, card_type, ability, a.value)
            except ValueError as e:
                a.stopped_at, a.problems = "card", [str(e).split(": ", 1)[-1]]
        return a

    def good(self, card_type: str | None = None) -> Attempt:
        while True:
            a = self.attempt(card_type)
            if a.stopped_at is None:
                return a

    def card(self, card_type: str | None = None) -> Attempt:
        """The next kept card (after the variety stage)."""
        card_type = card_type or ("action" if self.rng.random() < self.action_share else "unit")
        options = [self.good(card_type) for _ in range(self.variety)]
        best = min(options, key=lambda a: self.shapes[skeleton(a.ability, abstract_traits=True)])
        for a in options:
            if a is not best:
                a.stopped_at, a.problems = "variety", ["kept a draw whose shape had been used less instead"]
        self.shapes[skeleton(best.ability, abstract_traits=True)] += 1
        return best

    def _build(self, index: int, card_type: str, ability: dict, value: float) -> tuple[Card, str | None]:
        rng = self.rng
        species, job = rng.choice(SPECIES), rng.choice(self.jobs)
        name = f"{species} {job}"
        aspect = (rng.choice(ASPECTS),)
        energy_source = rng.random() < 0.8
        if card_type == "action":
            cost = max(0, math.ceil(value / 2))
            return Card(f"gen-{index}", name, "action", aspect, energy_source, cost, 0, 0, 0,
                        abilities=(ability,)), None

        archetype = rng.choice(list(ARCHETYPES))
        keywords = {}
        if rng.random() < 0.35:
            options = {k: w for k, w in ARCHETYPE_KEYWORDS[archetype].items() if w}
            keyword = rng.choices(list(options), list(options.values()))[0]
            lo, hi = KEYWORD_RANGE.get(keyword, (1, 1))
            keywords[keyword] = rng.randint(lo, hi)
        spend = math.ceil(value) + keyword_value(keywords)
        cost = rng.randint(1, 5)
        while stat_budget(cost, energy_source) - spend < MIN_STATS_VALUE and cost < 9:
            cost += 1
        stats = _allocate(rng, max(MIN_STATS_VALUE, stat_budget(cost, energy_source) - spend), ARCHETYPES[archetype])
        return Card(f"gen-{index}", name, "unit", aspect, energy_source, cost, **stats, traits=(job,),
                    keywords=tuple(sorted(keywords.items())), abilities=(ability,)), archetype
