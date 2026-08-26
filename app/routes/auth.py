from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from datetime import datetime, timedelta
import os

from app import db
from app.models import Shop, Subscription

auth_bp = Blueprint('auth', __name__)


def validate_password_strength(password):
    
    if len(password) < 8:
        return False, "❌ Password must be at least 8 characters"
    
    if not any(c.isupper() for c in password):
        return False, "❌ Password must contain at least 1 uppercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "❌ Password must contain at least 1 number"
    
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    if not any(c in special_chars for c in password):
        return False, "❌ Password must contain at least 1 special character (!@#$%^&*)"
    
    return True, "✅ Strong"


def check_subscription(shop_id):
    
    subscription = Subscription.query.filter_by(shop_id=shop_id).first()
    
    if not subscription:
        return False, "Subscription Not Found"
    
    today = datetime.now().date()
    
    if subscription.expiry_date and subscription.expiry_date < today:
        subscription.status = "Expired"
        db.session.commit()
        return False, "Expired"
    
    subscription.status = "Active"
    db.session.commit()
    
    return True, "Active"


LOGIN_ATTEMPTS = {}


def record_failed_login(username):
    
    client_ip = request.remote_addr
    login_key = f"{username}_{client_ip}"
    
    if login_key not in LOGIN_ATTEMPTS:
        LOGIN_ATTEMPTS[login_key] = {
            "attempts": 0,
            "blocked_until": None
        }
    
    LOGIN_ATTEMPTS[login_key]["attempts"] += 1
    
    if LOGIN_ATTEMPTS[login_key]["attempts"] >= 5:
        LOGIN_ATTEMPTS[login_key]["blocked_until"] = (
            datetime.now() + timedelta(minutes=15)
        )


def reset_login_attempts(username):
    
    client_ip = request.remote_addr
    login_key = f"{username}_{client_ip}"
    
    if login_key in LOGIN_ATTEMPTS:
        del LOGIN_ATTEMPTS[login_key]


def check_login_rate_limit(username):
    
    client_ip = request.remote_addr
    login_key = f"{username}_{client_ip}"
    
    if login_key in LOGIN_ATTEMPTS:
        
        blocked_until = LOGIN_ATTEMPTS[login_key].get("blocked_until")
        
        if blocked_until and datetime.now() < blocked_until:
            remaining = (blocked_until - datetime.now()).seconds
            return False, remaining
    
    return True, 0


@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        session["csrf_token"] = os.urandom(32).hex()
        return render_template(
            "register.html",
            csrf_token=session.get("csrf_token")
        )

    shop_name = request.form.get("shop_name", "").strip()
    address = request.form.get("address", "").strip()
    phone = request.form.get("phone", "").strip()
    shop_type = request.form.get("shop_type", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    csrf_token = request.form.get("csrf_token", "")
    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    if not shop_name:
        return "❌ Shop name is required"
    if not username:
        return "❌ Username is required"
    if not password:
        return "❌ Password is required"

    is_strong, message = validate_password_strength(password)
    if not is_strong:
        return message

    existing_shop = Shop.query.filter_by(username=username).first()
    if existing_shop:
        return "❌ Username already exists"

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

        session.clear()
        session["shop_id"] = new_shop.id

        return redirect("/")

    except Exception as e:
        db.session.rollback()
        return f"❌ Registration failed: {str(e)}"


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        session["csrf_token"] = os.urandom(32).hex()
        return render_template(
            "login.html",
            csrf_token=session.get("csrf_token")
        )

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    csrf_token = request.form.get("csrf_token", "")
    if not csrf_token or csrf_token != session.get("csrf_token"):
        return "❌ CSRF Token Invalid. Please try again."

    is_allowed, remaining = check_login_rate_limit(username)
    if not is_allowed:
        return f"""
        <h2 style='color: red; text-align: center;'>
        ❌ Too many login attempts!
        </h2>
        <p style='text-align: center;'>
        Try again in {remaining} seconds.
        </p>
        <a href='/login'>Back to Login</a>
        """, 429

    shop = Shop.query.filter_by(username=username).first()

    if shop and check_password_hash(shop.password, password):

        ok, status = check_subscription(shop.id)

        if not ok:
            return "❌ Your subscription has expired. Please renew."

        session.clear()
        session["shop_id"] = shop.id
        session["csrf_token"] = os.urandom(32).hex()

        reset_login_attempts(username)

        return redirect("/")

    record_failed_login(username)
    return "❌ Invalid Username or Password"


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")