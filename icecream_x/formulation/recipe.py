"""Recipe: an arbitrary, user-defined formulation.

A :class:`Recipe` is nothing more than a named batch size plus a list of
(ingredient, mass) lines. It deliberately hard-codes nothing about what
"an ice cream" must contain -- any set of :class:`Ingredient` objects can
be combined, including recipes with zero fat, zero dairy, unconventional
sweeteners, etc. See :mod:`icecream_x.scenarios.recipes` for worked
examples (vanilla, high-fat premium, low-fat...) that build on this API
rather than being special-cased into it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from icecream_x.formulation.composition import Composition, WeighedIngredient, compose
from icecream_x.formulation.ingredients import Ingredient
from icecream_x.utils.validation import require_positive


@dataclass(slots=True)
class Recipe:
    name: str
    lines: list[WeighedIngredient] = field(default_factory=list)
    description: str = ""

    def add(self, ingredient: Ingredient, mass_kg: float) -> "Recipe":
        """Add an ingredient line and return self (fluent API)."""
        self.lines.append(WeighedIngredient(ingredient=ingredient, mass_kg=mass_kg))
        return self

    @property
    def batch_mass_kg(self) -> float:
        return sum(line.mass_kg for line in self.lines)

    def composition(self) -> Composition:
        if not self.lines:
            raise ValueError(f"Recipe '{self.name}' has no ingredient lines")
        return compose(self.lines)

    def scaled_to_batch_size(self, target_mass_kg: float) -> "Recipe":
        """Return a new Recipe with every line scaled to hit a target batch mass."""
        require_positive(target_mass_kg, "target_mass_kg")
        current = self.batch_mass_kg
        require_positive(current, f"batch mass of recipe '{self.name}'")
        factor = target_mass_kg / current
        scaled_lines = [
            WeighedIngredient(ingredient=line.ingredient, mass_kg=line.mass_kg * factor)
            for line in self.lines
        ]
        return Recipe(name=self.name, lines=scaled_lines, description=self.description)

    def ingredient_cost_per_kg(self) -> float:
        total = self.batch_mass_kg
        if total <= 0:
            return 0.0
        cost = sum(line.mass_kg * line.ingredient.cost_per_kg for line in self.lines)
        return cost / total

    def summary_table(self) -> list[dict[str, float | str]]:
        """A simple tabular summary (mass, mass %, cost) suitable for a DataFrame."""
        total = self.batch_mass_kg
        rows: list[dict[str, float | str]] = []
        for line in self.lines:
            rows.append(
                {
                    "ingredient": line.ingredient.name,
                    "mass_kg": line.mass_kg,
                    "mass_pct": 100.0 * line.mass_kg / total if total else 0.0,
                    "cost": line.mass_kg * line.ingredient.cost_per_kg,
                }
            )
        return rows
