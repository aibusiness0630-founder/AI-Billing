from flask import Flask, render_template, request, redirect, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from reportlab.pdfgen import canvas
import os
import matplotlib.pyplot as plt

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///billing.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    mobile = db.Column(db.String(20))
    product = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    total = db.Column(db.Float)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)


@app.route("/get_customer/<mobile>")
def get_customer(mobile):

    bill = Bill.query.filter_by(mobile=mobile).first()

    if bill and bill.customer_name != "Walk-in Customer":
        return jsonify({
            "customer_name": bill.customer_name
        })

    return jsonify({
        "customer_name": ""
    })

class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(100))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    shop_type = db.Column(db.String(50))

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":

        customer_name = request.form.get("customer_name")

        if not customer_name.strip():
          customer_name = "Walk-in Customer"

        mobile = request.form.get("mobile")

        products = request.form.getlist("product[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("price[]")

        grand_total = 0

        for product, quantity, price in zip(products, quantities, prices):

            if product.strip() == "" or quantity.strip() == "" or price.strip() == "":
                continue

            quantity = int(quantity)
            price = float(price)
            total = quantity * price
            grand_total += total

            new_bill = Bill(
                customer_name=customer_name,
                mobile=mobile,
                product=product,
                quantity=quantity,
                price=price,
                total=total
            )

            db.session.add(new_bill)

            product_data = Product.query.filter_by(product_name=product).first()

            if product_data:

                if product_data.stock < quantity:
                    return f"""
<h2 style='color:red;'>❌ Not enough stock for {product}</h2>
<h3>Available Stock: {product_data.stock}</h3>
<br>
<a href='/'>
    <button>⬅ Back to Billing</button>
</a>
"""

                # Stock reduce
                product_data.stock -= quantity

        db.session.commit()

        shop = Shop.query.first()
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

    product_list = Product.query.all()

    return render_template(
        "index.html",
        product_list=product_list
    )

@app.route("/sales_chart")
def sales_chart():

    bills = Bill.query.all()

    product_names = []
    quantities = []

    for bill in bills:
        product_names.append(bill.product)
        quantities.append(bill.quantity)

    plt.figure(figsize=(8, 5))
    plt.bar(product_names, quantities)
    plt.title("Product Sales")
    plt.xlabel("Products")
    plt.ylabel("Quantity Sold")
    plt.xticks(rotation=30)

    os.makedirs("static", exist_ok=True)

    chart_path = "static/sales_chart.png"
    plt.tight_layout()
    plt.savefig(chart_path)
    plt.close()

    return send_file(chart_path, mimetype="image/png")

         
@app.route("/dashboard")
def dashboard():

    bills = Bill.query.all()

    total_bills = len(bills)
    total_revenue = sum(bill.total for bill in bills)
    total_customers = len(set(bill.mobile for bill in bills))
    today_sales = total_revenue

    low_stock = Product.query.filter(Product.stock <= 10).all()

    best_products = {}

    for bill in bills:
        if bill.product in best_products:
            best_products[bill.product] += bill.quantity
        else:
            best_products[bill.product] = bill.quantity

    best_products = sorted(
        best_products.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return render_template(
        "dashboard.html",
        today_sales=today_sales,
        total_bills=total_bills,
        total_revenue=total_revenue,
        total_customers=total_customers,
        low_stock=low_stock,
        best_products=best_products
    )

@app.route("/add_product", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        product_name = request.form.get("product_name")
        price = float(request.form.get("price"))
        stock = int(request.form.get("stock"))

        new_product = Product(
            product_name=product_name,
            price=price,
            stock=stock
        )

        db.session.add(new_product)
        db.session.commit()

        return redirect("/products")

    return render_template("add_product.html")

@app.route("/products")
def products():
    all_products = Product.query.all()
    return render_template("products.html", products=all_products)

@app.route("/get_price/<int:product_id>")
def get_price(product_id):

    product = Product.query.get_or_404(product_id)

    return jsonify({
        "price": product.price
    })
@app.route("/search_products")
def search_products():

    keyword = request.args.get("q", "")

    products = Product.query.filter(
        Product.product_name.ilike(f"%{keyword}%")
    ).all()

    return jsonify([
        {
            "id": product.id,
            "name": product.product_name,
            "price": product.price
        }
        for product in products
    ])

@app.route("/history")
def history():
    bills = Bill.query.all()
    return render_template("history.html", bills=bills)

@app.route("/shop-settings", methods=["GET", "POST"])
def shop_settings():

    shop = Shop.query.first()

    if request.method == "POST":

        shop_name = request.form.get("shop_name")
        address = request.form.get("address")
        phone = request.form.get("phone")
        shop_type = request.form.get("shop_type")

        if shop:
            shop.shop_name = shop_name
            shop.address = address
            shop.phone = phone
            shop.shop_type = shop_type

        else:
            shop = Shop(
                shop_name=shop_name,
                address=address,
                phone=phone,
                shop_type=shop_type
            )
            db.session.add(shop)

        db.session.commit()

        return redirect("/shop-settings")

    return render_template(
        "shop_settings.html",
        shop=shop
    )

@app.route("/shop", methods=["GET", "POST"])
def shop():
    shop = Shop.query.first()

    if request.method == "POST":
        if shop is None:
            shop = Shop()

        shop.shop_name = request.form.get("shop_name")
        shop.address = request.form.get("address")
        shop.phone = request.form.get("phone")
        shop.shop_type = request.form.get("shop_type")

        db.session.add(shop)
        db.session.commit()

        return redirect("/")

    return render_template("shop.html", shop=shop)

@app.route("/search", methods=["GET", "POST"])
def search():
    bills = []

    if request.method == "POST":
        search_value = request.form.get("search")

        bills = Bill.query.filter(
            (Bill.customer_name.ilike("%" + search_value + "%")) |
            (Bill.mobile.ilike("%" + search_value + "%"))
        ).all()

    return render_template("search.html", bills=bills)

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    bill = Bill.query.get_or_404(id)

    if request.method == "POST":
        bill.customer_name = request.form.get("customer_name")
        bill.mobile = request.form.get("mobile")
        bill.product = request.form.get("product")
        bill.quantity = int(request.form.get("quantity"))
        bill.price = float(request.form.get("price"))
        bill.total = bill.quantity * bill.price

        db.session.commit()
        return redirect("/history")

    return render_template("edit.html", bill=bill)

@app.route("/delete/<int:id>")
def delete(id):
    bill = Bill.query.get_or_404(id)
    db.session.delete(bill)
    db.session.commit()
    return redirect("/history")

@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
def edit_product(id):

    product = Product.query.get_or_404(id)

    if request.method == "POST":
        product.product_name = request.form.get("product_name")
        product.price = float(request.form.get("price"))
        product.stock = int(request.form.get("stock"))

        db.session.commit()
        return redirect("/products")

    return render_template("edit_product.html", product=product)

@app.route("/download_bill/<int:id>")
def download_bill(id):

    bill = Bill.query.get_or_404(id)
    shop = Shop.query.first()

    pdf_name = f"bill_{bill.id}.pdf"

    c = canvas.Canvas(pdf_name)

    # Shop Name
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(300, 800, shop.shop_name if shop else "My Shop")

    # Address
    c.setFont("Helvetica", 11)
    c.drawCentredString(300, 780, shop.address if shop else "")

    # Phone
    c.drawCentredString(
        300,
        765,
        f"Phone : {shop.phone}" if shop else ""
    )

    # Line
    c.line(40, 750, 550, 750)

    # Invoice Details
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 725, f"Invoice No : INV-{bill.id:05d}")
    c.drawString(350, 725, f"Date & time : {datetime.now().strftime('%d-%m-%Y')}")

    # Customer Details
    c.drawString(50, 695, f"Customer : {bill.customer_name}")
    c.drawString(50, 675, f"Mobile : {bill.mobile}")

    # Table Header
    c.line(40, 655, 550, 655)

    c.drawString(50, 635, "Product")
    c.drawString(250, 635, "Qty")
    c.drawString(330, 635, "Price")
    c.drawString(430, 635, "Amount")

    c.line(40, 625, 550, 625)

    # Product Row
    c.setFont("Helvetica", 12)

    c.drawString(50, 600, bill.product)
    c.drawString(260, 600, str(bill.quantity))
    c.drawString(330, 600, f"Rs.{bill.price}")
    c.drawString(430, 600, f"Rs.{bill.total}")

    c.line(40, 580, 550, 580)

    # Grand Total
    c.setFont("Helvetica-Bold", 14)
    c.drawString(330, 555, "Grand Total :")
    c.drawString(455, 555, f"Rs.{bill.total}")

    c.line(40, 535, 550, 535)

    # Footer
    c.setFont("Helvetica", 12)
    c.drawCentredString(300, 500, "Thank You! Visit Again")

    c.save()

    return send_file(pdf_name, as_attachment=True)

@app.route("/delete_product/<int:id>")
def delete_product(id):

    product = Product.query.get_or_404(id)

    db.session.delete(product)
    db.session.commit()

    return redirect("/products")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)