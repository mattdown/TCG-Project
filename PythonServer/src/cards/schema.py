"""Card definitions and card-set files.

A card is pure data. The engine plays it and the graph builder describes it to the network,
so a new card never needs new code. Abilities are trees in the authoring form of
docs/technical-plan.md section 3 and are checked against the grammar when a card is created.
"""
import json
import copy
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from src.cards.abilities import card_problems, validate
from src.game.terms import ASPECTS, KEYWORDS

CARD_TYPES = ("unit", "action")


@dataclass(frozen=True)
class Card:
    id: str  # bookkeeping only, never shown to the network
    name: str
    type: str
    aspects: tuple[str, ...]
    energy_source: bool
    cost: int
    power: int
    health: int
    score: int
    traits: tuple[str, ...] = ()
    keywords: tuple[tuple[str, int], ...] = ()  # sorted (name, value); value is 1 for keywords without a number
    # Ability trees (dicts). Compared but not hashed, so cards stay usable as dict keys.
    abilities: tuple[dict, ...] = field(default=(), hash=False)
    subtitle: str = ""  # tells apart versions of the same character: "Porcini Baker – Up Before Dawn"

    def __post_init__(self):
        if self.type not in CARD_TYPES:
            raise ValueError(f"{self.id}: unknown card type {self.type!r}")
        if not self.aspects or any(a not in ASPECTS for a in self.aspects):
            raise ValueError(f"{self.id}: invalid aspects {self.aspects}")
        if self.cost < 0 or self.power < 0 or self.score < 0 or (self.type == "unit" and self.health < 1):
            raise ValueError(f"{self.id}: invalid stats")
        if self.type == "unit" and self.score < 1:
            raise ValueError(f"{self.id}: every unit scores at least 1 VP")
        if self.type == "action" and (self.power or self.health or self.score or self.keywords):
            raise ValueError(f"{self.id}: action cards have no stats or keywords")
        for ability in self.abilities:
            problems = validate(ability, self.type)
            if problems:
                raise ValueError(f"{self.id}: invalid ability: {'; '.join(problems)}")
        problems = card_problems(self.type, self.health, dict(self.keywords), self.abilities)
        if problems:
            raise ValueError(f"{self.id}: {'; '.join(problems)}")
        for name, value in self.keywords:
            if name not in KEYWORDS or value < 1 or (not KEYWORDS[name] and value != 1):
                raise ValueError(f"{self.id}: invalid keyword {name} {value}")

    def keyword(self, name: str) -> int:
        """The keyword's value, 1 for a keyword without a number, 0 if the card doesn't have it."""
        return dict(self.keywords).get(name, 0)

    def to_dict(self) -> dict:
        data = asdict(self)
        # In JSON: {"guard": true, "duelist": 2}
        data["keywords"] = {name: (value if KEYWORDS[name] else True) for name, value in self.keywords}
        data["abilities"] = [copy.deepcopy(a) for a in self.abilities]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"{data.get('id')}: unknown card fields {sorted(unknown)}")
        values = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}
        if "abilities" in values:
            values["abilities"] = tuple(copy.deepcopy(a) for a in data["abilities"])
        if "keywords" in values:
            values["keywords"] = tuple(sorted((name, int(value)) for name, value in values["keywords"].items()))
        return cls(**values)


@dataclass
class CardSet:
    name: str
    cards: list[Card]
    # Generator metadata. Never read by the engine or the network.
    notes: dict = field(default_factory=dict)

    def __post_init__(self):
        ids = [c.id for c in self.cards]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate card ids")
        self._by_id = {c.id: c for c in self.cards}

    def __getitem__(self, card_id: str) -> Card:
        return self._by_id[card_id]

    def __len__(self) -> int:
        return len(self.cards)


def save_card_set(card_set: CardSet, path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # One card per line keeps the file readable and its diffs small.
    cards = ",\n".join("  " + json.dumps(c.to_dict()) for c in card_set.cards)
    notes = json.dumps(card_set.notes, indent=1, sort_keys=True)
    path.write_text(f'{{\n "name": {json.dumps(card_set.name)},\n "cards": [\n{cards}\n ],\n "notes": {notes}\n}}\n')


def load_card_set(path: Path) -> CardSet:
    data = json.loads(Path(path).read_text())
    return CardSet(data["name"], [Card.from_dict(c) for c in data["cards"]], data.get("notes", {}))
