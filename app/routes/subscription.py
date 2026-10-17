from datetime import datetime

from flask import Blueprint, render_template, session, redirect, request

from app import db
from app.models import Subscription, SubscriptionPayment
from app.utils.decorators import shop_session_required
from app.utils.plans import PLAN_PRICES
from app.utils import razorpay_utils as rzp

subscription_bp = Blueprint("subscription", __name__)


@subscription_bp.route("/subscription")
@shop_session_required
def subscription_page():

    shop_id = session["shop_id"]
    today = datetime.now().date()

    subscription = Subscription.query.filter_by(shop_id=shop_id).first()

    if not subscription:
        subscription = Subscription(
            shop_id=shop_id,
            plan="Basic",
            status="Expired",
            start_date=today,
            expiry_date=today
        )
        db.session.add(subscription)
        db.session.commit()

    remaining_days = 0
    if subscription.expiry_date:
        remaining_days = (subscription.expiry_date - today).days

    expired = remaining_days < 0

    if expired and subscription.status != "Expired":
        subscription.status = "Expired"
        db.session.commit()

    payments = (
        SubscriptionPayment.query
        .filter_by(shop_id=shop_id)
        .order_by(SubscriptionPayment.created_at.desc())
        .limit(10)
        .all()
    )

    if "csrf_token" not in session:
        import os
        session["csrf_token"] = os.urandom(32).hex()

    return render_template(
        "subscription.html",
        subscription=subscription,
        remaining_days=max(remaining_days, 0),
        expired=expired,
        payments=payments,
        csrf_token=session["csrf_token"],
        razorpay_ready=rzp.is_configured(),
        paid=request.args.get("paid") == "1",
        prices=PLAN_PRICES
    )


# Old free-change routes are disabled: plans are now paid online only.
@subscription_bp.route("/select_plan", methods=["GET", "POST"])
@subscription_bp.route("/renew_subscription", methods=["GET", "POST"])
def disabled_free_routes():
    return redirect("/subscription")
