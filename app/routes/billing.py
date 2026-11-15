from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    send_file,
    session
)

from datetime import datetime
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app import db
from app.models import Product, Customer, Invoice, InvoiceItem, Subscription, StockMovement, AuditLog
from app.utils.decorators import login_required
from app.utils.units import normalize_unit, convert_to_base, fmt_qty, fmt_qty_unit, line_total

billing_bp = Blueprint('billing', __name__)


@billing_bp.route("/", methods=["GET", "POST"])
@login_required
def home():

    shop_id = session["shop_id"]

    product_list = Product.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Product.name
    ).all()

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        customer_name = request.form.get("customer_name", "").strip()
        if not customer_name:
            customer_name = "Walk-in Customer"

        mobile = request.form.get("mobile", "").strip()

        payment_method = request.form.get("payment_method", "Cash")

        discount_percent = request.form.get("discount_percent", "0")
        tax_percent = request.form.get("tax_percent", "0")

        try:
            discount_percent = float(discount_percent) if discount_percent else 0
            tax_percent = float(tax_percent) if tax_percent else 0
        except ValueError:
            discount_percent = 0
            tax_percent = 0

        products = request.form.getlist("product[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("price[]")
        entry_units_form = request.form.getlist("unit[]")

        # older pages may not send unit[] -> use each product's own unit
        while len(entry_units_form) < len(products):
            entry_units_form.append("")

        subtotal = 0
        bill_items = []
        used_stock = {}

        for product, quantity, price, entry_unit in zip(products, quantities, prices, entry_units_form):

            if not product or not quantity or not price:
                continue

            try:
                price = float(price)
            except ValueError:
                return "❌ Invalid quantity or price"

            if price < 0:
                return "❌ Invalid price"

            product_data = Product.query.filter_by(
                name=product,
                shop_id=shop_id
            ).first()

            if not product_data:
                return f"""
                <h2 style='color:red'>❌ Product not found</h2>
                <h3>{product}</h3>
                <a href='/'>Back</a>
                """

            base_unit = normalize_unit(product_data.unit)

            try:
                quantity = convert_to_base(quantity, entry_unit or base_unit, base_unit)
            except ValueError as e:
                return f"""
                <h2 style='color:red'>❌ {product}: {e}</h2>
                <a href='/'>Back</a>
                """

            # same product in 2 rows -> check the combined quantity
            already = used_stock.get(product_data.id, 0)
            used_stock[product_data.id] = round(already + quantity, 3)

            if (product_data.stock or 0) < used_stock[product_data.id]:
                return f"""
                <h2 style='color:red'>❌ Not enough stock for {product}</h2>
                <h3>Available Stock: {fmt_qty_unit(product_data.stock or 0, base_unit)}</h3>
                <a href='/'>Back</a>
                """

            total = line_total(quantity, price)

            bill_items.append({
                "product_id": product_data.id,
                "product": product,
                "quantity": quantity,
                "unit": base_unit,
                "price": price,
                "total": total
            })

            subtotal += total

        # -------------------------------------------------
        # CALCULATE DISCOUNT + TAX
        # -------------------------------------------------

        discount_amount = round(subtotal * (discount_percent / 100), 2)

        after_discount = subtotal - discount_amount

        tax_amount = round(after_discount * (tax_percent / 100), 2)

        grand_total = after_discount + tax_amount

        # Find or create customer
        customer = None
        if mobile:
            customer = Customer.query.filter_by(
                mobile=mobile,
                shop_id=shop_id
            ).first()

            if not customer:
                customer = Customer(
                    shop_id=shop_id,
                    name=customer_name,
                    mobile=mobile
                )
                db.session.add(customer)
                db.session.flush()
            else:
                customer.name = customer_name

            customer.total_spent = (customer.total_spent or 0) + grand_total
            customer.total_transactions = (customer.total_transactions or 0) + 1
            customer.last_purchase_date = datetime.utcnow()

        # Create invoice number
        last_invoice = Invoice.query.filter_by(shop_id=shop_id).order_by(Invoice.id.desc()).first()
        next_number = (last_invoice.id + 1) if last_invoice else 1
        invoice_number = f"INV-{shop_id}-{next_number:05d}"

        new_invoice = Invoice(
            shop_id=shop_id,
            customer_id=customer.id if customer else None,
            invoice_number=invoice_number,
            subtotal=subtotal,
            discount_amount=discount_amount,
            discount_percent=discount_percent,
            tax_amount=tax_amount,
            tax_percent=tax_percent,
            total_amount=grand_total,
            payment_method=payment_method,
            payment_status="PAID"
        )

        db.session.add(new_invoice)
        db.session.flush()

        for item in bill_items:

            invoice_item = InvoiceItem(
                invoice_id=new_invoice.id,
                product_id=item["product_id"],
                quantity=item["quantity"],
                unit=item["unit"],
                price=item["price"],
                total=item["total"]
            )

            db.session.add(invoice_item)

            product_data = Product.query.get(item["product_id"])

            if product_data:

                product_data.stock = round((product_data.stock or 0) - item["quantity"], 3)

                stock_movement = StockMovement(
                    product_id=product_data.id,
                    shop_id=shop_id,
                    quantity_change=-item["quantity"],
                    reason="SALE",
                    reference_id=invoice_number,
                    notes=f"Sold via billing - {payment_method}"
                )

                db.session.add(stock_movement)

        db.session.commit()

        from app.models import Shop
        shop = Shop.query.filter_by(id=shop_id).first()

        current_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")

        # what the bill / WhatsApp message shows: "750 g", "2 pcs", "1.5 kg"
        bill_products = [i["product"] for i in bill_items]
        bill_quantities = [fmt_qty_unit(i["quantity"], i["unit"]) for i in bill_items]
        bill_prices = [i["price"] for i in bill_items]

        return render_template(
            "bill.html",
            shop=shop,
            customer_name=customer_name,
            mobile=mobile,
            products=bill_products,
            quantities=bill_quantities,
            prices=bill_prices,
            items=bill_items,
            subtotal=subtotal,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            tax_percent=tax_percent,
            tax_amount=tax_amount,
            grand_total=grand_total,
            payment_method=payment_method,
            current_time=current_time,
            invoice_id=new_invoice.id
        )

    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "index.html",
        product_list=product_list,
        csrf_token=session.get("csrf_token")
    )


@billing_bp.route("/dashboard")
@login_required
def dashboard():

    shop_id = session["shop_id"]

    subscription = Subscription.query.filter_by(shop_id=shop_id).first()

    remaining_days = None
    subscription_warning = None

    if subscription:

        today = datetime.now().date()

        if subscription.expiry_date:

            remaining_days = (subscription.expiry_date - today).days

            if remaining_days == 2:
                subscription_warning = "⚠ Your subscription expires in 2 days."
            elif remaining_days == 1:
                subscription_warning = "⚠ Your subscription expires tomorrow."
            elif remaining_days == 0:
                subscription_warning = "⚠ Your subscription expires today."
            elif remaining_days < 0:
                subscription_warning = "❌ Your subscription has expired. Please renew."

    invoices = Invoice.query.filter_by(shop_id=shop_id).all()

    total_bills = len(invoices)
    total_revenue = sum(inv.total_amount or 0 for inv in invoices)

    total_customers = Customer.query.filter_by(shop_id=shop_id).count()

    today = datetime.now().date()

    today_sales = sum(
        inv.total_amount or 0
        for inv in invoices
        if inv.created_at and inv.created_at.date() == today
    )

    low_stock = Product.query.filter(
        Product.shop_id == shop_id,
        Product.stock <= 10
    ).all()

    items = InvoiceItem.query.join(Invoice).filter(Invoice.shop_id == shop_id).all()

    best_products = {}
    best_units = {}
    for item in items:
        product = Product.query.get(item.product_id)
        if product:
            best_products[product.name] = best_products.get(product.name, 0) + (item.quantity or 0)
            best_units[product.name] = normalize_unit(product.unit)

    best_products = sorted(best_products.items(), key=lambda x: x[1], reverse=True)
    # (name, "12.5 kg") - dashboard just prints the text
    best_products = [(n, fmt_qty_unit(q, best_units[n])) for n, q in best_products]

    customers = Customer.query.filter_by(shop_id=shop_id).order_by(
        Customer.total_spent.desc()
    ).limit(5).all()

    top_customers = [(c.name, c.total_spent) for c in customers]

    recent_deletions = AuditLog.query.filter_by(
        shop_id=shop_id,
        action="DELETE"
    ).order_by(
        AuditLog.created_at.desc()
    ).limit(5).all()

    return render_template(
        "dashboard.html",
        today_sales=today_sales,
        total_bills=total_bills,
        total_revenue=total_revenue,
        total_customers=total_customers,
        low_stock=low_stock,
        best_products=best_products,
        top_customers=top_customers,
        remaining_days=remaining_days,
        subscription_warning=subscription_warning,
        plan=(subscription.plan if subscription else None),
        status=(subscription.status if subscription else None),
        recent_deletions=recent_deletions
    )


@billing_bp.route("/sales_chart")
@login_required
def sales_chart():

    shop_id = session["shop_id"]

    items = InvoiceItem.query.join(Invoice).filter(Invoice.shop_id == shop_id).all()

    product_sales = {}
    for item in items:
        product = Product.query.get(item.product_id)
        if product:
            product_sales[product.name] = product_sales.get(product.name, 0) + item.quantity

    product_names = list(product_sales.keys())
    quantities = list(product_sales.values())

    plt.figure(figsize=(8, 5))
    plt.bar(product_names, quantities)
    plt.title("Product Sales")
    plt.xlabel("Products")
    plt.ylabel("Quantity Sold")
    plt.xticks(rotation=30)

    static_folder = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "static",
        "charts"
    )
    os.makedirs(static_folder, exist_ok=True)
    chart_path = os.path.join(static_folder, f"sales_{shop_id}.png")

    plt.tight_layout()
    plt.savefig(chart_path)
    plt.close()

    return send_file(chart_path, mimetype="image/png")