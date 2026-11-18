"""Classes: each aspect is two neighbouring play styles on a ring of six (docs/stage-2-research-plan.md, 4G).

    Aggro - Swarm - Growth - Fortress - Control - Spells - (back to Aggro)

Each class has two neighbouring styles, so neighbours share a style and opposite classes share
nothing. A style is a set of offsets on the sampler's labelled choices (the labels the Tracer
records: "Effect", "Trigger", "Keyword", …): an option's weight is multiplied by its offset. A
class never makes what is a signature (offset SIGNATURE) of its two opposite styles: those options
are 0, unless one of its own styles uses them too. The signatures of the two styles next to its own
are damped (NEIGHBOUR), so the generic grammar's heaviest options (damage, draw) don't drown the
class's identity. Neutral cards fill the gaps.

A class card takes one of its styles, or both for a bridge card (where the class's own synergy
lives). Neutral cards are mostly vanilla (keywords allowed); the rest are units with one
style's ability, taxed NEUTRAL_TAX stat points. Prices are the same for every class: a style
changes what is made, never what it costs.
"""
import json

from src.game.terms import ASPECTS

STYLES = ("aggro", "swarm", "growth", "fortress", "control", "spells")  # the ring, in order
SIGNATURE, LEAN = 4.0, 2.0
NEIGHBOUR = 0.5  # on the signatures of the styles next to a class's own, so its own lead

# label -> option -> multiplier on its weight. Labels are the sampler's (src/cards/abilities.py,
# src/cards/generate.py).
OFFSETS: dict[str, dict[str, dict]] = {
    "aggro": {
        "Effect": {"damage_hero": SIGNATURE, "modify_stat": LEAN},
        "Trigger": {"on_attack_hero": SIGNATURE, "on_attack": LEAN},
        "Keyword": {"charge": SIGNATURE, "duelist": LEAN},
        "Archetype": {"attacker": SIGNATURE},
        "Cost to pay": {"damage_hero": SIGNATURE},
        "Starting cost": {1: LEAN, 2: LEAN},
    },
    "swarm": {
        "Effect": {"summon": SIGNATURE},
        "Trigger": {"token_summoned": SIGNATURE, "another_played": SIGNATURE, "ally_defeated": LEAN},
        "Count what": {"job": SIGNATURE},
        "Condition": {"count": LEAN},
        "Target": {"all": LEAN},
        "Starting cost": {1: LEAN, 2: LEAN},
    },
    "growth": {
        "Effect": {"buff": SIGNATURE, "gain_crystal": SIGNATURE},
        "Static kind": {"lord": SIGNATURE, "discount": SIGNATURE},
        "Ability kind": {"static": LEAN},
        "Trigger": {"end_of_turn": LEAN},
        "Starting cost": {4: LEAN, 5: LEAN},
    },
    "fortress": {
        "Effect": {"heal_hero": SIGNATURE, "remove_damage": SIGNATURE, "grant_keyword": LEAN},
        "Keyword": {"guard": SIGNATURE, "armor": SIGNATURE},
        "Archetype": {"defender": SIGNATURE},
        "Trigger": {"damaged": SIGNATURE, "start_of_turn": LEAN},
        "Condition": {"behind_on_health": SIGNATURE},
        "Static kind": {"self_situational": LEAN, "self_keyword": LEAN},
    },
    "control": {
        "Effect": {"deal_damage": SIGNATURE, "defeat": SIGNATURE, "freeze": SIGNATURE,
                   "return_to_hand": SIGNATURE, "discard": SIGNATURE},
        "Trigger": {"opposing_defeated": SIGNATURE, "on_defeated": LEAN},
        "Static kind": {"debuff": SIGNATURE},
        "Starting cost": {4: LEAN, 5: LEAN},
    },
    "spells": {
        "Effect": {"draw": SIGNATURE},
        "Trigger": {"action_played": SIGNATURE},
        "Condition": {"played": SIGNATURE},
        "Count what": {"played": SIGNATURE, "hand": SIGNATURE},
        "Step pattern": {"choose_one": SIGNATURE},
        "Target": {"random": LEAN, "split": LEAN},
        "Keyword": {"elusive": SIGNATURE},
    },
}
# Share of a style's cards that are actions (units otherwise); a class averages its two.
ACTION_SHARE = {"aggro": 0.35, "swarm": 0.25, "growth": 0.2, "fortress": 0.2, "control": 0.4, "spells": 0.6}

CLASSES: dict[str, tuple[str, str]] = {  # aspect -> its two styles (docs/theme.md)
    "aspect_5": ("aggro", "swarm"),     # Glow: firefly swarms
    "aspect_4": ("swarm", "growth"),    # Meadow: harvest, go wide then pump
    "aspect_3": ("growth", "fortress"), # Moss: old growth, big sturdy bodies
    "aspect_6": ("fortress", "control"),# Frost: freeze and outlast
    "aspect_2": ("control", "spells"),  # Bog: spell control and card advantage
    "aspect_1": ("spells", "aggro"),    # Ember: burn
}
assert set(CLASSES) == set(ASPECTS)

BRIDGE = 0.2  # share of a class's cards that take both its styles
NEUTRAL_SHARE = 0.3  # of all cards
NEUTRAL_PLAIN = 0.7  # of neutral cards: vanilla units, keywords allowed
NEUTRAL_TAX = 1  # stat points (half a mana) a neutral ability unit pays on top of its price
PLAIN_VANILLA = 0.14  # of plain units, no keywords at all (the rest have a keyword or two)


def neighbours(aspect: str) -> tuple[str, str]:
    """The styles on either side of a class's own pair."""
    a, _ = CLASSES[aspect]
    i = STYLES.index(a)
    return STYLES[(i - 1) % 6], STYLES[(i + 2) % 6]


def opposite(aspect: str) -> tuple[str, str]:
    """The two styles across the ring from a class's own."""
    a, _ = CLASSES[aspect]
    i = STYLES.index(a)
    return STYLES[(i + 3) % 6], STYLES[(i + 4) % 6]


def zeros(aspect: str) -> dict[str, set]:
    """Options a class never makes: its opposite styles' signatures that its own styles don't use."""
    own = CLASSES[aspect]
    out: dict[str, set] = {}
    for style in opposite(aspect):
        for label, options in OFFSETS[style].items():
            for option, factor in options.items():
                if factor >= SIGNATURE and not any(option in OFFSETS[s].get(label, {}) for s in own):
                    out.setdefault(label, set()).add(option)
    return out


def tilt(styles: tuple[str, ...], aspect: str | None = None) -> dict[str, dict]:
    """The multipliers for a card of these styles (both for a bridge card), with the class's zeros."""
    out: dict[str, dict] = {}
    for style in styles:
        for label, options in OFFSETS[style].items():
            for option, factor in options.items():
                out.setdefault(label, {})[option] = out.get(label, {}).get(option, 1.0) * factor
    if aspect:
        own = CLASSES[aspect]
        for style in neighbours(aspect):
            for label, options in OFFSETS[style].items():
                for option, factor in options.items():
                    if factor >= SIGNATURE and not any(option in OFFSETS[s].get(label, {}) for s in own):
                        out.setdefault(label, {})[option] = out.get(label, {}).get(option, 1.0) * NEIGHBOUR
        for label, options in zeros(aspect).items():
            for option in options:
                out.setdefault(label, {})[option] = 0.0
    # The follow-up pattern ("deal damage; if it was defeated, …") always starts with damage.
    if "deal_damage" in out.get("Effect", {}):
        out.setdefault("Step pattern", {})["follow_up"] = out["Effect"]["deal_damage"]
    return out


def class_problems(card, aspect: str) -> list[str]:
    """What a class card has that its class never makes (a forced grammar path can reach it even
    with the option's weight at 0)."""
    from src.cards.names import static_kind

    banned = zeros(aspect)
    found = set()
    for ability in card.abilities:
        text = json.dumps(ability)
        if ability["kind"] == "triggered" and ability["trigger"]["event"] in banned.get("Trigger", ()):
            found.add(ability["trigger"]["event"])
        if ability["kind"] == "static" and static_kind(ability) in banned.get("Static kind", ()):
            found.add(static_kind(ability))
        found |= {op for op in banned.get("Effect", ()) if f'"effect": "{op}"' in text}
        found |= {k for k in banned.get("Keyword", ()) if f'"keyword": "{k}"' in text or f'"{k}": ' in text}
        if ability.get("condition", {}) and ability["condition"].get("behind_on_health") \
                and "behind_on_health" in banned.get("Condition", ()):
            found.add("behind_on_health")
        if '"played_this_turn"' in text and ({"played"} & (banned.get("Condition", set()) | banned.get("Count what", set()))):
            found.add("cards played this turn")
        if '"zone": "hand"' in text and "hand" in banned.get("Count what", ()):
            found.add("cards in hand")
        if '"choose_one"' in text and "choose_one" in banned.get("Step pattern", ()):
            found.add("choose one")
    found |= {k for k, _ in card.keywords if k in banned.get("Keyword", ())}
    return [f"{aspect} never makes {f}" for f in sorted(found)]
