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
from app.utils.decorators import login_required

stock_bp = Blueprint('stock', __name__)


@stock_bp.route("/stock_history")
@login_required
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

        movement_list.append({
            "id": m.id,
            "product_name": product.name if product else "Unknown",
            "quantity_change": m.quantity_change,
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
        reason_note = request.form.get("notes", "").strip()

        if not product_id or not quantity:
            return "❌ Product and quantity are required"

        try:
            quantity = int(quantity)
        except ValueError:
            return "❌ Invalid quantity"

        if quantity <= 0:
            return "❌ Quantity must be greater than 0"

        product = Product.query.filter_by(
            id=product_id,
            shop_id=shop_id
        ).first_or_404()

        if adjustment_type == "ADD":

            product.stock = (product.stock or 0) + quantity
            quantity_change = quantity
            reason = "ADJUSTMENT"

        elif adjustment_type == "REMOVE":

            if product.stock < quantity:
                return f"❌ Not enough stock. Available: {product.stock}"

            product.stock = product.stock - quantity
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