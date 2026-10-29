"""Generating one card at a time, with a record of every stage it went through.

    card kind → (ability cards) sample a tree → grammar → quality tests → build and cost → variety
              → (vanilla and keyword-only units) build → not a duplicate

Every attempt is kept with the stage that stopped it and why, so the card lab
(Blog/card_lab.py) can show what the generator throws away as well as what it keeps. The
coverage generator uses the same pipeline. docs/ability-generation.md describes each stage.
"""
import math
import random
from collections import Counter
from dataclasses import dataclass, field, replace

from src.cards.abilities import AbilitySampler, render, validate
from src.cards.costing import price, round_points
from src.cards.names import Namer
from src.cards.quality import ACTION_COMPLEXITY, MAX_COMPLEXITY, complexity, quality_problems, skeleton
from src.cards.schema import Card, CardSet
from src.cards.theme import JOBS, SPECIES
from src.cards.vanilla import (ARCHETYPES, ARCHETYPE_KEYWORDS, COST_WEIGHTS, KEYWORD_RANGE, MIN_STATS_VALUE,
                               _allocate, keyword_value, stat_budget)
from src.game.terms import ASPECTS, keyword_text

STAGES = ("grammar", "quality", "card", "duplicate", "variety")  # where an attempt can be stopped
KINDS = ("vanilla", "keywords", "unit", "action")  # stats only, stats + keywords, a unit with an ability, an action
PLAIN = ("vanilla", "keywords")  # kinds without an ability
MAX_DUPLICATES = 100  # plain draws in a row that only repeat existing cards before falling back to an ability unit


@dataclass
class Attempt:
    index: int
    card_type: str
    ability: dict | None  # None for vanilla and keyword-only units
    text: str
    complexity: int
    value: float  # what the card pays for its ability, in budget points (costing.price)
    kind: str = "unit"
    stopped_at: str | None = None  # None: the card was kept
    problems: list[str] = field(default_factory=list)
    card: Card | None = None
    archetype: str | None = None
    trace: dict | None = None  # every random decision (src/cards/trace.py)


def identity(card: Card) -> tuple:
    """What makes a card without an ability different from another: name and aspect don't."""
    return card.cost, card.power, card.health, card.keywords


MIN_ACTION_PRICE = 2  # budget points: an action worth less than 1 mana isn't worth a card


class CardGenerator:
    """Samples cards: vanilla units, keyword-only units, and units and actions with one ability
    each (one idea per card while the generator is young; the engine and card schema allow
    more). The shares of each kind are fractions of all cards.

    Vanilla and keyword-only units are neutral (any deck can use them), and no two have the same
    cost, stats and keywords. Ability cards get a random aspect, or none `neutral_share` of the
    time: aspects have no identity yet (docs/ability-generation.md).

    `variety` > 1 draws that many good ability cards for each one it keeps and keeps the one
    whose shape (skeleton, ignoring numbers and jobs) has been used least so far. Choosing a
    grammar branch uniformly over-produces branches with few possible outputs; this evens it out
    without per-branch weights."""

    def __init__(self, rng: random.Random, jobs: tuple[str, ...] = JOBS, action_share: float = 0.25,
                 variety: int = 1, max_complexity: int = MAX_COMPLEXITY, vanilla_share: float = 0.0,
                 keyword_share: float = 0.0, neutral_share: float = 0.1):
        self.rng = rng
        self.jobs = jobs
        self.shares = {"vanilla": vanilla_share, "keywords": keyword_share, "action": action_share,
                       "unit": 1 - vanilla_share - keyword_share - action_share}
        if self.shares["unit"] < 0:
            raise ValueError("the shares of vanilla, keyword-only and action cards add up to more than 1")
        self.neutral_share = neutral_share
        self.variety = variety
        self.max_complexity = max_complexity
        self.sampler = AbilitySampler(rng, traits=jobs)
        self.namer = Namer(self.sampler.trace)
        self.shapes = Counter()
        self.identities: set[tuple] = set()
        self.attempts: list[Attempt] = []
        self._next = 0

    def attempt(self, kind: str | None = None) -> Attempt:
        """One draw taken as far through the pipeline as it gets."""
        t = self.sampler.trace
        t.reset()
        if kind is None:
            kind = t.weighted("Card kind", self.shares)
        else:
            t.record("Card kind", list(self.shares.items()), kind,
                     "decided once per card: redraws after a thrown-away draw keep it")
        card_type = "action" if kind == "action" else "unit"
        if kind in PLAIN:
            a = Attempt(self._next, card_type, None, "", 0, 0.0, kind)
            self._register(a)
            try:
                with t.section("card"):
                    a.card, a.archetype = self._build_plain(a.index, kind)
            except ValueError as e:
                a.stopped_at, a.problems = "card", [str(e).split(": ", 1)[-1]]
                return a
            a.text = " ".join(f"{keyword_text(k, v)}." for k, v in a.card.keywords)
            if identity(a.card) in self.identities:
                a.stopped_at, a.problems = "duplicate", ["same cost, stats and keywords as a card already in the set"]
            return a

        with t.section("ability"):
            # A unit's job comes first, so its ability can refer to it.
            self.sampler.own_job = t.choice("Job", self.jobs) if card_type == "unit" else None
            ability = self.sampler.raw(card_type, reset=False)
        a = Attempt(self._next, card_type, ability, render(ability, card_type), complexity(ability),
                    round(price(ability, card_type), 2), kind)
        self._register(a)
        if problems := validate(ability, card_type):
            a.stopped_at, a.problems = "grammar", problems
        elif problems := quality_problems(ability, self.max_complexity + (ACTION_COMPLEXITY if card_type == "action" else 0)):
            a.stopped_at, a.problems = "quality", problems
        else:
            try:
                with t.section("card"):
                    a.card, a.archetype = self._build(a.index, card_type, ability, a.value)
            except ValueError as e:
                a.stopped_at, a.problems = "card", [str(e).split(": ", 1)[-1]]
        return a

    def _register(self, a: Attempt):
        a.trace = self.sampler.trace.root
        self._next += 1
        self.attempts.append(a)

    def good(self, kind: str | None = None, limit: int | None = None) -> Attempt | None:
        """The next draw that passes every test; None after `limit` draws that don't."""
        tries = 0
        while limit is None or tries < limit:
            a = self.attempt(kind)
            if a.stopped_at is None:
                return a
            tries += 1
        return None

    def card(self, kind: str | None = None) -> Attempt:
        """The next kept card (after the duplicate or variety stage)."""
        kind = kind or self.rng.choices(list(self.shares), list(self.shares.values()))[0]
        if kind in PLAIN:
            best = self.good(kind, limit=MAX_DUPLICATES)
            if best is None:  # every plain card at these costs is taken
                return self.card("unit")
            self.identities.add(identity(best.card))
        else:
            options = [self.good(kind) for _ in range(self.variety)]
            best = min(options, key=lambda a: self.shapes[skeleton(a.ability, abstract_traits=True)])
            for a in options:
                if a is not best:
                    a.stopped_at, a.problems = "variety", ["kept a draw whose shape had been used less instead"]
            self.shapes[skeleton(best.ability, abstract_traits=True)] += 1
        self.namer.reserve(best.card)
        return best

    def _aspect(self) -> tuple[str, ...]:
        t = self.sampler.trace
        if t.chance("Neutral?", self.neutral_share, "any deck can use a neutral card"):
            return ()
        return (t.choice("Aspect", ASPECTS, "at random: aspects have no identity yet"),)

    def _name(self, ability: dict | None, keywords: dict | None = None, job: str | None = None) -> tuple[str, str, str]:
        t = self.sampler.trace
        species = t.choice("Species", SPECIES)
        job = job or t.choice("Job", self.jobs)
        name = f"{species} {job}"
        return name, job, self.namer.subtitle(name, ability, keywords)

    def _build_plain(self, index: int, kind: str) -> tuple[Card, str]:
        """A neutral unit with stats only, or stats and one keyword (rarely two)."""
        t = self.sampler.trace
        cost = t.weighted("Cost", COST_WEIGHTS)
        archetype = t.choice("Archetype", list(ARCHETYPES))
        keywords = {}
        if kind == "keywords":
            for _ in range(2 if t.chance("Two keywords?", 0.15) else 1):
                options = {k: w for k, w in ARCHETYPE_KEYWORDS[archetype].items() if k not in keywords}
                keyword = t.weighted("Keyword", options, f"weighted for a {archetype}")
                lo, hi = KEYWORD_RANGE.get(keyword, (1, 1))
                keywords[keyword] = t.randint("Keyword value", lo, hi)
            if stat_budget(cost) - keyword_value(keywords) < MIN_STATS_VALUE:
                raise ValueError(f"gen-{index}: the keywords cost more than a {cost}-mana card can pay for")
        budget = stat_budget(cost) - keyword_value(keywords)
        stats = _allocate(self.rng, budget, ARCHETYPES[archetype])
        t.fixed("Stats", f"{stats['power']} power, {stats['health']} health",
                f"stat budget {stat_budget(cost)} for cost {cost}, minus {keyword_value(keywords)} for keywords, "
                f"spread at random with {archetype} weights")
        name, job, subtitle = self._name(None, keywords)
        return Card(f"gen-{index}", name, "unit", (), cost, **stats, traits=(job,),
                    keywords=tuple(sorted(keywords.items())), subtitle=subtitle), archetype

    def _build(self, index: int, card_type: str, ability: dict, value: float) -> tuple[Card, str | None]:
        t = self.sampler.trace
        aspect = self._aspect()
        if card_type == "action":
            name = self.namer.action(aspect[0] if aspect else None, ability)
            if value < MIN_ACTION_PRICE:
                raise ValueError(f"gen-{index}: worth less than 1 mana (price {value:g}): too weak to be a card")
            cost = round_points(value / 2)
            t.fixed("Cost", cost, f"half the ability's price ({value:g}), to the nearest")
            return Card(f"gen-{index}", name, "action", aspect, cost, 0, 0, abilities=(ability,)), None

        name, job, subtitle = self._name(ability, job=self.sampler.own_job)
        archetype = t.choice("Archetype", list(ARCHETYPES))
        keywords = {}
        if t.chance("Add a keyword?", 0.35):
            keyword = t.weighted("Keyword", ARCHETYPE_KEYWORDS[archetype], f"weighted for a {archetype}")
            lo, hi = KEYWORD_RANGE.get(keyword, (1, 1))
            keywords[keyword] = t.randint("Keyword value", lo, hi)
        spend = round_points(value) + keyword_value(keywords)
        cost = t.randint("Starting cost", 1, 5)
        start = cost
        while stat_budget(cost) - spend < MIN_STATS_VALUE and cost < 10:
            cost += 1
        if cost != start:
            t.fixed("Cost", cost, "raised until the card can afford its ability and keywords plus minimum stats")
        budget = max(MIN_STATS_VALUE, stat_budget(cost) - spend)
        stats = _allocate(self.rng, budget, ARCHETYPES[archetype])
        t.fixed("Stats", f"{stats['power']} power, {stats['health']} health",
                f"stat budget {stat_budget(cost)} for cost {cost}, minus {spend} for the ability and "
                f"keywords, spread at random with {archetype} weights")
        return Card(f"gen-{index}", name, "unit", aspect, cost, **stats, traits=(job,),
                    keywords=tuple(sorted(keywords.items())), abilities=(ability,), subtitle=subtitle), archetype


def generate_card_set(count: int, seed: int = 0, jobs: int = 6, action_share: float = 0.25,
                      vanilla_share: float = 0.04, keyword_share: float = 0.25, variety: int = 4,
                      prefix: str = "S1") -> CardSet:
    """`count` cards through the whole pipeline: vanilla, keyword-only, and ability units and
    actions in the given shares. As in the coverage set, abilities only refer to `jobs` jobs and
    the units use the same jobs, so job conditions can be met."""
    rng = random.Random(seed)
    job_list = tuple(rng.sample(JOBS, min(jobs, len(JOBS))))
    generator = CardGenerator(rng, job_list, action_share=action_share, variety=variety,
                              vanilla_share=vanilla_share, keyword_share=keyword_share)
    kept = [generator.card() for _ in range(count)]
    cards = [replace(a.card, id=f"{prefix}-{n + 1:03d}") for n, a in enumerate(kept)]
    stopped = Counter(a.stopped_at for a in generator.attempts if a.stopped_at)
    notes = {"generator": "set", "seed": seed, "jobs": list(job_list),
             "shares": {"vanilla": vanilla_share, "keywords": keyword_share, "action": action_share},
             "kinds": dict(Counter(a.kind for a in kept)), "variety": variety, "draws": len(generator.attempts),
             "stopped_at": dict(stopped), "costing": "ability prices from src/cards/costing.py (price)"}
    return CardSet(f"set_{count}", cards, notes)
