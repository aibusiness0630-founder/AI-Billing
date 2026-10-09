from io import BytesIO

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    send_file,
    session
)

from reportlab.pdfgen import canvas

from app import db
from app.models import (
    Invoice,
    InvoiceItem,
    Customer,
    Product,
    Shop,
    AuditLog
)
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


@history_bp.route("/delete_invoice/<int:id>")
@login_required
def delete_invoice(id):

    shop_id = session["shop_id"]

    invoice = Invoice.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    invoice_number = invoice.invoice_number
    total_amount = invoice.total_amount

    audit_log = AuditLog(
        shop_id=shop_id,
        action="DELETE",
        entity_type="INVOICE",
        entity_id=invoice.id,
        details=f"Deleted invoice {invoice_number} worth Rs.{total_amount:.2f}"
    )

    db.session.add(audit_log)

    InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()

    db.session.delete(invoice)
    db.session.commit()

    return redirect("/history")


@history_bp.route("/download_bill/<int:id>")
@login_required
def download_bill(id):

    shop_id = session["shop_id"]

    invoice = Invoice.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    shop = Shop.query.get(shop_id)

    customer = Customer.query.get(invoice.customer_id) if invoice.customer_id else None

    items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()

    buffer = BytesIO()
    c = canvas.Canvas(buffer)

    # HEADER
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(300, 800, shop.shop_name if shop else "My Shop")

    c.setFont("Helvetica", 11)
    c.drawCentredString(300, 780, (shop.address or "") if shop else "")
    c.drawCentredString(300, 765, f"Phone : {(shop.phone or '') if shop else ''}")

    c.line(40, 750, 550, 750)

    # INVOICE INFO
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 725, f"Invoice No : {invoice.invoice_number}")

    date_text = invoice.created_at.strftime("%d-%m-%Y %I:%M %p") if invoice.created_at else ""
    c.drawString(330, 725, date_text)

    c.drawString(50, 700, f"Customer : {customer.name if customer else 'Walk-in Customer'}")
    c.drawString(50, 680, f"Mobile : {customer.mobile if customer else '-'}")
    c.drawString(330, 680, f"Payment : {invoice.payment_method or 'Cash'}")

    # TABLE HEADER
    c.line(40, 660, 550, 660)

    c.drawString(50, 640, "Product")
    c.drawString(280, 640, "Qty")
    c.drawString(350, 640, "Price")
    c.drawString(450, 640, "Amount")

    c.line(40, 630, 550, 630)

    # ITEMS
    y = 605
    c.setFont("Helvetica", 11)

    for item in items:

        if y < 120:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = 780

        product = Product.query.get(item.product_id)
        name = (product.name if product else "N/A")[:32]

        c.drawString(50, y, name)
        c.drawString(280, y, str(item.quantity))
        c.drawString(350, y, f"Rs.{item.price:.2f}")
        c.drawString(450, y, f"Rs.{item.total:.2f}")

        y -= 22

    c.line(40, y, 550, y)
    y -= 22

    # TOTALS
    c.setFont("Helvetica", 11)
    c.drawString(330, y, "Subtotal:")
    c.drawString(450, y, f"Rs.{(invoice.subtotal or 0):.2f}")
    y -= 18

    if invoice.discount_amount:
        c.drawString(330, y, f"Discount ({invoice.discount_percent}%):")
        c.drawString(450, y, f"- Rs.{invoice.discount_amount:.2f}")
        y -= 18

    if invoice.tax_amount:
        c.drawString(330, y, f"Tax ({invoice.tax_percent}%):")
        c.drawString(450, y, f"+ Rs.{invoice.tax_amount:.2f}")
        y -= 18

    c.setFont("Helvetica-Bold", 14)
    c.drawString(330, y - 6, "Grand Total:")
    c.drawString(450, y - 6, f"Rs.{invoice.total_amount:.2f}")

    c.setFont("Helvetica", 12)
    c.drawCentredString(300, y - 60, "Thank You! Visit Again")

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{invoice.invoice_number}.pdf",
        mimetype="application/pdf"
    )