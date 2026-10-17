from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    session
)

from datetime import datetime, timedelta

from app import db
from app.models import Subscription

subscription_bp = Blueprint('subscription', __name__)


@subscription_bp.route("/subscription")
def subscription():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    sub = Subscription.query.filter_by(shop_id=shop_id).first()

    if not sub:
        return "Subscription not found"

    today = datetime.now().date()

    if sub.expiry_date:
        remaining_days = (sub.expiry_date - today).days
    else:
        remaining_days = 0

    if remaining_days < 0:
        sub.status = "Expired"
        db.session.commit()

    return render_template(
        "subscription.html",
        subscription=sub,
        remaining_days=max(remaining_days, 0)
    )


@subscription_bp.route("/select_plan", methods=["POST"])
def select_plan():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    selected_plan = request.form.get("plan")

    plan_prices = {"Basic": 499, "Premium": 999}

    if selected_plan not in plan_prices:
        return redirect("/subscription")

    sub = Subscription.query.filter_by(shop_id=shop_id).first()

    if not sub:
        return "Subscription not found"

    sub.plan = selected_plan
    db.session.commit()

    return redirect("/subscription")


@subscription_bp.route("/renew_subscription")
def renew_subscription():

    if "shop_id" not in session:
        return redirect("/login")

    shop_id = session["shop_id"]

    sub = Subscription.query.filter_by(shop_id=shop_id).first()

    if not sub:
        return "❌ Subscription not found"

    today = datetime.now().date()

    sub.start_date = today
    sub.expiry_date = today + timedelta(days=30)
    sub.status = "Active"
    sub.reminder_sent = False

    db.session.commit()

    return redirect("/dashboard")