from flask import session, redirect, render_template
from functools import wraps
from datetime import datetime
from app.models import Subscription, Shop, SuperAdmin


def _shop_is_approved(shop_id):
    shop = Shop.query.filter_by(id=shop_id).first()

    if not shop:
        return False

    return (shop.approval_status or "APPROVED") == "APPROVED"


def _subscription_is_valid(shop_id):
    sub = Subscription.query.filter_by(shop_id=shop_id).first()

    if not sub:
        return False

    if sub.expiry_date and sub.expiry_date < datetime.now().date():
        return False

    return True


def shop_session_required(f):
    """Logged-in + approved shop. Works even when the plan has expired
    (used by the Subscription page and online payment, so shops can renew)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "shop_id" not in session:
            return redirect("/login")

        if not _shop_is_approved(session["shop_id"]):
            session.clear()
            return redirect("/login")

        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "shop_id" not in session:
            return redirect("/login")

        shop_id = session["shop_id"]

        if not _shop_is_approved(shop_id):
            session.clear()
            return redirect("/login")

        # expired plan -> only the Subscription page is usable
        if not _subscription_is_valid(shop_id):
            return redirect("/subscription")

        return f(*args, **kwargs)
    return decorated_function


def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "shop_id" not in session:
            return redirect("/login")

        shop_id = session["shop_id"]

        if not _shop_is_approved(shop_id):
            session.clear()
            return redirect("/login")

        if not _subscription_is_valid(shop_id):
            return redirect("/subscription")

        subscription = Subscription.query.filter_by(shop_id=shop_id).first()

        if not subscription or subscription.plan != "Premium":
            return render_template("upgrade_required.html")

        return f(*args, **kwargs)

    return decorated_function


def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        admin_id = session.get("superadmin_id")

        if not admin_id:
            return redirect("/superadmin/login")

        if not SuperAdmin.query.filter_by(id=admin_id).first():
            session.clear()
            return redirect("/superadmin/login")

        return f(*args, **kwargs)
    return decorated_function
