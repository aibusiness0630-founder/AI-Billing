from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

import os

from app import db
from app.models import StockMovement, Product
from app.utils.decorators import login_required, premium_required
from app.utils.units import normalize_unit, convert_to_base, fmt_qty_unit, entry_units

stock_bp = Blueprint('stock', __name__)


@stock_bp.route("/stock_history")
@login_required
@premium_required
def stock_history():

    shop_id = session["shop_id"]

    movements = StockMovement.query.filter_by(
        shop_id=shop_id
    ).order_by(
        StockMovement.id.desc()
    ).limit(200).all()

    movement_list = []

    for m in movements:

        product = Product.query.get(m.product_id)
        unit = normalize_unit(product.unit) if product else "pcs"
        change = m.quantity_change or 0

        movement_list.append({
            "id": m.id,
            "product_name": product.name if product else "Unknown",
            # number kept for + / - colours, text for display ("+750 g", "-2 pcs")
            "quantity_change": change,
            "unit": unit,
            "quantity_text": ("+" if change > 0 else "-" if change < 0 else "") + fmt_qty_unit(abs(change), unit),
            "reason": m.reason,
            "reference_id": m.reference_id,
            "notes": m.notes,
            "created_at": m.created_at
        })

    return render_template(
        "stock_history.html",
        movements=movement_list
    )


@stock_bp.route("/adjust_stock", methods=["GET", "POST"])
@login_required
@premium_required
def adjust_stock():

    shop_id = session["shop_id"]

    products = Product.query.filter_by(shop_id=shop_id).order_by(Product.name).all()

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        product_id = request.form.get("product_id")
        adjustment_type = request.form.get("adjustment_type")
        quantity = request.form.get("quantity")
        entry_unit = request.form.get("unit", "")
        reason_note = request.form.get("notes", "").strip()

        if not product_id or not quantity:
            return "❌ Product and quantity are required"

        product = Product.query.filter_by(
            id=product_id,
            shop_id=shop_id
        ).first_or_404()

        base_unit = normalize_unit(product.unit)

        try:
            quantity = convert_to_base(quantity, entry_unit or base_unit, base_unit)
        except ValueError as e:
            return f"❌ {e}"

        if adjustment_type == "ADD":

            product.stock = round((product.stock or 0) + quantity, 3)
            quantity_change = quantity
            reason = "ADJUSTMENT"

        elif adjustment_type == "REMOVE":

            if (product.stock or 0) < quantity:
                return f"❌ Not enough stock. Available: {fmt_qty_unit(product.stock or 0, base_unit)}"

            product.stock = round(product.stock - quantity, 3)
            quantity_change = -quantity
            reason = "DAMAGE" if "damage" in reason_note.lower() else "ADJUSTMENT"

        else:
            return "❌ Invalid adjustment type"

        movement = StockMovement(
            product_id=product.id,
            shop_id=shop_id,
            quantity_change=quantity_change,
            reason=reason,
            notes=reason_note or f"Manual {adjustment_type.lower()} adjustment"
        )

        db.session.add(movement)
        db.session.commit()

        return redirect("/stock_history")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "adjust_stock.html",
        products=products,
        csrf_token=session.get("csrf_token")
    )