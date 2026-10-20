"""Generating one card at a time, with a record of every stage it went through.

    sample a tree → grammar (validate) → quality tests → build and cost the card → variety

Every attempt is kept with the stage that stopped it and why, so the card lab
(scripts/card_lab.py) can show what the generator throws away as well as what it keeps. The
coverage generator uses the same pipeline. docs/ability-generation.md describes each stage.
"""
import math
import random
from collections import Counter
from dataclasses import dataclass, field, replace

from src.cards.abilities import AbilitySampler, render, validate
from src.cards.costing import ability_value
from src.cards.names import Namer
from src.cards.quality import MAX_COMPLEXITY, complexity, quality_problems, skeleton
from src.cards.schema import Card, CardSet
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
    trace: dict | None = None  # every random decision (src/cards/trace.py)


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
        self.namer = Namer(self.sampler.trace)
        self.shapes = Counter()
        self.attempts: list[Attempt] = []
        self._next = 0

    def attempt(self, card_type: str | None = None) -> Attempt:
        """One draw from the grammar taken as far through the pipeline as it gets."""
        t = self.sampler.trace
        t.reset()
        p = self.action_share
        if card_type is None:
            card_type = "action" if t.chance("Action card?", p) else "unit"
        else:
            t.record("Action card?", [("yes", p), ("no", 1 - p)], "yes" if card_type == "action" else "no",
                     "decided once per card: redraws after a thrown-away ability keep it")
        with t.section("ability"):
            ability = self.sampler.raw(card_type, reset=False)
        a = Attempt(self._next, card_type, ability, render(ability, card_type), complexity(ability),
                    round(ability_value(ability), 2))
        a.trace = t.root
        self._next += 1
        self.attempts.append(a)
        if problems := validate(ability, card_type):
            a.stopped_at, a.problems = "grammar", problems
        elif problems := quality_problems(ability, self.max_complexity):
            a.stopped_at, a.problems = "quality", problems
        else:
            try:
                with t.section("card"):
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
        self.namer.reserve(best.card)
        return best

    def _build(self, index: int, card_type: str, ability: dict, value: float) -> tuple[Card, str | None]:
        t = self.sampler.trace
        aspect = (t.choice("Aspect", ASPECTS),)
        energy_source = t.chance("Energy source?", 0.8)
        if card_type == "action":
            name = self.namer.action(aspect[0], ability)
            cost = max(0, math.ceil(value / 2))
            t.fixed("Cost", cost, f"half the ability's rough value ({value:g}), rounded up")
            return Card(f"gen-{index}", name, "action", aspect, energy_source, cost, 0, 0, 0,
                        abilities=(ability,)), None

        species, job = t.choice("Species", SPECIES), t.choice("Job", self.jobs)
        name = f"{species} {job}"
        subtitle = self.namer.subtitle(name, ability)

        archetype = t.choice("Archetype", list(ARCHETYPES))
        keywords = {}
        if t.chance("Add a keyword?", 0.35):
            keyword = t.weighted("Keyword", ARCHETYPE_KEYWORDS[archetype], f"weighted for a {archetype}")
            lo, hi = KEYWORD_RANGE.get(keyword, (1, 1))
            keywords[keyword] = t.randint("Keyword value", lo, hi)
        spend = math.ceil(value) + keyword_value(keywords)
        cost = t.randint("Starting cost", 1, 5)
        start = cost
        while stat_budget(cost, energy_source) - spend < MIN_STATS_VALUE and cost < 9:
            cost += 1
        if cost != start:
            t.fixed("Cost", cost, "raised until the card can afford its ability and keywords plus minimum stats")
        budget = max(MIN_STATS_VALUE, stat_budget(cost, energy_source) - spend)
        stats = _allocate(self.rng, budget, ARCHETYPES[archetype])
        t.fixed("Stats", f"{stats['power']} power, {stats['health']} health, {stats['score']} VP",
                f"stat budget {stat_budget(cost, energy_source)} for cost {cost}, minus {spend} for the ability and "
                f"keywords, spread at random with {archetype} weights")
        return Card(f"gen-{index}", name, "unit", aspect, energy_source, cost, **stats, traits=(job,),
                    keywords=tuple(sorted(keywords.items())), abilities=(ability,), subtitle=subtitle), archetype


def generate_ability_set(count: int, seed: int = 0, jobs: int = 6, action_share: float = 0.25, variety: int = 4,
                         prefix: str = "A1") -> CardSet:
    """`count` cards with one ability each, through the whole pipeline. As in the coverage set,
    abilities only refer to `jobs` jobs and the units use the same jobs, so job conditions can be met."""
    rng = random.Random(seed)
    job_list = tuple(rng.sample(JOBS, min(jobs, len(JOBS))))
    generator = CardGenerator(rng, job_list, action_share=action_share, variety=variety)
    kept = [generator.card().card for _ in range(count)]
    cards = [replace(c, id=f"{prefix}-{n + 1:03d}") for n, c in enumerate(kept)]
    stopped = Counter(a.stopped_at for a in generator.attempts if a.stopped_at)
    notes = {"generator": "abilities", "seed": seed, "jobs": list(job_list), "action_share": action_share,
             "variety": variety, "draws": len(generator.attempts), "stopped_at": dict(stopped),
             "costing": "rough ability values from src/cards/costing.py"}
    return CardSet(f"abilities_{count}", cards, notes)
