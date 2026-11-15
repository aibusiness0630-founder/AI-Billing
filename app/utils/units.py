"""
Units for products (koli kadai, oil shop, grocery ...).

A product has ONE base unit: pcs, dozen, packet, kg or litre.
Price, stock and bill quantity are always stored in that base unit
(0.75 kg, not 750 g).

At billing time kg products can be typed in g, litre products in ml:
    convert_to_base(750, "g", "kg") -> 0.75
"""

# base unit -> {label, whole_only, entry units: {unit: factor to base}}
UNITS = {
    "pcs":    {"label": "Piece (pcs)",     "whole_only": True,  "entry": {"pcs": 1}},
    "dozen":  {"label": "Dozen",           "whole_only": False, "entry": {"dozen": 1}},
    "packet": {"label": "Packet / Box",    "whole_only": True,  "entry": {"packet": 1}},
    "kg":     {"label": "Kilogram (kg)",   "whole_only": False, "entry": {"kg": 1, "g": 0.001}},
    "litre":  {"label": "Litre",           "whole_only": False, "entry": {"litre": 1, "ml": 0.001}},
}

DEFAULT_UNIT = "pcs"


def normalize_unit(unit):
    """Unknown / empty unit -> 'pcs' (old products)."""
    unit = (unit or "").strip().lower()
    return unit if unit in UNITS else DEFAULT_UNIT


def unit_choices():
    return [(key, cfg["label"]) for key, cfg in UNITS.items()]


def entry_units(base_unit):
    """Units allowed while typing a quantity, e.g. kg -> ['kg', 'g']."""
    return list(UNITS[normalize_unit(base_unit)]["entry"].keys())


def convert_to_base(qty, entry_unit, base_unit):
    """
    Typed quantity -> quantity in the product's base unit (rounded to 3 decimals).
    Raises ValueError for bad input, so routes can show a friendly message.
    """
    base_unit = normalize_unit(base_unit)
    cfg = UNITS[base_unit]

    entry_unit = (entry_unit or base_unit).strip().lower()
    if entry_unit not in cfg["entry"]:
        raise ValueError("Unit '%s' is not allowed for a %s product" % (entry_unit, base_unit))

    try:
        qty = float(qty)
    except (TypeError, ValueError):
        raise ValueError("Quantity must be a number")

    if qty != qty or qty in (float("inf"), float("-inf")):
        raise ValueError("Quantity must be a number")
    if qty <= 0:
        raise ValueError("Quantity must be more than 0")

    base_qty = round(qty * cfg["entry"][entry_unit], 3)

    if base_qty <= 0:
        raise ValueError("Quantity is too small")
    if base_qty > 100000:
        raise ValueError("Quantity is too large")
    if cfg["whole_only"] and base_qty != int(base_qty):
        raise ValueError("%s must be a whole number" % cfg["label"])

    return base_qty


def fmt_qty(q):
    """1.0 -> '1', 0.75 -> '0.75', 12.5 -> '12.5' (no ugly .0 / long decimals)."""
    try:
        q = round(float(q), 3)
    except (TypeError, ValueError):
        return "0"
    if q == int(q):
        return str(int(q))
    return ("%.3f" % q).rstrip("0").rstrip(".")


def fmt_qty_unit(q, unit):
    """Bill text: 0.75 kg -> '750 g', 2.5 kg -> '2.5 kg', 0.25 litre -> '250 ml'."""
    unit = normalize_unit(unit)
    try:
        q = round(float(q), 3)
    except (TypeError, ValueError):
        q = 0.0

    if unit == "kg" and 0 < q < 1:
        return "%s g" % fmt_qty(q * 1000)
    if unit == "litre" and 0 < q < 1:
        return "%s ml" % fmt_qty(q * 1000)

    return "%s %s" % (fmt_qty(q), unit)


def line_total(qty, price):
    """Money for one bill line, rounded to paise."""
    return round(float(qty) * float(price), 2)