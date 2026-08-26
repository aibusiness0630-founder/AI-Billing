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
from app.models import Product, Customer, Invoice, InvoiceItem, Subscription
from app.utils.decorators import login_required

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

        products = request.form.getlist("product[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("price[]")

        grand_total = 0
        bill_items = []

        for product, quantity, price in zip(products, quantities, prices):

            if not product or not quantity or not price:
                continue

            try:
                quantity = int(quantity)
                price = float(price)
            except ValueError:
                return "❌ Invalid quantity or price"

            if quantity <= 0:
                return "❌ Quantity must be greater than 0"

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

            if product_data.stock < quantity:
                return f"""
                <h2 style='color:red'>❌ Not enough stock for {product}</h2>
                <h3>Available Stock: {product_data.stock}</h3>
                <a href='/'>Back</a>
                """

            total = quantity * price

            bill_items.append({
                "product_id": product_data.id,
                "product": product,
                "quantity": quantity,
                "price": price,
                "total": total
            })

            grand_total += total

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
            subtotal=grand_total,
            total_amount=grand_total,
            payment_status="PAID"
        )

        db.session.add(new_invoice)
        db.session.flush()

        for item in bill_items:

            invoice_item = InvoiceItem(
                invoice_id=new_invoice.id,
                product_id=item["product_id"],
                quantity=item["quantity"],
                price=item["price"],
                total=item["total"]
            )

            db.session.add(invoice_item)

            product_data = Product.query.get(item["product_id"])
            if product_data:
                product_data.stock -= item["quantity"]

        db.session.commit()

        from app.models import Shop
        shop = Shop.query.filter_by(id=shop_id).first()

        current_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")

        return render_template(
            "bill.html",
            shop=shop,
            customer_name=customer_name,
            mobile=mobile,
            products=products,
            quantities=quantities,
            prices=prices,
            grand_total=grand_total,
            current_time=current_time
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

    # Query invoice items directly
    items = InvoiceItem.query.join(Invoice).filter(Invoice.shop_id == shop_id).all()

    best_products = {}
    for item in items:
        product = Product.query.get(item.product_id)
        if product:
            best_products[product.name] = best_products.get(product.name, 0) + item.quantity

    best_products = sorted(best_products.items(), key=lambda x: x[1], reverse=True)

    customers = Customer.query.filter_by(shop_id=shop_id).order_by(
        Customer.total_spent.desc()
    ).limit(5).all()

    top_customers = [(c.name, c.total_spent) for c in customers]

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
        status=(subscription.status if subscription else None)
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