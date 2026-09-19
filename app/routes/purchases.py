from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

from datetime import datetime
import os

from app import db
from app.models import Purchase, PurchaseItem, Supplier, Product, StockMovement, Payment
from app.utils.decorators import login_required, premium_required

purchases_bp = Blueprint('purchases', __name__)


@purchases_bp.route("/purchases")
@login_required
@premium_required
def purchases():

    shop_id = session["shop_id"]

    all_purchases = Purchase.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Purchase.id.desc()
    ).all()

    purchase_list = []

    for p in all_purchases:

        supplier = Supplier.query.get(p.supplier_id)

        paid_amount = sum(
            pay.amount or 0
            for pay in Payment.query.filter_by(purchase_id=p.id).all()
        ) if hasattr(Payment, 'purchase_id') else 0

        balance = (p.total_amount or 0) - paid_amount

        purchase_list.append({
            "id": p.id,
            "purchase_number": p.purchase_number,
            "supplier_name": supplier.name if supplier else "Unknown",
            "total_amount": p.total_amount,
            "paid_amount": paid_amount,
            "balance": balance,
            "payment_status": p.payment_status,
            "created_at": p.created_at
        })

    return render_template(
        "purchases.html",
        purchases=purchase_list
    )


@purchases_bp.route("/add_purchase", methods=["GET", "POST"])
@login_required
@premium_required
def add_purchase():

    shop_id = session["shop_id"]

    suppliers = Supplier.query.filter_by(shop_id=shop_id).order_by(Supplier.name).all()
    products = Product.query.filter_by(shop_id=shop_id).order_by(Product.name).all()

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        supplier_id = request.form.get("supplier_id")

        if not supplier_id:
            return "❌ Supplier is required"

        payment_method = request.form.get("payment_method", "Cash")
        amount_paid = request.form.get("amount_paid", "0")

        try:
            amount_paid = float(amount_paid) if amount_paid else 0
        except ValueError:
            amount_paid = 0

        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        cost_prices = request.form.getlist("cost_price[]")

        grand_total = 0
        items = []

        for pid, qty, price in zip(product_ids, quantities, cost_prices):

            if not pid or not qty or not price:
                continue

            try:
                qty = int(qty)
                price = float(price)
            except ValueError:
                return "❌ Invalid quantity or price"

            if qty <= 0:
                return "❌ Quantity must be greater than 0"

            total = qty * price

            items.append({
                "product_id": int(pid),
                "quantity": qty,
                "cost_price": price,
                "total": total
            })

            grand_total += total

        if not items:
            return "❌ Add at least one product"

        if amount_paid > grand_total:
            return "❌ Amount paid cannot be more than total amount"

        if amount_paid >= grand_total:
            payment_status = "PAID"
        elif amount_paid > 0:
            payment_status = "PARTIAL"
        else:
            payment_status = "PENDING"

        last_purchase = Purchase.query.filter_by(shop_id=shop_id).order_by(Purchase.id.desc()).first()
        next_number = (last_purchase.id + 1) if last_purchase else 1
        purchase_number = f"PUR-{shop_id}-{next_number:05d}"

        new_purchase = Purchase(
            shop_id=shop_id,
            supplier_id=int(supplier_id),
            purchase_number=purchase_number,
            subtotal=grand_total,
            total_amount=grand_total,
            payment_status=payment_status
        )

        db.session.add(new_purchase)
        db.session.flush()

        for item in items:

            purchase_item = PurchaseItem(
                purchase_id=new_purchase.id,
                product_id=item["product_id"],
                quantity=item["quantity"],
                cost_price=item["cost_price"],
                total=item["total"]
            )

            db.session.add(purchase_item)

            product = Product.query.get(item["product_id"])

            if product:

                product.stock = (product.stock or 0) + item["quantity"]

                if item["cost_price"]:
                    product.price_cost = item["cost_price"]

                stock_movement = StockMovement(
                    product_id=product.id,
                    shop_id=shop_id,
                    quantity_change=item["quantity"],
                    reason="PURCHASE",
                    reference_id=purchase_number,
                    notes=f"Purchased from supplier - {payment_method}"
                )

                db.session.add(stock_movement)

        if amount_paid > 0:

            payment = Payment(
                shop_id=shop_id,
                invoice_id=None,
                amount=amount_paid,
                method=payment_method,
                reference_number=purchase_number,
                notes=f"Payment for purchase {purchase_number}"
            )

            db.session.add(payment)

        supplier = Supplier.query.get(int(supplier_id))

        if supplier:

            supplier.total_purchases = (supplier.total_purchases or 0) + grand_total

            balance = grand_total - amount_paid

            supplier.outstanding_amount = (supplier.outstanding_amount or 0) + balance

        db.session.commit()

        return redirect(f"/purchase/{new_purchase.id}")

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "add_purchase.html",
        suppliers=suppliers,
        products=products,
        csrf_token=session.get("csrf_token")
    )


@purchases_bp.route("/purchase/<int:id>")
@login_required
@premium_required
def view_purchase(id):

    shop_id = session["shop_id"]

    purchase = Purchase.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    supplier = Supplier.query.get(purchase.supplier_id)

    items = PurchaseItem.query.filter_by(purchase_id=purchase.id).all()

    items_with_product = []

    for item in items:
        product = Product.query.get(item.product_id)
        items_with_product.append({
            "product_name": product.name if product else "N/A",
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "total": item.total
        })

    payments = Payment.query.filter_by(
        reference_number=purchase.purchase_number
    ).order_by(Payment.id.desc()).all()

    total_paid = sum(p.amount or 0 for p in payments)

    balance = (purchase.total_amount or 0) - total_paid

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "view_purchase.html",
        purchase=purchase,
        supplier=supplier,
        items=items_with_product,
        payments=payments,
        total_paid=total_paid,
        balance=balance,
        csrf_token=session.get("csrf_token")
    )


@purchases_bp.route("/pay_purchase/<int:id>", methods=["POST"])
@login_required
@premium_required
def pay_purchase(id):

    shop_id = session["shop_id"]

    purchase = Purchase.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    csrf_token = request.form.get("csrf_token", "")
    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    amount = request.form.get("amount", "0")
    method = request.form.get("payment_method", "Cash")

    try:
        amount = float(amount)
    except ValueError:
        return "❌ Invalid amount"

    if amount <= 0:
        return "❌ Amount must be greater than 0"

    existing_payments = Payment.query.filter_by(
        reference_number=purchase.purchase_number
    ).all()

    total_paid = sum(p.amount or 0 for p in existing_payments)

    balance = (purchase.total_amount or 0) - total_paid

    if amount > balance:
        return f"❌ Amount exceeds remaining balance of ₹{balance:.2f}"

    payment = Payment(
        shop_id=shop_id,
        invoice_id=None,
        amount=amount,
        method=method,
        reference_number=purchase.purchase_number,
        notes=f"Balance payment for {purchase.purchase_number}"
    )

    db.session.add(payment)

    new_total_paid = total_paid + amount
    new_balance = (purchase.total_amount or 0) - new_total_paid

    if new_balance <= 0:
        purchase.payment_status = "PAID"
    else:
        purchase.payment_status = "PARTIAL"

    supplier = Supplier.query.get(purchase.supplier_id)

    if supplier:
        supplier.outstanding_amount = max(0, (supplier.outstanding_amount or 0) - amount)

    db.session.commit()

    return redirect(f"/purchase/{id}")