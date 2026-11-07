"""Costing: rate books, the nine-layer construction cost engine and repeat-build economics.

* :mod:`.rates` - validated rate-book loading (CSV / JSON, untrusted input), merging and
  rate resolution (unit, currency, VAT, validity, priority, escalation, regional factor).
* :mod:`.adapters` - ``PricingAdapter`` protocol, manual CSV adapter, bundled FICTIONAL demo rates
  (no network access).
* :mod:`.engine` - ``estimate_construction_cost``: BoQ x rates -> layered estimate with cumulative
  cost boundaries; unresolved items are listed, never priced as zero.
* :mod:`.repeat_build` - C(n), average, incremental and underlying marginal cost of repeat builds
  with learning (unit or cumulative-average model), order-level pack re-rounding, procurement
  tiers, capacity steps, time-related site overhead and factory-gate / installed / development
  boundaries.

Bundled prices are fictional demonstration data, not market prices.
"""

from .adapters import (
    DEMO_RATES_PATH,
    FictionalDemoPricingAdapter,
    ManualCSVPricingAdapter,
    PricingAdapter,
    demo_rate_book,
    fetch_rate_book,
)
from .engine import (
    BOUNDARY_KEYS,
    COST_CONVENTIONS,
    COST_PARAMETER_FALLBACKS,
    DEFAULT_COST_RULES,
    RULE_COST_KEYS,
    CostRules,
    boundary_table,
    cost_lines_table,
    estimate_construction_cost,
)
from .rates import (
    MAX_FILE_BYTES,
    MAX_ROWS,
    PRICING_DATE_WARNING,
    RATE_COLUMNS,
    RATE_SOURCE_BASIS,
    TIME_BASED_COST_KEY_PREFIXES,
    RateBookError,
    RateIndex,
    ResolvedRate,
    cost_key_layer,
    load_rate_book_csv,
    load_rate_book_json,
    merge_rate_books,
    rate_basis,
    rate_book_from_records,
    rate_book_to_dataframe,
    rate_index,
    resolve_rate,
    resolve_rate_detailed,
)
from .repeat_build import (
    BOUNDARY_COMPONENTS,
    BOUNDARY_DEFINITIONS,
    LEARNING_MODEL_LABELS,
    METHOD_FACTORY_MATERIAL_FRACTION,
    STEP_COMPONENTS,
    UNDERLYING_MARGINAL_DEFINITION,
    calculate_incremental_cost,
    comparison_table,
    component_curves,
    demo_production_scenarios,
    factory_vs_installed,
    learning_factors,
    single_house_reconciliation,
    site_logistics_for,
    tier_discount,
    total_cost_curve,
)

__all__ = [
    "DEMO_RATES_PATH", "FictionalDemoPricingAdapter", "ManualCSVPricingAdapter", "PricingAdapter", "demo_rate_book",
    "fetch_rate_book", "BOUNDARY_KEYS", "COST_CONVENTIONS", "DEFAULT_COST_RULES", "RULE_COST_KEYS", "CostRules",
    "boundary_table", "cost_lines_table", "estimate_construction_cost", "MAX_FILE_BYTES", "MAX_ROWS", "RATE_COLUMNS",
    "RATE_SOURCE_BASIS", "RateBookError", "RateIndex", "ResolvedRate", "cost_key_layer", "load_rate_book_csv",
    "load_rate_book_json", "merge_rate_books", "rate_basis", "rate_book_from_records", "rate_book_to_dataframe",
    "rate_index", "resolve_rate", "resolve_rate_detailed", "BOUNDARY_COMPONENTS", "BOUNDARY_DEFINITIONS",
    "METHOD_FACTORY_MATERIAL_FRACTION", "calculate_incremental_cost", "comparison_table", "component_curves",
    "demo_production_scenarios", "factory_vs_installed", "learning_factors", "tier_discount", "total_cost_curve",
    "COST_PARAMETER_FALLBACKS", "PRICING_DATE_WARNING", "TIME_BASED_COST_KEY_PREFIXES", "LEARNING_MODEL_LABELS",
    "STEP_COMPONENTS", "UNDERLYING_MARGINAL_DEFINITION", "single_house_reconciliation", "site_logistics_for",
]
