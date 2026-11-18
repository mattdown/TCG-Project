"""Records every random decision a generator makes: its derivation through the grammar.

Each decision keeps all the options that were open at that point, their probabilities and
the one taken, grouped into nested sections (trigger, steps, effect, target, …). The card
explorer (Blog/card_lab.py) draws this as the path the sampler took. The tracer makes the
same calls on the random generator as plain sampling would, so tracing never changes what is
generated.
"""
import random
from contextlib import contextmanager


class Tracer:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.tilt: dict[str, dict] = {}  # label -> option -> weight multiplier (a class's style, src/cards/classes.py)
        self.reset()

    def _tilted(self, label: str, options: dict) -> dict:
        """The options' weights times the tilt for this label. If the tilt closes every open option,
        the untilted weights are used (the class check then throws the card away)."""
        factors = self.tilt.get(label)
        if not factors:
            return options
        tilted = {o: w * factors.get(o, 1.0) for o, w in options.items()}
        return tilted if any(tilted.values()) else options

    def reset(self):
        self.root = {"section": "card", "children": []}
        self._stack = [self.root]

    @contextmanager
    def section(self, label: str):
        node = {"section": label, "children": []}
        self._stack[-1]["children"].append(node)
        self._stack.append(node)
        try:
            yield
        finally:
            self._stack.pop()

    def record(self, label: str, options: list[tuple[str, float]], chosen, note: str = ""):
        """A decision made elsewhere (with the random generator already called)."""
        total = sum(w for _, w in options) or 1
        self._stack[-1]["children"].append({
            "decision": label, "chosen": _name(chosen), "note": note,
            "options": [{"name": _name(o), "p": round(w / total, 4)} for o, w in options]})

    def weighted(self, label: str, options: dict, note: str = ""):
        """Options with weight 0 are shown as closed at this point but can't be chosen."""
        options = self._tilted(label, options)
        open_ = {o: w for o, w in options.items() if w}
        chosen = self.rng.choices(list(open_), list(open_.values()))[0]
        self.record(label, list(options.items()), chosen, note)
        return chosen

    def chance(self, label: str, p: float, note: str = "") -> bool:
        result = self.rng.random() < p
        self.record(label, [("yes", p), ("no", 1 - p)], "yes" if result else "no", note)
        return result

    def choice(self, label: str, seq, note: str = ""):
        seq = list(seq)
        if label in self.tilt and all(isinstance(o, (str, int)) for o in seq):
            return self.weighted(label, {o: 1 for o in seq}, note)
        chosen = self.rng.choice(seq)
        self.record(label, [(o, 1) for o in seq], chosen, note)
        return chosen

    def small(self, label: str, lo: int, hi: int, note: str = "") -> int:
        """A number in [lo, hi], weighted towards the low end."""
        values = list(range(lo, hi + 1))
        weights = [1 / (i + 1) for i in range(len(values))]
        chosen = self.rng.choices(values, weights)[0]
        self.record(label, list(zip(values, weights)), chosen, note)
        return chosen

    def randint(self, label: str, lo: int, hi: int, note: str = "") -> int:
        if label in self.tilt:
            return self.weighted(label, {v: 1 for v in range(lo, hi + 1)}, note)
        chosen = self.rng.randint(lo, hi)
        self.record(label, [(v, 1) for v in range(lo, hi + 1)], chosen, note)
        return chosen

    def fixed(self, label: str, value, note: str):
        """A step the grammar forces: shown on the path, but no randomness involved."""
        self.record(label, [(value, 1)], value, note)


def _name(option) -> str:
    if isinstance(option, tuple):
        return " ".join(str(o) for o in option)
    if isinstance(option, dict):
        return ", ".join(f"{k} {v}" for k, v in option.items())
    return str(option)


def path_probability(node: dict) -> float:
    """Chance of this exact path: the product of every chosen option's probability."""
    p = 1.0
    for child in node["children"]:
        if "decision" in child:
            p *= next(o["p"] for o in child["options"] if o["name"] == child["chosen"])
        else:
            p *= path_probability(child)
    return p


def decisions(node: dict) -> int:
    return sum(decisions(c) if "section" in c else len(c["options"]) > 1 for c in node["children"])
