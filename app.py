from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
    send_file,
    session
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from io import BytesIO

import os
import shutil
import pandas as pd
import dotenv

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

dotenv.load_dotenv()

# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

# IMPORTANT:
# Secret key from environment variable
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "AI_BILLING_SECRET_2026"
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URI",
    "sqlite:///billing.db"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================================================
# DATABASE MODELS
# =========================================================

class Shop(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    shop_name = db.Column(
        db.String(100),
        nullable=False
    )

    address = db.Column(
        db.String(200)
    )

    phone = db.Column(
        db.String(20)
    )

    shop_type = db.Column(
        db.String(50)
    )

    username = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class Product(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_name = db.Column(
        db.String(100),
        nullable=False
    )

    price = db.Column(
        db.Float,
        nullable=False
    )

    stock = db.Column(
        db.Integer,
        nullable=False
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )


class Bill(db.Model):

    __tablename__ = "bill"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    customer_name = db.Column(
        db.String(100)
    )

    mobile = db.Column(
        db.String(20)
    )

    product = db.Column(
        db.String(100)
    )

    quantity = db.Column(
        db.Integer
    )

    price = db.Column(
        db.Float
    )

    total = db.Column(
        db.Float
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )


class Subscription(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    plan = db.Column(
        db.String(50),
        default="Monthly"
    )

    start_date = db.Column(
        db.Date,
        default=lambda: datetime.utcnow().date()
    )

    expiry_date = db.Column(
        db.Date
    )

    status = db.Column(
        db.String(20),
        default="Active"
    )

    reminder_sent = db.Column(
        db.Boolean,
        default=False
    )


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_current_shop_id():

    return session.get("shop_id")

def get_csrf_token():

    if "csrf_token" not in session:
        session["csrf_token"] = os.urandom(32).hex()

    return session["csrf_token"]    


def require_login():

    if "shop_id" not in session:
        return redirect("/login")

    return None


def check_subscription(shop_id):

    subscription = Subscription.query.filter_by(
        shop_id=shop_id
    ).first()

    if not subscription:
        return False, "Subscription Not Found"

    today = datetime.now().date()

    if subscription.expiry_date:

        if subscription.expiry_date < today:

            subscription.status = "Expired"

            db.session.commit()

            return False, "Expired"

    subscription.status = "Active"

    db.session.commit()

    return True, "Active"


def validate_password_strength(password):
    """
    Validate password strength.
    Requirements:
    - At least 8 characters
    - At least 1 uppercase letter
    - At least 1 number
    - At least 1 special character
    """
    
    if len(password) < 8:
        return False, "❌ Password must be at least 8 characters"
    
    if not any(c.isupper() for c in password):
        return False, "❌ Password must contain at least 1 uppercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "❌ Password must contain at least 1 number"
    
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    if not any(c in special_chars for c in password):
        return False, "❌ Password must contain at least 1 special character (!@#$%^&*)"
    
    return True, "✅ Password strength: Strong"


# =========================================================
# RATE LIMITING FOR LOGIN
# =========================================================

LOGIN_ATTEMPTS = {}

def record_failed_login(username):
    """Record failed login attempt."""
    
    client_ip = request.remote_addr
    login_key = f"{username}_{client_ip}"
    
    if login_key not in LOGIN_ATTEMPTS:
        LOGIN_ATTEMPTS[login_key] = {
            "attempts": 0,
            "first_attempt": datetime.now(),
            "blocked_until": None
        }
    
    attempt_data = LOGIN_ATTEMPTS[login_key]
    
    attempt_data["attempts"] += 1
    
    # After 5 failed attempts, block for 15 min
    if attempt_data["attempts"] >= 5:
        
        attempt_data["blocked_until"] = (
            datetime.now() + timedelta(minutes=15)
        )


def reset_login_attempts(username):
    """Reset login attempts after successful login."""
    
    client_ip = request.remote_addr
    login_key = f"{username}_{client_ip}"
    
    if login_key in LOGIN_ATTEMPTS:
        del LOGIN_ATTEMPTS[login_key]


def check_login_rate_limit(username):
    """Check if user is rate limited."""
    
    client_ip = request.remote_addr
    login_key = f"{username}_{client_ip}"
    
    if login_key in LOGIN_ATTEMPTS:
        
        attempt_data = LOGIN_ATTEMPTS[login_key]
        blocked_until = attempt_data.get("blocked_until")
        
        if blocked_until and datetime.now() < blocked_until:
            
            remaining = (blocked_until - datetime.now()).seconds
            
            return False, remaining
    
    return True, 0

# =========================================================
# REGISTER / CREATE NEW SHOP
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        
        # Generate CSRF token for form
        session["csrf_token"] = os.urandom(32).hex()
        
        return render_template(
            "register.html",
            csrf_token=session.get("csrf_token")
        )

    shop_name = request.form.get(
        "shop_name",
        ""
    ).strip()

    address = request.form.get(
        "address",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    shop_type = request.form.get(
        "shop_type",
        ""
    ).strip()

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    # CSRF TOKEN CHECK (SECURITY)
    csrf_token = request.form.get("csrf_token", "")
    
    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if not shop_name:
        return "❌ Shop name is required"

    if not username:
        return "❌ Username is required"

    if not password:
        return "❌ Password is required"

    # NEW: Strong password validation
    is_strong, message = validate_password_strength(password)
    
    if not is_strong:
        return message

    # -----------------------------------------------------
    # CHECK USERNAME
    # -----------------------------------------------------

    existing_shop = Shop.query.filter_by(
        username=username
    ).first()

    if existing_shop:
        return "❌ Username already exists"

    # -----------------------------------------------------
    # CREATE SHOP + SUBSCRIPTION
    # -----------------------------------------------------

    try:

        new_shop = Shop(
            shop_name=shop_name,
            address=address,
            phone=phone,
            shop_type=shop_type,
            username=username,
            password=generate_password_hash(password)
        )

        db.session.add(new_shop)

        # Get new shop ID before commit
        db.session.flush()

        today = datetime.now().date()

        new_subscription = Subscription(
            shop_id=new_shop.id,
            plan="Basic",
            start_date=today,
            expiry_date=today + timedelta(days=30),
            status="Active",
            reminder_sent=False
        )

        db.session.add(new_subscription)

        db.session.commit()

        # -------------------------------------------------
        # AUTO LOGIN
        # -------------------------------------------------

        session.clear()

        session["shop_id"] = new_shop.id

        return redirect("/")

    except Exception as e:

        db.session.rollback()

        return f"❌ Registration failed: {str(e)}"

# =========================================================
# LOGIN - WITH RATE LIMITING & CSRF
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        
        # Generate CSRF token for form
        session["csrf_token"] = os.urandom(32).hex()
        
        return render_template(
            "login.html",
            csrf_token=session.get("csrf_token")
        )

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    # CSRF TOKEN CHECK (SECURITY)
    csrf_token = request.form.get("csrf_token", "")
    
    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    # RATE LIMITING CHECK
    is_allowed, remaining = check_login_rate_limit(username)
    
    if not is_allowed:
        
        return f"""
        <h2 style='color: red; text-align: center;'>
        ❌ Too many login attempts!
        </h2>
        <p style='text-align: center;'>
        Try again in {remaining} seconds.
        </p>
        <a href='/login' style='text-align: center; display: block;'>
        Back to Login
        </a>
        """, 429

    # Try login
    shop = Shop.query.filter_by(
        username=username
    ).first()

    if shop and check_password_hash(
        shop.password,
        password
    ):

        ok, status = check_subscription(
            shop.id
        )

        if not ok:

            return (
                "❌ Your subscription has expired. "
                "Please renew."
            )

        # Clear old session before creating new login session
        session.clear()

        session["shop_id"] = shop.id
        
        session["csrf_token"] = os.urandom(32).hex()

        # RESET rate limit on successful login
        reset_login_attempts(username)

        return redirect("/")

    # RECORD failed attempt (RATE LIMIT)
    record_failed_login(username)

    return "❌ Invalid Username or Password"


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# =========================================================
# SUBSCRIPTION
# =========================================================

@app.route("/subscription")
def subscription():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    subscription = Subscription.query.filter_by(
        shop_id=shop_id
    ).first()

    if not subscription:
        return "Subscription not found"

    today = datetime.now().date()

    if subscription.expiry_date:

        remaining_days = (
            subscription.expiry_date - today
        ).days

    else:

        remaining_days = 0

    if remaining_days < 0:

        subscription.status = "Expired"

        db.session.commit()

    return render_template(
        "subscription.html",
        subscription=subscription,
        remaining_days=max(
            remaining_days,
            0
        )
    )


@app.route("/select_plan", methods=["POST"])
def select_plan():

    if "shop_id" not in session:
        return redirect("/login")

    csrf_token = request.form.get("csrf_token", "")

    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    shop_id = session["shop_id"]

    selected_plan = request.form.get(
        "plan"
    )

    plan_prices = {
        "Basic": 499,
        "Premium": 999
    }

    if selected_plan not in plan_prices:

        return redirect("/subscription")

    subscription = Subscription.query.filter_by(
        shop_id=shop_id
    ).first()

    if not subscription:
        return "Subscription not found"

    subscription.plan = selected_plan

    db.session.commit()

    return redirect("/subscription")

@app.route("/renew_subscription", methods=["POST"])
def renew_subscription():

    if "shop_id" not in session:
        return redirect("/login")

    csrf_token = request.form.get("csrf_token", "")

    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    shop_id = session["shop_id"]

    subscription = Subscription.query.filter_by(
        shop_id=shop_id
    ).first()

    if not subscription:
        return "❌ Subscription not found"

    today = datetime.now().date()

    subscription.start_date = today

    subscription.expiry_date = (
        today + timedelta(days=30)
    )

    subscription.status = "Active"

    subscription.reminder_sent = False

    db.session.commit()

    return redirect("/dashboard")


# =========================================================
# CUSTOMER AUTO-FILL
# =========================================================

@app.route("/get_customer/<mobile>")
def get_customer(mobile):

    if "shop_id" not in session:
        return jsonify({
            "customer_name": ""
        }), 401

    shop_id = session["shop_id"]

    bill = Bill.query.filter_by(
        mobile=mobile,
        shop_id=shop_id
    ).order_by(
        Bill.id.desc()
    ).first()

    if bill and bill.customer_name != "Walk-in Customer":

        return jsonify({
            "customer_name": bill.customer_name
        })

    return jsonify({
        "customer_name": ""
    })


# =========================================================
# MAIN BILLING PAGE
# =========================================================

@app.route("/", methods=["GET", "POST"])
def home():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    product_list = Product.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Product.product_name
    ).all()

    if request.method == "POST":

        csrf_token = request.form.get(
            "csrf_token",
            ""
        )

        if csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        customer_name = request.form.get(
            "customer_name",
            ""
        ).strip()

        if not customer_name:
            customer_name = "Walk-in Customer"

        mobile = request.form.get(
            "mobile",
            ""
        ).strip()

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

        # ---------------------------------------------
        # VALIDATE BILL ITEMS
        # ---------------------------------------------

        for product, quantity, price in zip(
            products,
            quantities,
            prices
        ):

            if not product or not quantity:
                continue

            try:

                quantity = int(quantity)

            except ValueError:

                return "❌ Invalid quantity"

            if quantity <= 0:

                return "❌ Quantity must be greater than 0"

            # IMPORTANT:
            # Never trust price coming from browser.
            # Get the actual product from this shop.

            product_data = Product.query.filter_by(
                product_name=product,
                shop_id=shop_id
            ).first()

            if not product_data:

                return (
                    f"❌ Product not found: "
                    f"{product}"
                )

            if product_data.stock < quantity:

                return (
                    f"❌ Not enough stock for "
                    f"{product}. "
                    f"Available Stock: "
                    f"{product_data.stock}"
                )

            actual_price = float(
                product_data.price
            )

            total = quantity * actual_price

            bill_items.append({
                "product": product_data.product_name,
                "quantity": quantity,
                "price": actual_price,
                "total": total
            })

            grand_total += total

        if not bill_items:

            return "❌ Please add at least one product"

        # ---------------------------------------------
        # SAVE BILL
        # ---------------------------------------------

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

                product_data.stock -= (
                    item["quantity"]
                )

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
            products=[
                item["product"]
                for item in bill_items
            ],
            quantities=[
                item["quantity"]
                for item in bill_items
            ],
            prices=[
                item["price"]
                for item in bill_items
            ],
            grand_total=grand_total,
            current_time=current_time
        )

    # IMPORTANT:
    # Do NOT generate a new token here.
    csrf_token = get_csrf_token()

    return render_template(
        "index.html",
        product_list=product_list,
        csrf_token=csrf_token
    )
    
# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    # -----------------------------------------------------
    # SUBSCRIPTION
    # -----------------------------------------------------

    subscription = Subscription.query.filter_by(
        shop_id=shop_id
    ).first()

    remaining_days = None
    subscription_warning = None

    if subscription:

        today = datetime.now().date()

        if subscription.expiry_date:

            remaining_days = (
                subscription.expiry_date - today
            ).days

            if remaining_days == 2:

                subscription_warning = (
                    "⚠ Your subscription expires in 2 days."
                )

            elif remaining_days == 1:

                subscription_warning = (
                    "⚠ Your subscription expires tomorrow."
                )

            elif remaining_days == 0:

                subscription_warning = (
                    "⚠ Your subscription expires today."
                )

            elif remaining_days < 0:

                subscription_warning = (
                    "❌ Your subscription has expired. "
                    "Please renew."
                )

    # -----------------------------------------------------
    # SHOP-SPECIFIC BILLS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # TODAY'S SALES
    # -----------------------------------------------------

    today = datetime.now().date()

    today_sales = sum(
        bill.total or 0
        for bill in bills
        if bill.created_at
        and bill.created_at.date() == today
    )

    # -----------------------------------------------------
    # LOW STOCK
    # -----------------------------------------------------

    low_stock = Product.query.filter(
        Product.shop_id == shop_id,
        Product.stock <= 10
    ).all()

    # -----------------------------------------------------
    # BEST PRODUCTS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # TOP CUSTOMERS
    # -----------------------------------------------------

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

        plan=(
            subscription.plan
            if subscription
            else None
        ),

        status=(
            subscription.status
            if subscription
            else None
        )
    )


# =========================================================
# SALES CHART
# =========================================================

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
        figsize=(8, 5)
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


# =========================================================
# PRODUCTS
# =========================================================

@app.route("/add_product", methods=["GET", "POST"])
def add_product():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    if request.method == "POST":

        csrf_token = request.form.get("csrf_token", "")

        if csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        product_name = request.form.get(
            "product_name",
            ""
        ).strip()

        price = request.form.get("price")
        stock = request.form.get("stock")

        if not product_name or not price or not stock:
            return "❌ All fields are required"

        try:
            price = float(price)
            stock = int(stock)

        except ValueError:
            return "❌ Invalid price or stock"

        if price < 0:
            return "❌ Price cannot be negative"

        if stock < 0:
            return "❌ Stock cannot be negative"

        existing = Product.query.filter_by(
            product_name=product_name,
            shop_id=shop_id
        ).first()

        if existing:
            return "❌ Product already exists"

        new_product = Product(
            product_name=product_name,
            price=price,
            stock=stock,
            shop_id=shop_id
        )

        db.session.add(new_product)
        db.session.commit()

        return redirect("/products")

    csrf_token = get_csrf_token()

    return render_template(
        "add_product.html",
        csrf_token=csrf_token
    )


@app.route("/products")
def products():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    all_products = Product.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Product.product_name
    ).all()

    return render_template(
        "products.html",
        products=all_products
    )


# =========================================================
# IMPORT PRODUCTS
# =========================================================

@app.route("/import_products", methods=["GET", "POST"])
def import_products():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    if request.method == "POST":

        # CSRF TOKEN CHECK (SECURITY)
        csrf_token = request.form.get("csrf_token", "")
        
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        file = request.files.get(
            "file"
        )

        if not file or file.filename == "":

            return "❌ No File Selected"

        try:

            if file.filename.endswith(".csv"):

                df = pd.read_csv(file)

            elif file.filename.endswith(".xlsx"):

                df = pd.read_excel(file)

            else:

                return (
                    "❌ Only CSV or Excel "
                    "Files Supported"
                )

            df.columns = (
                df.columns
                .str.strip()
            )

            df = df.loc[
                :,
                ~df.columns.str.contains(
                    "^Unnamed"
                )
            ]

            df.rename(
                columns={
                    "product Name": "Product Name",
                    "product name": "Product Name",
                    "PRODUCT NAME": "Product Name"
                },
                inplace=True
            )

            required_columns = [
                "Product Name",
                "Price",
                "Stock"
            ]

            for column in required_columns:

                if column not in df.columns:

                    return (
                        f"❌ Missing Column : "
                        f"{column}"
                    )

            df = df[
                required_columns
            ]

            df = df.dropna(
                subset=required_columns
            )

            imported_count = 0
            skipped_count = 0

            for _, row in df.iterrows():

                product_name = str(
                    row["Product Name"]
                ).strip()

                # IMPORTANT:
                # Duplicate check is shop-specific.

                existing = Product.query.filter_by(
                    product_name=product_name,
                    shop_id=shop_id
                ).first()

                if existing:

                    skipped_count += 1

                    continue

                product = Product(
                    shop_id=shop_id,
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
            <a href='/products'>
            ⬅ Back to Products
            </a>
            """

        except Exception as e:

            db.session.rollback()

            return (
                f"❌ Import Error : {str(e)}"
            )

    # Generate CSRF token for form
    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "import_products.html",
        csrf_token=session.get("csrf_token")
    )


# =========================================================
# GET PRODUCT PRICE
# =========================================================

@app.route("/get_price/<int:product_id>")
def get_price(product_id):

    if "shop_id" not in session:
        return jsonify({
            "error": "Unauthorized"
        }), 401

    product = Product.query.filter_by(
        id=product_id,
        shop_id=session["shop_id"]
    ).first_or_404()

    return jsonify({
        "price": product.price
    })


# =========================================================
# SEARCH PRODUCTS
# =========================================================

@app.route("/search_products")
def search_products():

    if "shop_id" not in session:
        return jsonify({
            "error": "Unauthorized"
        }), 401

    shop_id = session["shop_id"]

    keyword = request.args.get(
        "q",
        ""
    ).strip()

    products = Product.query.filter(
        Product.shop_id == shop_id,
        Product.product_name.ilike(
            f"%{keyword}%"
        )
    ).all()

    return jsonify([
        {
            "id": product.id,
            "name": product.product_name,
            "price": product.price
        }

        for product in products
    ])


# =========================================================
# BILL HISTORY
# =========================================================

@app.route("/history")
def history():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    bills = Bill.query.filter_by(
        shop_id=shop_id
    ).order_by(
        Bill.id.desc()
    ).all()

    return render_template(
        "history.html",
        bills=bills
    )


# =========================================================
# CUSTOMERS
# =========================================================

@app.route("/customers")
def customers():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    customers = (
        db.session.query(
            Bill.customer_name,
            Bill.mobile
        )
        .filter(
            Bill.shop_id == shop_id
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


# =========================================================
# CUSTOMER PROFILE
# =========================================================

@app.route("/customer/<mobile>")
def customer_profile(mobile):

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    bills = Bill.query.filter_by(
        mobile=mobile,
        shop_id=shop_id
    ).order_by(
        Bill.id.desc()
    ).all()

    if not bills:

        return "Customer Not Found"

    customer_name = bills[0].customer_name

    total_bills = len(bills)

    total_purchase = sum(
        bill.total or 0
        for bill in bills
    )

    last_purchase = bills[0]

    average_bill = (
        round(
            total_purchase / total_bills,
            2
        )
        if total_bills
        else 0
    )

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


# =========================================================
# SEARCH BILLS
# =========================================================

@app.route("/search", methods=["GET", "POST"])
def search():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    bills = []

    search_value = ""

    if request.method == "POST":

        search_value = request.form.get(
            "search",
            ""
        ).strip()

        if search_value:

            bills = Bill.query.filter(
                Bill.shop_id == shop_id,
                (
                    Bill.customer_name.ilike(
                        f"%{search_value}%"
                    )
                    |
                    Bill.mobile.ilike(
                        f"%{search_value}%"
                    )
                )
            ).order_by(
                Bill.id.desc()
            ).all()

    return render_template(
        "search.html",
        bills=bills,
        search_value=search_value
    )


# =========================================================
# EDIT BILL
# =========================================================

@app.route(
    "/edit/<int:id>",
    methods=["GET", "POST"]
)
def edit(id):

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    # IMPORTANT:
    # Bill ID + Shop ID together.

    bill = Bill.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    if request.method == "POST":

        # CSRF TOKEN CHECK (SECURITY)
        csrf_token = request.form.get("csrf_token", "")
        
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        customer_name = request.form.get(
            "customer_name"
        )

        mobile = request.form.get(
            "mobile"
        )

        product = request.form.get(
            "product"
        )

        quantity = request.form.get(
            "quantity"
        )

        price = request.form.get(
            "price"
        )

        if not quantity or not price:

            return (
                "Quantity and Price required"
            )

        try:

            quantity = int(quantity)
            price = float(price)

        except ValueError:

            return (
                "❌ Invalid quantity or price"
            )

        if quantity <= 0:

            return (
                "❌ Quantity must be greater than 0"
            )

        bill.customer_name = (
            customer_name
        )

        bill.mobile = mobile

        bill.product = product

        bill.quantity = quantity

        bill.price = price

        bill.total = quantity * price

        db.session.commit()

        return redirect("/history")

    # Generate CSRF token for form
    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "edit.html",
        bill=bill,
        csrf_token=session.get("csrf_token")
    )


# =========================================================
# DELETE BILL
# =========================================================

@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):

    if "shop_id" not in session:
        return redirect("/login")

    csrf_token = request.form.get("csrf_token", "")

    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    shop_id = session["shop_id"]

    bill = Bill.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    db.session.delete(bill)
    db.session.commit()

    return redirect("/history")


# =========================================================
# EDIT PRODUCT
# =========================================================

@app.route(
    "/edit_product/<int:id>",
    methods=["GET", "POST"]
)
def edit_product(id):

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    product = Product.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    if request.method == "POST":

        # CSRF TOKEN CHECK (SECURITY)
        csrf_token = request.form.get("csrf_token", "")
        
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        product_name = request.form.get(
            "product_name"
        )

        price = request.form.get(
            "price"
        )

        stock = request.form.get(
            "stock"
        )

        if not product_name or not price or not stock:

            return "All fields required"

        try:

            price = float(price)
            stock = int(stock)

        except ValueError:

            return "❌ Invalid price or stock"

        product.product_name = product_name
        product.price = price
        product.stock = stock

        db.session.commit()

        return redirect("/products")

    # Generate CSRF token for form
    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "edit_product.html",
        product=product,
        csrf_token=session.get("csrf_token")
    )


# =========================================================
# DELETE PRODUCT
# =========================================================

@app.route("/delete_product/<int:id>", methods=["POST"])
def delete_product(id):

    if "shop_id" not in session:
        return redirect("/login")

    csrf_token = request.form.get("csrf_token", "")

    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    shop_id = session["shop_id"]

    product = Product.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    db.session.delete(product)

    db.session.commit()

    return redirect("/products")

# =========================================================
# DOWNLOAD BILL PDF
# =========================================================

@app.route("/download_bill/<int:id>")
def download_bill(id):

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    # IMPORTANT:
    # Foreign-shop bill cannot be accessed.

    bill = Bill.query.filter_by(
        id=id,
        shop_id=shop_id
    ).first_or_404()

    shop = Shop.query.filter_by(
        id=shop_id
    ).first_or_404()

    # Same customer bills from SAME SHOP only.

    bills = Bill.query.filter(
        Bill.customer_name == bill.customer_name,
        Bill.mobile == bill.mobile,
        Bill.shop_id == shop_id,
        Bill.id <= bill.id
    ).order_by(
        Bill.id.asc()
    ).all()

    buffer = BytesIO()

    c = canvas.Canvas(buffer)

    shop_name = (
        shop.shop_name
        if shop
        else "My Shop"
    )

    address = (
        shop.address
        if shop
        else ""
    )

    phone = (
        shop.phone
        if shop
        else ""
    )

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------

    c.setFont(
        "Helvetica-Bold",
        22
    )

    c.drawCentredString(
        300,
        800,
        shop_name
    )

    c.setFont(
        "Helvetica",
        11
    )

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

    c.line(
        40,
        750,
        550,
        750
    )

    # -----------------------------------------------------
    # INVOICE
    # -----------------------------------------------------

    c.setFont(
        "Helvetica-Bold",
        12
    )

    c.drawString(
        50,
        725,
        f"Invoice No : INV-{bill.id:05d}"
    )

    c.drawString(
        350,
        725,
        datetime.now().strftime(
            "%d-%m-%Y"
        )
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

    # -----------------------------------------------------
    # TABLE
    # -----------------------------------------------------

    c.line(
        40,
        650,
        550,
        650
    )

    c.drawString(
        50,
        630,
        "Product"
    )

    c.drawString(
        250,
        630,
        "Qty"
    )

    c.drawString(
        330,
        630,
        "Price"
    )

    c.drawString(
        430,
        630,
        "Amount"
    )

    c.line(
        40,
        620,
        550,
        620
    )

    y = 595

    grand_total = 0

    c.setFont(
        "Helvetica",
        12
    )

    for item in bills:

        c.drawString(
            50,
            y,
            item.product or ""
        )

        c.drawString(
            250,
            y,
            str(
                item.quantity or 0
            )
        )

        c.drawString(
            330,
            y,
            f"Rs.{item.price or 0:.2f}"
        )

        c.drawString(
            430,
            y,
            f"Rs.{item.total or 0:.2f}"
        )

        grand_total += (
            item.total or 0
        )

        y -= 25

    c.line(
        40,
        y,
        550,
        y
    )

    c.setFont(
        "Helvetica-Bold",
        14
    )

    c.drawString(
        330,
        y - 30,
        "Grand Total:"
    )

    c.drawString(
        450,
        y - 30,
        f"Rs.{grand_total:.2f}"
    )

    c.setFont(
        "Helvetica",
        12
    )

    c.drawCentredString(
        300,
        y - 80,
        "Thank You! Visit Again"
    )

    c.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=(
            f"invoice_{bill.id}.pdf"
        ),
        mimetype="application/pdf"
    )


# =========================================================
# SHOP SETTINGS
# =========================================================

@app.route(
    "/shop-settings",
    methods=["GET", "POST"]
)
def shop_settings():

    if "shop_id" not in session:
        return redirect("/login")

    shop = Shop.query.filter_by(
        id=session["shop_id"]
    ).first_or_404()

    if request.method == "POST":

        # CSRF TOKEN CHECK (SECURITY)
        csrf_token = request.form.get("csrf_token", "")
        
        if not csrf_token or csrf_token != session.get("csrf_token"):
            return "❌ CSRF Token Invalid. Please try again."

        shop_name = request.form.get(
            "shop_name"
        )

        address = request.form.get(
            "address"
        )

        phone = request.form.get(
            "phone"
        )

        shop_type = request.form.get(
            "shop_type"
        )

        if not shop_name:

            return "Shop name required"

        shop.shop_name = shop_name

        shop.address = address

        shop.phone = phone

        shop.shop_type = shop_type

        db.session.commit()

        return redirect(
            "/shop-settings"
        )

    # Generate CSRF token for form
    session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "shop_settings.html",
        shop=shop,
        csrf_token=session.get("csrf_token")
    )


# =========================================================
# SHOP SETUP
# =========================================================

@app.route(
    "/shop",
    methods=["GET", "POST"]
)
def shop():

    if request.method == "GET":

        if "shop_id" in session:

            shop = Shop.query.filter_by(
                id=session["shop_id"]
            ).first()

            # Generate CSRF token for form
            session["csrf_token"] = os.urandom(32).hex()

            return render_template(
                "shop.html",
                shop=shop,
                csrf_token=session.get("csrf_token")
            )

        # Generate CSRF token for form
        session["csrf_token"] = os.urandom(32).hex()

        return render_template(
            "shop.html",
            shop=None,
            csrf_token=session.get("csrf_token")
        )

    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

    shop_id = session.get(
        "shop_id"
    )

    if shop_id:

        shop = Shop.query.filter_by(
            id=shop_id
        ).first_or_404()

    else:

        shop = None

    shop_name = request.form.get(
        "shop_name"
    )

    address = request.form.get(
        "address"
    )

    phone = request.form.get(
        "phone"
    )

    shop_type = request.form.get(
        "shop_type"
    )

    username = request.form.get(
        "username"
    )

    password = request.form.get(
        "password"
    )

    if not shop_name:

        return "Shop name required"

    # CSRF TOKEN CHECK (SECURITY)
    csrf_token = request.form.get("csrf_token", "")
    
    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    # -----------------------------------------------------
    # CREATE NEW SHOP
    # -----------------------------------------------------

    if shop is None:

        if not username or not password:

            return (
                "Username and Password "
                "required for new shop"
            )

        existing_username = Shop.query.filter_by(
            username=username
        ).first()

        if existing_username:

            return (
                "❌ Username already exists"
            )

        shop = Shop(
            shop_name=shop_name,
            address=address,
            phone=phone,
            shop_type=shop_type,
            username=username,
            password=generate_password_hash(
                password
            )
        )

        db.session.add(shop)

        db.session.commit()

        subscription = Subscription(
            shop_id=shop.id,
            plan="Monthly",
            start_date=datetime.now().date(),
            expiry_date=(
                datetime.now()
                + timedelta(days=30)
            ).date(),
            status="Active"
        )

        db.session.add(
            subscription
        )

        db.session.commit()

        session.clear()

        session["shop_id"] = shop.id

        return redirect("/")

    # -----------------------------------------------------
    # UPDATE CURRENT SHOP
    # -----------------------------------------------------

    shop.shop_name = shop_name

    shop.address = address

    shop.phone = phone

    shop.shop_type = shop_type

    if username:

        existing_username = Shop.query.filter(
            Shop.username == username,
            Shop.id != shop.id
        ).first()

        if existing_username:

            return (
                "❌ Username already exists"
            )

        shop.username = username

    if password:

        shop.password = (
            generate_password_hash(
                password
            )
        )

    db.session.commit()

    return redirect("/shop")


# =========================================================
# VIEW SUBSCRIPTIONS
# =========================================================

@app.route("/view_subscriptions")
def view_subscriptions():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    subscription = Subscription.query.filter_by(
        shop_id=shop_id
    ).first()

    if not subscription:

        return "Subscription not found"

    return f"""
    Shop ID : {subscription.shop_id}<br>
    Plan : {subscription.plan}<br>
    Start Date : {subscription.start_date}<br>
    Expiry Date : {subscription.expiry_date}<br>
    Status : {subscription.status}
    """


# =========================================================
# DATABASE BACKUP - PER SHOP
# =========================================================

@app.route("/backup")
def backup_database():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    # Get shop name
    shop = Shop.query.filter_by(
        id=shop_id
    ).first()

    shop_name = (
        shop.shop_name.replace(" ", "_")
        if shop
        else f"shop_{shop_id}"
    )

    # Create backup for THIS SHOP ONLY
    source = "instance/billing.db"

    if not os.path.exists(source):
        return "❌ Database file not found"

    backup_folder = f"instance/backups/shop_{shop_id}"

    os.makedirs(
        backup_folder,
        exist_ok=True
    )

    backup_name = (
        f"{shop_name}_backup_"
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

    return (
        "✅ Backup Created Successfully<br>"
        f"File: {backup_name}<br>"
        f"Location: {backup_folder}"
    )


# =========================================================
# DATABASE RESTORE - DISABLED FOR SHOPS
# =========================================================

@app.route("/restore")
def restore_database():

    if "shop_id" not in session:
        return redirect("/login")

    return (
        "⚠️ Database restore is disabled for "
        "normal shop users. Use an admin-only "
        "restore process."
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

if __name__ == "__main__":

    with app.app_context():

        db.create_all()

    app.run(
        debug=True
    )