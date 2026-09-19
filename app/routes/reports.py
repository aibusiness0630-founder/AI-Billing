from flask import (
    Blueprint,
    render_template,
    request,
    session
)

from datetime import datetime, timedelta

from app.models import Invoice, InvoiceItem, Product, Customer, Purchase
from app.utils.decorators import login_required, premium_required

reports_bp = Blueprint('reports', __name__)


@reports_bp.route("/reports")
@login_required
@premium_required
def reports():

    shop_id = session["shop_id"]

    period = request.args.get("period", "daily")

    today = datetime.now().date()

    if period == "daily":
        start_date = today
        end_date = today
        period_label = "Today"

    elif period == "weekly":
        start_date = today - timedelta(days=7)
        end_date = today
        period_label = "Last 7 Days"

    elif period == "monthly":
        start_date = today - timedelta(days=30)
        end_date = today
        period_label = "Last 30 Days"

    else:
        start_date = today
        end_date = today
        period_label = "Today"

    invoices = Invoice.query.filter(
        Invoice.shop_id == shop_id,
        Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
        Invoice.created_at <= datetime.combine(end_date, datetime.max.time())
    ).all()

    total_sales = sum(inv.total_amount or 0 for inv in invoices)
    total_bills = len(invoices)
    total_discount = sum(inv.discount_amount or 0 for inv in invoices)
    total_tax = sum(inv.tax_amount or 0 for inv in invoices)

    avg_bill = round(total_sales / total_bills, 2) if total_bills else 0

    payment_breakdown = {}

    for inv in invoices:
        method = inv.payment_method or "Cash"
        payment_breakdown[method] = payment_breakdown.get(method, 0) + (inv.total_amount or 0)

    invoice_ids = [inv.id for inv in invoices]

    items = InvoiceItem.query.filter(
        InvoiceItem.invoice_id.in_(invoice_ids)
    ).all() if invoice_ids else []

    product_sales = {}

    for item in items:
        product = Product.query.get(item.product_id)
        pname = product.name if product else "Unknown"

        if pname not in product_sales:
            product_sales[pname] = {"qty": 0, "revenue": 0}

        product_sales[pname]["qty"] += item.quantity
        product_sales[pname]["revenue"] += item.total or 0

    product_sales_list = sorted(
        [{"name": k, "qty": v["qty"], "revenue": v["revenue"]} for k, v in product_sales.items()],
        key=lambda x: x["revenue"],
        reverse=True
    )

    total_cost = 0

    for item in items:
        product = Product.query.get(item.product_id)
        if product and product.price_cost:
            total_cost += (product.price_cost * item.quantity)

    estimated_profit = total_sales - total_cost

    purchases = Purchase.query.filter(
        Purchase.shop_id == shop_id,
        Purchase.created_at >= datetime.combine(start_date, datetime.min.time()),
        Purchase.created_at <= datetime.combine(end_date, datetime.max.time())
    ).all()

    total_purchases = sum(p.total_amount or 0 for p in purchases)

    return render_template(
        "reports.html",
        period=period,
        period_label=period_label,
        total_sales=total_sales,
        total_bills=total_bills,
        total_discount=total_discount,
        total_tax=total_tax,
        avg_bill=avg_bill,
        payment_breakdown=payment_breakdown,
        product_sales_list=product_sales_list[:10],
        estimated_profit=estimated_profit,
        total_cost=total_cost,
        total_purchases=total_purchases
    )