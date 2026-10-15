"""Card definitions and card-set files.

A card is pure data. The engine plays it and the graph builder describes it to the network,
so a new card never needs new code. Only vanilla units exist so far: keywords and abilities
will be added to this schema as the DSL is built.
"""
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from src.game.terms import ASPECTS

CARD_TYPES = ("unit",)


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

    def __post_init__(self):
        if self.type not in CARD_TYPES:
            raise ValueError(f"{self.id}: unknown card type {self.type!r}")
        if not self.aspects or any(a not in ASPECTS for a in self.aspects):
            raise ValueError(f"{self.id}: invalid aspects {self.aspects}")
        if self.cost < 0 or self.power < 0 or self.health < 1 or self.score < 0:
            raise ValueError(f"{self.id}: invalid stats")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"{data.get('id')}: unknown card fields {sorted(unknown)}")
        values = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}
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
