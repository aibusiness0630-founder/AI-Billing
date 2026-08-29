from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

from app.models import Invoice, Customer, InvoiceItem
from app.utils.decorators import login_required

history_bp = Blueprint('history', __name__)


@history_bp.route("/history")
@login_required
def history():

    shop_id = session["shop_id"]

    invoices = Invoice.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Invoice.id.desc()
    ).all()

    bills = []

    for inv in invoices:

        customer = Customer.query.get(inv.customer_id) if inv.customer_id else None

        bills.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "customer_name": customer.name if customer else "Walk-in Customer",
            "mobile": customer.mobile if customer else "",
            "total": inv.total_amount,
            "created_at": inv.created_at,
            "payment_status": inv.payment_status
        })

    return render_template(
        "history.html",
        bills=bills
    )


@history_bp.route("/search", methods=["GET", "POST"])
@login_required
def search():

    shop_id = session["shop_id"]

    bills = []
    search_value = ""

    if request.method == "POST":

        search_value = request.form.get("search", "").strip()

        if search_value:

            invoices = Invoice.query.join(Customer, isouter=True).filter(
                Invoice.shop_id == shop_id,
                (
                    Customer.name.ilike(f"%{search_value}%")
                    |
                    Customer.mobile.ilike(f"%{search_value}%")
                    |
                    Invoice.invoice_number.ilike(f"%{search_value}%")
                )
            ).order_by(
                Invoice.id.desc()
            ).all()

            for inv in invoices:
                customer = Customer.query.get(inv.customer_id) if inv.customer_id else None
                bills.append({
                    "id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "customer_name": customer.name if customer else "Walk-in Customer",
                    "mobile": customer.mobile if customer else "",
                    "total": inv.total_amount,
                    "created_at": inv.created_at
                })

    return render_template(
        "search.html",
        bills=bills,
        search_value=search_value
    )


@history_bp.route("/invoice/<int:id>")
@login_required
def view_invoice(id):

    shop_id = session["shop_id"]

    invoice = Invoice.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    items = InvoiceItem.query.filter_by(
        invoice_id=invoice.id
    ).all()

    from app.models import Product

    items_with_product = []

    for item in items:
        product = Product.query.get(item.product_id)
        items_with_product.append({
            "product_name": product.name if product else "N/A",
            "quantity": item.quantity,
            "price": item.price,
            "total": item.total
        })

    return render_template(
        "view_invoice.html",
        invoice=invoice,
        items=items_with_product
    )