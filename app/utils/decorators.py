from flask import session, redirect, render_template
from functools import wraps
from app.models import Subscription, Shop, SuperAdmin


def _shop_is_approved(shop_id):
    shop = Shop.query.filter_by(id=shop_id).first()

    if not shop:
        return False

    return (shop.approval_status or "APPROVED") == "APPROVED"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "shop_id" not in session:
            return redirect("/login")

        if not _shop_is_approved(session["shop_id"]):
            session.clear()
            return redirect("/login")

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
