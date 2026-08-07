from flask import Flask, render_template, request, redirect, jsonify, send_file, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from reportlab.pdfgen import canvas
from io import BytesIO
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shutil
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "AI_BILLING_SECRET_2026"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///billing.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

from datetime import datetime

class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    shop_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    shop_type = db.Column(db.String(50))

    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)

    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"))

class Bill(db.Model):
    __tablename__ = "bill"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    mobile = db.Column(db.String(20))
    product = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    total = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"))    

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    plan = db.Column(db.String(50), default="Monthly")

    start_date = db.Column(
        db.Date,
        default=datetime.utcnow().date
    )

    expiry_date = db.Column(db.Date)

    status = db.Column(
        db.String(20),
        default="Active"
    )

    reminder_sent = db.Column(
        db.Boolean,
        default=False
    )    

from datetime import datetime

def check_subscription(shop_id):

    subscription = Subscription.query.filter_by(shop_id=shop_id).first()

    if not subscription:
        return False, "Subscription Not Found"

    today = datetime.now().date()

    if subscription.expiry_date < today:
        subscription.status = "Expired"
        db.session.commit()
        return False, "Expired"

    subscription.status = "Active"
    db.session.commit()

    return True, "Active"

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        shop = Shop.query.filter_by(username=username).first()

        if shop and check_password_hash(shop.password, password):

            # Subscription Check
            ok, status = check_subscription(shop.id)

            if not ok:
                return "❌ Your subscription has expired. Please renew."

            session["shop_id"] = shop.id
            return redirect("/")

        return "❌ Invalid Username or Password"

    return render_template("login.html")

@app.route("/renew_subscription")
def renew_subscription():

    if "shop_id" not in session:
        return redirect("/login")

    sub = Subscription.query.filter_by(
        shop_id=session["shop_id"]
    ).first()

    if not sub:
        return "❌ Subscription not found"

    from datetime import timedelta

    today = datetime.now().date()

    sub.start_date = today
    sub.expiry_date = today + timedelta(days=30)
    sub.status = "Active"

    db.session.commit()

    return redirect("/dashboard")

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

@app.route("/", methods=["GET", "POST"])
def home():

    if "shop_id" not in session:
        return redirect("/login")


    shop_id = session["shop_id"]


    product_list = Product.query.filter_by(
        shop_id=shop_id
    ).all()



    if request.method == "POST":

        customer_name = request.form.get(
            "customer_name",
            ""
        ).strip()


        if not customer_name:
            customer_name = "Walk-in Customer"


        mobile = request.form.get(
            "mobile",
            ""
        )


        products = request.form.getlist(
            "product[]"
        )

        quantities = request.form.getlist(
            "quantity[]"
        )

        prices = request.form.getlist(
            "price[]"
        )


        grand_total = 0

        bill_items = []



        # Stock check first

        for product, quantity, price in zip(
            products,
            quantities,
            prices
        ):

            if not product or not quantity or not price:
                continue


            quantity = int(quantity)


            product_data = Product.query.filter_by(
                product_name=product,
                shop_id=shop_id
            ).first()


            if product_data and product_data.stock < quantity:

                return f"""
                <h2 style='color:red'>
                ❌ Not enough stock for {product}
                </h2>

                <h3>
                Available Stock: {product_data.stock}
                </h3>

                <a href='/'>
                Back
                </a>
                """


            price = float(price)

            total = quantity * price


            bill_items.append(
                {
                    "product": product,
                    "quantity": quantity,
                    "price": price,
                    "total": total
                }
            )


            grand_total += total



        # Save after stock validation


        for item in bill_items:


            new_bill = Bill(
                customer_name=customer_name,
                mobile=mobile,
                product=item["product"],
                quantity=item["quantity"],
                price=item["price"],
                total=item["total"],
                shop_id=shop_id
            )


            db.session.add(new_bill)



            product_data = Product.query.filter_by(
                product_name=item["product"],
                shop_id=shop_id
            ).first()


            if product_data:

                product_data.stock -= item["quantity"]



        db.session.commit()



        shop = Shop.query.filter_by(
            id=shop_id
        ).first()



        current_time = datetime.now().strftime(
            "%d-%m-%Y %I:%M %p"
        )



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



    return render_template(
        "index.html",
        product_list=product_list
    )

@app.route("/view_subscriptions")
def view_subscriptions():

    data = Subscription.query.all()

    for s in data:
        print(
            s.shop_id,
            s.plan,
            s.start_date,
            s.expiry_date,
            s.status
        )

    return f"Total Subscription : {len(data)}"

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

@app.route("/sales_chart")
def sales_chart():

    if "shop_id" not in session:
        return redirect("/login")


    shop_id = session["shop_id"]


    bills = Bill.query.filter_by(
        shop_id=shop_id
    ).all()


    product_sales = {}


    for bill in bills:

        if bill.product:

            product_sales[bill.product] = (
                product_sales.get(
                    bill.product,
                    0
                )
                +
                (bill.quantity or 0)
            )



    product_names = list(
        product_sales.keys()
    )

    quantities = list(
        product_sales.values()
    )



    plt.figure(
        figsize=(8,5)
    )


    plt.bar(
        product_names,
        quantities
    )


    plt.title(
        "Product Sales"
    )

    plt.xlabel(
        "Products"
    )

    plt.ylabel(
        "Quantity Sold"
    )


    plt.xticks(
        rotation=30
    )


    os.makedirs(
        "static/charts",
        exist_ok=True
    )


    chart_path = (
        f"static/charts/"
        f"sales_{shop_id}.png"
    )


    plt.tight_layout()

    plt.savefig(
        chart_path
    )

    plt.close()


    return send_file(
        chart_path,
        mimetype="image/png"
    )
         
@app.route("/dashboard")
def dashboard():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    # ---------------- Subscription ----------------
    subscription = Subscription.query.filter_by(
        shop_id=shop_id
    ).first()

    remaining_days = None
    subscription_warning = None

    if subscription:
        today = datetime.now().date()

        remaining_days = (
            subscription.expiry_date - today
        ).days

        if remaining_days == 2:
            subscription_warning = "⚠ Your subscription expires in 2 days."

        elif remaining_days == 1:
            subscription_warning = "⚠ Your subscription expires tomorrow."

        elif remaining_days == 0:
            subscription_warning = "⚠ Your subscription expires today."

        elif remaining_days < 0:
            subscription_warning = "❌ Your subscription has expired. Please renew."

    # ---------------- Bills ----------------
    bills = Bill.query.filter_by(
        shop_id=shop_id
    ).all()

    total_bills = len(bills)

    total_revenue = sum(
        bill.total or 0
        for bill in bills
    )

    total_customers = len(
        set(
            bill.mobile
            for bill in bills
            if bill.mobile
        )
    )

    # Today's Sales (temporary)
    today_sales = total_revenue

    # ---------------- Low Stock ----------------
    low_stock = Product.query.filter(
        Product.shop_id == shop_id,
        Product.stock <= 10
    ).all()

    # ---------------- Best Products ----------------
    best_products = {}

    for bill in bills:

        if bill.product:

            best_products[bill.product] = (
                best_products.get(
                    bill.product,
                    0
                )
                +
                (bill.quantity or 0)
            )

    best_products = sorted(
        best_products.items(),
        key=lambda x: x[1],
        reverse=True
    )

    # ---------------- Top Customers ----------------
    top_customers = {}

    for bill in bills:

        if bill.customer_name:

            top_customers[bill.customer_name] = (
                top_customers.get(
                    bill.customer_name,
                    0
                )
                +
                (bill.total or 0)
            )

    top_customers = sorted(
        top_customers.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

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

    plan=subscription.plan if subscription else None,
    status=subscription.status if subscription else None

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
            stock=stock,
            shop_id=session["shop_id"]
        )

        db.session.add(new_product)
        db.session.commit()

        return redirect("/products")

    return render_template("add_product.html")

@app.route("/products")
def products():

    if "shop_id" not in session:
        return redirect("/login")

    all_products = Product.query.filter_by(
        shop_id=session["shop_id"]
    ).order_by(Product.product_name).all()

    return render_template(
        "products.html",
        products=all_products
    )

@app.route("/import_products", methods=["GET", "POST"])
def import_products():

    if request.method == "POST":

        file = request.files.get("file")

        if not file or file.filename == "":
            return "❌ No File Selected"

        try:

            if file.filename.endswith(".csv"):
                df = pd.read_csv(file)

            elif file.filename.endswith(".xlsx"):
                df = pd.read_excel(file)

            else:
                return "❌ Only CSV or Excel Files Supported"

            # Clean column names
            df.columns = df.columns.str.strip()

            # Remove Unnamed columns
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

            # Rename if needed
            df.rename(columns={
                "product Name": "Product Name",
                "product name": "Product Name",
                "PRODUCT NAME": "Product Name"
            }, inplace=True)

            print(df.columns.tolist())

            required_columns = [
                "Product Name",
                "Price",
                "Stock"
            ]

            for column in required_columns:
                if column not in df.columns:
                    return f"❌ Missing Column : {column}"

            # Keep only required columns
            df = df[required_columns]

            # Remove empty rows
            df = df.dropna(subset=required_columns)

            print(df)

            imported_count = 0
            skipped_count = 0

            for _, row in df.iterrows():

                product_name = str(row["Product Name"]).strip()

                existing = Product.query.filter_by(
                    product_name=product_name
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                product = Product(
                    shop_id=session["shop_id"],
                    product_name=product_name,
                    price=float(row["Price"]),
                    stock=int(row["Stock"])
                )

                db.session.add(product)
                imported_count += 1

            db.session.commit()

            return f"""
            ✅ Imported : {imported_count}<br>
            ⚠️ Skipped : {skipped_count}<br><br>
            <a href='/products'>⬅ Back to Products</a>
            """

        except Exception as e:
            return f"❌ Import Error : {str(e)}"

    return render_template("import_products.html")

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
    bills = Bill.query.filter_by(
    shop_id=session["shop_id"]
).all()
    return render_template("history.html", bills=bills)

@app.route("/customers")
def customers():

    if "shop_id" not in session:
        return redirect("/login")


    customers = (
        db.session.query(
            Bill.customer_name,
            Bill.mobile
        )
        .filter(
            Bill.shop_id == session["shop_id"]
        )
        .group_by(
            Bill.mobile
        )
        .all()
    )


    return render_template(
        "customers.html",
        customers=customers
    )



@app.route("/customer/<mobile>")
def customer_profile(mobile):

    if "shop_id" not in session:
        return redirect("/login")


    bills = Bill.query.filter_by(
        mobile=mobile,
        shop_id=session["shop_id"]
    ).all()



    if not bills:
        return "Customer Not Found"



    customer_name = bills[0].customer_name



    total_bills = len(bills)


    total_purchase = sum(
        bill.total or 0
        for bill in bills
    )



    last_purchase = max(
        bills,
        key=lambda x: x.id
    )



    average_bill = round(
        total_purchase / total_bills,
        2
    ) if total_bills else 0



    product_count = {}

    total_items = 0



    for bill in bills:

        qty = bill.quantity or 0

        total_items += qty


        if bill.product:

            product_count[bill.product] = (
                product_count.get(
                    bill.product,
                    0
                )
                +
                qty
            )



    most_product = (
        max(
            product_count,
            key=product_count.get
        )
        if product_count
        else "No Purchase"
    )



    return render_template(
        "customer_profile.html",
        customer_name=customer_name,
        mobile=mobile,
        bills=bills,
        total_bills=total_bills,
        total_purchase=total_purchase,
        last_purchase=last_purchase,
        average_bill=average_bill,
        most_product=most_product,
        total_items=total_items
    )
@app.route("/backup")
def backup_database():

    if "shop_id" not in session:
        return redirect("/login")


    source = "instance/billing.db"


    if not os.path.exists(source):
        return "❌ Database file not found"


    backup_folder = "instance/backups"

    os.makedirs(
        backup_folder,
        exist_ok=True
    )


    backup_name = (
        f"billing_backup_"
        f"{datetime.now().strftime('%d_%m_%Y_%H_%M_%S')}.db"
    )


    destination = os.path.join(
        backup_folder,
        backup_name
    )


    shutil.copy(
        source,
        destination
    )


    return f"✅ Backup Created Successfully : {backup_name}"



@app.route("/restore")
def restore_database():

    if "shop_id" not in session:
        return redirect("/login")


    backup_folder = "instance/backups"


    if not os.path.exists(backup_folder):
        return "❌ No Backup Available"



    backups = sorted(
        os.listdir(backup_folder),
        reverse=True
    )


    if not backups:
        return "❌ No Backup Found"



    latest_backup = os.path.join(
        backup_folder,
        backups[0]
    )


    database = "instance/billing.db"


    shutil.copy(
        latest_backup,
        database
    )


    return "✅ Database Restored Successfully"    



@app.route("/shop-settings", methods=["GET", "POST"])
def shop_settings():

    if "shop_id" not in session:
        return redirect("/login")


    shop = Shop.query.filter_by(
        id=session["shop_id"]
    ).first_or_404()



    if request.method == "POST":

        shop_name = request.form.get("shop_name")
        address = request.form.get("address")
        phone = request.form.get("phone")
        shop_type = request.form.get("shop_type")


        if not shop_name:
            return "Shop name required"



        shop.shop_name = shop_name
        shop.address = address
        shop.phone = phone
        shop.shop_type = shop_type


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

        username = request.form.get("username")
        password = request.form.get("password")

        if username:
            shop.username = username

        if password:
            shop.password = generate_password_hash(password)

        if not shop.shop_name:
            return "Shop name required"

        db.session.add(shop)
        db.session.commit()

        from datetime import timedelta

        subscription = Subscription.query.filter_by(shop_id=shop.id).first()

        if not subscription:
            subscription = Subscription(
                shop_id=shop.id,
                plan="Monthly",
                start_date=datetime.now().date(),
                expiry_date=(datetime.now() + timedelta(days=30)).date(),
                status="Active"
            )

            db.session.add(subscription)
            db.session.commit()

            print("✅ Subscription Created")

        return redirect("/shop")

    return render_template("shop.html", shop=shop)

@app.route("/search", methods=["GET", "POST"])
def search():

    bills = []
    search_value = ""

    if request.method == "POST":

        search_value = request.form.get("search", "").strip()

        if search_value:

            bills = Bill.query.filter(
                (Bill.customer_name.ilike(f"%{search_value}%")) |
                (Bill.mobile.ilike(f"%{search_value}%"))
            ).all()

    return render_template(
        "search.html",
        bills=bills,
        search_value=search_value
    )

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):

    if "shop_id" not in session:
        return redirect("/login")

    bill = Bill.query.filter_by(
        id=id,
        shop_id=session["shop_id"]
    ).first_or_404()


    if request.method == "POST":

        customer_name = request.form.get("customer_name")
        mobile = request.form.get("mobile")
        product = request.form.get("product")

        quantity = request.form.get("quantity")
        price = request.form.get("price")


        if not quantity or not price:
            return "Quantity and Price required"


        quantity = int(quantity)
        price = float(price)


        bill.customer_name = customer_name
        bill.mobile = mobile
        bill.product = product
        bill.quantity = quantity
        bill.price = price
        bill.total = quantity * price


        db.session.commit()

        return redirect("/history")


    return render_template(
        "edit.html",
        bill=bill
    )



@app.route("/delete/<int:id>")
def delete(id):

    if "shop_id" not in session:
        return redirect("/login")


    bill = Bill.query.filter_by(
        id=id,
        shop_id=session["shop_id"]
    ).first_or_404()


    db.session.delete(bill)

    db.session.commit()


    return redirect("/history")



@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
def edit_product(id):

    if "shop_id" not in session:
        return redirect("/login")


    product = Product.query.filter_by(
        id=id,
        shop_id=session["shop_id"]
    ).first_or_404()



    if request.method == "POST":

        product_name = request.form.get("product_name")
        price = request.form.get("price")
        stock = request.form.get("stock")


        if not product_name or not price or not stock:
            return "All fields required"


        product.product_name = product_name
        product.price = float(price)
        product.stock = int(stock)


        db.session.commit()


        return redirect("/products")



    return render_template(
        "edit_product.html",
        product=product
    )

@app.route("/download_bill/<int:id>")
def download_bill(id):

    bill = Bill.query.get_or_404(id)

    if "shop_id" not in session:
        return redirect("/login")

    shop = Shop.query.filter_by(
        id=session["shop_id"]
    ).first()


    # Same invoice products
    bills = Bill.query.filter_by(
        customer_name=bill.customer_name,
        mobile=bill.mobile,
        shop_id=session["shop_id"]
    ).filter(
        Bill.id <= bill.id
    ).all()


    buffer = BytesIO()

    c = canvas.Canvas(buffer)


    shop_name = shop.shop_name if shop else "My Shop"
    address = shop.address if shop else ""
    phone = shop.phone if shop else ""


    # Header

    c.setFont("Helvetica-Bold",22)
    c.drawCentredString(
        300,
        800,
        shop_name
    )


    c.setFont("Helvetica",11)

    c.drawCentredString(
        300,
        780,
        address
    )

    c.drawCentredString(
        300,
        765,
        f"Phone : {phone}"
    )


    c.line(40,750,550,750)


    # Invoice

    c.setFont("Helvetica-Bold",12)

    c.drawString(
        50,
        725,
        f"Invoice No : INV-{bill.id:05d}"
    )

    c.drawString(
        350,
        725,
        datetime.now().strftime("%d-%m-%Y")
    )


    c.drawString(
        50,
        695,
        f"Customer : {bill.customer_name}"
    )

    c.drawString(
        50,
        675,
        f"Mobile : {bill.mobile}"
    )


    # Table

    c.line(40,650,550,650)


    c.drawString(50,630,"Product")
    c.drawString(250,630,"Qty")
    c.drawString(330,630,"Price")
    c.drawString(430,630,"Amount")


    c.line(40,620,550,620)


    y = 595
    grand_total = 0


    c.setFont("Helvetica",12)


    for item in bills:

        c.drawString(
            50,
            y,
            item.product
        )

        c.drawString(
            250,
            y,
            str(item.quantity)
        )

        c.drawString(
            330,
            y,
            f"Rs.{item.price}"
        )

        c.drawString(
            430,
            y,
            f"Rs.{item.total}"
        )


        grand_total += item.total

        y -= 25


    c.line(40,y,550,y)


    c.setFont("Helvetica-Bold",14)

    c.drawString(
        330,
        y-30,
        "Grand Total:"
    )

    c.drawString(
        450,
        y-30,
        f"Rs.{grand_total}"
    )


    c.setFont("Helvetica",12)

    c.drawCentredString(
        300,
        y-80,
        "Thank You! Visit Again"
    )


    c.save()


    buffer.seek(0)


    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{bill.id}.pdf",
        mimetype="application/pdf"
    )

@app.route("/delete_product/<int:id>")
def delete_product(id):

    if "shop_id" not in session:
        return redirect("/login")


    product = Product.query.filter_by(
        id=id,
        shop_id=session["shop_id"]
    ).first_or_404()


    db.session.delete(product)

    db.session.commit()


    return redirect("/products")

    with app.app_context():
       print("Subscriptions:", Subscription.query.all())

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)