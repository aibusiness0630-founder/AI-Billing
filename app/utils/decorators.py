from flask import session, redirect, render_template
from functools import wraps
from app.models import Subscription


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "shop_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "shop_id" not in session:
            return redirect("/login")

        shop_id = session["shop_id"]

        subscription = Subscription.query.filter_by(shop_id=shop_id).first()

        if not subscription or subscription.plan != "Premium":
            return render_template("upgrade_required.html")

        return f(*args, **kwargs)

    return decorated_function