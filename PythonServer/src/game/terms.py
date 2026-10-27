"""Player-facing names for game terms.

Every term is a placeholder until the game has a name and theme. Code uses the internal
keys; anything shown to a player (action text, the Unity client) goes through TERMS.
"""

TERMS = {
    "hero": "hero",
    "mana": "mana",
    "unit": "unit",
    "attack": "attack",
    "fresh": "fresh",
    "aspect": "aspect",
    "spare_spore": "Spare Spore",
}

ASPECTS = ("aspect_1", "aspect_2", "aspect_3", "aspect_4", "aspect_5", "aspect_6")
ASPECT_NAMES = {"aspect_1": "Ember", "aspect_2": "Bog", "aspect_3": "Moss", "aspect_4": "Meadow",
                "aspect_5": "Glow", "aspect_6": "Frost"}  # see docs/theme.md
# One line on each habitat's feel, for the client's help screen. Neutral cards have no aspect.
ASPECT_DESCRIPTIONS = {
    "aspect_1": "Burnt-woodland toadstools: fire and ash.",
    "aspect_2": "Puddle shrooms: rain, lily pads and reeds.",
    "aspect_3": "The deep forest floor: ferns and fallen logs.",
    "aspect_4": "Sunny fields: farms, bakeries and flowers.",
    "aspect_5": "Night shrooms: fireflies and moonlight.",
    "aspect_6": "Winter woods: snowcaps, ice and pine.",
}
NEUTRAL = "neutral"  # the key for cards with no aspect
NEUTRAL_NAME = "Neutral"
NEUTRAL_DESCRIPTION = "No habitat: any deck can use it."

# Keyword → whether it carries a number ("Duelist +2") or is just present ("Guard").
KEYWORDS = {"guard": False, "elusive": False, "charge": False, "duelist": True, "armor": True}
KEYWORD_NAMES = {"guard": "Guard", "elusive": "Elusive", "charge": "Charge", "duelist": "Duelist", "armor": "Armor"}
# Reminder text for each keyword, shown when a card is inspected. N is the keyword's number.
KEYWORD_RULES = {
    "guard": "Enemy units must attack a Guard unit if they can.",
    "elusive": "Can't be attacked or chosen by enemy abilities until it attacks.",
    "charge": "Can attack the turn it's played.",
    "duelist": "+N power while attacking.",
    "armor": "Takes N less damage from attacks, never below 0.",
}


def keyword_text(name: str, value: int) -> str:
    """'Guard', 'Duelist +2'."""
    return f"{KEYWORD_NAMES[name]} +{value}" if KEYWORDS[name] else KEYWORD_NAMES[name]
