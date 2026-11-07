"""Assembly library and quantity take-off.

* :mod:`.library` - generic illustrative materials, assemblies, foundation options and allowances
  (not specifications; carbon data are placeholders, not EPD/ICE values; no prices).
* :mod:`.measures` - named geometric measures per element instance with provenance.
* :mod:`.procurement` - cutting / waste / packaging arithmetic.
* :mod:`.takeoff` - assembly selection edits and the traceable bill of quantities.
"""

from .library import (
    LIBRARY_INFORMATION,
    SUBSTRUCTURE_RULES,
    TRADES,
    SubstructureRules,
    cost_keys,
    default_library,
    default_selection,
    is_purchasable,
    labour_cost_key,
    material_cost_key,
    validate_library,
)
from .measures import (
    ELEMENT_CODES,
    FOUNDATION_KEY,
    MEASURE_UNITS,
    MEASURES,
    OPENING_ELEMENT,
    ElementMeasures,
    Measure,
    TakeoffAssumptions,
    element_measures,
    opening_element,
    selection_basis,
)
from .procurement import procure, procurement_schedule
from .takeoff import (
    QUANTITY_CONVENTIONS,
    SUBSTRUCTURE_LINE_INDEX,
    apply_construction_assemblies,
    calculate_quantities,
    wall_thicknesses,
)

__all__ = [
    "LIBRARY_INFORMATION", "SUBSTRUCTURE_RULES", "TRADES", "SubstructureRules", "cost_keys", "default_library",
    "default_selection", "is_purchasable", "labour_cost_key", "material_cost_key", "validate_library",
    "ELEMENT_CODES", "FOUNDATION_KEY", "MEASURE_UNITS", "MEASURES", "OPENING_ELEMENT", "ElementMeasures", "Measure",
    "TakeoffAssumptions", "element_measures", "opening_element", "selection_basis", "procure", "procurement_schedule",
    "QUANTITY_CONVENTIONS", "SUBSTRUCTURE_LINE_INDEX", "apply_construction_assemblies", "calculate_quantities",
    "wall_thicknesses",
]
